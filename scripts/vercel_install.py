"""Install the lightweight Stackwise Python runtime. No local models or indices."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
# The Python builder seeds pip into its build venv.
subprocess.run([sys.executable, "-m", "pip", "install",
                "-r", str(root / "requirements.txt"),
                "-c", str(root / "requirements-vercel.lock")], check=True, cwd=root)
