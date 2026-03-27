from __future__ import annotations

import logging
import uuid
from typing import Any

from app.tasks import celery_app

logger = logging.getLogger(__name__)


def _mock_components(vessel_id: str, manual_id: str, tenant_id: str) -> list[dict[str, Any]]:
    """Generate 5 mock components for a manual."""
    return [
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "group1": "Main Machinery",
            "group2": "Propulsion",
            "main_machinery": "Main Engine",
            "component_name": "Fuel Injection Pump",
            "maker": "MAN B&W",
            "model": "MC-C",
            "specification": "High-pressure fuel injection pump",
            "confidence_score": 88,
            "source_manual_id": manual_id,
            "page_reference": 45,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "group1": "Main Machinery",
            "group2": "Propulsion",
            "main_machinery": "Main Engine",
            "component_name": "Turbocharger",
            "maker": "ABB",
            "model": "TCA55",
            "specification": "Axial turbocharger",
            "confidence_score": 92,
            "source_manual_id": manual_id,
            "page_reference": 78,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "group1": "Auxiliary Machinery",
            "group2": "Pumps",
            "main_machinery": "Seawater Cooling Pump",
            "component_name": "Seawater Pump",
            "maker": "Wartsila",
            "model": "SCP-200",
            "specification": "Centrifugal seawater cooling pump",
            "confidence_score": 80,
            "source_manual_id": manual_id,
            "page_reference": 112,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "group1": "Auxiliary Machinery",
            "group2": "Generators",
            "main_machinery": "Auxiliary Engine",
            "component_name": "Air Start Valve",
            "maker": "Hamworthy",
            "model": "ASV-100",
            "specification": "Pneumatic air start valve",
            "confidence_score": 75,
            "source_manual_id": manual_id,
            "page_reference": 150,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "group1": "Deck Machinery",
            "group2": "Mooring",
            "main_machinery": "Windlass",
            "component_name": "Windlass Brake",
            "maker": "Karmøy",
            "model": "WB-500",
            "specification": "Band brake for windlass",
            "confidence_score": 70,
            "source_manual_id": manual_id,
            "page_reference": 200,
        },
    ]


def _mock_jobs(vessel_id: str, manual_id: str, tenant_id: str) -> list[dict[str, Any]]:
    """Generate 3 mock jobs for a manual."""
    return [
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "job_name": "Fuel Injection Pump Overhaul",
            "job_description": "Complete overhaul of fuel injection pump including plunger and barrel replacement",
            "safety_precaution": "Ensure engine is stopped and fuel system depressurized",
            "tools_required": "Injection pump puller, torque wrench, calibration equipment",
            "performing_rank": "2nd Engineer",
            "verifying_rank": "Chief Engineer",
            "frequency": 8000,
            "frequency_type": "running_hours",
            "is_critical": True,
            "source_manual_id": manual_id,
            "confidence_score": 90,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "job_name": "Turbocharger Inspection",
            "job_description": "Visual inspection and cleaning of turbocharger blades",
            "safety_precaution": "Allow sufficient cool-down time before inspection",
            "tools_required": "Inspection mirror, cleaning brushes",
            "performing_rank": "3rd Engineer",
            "verifying_rank": "2nd Engineer",
            "frequency": 4000,
            "frequency_type": "running_hours",
            "is_critical": False,
            "source_manual_id": manual_id,
            "confidence_score": 85,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "job_name": "Seawater Pump Impeller Check",
            "job_description": "Check impeller wear and clearance measurement",
            "safety_precaution": "Close sea suction valve before opening pump casing",
            "tools_required": "Feeler gauge, calipers",
            "performing_rank": "3rd Engineer",
            "verifying_rank": "2nd Engineer",
            "frequency": 1,
            "frequency_type": "yearly",
            "is_critical": False,
            "source_manual_id": manual_id,
            "confidence_score": 78,
        },
    ]


