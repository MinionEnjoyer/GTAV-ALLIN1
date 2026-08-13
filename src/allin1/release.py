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
from allin1.updater import package_release


PUBLIC_ROOT_FILES = (
    "LICENSE",
    "README.md",
    "RELEASE_NOTES.md",
    "documentation.md",
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
)

PUBLIC_TREE_RULES = {
    "src/allin1": frozenset({".py", ".png", ".ico"}),
    "data": None,
    "script/dist": frozenset({".dll", ".png"}),
    "mods": frozenset({".md", ".example"}),
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


def collect_public_files(root: Path, *, require_toolchain: bool = True) -> list[Path]:
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

    patcher = root / "tools" / "RpfPatcher"
    if require_toolchain:
        executable = patcher / "RpfPatcher.exe"
        if not executable.is_file() or executable.stat().st_size == 0:
            raise FileNotFoundError(
                f"{executable} (run runtools.ps1 before packaging)"
            )
        files.extend(
            path for path in patcher.iterdir()
            if path.is_file() and path.suffix.lower() not in TOOL_SOURCE_SUFFIXES
        )

    unique = {path.resolve(): path for path in files}
    ordered = sorted(unique.values(), key=lambda path: path.relative_to(root).as_posix())
    for path in ordered:
        _validate_public_path(path.relative_to(root).as_posix())
    return ordered


def _validate_public_path(relative: str) -> None:
    path = PurePosixPath(relative)
    lowered_parts = {part.lower() for part in path.parts}
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe release path: {relative}")
    if path.name.lower() in FORBIDDEN_NAMES or lowered_parts & FORBIDDEN_PARTS:
        raise ValueError(f"development/private file is not allowed in a release: {relative}")
    if tuple(part.lower() for part in path.parts[:2]) in {
        ("script", "src"), ("script", "tools"),
    }:
        raise ValueError(f"client source/tooling is not allowed in a public release: {relative}")
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
    readme = (root / "README.md").read_text(encoding="utf-8")
    notes = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    observed = {
        "Python package": project_version,
        "Python module": python_version.group(1) if python_version else "missing",
        "uv lock": lock_version,
        "C# client": cs_version.group(1) if cs_version else "missing",
        "C# assembly": assembly_version.group(1).removesuffix(".0") if assembly_version else "missing",
        "C# file": file_version.group(1).removesuffix(".0") if file_version else "missing",
    }
    mismatches = [f"{name}={value}" for name, value in observed.items() if value != version]
    if mismatches:
        raise ValueError(f"release version mismatch (expected {version}): " + ", ".join(mismatches))
    if f"**{version}**" not in readme:
        raise ValueError(f"README does not identify release {version}")
    if version not in notes:
        raise ValueError(f"release notes do not identify release {version}")

    tool_sources = sorted(path.name for path in (root / "script" / "tools").glob("*.cs"))
    supported_tools = ["SeatTestTool.cs", "WorldVectorTool.cs"]
    if tool_sources != supported_tools:
        raise ValueError(
            "only SeatTestTool.cs and WorldVectorTool.cs may remain in "
            f"script/tools: {tool_sources}"
        )

    return ReleaseReport(version, 0, 0)


def build_public_release(root: Path, output: Path, version: str = __version__) -> ReleaseReport:
    """Create the checksum-verified Windows distribution ZIP."""
    root = root.resolve()
    validate_version_consistency(root, version)
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
            "script/dist/ALLIN1.dll",
            "script/dist/LemonUI.SHVDN3.dll",
            "tools/RpfPatcher/RpfPatcher.exe",
        }
        missing = sorted(required - payload)
        if missing:
            raise ValueError("release is missing required files: " + ", ".join(missing))
        size = sum(archive.getinfo(name).file_size for name in payload)
    return ReleaseReport(version, len(payload), size, archive_path)
