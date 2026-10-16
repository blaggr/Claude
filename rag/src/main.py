from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import require_bearer
from .config import settings
from .ingest import last_run_status, run_ingest
from .rag import answer, stream_answer
from .scheduler import start_scheduler
from .store import count, list_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    scheduler = start_scheduler()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="QIC Research RAG", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = False


@app.get("/api/health")
async def health():
    return {"ok": True, "chunks": count(), "last_ingest": last_run_status()}


@app.get("/api/status", dependencies=[Depends(require_bearer)])
async def status():
    return {
        "chunks": count(),
        "sources": len(list_sources()),
        "last_ingest": last_run_status(),
        "config": {
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
            "seed_urls": settings.seed_urls,
        },
    }


@app.get("/api/sources", dependencies=[Depends(require_bearer)])
async def sources():
    return {"sources": list_sources()}


@app.post("/api/chat", dependencies=[Depends(require_bearer)])
async def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages required")
    history = [m.model_dump() for m in req.messages]

    if not req.stream:
        result = await asyncio.to_thread(answer, history)
        return result

    async def gen():
        async for ev in stream_answer(history):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/ingest", dependencies=[Depends(require_bearer)])
async def ingest(full: bool = False, background: bool = True):
    if background:
        asyncio.create_task(run_ingest(full=full))
        return {"started": True, "full": full}
    stats = await run_ingest(full=full)
    return {"started": True, "full": full, "stats": stats}


# Static web UI -- mounted last so /api/* takes precedence.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
