"""A stand-in for a provider that starts fast and finishes slow, so the pool's
whole-answer replacement can be watched in the app.

The free pool does not raise a replacement on its own: whichever model is ranked
first tends to both start and finish first. This proxy stands between llmbroker and
the real providers, one path prefix per provider, and holds the lane the reader is
being shown after its opening deltas, releasing it only once a sibling lane has
delivered a whole answer. Which lane that is is read off the race rather than
configured -- the first lane if it produces a delta inside the selection window,
otherwise whichever lane produced one first, which is how llmbroker picks the visible
stream. Non-streamed calls and unknown paths are relayed untouched.

Point a throwaway llmbroker home at it and run the app against that home::

    uv run python experiments/lane_proxy.py 8123

with every ``base_url`` in the home's ``model-list.toml`` rewritten to
``http://127.0.0.1:8123/<groq|openrouter|gemini|zai>``. Out of CI, like every
other harness here.
"""

import asyncio
import hashlib
import json
import os
import sys
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

UPSTREAM = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "zai": "https://api.z.ai/api/paas/v4",
}

WINDOW = float(os.environ.get("PROXY_WINDOW", "1.0"))
LEAD_SECONDS = float(os.environ.get("PROXY_LEAD_SECONDS", "1.5"))
LEAD_CHARS = int(os.environ.get("PROXY_LEAD_CHARS", "1200"))
MAX_STALL = float(os.environ.get("PROXY_MAX_STALL", "16.0"))
RELEASE_MARGIN = float(os.environ.get("PROXY_RELEASE_MARGIN", "0.6"))
GAMED = os.environ.get("PROXY_GAME", "1") != "0"

HOP = {"host", "content-length", "accept-encoding", "connection"}

app = FastAPI()
client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
races: dict[str, dict] = {}
start = time.monotonic()


def log(*parts: object) -> None:
    print(f"[{time.monotonic() - start:7.3f}]", *parts, flush=True)


def race_of(body: dict) -> dict:
    key = hashlib.sha1(json.dumps(body.get("messages", []), sort_keys=True).encode()).hexdigest()[:8]
    if key not in races:
        races[key] = {
            "key": key,
            "lanes": 0,
            "start": time.monotonic(),
            "lane1_delta": False,
            "visible": None,
            "sibling_done": asyncio.Event(),
        }
    return races[key]


def content_of(line: str) -> str:
    if not line.startswith("data:"):
        return ""
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return ""
    try:
        chunk = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    choices = chunk.get("choices") or [{}]
    return (choices[0].get("delta") or {}).get("content") or ""


def claims_the_reader(race: dict, seat: int) -> bool:
    """Whether this lane is the one whose deltas the app is showing."""
    if race["visible"] is not None:
        return race["visible"] == seat
    visible = seat == 1 or (
        not race["lane1_delta"] and time.monotonic() - race["start"] > WINDOW
    )
    if visible:
        race["visible"] = seat
    return visible


async def relay(upstream: str, request: Request, body: bytes, parsed: dict, lane: str):
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    race = race_of(parsed)
    race["lanes"] += 1
    seat = race["lanes"]
    log(f"race {race['key']} lane {seat} {lane}/{parsed.get('model', '?')} opened")

    async def stream():
        decided = False
        visible = False
        first_at = None
        sent = 0
        async with client.stream("POST", upstream, headers=headers, content=body) as resp:
            log(f"race {race['key']} lane {seat} upstream HTTP {resp.status_code}")
            async for raw in resp.aiter_lines():
                text = content_of(raw)
                if text and first_at is None:
                    first_at = time.monotonic()
                    if seat == 1:
                        race["lane1_delta"] = True
                    log(f"race {race['key']} lane {seat} first delta")
                if text:
                    sent += len(text)
                if not decided and first_at is not None and (
                    sent >= LEAD_CHARS or time.monotonic() - first_at >= LEAD_SECONDS
                ):
                    decided = True
                    visible = claims_the_reader(race, seat)
                    yield (raw + "\n").encode()
                    if visible:
                        log(f"race {race['key']} lane {seat} is the visible one — held after {sent} chars")
                        try:
                            await asyncio.wait_for(race["sibling_done"].wait(), MAX_STALL)
                            log(f"race {race['key']} lane {seat} released by a sibling's whole answer")
                        except TimeoutError:
                            log(f"race {race['key']} lane {seat} released by the stall cap")
                        await asyncio.sleep(RELEASE_MARGIN)
                    else:
                        log(f"race {race['key']} lane {seat} runs on at full speed")
                    continue
                yield (raw + "\n").encode()
        if decided and not visible:
            log(f"race {race['key']} lane {seat} finished its whole answer")
            race["sibling_done"].set()

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.api_route("/{lane}/{path:path}", methods=["GET", "POST"])
async def proxy(lane: str, path: str, request: Request):
    base = UPSTREAM.get(lane)
    if base is None:
        return Response(status_code=404, content=b"unknown lane")
    upstream = f"{base}/{path}"
    body = await request.body()
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = {}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    if parsed.get("stream"):
        if GAMED:
            return await relay(upstream, request, body, parsed, lane)

        async def passthrough():
            async with client.stream("POST", upstream, headers=headers, content=body) as resp:
                async for raw in resp.aiter_lines():
                    yield (raw + "\n").encode()

        log(f"{lane}/{parsed.get('model', '?')} streamed straight through")
        return StreamingResponse(passthrough(), media_type="text/event-stream")
    resp = await client.request(request.method, upstream, headers=headers, content=body)
    log(f"{lane}/{parsed.get('model', '?')} {request.method} {path} -> {resp.status_code}")
    return Response(
        status_code=resp.status_code,
        content=resp.content,
        media_type=resp.headers.get("content-type"),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
