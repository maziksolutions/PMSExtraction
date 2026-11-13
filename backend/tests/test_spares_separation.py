import pytest
from app.services.extractor import (
    separate_spare_name_and_spec,
    normalize_spare_part_number_and_position,
    _format_specification_headers,
)


def test_parenthetical_spec_separation():
    cases = [
        ("O-RING (15.5 x 2.4 FKM)", ("O-Ring", "Material: FKM; Size: 15.5 x 2.4")),
        ("VALVE SEAT (SUS316)", ("Valve Seat", "Material: SUS316")),
        ("HEX BOLT (M12X45 STAINLESS)", ("Hex Bolt", "Material: STAINLESS; Size: M12X45")),
        ("LOCK NUT (M16)", ("Lock Nut", "Size: M16")),
    ]
    for raw, expected in cases:
        pname, spec = separate_spare_name_and_spec(raw)
        assert pname == expected[0], f"Failed name for {raw}: got {pname}, expected {expected[0]}"
        assert spec == expected[1], f"Failed spec for {raw}: got {spec}, expected {expected[1]}"


def test_trailing_pattern_separation():
    cases = [
        ("BALL BEARING 6205-2RS", ("Ball Bearing", "Size: 6205-2RS")),
        ("ROLLER BEARING NU206", ("Roller Bearing", "Size: NU206")),
        ("O-RING G-35", ("O-Ring", "Size: G-35")),
        ("O-RING 1A-P15", ("O-Ring", "Size: 1A-P15")),
        ("OIL SEAL TC 25 45 8", ("Oil Seal", "Size: TC 25 45 8")),
        ("OIL SEAL 25X45X8", ("Oil Seal", "Size: 25X45X8")),
        ("GASKET 150A 10K T=2.0", ("Gasket", "Size: 150A 10K T=2.0")),
        ("GASKET NON-ASBESTOS 1.5T", ("Gasket", "Material: NON-ASBESTOS; Size: 1.5T")),
        ("V-BELT B-48", ("V-Belt", "Size: B-48")),
        ("V-BELT SPA 1250", ("V-Belt", "Size: SPA 1250")),
        ("PLUG PT 1/2", ("Plug", "Size: PT 1/2")),
        ("NIPPLE R 1/4", ("Nipple", "Size: R 1/4")),
        ("HEX BOLT M12X45", ("Hex Bolt", "Size: M12X45")),
        ("STUD M16X60", ("Stud", "Size: M16X60")),
        ("VALVE SEAT SUS316", ("Valve Seat", "Material: SUS316")),
        ("PACKING TEFLON", ("Packing", "Material: TEFLON")),
    ]
    for raw, expected in cases:
        pname, spec = separate_spare_name_and_spec(raw)
        assert pname == expected[0], f"Failed name for {raw}: got {pname}, expected {expected[0]}"
        assert spec == expected[1], f"Failed spec for {raw}: got {spec}, expected {expected[1]}"


def test_existing_spec_deduplication():
    # If part_name contains dimension that already exists in specification
    raw = "O-RING 15.5X2.4"
    existing = "Size: 15.5X2.4; Material: FKM"
    pname, spec = separate_spare_name_and_spec(raw, existing)
    assert pname == "O-Ring"
    assert "15.5X2.4" in spec
    assert "FKM" in spec
    # Ensure no duplicates like "Size: 15.5X2.4; Size: 15.5X2.4"
    assert spec.count("15.5X2.4") == 1


def test_pure_part_names_untouched():
    pure = [
        "Impeller",
        "Piston Ring",
        "Suction Valve",
        "Connecting Rod",
        "Mechanical Seal",
        "Cylinder Liner",
        "Filter Element",
        "Crankshaft",
    ]
    for p in pure:
        pname, spec = separate_spare_name_and_spec(p, None)
        assert pname == p
        assert spec is None


def test_rule1_position_number_constraints():
    # Explicit position is preserved
    pn, pos, spec = normalize_spare_part_number_and_position("6205-01", "15", "FIG.7", None)
    assert pos == "15"
    assert pn == "6205-01"

    # Pos with label cleaned to number
    pn, pos, spec = normalize_spare_part_number_and_position("6205-01", "Pos. 11", "FIG.7", None)
    assert pos == "11"

    # Item/Ref/No in pos is cleared from position
    pn, pos, spec = normalize_spare_part_number_and_position("6205-01", "Ref No. 12", "FIG.7", None)
    assert pos is None
    assert "Ref No: 12" in (spec or "")


def test_rule2_item_ref_no_as_part_number():
    # When catalog Part Number is NOT present:
    # Item No treated as part_number with Prefix
    pn, pos, spec = normalize_spare_part_number_and_position(None, None, "FIG.4", "Item No: 5; Size: 15.5X2.4")
    assert pn == "Item No. 5"
    assert pos is None
    assert spec == "Size: 15.5X2.4"

    # Ref No treated as part_number with Prefix
    pn, pos, spec = normalize_spare_part_number_and_position("REF.NO 12", None, "FIG.4", None)
    assert pn == "Ref No. 12"

    # No. treated as part_number with Prefix
    pn, pos, spec = normalize_spare_part_number_and_position("NO: 3", None, "FIG.4", None)
    assert pn == "No. 3"

    # Serial No treated as part_number with Prefix
    pn, pos, spec = normalize_spare_part_number_and_position("Serial No: 101", None, "FIG.4", None)
    assert pn == "Serial No. 101"

    # When catalog Part Number IS present:
    # Item/Ref moved into specification
    pn, pos, spec = normalize_spare_part_number_and_position("9901-X", "Ref No. 12", "FIG.4", "Material: SUS304")
    assert pn == "9901-X"
    assert pos is None
    assert "Ref No: 12" in spec
    assert "Material: SUS304" in spec


