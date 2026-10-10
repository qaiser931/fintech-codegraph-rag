"""Dependency Call Graph Builder for Codebase Symbols using NetworkX.

Constructs a directed dependency graph where:
- Nodes represent code symbols (functions, methods, classes) with rich metadata.
- Edges represent relationships: 'calls', 'member_of', 'route_to_handler', and 'imports'.
- Call edges preserve source-code call order through the ``call_order`` attribute.

Provides serialization to disk and execution path resolution.
"""

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from src.config import settings
from src.ingestion.ast_parser import CodebaseASTParser, ParsedModule
from src.ingestion.chunker import CodeChunk, SymbolChunker


class DependencyGraphBuilder:
    """Builds, persists, and queries a directed symbol dependency call graph."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.symbol_chunker = SymbolChunker()
        self.ast_parser = self.symbol_chunker.parser

        # Lookup indices for symbol resolution.
        self.doc_id_to_node: Dict[str, str] = {}
        self.name_to_nodes: Dict[str, List[str]] = {}
        self.short_name_to_nodes: Dict[str, List[str]] = {}

    @staticmethod
    def _normalized_file_path(file_path: str) -> str:
        return PurePosixPath(file_path.replace("\\", "/")).as_posix()

    @classmethod
    def _module_name_from_file(cls, file_path: str) -> str:
        source_path = PurePosixPath(cls._normalized_file_path(file_path))
        if source_path.suffix != ".py":
            return ""
        parts = list(source_path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def _parse_modules_for_file_paths(
        self,
        file_paths: List[str],
        base_dir: Optional[Path] = None,
    ) -> List[ParsedModule]:
        root = Path(base_dir or settings.base_dir).resolve()
        parsed_modules: List[ParsedModule] = []

        for file_path in sorted(
            {self._normalized_file_path(file_path) for file_path in file_paths}
        ):
            source_path = Path(file_path)
            if not source_path.is_absolute():
                source_path = root / source_path
            source_path = source_path.resolve()
            if not source_path.is_file():
                continue
            try:
                parsed_modules.append(
                    self.ast_parser.parse_file(source_path, base_dir=root)
                )
            except (OSError, SyntaxError, ValueError):
                continue

        return parsed_modules

    def _parse_modules_for_chunks(
        self,
        chunks: List[CodeChunk],
        base_dir: Optional[Path] = None,
    ) -> List[ParsedModule]:
        return self._parse_modules_for_file_paths(
            [chunk.file_path for chunk in chunks],
            base_dir=base_dir,
        )

    @staticmethod
    def _resolve_import_module(
        parsed_module: ParsedModule,
        import_statement,
    ) -> str:
        if not import_statement.level:
            return import_statement.module

        current_module = DependencyGraphBuilder._module_name_from_file(
            parsed_module.file_path
        )
        package_parts = current_module.split(".")[:-1]
        parents_to_remove = import_statement.level - 1
        if parents_to_remove > len(package_parts):
            return ""
        if parents_to_remove:
            package_parts = package_parts[:-parents_to_remove]
        if import_statement.module:
            package_parts.extend(import_statement.module.split("."))
        return ".".join(package_parts)

    def _add_import_edges(self, parsed_modules: List[ParsedModule]) -> None:
        module_files: Dict[str, List[str]] = {}
        nodes_by_file: Dict[str, List[str]] = {}

        for parsed_module in parsed_modules:
            file_path = self._normalized_file_path(parsed_module.file_path)
            module_name = self._module_name_from_file(file_path)
            if module_name:
                module_files.setdefault(module_name, []).append(file_path)

        for node_id, attributes in self.graph.nodes(data=True):
            file_path = self._normalized_file_path(attributes.get("file_path", ""))
            nodes_by_file.setdefault(file_path, []).append(node_id)

        for files in module_files.values():
            files.sort()
        for nodes in nodes_by_file.values():
            nodes.sort()

        def module_nodes(module_name: str) -> List[str]:
            return [
                node_id
                for file_path in module_files.get(module_name, [])
                for node_id in nodes_by_file.get(file_path, [])
            ]

        for parsed_module in sorted(
            parsed_modules,
            key=lambda item: self._normalized_file_path(item.file_path),
        ):
            source_nodes = nodes_by_file.get(
                self._normalized_file_path(parsed_module.file_path),
                [],
            )
            if not source_nodes:
                continue

            imports = sorted(
                parsed_module.imports,
                key=lambda item: (
                    item.line_number,
                    item.module,
                    item.imported_name,
                    item.alias or "",
                    item.level,
                ),
            )
            for import_statement in imports:
                imported_module = self._resolve_import_module(
                    parsed_module,
                    import_statement,
                )
                if not imported_module:
                    continue

                if not import_statement.is_from_import:
                    target_nodes = module_nodes(imported_module)
                elif import_statement.imported_name == "*":
                    target_nodes = module_nodes(imported_module)
                else:
                    module_file_set = set(module_files.get(imported_module, []))
                    target_nodes = [
                        node_id
                        for node_id in self.short_name_to_nodes.get(
                            import_statement.imported_name,
                            [],
                        )
                        if self._normalized_file_path(
                            self.graph.nodes[node_id].get("file_path", "")
                        )
                        in module_file_set
                    ]
                    if not target_nodes:
                        target_nodes = module_nodes(
                            f"{imported_module}.{import_statement.imported_name}"
                        )
                    if not target_nodes:
                        target_nodes = module_nodes(imported_module)

                if not target_nodes:
                    continue

                reference = {
                    "module": imported_module,
                    "name": import_statement.imported_name,
                    "alias": import_statement.alias,
                    "line_number": import_statement.line_number,
                }
                for source_node in source_nodes:
                    for target_node in target_nodes:
                        if source_node == target_node:
                            continue
                        edge = self.graph.get_edge_data(source_node, target_node)
                        if edge is not None:
                            references = edge.setdefault("import_references", [])
                            if reference not in references:
                                references.append(reference)
                                references.sort(
                                    key=lambda item: (
                                        item["line_number"],
                                        item["module"],
                                        item["name"],
                                        item["alias"] or "",
                                    )
                                )
                            continue

                        self.graph.add_edge(
                            source_node,
                            target_node,
                            relation="imports",
                            import_references=[reference],
                        )

    def build_from_chunks(
        self,
        chunks: List[CodeChunk],
        parsed_modules: Optional[List[ParsedModule]] = None,
    ) -> nx.DiGraph:
        """Construct the NetworkX graph from a list of CodeChunks.

        Args:
            chunks: List of CodeChunk objects extracted from AST.
            parsed_modules: Optional list of ParsedModules for import-level
                resolution.

        Returns:
            Populated networkx.DiGraph instance.
        """
        if parsed_modules is None:
            parsed_modules = self._parse_modules_for_chunks(chunks)

        self.graph.clear()
        self.doc_id_to_node.clear()
        self.name_to_nodes.clear()
        self.short_name_to_nodes.clear()

        # ------------------------------------------------------------------
        # Phase A: Add all symbol nodes.
        # ------------------------------------------------------------------
        for chunk in chunks:
            node_id = chunk.doc_id

            self.graph.add_node(
                node_id,
                doc_id=chunk.doc_id,
                symbol_name=chunk.symbol_name,
                short_name=chunk.symbol_name.split(".")[-1],
                symbol_type=chunk.symbol_type,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                security_level=chunk.security_level,
                jurisdiction=chunk.jurisdiction,
                tenant_id=chunk.tenant_id,
                source_authority=chunk.source_authority,
                decorators=chunk.decorators,
                parameters=chunk.parameters,
                calls=chunk.calls,
                content=chunk.content,
                search_text=chunk.search_text,
            )

            # Populate fast lookup tables.
            self.doc_id_to_node[node_id] = node_id

            full_name = chunk.symbol_name
            self.name_to_nodes.setdefault(full_name, []).append(node_id)

            short_name = full_name.split(".")[-1]
            self.short_name_to_nodes.setdefault(short_name, []).append(node_id)

        # ------------------------------------------------------------------
        # Phase B: Add structural edges.
        # ------------------------------------------------------------------
        for chunk in chunks:
            if "." in chunk.symbol_name and chunk.symbol_type in [
                "method",
                "async_method",
            ]:
                parent_class_name = chunk.symbol_name.split(".")[0]

                parent_candidates = [
                    nid
                    for nid in self.name_to_nodes.get(parent_class_name, [])
                    if self.graph.nodes[nid]["file_path"] == chunk.file_path
                ]

                for p_node in parent_candidates:
                    self.graph.add_edge(
                        p_node,
                        chunk.doc_id,
                        relation="member_of",
                    )

        # ------------------------------------------------------------------
        # Phase C: Add invocation edges.
        #
        # IMPORTANT:
        # ``chunk.calls`` preserves the source-code order produced by the
        # AST parser/chunker. We preserve that order as ``call_order`` on
        # every call edge.
        # ------------------------------------------------------------------
        for chunk in chunks:
            caller_node_id = chunk.doc_id

            for call_order, call_expr in enumerate(chunk.calls, start=1):
                resolved_callees = self._resolve_call_target(
                    call_expr,
                    chunk.file_path,
                )

                for callee_node_id in resolved_callees:
                    if caller_node_id != callee_node_id:
                        self.graph.add_edge(
                            caller_node_id,
                            callee_node_id,
                            relation="calls",
                            call_expr=call_expr,
                            call_order=call_order,
                        )

        # ------------------------------------------------------------------
        # Phase D: Connect route decorators if present.
        # ------------------------------------------------------------------
        for chunk in chunks:
            for dec in chunk.decorators:
                if any(
                    kw in dec
                    for kw in [
                        "router.post",
                        "router.get",
                        "router.put",
                        "router.delete",
                    ]
                ):
                    self.graph.nodes[chunk.doc_id]["is_route_entry"] = True
                    self.graph.nodes[chunk.doc_id]["route_signature"] = dec

        self._add_import_edges(parsed_modules)

        return self.graph

    def _disambiguate(
        self,
        candidates: List[str],
        receiver_parts: List[str],
        caller_file_path: str,
    ) -> List[str]:
        """Pick the best candidates when one method name exists on several classes."""
        keys: Set[str] = set()

        for text in list(receiver_parts) + [Path(caller_file_path).stem]:
            for piece in re.split(r"[_\W]+", text.lower()):
                if len(piece) > 3:
                    keys.add(piece)

        def score(node_id: str) -> int:
            attrs = self.graph.nodes[node_id]
            owner = attrs["symbol_name"].split(".")[0]

            haystack = (
                owner + Path(attrs["file_path"]).stem
            ).lower().replace("_", "")

            return sum(
                1
                for key in keys
                if key in haystack
            )

        best = max(score(c) for c in candidates)

        if best == 0:
            return candidates

        return [
            candidate
            for candidate in candidates
            if score(candidate) == best
        ]

    def _resolve_call_target(
        self,
        call_expr: str,
        caller_file_path: str,
    ) -> List[str]:
        """Resolve a call expression string to node IDs."""

        # 1. Exact full-name match.
        if call_expr in self.name_to_nodes:
            return self.name_to_nodes[call_expr]

        # 2. Method on an object.
        if "." in call_expr:
            parts = call_expr.split(".")
            leaf_method = parts[-1]

            receiver = [
                part
                for part in parts[:-1]
                if part not in ("self", "cls")
            ]

            candidates = self.short_name_to_nodes.get(
                leaf_method,
                [],
            )

            if len(candidates) > 1:
                candidates = self._disambiguate(
                    candidates,
                    receiver,
                    caller_file_path,
                )

            if candidates:
                return candidates

        # 3. Plain function name.
        if call_expr in self.short_name_to_nodes:
            candidates = self.short_name_to_nodes[call_expr]

            same_file = [
                candidate
                for candidate in candidates
                if self.graph.nodes[candidate]["file_path"]
                == caller_file_path
            ]

            return same_file if same_file else candidates

        return []

    def build_from_directory(
        self,
        directory: Path,
        base_dir: Optional[Path] = None,
    ) -> nx.DiGraph:
        """Chunk an entire directory and construct the graph."""
        chunks = self.symbol_chunker.chunk_directory(
            directory,
            base_dir=base_dir,
        )

        return self.build_from_chunks(chunks)

    def save_graph(
        self,
        file_path: Optional[Path] = None,
    ) -> Path:
        """Serialize NetworkX graph to JSON."""
        target_path = Path(
            file_path or settings.graph_store_path
        )

        target_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = nx.node_link_data(self.graph)

        with open(
            target_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                data,
                f,
                indent=2,
            )

        return target_path

    def load_graph(
        self,
        file_path: Optional[Path] = None,
    ) -> nx.DiGraph:
        """Load NetworkX graph from persisted JSON."""
        target_path = Path(
            file_path or settings.graph_store_path
        )

        if not target_path.exists():
            raise FileNotFoundError(
                f"Graph file not found at {target_path}"
            )

        with open(
            target_path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        self.graph = nx.node_link_graph(
            data,
            directed=True,
        )

        # Rebuild lookup tables.
        self.doc_id_to_node.clear()
        self.name_to_nodes.clear()
        self.short_name_to_nodes.clear()

        for node_id, attrs in self.graph.nodes(data=True):
            self.doc_id_to_node[node_id] = node_id

            symbol_name = attrs.get(
                "symbol_name",
                "",
            )

            self.name_to_nodes.setdefault(
                symbol_name,
                [],
            ).append(node_id)

            short_name = symbol_name.split(".")[-1]

            self.short_name_to_nodes.setdefault(
                short_name,
                [],
            ).append(node_id)

        parsed_modules = self._parse_modules_for_file_paths(
            [
                attrs.get("file_path", "")
                for _, attrs in self.graph.nodes(data=True)
            ]
        )
        self._add_import_edges(parsed_modules)

        return self.graph

    def _call_successors_in_source_order(
        self,
        node_id: str,
    ) -> List[str]:
        """Return direct call successors ordered by source-code call order.

        Only ``calls`` edges are considered. Structural relationships such as
        ``member_of`` are intentionally excluded.
        """
        successors: List[Tuple[int, str]] = []

        for target in self.graph.successors(node_id):
            edge_data = self.graph.get_edge_data(
                node_id,
                target,
            ) or {}

            if edge_data.get("relation") != "calls":
                continue

            call_order = edge_data.get(
                "call_order",
                10**9,
            )

            try:
                numeric_order = int(call_order)
            except (TypeError, ValueError):
                numeric_order = 10**9

            successors.append(
                (
                    numeric_order,
                    target,
                )
            )

        successors.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        return [
            target
            for _, target in successors
        ]

    def find_execution_path(
        self,
        source_pattern: str,
        target_pattern: str,
    ) -> Optional[List[str]]:
        """Find an execution-aware path between two symbol patterns.

        The dependency graph represents calls from a function to each of its
        callees. When multiple calls occur inside the same function, those
        calls are siblings in the dependency graph. ``call_order`` is used
        here to preserve their source-code execution ordering.

        This method first tries the normal directed shortest path. If that
        path exists, it is returned. This preserves the original behavior.

        For a sequence of sibling calls inside a caller, the method can also
        construct an execution sequence such as:

            handler
            -> process_callback
            -> acquire_lock
            -> verify_switch_transaction

        even though ``acquire_lock`` and ``verify_switch_transaction`` are
        sibling dependency nodes.
        """
        source_nodes = [
            node_id
            for node_id, data in self.graph.nodes(data=True)
            if source_pattern in data.get(
                "symbol_name",
                "",
            )
        ]

        target_nodes = [
            node_id
            for node_id, data in self.graph.nodes(data=True)
            if target_pattern in data.get(
                "symbol_name",
                "",
            )
        ]

        if not source_nodes or not target_nodes:
            return None

        call_graph = nx.subgraph_view(
            self.graph,
            filter_edge=lambda source, target: self.graph.edges[
                source,
                target,
            ].get("relation") != "imports",
        )

        # --------------------------------------------------------------
        # 1. Preserve the original graph shortest-path behavior.
        # --------------------------------------------------------------
        shortest_path: Optional[List[str]] = None

        for source in source_nodes:
            for target in target_nodes:
                try:
                    if nx.has_path(
                        call_graph,
                        source,
                        target,
                    ):
                        path = nx.shortest_path(
                            call_graph,
                            source,
                            target,
                        )

                        if (
                            shortest_path is None
                            or len(path) < len(shortest_path)
                        ):
                            shortest_path = path

                except nx.NetworkXNoPath:
                    continue

        if shortest_path is not None:
            # Check whether the path contains a caller with ordered sibling
            # calls that can explain the target more accurately.
            expanded = self._expand_execution_sequence(
                shortest_path
            )

            if expanded is not None:
                return expanded

            return shortest_path

        # --------------------------------------------------------------
        # 2. If no normal directed path exists, search for an execution
        #    sequence composed from ordered sibling calls.
        # --------------------------------------------------------------
        for source in source_nodes:
            for target in target_nodes:
                sequence = self._find_ordered_execution_sequence(
                    source,
                    target,
                )

                if sequence is not None:
                    return sequence

        return None

    def _expand_execution_sequence(
        self,
        path: List[str],
    ) -> Optional[List[str]]:
        """Expand a normal graph path using ordered sibling calls.

        Example:

            A -> B -> C

        If B calls X before C in source order, return:

            A -> B -> X -> C

        This is particularly useful for database-lock followed by external
        network-call sequences.
        """
        if len(path) < 3:
            return None

        expanded = list(path)

        for index in range(1, len(path) - 1):
            caller = path[index]
            next_node = path[index + 1]

            ordered_calls = self._call_successors_in_source_order(
                caller
            )

            if next_node not in ordered_calls:
                continue

            next_position = ordered_calls.index(next_node)

            if next_position == 0:
                continue

            # Insert the ordered sibling calls that occur immediately before
            # the existing next node.
            preceding = ordered_calls[:next_position]

            # Avoid duplicating nodes already present in the path.
            insertion = [
                node
                for node in preceding
                if node not in expanded
            ]

            if insertion:
                insert_at = expanded.index(next_node)

                expanded[
                    insert_at:insert_at
                ] = insertion

                return expanded

        return None

    def _find_ordered_execution_sequence(
        self,
        source: str,
        target: str,
    ) -> Optional[List[str]]:
        """Find an execution sequence using ordered sibling calls.

        This searches recursively through call relationships while allowing
        source-order sibling transitions inside a caller.
        """
        visited: Set[Tuple[str, str]] = set()

        def search(
            current: str,
            goal: str,
            prefix: List[str],
            depth: int,
        ) -> Optional[List[str]]:
            if depth > 6:
                return None

            state = (current, goal)

            if state in visited:
                return None

            visited.add(state)

            if current == goal:
                return prefix

            direct_calls = self._call_successors_in_source_order(
                current
            )

            # First try ordinary child traversal.
            for child in direct_calls:
                if child in prefix:
                    continue

                result = search(
                    child,
                    goal,
                    prefix + [child],
                    depth + 1,
                )

                if result is not None:
                    return result

            return None

        return search(
            source,
            target,
            [source],
            0,
        )

    def expand_subgraph(
        self,
        seed_node_ids: List[str],
        hops: int = 2,
        direction: str = "both",
    ) -> List[Dict[str, Any]]:
        """Expand outward from seed nodes to retrieve multi-hop context.

        Args:
            seed_node_ids: List of starting node doc_ids.
            hops: Max depth of traversal (1-3 hops).
            direction: 'out' (callees), 'in' (callers), or 'both'.

        Returns:
            List of expanded node metadata dictionaries.
        """
        visited: Set[str] = set()

        queue: List[Tuple[str, int]] = [
            (node_id, 0)
            for node_id in seed_node_ids
            if node_id in self.graph
        ]

        for node_id, _ in queue:
            visited.add(node_id)

        index = 0

        while index < len(queue):
            current_id, current_hop = queue[index]
            index += 1

            if current_hop >= hops:
                continue

            neighbors: Set[str] = set()

            if direction in ["out", "both"]:
                neighbors.update(
                    neighbor
                    for neighbor in self.graph.successors(current_id)
                    if self.graph.edges[current_id, neighbor].get("relation")
                    != "imports"
                )

            if direction in ["in", "both"]:
                neighbors.update(
                    neighbor
                    for neighbor in self.graph.predecessors(current_id)
                    if self.graph.edges[neighbor, current_id].get("relation")
                    != "imports"
                )

            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(
                        (
                            neighbor,
                            current_hop + 1,
                        )
                    )

        result: List[Dict[str, Any]] = []

        for node_id in visited:
            node_data = dict(
                self.graph.nodes[node_id]
            )

            node_data["id"] = node_id

            result.append(node_data)

        return result

    def format_path_summary(
        self,
        path_node_ids: List[str],
    ) -> str:
        """Format an execution path as a human-readable arrow chain."""
        chain: List[str] = []

        for node_id in path_node_ids:
            symbol_name = self.graph.nodes[node_id].get(
                "symbol_name",
                node_id,
            )

            chain.append(symbol_name)

        return " -> ".join(chain)