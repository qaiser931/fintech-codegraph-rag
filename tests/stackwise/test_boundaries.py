import hashlib
import hmac
import io
import json
import tarfile
import time

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.stackwise import analysis, service
from src.stackwise.application import app
from src.stackwise.demo import FILES, SHA, demo_data
from src.stackwise.github import GitHub, IntegrationError, accepted, read_archive
from src.stackwise.security import digest, redact, repository_name, safe_path, seal
from src.stackwise.store import (AccessKey, Finding, Job, Report, Repository, Review,
                                 Workspace, database)

ORIGIN = "http://testserver"
ADMIN = "test-owner-key-with-at-least-32-characters"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKWISE_LOCAL", "1")
    monkeypatch.setenv("STACKWISE_APP_URL", ORIGIN)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("STACKWISE_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("STACKWISE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("STACKWISE_QUEUE_ENABLED", raising=False)
    for proxy in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "http_proxy", "https_proxy"):
        monkeypatch.delenv(proxy, raising=False)
    database.cache_clear()
    with TestClient(app) as client:
        yield client
    database.cache_clear()


def login(client, key=ADMIN):
    result = client.post("/api/login", json={"key": key}, headers={"Origin": ORIGIN})
    assert result.status_code == 200, result.text
    user = client.get("/api/session").json()["user"]
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": user["csrf"]})
    return user


def workspace(client, name="Client A"):
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def seed(workspace_id):
    demo = demo_data()
    with database()() as db:
        repo = Repository(workspace_id=workspace_id, full_name="owner/repo", snapshot={"sha": SHA, "files": FILES}, sha=SHA, status="indexed")
        db.add(repo); db.flush()
        review = Review(workspace_id=workspace_id, repo_id=repo.id, number=128, sha=SHA, title="Account route", files=demo["reviews"][0]["files"], checks={}, summary="Potential issues")
        db.add(review); db.flush()
        item = demo["findings"][1]
        finding = Finding(workspace_id=workspace_id, review_id=review.id, **{k: item[k] for k in ("severity", "title", "detail", "next_step", "evidence", "patch", "origin")})
        db.add(finding); db.flush()
        report = Report(workspace_id=workspace_id, period="sample", title="Private client report", markdown="Private content")
        db.add(report)
        job = service.create_job(db, repo, "index")
        db.commit()
        return repo.id, review.id, finding.id, report.id, job.id


