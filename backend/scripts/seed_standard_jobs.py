#!/usr/bin/env python3
"""
Seed script for standard jobs and vessel type templates.
Run: python -m scripts.seed_standard_jobs
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.standard_jobs import ClassSociety, StandardJob, VesselTypeTemplate

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

VESSEL_TYPE_TEMPLATES = [
    # Bulk Carrier
    ("Bulk Carrier", "Main Machinery", "Main Engine", True, ["components", "jobs", "spares"]),
    ("Bulk Carrier", "Main Machinery", "Auxiliary Engine", True, ["components", "jobs", "spares"]),
    ("Bulk Carrier", "Deck Machinery", "Cargo Gear", True, ["components", "jobs"]),
    ("Bulk Carrier", "Auxiliary Machinery", "Bilge/Ballast System", True, ["components", "jobs", "spares"]),
    ("Bulk Carrier", "Safety Equipment", "Fire Fighting System", True, ["components", "jobs"]),
    # Tanker
    ("Tanker", "Main Machinery", "Main Engine", True, ["components", "jobs", "spares"]),
    ("Tanker", "Cargo System", "Cargo Pumps", True, ["components", "jobs", "spares"]),
    ("Tanker", "Cargo System", "Inert Gas System", True, ["components", "jobs", "spares"]),
    ("Tanker", "Auxiliary Machinery", "Boiler", True, ["components", "jobs", "spares"]),
    ("Tanker", "Safety Equipment", "Gas Detection System", True, ["components", "jobs"]),
    # Container Ship
    ("Container Ship", "Main Machinery", "Main Engine", True, ["components", "jobs", "spares"]),
    ("Container Ship", "Deck Machinery", "Hatch Covers", True, ["components", "jobs"]),
    ("Container Ship", "Reefer System", "Reefer Power Sockets", False, ["components", "jobs"]),
    # General Cargo
    ("General Cargo", "Main Machinery", "Main Engine", True, ["components", "jobs", "spares"]),
    ("General Cargo", "Deck Machinery", "Cranes", True, ["components", "jobs"]),
]

STANDARD_JOBS = [
    # DNV GL
    (ClassSociety.dnv_gl, "Diesel Engine", "Main Engine Piston Overhaul", "Complete overhaul of main engine pistons", 16000, "running_hours", True, "DNVGL-CG-0052-ME-001"),
    (ClassSociety.dnv_gl, "Diesel Engine", "Cylinder Liner Inspection", "Inspection and measurement of cylinder liners", 8000, "running_hours", True, "DNVGL-CG-0052-ME-002"),
    (ClassSociety.dnv_gl, "Diesel Engine", "Turbocharger Overhaul", "Complete turbocharger overhaul", 24000, "running_hours", True, "DNVGL-CG-0052-ME-003"),
    (ClassSociety.dnv_gl, "Diesel Engine", "Fuel Injection Pump Calibration", "Calibration of fuel injection pumps", 8000, "running_hours", False, "DNVGL-CG-0052-ME-004"),
    (ClassSociety.dnv_gl, "Purifier", "Purifier Bowl Cleaning", "Cleaning of separator bowl and disc stack", None, "monthly", False, "DNVGL-CG-0052-PU-001"),
    (ClassSociety.dnv_gl, "Auxiliary Engine", "Auxiliary Engine Top Overhaul", "Top overhaul of auxiliary engine", 12000, "running_hours", True, "DNVGL-CG-0052-AE-001"),
    # Lloyd's Register
    (ClassSociety.lr, "Diesel Engine", "Main Engine Annual Survey", "Class survey of main engine", 1, "yearly", True, "LR-ME-ANNUAL-001"),
    (ClassSociety.lr, "Diesel Engine", "Crankshaft Deflection Check", "Crankshaft deflection measurement", 1, "yearly", True, "LR-ME-001"),
    (ClassSociety.lr, "Boiler", "Boiler Internal Inspection", "Internal inspection of boiler", 1, "yearly", True, "LR-BLR-001"),
    (ClassSociety.lr, "Pump", "Bilge Pump Overhaul", "Overhaul of bilge pumps", 1, "yearly", False, "LR-PMP-001"),
    # Bureau Veritas
    (ClassSociety.bv, "Diesel Engine", "Engine Condition Monitoring", "Performance monitoring and analysis", None, "monthly", False, "BV-ME-ECM-001"),
    (ClassSociety.bv, "Steering Gear", "Steering Gear Full Test", "Full functionality test of steering gear", None, "weekly", True, "BV-STR-001"),
    (ClassSociety.bv, "Safety", "Lifeboat Release Mechanism Test", "Test of lifeboat release and retrieval", None, "monthly", True, "BV-LSA-001"),
    # ABS
    (ClassSociety.abs, "Diesel Engine", "Main Engine Critical Component Inspection", "Inspection per ABS maintenance guidelines", 8000, "running_hours", True, "ABS-ME-CRIT-001"),
    (ClassSociety.abs, "Electrical", "Emergency Generator Test", "Full load test of emergency generator", None, "monthly", True, "ABS-EG-001"),
    (ClassSociety.abs, "Fire Fighting", "Fixed Fire Fighting System Test", "Test of CO2/foam system", None, "yearly", True, "ABS-FFS-001"),
    # ClassNK
    (ClassSociety.classnk, "Diesel Engine", "Main Engine Performance Test", "Power and efficiency measurement", None, "half_yearly", True, "NK-ME-PERF-001"),
    (ClassSociety.classnk, "Cooling System", "Seawater Cooling Pump Overhaul", "Overhaul of seawater cooling pumps", 1, "yearly", False, "NK-CL-001"),
    (ClassSociety.classnk, "Exhaust System", "Exhaust Gas Boiler Cleaning", "Water washing of EGB", None, "monthly", False, "NK-EGB-001"),
    (ClassSociety.classnk, "Navigation", "Main GPS/GMDSS Equipment Test", "Functional test of navigation equipment", None, "quarterly", True, "NK-NAV-001"),
]


async def seed(db: AsyncSession) -> None:
    created_templates = 0
    updated_templates = 0
    created_jobs = 0
    updated_jobs = 0

    print("Seeding vessel type templates...")
    for vessel_type, machinery_group, machinery_name, is_mandatory, extraction_types in VESSEL_TYPE_TEMPLATES:
        existing_template = await db.scalar(
            select(VesselTypeTemplate).where(
                VesselTypeTemplate.tenant_id == DEFAULT_TENANT_ID,
                VesselTypeTemplate.vessel_type == vessel_type,
                VesselTypeTemplate.machinery_group == machinery_group,
                VesselTypeTemplate.machinery_name == machinery_name,
                VesselTypeTemplate.is_deleted == False,
            )
        )
        if existing_template:
            existing_template.is_mandatory = is_mandatory
            existing_template.extraction_types = extraction_types
            existing_template.is_system = True
            updated_templates += 1
        else:
            template = VesselTypeTemplate(
                tenant_id=DEFAULT_TENANT_ID,
                vessel_type=vessel_type,
                machinery_group=machinery_group,
                machinery_name=machinery_name,
                is_mandatory=is_mandatory,
                extraction_types=extraction_types,
                is_system=True,
            )
            db.add(template)
            created_templates += 1

    print("Seeding standard jobs...")
    for class_society, machinery_type, job_name, description, frequency, freq_type, is_critical, ref in STANDARD_JOBS:
        from app.models.job import FrequencyType

        try:
            ft = FrequencyType(freq_type) if freq_type else None
        except ValueError:
            ft = None

        existing_job = await db.scalar(
            select(StandardJob).where(
                StandardJob.tenant_id == DEFAULT_TENANT_ID,
                StandardJob.library_reference == ref,
                StandardJob.is_deleted == False,
            )
        )
        if existing_job:
            existing_job.class_society = class_society
            existing_job.machinery_type = machinery_type
            existing_job.job_name = job_name
            existing_job.job_description = description
            existing_job.frequency = frequency
            existing_job.frequency_type = ft
            existing_job.is_critical = is_critical
            existing_job.is_system = True
            updated_jobs += 1
        else:
            job = StandardJob(
                tenant_id=DEFAULT_TENANT_ID,
                class_society=class_society,
                machinery_type=machinery_type,
                job_name=job_name,
                job_description=description,
                frequency=frequency,
                frequency_type=ft,
                is_critical=is_critical,
                library_reference=ref,
                is_system=True,
            )
            db.add(job)
            created_jobs += 1

    await db.commit()
    print(
        "Seeding complete: "
        f"{created_templates} templates created, {updated_templates} templates updated, "
        f"{created_jobs} jobs created, {updated_jobs} jobs updated."
    )


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
