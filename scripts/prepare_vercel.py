"""Build immutable indices and pinned float32 ONNX models; never read private env files."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import sysconfig
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.environ["CODEGRAPH_SERVERLESS"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(ROOT))

MODELS = {
    "embedding": ("Xenova/bge-small-en-v1.5", "ea104dacec62c0de699686887e3f920caeb4f3e3", {
        "model.onnx": "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
        "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    }),
    "reranker": ("Xenova/ms-marco-MiniLM-L-6-v2", "a09144355adeed5f58c8ed011d209bf8ee5a1fec", {
        "model.onnx": "c623d0bcb99f4622beb413eaef00cfbe5db20df9f1dd982da4b4f26022881870",
        "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    }),
}

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def prepare():
    # Build-time configuration is intentionally independent of runtime keys/tenants.
    from src.config import settings
    settings.base_dir = ROOT
    settings.sample_codebase_dir = ROOT / "data/sample_codebase"
    settings.default_tenant_id = "fintech-pk-corp"
    from src.ingestion.chunker import SymbolChunker
    from src.ingestion.graph_builder import DependencyGraphBuilder
    from src.serverless.retrieval import OnnxEmbedding
    import numpy as np
    assets = ROOT / "codegraph_assets"
    assets.mkdir(exist_ok=True)
    cache = os.environ.get("CODEGRAPH_MODEL_CACHE")
    for name, (repo, revision, files) in MODELS.items():
        folder = assets / name
        folder.mkdir(exist_ok=True)
        for filename, expected in files.items():
            target = folder / filename
            if target.exists() and digest(target) == expected:
                continue
            cached = Path(cache) / name / filename if cache else None
            partial = target.with_suffix(".partial")
            if cached and cached.is_file():
                shutil.copyfile(cached, partial)
            else:
                remote = "onnx/model.onnx" if filename == "model.onnx" else filename
                url = f"https://huggingface.co/{repo}/resolve/{revision}/{remote}"
                with urllib.request.urlopen(url, timeout=90) as r, partial.open("wb") as f:
                    shutil.copyfileobj(r, f)
            if digest(partial) != expected:
                partial.unlink()
                raise RuntimeError(f"Pinned {name} asset integrity check failed.")
            partial.replace(target)
    chunks = SymbolChunker().chunk_directory(settings.sample_codebase_dir, base_dir=ROOT)
    for c in chunks:
        c.timestamp = "2026-10-12T00:00:00+00:00"
    graph = DependencyGraphBuilder()
    graph.build_from_chunks(chunks)
    graph.save_graph(assets / "graph.json")
    (assets / "chunks.json").write_text(json.dumps([c.model_dump() for c in chunks]), encoding="utf-8")
    vectors = OnnxEmbedding(assets / "embedding").encode([c.search_text for c in chunks])
    np.save(assets / "vectors.npy", vectors, allow_pickle=False)
    manifest = {p.relative_to(assets).as_posix(): digest(p) for p in assets.rglob("*")
                if p.is_file() and p.name != "manifest.json"}
    (assets / "manifest.json").write_text(json.dumps(manifest, indent=2))
    size = sum(p.stat().st_size for p in assets.rglob("*") if p.is_file())
    if size > 250_000_000:
        raise RuntimeError("Model assets exceed the reserved build budget.")
    # Conservative: count the entire installed dependency tree, including pip
    # and bytecode, plus the backend/sample sources and a runtime overhead reserve.
    packages = Path(sysconfig.get_paths()["purelib"])
    dependencies = sum(p.stat().st_size for p in packages.rglob("*") if p.is_file())
    sources = sum(p.stat().st_size for folder in (ROOT / "src", ROOT / "data/sample_codebase")
                  for p in folder.rglob("*") if p.is_file())
    estimated = size + dependencies + sources + 10_000_000
    if os.environ.get("VERCEL_PYTHON_VENV_PATH") and estimated > 480_000_000:
        raise RuntimeError("Python bundle budget exceeded; deployment stopped before publication.")
    print(f"Prepared {len(chunks)} chunks, {graph.graph.number_of_nodes()} nodes, "
          f"{size / 1_000_000:.1f} MB immutable assets. No generation submitted.")
    print(f"Conservative assets/dependencies estimate: {estimated / 1_000_000:.1f} MB.")

if __name__ == "__main__":
    prepare()
