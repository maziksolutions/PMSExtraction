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
async def debug_test_render(manual_id: str, page: int = 105, db: AsyncSession = Depends(get_db)):
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
        
        return {
            "pdf_len": len(pdf_bytes),
            "page_count": page_count,
            "text_len": len(t),
            "text_sample": t[:300],
            "img_len": img_len,
            "render_err": err,
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
            
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
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


@router.post("/debug-extract-manual/{manual_id}", tags=["Debug"], summary="Trigger extraction without auth")
async def debug_extract_manual(
    manual_id: str,
    entity_types: str = "spare",
    pages: str | None = None,
    target_model: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.extractor import auto_extract_from_manual
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
                if "spare" in etypes:
                    m.pages_with_spares = pages
                    m.pages_with_spares_physical = pages
            if target_model:
                m.target_model = target_model.strip()
            m.status = ManualStatus.classified
            db.add(m)
            await db.commit()

        await auto_extract_from_manual(
            manual_id_str=manual_id,
            entity_types=etypes,
            page_numbers=page_list,
            target_model=target_model,
        )
        from sqlalchemy import text
        spares_res = await db.execute(
            text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = false"),
            {"mid": mid}
        )
        total_spares = spares_res.scalar() or 0
        return {
            "status": "success",
            "message": f"Extraction completed for manual {manual_id}",
            "filename": m_filename,
            "extension": m_ext,
            "target_model": target_model,
            "pages": pages,
            "spares_extracted": total_spares,
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
