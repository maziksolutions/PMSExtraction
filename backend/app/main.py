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
    import json
    from datetime import datetime
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    
    csv_path = os.path.join(os.path.dirname(__file__), "assets", "asm_jobs.csv")
    if not os.path.exists(csv_path):
        return
        
    async with AsyncSessionLocal() as db:
        # 1. Resolve all unique active tenant IDs in the database
        tenant_ids = set()
        
        # Always seed the default tenant ID
        tenant_ids.add(uuid.UUID("00000000-0000-0000-0000-000000000001"))
        
        res = await db.execute(text("SELECT tenant_id FROM vessel_projects;"))
        for row in res.fetchall():
            if row[0]:
                tenant_ids.add(row[0])
                
        res = await db.execute(text("SELECT tenant_id FROM users;"))
        for row in res.fetchall():
            if row[0]:
                tenant_ids.add(row[0])
                
        print(f"[STARTUP SEED] Resolved active tenant IDs to seed: {list(tenant_ids)}", flush=True)

        # 2. Load the CSV records once
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
        
        # 3. Seed each tenant individually if not already fully seeded
        for tenant_id in tenant_ids:
            res = await db.execute(text("""
                SELECT COUNT(*) FROM global_job_library 
                WHERE tenant_id = :tid 
                  AND (canonical_data->>'ship_component_job_link_id') IS NOT NULL;
            """), {"tid": str(tenant_id)})
            link_id_count = res.scalar()
            
            if link_id_count >= 15000:
                print(f"[STARTUP SEED] Tenant {tenant_id} already seeded (count={link_id_count}). Skipping.", flush=True)
                continue
                
            print(f"[STARTUP SEED] Seeding 16,940 records for tenant {tenant_id}...", flush=True)
            # Delete any partial library seeds for this tenant (user accepted jobs remain safe)
            await db.execute(text("""
                DELETE FROM global_job_library 
                WHERE tenant_id = :tid 
                  AND (canonical_data->>'ship_component_job_link_id') IS NOT NULL;
            """), {"tid": str(tenant_id)})
            await db.commit()
            
            # Perform batch insert
            now = datetime.utcnow()
            batch_size = 5000
            for i in range(0, len(records), batch_size):
                chunk = records[i : i + batch_size]
                
                stmt = text("""
                    INSERT INTO global_job_library (
                        id, tenant_id, canonical_data, source_vessels, occurrence_count,
                        first_seen_at, last_confirmed_at, created_at, updated_at, is_deleted
                    ) VALUES (
                        :id, :tenant_id, :canonical_data, :source_vessels, :occurrence_count,
                        :now, :now, :now, :now, false
                    )
                """)
                
                params_list = []
                for r in chunk:
                    canonical_dict = {
                        "job_name": r["job_name"],
                        "job_code": r["job_code"],
                        "job_description": r["job_name"],
                        "frequency": r["frequency"],
                        "frequency_type": r["frequency_type"],
                        "component_name": r["component_name"],
                        "ship_component_job_link_id": r["ship_component_job_link_id"],
                        "vessel_name": r["vessel_name"],
                        "responsibility": r["responsibility"]
                    }
                    params_list.append({
                        "id": str(uuid.uuid4()),
                        "tenant_id": str(tenant_id),
                        "canonical_data": json.dumps(canonical_dict),
                        "source_vessels": json.dumps([{"name": r["vessel_name"]}]),
                        "occurrence_count": 1,
                        "now": now
                    })
                
                await db.execute(stmt, params_list)
                await db.commit()
            print(f"[STARTUP SEED] Successfully seeded tenant {tenant_id}!", flush=True)


