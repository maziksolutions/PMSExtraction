from __future__ import annotations

import re
import string
from difflib import SequenceMatcher
from typing import Optional

# ---------------------------------------------------------------------------
# Maker alias normalisation table
# ---------------------------------------------------------------------------

MAKER_ALIASES: dict[str, str] = {
    # Wärtsilä variants
    "wartsila": "wartsila",
    "wärtsilä": "wartsila",
    "wartsilä": "wartsila",
    "wartsilla": "wartsila",
    "w-nsd": "wartsila",
    "wnsd": "wartsila",
    "wartsila-nsd": "wartsila",
    # MAN variants
    "man": "man",
    "man b&w": "man",
    "man b and w": "man",
    "man bw": "man",
    "man diesel": "man",
    "man diesel & turbo": "man",
    "man diesel and turbo": "man",
    "man es": "man",
    "man energy solutions": "man",
    # ABB
    "abb": "abb",
    "asea brown boveri": "abb",
    # Caterpillar / CAT
    "caterpillar": "caterpillar",
    "cat": "caterpillar",
    # Alfa Laval
    "alfa laval": "alfa laval",
    "alfalaval": "alfa laval",
    # Kongsberg
    "kongsberg": "kongsberg",
    "km": "kongsberg",
    "kongsberg maritime": "kongsberg",
    # Rolls-Royce / Bergen
    "rolls-royce": "rolls-royce",
    "rolls royce": "rolls-royce",
    "bergen": "rolls-royce",
    "bergen engines": "rolls-royce",
    # Mitsubishi
    "mitsubishi": "mitsubishi",
    "mhi": "mitsubishi",
    # Yanmar
    "yanmar": "yanmar",
    # Cummins
    "cummins": "cummins",
    # Sulzer
    "sulzer": "sulzer",
    # SKF
    "skf": "skf",
    # Parker
    "parker": "parker",
    "parker hannifin": "parker",
    # Danfoss
    "danfoss": "danfoss",
    # Hamworthy / Wärtsilä Gas Solutions
    "hamworthy": "hamworthy",
    "hamworthy pumps": "hamworthy",
}

# ---------------------------------------------------------------------------
# Common abbreviation expansions for maritime text
# ---------------------------------------------------------------------------

_ABBREVIATION_MAP: dict[str, str] = {
    r"\bfw\b": "fresh water",
    r"\bsw\b": "sea water",
    r"\bme\b": "main engine",
    r"\bae\b": "auxiliary engine",
    r"\bo/h\b": "overhaul",
    r"\boh\b": "overhaul",
    r"\bpms\b": "planned maintenance system",
    r"\blo\b": "lubricating oil",
    r"\bfo\b": "fuel oil",
    r"\bhfo\b": "heavy fuel oil",
    r"\bmdo\b": "marine diesel oil",
    r"\bmgo\b": "marine gas oil",
    r"\bdo\b": "diesel oil",
    r"\bcw\b": "cooling water",
    r"\blw\b": "low water",
    r"\bhp\b": "high pressure",
    r"\blp\b": "low pressure",
    r"\bpb\b": "pump bearing",
    r"\bvs\b": "valve seat",
    r"\bht\b": "high temperature",
    r"\blt\b": "low temperature",
    r"\bac\b": "air cooler",
    r"\bec\b": "exhaust cooler",
    r"\btc\b": "turbocharger",
    r"\bgb\b": "gear box",
    r"\bpv\b": "pressure valve",
    r"\bsv\b": "safety valve",
    r"\bnrv\b": "non return valve",
}

_ROOT_COMPONENT_ALIASES: dict[str, tuple[str, ...]] = {
    "pump": ("pump", "pumps"),
    "motor": ("motor", "motors"),
    "fan": ("fan", "fans"),
    "blower": ("blower", "blowers"),
    "compressor": ("compressor", "compressors"),
}


def normalise(text: str) -> str:
    """
    Normalise a string for fuzzy comparison:
    - Lowercase
    - Expand common maritime abbreviations
    - Remove punctuation
    - Collapse whitespace
    """
    if not text:
        return ""

    result = text.lower().strip()

    # Expand abbreviations
    for pattern, expansion in _ABBREVIATION_MAP.items():
        result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)

    # Remove punctuation (keep alphanumeric and spaces)
    result = result.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))

    # Collapse whitespace
    result = " ".join(result.split())

    return result


def _normalise_maker(text: str) -> str:
    """Normalise a maker name via alias table, then standard normalise."""
    if not text:
        return ""
    lowered = text.lower().strip()
    # Try alias lookup on the raw lowered text first
    if lowered in MAKER_ALIASES:
        return MAKER_ALIASES[lowered]
    # Try after punctuation removal
    cleaned = re.sub(r"[^\w\s]", " ", lowered)
    cleaned = " ".join(cleaned.split())
    if cleaned in MAKER_ALIASES:
        return MAKER_ALIASES[cleaned]
    # Return normalised version without alias
    return normalise(text)


