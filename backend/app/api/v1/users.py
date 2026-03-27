from __future__ import annotations

import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_password_hash
from app.deps import get_current_user, require_role
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate

router = APIRouter()


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all users (super_admin only)",
)
async def list_users(
    _: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> UserListResponse:
    """Return a paginated list of all non-deleted users in the system."""
    base_query = select(User).where(User.is_deleted == False)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total: int = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(base_query.offset(offset).limit(page_size))
    users = list(result.scalars().all())

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (super_admin only)",
)
async def create_user(
    _: Annotated[User, Depends(require_role(UserRole.super_admin))],
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Create a new user account. Email must be unique across the entire system."""
    # Check duplicate email
    existing = await db.execute(
        select(User).where(User.email == user_data.email, User.is_deleted == False)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{user_data.email}' already exists",
        )

    new_user = User(
        tenant_id=user_data.tenant_id,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return UserResponse.model_validate(new_user)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the current authenticated user",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.put(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update the current authenticated user's profile",
)
async def update_me(
    current_user: Annotated[User, Depends(get_current_user)],
    user_data: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Update editable fields on the current user's profile (not role)."""
    update_fields = user_data.model_dump(exclude_unset=True, exclude={"role", "is_active"})
    for field, value in update_fields.items():
        setattr(current_user, field, value)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a user by ID (super_admin only)",
)
async def get_user(
    user_id: uuid.UUID,
    _: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Retrieve a specific user by their UUID."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a user by ID (super_admin only)",
)
async def update_user(
    user_id: uuid.UUID,
    user_data: UserUpdate,
    _: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Update any field on a user, including role and active status."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    for field, value in user_data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Soft-delete a user (super_admin only)",
)
async def delete_user(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft-delete a user by setting is_deleted=True. Data is retained."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    user.is_deleted = True
    user.is_active = False
    db.add(user)
    await db.commit()
