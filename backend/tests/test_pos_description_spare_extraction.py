import pytest
from app.services.extractor import (
    normalize_spare_part_number_and_position,
    _sanitize_extracted_record,
    _standardize_item_prefix,
    _is_fallback_item_id,
)
from app.services.classifier import (
    _looks_like_spare_seed_page,
    _looks_like_spare_continuation,
)


def test_classifier_recognizes_pos_description_tables():
    """Verify that classifier recognizes simple Pos. | Description tables like Page 63 of PV Valve manual."""
    page_63_sample = """
    #HVV-HPHVV; 26_2024-02-21
    Page 42 of 52
    9.1. Corrosion test
    1
    2
    3
    4
    5
    6
    Pos.
    Description
    1
    Water heater
    2
    Thermometer
    3
    Hydrometer
    4
    Water spray nozzle
    5
    Device to be tested
    6
    Pump
    """
    assert _looks_like_spare_seed_page(page_63_sample) is True
    assert _looks_like_spare_continuation(page_63_sample) is True


def test_classifier_recognizes_item_description_material_tables():
    """Verify that classifier recognizes Item No. | Description | Material tables without QTY (like Page 5)."""
    page_5_sample = """
    Item No.
    Description
    Material
    1
    Housing
    AISI 316
    2
    Pressure Disc
    AISI 316
    """
    assert _looks_like_spare_seed_page(page_5_sample) is True


def test_standardize_pos_item_prefix():
    """Verify standardization of Pos / Position prefixes."""
    assert _standardize_item_prefix("Pos. 1") == "Pos. 1"
    assert _standardize_item_prefix("Pos 1") == "Pos. 1"
    assert _standardize_item_prefix("Position 2") == "Pos. 2"
    assert _standardize_item_prefix("Pos No: 5") == "Pos. 5"
    assert _is_fallback_item_id("Pos. 1") is True
    assert _is_fallback_item_id("Position 3") is True


def test_normalize_spare_pos_description_page_63():
    """Verify that normalize_spare_part_number_and_position handles Page 63 records."""
    # Case 1: Model returns drawing_position='1' and part_number=None (no catalog part number)
    pn, pos, spec = normalize_spare_part_number_and_position(
        part_number=None,
        drawing_position="1",
        drawing_number=None,
        specification=None,
    )
    assert pn == "Pos. 1"
    assert pos == "1"

    # Case 2: Model returns part_number='Pos. 1' and drawing_position='1'
    pn, pos, spec = normalize_spare_part_number_and_position(
        part_number="Pos. 1",
        drawing_position="1",
        drawing_number=None,
        specification=None,
    )
    assert pn == "Pos. 1"
    assert pos == "1"

    # Case 3: Model returns part_number='Pos. 1' but forgot drawing_position
    pn, pos, spec = normalize_spare_part_number_and_position(
        part_number="Pos. 1",
        drawing_position=None,
        drawing_number=None,
        specification=None,
    )
    assert pn == "Pos. 1"
    assert pos == "1"

    # Case 4: Model returns part_number='Position 4'
    pn, pos, spec = normalize_spare_part_number_and_position(
        part_number="Position 4",
        drawing_position=None,
        drawing_number=None,
        specification=None,
    )
    assert pn == "Pos. 4"
    assert pos == "4"


def test_normalize_spare_catalog_and_drawing_combinations():
    """Verify that catalog part numbers and drawing numbers are preserved correctly."""
    # When drawing number exists and position exists with no catalog number -> Drawing No./Pos No.
    pn, pos, spec = normalize_spare_part_number_and_position(
        part_number=None,
        drawing_position="15",
        drawing_number="FIG.7",
        specification=None,
    )
    assert pn == "FIG.7/15"
    assert pos == "15"

    # When catalog part number exists -> catalog number is kept, drawing_position is kept
    pn, pos, spec = normalize_spare_part_number_and_position(
        part_number="00621141",
        drawing_position="1",
        drawing_number="FIG.7",
        specification="Material: AISI 316",
    )
    assert pn == "00621141"
    assert pos == "1"


def test_sanitize_extracted_record_page_63_items():
    """Verify end-to-end record sanitization for Page 63 spares."""
    raw_record = {
        "part_name": "water heater",
        "drawing_position": "1",
        "source_page_number": 63,
    }
    cleaned = _sanitize_extracted_record(raw_record, filename="102# PV VALVE光伏阀.pdf", extraction_type="spare")
    assert cleaned["part_name"] == "Water Heater"
    assert cleaned["drawing_position"] == "1"
    assert cleaned["part_number"] == "Pos. 1"
    assert cleaned["source_page_number"] == 63
