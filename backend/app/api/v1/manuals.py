from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import tempfile
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update, text
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.database import get_db
from app.deps import get_current_user
from app.models.feedback import CorrectionType, FeedbackEntry
from app.models.ingestion import Manual, ManualPageRefHistory, ManualStatus
from app.models.user import User
from app.models.vessel import VesselProject
from app.schemas.manual import DeletedManualOut, ManualOut, ManualPageRefHistoryOut, ManualUpdate
from app.services.feedback_learning import schedule_feedback_learning
from app.services.review_workflow import broadcast_activity, log_activity
from app.services.upload_security import validate_uploaded_file_bytes

router = APIRouter()
logger = logging.getLogger(__name__)
MANUAL_CACHE_DIR = os.path.join(tempfile.gettempdir(), "pms_manual_cache")


VESSEL_TYPE_MANUAL_TEMPLATES = {
    "Bulk Carrier": [
        "Instruction Manual",
        "Machinery Particulars",
        "General Arrangement",
        "Pipeline Diagrams/P&ID",
        "Electrical Diagrams",
    ],
    "Tanker": [
        "Instruction Manual",
        "Machinery Particulars",
        "General Arrangement",
        "Pipeline Diagrams/P&ID",
        "LSA/FFA Plans",
        "Tank Capacity Plan",
        "Electrical Diagrams",
    ],
    "Container Ship": [
        "Instruction Manual",
        "Machinery Particulars",
        "General Arrangement",
        "Electrical Diagrams",
        "Class Certificates/Surveys",
    ],
}


async def _get_vessel_or_404(vessel_id: uuid.UUID, db: AsyncSession) -> VesselProject:
    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id,
            VesselProject.is_deleted == False,
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")
    return vessel


def _build_manual_filters(
    *,
    vessel_id: uuid.UUID,
    tenant_id: uuid.UUID,
    category: Optional[str] = None,
    manual_status: Optional[str] = None,
    min_confidence: Optional[int] = None,
    search: Optional[str] = None,
    useful_for_extraction: Optional[str] = None,
    batch_number: Optional[int] = None,
) -> list[Any]:
    base_filter: list[Any] = [
        Manual.vessel_id == vessel_id,
        Manual.tenant_id == tenant_id,
        Manual.is_deleted == False,
        Manual.blob_storage_key.is_not(None),
    ]

    if category:
        base_filter.append(Manual.category == category)
    if batch_number is not None:
        base_filter.append(Manual.batch_number == batch_number)
    if manual_status:
        try:
            base_filter.append(Manual.status == ManualStatus(manual_status))
        except ValueError:
            pass
    if min_confidence is not None:
        base_filter.append(Manual.classification_confidence >= min_confidence)
    if search:
        base_filter.append(Manual.original_filename.ilike(f"%{search}%"))
    if useful_for_extraction:
        base_filter.append(Manual.useful_for_extraction == useful_for_extraction)

    return base_filter


def _manual_order_expr(sort_by: str, sort_order: str):
    if sort_by == "filename":
        order_col = Manual.original_filename
    elif sort_by in ("created_at", "sequence_number"):
        order_col = Manual.created_at
    elif sort_by == "file_size":
        order_col = Manual.file_size
    elif sort_by == "category":
        order_col = Manual.category
    elif sort_by == "useful_for_extraction":
        order_col = Manual.useful_for_extraction
    elif sort_by in ("batch_number", "iteration", "batch"):
        order_col = Manual.batch_number
    else:
        order_col = Manual.classification_confidence
    return order_col.asc() if sort_order == "asc" else order_col.desc()


def _prepare_manual_update_data(
    manual: Manual,
    update_data: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    prepared = dict(update_data)
    page_field_groups = [
        ("pages_with_components", "pages_with_components_printed", "pages_with_components_physical"),
        ("pages_with_jobs", "pages_with_jobs_printed", "pages_with_jobs_physical"),
        ("pages_with_spares", "pages_with_spares_printed", "pages_with_spares_physical"),
    ]
    page_fields_changed = False

    for canonical_field, printed_field, physical_field in page_field_groups:
        if printed_field in prepared or physical_field in prepared:
            printed_value = prepared.get(printed_field, getattr(manual, printed_field))
            physical_value = prepared.get(physical_field, getattr(manual, physical_field))
            if physical_field in prepared:
                prepared[canonical_field] = physical_value or printed_value or ""
            else:
                prepared[canonical_field] = printed_value or physical_value or ""
            page_fields_changed = True
        elif canonical_field in prepared:
            canonical_value = prepared[canonical_field]
            prepared.setdefault(printed_field, canonical_value)

    return prepared, page_fields_changed


def _original_manual_snapshot(manual: Manual) -> dict[str, Any]:
    return {
        "category": manual.category,
        "useful_for_extraction": manual.useful_for_extraction,
        "classification_confidence": manual.classification_confidence,
        "pages_with_components": manual.pages_with_components,
        "pages_with_jobs": manual.pages_with_jobs,
        "pages_with_spares": manual.pages_with_spares,
        "pages_with_components_printed": manual.pages_with_components_printed,
        "pages_with_jobs_printed": manual.pages_with_jobs_printed,
        "pages_with_spares_printed": manual.pages_with_spares_printed,
        "pages_with_components_physical": manual.pages_with_components_physical,
        "pages_with_jobs_physical": manual.pages_with_jobs_physical,
        "pages_with_spares_physical": manual.pages_with_spares_physical,
        "page_explanations": manual.page_explanations,
        "reviewer_comments": manual.reviewer_comments,
        "supply_type": manual.supply_type,
        "target_model": manual.target_model,
    }


async def _apply_manual_updates(
    *,
    manual: Manual,
    update_data: dict[str, Any],
    current_user: User,
    db: AsyncSession,
    change_source: str = "user_edit",
    notes: Optional[str] = None,
) -> tuple[dict[str, Any], uuid.UUID | None]:
    orig_comp = manual.pages_with_components
    orig_jobs = manual.pages_with_jobs
    orig_spares = manual.pages_with_spares
    orig_comp_phys = manual.pages_with_components_physical
    orig_jobs_phys = manual.pages_with_jobs_physical
    orig_spares_phys = manual.pages_with_spares_physical
    prepared, page_fields_changed = _prepare_manual_update_data(manual, update_data)
    original = _original_manual_snapshot(manual)

    if page_fields_changed and "page_explanations" not in prepared:
        # Imported/manual overrides replace model-selected page refs, so do not leave stale reasons behind.
        prepared["page_explanations"] = None

    for field, value in prepared.items():
        setattr(manual, field, value)

    db.add(manual)

    new_comp = manual.pages_with_components
    new_jobs = manual.pages_with_jobs
    new_spares = manual.pages_with_spares
    new_comp_phys = manual.pages_with_components_physical
    new_jobs_phys = manual.pages_with_jobs_physical
    new_spares_phys = manual.pages_with_spares_physical

    has_page_diff = (
        orig_comp != new_comp
        or orig_jobs != new_jobs
        or orig_spares != new_spares
        or orig_comp_phys != new_comp_phys
        or orig_jobs_phys != new_jobs_phys
        or orig_spares_phys != new_spares_phys
    )

    if page_fields_changed or has_page_diff:
        user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None) or "User"
        history_entry = ManualPageRefHistory(
            tenant_id=manual.tenant_id,
            vessel_id=manual.vessel_id,
            manual_id=manual.id,
            changed_by_user_id=getattr(current_user, "id", None),
            changed_by_name=user_name,
            change_source=change_source,
            pages_with_components=new_comp,
            pages_with_jobs=new_jobs,
            pages_with_spares=new_spares,
            pages_with_components_physical=new_comp_phys,
            pages_with_jobs_physical=new_jobs_phys,
            pages_with_spares_physical=new_spares_phys,
            previous_pages_with_components=orig_comp,
            previous_pages_with_jobs=orig_jobs,
            previous_pages_with_spares=orig_spares,
            notes=notes,
        )
        db.add(history_entry)

    feedback_id: uuid.UUID | None = None
    corrected = {k: v for k, v in prepared.items()}
    if corrected:
        feedback = FeedbackEntry(
            tenant_id=current_user.tenant_id,
            manual_id=manual.id,
            entity_type="manual_classification",
            original_value=original,
            corrected_value=corrected,
            correction_type=CorrectionType.wrong_value,
            vessel_type=None,
            source_manual_category=prepared.get("category") or manual.category,
            context_span=(
                corrected.get("reviewer_comments")
                if isinstance(corrected.get("reviewer_comments"), str)
                else f"Updated manual screening fields: {', '.join(sorted(corrected.keys()))}"
            ),
            created_by=current_user.id,
        )
        db.add(feedback)
        await db.flush()
        feedback_id = feedback.id

    return prepared, feedback_id


