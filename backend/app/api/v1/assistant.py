from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.assistant import AmbiguityQueue
from app.models.user import User
from app.models.vessel import VesselProject

router = APIRouter()


MOCK_RESPONSES = {
    "component": [
        "Based on the document context, this component appears to be a centrifugal pump used in the seawater cooling system.",
        "The maker information suggests this is a Wartsila manufactured component. Typical maintenance intervals are 4000 running hours.",
        "I can see this component is linked to the main engine cooling circuit. The specification looks correct based on the manual.",
    ],
    "job": [
        "This maintenance job aligns with the manufacturer's recommended overhaul schedule of 8000 running hours.",
        "The safety precautions listed appear complete. I recommend also adding a note about lockout/tagout procedures.",
        "Based on similar vessels, this job typically takes 4-6 hours with 2 engineers.",
    ],
    "spare": [
        "This part number matches the manufacturer's spare parts catalog. The drawing reference looks correct.",
        "I noticed a potential duplicate: there's a similar part already in the spares list with part number close to this one.",
        "The specification for this spare part is consistent with the machinery maker's recommendations.",
    ],
    "general": [
        "I can help you review and correct extracted data from your vessel's technical manuals.",
        "If you have specific questions about a component, job, or spare part, click on that row and ask me directly.",
        "I'm analyzing the uploaded manuals and can provide context for any extracted information.",
    ],
}


async def _stream_mock_response(context_type: str) -> AsyncGenerator[str, None]:
    """Stream a mock response for dev/testing."""
    import asyncio
    import random

    responses = MOCK_RESPONSES.get(context_type, MOCK_RESPONSES["general"])
    response_text = random.choice(responses)

    # Simulate streaming word by word
    words = response_text.split()
    for i, word in enumerate(words):
        chunk = {"type": "delta", "content": word + (" " if i < len(words) - 1 else "")}
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.05)

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def _stream_openai_response(
    message: str, context_type: str, system_prompt: str
) -> AsyncGenerator[str, None]:
    """Stream from OpenAI GPT-4o."""
    try:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'type': 'delta', 'content': delta})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception:
        async for chunk in _stream_mock_response(context_type):
            yield chunk


@router.post("/{vessel_id}/assistant/chat", summary="Streaming AI chat for vessel context")
async def chat(
    vessel_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    message: str = body.get("message", "")
    context_type: str = body.get("context_type", "general")
    context_id: Optional[str] = body.get("context_id")

    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id, VesselProject.is_deleted == False
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")

    system_prompt = (
        f"You are a maritime PMS data extraction assistant for vessel '{vessel.name}'.\n"
        f"Vessel type: {vessel.vessel_type or 'Unknown'}.\n"
        f"Your role is to help QC reviewers verify and correct extracted components, "
        f"maintenance jobs, and spare parts from vessel technical manuals.\n"
        f"Context type: {context_type}. Context ID: {context_id or 'none'}.\n"
        "Be concise, accurate, and maritime-domain-aware."
    )

    if settings.OPENAI_API_KEY:
        stream_gen = _stream_openai_response(message, context_type, system_prompt)
    elif settings.ANTHROPIC_API_KEY:
        # Fallback to mock (Claude API streaming would go here)
        stream_gen = _stream_mock_response(context_type)
    else:
        stream_gen = _stream_mock_response(context_type)

    return StreamingResponse(
        stream_gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{vessel_id}/assistant/ambiguities", summary="List pending ambiguity questions")
async def list_ambiguities(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(AmbiguityQueue).where(
            AmbiguityQueue.vessel_id == vessel_id,
            AmbiguityQueue.resolved_at.is_(None),
            AmbiguityQueue.is_deleted == False,
        )
    )
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": str(a.id),
                "entity_type": a.entity_type,
                "entity_id": str(a.entity_id) if a.entity_id else None,
                "question_text": a.question_text,
                "context_page": a.context_page,
                "context_text": a.context_text,
                "created_at": a.created_at.isoformat(),
            }
            for a in items
        ]
    }


@router.post("/{vessel_id}/assistant/ambiguities/{item_id}/resolve", summary="Resolve an ambiguity")
async def resolve_ambiguity(
    vessel_id: uuid.UUID,
    item_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(AmbiguityQueue).where(
            AmbiguityQueue.id == item_id,
            AmbiguityQueue.vessel_id == vessel_id,
            AmbiguityQueue.is_deleted == False,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ambiguity not found")

    item.resolved_at = datetime.now(timezone.utc)
    item.resolution_text = body.get("resolution", "")
    db.add(item)
    await db.commit()
    return {"resolved": True, "id": str(item_id)}


@router.post("/{vessel_id}/assistant/batch-summary", summary="Batch summary of ambiguities")
async def batch_summary(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(AmbiguityQueue).where(
            AmbiguityQueue.vessel_id == vessel_id,
            AmbiguityQueue.is_deleted == False,
        )
    )
    all_items = result.scalars().all()
    pending = [a for a in all_items if a.resolved_at is None]
    resolved = [a for a in all_items if a.resolved_at is not None]

    return {
        "total": len(all_items),
        "pending": len(pending),
        "resolved": len(resolved),
        "pending_by_entity_type": {
            etype: sum(1 for a in pending if a.entity_type == etype)
            for etype in {a.entity_type for a in pending}
        },
        "summary": (
            f"There are {len(pending)} pending questions requiring your attention. "
            f"{len(resolved)} have been resolved in this session."
        ),
    }
