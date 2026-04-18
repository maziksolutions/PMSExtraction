from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import verify_token
from app.models.user import User
from app.services.access_control import get_accessible_vessel_or_404
from app.services.token_store import is_token_revoked

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
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.EXPOSE_API_DOCS else None,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.EXPOSE_API_DOCS else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.EXPOSE_API_DOCS else None,
)

if settings.ENFORCE_TRUSTED_HOST_MIDDLEWARE:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.TRUSTED_HOSTS,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=settings.ALLOWED_ORIGINS_REGEX or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# ---------------------------------------------------------------------------
# In-process rate limiter (per client IP, resets each minute)
# For production, replace with a Redis-backed solution.
# ---------------------------------------------------------------------------

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_VESSEL_PATH_RE = re.compile(rf"^{re.escape(settings.API_V1_STR)}/vessels/([0-9a-fA-F-]+)(?:/|$)")


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def _extract_websocket_token(websocket: WebSocket) -> str | None:
    protocol_header = websocket.headers.get("sec-websocket-protocol", "")
    if protocol_header:
        parts = [part.strip() for part in protocol_header.split(",") if part.strip()]
        if len(parts) >= 2 and parts[0] == "access-token":
            return parts[1]
        if len(parts) == 1 and parts[0] != "access-token":
            return parts[0]

    token = websocket.query_params.get("token")
    return token or None


async def _load_vessel_scoped_user(request: Request) -> User | None:
    token = _extract_bearer_token(request)
    if not token:
        return None
    try:
        payload = verify_token(token)
    except Exception:
        return None
    if payload.get("token_type") != "access":
        return None
    if await is_token_revoked(payload):
        return None

    user_id = payload.get("user_id")
    if not user_id:
        return None
    try:
        user_uuid = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == user_uuid, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        return user


@app.middleware("http")
async def request_size_middleware(request: Request, call_next: Any) -> Response:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_REQUEST_SIZE_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request payload exceeds the allowed size limit."},
                )
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid Content-Length header."},
            )
    return await call_next(request)


@app.middleware("http")
async def vessel_access_middleware(request: Request, call_next: Any) -> Response:
    if request.method == "OPTIONS":
        return await call_next(request)

    match = _VESSEL_PATH_RE.match(request.url.path)
    if not match:
        return await call_next(request)

    try:
        vessel_id = uuid.UUID(match.group(1))
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid vessel identifier."},
        )

    user = await _load_vessel_scoped_user(request)
    if user is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Could not validate credentials"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with AsyncSessionLocal() as db:
        try:
            await get_accessible_vessel_or_404(
                vessel_id=vessel_id,
                current_user=user,
                db=db,
            )
        except Exception as exc:
            if hasattr(exc, "status_code") and hasattr(exc, "detail"):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                )
            raise

    return await call_next(request)


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
    print(
        f"[REDIS CONFIG] REDIS_URL={settings.redis_url_safe}",
        flush=True,
    )

# ---------------------------------------------------------------------------
# WebSocket endpoint (Sprint 8)
# ---------------------------------------------------------------------------

from app.websocket import manager  # noqa: E402


@app.websocket(f"{settings.API_V1_STR}/ws/{{vessel_id}}")
async def websocket_endpoint(websocket: WebSocket, vessel_id: str) -> None:
    """
    WebSocket endpoint for real-time presence and activity events.
    Clients connect with a bearer token passed in the Sec-WebSocket-Protocol
    header, with query-string token fallback retained only for compatibility.
    """
    user_id = "unknown"
    user_name = "Unknown"

    # Validate JWT token
    try:
        token = _extract_websocket_token(websocket)
        if not token:
            raise ValueError("Missing token")
        payload = verify_token(token)
        user_id = payload.get("user_id", "unknown")
        if payload.get("token_type") != "access":
            raise ValueError("Invalid token type")
        if await is_token_revoked(payload):
            raise ValueError("Revoked token")
        vessel_uuid = uuid.UUID(vessel_id)
        user_uuid = uuid.UUID(str(user_id))
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.id == user_uuid, User.is_deleted == False)
            )
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                raise ValueError("Inactive or missing user")
            user_name = user.full_name or user.email or "Unknown"
            await get_accessible_vessel_or_404(
                vessel_id=vessel_uuid,
                current_user=user,
                db=db,
            )
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
