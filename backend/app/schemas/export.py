from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.models.export import ExportVersionStatus


class ExportSchemaOut(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    sheet_mappings: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportVersionOut(BaseModel):
    id: uuid.UUID
    vessel_id: uuid.UUID
    export_schema_id: Optional[uuid.UUID] = None
    version_number: int
    blob_storage_key: Optional[str] = None
    generated_by: uuid.UUID
    row_counts: Optional[Dict[str, Any]] = None
    status: ExportVersionStatus
    created_at: datetime

    model_config = {"from_attributes": True}
