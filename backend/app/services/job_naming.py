from __future__ import annotations

import re
from typing import Iterable, Sequence

SOURCE_HEADER = "Source References:"
_BODY_ACTION_RE = re.compile(r"^\s*(.+?)\s+-\s+(.+?)\s*$")
_UNMAPPED_PREFIX_RE = re.compile(r"^\s*(?:unmapped component(?:\s*[/,:;|\-]\s*|\s+))*", re.I)

_ACTION_PHRASES = [
    "alignment",
    "tension",
    "back wash",
    "backwash",
    "discharge",
    "clean",
    "cleaning",
    "inspect",
    "inspection",
    "check",
    "replace",
    "install",
    "replenish",
    "overhaul",
    "lubricate",
    "grease",
    "repair",
    "renew",
    "adjust",
    "measure",
    "verify",
    "test",
    "service",
    "flush",
    "drain",
    "monitor",
    "calibrate",
    "tighten",
    "remove",
]
_ACTION_LABELS = {
    "alignment": "Adjustment",
    "tension": "Adjustment",
    "back wash": "Cleaning",
    "backwash": "Cleaning",
    "discharge": "Cleaning",
    "clean": "Cleaning",
    "cleaning": "Cleaning",
    "flush": "Cleaning",
    "drain": "Cleaning",
    "remove": "Cleaning",
    "check": "Inspection",
    "inspect": "Inspection",
    "inspection": "Inspection",
    "verify": "Inspection",
    "test": "Inspection",
    "monitor": "Inspection",
    "measure": "Inspection",
    "calibrate": "Inspection",
    "replace": "Replacement",
    "install": "Replacement",
    "renew": "Replacement",
    "replenish": "Replenishment",
    "overhaul": "Overhaul",
    "service": "Service",
    "lubricate": "Lubrication",
    "grease": "Lubrication",
    "repair": "Repair",
    "adjust": "Adjustment",
    "tighten": "Adjustment",
}
_PREPOSITIONS = ("of",)
_BODY_STOP_PHRASES = (
    " by ",
    " using ",
    " while ",
    " when ",
    " where ",
    " because ",
    " due to ",
    " in order to ",
    " to ",
    " with ",
    " after ",
    " before ",
    " during ",
    " if ",
)
_LEADING_NOISE_PHRASES = (
    "after ",
    "before ",
    "then ",
    "when ",
    "while ",
    "if ",
    "because ",
    "due to ",
    "in order to ",
)
_GENERIC_BODY_TOKENS = {
    "1st",
    "2nd",
    "3rd",
    "4th",
    "5th",
    "6th",
    "7th",
    "8th",
    "9th",
    "10th",
    "all",
    "any",
    "another",
    "other",
    "unmapped",
    "times",
    "time",
    "minute",
    "minutes",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "of",
    "the",
}
_GENERIC_COMPONENT_LABELS = {
    "unmapped",
    "unmapped component",
    "component",
    "unknown component",
}
_REF_RE = re.compile(r"^\s*(.+?)\s*\(p\.(\d+)\)\s*$", re.I)


def _unique_nonempty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _normalise_compare_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _is_component_fragment(value: str | None, component_name: str | None) -> bool:
    value_tokens = _normalise_compare_text(value).split()
    component_tokens = _normalise_compare_text(component_name).split()
    if not value_tokens or not component_tokens:
        return False
    if value_tokens == component_tokens:
        return True
    if len(value_tokens) <= len(component_tokens) and value_tokens == component_tokens[: len(value_tokens)]:
        return True
    return False


def strip_source_reference_footer(text: str | None) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    marker = f"\n\n{SOURCE_HEADER}"
    idx = cleaned.find(marker)
    if idx >= 0:
        cleaned = cleaned[:idx].rstrip()
    return cleaned or None


def _strip_component_prefix(text: str | None, component_name: str | None) -> str:
    cleaned = strip_source_reference_footer(text) or ""
    component = re.sub(r"\s+", " ", (component_name or "").strip())
    cleaned = _UNMAPPED_PREFIX_RE.sub("", cleaned).strip(" -:/,.;")
    if not cleaned or not component:
        return cleaned
    pattern = re.compile(
        r"^\s*(?:"
        + re.escape(component).replace(r"\ ", r"\s+")
        + r"(?:\s*[/,:;|\-]\s*|\s+))*",
        flags=re.I,
    )
    stripped = pattern.sub("", cleaned)
    stripped = stripped.strip(" -:/,.;")
    if _is_component_fragment(stripped, component):
        return ""
    return stripped


