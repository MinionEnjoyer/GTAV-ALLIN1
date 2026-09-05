"""Tests for the consent-based third-party RPF dependency installer."""

from __future__ import annotations

import hashlib
import io
import json
import struct
import urllib.error
import zipfile
from pathlib import Path

import pytest

from allin1 import rpf_loader


def _pe_bytes(size: int = 4096) -> bytes:
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    return bytes(payload)


def _zip(member: str, payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, payload)
    return output.getvalue()


def _asset(provider: str, member: str, payload: bytes) -> rpf_loader.ReleaseAsset:
    return rpf_loader.ReleaseAsset(
        provider=provider,
        version="test",
        url=f"https://github.com/example/{provider}/release.zip",
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        member=member,
        release_page="https://github.com/example/releases/test",
        source_url="https://github.com/example/source",
    )


def _sources(monkeypatch):
    plugin_zip = _zip("RageOpenV.asi", _pe_bytes())
    asi_zip = _zip("dinput8.dll", _pe_bytes(5000))
    plugin = _asset("RageOpenV", "RageOpenV.asi", plugin_zip)
    asi = _asset("Ultimate ASI Loader", "dinput8.dll", asi_zip)
    monkeypatch.setattr(rpf_loader, "RAGEOPENV_ASSET", plugin)
    monkeypatch.setattr(rpf_loader, "ULTIMATE_ASI_ASSET", asi)
    payloads = {plugin.provider: plugin_zip, asi.provider: asi_zip}
    return plugin, asi, lambda asset: payloads[asset.provider]


@pytest.mark.parametrize(
    ("enhanced", "game_exe", "asi_name"),
    ((False, "GTA5.exe", "dinput8.dll"),
     (True, "GTA5_Enhanced.exe", "xinput1_4.dll")),
)
def test_installs_verified_rageopenv_and_owned_asi_loader(
    tmp_path, monkeypatch, enhanced, game_exe, asi_name,
):
    (tmp_path / game_exe).touch()
    _plugin, _asi, download = _sources(monkeypatch)

    result = rpf_loader.install_recommended_rpf_loader(
        tmp_path, enhanced, download=download,
    )

    assert [path.name for path in result.installed] == ["RageOpenV.asi", asi_name]
    assert rpf_loader.inspect_rpf_loader(tmp_path, enhanced).ready is True
    receipt = json.loads(
        (tmp_path / rpf_loader.RECEIPT_RELATIVE).read_text(encoding="utf-8")
    )
    assert receipt["managed_by"] == "ALLIN1"
    assert [entry["path"] for entry in receipt["files"]] == [
        "RageOpenV.asi", asi_name,
    ]

    removed = rpf_loader.uninstall_managed_rpf_loader(tmp_path)

    assert {path.name for path in removed} == {"RageOpenV.asi", asi_name}
    assert not (tmp_path / rpf_loader.RECEIPT_RELATIVE).exists()


def test_reuses_existing_valid_asi_loader_without_claiming_it(tmp_path, monkeypatch):
    (tmp_path / "GTA5_Enhanced.exe").touch()
    (tmp_path / "dsound.dll").write_bytes(_pe_bytes())
    _plugin, _asi, download = _sources(monkeypatch)

    result = rpf_loader.install_recommended_rpf_loader(
        tmp_path, True, download=download,
    )

    assert [path.name for path in result.installed] == ["RageOpenV.asi"]
    assert result.asi_loader.name == "dsound.dll"
    receipt = json.loads(
        (tmp_path / rpf_loader.RECEIPT_RELATIVE).read_text(encoding="utf-8")
    )
    assert [entry["path"] for entry in receipt["files"]] == ["RageOpenV.asi"]


def test_refuses_checksum_mismatch_without_mutating_game(tmp_path, monkeypatch):
    plugin, _asi, download = _sources(monkeypatch)
    monkeypatch.setattr(
        rpf_loader,
        "RAGEOPENV_ASSET",
        rpf_loader.ReleaseAsset(
            **{**plugin.__dict__, "sha256": "0" * 64}
        ),
    )

    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="SHA-256"):
        rpf_loader.install_recommended_rpf_loader(
            tmp_path, True, download=download,
        )

    assert not (tmp_path / "RageOpenV.asi").exists()
    assert not (tmp_path / "xinput1_4.dll").exists()


def test_refuses_to_overwrite_or_mix_existing_plugin(tmp_path, monkeypatch):
    (tmp_path / "OpenIV.asi").write_bytes(_pe_bytes())
    _plugin, _asi, download = _sources(monkeypatch)

    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="resolved manually"):
        rpf_loader.install_recommended_rpf_loader(
            tmp_path, True, download=download,
        )

    assert not (tmp_path / "RageOpenV.asi").exists()


def test_uninstall_preserves_managed_file_modified_after_install(tmp_path, monkeypatch):
    _plugin, _asi, download = _sources(monkeypatch)
    rpf_loader.install_recommended_rpf_loader(
        tmp_path, False, download=download,
    )
    (tmp_path / "RageOpenV.asi").write_bytes(_pe_bytes(6000))

    removed = rpf_loader.uninstall_managed_rpf_loader(tmp_path)

    assert (tmp_path / "RageOpenV.asi").exists()
    assert (tmp_path / "dinput8.dll") in removed
    receipt = json.loads(
        (tmp_path / rpf_loader.RECEIPT_RELATIVE).read_text(encoding="utf-8")
    )
    assert [entry["path"] for entry in receipt["files"]] == ["RageOpenV.asi"]


