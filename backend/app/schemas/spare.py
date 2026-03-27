from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.component import QCStatus
from app.models.spare import ExtractionMethod


class SpareOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    component_id: Optional[uuid.UUID] = None
    part_name: str
    part_number: Optional[str] = None
    drawing_number: Optional[str] = None
    drawing_position: Optional[str] = None
    specification: Optional[str] = None
    spare_maker: Optional[str] = None
    spare_model: Optional[str] = None
    machinery_maker: Optional[str] = None
    machinery_model: Optional[str] = None
    source_manual_id: Optional[uuid.UUID] = None
    page_reference: Optional[int] = None
    extraction_method: ExtractionMethod
    is_critical: bool
    qc_status: QCStatus
    confidence_score: Optional[int] = None
    is_duplicate: bool
    merged_into_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SpareCreate(BaseModel):
    part_name: str
    part_number: Optional[str] = None
    drawing_number: Optional[str] = None
    drawing_position: Optional[str] = None
    specification: Optional[str] = None
    spare_maker: Optional[str] = None
    component_id: Optional[uuid.UUID] = None
    is_critical: bool = False


class SpareUpdate(BaseModel):
    part_name: Optional[str] = None
    part_number: Optional[str] = None
    drawing_number: Optional[str] = None
    drawing_position: Optional[str] = None
    specification: Optional[str] = None
    spare_maker: Optional[str] = None
    spare_model: Optional[str] = None
    component_id: Optional[uuid.UUID] = None
    is_critical: Optional[bool] = None
    qc_status: Optional[QCStatus] = None
