from __future__ import annotations

import re
from typing import Iterable, Sequence

SOURCE_HEADER = "Source References:"
_BODY_ACTION_RE = re.compile(r"^\s*(.+?)\s*-\s*(.+?)\s*$")

_ACTION_PHRASES = [
    "back wash",
    "backwash",
    "discharge",
    "clean",
    "cleaning",
    "inspect",
    "inspection",
    "check",
    "replace",
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
_PREPOSITIONS = ("of", "inside", "within", "in", "on", "at")
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
    words = body.split()
    if len(words) > 7:
        body = " ".join(words[:7]).rstrip(" -:/,.;")
    return body


def _normalise_action_label(action: str) -> str:
    key = (action or "").strip().lower()
    return _ACTION_LABELS.get(key, action.title())


def _extract_body_and_actions(text: str | None) -> tuple[list[str], list[str]]:
    cleaned = strip_source_reference_footer(text) or ""
    canonical_match = _BODY_ACTION_RE.match(cleaned)
    if canonical_match:
        canonical_body = _trim_body_text(canonical_match.group(1))
        canonical_actions = _unique_nonempty(
            [_normalise_action_label(part) for part in re.split(r"\s*/\s*", canonical_match.group(2))]
        )
        return _unique_nonempty([canonical_body]), canonical_actions

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:/")
    cleaned = re.sub(r"^(item|step|procedure|job)\s*[\d.()-]*\s*[:\-]?\s*", "", cleaned, flags=re.I)
    if not cleaned:
        return [], []

    lowered = cleaned.lower()
    actions: list[str] = []
    for phrase in _ACTION_PHRASES:
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, lowered):
            actions.append(_normalise_action_label(phrase))

    body = ""
    for phrase in sorted(_ACTION_PHRASES, key=len, reverse=True):
        pattern = re.compile(
            r"^\s*" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b\s*",
            flags=re.I,
        )
        match = pattern.match(cleaned)
        if match:
            body = _trim_body_text(cleaned[match.end():])
            if body:
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
        body = re.sub(r"^(and|/|,|-|\.)+\s*", "", body, flags=re.I)
        body = _trim_body_text(body)

    if not actions and cleaned:
        first_token = _normalise_action_label(cleaned.split(" ", 1)[0].strip(" -:/"))
        if first_token:
            actions = [first_token]

    if not body:
        body = _trim_body_text(cleaned)
    return _unique_nonempty([body]), _unique_nonempty(actions)


def build_canonical_job_name(
    *,
    component_name: str | None,
    job_names: Sequence[str | None] = (),
    job_descriptions: Sequence[str | None] = (),
) -> str:
    component_label = (component_name or "Unmapped Component").strip() or "Unmapped Component"
    name_bodies: list[str] = []
    name_actions: list[str] = []
    for source_text in job_names:
        stripped_name = _strip_component_prefix(source_text, component_label)
        candidate_name = stripped_name if component_name else source_text
        body_parts, action_parts = _extract_body_and_actions(candidate_name)
        name_bodies.extend(body_parts)
        name_actions.extend(action_parts)

    desc_bodies: list[str] = []
    desc_actions: list[str] = []
    for source_text in job_descriptions:
        body_parts, action_parts = _extract_body_and_actions(source_text)
        desc_bodies.extend(body_parts)
        desc_actions.extend(action_parts)

    component_key = _normalise_compare_text(component_label)
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
    body_text = " / ".join(_unique_nonempty(bodies))
    action_text = " / ".join(_unique_nonempty(actions)) or "Maintenance"
    if body_text:
        return f"{component_label} {body_text} - {action_text}"[:500]
    return f"{component_label} - {action_text}"[:500]
