"""Run the mocked/unit suite with a bounded wait and no live LLM calls."""

from pathlib import Path
import subprocess
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
TEST_FILES = (
    "test_phase1_setup.py",
    "test_phase2_ast_chunker.py",
    "test_phase3_graph.py",
    "test_phase6_generation.py",
    "test_phase7_api.py",
    "test_phase8_evaluation.py",
    "test_ui_api_client.py",
    "test_query_timeout_regressions.py",
    "test_indexer_startup.py",
    "test_retrieval_api.py",
    "test_ui_explore.py",
    "test_public_demo_ui.py",
)


def main() -> int:
    command = [sys.executable, "-m", "pytest", "-q", "--durations=10"]
    command.extend(str(BASE_DIR / "tests" / name) for name in TEST_FILES)
    try:
        return subprocess.run(command, cwd=BASE_DIR, timeout=180).returncode
    except subprocess.TimeoutExpired:
        print("Offline suite stopped after 180 seconds; verification is incomplete.", file=sys.stderr)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
