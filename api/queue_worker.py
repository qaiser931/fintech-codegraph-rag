"""Private Vercel Queues callback; never a public job-processing API.

The queue/v2beta trigger in vercel.json is the platform access boundary.
CloudEvent headers alone are not authentication. The SDK claims the delivery,
renews its lease, dispatches the subscriber and acknowledges only after success.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request, Response
from vercel.queue import accept_and_handle

# Import registers the existing stage handler; no database/provider work at import.
from src.stackwise.worker import QUEUE_CONSUMER, handle_job

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.post("/{path:path}")
async def delivery(request: Request, path: str):
    headers = request.headers
    if (headers.get("ce-type") != "com.vercel.queue.v2beta"
            or headers.get("ce-vqsqueuename") != "stackwise-jobs"
            or headers.get("ce-vqsconsumergroup") != str(QUEUE_CONSUMER)
            or not headers.get("ce-vqsmessageid")):
        return Response(status_code=404)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16_384:
            return Response(status_code=413)
    # Failures propagate so Vercel can redeliver. Do not acknowledge in finally.
    await accept_and_handle(bytes(body), headers, lease_duration=300)
    return Response(status_code=204)