def test_rule3_drawing_no_position_no_combination():
    # When NO catalog Part Number and NO Item/Ref No, combine Drawing No / Position No
    pn, pos, spec = normalize_spare_part_number_and_position(None, "15", "FIG.7", "Material: BRONZE")
    assert pn == "FIG.7/15"
    assert pos == "15"
    assert spec == "Material: BRONZE"

    # If Drawing No missing or Position No missing, do NOT combine
    pn, pos, spec = normalize_spare_part_number_and_position(None, None, "FIG.7", "Material: BRONZE")
    assert pn is None

    # If Item No was captured as part number, do NOT combine Drawing No
    pn, pos, spec = normalize_spare_part_number_and_position("Item No. 8", None, "DWG-99", None)
    assert pn == "Item No. 8"
    assert "DWG-99" not in pn


def test_catalog_part_number_prefix_removal():
    # Normal catalog part numbers must NOT be prefixed with column headers
    cases = [
        ("Part No: 00621141", "00621141"),
        ("Part Number: 00617736", "00617736"),
        ("Part No. 6205-01", "6205-01"),
        ("PC. NO. 6205-01", "6205-01"),
        ("PC NO: 4455", "4455"),
        ("Code No: 12345", "12345"),
        ("Code: 9901-X", "9901-X"),
        ("00621141", "00621141"),
    ]
    for raw_pn, expected_pn in cases:
        pn, pos, spec = normalize_spare_part_number_and_position(raw_pn, "15", "FIG.7", None)
        assert pn == expected_pn, f"Failed for {raw_pn}: got {pn}, expected {expected_pn}"
        assert pos == "15"


def test_pid_item_prefixing_and_cleanup():
    # Fallback P&ID items like BM 005, BO 002 must have header title prefixed
    cases = [
        ("BM 005", "PID Item BM 005"),
        ("BO 002", "PID Item BO 002"),
        ("PID Item BM 090", "PID Item BM 090"),
        ("PID-Item: BM 090", "PID Item BM 090"),
        ("PID Item: BO 007", "PID Item BO 007"),
    ]
    for raw_pn, expected_pn in cases:
        pn, pos, spec = normalize_spare_part_number_and_position(raw_pn, None, None, None)
        assert pn == expected_pn, f"Failed for {raw_pn}: got {pn}, expected {expected_pn}"

    # When part_number was empty and PID Item was leaked into specification with Remarks
    pn, pos, spec = normalize_spare_part_number_and_position(
        None, None, None, "QTY: 2 PCS; Remarks: PID Item BM 090"
    )
    assert pn == "PID Item BM 090"
    assert spec == "QTY: 2 PCS"
    assert "Remarks" not in (spec or "")


def test_specification_remarks_complete_removal():
    # Specification must NEVER contain the keyword 'Remarks:' or remarks notes
    assert _format_specification_headers("QTY: 2 PCS; Remarks: PID Item BM 090") == "QTY: 2 PCS"
    assert _format_specification_headers("Remarks: PID Item BM 090") is None
    assert _format_specification_headers("QTY: 1 SET; Remarks: (USH-20) For pump outlet") == "QTY: 1 SET"
    assert _format_specification_headers("Remarks: Items 7, 8 for blinding") is None
    assert _format_specification_headers("QTY: 2 PCS; Material: STEEL; Remarks: Items 7, 8 for blinding") == "QTY: 2 PCS; Material: STEEL"

    # In normalization
    pn, pos, spec = normalize_spare_part_number_and_position(
        "00621141", "15", "FIG.7", "QTY: 2 PCS; Remarks: Items 7, 8 for blinding"
    )
    assert pn == "00621141"
    assert spec == "QTY: 2 PCS"
    assert "Remarks" not in (spec or "")


@pytest.mark.asyncio
async def test_process_and_save_page_records_default_qty_one():
    from app.services.extractor import _process_and_save_page_records
    from unittest.mock import AsyncMock, MagicMock
    import uuid

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_manual = MagicMock()
    mock_manual.id = uuid.uuid4()
    mock_manual.original_filename = 'test_manual.pdf'
    mock_manual.pages_with_spares = '58-60'
    mock_manual.target_model = None

    records = [
        {'part_name': 'ENCLOSER', 'part_number': 'No. 29', 'specification': None},
        {'part_name': 'SCREW B', 'part_number': 'No. 57', 'specification': 'Material: STEEL'},
        {'part_name': 'BALL BEARING 6202 X2', 'part_number': 'No. 62', 'specification': 'QTY: 2 PCS'},
    ]

    await _process_and_save_page_records(
        db=mock_db,
        page_records=records,
        etype='spare',
        manual=mock_manual,
        all_manual_ids=[mock_manual.id],
        filename='test_manual.pdf',
        vessel_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        vessel_shipyard=None,
        page_no=78,
        extracted_component_context=[],
        existing_manual_component_context=[],
    )

    added_spares = [call[0][0] for call in mock_db.add.call_args_list]
    assert len(added_spares) == 3

    # Record 1: no qty provided -> defaults to QTY: 1 PCS
    assert added_spares[0].part_name == 'Encloser'
    assert added_spares[0].specification == 'QTY: 1 PCS'

    # Record 2: only material provided -> defaults to QTY: 1 PCS; Material: STEEL
    assert added_spares[1].part_name == 'Screw B'
    assert added_spares[1].specification == 'QTY: 1 PCS; Material: STEEL'

    # Record 3: explicit QTY: 2 PCS provided -> preserves QTY: 2 PCS
    assert added_spares[2].part_name == 'Ball Bearing'
    assert 'QTY: 2 PCS' in added_spares[2].specification
