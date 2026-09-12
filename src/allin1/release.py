"""Build and verify a minimal, end-user ALLIN1 release archive."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

from allin1 import __version__
from allin1.reactor_bridge_contract import (
    BRIDGE_FILENAME,
    CONTRACT_FILENAME,
    CORE_FILENAME,
    validate_reactor_bridge_pair,
    validate_reactor_bridge_pair_payloads,
)
from allin1.updater import package_release


PUBLIC_SMOKE_EXAMPLE_SOURCES = (
    "docs/enhanced-smoke-rpf-port.md",
    "script/src/EnhancedSmokeController.cs",
    "script/src/SmokeGrenadeCatalog.cs",
    "tools/RpfPatcher/Program.cs",
)

PUBLIC_DOCUMENTATION_FILES = (
    "docs/audits/vehicle-support-20260906.md",
    "docs/audits/vehicle-support-matrix-20260906.md",
    "docs/complete-vehicle-catalog.md",
    "docs/driving-telemetry.md",
    "docs/trailer-hitches.md",
    "desktop/README.md",
    "docs/README.md",
    "docs/architecture-review-react-0.6.4.md",
    "docs/archive/release-notes-before-0.6.4.md",
    "docs/cli-reference.md",
    "docs/configuration-reference.md",
    "docs/content-extension-api.md",
    "docs/development.md",
    "docs/edition-bundles.md",
    "docs/enhanced-smoke-rpf-port.md",
    "docs/gbay-weapon-catalogs.md",
    "docs/gtaiv-npc-physics-experiment.md",
    "docs/launcher-guide.md",
    "docs/mpclothes-compatibility-architecture.md",
    "docs/optional-assistant.md",
    "docs/react-release-harness.md",
    "docs/realistic-suppressors.md",
    "docs/release-0.6.4.md",
    "docs/release-0.6.5.md",
    "docs/gbay-default-previews.md",
    "docs/hardening-harness.md",
    "docs/rpf-authoring-safety.md",
    "docs/suppressor-json-profiles.md",
    "docs/suppressor-sleeve-tracking.md",
    "docs/test-tools-capability-review.md",
    "docs/vector-suppressor-integration.md",
    "docs/ymt-limit-expansion-research-and-architecture.md",
    "docs/catalog.json",
)


PUBLIC_ROOT_FILES = (
    "LICENSE",
    "README.md",
    "RELEASE_NOTES.md",
    *PUBLIC_DOCUMENTATION_FILES,
    "config.example.toml",
    "install.bat",
    "manager.bat",
    "uninstall.bat",
    "update.bat",
    "pyproject.toml",
    "uv.lock",
    "prices_gear.toml",
    "prices_vehicles.toml",
    "prices_weapons.toml",
    "mods/README.md",
    "sdk/examples/colored_smokes/addon.json",
    f"script/dist/{CONTRACT_FILENAME}",
    *PUBLIC_SMOKE_EXAMPLE_SOURCES,
)

PUBLIC_TREE_RULES = {
    "src/allin1": frozenset({".py", ".png", ".ico"}),
    "content": frozenset({".json"}),
    "data": None,
    "script/dist": frozenset({".dll", ".plugin"}),
}

FORBIDDEN_PARTS = frozenset({
    ".git", ".github", ".pytest_cache", "__pycache__", ".venv",
    "tests", "logs", "catalog", "work", "htmlcov", "obj", "bin",
})

FORBIDDEN_NAMES = frozenset({
    ".coverage", ".gta_path", ".gh_token", "allin1.log", "config.toml",
    "runtools.ps1", "test-all.ps1", "test-all.sh", "upload_log.bat",
})

TOOL_SOURCE_SUFFIXES = frozenset({".cs", ".csproj", ".pdb"})
RPF_TOOL_RUNTIME_IGNORED_NAMES = frozenset({"strings.txt"})

FORBIDDEN_RUNTIME_DEV_FILES = frozenset({
    "GarageTraversalLab.cs",
})


@dataclass(frozen=True)
class ReleaseReport:
    version: str
    file_count: int
    unpacked_bytes: int
    archive: Path | None = None


def _files_under(root: Path, relative: str, suffixes: frozenset[str] | None) -> list[Path]:
    directory = root / relative
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    files = []
    for path in directory.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if suffixes is None or path.suffix.lower() in suffixes:
            files.append(path)
    return files


def collect_public_files(root: Path, *, require_toolchain: bool = True, require_preview_worker: bool = True) -> list[Path]:
    """Return the explicit public payload; no git-status or glob accidents."""
    root = root.resolve()
    files: list[Path] = []
    for relative in PUBLIC_ROOT_FILES:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(path)

    for relative, suffixes in PUBLIC_TREE_RULES.items():
        files.extend(_files_under(root, relative, suffixes))

    from allin1.reactor_dependency import consumer_files
    consumer_files(root / "data/reactor/allin1-ui")

    patcher = root / "tools" / "RpfPatcher"
    if require_toolchain:
        executable = patcher / "RpfPatcher.exe"
        if not executable.is_file() or executable.stat().st_size == 0:
            raise FileNotFoundError(
                f"{executable} (run runtools.ps1 before packaging)"
            )
        files.extend(
            path for path in patcher.iterdir()
            if (
                path.is_file()
                and path.suffix.lower() not in TOOL_SOURCE_SUFFIXES
                and path.name.casefold() not in RPF_TOOL_RUNTIME_IGNORED_NAMES
            )
        )

    preview_worker = root / "tools" / "WeaponPreview" / "WeaponPreview.exe"
    if require_toolchain and require_preview_worker and (not preview_worker.is_file() or preview_worker.stat().st_size == 0):
        raise FileNotFoundError("WeaponPreview.exe is missing; run tools/build_weapon_preview_worker.py before packaging")
    if preview_worker.is_file():
        files.append(preview_worker)
    unique = {path.resolve(): path for path in files}
    ordered = sorted(unique.values(), key=lambda path: path.relative_to(root).as_posix())
    for path in ordered:
        _validate_public_path(path.relative_to(root).as_posix())
    return ordered


def _validate_public_path(relative: str) -> None:
    path = PurePosixPath(relative)
    normalized = path.as_posix()
    lowered_parts = {part.lower() for part in path.parts}
    if tuple(part.casefold() for part in path.parts[:2]) == ("script", "dist"):
        if path.suffix.casefold() == ".png":
            raise ValueError("Catalog artwork belongs in the separate preview download pack, not the launcher release")
        if path.suffix.casefold() in {".dll", ".plugin", ".asi", ".exe", ".zip", ".oiv"} and normalized not in {
            f"script/dist/{CORE_FILENAME}", f"script/dist/{BRIDGE_FILENAME}",
        }:
            raise ValueError(f"Unapproved runtime component in ALLIN1 release: {relative}")
    if normalized.startswith("data/reactor/") and path.suffix.lower() in {".exe", ".dll", ".asi", ".zip"}:
        raise ValueError("Reactor runtime binaries must be downloaded as a shared dependency, not bundled")
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe release path: {relative}")
    if path.name.lower() in FORBIDDEN_NAMES or lowered_parts & FORBIDDEN_PARTS:
        raise ValueError(f"development/private file is not allowed in a release: {relative}")
    if tuple(part.lower() for part in path.parts[:2]) == ("mods", "examples"):
        raise ValueError(f"sample/test mod is not allowed in a release: {relative}")
    if path.parts and path.parts[0].casefold() == "mods" and normalized != "mods/README.md":
        raise ValueError(f"Independent mod payload is not an ALLIN1 release component: {relative}")
    if (
        tuple(part.lower() for part in path.parts[:2]) == ("script", "src")
        and normalized not in PUBLIC_SMOKE_EXAMPLE_SOURCES
    ) or tuple(part.lower() for part in path.parts[:2]) == ("script", "tools"):
        raise ValueError(f"client source/tooling is not allowed in a public release: {relative}")
    if (
        tuple(part.lower() for part in path.parts[:2]) == ("tools", "rpfpatcher")
        and path.suffix.lower() in TOOL_SOURCE_SUFFIXES
        and path.suffix.lower() != ".pdb"
        and normalized not in PUBLIC_SMOKE_EXAMPLE_SOURCES
    ):
        raise ValueError(f"tool source is not allowed in a public release: {relative}")
    if path.suffix.lower() == ".pdb":
        raise ValueError(f"debug symbols are not allowed in a public release: {relative}")


def validate_version_consistency(root: Path, version: str = __version__) -> ReleaseReport:
    """Fail fast when independently versioned release surfaces disagree."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    package_init = (root / "src" / "allin1" / "__init__.py").read_text(encoding="utf-8")
    python_version = re.search(r'__version__\s*=\s*"([^"]+)"', package_init)
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    lock_version = next(
        (str(package["version"]) for package in lock.get("package", [])
         if package.get("name") == "gta-v-allin1"),
        "missing",
    )
    csproj = (root / "script" / "ALLIN1.csproj").read_text(encoding="utf-8")
    cs_version = re.search(r"<Version>([^<]+)</Version>", csproj)
    assembly_version = re.search(r"<AssemblyVersion>([^<]+)</AssemblyVersion>", csproj)
    file_version = re.search(r"<FileVersion>([^<]+)</FileVersion>", csproj)
    bridge_csproj = (
        root / "script" / "reactor-bridge" / "ALLIN1.ReactorBridge.csproj"
    ).read_text(encoding="utf-8")
    bridge_version = re.search(r"<Version>([^<]+)</Version>", bridge_csproj)
    bridge_assembly_version = re.search(
        r"<AssemblyVersion>([^<]+)</AssemblyVersion>", bridge_csproj,
    )
    bridge_file_version = re.search(
        r"<FileVersion>([^<]+)</FileVersion>", bridge_csproj,
    )
    online_content = json.loads(
        (root / "content" / "allin1-online-content" / "allin1.content.json")
        .read_text(encoding="utf-8")
    )
    experimental_content = json.loads(
        (root / "content" / "allin1-experimental-gameplay" / "allin1.content.json")
        .read_text(encoding="utf-8")
    )
    readme = (root / "README.md").read_text(encoding="utf-8")
    notes = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    observed = {
        "Python package": project_version,
        "Python module": python_version.group(1) if python_version else "missing",
        "uv lock": lock_version,
        "C# client": cs_version.group(1) if cs_version else "missing",
        "C# assembly": assembly_version.group(1).removesuffix(".0") if assembly_version else "missing",
        "C# file": file_version.group(1).removesuffix(".0") if file_version else "missing",
        "Reactor bridge": bridge_version.group(1) if bridge_version else "missing",
        "Reactor bridge assembly": (
            bridge_assembly_version.group(1).removesuffix(".0")
            if bridge_assembly_version else "missing"
        ),
        "Reactor bridge file": (
            bridge_file_version.group(1).removesuffix(".0")
            if bridge_file_version else "missing"
        ),
        "Online content manifest": str(online_content.get("version", "missing")),
        "Experimental content manifest": str(
            experimental_content.get("version", "missing")
        ),
    }
    mismatches = [f"{name}={value}" for name, value in observed.items() if value != version]
    if mismatches:
        raise ValueError(f"release version mismatch (expected {version}): " + ", ".join(mismatches))
    if f"**{version}**" not in readme:
        raise ValueError(f"README does not identify release {version}")
    if version not in notes:
        raise ValueError(f"release notes do not identify release {version}")

    tool_sources = sorted(path.name for path in (root / "script" / "tools").glob("*.cs"))
    if tool_sources:
        raise ValueError(
            "production C# tools must not remain in "
            f"script/tools: {tool_sources}"
        )

    runtime_dev_files = sorted(
        path.name for path in (root / "script" / "src").glob("*.cs")
        if path.name in FORBIDDEN_RUNTIME_DEV_FILES
    )
    if runtime_dev_files:
        raise ValueError(
            "retired runtime developer tools must not be compiled into a "
            f"public client: {runtime_dev_files}"
        )

    return ReleaseReport(version, 0, 0)


