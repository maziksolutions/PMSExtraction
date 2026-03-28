from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.ingestion import (
    IngestionSessionStatus,
    ManualStatus,
    VirusScanStatus,
)


# ---------------------------------------------------------------------------
# SharePoint file preview
# ---------------------------------------------------------------------------


class SharePointFileInfo(BaseModel):
    name: str
    path: str
    size_bytes: int
    extension: str
    selected: bool = True


class SharePointFolderPreview(BaseModel):
    folder_url: str
    files: List[SharePointFileInfo]


# ---------------------------------------------------------------------------
# Manual schemas
# ---------------------------------------------------------------------------


class ManualResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    vessel_id: uuid.UUID
    original_filename: str
    file_extension: str
    file_size_bytes: int
    sharepoint_path: Optional[str]
    blob_storage_key: Optional[str]
    status: ManualStatus
    error_message: Optional[str]
    retry_count: int
    detected_language: Optional[str]
    translated: bool
    virus_scan_status: VirusScanStatus
    uploaded_by: uuid.UUID
    category: Optional[str]
    classification_confidence: Optional[int]
    useful_for_extraction: Optional[str]
    pages_with_components: Optional[str]
    pages_with_jobs: Optional[str]
    pages_with_spares: Optional[str]
    reviewer_comments: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    model_config = {"from_attributes": True}


class ManualUpdate(BaseModel):
    category: Optional[str] = None
    useful_for_extraction: Optional[str] = Field(
        default=None,
        description="yes, reference, or no",
    )
    pages_with_components: Optional[str] = None
    pages_with_jobs: Optional[str] = None
    pages_with_spares: Optional[str] = None
    reviewer_comments: Optional[str] = None


# ---------------------------------------------------------------------------
# Ingestion session schemas
# ---------------------------------------------------------------------------


class IngestionSessionCreate(BaseModel):
    vessel_id: uuid.UUID
    sharepoint_folder_url: str = Field(..., min_length=1, max_length=2048)


class IngestionSessionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    vessel_id: uuid.UUID
    sharepoint_folder_url: str
    total_files: int
    downloaded_files: int
    failed_files: int
    status: IngestionSessionStatus
    started_by: uuid.UUID
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    manuals: List[ManualResponse] = []

    model_config = {"from_attributes": True}


class SessionProgressResponse(BaseModel):
    session_id: uuid.UUID
    status: IngestionSessionStatus
    total_files: int
    downloaded_files: int
    failed_files: int
    percent_complete: float
    manuals: List[ManualResponse] = []


# ---------------------------------------------------------------------------
# Sprint 2 – new schemas used by ingestion.py router
# ---------------------------------------------------------------------------


class SharePointAuthResponse(BaseModel):
    auth_url: str
    vessel_id: uuid.UUID


class SharePointFileListRequest(BaseModel):
    folder_url: Optional[str] = None


class SharePointFileListResponse(BaseModel):
    files: List[Dict[str, Any]]
    total: int


class IngestionStartRequest(BaseModel):
    folder_url: str
    selected_files: List[Dict[str, Any]]


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
    # F-09 duplicate detection
    sha256_hash: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestionSessionOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    sharepoint_folder_url: str
    total_files: int
    downloaded_files: int
    failed_files: int
    status: IngestionSessionStatus
    started_by: uuid.UUID
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
