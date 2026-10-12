"""Vercel Python install hook: prepare assets before the Python function is bundled."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
# The Python builder seeds pip into its build venv.
subprocess.run([sys.executable, "-m", "pip", "install",
                "-r", str(root / "requirements.txt"),
                "-c", str(root / "requirements-vercel.lock")], check=True, cwd=root)
subprocess.run([sys.executable, str(root / "scripts/prepare_vercel.py")],
               check=True, cwd=root, env={**os.environ, "CODEGRAPH_SERVERLESS": "1"})
