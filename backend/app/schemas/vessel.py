from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl

from app.models.vessel import VesselStatus


class VesselCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    imo_number: str = Field(..., min_length=7, max_length=20, description="IMO number (e.g. IMO9999999)")
    vessel_type: str = Field(..., min_length=1, max_length=100)
    sharepoint_folder_url: Optional[str] = Field(None, max_length=2048)
    shipyard: Optional[str] = Field(None, max_length=255)


class VesselUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    vessel_type: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[VesselStatus] = None
    sharepoint_folder_url: Optional[str] = Field(None, max_length=2048)
    export_schema_id: Optional[uuid.UUID] = None
    shipyard: Optional[str] = Field(None, max_length=255)


class VesselUserAssignment(BaseModel):
    user_id: uuid.UUID
    role: str = Field(..., min_length=1, max_length=50)


class VesselResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    imo_number: str
    vessel_type: str
    status: VesselStatus
    sharepoint_folder_url: Optional[str] = None
    shipyard: Optional[str] = None
    created_by: uuid.UUID
    export_schema_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class VesselListResponse(BaseModel):
    items: list[VesselResponse]
    total: int
    page: int
    page_size: int
    pages: int
