"""Unit tests for Phase 2: AST parser, symbol extractor, and symbol-level chunker."""

from pathlib import Path
import pytest
from src.config import settings
from src.ingestion.ast_parser import CodebaseASTParser, SymbolNode
from src.ingestion.chunker import CodeChunk, SymbolChunker


@pytest.fixture
def parser() -> CodebaseASTParser:
    return CodebaseASTParser()


@pytest.fixture
def chunker() -> SymbolChunker:
    return SymbolChunker()


def test_ast_parser_extracts_function_symbols_and_decorators(parser: CodebaseASTParser) -> None:
    """Test extracting route decorators, parameters, and calls from jazzcash_callback.py."""
    route_file = settings.sample_codebase_dir / "api" / "routes" / "jazzcash_callback.py"
    parsed = parser.parse_file(route_file, base_dir=settings.base_dir)

    assert len(parsed.symbols) > 0
    route_symbol = next((s for s in parsed.symbols if s.short_name == "handle_jazzcash_callback"), None)
    assert route_symbol is not None
    assert route_symbol.symbol_type == "async_function"
    assert any("router.post" in d for d in route_symbol.decorators)
    assert "request" in route_symbol.parameters

    # Verify calls extracted within handle_jazzcash_callback
    call_names = route_symbol.calls
    assert any("verify_webhook_signature" in c for c in call_names)
    assert any("process_jazzcash_callback" in c for c in call_names)
    assert any("send_payment_sms_alert" in c for c in call_names)


def test_ast_parser_extracts_class_and_methods(parser: CodebaseASTParser) -> None:
    """Test extracting class and method hierarchies from payment_service.py."""
    service_file = settings.sample_codebase_dir / "services" / "payment_service.py"
    parsed = parser.parse_file(service_file, base_dir=settings.base_dir)

    class_sym = next((s for s in parsed.symbols if s.name == "PaymentService"), None)
    assert class_sym is not None
    assert class_sym.symbol_type == "class"

    method_sym = next((s for s in parsed.symbols if s.name == "PaymentService.process_jazzcash_callback"), None)
    assert method_sym is not None
    assert method_sym.symbol_type == "method"
    assert method_sym.parent_symbol == "PaymentService"

    # Verify planted execution call chain targets
    calls = method_sym.calls
    assert any("acquire_account_lock" in c for c in calls)
    assert any("verify_switch_transaction" in c for c in calls)
    assert any("save_transaction" in c for c in calls)


def test_ast_parser_extracts_imports(parser: CodebaseASTParser) -> None:
    """Test extraction of import statements."""
    service_file = settings.sample_codebase_dir / "services" / "payment_service.py"
    parsed = parser.parse_file(service_file, base_dir=settings.base_dir)

    imports = [imp.imported_name for imp in parsed.imports]
    assert "payment_repository" in imports
    assert "onelink_client" in imports
    assert "get_db_session" in imports


def test_chunker_generates_all_mandatory_metadata_fields(chunker: SymbolChunker) -> None:
    """Verify all 12+ required metadata fields are populated on every chunk."""
    service_file = settings.sample_codebase_dir / "services" / "payment_service.py"
    chunks = chunker.chunk_file(service_file, base_dir=settings.base_dir)

    assert len(chunks) >= 2  # PaymentService class + process_jazzcash_callback method

    for chunk in chunks:
        # 1. doc_id format: file_path::symbol_name
        assert "::" in chunk.doc_id
        assert chunk.doc_id.endswith(chunk.symbol_name)
        # 2. tenant_id
        assert chunk.tenant_id == settings.default_tenant_id
        # 3. version_tag
        assert chunk.version_tag == "v1.0.0"
        # 4. timestamp
        assert isinstance(chunk.timestamp, str) and len(chunk.timestamp) > 10
        # 5. security_level
        assert chunk.security_level in ["public", "internal", "confidential", "restricted"]
        # 6. jurisdiction
        assert chunk.jurisdiction == "PK"
        # 7. source_authority
        assert chunk.source_authority == "SBP-Fintech-Core"
        # 8. symbol_name
        assert len(chunk.symbol_name) > 0
        # 9. symbol_type
        assert chunk.symbol_type in ["function", "async_function", "class", "method", "async_method"]
        # 10. start_line
        assert chunk.start_line > 0
        # 11. end_line
        assert chunk.end_line >= chunk.start_line
        # 12. file_path
        assert "payment_service.py" in chunk.file_path

        # Code content and search text
        assert len(chunk.content.strip()) > 0
        assert "SYMBOL:" in chunk.search_text


def test_security_level_classification_rules(chunker: SymbolChunker) -> None:
    """Test RBAC security classification tagging across different codebase tiers."""
    # Restricted: secrets/signing_keys.py
    secrets_file = settings.sample_codebase_dir / "secrets" / "signing_keys.py"
    secret_chunks = chunker.chunk_file(secrets_file, base_dir=settings.base_dir)
    assert len(secret_chunks) > 0
    for chunk in secret_chunks:
        assert chunk.security_level == "restricted", (
            f"File in secrets/ must have security_level='restricted', got '{chunk.security_level}'"
        )

    # Confidential: auth/webhook_verification.py
    auth_file = settings.sample_codebase_dir / "auth" / "webhook_verification.py"
    auth_chunks = chunker.chunk_file(auth_file, base_dir=settings.base_dir)
    assert len(auth_chunks) > 0
    for chunk in auth_chunks:
        assert chunk.security_level == "confidential", (
            f"File in auth/ must have security_level='confidential', got '{chunk.security_level}'"
        )

    # Internal: services/payment_service.py
    service_file = settings.sample_codebase_dir / "services" / "payment_service.py"
    service_chunks = chunker.chunk_file(service_file, base_dir=settings.base_dir)
    assert len(service_chunks) > 0
    for chunk in service_chunks:
        assert chunk.security_level == "internal"


def test_full_sample_codebase_chunking(chunker: SymbolChunker) -> None:
    """Ensure chunk_directory processes the full mock codebase and discovers all symbols."""
    chunks = chunker.chunk_directory(settings.sample_codebase_dir, base_dir=settings.base_dir)

    # We expect roughly 30-70 symbol chunks across all 24+ files
    assert len(chunks) >= 25, f"Expected at least 25 symbol chunks, got {len(chunks)}"

    symbol_names = [c.symbol_name for c in chunks]
    assert "handle_jazzcash_callback" in symbol_names
    assert "handle_easypaisa_callback" in symbol_names
    assert "PaymentService.process_jazzcash_callback" in symbol_names
    assert "PaymentRepository.acquire_account_lock" in symbol_names
    assert "OneLinkSwitchClient.verify_switch_transaction" in symbol_names
    assert "SigningKeyStore" in symbol_names
    assert "verify_webhook_signature" in symbol_names
