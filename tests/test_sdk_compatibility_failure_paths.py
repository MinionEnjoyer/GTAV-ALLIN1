"""Legacy-to-Tauri migration boundaries; registry access is entirely simulated."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

import pytest

from allin1 import sdk_manager as sdk
from tests.test_sdk_manager import _sdk_archive


@pytest.mark.skipif(os.name != "nt", reason="Windows user registry contract")
@pytest.mark.parametrize("initial", [None, "C:\\Tools", "same"])
@pytest.mark.parametrize("remove", [False, True])
def test_sdk_cli_registration_uses_only_mock_user_registry(tmp_path, monkeypatch, initial, remove):
    root = tmp_path / "SDK with spaces"
    value = str(root) if initial == "same" else initial
    written, broadcasts = [], []
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    def query(key, name):
        assert name == "Path"
        if value is None: raise FileNotFoundError()
        return value, 2
    def create(hive, name, reserved, flags):
        assert (hive, name, reserved, flags) == (1, "Environment", 0, 6)
        return Key()
    fake = SimpleNamespace(HKEY_CURRENT_USER=1, KEY_QUERY_VALUE=2, KEY_SET_VALUE=4, REG_EXPAND_SZ=2,
        CreateKeyEx=create, QueryValueEx=query, SetValueEx=lambda key, name, reserved, kind, data: written.append(data))
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setenv("PATH", "C:\\OtherTool")
    monkeypatch.setattr(sdk, "_broadcast_environment_change", lambda: broadcasts.append(True))
    sdk.register_sdk_cli(root, remove=remove)
    expected = sdk.updated_sdk_user_path(value or "", root, remove=remove)
    assert written == ([] if expected == (value or "") else [expected])
    assert broadcasts == [True]
    assert (str(root) in os.environ["PATH"].split(os.pathsep)) is not remove


@pytest.mark.skipif(os.name != "nt", reason="Windows environment broadcast contract")
@pytest.mark.parametrize("fail", [False, True])
def test_environment_broadcast_is_best_effort_without_calling_windows(tmp_path, monkeypatch, fail):
    import ctypes
    calls = []
    def send(*args):
        calls.append(args[:6])
        if fail: raise OSError("synthetic desktop unavailable")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(SendMessageTimeoutW=send)))
    sdk._broadcast_environment_change()
    assert calls == [(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000)]


def archive_with(tmp_path, transform):
    path = tmp_path / "sdk.zip"
    _sdk_archive(path)
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/") and name != "checksums.json"}
    transform(files)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items(): archive.writestr(name, content)
        archive.writestr("checksums.json", json.dumps({name: hashlib.sha256(content).hexdigest() for name, content in files.items()}))
    return path


@pytest.mark.parametrize("field,value", [("product", "Unrelated"), ("entrypoint", "wrong.exe"),
    ("cli_entrypoint", "wrong.exe"), ("updater_entrypoint", "wrong.exe"), ("updater_entrypoint", sdk.SDK_UPDATER_EXECUTABLE),
    ("version", "invalid")])
def test_valid_archive_hashes_cannot_hide_wrong_legacy_entrypoints(tmp_path, field, value):
    def transform(files):
        metadata = json.loads(files["release.json"])
        metadata[field] = value
        files["release.json"] = json.dumps(metadata).encode()
    archive = archive_with(tmp_path, transform)
    with pytest.raises(ValueError): sdk.inspect_sdk_archive(archive)
    assert not (tmp_path / "SDK").exists()


@pytest.mark.parametrize("name", [sdk.SDK_EXECUTABLE, sdk.SDK_CLI_EXECUTABLE, sdk.SDK_AGENT_EXECUTABLE])
def test_each_legacy_entrypoint_requires_executable_content(tmp_path, name):
    archive = archive_with(tmp_path, lambda files: files.update({name: b"not executable"}))
    with pytest.raises(ValueError, match="Windows PE"): sdk.inspect_sdk_archive(archive)


def test_sdk_registration_error_reports_installed_payload_without_touching_real_path(tmp_path, monkeypatch):
    archive = tmp_path / "sdk.zip"
    _sdk_archive(archive)
    root = tmp_path / "SDK"
    monkeypatch.setattr(sdk, "default_sdk_root", lambda: root)
    def fail(*args, **kwargs): raise PermissionError("synthetic registry policy")
    monkeypatch.setattr(sdk, "register_sdk_cli", fail)
    with pytest.raises(RuntimeError, match="installed, but Windows could not register"):
        sdk.install_sdk_archive(archive)
    assert sdk.read_sdk_status(root).healthy
    # Uninstall remains recoverable even if PATH removal is refused by policy.
    assert sdk.uninstall_sdk()
    retired = list(tmp_path.glob("SDK.uninstalled-*"))
    assert len(retired) == 1 and sdk.read_sdk_status(retired[0]).healthy


@pytest.mark.parametrize("damage", ["wrong-name", "missing", "invalid", "unreadable"])
def test_legacy_updater_status_fails_closed(tmp_path, monkeypatch, damage):
    archive = tmp_path / "sdk.zip"
    _sdk_archive(archive)
    root = tmp_path / "SDK"
    sdk.install_sdk_archive(archive, root)
    metadata = root / "release.json"
    payload = json.loads(metadata.read_bytes())
    payload["updater_entrypoint"] = "wrong.exe" if damage == "wrong-name" else sdk.SDK_UPDATER_EXECUTABLE
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    updater = root / sdk.SDK_UPDATER_EXECUTABLE
    if damage in {"invalid", "unreadable"}: updater.write_bytes(b"bad")
    if damage == "unreadable":
        original = Path.open
        def open_file(path, *args, **kwargs):
            if path == updater: raise PermissionError("synthetic updater policy")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "open", open_file)
    status = sdk.read_sdk_status(root)
    assert not status.healthy and "updater" in status.detail
