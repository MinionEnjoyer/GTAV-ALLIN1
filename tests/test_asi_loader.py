"""Tests for the ASI loader download and deployment module."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import io
import zipfile

import pytest

from allin1 import asi_loader


def _make_fake_zip(dll_name: str = "dinput8.dll", content: bytes = b"\x00" * 50_000) -> bytes:
    """Create a fake ZIP containing a DLL with the given name."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(dll_name, content)
    return buf.getvalue()


class TestDllName:
    def test_legacy(self):
        assert asi_loader.dll_name(is_enhanced=False) == "dinput8.dll"

    def test_enhanced(self):
        assert asi_loader.dll_name(is_enhanced=True) == "dsound.dll"


class TestEnsure:
    def test_skips_if_dll_exists(self, tmp_path):
        (tmp_path / "dinput8.dll").write_bytes(b"existing")
        status = asi_loader.ensure(tmp_path, is_enhanced=False)
        assert status == "skipped"

    def test_skips_enhanced_if_dll_exists(self, tmp_path):
        (tmp_path / "dsound.dll").write_bytes(b"existing")
        status = asi_loader.ensure(tmp_path, is_enhanced=True)
        assert status == "skipped"

    @patch("allin1.asi_loader.urlopen")
    def test_deploys_legacy(self, mock_urlopen, tmp_path):
        fake_zip = _make_fake_zip("dinput8.dll")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_zip
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure(tmp_path, is_enhanced=False)

        assert status == "deployed"
        assert (tmp_path / "dinput8.dll").exists()
        assert (tmp_path / "dinput8.dll").stat().st_size == 50_000

    @patch("allin1.asi_loader.urlopen")
    def test_deploys_enhanced_as_dsound(self, mock_urlopen, tmp_path):
        fake_zip = _make_fake_zip("dinput8.dll")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_zip
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure(tmp_path, is_enhanced=True)

        assert status == "deployed"
        assert (tmp_path / "dsound.dll").exists()

    @patch("allin1.asi_loader.urlopen")
    def test_network_failure_returns_failed(self, mock_urlopen, tmp_path):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        status = asi_loader.ensure(tmp_path, is_enhanced=False)

        assert status == "failed"
        assert not (tmp_path / "dinput8.dll").exists()

    @patch("allin1.asi_loader.urlopen")
    def test_bad_zip_size_returns_failed(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"tiny"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure(tmp_path, is_enhanced=False)

        assert status == "failed"

    @patch("allin1.asi_loader.urlopen")
    def test_missing_dll_in_zip_returns_failed(self, mock_urlopen, tmp_path):
        # ZIP with wrong filename inside
        fake_zip = _make_fake_zip("wrong.dll")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_zip
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure(tmp_path, is_enhanced=False)

        assert status == "failed"