def _alphanumeric_only(text: str) -> str:
    """Strip everything except letters and digits, lowercase."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _root_component_name(text: str) -> str:
    normalised = normalise(text)
    if not normalised:
        return ""
    tokens = set(normalised.split())
    for root_name, aliases in _ROOT_COMPONENT_ALIASES.items():
        if any(alias in tokens for alias in aliases):
            return root_name
    return ""


# ---------------------------------------------------------------------------
# Core fuzzy similarity
# ---------------------------------------------------------------------------


def fuzzy_similarity(a: str, b: str) -> float:
    """
    Return a similarity ratio in [0.0, 1.0] between two strings using
    difflib.SequenceMatcher.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# F-05: Component deduplication
# ---------------------------------------------------------------------------


def is_duplicate_component(new: dict, existing: dict) -> bool:
    """
    F-05 criteria:
    - component_name fuzzy >= 0.90 (after normalise)
    - maker fuzzy >= 0.85 (after alias normalisation) — excluded if either blank
    - model fuzzy >= 0.90 (alphanumeric only) — excluded if either blank
    - Returns True if name matches AND (maker+model match OR both maker+model are blank)
    """
    # --- component name ---
    new_name = normalise(new.get("component_name", ""))
    ex_name = normalise(existing.get("component_name", ""))
    if not new_name or not ex_name:
        return False

    # --- maker ---
    new_maker_raw = new.get("maker", "") or ""
    ex_maker_raw = existing.get("maker", "") or ""
    new_maker = _normalise_maker(new_maker_raw)
    ex_maker = _normalise_maker(ex_maker_raw)
    maker_present = bool(new_maker) and bool(ex_maker)
    maker_matches = (
        fuzzy_similarity(new_maker, ex_maker) >= 0.85 if maker_present else True
    )

    # --- model ---
    new_model_raw = new.get("model", "") or ""
    ex_model_raw = existing.get("model", "") or ""
    new_model = _alphanumeric_only(new_model_raw)
    ex_model = _alphanumeric_only(ex_model_raw)
    model_present = bool(new_model) and bool(ex_model)
    model_matches = (
        fuzzy_similarity(new_model, ex_model) >= 0.90 if model_present else True
    )

    new_root = _root_component_name(f"{new.get('component_name', '')} {new.get('main_machinery', '')}")
    ex_root = _root_component_name(f"{existing.get('component_name', '')} {existing.get('main_machinery', '')}")

    name_matches = fuzzy_similarity(new_name, ex_name) >= 0.90
    root_maker_model_match = bool(new_root and ex_root and new_root == ex_root and maker_present and model_present and maker_matches and model_matches)

    if not name_matches and not root_maker_model_match:
        return False

    # maker+model must match; if neither is present, treat as matching
    both_blank = (not new_maker and not ex_maker) and (not new_model and not ex_model)
    if both_blank:
        return True  # name match is sufficient when no maker/model to compare

    return maker_matches and model_matches


# ---------------------------------------------------------------------------
# F-06: Job deduplication
# ---------------------------------------------------------------------------


def is_duplicate_job(new: dict, existing: dict) -> bool:
    """
    F-06 criteria:
    - job_name fuzzy >= 0.88
    - frequency within 10% AND same frequency_type (excluded if either record is blank)
    - Returns True if name AND frequency conditions are met
    """
    # --- job name ---
    new_name = normalise(new.get("job_name", ""))
    ex_name = normalise(existing.get("job_name", ""))
    if not new_name or not ex_name:
        return False
    if fuzzy_similarity(new_name, ex_name) < 0.88:
        return False

    # --- frequency ---
    new_freq = new.get("frequency")
    ex_freq = existing.get("frequency")
    new_ftype = (new.get("frequency_type") or "").strip().lower()
    ex_ftype = (existing.get("frequency_type") or "").strip().lower()

    freq_present = (new_freq is not None and new_freq != "") and (
        ex_freq is not None and ex_freq != ""
    )

    if freq_present:
        try:
            nf = float(new_freq)
            ef = float(ex_freq)
        except (TypeError, ValueError):
            freq_present = False

        if freq_present:
            # Must be same frequency_type
            if new_ftype != ex_ftype:
                return False
            # Within 10%
            if ef == 0:
                freq_matches = nf == 0
            else:
                freq_matches = abs(nf - ef) / abs(ef) <= 0.10
            if not freq_matches:
                return False

    return True


# ---------------------------------------------------------------------------
# F-07: Spare deduplication
# ---------------------------------------------------------------------------