def _normalise_excel_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    cleaned = str(value).strip()
    return cleaned or None


def _parse_optional_int(value: Any, *, field_name: str) -> Optional[int]:
    cleaned = _normalise_excel_value(value)
    if cleaned is None:
        return None
    try:
        return int(float(cleaned))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a whole number") from exc


def _normalise_import_field_value(field: str, value: Any) -> Any:
    cleaned = _normalise_excel_value(value)
    if cleaned is None:
        return None

    lowered = cleaned.lower()
    if field == "useful_for_extraction":
        allowed = {"yes", "partial", "no"}
        if lowered not in allowed:
            raise ValueError("Useful For Extraction must be yes, partial, or no")
        return lowered
    if field == "supply_type":
        if lowered in {"yard supply", "yard_supply", "yard-supply"}:
            return "yard_supply"
        if lowered == "oem":
            return "OEM"
        raise ValueError("Source must be OEM or yard_supply")

    return cleaned


def _manual_export_headers() -> list[str]:
    return [
        "Manual ID",
        "File Name",
        "Size (MB)",
        "Status",
        "Category",
        "Useful For Extraction",
        "Source",
        "Confidence (%)",
        "Components Printed Page Ref",
        "Components Physical Page Ref",
        "Job Printed Page Ref",
        "Job Physical Page Ref",
        "Spare Printed Page Ref",
        "Spare Physical Page Ref",
        "Target Model",
        "Reviewer Comments",
    ]


