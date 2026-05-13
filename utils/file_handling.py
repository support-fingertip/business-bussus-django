"""File upload entry-point — Phase 8.1 hardened.

Every upload now passes through ``utils.file_validation.validate_upload``
BEFORE persistence:

  * size cap (default 50 MB, overridable per call site or via the
    ``FILE_UPLOAD_MAX_BYTES`` env var)
  * MIME sniff via ``python-magic`` (with extension fallback if the
    library isn't installed)
  * filename sanitisation — no path traversal, no shell metacharacters

The stored file's path uses the **sanitised** filename, prefixed with
a UUID-shaped directory so two uploads with the same sanitised name
don't collide. The previous behaviour (use the raw, attacker-controlled
``file.name`` directly) is gone.

Operator action
---------------

Install ``python-magic`` and the underlying ``libmagic1`` system
library so MIME sniffing uses content, not extensions. Without it,
the helper falls back to extension-based validation with a WARNING
log — materially weaker (attacker can spoof an extension on a
malicious file).

  * In requirements.txt: ``python-magic``
  * In Dockerfile: ``apt-get install -y libmagic1``
"""

import os
import uuid

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from utils.file_validation import (
    ALLOWED_MIME,
    ValidationError,  # noqa: F401  (re-exported for caller convenience)
    validate_upload,
)


# 50 MB default — chosen to be generous enough not to break existing
# upload flows. Override per call site with the ``max_bytes`` kwarg,
# or globally via the env var.
_DEFAULT_MAX_BYTES = int(
    os.getenv("FILE_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024))
)

# Permissive default kind: combine 'image' + 'doc' MIMEs. Call sites
# that know they only accept images should pass ``kind='image'``
# explicitly for tighter validation.
_PERMISSIVE_MIMES: set[str] = ALLOWED_MIME["image"] | ALLOWED_MIME["doc"]


def _sanitize_org_segment(org_name: str | None) -> str:
    """Make the org-name portion of the path safe for filesystem use.

    The org name comes from a tenant-controlled column; we never trust
    it for filesystem composition without scrubbing.
    """
    raw = (org_name or "public").replace(" ", "_").lower()
    cleaned = "".join(c for c in raw if c.isalnum() or c in "._-")[:64]
    return cleaned or "public"


def _classify(mime: str | None, safe_name: str) -> str:
    """Map a MIME / extension to a coarse 'image' / 'document' / 'video' label."""
    if mime is not None:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime in ALLOWED_MIME["doc"]:
            return "document"
        return "unknown"
    # Fallback: extension-based heuristic.
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext in {"jpg", "jpeg", "png", "gif", "webp"}:
        return "image"
    if ext in {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt"}:
        return "document"
    if ext in {"mp4", "avi", "mkv"}:
        return "video"
    return "unknown"


def _validate_and_path(file, *, org_name: str, kind: str | None, max_bytes: int | None):
    """Run validation and return (mime, safe_name, upload_folder, file_path).

    Shared between upload and update so both paths get the same
    treatment. Raises ValidationError on failure.
    """
    max_b = int(max_bytes or _DEFAULT_MAX_BYTES)
    if kind in (None, "permissive", "any"):
        mime, safe_name = validate_upload(
            file, kind="image", max_bytes=max_b,
            extra_mimes=_PERMISSIVE_MIMES,
        )
    else:
        mime, safe_name = validate_upload(file, kind=kind, max_bytes=max_b)

    org_segment = _sanitize_org_segment(org_name)
    upload_folder = os.path.join("uploads", org_segment, uuid.uuid4().hex)
    file_path = os.path.join(upload_folder, safe_name)
    return mime, safe_name, upload_folder, file_path


def handle_file_upload(file, **kwargs):
    """Validate, store, and report on an uploaded file.

    Args:
        file (UploadedFile): The file to be uploaded.
        kwargs: Recognised keys —
            ``org`` (dict) — organization context (used in storage path).
            ``kind`` (str) — one of ``'image'`` / ``'doc'`` / ``'logo'``
                for per-context strict MIME checks. Default: permissive
                (image + doc MIMEs combined).
            ``max_bytes`` (int) — override the default size cap.

    Returns:
        dict: ``{'type', 'file_path', 'size', 'mime'}``.

    Raises:
        ValidationError: file failed validation. Callers map this to 400.
        Exception: storage backend failure.
    """
    org_dict = kwargs.get("org", {}) or {}
    mime, safe_name, upload_folder, file_path = _validate_and_path(
        file,
        org_name=org_dict.get("name"),
        kind=kwargs.get("kind"),
        max_bytes=kwargs.get("max_bytes"),
    )

    os.makedirs(
        os.path.join(default_storage.location, upload_folder),
        exist_ok=True,
    )
    file.seek(0)  # validate_upload may have left the pointer mid-file
    file_saved_path = default_storage.save(file_path, ContentFile(file.read()))

    return {
        "type": _classify(mime, safe_name),
        "file_path": file_saved_path,
        "size": file.size,
        "mime": mime,
    }


def handle_file_update(file, previous_file_path, **kwargs):
    """Update an existing file with a new file and delete the old one."""
    if not previous_file_path:
        raise Exception({"error": "No previous file path provided"})

    org_dict = kwargs.get("org", {}) or {}
    mime, safe_name, upload_folder, file_path = _validate_and_path(
        file,
        org_name=org_dict.get("name"),
        kind=kwargs.get("kind"),
        max_bytes=kwargs.get("max_bytes"),
    )

    # Validation passed — now delete the old file. (We delete AFTER
    # validating the new one so a bad new upload doesn't leave the
    # caller with no file at all.)
    if default_storage.exists(previous_file_path):
        default_storage.delete(previous_file_path)

    os.makedirs(
        os.path.join(default_storage.location, upload_folder),
        exist_ok=True,
    )
    file.seek(0)
    file_saved_path = default_storage.save(file_path, ContentFile(file.read()))

    return {
        "type": _classify(mime, safe_name),
        "file_path": file_saved_path,
        "mime": mime,
    }


class FileDeletionError(Exception):
    """Custom exception raised when file deletion fails."""


class FileNotFoundError(Exception):
    """Custom exception raised when a file is not found."""


def handle_file_delete(file_path):
    """Delete the file at the given path.

    Args:
        file_path (str): The path to the file to be deleted.

    Raises:
        FileDeletionError: If there is an issue deleting the file.
        FileNotFoundError: If the file does not exist.

    Returns:
        None: If the file is successfully deleted.
    """
    try:
        if not file_path:
            raise FileDeletionError("No file path provided")

        if default_storage.exists(file_path):
            default_storage.delete(file_path)
            if default_storage.exists(file_path):
                raise FileDeletionError("File could not be deleted")
            return

    except FileDeletionError as e:
        raise FileDeletionError(f"Error deleting file: {str(e)}")

    except FileNotFoundError as e:
        raise FileNotFoundError(f"Error: {str(e)}")

    except Exception as e:
        raise Exception(f"An unexpected error occurred: {str(e)}")
