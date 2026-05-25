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
