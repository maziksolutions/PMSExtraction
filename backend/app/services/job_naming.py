from __future__ import annotations

import re
from typing import Iterable, Sequence

SOURCE_HEADER = "Source References:"

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
_PREPOSITIONS = ("from", "of", "inside", "within", "in", "on", "at", "for")
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


def strip_source_reference_footer(text: str | None) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    marker = f"\n\n{SOURCE_HEADER}"
    idx = cleaned.find(marker)
    if idx >= 0:
        cleaned = cleaned[:idx].rstrip()
    return cleaned or None


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


def _extract_body_and_actions(text: str | None) -> tuple[list[str], list[str]]:
    cleaned = strip_source_reference_footer(text) or ""
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:/")
    if not cleaned:
        return [], []

    lowered = cleaned.lower()
    actions: list[str] = []
    for phrase in _ACTION_PHRASES:
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, lowered):
            actions.append(phrase.title())

    body = ""
    prep_match = re.search(
        r"\b(?:"
        + "|".join(_PREPOSITIONS)
        + r")\b\s+(.+)$",
        cleaned,
        flags=re.I,
    )
    if prep_match:
        body = prep_match.group(1).strip(" -:/")
    else:
        body = cleaned
        for phrase in _ACTION_PHRASES:
            body = re.sub(
                r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b",
                "",
                body,
                flags=re.I,
            )
        body = re.sub(r"^(and|/|,|-|\.)+\s*", "", body, flags=re.I)
        body = re.sub(r"\s+", " ", body).strip(" -:/")

    if not actions and cleaned:
        first_token = cleaned.split(" ", 1)[0].strip(" -:/").title()
        if first_token:
            actions = [first_token]

    if not body:
        body = cleaned
    return _unique_nonempty([body]), _unique_nonempty(actions)


def build_canonical_job_name(
    *,
    component_name: str | None,
    job_names: Sequence[str | None] = (),
    job_descriptions: Sequence[str | None] = (),
) -> str:
    component_label = (component_name or "Unmapped Component").strip() or "Unmapped Component"
    bodies: list[str] = []
    actions: list[str] = []
    for source_text in [*job_names, *job_descriptions]:
        body_parts, action_parts = _extract_body_and_actions(source_text)
        bodies.extend(body_parts)
        actions.extend(action_parts)
    body_text = " / ".join(_unique_nonempty(bodies)) or "General maintenance"
    action_text = " / ".join(_unique_nonempty(actions)) or "Maintenance"
    return f"{component_label} - {body_text} - {action_text}"[:500]