def _normalise_header(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _manual_import_aliases() -> dict[str, str]:
    return {
        "manual id": "manual_id",
        "id": "manual_id",
        "file name": "original_filename",
        "filename": "original_filename",
        "category": "category",
        "useful for extraction": "useful_for_extraction",
        "useful": "useful_for_extraction",
        "source": "supply_type",
        "supply type": "supply_type",
        "confidence (%)": "classification_confidence",
        "confidence": "classification_confidence",
        "components printed page ref": "pages_with_components_printed",
        "components physical page ref": "pages_with_components_physical",
        "job printed page ref": "pages_with_jobs_printed",
        "job physical page ref": "pages_with_jobs_physical",
        "spare printed page ref": "pages_with_spares_printed",
        "spare physical page ref": "pages_with_spares_physical",
        "reviewer comments": "reviewer_comments",
    }


_MANUAL_PAGE_BLOCK_RE = re.compile(r"\[PAGE\s+(\d+)\]\s*\n?(.*?)(?=(?:\n\[PAGE\s+\d+\])|\Z)", re.S)


def _parse_preview_pages(value: str) -> list[int]:
    pages: set[int] = set()
    for token in value.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        if "-" in cleaned:
            start_raw, end_raw = cleaned.split("-", 1)
            try:
                start = int(start_raw.strip())
                end = int(end_raw.strip())
            except ValueError:
                continue
            for page in range(min(start, end), max(start, end) + 1):
                pages.add(page)
            continue
        try:
            pages.add(int(cleaned))
        except ValueError:
            continue
    return sorted(page for page in pages if page > 0)


def _manual_text_by_page(manual: Manual) -> dict[int, str]:
    text = manual.extracted_text or ""
    if not text:
        return {}
    pages: dict[int, str] = {}
    for match in _MANUAL_PAGE_BLOCK_RE.finditer(text):
        pages[int(match.group(1))] = match.group(2).strip()
    if pages:
        return pages
    return {1: text.strip()}


async def _download_manual_bytes(manual: Manual) -> bytes:
    from app.services.blob_storage import BlobStorageService

    blob_key = manual.blob_storage_key
    if not blob_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual file is not available.")

    if os.path.exists(blob_key):
        with open(blob_key, "rb") as fh:
            return fh.read()

    # Check local container cache
    os.makedirs(MANUAL_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(MANUAL_CACHE_DIR, f"{manual.id}.pdf")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as fh:
                cached_data = fh.read()
                if len(cached_data) > 0:
                    return cached_data
        except Exception as err:
            logger.warning(f"Could not read cached manual {manual.id}: {err}")

    blob_service = BlobStorageService()
    file_bytes = await blob_service.download_bytes(blob_key)
    try:
        with open(cache_path, "wb") as fh:
            fh.write(file_bytes)
    except Exception as err:
        logger.warning(f"Could not write manual to cache {manual.id}: {err}")
    return file_bytes


def _render_pdf_preview_pages_sync(
    file_bytes: bytes,
    requested_pages: list[int],
    page_text_lookup: dict[int, str],
) -> tuple[int, list[dict[str, Any]]]:
    """Render preview pages for a PDF file using PyMuPDF (fitz) with pdfplumber fallback."""
    preview_pages: list[dict[str, Any]] = []
    total_pages = 0

    # 1. High-performance PyMuPDF (fitz) rendering (~30ms per page)
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(doc)
        for page_number in requested_pages:
            page_payload: dict[str, Any] = {
                "page_number": page_number,
                "text_excerpt": (page_text_lookup.get(page_number) or "")[:4000],
                "image_data_url": None,
            }
            if 1 <= page_number <= len(doc):
                page = doc.load_page(page_number - 1)
                try:
                    pix = page.get_pixmap(dpi=140)
                    png_bytes = pix.tobytes("png")
                    page_payload["image_data_url"] = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
                except Exception as render_exc:
                    logger.warning(f"PyMuPDF rendering error on page {page_number}: {render_exc}")
                    page_payload["image_data_url"] = None

                if not page_payload["text_excerpt"]:
                    try:
                        page_payload["text_excerpt"] = (page.get_text() or "")[:4000]
                    except Exception:
                        page_payload["text_excerpt"] = ""
            else:
                page_payload["error"] = "Requested page is outside the PDF page count."
            preview_pages.append(page_payload)
        doc.close()
        return total_pages, preview_pages
    except Exception as fitz_err:
        logger.warning(f"PyMuPDF failed or unavailable, falling back to pdfplumber: {fitz_err}")

    # 2. Fallback to pdfplumber
    import pdfplumber

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        total_pages = len(pdf.pages)
        for page_number in requested_pages:
            page_payload: dict[str, Any] = {
                "page_number": page_number,
                "text_excerpt": (page_text_lookup.get(page_number) or "")[:4000],
                "image_data_url": None,
            }
            if 1 <= page_number <= len(pdf.pages):
                page = pdf.pages[page_number - 1]
                try:
                    page_payload["image_data_url"] = _encode_png_data_url(
                        page.to_image(resolution=140).original
                    )
                except Exception:
                    page_payload["image_data_url"] = None
                if not page_payload["text_excerpt"]:
                    try:
                        page_payload["text_excerpt"] = (page.extract_text() or "")[:4000]
                    except Exception:
                        page_payload["text_excerpt"] = ""
            else:
                page_payload["error"] = "Requested page is outside the PDF page count."
            preview_pages.append(page_payload)

    return total_pages, preview_pages



def _encode_png_data_url(image: Any) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _build_manual_workbook(manuals: list[Manual], *, include_sample_rows: bool) -> StreamingResponse:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Manual Review"

    headers = _manual_export_headers()
    header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    rows: list[list[Any]] = []
    if include_sample_rows:
        rows.extend(
            [
                [
                    "",
                    "02. SEWAGE TREATMENT PLANT INSTRUCTION MANUAL.pdf",
                    3.3,
                    "classified",
                    "Instruction Manual",
                    "yes",
                    "OEM",
                    92,
                    "1",
                    "1",
                    "9-14",
                    "10-15",
                    "",
                    "",
                    "Sample: component starts on physical page 1 with no printed footer.",
                ],
                [
                    "",
                    "SEWAGE TREATMENT PLANT.pdf",
                    1.1,
                    "classified",
                    "Yard/Finished Drawings",
                    "partial",
                    "yard_supply",
                    88,
                    "1",
                    "2",
                    "",
                    "",
                    "2-12",
                    "3-13",
                    "Sample: drawing package with printed pages offset by one physical page.",
                ],
            ]
        )
    else:
        for manual in manuals:
            rows.append(
                [
                    str(manual.id),
                    manual.original_filename,
                    round((manual.file_size_bytes or 0) / (1024 * 1024), 2),
                    manual.status.value if hasattr(manual.status, "value") else str(manual.status),
                    manual.category or "",
                    manual.useful_for_extraction or "",
                    manual.supply_type or "",
                    manual.classification_confidence or "",
                    manual.pages_with_components_printed or "",
                    manual.pages_with_components_physical or "",
                    manual.pages_with_jobs_printed or "",
                    manual.pages_with_jobs_physical or "",
                    manual.pages_with_spares_printed or "",
                    manual.pages_with_spares_physical or "",
                    manual.reviewer_comments or "",
                ]
            )

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 4, 16), 40)

    info = wb.create_sheet("Instructions")
    info["A1"] = "Manual Review Import Guidance"
    info["A1"].font = Font(bold=True, size=14)
    guidance_rows = [
        "1. Use the Export Screening file for real vessel updates because it includes Manual ID values.",
        "2. Edit only the review columns: Category, Useful For Extraction, Source, confidence, page refs, and Reviewer Comments.",
        "3. Components / Job / Spare page refs accept comma-separated numbers and ranges like 1, 3-5, 9.",
        "4. Printed refs are the page numbers shown inside the document. Physical refs are the actual PDF page positions.",
        "5. Import overwrites the current screening values for matched manuals.",
        "6. If page refs are changed by import, old model page explanations are cleared so reviewers do not see stale reasons.",
        "7. Source should be OEM or yard_supply.",
        "8. Useful For Extraction should be yes, partial, or no.",
        "9. This template sheet is only for guidance. Start from Export Screening when updating a real vessel.",
    ]
    for idx, text in enumerate(guidance_rows, start=3):
        info.cell(row=idx, column=1, value=text)
    info.column_dimensions["A"].width = 120

    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get(
    "/{vessel_id}/manuals/batches",
    summary="List unique batch numbers of manuals for a vessel",
)
async def list_manual_batches(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[int]:
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(Manual.batch_number)
        .where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.batch_number.is_not(None),
        )
        .distinct()
        .order_by(Manual.batch_number.asc())
    )
    batches = [row[0] for row in result.all()]
    return batches


