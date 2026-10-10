"""Script to build, persist, and test the codebase dependency graph."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import settings
from src.ingestion.graph_builder import DependencyGraphBuilder


def main() -> None:
    print("=" * 70)
    print("Building Fintech Codebase Dependency Call Graph (NetworkX)...")
    print(f"Target directory: {settings.sample_codebase_dir}")
    print("=" * 70)

    builder = DependencyGraphBuilder()
    graph = builder.build_from_directory(settings.sample_codebase_dir, base_dir=settings.base_dir)

    print(f"\n[Graph Statistics]")
    print(f"Total Symbol Nodes : {graph.number_of_nodes()}")
    print(f"Total Dependency Edges: {graph.number_of_edges()}")

    # Persist graph to disk
    saved_path = builder.save_graph(settings.graph_store_path)
    print(f"\n[Graph Persisted]")
    print(f"Graph successfully saved to: {saved_path}")

    # Trace JazzCash payment callback execution path
    print("\n" + "=" * 70)
    print("Tracing JazzCash Callback Execution Path -> 1LINK Switch:")
    print("=" * 70)

    path = builder.find_execution_path("handle_jazzcash_callback", "verify_switch_transaction")

    if path:
        summary = builder.format_path_summary(path)
        print(f"\n[Discovered Execution Path Chain]:\n{summary}\n")
        print("[Detailed Step-by-Step Path with Grounded Lines]:")
        for i, node_id in enumerate(path, 1):
            node_data = graph.nodes[node_id]
            sym = node_data.get("symbol_name")
            fp = node_data.get("file_path")
            sline = node_data.get("start_line")
            eline = node_data.get("end_line")
            sec = node_data.get("security_level")
            stype = node_data.get("symbol_type")
            print(f"  Step {i}: [{stype}] {sym}")
            print(f"          File: {fp} (Lines {sline}-{eline})")
            print(f"          Security Clearance: {sec}")
    else:
        print("ERROR: No path found between handle_jazzcash_callback and verify_switch_transaction")

    # Trace DB row locking path
    print("\n" + "=" * 70)
    print("Tracing JazzCash Callback -> DB Row Lock (SELECT FOR UPDATE):")
    print("=" * 70)
    lock_path = builder.find_execution_path("handle_jazzcash_callback", "acquire_account_lock")
    if lock_path:
        print(f"[Discovered Lock Path]: {builder.format_path_summary(lock_path)}")
        lock_node = graph.nodes[lock_path[-1]]
        print(f"  Target File: {lock_node['file_path']} (Lines {lock_node['start_line']}-{lock_node['end_line']})")
    print("=" * 70)


if __name__ == "__main__":
    main()
