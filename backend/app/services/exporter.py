from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Known system fields mapped to Excel column headers
FIELD_MAPPINGS = {
    # Components
    "group1": "Group 1",
    "group2": "Group 2",
    "main_machinery": "Main Machinery",
    "component_name": "Component Name",
    "maker": "Maker",
    "model": "Model",
    "specification": "Specification",
    "serial_number": "Serial Number",
    "is_critical": "Critical",
    "qc_status": "QC Status",
    # Jobs
    "job_name": "Job Name",
    "job_code": "Job Code",
    "job_description": "Description",
    "safety_precaution": "Safety Precautions",
    "tools_required": "Tools Required",
    "performing_rank": "Performing Rank",
    "verifying_rank": "Verifying Rank",
    "frequency": "Frequency",
    "frequency_type": "Frequency Type",
    "cms_id": "CMS ID",
    # Spares
    "part_name": "Part Name",
    "part_number": "Part Number",
    "drawing_number": "Drawing Number",
    "drawing_position": "Drawing Position",
    "spare_maker": "Spare Maker",
    "extraction_method": "Extraction Method",
}


class ExportService:
    """Adapter-pattern export engine."""

    def serialize(
        self, vessel_id: str, export_schema: dict | None = None
    ) -> dict[str, Any]:
        """
        Build structured data dict for export.
        Returns {components: [...], jobs: [...], spares: [...], excluded: [...]}.
        Queries DB for all accepted records for the given vessel.
        """
        import uuid as _uuid

        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session, sessionmaker

        from app.core.config import settings
        from app.models.component import Component, QCStatus
        from app.models.job import Job
        from app.models.spare import Spare

        sync_url = settings.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )
        engine = create_engine(sync_url, pool_pre_ping=True)
        SyncSession = sessionmaker(bind=engine, expire_on_commit=False)

        vessel_uuid = _uuid.UUID(vessel_id) if isinstance(vessel_id, str) else vessel_id

        components_out: list[dict] = []
        jobs_out: list[dict] = []
        spares_out: list[dict] = []
        excluded_out: list[dict] = []

        with SyncSession() as session:
            # ---- Components ----
            comps = session.execute(
                select(Component).where(
                    Component.vessel_id == vessel_uuid,
                    Component.is_deleted == False,
                )
            ).scalars().all()

            for c in comps:
                row = {
                    "group1": c.group1,
                    "group2": c.group2,
                    "main_machinery": c.main_machinery,
                    "component_name": c.component_name,
                    "maker": c.maker or "",
                    "model": c.model or "",
                    "specification": c.specification or "",
                    "serial_number": c.serial_number or "",
                    "is_critical": "Yes" if c.is_critical else "No",
                    "qc_status": c.qc_status.value,
                    "page_reference": c.page_reference or "",
                }
                if c.qc_status in (QCStatus.accepted, QCStatus.modified):
                    components_out.append(row)
                else:
                    excluded_out.append({**row, "reason": f"QC Status: {c.qc_status.value}"})

            # ---- Jobs ----
            jobs = session.execute(
                select(Job).where(
                    Job.vessel_id == vessel_uuid,
                    Job.is_deleted == False,
                )
            ).scalars().all()

            for j in jobs:
                row = {
                    "job_name": j.job_name,
                    "job_code": j.job_code or "",
                    "job_description": j.job_description or "",
                    "safety_precaution": j.safety_precaution or "",
                    "tools_required": j.tools_required or "",
                    "performing_rank": j.performing_rank or "",
                    "verifying_rank": j.verifying_rank or "",
                    "frequency": j.frequency or "",
                    "frequency_type": j.frequency_type.value if j.frequency_type else "",
                    "cms_id": j.cms_id or "",
                    "is_critical": "Yes" if j.is_critical else "No",
                    "qc_status": j.qc_status.value,
                    "component_linked": str(j.component_id) if j.component_id else "",
                }
                if j.qc_status in (QCStatus.accepted, QCStatus.modified):
                    jobs_out.append(row)
                else:
                    excluded_out.append({**row, "reason": f"QC Status: {j.qc_status.value}"})

            # ---- Spares ----
            spares = session.execute(
                select(Spare).where(
                    Spare.vessel_id == vessel_uuid,
                    Spare.is_deleted == False,
                    Spare.is_duplicate == False,
                )
            ).scalars().all()

            for s in spares:
                row = {
                    "part_name": s.part_name,
                    "part_number": s.part_number or "",
                    "drawing_number": s.drawing_number or "",
                    "drawing_position": s.drawing_position or "",
                    "specification": s.specification or "",
                    "spare_maker": s.spare_maker or "",
                    "spare_model": s.spare_model or "",
                    "machinery_maker": s.machinery_maker or "",
                    "machinery_model": s.machinery_model or "",
                    "extraction_method": s.extraction_method.value,
                    "is_critical": "Yes" if s.is_critical else "No",
                    "qc_status": s.qc_status.value,
                    "component_linked": str(s.component_id) if s.component_id else "",
                }
                if s.qc_status in (QCStatus.accepted, QCStatus.modified):
                    spares_out.append(row)
                else:
                    excluded_out.append({**row, "reason": f"QC Status: {s.qc_status.value}"})

        return {
            "components": components_out,
            "jobs": jobs_out,
            "spares": spares_out,
            "excluded": excluded_out,
        }

    def to_excel(
        self, serialized_data: dict[str, Any], template_schema: dict | None = None
    ) -> bytes:
        """
        Generate Excel workbook from serialized data.
        Uses openpyxl if available, otherwise returns CSV-like bytes.
        """
        try:
            return self._to_excel_openpyxl(serialized_data, template_schema)
        except ImportError:
            return self._to_csv_fallback(serialized_data)

    def _to_excel_openpyxl(
        self, data: dict[str, Any], schema: dict | None
    ) -> bytes:
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        wb = openpyxl.Workbook()

        sheets = {
            "Components": data.get("components", []),
            "Jobs": data.get("jobs", []),
            "Spares": data.get("spares", []),
            "Excluded Records": data.get("excluded", []),
        }

        first = True
        for sheet_name, rows in sheets.items():
            if first:
                ws = wb.active
                ws.title = sheet_name
                first = False
            else:
                ws = wb.create_sheet(sheet_name)

            if not rows:
                ws.append([f"No {sheet_name.lower()} records to export."])
                continue

            # Write headers
            headers = list(rows[0].keys()) if rows else []
            header_row = [
                FIELD_MAPPINGS.get(h, h.replace("_", " ").title()) for h in headers
            ]
            ws.append(header_row)

            # Style header
            header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = header_fill

            for row in rows:
                ws.append([row.get(h, "") for h in headers])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def _to_csv_fallback(self, data: dict[str, Any]) -> bytes:
        """Simple CSV fallback when openpyxl is not installed."""
        lines = []
        for section, rows in data.items():
            lines.append(f"=== {section} ===")
            if rows:
                lines.append(",".join(rows[0].keys()))
                for row in rows:
                    lines.append(",".join(str(v) for v in row.values()))
        return "\n".join(lines).encode("utf-8")

    def parse_template(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """
        Parse an uploaded Excel template to detect sheets and columns.
        Returns sheet_mappings structure.
        """
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
            sheets: dict[str, list] = {}
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                headers = []
                first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])
                for col_idx, cell_value in enumerate(first_row, start=1):
                    if cell_value:
                        # Try to auto-map header to system field
                        system_field = self._auto_map(str(cell_value))
                        headers.append(
                            {
                                "column_index": col_idx,
                                "column_header": str(cell_value),
                                "field_name": system_field,
                                "auto_mapped": system_field is not None,
                            }
                        )
                sheets[sheet_name] = headers
            return {"sheet_mappings": sheets}
        except Exception as exc:
            logger.warning("Could not parse Excel template: %s", exc)
            return {"sheet_mappings": {}}

    def _auto_map(self, header: str) -> str | None:
        """Attempt to auto-map a column header to a known system field."""
        header_lower = header.lower().replace(" ", "_")
        for field, display in FIELD_MAPPINGS.items():
            if field == header_lower or display.lower().replace(" ", "_") == header_lower:
                return field
        return None


export_service = ExportService()
