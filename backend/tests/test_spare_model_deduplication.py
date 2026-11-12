import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.deduplication import extract_spare_model_heading, is_duplicate_spare
from app.services.extractor import _dedupe_records, _consolidate_spares_for_manual


def test_extract_spare_model_heading():
    # 1. From spare_model dictionary
    assert extract_spare_model_heading({"spare_model": "HVV-2.5"}) == "HVV-2.5"
    assert extract_spare_model_heading({"spare_model": "Model: HVV-3"}) == "HVV-3"
    assert extract_spare_model_heading({"spare_model": "TYPE: 6EY18ALW"}) == "6EY18ALW"
    assert extract_spare_model_heading({"spare_model": "DK-20"}) == "DK-20"

    # 2. From machinery_model dictionary fallback
    assert extract_spare_model_heading({"machinery_model": "HVV-2.5"}) == "HVV-2.5"

    # 3. From spare_assembly regex (KIT <MODEL>)
    assert extract_spare_model_heading({"spare_assembly": "KIT HVV-2.5 VOC"}) == "HVV-2.5"
    assert extract_spare_model_heading({"spare_assembly": "KIT HVV-3 O"}) == "HVV-3"
    assert extract_spare_model_heading({"spare_assembly": "HVV-2.5"}) == "HVV-2.5"

    # 4. From Object with attributes
    class SpareStub:
        def __init__(self, spare_model="", machinery_model="", spare_assembly=""):
            self.spare_model = spare_model
            self.machinery_model = machinery_model
            self.spare_assembly = spare_assembly

    assert extract_spare_model_heading(SpareStub(spare_model="HVV-2.5")) == "HVV-2.5"
    assert extract_spare_model_heading(SpareStub(spare_assembly="KIT HVV-3 VOC")) == "HVV-3"
    assert extract_spare_model_heading(SpareStub()) == ""


def test_is_duplicate_spare_respects_model_headings():
    # Same part number & name, but DIFFERENT model headings -> NOT duplicate
    spare1 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-2.5",
        "spare_assembly": "KIT HVV-2.5 VOC",
    }
    spare2 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-3",
        "spare_assembly": "KIT HVV-3 O",
    }
    assert is_duplicate_spare(spare1, spare2) is False

    # Same part number & name, SAME model heading -> DUPLICATE
    spare3 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-2.5",
        "spare_assembly": "KIT HVV-2.5 O",
    }
    assert is_duplicate_spare(spare1, spare3) is True

    # Same part number & name, one has model heading, other has none -> DUPLICATE only if neither differs
    # But if both have model headings that match -> True
    spare4 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
    }
    assert is_duplicate_spare(spare1, spare4) is True


def test_dedupe_records_retains_different_model_headings():
    records = [
        {
            "part_name": "O-Ring",
            "part_number": "1380-53",
            "drawing_number": "",
            "drawing_position": "1",
            "spare_model": "HVV-2.5",
            "source_page_number": 58,
        },
        {
            "part_name": "O-Ring",
            "part_number": "1380-53",
            "drawing_number": "",
            "drawing_position": "1",
            "spare_model": "HVV-3",
            "source_page_number": 59,
        },
        # Duplicate under same model
        {
            "part_name": "O-Ring",
            "part_number": "1380-53",
            "drawing_number": "",
            "drawing_position": "1",
            "spare_model": "HVV-2.5",
            "source_page_number": 58,
        },
    ]

    deduped = _dedupe_records(records, "spare")
    # Should keep the first HVV-2.5 and the HVV-3, but discard the duplicate HVV-2.5
    assert len(deduped) == 2
    models = [r["spare_model"] for r in deduped]
    assert "HVV-2.5" in models
    assert "HVV-3" in models