def _compact_body_phrase(value: str) -> str:
    body = re.sub(r"\s+", " ", (value or "").strip(" -:/,.;")).strip()
    if not body:
        return ""
    lowered = body.lower()
    for noise in _LEADING_NOISE_PHRASES:
        if lowered.startswith(noise):
            return ""
    body = re.sub(r"^(the|a|an|all|any)\s+", "", body, flags=re.I)
    body = re.sub(r"^(&|and|or)\s+", "", body, flags=re.I)
    body = re.sub(r"^(of|the)\s+", "", body, flags=re.I)
    changed = True
    while changed:
        changed = False
        for phrase in sorted(_ACTION_PHRASES, key=len, reverse=True):
            pattern = re.compile(r"^\s*" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b\s*", flags=re.I)
            updated = pattern.sub("", body)
            if updated != body:
                body = updated
                changed = True
                body = re.sub(r"^(&|and|or)\s+", "", body, flags=re.I)
    body = re.sub(r"\b(?:then|therefore|please|carefully)\b", "", body, flags=re.I)
    body = re.sub(r"\s+", " ", body).strip(" -:/,.;")
    body = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "-", body)

    for stop in (",", ";", ":", " then ", " and then ", " followed by "):
        idx = body.lower().find(stop.strip().lower()) if len(stop.strip()) > 1 else body.find(stop)
        if idx > 0:
            candidate = body[:idx].strip(" -:/,.;")
            if candidate:
                body = candidate
                break

    for connector in (" in the ", " in ", " on the ", " on ", " at the ", " at ", " within "):
        idx = body.lower().find(connector)
        if idx > 0:
            candidate = body[:idx].strip(" -:/,.;")
            if candidate:
                body = candidate
                break

    if " of " in body.lower():
        tail = body.split(" of ", 1)[1].strip(" -:/,.;")
        if tail:
            body = tail

    body = re.sub(r"^(the|a|an)\s+", "", body, flags=re.I)
    body = re.sub(r"^\d+(?:st|nd|rd|th)?\s+", "", body, flags=re.I)
    tokens = [token for token in body.split() if _normalise_compare_text(token) not in _GENERIC_BODY_TOKENS]
    if not tokens:
        return ""
    if len(tokens) > 2:
        tokens = tokens[:2]
    return " ".join(tokens).strip(" -:/,.;")


def _join_body_parts(parts: Sequence[str]) -> str:
    unique_parts = _unique_nonempty(parts)
    if not unique_parts:
        return ""
    if len(unique_parts) == 1:
        return unique_parts[0]
    if len(unique_parts) == 2:
        return f"{unique_parts[0]} and {unique_parts[1]}"
    return ", ".join(unique_parts[:-1]) + f", and {unique_parts[-1]}"


def split_reference_entries(
    *,
    pdf_reference: str | None = None,
    page_reference: int | None = None,
    source_reference: str | None = None,
) -> list[str]:
    entries: list[str] = []
    raw_source = (source_reference or "").strip()
    if raw_source:
        for part in re.split(r";\s*", raw_source):
            part_clean = part.strip().lstrip("-").strip()
            if part_clean and part_clean != SOURCE_HEADER:
                entries.append(part_clean)
    elif pdf_reference:
        entries.append(f"{pdf_reference} (p.{page_reference})" if page_reference else pdf_reference)
    return _unique_nonempty(entries)


def summarize_reference_entries(entries: Sequence[str]) -> tuple[str | None, int | None, str | None]:
    unique_entries = _unique_nonempty(entries)
    if not unique_entries:
        return None, None, None

    pdf_names: list[str] = []
    pages: list[int] = []
    for entry in unique_entries:
        match = _REF_RE.match(entry)
        if match:
            pdf_names.append(match.group(1).strip())
            pages.append(int(match.group(2)))
        else:
            pdf_names.append(entry)

    pdf_reference = "; ".join(_unique_nonempty(pdf_names)) or None
    primary_page = min(pages) if pages else None
    source_reference = "; ".join(unique_entries)
    return pdf_reference, primary_page, source_reference


def append_source_references_to_description(
    description: str | None,
    entries: Sequence[str],
) -> str | None:
    body = strip_source_reference_footer(description)
    unique_entries = _unique_nonempty(entries)
    if not unique_entries:
        return body
    footer = SOURCE_HEADER + "\n" + "\n".join(f"- {entry}" for entry in unique_entries)
    return f"{body}\n\n{footer}" if body else footer


def _trim_body_text(value: str) -> str:
    body = re.sub(r"\s+", " ", (value or "").strip(" -:/,.;")).strip()
    body = re.sub(r"^(the|a|an)\s+", "", body, flags=re.I)
    for stop in _BODY_STOP_PHRASES:
        idx = body.lower().find(stop)
        if idx > 0:
            body = body[:idx].rstrip(" -:/,.;")
            break
    body = body.rstrip(" -:/,.;")
    return _compact_body_phrase(body)


