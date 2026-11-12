import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.deduplication import (
    extract_spare_model_heading,
    is_duplicate_spare,
)
from app.services.extractor import (
    _dedupe_records,
    _consolidate_spares_for_manual,
    _parse_simple_pos_description_table,
)


def test_extract_spare_model_heading():
    # Direct model
    assert extract_spare_model_heading({"spare_model": "HVV-2.5"}) == "HVV-2.5"
    assert extract_spare_model_heading({"machinery_model": "DK-20"}) == "DK-20"
    assert extract_spare_model_heading({"spare_model": "MODEL: 6EY18ALW"}) == "6EY18ALW"

    # Extracted from assembly / kit heading
    assert extract_spare_model_heading({"spare_assembly": "KIT HVV-2.5 VOC"}) == "HVV-2.5"
    assert extract_spare_model_heading({"spare_assembly": "KIT HVV-3 O"}) == "HVV-3"
    assert extract_spare_model_heading({"spare_assembly": "6EY18ALW Cylinder Head"}) == "6EY18ALW"

    # Empty
    assert extract_spare_model_heading({"spare_assembly": "General Tools"}) == ""


def test_is_duplicate_spare_respects_model_headings():
    # Same part number & name, but DIFFERENT model headings -> NOT duplicate
    spare1 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-2.5",
        "spare_assembly": "KIT HVV-2.5 VOC",
        "page_reference": 58,
    }
    spare2 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-3",
        "spare_assembly": "KIT HVV-3 O",
        "page_reference": 59,
    }
    assert is_duplicate_spare(spare1, spare2) is False

    # Same part number & name, but DIFFERENT assemblies/kits on same page -> NOT duplicate
    spare3 = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-2.5",
        "spare_assembly": "KIT HVV-2.5 O",
        "page_reference": 58,
    }
    assert is_duplicate_spare(spare1, spare3) is False

    # Exact duplicate: same part number, name, model, assembly, and page -> DUPLICATE
    spare_exact = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-2.5",
        "spare_assembly": "KIT HVV-2.5 VOC",
        "page_reference": 58,
    }
    assert is_duplicate_spare(spare1, spare_exact) is True

    # Same part, different pages -> NOT duplicate
    spare_diff_page = {
        "part_name": "O-RING",
        "part_number": "1380-53",
        "spare_model": "HVV-2.5",
        "spare_assembly": "KIT HVV-2.5 VOC",
        "page_reference": 59,
    }
    assert is_duplicate_spare(spare1, spare_diff_page) is False


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
        # Duplicate under same model and same page
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


