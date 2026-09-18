from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from allin1 import __version__
from allin1 import launcher_installation as installation
from allin1.runtime_resources import verify_resources
from allin1.updater import deploy_release


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _rewrite(path: Path, mutate) -> None:
    with zipfile.ZipFile(path) as source:
        payload = {name: source.read(name) for name in source.namelist()
                   if name != "checksums.json"}
    mutate(payload)
    with zipfile.ZipFile(path, "w") as target:
        for name, value in payload.items():
            target.writestr(name, value)
        target.writestr("checksums.json", json.dumps({
            name: _sha(value) for name, value in payload.items()
        }, sort_keys=True))


def _portable(path: Path, build_id: str, *, resources: dict[str, bytes],
              extra: dict[str, bytes] | None = None) -> Path:
    payload = {
        "allin1-launcher-desktop.exe": b"MZ synthetic shell",
        "runtime/python.exe": b"MZ synthetic python",
        "runtime/bootstrap.py": b"# frozen bootstrap\n",
        **{"resources/" + name: value for name, value in resources.items()},
        **(extra or {}),
    }
    identity = {
        "schema_version": 1, "kind": "launcher_desktop_build", "version": __version__,
        "build_id": build_id, "resources": {name: _sha(value) for name, value in resources.items()},
        "runtime": {"kind": "shared-python"},
    }
    encoded_identity = json.dumps(identity, sort_keys=True).encode()
    payload["build-identity.json"] = encoded_identity
    payload["runtime/lib/allin1/_desktop_build.json"] = encoded_identity
    payload["runtime/runtime-manifest.json"] = json.dumps({
        "schema_version": 1,
        "files": {name.removeprefix("runtime/"): _sha(value)
                  for name, value in payload.items() if name.startswith("runtime/")},
    }, sort_keys=True).encode()
    payload["release.json"] = json.dumps({
        "schema_version": 1, "product": "ALLIN1-Launcher", "format": "tauri-v2",
        "version": __version__, "build_id": build_id,
        "entrypoint": "allin1-launcher-desktop.exe",
        "unsigned_manual_download": True, "release_qualified": False,
    }, sort_keys=True).encode()
    checksums = {name: _sha(value) for name, value in payload.items()}
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in payload.items():
            archive.writestr(name, value)
        archive.writestr("checksums.json", json.dumps(checksums, sort_keys=True))
    return path


def _mismatched_embedded_identity(payload: dict[str, bytes]) -> None:
    payload["runtime/lib/allin1/_desktop_build.json"] = b"{}"
    manifest = json.loads(payload["runtime/runtime-manifest.json"])
    manifest["files"]["lib/allin1/_desktop_build.json"] = _sha(b"{}")
    payload["runtime/runtime-manifest.json"] = json.dumps(manifest, sort_keys=True).encode()


def test_exact_launcher_upgrade_retires_old_assets_installs_marker_and_preserves_user_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "launcher"
    old = _portable(tmp_path / "old.zip", "old-build", resources={
        "data/catalog.json": b"old", "assets/old-vite.js": b"old-vite",
    })
    installation.install_launcher_archive(old, root)
    (root / "notes.txt").write_bytes(b"user note")
    current = _portable(tmp_path / "current.zip", "current-build", resources={
        "data/catalog.json": b"new", "assets/current-vite.js": b"current-vite",
    })

    result = installation.install_launcher_archive(current, root)

    assert result.backup is not None and result.backup.is_dir()
    assert (root / "checksums.json").is_file()
    assert not (root / "resources/assets/old-vite.js").exists()
    assert (root / "resources/assets/current-vite.js").read_bytes() == b"current-vite"
    assert (root / "notes.txt").read_bytes() == b"user note"
    identity = json.loads((root / "build-identity.json").read_text())
    verify_resources(root / "resources", identity)