@pytest.mark.asyncio
async def test_consolidate_spares_intra_manual_different_models():
    # Simulate DB Spare model objects
    class MockSpare:
        def __init__(self, id_val, part_name, part_number, drawing_position, spare_model, spare_assembly, page_ref):
            self.id = id_val
            self.part_name = part_name
            self.part_number = part_number
            self.drawing_position = drawing_position
            self.drawing_number = None
            self.spare_model = spare_model
            self.spare_assembly = spare_assembly
            self.assembly_description = None
            self.spare_maker = None
            self.specification = None
            self.page_reference = page_ref
            self.component_id = None
            self.is_critical = False
            self.confidence_score = 90
            self.is_deleted = False
            self.is_duplicate = False
            self.merged_into_id = None
            self.vessel_id = None
            self.tenant_id = None
            self.source_manual_id = None

    vessel_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    manual = MagicMock()
    manual.id = uuid.uuid4()

    # Spares on Pg 58 (HVV-2.5) and Pg 59 (HVV-3) with identical part numbers
    s1 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", "KIT HVV-2.5 VOC", 58)
    s2 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-3", "KIT HVV-3 O", 59)
    # Duplicate spare under HVV-2.5
    s3 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", "KIT HVV-2.5 O", 58)

    spares_in_manual = [s1, s2, s3]

    # Mock DB execute
    db = AsyncMock()

    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return self
        def all(self):
            return self.items

    # 1st call: spares in this manual -> [s1, s2, s3]
    # 2nd call: spares in other manuals -> []
    db.execute.side_effect = [
        MockResult(spares_in_manual),
        MockResult([]),
    ]

    merged_count = await _consolidate_spares_for_manual(
        db=db,
        manual=manual,
        vessel_id=vessel_id,
        tenant_id=tenant_id,
    )

    # s1 and s2 belong to different model headings (HVV-2.5 vs HVV-3) -> NEITHER is deleted!
    assert s1.is_deleted is False
    assert s2.is_deleted is False

    # s3 belongs to the same model heading (HVV-2.5) as s1 -> s3 is marked deleted/duplicate!
    assert s3.is_deleted is True
    assert s3.is_duplicate is True
    assert s3.merged_into_id == s1.id

    assert merged_count == 1


@pytest.mark.asyncio
async def test_consolidate_spares_cross_manual_model_headings():
    class MockSpare:
        def __init__(self, id_val, part_name, part_number, drawing_position, spare_model, manual_id):
            self.id = id_val
            self.part_name = part_name
            self.part_number = part_number
            self.drawing_position = drawing_position
            self.drawing_number = None
            self.spare_model = spare_model
            self.spare_assembly = None
            self.assembly_description = None
            self.spare_maker = None
            self.specification = None
            self.page_reference = 10
            self.component_id = None
            self.is_critical = False
            self.confidence_score = 90
            self.is_deleted = False
            self.is_duplicate = False
            self.merged_into_id = None
            self.source_manual_id = manual_id

    vessel_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    manual_1 = MagicMock()
    manual_1.id = uuid.uuid4()
    manual_2_id = uuid.uuid4()

    # Manual 1 spares (being consolidated)
    s_m1_modelA = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", manual_1.id)
    s_m1_modelB = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-3", manual_1.id)

    # Existing spare in Manual 2 for HVV-2.5
    s_m2_modelA = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", manual_2_id)

    db = AsyncMock()

    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return self
        def all(self):
            return self.items

    db.execute.side_effect = [
        MockResult([s_m1_modelA, s_m1_modelB]),  # Intra-manual query
        MockResult([s_m2_modelA]),               # Cross-manual query
    ]

    merged_count = await _consolidate_spares_for_manual(
        db=db,
        manual=manual_1,
        vessel_id=vessel_id,
        tenant_id=tenant_id,
    )

    # s_m1_modelA matches s_m2_modelA with SAME model heading HVV-2.5 -> marked duplicate
    assert s_m1_modelA.is_deleted is True
    assert s_m1_modelA.is_duplicate is True
    assert s_m1_modelA.merged_into_id == s_m2_modelA.id

    # s_m1_modelB has model HVV-3 != HVV-2.5 -> NOT duplicate!
    assert s_m1_modelB.is_deleted is False

    assert merged_count == 1
