"""Disposable resource/packaging regressions; never use a game installation."""
import json
import os
from pathlib import Path
import sys
import subprocess

import pytest

from allin1 import __version__
from allin1 import runtime_resources as runtime
from tools import launcher_desktop_candidate as candidate

ROOT = Path(__file__).resolve().parents[1]


def identity(files):
    return {"schema_version": 1, "kind": "launcher_desktop_build", "version": __version__, "resources": files}


def test_source_runtime_path_is_unchanged_and_frozen_path_ignores_environment(tmp_path, monkeypatch):
    assert runtime.resource_root() == ROOT
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "standalone with spaces/sidecar" / runtime.SIDECAR_NAME))
    monkeypatch.setenv("ALLIN1_RESOURCE_ROOT", str(ROOT))
    assert runtime.resource_root() == tmp_path / "standalone with spaces/resources"
    monkeypatch.setattr(sys, "executable", str(tmp_path / "legacy-gui.exe"))
    assert runtime.resource_root() == ROOT


@pytest.mark.parametrize("module,field,suffix", [
    ("allin1.installer", "_PROJECT_ROOT", ""),
    ("allin1.mods", "_PROJECT_ROOT", ""),
    ("allin1.reactor_dependency", "UI_SOURCE", "data/reactor/allin1-ui"),
])
def test_frozen_services_resolve_resources_not_python_extraction_directory(tmp_path, module, field, suffix):
    # Isolate module initialization: reloading shared modules in pytest changes
    # function/class identities already captured by other collected tests.
    script = """
import importlib, sys
from pathlib import Path
sys.frozen = True
sys.executable = sys.argv[3]
loaded = importlib.import_module(sys.argv[1])
assert getattr(loaded, sys.argv[2]) == Path(sys.argv[4])
"""
    result = subprocess.run([sys.executable, "-c", script, module, field,
        str(tmp_path / "sidecar" / runtime.SIDECAR_NAME), str(tmp_path / "resources" / suffix)],
        capture_output=True, text=True, timeout=30, cwd=tmp_path,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr


def test_exact_staging_preserves_sources_and_rejects_existing_destination(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"known resource")
    destination = tmp_path / "candidate with spaces"
    files = candidate.stage_resources({"data/catalog.json": source}, destination)
    runtime.verify_resources(destination, identity(files))
    assert source.read_bytes() == b"known resource"
    with pytest.raises(FileExistsError):
        candidate.stage_resources({"data/catalog.json": source}, destination)


@pytest.mark.parametrize("name", ["../canary", "/absolute", "C:/absolute", "C:relative", "//server/share", "data\\escape", "data/../escape", "data//file", "data/NUL.txt", "data/trailing.", "data/x:stream", "data/./file"])
def test_unsafe_declared_destination_rejected_before_any_writes(tmp_path, name):
    source = tmp_path / "source"
    source.write_bytes(b"input")
    outside = tmp_path / "canary"
    outside.write_bytes(b"preserve")
    destination = tmp_path / "candidate"
    with pytest.raises(ValueError):
        candidate.stage_resources({"data/valid": source, name: source}, destination)
    with pytest.raises(ValueError):
        runtime.verify_resources(tmp_path, identity({name: "0" * 64}))
    assert not destination.exists()
    assert outside.read_bytes() == b"preserve"


@pytest.mark.parametrize("names", [["data/X", "data/x"], ["data/file", "data/file/child"]])
def test_duplicate_and_colliding_destinations_fail_preflight(tmp_path, names):
    source = tmp_path / "source"
    source.write_bytes(b"input")
    with pytest.raises(ValueError):
        candidate.stage_resources(dict.fromkeys(names, source), tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_missing_and_hardlinked_sources_fail_before_writing(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"input")
    with pytest.raises(FileNotFoundError):
        candidate.stage_resources({"good": source, "missing": tmp_path / "absent"}, tmp_path / "first")
    assert not (tmp_path / "first").exists()
    linked = tmp_path / "hardlink"
    os.link(source, linked)
    with pytest.raises(ValueError, match="Hard-linked"):
        candidate.stage_resources({"linked": linked}, tmp_path / "second")
    assert not (tmp_path / "second").exists()
    assert source.read_bytes() == b"input"


@pytest.mark.parametrize("change", ["missing", "extra", "changed", "boolean-schema", "version", "kind", "empty"])
def test_frozen_resource_corruption_fails_closed(tmp_path, change):
    root = tmp_path / "resources"
    root.mkdir()
    file = root / "catalog.json"
    file.write_bytes(b"original")
    document = identity({"catalog.json": runtime.sha256(file)})
    if change == "missing": file.unlink()
    elif change == "extra": (root / "stale.txt").write_text("stale")
    elif change == "changed": file.write_bytes(b"changed")
    elif change == "boolean-schema": document["schema_version"] = True
    elif change == "version": document["version"] = "0.6.3"
    elif change == "kind": document["kind"] = "sdk_build"
    else: document["resources"] = {}
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(ValueError): runtime.verify_resources(root, document)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


def test_frozen_identity_requires_own_root_and_embedded_manifest(tmp_path, monkeypatch):
    assert runtime.frozen_identity(tmp_path) is None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "sidecar" / runtime.SIDECAR_NAME))
    (tmp_path / "resources").mkdir()
    with pytest.raises(ValueError, match="own resource"):
        runtime.frozen_identity(tmp_path / "another")
    # No fallback to checkout resources when packaged identity is absent.
    with pytest.raises(FileNotFoundError):
        runtime.frozen_identity(tmp_path / "resources")


