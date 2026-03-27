from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.feedback import CorrectionType, FeedbackAggregate, FeedbackEntry
from app.models.learning import FewShotStore, FineTuneRequest, FineTuneStatus
from app.models.user import User, UserRole

router = APIRouter()


@router.get("/feedback/dashboard", summary="Feedback and model performance dashboard")
async def feedback_dashboard(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    # Total corrections by type
    result = await db.execute(
        select(FeedbackEntry.correction_type, func.count().label("count"))
        .where(FeedbackEntry.tenant_id == current_user.tenant_id, FeedbackEntry.is_deleted == False)
        .group_by(FeedbackEntry.correction_type)
    )
    corrections_by_type = {
        row.correction_type.value if hasattr(row.correction_type, 'value') else str(row.correction_type): row.count
        for row in result.all()
    }

    # Last 12 weeks trend
    twelve_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=12)
    trend_result = await db.execute(
        select(FeedbackEntry.created_at)
        .where(
            FeedbackEntry.tenant_id == current_user.tenant_id,
            FeedbackEntry.created_at >= twelve_weeks_ago,
            FeedbackEntry.is_deleted == False,
        )
    )
    dates = [row[0] for row in trend_result.all()]
    weekly_counts: dict[str, int] = {}
    for d in dates:
        week_key = d.strftime("%Y-W%W")
        weekly_counts[week_key] = weekly_counts.get(week_key, 0) + 1

    trend = [
        {"week": k, "count": v}
        for k, v in sorted(weekly_counts.items())[-12:]
    ]

    # Current model version
    latest_ft = await db.execute(
        select(FineTuneRequest)
        .where(
            FineTuneRequest.status == FineTuneStatus.completed,
            FineTuneRequest.is_deleted == False,
        )
        .order_by(FineTuneRequest.completed_at.desc())
        .limit(1)
    )
    ft = latest_ft.scalar_one_or_none()
    model_version = ft.model_version if ft else "base"

    # Pending fine-tune count
    pending_ft = await db.scalar(
        select(func.count()).select_from(FineTuneRequest).where(
            FineTuneRequest.status == FineTuneStatus.pending,
            FineTuneRequest.is_deleted == False,
        )
    ) or 0

    # False positive/negative rates by category
    fp_result = await db.execute(
        select(
            FeedbackEntry.source_manual_category,
            func.count().label("count"),
        )
        .where(
            FeedbackEntry.correction_type == CorrectionType.false_positive,
            FeedbackEntry.tenant_id == current_user.tenant_id,
            FeedbackEntry.is_deleted == False,
        )
        .group_by(FeedbackEntry.source_manual_category)
    )
    false_positive_by_cat = {
        row[0] or "Unknown": row[1] for row in fp_result.all()
    }

    fn_result = await db.execute(
        select(
            FeedbackEntry.source_manual_category,
            func.count().label("count"),
        )
        .where(
            FeedbackEntry.correction_type == CorrectionType.false_negative,
            FeedbackEntry.tenant_id == current_user.tenant_id,
            FeedbackEntry.is_deleted == False,
        )
        .group_by(FeedbackEntry.source_manual_category)
    )
    false_negative_by_cat = {
        row[0] or "Unknown": row[1] for row in fn_result.all()
    }

    return {
        "total_corrections_by_type": corrections_by_type,
        "correction_rate_trend": trend,
        "current_model_version": model_version,
        "pending_fine_tune_count": pending_ft,
        "false_positive_rate_by_category": false_positive_by_cat,
        "false_negative_rate_by_category": false_negative_by_cat,
    }


@router.get("/feedback/entries", summary="Paginated feedback entries")
async def list_feedback_entries(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    result = await db.execute(
        select(FeedbackEntry)
        .where(
            FeedbackEntry.tenant_id == current_user.tenant_id,
            FeedbackEntry.is_deleted == False,
        )
        .order_by(FeedbackEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entries = result.scalars().all()
    return {
        "items": [
            {
                "id": str(e.id),
                "manual_id": str(e.manual_id),
                "entity_type": e.entity_type,
                "correction_type": e.correction_type.value if hasattr(e.correction_type, 'value') else str(e.correction_type),
                "original_value": e.original_value,
                "corrected_value": e.corrected_value,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "page": page,
    }


@router.post(
    "/feedback/trigger-fine-tune",
    summary="Trigger fine-tuning (Super Admin only)",
)
async def trigger_fine_tune(
    current_user: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    total = await db.scalar(
        select(func.count()).select_from(FeedbackEntry).where(
            FeedbackEntry.tenant_id == current_user.tenant_id,
            FeedbackEntry.is_deleted == False,
        )
    ) or 0

    req = FineTuneRequest(
        tenant_id=current_user.tenant_id,
        trigger_reason="Manual trigger by Super Admin",
        total_corrections=total,
        status=FineTuneStatus.pending,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return {"id": str(req.id), "status": req.status.value, "total_corrections": total}


@router.get("/feedback/few-shot-examples", summary="List few-shot example stores")
async def list_few_shot_examples(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(FewShotStore).where(
            FewShotStore.is_active == True, FewShotStore.is_deleted == False
        )
    )
    stores = result.scalars().all()
    return {
        "items": [
            {
                "id": str(s.id),
                "entity_type": s.entity_type,
                "version": s.version,
                "example_count": len(s.examples_json or []),
            }
            for s in stores
        ]
    }
