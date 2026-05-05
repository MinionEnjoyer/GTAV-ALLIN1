"""Tests for the ASI loader deployment and BattlEye configuration module."""

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


class TestEnsureLoader:
    def test_skips_if_dll_exists(self, tmp_path):
        (tmp_path / "dinput8.dll").write_bytes(b"existing")
        status = asi_loader.ensure_loader(tmp_path, is_enhanced=False)
        assert status == "skipped"

    def test_skips_enhanced_if_dll_exists(self, tmp_path):
        (tmp_path / "dsound.dll").write_bytes(b"existing")
        status = asi_loader.ensure_loader(tmp_path, is_enhanced=True)
        assert status == "skipped"

    @patch("allin1.asi_loader.urlopen")
    def test_deploys_legacy(self, mock_urlopen, tmp_path):
        fake_zip = _make_fake_zip("dinput8.dll")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_zip
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure_loader(tmp_path, is_enhanced=False)

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

        status = asi_loader.ensure_loader(tmp_path, is_enhanced=True)

        assert status == "deployed"
        assert (tmp_path / "dsound.dll").exists()

    @patch("allin1.asi_loader.urlopen")
    def test_network_failure_returns_failed(self, mock_urlopen, tmp_path):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        status = asi_loader.ensure_loader(tmp_path, is_enhanced=False)

        assert status == "failed"
        assert not (tmp_path / "dinput8.dll").exists()

    @patch("allin1.asi_loader.urlopen")
    def test_bad_zip_size_returns_failed(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"tiny"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure_loader(tmp_path, is_enhanced=False)

        assert status == "failed"

    @patch("allin1.asi_loader.urlopen")
    def test_missing_dll_in_zip_returns_failed(self, mock_urlopen, tmp_path):
        fake_zip = _make_fake_zip("wrong.dll")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_zip
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status = asi_loader.ensure_loader(tmp_path, is_enhanced=False)

        assert status == "failed"


# ---------------------------------------------------------------------------
# BattlEye / commandline.txt tests
# ---------------------------------------------------------------------------


class TestSetCommandlineTxt:
    def test_creates_file_when_missing(self, tmp_path):
        status = asi_loader._set_commandline_txt(tmp_path)

        assert status == "set"
        cmdline = tmp_path / "commandline.txt"
        assert cmdline.exists()
        assert "-nobattleye" in cmdline.read_text()

    def test_already_set(self, tmp_path):
        (tmp_path / "commandline.txt").write_text("-nobattleye\n")

        status = asi_loader._set_commandline_txt(tmp_path)
        assert status == "already_set"

    def test_appends_to_existing_flags(self, tmp_path):
        (tmp_path / "commandline.txt").write_text("-windowed\n")

        status = asi_loader._set_commandline_txt(tmp_path)

        assert status == "set"
        text = (tmp_path / "commandline.txt").read_text()
        assert "-windowed" in text
        assert "-nobattleye" in text

    def test_write_failure_returns_failed(self, tmp_path):
        (tmp_path / "commandline.txt").mkdir()
        status = asi_loader._set_commandline_txt(tmp_path)
        assert status == "failed"


# ---------------------------------------------------------------------------
# BattlEye / Steam localconfig.vdf tests
# ---------------------------------------------------------------------------

_SAMPLE_VDF = '''"UserLocalConfigStore"
{
\t"Software"
\t{
\t\t"Valve"
\t\t{
\t\t\t"Steam"
\t\t\t{
\t\t\t\t"apps"
\t\t\t\t{
\t\t\t\t\t"3240220"
\t\t\t\t\t{
\t\t\t\t\t\t"LastPlayed"\t\t"1714900000"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}
'''

_SAMPLE_VDF_WITH_OPTION = _SAMPLE_VDF.replace(
    '"LastPlayed"\t\t"1714900000"',
    '"LastPlayed"\t\t"1714900000"\n\t\t\t\t\t\t\t"LaunchOptions"\t\t"-nobattleye"',
)


class TestExtractLaunchOptions:
    def test_no_launch_options(self):
        assert asi_loader._extract_launch_options(_SAMPLE_VDF, "3240220") is None

    def test_has_launch_options(self):
        assert asi_loader._extract_launch_options(_SAMPLE_VDF_WITH_OPTION, "3240220") == "-nobattleye"

    def test_wrong_appid(self):
        assert asi_loader._extract_launch_options(_SAMPLE_VDF_WITH_OPTION, "271590") is None


class TestSetLaunchOptionsText:
    def test_inserts_into_existing_block(self):
        result = asi_loader._set_launch_options_text(_SAMPLE_VDF, "3240220", "-nobattleye")
        assert result is not None
        assert asi_loader._extract_launch_options(result, "3240220") == "-nobattleye"

    def test_replaces_existing_value(self):
        result = asi_loader._set_launch_options_text(
            _SAMPLE_VDF_WITH_OPTION, "3240220", "-nobattleye -windowed"
        )
        assert result is not None
        assert asi_loader._extract_launch_options(result, "3240220") == "-nobattleye -windowed"

    def test_creates_new_app_block(self):
        result = asi_loader._set_launch_options_text(_SAMPLE_VDF, "271590", "-nobattleye")
        assert result is not None
        assert asi_loader._extract_launch_options(result, "271590") == "-nobattleye"
        assert '"3240220"' in result


class TestPatchLocalconfig:
    def test_sets_option(self, tmp_path):
        vdf = tmp_path / "localconfig.vdf"
        vdf.write_text(_SAMPLE_VDF, encoding="utf-8")

        status = asi_loader._patch_localconfig(vdf, "3240220", "-nobattleye")

        assert status == "set"
        assert "-nobattleye" in vdf.read_text()
        assert (tmp_path / "localconfig.vdf.bak").exists()

    def test_already_set(self, tmp_path):
        vdf = tmp_path / "localconfig.vdf"
        vdf.write_text(_SAMPLE_VDF_WITH_OPTION, encoding="utf-8")

        status = asi_loader._patch_localconfig(vdf, "3240220", "-nobattleye")
        assert status == "already_set"

    def test_appends_to_existing(self, tmp_path):
        vdf_text = _SAMPLE_VDF_WITH_OPTION.replace("-nobattleye", "-windowed")
        vdf = tmp_path / "localconfig.vdf"
        vdf.write_text(vdf_text, encoding="utf-8")

        status = asi_loader._patch_localconfig(vdf, "3240220", "-nobattleye")

        assert status == "set"
        opts = asi_loader._extract_launch_options(vdf.read_text(), "3240220")
        assert "-windowed" in opts
        assert "-nobattleye" in opts


class TestEnsureNobattleye:
    """Integration test: ensure_nobattleye uses both methods."""

    @patch("allin1.asi_loader._set_steam_launch_option", return_value="failed")
    def test_falls_back_to_commandline_txt(self, mock_steam, tmp_path):
        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)

        assert status == "set"
        assert (tmp_path / "commandline.txt").exists()

    @patch("allin1.asi_loader._set_steam_launch_option", return_value="set")
    def test_reports_set_when_steam_succeeds(self, mock_steam, tmp_path):
        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)
        assert status == "set"

    @patch("allin1.asi_loader._set_steam_launch_option", return_value="already_set")
    def test_already_set_both(self, mock_steam, tmp_path):
        (tmp_path / "commandline.txt").write_text("-nobattleye\n")
        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)
        assert status == "already_set"