def test_status_accepts_legacy_named_loader_and_rejects_mixed_plugins(tmp_path):
    (tmp_path / "OpenIV.asi").write_bytes(_pe_bytes())
    (tmp_path / "dinput8.dll").write_bytes(_pe_bytes())
    assert rpf_loader.inspect_rpf_loader(tmp_path, False).ready is True

    (tmp_path / "RageOpenV.asi").write_bytes(_pe_bytes())
    status = rpf_loader.inspect_rpf_loader(tmp_path, False)
    assert status.ready is False
    assert "Conflicting" in status.reason


class _Response:
    def __init__(self, payload: bytes, content_length: str | None = None):
        self.payload = payload
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_official_downloader_limits_size_and_wraps_network_errors(monkeypatch):
    payload = b"archive"
    asset = _asset("Official", "file.asi", payload)
    monkeypatch.setattr(rpf_loader, "MAX_DOWNLOAD_BYTES", 8)
    monkeypatch.setattr(
        rpf_loader.urllib.request, "urlopen",
        lambda request, timeout: _Response(payload, str(len(payload))),
    )
    assert rpf_loader._download_asset(asset) == payload

    monkeypatch.setattr(
        rpf_loader.urllib.request, "urlopen",
        lambda request, timeout: _Response(payload, "9"),
    )
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="unexpectedly large"):
        rpf_loader._download_asset(asset)

    monkeypatch.setattr(
        rpf_loader.urllib.request, "urlopen",
        lambda request, timeout: _Response(b"123456789"),
    )
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="safety limit"):
        rpf_loader._download_asset(asset)

    def fail(_request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(rpf_loader.urllib.request, "urlopen", fail)
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="official release"):
        rpf_loader._download_asset(asset)


def test_archive_and_binary_validation_fail_closed(tmp_path):
    valid_zip = _zip("wrong.asi", _pe_bytes())
    wrong_member = _asset("Wrong member", "expected.asi", valid_zip)
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="expected file"):
        rpf_loader._verified_member(wrong_member, lambda _asset: valid_zip)

    malformed = b"not a zip"
    malformed_asset = _asset("Malformed", "file.asi", malformed)
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="could not be read"):
        rpf_loader._verified_member(malformed_asset, lambda _asset: malformed)

    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="not a valid x64"):
        rpf_loader._validate_binary(b"not a PE", "RageOpenV.asi")

    too_short = _asset("Short", "file.asi", b"expected")
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="size check failed"):
        rpf_loader._verified_member(too_short, lambda _asset: b"short")


def test_install_is_idempotent_and_refuses_invalid_existing_asi(tmp_path, monkeypatch):
    _plugin, _asi, download = _sources(monkeypatch)
    first = rpf_loader.install_recommended_rpf_loader(
        tmp_path, True, download=download,
    )
    second = rpf_loader.install_recommended_rpf_loader(
        tmp_path, True, download=download,
    )
    assert first.installed
    assert second.installed == ()

    other = tmp_path / "other"
    other.mkdir()
    (other / "xinput1_4.dll").write_bytes(b"invalid")
    with pytest.raises(rpf_loader.RpfLoaderInstallError, match="will not overwrite"):
        rpf_loader.install_recommended_rpf_loader(
            other, True, download=download,
        )


def test_receipt_failure_rolls_back_and_bad_receipts_are_ignored(
    tmp_path, monkeypatch,
):
    _plugin, _asi, download = _sources(monkeypatch)
    monkeypatch.setattr(
        rpf_loader, "_write_receipt",
        lambda *_args: (_ for _ in ()).throw(OSError("read-only")),
    )
    with pytest.raises(OSError, match="read-only"):
        rpf_loader.install_recommended_rpf_loader(
            tmp_path, False, download=download,
        )
    assert not (tmp_path / "RageOpenV.asi").exists()
    assert not (tmp_path / "dinput8.dll").exists()

    receipt = tmp_path / rpf_loader.RECEIPT_RELATIVE
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text("not json", encoding="utf-8")
    assert rpf_loader.uninstall_managed_rpf_loader(tmp_path) == []
    receipt.write_text('{"schema_version":99}', encoding="utf-8")
    assert rpf_loader.uninstall_managed_rpf_loader(tmp_path) == []


@pytest.mark.parametrize("enhanced", [False, True])
def test_uninstall_keeps_asi_loader_used_by_shared_reactor(tmp_path, monkeypatch, enhanced):
    _plugin, _asi, download = _sources(monkeypatch)
    result = rpf_loader.install_recommended_rpf_loader(tmp_path, enhanced, download=download)
    (tmp_path / "ReactorV.RenderHook.asi").write_bytes(b"shared")
    removed = rpf_loader.uninstall_managed_rpf_loader(tmp_path)
    assert result.plugin in removed
    assert result.asi_loader.is_file()
    assert result.asi_loader not in removed