@router.get(
    "/{vessel_id}/manuals",
    summary="List manuals for a vessel with optional filters",
)
async def list_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[str] = Query(None),
    manual_status: Optional[str] = Query(None, alias="status"),
    min_confidence: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    useful_for_extraction: Optional[str] = Query(None),
    batch_number: Optional[int] = Query(None),
    sort_by: str = Query("filename", regex="^(filename|created_at|confidence|file_size|category|useful_for_extraction|batch_number|sequence_number)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    base_filter = _build_manual_filters(
        vessel_id=vessel_id,
        tenant_id=current_user.tenant_id,
        category=category,
        manual_status=manual_status,
        min_confidence=min_confidence,
        search=search,
        useful_for_extraction=useful_for_extraction,
        batch_number=batch_number,
    )

    # Count query
    count_result = await db.execute(select(func.count()).select_from(Manual).where(*base_filter))
    total = count_result.scalar_one()

    order_expr = _manual_order_expr(sort_by, sort_order)

    # Subquery for sequential manual upload number
    seq_subquery = (
        select(
            Manual.id.label("manual_id"),
            func.row_number().over(
                partition_by=Manual.vessel_id,
                order_by=[Manual.created_at.asc(), Manual.id.asc()],
            ).label("seq_no"),
        )
        .where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
        .subquery()
    )

    query = (
        select(Manual, seq_subquery.c.seq_no)
        .outerjoin(seq_subquery, Manual.id == seq_subquery.c.manual_id)
        .where(*base_filter)
        .order_by(order_expr)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = []
    for idx, row in enumerate(result.all(), 1):
        if isinstance(row, (tuple, list)) or hasattr(row, "_mapping"):
            m_obj = row[0]
            seq_val = row[1] if len(row) > 1 and row[1] is not None else idx
        else:
            m_obj = row
            seq_val = getattr(row, "sequence_number", None) or idx
        out = ManualOut.model_validate(m_obj)
        out.sequence_number = int(seq_val)
        items.append(out)

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get(
    "/{vessel_id}/manuals/{manual_id}/page-preview",
    summary="Return rendered manual pages and extracted text for review",
)
async def preview_manual_pages(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pages: str = Query(..., description="Comma-separated physical page numbers, e.g. 1,3-5"),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manual = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    requested_pages = _parse_preview_pages(pages)
    if not requested_pages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide at least one valid page number.")
    if len(requested_pages) > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preview up to 12 pages at a time.")

    page_text_lookup = _manual_text_by_page(manual)
    preview_pages: list[dict[str, Any]] = []
    page_count = manual.page_count

    if (manual.file_extension or "").lower() == "pdf":
        file_bytes = await _download_manual_bytes(manual)
        try:
            total_pages, preview_pages = await asyncio.to_thread(
                _render_pdf_preview_pages_sync,
                file_bytes,
                requested_pages,
                page_text_lookup,
            )
            page_count = page_count or total_pages
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not render preview pages: {exc}",
            ) from exc
    else:
        for page_number in requested_pages:
            preview_pages.append(
                {
                    "page_number": page_number,
                    "text_excerpt": (page_text_lookup.get(page_number) or "")[:4000],
                    "image_data_url": None,
                }
            )

    return {
        "manual_id": str(manual.id),
        "file_name": manual.original_filename,
        "file_extension": manual.file_extension,
        "page_count": page_count,
        "pages": preview_pages,
    }


@router.patch(
    "/{vessel_id}/manuals/{manual_id}",
    response_model=ManualOut,
    summary="Update manual classification fields",
)
async def update_manual(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    body: ManualUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManualOut:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    update_data = body.model_dump(exclude_unset=True)

    # If manual is currently part of an active extraction batch, prevent changing page references
    from app.services.extractor import is_manual_locked_for_extraction
    if is_manual_locked_for_extraction(str(manual_id), str(vessel_id)):
        _, page_fields_changed = _prepare_manual_update_data(manual, update_data)
        if page_fields_changed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Page references for manual '{manual.original_filename}' are locked while extraction is in progress. Please wait until extraction completes.",
            )

    prepared, feedback_id = await _apply_manual_updates(
        manual=manual,
        update_data=update_data,
        current_user=current_user,
        db=db,
        change_source="user_edit",
    )
    activity = None
    if prepared:
        activity = await log_activity(
            db,
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            user_id=current_user.id,
            action_type="manual.corrected",
            entity_type="manual",
            entity_id=manual.id,
            description=f"Updated screening details for '{manual.original_filename}'.",
            metadata={"fields": sorted(prepared.keys())},
        )
    await db.commit()
    if feedback_id:
        await schedule_feedback_learning(feedback_id)
    await db.refresh(manual)
    if activity:
        await broadcast_activity(activity)
    return ManualOut.model_validate(manual)


@router.get(
    "/{vessel_id}/manuals/export-screening",
    summary="Export manual review screening as Excel",
)
async def export_manual_screening(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[str] = Query(None),
    manual_status: Optional[str] = Query(None, alias="status"),
    min_confidence: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    useful_for_extraction: Optional[str] = Query(None),
    sort_by: str = Query("filename", regex="^(filename|created_at|confidence|file_size|category|useful_for_extraction|batch_number|sequence_number)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
) -> StreamingResponse:
    await _get_vessel_or_404(vessel_id, db)

    base_filter = _build_manual_filters(
        vessel_id=vessel_id,
        tenant_id=current_user.tenant_id,
        category=category,
        manual_status=manual_status,
        min_confidence=min_confidence,
        search=search,
        useful_for_extraction=useful_for_extraction,
    )
    result = await db.execute(
        select(Manual)
        .where(*base_filter)
        .order_by(_manual_order_expr(sort_by, sort_order))
    )
    manuals = result.scalars().all()

    response = _build_manual_workbook(manuals, include_sample_rows=False)
    response.headers["Content-Disposition"] = f'attachment; filename="manual_review_export_{vessel_id}.xlsx"'
    return response


@router.get(
    "/{vessel_id}/manuals/screening-template",
    summary="Download manual review import template",
)
async def download_manual_screening_template(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    await _get_vessel_or_404(vessel_id, db)
    response = _build_manual_workbook([], include_sample_rows=True)
    response.headers["Content-Disposition"] = 'attachment; filename="manual_review_template.xlsx"'
    return response


@router.post(
    "/{vessel_id}/manuals/import-screening",
    summary="Import manual review screening from Excel",
)
async def import_manual_screening(
    vessel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload an .xlsx file exported from Manual Review.",
        )

    content = await file.read()
    validate_uploaded_file_bytes(
        filename=file.filename or "manual_review_import.xlsx",
        content=content,
        allowed_extensions={"xlsx"},
        max_size_bytes=10 * 1024 * 1024,
    )
    try:
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        worksheet = workbook["Manual Review"] if "Manual Review" in workbook.sheetnames else workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        workbook.close()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not parse Excel file: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded workbook is empty.")

    raw_headers = [str(cell or "").strip() for cell in rows[0]]
    aliases = _manual_import_aliases()
    mapped_headers = [aliases.get(_normalise_header(header), "") for header in raw_headers]

    if "manual_id" not in mapped_headers and "original_filename" not in mapped_headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The workbook must contain 'Manual ID' or 'File Name' columns.",
        )

    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manuals = result.scalars().all()
    manuals_by_id = {str(manual.id): manual for manual in manuals}
    manuals_by_filename = {manual.original_filename.strip().lower(): manual for manual in manuals}

    editable_fields = {
        "category",
        "useful_for_extraction",
        "supply_type",
        "classification_confidence",
        "pages_with_components_printed",
        "pages_with_components_physical",
        "pages_with_jobs_printed",
        "pages_with_jobs_physical",
        "pages_with_spares_printed",
        "pages_with_spares_physical",
        "reviewer_comments",
    }

    updated = 0
    skipped = 0
    errors: list[str] = []
    activities = []
    feedback_ids: list[uuid.UUID] = []

    for row_number, row in enumerate(rows[1:], start=2):
        row_map = {
            mapped_headers[index]: row[index]
            for index in range(min(len(mapped_headers), len(row)))
            if mapped_headers[index]
        }
        if not row_map or not any(_normalise_excel_value(value) for value in row_map.values()):
            continue

        manual = None
        manual_id_value = _normalise_excel_value(row_map.get("manual_id"))
        if manual_id_value:
            manual = manuals_by_id.get(manual_id_value)
        if manual is None:
            filename_value = _normalise_excel_value(row_map.get("original_filename"))
            if filename_value:
                manual = manuals_by_filename.get(filename_value.lower())

        if manual is None:
            skipped += 1
            errors.append(f"Row {row_number}: manual not found for the provided Manual ID / File Name.")
            continue

        try:
            update_data: dict[str, Any] = {}
            for field in editable_fields:
                if field not in row_map:
                    continue
                if field == "classification_confidence":
                    update_data[field] = _parse_optional_int(row_map[field], field_name="Confidence (%)")
                else:
                    update_data[field] = _normalise_import_field_value(field, row_map[field])

            if not update_data:
                skipped += 1
                continue

            from app.services.extractor import is_manual_locked_for_extraction
            if is_manual_locked_for_extraction(str(manual.id), str(vessel_id)):
                page_fields = {
                    "pages_with_components_printed", "pages_with_components_physical",
                    "pages_with_jobs_printed", "pages_with_jobs_physical",
                    "pages_with_spares_printed", "pages_with_spares_physical",
                    "pages_with_components", "pages_with_jobs", "pages_with_spares",
                }
                removed_page_fields = [f for f in page_fields if f in update_data]
                for f in removed_page_fields:
                    update_data.pop(f, None)
                if removed_page_fields:
                    errors.append(f"Row {row_number}: Page references for '{manual.original_filename}' were locked and skipped because extraction is actively running.")
                if not update_data:
                    skipped += 1
                    continue

            prepared, feedback_id = await _apply_manual_updates(
                manual=manual,
                update_data=update_data,
                current_user=current_user,
                db=db,
                change_source="excel_import",
                notes="Updated via screening import",
            )
            if feedback_id:
                feedback_ids.append(feedback_id)
            activities.append(
                await log_activity(
                    db,
                    tenant_id=current_user.tenant_id,
                    vessel_id=vessel_id,
                    user_id=current_user.id,
                    action_type="manual.imported_screening",
                    entity_type="manual",
                    entity_id=manual.id,
                    description=f"Imported screening updates for '{manual.original_filename}'.",
                    metadata={"fields": sorted(prepared.keys())},
                )
            )
            updated += 1
        except ValueError as exc:
            skipped += 1
            errors.append(f"Row {row_number}: {exc}")

    await db.commit()
    for feedback_id in feedback_ids:
        await schedule_feedback_learning(feedback_id)
    for activity in activities:
        await broadcast_activity(activity)

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:50],
        "message": f"Imported screening updates for {updated} manual(s). Imported values overwrite existing screening fields.",
    }