def extract_spare_model_heading(spare_or_record: object) -> str:
    """
    Extracts the normalized model heading from a Spare object or extraction record dictionary.
    Priority:
    1. spare_model
    2. machinery_model
    3. Model identifier detected in spare_assembly / table heading (e.g. 'HVV-2.5', 'HVV-3')
    """
    if isinstance(spare_or_record, dict):
        model = str(spare_or_record.get("spare_model") or "").strip()
        if not model:
            model = str(spare_or_record.get("machinery_model") or "").strip()
        assembly = str(spare_or_record.get("spare_assembly") or "").strip()
    else:
        model = str(getattr(spare_or_record, "spare_model", "") or "").strip()
        if not model:
            model = str(getattr(spare_or_record, "machinery_model", "") or "").strip()
        assembly = str(getattr(spare_or_record, "spare_assembly", "") or "").strip()

    if model:
        norm = model.upper()
        for prefix in ("MODEL:", "TYPE:", "MODEL ", "TYPE "):
            if norm.startswith(prefix):
                norm = norm[len(prefix):].strip()
        return norm

    if assembly:
        # Match 'KIT <MODEL>' e.g. 'KIT HVV-2.5', 'KIT HVV-3'
        m_kit = re.search(r'\bKIT\s+([A-Z0-9]+(?:[-/.][A-Z0-9]+)*)', assembly, re.IGNORECASE)
        if m_kit:
            return m_kit.group(1).upper()
        # Match standalone model patterns like 'HVV-2.5', '6EY18ALW', 'DK-20'
        m_pattern = re.search(r'\b([0-9]*[A-Z]{2,}[0-9A-Z]*(?:[-/][A-Z0-9.]+)?)\b', assembly)
        if m_pattern:
            return m_pattern.group(1).upper()

    return ""


def is_duplicate_spare(new: dict, existing: dict) -> bool:
    """
    F-07 criteria:
    - part_name fuzzy >= 0.88
    - part_number exact match (if both present; if both present and differ → NOT duplicate)
    - model heading match: if both belong to different model headings → NOT duplicate!
    - page match: spares from different pages are NOT duplicates!
    - assembly/kit match: spares from different assemblies or kits are NOT duplicates!
    - drawing position match: spares with different drawing positions are NOT duplicates!
    - drawing number match: spares with different drawing numbers are NOT duplicates!
    - manual match: spares from different manuals are NOT duplicates!
    - Returns True based on criteria
    """
    # --- source manual check ---
    m_new = new.get("source_manual_id") or new.get("manual_id")
    m_ex = existing.get("source_manual_id") or existing.get("manual_id")
    if m_new is not None and m_ex is not None and str(m_new).strip() != str(m_ex).strip():
        return False

    # --- page reference check: spares on different pages are NOT duplicates ---
    page_new = new.get("page_reference") or new.get("source_page_number") or new.get("page_number")
    page_ex = existing.get("page_reference") or existing.get("source_page_number") or existing.get("page_number")
    if page_new is not None and page_ex is not None and str(page_new).strip() != str(page_ex).strip():
        return False

    # --- assembly / kit check: spares in different assemblies or kits are NOT duplicates ---
    assy_new = (new.get("spare_assembly") or "").strip().lower()
    assy_ex = (existing.get("spare_assembly") or "").strip().lower()
    if assy_new and assy_ex and assy_new != assy_ex:
        return False

    # --- drawing position check: spares with differing drawing positions are NOT duplicates ---
    pos_new = (new.get("drawing_position") or "").strip().lower()
    pos_ex = (existing.get("drawing_position") or "").strip().lower()
    if pos_new and pos_ex and pos_new != pos_ex:
        return False

    # --- drawing number check ---
    dwg_new = (new.get("drawing_number") or "").strip().upper()
    dwg_ex = (existing.get("drawing_number") or "").strip().upper()
    if dwg_new and dwg_ex and dwg_new != dwg_ex:
        return False

    # --- part name ---
    new_name = normalise(new.get("part_name", ""))
    ex_name = normalise(existing.get("part_name", ""))
    if not new_name or not ex_name:
        return False
    if fuzzy_similarity(new_name, ex_name) < 0.88:
        return False

    # --- part number ---
    new_pn = (new.get("part_number") or "").strip().upper()
    ex_pn = (existing.get("part_number") or "").strip().upper()

    both_present = bool(new_pn) and bool(ex_pn)
    if both_present:
        # If both have part numbers and they differ → definitely not a duplicate
        if new_pn != ex_pn:
            return False

    # --- model heading check ---
    m_new = extract_spare_model_heading(new)
    m_ex = extract_spare_model_heading(existing)
    if m_new and m_ex and m_new != m_ex:
        return False
    if bool(m_new) != bool(m_ex):
        return False

    return True
