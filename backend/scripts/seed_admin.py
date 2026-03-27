#!/usr/bin/env python
"""
Seed script: create the default super_admin user.

Usage (from the backend/ directory):
    python scripts/seed_admin.py

Environment variables (can be set in .env):
    SEED_ADMIN_EMAIL        - defaults to admin@unionmaritime.com
    SEED_ADMIN_PASSWORD     - REQUIRED (or set in .env)
    SEED_ADMIN_FULL_NAME    - defaults to "System Administrator"
    SEED_TENANT_ID          - defaults to 00000000-0000-0000-0000-000000000001
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

# Make sure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, UserRole


async def seed() -> None:
    email = os.getenv("SEED_ADMIN_EMAIL", "admin@unionmaritime.com")
    password = os.getenv("SEED_ADMIN_PASSWORD", "")
    full_name = os.getenv("SEED_ADMIN_FULL_NAME", "System Administrator")
    tenant_id_str = os.getenv("SEED_TENANT_ID", "00000000-0000-0000-0000-000000000001")

    if not password:
        print("ERROR: SEED_ADMIN_PASSWORD environment variable is not set.")
        print("       Set it in your .env file or export it before running this script.")
        sys.exit(1)

    tenant_id = uuid.UUID(tenant_id_str)

    engine = create_async_engine(settings.async_database_url, echo=False)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine, expire_on_commit=False
    )

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == email, User.is_deleted == False)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Super admin '{email}' already exists — skipping.")
            return

        admin = User(
            tenant_id=tenant_id,
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            role=UserRole.super_admin,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        print(f"Created super_admin user:")
        print(f"  ID:        {admin.id}")
        print(f"  Email:     {admin.email}")
        print(f"  Full name: {admin.full_name}")
        print(f"  Role:      {admin.role.value}")
        print(f"  Tenant:    {admin.tenant_id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
