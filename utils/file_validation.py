"""File upload validation — Phase 8.1.

Centralised helper for validating uploaded files BEFORE they're
persisted. The BL layer (``api/BL/blcontroller.py`` ~line 2820 and
similar sites) historically called ``handle_file_upload(request.FILES.get('file'))``
with no validation; SECURITY_AUDIT_REPORT flagged this as HIGH —
no size cap, no MIME check, no filename sanitisation, no virus scan.

This module ships:

  1. :func:`validate_upload` — size + MIME + sanitised filename
  2. :data:`ALLOWED_MIME` — per-context MIME allow-list (extensible)
  3. :data:`MAX_BYTES` — default size cap (10 MB, overridable)

Phase 8.2 (virus scan) plugs into the same function via a hook —
see the TODO comment in :func:`validate_upload`.

Why ``python-magic`` (content sniffing) instead of trusting Content-Type?
------------------------------------------------------------------------

The browser-supplied ``Content-Type`` is attacker-controlled. A
malicious caller can claim ``image/png`` while shipping a PE32
binary. ``python-magic`` reads the first few KB of the file and
identifies it by content signature (the same way Unix's ``file``
command does) — far harder to spoof.

If ``python-magic`` is not installed (it depends on libmagic), the
function falls back to extension-only validation with a warning
log. That's deliberately weaker so the developer fixes the
environment rather than getting a silent green light.

Usage
-----

    from utils.file_validation import validate_upload, ValidationError

    try:
        mime, safe_name = validate_upload(
            request.FILES["file"],
            kind="image",      # or "doc"
            max_bytes=5 * 1024 * 1024,  # 5 MB override
        )
    except ValidationError as e:
        return Response({"error": str(e)}, status=400)

    # Persist under a UUID-prefixed path, NOT the user-supplied filename
    storage_path = f"tenants/{ctx.org_id}/uploads/{uuid.uuid4()}/{safe_name}"
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# Default 10 MB. Override per call site for stricter (logos: 1 MB)
# or looser (exports: 100 MB) contexts.
MAX_BYTES: int = 10 * 1024 * 1024


# MIME-type allow-lists, keyed by upload "kind". Add new kinds by
# extending this dict — keeping the list central makes it
# reviewable from one place.
ALLOWED_MIME: dict[str, set[str]] = {
    "image": {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    },
    "doc": {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "text/plain",
    },
    "logo": {  # tighter than 'image' — no GIF (animated logos are noisy)
        "image/jpeg",
        "image/png",
        "image/svg+xml",
    },
}


# Filename sanitisation: keep alnum + dot + dash + underscore. Strip
# everything else (paths, control chars, unicode tricks). Cap at 255
# chars (most filesystems' upper bound).
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


class ValidationError(ValueError):
    """File failed upload validation — caller should return 400 to client."""


def _detect_mime(uploaded_file) -> Optional[str]:
    """Detect the MIME type by sniffing the file content.

    Returns None if ``python-magic`` isn't installed; callers fall
    back to extension-based validation in that case.
    """
    try:
        import magic  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "validate_upload: python-magic not installed — falling back to "
            "extension-only validation. Install python-magic + libmagic1 "
            "in your Dockerfile for content-based MIME sniffing."
        )
        return None

    head = uploaded_file.read(2048)
    # Restore the file pointer so the caller can re-read the contents.
    uploaded_file.seek(0)
    return magic.from_buffer(head, mime=True)


def sanitize_filename(original: str, max_len: int = 200) -> str:
    """Strip path components and unsafe chars from a user-supplied filename.

    Returns a safe basename; never includes path separators or control
    chars. Caller is still responsible for storing under a UUID-prefixed
    path so two uploads with the same sanitised name don't collide.
    """
    # Strip directory components (anything before the last slash/backslash)
    base = Path(original).name
    # Sanitise to alnum + dot + dash + underscore
    cleaned = _SAFE_NAME_RE.sub("_", base)
    # Cap length (preserve extension where possible)
    if len(cleaned) > max_len:
        stem, dot, ext = cleaned.rpartition(".")
        if dot:
            # Trim the stem, keep the extension
            cleaned = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:max_len]
    return cleaned or "unnamed"


def validate_upload(
    uploaded_file,
    *,
    kind: str = "image",
    max_bytes: int = MAX_BYTES,
    extra_mimes: Optional[set[str]] = None,
) -> Tuple[Optional[str], str]:
    """Validate ``uploaded_file`` against size + MIME + filename rules.

    Parameters
    ----------
    uploaded_file
        Django ``UploadedFile`` (e.g. ``request.FILES["file"]``).
    kind
        Key into :data:`ALLOWED_MIME`. Use ``"image"`` for general images,
        ``"doc"`` for document uploads, ``"logo"`` for org logos.
    max_bytes
        Override the default :data:`MAX_BYTES`. Reject files larger
        than this.
    extra_mimes
        Optional extra MIMEs accepted for this specific call site.
        Combined (UNION) with the per-kind allow-list.

    Returns
    -------
    (detected_mime, safe_filename)
        ``detected_mime`` is None when ``python-magic`` is not installed
        (extension-only validation took place).

    Raises
    ------
    ValidationError
        Size exceeded, MIME not on the allow-list, missing filename,
        empty file, or unknown ``kind``.
    """
    if uploaded_file is None:
        raise ValidationError("No file provided.")

    if kind not in ALLOWED_MIME:
        raise ValidationError(f"Unknown upload kind: {kind!r}")

    # 1. Size check (cheap — get this out of the way first)
    if not uploaded_file.size:
        raise ValidationError("Uploaded file is empty.")
    if uploaded_file.size > max_bytes:
        raise ValidationError(
            f"File too large: {uploaded_file.size} bytes "
            f"(max {max_bytes} bytes)."
        )

    # 2. MIME sniffing (content-based, not extension-based)
    allowed_mimes = ALLOWED_MIME[kind] | (extra_mimes or set())
    detected = _detect_mime(uploaded_file)
    if detected is not None:
        if detected not in allowed_mimes:
            raise ValidationError(
                f"File content type {detected!r} is not allowed for kind "
                f"{kind!r}. Allowed: {sorted(allowed_mimes)}."
            )
    else:
        # Fallback: validate by extension. This is materially weaker;
        # log a WARNING so monitoring catches a misconfigured image.
        ext = Path(uploaded_file.name or "").suffix.lower().lstrip(".")
        ext_to_mime_hint = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "pdf": "application/pdf",
            "doc": "application/msword", "docx": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "xls": "application/vnd.ms-excel", "xlsx": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "csv": "text/csv", "txt": "text/plain", "svg": "image/svg+xml",
        }
        hinted = ext_to_mime_hint.get(ext)
        if hinted is None or hinted not in allowed_mimes:
            raise ValidationError(
                f"Extension {ext!r} not allowed for kind {kind!r}. "
                f"(MIME sniffer unavailable; install python-magic for stronger checks.)"
            )

    # 3. Filename sanitisation
    safe_name = sanitize_filename(uploaded_file.name or "unnamed")

    # 4. TODO Phase 8.2 — virus scan hook. Plug ClamAV / AWS GuardDuty
    # Malware Protection / Azure Defender for Storage here. On positive
    # detection, raise ValidationError so the file never persists.
    # virus_scan(uploaded_file)

    return detected, safe_name
