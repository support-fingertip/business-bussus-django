"""Tests for utils.file_handling — verify validate_upload is wired in.

Distinct from tests/security/test_file_validation.py which exercises
validate_upload itself. These verify that handle_file_upload routes
every upload through validation BEFORE persistence.
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.unit


class _StubUpload:
    """Minimal Django UploadedFile stand-in."""

    def __init__(self, content: bytes, name: str = "upload.png"):
        self._buf = io.BytesIO(content)
        self.size = len(content)
        self.name = name

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def seek(self, pos: int) -> None:
        self._buf.seek(pos)


def _ensure_django():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


class TestValidationGatesUpload:
    def test_oversized_file_rejected_before_storage(self, monkeypatch):
        _ensure_django()
        from utils import file_handling
        from utils.file_validation import ValidationError

        # Pretend python-magic isn't around so fallback extension check runs
        monkeypatch.setattr(
            "utils.file_validation._detect_mime", lambda f: None
        )
        big = _StubUpload(b"X" * 100, name="image.png")

        with patch("utils.file_handling.default_storage") as fake_storage:
            with pytest.raises(ValidationError, match="too large"):
                file_handling.handle_file_upload(big, max_bytes=10)
            # If validation raises, storage MUST NOT have been touched
            fake_storage.save.assert_not_called()

    def test_path_traversal_filename_sanitised_before_storage(self, monkeypatch):
        _ensure_django()
        from utils import file_handling

        # Permissive monkey-patch: bypass MIME sniffing
        monkeypatch.setattr(
            "utils.file_validation._detect_mime", lambda f: "image/png"
        )
        evil = _StubUpload(b"\x89PNG", name="../../etc/passwd.png")

        with patch("utils.file_handling.default_storage") as fake_storage, \
             patch("utils.file_handling.os.makedirs"):
            fake_storage.save.return_value = "saved/path.png"
            fake_storage.location = "/tmp"
            file_handling.handle_file_upload(evil, org={"name": "acme"})

            # Whatever path got passed to storage.save MUST NOT contain
            # the traversal segments — sanitization stripped them.
            stored_path = fake_storage.save.call_args.args[0]
            assert "../" not in stored_path
            assert ".." not in stored_path.split(os.sep)
            # The sanitised basename appears at the end
            assert stored_path.endswith("passwd.png")

    def test_empty_file_rejected(self, monkeypatch):
        _ensure_django()
        from utils import file_handling
        from utils.file_validation import ValidationError

        monkeypatch.setattr(
            "utils.file_validation._detect_mime", lambda f: "image/png"
        )
        with pytest.raises(ValidationError, match="empty"):
            file_handling.handle_file_upload(_StubUpload(b"", name="x.png"))

    def test_org_name_in_path_sanitised(self, monkeypatch):
        _ensure_django()
        from utils import file_handling

        monkeypatch.setattr(
            "utils.file_validation._detect_mime", lambda f: "image/png"
        )
        upload = _StubUpload(b"\x89PNG", name="logo.png")

        with patch("utils.file_handling.default_storage") as fake_storage, \
             patch("utils.file_handling.os.makedirs"):
            fake_storage.save.return_value = "saved/path.png"
            fake_storage.location = "/tmp"
            file_handling.handle_file_upload(
                upload,
                org={"name": "acme/../malicious; rm -rf"},
            )
            stored_path = fake_storage.save.call_args.args[0]
            # No shell metas, no path traversal in the path
            for bad in (";", "..", " "):
                assert bad not in stored_path
