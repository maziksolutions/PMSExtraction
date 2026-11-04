import pytest
from app.services.extractor import separate_spare_name_and_spec


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
