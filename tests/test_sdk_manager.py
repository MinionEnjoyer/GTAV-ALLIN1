"""Managed standalone SDK download and installation tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from allin1.sdk_manager import (
    SDK_AGENT_EXECUTABLE,
    SDK_CLI_EXECUTABLE,
    SDK_EXECUTABLE,
    SDK_UPDATER_EXECUTABLE,
    SdkRelease,
    default_sdk_root,
    fetch_latest_sdk_release,
    inspect_sdk_archive,
    install_sdk_archive,
    install_sdk_release,
    read_sdk_status,
    sdk_launch_error_message,
    sdk_update_available,
    uninstall_sdk,
    updated_sdk_user_path,
    _safe_member,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _sdk_archive(path: Path, version: str = "0.4.8", *, tamper: bool = False) -> bytes:
    payload = {
        SDK_EXECUTABLE: b"MZ" + b"sdk-client",
        SDK_CLI_EXECUTABLE: b"MZ" + b"sdk-cli",
        SDK_AGENT_EXECUTABLE: b"MZ" + b"sdk-agent",
        "release.json": json.dumps({
            "product": "ALLIN1-SDK", "version": version,
            "entrypoint": SDK_EXECUTABLE, "cli_entrypoint": SDK_CLI_EXECUTABLE,
        }).encode(),
        "sdk/example.json": b'{"example":true}',
    }
    checksums = {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()}
    if tamper:
        checksums["sdk/example.json"] = "0" * 64
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sdk/", b"")
        for name, content in payload.items():
            archive.writestr(name, content)
        archive.writestr("checksums.json", json.dumps(checksums))
    return path.read_bytes()


def test_default_sdk_root_is_per_user_and_separate_from_game(tmp_path):
    root = default_sdk_root({"LOCALAPPDATA": str(tmp_path)})
    assert root == tmp_path / "ALLIN1" / "SDK"
    assert default_sdk_root({}).name == "SDK"
    value = os.pathsep.join(("C:\\Tools", str(root), str(root)))
    assert updated_sdk_user_path(value, root).split(os.pathsep).count(str(root.resolve())) == 1
    assert str(root.resolve()) not in updated_sdk_user_path(value, root, remove=True)


def test_launch_error_explains_enforced_application_control_policy():
    error = OSError("raw system message")
    error.winerror = 4551
    message = sdk_launch_error_message(error)
    assert "Windows Application Control" in message
    assert "publisher-signed SDK build" in message
    assert "unblocking the file will not change this policy" in message


def test_launch_error_preserves_unrecognized_system_message():
    error = OSError("ordinary launch failure")
    error.winerror = 2
    assert sdk_launch_error_message(error) == "ordinary launch failure"


def test_status_reports_invalid_partial_installations(tmp_path):
    root = tmp_path / "SDK"
    root.mkdir()
    executable = root / SDK_EXECUTABLE
    executable.write_bytes(b"not-pe")
    assert "invalid" in read_sdk_status(root).detail
    executable.write_bytes(b"MZvalid")
    (root / SDK_CLI_EXECUTABLE).write_bytes(b"MZcli")
    assert "metadata is missing" in read_sdk_status(root).detail
    (root / "release.json").write_text("not-json")
    assert "metadata is invalid" in read_sdk_status(root).detail


def test_latest_release_requires_matching_archive_and_checksum_assets():
    payload = json.dumps({
        "tag_name": "v0.4.8",
        "name": "SDK 0.4.8",
        "html_url": "https://example.test/release",
        "assets": [
            {"name": "ALLIN1-SDK-0.4.8-win-x64.zip", "size": 123,
             "browser_download_url": "https://example.test/sdk.zip"},
            {"name": "ALLIN1-SDK-0.4.8-win-x64.zip.sha256", "size": 64,
             "browser_download_url": "https://example.test/sdk.sha256"},
        ],
    }).encode()
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, timeout))
        return _Response(payload)

    release = fetch_latest_sdk_release(timeout=1.5, opener=opener)
    assert release.version == "0.4.8"
    assert release.archive_size == 123
    assert release.checksum_url.endswith(".sha256")
    assert seen[0][0].endswith("/releases/latest")


def test_latest_release_rejects_missing_or_mismatched_assets():
    def response(assets, tag="v0.4.8"):
        return _Response(json.dumps({
            "tag_name": tag, "html_url": "https://example.test", "assets": assets,
        }).encode())

    with pytest.raises(ValueError, match="archive"):
        fetch_latest_sdk_release(opener=lambda *_args, **_kwargs: response([]))
    archive = {"name": "ALLIN1-SDK-0.4.7-win-x64.zip", "size": 10,
               "browser_download_url": "https://example.test/sdk.zip"}
    checksum = {"name": archive["name"] + ".sha256",
                "browser_download_url": "https://example.test/sum"}
    with pytest.raises(ValueError, match="version"):
        fetch_latest_sdk_release(opener=lambda *_args, **_kwargs: response([archive, checksum]))
    archive["name"] = "ALLIN1-SDK-0.4.8-win-x64.zip"
    with pytest.raises(ValueError, match="missing.*sha256"):
        fetch_latest_sdk_release(opener=lambda *_args, **_kwargs: response([archive]))
    archive["size"] = 0
    checksum["name"] = archive["name"] + ".sha256"
    with pytest.raises(ValueError, match="size"):
        fetch_latest_sdk_release(opener=lambda *_args, **_kwargs: response([archive, checksum]))


def test_archive_install_status_repair_and_uninstall(tmp_path):
    package = tmp_path / "sdk.zip"
    _sdk_archive(package)
    root = tmp_path / "managed" / "SDK"
    assert read_sdk_status(root).installed is False

    info = inspect_sdk_archive(package, "0.4.8")
    assert info.version == "0.4.8" and info.file_count == 5
    status = install_sdk_archive(package, root, expected_version="0.4.8")
    assert status.healthy and status.version == "0.4.8"
    assert status.executable == root / SDK_EXECUTABLE

    (root / "stale.txt").write_text("old")
    pending = root.with_name(root.name + ".installing")
    previous = root.with_name(root.name + ".previous")
    pending.mkdir()
    previous.mkdir()
    repaired = install_sdk_archive(package, root)
    assert repaired.healthy
    assert not (root / "stale.txt").exists()
    assert uninstall_sdk(root) is True
    assert uninstall_sdk(root) is False


def test_launcher_validates_declared_standalone_updater(tmp_path):
    archive_path = tmp_path / "sdk-with-updater.zip"
    payload = {
        SDK_EXECUTABLE: b"MZdesktop",
        SDK_CLI_EXECUTABLE: b"MZconsole",
        SDK_AGENT_EXECUTABLE: b"MZagent",
        SDK_UPDATER_EXECUTABLE: b"MZupdater",
        "release.json": json.dumps({
            "product": "ALLIN1-SDK", "version": "0.6.1",
            "entrypoint": SDK_EXECUTABLE,
            "cli_entrypoint": SDK_CLI_EXECUTABLE,
            "agent_entrypoint": SDK_AGENT_EXECUTABLE,
            "updater_entrypoint": SDK_UPDATER_EXECUTABLE,
        }).encode(),
    }
    checksums = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in payload.items()
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
        archive.writestr("checksums.json", json.dumps(checksums))

    assert inspect_sdk_archive(archive_path).version == "0.6.1"
    root = tmp_path / "SDK"
    assert install_sdk_archive(archive_path, root).healthy
    (root / SDK_UPDATER_EXECUTABLE).unlink()
    assert read_sdk_status(root).healthy is False
    assert "updater is missing" in read_sdk_status(root).detail


def test_archive_rejects_tampering_unsafe_paths_and_wrong_version(tmp_path):
    tampered = tmp_path / "tampered.zip"
    _sdk_archive(tampered, tamper=True)
    with pytest.raises(ValueError, match="checksum mismatch"):
        inspect_sdk_archive(tampered)

    wrong = tmp_path / "wrong.zip"
    _sdk_archive(wrong, "0.4.7")
    with pytest.raises(ValueError, match="does not match"):
        inspect_sdk_archive(wrong, "0.4.8")

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside", b"bad")
    with pytest.raises(ValueError, match="unsafe"):
        inspect_sdk_archive(unsafe)

    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("readme.txt", b"safe but incomplete")
    with pytest.raises(ValueError, match="is missing"):
        inspect_sdk_archive(missing)


@pytest.mark.parametrize(("metadata", "checksums", "match"), [
    (b"[]", {}, "metadata is invalid"),
    (json.dumps({
        "product": "ALLIN1-SDK", "version": "0.4.8",
        "entrypoint": SDK_EXECUTABLE, "cli_entrypoint": SDK_CLI_EXECUTABLE,
    }).encode(), [], "must be an object"),
])
def test_archive_rejects_malformed_internal_json(tmp_path, metadata, checksums, match):
    executable = b"MZsdk"
    archive_path = tmp_path / "malformed.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(SDK_EXECUTABLE, executable)
        archive.writestr(SDK_CLI_EXECUTABLE, executable)
        archive.writestr(SDK_AGENT_EXECUTABLE, executable)
        archive.writestr("release.json", metadata)
        archive.writestr("checksums.json", json.dumps(checksums))
    with pytest.raises(ValueError, match=match):
        inspect_sdk_archive(archive_path)


@pytest.mark.parametrize("name", ["C:/escape"])
def test_archive_rejects_platform_specific_unsafe_names(tmp_path, name):
    archive_path = tmp_path / "unsafe-name.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(name, b"bad")
    with pytest.raises(ValueError, match="unsafe"):
        inspect_sdk_archive(archive_path)


def test_member_validator_rejects_backslashes():
    info = zipfile.ZipInfo("safe")
    info.filename = "folder\\escape"
    with pytest.raises(ValueError, match="unsafe"):
        _safe_member(info)


def test_archive_rejects_symbolic_links(tmp_path):
    archive_path = tmp_path / "link.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, b"target")
    with pytest.raises(ValueError, match="symbolic link"):
        inspect_sdk_archive(archive_path)


@pytest.mark.parametrize(("constant", "value", "match"), [
    ("MAX_ARCHIVE_BYTES", 1, "exceeds the allowed size"),
    ("MAX_ARCHIVE_FILES", 1, "too many files"),
    ("MAX_EXTRACTED_BYTES", 1, "expands beyond"),
])
def test_archive_enforces_resource_limits(tmp_path, monkeypatch, constant, value, match):
    archive_path = tmp_path / "sdk.zip"
    _sdk_archive(archive_path)
    monkeypatch.setattr(f"allin1.sdk_manager.{constant}", value)
    with pytest.raises(ValueError, match=match):
        inspect_sdk_archive(archive_path)


@pytest.mark.parametrize(("mutation", "match"), [
    (lambda payload, checksums: payload.update({SDK_EXECUTABLE: b"not-pe"}), "Windows PE"),
    (lambda payload, checksums: payload.update({"release.json": b'{"product":"wrong","version":"0.4.8"}'}), "wrong product"),
    (lambda payload, checksums: checksums.update({"extra.txt": "0" * 64}), "exactly match"),
    (lambda payload, checksums: checksums.update({SDK_EXECUTABLE: "invalid"}), "invalid SDK checksum"),
])
def test_archive_rejects_invalid_release_contract(tmp_path, mutation, match):
    payload = {
        SDK_EXECUTABLE: b"MZsdk",
        SDK_CLI_EXECUTABLE: b"MZcli",
        SDK_AGENT_EXECUTABLE: b"MZagent",
        "release.json": json.dumps({
            "product": "ALLIN1-SDK", "version": "0.4.8",
            "entrypoint": SDK_EXECUTABLE, "cli_entrypoint": SDK_CLI_EXECUTABLE,
        }).encode(),
    }
    checksums = {name: hashlib.sha256(value).hexdigest() for name, value in payload.items()}
    mutation(payload, checksums)
    for name, value in payload.items():
        if checksums.get(name) != "invalid":
            checksums[name] = hashlib.sha256(value).hexdigest()
    archive_path = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, value in payload.items():
            archive.writestr(name, value)
        archive.writestr("checksums.json", json.dumps(checksums))
    with pytest.raises(ValueError, match=match):
        inspect_sdk_archive(archive_path)


def test_download_verifies_external_checksum_and_installs(tmp_path):
    archive_path = tmp_path / "source.zip"
    archive_bytes = _sdk_archive(archive_path)
    digest = hashlib.sha256(archive_bytes).hexdigest()
    release = SdkRelease(
        version="0.4.8", name="SDK", page_url="https://example.test/release",
        archive_url="https://example.test/sdk.zip",
        archive_name="ALLIN1-SDK-0.4.8-win-x64.zip",
        archive_size=len(archive_bytes), checksum_url="https://example.test/sdk.sha256",
    )
    downloads = {
        release.archive_url: archive_bytes,
        release.checksum_url: f"{digest}  {release.archive_name}\n".encode(),
    }
    progress = []

    def opener(request, timeout):
        assert timeout == 2.0
        return _Response(downloads[request.full_url])

    status = install_sdk_release(
        release, tmp_path / "SDK", timeout=2.0, opener=opener,
        progress=lambda *values: progress.append(values),
    )
    assert status.healthy
    assert progress[-1][0] == "Verifying SDK"
    assert sdk_update_available(status, release) is False


def test_download_rejects_wrong_external_checksum(tmp_path):
    archive_path = tmp_path / "source.zip"
    archive_bytes = _sdk_archive(archive_path)
    release = SdkRelease(
        "0.4.8", "SDK", "https://example.test/release", "https://example.test/sdk.zip",
        "ALLIN1-SDK-0.4.8-win-x64.zip", len(archive_bytes), "https://example.test/sdk.sha256",
    )
    downloads = {
        release.archive_url: archive_bytes,
        release.checksum_url: ("0" * 64 + "  " + release.archive_name).encode(),
    }
    with pytest.raises(ValueError, match="SHA-256"):
        install_sdk_release(
            release, tmp_path / "SDK",
            opener=lambda request, timeout: _Response(downloads[request.full_url]),
        )


@pytest.mark.parametrize(("checksum", "size_delta", "match"), [
    (b"", 0, "empty or invalid"),
    (b"not-a-digest", 0, "SHA-256 digest"),
    (("0" * 64 + "  other.zip").encode(), 0, "different archive"),
    (None, 1, "size mismatch"),
])
def test_download_rejects_malformed_metadata(tmp_path, checksum, size_delta, match):
    archive_path = tmp_path / "source.zip"
    archive_bytes = _sdk_archive(archive_path)
    archive_name = "ALLIN1-SDK-0.4.8-win-x64.zip"
    if checksum is None:
        checksum = (hashlib.sha256(archive_bytes).hexdigest() + "  " + archive_name).encode()
    release = SdkRelease(
        "0.4.8", "SDK", "https://example.test", "https://example.test/sdk",
        archive_name, len(archive_bytes) + size_delta, "https://example.test/sum",
    )
    downloads = {release.archive_url: archive_bytes, release.checksum_url: checksum}
    with pytest.raises(ValueError, match=match):
        install_sdk_release(
            release, tmp_path / "SDK",
            opener=lambda request, timeout: _Response(downloads[request.full_url]),
        )


def test_update_is_available_for_unknown_or_older_install(tmp_path):
    release = SdkRelease("0.4.8", "SDK", "page", "archive", "name", 1, "sum")
    missing = read_sdk_status(tmp_path / "missing")
    assert sdk_update_available(missing, release)
