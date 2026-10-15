"""Bounded deployment checks; one explicit live answer, no automatic retries."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def verify(base_url, generation=True):
    base_url = base_url.rstrip("/")
    records = []
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": base_url,
              "checks": records, "generation_requests": 0,
              "scope": "Live contract/security checks plus at most one documented sample-code answer; not a correctness benchmark."}
    with httpx.Client(timeout=httpx.Timeout(240, connect=10), follow_redirects=False,
                      headers={"User-Agent": "CodeGraph-Submission-Check/1.0"}) as client:
        def check(name, method, path, expected=200, **kwargs):
            started = time.perf_counter()
            response = client.request(method, base_url + path, **kwargs)
            value = {"name": name, "status": response.status_code, "expected": expected,
                     "passed": response.status_code == expected,
                     "elapsed_seconds": round(time.perf_counter() - started, 3)}
            records.append(value)
            if not value["passed"]:
                raise RuntimeError(name + " failed: HTTP " + str(response.status_code))
            print(name + ": HTTP " + str(response.status_code), flush=True)
            return response

        health = check("health", "GET", "/api/health").json()
        if not health.get("ok") or (health.get("chunks"), health.get("graph_nodes")) != (64, 64):
            raise RuntimeError("Unexpected corpus readiness/counts")
        report["health"] = health
        for path in ("/", "/dashboard"):
            page = check("page " + path, "GET", path)
            if "text/html" not in page.headers.get("content-type", ""):
                raise RuntimeError("Page is not HTML")
        question = "What is the expected 1LINK latency during peak traffic?"
        levels = {"Junior Dev": {"public", "internal"},
                  "Senior Dev": {"public", "internal", "confidential"},
                  "Security Lead": {"public", "internal", "confidential", "restricted"}}
        for role, allowed in levels.items():
            value = check("retrieval " + role, "POST", "/api/retrieve",
                          json={"query": question, "role": role}).json()
            if not value.get("sources") or any(s["security_level"] not in allowed for s in value["sources"]):
                raise RuntimeError("Missing or unauthorized source")
            records[-1].update(sources=len(value["sources"]), unauthorized_sources=0)
        path = "/api/source/data/sample_codebase/integrations/onelink_client.py"
        source = check("literal source", "GET", path, params={"role": "Junior Dev"}).json()
        if source.get("code") != (ROOT / "data/sample_codebase/integrations/onelink_client.py").read_text(encoding="utf-8").rstrip("\n"):
            raise RuntimeError("Deployed source differs from reviewed source")
        check("Junior confidential source denied", "GET",
              "/api/source/data/sample_codebase/auth/webhook_verification.py",
              expected=403, params={"role": "Junior Dev"})
        signing = "/api/source/data/sample_codebase/secrets/signing_keys.py"
        check("Junior restricted source denied", "GET", signing, expected=403, params={"role": "Junior Dev"})
        check("Security Lead restricted source allowed", "GET", signing, params={"role": "Security Lead"})
        check("invalid bearer rejected", "POST", "/api/retrieve", expected=401,
              headers={"Authorization": "Bearer submission-invalid-fixture"},
              json={"query": question, "role": "Junior Dev"})
        check("source escape rejected", "GET", "/api",
              params={"endpoint": "source/../.env", "role": "Security Lead"}, expected=400)
        check("invalid role rejected", "POST", "/api/retrieve", expected=400,
              json={"query": question, "role": "invalid"})
        if generation:
            report["generation_requests"] = 1
            result = check("documented latency answer", "POST", "/api/query",
                           json={"query": question, "role": "Junior Dev"}).json()
            if (result.get("status") != "SUPPORTED" or not result.get("citations")
                or not re.search(r"\b2(?:\.0)?\b", result.get("answer", ""))
                or not re.search(r"\b6(?:\.0)?\b", result.get("answer", ""))):
                raise RuntimeError("Documented answer was not supported/cited")
            report["sample_answer"] = result
    report["complete"] = all(c["passed"] for c in records)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://fintech-codegraph-rag.vercel.app")
    parser.add_argument("--no-generation", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation/final_live_checks.json")
    args = parser.parse_args()
    if not args.base_url.startswith("https://"):
        parser.error("Use the HTTPS deployment URL")
    report = verify(args.base_url, not args.no_generation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Live verification complete. No production-performance or full answer-quality score is claimed.")


if __name__ == "__main__":
    main()
