import re
from typing import Any, Optional
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.component import QCStatus
from app.models.job import FrequencyType


def _parse_frequency_lowest(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except (ValueError, TypeError, OverflowError):
            return None
    s = str(v).strip()
    if not s or s.lower() in ("none", "null", "n/a", "-"):
        return None
    range_match = re.search(r"(\d+)\s*(?:[-~–—/]|to)\s*(\d+)", s, re.I)
    if range_match:
        n1 = int(range_match.group(1))
        n2 = int(range_match.group(2))
        return min(n1, n2)
    num_match = re.search(r"\b\d+\b", s)
    if num_match:
        try:
            return int(num_match.group(0))
        except (ValueError, TypeError):
            return None
    return None


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

    @field_validator("frequency", mode="before")
    @classmethod
    def parse_frequency_lowest(cls, v: Any) -> Optional[int]:
        return _parse_frequency_lowest(v)


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

    @field_validator("frequency", mode="before")
    @classmethod
    def parse_frequency_lowest(cls, v: Any) -> Optional[int]:
        return _parse_frequency_lowest(v)

