"""GET /api/v1/compare/stream — SSE with replay (race condition fix).

Flow:
1. Client connects after POST /compare returned comparison_id.
2. HGETALL comparison:{id}:results — replay any results already stored.
3. If _final exists → send all events + comparison_ready, close.
4. Else → SUBSCRIBE comparison:{id}, forward live events.
5. Hard timeout: 15 seconds.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/v1", tags=["compare"])

HARD_TIMEOUT_SECONDS = 15
RESULTS_KEY_PREFIX = "comparison:"
RESULTS_KEY_SUFFIX = ":results"


@router.get("/compare/stream")
async def compare_stream(
    request: Request,
    id: str = Query(..., description="comparison_id from POST /compare"),
) -> EventSourceResponse:
    """SSE stream for comparison results with replay on connect."""
    redis = request.app.state.redis

    async def event_generator():
        results_key = f"{RESULTS_KEY_PREFIX}{id}{RESULTS_KEY_SUFFIX}"
        channel_name = f"{RESULTS_KEY_PREFIX}{id}"

        # ── 1. REPLAY: check if results already exist ───────
        existing = await redis.hgetall(results_key)
        if existing:
            # Emit platform results first (everything except _final)
            for field, data in existing.items():
                if field == "_final":
                    continue
                yield {
                    "event": "platform_status",
                    "data": data,
                }

            # If worker already finished, emit final and close
            if "_final" in existing:
                yield {
                    "event": "comparison_ready",
                    "data": existing["_final"],
                }
                return

        # ── 2. SUBSCRIBE: wait for live results ─────────────
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_name)

        try:
            loop = asyncio.get_event_loop()
            deadline = loop.time() + HARD_TIMEOUT_SECONDS

            # After subscribing, check hash again — worker might have
            # finished between our HGETALL and SUBSCRIBE (second race window)
            existing_after_sub = await redis.hgetall(results_key)
            already_sent = set(existing.keys()) if existing else set()

            for field, data in existing_after_sub.items():
                if field == "_final" or field in already_sent:
                    continue
                yield {
                    "event": "platform_status",
                    "data": data,
                }
                already_sent.add(field)

            if "_final" in existing_after_sub and "_final" not in already_sent:
                yield {
                    "event": "comparison_ready",
                    "data": existing_after_sub["_final"],
                }
                return

            # ── Listen for pub/sub messages ─────────────────
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    yield {
                        "event": "timeout",
                        "data": json.dumps({"message": "Comparison timed out after 15s"}),
                    }
                    return

                # Check for disconnect
                if await request.is_disconnected():
                    return

                # Wait for next message with timeout
                try:
                    message = await asyncio.wait_for(
                        _get_next_message(pubsub),
                        timeout=min(remaining, 1.0),
                    )
                except asyncio.TimeoutError:
                    # Send keepalive comment to detect broken connections
                    yield {"comment": "keepalive"}
                    continue

                if message is None:
                    continue

                if message["type"] != "message":
                    continue

                raw_data = message["data"]
                try:
                    parsed = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                event_type = parsed.get("event", "platform_status")

                if event_type == "ready":
                    yield {
                        "event": "comparison_ready",
                        "data": raw_data,
                    }
                    return
                else:
                    yield {
                        "event": "platform_status",
                        "data": raw_data,
                    }

        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.aclose()

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )


async def _get_next_message(pubsub) -> dict | None:
    """Read next message from pubsub, handling the async iterator."""
    message = await pubsub.get_message(
        ignore_subscribe_messages=True,
        timeout=1.0,
    )
    return message
