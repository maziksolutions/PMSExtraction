from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

try:
    from app.api.v1.router import api_router
except Exception as exc:
    import traceback

    print(f"[STARTUP ERROR] Failed to import API router: {exc}", flush=True)
    traceback.print_exc()
    raise

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Maritime PMS Data Extraction & Setup Tool API.\n\n"
        "Provides authentication, vessel project management, user administration, "
        "and document extraction endpoints for the Union Maritime platform."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

CORS_ALLOW_ORIGINS = set(settings.ALLOWED_ORIGINS)


class CORSHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")
        if request.method == "OPTIONS":
            response = Response(status_code=200)
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,PATCH,OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Max-Age"] = "600"
            return response
        response = await call_next(request)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response


app.add_middleware(CORSHandlerMiddleware)

# ---------------------------------------------------------------------------
# In-process rate limiter (per client IP, resets each minute)
# For production, replace with a Redis-backed solution.
# ---------------------------------------------------------------------------

_rate_limit_store: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - 60.0

    # Remove timestamps outside the current 60-second window
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if ts > window_start
    ]

    if len(_rate_limit_store[client_ip]) >= settings.RATE_LIMIT_PER_MINUTE:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Try again in a minute."},
        )

    _rate_limit_store[client_ip].append(now)
    return await call_next(request)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(api_router, prefix=settings.API_V1_STR)

# Log which AI keys are configured at startup
import logging as _logging
_startup_log = _logging.getLogger("app.startup")

@app.on_event("startup")
async def _log_ai_config() -> None:
    print(
        f"[AI CONFIG] OPENAI_API_KEY={'SET' if settings.OPENAI_API_KEY else 'NOT SET'} | "
        f"GROQ_API_KEY={'SET' if settings.GROQ_API_KEY else 'NOT SET'} | "
        f"GEMINI_API_KEY={'SET' if settings.GEMINI_API_KEY else 'NOT SET'} | "
        f"ANTHROPIC_API_KEY={'SET' if settings.ANTHROPIC_API_KEY else 'NOT SET'}",
        flush=True,
    )

# ---------------------------------------------------------------------------
# WebSocket endpoint (Sprint 8)
# ---------------------------------------------------------------------------

from app.websocket import manager  # noqa: E402


@app.websocket(f"{settings.API_V1_STR}/ws/{{vessel_id}}")
async def websocket_endpoint(websocket: WebSocket, vessel_id: str, token: str = "") -> None:
    """
    WebSocket endpoint for real-time presence and activity events.
    Clients connect with: ws://<host>/api/v1/ws/<vessel_id>?token=<jwt>
    """
    user_id = "unknown"
    user_name = "Unknown"

    # Validate JWT token
    try:
        from app.core.security import verify_token

        payload = verify_token(token)
        user_id = payload.get("user_id", "unknown")
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, vessel_id, user_id, {"user_id": user_id, "user_name": user_name})

    try:
        while True:
            data = await websocket.receive_text()
            # Handle heartbeat / client messages
            import json
            try:
                msg = json.loads(data)
                if msg.get("type") == "heartbeat":
                    await manager.send_personal(websocket, {"type": "heartbeat_ack"})
            except Exception:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(vessel_id, user_id)


# ---------------------------------------------------------------------------
# Security headers middleware (Sprint 12)
# ---------------------------------------------------------------------------

from app.middleware.security import SecurityHeadersMiddleware  # noqa: E402
from app.middleware.audit import AuditLogMiddleware  # noqa: E402

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuditLogMiddleware)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get(
    "/health/live",
    tags=["Health"],
    summary="Liveness health check endpoint",
    response_description="Basic service liveness status",
    response_class=Response,
)
async def health_live() -> Response:
    """
    Lightweight liveness probe for container platforms.
    This endpoint intentionally avoids DB/Redis/blob checks so startup and
    rolling deploys are not blocked by cold dependencies.
    """
    import json

    data = {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }
    return Response(content=json.dumps(data), media_type="application/json", status_code=200)


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check endpoint",
    response_description="Service health status",
    response_class=Response,
)
async def health_check() -> Response:
    """
    Returns a simple JSON payload confirming the service is running.
    Suitable for container health checks and load balancer probes.
    Uses deep health check when available.
    """
    import json

    try:
        from app.core.health import deep_health_check

        data = await deep_health_check()
    except Exception:
        data = {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
        }
    return Response(content=json.dumps(data), media_type="application/json", status_code=200)