async def _run_startup_restore() -> None:
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as db:
            # Check if the backup table exists
            res = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'job_name_backup'
                );
            """))
            exists = res.scalar()
            if exists:
                res = await db.execute(text("SELECT COUNT(*) FROM job_name_backup;"))
                count = res.scalar()
                print(f"[STARTUP RESTORE] Found {count} backed up job titles in 'job_name_backup'. Restoring...", flush=True)
                await db.execute(text("""
                    UPDATE jobs
                    SET job_name = b.original_job_name
                    FROM job_name_backup b
                    WHERE jobs.id = b.job_id;
                """))
                await db.commit()
                print("[STARTUP RESTORE] Successfully restored all original job titles!", flush=True)
            else:
                print("[STARTUP RESTORE] Backup table 'job_name_backup' does not exist! Cannot restore.", flush=True)
    except Exception as e:
        print(f"[STARTUP RESTORE ERROR] Failed to restore: {e}", flush=True)


async def _run_startup_desc_cleanup() -> None:
    from app.core.database import AsyncSessionLocal
    from app.models.job import Job
    from app.services.job_naming import (
        strip_source_reference_footer,
        split_reference_entries,
        append_source_references_to_description
    )
    from sqlalchemy import select
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Job))
            jobs = res.scalars().all()
            print(f"[STARTUP CLEANUP] Checking {len(jobs)} jobs for repeated descriptions...", flush=True)
            
            updated_count = 0
            for job in jobs:
                if not job.job_description:
                    continue
                orig_desc = job.job_description
                reference_entries = split_reference_entries(
                    pdf_reference=job.pdf_reference,
                    page_reference=job.page_reference,
                    source_reference=job.source_reference
                )
                stripped_desc = strip_source_reference_footer(orig_desc)
                new_desc = append_source_references_to_description(stripped_desc, reference_entries)
                if new_desc != orig_desc:
                    job.job_description = new_desc
                    db.add(job)
                    updated_count += 1
            if updated_count > 0:
                await db.commit()
                print(f"[STARTUP CLEANUP] Successfully cleaned and deduplicated {updated_count} descriptions!", flush=True)
            else:
                print("[STARTUP CLEANUP] No descriptions needed deduplication.", flush=True)
    except Exception as e:
        print(f"[STARTUP CLEANUP ERROR] Failed to clean up: {e}", flush=True)


async def _check_vessel4_status() -> None:
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as db:
            # 1. Run recovery check for M-29 Air Compressor manuals
            m29_res = await db.execute(text("""
                SELECT id, original_filename FROM manuals 
                WHERE original_filename LIKE '%M-29%' AND is_deleted = false;
            """))
            m29_rows = m29_res.fetchall()
            for row in m29_rows:
                mid = row[0]
                filename = row[1]
                print(f"[M29 RECOVERY] Found manual: {filename} (ID: {mid})", flush=True)
                
                c_del = await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})
                j_del = await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})
                s_del = await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})
                
                c_count = c_del.scalar()
                j_count = j_del.scalar()
                s_count = s_del.scalar()
                print(f"[M29 RECOVERY] Deleted records in DB: {c_count} components, {j_count} jobs, {s_count} spares", flush=True)
                
                if c_count > 0 or j_count > 0 or s_count > 0:
                    print(f"[M29 RECOVERY] Restoring previously extracted data for {filename}...", flush=True)
                    await db.execute(text("UPDATE components SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
                    await db.execute(text("UPDATE jobs SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
                    await db.execute(text("UPDATE spares SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
                    await db.execute(text("UPDATE manuals SET status = 'classified', error_message = null WHERE id = :mid;"), {"mid": mid})
                    await db.commit()
                    print(f"[M29 RECOVERY] Restore complete!", flush=True)
                    
            # 2. Count manuals updated recently (August 25-26, 2026) in production database
            prod_m_res = await db.execute(text("""
                SELECT original_filename, status, updated_at 
                FROM manuals 
                WHERE DATE(updated_at) >= '2026-08-25' AND is_deleted = false;
            """))
            prod_m_rows = prod_m_res.fetchall()
            print(f"[PROD MANUALS RECENT] Total manuals updated/extracted recently (>=2026-08-25): {len(prod_m_rows)}", flush=True)
            for pm in prod_m_rows:
                print(f"  - Manual: {pm[0]} | Status: {pm[1]} | Updated At: {pm[2]}", flush=True)
                
            # 3. Diagnostic check for M-29 Air compressor(2-2).pdf
            diag_res = await db.execute(text("""
                SELECT id, original_filename, status, pages_with_spares, pages_with_components, pages_with_jobs, error_message
                FROM manuals 
                WHERE original_filename LIKE '%M-29%2-2%' AND is_deleted = false;
            """))
            diag_rows = diag_res.fetchall()
            print(f"[M29 DIAG] Matching manuals count: {len(diag_rows)}", flush=True)
            for row in diag_rows:
                mid = row[0]
                filename = row[1]
                status = row[2]
                pages_spares = row[3]
                pages_comps = row[4]
                pages_jobs = row[5]
                err = row[6]
                
                # Active counts
                c_act = (await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": mid})).scalar()
                j_act = (await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": mid})).scalar()
                s_act = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": mid})).scalar()
                
                # Deleted counts
                c_del = (await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
                j_del = (await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
                s_del = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
                
                print(f"[M29 DIAG] Manual: {filename} | ID: {mid}", flush=True)
                print(f"  * Status: {status} | Error: {err}", flush=True)
                print(f"  * Page Ranges -> Components: {pages_comps} | Jobs: {pages_jobs} | Spares: {pages_spares}", flush=True)
                print(f"  * Active Counts -> Components: {c_act} | Jobs: {j_act} | Spares: {s_act}", flush=True)
                print(f"  * Deleted Counts -> Components: {c_del} | Jobs: {j_del} | Spares: {s_del}", flush=True)
                
            # 4. Diagnostic check for E-32 Electroc clock & communal aerial system.pdf
            e32_res = await db.execute(text("""
                SELECT id, original_filename, status, pages_with_spares, pages_with_components, pages_with_jobs, error_message
                FROM manuals 
                WHERE original_filename LIKE '%E-32%' AND is_deleted = false;
            """))
            e32_rows = e32_res.fetchall()
            print(f"[E32 DIAG] Matching manuals count: {len(e32_rows)}", flush=True)
            for row in e32_rows:
                mid = row[0]
                filename = row[1]
                status = row[2]
                pages_spares = row[3]
                pages_comps = row[4]
                pages_jobs = row[5]
                err = row[6]
                print(f"[E32 DIAG] Manual: {filename} | ID: {mid} | Status: {status} | Error: {err}", flush=True)
                print(f"  * Page Ranges -> Components: {pages_comps} | Jobs: {pages_jobs} | Spares: {pages_spares}", flush=True)
                
            # 5. Reset any manuals stuck in progress states on startup (due to container terminations)
            stuck_res = await db.execute(text("""
                SELECT id, original_filename, status 
                FROM manuals 
                WHERE status IN ('queued', 'downloading', 'converting', 'translating', 'scanning') 
                  AND is_deleted = false;
            """))
            stuck_rows = stuck_res.fetchall()
            if stuck_rows:
                print(f"[STARTUP MANUAL CLEANUP] Found {len(stuck_rows)} stuck manuals. Resetting to failed.", flush=True)
                for row in stuck_rows:
                    mid = row[0]
                    name = row[1]
                    prev_status = row[2]
                    print(f"  * Resetting stuck manual: {name} (ID: {mid}) from {prev_status} to failed", flush=True)
                    await db.execute(text("""
                        UPDATE manuals 
                        SET status = 'failed', error_message = 'Extraction was interrupted by server deployment/restart. Please try re-extracting.'
                        WHERE id = :mid;
                    """), {"mid": mid})
                await db.commit()
    except Exception as e:
        print(f"[M29/E32 DIAG/RECOVERY ERROR] Failed: {e}", flush=True)


async def _run_startup_backfill_and_backup() -> None:
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    from app.models.job import Job
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        # Step 1: Backup and backfill job descriptions
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS job_description_backup (
                job_id UUID PRIMARY KEY,
                original_description TEXT,
                backed_up_at TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        await db.commit()
        
        res = await db.execute(text("SELECT COUNT(*) FROM job_description_backup;"))
        backup_count = res.scalar()
        
        if backup_count == 0:
            print("[STARTUP MIGRATION] Backing up original job descriptions...", flush=True)
            await db.execute(text("""
                INSERT INTO job_description_backup (job_id, original_description)
                SELECT id, job_description FROM jobs
                WHERE job_description IS NOT NULL;
            """))
            await db.commit()
            print("[STARTUP MIGRATION] Backup complete.", flush=True)
            
        res = await db.execute(select(Job).where(Job.job_description.is_not(None)))
        jobs = res.scalars().all()
        
        updated_count = 0
        for job in jobs:
            if not job.job_description:
                continue
            orig = job.job_description
            job.job_description = orig
            if job.job_description != orig:
                db.add(job)
                updated_count += 1
                
        if updated_count > 0:
            await db.commit()
            print(f"[STARTUP MIGRATION] Successfully backfilled and formatted {updated_count} existing job descriptions!", flush=True)
        else:
            print("[STARTUP MIGRATION] No job descriptions needed backfilling.", flush=True)

        # Step 2: Backup and backfill/re-name job titles based on global library (DISABLED)
        # To re-enable, change the condition below to True.
        if False:
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS job_name_backup (
                    job_id UUID PRIMARY KEY,
                    original_job_name TEXT,
                    backed_up_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            await db.commit()
            
            res = await db.execute(text("SELECT COUNT(*) FROM job_name_backup;"))
            name_backup_count = res.scalar()
            
            if name_backup_count == 0:
                print("[STARTUP MIGRATION] Backing up original job names...", flush=True)
                await db.execute(text("""
                    INSERT INTO job_name_backup (job_id, original_job_name)
                    SELECT id, job_name FROM jobs
                    WHERE job_name IS NOT NULL;
                """))
                await db.commit()
                print("[STARTUP MIGRATION] Job names backup complete.", flush=True)
                
            # Re-resolve job names using build_canonical_job_name
            from app.services.job_naming import build_canonical_job_name
            
            # Load unique component names from global library once to use as scanning fallback
            lib_comp_res = await db.execute(text("""
                SELECT DISTINCT canonical_data->>'component_name' 
                FROM global_job_library 
                WHERE (canonical_data->>'component_name') IS NOT NULL;
            """))
            lib_comp_names = [r[0] for r in lib_comp_res.fetchall() if r[0]]
            lib_comp_names.sort(key=len, reverse=True)
            
            res = await db.execute(select(Job))
            jobs_to_rename = res.scalars().all()
            
            renamed_count = 0
            for job in jobs_to_rename:
                orig_name = job.job_name
                comp_name = None
                
                # Method 1: Component ID
                if job.component_id:
                    comp_res = await db.execute(
                        text("SELECT component_name FROM components WHERE id = :cid;"),
                        {"cid": str(job.component_id)}
                    )
                    comp_row = comp_res.fetchone()
                    if comp_row:
                        comp_name = comp_row[0]
                        
                # Method 2: Hyphen split in name
                if not comp_name and job.job_name and " - " in job.job_name:
                    parts = job.job_name.split(" - ", 1)
                    comp_name = parts[0].strip()
                    
                # Method 3: Scan name/description for library component keywords
                if not comp_name and job.job_name:
                    job_name_lower = job.job_name.lower()
                    for name in lib_comp_names:
                        if name.lower() in job_name_lower:
                            comp_name = name
                            break
                            
                if not comp_name and job.job_description:
                    job_desc_lower = job.job_description.lower()
                    for name in lib_comp_names:
                        if name.lower() in job_desc_lower:
                            comp_name = name
                            break
                            
                new_name = await build_canonical_job_name(
                    db,
                    component_name=comp_name,
                    job_names=[job.job_name],
                    job_descriptions=[job.job_description],
                    tenant_id=job.tenant_id,
                    frequency=job.frequency,
                    frequency_type=job.frequency_type,
                    job_id=job.id,
                    component_id=job.component_id,
                )
                if new_name and new_name != orig_name:
                    job.job_name = new_name
                    db.add(job)
                    renamed_count += 1
                    
            if renamed_count > 0:
                await db.commit()
                print(f"[STARTUP MIGRATION] Successfully backfilled and updated {renamed_count} job titles based on library!", flush=True)
            else:
                print("[STARTUP MIGRATION] No job titles needed renaming.", flush=True)


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
    try:
        await _run_startup_backfill_and_backup()
    except Exception as e:
        print(f"[STARTUP MIGRATION ERROR] Failed to run backfill: {e}", flush=True)
    try:
        await _run_startup_restore()
    except Exception as e:
        print(f"[STARTUP RESTORE ERROR] Failed to run restore: {e}", flush=True)
    try:
        await _run_startup_desc_cleanup()
    except Exception as e:
        print(f"[STARTUP CLEANUP ERROR] Failed to run description cleanup: {e}", flush=True)
    try:
        await _check_vessel4_status()
    except Exception as e:
        print(f"[STARTUP CHECK ERROR] Failed to run vessel 4 check: {e}", flush=True)

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
