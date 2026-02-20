"""
Demo App — FastAPI assembly file.
Imports core modules, sets up lifespan, mounts health + chat + frontend.

Add your domain-specific routes below the marked section.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from backend.core.lakebase import _init_pg_pool
from backend.core.health import health_router
from backend.core.streaming import stream_mas_chat

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# ─── Chat history (in-memory, per-process) ────────────────────────────────
_chat_history: list[dict] = []

# ─── Action card config for your domain ───────────────────────────────────
# Override this list to detect entities created by the MAS agent during chat.
# Each entry maps a Lakebase table to an action card in the chat UI.
#
# ACTION_CARD_TABLES = [
#     {
#         "table": "work_orders",
#         "card_type": "work_order",
#         "id_col": "work_order_id",
#         "title_template": "Work Order {wo_number}",
#         "actions": ["approve", "dismiss"],
#         "detail_cols": {"asset": "asset_name", "priority": "priority", "status": "status"},
#     },
# ]
ACTION_CARD_TABLES: list[dict] = []


# ─── Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        _init_pg_pool()
    except Exception as e:
        log.warning("Lakebase pool init deferred: %s", e)
    yield


app = FastAPI(title="Demo App", lifespan=lifespan)

# ─── Health endpoint ──────────────────────────────────────────────────────
app.include_router(health_router)


# ─── Chat endpoint (MAS streaming) ───────────────────────────────────────

@app.post("/api/chat")
async def chat(body: dict):
    """Streaming SSE endpoint for MAS chat."""
    message = body.get("message", "").strip()
    context = body.get("context", "").strip()
    if not message:
        raise HTTPException(400, "Empty message")

    full_message = f"Context: {context}\n\nQuestion: {message}" if context else message
    _chat_history.append({"role": "user", "content": full_message})

    async def event_stream():
        final_text = ""
        async for chunk in stream_mas_chat(message, _chat_history, ACTION_CARD_TABLES):
            yield chunk
            # Track final text for chat history
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    evt = json.loads(chunk[6:])
                    if evt.get("type") == "delta":
                        final_text += evt.get("text", "")
                except (json.JSONDecodeError, KeyError):
                    pass
        if final_text:
            _chat_history.append({"role": "assistant", "content": final_text})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════════════
# --- Add your domain routes below ---
# ═══════════════════════════════════════════════════════════════════════════
#
# Example:
#   from backend.core import run_query, run_pg_query, write_pg, _safe
#
#   @app.get("/api/my-domain/metrics")
#   async def get_metrics():
#       return await asyncio.to_thread(run_query, "SELECT COUNT(*) as total FROM my_table")
#
#   @app.get("/api/my-domain/items")
#   async def get_items(status: str = None):
#       if status:
#           return await asyncio.to_thread(
#               run_pg_query,
#               "SELECT * FROM items WHERE status = %s ORDER BY created_at DESC",
#               (_safe(status),),
#           )
#       return await asyncio.to_thread(run_pg_query, "SELECT * FROM items ORDER BY created_at DESC")


# ─── Frontend Serving ─────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend", "src")), name="static")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "index.html"))
