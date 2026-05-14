from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.feedback import FeedbackEntry
from app.models.ingestion import Manual
from app.models.learning import FewShotStore, FineTuneRequest, FineTuneStatus, RuleUpdateLog
from app.models.vessel import VesselProject

logger = logging.getLogger(__name__)

MAX_FEW_SHOT_EXAMPLES = 24
PROMPT_FEW_SHOT_LIMIT = 4
PROMPT_CONTEXT_MAX_CHARS = 3_000
RULE_TRIGGER_THRESHOLD = 20
RULE_LOG_SUPPRESSION_DAYS = 7
FINE_TUNE_THRESHOLD = 500


def _coerce_examples(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _truncate(value: str, max_chars: int = 220) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."


def _json_preview(value: Any, max_chars: int = 220) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except Exception:
        rendered = str(value)
    return _truncate(rendered, max_chars=max_chars)


def _field_label(field: str) -> str:
    return field.replace("_", " ")


def _changed_fields(original: dict[str, Any], corrected: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for field, new_value in corrected.items():
        if original.get(field) != new_value:
            fields.append(field)
    return sorted(set(fields))


def _field_reason(field: str, old_value: Any, new_value: Any) -> str:
    label = _field_label(field)
    if field == "category":
        return f"the document was reclassified because the previous category did not match the manual type"
    if "pages_with_" in field:
        return f"the {label} were corrected to the reviewer-verified page references"
    if field == "useful_for_extraction":
        return "the document usefulness was corrected to reflect whether extraction should run on this manual"
    if field in {"frequency", "frequency_type", "initial_due", "initial_frequency_type"}:
        return f"the {label} was corrected to match the maintenance interval stated in the manual"
    if field in {"maker", "model", "spare_maker", "spare_model"}:
        return f"the {label} was corrected to match the manufacturer/model shown in the source"
    if old_value in (None, "", [], {}):
        return f"the {label} was missing in the original extraction"
    if new_value in (None, "", [], {}):
        return f"the incorrect {label} was removed because it was not supported by the source"
    return f"the {label} was corrected from the extracted value to the reviewer-approved value"


def _field_instruction(entity_type: str, field: str, old_value: Any, new_value: Any) -> str:
    label = _field_label(field)
    if field == "category":
        return "Classify by the dominant document purpose, and prefer the reviewer-approved category when filename and page structure match similar manuals."
    if "pages_with_" in field:
        return "Use only reviewer-verified physical PDF pages for extraction targeting, and do not infer adjacent page ranges unless the section clearly continues."
    if field == "useful_for_extraction":
        return "Run extraction only when the manual contains usable equipment, maintenance, or spare-part content."
    if field == "reviewer_comments":
        return "Treat reviewer comments as explicit guidance for similar future manuals."
    if field in {"frequency", "frequency_type", "initial_due", "initial_frequency_type"}:
        return "Normalize maintenance intervals to the allowed PMS frequency schema without guessing missing intervals."
    if field in {"maker", "model", "spare_maker", "spare_model"}:
        return "Extract maker and model only from explicit title, table, or nameplate evidence."
    if field in {"component_name", "job_name", "part_name"}:
        return f"Prefer the exact equipment terminology used in the manual for {label}, keeping the machine context intact."
    if field in {"job_description", "safety_precaution", "specification", "assembly_description"}:
        return f"Capture {label} only when it is explicitly stated in the source text or table."
    if new_value in (None, "", [], {}):
        return f"Leave {label} blank when the source does not support a reliable value instead of guessing."
    return f"For {entity_type.replace('_', ' ')}, extract {label} from explicit source evidence and follow the reviewer-approved normalization pattern."


def _derive_reason(
    *,
    original: dict[str, Any],
    corrected: dict[str, Any],
    changed_fields: list[str],
    reviewer_comment: str | None,
) -> str:
    reviewer_comment = (reviewer_comment or "").strip()
    if reviewer_comment:
        return reviewer_comment

    reasons = [_field_reason(field, original.get(field), corrected.get(field)) for field in changed_fields[:3]]
    if not reasons:
        return "the reviewer adjusted the extracted data to better match the source manual"
    return "; ".join(reasons)


def _derive_instruction(
    *,
    entity_type: str,
    original: dict[str, Any],
    corrected: dict[str, Any],
    changed_fields: list[str],
) -> str:
    instructions: list[str] = []
    for field in changed_fields:
        instruction = _field_instruction(entity_type, field, original.get(field), corrected.get(field))
        if instruction not in instructions:
            instructions.append(instruction)
    if not instructions:
        instructions.append(
            f"For {entity_type.replace('_', ' ')}, prefer reviewer-approved patterns from similar manuals before falling back to generic extraction."
        )
    return " ".join(instructions[:3])


def _sort_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        examples,
        key=lambda item: str(item.get("captured_at") or ""),
        reverse=True,
    )


async def build_learning_context(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    source_manual_category: str | None = None,
    max_examples: int = PROMPT_FEW_SHOT_LIMIT,
) -> str | None:
    result = await db.execute(
        select(FewShotStore).where(
            FewShotStore.tenant_id == tenant_id,
            FewShotStore.entity_type == entity_type,
            FewShotStore.is_active == True,
            FewShotStore.is_deleted == False,
        )
    )
    store = result.scalar_one_or_none()
    if store is None:
        return None

    examples = _sort_examples(_coerce_examples(store.examples_json))
    if source_manual_category:
        category_examples = [
            item for item in examples if item.get("source_manual_category") == source_manual_category
        ]
        if category_examples:
            examples = category_examples

    if not examples:
        return None

    lines = [
        f"Reviewer-learned guidance for {entity_type.replace('_', ' ')}.",
        "Use these corrections as tie-breakers for similar manuals, but do not invent unsupported values.",
    ]

    for index, example in enumerate(examples[:max_examples], start=1):
        changed = ", ".join(example.get("changed_fields") or []) or "reviewed fields"
        reason = _truncate(str(example.get("reason") or ""), 220)
        instruction = _truncate(str(example.get("next_time_instruction") or ""), 260)
        original_preview = _json_preview(example.get("original"))
        corrected_preview = _json_preview(example.get("corrected"))
        lines.append(
            f"Example {index}: fields={changed}; why={reason}; next_time={instruction}; "
            f"original={original_preview}; corrected={corrected_preview}"
        )
        if len("\n".join(lines)) >= PROMPT_CONTEXT_MAX_CHARS:
            break

    context = "\n".join(lines)
    return context[:PROMPT_CONTEXT_MAX_CHARS]


async def run_feedback_learning_pipeline(
    db: AsyncSession,
    *,
    feedback_id: uuid.UUID,
) -> dict[str, Any]:
    feedback_result = await db.execute(
        select(FeedbackEntry).where(
            FeedbackEntry.id == feedback_id,
            FeedbackEntry.is_deleted == False,
        )
    )
    feedback = feedback_result.scalar_one_or_none()
    if feedback is None:
        return {"status": "missing"}

    original = feedback.original_value if isinstance(feedback.original_value, dict) else {}
    corrected = feedback.corrected_value if isinstance(feedback.corrected_value, dict) else {}
    changed_fields = _changed_fields(original, corrected)
    if not changed_fields:
        return {"status": "noop", "feedback_id": str(feedback.id)}

    manual_result = await db.execute(
        select(Manual, VesselProject.vessel_type)
        .join(VesselProject, VesselProject.id == Manual.vessel_id, isouter=True)
        .where(Manual.id == feedback.manual_id)
    )
    manual_row = manual_result.first()
    manual = manual_row[0] if manual_row else None
    vessel_type = feedback.vessel_type or (manual_row[1] if manual_row else None)
    source_manual_category = feedback.source_manual_category or (manual.category if manual else None)
    reviewer_comment = None
    if isinstance(corrected.get("reviewer_comments"), str):
        reviewer_comment = corrected.get("reviewer_comments")
    elif manual and manual.reviewer_comments:
        reviewer_comment = manual.reviewer_comments

    reason = _derive_reason(
        original=original,
        corrected=corrected,
        changed_fields=changed_fields,
        reviewer_comment=reviewer_comment,
    )
    next_time_instruction = _derive_instruction(
        entity_type=feedback.entity_type,
        original=original,
        corrected=corrected,
        changed_fields=changed_fields,
    )

    example_payload = {
        "feedback_id": str(feedback.id),
        "entity_type": feedback.entity_type,
        "correction_type": feedback.correction_type.value,
        "source_manual_category": source_manual_category,
        "vessel_type": vessel_type,
        "page_number": feedback.page_number,
        "context_span": feedback.context_span,
        "changed_fields": changed_fields,
        "reason": reason,
        "next_time_instruction": next_time_instruction,
        "original": original,
        "corrected": corrected,
        "captured_at": feedback.created_at.isoformat() if feedback.created_at else datetime.now(timezone.utc).isoformat(),
        "manual_filename": manual.original_filename if manual else None,
    }

    store_result = await db.execute(
        select(FewShotStore).where(
            FewShotStore.tenant_id == feedback.tenant_id,
            FewShotStore.entity_type == feedback.entity_type,
            FewShotStore.is_active == True,
            FewShotStore.is_deleted == False,
        )
    )
    store = store_result.scalar_one_or_none()
    examples = []
    if store is not None:
        examples = [
            item
            for item in _coerce_examples(store.examples_json)
            if str(item.get("feedback_id")) != str(feedback.id)
        ]
        examples.append(example_payload)
        store.examples_json = _sort_examples(examples)[:MAX_FEW_SHOT_EXAMPLES]
        store.version += 1
        db.add(store)
    else:
        store = FewShotStore(
            tenant_id=feedback.tenant_id,
            entity_type=feedback.entity_type,
            examples_json=[example_payload],
            version=1,
            is_active=True,
        )
        db.add(store)

    recent_window = datetime.now(timezone.utc) - timedelta(days=30)
    recent_count = await db.scalar(
        select(func.count()).select_from(FeedbackEntry).where(
            FeedbackEntry.tenant_id == feedback.tenant_id,
            FeedbackEntry.entity_type == feedback.entity_type,
            FeedbackEntry.correction_type == feedback.correction_type,
            FeedbackEntry.created_at >= recent_window,
            FeedbackEntry.is_deleted == False,
        )
    ) or 0

    if recent_count >= RULE_TRIGGER_THRESHOLD:
        recent_rule_window = datetime.now(timezone.utc) - timedelta(days=RULE_LOG_SUPPRESSION_DAYS)
        existing_rule = await db.scalar(
            select(func.count()).select_from(RuleUpdateLog).where(
                RuleUpdateLog.tenant_id == feedback.tenant_id,
                RuleUpdateLog.entity_type == feedback.entity_type,
                RuleUpdateLog.correction_type == feedback.correction_type.value,
                RuleUpdateLog.created_at >= recent_rule_window,
                RuleUpdateLog.is_deleted == False,
            )
        ) or 0
        if existing_rule == 0:
            db.add(
                RuleUpdateLog(
                    tenant_id=feedback.tenant_id,
                    correction_type=feedback.correction_type.value,
                    entity_type=feedback.entity_type,
                    count_trigger=recent_count,
                    action_taken=(
                        f"Auto-learned repeated correction pattern for fields: {', '.join(changed_fields)}. "
                        f"Reason: {reason}"
                    ),
                    status="learned",
                )
            )

    total_corrections = await db.scalar(
        select(func.count()).select_from(FeedbackEntry).where(
            FeedbackEntry.tenant_id == feedback.tenant_id,
            FeedbackEntry.is_deleted == False,
        )
    ) or 0
    if total_corrections >= FINE_TUNE_THRESHOLD:
        pending_or_running = await db.scalar(
            select(func.count()).select_from(FineTuneRequest).where(
                FineTuneRequest.tenant_id == feedback.tenant_id,
                FineTuneRequest.status.in_([FineTuneStatus.pending, FineTuneStatus.running]),
                FineTuneRequest.is_deleted == False,
            )
        ) or 0
        if pending_or_running == 0:
            db.add(
                FineTuneRequest(
                    tenant_id=feedback.tenant_id,
                    trigger_reason=(
                        f"Auto-triggered from reviewer corrections for {feedback.entity_type}. "
                        f"Latest pattern: {', '.join(changed_fields)}"
                    ),
                    total_corrections=total_corrections,
                    status=FineTuneStatus.pending,
                )
            )

    await db.commit()
    return {
        "status": "processed",
        "feedback_id": str(feedback.id),
        "entity_type": feedback.entity_type,
        "changed_fields": changed_fields,
    }


async def schedule_feedback_learning(feedback_id: uuid.UUID) -> None:
    try:
        from app.tasks.learning import process_feedback_entry

        process_feedback_entry.delay(str(feedback_id))
        return
    except Exception as exc:
        logger.warning(
            "schedule_feedback_learning: Celery dispatch failed for %s, running inline: %s",
            feedback_id,
            exc,
        )

    try:
        async with AsyncSessionLocal() as db:
            await run_feedback_learning_pipeline(db, feedback_id=feedback_id)
    except Exception:
        logger.exception("schedule_feedback_learning: inline processing failed for %s", feedback_id)
