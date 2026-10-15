"""Authored sample portfolio. Never mixed with connected client data or real metrics."""
import copy
import hashlib

from .analysis import evidence, replacement_patch, review_pull


SOURCE = '''import requests
from fastapi import APIRouter
from services.accounts import fetch_account

router = APIRouter()

@router.get("/account")
def get_account(user_id: str):
    return fetch_account(user_id)

def verify_payment(reference: str):
    return requests.get(
        "https://payments.example.test/verify",
        params={"reference": reference},
        verify=False,
        timeout=10,
    ).json()
'''
FILES = {"auth/routes.py": SOURCE,
         "services/accounts.py": '''def fetch_account(user_id: str):
    """Return the account selected by its owner ID (sample implementation)."""
    return {"owner_id": user_id, "balance": 100}
''',
         "tests/test_accounts.py": '''from services.accounts import fetch_account

def test_account_shape():
    assert "balance" in fetch_account("user-1")
''', "requirements.txt": "fastapi==0.115.0\nrequests==2.31.0\n"}
SHA = hashlib.sha256(SOURCE.encode()).hexdigest()[:40]


def demo_data():
    snapshot = {"sha": SHA, "files": FILES}
    patch = "@@ -1,0 +1,17 @@\n" + "\n".join("+" + x for x in SOURCE.splitlines())
    pull = {"title": "Add client account endpoint", "number": 128, "sha": SHA, "base_sha": "a" * 40,
            "snapshot": snapshot, "ci": {"status": "sample", "runs": []},
            "files": [{"path": "auth/routes.py", "patch": patch, "additions": 17, "deletions": 0,
                       "patch_available": True, "status": "added"}]}
    result = review_pull(pull, use_ai=False)
    authored = {"id": "demo-auth", "workspace_id": "demo-alpha", "review_id": "demo-review", "severity": "high",
                "title": "Account ownership needs a check", "detail": "This sample route accepts user_id directly from the request and passes it to fetch_account. The shown code does not check the authenticated caller's ownership. Confirm upstream controls before treating this as an exploitable issue.",
                "next_step": "Derive the account owner from the authenticated user and add a cross-user access regression test.",
                "evidence": evidence(snapshot, "auth/routes.py", 7, 9), "patch": "", "origin": "authored_demo", "status": "open", "feedback": None}
    findings = [authored] + [{**f, "id": f"demo-static-{i}", "workspace_id": "demo-alpha", "review_id": "demo-review", "status": "open", "feedback": None}
                               for i, f in enumerate(result["findings"])]
    workspaces = [{"id": "demo-alpha", "name": "Client Alpha", "color": "teal"},
                  {"id": "demo-beta", "name": "Client Beta", "color": "orange"},
                  {"id": "demo-internal", "name": "Internal tools", "color": "purple"}]
    repos = [{"id": "demo-api", "workspace_id": "demo-alpha", "full_name": "client-alpha/api-service", "status": "indexed", "sha": SHA, "branch": "main", "file_count": 4, "indexed": None,
              "dependencies": {"status": "sample", "unresolved": 0, "packages": [{"name": "requests", "version": "2.31.0", "ecosystem": "PyPI", "path": "requirements.txt", "advisories": [{"id": "DEMO-ADVISORY"}]}]},
              "ci": {"status": "sample", "runs": [{"name": "Unit tests", "status": "completed", "conclusion": "success"}]},
              "prs": [{"number": 128, "title": pull["title"], "sha": SHA, "draft": False}]},
             {"id": "demo-web", "workspace_id": "demo-beta", "full_name": "client-beta/web-app", "status": "not_indexed", "sha": "", "branch": "main", "file_count": 0, "indexed": None, "dependencies": {"status": "not_run", "packages": []}, "ci": {"status": "not_observed", "runs": []}, "prs": []},
             {"id": "demo-cli", "workspace_id": "demo-internal", "full_name": "studio/release-cli", "status": "not_indexed", "sha": "", "branch": "main", "file_count": 0, "indexed": None, "dependencies": {"status": "not_run", "packages": []}, "ci": {"status": "not_observed", "runs": []}, "prs": []}]
    review = {"id": "demo-review", "workspace_id": "demo-alpha", "repo_id": "demo-api", "number": 128,
              "title": pull["title"], "sha": SHA, "base_sha": pull["base_sha"], "status": "needs_review", "created": 0,
              "summary": "The account endpoint and payment verification both need a human review. Inspect source evidence before accepting a finding; the TLS check includes a downloadable patch preview.",
              "files": [{**f, "source": FILES[f["path"]]} for f in pull["files"]],
              "context": result["context"], "checks": {**result["checks"], "ai": "authored_demo"}, "elapsed": 0, "findings": findings}
    return copy.deepcopy({"demo": True, "workspaces": workspaces, "repositories": repos, "reviews": [review],
                          "findings": findings, "jobs": [], "reports": [], "audit": [],
                          "note": "Illustrative sample portfolio. Findings and activity are demo data; actions stay in this browser session."})
