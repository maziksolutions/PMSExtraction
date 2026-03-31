from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.ingestion import ManualStatus, VirusScanStatus


class ManualOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    original_filename: str
    file_extension: str
    file_size_bytes: int
    sharepoint_path: Optional[str] = None
    blob_storage_key: Optional[str] = None
    status: ManualStatus
    error_message: Optional[str] = None
    retry_count: int
    detected_language: Optional[str] = None
    translated: bool
    virus_scan_status: VirusScanStatus
    category: Optional[str] = None
    classification_confidence: Optional[int] = None
    useful_for_extraction: Optional[str] = None
    pages_with_components: Optional[str] = None
    pages_with_jobs: Optional[str] = None
    pages_with_spares: Optional[str] = None
    reviewer_comments: Optional[str] = None
    supply_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManualUpdate(BaseModel):
    category: Optional[str] = None
    useful_for_extraction: Optional[str] = None
    pages_with_components: Optional[str] = None
    pages_with_jobs: Optional[str] = None
    pages_with_spares: Optional[str] = None
    reviewer_comments: Optional[str] = None
    supply_type: Optional[str] = None
    classification_confidence: Optional[int] = None