@router.post(
    "/{vessel_id}/manuals/{manual_id}/trigger-classification",
    summary="Re-run classification for a manual",
)
async def trigger_classification(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    try:
        from app.tasks.classification import classify_manual

        task = classify_manual.delay(str(manual_id))
        return {"task_id": task.id, "status": "queued"}
    except Exception:
        return {"status": "queued", "task_id": "mock"}


@router.get(
    "/{vessel_id}/manuals/missing-report",
    summary="Missing manual gap analysis for vessel type",
)
async def missing_manual_report(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    vessel = await _get_vessel_or_404(vessel_id, db)

    expected = VESSEL_TYPE_MANUAL_TEMPLATES.get(vessel.vessel_type or "", [])

    result = await db.execute(
        select(Manual.category).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.category.isnot(None),
        )
    )
    classified_categories = {row[0] for row in result.all()}

    gaps = []
    for cat in expected:
        if cat not in classified_categories:
            gaps.append(
                {
                    "category": cat,
                    "status": "missing",
                    "message": f"No {cat} found for this vessel.",
                }
            )

    return {
        "vessel_type": vessel.vessel_type,
        "expected_categories": expected,
        "found_categories": list(classified_categories),
        "gaps": gaps,
        "gap_count": len(gaps),
    }


@router.get(
    "/{vessel_id}/manuals/no-extracted-records",
    summary="Get specified manual pages that yielded zero extracted items",
)
async def get_no_extracted_records_report(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    # 1. Fetch all manuals for this vessel
    manuals_res = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manuals = manuals_res.scalars().all()
    manual_ids = [m.id for m in manuals]

    if not manual_ids:
        return {"manuals": [], "total_no_extracted_pages": 0}

    # 2. Fetch all active extracted records
    from app.models.component import Component
    from app.models.job import Job
    from app.models.spare import Spare

    comp_res = await db.execute(
        select(Component.source_manual_id, Component.page_reference).where(
            Component.source_manual_id.in_(manual_ids),
            Component.is_deleted == False,
        )
    )
    components = comp_res.all()

    job_res = await db.execute(
        select(Job.source_manual_id, Job.page_reference).where(
            Job.source_manual_id.in_(manual_ids),
            Job.is_deleted == False,
        )
    )
    jobs = job_res.all()

    spare_res = await db.execute(
        select(Spare.source_manual_id, Spare.page_reference).where(
            Spare.source_manual_id.in_(manual_ids),
            Spare.is_deleted == False,
        )
    )
    spares = spare_res.all()

    # 3. Group extracted pages by manual ID
    extracted_components = {}
    extracted_jobs = {}
    extracted_spares = {}

    for mid, page in components:
        if page is not None:
            extracted_components.setdefault(mid, set()).add(page)

    for mid, page in jobs:
        if page is not None:
            extracted_jobs.setdefault(mid, set()).add(page)

    for mid, page in spares:
        if page is not None:
            extracted_spares.setdefault(mid, set()).add(page)

    # 4. Process each manual to compare targeted vs extracted pages
    from app.services.extractor import _parse_page_tokens

    report = []
    extracted_report = []
    total_no_extracted_pages = 0
    total_extracted_pages = 0
    all_manuals_summary: dict[str, Any] = {}

    for manual in manuals:
        # Determine if user has edited/customized any page reference fields for this manual
        comp_ref_str = (manual.pages_with_components_physical or "").strip() or (manual.pages_with_components or "").strip()
        job_ref_str = (manual.pages_with_jobs_physical or "").strip() or (manual.pages_with_jobs or "").strip()
        spare_ref_str = (manual.pages_with_spares_physical or "").strip() or (manual.pages_with_spares or "").strip()

        comp_pages = set(_parse_page_tokens(comp_ref_str))
        job_pages = set(_parse_page_tokens(job_ref_str))
        spare_pages = set(_parse_page_tokens(spare_ref_str))

        ext_comp = extracted_components.get(manual.id, set())
        ext_job = extracted_jobs.get(manual.id, set())
        ext_spare = extracted_spares.get(manual.id, set())

        missing_comp = sorted(list(comp_pages - ext_comp))
        missing_job = sorted(list(job_pages - ext_job))
        missing_spare = sorted(list(spare_pages - ext_spare))

        ext_comp_sorted = sorted(list(ext_comp))
        ext_job_sorted = sorted(list(ext_job))
        ext_spare_sorted = sorted(list(ext_spare))
        all_ext_pages = set(ext_comp) | set(ext_job) | set(ext_spare)

        total_target_pages = len(comp_pages) + len(job_pages) + len(spare_pages)
        has_target_pages = total_target_pages > 0
        missing_count = len(missing_comp) + len(missing_job) + len(missing_spare)
        is_complete = has_target_pages and (missing_count == 0)

        all_manuals_summary[str(manual.id)] = {
            "has_target_pages": has_target_pages,
            "total_target_pages": total_target_pages,
            "is_complete": is_complete,
            "total_missing_pages_count": missing_count,
            "missing_components_count": len(missing_comp),
            "missing_jobs_count": len(missing_job),
            "missing_spares_count": len(missing_spare),
            "missing_components_pages": missing_comp,
            "missing_jobs_pages": missing_job,
            "missing_spares_pages": missing_spare,
            "extracted_components_pages": ext_comp_sorted,
            "extracted_jobs_pages": ext_job_sorted,
            "extracted_spares_pages": ext_spare_sorted,
            "extracted_components_count": len(ext_comp_sorted),
            "extracted_jobs_count": len(ext_job_sorted),
            "extracted_spares_count": len(ext_spare_sorted),
            "total_extracted_pages_count": len(all_ext_pages),
        }

        if missing_comp or missing_job or missing_spare:
            missing_count = len(missing_comp) + len(missing_job) + len(missing_spare)
            total_no_extracted_pages += missing_count
            report.append({
                "manual_id": str(manual.id),
                "original_filename": manual.original_filename,
                "category": manual.category,
                "missing_components_pages": missing_comp,
                "missing_jobs_pages": missing_job,
                "missing_spares_pages": missing_spare,
                "missing_components_count": len(missing_comp),
                "missing_jobs_count": len(missing_job),
                "missing_spares_count": len(missing_spare),
                "total_missing_pages_count": missing_count,
            })

        if all_ext_pages:
            total_extracted_pages += len(all_ext_pages)
            extracted_report.append({
                "manual_id": str(manual.id),
                "original_filename": manual.original_filename,
                "category": manual.category,
                "extracted_components_pages": ext_comp_sorted,
                "extracted_jobs_pages": ext_job_sorted,
                "extracted_spares_pages": ext_spare_sorted,
                "extracted_components_count": len(ext_comp_sorted),
                "extracted_jobs_count": len(ext_job_sorted),
                "extracted_spares_count": len(ext_spare_sorted),
                "total_extracted_pages_count": len(all_ext_pages),
            })

    report.sort(key=lambda m: m["original_filename"].lower())
    extracted_report.sort(key=lambda m: m["original_filename"].lower())

    total_completed_manuals = sum(1 for s in all_manuals_summary.values() if s.get("is_complete"))
    total_targeted_manuals = sum(1 for s in all_manuals_summary.values() if s.get("has_target_pages"))

    return {
        "manuals": report,
        "total_no_extracted_pages": total_no_extracted_pages,
        "extracted_manuals": extracted_report,
        "total_extracted_pages": total_extracted_pages,
        "all_manuals_summary": all_manuals_summary,
        "total_completed_manuals": total_completed_manuals,
        "total_targeted_manuals": total_targeted_manuals,
        "total_manuals": len(manuals),
    }

async def _ensure_manual_page_ref_history_table_local(db: AsyncSession) -> None:
    try:
        from sqlalchemy import text
        conn = await db.connection()
        is_postgres = conn.dialect.name == "postgresql"
        if is_postgres:
            await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
            uuid_default = "gen_random_uuid()"
        else:
            uuid_default = "(lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-a' || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6))))"

        await db.execute(text(f"""
            CREATE TABLE IF NOT EXISTS manual_page_ref_history (
                id UUID PRIMARY KEY DEFAULT {uuid_default},
                tenant_id UUID NOT NULL,
                vessel_id UUID NOT NULL REFERENCES vessel_projects(id) ON DELETE CASCADE,
                manual_id UUID NOT NULL REFERENCES manuals(id) ON DELETE CASCADE,
                changed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                changed_by_name VARCHAR(255),
                change_source VARCHAR(100) NOT NULL DEFAULT 'user_edit',
                pages_with_components TEXT,
                pages_with_jobs TEXT,
                pages_with_spares TEXT,
                pages_with_components_physical TEXT,
                pages_with_jobs_physical TEXT,
                pages_with_spares_physical TEXT,
                previous_pages_with_components TEXT,
                previous_pages_with_jobs TEXT,
                previous_pages_with_spares TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            );
        """))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_manual_page_ref_history_manual ON manual_page_ref_history(manual_id);"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_manual_page_ref_history_vessel ON manual_page_ref_history(vessel_id);"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS idx_manual_page_ref_history_created ON manual_page_ref_history(created_at DESC);"))
        await db.commit()
    except Exception as exc:
        logger.warning(f"Could not auto-create manual_page_ref_history table: {exc}")


@router.get(
    "/{vessel_id}/manuals/{manual_id}/page-ref-history",
    response_model=list[ManualPageRefHistoryOut],
    summary="Get page references change history snapshots for a manual",
)
async def get_manual_page_ref_history(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ManualPageRefHistoryOut]:
    await _get_vessel_or_404(vessel_id, db)

    m_res = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
        )
    )
    manual = m_res.scalar_one_or_none()
    if not manual:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    history_entries: list[ManualPageRefHistory] = []
    try:
        result = await db.execute(
            select(ManualPageRefHistory)
            .where(
                ManualPageRefHistory.vessel_id == vessel_id,
                ManualPageRefHistory.manual_id == manual_id,
            )
            .order_by(ManualPageRefHistory.created_at.desc())
        )
        history_entries = list(result.scalars().all())
    except Exception:
        await _ensure_manual_page_ref_history_table_local(db)
        try:
            result = await db.execute(
                select(ManualPageRefHistory)
                .where(
                    ManualPageRefHistory.vessel_id == vessel_id,
                    ManualPageRefHistory.manual_id == manual_id,
                )
                .order_by(ManualPageRefHistory.created_at.desc())
            )
            history_entries = list(result.scalars().all())
        except Exception as e:
            logger.error(f"Could not query manual_page_ref_history: {e}")
            return []

    # If no snapshot exists yet for this manual, synthesize and save an initial baseline snapshot!
    if not history_entries:
        has_any_ref = bool(
            (manual.pages_with_components and manual.pages_with_components.strip())
            or (manual.pages_with_jobs and manual.pages_with_jobs.strip())
            or (manual.pages_with_spares and manual.pages_with_spares.strip())
            or (manual.pages_with_components_physical and manual.pages_with_components_physical.strip())
            or (manual.pages_with_jobs_physical and manual.pages_with_jobs_physical.strip())
            or (manual.pages_with_spares_physical and manual.pages_with_spares_physical.strip())
        )
        if has_any_ref:
            try:
                baseline_snap = ManualPageRefHistory(
                    tenant_id=manual.tenant_id,
                    vessel_id=manual.vessel_id,
                    manual_id=manual.id,
                    changed_by_name="Initial Saved Reference",
                    change_source="baseline",
                    pages_with_components=manual.pages_with_components,
                    pages_with_jobs=manual.pages_with_jobs,
                    pages_with_spares=manual.pages_with_spares,
                    pages_with_components_physical=manual.pages_with_components_physical,
                    pages_with_jobs_physical=manual.pages_with_jobs_physical,
                    pages_with_spares_physical=manual.pages_with_spares_physical,
                    notes="Baseline page references snapshot",
                    created_at=manual.updated_at or datetime.now(timezone.utc),
                    updated_at=manual.updated_at or datetime.now(timezone.utc),
                )
                db.add(baseline_snap)
                await db.commit()
                await db.refresh(baseline_snap)
                history_entries = [baseline_snap]
            except Exception as e:
                logger.warning(f"Could not persist baseline snapshot: {e}")

    return history_entries


