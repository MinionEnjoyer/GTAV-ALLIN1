"""Tauri distribution consumer tests; every filesystem target is disposable."""
import hashlib
import json
import zipfile
import pytest
from allin1.sdk_manager import inspect_sdk_archive, install_sdk_archive, read_sdk_status, uninstall_sdk
from allin1.sdk_installation import SHELL, SIDECAR


def sha(value): return hashlib.sha256(value).hexdigest()


def tauri_payload(version="0.6.4", build="test-build-a"):
    identity = {"schema_version": 1, "kind": "sdk_build_identity", "sdk_version": version, "build_id": build}
    resources = {"build-identity.json": json.dumps(identity).encode(), "docs/help.md": b"test help"}
    return {**resources, SHELL: b"MZshell-fixture", SIDECAR: b"MZsidecar-fixture",
        "resource-checksums.json": json.dumps({n: sha(v) for n, v in resources.items()}).encode(),
        "release.json": json.dumps({"schema_version": 1, "product": "ALLIN1-SDK", "format": "tauri-v2",
            "version": version, "build_id": build, "entrypoint": SHELL, "sidecar_entrypoint": SIDECAR,
            "build_identity_sha256": sha(resources["build-identity.json"])}).encode()}


def archive(path, payload, checksums=None):
    with zipfile.ZipFile(path, "w") as output:
        for name, value in payload.items(): output.writestr(name, value)
        output.writestr("checksums.json", json.dumps(checksums if checksums is not None else {n: sha(v) for n, v in payload.items()}))
    return path


def test_tauri_clean_upgrade_repair_and_recoverable_uninstall(tmp_path):
    root = tmp_path / "User directory with spaces" / "SDK"
    source = archive(tmp_path / "SDK.zip", tauri_payload())
    assert inspect_sdk_archive(source).version == "0.6.4"
    assert install_sdk_archive(source, root).executable == root / SHELL
    assert "live acceptance is separate" in read_sdk_status(root).detail
    (root / "user-project.json").write_text("keep me")
    (root / SIDECAR).write_bytes(b"MZtampered")
    assert not read_sdk_status(root).healthy
    assert install_sdk_archive(source, root).healthy
    assert (root / "user-project.json").read_text() == "keep me"
    archive(source, tauri_payload("0.6.5", "test-build-b"))
    assert install_sdk_archive(source, root).version == "0.6.5"
    assert len(list(root.parent.glob("SDK.previous-*"))) == 2
    assert uninstall_sdk(root)
    assert not root.exists()
    assert next(root.parent.glob("SDK.uninstalled-*")).joinpath("user-project.json").read_text() == "keep me"


@pytest.mark.parametrize("name", ["../outside.txt", "C:/outside.txt", "//server/share/file", "docs\\bad", "docs/../bad", "NUL.txt", "docs/foo.", "docs/foo "])
@pytest.mark.parametrize("location", ["archive", "manifest"])
def test_sdk_rejects_unsafe_names_before_destination_write(tmp_path, name, location):
    canary = tmp_path / "outside.txt"; canary.write_text("unchanged")
    payload = tauri_payload(); checksums = {n: sha(v) for n, v in payload.items()}
    checksums[name] = sha(b"bad")
    if location == "archive": payload[name] = b"bad"
    source = archive(tmp_path / "bad.zip", payload, checksums)
    with pytest.raises(ValueError): install_sdk_archive(source, tmp_path / "SDK")
    assert canary.read_text() == "unchanged" and not (tmp_path / "SDK").exists()
    assert not list(tmp_path.glob("SDK.installing*"))


@pytest.mark.parametrize("mutation", ["identity", "resource", "missing_sidecar", "duplicate", "collision"])
def test_sdk_rejects_identity_and_companion_ambiguity(tmp_path, mutation):
    payload = tauri_payload()
    if mutation == "identity": payload["build-identity.json"] = json.dumps({"kind": "other-build"}).encode()
    if mutation == "resource": payload["docs/help.md"] = b"wrong companion"
    if mutation == "missing_sidecar": del payload[SIDECAR]
    if mutation == "duplicate": payload[SHELL.upper()] = payload[SHELL]
    if mutation == "collision": payload["docs"] = b"file/directory clash"
    source = archive(tmp_path / "bad.zip", payload)
    with pytest.raises((ValueError, KeyError)): install_sdk_archive(source, tmp_path / "SDK")
    assert not (tmp_path / "SDK").exists()


def test_sdk_does_not_adopt_unowned_destination(tmp_path):
    root = tmp_path / "not an SDK"; root.mkdir(); (root / "canary").write_text("keep")
    source = archive(tmp_path / "source.zip", tauri_payload())
    with pytest.raises(ValueError, match="ownership"): install_sdk_archive(source, root)
    with pytest.raises(FileNotFoundError): uninstall_sdk(root)
    assert (root / "canary").read_text() == "keep"


