from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath

from fastapi import HTTPException, status

from app.core.config import settings


MAX_ARCHIVE_ENTRIES = 2048
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

PDF_MAGIC = b"%PDF-"
OLE_MAGIC = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
ZIP_MAGIC_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
SUSPICIOUS_PDF_MARKERS = (
    b"/javascript",
    b"/js",
    b"/launch",
    b"/richmedia",
    b"/embeddedfile",
    b"/openaction",
)


def _raise(detail: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _validate_zip_office_document(content: bytes, *, expected_root: str, filename: str) -> None:
    if not content.startswith(ZIP_MAGIC_PREFIXES):
        _raise(f"File '{filename}' is not a valid Office Open XML document.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except Exception as exc:
        _raise(f"File '{filename}' could not be opened safely: {exc}")

    with archive:
        entries = archive.infolist()
        if not entries:
            _raise(f"File '{filename}' is empty.")
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            _raise(f"File '{filename}' contains too many embedded archive entries.")

        total_uncompressed = 0
        has_content_types = False
        has_expected_root = False
        for info in entries:
            name = info.filename or ""
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                _raise(f"File '{filename}' contains unsafe embedded paths.")
            if info.flag_bits & 0x1:
                _raise(f"File '{filename}' is encrypted and cannot be accepted.")
            total_uncompressed += max(0, info.file_size)
            if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                _raise(f"File '{filename}' expands beyond the safe archive limit.")
            compressed = max(1, info.compress_size)
            if info.file_size > compressed * MAX_COMPRESSION_RATIO:
                _raise(f"File '{filename}' appears to have an unsafe compression ratio.")
            lower_name = name.lower()
            if lower_name == "[content_types].xml":
                has_content_types = True
            if lower_name.startswith(f"{expected_root}/"):
                has_expected_root = True
            if lower_name.endswith("vbaproject.bin"):
                _raise(f"File '{filename}' contains embedded macros and is not allowed.")
            if lower_name.endswith(".rels"):
                try:
                    rels_data = archive.read(info)
                except Exception as exc:
                    _raise(f"File '{filename}' contains unreadable relationship metadata: {exc}")
                if b'targetmode="external"' in rels_data.lower():
                    _raise(f"File '{filename}' contains unsafe external document links.")

        if not has_content_types or not has_expected_root:
            _raise(f"File '{filename}' is not a supported {expected_root.upper()} workbook/document.")


def _validate_pdf_document(content: bytes, *, filename: str) -> None:
    if not content.startswith(PDF_MAGIC):
        _raise(f"File '{filename}' is not a valid PDF.")

    lowered = content[:2_000_000].lower()
    for marker in SUSPICIOUS_PDF_MARKERS:
        if marker in lowered:
            _raise(f"File '{filename}' contains active PDF content and is not allowed.")


def validate_uploaded_file_bytes(
    *,
    filename: str,
    content: bytes,
    allowed_extensions: set[str],
    max_size_bytes: int,
) -> str:
    safe_name = filename or "uploaded-file"
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""

    if ext not in allowed_extensions:
        _raise(
            f"File '{safe_name}' has unsupported extension '.{ext}'. Allowed: {', '.join(sorted(allowed_extensions))}"
        )
    if not content:
        _raise(f"File '{safe_name}' is empty.")
    if len(content) > max_size_bytes:
        _raise(f"File '{safe_name}' exceeds the allowed size limit.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    if ext == "pdf":
        _validate_pdf_document(content, filename=safe_name)
    elif ext in {"docx", "xlsx"}:
        _validate_zip_office_document(
            content,
            expected_root="word" if ext == "docx" else "xl",
            filename=safe_name,
        )
    elif ext in {"doc", "xls"}:
        if settings.REQUIRE_STRICT_UPLOAD_VALIDATION:
            _raise(
                f"Legacy Office file '{safe_name}' is not accepted in secure mode. "
                "Please convert it to DOCX, XLSX, or PDF before upload."
            )
        if not content.startswith(OLE_MAGIC):
            _raise(f"File '{safe_name}' is not a valid legacy Office document.")
    elif ext == "csv":
        if b"\x00" in content:
            _raise(f"File '{safe_name}' contains unexpected binary data.")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            _raise(f"File '{safe_name}' must be UTF-8 encoded CSV.")

    return ext
