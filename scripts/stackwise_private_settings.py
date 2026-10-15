"""Create private Vercel settings locally. Never print credentials or overwrite existing keys."""
from __future__ import annotations
import argparse
import base64
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse


def create(project: Path, app_url: str):
    parsed = urlparse(app_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Use the canonical HTTPS application origin, without a path or query.")
    target = project / ".env.stackwise.vercel"
    if target.exists():
        print("Existing private Stackwise settings retained; values not printed.")
        return target
    values = {
        "STACKWISE_APP_URL": app_url.rstrip("/"),
        "STACKWISE_ADMIN_TOKEN": secrets.token_urlsafe(40),
        "STACKWISE_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "CRON_SECRET": secrets.token_urlsafe(40),
        "STACKWISE_QUEUE_ENABLED": "1",
        "STACKWISE_QUEUE_REGION": "iad1",
    }
    # Exclusive creation, restrictive permissions on POSIX. Windows uses the project owner's ACL.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("# PRIVATE. Import into Vercel Production; never commit or share this file.\n")
        for key, value in values.items():
            stream.write(f"{key}={value}\n")
    print("Private Stackwise settings created in ignored .env.stackwise.vercel; values not printed.")
    print("Keep existing GROQ_API_KEY and LLM_MODEL. Connect Postgres for DATABASE_URL.")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--app-url", default="https://fintech-codegraph-rag.vercel.app")
    args = parser.parse_args()
    create(args.project.resolve(), args.app_url)
