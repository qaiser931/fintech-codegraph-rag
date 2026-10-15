"""Access keys, browser sessions, secret redaction and untrusted-path handling."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from sqlalchemy import select

from .store import AccessKey, Session, database

COOKIE = "sw_session"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def seal(text):
    key = os.getenv("STACKWISE_ENCRYPTION_KEY", "")
    if not key:
        raise HTTPException(503, "Set STACKWISE_ENCRYPTION_KEY before connecting private repositories.")
    return Fernet(key.encode()).encrypt(text.encode()).decode()


def unseal(text):
    return Fernet(os.environ["STACKWISE_ENCRYPTION_KEY"].encode()).decrypt(text.encode()).decode() if text else ""


def redact(text):
    """Preserve line positions. Conservative redaction, not a secret-detection guarantee."""
    text = re.sub(r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----",
                  lambda m: "\n".join("[REDACTED PRIVATE KEY]" for _ in m.group().split("\n")), text, flags=re.S)
    patterns = [r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
                r"\b(?:gsk_|sk-)[A-Za-z0-9_-]{20,}\b", r"\bAKIA[A-Z0-9]{16}\b",
                r"(?i)(?<=bearer )[A-Za-z0-9._~+/=-]{12,}"]
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    text = re.sub(r"(?im)((?:[\w-]*(?:password|secret|api[_-]?key|access[_-]?token)[\w-]*)\s*[=:]\s*)([\"'])([^\n\"']{6,})\2",
                  lambda m: m[1] + m[2] + "[REDACTED]" + m[2], text)
    # Hide credentials in database/service URLs.
    text = re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    return text


def safe_path(path):
    if not isinstance(path, str) or "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path) or len(path) > 300:
        return False
    return bool(path and not path.startswith("/") and all(p not in ("..", ".", "") for p in path.split("/")))


def repository_name(value):
    value = value.strip().rstrip("/").removesuffix(".git")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/"):]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}", value):
        raise HTTPException(422, "Use owner/repository or an https://github.com/owner/repository URL.")
    if any(x in (".", "..") for x in value.split("/")):
        raise HTTPException(422, "Invalid repository name.")
    return value


def check_origin(request: Request):
    origin = request.headers.get("origin", "")
    expected = os.getenv("STACKWISE_APP_URL", "").rstrip("/")
    if not expected and os.getenv("STACKWISE_LOCAL") == "1":
        expected = str(request.base_url).rstrip("/")
    if not origin or not expected or origin != expected:
        raise HTTPException(403, "Open Stackwise on its configured application URL.")


@dataclass
class Identity:
    role: str
    workspace_id: str | None
    name: str
    csrf: str
    access_id: str


def identity(request: Request, *, write=False, owner=False, allow_viewer=False):
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(401, "Sign in to your agency workspace.")
    with database()() as db:
        session = db.get(Session, digest(token)) if token else None
        if not session or session.expires < time.time():
            raise HTTPException(401, "Sign in to your agency workspace.")
        if session.access_id == "owner":
            if session.workspace_id != digest(os.getenv("STACKWISE_ADMIN_TOKEN", "")):
                raise HTTPException(401, "Your agency access key changed. Sign in again.")
            workspace_id = None
        else:
            key = db.get(AccessKey, session.access_id)
            if not key or key.revoked:
                raise HTTPException(401, "This workspace access key has been revoked.")
            workspace_id = key.workspace_id
        result = Identity(session.role, workspace_id, session.name, session.csrf, session.access_id)
    if owner and result.role != "owner":
        raise HTTPException(403, "Only the agency owner can perform this action.")
    if write:
        check_origin(request)
        if result.role == "viewer" and not allow_viewer:
            raise HTTPException(403, "This client access key is read-only.")
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), result.csrf):
            raise HTTPException(403, "Refresh the page before making this change.")
    return result


def workspace_access(user, workspace_id):
    if user.role != "owner" and user.workspace_id != workspace_id:
        raise HTTPException(404, "Workspace not found.")


def webhook_valid(body, signature, secret):
    return bool(secret and hmac.compare_digest(signature, "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()))
