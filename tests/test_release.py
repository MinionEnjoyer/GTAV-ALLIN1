import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from allin1.release import (
    PUBLIC_ROOT_FILES,
    PUBLIC_SMOKE_EXAMPLE_SOURCES,
    build_public_release,
    collect_public_files,
    _validate_public_path,
    validate_version_consistency,
    verify_public_release,
)


ROOT = Path(__file__).resolve().parents[1]


def _reactor_pair_contract(
    core: bytes, bridge: bytes, version: str = "0.6.4",
) -> bytes:
    return json.dumps({
        "schema_version": 1,
        "version": version,
        "core_file": "ALLIN1.dll",
        "core_sha256": hashlib.sha256(core).hexdigest(),
        "bridge_file": "ALLIN1.ReactorBridge.plugin",
        "bridge_sha256": hashlib.sha256(bridge).hexdigest(),
    }, separators=(",", ":")).encode("utf-8")


def _release_tree(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    from allin1.reactor_dependency import UI_REQUIRED, TAG
    ui_root = root / "data/reactor/allin1-ui"
    ui_files = {}
    for name in UI_REQUIRED:
        target = ui_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"ui-fixture")
        ui_files[name] = hashlib.sha256(b"ui-fixture").hexdigest()
    (ui_root / "allin1-ui.json").write_text(json.dumps(dict(
        schema_version=1, profile="allin1-composition", reactor_release=TAG, files=ui_files,
    )), encoding="utf-8")
    for relative in PUBLIC_ROOT_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture {relative}\n", encoding="utf-8")

    (root / "pyproject.toml").write_text(
        '[project]\nname = "gta-v-allin1"\nversion = "0.6.4"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        '[[package]]\nname = "gta-v-allin1"\nversion = "0.6.4"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("Current public release: **0.6.4**\n")
    (root / "RELEASE_NOTES.md").write_text("# Release 0.6.4\n")

    core = b"client"
    bridge = b"reactor-bridge"
    files = {
        "src/allin1/__init__.py": b'__version__ = "0.6.4"\n',
        "src/allin1/assets/logo.png": b"png",
        "content/allin1-content.schema.json": b'{"schema_version":1}',
        "content/allin1-vehicle-catalog.schema.json": b'{"schema_version":1}',
        "content/allin1-online-content/allin1.content.json": b'{"schema_version":1,"version":"0.6.4"}',
        "content/allin1-experimental-gameplay/allin1.content.json": b'{"schema_version":1,"version":"0.6.4"}',
        "data/story_vehicles.json": b'{"vehicles":[]}',
        "data/vehicles.toml": b"data",
        "data/vehicle_grounding.json": b'{"Entries":{}}',
        "script/dist/ALLIN1.dll": core,
        "script/dist/ALLIN1.ReactorBridge.plugin": bridge,
        "script/dist/ALLIN1.ReactorBridge.contract.json":
            _reactor_pair_contract(core, bridge),
        "script/dist/previews/test.png": b"preview",
        "mods/README.md": b"mods",
        "mods/examples/script/mod.toml.example": b"example",
        "tools/RpfPatcher/RpfPatcher.exe": b"patcher",
        "tools/RpfPatcher/CodeWalker.Core.dll": b"codewalker",
        "tools/RpfPatcher/RpfPatcher.pdb": b"symbols",
        "tools/RpfPatcher/Program.cs": b"source",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "script/ALLIN1.csproj").write_text(
        "<Project><PropertyGroup><Version>0.6.4</Version>"
        "<AssemblyVersion>0.6.4.0</AssemblyVersion>"
        "<FileVersion>0.6.4.0</FileVersion></PropertyGroup></Project>"
    )
    bridge_project = root / "script/reactor-bridge/ALLIN1.ReactorBridge.csproj"
    bridge_project.parent.mkdir(parents=True, exist_ok=True)
    bridge_project.write_text(
        "<Project><PropertyGroup><Version>0.6.4</Version>"
        "<AssemblyVersion>0.6.4.0</AssemblyVersion>"
        "<FileVersion>0.6.4.0</FileVersion></PropertyGroup></Project>"
    )
    return root


def test_repository_release_versions_and_tool_surface_are_consistent():
    report = validate_version_consistency(ROOT)
    assert report.version == "0.6.4"


def test_public_file_collection_is_explicit_and_excludes_sources(tmp_path):
    root = _release_tree(tmp_path)
    names = {path.relative_to(root).as_posix() for path in collect_public_files(root)}
    assert "script/dist/ALLIN1.dll" in names
    assert "script/dist/ALLIN1.ReactorBridge.plugin" in names
    assert "script/dist/ALLIN1.ReactorBridge.contract.json" in names
    assert "content/allin1-online-content/allin1.content.json" in names
    assert "content/allin1-vehicle-catalog.schema.json" in names
    assert "content/allin1-experimental-gameplay/allin1.content.json" in names
    assert "data/story_vehicles.json" in names
    assert "data/vehicle_grounding.json" in names
    assert "tools/RpfPatcher/RpfPatcher.exe" in names
    assert "tools/RpfPatcher/strings.txt" not in names
    assert "mods/README.md" in names
    assert not any(name.startswith("mods/realistic-suppressors/") for name in names)
    assert "docs/content-extension-api.md" in names
    assert "docs/gtaiv-npc-physics-experiment.md" in names
    assert "docs/optional-assistant.md" in names
    assert "docs/realistic-suppressors.md" in names
    assert "sdk/examples/colored_smokes/addon.json" in names
    assert set(PUBLIC_SMOKE_EXAMPLE_SOURCES).issubset(names)
    assert "mods/examples/script/mod.toml.example" not in names
    assert "tools/RpfPatcher/RpfPatcher.pdb" not in names


@pytest.mark.parametrize("project", ["realistic-suppressors", "weapon-pack-bundle", "gta-vr", "gta-v-fpv"])
def test_independent_project_payloads_are_not_collected_or_accepted(tmp_path, project):
    root = _release_tree(tmp_path)
    relative = f"mods/{project}/payload/Independent.dll"
    source = root / relative
    source.parent.mkdir(parents=True)
    source.write_bytes(b"independent project; not an ALLIN1 component")
    names = {path.relative_to(root).as_posix() for path in collect_public_files(root)}
    assert relative not in names
    with pytest.raises(ValueError, match="Independent mod"):
        _validate_public_path(relative)
    with pytest.raises(ValueError, match="Independent mod"):
        _validate_public_path(relative.upper())
    assert source.read_bytes() == b"independent project; not an ALLIN1 component"


@pytest.mark.parametrize("filename", ["RealisticSuppressors.dll", "OtherWeaponPack.dll", "VR.asi", "FPV.plugin"])
def test_staged_independent_binaries_cannot_leak_into_verified_release(tmp_path, filename):
    root = _release_tree(tmp_path)
    relative = f"script/dist/{filename}"
    (root / relative).write_bytes(b"not core")
    with pytest.raises(ValueError, match="Unapproved runtime"):
        _validate_public_path(relative)
    # DLL/plugin files are otherwise selected by the runtime tree rule.
    if Path(filename).suffix in {".dll", ".plugin"}:
        with pytest.raises(ValueError, match="Unapproved runtime"):
            collect_public_files(root)
    archive = tmp_path / "foreign.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(relative, b"not core")
    with pytest.raises(ValueError, match="Unapproved runtime"):
        verify_public_release(archive)


def test_allin1_build_and_test_entrypoints_do_not_build_independent_mods():
    for name in ("test-all.ps1", "test-all.sh", ".github/workflows/build-asi.yml", ".github/workflows/test.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "mods/realistic-suppressors/" not in text, name
    independent = (ROOT / ".github/workflows/suppressors-tests.yml").read_text(encoding="utf-8")
    assert "mods/realistic-suppressors/tests/test_package_contract.py" in independent
    assert "RealisticSuppressors.Tests.csproj" in independent


def test_public_release_round_trip_and_tamper_detection(tmp_path):
    root = _release_tree(tmp_path)
    archive = tmp_path / "ALLIN1.zip"
    report = build_public_release(root, archive)
    assert report.version == "0.6.4"
    assert report.file_count > len(PUBLIC_ROOT_FILES)

    with zipfile.ZipFile(archive) as bundle:
        assert json.loads(bundle.read("release.json"))["entrypoint"] == "install.bat"
        assert "checksums.json" in bundle.namelist()
        assert "script/dist/ALLIN1.ReactorBridge.plugin" in bundle.namelist()
        assert "script/dist/ALLIN1.ReactorBridge.contract.json" in bundle.namelist()
        assert "docs/gtaiv-npc-physics-experiment.md" in bundle.namelist()
        assert "docs/optional-assistant.md" in bundle.namelist()
        assert "docs/realistic-suppressors.md" in bundle.namelist()
        assert not any(
            name.startswith("mods/realistic-suppressors/")
            for name in bundle.namelist()
        )
        assert set(PUBLIC_SMOKE_EXAMPLE_SOURCES).issubset(bundle.namelist())

    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as destination:
        for item in source.infolist():
            content = source.read(item)
            if item.filename == "script/dist/ALLIN1.dll":
                content = b"tampered"
            destination.writestr(item, content)
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_public_release(broken)


def test_release_rejects_version_drift(tmp_path):
    root = _release_tree(tmp_path)
    (root / "script/ALLIN1.csproj").write_text(
        "<Project><PropertyGroup><Version>0.2.0</Version></PropertyGroup></Project>"
    )
    with pytest.raises(ValueError, match="version mismatch"):
        validate_version_consistency(root)


def test_release_build_rejects_mixed_core_and_bridge_binaries(tmp_path):
    root = _release_tree(tmp_path)
    (root / "script/dist/ALLIN1.ReactorBridge.plugin").write_bytes(
        b"new-bridge-with-stale-contract"
    )

    with pytest.raises(ValueError, match="does not match the Reactor bridge"):
        build_public_release(root, tmp_path / "mixed.zip")


@pytest.mark.parametrize("package", [
    "allin1-online-content",
    "allin1-experimental-gameplay",
])
def test_release_rejects_official_content_manifest_version_drift(
    tmp_path, package
):
    root = _release_tree(tmp_path)
    manifest = root / "content" / package / "allin1.content.json"
    manifest.write_text(
        '{"schema_version":1,"version":"9.9.9"}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="version mismatch"):
        validate_version_consistency(root)


@pytest.mark.parametrize(("relative", "match"), [
    ("../secret", "unsafe"),
    ("tests/test_release.py", "development/private"),
    ("mods/examples/script/mod.toml.example", "sample/test mod"),
    ("script/src/GbayShop.cs", "client source/tooling"),
    ("tools/RpfPatcher/SeatCatalogAudit.cs", "tool source"),
    ("tools/RpfPatcher/RpfPatcher.pdb", "debug symbols"),
])
def test_release_path_guard_rejects_private_and_development_files(relative, match):
    with pytest.raises(ValueError, match=match):
        _validate_public_path(relative)


def test_public_smoke_example_has_every_declared_source() -> None:
    names = {
        path.relative_to(ROOT).as_posix()
        for path in collect_public_files(ROOT, require_toolchain=False)
    }
    descriptor = json.loads(
        (ROOT / "sdk/examples/colored_smokes/addon.json").read_text(encoding="utf-8")
    )
    declared_sources = {
        item["source"]
        for section in ("nodes", "install_steps")
        for item in descriptor[section]
        if item.get("source")
    }
    assert declared_sources == set(PUBLIC_SMOKE_EXAMPLE_SOURCES)
    assert declared_sources.issubset(names)


def test_collection_reports_missing_release_inputs(tmp_path):
    root = _release_tree(tmp_path)
    (root / "LICENSE").unlink()
    with pytest.raises(FileNotFoundError, match="LICENSE"):
        collect_public_files(root)

    root = _release_tree(tmp_path / "missing-tree")
    for path in sorted((root / "data").rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    (root / "data").rmdir()
    with pytest.raises(FileNotFoundError, match="data"):
        collect_public_files(root)

    root = _release_tree(tmp_path / "missing-patcher")
    (root / "tools/RpfPatcher/RpfPatcher.exe").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="runtools.ps1"):
        collect_public_files(root)
    assert collect_public_files(root, require_toolchain=False)


@pytest.mark.parametrize(("target", "content", "match"), [
    ("README.md", "no release here", "README"),
    ("RELEASE_NOTES.md", "no version here", "release notes"),
])
def test_version_validation_requires_public_documentation(tmp_path, target, content, match):
    root = _release_tree(tmp_path)
    (root / target).write_text(content)
    with pytest.raises(ValueError, match=match):
        validate_version_consistency(root)


def test_version_validation_rejects_extra_or_missing_client_tools(tmp_path):
    root = _release_tree(tmp_path)
    (root / "script/tools").mkdir(parents=True, exist_ok=True)
    (root / "script/tools/ExtraTool.cs").write_text("tool")
    with pytest.raises(
        ValueError,
        match="production C# tools",
    ):
        validate_version_consistency(root)


def test_version_validation_rejects_retired_runtime_developer_tools(tmp_path):
    root = _release_tree(tmp_path)
    runtime_tool = root / "script/src/GarageTraversalLab.cs"
    runtime_tool.parent.mkdir(parents=True, exist_ok=True)
    runtime_tool.write_text("// retired runtime lab", encoding="utf-8")
    with pytest.raises(ValueError, match="retired runtime developer tools"):
        validate_version_consistency(root)


def _write_manifest_archive(path: Path, files: dict[str, bytes]) -> None:
    checksums = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("checksums.json", json.dumps(checksums))


def test_release_verifier_rejects_rechecksummed_mixed_binary_pair(tmp_path):
    root = _release_tree(tmp_path / "source")
    original = tmp_path / "original.zip"
    build_public_release(root, original)
    mixed = tmp_path / "mixed.zip"
    with zipfile.ZipFile(original) as source:
        files = {
            name: source.read(name)
            for name in source.namelist()
            if name != "checksums.json"
        }
    files["script/dist/ALLIN1.dll"] = b"different-core"
    _write_manifest_archive(mixed, files)

    with pytest.raises(ValueError, match="does not match the Reactor bridge"):
        verify_public_release(mixed)


def test_release_verifier_rejects_structural_manifest_errors(tmp_path):
    missing_metadata = tmp_path / "missing-metadata.zip"
    _write_manifest_archive(missing_metadata, {"README.md": b"readme"})
    with pytest.raises(ValueError, match="missing checksums.json or release.json"):
        verify_public_release(missing_metadata)

    unmatched = tmp_path / "unmatched.zip"
    with zipfile.ZipFile(unmatched, "w") as archive:
        archive.writestr("release.json", b'{"version":"0.6.4"}')
        archive.writestr("extra.txt", b"extra")
        archive.writestr("checksums.json", json.dumps({
            "release.json": hashlib.sha256(b'{"version":"0.6.4"}').hexdigest(),
        }))
    with pytest.raises(ValueError, match="exactly match"):
        verify_public_release(unmatched)

    wrong_version = tmp_path / "wrong-version.zip"
    _write_manifest_archive(wrong_version, {"release.json": b'{"version":"9.9.9"}'})
    with pytest.raises(ValueError, match="metadata version"):
        verify_public_release(wrong_version)

    incomplete = tmp_path / "incomplete.zip"
    _write_manifest_archive(incomplete, {"release.json": b'{"version":"0.6.4"}'})
    with pytest.raises(ValueError, match="missing required files"):
        verify_public_release(incomplete)


def test_release_verifier_rejects_duplicate_members(tmp_path):
    archive = tmp_path / "duplicate.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("release.json", b"one")
            bundle.writestr("release.json", b"two")
            bundle.writestr("checksums.json", b"{}")
    with pytest.raises(ValueError, match="duplicate archive members"):
        verify_public_release(archive)
