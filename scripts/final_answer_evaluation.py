"""Resumable deployed-app evaluation; explicit Groq judge, no Ollama or retries.

Use the separate requirements-evaluation.txt environment. Does not alter indexes
or private env files. Failed stages remain unscored and completed stages are saved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["CODEGRAPH_SERVERLESS"] = "1"
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def private_key():
    from dotenv import dotenv_values
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    for path in (ROOT / ".env.vercel.local", ROOT / ".env"):
        if path.is_file():
            key = (dotenv_values(path).get("GROQ_API_KEY") or "").strip()
            if key:
                return key
    raise RuntimeError("Save GROQ_API_KEY privately in the ignored root .env; never send it in chat")


def completed(record):
    from src.evaluation.judge import METRIC_NAMES
    snapshot = record.get("snapshot")
    return snapshot is not None and record.get("source_verified") is True and record.get("snapshot_sha256") == fingerprint(snapshot) and all(
        record.get("metrics", {}).get(n, {}).get("status") == "complete" for n in METRIC_NAMES)


def save_reports(directory, meta, records, selected_count):
    from src.evaluation.judge import METRIC_NAMES
    summary = {}
    for name in METRIC_NAMES:
        scores = [r["metrics"][name]["score"] for r in records
                  if r.get("metrics", {}).get(name, {}).get("status") == "complete"]
        summary[name] = {"scored_cases": len(scores),
                         "mean": sum(scores) / len(scores) if scores else None}
    complete = len(records) == selected_count and all(completed(r) for r in records)
    data = {**meta, "selected_cases": selected_count, "completed_cases": sum(completed(r) for r in records),
            "complete": complete, "full_dataset_complete": complete and selected_count == 40,
            "summary": summary, "cases": records,
            "citation_gold_match_proxy": {"scored_cases": sum("citation_gold_match_proxy" in r for r in records),
                "mean": (sum(r["citation_gold_match_proxy"] for r in records if "citation_gold_match_proxy" in r)
                         / sum("citation_gold_match_proxy" in r for r in records))
                         if any("citation_gold_match_proxy" in r for r in records) else None},
            "limitations": ["Reference correctness compares to gold facts, not human-validated production truth.",
                            "Citation gold match is a file/symbol proxy over actual answer citations, not semantic claim grounding.",
                            "Hallucination-free is the raw DeepEval HallucinationMetric score; higher is better. It is not 1 minus faithfulness.",
                            "This run does not establish universal accuracy or production performance.",
                            "Incomplete stages are null/unscored; no proxy or historical result is substituted."]}
    atomic_json(directory / "results.json", data)
    lines = ["# Final generated-answer evaluation", "",
             f"Completed cases: {data['completed_cases']}/{selected_count}. Full 40-case benchmark complete: {data['full_dataset_complete']}.",
             "", "| Metric | Mean | Scored cases |", "| --- | ---: | ---: |"]
    for name, values in summary.items():
        mean = "Unscored" if values["mean"] is None else f"{values['mean']:.4f}"
        lines.append(f"| {name} | {mean} | {values['scored_cases']} |")
    lines.extend(["", "All four SDK scores: higher is better. Hallucination-free measures agreement with supplied contexts, not universal absence of hallucination.",
                  "", "## Limits", ""] + ["- " + item for item in data["limitations"]])
    (directory / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://fintech-codegraph-rag.vercel.app")
    parser.add_argument("--judge-model", default="openai/gpt-oss-120b")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "telemetry_logs/final-answer-evaluation")
    parser.add_argument("--request-budget", type=int, default=600)
    parser.add_argument("--max-seconds", type=int, default=3600)
    args = parser.parse_args()
    if not 1 <= args.limit <= 40 or args.request_budget < 1 or args.max_seconds < 1:
        parser.error("Use 1-40 cases and positive request/time budgets")
    address = urlparse(args.base_url)
    if address.scheme != "https" or address.username or address.password or address.query or address.fragment:
        parser.error("Use a plain HTTPS deployment URL")
    try:
        key = private_key()
    except RuntimeError:
        print("STOPPED: Save the existing GROQ_API_KEY privately in root .env.vercel.local or .env. Do not send it in chat.")
        return 1
    from src.evaluation.judge import (PROTOCOL, RequestBudget, groq_judge, make_metrics, measure_metric)
    from deepeval.test_case import LLMTestCase
    from src.ingestion.chunker import SymbolChunker
    from src.config import settings
    import httpx
    # Match the deployed immutable sample profile regardless of local native-index
    # environment settings. This process does not alter any saved configuration.
    settings.base_dir = ROOT
    settings.sample_codebase_dir = ROOT / "data/sample_codebase"
    settings.default_tenant_id = "fintech-pk-corp"
    budget = RequestBudget(args.request_budget, args.max_seconds)
    judge = groq_judge(args.judge_model, key, budget)
    gold_path = ROOT / "data/evaluation/gold_dataset.json"
    cases = json.loads(gold_path.read_text(encoding="utf-8"))[:args.limit]
    chunks = {c.doc_id: c for c in SymbolChunker().chunk_directory(settings.sample_codebase_dir, ROOT)}
    corpus = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT / "data/sample_codebase").rglob("*.py"))}
    meta = {"protocol": PROTOCOL, "deepeval_version": importlib.metadata.version("deepeval"),
            "judge_code_sha256": hashlib.sha256((ROOT / "src/evaluation/judge.py").read_bytes()).hexdigest(),
            "judge_model": args.judge_model, "base_url": args.base_url.rstrip("/"),
            "role": "Security Lead", "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
            "corpus_sha256": fingerprint(corpus), "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "started_utc": datetime.now(timezone.utc).isoformat()}
    records = []
    result_path = args.output / "results.json"
    if result_path.exists():
        if not args.resume:
            parser.error("Saved evaluation exists; use --resume or a new --output directory")
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        for name in ("protocol", "deepeval_version", "judge_code_sha256", "judge_model", "base_url", "role", "gold_sha256", "corpus_sha256"):
            if previous.get(name) != meta[name]:
                parser.error("Saved evaluation protocol/corpus differs; choose a new --output directory")
        records = previous["cases"]
        meta["started_utc"] = previous["started_utc"]
    selected = {c["id"] for c in cases}
    records = [r for r in records if r["id"] in selected]
    by_id = {r["id"]: r for r in records}
    checked_files = set()
    save_reports(args.output, meta, records, len(cases))
    with httpx.Client(timeout=httpx.Timeout(240, connect=10), follow_redirects=False,
                      headers={"User-Agent": "CodeGraph-Evaluation/1.0"}) as client:
        for case in cases:
            record = by_id.get(case["id"])
            if record is None:
                record = {"id": case["id"], "question": case["question"], "metrics": {}}
                records.append(record)
            if completed(record):
                print(case["id"] + ": reusing completed snapshot and metrics", flush=True)
                continue
            if "snapshot" not in record:
                try:
                    budget.take()
                    started = time.perf_counter()
                    response = client.post(meta["base_url"] + "/api/query",
                                           json={"query": case["question"], "role": meta["role"]})
                    if response.status_code != 200:
                        raise RuntimeError("Application HTTP " + str(response.status_code))
                    payload = response.json()
                    ids = [i["doc_id"] for i in payload["retrieved_items"]]
                    if (not ids or any(i not in chunks for i in ids) or not payload.get("answer")
                        or payload.get("query") != case["question"] or payload.get("role") != meta["role"]):
                        raise RuntimeError("Invalid application evidence")
                    snapshot = {"response": payload, "retrieval_context": [chunks[i].search_text for i in ids],
                                "answer_facts": case["answer_facts"],
                                "observed_seconds": round(time.perf_counter() - started, 3)}
                    record["snapshot"] = snapshot
                    record["snapshot_sha256"] = fingerprint(snapshot)
                    record.pop("generation_error", None)
                    save_reports(args.output, meta, records, len(cases))
                except Exception as exc:
                    record["generation_error"] = {"error_type": type(exc).__name__, "score": None}
                    save_reports(args.output, meta, records, len(cases))
                    print(case["id"] + ": application/source check stopped; no retry or substituted answer", flush=True)
                    return 1
            snapshot = record["snapshot"]
            if record.get("snapshot_sha256") != fingerprint(snapshot):
                raise RuntimeError("Saved answer/evidence fingerprint differs")
            if not record.get("source_verified"):
                try:
                    for item in snapshot["response"]["retrieved_items"]:
                        path = chunks[item["doc_id"]].file_path
                        if path in checked_files:
                            continue
                        budget.take()
                        source = client.get(meta["base_url"] + "/api/source/" + path, params={"role": meta["role"]})
                        if source.status_code != 200 or source.json().get("code") != (ROOT / path).read_text(encoding="utf-8").rstrip("\n"):
                            raise RuntimeError("Deployed source differs from local corpus")
                        checked_files.add(path)
                    record["source_verified"] = True
                    record.pop("source_error", None)
                    from src.evaluation.metrics import citation_groundedness
                    record["citation_gold_match_proxy"] = citation_groundedness(
                        snapshot["response"]["citations"], case["expected_files"], case["expected_symbols"])
                    save_reports(args.output, meta, records, len(cases))
                except Exception as exc:
                    record["source_error"] = {"error_type": type(exc).__name__, "score": None}
                    save_reports(args.output, meta, records, len(cases))
                    print(case["id"] + ": source verification stopped; saved answer retained, no retry", flush=True)
                    return 1
            test_case = LLMTestCase(input=case["question"], actual_output=snapshot["response"]["answer"],
                expected_output="\n".join(snapshot["answer_facts"]),
                retrieval_context=snapshot["retrieval_context"], context=snapshot["retrieval_context"])
            for name, metric in make_metrics(judge).items():
                if record["metrics"].get(name, {}).get("status") == "complete":
                    continue
                print(case["id"] + ": judging " + name, flush=True)
                record["metrics"][name] = measure_metric(metric, test_case)
                save_reports(args.output, meta, records, len(cases))
                if record["metrics"][name]["status"] != "complete":
                    print("Judge stopped unscored. Saved stages retained; --resume is an explicit retry.", flush=True)
                    return 1
            print(case["id"] + ": all four judge metrics complete", flush=True)
    meta["requests_this_invocation"] = budget.requests
    complete = save_reports(args.output, meta, records, len(cases))
    print("Evaluation complete:", complete, "Report:", args.output / "REPORT.md", flush=True)
    return 0 if complete else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, Exception) as exc:
        print("STOPPED:", type(exc).__name__, "Saved results retained; no credentials printed.", file=sys.stderr)
        raise SystemExit(1)
