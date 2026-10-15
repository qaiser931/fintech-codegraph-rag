"""Private Vercel Queue subscriber; imports safely without credentials at build time."""
import asyncio

from vercel.queue import Message, RetryAfter, subscribe

from .service import enqueue, process_job
from .store import Job, database


@subscribe(topic="stackwise-jobs", consumer_group="stackwise-worker", max_concurrency=2, max_attempts=5, retry_after=300)
async def handle_job(message: Message[dict[str, str]]):
    result = await asyncio.to_thread(process_job, message.payload["job_id"])
    if result and result["status"] == "running":
        raise RetryAfter(300)
    if result and result["status"] == "queued":
        with database()() as db:
            job = db.get(Job, result["id"])
            if await enqueue(job) != "queued":
                raise RetryAfter(60)
    # Failed stages are acknowledged, not repeatedly billed. Retry is an explicit owner action.
