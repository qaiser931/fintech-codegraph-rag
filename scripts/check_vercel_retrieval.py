"""Explicit 40-question, three-role ONNX retrieval check. Makes no LLM requests."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.environ["CODEGRAPH_SERVERLESS"] = "1"
os.environ.setdefault("LLM_PROVIDER", "groq")
sys.path.insert(0, str(ROOT))


def main():
    from src.serverless.application import initialize
    from src.api.dependencies import app_state
    from src.security.rbac import rbac_manager
    initialize()
    cases = json.loads((ROOT / "data/evaluation/gold_dataset.json").read_text())
    chunks = {c.doc_id: c for c in app_state.indexer.chunks}
    results = []
    summary = {}
    for role in ("Junior Dev", "Senior Dev", "Security Lead"):
        clearance = rbac_manager.get_clearance_for_role(role)
        for case in cases:
            started = time.perf_counter()
            retrieved = app_state.retriever.retrieve(case["question"], role=role)
            if not all(i.chunk.security_level in clearance for i in retrieved.items):
                raise RuntimeError("Unauthorized source was returned.")
            expected = {x for x in case["expected_symbols"] if x in chunks
                        and chunks[x].security_level in clearance}
            found = expected.intersection(retrieved.doc_ids)
            results.append({"id": case["id"], "role": role,
                            "expected_authorized": len(expected), "found_expected": len(found),
                            "context_recall": len(found) / len(expected) if expected else None,
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "doc_ids": retrieved.doc_ids})
        values = [r["context_recall"] for r in results if r["role"] == role
                  and r["context_recall"] is not None]
        summary[role] = {"questions": len(cases), "unauthorized_results": 0,
                        "mean_authorized_expected_symbol_context_recall": round(sum(values) / len(values), 4)}
        print(f"Completed {len(cases)} retrieval questions for {role}.", flush=True)
    data = {"runtime": "Float32 ONNX BGE + MiniLM cross-encoder; exact cosine + BM25 + RRF + graph expansion",
            "scope": "40 dataset questions per role, 120 retrieval-only checks; no LLM answers or correctness scores",
            "baseline_equivalence": "PyTorch baseline was not rerun; fresh ONNX results, not an equivalence claim",
            "summary": summary, "cases": results}
    target = ROOT / "data/evaluation/vercel_retrieval_report.json"
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
