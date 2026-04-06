from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.component import QCStatus
from app.models.job import FrequencyType


class JobOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    component_id: Optional[uuid.UUID] = None
    job_name: str
    job_code: Optional[str] = None
    job_description: Optional[str] = None
    safety_precaution: Optional[str] = None
    tools_required: Optional[str] = None
    performing_rank: Optional[str] = None
    verifying_rank: Optional[str] = None
    frequency: Optional[int] = None
    frequency_type: Optional[FrequencyType] = None
    initial_due: Optional[int] = None
    initial_frequency_type: Optional[FrequencyType] = None
    cms_id: Optional[str] = None
    page_reference: Optional[int] = None
    pdf_reference: Optional[str] = None
    source_reference: Optional[str] = None
    is_critical: bool
    qc_status: QCStatus
    is_unmapped: bool
    source_manual_id: Optional[uuid.UUID] = None
    confidence_score: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    job_name: str
    job_code: Optional[str] = None
    job_description: Optional[str] = None
    safety_precaution: Optional[str] = None
    tools_required: Optional[str] = None
    performing_rank: Optional[str] = None
    verifying_rank: Optional[str] = None
    frequency: Optional[int] = None
    frequency_type: Optional[FrequencyType] = None
    initial_due: Optional[int] = None
    initial_frequency_type: Optional[FrequencyType] = None
    cms_id: Optional[str] = None
    is_critical: bool = False
    component_id: Optional[uuid.UUID] = None
    qc_status: Optional[QCStatus] = None
    page_reference: Optional[int] = None
    pdf_reference: Optional[str] = None
    source_reference: Optional[str] = None
    source_manual_id: Optional[uuid.UUID] = None


class JobUpdate(BaseModel):
    job_name: Optional[str] = None
    job_code: Optional[str] = None
    job_description: Optional[str] = None
    safety_precaution: Optional[str] = None
    tools_required: Optional[str] = None
    performing_rank: Optional[str] = None
    verifying_rank: Optional[str] = None
    frequency: Optional[int] = None
    frequency_type: Optional[FrequencyType] = None
    initial_due: Optional[int] = None
    initial_frequency_type: Optional[FrequencyType] = None
    cms_id: Optional[str] = None
    is_critical: Optional[bool] = None
    qc_status: Optional[QCStatus] = None
    component_id: Optional[uuid.UUID] = None
    page_reference: Optional[int] = None
    pdf_reference: Optional[str] = None
    source_reference: Optional[str] = None