def test_dedupe_records_preserves_page_58_all_13_spares():
    # Page 58 in PV valve manual has 2 kits: KIT HVV-2.5 VOC (4 spares) and KIT HVV-2.5 O (9 spares)
    # Both kits contain Pos. H / Part No. 1380-53 O-ring. All 13 spares must be preserved!
    p58_spares = [
        # Kit HVV-2.5 VOC (4 spares)
        {"part_name": "Secondary Valve Housing", "part_number": "2001-238-2,8", "drawing_position": "G", "spare_assembly": "KIT HVV-2.5 VOC", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "O-Ring", "part_number": "1380-53", "drawing_position": "H", "spare_assembly": "KIT HVV-2.5 VOC", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Secondary Valve Seat", "part_number": "1401-23-2", "drawing_position": "F", "spare_assembly": "KIT HVV-2.5 VOC", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Secondary Valve Plunger Acc. To Order", "part_number": "1402-xxx", "drawing_position": "E", "spare_assembly": "KIT HVV-2.5 VOC", "spare_model": "HVV-2.5", "source_page_number": 58},
        # Kit HVV-2.5 O (9 spares)
        {"part_name": "O-Ring", "part_number": "1380-53", "drawing_position": "H", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "O-Ring", "part_number": "1380-52", "drawing_position": "Q", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "O-Ring", "part_number": "1380-54", "drawing_position": "AZ", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "O-Ring", "part_number": "1380-57", "drawing_position": "AU", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Screw", "part_number": "105094", "drawing_position": "AC", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Lubrication Nipple", "part_number": "1307-2", "drawing_position": "AG", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Gasket", "part_number": "1381-3", "drawing_position": "AK", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Splitpin", "part_number": "106576", "drawing_position": "AE", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
        {"part_name": "Resilient Seal", "part_number": "1380-149", "drawing_position": "AL", "spare_assembly": "KIT HVV-2.5 O", "spare_model": "HVV-2.5", "source_page_number": 58},
    ]

    deduped = _dedupe_records(p58_spares, "spare")
    assert len(deduped) == 13

    # Verify both O-Rings (1380-53) are present with their respective kits
    o_rings = [s for s in deduped if s["part_number"] == "1380-53"]
    assert len(o_rings) == 2
    assemblies = {s["spare_assembly"] for s in o_rings}
    assert assemblies == {"KIT HVV-2.5 VOC", "KIT HVV-2.5 O"}


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

    # Spares on Pg 58 (HVV-2.5 VOC), Pg 58 (HVV-2.5 O-ring kit), and Pg 59 (HVV-3 O-ring kit)
    s1 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", "KIT HVV-2.5 VOC", 58)
    s2 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-3", "KIT HVV-3 O", 59)
    s3 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", "KIT HVV-2.5 O", 58)
    # Exact duplicate of s1 on same page and same kit
    s4 = MockSpare(uuid.uuid4(), "O-Ring", "1380-53", "1", "HVV-2.5", "KIT HVV-2.5 VOC", 58)

    spares_in_manual = [s1, s2, s3, s4]

    # Mock DB execute
    db = AsyncMock()

    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return self
        def all(self):
            return self.items

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

    # s1, s2, and s3 MUST be preserved:
    # - s1 is in KIT HVV-2.5 VOC on pg 58
    # - s2 is in KIT HVV-3 O on pg 59 (different model & different page)
    # - s3 is in KIT HVV-2.5 O on pg 58 (different kit)
    assert s1.is_deleted is False
    assert s2.is_deleted is False
    assert s3.is_deleted is False

    # s4 is an exact duplicate of s1 in the same kit on the same page -> merged
    assert s4.is_deleted is True
    assert s4.is_duplicate is True
    assert s4.merged_into_id == s1.id

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
            self.spare_assembly = "Assembly 1"
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

    db = AsyncMock()

    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return self
        def all(self):
            return self.items

    db.execute.side_effect = [
        MockResult([s_m1_modelA, s_m1_modelB]),
        MockResult([]),
    ]

    merged_count = await _consolidate_spares_for_manual(
        db=db,
        manual=manual_1,
        vessel_id=vessel_id,
        tenant_id=tenant_id,
    )

    # All spares belonging to manual_1 are preserved and NOT deleted across manuals
    assert s_m1_modelA.is_deleted is False
    assert s_m1_modelB.is_deleted is False


def test_parse_simple_pos_description_table_page_98():
    sample_text = """
#VV-1.5M 05 – 201214
Page 25 of 32
13.2. Hydrostatic Pressure Test
Pos.
Description
1
Blind flanges
2
Pressure gauge
3
Air bleed screw
4
Pressurized water supply
5
Device to be tested
1
2
3
4
5
"""
    records = _parse_simple_pos_description_table(sample_text, 98)
    assert len(records) == 5

    names = [r["part_name"] for r in records]
    assert names == [
        "Blind Flanges",
        "Pressure Gauge",
        "Air Bleed Screw",
        "Pressurized Water Supply",
        "Device To Be Tested",
    ]

    pns = [r["part_number"] for r in records]
    assert pns == ["Pos. 1", "Pos. 2", "Pos. 3", "Pos. 4", "Pos. 5"]

    pos = [r["drawing_position"] for r in records]
    assert pos == ["1", "2", "3", "4", "5"]

    pages = [r["source_page_number"] for r in records]
    assert all(p == 98 for p in pages)
