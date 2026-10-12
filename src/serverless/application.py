"""Public sample-code facade with server-bound roles and the unchanged core API."""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import threading

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import app_state
from src.api.routes import router
from src.config import settings
from src.generation.generator import CodeRAGGenerator
from src.retrieval.hybrid import HybridRetriever
from src.serverless.retrieval import OnnxReranker, ReadOnlyIndexer

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "codegraph_assets"
ROLES = ("Junior Dev", "Senior Dev", "Security Lead")
_lock = threading.Lock()
core = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
core.include_router(router)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def initialize():
    with _lock:
        if app_state.ready:
            return
        if settings.llm_provider != "groq":
            raise RuntimeError("The serverless profile requires Groq.")
        if settings.default_tenant_id != "fintech-pk-corp":
            raise RuntimeError("Rebuild the immutable corpus for a different tenant.")
        settings.base_dir = ROOT
        settings.sample_codebase_dir = ROOT / "data/sample_codebase"
        indexer = ReadOnlyIndexer(ASSETS)
        retriever = HybridRetriever(indexer, reranker=OnnxReranker(ASSETS / "reranker"))
        app_state.indexer = indexer
        app_state.retriever = retriever
        app_state.generator = CodeRAGGenerator(retriever)
        app_state.ready = True


def fail(status, message):
    return JSONResponse({"error": message}, status_code=status,
                        headers={"Cache-Control": "no-store"})


def public_token(role):
    # Same sample-role selector as the former Node facade. This is not user login.
    if role not in ROLES:
        raise HTTPException(400, "Choose a valid investigator role.")
    for key, value in settings.api_role_tokens.items():
        if value == role and len(key) >= 16 and key == key.strip() and not re.search(r"[\r\n]", key):
            return key
    raise HTTPException(503, "A server role credential is not configured.")


class SourceText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.active = [], False

    def handle_starttag(self, tag, attrs):
        if tag == "span" and re.fullmatch(r"L\d+", dict(attrs).get("id", "")):
            self.active = True
            self.lines.append("")

    def handle_endtag(self, tag):
        if tag == "span":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.lines[-1] += data

    def code(self):
        return "\n".join("" if x == "\u00a0" else x for x in self.lines)


ERRORS = {
    400: "The request was rejected. Check your question and role.",
    401: "The server role credential was rejected.",
    403: "Access was denied for your selected role.",
    404: "The requested source or endpoint was not found.",
    422: "The request format was rejected.",
    429: "The service quota was reached. Try again later.",
    503: "The backend or generation provider is unavailable. Check its configuration.",
    504: "Generation timed out. Try again later.",
}


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def dispatch(request: Request, path: str):
    # Rewrites may retain the original path or supply the destination path.
    endpoints = request.query_params.getlist("endpoint")
    if len(endpoints) > 1:
        return fail(400, "Send one endpoint.")
    endpoint = endpoints[0] if endpoints else path.removeprefix("api/")
    if endpoint not in ("health", "retrieve", "query") and not endpoint.startswith("source/"):
        return fail(404, ERRORS[404])
    expected_method = "POST" if endpoint in ("query", "retrieve") else "GET"
    if request.method != expected_method:
        return fail(405, "This endpoint does not support that method.")
    body = None
    try:
        if endpoint in ("query", "retrieve"):
            # Bound body size before deserializing; do not pass unrelated client fields.
            raw = await request.body()
            if len(raw) > 48_000:
                return fail(413, "The question or stack trace is too large.")
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return fail(400, "Send a valid JSON request.")
            if not isinstance(value, dict):
                return fail(400, "Send a question and investigator role.")
            role = value.get("role")
            query = value.get("query")
            stack = value.get("stack_trace")
            if not isinstance(query, str) or not 3 <= len(query.strip()) <= 2000:
                return fail(400, "The question must contain 3–2000 characters.")
            if stack is not None and (not isinstance(stack, str) or len(stack.strip()) > 8000):
                return fail(400, "The stack trace must be text of at most 8000 characters.")
            body = {"query": query.strip(), "role": role, "stack_trace": stack.strip() or None if stack else None}
        elif endpoint.startswith("source/"):
            role = request.query_params.get("role")
            parts = endpoint.removeprefix("source/").split("/")
            if (len(parts) < 3 or parts[:2] != ["data", "sample_codebase"]
                or not parts[-1].endswith(".py")
                or any(not re.fullmatch(r"[a-zA-Z0-9_.-]+", p) or p in (".", "..") for p in parts)):
                return fail(400, "Choose a Python source inside the sample codebase.")
        else:
            role = None
        headers = {}
        if role is not None:
            token = public_token(role)
            # Explicit credentials remain subject to the core 401/403 checks.
            headers["Authorization"] = request.headers.get("authorization") or f"Bearer {token}"
        elif endpoint != "health":
            return fail(400, "Choose a valid investigator role.")
        await run_in_threadpool(initialize)
        params = {"role": role} if endpoint.startswith("source/") else None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=core),
                                     base_url="http://codegraph-internal") as client:
            response = await client.request(request.method, "/" + endpoint,
                                            headers=headers, json=body, params=params)
        if not response.is_success:
            return fail(response.status_code, ERRORS.get(response.status_code, "The backend could not complete this request."))
        if endpoint.startswith("source/"):
            parser = SourceText()
            parser.feed(response.text)
            data = {"code": parser.code(), "file_path": endpoint.removeprefix("source/")}
        else:
            data = response.json()
            if endpoint == "health":
                data.update(ok=data.get("status") == "healthy" and data.get("indexed") is True,
                            checked_at=datetime.now(timezone.utc).isoformat())
        return JSONResponse(data, headers={"Cache-Control": "no-store"})
    except HTTPException as exc:
        return fail(exc.status_code, str(exc.detail))
    except Exception:
        # Never expose provider responses, paths or credential-bearing exception text.
        return fail(503, "The serverless backend could not initialize or complete this request. Check the Vercel function logs.")
