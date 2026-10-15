"""Read-only GitHub integration. Never checks out, imports or executes client code."""
from __future__ import annotations

import io
import re
import tarfile
import time
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

import httpx

from .security import redact, repository_name, safe_path

EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".rb", ".php", ".rs", ".cs", ".c", ".h", ".cpp", ".kt", ".swift", ".sql", ".md", ".json", ".toml", ".yaml", ".yml", ".txt", ".html", ".css", ".scss", ".vue", ".svelte", ".sh", ".bash", ".xml"}
SKIP_DIRS = {".git", "node_modules", ".next", ".venv", "venv", "vendor", "dist", "build", "coverage", "__pycache__", ".terraform"}
MAX_FILES, MAX_FILE_BYTES, MAX_SOURCE_BYTES, MAX_ARCHIVE_BYTES = 350, 100_000, 3_000_000, 20_000_000


class IntegrationError(Exception):
    """Safe, deliberate user-facing integration error (no upstream body or tokens)."""


def accepted(path):
    parts = PurePosixPath(path).parts
    name = parts[-1] if parts else ""
    return bool(safe_path(path) and not SKIP_DIRS.intersection(parts) and
                not any(p.lower().startswith(".env") for p in parts) and
                not name.endswith((".lock", "-lock.json", ".min.js", ".map")) and
                not any(x in name.lower() for x in ("secret", "credential", "private-key")) and
                (PurePosixPath(path).suffix in EXTENSIONS or name == "Dockerfile"))


def read_archive(data, sha):
    """Read regular text members in memory; do not extract paths or follow links."""
    files, skipped, total, expanded = {}, 0, 0, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for i, member in enumerate(archive):
                if i > 30_000:
                    raise IntegrationError("This repository has too many archive entries for the starter limit.")
                expanded += max(0, member.size)
                if expanded > 80_000_000:
                    raise IntegrationError("The expanded repository exceeds the 80 MB archive limit.")
                if not member.isfile():
                    continue
                # GitHub archives have one generated root directory.
                path = member.name.split("/", 1)[1] if "/" in member.name else ""
                if not accepted(path) or member.size > MAX_FILE_BYTES:
                    skipped += 1
                    continue
                if len(files) >= MAX_FILES or total + member.size > MAX_SOURCE_BYTES:
                    raise IntegrationError("Repository exceeds the starter limit: 350 supported files / 3 MB source. No partial index was saved.")
                raw = archive.extractfile(member).read(MAX_FILE_BYTES + 1)
                if b"\x00" in raw:
                    skipped += 1
                    continue
                try:
                    source = raw.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
                files[path] = redact(source)
                total += len(raw)
    except (tarfile.TarError, OSError, EOFError):
        raise IntegrationError("GitHub returned an invalid repository archive.") from None
    if not files:
        raise IntegrationError("No supported UTF-8 source files were found.")
    return {"sha": sha, "files": files, "skipped": skipped, "source_bytes": total,
            "redaction": "Heuristic redaction applied; exclude sensitive files before connecting a repository."}


class GitHub:
    def __init__(self, token="", transport=None):
        self.deadline = time.monotonic() + 180
        self.client = httpx.Client(timeout=httpx.Timeout(35, connect=8), follow_redirects=False,
                                  transport=transport, headers={"Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "Stackwise/1.0",
                                  **({"Authorization": f"Bearer {token}"} if token else {})})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def get(self, path, params=None):
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise IntegrationError("The GitHub stage time budget was reached. Retry the saved stage later.")
            response = self.client.get("https://api.github.com" + path, params=params, timeout=min(35, remaining))
            if response.status_code in (403, 429):
                raise IntegrationError("GitHub access or rate limit reached. Check the repository token and retry later.")
            if response.status_code == 404:
                raise IntegrationError("Repository or pull request not found, or the token cannot read it.")
            if response.status_code != 200:
                raise IntegrationError(f"GitHub request failed (HTTP {response.status_code}).")
            if len(response.content) > 4_000_000:
                raise IntegrationError("GitHub metadata exceeds the supported response size.")
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise IntegrationError("GitHub could not be reached. No repository data was replaced.") from None

    def snapshot(self, name, sha=None):
        name = repository_name(name)
        meta = self.get(f"/repos/{name}")
        branch = meta["default_branch"]
        if sha is None:
            sha = self.get(f"/repos/{name}/commits/{quote(branch, safe='')}")["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise IntegrationError("GitHub returned an invalid commit reference.")
        # Obtain redirect from API, then use a fresh unauthenticated client for codeload.
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise IntegrationError("The GitHub stage time budget was reached.")
            response = self.client.get(f"https://api.github.com/repos/{name}/tarball/{sha}", timeout=min(35, remaining))
            location = response.headers.get("location", "")
            parsed = urlparse(location)
            if response.status_code != 302 or parsed.scheme != "https" or parsed.hostname != "codeload.github.com" or parsed.username:
                raise IntegrationError("GitHub archive download was not authorized.")
            data, deadline = bytearray(), min(self.deadline, time.monotonic() + 75)
            with httpx.Client(timeout=30, follow_redirects=False) as download:
                with download.stream("GET", location) as stream:
                    if stream.status_code != 200:
                        raise IntegrationError("The repository archive could not be downloaded.")
                    for chunk in stream.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_ARCHIVE_BYTES or time.monotonic() > deadline:
                            raise IntegrationError("Archive exceeds the 20 MB / 75 second download limit.")
            result = read_archive(bytes(data), sha)
            return {**result, "branch": branch}
        except httpx.HTTPError:
            raise IntegrationError("Repository archive download timed out. Previous data was retained.") from None

    def pulls(self, name):
        items = self.get(f"/repos/{name}/pulls", {"state": "open", "per_page": 30})
        return [{"number": x["number"], "title": redact(x["title"]), "sha": x["head"]["sha"],
                 "draft": x.get("draft", False)} for x in items]

    def pull(self, name, number):
        info = self.get(f"/repos/{name}/pulls/{number}")
        if info.get("changed_files", 0) > 60:
            raise IntegrationError("Split this PR before reviewing it: the first version supports 60 changed files.")
        files = self.get(f"/repos/{name}/pulls/{number}/files", {"per_page": 100})
        sha = info["head"]["sha"]
        if not info["head"].get("repo"):
            raise IntegrationError("The PR head repository is no longer available.")
        snapshot = self.snapshot(info["head"]["repo"]["full_name"], sha)
        return {"number": number, "title": redact(info["title"]), "sha": sha,
                "base_sha": info["base"]["sha"], "snapshot": snapshot,
                "files": [{"path": x["filename"], "patch": redact(x.get("patch", "")) if accepted(x["filename"]) else "",
                           "additions": x["additions"], "deletions": x["deletions"], "status": x["status"],
                           "patch_available": "patch" in x and accepted(x["filename"])} for x in files if safe_path(x["filename"])],
                "ci": self.ci(info["head"]["repo"]["full_name"], sha)}

    def ci(self, name, sha):
        try:
            data = self.get(f"/repos/{name}/commits/{sha}/check-runs", {"per_page": 50})
            return {"status": "observed", "commit_sha": sha, "runs": [
                {"name": redact(x["name"]), "status": x["status"], "conclusion": x.get("conclusion")}
                for x in data.get("check_runs", [])]}
        except IntegrationError:
            return {"status": "unavailable", "commit_sha": sha, "runs": [],
                    "note": "CI results could not be read; Stackwise did not execute tests."}
