"""Unit tests and execution path validation for Phase 3 Dependency Call Graph."""

import json
from pathlib import Path
import pytest
import networkx as nx
from src.config import settings
from src.ingestion.ast_parser import CodebaseASTParser
from src.ingestion.chunker import SymbolChunker
from src.ingestion.graph_builder import DependencyGraphBuilder


@pytest.fixture
def graph_builder() -> DependencyGraphBuilder:
    builder = DependencyGraphBuilder()
    builder.build_from_directory(settings.sample_codebase_dir, base_dir=settings.base_dir)
    return builder


def _build_synthetic_graph(sources: dict[str, str]) -> DependencyGraphBuilder:
    parser = CodebaseASTParser()
    chunker = SymbolChunker(parser)
    parsed_modules = [
        parser.parse_source(source, file_path)
        for file_path, source in sorted(sources.items())
    ]
    chunks = [
        chunk
        for parsed_module in parsed_modules
        for chunk in chunker.chunk_module(parsed_module)
    ]
    builder = DependencyGraphBuilder()
    builder.build_from_chunks(chunks, parsed_modules=parsed_modules)
    return builder


def _import_test_sources() -> dict[str, str]:
    return {
        "project_pkg/consumer.py": (
            "from .provider import provide_value\n\n"
            "def consume():\n"
            "    return helper()\n\n"
            "def helper():\n"
            "    return 2\n"
        ),
        "project_pkg/provider.py": (
            "def provide_value():\n"
            "    return 1\n"
        ),
    }


def test_dependency_graph_nodes_and_edges(graph_builder: DependencyGraphBuilder) -> None:
    """Verify graph contains symbols as nodes and relationships as edges."""
    g = graph_builder.graph
    assert g.number_of_nodes() >= 25
    assert g.number_of_edges() >= 15

    # Check key symbols exist in the graph
    node_symbols = [d.get("symbol_name") for _, d in g.nodes(data=True)]
    assert "handle_jazzcash_callback" in node_symbols
    assert "PaymentService.process_jazzcash_callback" in node_symbols
    assert "PaymentRepository.acquire_account_lock" in node_symbols
    assert "OneLinkSwitchClient.verify_switch_transaction" in node_symbols
    assert "verify_webhook_signature" in node_symbols


def test_jazzcash_callback_execution_path_to_onelink(graph_builder: DependencyGraphBuilder) -> None:
    """Validate that the execution path from JazzCash callback route to 1LINK client is fully traceable."""
    # Find execution path from route handler to 1LINK verify_switch_transaction
    path = graph_builder.find_execution_path(
        source_pattern="handle_jazzcash_callback",
        target_pattern="verify_switch_transaction",
    )
    assert path is not None, "Execution path from handle_jazzcash_callback to verify_switch_transaction must exist"
    assert len(path) >= 3

    path_summary = graph_builder.format_path_summary(path)
    print("\n[TEST OUTPUT] Discovered JazzCash -> 1LINK Execution Path:")
    print(path_summary)

    # Verify the chain steps: handle_jazzcash_callback -> process_jazzcash_callback -> verify_switch_transaction
    assert "handle_jazzcash_callback" in path_summary
    assert "process_jazzcash_callback" in path_summary
    assert "verify_switch_transaction" in path_summary


def test_jazzcash_callback_execution_path_to_db_row_lock(graph_builder: DependencyGraphBuilder) -> None:
    """Validate that the execution path from JazzCash callback to DB row locking is fully traceable."""
    path = graph_builder.find_execution_path(
        source_pattern="handle_jazzcash_callback",
        target_pattern="acquire_account_lock",
    )
    assert path is not None, "Execution path from handle_jazzcash_callback to acquire_account_lock must exist"

    path_summary = graph_builder.format_path_summary(path)
    print("\n[TEST OUTPUT] Discovered JazzCash -> DB Row Lock Execution Path:")
    print(path_summary)

    assert "acquire_account_lock" in path_summary


def test_jazzcash_callback_execution_path_to_webhook_verification(graph_builder: DependencyGraphBuilder) -> None:
    """Validate that the callback handler directly verifies HMAC signature before processing."""
    path = graph_builder.find_execution_path(
        source_pattern="handle_jazzcash_callback",
        target_pattern="verify_webhook_signature",
    )
    assert path is not None
    assert len(path) == 2  # Direct edge: handle_jazzcash_callback -> verify_webhook_signature


