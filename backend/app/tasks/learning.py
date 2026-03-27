from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from app.tasks import celery_app

logger = logging.getLogger(__name__)

CORRECTION_TRIGGER_THRESHOLD = 20
FINE_TUNE_THRESHOLD = 500


@celery_app.task(name="app.tasks.learning.check_rule_update_triggers")
def check_rule_update_triggers() -> dict:
    """
    Scheduled daily task.
    Counts corrections by type in last 30 days.
    If any type has >= 20 corrections: creates a RuleUpdateLog entry.
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import func, select
        from app.core.database import AsyncSessionLocal
        from app.models.feedback import CorrectionType, FeedbackEntry
        from app.models.learning import RuleUpdateLog
        from app.core.config import settings
        import uuid

        DEFAULT_TENANT_ID = uuid.UUID(settings.DEFAULT_TENANT_ID)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    FeedbackEntry.correction_type,
                    FeedbackEntry.entity_type,
                    func.count().label("count"),
                )
                .where(FeedbackEntry.created_at >= thirty_days_ago)
                .group_by(FeedbackEntry.correction_type, FeedbackEntry.entity_type)
            )
            rows = result.all()

            triggered = 0
            for row in rows:
                if row.count >= CORRECTION_TRIGGER_THRESHOLD:
                    log = RuleUpdateLog(
                        tenant_id=DEFAULT_TENANT_ID,
                        correction_type=row.correction_type.value if hasattr(row.correction_type, 'value') else str(row.correction_type),
                        entity_type=row.entity_type,
                        count_trigger=row.count,
                        action_taken=f"Auto-rule update recommended: {row.count} corrections in 30 days",
                        status="recommended",
                    )
                    db.add(log)
                    triggered += 1

            await db.commit()
            return {"rule_updates_triggered": triggered}

    return asyncio.run(_run())


@celery_app.task(name="app.tasks.learning.update_few_shot_examples")
def update_few_shot_examples() -> dict:
    """
    Selects top 10 highest-confidence corrections per entity_type.
    Stores them as few-shot examples.
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.feedback import CorrectionType, FeedbackEntry
        from app.models.learning import FewShotStore
        from app.core.config import settings
        import uuid

        DEFAULT_TENANT_ID = uuid.UUID(settings.DEFAULT_TENANT_ID)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(FeedbackEntry)
                .where(FeedbackEntry.corrected_value.isnot(None))
                .order_by(FeedbackEntry.created_at.desc())
                .limit(100)
            )
            entries = result.scalars().all()

            by_entity: dict[str, list] = {}
            for e in entries:
                etype = e.entity_type
                if etype not in by_entity:
                    by_entity[etype] = []
                if len(by_entity[etype]) < 10:
                    by_entity[etype].append(
                        {
                            "original": e.original_value,
                            "corrected": e.corrected_value,
                            "correction_type": e.correction_type.value if hasattr(e.correction_type, 'value') else str(e.correction_type),
                        }
                    )

            updated = 0
            for entity_type, examples in by_entity.items():
                # Find existing or create new
                existing = await db.execute(
                    select(FewShotStore).where(
                        FewShotStore.entity_type == entity_type,
                        FewShotStore.is_active == True,
                        FewShotStore.is_deleted == False,
                    )
                )
                store = existing.scalar_one_or_none()
                if store:
                    store.examples_json = examples
                    store.version += 1
                    db.add(store)
                else:
                    store = FewShotStore(
                        tenant_id=DEFAULT_TENANT_ID,
                        entity_type=entity_type,
                        examples_json=examples,
                        version=1,
                        is_active=True,
                    )
                    db.add(store)
                updated += 1

            await db.commit()
            return {"entity_types_updated": updated}

    return asyncio.run(_run())


@celery_app.task(name="app.tasks.learning.trigger_fine_tune_check")
def trigger_fine_tune_check() -> dict:
    """
    Counts total corrections. If >= 500: logs FineTuneRequest.
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import func, select
        from app.core.database import AsyncSessionLocal
        from app.models.feedback import FeedbackEntry
        from app.models.learning import FineTuneRequest, FineTuneStatus
        from app.core.config import settings
        import uuid

        DEFAULT_TENANT_ID = uuid.UUID(settings.DEFAULT_TENANT_ID)

        async with AsyncSessionLocal() as db:
            total = await db.scalar(select(func.count()).select_from(FeedbackEntry)) or 0

            if total >= FINE_TUNE_THRESHOLD:
                req = FineTuneRequest(
                    tenant_id=DEFAULT_TENANT_ID,
                    trigger_reason=f"Threshold reached: {total} total corrections",
                    total_corrections=total,
                    status=FineTuneStatus.pending,
                )
                db.add(req)
                await db.commit()
                return {"fine_tune_requested": True, "total_corrections": total}

            return {"fine_tune_requested": False, "total_corrections": total}

    return asyncio.run(_run())
