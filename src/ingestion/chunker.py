"""Symbol-level chunker transforming AST symbol nodes into enriched retrieval chunks.

Chunks source code by symbol (function, class, method) rather than fixed token length,
and populates comprehensive compliance and security metadata on each chunk.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.config import settings
from src.ingestion.ast_parser import CodebaseASTParser, ParsedModule, SymbolNode


class CodeChunk(BaseModel):
    """Enriched code chunk containing symbol code and 12+ metadata attributes."""

    # Mandatory RAG & compliance metadata
    doc_id: str  # Format: {file_path}::{symbol_name}
    tenant_id: str = Field(default_factory=lambda: settings.default_tenant_id)
    version_tag: str = "v1.0.0"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    security_level: str  # "public", "internal", "confidential", "restricted"
    jurisdiction: str = "PK"  # State Bank of Pakistan compliance
    source_authority: str = "SBP-Fintech-Core"
    symbol_name: str
    symbol_type: str  # "function", "async_function", "class", "method", "async_method"
    start_line: int
    end_line: int
    file_path: str

    # Retrieval and Graph attributes
    decorators: List[str] = Field(default_factory=list)
    calls: List[str] = Field(default_factory=list)
    parameters: List[str] = Field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    content: str  # Raw code snippet
    search_text: str  # Formatted text used for dense/BM25 indexing

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Convert chunk metadata to flat dictionary suitable for Vector DB and BM25 filters."""
        return {
            "doc_id": self.doc_id,
            "tenant_id": self.tenant_id,
            "version_tag": self.version_tag,
            "timestamp": self.timestamp,
            "security_level": self.security_level,
            "jurisdiction": self.jurisdiction,
            "source_authority": self.source_authority,
            "symbol_name": self.symbol_name,
            "symbol_type": self.symbol_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "file_path": self.file_path,
            "decorators": ",".join(self.decorators),
            "calls": ",".join(self.calls),
        }


class SymbolChunker:
    """Chunks Python codebase by AST symbols and applies security classifications."""

    def __init__(self, parser: Optional[CodebaseASTParser] = None) -> None:
        self.parser = parser or CodebaseASTParser()

    def determine_security_level(self, file_path: str, raw_code: str = "") -> str:
        """Determine security classification based on path rules and docstring markers."""
        norm_path = file_path.replace("\\", "/").lower()

        # Check explicit code markers first
        if "security_level: restricted" in raw_code.lower():
            return "restricted"
        if "security_level: confidential" in raw_code.lower():
            return "confidential"

        # Check configured security path rules
        for pattern, level in settings.security_path_rules.items():
            if pattern.lower() in norm_path:
                return level

        return "internal"

    def _build_search_text(self, symbol: SymbolNode, file_path: str) -> str:
        """Create enriched textual representation for dense and keyword retrieval."""
        parts = [
            f"FILE: {file_path}",
            f"SYMBOL: {symbol.name} ({symbol.symbol_type})",
            f"LINES: {symbol.start_line}-{symbol.end_line}",
        ]
        if symbol.decorators:
            parts.append(f"DECORATORS: {', '.join(symbol.decorators)}")
        if symbol.parameters:
            parts.append(f"PARAMETERS: {', '.join(symbol.parameters)}")
        if symbol.return_type:
            parts.append(f"RETURN TYPE: {symbol.return_type}")
        if symbol.docstring:
            parts.append(f"DOCSTRING: {symbol.docstring}")
        if symbol.calls:
            parts.append(f"CALLS: {', '.join(symbol.calls)}")
        parts.append(f"CODE:\n{symbol.code_snippet}")
        return "\n".join(parts)

    def chunk_module(self, parsed_module: ParsedModule) -> List[CodeChunk]:
        """Convert a ParsedModule into a list of CodeChunks, one per symbol."""
        security_level = self.determine_security_level(parsed_module.file_path, parsed_module.raw_code)
        chunks: List[CodeChunk] = []

        for symbol in parsed_module.symbols:
            doc_id = f"{parsed_module.file_path}::{symbol.name}"
            search_text = self._build_search_text(symbol, parsed_module.file_path)

            chunk = CodeChunk(
                doc_id=doc_id,
                tenant_id=settings.default_tenant_id,
                version_tag="v1.0.0",
                security_level=security_level,
                jurisdiction="PK",
                source_authority="SBP-Fintech-Core",
                symbol_name=symbol.name,
                symbol_type=symbol.symbol_type,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                file_path=parsed_module.file_path,
                decorators=symbol.decorators,
                calls=symbol.calls,
                parameters=symbol.parameters,
                return_type=symbol.return_type,
                docstring=symbol.docstring,
                content=symbol.code_snippet,
                search_text=search_text,
            )
            chunks.append(chunk)

        return chunks

    def chunk_file(self, file_path: Path, base_dir: Optional[Path] = None) -> List[CodeChunk]:
        """Parse and chunk a single Python source file."""
        parsed = self.parser.parse_file(file_path, base_dir=base_dir)
        return self.chunk_module(parsed)

    def chunk_directory(self, directory: Path, base_dir: Optional[Path] = None) -> List[CodeChunk]:
        """Recursively chunk all Python files in a directory."""
        dir_path = Path(directory)
        base = base_dir or dir_path
        all_chunks: List[CodeChunk] = []

        for py_path in sorted(dir_path.rglob("*.py")):
            # Skip hidden files or caches
            if "__pycache__" in py_path.parts or any(p.startswith(".") for p in py_path.parts):
                continue
            file_chunks = self.chunk_file(py_path, base_dir=base)
            all_chunks.extend(file_chunks)

        return all_chunks