def test_unowned_collision_or_strict_runtime_tree_refuses_before_writes(tmp_path: Path) -> None:
    root = tmp_path / "launcher"
    old = _portable(tmp_path / "old.zip", "old-build", resources={"data/catalog.json": b"old"})
    installation.install_launcher_archive(old, root)
    (root / "notes.txt").write_bytes(b"user note")
    colliding = _portable(tmp_path / "collision.zip", "new-build", resources={"data/catalog.json": b"new"},
                          extra={"notes.txt": b"release note"})
    before = _snapshot(root)
    with pytest.raises(ValueError, match="Duplicate path"):
        installation.install_launcher_archive(colliding, root)
    assert _snapshot(root) == before

    (root / "resources/unowned.js").write_bytes(b"do not erase")
    before = _snapshot(root)
    clean = _portable(tmp_path / "clean.zip", "new-build", resources={"data/catalog.json": b"new"})
    with pytest.raises(ValueError, match="resource or runtime"):
        installation.install_launcher_archive(clean, root)
    assert _snapshot(root) == before


def test_unrecognized_or_traversal_ownership_marker_cannot_modify_target(tmp_path: Path) -> None:
    root = tmp_path / "launcher"; root.mkdir()
    (root / "notes.txt").write_bytes(b"user note")
    archive = _portable(tmp_path / "new.zip", "new-build", resources={"data/catalog.json": b"new"})
    before = _snapshot(root)
    with pytest.raises(ValueError, match="no ownership manifest"):
        installation.install_launcher_archive(archive, root)
    assert _snapshot(root) == before

    root = tmp_path / "marked"
    old = _portable(tmp_path / "old.zip", "old-build", resources={"data/catalog.json": b"old"})
    installation.install_launcher_archive(old, root)
    (root / "checksums.json").write_text(json.dumps({"../outside": "0" * 64}))
    before = _snapshot(root)
    with pytest.raises(ValueError, match="Unsafe|Duplicate|Invalid"):
        installation.install_launcher_archive(archive, root)
    assert _snapshot(root) == before


def test_invalid_launcher_identity_and_post_swap_failure_restore_byte_identical_root(
    tmp_path: Path, monkeypatch,
) -> None:
    root = tmp_path / "launcher"
    old = _portable(tmp_path / "old.zip", "old-build", resources={"data/catalog.json": b"old"})
    installation.install_launcher_archive(old, root)
    candidate = _portable(tmp_path / "candidate.zip", "new-build", resources={"data/catalog.json": b"new"})
    # Make an otherwise checksum-valid archive fail the Launcher-specific identity check.
    with zipfile.ZipFile(candidate) as source:
        payload = {name: source.read(name) for name in source.namelist() if name != "checksums.json"}
    release = json.loads(payload["release.json"]); release["product"] = "Other"
    payload["release.json"] = json.dumps(release).encode()
    with zipfile.ZipFile(candidate, "w") as target:
        for name, value in payload.items(): target.writestr(name, value)
        target.writestr("checksums.json", json.dumps({name: _sha(value) for name, value in payload.items()}))
    before = _snapshot(root)
    with pytest.raises(ValueError, match="release metadata"):
        installation.install_launcher_archive(candidate, root)
    assert _snapshot(root) == before

    candidate = _portable(tmp_path / "candidate-good.zip", "new-build", resources={"data/catalog.json": b"new"})
    real_verify, calls = installation._verify_launcher_root, []

    def fail_only_after_swap(path: Path) -> None:
        real_verify(path); calls.append(path)
        if len(calls) == 2:
            raise ValueError("injected post-swap failure")

    monkeypatch.setattr(installation, "_verify_launcher_root", fail_only_after_swap)
    with pytest.raises(ValueError, match="post-swap"):
        installation.install_launcher_archive(candidate, root)
    assert len(calls) == 2
    assert _snapshot(root) == before
    assert not list(tmp_path.glob("launcher.installing-*"))


def test_generic_updater_remains_an_overlay_for_nonlauncher_payloads(tmp_path: Path) -> None:
    root = tmp_path / "generic"; root.mkdir()
    (root / "retired-file").write_bytes(b"keep")
    archive = tmp_path / "generic.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("new-file", b"new")
        bundle.writestr("checksums.json", json.dumps({"new-file": _sha(b"new")}))
    deploy_release(archive, root, tmp_path / "backups")
    assert (root / "new-file").read_bytes() == b"new"
    assert (root / "retired-file").read_bytes() == b"keep"


