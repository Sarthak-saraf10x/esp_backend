"""
FastAPI Application Factory
----------------------------
Replaces the old Flask create_app().
- Mounts the WebSocket conversation route
- Starts the persistent MCP server on startup
- Keeps the old /audio_stream HTTP route disabled (returns 410 Gone with a hint)
"""

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="ESP32 AI Desktop Bot — Backend",
        version="2.0.0",
        description="Real-time WebSocket pipeline: STT → LLM → TTS",
    )

    # ── Startup: persistent MCP session ────────────────────────────────────
    from app.services.mcp_manager import start_mcp_server

    @app.on_event("startup")
    async def _startup():
        await start_mcp_server()

    # ── WebSocket route ─────────────────────────────────────────────────────
    from app.routes.ws_routes import router as ws_router
    app.include_router(ws_router)

    # ── Legacy HTTP endpoint tombstone ──────────────────────────────────────
    @app.post("/audio_stream")
    async def _legacy_audio_stream():
        return JSONResponse(
            status_code=410,
            content={
                "error": "Deprecated",
                "message": "This endpoint has been replaced by the WebSocket API. "
                           "Connect to ws://<host>:5000/ws/conversation instead.",
            },
        )

    @app.get("/health")
    async def _health():
        from app.services.mcp_manager import _mcp_session
        return {
            "status": "ok",
            "mcp_ready": _mcp_session is not None,
        }

    return app