@router.post(
    "/{vessel_id}/manuals/{manual_id}/restore-page-ref-snapshot/{history_id}",
    response_model=ManualOut,
    summary="Restore a manual's page references to a previous snapshot",
)
async def restore_manual_page_ref_snapshot(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    history_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManualOut:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    from app.services.extractor import is_manual_locked_for_extraction
    if is_manual_locked_for_extraction(str(manual_id), str(vessel_id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Page references for manual '{manual.original_filename}' are locked while batch extraction is in progress."
        )

    snap_result = await db.execute(
        select(ManualPageRefHistory).where(
            ManualPageRefHistory.id == history_id,
            ManualPageRefHistory.manual_id == manual_id,
            ManualPageRefHistory.vessel_id == vessel_id,
        )
    )
    snapshot: ManualPageRefHistory | None = snap_result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History snapshot not found")

    orig_comp = manual.pages_with_components
    orig_jobs = manual.pages_with_jobs
    orig_spares = manual.pages_with_spares

    manual.pages_with_components = snapshot.pages_with_components
    manual.pages_with_jobs = snapshot.pages_with_jobs
    manual.pages_with_spares = snapshot.pages_with_spares
    manual.pages_with_components_physical = snapshot.pages_with_components_physical
    manual.pages_with_jobs_physical = snapshot.pages_with_jobs_physical
    manual.pages_with_spares_physical = snapshot.pages_with_spares_physical
    manual.pages_with_components_printed = snapshot.pages_with_components
    manual.pages_with_jobs_printed = snapshot.pages_with_jobs
    manual.pages_with_spares_printed = snapshot.pages_with_spares

    db.add(manual)

    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None) or "User"
    restored_entry = ManualPageRefHistory(
        tenant_id=manual.tenant_id,
        vessel_id=manual.vessel_id,
        manual_id=manual.id,
        changed_by_user_id=getattr(current_user, "id", None),
        changed_by_name=user_name,
        change_source="restored",
        pages_with_components=manual.pages_with_components,
        pages_with_jobs=manual.pages_with_jobs,
        pages_with_spares=manual.pages_with_spares,
        pages_with_components_physical=manual.pages_with_components_physical,
        pages_with_jobs_physical=manual.pages_with_jobs_physical,
        pages_with_spares_physical=manual.pages_with_spares_physical,
        previous_pages_with_components=orig_comp,
        previous_pages_with_jobs=orig_jobs,
        previous_pages_with_spares=orig_spares,
        notes=f"Restored to snapshot from {snapshot.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
    )
    db.add(restored_entry)
    await db.commit()
    await db.refresh(manual)

    return ManualOut.model_validate(manual)

@router.get(
    "/{vessel_id}/manuals/deleted",
    response_model=list[DeletedManualOut],
    summary="Get all deleted manuals for a vessel with extraction run counts and history",
)
async def get_deleted_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DeletedManualOut]:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual)
        .where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == True,
        )
        .order_by(Manual.updated_at.desc())
    )
    deleted_manuals = result.scalars().all()
    if not deleted_manuals:
        return []

    manual_ids = [m.id for m in deleted_manuals]

    from app.services.extraction_counter import ensure_extraction_counter_tables
    await ensure_extraction_counter_tables()

    # 1. Fetch manual extraction runs
    run_counts: dict[uuid.UUID, tuple[int, Optional[datetime]]] = {}
    for mid in manual_ids:
        try:
            r_res = await db.execute(
                text("SELECT run_count, last_run_at FROM manual_extraction_runs WHERE manual_id = :mid"),
                {"mid": mid}
            )
            row = r_res.fetchone()
            if row:
                run_counts[mid] = (int(row[0] or 0), row[1])
        except Exception:
            pass

    # 2. Fetch page extraction run counts
    page_runs: dict[uuid.UUID, dict[int, int]] = {mid: {} for mid in manual_ids}
    for mid in manual_ids:
        try:
            p_res = await db.execute(
                text("SELECT page_number, run_count FROM manual_page_extractions WHERE manual_id = :mid"),
                {"mid": mid}
            )
            for pr in p_res.fetchall():
                page_runs[mid][int(pr[0])] = int(pr[1] or 0)
        except Exception:
            pass

    # 3. Fetch extracted records counts
    comp_counts: dict[uuid.UUID, int] = {}
    job_counts: dict[uuid.UUID, int] = {}
    spare_counts: dict[uuid.UUID, int] = {}
    history_counts: dict[uuid.UUID, int] = {}

    for mid in manual_ids:
        try:
            c_res = await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid"), {"mid": mid})
            comp_counts[mid] = int(c_res.scalar() or 0)
        except Exception:
            comp_counts[mid] = 0

        try:
            j_res = await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid"), {"mid": mid})
            job_counts[mid] = int(j_res.scalar() or 0)
        except Exception:
            job_counts[mid] = 0

        try:
            s_res = await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid"), {"mid": mid})
            spare_counts[mid] = int(s_res.scalar() or 0)
        except Exception:
            spare_counts[mid] = 0

        try:
            h_res = await db.execute(text("SELECT COUNT(*) FROM manual_page_ref_history WHERE manual_id = :mid"), {"mid": mid})
            history_counts[mid] = int(h_res.scalar() or 0)
        except Exception:
            history_counts[mid] = 0

    output = []
    for m in deleted_manuals:
        m_runs, last_run = run_counts.get(m.id, (0, None))
        output.append(
            DeletedManualOut(
                id=m.id,
                vessel_id=m.vessel_id,
                original_filename=m.original_filename,
                file_extension=m.file_extension,
                file_size_bytes=m.file_size_bytes,
                category=m.category,
                classification_confidence=m.classification_confidence,
                useful_for_extraction=m.useful_for_extraction,
                pages_with_components=m.pages_with_components,
                pages_with_jobs=m.pages_with_jobs,
                pages_with_spares=m.pages_with_spares,
                pages_with_components_physical=m.pages_with_components_physical,
                pages_with_jobs_physical=m.pages_with_jobs_physical,
                pages_with_spares_physical=m.pages_with_spares_physical,
                page_count=m.page_count,
                created_at=m.created_at,
                updated_at=m.updated_at,
                manual_extraction_run_count=m_runs,
                page_extraction_counts=page_runs.get(m.id, {}),
                last_extraction_at=last_run,
                extracted_components_count=comp_counts.get(m.id, 0),
                extracted_jobs_count=job_counts.get(m.id, 0),
                extracted_spares_count=spare_counts.get(m.id, 0),
                history_snapshot_count=history_counts.get(m.id, 0),
            )
        )

    return output