@pytest.mark.parametrize("mutate, message", [
    (lambda payload: payload.__setitem__("runtime/runtime-manifest.json", b"{}"), "runtime manifest"),
    (_mismatched_embedded_identity, "identity differs"),
    (lambda payload: payload.__setitem__("runtime/stale.py", b"stale"), "runtime does not exactly"),
    (lambda payload: payload.__setitem__("sidecar/ALLIN1-Launcher-Sidecar.exe", b"obsolete"), "obsolete frozen"),
])
def test_shared_runtime_must_be_complete_identity_bound_and_not_mixed(
    tmp_path: Path, mutate, message: str,
) -> None:
    archive = _portable(tmp_path / "candidate.zip", "build", resources={"data/catalog.json": b"data"})
    _rewrite(archive, mutate)
    root = tmp_path / "launcher"
    with pytest.raises(ValueError, match=message):
        installation.install_launcher_archive(archive, root)
    assert not root.exists()


def test_unrelated_checksum_marked_directory_is_not_recognized_as_a_launcher(tmp_path: Path) -> None:
    root = tmp_path / "unrelated"; root.mkdir()
    (root / "payload").write_bytes(b"not a launcher")
    (root / "checksums.json").write_text(json.dumps({"payload": _sha(b"not a launcher")}))
    archive = _portable(tmp_path / "candidate.zip", "build", resources={"data/catalog.json": b"data"})
    before = _snapshot(root)
    with pytest.raises(ValueError, match="required runtime payloads|Launcher release"):
        installation.install_launcher_archive(archive, root)
    assert _snapshot(root) == before


def test_stage_rename_and_source_race_failures_never_replace_the_existing_launcher(
    tmp_path: Path, monkeypatch,
) -> None:
    root = tmp_path / "launcher"
    installation.install_launcher_archive(
        _portable(tmp_path / "old.zip", "old", resources={"data/catalog.json": b"old"}), root,
    )
    candidate = _portable(tmp_path / "candidate.zip", "new", resources={"data/catalog.json": b"new"})
    before = _snapshot(root)
    real_verify = installation._verify_launcher_root

    def fail_stage(path: Path) -> None:
        if ".installing-" in path.name:
            raise ValueError("injected stage verification failure")
        real_verify(path)

    monkeypatch.setattr(installation, "_verify_launcher_root", fail_stage)
    with pytest.raises(ValueError, match="stage verification"):
        installation.install_launcher_archive(candidate, root)
    assert _snapshot(root) == before

    monkeypatch.setattr(installation, "_verify_launcher_root", real_verify)
    real_move = installation._move_directory

    def fail_pending_rename(source: Path, target: Path) -> None:
        if ".installing-" in source.name:
            raise OSError("injected pending rename failure")
        real_move(source, target)

    monkeypatch.setattr(installation, "_move_directory", fail_pending_rename)
    with pytest.raises(OSError, match="pending rename"):
        installation.install_launcher_archive(candidate, root)
    assert _snapshot(root) == before
    assert not list(tmp_path.glob("launcher.previous-*"))

    monkeypatch.setattr(installation, "_move_directory", real_move)

    def introduce_source_race(path: Path) -> None:
        real_verify(path)
        if ".installing-" in path.name:
            (root / "unexpected-race-file").write_bytes(b"external")

    monkeypatch.setattr(installation, "_verify_launcher_root", introduce_source_race)
    with pytest.raises(ValueError, match="changed before deployment"):
        installation.install_launcher_archive(candidate, root)
    assert (root / "unexpected-race-file").read_bytes() == b"external"
    assert not (root / "resources/data/catalog.json").read_bytes() == b"new"


@pytest.mark.parametrize("relative", ["Resources/unowned.js", "Runtime/unowned.py", "SIDECAR/unowned.exe"])
def test_unowned_strict_trees_are_case_insensitive(relative: str, tmp_path: Path) -> None:
    root = tmp_path / "launcher"
    installation.install_launcher_archive(
        _portable(tmp_path / "old.zip", "old", resources={"data/catalog.json": b"old"}), root,
    )
    rogue = root / Path(*relative.split("/")); rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_bytes(b"unowned")
    archive = _portable(tmp_path / "candidate.zip", "new", resources={"data/catalog.json": b"new"})
    with pytest.raises(ValueError, match="resource or runtime"):
        installation.install_launcher_archive(archive, root)