def _normalise_action_label(action: str) -> str:
    key = (action or "").strip().lower()
    return _ACTION_LABELS.get(key, action.title())


def _extract_known_action_labels(text: str | None) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip(" -:/,.;")).strip()
    if not cleaned:
        return []
    labels: list[str] = []
    lowered = cleaned.lower()
    for phrase in sorted(_ACTION_PHRASES, key=len, reverse=True):
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, lowered):
            labels.append(_normalise_action_label(phrase))
    return _unique_nonempty(labels)


def _extract_body_and_actions(text: str | None) -> tuple[list[str], list[str]]:
    cleaned = strip_source_reference_footer(text) or ""
    canonical_match = _BODY_ACTION_RE.match(cleaned)
    if canonical_match:
        canonical_body = _trim_body_text(canonical_match.group(1))
        canonical_actions = _extract_known_action_labels(canonical_match.group(2))
        return _unique_nonempty([canonical_body]), canonical_actions

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:/")
    cleaned = re.sub(r"^(item|step|procedure|job)\s*[\d.()-]*\s*[:\-]?\s*", "", cleaned, flags=re.I)
    if not cleaned:
        return [], []
    if any(cleaned.lower().startswith(prefix) for prefix in _LEADING_NOISE_PHRASES):
        return [], []

    lowered = cleaned.lower()
    actions = _extract_known_action_labels(cleaned)

    body = ""
    for phrase in sorted(_ACTION_PHRASES, key=len, reverse=True):
        pattern = re.compile(
            r"^\s*" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b\s*",
            flags=re.I,
        )
        match = pattern.match(cleaned)
        if match:
            candidate = _trim_body_text(cleaned[match.end():])
            if candidate and not re.match(r"^(?:of|the)\b", candidate, flags=re.I):
                body = candidate
                break

    prep_match = re.search(
        r"\b(?:"
        + "|".join(_PREPOSITIONS)
        + r")\b\s+(.+)$",
        cleaned,
        flags=re.I,
    )
    if not body and prep_match:
        body = _trim_body_text(prep_match.group(1))
    if not body:
        body = cleaned
        for phrase in _ACTION_PHRASES:
            body = re.sub(
                r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b",
                "",
                body,
                flags=re.I,
            )
        body = re.sub(r"^(&|and|or|/|,|-|\.)+\s*", "", body, flags=re.I)
        body = _trim_body_text(body)

    if not actions and cleaned:
        first_token_raw = cleaned.split(" ", 1)[0].strip(" -:/").lower()
        if first_token_raw in _ACTION_LABELS:
            actions = [_normalise_action_label(first_token_raw)]

    if not body:
        body = _trim_body_text(cleaned)
    return _unique_nonempty([body]), _unique_nonempty(actions)


def build_canonical_job_name(
    *,
    component_name: str | None,
    job_names: Sequence[str | None] = (),
    job_descriptions: Sequence[str | None] = (),
) -> str:
    component_label = (component_name or "").strip()
    if _normalise_compare_text(component_label) in _GENERIC_COMPONENT_LABELS:
        component_label = ""
    name_bodies: list[str] = []
    name_actions: list[str] = []
    for source_text in job_names:
        stripped_name = _strip_component_prefix(source_text, component_label)
        candidate_name = stripped_name or (None if component_name else _UNMAPPED_PREFIX_RE.sub("", source_text or "").strip())
        body_parts, action_parts = _extract_body_and_actions(candidate_name)
        name_bodies.extend(body_parts)
        name_actions.extend(action_parts)

    desc_bodies: list[str] = []
    desc_actions: list[str] = []
    for source_text in job_descriptions:
        body_parts, action_parts = _extract_body_and_actions(source_text)
        desc_bodies.extend(body_parts)
        desc_actions.extend(action_parts)

    filtered_name_bodies = [
        body
        for body in _unique_nonempty(name_bodies)
        if _normalise_compare_text(body) and not _is_component_fragment(body, component_label)
    ]
    filtered_desc_bodies = [
        body
        for body in _unique_nonempty(desc_bodies)
        if _normalise_compare_text(body) and not _is_component_fragment(body, component_label)
    ]

    bodies = filtered_name_bodies or filtered_desc_bodies
    actions = _unique_nonempty(name_actions) or _unique_nonempty(desc_actions)
    body_text = _join_body_parts(_unique_nonempty(bodies))
    action_text = " / ".join(_unique_nonempty(actions)) or "Maintenance"
    if component_label and body_text:
        return f"{component_label} {body_text} - {action_text}"[:500]
    if component_label:
        return f"{component_label} - {action_text}"[:500]
    if body_text:
        return f"{body_text} - {action_text}"[:500]
    return f"General maintenance - {action_text}"[:500]
