from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.component import QCStatus


class ComponentOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    group1: str
    group2: str
    main_machinery: str
    component_name: str
    maker: Optional[str] = None
    model: Optional[str] = None
    specification: Optional[str] = None
    serial_number: Optional[str] = None
    source_manual_id: Optional[uuid.UUID] = None
    page_reference: Optional[int] = None
    confidence_score: Optional[int] = None
    is_critical: bool
    criticality: str = "non_critical"
    qc_status: QCStatus
    is_unmapped: bool
    extraction_notes: Optional[str] = None
    job_pages: Optional[str] = None
    spare_pages: Optional[str] = None
    pdf_reference: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComponentCreate(BaseModel):
    group1: str
    group2: str
    main_machinery: str
    component_name: str
    maker: Optional[str] = None
    model: Optional[str] = None
    specification: Optional[str] = None
    serial_number: Optional[str] = None
    is_critical: bool = False
    criticality: str = "non_critical"
    job_pages: Optional[str] = None
    spare_pages: Optional[str] = None
    pdf_reference: Optional[str] = None


class ComponentUpdate(BaseModel):
    group1: Optional[str] = None
    group2: Optional[str] = None
    main_machinery: Optional[str] = None
    component_name: Optional[str] = None
    maker: Optional[str] = None
    model: Optional[str] = None
    specification: Optional[str] = None
    serial_number: Optional[str] = None
    is_critical: Optional[bool] = None
    criticality: Optional[str] = None
    qc_status: Optional[QCStatus] = None
    extraction_notes: Optional[str] = None
    job_pages: Optional[str] = None
    spare_pages: Optional[str] = None
    pdf_reference: Optional[str] = None
