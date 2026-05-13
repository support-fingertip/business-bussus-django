"""Tests for utils.file_validation — Phase 8.1.

Verify size / MIME / filename behaviour. Uses an in-memory file
stand-in so no Django dependency is required for the simple cases.
"""

from __future__ import annotations

import io

import pytest


pytestmark = pytest.mark.unit


class _StubUpload:
    """Mimics Django's UploadedFile API for the bits we use."""

    def __init__(self, content: bytes, name: str = "upload.bin"):
        self._buf = io.BytesIO(content)
        self.size = len(content)
        self.name = name

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def seek(self, pos: int) -> None:
        self._buf.seek(pos)


class TestSizeCheck:
    def test_empty_file_rejected(self):
        from utils.file_validation import validate_upload, ValidationError
        with pytest.raises(ValidationError, match="empty"):
            validate_upload(_StubUpload(b""), kind="image")

    def test_oversized_file_rejected(self):
        from utils.file_validation import validate_upload, ValidationError
        big = _StubUpload(b"X" * 50, name="x.png")
        with pytest.raises(ValidationError, match="too large"):
            validate_upload(big, kind="image", max_bytes=10)

    def test_none_file_rejected(self):
        from utils.file_validation import validate_upload, ValidationError
        with pytest.raises(ValidationError, match="No file"):
            validate_upload(None, kind="image")


class TestKindCheck:
    def test_unknown_kind_rejected(self):
        from utils.file_validation import validate_upload, ValidationError
        with pytest.raises(ValidationError, match="Unknown upload kind"):
            validate_upload(_StubUpload(b"x"), kind="weird_kind")


class TestFilenameSanitisation:
    def test_path_traversal_stripped(self):
        from utils.file_validation import sanitize_filename
        assert sanitize_filename("../../etc/passwd") == "passwd"
        # Backslash variant
        assert sanitize_filename("..\\..\\etc\\passwd") == ".._.._etc_passwd" or \
               sanitize_filename("..\\..\\etc\\passwd").endswith("passwd")

    def test_unsafe_chars_replaced(self):
        from utils.file_validation import sanitize_filename
        out = sanitize_filename("hello world; rm -rf /.txt")
        # No spaces, no shell metacharacters in result
        for bad in (" ", ";", "/", "\x00"):
            assert bad not in out

    def test_extension_preserved_on_truncate(self):
        from utils.file_validation import sanitize_filename
        long_name = "A" * 500 + ".png"
        out = sanitize_filename(long_name, max_len=50)
        assert len(out) <= 50
        assert out.endswith(".png")

    def test_empty_falls_back_to_unnamed(self):
        from utils.file_validation import sanitize_filename
        assert sanitize_filename("") == "unnamed"


class TestExtensionFallback:
    """When python-magic isn't available we fall back to extension."""

    def test_known_extension_accepted_in_fallback(self, monkeypatch):
        from utils import file_validation

        # Force the magic-import to fail so the fallback path runs
        monkeypatch.setattr(file_validation, "_detect_mime", lambda f: None)
        mime, name = file_validation.validate_upload(
            _StubUpload(b"fakepngcontent", name="logo.png"), kind="image"
        )
        assert mime is None  # fallback path returned no detected MIME
        assert name == "logo.png"

    def test_unknown_extension_rejected_in_fallback(self, monkeypatch):
        from utils import file_validation

        monkeypatch.setattr(file_validation, "_detect_mime", lambda f: None)
        with pytest.raises(file_validation.ValidationError):
            file_validation.validate_upload(
                _StubUpload(b"x", name="malware.exe"), kind="image"
            )
