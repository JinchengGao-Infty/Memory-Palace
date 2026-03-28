"""
Memory Palace MCP server — Streamable HTTP transport.

Replaces run_sse.py. Manually builds a Starlette app with FastMCP's
StreamableHTTP handler instead of the custom SSE transport (680 → ~80 lines).

Key design: lifespan is at the Starlette app level (runs once), NOT at the
MCP session level (mcp.settings.lifespan runs per-session — wrong for DB init/shutdown).
"""

import hmac
import os
import sys
import traceback
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mcp_server import mcp, drain_pending_flush_summaries
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from db import close_sqlite_client
from runtime_state import runtime_state
from runtime_bootstrap import initialize_backend_runtime

_MCP_API_KEY_ENV = "MCP_API_KEY"
_PUBLIC_PATHS = {"/health", "/health/"}


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    return os.getenv(_MCP_API_KEY_ENV, "").strip()


def _wrap_auth(app: ASGIApp) -> ASGIApp:
    """API key auth via X-MCP-API-Key header or Bearer token."""

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _PUBLIC_PATHS:
            await app(scope, receive, send)
            return

        configured_key = _get_api_key()
        if not configured_key:
            # No key configured → allow all (dev mode)
            await app(scope, receive, send)
            return

        request = Request(scope, receive)
        provided = request.headers.get("x-mcp-api-key", "")
        if not provided:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()

        if not provided or not hmac.compare_digest(provided, configured_key):
            response = JSONResponse(
                {"error": "auth_failed", "reason": "invalid_or_missing_api_key"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        try:
            await app(scope, receive, send)
        except Exception:
            traceback.print_exc()

    return middleware


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

async def _health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "memory-palace-mcp"})


# ---------------------------------------------------------------------------
# Build Starlette app with proper app-level lifespan
# ---------------------------------------------------------------------------

# Create session manager (must exist before building routes)
_session_manager = StreamableHTTPSessionManager(
    app=mcp._mcp_server,
    json_response=mcp.settings.json_response,
    stateless=mcp.settings.stateless_http,
    security_settings=mcp.settings.transport_security,
)


@asynccontextmanager
async def _lifespan(_app):
    """App-level lifespan: runs once on startup/shutdown (NOT per-session)."""
    await initialize_backend_runtime()
    async with _session_manager.run():
        yield
    try:
        await drain_pending_flush_summaries(reason="runtime.shutdown")
    finally:
        await runtime_state.shutdown()
        await close_sqlite_client()


_starlette_app = Starlette(
    debug=mcp.settings.debug,
    routes=[
        Route("/health", endpoint=_health, methods=["GET"]),
        *mcp._custom_starlette_routes,
    ],
    lifespan=_lifespan,
)


def _inject_mcp_route(app: ASGIApp) -> ASGIApp:
    """Route /mcp to session manager, everything else to Starlette."""

    async def dispatcher(scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("path", "") in ("/mcp", "/mcp/"):
            await _session_manager.handle_request(scope, receive, send)
        else:
            await app(scope, receive, send)

    return dispatcher

app = _wrap_auth(_inject_mcp_route(_starlette_app))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("PORT", "8765"))
    print(f"Memory Palace MCP (Streamable HTTP) on http://{host}:{port}/mcp")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
