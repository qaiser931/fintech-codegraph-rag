"""Run the current lightweight profile's offline checks without live LLM calls."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "test_phase2_ast_chunker.py", "test_phase3_graph.py", "test_phase6_generation.py",
    "test_phase8_evaluation.py", "test_groq_generation.py", "test_documented_facts.py",
    "test_serverless.py", "test_final_evaluation.py",
)

if __name__ == "__main__":
    if not (ROOT / "codegraph_assets/vectors.npy").is_file():
        print("Prepare immutable assets with scripts/prepare_vercel.py before running real-inference tests.")
        raise SystemExit(1)
    environment = dict(os.environ, CODEGRAPH_SERVERLESS="1", LLM_PROVIDER="groq")
    raise SystemExit(subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *[str(ROOT / "tests" / name) for name in FILES]],
        cwd=ROOT, env=environment, timeout=300).returncode)