def _mock_spares(vessel_id: str, manual_id: str, tenant_id: str) -> list[dict[str, Any]]:
    """Generate 5 mock spares for a manual."""
    return [
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "part_name": "Plunger and Barrel Assembly",
            "part_number": "23900-01H",
            "drawing_number": "DWG-FIP-001",
            "specification": "High-pressure plunger and barrel for fuel injection pump",
            "spare_maker": "MAN B&W",
            "source_manual_id": manual_id,
            "page_reference": 48,
            "extraction_method": "table",
            "confidence_score": 90,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "part_name": "Delivery Valve Assembly",
            "part_number": "23910-02H",
            "drawing_number": "DWG-FIP-002",
            "specification": "Delivery valve set for fuel injection pump",
            "spare_maker": "MAN B&W",
            "source_manual_id": manual_id,
            "page_reference": 49,
            "extraction_method": "table",
            "confidence_score": 88,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "part_name": "Turbocharger Bearing Kit",
            "part_number": "TCK-TCA55-001",
            "specification": "Complete bearing kit for TCA55 turbocharger",
            "spare_maker": "ABB",
            "source_manual_id": manual_id,
            "page_reference": 82,
            "extraction_method": "text",
            "confidence_score": 80,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "part_name": "Pump Impeller",
            "part_number": "SCP-IMP-200",
            "specification": "Bronze impeller for SCP-200 seawater pump",
            "spare_maker": "Wartsila",
            "source_manual_id": manual_id,
            "page_reference": 115,
            "extraction_method": "table",
            "confidence_score": 82,
        },
        {
            "vessel_id": vessel_id,
            "tenant_id": tenant_id,
            "part_name": "Mechanical Seal",
            "part_number": "MS-SCP-001",
            "specification": "Mechanical seal set for seawater pump",
            "spare_maker": "Wartsila",
            "source_manual_id": manual_id,
            "page_reference": 116,
            "extraction_method": "drawing",
            "confidence_score": 76,
        },
    ]


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_components(self, vessel_id: str) -> dict[str, Any]:
    """Extract components from all classified manuals for a vessel."""
    import asyncio

    async def _run() -> dict[str, Any]:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.component import Component, QCStatus
        from app.models.ingestion import Manual

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Manual).where(
                    Manual.vessel_id == uuid.UUID(vessel_id),
                    Manual.is_deleted == False,
                    Manual.useful_for_extraction == "Yes",
                )
            )
            manuals = result.scalars().all()

            total_created = 0
            for manual in manuals:
                try:
                    component_data = _mock_components(
                        vessel_id, str(manual.id), str(manual.tenant_id)
                    )
                    for comp_dict in component_data:
                        comp = Component(
                            tenant_id=uuid.UUID(comp_dict["tenant_id"]),
                            vessel_id=uuid.UUID(comp_dict["vessel_id"]),
                            group1=comp_dict["group1"],
                            group2=comp_dict["group2"],
                            main_machinery=comp_dict["main_machinery"],
                            component_name=comp_dict["component_name"],
                            maker=comp_dict.get("maker"),
                            model=comp_dict.get("model"),
                            specification=comp_dict.get("specification"),
                            confidence_score=comp_dict.get("confidence_score"),
                            source_manual_id=uuid.UUID(comp_dict["source_manual_id"])
                            if comp_dict.get("source_manual_id")
                            else None,
                            page_reference=comp_dict.get("page_reference"),
                            qc_status=QCStatus.pending,
                        )
                        db.add(comp)
                        total_created += 1
                except Exception as exc:
                    logger.warning("Component extraction failed for manual %s: %s", manual.id, exc)

            await db.commit()
            return {"status": "completed", "components_created": total_created}

    return asyncio.run(_run())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_jobs(self, vessel_id: str) -> dict[str, Any]:
    """Extract jobs from manuals with pages_with_jobs set."""
    import asyncio

    async def _run() -> dict[str, Any]:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.job import Job, QCStatus as JobQCStatus
        from app.models.ingestion import Manual

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Manual).where(
                    Manual.vessel_id == uuid.UUID(vessel_id),
                    Manual.is_deleted == False,
                    Manual.pages_with_jobs.isnot(None),
                )
            )
            manuals = result.scalars().all()

            total_created = 0
            for manual in manuals:
                try:
                    job_data = _mock_jobs(
                        vessel_id, str(manual.id), str(manual.tenant_id)
                    )
                    for job_dict in job_data:
                        from app.models.job import FrequencyType
                        job = Job(
                            tenant_id=uuid.UUID(job_dict["tenant_id"]),
                            vessel_id=uuid.UUID(job_dict["vessel_id"]),
                            job_name=job_dict["job_name"],
                            job_description=job_dict.get("job_description"),
                            safety_precaution=job_dict.get("safety_precaution"),
                            tools_required=job_dict.get("tools_required"),
                            performing_rank=job_dict.get("performing_rank"),
                            verifying_rank=job_dict.get("verifying_rank"),
                            frequency=job_dict.get("frequency"),
                            frequency_type=FrequencyType(job_dict["frequency_type"])
                            if job_dict.get("frequency_type")
                            else None,
                            is_critical=job_dict.get("is_critical", False),
                            source_manual_id=uuid.UUID(job_dict["source_manual_id"])
                            if job_dict.get("source_manual_id")
                            else None,
                            confidence_score=job_dict.get("confidence_score"),
                            qc_status=JobQCStatus.pending,
                        )
                        db.add(job)
                        total_created += 1
                except Exception as exc:
                    logger.warning("Job extraction failed for manual %s: %s", manual.id, exc)

            await db.commit()
            return {"status": "completed", "jobs_created": total_created}

    return asyncio.run(_run())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_spares_table(self, vessel_id: str) -> dict[str, Any]:
    """Table-based spare extraction."""
    import asyncio

    async def _run() -> dict[str, Any]:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.spare import Spare, ExtractionMethod
        from app.models.component import QCStatus
        from app.models.ingestion import Manual

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Manual).where(
                    Manual.vessel_id == uuid.UUID(vessel_id),
                    Manual.is_deleted == False,
                    Manual.pages_with_spares.isnot(None),
                )
            )
            manuals = result.scalars().all()

            total_created = 0
            for manual in manuals:
                try:
                    spare_data = _mock_spares(
                        vessel_id, str(manual.id), str(manual.tenant_id)
                    )
                    for sp_dict in spare_data:
                        spare = Spare(
                            tenant_id=uuid.UUID(sp_dict["tenant_id"]),
                            vessel_id=uuid.UUID(sp_dict["vessel_id"]),
                            part_name=sp_dict["part_name"],
                            part_number=sp_dict.get("part_number"),
                            drawing_number=sp_dict.get("drawing_number"),
                            specification=sp_dict.get("specification"),
                            spare_maker=sp_dict.get("spare_maker"),
                            source_manual_id=uuid.UUID(sp_dict["source_manual_id"])
                            if sp_dict.get("source_manual_id")
                            else None,
                            page_reference=sp_dict.get("page_reference"),
                            extraction_method=ExtractionMethod(sp_dict.get("extraction_method", "table")),
                            confidence_score=sp_dict.get("confidence_score"),
                            qc_status=QCStatus.pending,
                        )
                        db.add(spare)
                        total_created += 1
                except Exception as exc:
                    logger.warning("Spare extraction failed for manual %s: %s", manual.id, exc)

            await db.commit()
            return {"status": "completed", "spares_created": total_created}

    return asyncio.run(_run())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_spares_text(self, vessel_id: str) -> dict[str, Any]:
    """NLP text-based spare extraction (delegates to table extractor for mock)."""
    return extract_spares_table.delay(vessel_id).get(timeout=120)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def extract_spares_drawing(self, vessel_id: str) -> dict[str, Any]:
    """IPC drawing-based spare extraction (mock)."""
    return {"status": "completed", "spares_created": 0, "note": "Drawing extraction is mock"}
