import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from allin1.release import (
    PUBLIC_ROOT_FILES,
    build_public_release,
    collect_public_files,
    _validate_public_path,
    validate_version_consistency,
    verify_public_release,
)


ROOT = Path(__file__).resolve().parents[1]


def _release_tree(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    for relative in PUBLIC_ROOT_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture {relative}\n", encoding="utf-8")

    (root / "pyproject.toml").write_text(
        '[project]\nname = "gta-v-allin1"\nversion = "0.3.1"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        '[[package]]\nname = "gta-v-allin1"\nversion = "0.3.1"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("Current public release: **0.3.1**\n")
    (root / "RELEASE_NOTES.md").write_text("# Release 0.3.1\n")

    files = {
        "src/allin1/__init__.py": b'__version__ = "0.3.1"\n',
        "src/allin1/assets/logo.png": b"png",
        "data/vehicles.toml": b"data",
        "script/dist/ALLIN1.dll": b"client",
        "script/dist/LemonUI.SHVDN3.dll": b"lemon",
        "script/dist/previews/test.png": b"preview",
        "mods/README.md": b"mods",
        "mods/examples/script/mod.toml.example": b"example",
        "tools/RpfPatcher/RpfPatcher.exe": b"patcher",
        "tools/RpfPatcher/CodeWalker.Core.dll": b"codewalker",
        "tools/RpfPatcher/RpfPatcher.pdb": b"symbols",
        "tools/RpfPatcher/Program.cs": b"source",
        "script/tools/WorldVectorTool.cs": b"vector",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "script/ALLIN1.csproj").write_text(
        "<Project><PropertyGroup><Version>0.3.1</Version>"
        "<AssemblyVersion>0.3.1.0</AssemblyVersion>"
        "<FileVersion>0.3.1.0</FileVersion></PropertyGroup></Project>"
    )
    return root


def test_repository_release_versions_and_tool_surface_are_consistent():
    report = validate_version_consistency(ROOT)
    assert report.version == "0.3.1"


def test_public_file_collection_is_explicit_and_excludes_sources(tmp_path):
    root = _release_tree(tmp_path)
    names = {path.relative_to(root).as_posix() for path in collect_public_files(root)}
    assert "script/dist/ALLIN1.dll" in names
    assert "tools/RpfPatcher/RpfPatcher.exe" in names
    assert "tools/RpfPatcher/Program.cs" not in names
    assert "tools/RpfPatcher/RpfPatcher.pdb" not in names
    assert "script/tools/WorldVectorTool.cs" not in names


def test_public_release_round_trip_and_tamper_detection(tmp_path):
    root = _release_tree(tmp_path)
    archive = tmp_path / "ALLIN1.zip"
    report = build_public_release(root, archive)
    assert report.version == "0.3.1"
    assert report.file_count > len(PUBLIC_ROOT_FILES)

    with zipfile.ZipFile(archive) as bundle:
        assert json.loads(bundle.read("release.json"))["entrypoint"] == "install.bat"
        assert "checksums.json" in bundle.namelist()

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


@pytest.mark.parametrize(("relative", "match"), [
    ("../secret", "unsafe"),
    ("tests/test_release.py", "development/private"),
    ("script/src/GbayShop.cs", "client source/tooling"),
    ("tools/RpfPatcher/RpfPatcher.pdb", "debug symbols"),
])
def test_release_path_guard_rejects_private_and_development_files(relative, match):
    with pytest.raises(ValueError, match=match):
        _validate_public_path(relative)


def test_collection_reports_missing_release_inputs(tmp_path):
    root = _release_tree(tmp_path)
    (root / "LICENSE").unlink()
    with pytest.raises(FileNotFoundError, match="LICENSE"):
        collect_public_files(root)

    root = _release_tree(tmp_path / "missing-tree")
    for path in (root / "data").iterdir():
        path.unlink()
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
    (root / "script/tools/ExtraTool.cs").write_text("tool")
    with pytest.raises(ValueError, match="only WorldVectorTool"):
        validate_version_consistency(root)


def _write_manifest_archive(path: Path, files: dict[str, bytes]) -> None:
    checksums = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("checksums.json", json.dumps(checksums))


def test_release_verifier_rejects_structural_manifest_errors(tmp_path):
    missing_metadata = tmp_path / "missing-metadata.zip"
    _write_manifest_archive(missing_metadata, {"README.md": b"readme"})
    with pytest.raises(ValueError, match="missing checksums.json or release.json"):
        verify_public_release(missing_metadata)

    unmatched = tmp_path / "unmatched.zip"
    with zipfile.ZipFile(unmatched, "w") as archive:
        archive.writestr("release.json", b'{"version":"0.3.1"}')
        archive.writestr("extra.txt", b"extra")
        archive.writestr("checksums.json", json.dumps({
            "release.json": hashlib.sha256(b'{"version":"0.3.1"}').hexdigest(),
        }))
    with pytest.raises(ValueError, match="exactly match"):
        verify_public_release(unmatched)

    wrong_version = tmp_path / "wrong-version.zip"
    _write_manifest_archive(wrong_version, {"release.json": b'{"version":"9.9.9"}'})
    with pytest.raises(ValueError, match="metadata version"):
        verify_public_release(wrong_version)

    incomplete = tmp_path / "incomplete.zip"
    _write_manifest_archive(incomplete, {"release.json": b'{"version":"0.3.1"}'})
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