def test_demo_needs_no_database_or_credentials(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    database.cache_clear()
    data = client.get("/api/demo").json()
    assert data["demo"] is True
    assert len(data["findings"]) == 2
    assert any(f["patch"] for f in data["findings"])
    assert client.get("/api/portfolio").status_code == 401
    assert client.get("/api/session").json()["user"] is None


@pytest.mark.parametrize("endpoint", ["portfolio", "reviews/missing", "reports/missing", "findings/missing/patch", "jobs/missing", "access"])
def test_private_api_is_closed_without_session(client, endpoint):
    assert client.get("/api/" + endpoint).status_code == 401


def test_login_origin_csrf_session_rotation_and_cache(client, monkeypatch):
    assert client.post("/api/login", json={"key": ADMIN}, headers={"Origin": "https://evil.example"}).status_code == 403
    login(client)
    cookie = client.cookies.get("sw_session")
    assert cookie and "httponly" in client.post("/api/login", json={"key": ADMIN}).headers["set-cookie"].lower()
    user = client.get("/api/session").json()["user"]
    client.headers["X-CSRF-Token"] = "bad"
    assert client.post("/api/workspaces", json={"name": "Rejected"}).status_code == 403
    client.headers["X-CSRF-Token"] = user["csrf"]
    result = client.get("/api/portfolio")
    assert result.headers["cache-control"] == "no-store, private"
    monkeypatch.setenv("STACKWISE_ADMIN_TOKEN", "rotated-test-owner-key-with-32-characters")
    assert client.get("/api/portfolio").status_code == 401


def test_repeated_bad_login_is_limited(client):
    for _ in range(15):
        assert client.post("/api/login", json={"key": "wrong-token-value-123"}, headers={"Origin": ORIGIN}).status_code == 401
    assert client.post("/api/login", json={"key": ADMIN}, headers={"Origin": ORIGIN}).status_code == 429


@pytest.mark.parametrize("role", ["viewer", "reviewer"])
def test_client_isolation_every_record_and_mutation(client, role):
    login(client)
    a, b = workspace(client, "Client Alpha"), workspace(client, "Client Beta")
    repo, review, finding, report, job = seed(b)
    key = client.post(f"/api/workspaces/{a}/access", json={"name": "A client", "role": role}).json()["key"]
    login(client, key)
    data = client.get("/api/portfolio").json()
    assert [w["id"] for w in data["workspaces"]] == [a]
    assert data["reviews"] == data["findings"] == data["repositories"] == data["reports"] == []
    for path in (f"reviews/{review}", f"reports/{report}", f"jobs/{job}", f"findings/{finding}/patch"):
        assert client.get("/api/" + path).status_code == 404
    for path, body in [(f"findings/{finding}", {"status": "resolved"}), (f"jobs/{job}/run", None),
                       (f"repositories/{repo}/ask", {"question": "What is private?"}),
                       (f"repositories/{repo}/index", None), (f"repositories/{repo}/reviews", {"number": 128}),
                       (f"workspaces/{b}/reports", None)]:
        result = client.post("/api/" + path, json=body)
        assert result.status_code == (403 if role == "viewer" else 404), (path, result.text)
    assert client.post("/api/workspaces", json={"name": "Unauthorized"}).status_code == 403
    assert client.post(f"/api/workspaces/{a}/connection", json={}).status_code == 403


def test_read_only_key_and_revocation(client):
    login(client)
    wid = workspace(client)
    _, rid, fid, _, _ = seed(wid)
    key_data = client.post(f"/api/workspaces/{wid}/access", json={"name": "Viewer", "role": "viewer"}).json()
    login(client, key_data["key"])
    assert client.get(f"/api/reviews/{rid}").status_code == 200
    assert client.post(f"/api/findings/{fid}", json={"status": "resolved"}).status_code == 403
    assert client.get(f"/api/findings/{fid}/patch").status_code == 200
    client_cookie = client.cookies.get("sw_session")
    login(client)
    client.post(f"/api/access/{key_data['id']}/revoke")
    client.cookies.set("sw_session", client_cookie, domain="testserver.local", path="/")
    assert client.get("/api/portfolio").status_code == 401


def test_reviewer_decisions_and_reports_are_honest(client):
    login(client)
    wid = workspace(client)
    _, rid, fid, _, _ = seed(wid)
    key = client.post(f"/api/workspaces/{wid}/access", json={"name": "Engineer", "role": "reviewer"}).json()["key"]
    login(client, key)
    result = client.post(f"/api/findings/{fid}", json={"status": "resolved", "feedback": "useful"})
    assert result.json()["status"] == "resolved"
    report = client.post(f"/api/workspaces/{wid}/reports").json()
    assert "reviewer-reported" in report["markdown"]
    assert "does not execute" in report["markdown"]
    assert "passing test" in report["markdown"]
    assert client.get(f"/api/reviews/{rid}").json()["sha"] == SHA


def test_connection_secrets_encrypted_and_never_returned(client):
    login(client)
    wid = workspace(client)
    token, secret = "github_pat_" + "a" * 60, "b" * 40
    assert client.post(f"/api/workspaces/{wid}/connection", json={"github_token": token, "webhook_secret": secret}).status_code == 200
    with database()() as db:
        row = db.get(Workspace, wid)
        assert token not in row.github_token and row.github_token.startswith("gAAAA")
    for path in ("portfolio", "session", "access"):
        text = client.get("/api/" + path).text
        assert token not in text and secret not in text


def test_signed_webhook_is_idempotent_and_workspace_scoped(client):
    login(client)
    a, b = workspace(client), workspace(client, "Second")
    repo_id, *_ = seed(a)
    secret = "webhook-test-secret-at-least-32-characters"
    with database()() as db:
        db.get(Workspace, a).webhook_secret = seal(secret)
        db.commit()
    raw = json.dumps({"action": "opened", "number": 128, "repository": {"full_name": "owner/repo"}, "pull_request": {"head": {"sha": SHA}}}).encode()
    headers = {"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()}
    assert client.post(f"/api/webhooks/{a}", content=raw).status_code == 401
    first = client.post(f"/api/webhooks/{a}", content=raw, headers=headers)
    second = client.post(f"/api/webhooks/{a}", content=raw, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["job"]["id"] == second.json()["job"]["id"]
    assert client.post(f"/api/webhooks/{b}", content=raw, headers=headers).status_code == 401


def test_vercel_rewrite_and_request_size(client):
    assert client.get("/api?endpoint=demo").json()["demo"] is True
    assert client.get("/api?endpoint=health&endpoint=demo").status_code == 400
    assert client.post("/api/login", content=b"a" * 256001).status_code == 413


def test_no_persistent_sqlite_on_vercel(client, monkeypatch):
    database.cache_clear(); monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="SQLite"):
        database()


def make_archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, data, kind in entries:
            info = tarfile.TarInfo("root/" + name)
            info.size = len(data)
            if kind == "link":
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                archive.addfile(info)
            else:
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def test_archive_is_redacted_and_traversal_and_links_never_extracted():
    token = "ghp_" + "x" * 40
    data = make_archive([("app.py", f'KEY = "{token}"\nprint("safe")\n'.encode(), "file"),
                         ("../../escape.py", b"bad", "file"), ("leak.py", b"", "link"),
                         (".env", b"secret", "file"), ("node_modules/no.py", b"skip", "file")])
    result = read_archive(data, SHA)
    assert list(result["files"]) == ["app.py"]
    assert token not in result["files"]["app.py"] and "[REDACTED]" in result["files"]["app.py"]
    assert result["files"]["app.py"].count("\n") == 2


@pytest.mark.parametrize("name", ["../../app.py", "/etc/passwd", "x\\y.py", "x/../y.py", ".env.local", "credentials.json", "node_modules/x.js"])
def test_untrusted_paths_and_sensitive_files_rejected(name):
    assert not accepted(name)


@pytest.mark.parametrize("name", ["https://evil.example/org/repo", "org/../repo", "a/b?token=secret", "a/b#main", "a/b/c"])
def test_arbitrary_network_targets_are_not_allowed(name):
    with pytest.raises(Exception): repository_name(name)


def test_redaction_private_key_multiline_and_db_url():
    source = 'password = "really-sensitive"\npostgres://user:secret@host/db\n-----BEGIN RSA PRIVATE KEY-----\nsecret\n-----END RSA PRIVATE KEY-----\n'
    result = redact(source)
    assert "really-sensitive" not in result and "secret" not in result
    assert result.count("\n") == source.count("\n")


def test_git_provider_errors_do_not_expose_tokens_or_upstream_body():
    with GitHub("private-token", transport=httpx.MockTransport(lambda r: httpx.Response(403, text="SENSITIVE"))) as provider:
        with pytest.raises(IntegrationError) as exc:
            provider.get("/repos/a/b")
    assert "SENSITIVE" not in str(exc.value) and "private-token" not in str(exc.value)


def test_index_job_commits_stages_preserves_old_snapshot_on_failure(client, monkeypatch):
    login(client); wid = workspace(client); repo_id, *_, job_id = seed(wid)
    def fail(*args, **kwargs): raise IntegrationError("Deliberate archive limit; original data retained.")
    monkeypatch.setattr(GitHub, "snapshot", fail)
    result = service.process_job(job_id)
    assert result["status"] == "failed"
    with database()() as db:
        assert db.get(Repository, repo_id).snapshot["sha"] == SHA
        assert db.get(Job, job_id).stage == "snapshot"
    # No retry happens on duplicate queue delivery of a failed stage.
    assert service.process_job(job_id)["status"] == "failed"


def test_review_job_duplicate_delivery_does_not_regenerate(client, monkeypatch):
    login(client); wid = workspace(client); repo_id, *_ = seed(wid)
    pull = {"number": 129, "title": "TLS hardening", "sha": "c" * 40, "base_sha": SHA,
            "files": [{"path": "client.py", "patch": "@@ -1 +1 @@\n+requests.get(url, verify=False)\n", "additions": 1, "deletions": 0, "status": "modified", "patch_available": True}],
            "snapshot": {"sha": "c" * 40, "files": {"client.py": "requests.get(url, verify=False)\n"}}, "ci": {}}
    monkeypatch.setattr(GitHub, "pull", lambda *a: pull)
    calls = []
    monkeypatch.setattr(analysis, "groq_json", lambda *a: (calls.append(1) or None, "not_configured"))
    with database()() as db:
        job = service.create_job(db, db.get(Repository, repo_id), "review", {"number": 129})
        jid = job.id
    assert service.process_job(jid)["stage"] == "analysis"
    result = service.process_job(jid)
    assert result["status"] == "complete" and result["result_id"]
    assert service.process_job(jid)["status"] == "complete"
    assert len(calls) == 1
    with database()() as db:
        findings = list(db.scalars(select(Finding).where(Finding.review_id == result["result_id"])))
        assert len(findings) == 1 and findings[0].patch


def test_ai_fabricated_or_unchanged_source_evidence_is_rejected(monkeypatch):
    pull = {"sha": SHA, "title": "Change", "snapshot": {"sha": SHA, "files": {"a.py": "first()\nsecond()\n"}}, "files": [{"path": "a.py", "patch": "@@ -1 +1 @@\n+first()"}]}
    base = {"title": "Potential issue", "severity": "high", "path": "a.py", "start": 2, "end": 2, "quote": "second()", "detail": "Some potential issue needs checking", "next_step": "Check caller"}
    monkeypatch.setattr(analysis, "groq_json", lambda *a: ({"findings": [base], "summary": "summary"}, "complete"))
    findings, metadata = analysis.ai_review(pull, [], [])
    assert not findings and metadata["rejected"] == 1
    base.update(start=1, end=1, quote="invented()")
    findings, metadata = analysis.ai_review(pull, [], [])
    assert not findings and metadata["rejected"] == 1


def test_bm25_retrieval_is_commit_pinned_and_does_not_execute_code():
    snapshot = {"sha": SHA, "files": {"a.py": "raise RuntimeError('never execute')\ndef lookup_account(user_id):\n    return user_id\n", "tests/test_a.py": "def test_lookup_account():\n    assert True\n"}}
    refs = analysis.retrieve(snapshot, "lookup account user_id")
    assert refs and all(r["sha"] == SHA and r["symbol"] and r["path"] for r in refs)


def test_patch_validates_unique_source_and_python_syntax():
    snap = {"sha": SHA, "files": {"a.py": "verify=False\n"}}
    assert "+verify=True" in analysis.replacement_patch(snap, "a.py", "verify=False", "verify=True")
    assert not analysis.replacement_patch(snap, "a.py", "missing", "replace")
    assert not analysis.replacement_patch(snap, "a.py", "verify=False", "invalid(")


def test_dependency_coverage_is_exact_direct_only_and_provider_failure_not_clean(monkeypatch):
    snap = {"sha": SHA, "files": {"package.json": json.dumps({"dependencies": {"exact": "1.0.0", "range": "^2.0.0"}}), "requirements.txt": "requests==2.31.0\nfastapi>=0.100\n"}}
    packages, skipped = analysis.direct_dependencies(snap)
    assert len(packages) == 2 and skipped == 2
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(503, request=httpx.Request("POST", "https://api.osv.dev")))
    result = analysis.dependency_check(snap)
    assert result["status"] == "unavailable" and "not been declared" in result["note"]


def test_cron_requires_secret_and_weekly_reports_deduplicate(client, monkeypatch):
    login(client); wid = workspace(client)
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret-with-at-least-32-characters")
    assert client.get("/api/cron").status_code == 401
    headers = {"Authorization": "Bearer test-cron-secret-with-at-least-32-characters"}
    assert client.get("/api/cron", headers=headers).status_code == 200
    assert client.get("/api/cron", headers=headers).status_code == 200
    with database()() as db:
        assert len(list(db.scalars(select(Report).where(Report.workspace_id == wid)))) == 1


def test_viewer_can_log_out_without_write_permission(client):
    login(client); wid = workspace(client)
    key = client.post(f"/api/workspaces/{wid}/access", json={"name": "Viewer", "role": "viewer"}).json()["key"]
    login(client, key)
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/session").json()["user"] is None


def test_request_changes_records_decision_without_github_write(client):
    login(client); wid = workspace(client); _, review, *_ = seed(wid)
    result = client.post(f"/api/reviews/{review}/decision", json={"status": "request_changes"})
    assert result.status_code == 200 and result.json()["status"] == "request_changes"
    assert client.get(f"/api/reviews/{review}").json()["status"] == "request_changes"


def test_validation_errors_do_not_echo_submitted_secrets(client):
    secret = "test-sensitive-value-never-echo"
    result = client.post("/api/login", json={"key": secret, "unknown": secret}, headers={"Origin": ORIGIN})
    assert result.status_code == 422 and secret not in result.text


def test_interrupted_job_is_explicitly_resumable(client):
    login(client); wid = workspace(client); *_, job_id = seed(wid)
    with database()() as db:
        job = db.get(Job, job_id)
        job.status, job.lease_until = "running", time.time() - 5
        db.commit()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "interrupted"


def test_queue_subscriber_imports_without_runtime_secrets(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL"); database.cache_clear()
    from src.stackwise.worker import handle_job
    assert handle_job is not None

@pytest.mark.parametrize('newer_finishes_first', [True, False])
def test_later_started_index_wins_even_when_jobs_overlap(client, monkeypatch, newer_finishes_first):
    login(client); wid = workspace(client); repo_id, *_, older_id = seed(wid)
    with database()() as db:
        older = db.get(Job, older_id); older.created = time.time() - 10
        db.commit()
        newer = service.create_job(db, db.get(Repository, repo_id), 'index')
        newer.created = time.time() - 5; db.commit(); newer_id = newer.id
    order = [(newer_id, 'b'), (older_id, 'a')] if newer_finishes_first else [(older_id, 'a'), (newer_id, 'b')]
    for jid, letter in order:
        monkeypatch.setattr(GitHub, 'snapshot', lambda *a, char=letter: {'sha': char * 40, 'files': {'a.py': f'name = "{char}"'}, 'branch': 'main'})
        assert service.process_job(jid)['stage'] == 'maintenance'
    with database()() as db:
        assert db.get(Repository, repo_id).sha == 'b' * 40


def test_portfolio_summaries_do_not_duplicate_source_or_patch_bodies(client):
    login(client); wid = workspace(client); _, review_id, *_ = seed(wid)
    portfolio = client.get('/api/portfolio').json()
    assert portfolio['findings'][0]['patch'] == ''
    assert portfolio['findings'][0]['evidence']['text'] == ''
    detail = client.get(f'/api/reviews/{review_id}').json()
    assert detail['findings'][0]['patch'] and detail['findings'][0]['evidence']['text']


def test_updating_webhook_preserves_existing_github_token(client):
    login(client); wid = workspace(client)
    client.post(f'/api/workspaces/{wid}/connection', json={'github_token': 'github_pat_' + 'a' * 60})
    with database()() as db:
        before = db.get(Workspace, wid).github_token
    client.post(f'/api/workspaces/{wid}/connection', json={'github_token': None, 'webhook_secret': 'b' * 40})
    with database()() as db:
        assert db.get(Workspace, wid).github_token == before
    client.post(f'/api/workspaces/{wid}/connection', json={'github_token': '', 'webhook_secret': ''})
    with database()() as db:
        assert not db.get(Workspace, wid).github_token and not db.get(Workspace, wid).webhook_secret


def test_python_string_literals_do_not_become_security_findings():
    source = 'example = "Never use eval(value) or verify=False"\n'
    result = analysis.static_review({'snapshot': {'sha': SHA, 'files': {'a.py': source}}, 'files': [{'path': 'a.py', 'patch': '@@ -0,0 +1 @@\n+' + source}]})
    assert not result


def test_explicit_ai_retry_retains_existing_human_decisions(client, monkeypatch):
    login(client); wid = workspace(client); repo_id, review_id, finding_id, *_ = seed(wid)
    with database()() as db:
        review = db.get(Review, review_id); review.checks = {'ai': 'provider_http_429'}
        finding = db.get(Finding, finding_id); finding.status = 'dismissed'; finding.feedback = 'false_positive'
        original = {k: getattr(finding, k) for k in ('severity','title','detail','next_step','evidence','patch','origin')}
        db.commit()
        job = service.create_job(db, db.get(Repository, repo_id), 'review', {'number':128, 'retry_ai':True, 'pull': {'number':128,'sha':SHA,'title':'Account route','base_sha':'a'*40,'snapshot':{'sha':SHA,'files':FILES},'files':[]}})
        job.stage = 'analysis'; db.commit(); jid=job.id
    monkeypatch.setattr(service, 'review_pull', lambda *a: {'findings':[original], 'context':[], 'checks':{'ai':'complete'}, 'summary':'Checked again', 'elapsed':1})
    assert service.process_job(jid)['status'] == 'complete'
    with database()() as db:
        assert db.get(Review, review_id).checks['ai'] == 'complete'
        finding = db.get(Finding, finding_id)
        assert finding.status == 'dismissed' and finding.feedback == 'false_positive'
        assert len(list(db.scalars(select(Finding).where(Finding.review_id == review_id)))) == 1
