from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
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
    openapi_version="3.0.3",
    description=(
        "Maritime PMS Data Extraction & Setup Tool API.\n\n"
        "Provides authentication, vessel project management, user administration, "
        "and document extraction endpoints for the Union Maritime platform."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.EXPOSE_API_DOCS else None,
    docs_url=None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.EXPOSE_API_DOCS else None,
    servers=[{"url": "http://localhost:8000", "description": "Local development"}],
)
app.openapi_version = "3.0.3"

if settings.EXPOSE_API_DOCS:
    swagger_js_url = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"
    swagger_css_url = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css"

    try:
        from swagger_ui_bundle import swagger_ui_3_path

        app.mount(
            "/static/swagger-ui",
            StaticFiles(directory=swagger_ui_3_path),
            name="swagger-ui",
        )
        swagger_js_url = "/static/swagger-ui/swagger-ui-bundle.js"
        swagger_css_url = "/static/swagger-ui/swagger-ui.css"
    except Exception as exc:
        print(
            f"[DOCS WARNING] Local Swagger UI assets unavailable, falling back to CDN: {exc}",
            flush=True,
        )

    @app.get(f"{settings.API_V1_STR}/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        return get_swagger_ui_html(
            openapi_url=f"{settings.API_V1_STR}/openapi.json",
            title=f"{settings.PROJECT_NAME} - Swagger UI",
            swagger_js_url=swagger_js_url,
            swagger_css_url=swagger_css_url,
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

async def _seed_job_title_library_if_empty() -> None:
    import os
    import csv
    import uuid
    from datetime import datetime
    from app.core.database import AsyncSessionLocal
    from app.models.job_title_library import JobTitleLibrary
    from sqlalchemy import select, func
    
    csv_path = os.path.join(os.path.dirname(__file__), "assets", "asm_jobs.csv")
    if not os.path.exists(csv_path):
        return
        
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(func.count(JobTitleLibrary.id)))
        count = res.scalar()
        if count > 0:
            return
            
        print("[STARTUP SEED] job_title_library is empty. Seeding from asm_jobs.csv...", flush=True)
        from sqlalchemy import text
        res = await db.execute(text("SELECT tenant_id FROM vessel_projects LIMIT 1;"))
        row = res.fetchone()
        if not row:
            res = await db.execute(text("SELECT tenant_id FROM users LIMIT 1;"))
            row = res.fetchone()
        tenant_id = row[0] if row else uuid.UUID("00000000-0000-0000-0000-000000000001")
        
        records = []
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if not row or len(row) < 11:
                    continue
                if not row[0] or not row[0].strip().isdigit():
                    continue
                
                link_id = int(row[0].strip())
                vessel = row[1].strip() if row[1] else ""
                comp_name = row[2].strip() if row[2] else ""
                comp_code = row[3].strip() if row[3] else ""
                job_code = row[4].strip() if row[4] else ""
                job_name = row[5].strip() if row[5] else ""
                freq_type = row[6].strip() if row[6] else None
                
                freq_val = row[7].strip() if row[7] else ""
                freq = int(freq_val) if freq_val.isdigit() else None
                
                alt_freq_type = row[8].strip() if row[8] else None
                
                alt_freq_val = row[9].strip() if row[9] else ""
                alt_freq = int(alt_freq_val) if alt_freq_val.isdigit() else None
                
                resp = row[10].strip() if row[10] else None
                
                records.append({
                    "ship_component_job_link_id": link_id,
                    "vessel_name": vessel,
                    "component_name": comp_name,
                    "component_code": comp_code,
                    "job_code": job_code,
                    "job_name": job_name,
                    "frequency_type": freq_type,
                    "frequency": freq,
                    "alternate_frequency_type": alt_freq_type,
                    "alternate_frequency": alt_freq,
                    "responsibility": resp
                })
        
        batch_size = 10000
        now = datetime.utcnow()
        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            db_entries = []
            for r in chunk:
                db_entries.append(
                    JobTitleLibrary(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        created_at=now,
                        updated_at=now,
                        is_deleted=False,
                        ship_component_job_link_id=r["ship_component_job_link_id"],
                        vessel_name=r["vessel_name"],
                        component_name=r["component_name"],
                        component_code=r["component_code"],
                        job_code=r["job_code"],
                        job_name=r["job_name"],
                        frequency_type=r["frequency_type"],
                        frequency=r["frequency"],
                        alternate_frequency_type=r["alternate_frequency_type"],
                        alternate_frequency=r["alternate_frequency"],
                        responsibility=r["responsibility"]
                    )
                )
            db.add_all(db_entries)
            await db.commit()
            
        print(f"[STARTUP SEED] Successfully seeded {len(records)} records into job_title_library!", flush=True)


@app.on_event("startup")
async def _log_ai_config() -> None:
    print(
        f"[AI CONFIG] ANTHROPIC_API_KEY={'SET' if settings.ANTHROPIC_API_KEY else 'NOT SET'} | "
        f"OPENAI_API_KEY={'SET' if settings.OPENAI_API_KEY else 'NOT SET'} | "
        f"GEMINI_API_KEY={'SET' if settings.GEMINI_API_KEY else 'NOT SET'}",
        flush=True,
    )
    print(
        f"[REDIS CONFIG] REDIS_URL={settings.redis_url_safe}",
        flush=True,
    )
    try:
        await _seed_job_title_library_if_empty()
    except Exception as e:
        print(f"[STARTUP SEED ERROR] Failed to seed job title library: {e}", flush=True)

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
