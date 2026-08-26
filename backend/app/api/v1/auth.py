from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
optional_bearer = HTTPBearer(auto_error=False)


@router.get("/debug-restore-m29", tags=["Debug"])
async def debug_restore_m29(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    try:
        results = []
        
        # 1. Check if the historical manual b480204a exists (even if deleted)
        old_res = await db.execute(text("""
            SELECT id, original_filename, is_deleted 
            FROM manuals 
            WHERE id = 'b480204a-2bdf-454d-9a82-a1941f92167f';
        """))
        old_row = old_res.fetchone()
        
        # 2. Find active M-29 manuals
        res = await db.execute(text("""
            SELECT id, original_filename FROM manuals 
            WHERE original_filename LIKE '%M-29%' AND is_deleted = false 
              AND id != 'b480204a-2bdf-454d-9a82-a1941f92167f';
        """))
        active_manuals = res.fetchall()
        
        # 3. If the old manual with the spares exists, re-link them to the active manuals
        relinked_count = 0
        if old_row:
            old_mid = old_row[0]
            old_name = old_row[1]
            
            # Find the active M-29 manual (preferably (1-2) or (2-2))
            for active_manual in active_manuals:
                active_mid = active_manual[0]
                active_name = active_manual[1]
                
                # Check how many spares are currently active for the new manual
                s_act = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = false;"), {"mid": active_mid})).scalar()
                
                # If the new manual has 0 spares, let's move the 1068 spares to it
                if s_act == 0:
                    # Count spares to move
                    s_to_move = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :old_mid;"), {"old_mid": old_mid})).scalar()
                    if s_to_move > 0:
                        await db.execute(text("""
                            UPDATE spares 
                            SET source_manual_id = :new_mid, is_deleted = false 
                            WHERE source_manual_id = :old_mid;
                        """), {"new_mid": active_mid, "old_mid": old_mid})
                        await db.execute(text("""
                            UPDATE manuals 
                            SET status = 'classified', error_message = null 
                            WHERE id = :new_mid;
                        """), {"new_mid": active_mid})
                        await db.commit()
                        
                        relinked_count += s_to_move
                        results.append({
                            "action": "relinked_spares",
                            "from_manual_id": str(old_mid),
                            "from_filename": old_name,
                            "to_manual_id": str(active_mid),
                            "to_filename": active_name,
                            "spares_moved": s_to_move
                        })
        
        # 4. Standard restore for other manuals
        for manual in active_manuals:
            mid = manual[0]
            filename = manual[1]
            
            # Count deleted records
            c_del = (await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            j_del = (await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            s_del = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            
            # Restore
            await db.execute(text("UPDATE components SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
            await db.execute(text("UPDATE jobs SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
            await db.execute(text("UPDATE spares SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
            await db.execute(text("UPDATE manuals SET status = 'classified', error_message = null WHERE id = :mid;"), {"mid": mid})
            await db.commit()
            
            results.append({
                "action": "standard_restore",
                "manual_id": str(mid),
                "filename": filename,
                "components_restored": c_del,
                "jobs_restored": j_del,
                "spares_restored": s_del
            })
            
        return {"status": "success", "results": results, "relinked_total_spares": relinked_count}
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
