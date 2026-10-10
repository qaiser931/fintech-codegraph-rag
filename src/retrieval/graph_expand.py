"""RBAC-aware call-graph expansion.

Nodes above the caller's clearance are removed from the graph *view* before
traversal, so the walk can never visit them or pass through them.
"""

from collections import deque
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import networkx as nx

from src.security.rbac import rbac_manager


@dataclass(frozen=True)
class ExpandedNode:
    doc_id: str
    hop: int
    via: str
    direction: str  # "caller" or "callee"


def authorized_view(
    graph: nx.DiGraph,
    role: str,
    relations: Sequence[str] = ("calls",),
) -> nx.DiGraph:
    """Read-only view containing only nodes the role may see and the given edge types."""
    clearance = rbac_manager.get_clearance_for_role(role)

    def node_ok(n: str) -> bool:
        return str(graph.nodes[n].get("security_level", "")).lower() in clearance

    def edge_ok(u: str, v: str) -> bool:
        return graph.edges[u, v].get("relation") in relations

    return nx.subgraph_view(
        graph,
        filter_node=node_ok,
        filter_edge=edge_ok,
    )


def expand_call_graph(
    graph: nx.DiGraph,
    seed_ids: Iterable[str],
    role: str,
    hops: int = 2,
    direction: str = "both",
    relations: Sequence[str] = ("calls",),
) -> List[ExpandedNode]:
    """Breadth-first walk over callers/callees of the seeds, inside the authorized view."""
    view = authorized_view(graph, role, relations)
    seeds = [s for s in seed_ids if s in view]
    visited = set(seeds)
    queue = deque((s, 0) for s in seeds)
    found: List[ExpandedNode] = []

    while queue:
        node, hop = queue.popleft()
        if hop >= hops:
            continue

        steps = []

        if direction in ("in", "both"):
            steps += [(p, "caller") for p in view.predecessors(node)]

        if direction in ("out", "both"):
            steps += [(s, "callee") for s in view.successors(node)]

        for nxt, kind in sorted(steps):
            if nxt in visited:
                continue

            visited.add(nxt)
            found.append(
                ExpandedNode(
                    doc_id=nxt,
                    hop=hop + 1,
                    via=node,
                    direction=kind,
                )
            )
            queue.append((nxt, hop + 1))

    return found


def _add_call_order_edges(
    graph: nx.DiGraph,
    members: Sequence[str],
) -> nx.DiGraph:
    """Build an execution-aware graph from the full authorized graph.

    Normal ``calls`` edges describe caller -> callee relationships.
    ``call_order`` describes the order in which a caller invokes its callees.

    Consecutive callees are connected with temporary ``execution_order``
    edges. Only nodes present in ``members`` are included in the returned
    graph, while call-order metadata is read from the full graph.
    """
    member_set = set(members)

    execution_graph = graph.subgraph(member_set).copy()

    for caller in graph.nodes:
        if caller not in member_set:
            continue

        outgoing = [
            (target, data)
            for _, target, data in graph.out_edges(caller, data=True)
            if data.get("relation") == "calls"
            and data.get("call_order") is not None
            and target in member_set
        ]

        outgoing.sort(
            key=lambda item: (
                int(item[1].get("call_order", 10**9)),
                str(item[0]),
            )
        )

        for (first, first_data), (second, second_data) in zip(
            outgoing,
            outgoing[1:],
        ):
            first_order = first_data.get("call_order")
            second_order = second_data.get("call_order")

            if first_order is None or second_order is None:
                continue

            if first == second:
                continue

            execution_graph.add_edge(
                first,
                second,
                relation="execution_order",
                call_order=second_order,
                via_caller=caller,
            )

    return execution_graph


def find_execution_paths(
    graph: nx.DiGraph,
    node_ids: Iterable[str],
    role: str,
    max_paths: int = 5,
    relations: Sequence[str] = ("calls",),
    root_ids: Iterable[str] | None = None,
) -> List[List[str]]:
    """Find execution-aware entry-to-leaf paths.

    The path preserves normal caller -> callee relationships and follows
    call-order edges when they represent sequential calls inside the same
    function.
    """
    view = authorized_view(graph, role, relations)

    members = [
        node
        for node in dict.fromkeys(node_ids)
        if node in view
    ]

    if not members:
        return []

    roots = {
        node
        for node in (root_ids or [])
        if node in members
    }

    if not members:
        return []

    execution_graph = _add_call_order_edges(view, members)

    # Add normal caller -> callee edges from the authorized graph.
    # These are required to connect route -> service -> first sequential call.
    for caller in members:
        for _, callee, data in view.out_edges(caller, data=True):
            if (
                data.get("relation") in relations
                and callee in members
            ):
                execution_graph.add_edge(
                    caller,
                    callee,
                    relation="calls",
                )

    if roots:
        entries = sorted(roots)
    else:
        entries = [
            node
            for node in members
            if (
                graph.nodes[node].get("is_route_entry")
                or any(
                    predecessor not in members
                    for predecessor in view.predecessors(node)
                )
                or execution_graph.in_degree(node) == 0
            )
        ]

        if not entries:
            entries = [
                node
                for node in members
                if execution_graph.in_degree(node) == 0
        ]

    paths: List[List[str]] = []

    for entry in sorted(set(entries)):
        # DFS gives us the longest execution-aware path rather than the
        # shortest path, which would skip intermediate ordered calls.
        stack: List[tuple[str, List[str], str | None]] = [
            (entry, [entry], None)
        ]

        while stack:
            current, path, active_caller = stack.pop()

            successors = sorted(
                execution_graph.successors(current),
                key=lambda node: (
                    0
                    if execution_graph.edges[current, node].get("relation")
                    == "execution_order"
                    else 1,
                    execution_graph.edges[current, node].get(
                        "call_order",
                        10**9,
                    ),
                    str(node),
                ),
                reverse=True,
            )

            extended = False

            for successor in successors:
                if successor in path:
                    continue

                edge_data = execution_graph.edges[current, successor]
                relation = edge_data.get("relation")
                if (
                    relation == "execution_order"
                    and edge_data.get("via_caller") != active_caller
                ):
                    continue

                extended = True
                next_caller = current if relation == "calls" else active_caller
                stack.append(
                    (
                        successor,
                        path + [successor],
                        next_caller,
                    )
                )

            if not extended and len(path) > 1:
                if path not in paths:
                    paths.append(path)

    paths.sort(
        key=lambda path: (
            -len(path),
            path,
        )
    )

    return paths[:max_paths]