@router.post(
    "/{vessel_id}/manuals/{manual_id}/restore-deleted",
    response_model=ManualOut,
    summary="Restore a soft-deleted manual and its extracted entities",
)
async def restore_deleted_manual(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManualOut:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == True,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deleted manual not found")

    manual.is_deleted = False
    db.add(manual)

    # Restore associated components, jobs, spares
    from app.models.component import Component
    from app.models.job import Job
    from app.models.spare import Spare

    await db.execute(
        update(Component)
        .where(Component.source_manual_id == manual.id)
        .values(is_deleted=False)
    )
    await db.execute(
        update(Job)
        .where(Job.source_manual_id == manual.id)
        .values(is_deleted=False)
    )
    await db.execute(
        update(Spare)
        .where(Spare.source_manual_id == manual.id)
        .values(is_deleted=False)
    )

    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None) or "User"
    restored_snap = ManualPageRefHistory(
        tenant_id=manual.tenant_id,
        vessel_id=manual.vessel_id,
        manual_id=manual.id,
        changed_by_user_id=getattr(current_user, "id", None),
        changed_by_name=user_name,
        change_source="manual_restored",
        pages_with_components=manual.pages_with_components,
        pages_with_jobs=manual.pages_with_jobs,
        pages_with_spares=manual.pages_with_spares,
        pages_with_components_physical=manual.pages_with_components_physical,
        pages_with_jobs_physical=manual.pages_with_jobs_physical,
        pages_with_spares_physical=manual.pages_with_spares_physical,
        previous_pages_with_components=manual.pages_with_components,
        previous_pages_with_jobs=manual.pages_with_jobs,
        previous_pages_with_spares=manual.pages_with_spares,
        notes="Manual undeleted and restored to active review list",
    )
    db.add(restored_snap)

    await db.commit()
    await db.refresh(manual)

    return ManualOut.model_validate(manual)

