"""Resumable bounded jobs. Each stage commits before the next Vercel delivery."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .analysis import dependency_check, review_pull
from .github import GitHub, IntegrationError
from .security import unseal
from .store import Audit, Finding, Job, Report, Repository, Review, Workspace, database, uid


def create_job(db, repo, kind, payload=None, dedupe=None):
    dedupe = dedupe or uid()
    existing = db.scalar(select(Job).where(Job.dedupe == dedupe))
    if existing:
        return existing
    job = Job(workspace_id=repo.workspace_id, repo_id=repo.id, kind=kind,
              payload=payload or {}, dedupe=dedupe, stage="snapshot")
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(Job).where(Job.dedupe == dedupe))
    return job


def job_view(job):
    result = {k: getattr(job, k) for k in ("id", "workspace_id", "repo_id", "kind", "stage", "status", "error", "result_id", "created", "updated")}
    if result["status"] == "running" and job.lease_until < time.time():
        result["status"] = "interrupted"
    return result


def process_job(job_id):
    now = time.time()
    with database()() as db:
        claimed = db.execute(update(Job).where(Job.id == job_id, Job.lease_until < now,
                                              Job.status.in_(("queued", "running"))).values(status="running", lease_until=now + 290, updated=now))
        db.commit()
        job = db.get(Job, job_id)
        if not job:
            return None
        if not claimed.rowcount:
            return job_view(job)
        repo = db.get(Repository, job.repo_id)
        workspace = db.get(Workspace, job.workspace_id)
        try:
            with GitHub(unseal(workspace.github_token)) as github:
                if job.stage == "snapshot":
                    if job.kind == "review":
                        pull = github.pull(repo.full_name, int(job.payload["number"]))
                        expected = job.payload.get("expected_sha")
                        if expected and expected != pull["sha"]:
                            raise IntegrationError("The PR head changed after this event. Start a new review for the current commit.")
                        job.payload = {**job.payload, "pull": pull}
                        job.stage = "analysis"
                    else:
                        snapshot = github.snapshot(repo.full_name)
                        # A later-started completed index wins over an older concurrent job.
                        db.execute(update(Repository).where(Repository.id == repo.id, Repository.index_order <= job.created).values(
                            snapshot=snapshot, sha=snapshot["sha"], branch=snapshot["branch"],
                            indexed=time.time(), index_order=job.created, status="indexed"))
                        job.payload = {"snapshot": snapshot}
                        job.stage = "maintenance"
                elif job.stage == "maintenance":
                    snapshot = job.payload["snapshot"]
                    deps = dependency_check(snapshot)
                    pulls = github.pulls(repo.full_name)
                    ci = github.ci(repo.full_name, snapshot["sha"])
                    db.execute(update(Repository).where(Repository.id == repo.id, Repository.sha == snapshot["sha"]).values(
                        dependencies=deps, prs=pulls, ci=ci))
                    job.status, job.stage, job.payload = "complete", "complete", {}
                elif job.stage == "analysis":
                    pull = job.payload["pull"]
                    existing = db.scalar(select(Review).where(Review.repo_id == repo.id, Review.number == pull["number"], Review.sha == pull["sha"]))
                    if existing and (not job.payload.get("retry_ai") or (existing.checks or {}).get("ai") == "complete"):
                        job.result_id = existing.id
                    else:
                        history = [{"pr": r.number, "sha": r.sha, "summary": r.summary[:400]}
                                   for r in db.scalars(select(Review).where(Review.repo_id == repo.id, Review.workspace_id == workspace.id).order_by(Review.created.desc()).limit(5))]
                        result = review_pull(pull, history)
                        # Keep only changed-file source excerpts, not a duplicate full repository.
                        changed = [{**f, "source": pull["snapshot"]["files"].get(f["path"], "")}
                                   for f in pull["files"]]
                        review = existing
                        if review is None:
                            review = Review(workspace_id=workspace.id, repo_id=repo.id, number=pull["number"],
                                            title=pull["title"], sha=pull["sha"], base_sha=pull["base_sha"], files=changed,
                                            context=result["context"], checks=result["checks"], summary=result["summary"], elapsed=result["elapsed"])
                            db.add(review)
                            db.flush()
                        else:
                            review.context, review.checks, review.summary, review.elapsed = result["context"], result["checks"], result["summary"], result["elapsed"]
                        prior = {(f.title, f.evidence["path"], f.evidence["start"]) for f in db.scalars(select(Finding).where(Finding.review_id == review.id))}
                        for item in result["findings"]:
                            if (item["title"], item["evidence"]["path"], item["evidence"]["start"]) not in prior:
                                db.add(Finding(workspace_id=workspace.id, review_id=review.id, **item))
                                if review.status == "approved":
                                    review.status = "needs_review"
                        job.result_id = review.id
                    job.status, job.stage, job.payload = "complete", "complete", {}
                    db.add(Audit(workspace_id=workspace.id, actor="review-worker", action="review_completed", subject=job.result_id))
                else:
                    raise IntegrationError("This job has an unsupported stage.")
            if job.status != "complete":
                job.status = "queued"
            job.lease_until, job.updated, job.error = 0, time.time(), ""
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            # Never persist raw HTTP exceptions, credentials, response bodies or SQL errors.
            job.error = str(exc) if isinstance(exc, IntegrationError) else "The stage could not complete. Check server configuration; saved stages were retained."
            job.status, job.lease_until, job.updated = "failed", 0, time.time()
            db.commit()
        return job_view(job)


async def enqueue(job):
    if os.getenv("STACKWISE_QUEUE_ENABLED") != "1" or job.status != "queued":
        return "manual"
    try:
        from vercel.queue import DuplicateIdempotencyKeyError, QueueClient
        client = QueueClient(region=os.getenv("STACKWISE_QUEUE_REGION", "iad1"))
        try:
            await client.send("stackwise-jobs", {"job_id": job.id},
                              idempotency_key=f"{job.id}-{job.stage}-{int(job.updated)}-{os.getenv('VERCEL_DEPLOYMENT_ID', 'local')}")
        except DuplicateIdempotencyKeyError:
            pass
        return "queued"
    except Exception as exc:
        # The database is the source of truth: owner can run the saved stage explicitly.
        print(f"Stackwise queue unavailable: {type(exc).__name__}", flush=True)
        return "manual"


def report_for(db, workspace, *, refresh=True):
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    period = f"{iso.year}-W{iso.week:02d}"
    report = db.scalar(select(Report).where(Report.workspace_id == workspace.id, Report.period == period))
    if report and not refresh:
        return report
    repos = list(db.scalars(select(Repository).where(Repository.workspace_id == workspace.id)))
    findings = list(db.scalars(select(Finding).where(Finding.workspace_id == workspace.id)))
    reviews = list(db.scalars(select(Review).where(Review.workspace_id == workspace.id, Review.created >= time.time() - 7 * 86400)))
    open_items = [f for f in findings if f.status == "open"]
    resolved = [f for f in findings if f.status == "resolved" and f.updated >= time.time() - 7 * 86400]
    risks = sum(sum(bool(p.get("advisories")) for p in (r.dependencies or {}).get("packages", [])) for r in repos)
    lines = [f"# {workspace.name} · Weekly maintenance report", f"Period: {period}", f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}", "",
             "## What changed", f"- {len(reviews)} pull requests reviewed in the last 7 days.",
             f"- {len(resolved)} findings marked resolved by a reviewer in the last 7 days.",
             "", "## Open risks", f"- {len(open_items)} open review findings across {len(repos)} repositories.",
             f"- {risks} exact direct dependency versions have OSV advisory matches."]
    for finding in sorted(open_items, key=lambda f: {"high": 0, "medium": 1, "low": 2, "info": 3}.get(f.severity, 4))[:15]:
        ref = finding.evidence
        lines.extend([f"- **{finding.severity.upper()}: {finding.title}** — potential issue.",
                      f"  Evidence: `{ref['path']}:{ref['start']}-{ref['end']}` at `{ref['sha']}`.",
                      f"  Next step: {finding.next_step}"])
    lines.extend(["", "## Next steps", "Review open findings, validate suggested patches, and add regression tests before merging.", "",
                  "## Coverage and limitations", "Source-location checks do not prove a finding is correct. Findings require human validation.",
                  "Stackwise does not execute client code or tests, merge pull requests, or deploy changes.",
                  "Dependency coverage is exact direct npm/PyPI versions; ranges, lockfiles and transitive dependencies are not resolved.",
                  "Resolved means reviewer-reported, not a passing test or verified deployed fix."])
    for repo in repos:
        lines.append(f"- {repo.full_name}: index {repo.status}; dependency scan {(repo.dependencies or {}).get('status', 'not_run')}; CI {(repo.ci or {}).get('status', 'not_observed')}.")
    if not report:
        report = Report(workspace_id=workspace.id, period=period, title=f"{workspace.name} · {period}", markdown="")
        db.add(report)
    report.markdown, report.created = "\n".join(lines), time.time()
    db.commit()
    return report
