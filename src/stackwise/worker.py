"""Stage handler for the explicitly deployed private api/queue_worker.py function."""
import asyncio

from vercel.queue import Message, RetryAfter, sanitize_name, subscribe

from .service import enqueue, process_job
from .store import Job, database


# Vercel derives a v2beta consumer from the exact functions configuration key.
# Use the SDK's matching reversible encoding (including the .py extension).
QUEUE_CONSUMER = sanitize_name("api/queue_worker.py")


@subscribe(topic="stackwise-jobs", consumer_group=QUEUE_CONSUMER, max_concurrency=2, max_attempts=5, retry_after=300)
async def handle_job(message: Message[dict[str, str]]):
    result = await asyncio.to_thread(process_job, message.payload["job_id"])
    if result:
        print(f"Stackwise worker: job={result['id']} stage={result['stage']} status={result['status']}", flush=True)
    if result and result["status"] == "running":
        raise RetryAfter(300)
    if result and result["status"] == "queued":
        with database()() as db:
            job = db.get(Job, result["id"])
            if await enqueue(job) != "queued":
                raise RetryAfter(60)
    # Failed stages are acknowledged, not repeatedly billed. Retry is an explicit owner action.
