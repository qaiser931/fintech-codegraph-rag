"""Stackwise Python API, served on the same Vercel project as Next.js."""
from __future__ import annotations
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_MODEL", "openai/gpt-oss-120b")

from src.stackwise.application import app