def test_graph_persistence_and_loading(graph_builder: DependencyGraphBuilder, tmp_path: Path) -> None:
    """Verify serialization to disk and reload functionality."""
    out_file = tmp_path / "test_graph.json"
    saved_path = graph_builder.save_graph(out_file)
    assert saved_path.exists()

    # Verify file is valid JSON
    with open(saved_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "nodes" in data
    assert "edges" in data or "links" in data

    # Create fresh builder and reload from disk
    new_builder = DependencyGraphBuilder()
    new_builder.load_graph(saved_path)
    assert new_builder.graph.number_of_nodes() == graph_builder.graph.number_of_nodes()
    assert new_builder.graph.number_of_edges() == graph_builder.graph.number_of_edges()


def test_graph_subgraph_expansion(graph_builder: DependencyGraphBuilder) -> None:
    """Verify multi-hop expansion outward from seed symbols."""
    # Find handle_jazzcash_callback node
    seed_nodes = [
        nid for nid, d in graph_builder.graph.nodes(data=True)
        if "handle_jazzcash_callback" in d.get("symbol_name", "")
    ]
    assert len(seed_nodes) > 0

    # Expand 2 hops outward
    expanded = graph_builder.expand_subgraph(seed_nodes, hops=2, direction="out")
    expanded_names = [n["symbol_name"] for n in expanded]

    assert "handle_jazzcash_callback" in expanded_names
    assert "PaymentService.process_jazzcash_callback" in expanded_names
    # 2 hops reaches DB lock and 1LINK
    assert any("acquire_account_lock" in name for name in expanded_names)
    assert any("verify_switch_transaction" in name for name in expanded_names)


def test_project_relative_import_creates_import_edge_in_importer_to_imported_direction():
    builder = _build_synthetic_graph(_import_test_sources())
    source_node = "project_pkg/consumer.py::consume"
    target_node = "project_pkg/provider.py::provide_value"

    assert builder.graph.has_edge(source_node, target_node), list(
        builder.graph.edges(data=True)
    )
    edge = builder.graph.edges[source_node, target_node]
    assert edge["relation"] == "imports"
    assert edge["import_references"][0]["module"] == "project_pkg.provider"
    assert edge["import_references"][0]["name"] == "provide_value"


def test_import_addition_preserves_existing_call_edges_and_order():
    builder = _build_synthetic_graph(_import_test_sources())
    caller = "project_pkg/consumer.py::consume"
    helper = "project_pkg/consumer.py::helper"

    assert builder.graph.has_edge(caller, helper)
    call_edge = builder.graph.edges[caller, helper]
    assert call_edge["relation"] == "calls"
    assert call_edge["call_expr"] == "helper"
    assert call_edge["call_order"] == 1


def test_unresolved_external_imports_create_no_graph_nodes_or_edges():
    builder = _build_synthetic_graph(
        {
            "project_pkg/consumer.py": (
                "import json\n"
                "from external_package.module import ExternalType\n\n"
                "def consume():\n"
                "    return 1\n"
            )
        }
    )

    assert list(builder.graph.nodes) == ["project_pkg/consumer.py::consume"]
    assert builder.graph.number_of_edges() == 0


def test_import_graph_construction_is_deterministic():
    sources = _import_test_sources()
    first = _build_synthetic_graph(sources).graph
    second = _build_synthetic_graph(sources).graph

    first_nodes = list(first.nodes(data=True))
    second_nodes = list(second.nodes(data=True))
    first_edges = list(first.edges(data=True))
    second_edges = list(second.edges(data=True))

    assert first_nodes == second_nodes
    assert first_edges == second_edges


def test_loading_graph_without_import_edges_rebuilds_project_imports(
    graph_builder: DependencyGraphBuilder,
    tmp_path: Path,
):
    for source, target, attrs in list(graph_builder.graph.edges(data=True)):
        if attrs.get("relation") == "imports":
            graph_builder.graph.remove_edge(source, target)
    legacy_graph_data = nx.node_link_data(graph_builder.graph)
    legacy_path = tmp_path / "legacy_graph.json"
    legacy_path.write_text(json.dumps(legacy_graph_data), encoding="utf-8")

    loaded = DependencyGraphBuilder()
    loaded.load_graph(legacy_path)

    loaded_edge = loaded.graph.edges[
        "data/sample_codebase/api/routes/jazzcash_callback.py::handle_jazzcash_callback",
        "data/sample_codebase/auth/webhook_verification.py::verify_webhook_signature",
    ]
    assert loaded_edge["relation"] == "calls"
    assert loaded_edge["import_references"][0]["name"] == "verify_webhook_signature"
