"""AST-based Python source code parser and symbol extractor.

Extracts symbols (functions, classes, methods), imports, decorators,
and call relationships directly from Python's Abstract Syntax Tree (AST).
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ImportStatement:
    """Represents an imported module or symbol."""
    module: str
    imported_name: str
    alias: Optional[str] = None
    is_from_import: bool = False
    line_number: int = 1
    level: int = 0


@dataclass
class SymbolNode:
    """Represents a code symbol extracted from an AST."""
    name: str  # e.g. "PaymentService.process_jazzcash_callback"
    short_name: str  # e.g. "process_jazzcash_callback"
    symbol_type: str  # "function", "async_function", "class", "method", "async_method"
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    calls: List[str] = field(default_factory=list)  # Symbols called within this scope
    code_snippet: str = ""
    parent_symbol: Optional[str] = None


@dataclass
class ParsedModule:
    """Represents an entire parsed Python file."""
    file_path: str
    raw_code: str
    imports: List[ImportStatement] = field(default_factory=list)
    symbols: List[SymbolNode] = field(default_factory=list)
    top_level_calls: List[str] = field(default_factory=list)


class CallVisitor(ast.NodeVisitor):
    """Visitor collecting all function and method invocations within an AST subtree."""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        call_name = self._resolve_call_name(func)
        if call_name:
            self.calls.append(call_name)
        self.generic_visit(node)

    def _resolve_call_name(self, node: ast.AST) -> Optional[str]:
        """Convert AST call target node to readable string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val_str = self._resolve_call_name(node.value)
            if val_str:
                return f"{val_str}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Call):
            # Chained call e.g. foo().bar()
            return self._resolve_call_name(node.func)
        return None


class CodebaseASTParser:
    """Parses Python source files and extracts structured symbol metadata."""

    def parse_file(self, file_path: Path, base_dir: Optional[Path] = None) -> ParsedModule:
        """Parse a single Python file into a ParsedModule.

        Args:
            file_path: Absolute or relative path to the Python file.
            base_dir: Optional base directory to calculate relative path.

        Returns:
            ParsedModule containing extracted symbols, imports, and calls.
        """
        path_obj = Path(file_path).resolve()
        raw_code = path_obj.read_text(encoding="utf-8", errors="replace")
        rel_path = str(path_obj.relative_to(base_dir)) if base_dir and path_obj.is_relative_to(base_dir) else str(path_obj)
        # Normalize Windows backslashes for cross-platform consistency
        rel_path = rel_path.replace("\\", "/")

        return self.parse_source(raw_code, rel_path)

    def parse_source(self, source_code: str, file_path: str) -> ParsedModule:
        """Parse source code string into ParsedModule."""
        tree = ast.parse(source_code, filename=file_path)
        lines = source_code.splitlines()

        parsed = ParsedModule(file_path=file_path, raw_code=source_code)
        parsed.imports = self._extract_imports(tree)

        # Extract top-level symbols and nested methods
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parsed.symbols.append(self._parse_function(node, lines, file_path, parent=None))
            elif isinstance(node, ast.ClassDef):
                cls_symbol, method_symbols = self._parse_class(node, lines, file_path)
                parsed.symbols.append(cls_symbol)
                parsed.symbols.extend(method_symbols)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call_visitor = CallVisitor()
                call_visitor.visit(node.value)
                parsed.top_level_calls.extend(call_visitor.calls)

        return parsed

    def _extract_imports(self, tree: ast.AST) -> List[ImportStatement]:
        """Extract all import statements."""
        imports: List[ImportStatement] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportStatement(
                            module=alias.name,
                            imported_name=alias.name,
                            alias=alias.asname,
                            is_from_import=False,
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(
                        ImportStatement(
                            module=module,
                            imported_name=alias.name,
                            alias=alias.asname,
                            is_from_import=True,
                            line_number=node.lineno,
                            level=node.level,
                        )
                    )
        return imports

    def _get_snippet(self, lines: List[str], start_line: int, end_line: int) -> str:
        """Slice raw lines corresponding to start_line and end_line (1-indexed)."""
        clamped_start = max(1, start_line)
        clamped_end = min(len(lines), end_line)
        return "\n".join(lines[clamped_start - 1 : clamped_end])

    def _extract_decorators(self, decorator_list: List[ast.expr]) -> List[str]:
        """Extract string representation of decorators."""
        decorators = []
        for dec in decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
                elif isinstance(dec, ast.Attribute):
                    decorators.append(dec.attr)
        return decorators

    def _extract_parameters(self, args: ast.arguments) -> List[str]:
        """Extract parameter names."""
        params = [arg.arg for arg in args.posonlyargs + args.args]
        if args.vararg:
            params.append(f"*{args.vararg.arg}")
        params.extend([arg.arg for arg in args.kwonlyargs])
        if args.kwarg:
            params.append(f"**{args.kwarg.arg}")
        return params

    def _extract_calls(self, node: ast.AST) -> List[str]:
        """Extract all function/method calls inside a node."""
        visitor = CallVisitor()
        visitor.visit(node)
        # Deduplicate while preserving order
        seen: Set[str] = set()
        deduped: List[str] = []
        for c in visitor.calls:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        return deduped

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: List[str],
        file_path: str,
        parent: Optional[str] = None,
    ) -> SymbolNode:
        """Parse standalone function or class method."""
        is_async = isinstance(node, ast.AsyncFunctionDef)
        if parent:
            sym_type = "async_method" if is_async else "method"
            qualified_name = f"{parent}.{node.name}"
        else:
            sym_type = "async_function" if is_async else "function"
            qualified_name = node.name

        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node)
        decorators = self._extract_decorators(node.decorator_list)
        parameters = self._extract_parameters(node.args)
        return_type = ast.unparse(node.returns) if node.returns else None
        calls = self._extract_calls(node)
        code_snippet = self._get_snippet(lines, start_line, end_line)

        return SymbolNode(
            name=qualified_name,
            short_name=node.name,
            symbol_type=sym_type,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            decorators=decorators,
            parameters=parameters,
            return_type=return_type,
            calls=calls,
            code_snippet=code_snippet,
            parent_symbol=parent,
        )

    def _parse_class(
        self, node: ast.ClassDef, lines: List[str], file_path: str
    ) -> Tuple[SymbolNode, List[SymbolNode]]:
        """Parse class declaration and its constituent methods."""
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node)
        decorators = self._extract_decorators(node.decorator_list)
        code_snippet = self._get_snippet(lines, start_line, end_line)
        calls = self._extract_calls(node)

        class_symbol = SymbolNode(
            name=node.name,
            short_name=node.name,
            symbol_type="class",
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            decorators=decorators,
            calls=calls,
            code_snippet=code_snippet,
            parent_symbol=None,
        )

        methods: List[SymbolNode] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._parse_function(item, lines, file_path, parent=node.name))

        return class_symbol, methods