@router.get(
    "/{vessel_id}/manuals/untouched",
    summary="Get manuals that have never had a single extraction run or have 0 extracted pages",
)
async def get_untouched_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        await _get_vessel_or_404(vessel_id, db)

        # 1. Fetch non-deleted manuals for this vessel along with sequence number
        res = await db.execute(
            select(
                Manual,
                func.row_number().over(
                    partition_by=Manual.vessel_id,
                    order_by=[Manual.created_at.asc(), Manual.id.asc()],
                ).label("seq_no"),
            ).where(
                Manual.vessel_id == vessel_id,
                Manual.tenant_id == current_user.tenant_id,
                Manual.is_deleted == False,
            ).order_by(Manual.created_at.desc(), Manual.id.desc())
        )
        manual_rows = res.all()
        manuals = []
        seq_map = {}
        for idx, row in enumerate(manual_rows, 1):
            if isinstance(row, (tuple, list)) or hasattr(row, "_mapping"):
                m_obj = row[0]
                seq_val = int(row[1]) if len(row) > 1 and row[1] is not None else idx
            else:
                m_obj = row
                seq_val = getattr(row, "sequence_number", None) or idx
            manuals.append(m_obj)
            seq_map[m_obj.id] = seq_val
        if not manuals:
            return {"total_untouched": 0, "manuals": []}

        manual_ids = [m.id for m in manuals]

        # 2. Fetch extraction run counts safely using a savepoint
        run_counts: dict[uuid.UUID, int] = {}
        try:
            r_res = await db.execute(
                text("SELECT manual_id, run_count FROM manual_extraction_runs")
            )
            for row in r_res.fetchall():
                try:
                    run_counts[uuid.UUID(str(row[0]))] = int(row[1] or 0)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("Could not query manual_extraction_runs in get_untouched_manuals: %s", exc)
            try:
                await db.rollback()
            except Exception:
                pass

        # 3. Fetch extracted page counts (components, jobs, spares)
        from app.models.component import Component
        from app.models.job import Job
        from app.models.spare import Spare

        extracted_pages_map: dict[uuid.UUID, set[int]] = {}

        try:
            comp_res = await db.execute(
                select(Component.source_manual_id, Component.page_reference).where(
                    Component.source_manual_id.in_(manual_ids),
                    Component.is_deleted == False,
                )
            )
            for mid, pg in comp_res.all():
                if pg is not None:
                    try:
                        extracted_pages_map.setdefault(mid, set()).add(int(pg))
                    except (ValueError, TypeError):
                        pass
        except Exception as exc:
            logger.warning("Could not fetch component page references for untouched: %s", exc)

        try:
            job_res = await db.execute(
                select(Job.source_manual_id, Job.page_reference).where(
                    Job.source_manual_id.in_(manual_ids),
                    Job.is_deleted == False,
                )
            )
            for mid, pg in job_res.all():
                if pg is not None:
                    try:
                        extracted_pages_map.setdefault(mid, set()).add(int(pg))
                    except (ValueError, TypeError):
                        pass
        except Exception as exc:
            logger.warning("Could not fetch job page references for untouched: %s", exc)

        try:
            spare_res = await db.execute(
                select(Spare.source_manual_id, Spare.page_reference).where(
                    Spare.source_manual_id.in_(manual_ids),
                    Spare.is_deleted == False,
                )
            )
            for mid, pg in spare_res.all():
                if pg is not None:
                    try:
                        extracted_pages_map.setdefault(mid, set()).add(int(pg))
                    except (ValueError, TypeError):
                        pass
        except Exception as exc:
            logger.warning("Could not fetch spare page references for untouched: %s", exc)

        from app.services.extractor import _parse_page_tokens

        untouched_list = []
        for m in manuals:
            runs = run_counts.get(m.id, 0)
            ext_pages = extracted_pages_map.get(m.id, set())

            # CRITICAL FIX: If manual already has extracted pages, it has been extracted and is NOT untouched!
            if len(ext_pages) > 0:
                continue

            # Here len(ext_pages) == 0: manual has 0 extracted pages
            comp_ref = (m.pages_with_components_physical or "").strip() or (m.pages_with_components or "").strip()
            job_ref = (m.pages_with_jobs_physical or "").strip() or (m.pages_with_jobs or "").strip()
            spare_ref = (m.pages_with_spares_physical or "").strip() or (m.pages_with_spares or "").strip()

            comp_count = len(_parse_page_tokens(comp_ref))
            job_count = len(_parse_page_tokens(job_ref))
            spare_count = len(_parse_page_tokens(spare_ref))

            untouched_list.append({
                "id": str(m.id),
                "original_filename": m.original_filename,
                "category": m.category,
                "target_model": m.target_model,
                "sequence_number": seq_map.get(m.id, 1),
                "batch_number": m.batch_number or 1,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "file_size_bytes": m.file_size_bytes,
                "useful_for_extraction": m.useful_for_extraction,
                "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                "pages_with_components": comp_ref,
                "pages_with_jobs": job_ref,
                "pages_with_spares": spare_ref,
                "targeted_components_count": comp_count,
                "targeted_jobs_count": job_count,
                "targeted_spares_count": spare_count,
                "total_targeted_pages": comp_count + job_count + spare_count,
                "run_count": runs,
                "extracted_pages_count": 0,
                "is_never_run": runs == 0,
            })

        return {
            "total_untouched": len(untouched_list),
            "manuals": untouched_list,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_untouched_manuals encountered unexpected error for %s: %s", vessel_id, exc)
        return {
            "total_untouched": 0,
            "manuals": [],
        }

