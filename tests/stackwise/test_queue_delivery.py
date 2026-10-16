"""Exercise the real SDK callback/lease path without cloud credentials or AI."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from vercel.queue import RetryAfter, sanitize_name
from vercel.queue.embedded import create_embedded_queue_app

from api import queue_worker as callback
from src.stackwise import service, worker
from src.stackwise.github import IntegrationError
from src.stackwise.store import Job, Repository, Workspace, database


@pytest.fixture
def isolated_db(monkeypatch):
    monkeypatch.setenv("STACKWISE_LOCAL", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("STACKWISE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("STACKWISE_QUEUE_ENABLED", "1")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_DEPLOYMENT_ID", raising=False)
    database.cache_clear()
    with database()() as db:
        workspace = Workspace(name="Queue test")
        db.add(workspace); db.flush()
        repo = Repository(workspace_id=workspace.id, full_name="owner/repo")
        db.add(repo); db.flush()
        job = service.create_job(db, repo, "index")
        yield job.id
    database.cache_clear()


def test_explicit_trigger_matches_sdk_consumer_and_stays_out_of_main_rewrite():
    config = json.loads(Path("vercel.json").read_text())
    name = "api/queue_worker.py"
    options = config["functions"][name]
    assert options["regions"] == ["iad1"]
    assert options["maxDuration"] == 300
    assert options["experimentalTriggers"] == [{
        "type": "queue/v2beta", "topic": "stackwise-jobs", "maxConcurrency": 2,
        "maxDeliveries": 5, "retryAfterSeconds": 300,
    }]
    assert worker.QUEUE_CONSUMER == sanitize_name(name)
    assert str(worker.QUEUE_CONSUMER) == "api_Squeue__worker_Dpy"
    assert "queue_worker" in config["rewrites"][0]["source"]
    assert "[[tool.vercel.subscribers]]" not in Path("pyproject.toml").read_text()


def test_direct_http_cannot_start_job_without_queue_metadata(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("SDK must not be called for ordinary HTTP requests")
    monkeypatch.setattr(callback, "accept_and_handle", forbidden)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=callback.app), base_url="http://test") as client:
            assert (await client.post("/api/queue_worker", json={"job_id": "x"})).status_code == 404
            assert (await client.get("/api/queue_worker")).status_code == 405
            assert (await client.get("/docs")).status_code == 405
    asyncio.run(run())


def queue_headers():
    return {"ce-type": "com.vercel.queue.v2beta", "ce-vqsqueuename": "stackwise-jobs",
            "ce-vqsconsumergroup": str(worker.QUEUE_CONSUMER), "ce-vqsmessageid": "test-message"}


@pytest.mark.parametrize("field,value", [("ce-type", "wrong"), ("ce-vqsqueuename", "other"),
                                        ("ce-vqsconsumergroup", "other"), ("ce-vqsmessageid", "")])
def test_wrong_queue_metadata_is_rejected(field, value, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("unexpected queue must not run a stage")
    monkeypatch.setattr(callback, "accept_and_handle", forbidden)
    headers = {**queue_headers(), field: value}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=callback.app), base_url="http://test") as client:
            assert (await client.post("/", content=b"{}", headers=headers)).status_code == 404
    asyncio.run(run())


def test_callback_failure_is_not_returned_as_success(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("simulated delivery failure")
    monkeypatch.setattr(callback, "accept_and_handle", fail)
    async def run():
        transport = httpx.ASGITransport(app=callback.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.post("/", content=b"{}", headers=queue_headers())).status_code == 500
            assert (await client.post("/", content=b"x" * 16385, headers=queue_headers())).status_code == 413
    asyncio.run(run())


@pytest.mark.parametrize("fail_snapshot", [False, True])
def test_real_sdk_push_runs_and_acknowledges_durable_stages(isolated_db, monkeypatch, fail_snapshot):
    """Real SDK send → callback → database stage → next send → SDK acknowledgement."""
    queue = create_embedded_queue_app()
    sdk = queue.get_async_client()
    import vercel.queue
    monkeypatch.setattr(vercel.queue, "QueueClient", lambda **kwargs: sdk)
    monkeypatch.setattr(callback, "accept_and_handle", sdk.accept_and_handle)
    def snapshot(*args):
        if fail_snapshot:
            raise IntegrationError("Snapshot unavailable in test.")
        return {"sha": "a" * 40, "branch": "main", "files": {"a.py": "value = 1\n"}}
    monkeypatch.setattr(service.GitHub, "snapshot", snapshot)
    monkeypatch.setattr(service, "dependency_check", lambda *args: {"status": "complete", "packages": []})
    monkeypatch.setattr(service.GitHub, "pulls", lambda *args: [])
    monkeypatch.setattr(service.GitHub, "ci", lambda *args: {"status": "observed", "checks": []})
    async def run():
        with database()() as db:
            assert await service.enqueue(db.get(Job, isolated_db)) == "queued"
        seen = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=callback.app), base_url="http://test") as client:
            for _ in range(2):
                deliveries = list(queue.iter_push_deliveries("stackwise-jobs", str(worker.QUEUE_CONSUMER)))
                assert len(deliveries) == 1
                response = await client.post("/api/queue_worker", content=deliveries[0].body, headers=deliveries[0].headers)
                assert response.status_code == 204, response.text
                with database()() as db:
                    job = db.get(Job, isolated_db)
                    seen.append((job.stage, job.status))
                if fail_snapshot:
                    break
        assert not list(queue.iter_push_deliveries("stackwise-jobs", str(worker.QUEUE_CONSUMER)))
        if fail_snapshot:
            assert seen == [("snapshot", "failed")]
        else:
            assert seen == [("maintenance", "queued"), ("complete", "complete")]
        with database()() as db:
            assert len(list(db.scalars(select(Job)))) == 1
    asyncio.run(run())


@pytest.mark.parametrize("state,delay", [("running", 300), ("queued", 60)])
def test_stage_publish_failure_and_existing_lease_request_redelivery(isolated_db, monkeypatch, state, delay):
    result = {"id": isolated_db, "stage": "snapshot", "status": state}
    monkeypatch.setattr(worker, "process_job", lambda _: result)
    async def unavailable(_):
        return "manual"
    monkeypatch.setattr(worker, "enqueue", unavailable)
    with pytest.raises(RetryAfter) as exc:
        asyncio.run(worker.handle_job(SimpleNamespace(payload={"job_id": isolated_db})))
    assert exc.value.timeout_seconds == delay


def test_publication_is_stable_within_deployment_and_distinct_after_deploy(monkeypatch):
    import vercel.queue
    keys = []
    class FakeSDK:
        async def send(self, topic, payload, **kwargs):
            keys.append(kwargs["idempotency_key"])
    monkeypatch.setattr(vercel.queue, "QueueClient", lambda **kwargs: FakeSDK())
    monkeypatch.setenv("STACKWISE_QUEUE_ENABLED", "1")
    job = SimpleNamespace(id="same-job", stage="snapshot", status="queued", updated=123.4)
    async def run():
        for deployment in ("first", "first", "second"):
            monkeypatch.setenv("VERCEL_DEPLOYMENT_ID", deployment)
            assert await service.enqueue(job) == "queued"
    asyncio.run(run())
    assert keys[0] == keys[1] and keys[1] != keys[2]


def test_queue_failure_log_contains_type_without_exception_secrets(monkeypatch, capsys):
    import vercel.queue
    class FailingSDK:
        async def send(self, *args, **kwargs):
            raise RuntimeError("secret-token-and-database-url")
    monkeypatch.setattr(vercel.queue, "QueueClient", lambda **kwargs: FailingSDK())
    monkeypatch.setenv("STACKWISE_QUEUE_ENABLED", "1")
    job = SimpleNamespace(id="job", stage="snapshot", status="queued", updated=123)
    assert asyncio.run(service.enqueue(job)) == "manual"
    output = capsys.readouterr().out
    assert "RuntimeError" in output and "secret-token" not in output