def test_failed_post_swap_verification_restores_original(tmp_path, monkeypatch):
    from allin1 import sdk_manager
    from dataclasses import replace
    root = tmp_path / "SDK"; source = archive(tmp_path / "source.zip", tauri_payload())
    install_sdk_archive(source, root); (root / "user.txt").write_text("original")
    original = sdk_manager.read_sdk_status
    def verify(path):
        result = original(path)
        return replace(result, healthy=False) if path == root else result
    monkeypatch.setattr(sdk_manager, "read_sdk_status", verify)
    with pytest.raises(ValueError, match="Installed SDK"): install_sdk_archive(source, root)
    assert original(root).healthy and (root / "user.txt").read_text() == "original"


def test_managed_health_rejects_same_extra_resources_as_sdk_runtime(tmp_path):
    root = tmp_path / "SDK"
    source = archive(tmp_path / "SDK.zip", tauri_payload())
    install_sdk_archive(source, root)
    (root / "user-project.json").write_bytes(b"user data allowed at root")
    assert read_sdk_status(root).healthy
    (root / "docs/stale-companion.dll").write_bytes(b"unlisted companion")
    status = read_sdk_status(root)
    assert not status.healthy
    assert "unlisted SDK resources" in status.detail


def test_repair_preserves_unowned_resource_and_refuses_false_healthy_swap(tmp_path):
    root = tmp_path / "SDK"
    source = archive(tmp_path / "SDK.zip", tauri_payload())
    install_sdk_archive(source, root)
    (root / "docs/custom.md").write_bytes(b"unowned resource must not be deleted")
    before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="Staged SDK failed verification"):
        install_sdk_archive(source, root)
    assert {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    assert not list(tmp_path.glob("SDK.previous-*"))
    assert not list(tmp_path.glob("SDK.installing-*"))


@pytest.mark.parametrize("field", ["release", "identity"])
def test_tauri_schema_does_not_accept_boolean_as_version_one(tmp_path, field):
    payload = tauri_payload()
    name = "release.json" if field == "release" else "build-identity.json"
    document = json.loads(payload[name]); document["schema_version"] = True
    payload[name] = json.dumps(document).encode()
    if field == "identity":
        metadata = json.loads(payload["release.json"])
        metadata["build_identity_sha256"] = sha(payload[name])
        payload["release.json"] = json.dumps(metadata).encode()
        resources = json.loads(payload["resource-checksums.json"])
        resources[name] = sha(payload[name])
        payload["resource-checksums.json"] = json.dumps(resources).encode()
    source = archive(tmp_path / "SDK.zip", payload)
    with pytest.raises(ValueError):
        install_sdk_archive(source, tmp_path / "SDK")
    assert not (tmp_path / "SDK").exists()


def test_old_gui_package_upgrades_to_tauri_without_leaving_legacy_entrypoints(tmp_path):
    from allin1.sdk_manager import SDK_EXECUTABLE, SDK_CLI_EXECUTABLE, SDK_AGENT_EXECUTABLE
    old = {SDK_EXECUTABLE: b"MZ old GUI fixture", SDK_CLI_EXECUTABLE: b"MZ old CLI fixture",
           SDK_AGENT_EXECUTABLE: b"MZ old Agent fixture",
           "release.json": json.dumps({"product": "ALLIN1-SDK", "version": "0.6.3",
               "entrypoint": SDK_EXECUTABLE, "cli_entrypoint": SDK_CLI_EXECUTABLE}).encode()}
    root = tmp_path / "SDK with spaces"
    install_sdk_archive(archive(tmp_path / "old.zip", old), root)
    (root / "workspace.json").write_bytes(b"keep user workspace")
    result = install_sdk_archive(archive(tmp_path / "new.zip", tauri_payload()), root)
    assert result.healthy and result.executable == root / SHELL
    # Old/new GUI names differ only by case on Windows; inspect actual bytes.
    assert (root / SHELL).read_bytes() == tauri_payload()[SHELL]
    assert not any((root / name).exists() for name in (SDK_CLI_EXECUTABLE, SDK_AGENT_EXECUTABLE))
    previous = next(tmp_path.glob("SDK with spaces.previous-*"))
    assert (previous / SDK_EXECUTABLE).read_bytes() == old[SDK_EXECUTABLE]
    assert (root / "workspace.json").read_bytes() == (previous / "workspace.json").read_bytes() == b"keep user workspace"


def test_managed_sdk_lifecycle_at_long_disposable_path(tmp_path):
    from allin1.release_paths import filesystem_path
    root = tmp_path
    while len(str(root)) < 285:
        root /= "long directory segment with spaces"
    root /= "SDK"
    source = archive(tmp_path / "SDK.zip", tauri_payload())
    assert install_sdk_archive(source, root).healthy
    filesystem_path(root / "project.json").write_bytes(b"retained project")
    filesystem_path(root / SIDECAR).write_bytes(b"corrupt")
    assert not read_sdk_status(root).healthy
    assert install_sdk_archive(source, root).healthy
    assert uninstall_sdk(root)
    retired = next(filesystem_path(root.parent).glob("SDK.uninstalled-*"))
    assert (retired / "project.json").read_bytes() == b"retained project"