@pytest.mark.skipif(os.name != "nt", reason="Windows canonical Tauri paths")
@pytest.mark.parametrize("extended", [False, True])
def test_frozen_identity_accepts_same_windows_root_but_checks_all_payloads(tmp_path, monkeypatch, extended):
    resources = tmp_path / "packaged application with spaces/resources"
    resources.mkdir(parents=True)
    payload = resources / "resource.bin"
    payload.write_bytes(b"payload")
    document = identity({"resource.bin": runtime.sha256(payload)})
    document.update(build_id="test-build", commit="test-commit", source_sha256="test-source",
                    source_dirty=False, created_at="test-date", resources_sha256="test-resources")
    (tmp_path / "_desktop_build.json").write_text(json.dumps(document))
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "runtime_resources.py"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(resources.parent / "sidecar" / runtime.SIDECAR_NAME))
    selected = Path("\\\\?\\" + str(resources)) if extended else resources
    assert runtime.frozen_identity(selected)["build_id"] == "test-build"
    other = tmp_path / "other-resources"; other.mkdir()
    (other / payload.name).write_bytes(payload.read_bytes())
    with pytest.raises(ValueError, match="own resource"):
        runtime.frozen_identity(other)
    payload.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        runtime.frozen_identity(selected)


@pytest.mark.parametrize("name", ["tkinter", "tkinter.ttk", "_tkinter.pyd", "_internal/tcl86t.dll", "_internal/tk86t.dll", "_internal/_tcl_data/init.tcl", "_internal/_tk_data/tk.tcl", "tkinter/__init__.pyc", "PIL.ImageTk", "PIL/_imagingtk.pyi", "PIL/_tkinter_finder.py", "allin1.gui", "allin1.customization_ui"])
def test_packaging_scan_rejects_tk_and_legacy_gui_even_when_not_imported(name):
    with pytest.raises(ValueError, match="leaked"):
        candidate.assert_no_tk(["allin1.desktop_host", name])


def test_runtime_staging_does_not_include_legacy_gui_or_user_preferences(tmp_path):
    from tests.test_release import _release_tree
    # A complete disposable fixture exercises the real inventory/filter without
    # relying on developer-generated binaries. Candidate builds test real tools.
    root = _release_tree(tmp_path)
    (root / "config.toml").write_bytes(b"private preferences")
    files = candidate.resource_inputs(root)
    assert "data/vehicles.toml" in files
    assert "script/dist/ALLIN1.dll" in files
    assert "tools/RpfPatcher/RpfPatcher.exe" in files
    assert "data/reactor/allin1-ui/index.html" in files
    assert not any(name.startswith("src/") or name.endswith((".bat", ".py", ".cs", ".pdb")) for name in files)
    assert "config.toml" not in files and "config.example.toml" in files
    candidate.assert_no_tk(files)


def portable_fixture(tmp_path):
    app = tmp_path / "application with spaces"
    for name, content in {"allin1-launcher-desktop.exe": b"MZ synthetic shell",
                          "sidecar/" + runtime.SIDECAR_NAME: b"MZ synthetic service",
                          "resources/docs/readme.md": b"readable help"}.items():
        path = app / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    return app, {"version": "0.6.4", "build_id": "a" * 32, "release_ready": False}


def test_complete_launcher_portable_is_deterministic_and_exact(tmp_path):
    import zipfile
    from allin1.updater import _archive_payloads
    app, build = portable_fixture(tmp_path)
    first = candidate.write_portable(app, tmp_path / "first.zip", build)
    candidate.write_portable(app, tmp_path / "second.zip", build)
    assert (tmp_path / "first.zip").read_bytes() == (tmp_path / "second.zip").read_bytes()
    assert first["package_integrity"] == "PASS" and first["release_ready"] is False
    with zipfile.ZipFile(tmp_path / "first.zip") as archive:
        hashes = _archive_payloads(archive)
        assert len(hashes) == 5
        metadata = json.loads(archive.read("release.json"))
        assert metadata["entrypoint"] == "allin1-launcher-desktop.exe"
        assert metadata["unsigned_manual_download"] is True and metadata["release_qualified"] is False
        assert json.loads(archive.read("build-identity.json")) == build
    with pytest.raises(FileExistsError):
        candidate.write_portable(app, tmp_path / "first.zip", build)


@pytest.mark.parametrize("mutation", ["shell", "service", "metadata", "inside"])
def test_portable_preflights_required_payloads_and_reserved_names(tmp_path, mutation):
    app, build = portable_fixture(tmp_path)
    destination = tmp_path / "output.zip"
    if mutation == "shell": (app / "allin1-launcher-desktop.exe").unlink()
    elif mutation == "service": (app / "sidecar" / runtime.SIDECAR_NAME).unlink()
    elif mutation == "metadata": (app / "RELEASE.JSON").write_bytes(b"stale")
    else: destination = app / "output.zip"
    with pytest.raises(ValueError):
        candidate.write_portable(app, destination, build)
    assert not destination.exists()


def test_native_release_build_embeds_frontend_and_probes_actual_shell():
    source = (ROOT / "tools/launcher_desktop_candidate.py").read_text(encoding="utf-8")
    guard = (ROOT / "desktop/src-tauri/build.rs").read_text(encoding="utf-8")
    assert '"--features", "tauri/custom-protocol"' in source
    assert '"--verify-embedded-frontend"' in source
    assert '!tauri_build::is_dev()' in guard


def test_frozen_smoke_requires_exact_current_builtin_content_catalog():
    source = (ROOT / "tools/launcher_desktop_candidate.py").read_text(
        encoding="utf-8"
    )
    assert 'builtin_ids != ["allin1.online-content"]' in source
    assert 'len(library["builtin_packages"]) != 2' not in source