def build_public_release(root: Path, output: Path, version: str = __version__) -> ReleaseReport:
    """Create the checksum-verified Windows distribution ZIP."""
    root = root.resolve()
    validate_version_consistency(root, version)
    validate_reactor_bridge_pair(
        root / "script" / "dist", expected_version=version,
    )
    files = collect_public_files(root)
    metadata = {
        "format": 1,
        "name": "GTA V ALLIN1",
        "version": version,
        "entrypoint": "install.bat",
        "platform": "Windows",
    }
    package_release(
        output,
        root,
        files,
        extra_files={
            "release.json": (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
        },
    )
    report = verify_public_release(output, version)
    return ReleaseReport(report.version, report.file_count, report.unpacked_bytes, output)


def verify_public_release(archive_path: Path, version: str = __version__) -> ReleaseReport:
    """Verify checksums, metadata, required files, and public-only contents."""
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("release contains duplicate archive members")
        for name in names:
            if name != "checksums.json":
                _validate_public_path(name)

        if "checksums.json" not in names or "release.json" not in names:
            raise ValueError("release is missing checksums.json or release.json")
        checksums = json.loads(archive.read("checksums.json"))
        payload = set(names) - {"checksums.json"}
        if set(checksums) != payload:
            raise ValueError("checksum manifest does not exactly match the release payload")
        for name, expected in checksums.items():
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            if actual != str(expected).lower():
                raise ValueError(f"checksum mismatch: {name}")

        metadata = json.loads(archive.read("release.json"))
        if metadata.get("version") != version:
            raise ValueError(f"release metadata version is not {version}")
        required = set(PUBLIC_ROOT_FILES) | {
            "content/allin1-vehicle-catalog.schema.json",
            "data/story_vehicles.json",
            "data/vehicle_grounding.json",
            f"script/dist/{CORE_FILENAME}",
            f"script/dist/{BRIDGE_FILENAME}",
            f"script/dist/{CONTRACT_FILENAME}",
            "tools/RpfPatcher/RpfPatcher.exe",
        }
        missing = sorted(required - payload)
        if missing:
            raise ValueError("release is missing required files: " + ", ".join(missing))
        from allin1.reactor_dependency import UI_REQUIRED, TAG
        ui_prefix = "data/reactor/allin1-ui/"
        manifest_name = ui_prefix + "allin1-ui.json"
        if manifest_name not in payload:
            raise ValueError("release is missing the ALLIN1 Reactor UI composition")
        ui_manifest = json.loads(archive.read(manifest_name))
        if (ui_manifest.get("schema_version"), ui_manifest.get("profile"), ui_manifest.get("reactor_release")) != (1, "allin1-composition", TAG):
            raise ValueError("release contains an incompatible Reactor UI composition")
        ui_files = ui_manifest.get("files", {})
        if not isinstance(ui_files, dict) or not UI_REQUIRED <= ui_files.keys():
            raise ValueError("release is missing ALLIN1 UI files or licenses")
        if {name.removeprefix(ui_prefix) for name in payload if name.startswith(ui_prefix)} != {*ui_files, "allin1-ui.json"}:
            raise ValueError("ALLIN1 UI manifest does not match the release payload")
        for name, expected in ui_files.items():
            if hashlib.sha256(archive.read(ui_prefix + name)).hexdigest() != expected:
                raise ValueError(f"ALLIN1 UI checksum mismatch: {name}")
        validate_reactor_bridge_pair_payloads(
            archive.read(f"script/dist/{CORE_FILENAME}"),
            archive.read(f"script/dist/{BRIDGE_FILENAME}"),
            archive.read(f"script/dist/{CONTRACT_FILENAME}"),
            expected_version=version,
        )
        size = sum(archive.getinfo(name).file_size for name in payload)
    return ReleaseReport(version, len(payload), size, archive_path)
