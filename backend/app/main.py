"""FastAPI entrypoint: chat SSE endpoint + data endpoints + static frontend."""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import models, run_agent
from .tools import store

app = FastAPI(title="Dar Concierge API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
_hits: dict[str, deque] = defaultdict(deque)
RATE = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))


class Msg(BaseModel):
    role: str
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)


def _rate_limit(ip: str) -> None:
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE:
        raise HTTPException(429, "Too many messages — please wait a few seconds.")
    q.append(now)


@app.on_event("startup")
def _warm() -> None:
    store()  # build BM25 index once


@app.get("/api/health")
def health():
    return {"ok": True, "models": models(), "key_configured": bool(os.getenv("OPENROUTER_API_KEY"))}


@app.get("/api/stats")
def stats():
    return store().stats()


@app.get("/api/projects")
def projects():
    skip = ("mortgage", "invest", "exclusive plots", "welcome", "catalogue", "sohar")
    ps = [p for p in store().projects if p["image"] and not any(k in p["name"].lower() for k in skip)]
    ps.sort(key=lambda p: (-len(p["brands"]), p["section"] != "project", p["name"]))
    return [{"slug": p["slug"], "name": p["name"], "country": p["country"], "brands": p["brands"],
             "image": p["image"], "url": p["url"], "summary": (p["summary"] or "")[:200],
             "location": p["specs"].get("location")} for p in ps]


@app.get("/api/listings/map")
def listings_map():
    rows = store().con.execute(
        "SELECT id, title, purpose, city, price, lat, lon, url FROM listings WHERE lat IS NOT NULL").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    _rate_limit(request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0])

    async def gen():
        async for ev in run_agent([m.model_dump() for m in body.messages]):
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC / path
        return FileResponse(f if path and f.is_file() else STATIC / "index.html")
