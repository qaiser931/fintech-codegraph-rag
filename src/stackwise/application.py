"""Same-origin FastAPI API for Stackwise on Vercel. No local service hop."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from urllib.parse import parse_qsl, quote, urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from .analysis import answer, retrieve
from .demo import demo_data
from .security import (COOKIE, OAUTH_COOKIE, check_origin, digest, identity,
                       repository_name, seal, unseal, webhook_valid,
                       workspace_access)
from .service import create_job, enqueue, job_view, process_job, report_for
from .store import (AccessKey, Attempt, Audit, Finding, Job, Report, Repository,
                    Review, Session, Workspace, accessible_workspaces_query, database, scoped, uid)

app = FastAPI(title="Stackwise", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def boundary(request: Request, call_next):
    pairs = parse_qsl(request.scope.get("query_string", b"").decode(), keep_blank_values=True)
    endpoints = [v for k, v in pairs if k == "endpoint"]
    if len(endpoints) > 1:
        return JSONResponse({"error": "Send one endpoint."}, 400)
    if endpoints:
        request.scope["path"] = "/api/" + endpoints[0].lstrip("/")
        request.scope["query_string"] = urlencode([(k, v) for k, v in pairs if k != "endpoint"]).encode()
    # Reject large requests before any JSON/parser work, including chunked bodies.
    total = 0
    chunks = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > 256_000:
            return JSONResponse({"error": "Request exceeds the 256 KB limit."}, 413)
        chunks.append(chunk)
    request._body = b"".join(chunks)
    try:
        response = await call_next(request)
    except (RuntimeError, SQLAlchemyError):
        response = JSONResponse({"error": "The workspace database is not ready. Check DATABASE_URL in Vercel."}, 503)
    except Exception:
        response = JSONResponse({"error": "The request could not complete. Saved data was retained."}, 500)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({"error": exc.detail}, exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # FastAPI's default validation payload can echo submitted credentials.
    return JSONResponse({"error": "Check the submitted fields and their length or format."}, 422)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    key: str = Field(min_length=16, max_length=256)


class WorkspaceInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)


class ConnectInput(StrictModel):
    github_token: str | None = Field(default=None, max_length=400)
    webhook_secret: str | None = Field(default=None, max_length=256)


class RepoInput(StrictModel):
    repository: str = Field(min_length=3, max_length=250)


class ReviewInput(StrictModel):
    number: int = Field(ge=1, le=10_000_000)


class FindingInput(StrictModel):
    status: str = Field(pattern="^(open|dismissed|resolved)$")
    feedback: str | None = Field(default=None, pattern="^(useful|false_positive|uncertain)$")


class ReviewDecision(StrictModel):
    status: str = Field(pattern="^(approved|request_changes|needs_review)$")


class AccessInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    role: str = Field(pattern="^(reviewer|viewer)$")


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1500)


def owned(db, model, record_id, user):
    record = db.get(model, record_id)
    if not record:
        raise HTTPException(404, "Record not found.")
    workspace_access(user, record.workspace_id if model != Workspace else record.id, db)
    return record


def view(row, fields):
    return {k: getattr(row, k) for k in fields.split()}


def repo_view(row):
    return {**view(row, "id workspace_id full_name branch sha status indexed dependencies ci prs created"),
            "file_count": len((row.snapshot or {}).get("files", {}))}


def finding_view(row, summary=False):
    result = view(row, "id workspace_id review_id severity title detail next_step evidence patch origin status feedback updated created")
    if summary:
        result.update(patch="", detail="", evidence={**row.evidence, "text": ""})
    return result


def review_view(row, details=False):
    fields = "id workspace_id repo_id number title sha base_sha status summary checks elapsed created"
    return view(row, fields + (" files context" if details else ""))


@app.get("/api/health")
def health():
    return {"service": "stackwise", "version": 1, "runtime": "python", "storage": "postgres" if os.getenv("DATABASE_URL") else "not_configured",
            "demo_available": True, "ai_configured": bool(os.getenv("GROQ_API_KEY")),
            "queue_enabled": os.getenv("STACKWISE_QUEUE_ENABLED") == "1"}


@app.get("/api/demo")
def demo():
    return demo_data()


@app.get("/api/session")
def session(request: Request):
    setup = {"database": bool(os.getenv("DATABASE_URL")), "owner_key": len(os.getenv("STACKWISE_ADMIN_TOKEN", "")) >= 32,
             "application_url": bool(os.getenv("STACKWISE_APP_URL")), "encryption": bool(os.getenv("STACKWISE_ENCRYPTION_KEY")),
             "ai": bool(os.getenv("GROQ_API_KEY")), "queue": os.getenv("STACKWISE_QUEUE_ENABLED") == "1",
             "github_oauth": bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))}
    if not request.cookies.get(COOKIE):
        return {"user": None, "setup": setup}
    try:
        user = identity(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return {"user": None, "setup": setup}
        raise
    auth_method = "github" if user.access_id.startswith("github:") else ("owner_key" if user.access_id == "owner" else "workspace_key")
    return {"user": {"name": user.name, "role": user.role, "workspace_id": user.workspace_id, "csrf": user.csrf, "auth_method": auth_method}, "setup": setup}


@app.get("/api/auth/github")
def github_login(request: Request):
    client_id = os.getenv("GITHUB_CLIENT_ID", "")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return RedirectResponse("/dashboard?auth_error=github_not_configured", status_code=302)
    state = secrets.token_urlsafe(32)
    app_url = os.getenv("STACKWISE_APP_URL", "").rstrip("/")
    if not app_url:
        app_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{app_url}/api/auth/github/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }
    response = RedirectResponse(f"https://github.com/login/oauth/authorize?{urlencode(params)}", status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        state,
        httponly=True,
        secure=os.getenv("STACKWISE_LOCAL") != "1",
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@app.get("/api/auth/github/callback")
def github_callback(request: Request):
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description", "")
    if error:
        msg = error_description or error
        return RedirectResponse(f"/dashboard?auth_error={quote(msg)}", status_code=302)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    cookie_state = request.cookies.get(OAUTH_COOKIE, "")

    if not code or not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        return RedirectResponse("/dashboard?auth_error=invalid_oauth_state", status_code=302)

    client_id = os.getenv("GITHUB_CLIENT_ID", "")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return RedirectResponse("/dashboard?auth_error=github_not_configured", status_code=302)

    app_url = os.getenv("STACKWISE_APP_URL", "").rstrip("/")
    if not app_url:
        app_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{app_url}/api/auth/github/callback"

    try:
        with httpx.Client(timeout=15) as client:
            token_resp = client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json", "User-Agent": "Stackwise/1.0"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            token_data = token_resp.json() if token_resp.status_code == 200 else {}
            access_token = token_data.get("access_token")
            if not access_token:
                desc = token_data.get("error_description") or token_data.get("error") or "token_exchange_failed"
                return RedirectResponse(f"/dashboard?auth_error={quote(str(desc))}", status_code=302)

            user_resp = client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Stackwise/1.0",
                },
            )
            if user_resp.status_code != 200:
                return RedirectResponse("/dashboard?auth_error=failed_to_fetch_profile", status_code=302)
            user_info = user_resp.json()
    except Exception:
        return RedirectResponse("/dashboard?auth_error=github_service_error", status_code=302)

    gh_login = str(user_info.get("login", "")).strip()
    if not gh_login:
        return RedirectResponse("/dashboard?auth_error=invalid_user_data", status_code=302)

    gh_name = str(user_info.get("name") or gh_login).strip()
    access_id = f"github:{gh_login.lower()}"

    admin_users_str = os.getenv("GITHUB_ADMIN_USERS", "")
    is_admin = False
    if admin_users_str.strip():
        admin_users = [u.strip().lower() for u in admin_users_str.split(",") if u.strip()]
        if gh_login.lower() in admin_users:
            is_admin = True

    role = "owner"
    now = time.time()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)

    with database()() as db:
        db.execute(delete(Session).where(Session.expires < now))
        if is_admin:
            access_id = "owner"
            user_ws = db.scalar(select(Workspace).where((Workspace.owner_id == "owner") | (Workspace.owner_id == None)).order_by(Workspace.created.asc()))
            if not user_ws:
                user_ws = Workspace(name=f"{gh_name}'s Workspace", owner_id="owner")
                db.add(user_ws)
                db.flush()
                db.add(Audit(workspace_id=user_ws.id, actor=gh_name, action="workspace_created", subject=user_ws.id))
        else:
            user_ws = db.scalar(select(Workspace).where(Workspace.owner_id == access_id).order_by(Workspace.created.asc()))
            if not user_ws:
                user_ws = Workspace(name=f"{gh_name}'s Workspace", owner_id=access_id)
                db.add(user_ws)
                db.flush()
                db.add(Audit(workspace_id=user_ws.id, actor=gh_name, action="workspace_created", subject=user_ws.id))

        db.add(Session(
            id=digest(token),
            access_id=access_id,
            workspace_id=user_ws.id,
            role=role,
            name=gh_name,
            csrf=csrf,
            expires=now + 8 * 3600,
        ))
        db.add(Audit(
            workspace_id=user_ws.id,
            actor=gh_name,
            action="signed_in_github",
            subject=access_id,
        ))
        db.commit()

    response = RedirectResponse("/dashboard?signed_in=1", status_code=302)
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=os.getenv("STACKWISE_LOCAL") != "1",
        samesite="lax",
        max_age=8 * 3600,
        path="/",
    )
    response.delete_cookie(OAUTH_COOKIE, path="/")
    return response


@app.post("/api/login")
def login(body: Login, request: Request):
    check_origin(request)
    now, address = time.time(), digest(request.client.host if request.client else "unknown")
    with database()() as db:
        db.execute(delete(Attempt).where(Attempt.created < now - 900))
        attempts = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.address == address))
        total = db.scalar(select(func.count()).select_from(Attempt))
        if attempts >= 15 or total >= 100:
            raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes.")
        db.add(Attempt(address=address))
        db.commit()
        admin = os.getenv("STACKWISE_ADMIN_TOKEN", "")
        if len(admin) >= 32 and secrets.compare_digest(body.key, admin):
            role, workspace_id, name, access_id = "owner", digest(admin), "Agency owner", "owner"
        else:
            key = db.get(AccessKey, digest(body.key))
            if not key or key.revoked:
                raise HTTPException(401, "This access key was not recognized.")
            role, workspace_id, name, access_id = key.role, key.workspace_id, key.name, key.id
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute(delete(Session).where(Session.expires < now))
        db.add(Session(id=digest(token), access_id=access_id, workspace_id=workspace_id,
                       role=role, name=name, csrf=csrf, expires=now + 8 * 3600))
        db.add(Audit(workspace_id=None if role == "owner" else workspace_id, actor=name, action="signed_in", subject=access_id))
        db.commit()
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, token, httponly=True, secure=os.getenv("STACKWISE_LOCAL") != "1",
                        samesite="lax", max_age=8 * 3600, path="/")
    return response


@app.post("/api/logout")
def logout(request: Request):
    identity(request, write=True, allow_viewer=True)
    with database()() as db:
        db.execute(delete(Session).where(Session.id == digest(request.cookies.get(COOKIE, ""))))
        db.commit()
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


@app.get("/api/portfolio")
def portfolio(request: Request):
    user = identity(request)
    with database()() as db:
        workspaces = accessible_workspaces_query(user)
        def rows(model, limit=300):
            query = scoped(db.query(model), model, user)
            if hasattr(model, "created"):
                query = query.order_by(model.created.desc())
            return query.limit(limit).all()
        return {"demo": False,
                "workspaces": [{**view(w, "id name color created"), "github_connected": bool(w.github_token), "webhook_configured": bool(w.webhook_secret)} for w in db.scalars(workspaces)],
                "repositories": [repo_view(r) for r in rows(Repository)],
                "reviews": [review_view(r) for r in rows(Review)],
                "findings": [finding_view(f, summary=True) for f in rows(Finding, 1000)],
                "jobs": [job_view(j) for j in rows(Job, 100)],
                "reports": [view(r, "id workspace_id period title created") for r in rows(Report, 100)],
                "audit": [view(a, "id workspace_id actor action subject created") for a in rows(Audit, 100)],
                "limits": {"repositories_per_workspace": 10, "workspaces": 20, "files_per_snapshot": 350, "source_mb": 3},
                "truncated": "Portfolio lists up to 300 reviews, 1000 findings and 100 reports; filtered metrics describe loaded records."}


@app.post("/api/workspaces")
def add_workspace(body: WorkspaceInput, request: Request):
    user = identity(request, write=True, owner=True)
    with database()() as db:
        user_ws_count = db.scalar(select(func.count()).select_from(Workspace).where(Workspace.owner_id == user.access_id))
        if user_ws_count >= 20:
            raise HTTPException(409, "The first version supports 20 client workspaces.")
        row = Workspace(name=body.name.strip(), owner_id=user.access_id)
        if len(row.name) < 2:
            raise HTTPException(422, "Enter a workspace name.")
        db.add(row)
        db.flush()
        db.add(Audit(workspace_id=row.id, actor=user.name, action="workspace_created", subject=row.id))
        db.commit()
        return view(row, "id name color created")


@app.post("/api/workspaces/{workspace_id}/connection")
def connection(workspace_id: str, body: ConnectInput, request: Request):
    user = identity(request, write=True, owner=True)
    if body.github_token and not body.github_token.startswith(("github_pat_", "ghp_")):
        raise HTTPException(422, "Use a GitHub fine-grained, repository-scoped read-only token.")
    if body.webhook_secret and len(body.webhook_secret) < 32:
        raise HTTPException(422, "Use a random webhook secret of at least 32 characters.")
    with database()() as db:
        workspace = owned(db, Workspace, workspace_id, user)
        if body.github_token is not None:
            workspace.github_token = seal(body.github_token) if body.github_token else ""
        if body.webhook_secret is not None:
            workspace.webhook_secret = seal(body.webhook_secret) if body.webhook_secret else ""
        db.add(Audit(workspace_id=workspace_id, actor=user.name, action="github_connection_updated", subject=workspace_id))
        db.commit()
    return {"ok": True}


@app.post("/api/workspaces/{workspace_id}/access")
def add_access(workspace_id: str, body: AccessInput, request: Request):
    user = identity(request, write=True, owner=True)
    token = "sw_" + secrets.token_urlsafe(32)
    with database()() as db:
        owned(db, Workspace, workspace_id, user)
        if db.scalar(select(func.count()).select_from(AccessKey).where(AccessKey.workspace_id == workspace_id, AccessKey.revoked == 0)) >= 25:
            raise HTTPException(409, "Revoke an existing key before adding more than 25 workspace keys.")
        key = AccessKey(id=digest(token), workspace_id=workspace_id, name=body.name, role=body.role)
        db.add(key)
        db.add(Audit(workspace_id=workspace_id, actor=user.name, action="access_created", subject=key.id))
        db.commit()
        return {"key": token, "id": key.id, "note": "Copy now. Only a hash is stored; this value cannot be shown again."}


@app.get("/api/access")
def access_list(request: Request):
    user = identity(request, owner=True)
    with database()() as db:
        ws_ids = [w.id for w in db.scalars(accessible_workspaces_query(user))]
        return {"keys": [view(k, "id workspace_id name role revoked created") for k in db.scalars(select(AccessKey).where(AccessKey.workspace_id.in_(ws_ids)))]}


@app.post("/api/access/{key_id}/revoke")
def revoke_access(key_id: str, request: Request):
    user = identity(request, write=True, owner=True)
    with database()() as db:
        key = owned(db, AccessKey, key_id, user)
        key.revoked = 1
        db.add(Audit(workspace_id=key.workspace_id, actor=user.name, action="access_revoked", subject=key.id))
        db.commit()
    return {"ok": True}


@app.post("/api/workspaces/{workspace_id}/repositories")
async def add_repo(workspace_id: str, body: RepoInput, request: Request):
    user = identity(request, write=True, owner=True)
    name = repository_name(body.repository)
    with database()() as db:
        owned(db, Workspace, workspace_id, user)
        if db.scalar(select(Repository).where(Repository.workspace_id == workspace_id, func.lower(Repository.full_name) == name.lower())):
            raise HTTPException(409, "This repository is already connected to this workspace.")
        if db.scalar(select(func.count()).select_from(Repository).where(Repository.workspace_id == workspace_id)) >= 10:
            raise HTTPException(409, "The first version supports 10 repositories per workspace.")
        repo = Repository(workspace_id=workspace_id, full_name=name)
        db.add(repo)
        db.flush()
        db.add(Audit(workspace_id=workspace_id, actor=user.name, action="repository_connected", subject=name))
        job = create_job(db, repo, "index")
        return {"repository": repo_view(repo), "job": job_view(job), "delivery": await enqueue(job)}


async def start_job(repo_id, kind, request, payload=None):
    user = identity(request, write=True)
    with database()() as db:
        repo = owned(db, Repository, repo_id, user)
        pending = next((j for j in db.scalars(select(Job).where(Job.repo_id == repo.id, Job.kind == kind, Job.status.in_(("queued", "running"))))
                        if kind != "review" or j.payload.get("number") == (payload or {}).get("number")), None)
        if pending:
            return {"job": job_view(pending), "delivery": await enqueue(pending)}
        # A bounded daily budget protects shared cloud-provider quotas.
        recent = db.scalar(select(func.count()).select_from(Job).where(Job.workspace_id == repo.workspace_id, Job.created > time.time() - 86400))
        if recent >= 100:
            raise HTTPException(429, "Workspace daily job budget reached (100). Retry tomorrow.")
        job = create_job(db, repo, kind, payload)
        return {"job": job_view(job), "delivery": await enqueue(job)}


@app.post("/api/repositories/{repo_id}/index")
async def index_repo(repo_id: str, request: Request):
    return await start_job(repo_id, "index", request)


@app.post("/api/repositories/{repo_id}/reviews")
async def start_review(repo_id: str, body: ReviewInput, request: Request):
    return await start_job(repo_id, "review", request, {"number": body.number})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    user = identity(request)
    with database()() as db:
        return job_view(owned(db, Job, job_id, user))


@app.post("/api/jobs/{job_id}/run")
async def run_job(job_id: str, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        owned(db, Job, job_id, user)
    return await asyncio.to_thread(process_job, job_id)


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        job = owned(db, Job, job_id, user)
        if job.status != "failed":
            raise HTTPException(409, "Only failed jobs can be explicitly retried.")
        job.status, job.error, job.updated, job.lease_until = "queued", "", time.time(), 0
        db.add(Audit(workspace_id=job.workspace_id, actor=user.name, action="job_retry_requested", subject=job.id))
        db.commit()
        return {"job": job_view(job), "delivery": await enqueue(job)}


@app.get("/api/reviews/{review_id}")
def get_review(review_id: str, request: Request):
    user = identity(request)
    with database()() as db:
        row = owned(db, Review, review_id, user)
        result = {**review_view(row, True), "findings": [finding_view(f) for f in db.scalars(select(Finding).where(Finding.review_id == row.id, Finding.workspace_id == row.workspace_id))]}
        if len(json.dumps(result, ensure_ascii=False).encode()) > 3_500_000:
            raise HTTPException(413, "This PR evidence view exceeds the 3.5 MB response limit. Split the PR into smaller changes; saved review data was retained.")
        return result


@app.post("/api/reviews/{review_id}/retry-ai")
async def retry_ai_review(review_id: str, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        row = owned(db, Review, review_id, user)
        if (row.checks or {}).get("ai") == "complete":
            raise HTTPException(409, "AI review already completed for this head. Existing findings were retained.")
        if not os.getenv("GROQ_API_KEY"):
            raise HTTPException(503, "Configure GROQ_API_KEY before explicitly retrying AI review.")
        repo_id, payload = row.repo_id, {"number": row.number, "expected_sha": row.sha, "retry_ai": True}
    return await start_job(repo_id, "review", request, payload)


@app.post("/api/findings/{finding_id}")
def set_finding(finding_id: str, body: FindingInput, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        row = owned(db, Finding, finding_id, user)
        row.status, row.feedback, row.updated = body.status, body.feedback, time.time()
        db.add(Audit(workspace_id=row.workspace_id, actor=user.name, action="finding_" + body.status, subject=row.id))
        db.commit()
        return finding_view(row)


@app.post("/api/reviews/{review_id}/decision")
def review_decision(review_id: str, body: ReviewDecision, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        row = owned(db, Review, review_id, user)
        row.status = body.status
        db.add(Audit(workspace_id=row.workspace_id, actor=user.name, action="review_" + body.status, subject=row.id))
        db.commit()
        return review_view(row, True)


@app.get("/api/findings/{finding_id}/patch")
def patch(finding_id: str, request: Request):
    user = identity(request)
    with database()() as db:
        row = owned(db, Finding, finding_id, user)
        if not row.patch:
            raise HTTPException(404, "No source-validated patch preview is available for this finding.")
        return PlainTextResponse(row.patch, headers={"Content-Disposition": f'attachment; filename="stackwise-{row.id}.diff"'})


@app.post("/api/repositories/{repo_id}/ask")
async def ask_repo(repo_id: str, body: Question, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        repo = owned(db, Repository, repo_id, user)
        if not repo.snapshot:
            raise HTTPException(409, "Index this repository before asking about its code.")
        # Durable per-workspace AI budget, not a process-local limiter.
        recent = db.scalar(select(func.count()).select_from(Audit).where(Audit.workspace_id == repo.workspace_id, Audit.action == "code_question", Audit.created > time.time() - 3600))
        if recent >= 30:
            raise HTTPException(429, "Workspace question budget reached (30/hour).")
        db.add(Audit(workspace_id=repo.workspace_id, actor=user.name, action="code_question", subject=repo.id))
        db.commit()
        snapshot = repo.snapshot
    return await asyncio.to_thread(answer, snapshot, body.question)


@app.post("/api/workspaces/{workspace_id}/reports")
def generate_report(workspace_id: str, request: Request):
    user = identity(request, write=True)
    with database()() as db:
        workspace = owned(db, Workspace, workspace_id, user)
        report = report_for(db, workspace)
        return view(report, "id workspace_id period title markdown created")


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, request: Request):
    user = identity(request)
    with database()() as db:
        return view(owned(db, Report, report_id, user), "id workspace_id period title markdown created")


@app.post("/api/webhooks/{workspace_id}")
async def webhook(workspace_id: str, request: Request):
    raw = await request.body()
    with database()() as db:
        workspace = db.get(Workspace, workspace_id)
        if not workspace or not webhook_valid(raw, request.headers.get("x-hub-signature-256", ""), unseal(workspace.webhook_secret)):
            raise HTTPException(401, "Webhook signature rejected.")
        if request.headers.get("x-github-event") == "ping":
            return {"ok": True}
        if request.headers.get("x-github-event") != "pull_request":
            return {"ignored": True}
        try:
            body = json.loads(raw)
            if body.get("action") not in ("opened", "synchronize", "reopened", "ready_for_review"):
                return {"ignored": True}
            repo = db.scalar(select(Repository).where(Repository.workspace_id == workspace_id, Repository.full_name == body["repository"]["full_name"]))
            if not repo:
                raise HTTPException(404, "Repository is not connected to this workspace.")
            number, sha = int(body["number"]), body["pull_request"]["head"]["sha"]
            if not 1 <= number <= 10_000_000 or len(sha) != 40:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, "Invalid pull request event.") from None
        budget = db.scalar(select(func.count()).select_from(Job).where(Job.workspace_id == workspace_id, Job.created > time.time() - 86400))
        if budget >= 100:
            raise HTTPException(429, "Workspace daily job budget reached.")
        job = create_job(db, repo, "review", {"number": number, "expected_sha": sha}, f"pr:{workspace_id}:{repo.id}:{number}:{sha}")
        return {"job": job_view(job), "delivery": await enqueue(job)}


@app.get("/api/cron")
async def cron(request: Request):
    secret = os.getenv("CRON_SECRET", "")
    if len(secret) < 32 or not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + secret):
        raise HTTPException(401, "Cron authorization required.")
    with database()() as db:
        # Daily invocation, weekly deduplicated reports; manual refresh remains available.
        for workspace in db.scalars(select(Workspace).limit(20)):
            report_for(db, workspace, refresh=False)
        repos = list(db.scalars(select(Repository).order_by(Repository.indexed.asc().nullsfirst()).limit(5)))
        delivered = 0
        for repo in repos:
            pending = db.scalar(select(Job).where(Job.repo_id == repo.id, Job.status.in_(("queued", "running"))))
            job = pending or create_job(db, repo, "index", dedupe=f"daily:{repo.id}:{int(time.time() // 86400)}")
            delivered += (await enqueue(job)) == "queued"
        return {"reports": "weekly_snapshots_saved", "maintenance_jobs": len(repos), "queue_deliveries": delivered}
