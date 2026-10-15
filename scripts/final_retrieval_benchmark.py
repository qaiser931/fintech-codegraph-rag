"""40 gold cases x three roles x three modes, real ONNX inference, no LLM calls."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.environ["CODEGRAPH_SERVERLESS"] = "1"
os.environ.setdefault("LLM_PROVIDER", "groq")
sys.path.insert(0, str(ROOT))

MODES = ("vector_only", "hybrid", "hybrid_graph")
ROLES = ("Junior Dev", "Senior Dev", "Security Lead")


def summarize(rows):
    names = sorted({name for row in rows for name in row["metrics"]})
    summary = {}
    for name in names:
        values = [r["metrics"][name] for r in rows if r["metrics"].get(name) is not None]
        summary[name] = {"mean": round(sum(values) / len(values), 6) if values else None,
                         "scored_cases": len(values)}
    latencies = sorted(r["elapsed_seconds"] for r in rows)
    import numpy as np
    return {"questions": len(rows), "unauthorized_results": sum(r["unauthorized_count"] for r in rows),
            "metrics": summary, "latency_seconds": {
                "p50": round(float(np.percentile(latencies, 50)), 3),
                "p95": round(float(np.percentile(latencies, 95)), 3)}}


def main():
    from src.serverless.application import initialize
    from src.api.dependencies import app_state
    from src.evaluation.metrics import (evaluate_retrieval_case, call_path_recall_at_k,
                                       execution_path_accuracy)
    from src.security.rbac import rbac_manager
    initialize()
    gold = ROOT / "data/evaluation/gold_dataset.json"
    cases = json.loads(gold.read_text(encoding="utf-8"))
    chunks = {c.doc_id: c for c in app_state.indexer.chunks}
    unknown = {s for c in cases for s in c["expected_symbols"] if s not in chunks}
    if unknown:
        raise RuntimeError("Gold dataset references missing corpus symbols")
    rows = []
    summary = {}
    for role in ROLES:
        clearance = rbac_manager.get_clearance_for_role(role)
        for mode in MODES:
            group = []
            for case in cases:
                started = time.perf_counter()
                if mode == "vector_only":
                    hits = app_state.indexer.vector_index.search(case["question"], role=role, top_k=6,
                                                                tenant_id="fintech-pk-corp")
                    ids = [c.doc_id for c, _ in hits]
                    paths = []
                else:
                    result = app_state.retriever.retrieve(case["question"], role=role,
                        use_graph=mode == "hybrid_graph", tenant_id="fintech-pk-corp")
                    ids, paths = result.doc_ids, result.execution_paths
                unauthorized = sum(chunks[d].security_level not in clearance for d in ids)
                if unauthorized:
                    raise RuntimeError("Unauthorized benchmark result")
                expected = [d for d in case["expected_symbols"] if chunks[d].security_level in clearance]
                expected_path = [d for d in case["expected_call_path"] if chunks[d].security_level in clearance]
                metrics = evaluate_retrieval_case(retrieved_symbols=ids, expected_symbols=expected, k=5)
                # No gold symbols visible to this role means N/A, not perfect or zero recall.
                if not expected:
                    metrics = {name: None for name in metrics}
                flattened = list(dict.fromkeys(d for path in paths for d in path))
                metrics["call_path_recall"] = (call_path_recall_at_k(flattened, expected_path, k=None)
                                                if expected_path else None)
                metrics["execution_path_accuracy"] = (execution_path_accuracy(paths, expected_path)
                                                       if expected_path else None)
                metrics["context_recall"] = len(set(ids) & set(expected)) / len(expected) if expected else None
                # Retrieval sources are not generated-answer citations. Never score these as claim grounding.
                metrics.pop("citation_groundedness", None)
                metrics.pop("call_path_recall_at_k", None)
                row = {"id": case["id"], "role": role, "mode": mode, "doc_ids": ids,
                       "execution_paths": paths, "expected_authorized_symbols": expected,
                       "expected_authorized_path": expected_path, "unauthorized_count": unauthorized,
                       "elapsed_seconds": round(time.perf_counter() - started, 3), "metrics": metrics}
                rows.append(row)
                group.append(row)
            summary[role + " / " + mode] = summarize(group)
            print(f"Completed {len(group)} cases: {role} / {mode}", flush=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    payload = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": commit,
               "gold_sha256": hashlib.sha256(gold.read_bytes()).hexdigest(),
               "benchmark_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "runtime": "Float32 ONNX BGE + MiniLM; exact cosine + BM25 + RRF + NetworkX",
               "scope": "40 questions x 3 roles x 3 retrieval modes; no generated-answer or judge scores",
               "definitions": {
                   "ranking": "Recall/precision/NDCG@5 and MRR use authorized gold symbol IDs; unavailable gold sets are N/A.",
                   "code_symbol_resolution_precision": "Share of returned symbols in the authorized gold set; full context.",
                   "call_path_recall": "Coverage of authorized expected-path symbols in the union of returned paths; no order credit.",
                   "execution_path_accuracy": "One returned path must contain the authorized gold path in order, allowing intermediate calls.",
                   "citation_groundedness": "Not measured by retrieval; actual answer citations and semantic claim grounding require answer evaluation.",
                   "latency": "Local benchmark on this machine, including one cold first query; not Vercel p50/p95 or PyTorch equivalence."},
               "summary": summary, "cases": rows}
    target = ROOT / "data/evaluation/final_retrieval_report.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["# Final ONNX retrieval benchmark", "", payload["scope"], "",
             "| Role / Mode | Recall@5 | Precision@5 | MRR | NDCG@5 | Context recall | Symbol precision | Path recall | Path accuracy |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    names = ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k", "context_recall",
             "code_symbol_resolution_precision", "call_path_recall", "execution_path_accuracy")
    for name, group in summary.items():
        values = [group["metrics"][metric]["mean"] for metric in names]
        lines.append("| " + name + " | " + " | ".join("N/A" if v is None else f"{v:.4f}" for v in values) + " |")
    lines.extend(["", "All returned chunks were authorized. See JSON for per-case denominators, paths, timings and provenance.",
                  "", "## Interpretation", ""])
    lines.extend("- " + text for text in payload["definitions"].values())
    (target.with_suffix(".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
