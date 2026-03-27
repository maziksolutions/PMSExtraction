from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Fields to redact from request/response bodies
REDACTED_FIELDS = {
    "password",
    "hashed_password",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "authorization",
    "client_secret",
}

STATE_CHANGING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _redact(data: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive fields from a dict."""
    if depth > 5:
        return data
    if isinstance(data, dict):
        return {
            k: "[REDACTED]" if k.lower() in REDACTED_FIELDS else _redact(v, depth + 1)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_redact(item, depth + 1) for item in data[:10]]  # cap lists at 10
    return data


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Logs state-changing HTTP requests (POST/PATCH/PUT/DELETE) to the
    audit_logs table for compliance and forensics.

    Does NOT log GET/HEAD/OPTIONS requests to avoid excessive noise.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in STATE_CHANGING_METHODS:
            return await call_next(request)

        start_time = time.perf_counter()

        # Attempt to capture request body (small bodies only)
        request_summary: Optional[dict] = None
        try:
            body_bytes = await request.body()
            if body_bytes and len(body_bytes) < 4096:
                try:
                    parsed = json.loads(body_bytes)
                    request_summary = _redact(parsed)
                except Exception:
                    request_summary = {"_raw": body_bytes.decode("utf-8", errors="replace")[:200]}
        except Exception:
            pass

        response = await call_next(request)

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Extract user_id from auth token if present
        user_id: Optional[str] = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from app.core.security import verify_token

                payload = verify_token(auth_header[7:])
                user_id = payload.get("user_id")
            except Exception:
                pass

        # Write to DB asynchronously (fire and forget)
        try:
            await _write_audit_log(
                user_id=user_id,
                ip_address=request.client.host if request.client else "unknown",
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_summary=request_summary,
            )
        except Exception as exc:
            logger.debug("Audit log write failed: %s", exc)

        return response


async def _write_audit_log(
    user_id: Optional[str],
    ip_address: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    request_summary: Optional[dict],
) -> None:
    """Write an audit log entry to the database."""
    try:
        from app.core.config import settings
        from app.core.database import AsyncSessionLocal
        from app.models.audit import AuditLog

        default_tenant = uuid.UUID(settings.DEFAULT_TENANT_ID)

        async with AsyncSessionLocal() as db:
            log = AuditLog(
                tenant_id=default_tenant,
                user_id=uuid.UUID(user_id) if user_id else None,
                ip_address=ip_address,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_summary=request_summary,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        logger.debug("DB audit log write error: %s", exc)
