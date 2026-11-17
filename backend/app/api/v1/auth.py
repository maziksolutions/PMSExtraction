from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.token_store import is_token_revoked, revoke_token_payload

router = APIRouter()

@router.get("/debug-test-render/{manual_id}", tags=["Debug"])
async def debug_test_render(manual_id: str, page: int = 105, return_image: bool = False, db: AsyncSession = Depends(get_db)):
    from app.services.blob_storage import BlobStorageService
    from sqlalchemy import text
    import traceback
    try:
        res = await db.execute(text("SELECT id, original_filename, blob_storage_key FROM manuals WHERE id = :mid"), {"mid": manual_id})
        m = res.fetchone()
        if not m:
            return {"error": "manual not found"}
        blob_key = m[2]
        blob_svc = BlobStorageService()
        pdf_bytes = await blob_svc.download_bytes(blob_key)
        
        err = None
        img_len = None
        t = ""
        page_count = 0
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc)
            p = doc[page - 1]
            t = p.get_text() or ""
            pix = p.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_len = len(img_bytes)
            doc.close()
        except Exception as e:
            err = traceback.format_exc()
        
        if return_image and img_bytes:
            return Response(content=img_bytes, media_type="image/png")

        return {
            "pdf_len": len(pdf_bytes),
            "page_count": page_count,
            "text_len": len(t),
            "text_sample": t[:300],
            "img_len": img_len,
            "render_err": err,
            "anthropic_key_set": bool(settings.ANTHROPIC_API_KEY),
            "claude_model": getattr(settings, "CLAUDE_MODEL_ID", None),
            "openai_key_set": bool(settings.OPENAI_API_KEY),
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

optional_bearer = HTTPBearer(auto_error=False)


@router.get("/debug-restore-m29", tags=["Debug"])
async def debug_restore_m29(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    try:
        res = await db.execute(text("""
            SELECT id, original_filename, status, error_message, updated_at 
            FROM manuals 
            WHERE original_filename LIKE '%M-29%' AND is_deleted = false;
        """))
        rows = res.fetchall()
        results = []
        for row in rows:
            mid = row[0]
            filename = row[1]
            status = row[2]
            err = row[3]
            updated = row[4]
            
            c_act = (await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": mid})).scalar()
            j_act = (await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": mid})).scalar()
            s_act = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": mid})).scalar()
            
            c_del = (await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            j_del = (await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            s_del = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            
            results.append({
                "manual_id": str(mid),
                "filename": filename,
                "status": status,
                "error": err,
                "updated_at": updated.isoformat() if updated else None,
                "active_counts": {
                    "components": c_act,
                    "jobs": j_act,
                    "spares": s_act
                },
                "deleted_counts": {
                    "components": c_del,
                    "jobs": j_del,
                    "spares": s_del
                }
            })
        return {"status": "success", "m29_diagnostics": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/debug-check-p42", summary="Temporary diagnostics for P-42 manual failure")
async def debug_check_p42(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    try:
        res = await db.execute(text("""
            SELECT id, original_filename, status, error_message, is_deleted, created_at, updated_at, vessel_id 
            FROM manuals 
            WHERE original_filename ILIKE '%P-42%' 
               OR original_filename ILIKE '%P42%' 
               OR original_filename ILIKE '%VALVE%' 
               OR original_filename ILIKE '%REMOTE%' 
               OR original_filename ILIKE '%CONTROL%';
        """))
        rows = res.fetchall()
        results = []
        for row in rows:
            results.append({
                "id": str(row[0]),
                "filename": row[1],
                "status": row[2],
                "error": row[3],
                "is_deleted": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None,
                "vessel_id": str(row[7])
            })
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/debug-extraction-status", tags=["Debug"], summary="Diagnostic endpoint to check live extraction status and stuck manuals")
async def debug_extraction_status(
    vessel_id: str | None = None,
    action: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.extractor import get_extraction_state, set_extraction_state, _active_extraction_tasks, _extraction_paused_flags
    from sqlalchemy import text
    try:
        candidates = ["607e4783-4f0f-433e-a010-609bd93250cd", "4acf710a-2816-445c-8bb3-72e8373600d1"]
        if vessel_id and vessel_id not in candidates:
            candidates.insert(0, vessel_id)
        elif vessel_id:
            candidates.remove(vessel_id)
            candidates.insert(0, vessel_id)

        vessels_data = {}
        for vid in candidates:
            st = get_extraction_state(vid)
            if action == "reset_completed":
                set_extraction_state(vid, status="completed")
                st = get_extraction_state(vid)
            elif action == "reset_idle":
                set_extraction_state(vid, status="idle")
                st = get_extraction_state(vid)

            res = await db.execute(text("""
                SELECT id, original_filename, status, error_message, updated_at, pages_with_spares,
                       (SELECT COUNT(*) FROM spares s WHERE s.source_manual_id = manuals.id AND s.is_deleted = false) as spares_count
                FROM manuals
                WHERE vessel_id = :vid AND is_deleted = false
                ORDER BY updated_at DESC
                LIMIT 45;
            """), {"vid": vid})
            rows = res.fetchall()
            manuals_list = []
            for r in rows:
                manuals_list.append({
                    "id": str(r[0]),
                    "filename": r[1],
                    "status": r[2],
                    "error": r[3],
                    "updated_at": r[4].isoformat() if r[4] else None,
                    "pages_with_spares": r[5],
                    "spares_count": r[6],
                })

            vessels_data[vid] = {
                "extraction_state": st,
                "has_async_task": vid in _active_extraction_tasks,
                "is_paused": _extraction_paused_flags.get(vid, False),
                "recent_manuals": manuals_list,
            }

        return {"status": "success", "vessels": vessels_data}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}






@router.get("/debug-manuals", tags=["Debug"], summary="Query manuals without auth")
async def debug_manuals(
    query: str = "",
    vessel_id: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        sql = """
            SELECT m.id, m.vessel_id, m.original_filename, m.blob_storage_key, m.status, 
                   m.pages_with_spares, m.pages_with_spares_physical, m.pages_with_components,
                   m.pages_with_jobs, m.category,
                   (SELECT COUNT(*) FROM spares s WHERE s.source_manual_id = m.id AND s.is_deleted = false) as spares_count,
                   (SELECT COUNT(*) FROM components c WHERE c.source_manual_id = m.id AND c.is_deleted = false) as components_count
            FROM manuals m
            WHERE m.is_deleted = false
        """
        params = {}
        if query:
            sql += " AND m.original_filename ILIKE :q"
            params["q"] = f"%{query}%"
        if vessel_id:
            sql += " AND m.vessel_id = :vid"
            params["vid"] = vessel_id
        sql += " ORDER BY m.created_at DESC LIMIT :lim"
        params["lim"] = limit

        res = await db.execute(text(sql), params)
        rows = res.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": str(r[0]),
                "vessel_id": str(r[1]),
                "original_filename": r[2],
                "blob_storage_key": r[3],
                "status": r[4],
                "pages_with_spares": r[5],
                "pages_with_spares_physical": r[6],
                "pages_with_components": r[7],
                "pages_with_jobs": r[8],
                "category": r[9],
                "spares_count": r[10],
                "components_count": r[11],
            })
        return {"status": "success", "count": len(results), "manuals": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/debug-components", tags=["Debug"], summary="Query components without auth")
async def debug_components(
    manual_id: str | None = None,
    vessel_id: str | None = None,
    query: str = "",
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        sql = """
            SELECT id, vessel_id, source_manual_id, component_name, maker, model, page_reference, pdf_reference
            FROM components
            WHERE is_deleted = false
        """
        params = {}
        if manual_id:
            sql += " AND source_manual_id = :mid"
            params["mid"] = manual_id
        if vessel_id:
            sql += " AND vessel_id = :vid"
            params["vid"] = vessel_id
        if query:
            sql += " AND (component_name ILIKE :q OR maker ILIKE :q OR model ILIKE :q)"
            params["q"] = f"%{query}%"
        sql += " LIMIT :lim"
        params["lim"] = limit

        res = await db.execute(text(sql), params)
        rows = res.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": str(r[0]),
                "vessel_id": str(r[1]),
                "source_manual_id": str(r[2]) if r[2] else None,
                "component_name": r[3],
                "maker": r[4],
                "model": r[5],
                "page_reference": r[6],
                "pdf_reference": r[7],
            })
        return {"status": "success", "count": len(results), "components": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/debug-jobs", tags=["Debug"], summary="Query jobs without auth")
async def debug_jobs(
    manual_id: str | None = None,
    vessel_id: str | None = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        sql = """
            SELECT id, vessel_id, source_manual_id, job_name, page_reference, frequency, frequency_type,
                   created_at, updated_at, job_description
            FROM jobs
            WHERE is_deleted = false
        """
        params = {"lim": limit}
        if manual_id:
            sql += " AND source_manual_id = :mid"
            params["mid"] = manual_id
        if vessel_id:
            sql += " AND vessel_id = :vid"
            params["vid"] = vessel_id
        sql += " ORDER BY page_reference ASC, id ASC LIMIT :lim"
        res = await db.execute(text(sql), params)
        rows = res.fetchall()
        results = [
            {
                "id": str(r[0]),
                "vessel_id": str(r[1]),
                "source_manual_id": str(r[2]),
                "job_name": r[3],
                "page_reference": r[4],
                "frequency": r[5],
                "frequency_type": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
                "updated_at": r[8].isoformat() if r[8] else None,
                "job_description": r[9],
            }
            for r in rows
        ]
        return {"status": "success", "count": len(results), "jobs": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/debug-manual-audit/{manual_id}", tags=["Debug"], summary="Audit history and runs for manual")
async def debug_manual_audit(manual_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    import uuid
    try:
        mid = uuid.UUID(manual_id)
        m_row = (await db.execute(text("""
            SELECT id, original_filename, status, pages_with_components, pages_with_jobs, pages_with_spares,
                   pages_with_components_physical, pages_with_jobs_physical, pages_with_spares_physical,
                   created_at, updated_at
            FROM manuals WHERE id = :mid
        """), {"mid": mid})).fetchone()
        
        hist_rows = (await db.execute(text("""
            SELECT id, changed_by_name, change_source, pages_with_components, pages_with_jobs, pages_with_spares,
                   previous_pages_with_components, previous_pages_with_jobs, previous_pages_with_spares, created_at
            FROM manual_page_ref_history WHERE manual_id = :mid ORDER BY created_at ASC
        """), {"mid": mid})).fetchall()
        
        runs_row = (await db.execute(text("""
            SELECT run_count, last_run_at FROM manual_extraction_runs WHERE manual_id = :mid
        """), {"mid": mid})).fetchone()
        
        pages_rows = (await db.execute(text("""
            SELECT page_number, run_count, last_extracted_at FROM manual_page_extractions WHERE manual_id = :mid ORDER BY page_number ASC
        """), {"mid": mid})).fetchall()

        jobs_rows = (await db.execute(text("""
            SELECT id, job_name, page_reference, frequency, frequency_type, created_at, updated_at, job_description
            FROM jobs WHERE source_manual_id = :mid AND is_deleted = false ORDER BY page_reference ASC, created_at ASC
        """), {"mid": mid})).fetchall()

        return {
            "status": "success",
            "manual": {
                "id": str(m_row[0]),
                "original_filename": m_row[1],
                "status": m_row[2],
                "pages_with_components": m_row[3],
                "pages_with_jobs": m_row[4],
                "pages_with_spares": m_row[5],
                "pages_with_components_physical": m_row[6],
                "pages_with_jobs_physical": m_row[7],
                "pages_with_spares_physical": m_row[8],
                "created_at": m_row[9].isoformat() if m_row[9] else None,
                "updated_at": m_row[10].isoformat() if m_row[10] else None,
            } if m_row else None,
            "extraction_runs": {
                "run_count": runs_row[0],
                "last_run_at": runs_row[1].isoformat() if runs_row[1] else None,
            } if runs_row else None,
            "page_extractions": [
                {"page": r[0], "run_count": r[1], "last_extracted_at": r[2].isoformat() if r[2] else None}
                for r in pages_rows
            ],
            "history": [
                {
                    "id": str(r[0]),
                    "changed_by": r[1],
                    "source": r[2],
                    "pages_with_components": r[3],
                    "pages_with_jobs": r[4],
                    "pages_with_spares": r[5],
                    "previous_pages_with_components": r[6],
                    "previous_pages_with_jobs": r[7],
                    "previous_pages_with_spares": r[8],
                    "created_at": r[9].isoformat() if r[9] else None,
                }
                for r in hist_rows
            ],
            "jobs": [
                {
                    "id": str(r[0]),
                    "job_name": r[1],
                    "page_reference": r[2],
                    "frequency": r[3],
                    "frequency_type": r[4],
                    "created_at": r[5].isoformat() if r[5] else None,
                    "updated_at": r[6].isoformat() if r[6] else None,
                    "job_description": r[7],
                }
                for r in jobs_rows
            ]
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-recent-extractions", tags=["Debug"], summary="Audit recent jobs extractions and manual runs")
async def debug_recent_extractions(
    since: str = "2026-11-15T00:00:00Z",
    until: str = "2026-11-17T23:59:59Z",
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        # Diagnostic: overall DB timestamp ranges
        db_stats_row = (await db.execute(text("""
            SELECT 
                (SELECT MIN(created_at) FROM jobs) AS min_job_created,
                (SELECT MAX(created_at) FROM jobs) AS max_job_created,
                (SELECT COUNT(*) FROM jobs) AS total_jobs,
                (SELECT MIN(last_run_at) FROM manual_extraction_runs) AS min_run_at,
                (SELECT MAX(last_run_at) FROM manual_extraction_runs) AS max_run_at,
                (SELECT COUNT(*) FROM manual_extraction_runs) AS total_runs,
                (SELECT MIN(last_extracted_at) FROM manual_page_extractions) AS min_page_at,
                (SELECT MAX(last_extracted_at) FROM manual_page_extractions) AS max_page_at,
                (SELECT COUNT(*) FROM manual_page_extractions) AS total_page_runs
        """))).fetchone()
        
        db_stats = {
            "min_job_created": db_stats_row[0].isoformat() if db_stats_row[0] else None,
            "max_job_created": db_stats_row[1].isoformat() if db_stats_row[1] else None,
            "total_jobs": db_stats_row[2],
            "min_run_at": db_stats_row[3].isoformat() if db_stats_row[3] else None,
            "max_run_at": db_stats_row[4].isoformat() if db_stats_row[4] else None,
            "total_runs": db_stats_row[5],
            "min_page_at": db_stats_row[6].isoformat() if db_stats_row[6] else None,
            "max_page_at": db_stats_row[7].isoformat() if db_stats_row[7] else None,
            "total_page_runs": db_stats_row[8],
        }

        # 25 most recently created jobs
        recent_jobs_res = await db.execute(text("""
            SELECT j.id, j.job_name, j.page_reference, j.created_at, j.updated_at, m.id AS manual_id, m.original_filename
            FROM jobs j
            LEFT JOIN manuals m ON j.source_manual_id = m.id
            ORDER BY j.created_at DESC
            LIMIT 25;
        """))
        recent_jobs = [
            {
                "id": str(r[0]),
                "job_name": r[1],
                "page": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "updated_at": r[4].isoformat() if r[4] else None,
                "manual_id": str(r[5]) if r[5] else None,
                "original_filename": r[6],
            }
            for r in recent_jobs_res.fetchall()
        ]

        # 1. Jobs created in time window grouped by manual
        sql_jobs = """
            SELECT 
                m.id AS manual_id,
                m.original_filename,
                m.vessel_id,
                vp.name AS vessel_name,
                COUNT(j.id) AS jobs_count,
                MIN(j.created_at) AS first_created_at,
                MAX(j.created_at) AS last_created_at,
                ARRAY_AGG(DISTINCT j.page_reference) AS page_references
            FROM jobs j
            JOIN manuals m ON j.source_manual_id = m.id
            LEFT JOIN vessel_projects vp ON m.vessel_id = vp.id
            WHERE j.created_at >= CAST(:since AS TIMESTAMPTZ) 
              AND j.created_at <= CAST(:until AS TIMESTAMPTZ)
              AND j.is_deleted = false
            GROUP BY m.id, m.original_filename, m.vessel_id, vp.name
            ORDER BY first_created_at DESC;
        """
        res_jobs = await db.execute(text(sql_jobs), {"since": since, "until": until})
        manuals_jobs = [
            {
                "manual_id": str(r[0]),
                "original_filename": r[1],
                "vessel_id": str(r[2]),
                "vessel_name": r[3],
                "jobs_count": r[4],
                "first_created_at": r[5].isoformat() if r[5] else None,
                "last_created_at": r[6].isoformat() if r[6] else None,
                "pages": [p for p in (r[7] or []) if p is not None],
            }
            for r in res_jobs.fetchall()
        ]

        # 2. Manual extraction runs in time window
        sql_runs = """
            SELECT 
                m.id AS manual_id,
                m.original_filename,
                m.vessel_id,
                vp.name AS vessel_name,
                mer.run_count,
                mer.last_run_at
            FROM manual_extraction_runs mer
            JOIN manuals m ON mer.manual_id = m.id
            LEFT JOIN vessel_projects vp ON m.vessel_id = vp.id
            WHERE mer.last_run_at >= CAST(:since AS TIMESTAMPTZ) 
              AND mer.last_run_at <= CAST(:until AS TIMESTAMPTZ)
            ORDER BY mer.last_run_at DESC;
        """
        res_runs = await db.execute(text(sql_runs), {"since": since, "until": until})
        manual_runs = [
            {
                "manual_id": str(r[0]),
                "original_filename": r[1],
                "vessel_id": str(r[2]),
                "vessel_name": r[3],
                "run_count": r[4],
                "last_run_at": r[5].isoformat() if r[5] else None,
            }
            for r in res_runs.fetchall()
        ]

        # 3. Manual page extractions in time window
        sql_page_runs = """
            SELECT 
                m.id AS manual_id,
                m.original_filename,
                COUNT(mpe.page_number) AS pages_extracted_count,
                ARRAY_AGG(mpe.page_number ORDER BY mpe.page_number) AS extracted_pages,
                MIN(mpe.last_extracted_at) AS first_run,
                MAX(mpe.last_extracted_at) AS last_run
            FROM manual_page_extractions mpe
            JOIN manuals m ON mpe.manual_id = m.id
            WHERE mpe.last_extracted_at >= CAST(:since AS TIMESTAMPTZ) 
              AND mpe.last_extracted_at <= CAST(:until AS TIMESTAMPTZ)
            GROUP BY m.id, m.original_filename
            ORDER BY last_run DESC;
        """
        res_page_runs = await db.execute(text(sql_page_runs), {"since": since, "until": until})
        page_runs = [
            {
                "manual_id": str(r[0]),
                "original_filename": r[1],
                "pages_extracted_count": r[2],
                "extracted_pages": r[3],
                "first_run": r[4].isoformat() if r[4] else None,
                "last_run": r[5].isoformat() if r[5] else None,
            }
            for r in res_page_runs.fetchall()
        ]

        # 4. 20 most recently updated manuals
        recent_manuals_res = await db.execute(text("""
            SELECT id, original_filename, status, updated_at, pages_with_jobs, pages_with_spares, pages_with_components
            FROM manuals
            ORDER BY updated_at DESC
            LIMIT 20;
        """))
        recent_manuals = [
            {
                "id": str(r[0]),
                "original_filename": r[1],
                "status": r[2],
                "updated_at": r[3].isoformat() if r[3] else None,
                "pages_with_jobs": r[4],
                "pages_with_spares": r[5],
                "pages_with_components": r[6],
            }
            for r in recent_manuals_res.fetchall()
        ]

        return {
            "status": "success",
            "time_window": {"since": since, "until": until},
            "db_stats": db_stats,
            "most_recent_jobs_in_db": recent_jobs,
            "manuals_with_jobs_created_in_window": manuals_jobs,
            "manual_extraction_runs_in_window": manual_runs,
            "manual_page_extractions_in_window": page_runs,
            "most_recent_updated_manuals": recent_manuals,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-manual-summary/{manual_id}", tags=["Debug"], summary="Get comprehensive extraction summary for manual")
async def debug_manual_summary(manual_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    from app.services.extractor import _parse_page_tokens
    import uuid
    try:
        mid = uuid.UUID(manual_id)
        res = await db.execute(text("""
            SELECT id, original_filename, pages_with_components, pages_with_jobs, pages_with_spares,
                   pages_with_components_physical, pages_with_jobs_physical, pages_with_spares_physical
            FROM manuals WHERE id = :mid
        """), {"mid": mid})
        row = res.fetchone()
        if not row:
            return {"error": "manual not found"}
            
        c_ref = row[5] or row[2] or ""
        j_ref = row[6] or row[3] or ""
        s_ref = row[7] or row[4] or ""
        
        c_target = _parse_page_tokens(c_ref)
        j_target = _parse_page_tokens(j_ref)
        s_target = _parse_page_tokens(s_ref)
        
        c_res = await db.execute(text("SELECT DISTINCT page_reference FROM components WHERE source_manual_id = :mid AND is_deleted = false AND page_reference IS NOT NULL"), {"mid": mid})
        j_res = await db.execute(text("SELECT DISTINCT page_reference FROM jobs WHERE source_manual_id = :mid AND is_deleted = false AND page_reference IS NOT NULL"), {"mid": mid})
        s_res = await db.execute(text("SELECT DISTINCT page_reference FROM spares WHERE source_manual_id = :mid AND is_deleted = false AND page_reference IS NOT NULL"), {"mid": mid})
        
        c_ext = [r[0] for r in c_res.fetchall()]
        j_ext = [r[0] for r in j_res.fetchall()]
        s_ext = [r[0] for r in s_res.fetchall()]
        
        return {
            "status": "success",
            "manual_id": manual_id,
            "filename": row[1],
            "components": {
                "target_count": len(c_target),
                "target_pages": c_target,
                "extracted_pages": sorted(c_ext),
                "missing_pages": sorted(list(set(c_target) - set(c_ext))),
            },
            "jobs": {
                "target_count": len(j_target),
                "target_pages": j_target,
                "extracted_pages": sorted(j_ext),
                "missing_pages": sorted(list(set(j_target) - set(j_ext))),
            },
            "spares": {
                "target_count": len(s_target),
                "target_pages": s_target,
                "extracted_pages": sorted(s_ext),
                "missing_pages": sorted(list(set(s_target) - set(s_ext))),
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/debug-download-manual/{manual_id}", tags=["Debug"], summary="Download raw manual PDF without auth")
async def debug_download_manual(manual_id: str, db: AsyncSession = Depends(get_db)):
    import os
    from sqlalchemy import text
    from app.services.blob_storage import BlobStorageService
    try:
        res = await db.execute(text("SELECT id, original_filename, blob_storage_key FROM manuals WHERE id = :mid"), {"mid": manual_id})
        row = res.fetchone()
        if not row:
            return Response(content="Manual not found", status_code=404)
        filename = row[1]
        blob_key = row[2]
        
        pdf_bytes = None
        if blob_key:
            try:
                blob_service = BlobStorageService()
                pdf_bytes = await blob_service.download_bytes(blob_key)
            except Exception as be:
                if os.path.exists(blob_key):
                    with open(blob_key, "rb") as f:
                        pdf_bytes = f.read()
                else:
                    raise be
        
        if not pdf_bytes:
            return Response(content="File bytes not found", status_code=404)
            
        import urllib.parse
        safe_fn = urllib.parse.quote(filename or "manual.pdf")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_fn}"}
        )
    except Exception as e:
        return Response(content=f"Error: {e}", status_code=500)


@router.post("/debug-upload-manual", tags=["Debug"], summary="Upload manual without auth")
async def debug_upload_manual(
    vessel_id: str = Form(...),
    file: UploadFile = File(...),
    pages_with_spares: str | None = Form(None),
    pages_with_spares_physical: str | None = Form(None),
    pages_with_components: str | None = Form(None),
    pages_with_jobs: str | None = Form(None),
    category: str | None = Form("Technical Manual"),
    component_name: str | None = Form(None),
    maker: str | None = Form(None),
    model: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    import hashlib
    import io
    import os
    import uuid
    from sqlalchemy import select
    from app.models.ingestion import Manual, ManualStatus
    from app.models.component import Component, QCStatus
    from app.models.vessel import VesselProject
    from app.models.user import User
    from app.services.blob_storage import BlobStorageService

    try:
        vid = uuid.UUID(vessel_id)
        v_res = await db.execute(select(VesselProject).where(VesselProject.id == vid))
        vessel = v_res.scalar_one_or_none()
        if not vessel:
            return {"status": "error", "message": f"Vessel {vessel_id} not found"}

        tenant_id = vessel.tenant_id
        u_res = await db.execute(select(User.id).where(User.tenant_id == tenant_id, User.is_deleted == False).limit(1))
        uploaded_by = u_res.scalar() or uuid.UUID("00000000-0000-0000-0000-000000000001")

        content = await file.read()
        sha256 = hashlib.sha256(content).hexdigest()
        manual_id = uuid.uuid4()
        filename = file.filename or "uploaded_manual.pdf"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

        blob_key = f"{tenant_id}/{vid}/{manual_id}/{filename}"
        blob_saved = False
        try:
            blob_svc = BlobStorageService()
            await blob_svc.upload_stream(blob_key, io.BytesIO(content), "application/pdf")
            blob_saved = True
        except Exception as e:
            upload_dir = f"/tmp/pms_uploads/{vid}"
            os.makedirs(upload_dir, exist_ok=True)
            disk_path = f"{upload_dir}/{manual_id}.pdf"
            with open(disk_path, "wb") as fh:
                fh.write(content)
            blob_key = disk_path

        manual = Manual(
            id=manual_id,
            tenant_id=tenant_id,
            vessel_id=vid,
            original_filename=filename,
            file_extension=ext,
            file_size_bytes=len(content),
            sharepoint_path="",
            blob_storage_key=blob_key,
            status=ManualStatus.classified,
            uploaded_by=uploaded_by,
            sha256_hash=sha256,
            category=category,
            pages_with_spares=pages_with_spares,
            pages_with_spares_physical=pages_with_spares_physical or pages_with_spares,
            pages_with_components=pages_with_components,
            pages_with_jobs=pages_with_jobs,
        )
        db.add(manual)

        if component_name or maker or model:
            comp = Component(
                tenant_id=tenant_id,
                vessel_id=vid,
                source_manual_id=manual_id,
                component_name=component_name or (filename.rsplit(".", 1)[0]),
                maker=maker,
                model=model,
                qc_status=QCStatus.approved,
                pdf_reference=filename,
            )
            db.add(comp)

        await db.commit()

        return {
            "status": "success",
            "manual_id": str(manual_id),
            "filename": filename,
            "blob_key": blob_key,
            "vessel_id": str(vid),
            "spares_pages": pages_with_spares_physical or pages_with_spares,
            "component_created": bool(component_name or maker or model),
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-claude-status", tags=["Debug"], summary="Check Claude API key and circuit breaker status")
async def debug_claude_status(
    reset_breaker: bool = True,
    key_override: str | None = None,
    test_call: bool = True,
):
    from app.services.extractor import is_claude_vision_billing_tripped, reset_claude_billing_breakers
    breaker_before = is_claude_vision_billing_tripped()

    if key_override:
        settings.ANTHROPIC_API_KEY = key_override.strip()

    if reset_breaker:
        reset_claude_billing_breakers()

    breaker_after = is_claude_vision_billing_tripped()

    current_key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    key_prefix = current_key[:12] if current_key else None
    key_suffix = current_key[-4:] if len(current_key) > 16 else None
    key_len = len(current_key)

    test_result = {}
    if test_call and current_key:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=current_key)
            model_id = getattr(settings, "CLAUDE_MODEL_ID", None) or "claude-sonnet-4-6"
            msg = await client.messages.create(
                model=model_id,
                max_tokens=20,
                messages=[{"role": "user", "content": "Respond with OK"}]
            )
            try:
                from app.services.token_tracker import record_claude_usage
                record_claude_usage(msg.usage, model=model_id)
            except Exception:
                pass
            test_result = {
                "success": True,
                "model": msg.model,
                "reply": msg.content[0].text if msg.content else None,
            }
        except Exception as exc:
            test_result = {
                "success": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
    elif not current_key:
        test_result = {"success": False, "error": "No ANTHROPIC_API_KEY set"}

    return {
        "status": "success",
        "key_configured": bool(current_key),
        "key_prefix": key_prefix,
        "key_suffix": key_suffix,
        "key_length": key_len,
        "claude_model": getattr(settings, "CLAUDE_MODEL_ID", None) or "claude-sonnet-4-6",
        "breaker_tripped_before": breaker_before,
        "breaker_tripped_after": breaker_after,
        "claude_test_call": test_result,
    }


@router.post("/debug-restore-freshwater-pages", tags=["Debug"], summary="Restore freshwater generator spare pages")
async def debug_restore_freshwater_pages(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.models.ingestion import Manual
    import uuid
    mid = uuid.UUID("806d403e-8910-4438-ad93-db2129751181")
    res = await db.execute(select(Manual).where(Manual.id == mid))
    m = res.scalar_one_or_none()
    if not m:
        res = await db.execute(select(Manual).where(Manual.original_filename.ilike("%Freshwater%"), Manual.is_deleted == False))
        m = res.scalar_one_or_none()
    if m:
        old_val = m.pages_with_spares_physical or m.pages_with_spares
        full_pages = "71-76, 88-90, 98-100, 104-106, 108, 110, 112, 113, 115, 116, 117, 118, 135, 143, 151, 178, 184, 185, 243, 245, 250, 251"
        m.pages_with_spares = full_pages
        m.pages_with_spares_physical = full_pages
        db.add(m)
        await db.commit()
        return {
            "status": "success",
            "manual_id": str(m.id),
            "manual": m.original_filename,
            "old_pages": old_val,
            "restored_pages": full_pages,
        }
    return {"status": "error", "message": "Manual not found"}


@router.post("/debug-extract-manual/{manual_id}", tags=["Debug"], summary="Trigger extraction without auth")
async def debug_extract_manual(
    manual_id: str,
    entity_types: str = "spare",
    pages: str | None = None,
    target_model: str | None = None,
    anthropic_key: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.extractor import auto_extract_from_manual, reset_claude_billing_breakers
    reset_claude_billing_breakers()
    if anthropic_key:
        settings.ANTHROPIC_API_KEY = anthropic_key.strip()
    from sqlalchemy import select
    from app.models.ingestion import Manual, ManualStatus
    import uuid
    try:
        etypes = [e.strip() for e in entity_types.split(",") if e.strip()]
        page_list = None
        m_filename = None
        m_ext = None
        mid = uuid.UUID(manual_id)
        res = await db.execute(select(Manual).where(Manual.id == mid))
        m = res.scalar_one_or_none()
        if m:
            m_filename = m.original_filename
            if not m.file_extension and m.original_filename and "." in m.original_filename:
                m.file_extension = m.original_filename.rsplit(".", 1)[-1].lower()
            m_ext = m.file_extension
            if pages:
                page_list = [int(p.strip()) for p in pages.split(",") if p.strip().isdigit()]
            if target_model:
                m.target_model = target_model.strip()
            m.status = ManualStatus.classified
            db.add(m)
            await db.commit()

        import asyncio
        async def _run_extraction():
            try:
                await auto_extract_from_manual(
                    manual_id_str=manual_id,
                    entity_types=etypes,
                    page_numbers=page_list,
                    target_model=target_model,
                )
            except Exception as e:
                import logging
                logging.getLogger("debug_extract").exception("debug-extract-manual failed: %s", e)

        asyncio.create_task(_run_extraction())
        return {
            "status": "queued",
            "message": f"Extraction triggered in background for manual {manual_id}",
            "filename": m_filename,
            "extension": m_ext,
            "target_model": target_model,
            "pages": page_list,
            "entity_types": etypes,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-spares/{manual_id}", tags=["Debug"], summary="List spares for manual without auth")
async def debug_spares(
    manual_id: str,
    page: int | None = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        sql = """
            SELECT id, part_number, part_name, drawing_number, drawing_position,
                   specification, spare_maker, spare_model, page_reference, confidence_score
            FROM spares
            WHERE source_manual_id = :mid AND is_deleted = false
        """
        params = {"mid": manual_id, "lim": limit}
        if page is not None:
            sql += " AND page_reference = :page"
            params["page"] = page
        sql += " ORDER BY page_reference ASC, id ASC LIMIT :lim"

        res = await db.execute(text(sql), params)
        rows = res.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": str(r[0]),
                "part_number": r[1],
                "part_name": r[2],
                "drawing_number": r[3],
                "drawing_position": r[4],
                "specification": r[5],
                "spare_maker": r[6],
                "spare_model": r[7],
                "page_reference": r[8],
                "confidence_score": r[9],
            })
        return {"status": "success", "count": len(results), "spares": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}



@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT tokens",
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Authenticate with email + password.

    Returns an access token (short-lived) and a refresh token (longer-lived).
    The JWT payload contains: user_id, email, role, tenant_id.
    """
    result = await db.execute(
        select(User).where(User.email == payload.email, User.is_deleted == False)
    )
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled. Contact your administrator.",
        )

    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "tenant_id": str(user.tenant_id),
    }

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    # Update last_login timestamp
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token for a new access token",
)
async def refresh_token(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Provide a valid refresh token to receive a new access token.

    The refresh token is validated and the user record is checked to ensure
    the account is still active.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token_payload = verify_token(payload.refresh_token)
    except JWTError:
        raise credentials_exception

    if token_payload.get("token_type") != "refresh":
        raise credentials_exception
    if await is_token_revoked(token_payload):
        raise credentials_exception

    user_id_str: str | None = token_payload.get("user_id")
    if not user_id_str:
        raise credentials_exception

    import uuid

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    new_token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "tenant_id": str(user.tenant_id),
    }

    new_access_token = create_access_token(data=new_token_data)
    new_refresh_token = create_refresh_token(data=new_token_data)
    await revoke_token_payload(token_payload)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Logout and revoke the active tokens",
)
async def logout(
    payload: LogoutRequest | None = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)] = None,
) -> Response:
    """
    Revoke the active access token and optionally the refresh token.
    """
    if credentials and credentials.credentials:
        try:
            access_payload = verify_token(credentials.credentials)
            if access_payload.get("token_type") == "access":
                await revoke_token_payload(access_payload)
        except JWTError:
            pass

    refresh_token = payload.refresh_token if payload else None
    if refresh_token:
        try:
            refresh_payload = verify_token(refresh_token)
            if refresh_payload.get("token_type") == "refresh":
                await revoke_token_payload(refresh_payload)
        except JWTError:
            pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/debug-claude-test-page/{manual_id}/{page_no}", tags=["Debug"])
async def debug_claude_test_page(manual_id: str, page_no: int, db: AsyncSession = Depends(get_db)):
    from app.services.extractor import _render_single_pdf_page_image, DEFAULT_PROMPTS
    from app.services.blob_storage import BlobStorageService
    from sqlalchemy import text
    import anthropic, base64

    res = await db.execute(text("SELECT id, original_filename, blob_storage_key FROM manuals WHERE id = :mid"), {"mid": manual_id})
    row = res.fetchone()
    if not row:
        return {"error": "manual not found"}
    blob_svc = BlobStorageService()
    pdf_bytes = await blob_svc.download_bytes(row[2])
    img_bytes = _render_single_pdf_page_image(pdf_bytes, page_no, 200)
    if not img_bytes:
        return {"error": "failed to render image"}

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    b64_data = base64.b64encode(img_bytes).decode("ascii")
    prompt_cfg = DEFAULT_PROMPTS["spare"]
    user_content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64_data}},
        {"type": "text", "text": "Extract all spare parts table rows from this page image into a raw JSON array. Start with [ and end with ]. Translate to English."},
    ]
    try:
        message = await client.messages.create(
            model=getattr(settings, "CLAUDE_MODEL_ID", None) or "claude-sonnet-4-6",
            max_tokens=4096,
            system=prompt_cfg["system"],
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = message.content[0].text
        tokens = {"input": message.usage.input_tokens, "output": message.usage.output_tokens}
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "img_len": len(img_bytes),
        }
    return {
        "manual": row[1],
        "page_no": page_no,
        "img_len": len(img_bytes),
        "raw_claude_response": raw_text,
        "tokens": tokens,
    }


@router.post("/debug-cleanup-manual-components/{manual_id}", tags=["Debug"], summary="Clean up falsely extracted components if manual has no component references")
async def debug_cleanup_manual_components(
    manual_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    from app.models.component import Component
    from app.models.ingestion import Manual
    import uuid
    from sqlalchemy import select, update

    try:
        mid = uuid.UUID(manual_id)
    except Exception:
        return {"status": "error", "message": f"Invalid UUID: {manual_id}"}

    m = await db.scalar(select(Manual).where(Manual.id == mid, Manual.is_deleted == False))
    if not m:
        return {"status": "error", "message": "Manual not found"}

    comp_ref = (m.pages_with_components_physical or "").strip() or (m.pages_with_components or "").strip()
    if comp_ref and not force:
        return {"status": "skipped", "message": f"Manual has configured component references: {comp_ref}. Cleanup skipped (use ?force=true to override)."}

    res = await db.execute(
        update(Component)
        .where(Component.source_manual_id == mid, Component.is_deleted == False)
        .values(is_deleted=True)
    )
    await db.commit()
    return {"status": "success", "manual_id": str(mid), "cleaned_components_count": res.rowcount}

