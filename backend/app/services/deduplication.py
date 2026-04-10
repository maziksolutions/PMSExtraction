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


def is_duplicate_spare(new: dict, existing: dict) -> bool:
    """
    F-07 criteria:
    - part_name fuzzy >= 0.88
    - part_number exact match (if both present; if both present and differ → NOT duplicate)
    - Returns True based on criteria
    """
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

    return True
