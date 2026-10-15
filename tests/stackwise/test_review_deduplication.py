"""Static and AI evidence may cover the same call with different line spans."""
import difflib

import pytest

from src.stackwise import analysis


SOURCE = '''import httpx

def fetch_demo_status():
    return httpx.get(
        "https://example.com",
        verify=False,
        timeout=5.0,
    )
'''
PATH = "examples/tls_review.py"
SHA = "b" * 40


def pull(source=SOURCE):
    return {"title": "Test TLS review", "sha": SHA, "ci": {},
            "snapshot": {"sha": SHA, "files": {PATH: source}},
            "files": [{"path": PATH, "patch": "".join(difflib.unified_diff(
                [], source.splitlines(True), fromfile="/dev/null", tofile="b/" + PATH))}]}


def suggestion(title="TLS certificate verification is disabled", start=4, end=8, source=SOURCE):
    return {"title": title, "severity": "high", "path": PATH, "start": start, "end": end,
            "quote": "\n".join(source.splitlines()[start - 1:end]),
            "detail": "Inspect the highlighted call and its TLS configuration.",
            "next_step": "Keep TLS certificate verification enabled."}


def run_review(monkeypatch, values, source=SOURCE):
    monkeypatch.setattr(analysis, "groq_json", lambda *args: (
        {"findings": values, "summary": "Review completed."}, "complete"))
    return analysis.review_pull(pull(source))


@pytest.mark.parametrize("title", [
    "TLS certificate verification is disabled",
    "TLS certificate verification is disabled!",
    "  TLS   CERTIFICATE verification is disabled  ",
])
def test_ai_call_span_and_static_keyword_are_one_issue(monkeypatch, title):
    result = run_review(monkeypatch, [suggestion(title)])
    assert result["checks"]["ai"] == "complete"
    assert result["checks"]["rejected_citations"] == 0
    assert result["checks"]["deduplicated_findings"] == 1
    assert len(result["findings"]) == 1
    item = result["findings"][0]
    assert item["origin"] == "static"
    assert item["evidence"]["start"] == 6
    assert "+        verify=True," in item["patch"]


def test_distinct_issue_at_the_same_line_is_not_silently_dropped(monkeypatch):
    result = run_review(monkeypatch, [suggestion(
        "Different caller validation concern", start=6, end=6)])
    assert len(result["findings"]) == 2
    assert result["checks"]["deduplicated_findings"] == 0


def test_repeated_ai_reports_over_the_same_source_are_joined(monkeypatch):
    result = run_review(monkeypatch, [suggestion("Inspect caller validation"),
                                     suggestion("Inspect caller validation", start=6, end=6)])
    assert len(result["findings"]) == 2  # One TLS observation and one caller concern.
    assert result["checks"]["deduplicated_findings"] == 1


def test_matching_title_at_separate_calls_remains_two_issues(monkeypatch):
    source = "first_call()\nsecond_call()\n"
    result = run_review(monkeypatch, [
        suggestion("Inspect caller validation", 1, 1, source),
        suggestion("Inspect caller validation", 2, 2, source),
    ], source)
    assert len(result["findings"]) == 2
    assert result["checks"]["deduplicated_findings"] == 0


@pytest.mark.parametrize("field,value", [("sha", "c" * 40), ("path", "another_file.py")])
def test_similar_evidence_from_another_file_or_commit_is_not_equal(field, value):
    first = {"title": "TLS issue", "evidence": {"path": PATH, "sha": SHA, "start": 6, "end": 6}}
    second = {"title": "TLS issue", "evidence": {**first["evidence"], field: value}}
    assert not analysis.same_finding(first, second)
