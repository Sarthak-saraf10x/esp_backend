"""
Persistent MCP Server Manager
------------------------------
Starts mcp_server.py ONCE at FastAPI startup and keeps the session alive
for the entire process lifetime. All WebSocket conversations share the same
MCP session — eliminating the ~300ms per-request subprocess spawn cost.
"""

import asyncio
import os
import sys
import logging

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from app.config import Config

logger = logging.getLogger(__name__)

_mcp_session: ClientSession | None = None
_mcp_tools: list = []
_mcp_ready = asyncio.Event()


async def start_mcp_server():
    """
    Called once at FastAPI startup via @app.on_event("startup").
    Spawns the MCP subprocess and holds the session open indefinitely
    in a background asyncio task.
    """
    asyncio.create_task(_run_mcp_forever())
    # Wait up to 10s for MCP to initialise before accepting requests
    try:
        await asyncio.wait_for(_mcp_ready.wait(), timeout=10.0)
        logger.info("[MCP] Persistent session ready with %d tools", len(_mcp_tools))
    except asyncio.TimeoutError:
        logger.error("[MCP] Session did not initialise within 10s — tools unavailable")


async def _run_mcp_forever():
    """Background task: owns the MCP subprocess lifetime."""
    global _mcp_session, _mcp_tools

    params = StdioServerParameters(
        command=sys.executable,
        args=[Config.MCP_SERVER_SCRIPT],
        env=os.environ.copy()
    )

    while True:  # Restart on unexpected subprocess death
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    _mcp_tools = result.tools
                    _mcp_session = session
                    _mcp_ready.set()
                    logger.info("[MCP] Server running — %d tools loaded", len(_mcp_tools))
                    # Hold context open forever (never returns normally)
                    await asyncio.get_event_loop().create_future()
        except Exception as e:
            logger.error("[MCP] Session crashed: %s — restarting in 3s", e)
            _mcp_session = None
            _mcp_ready.clear()
            await asyncio.sleep(3)


async def get_mcp_session() -> tuple[ClientSession | None, list]:
    """Return the live MCP session and registered tools list."""
    return _mcp_session, _mcp_tools
