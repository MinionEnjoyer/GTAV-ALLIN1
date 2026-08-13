"""Pre-launch installation health and conflict checks."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

from allin1.versioning import read_installed_version


@dataclass(frozen=True)
class HealthIssue:
    code: str
    severity: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class HealthReport:
    edition: str
    installed_version: str | None
    issues: tuple[HealthIssue, ...]

    @property
    def launch_safe(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict:
        return {"edition": self.edition, "installed_version": self.installed_version,
                "launch_safe": self.launch_safe,
                "issues": [asdict(issue) for issue in self.issues]}


@dataclass(frozen=True)
class BinaryInspection:
    valid: bool
    reason: str


def inspect_windows_binary(path: Path, *, minimum_size: int = 4096) -> BinaryInspection:
    """Perform a cheap structural PE check without loading third-party code."""
    if not path.is_file():
        return BinaryInspection(False, "missing")
    try:
        size = path.stat().st_size
        if size < minimum_size:
            return BinaryInspection(False, f"too small ({size} bytes)")
        with path.open("rb") as stream:
            header = stream.read(64)
            if len(header) < 64 or header[:2] != b"MZ":
                return BinaryInspection(False, "missing DOS/PE signature")
            pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
            if pe_offset < 64 or pe_offset + 6 > size:
                return BinaryInspection(False, "invalid PE header offset")
            stream.seek(pe_offset)
            pe_header = stream.read(6)
            if len(pe_header) != 6 or pe_header[:4] != b"PE\0\0":
                return BinaryInspection(False, "missing PE signature")
            machine = struct.unpack_from("<H", pe_header, 4)[0]
            if machine != 0x8664:
                return BinaryInspection(False, f"wrong architecture (0x{machine:04X})")
    except OSError as exc:
        return BinaryInspection(False, f"unreadable ({exc})")
    return BinaryInspection(True, "validated x64 PE file")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_installation(gta_path: Path, *, expected_hashes: dict[str, str] | None = None) -> HealthReport:
    issues: list[HealthIssue] = []
    legacy = gta_path / "GTA5.exe"
    enhanced = gta_path / "GTA5_Enhanced.exe"
    edition = "enhanced" if enhanced.is_file() else "legacy" if legacy.is_file() else "unknown"
    if edition == "unknown":
        issues.append(HealthIssue("game_missing", "error", "GTA V executable was not found.", str(gta_path)))
    for name in ("ScriptHookV.dll", "ScriptHookVDotNet.asi"):
        path = gta_path / name
        if not path.is_file():
            issues.append(HealthIssue("dependency_missing", "error", f"Required dependency is missing: {name}", str(path)))
        else:
            inspection = inspect_windows_binary(path)
            if not inspection.valid:
                issues.append(HealthIssue(
                    "dependency_corrupt", "error",
                    f"Required dependency is invalid: {name} ({inspection.reason}).", str(path),
                ))
    loader = "OpenRPF.asi" if edition == "enhanced" else "OpenIV.asi"
    if edition != "unknown" and not (gta_path / loader).is_file():
        issues.append(HealthIssue("rpf_loader_missing", "warning", f"{loader} is missing; previews may not load.", str(gta_path / loader)))
    elif edition != "unknown":
        inspection = inspect_windows_binary(gta_path / loader)
        if not inspection.valid:
            issues.append(HealthIssue(
                "rpf_loader_corrupt", "error", f"{loader} is invalid ({inspection.reason}).",
                str(gta_path / loader),
            ))
    if edition == "enhanced" and (gta_path / "OpenRPF.asi").exists():
        if (gta_path / "OpenIV.asi").exists():
            issues.append(HealthIssue("rpf_loader_conflict", "error",
                                      "OpenIV.asi cannot be loaded alongside OpenRPF on Enhanced.",
                                      str(gta_path / "OpenIV.asi")))
        loader_paths = [gta_path / name for name in
                        ("dsound.dll", "xinput1_4.dll", "dinput8.dll")]
        present_loaders = [path for path in loader_paths if path.is_file()]
        valid_loaders = [path for path in present_loaders
                         if inspect_windows_binary(path).valid]
        if not present_loaders:
            issues.append(HealthIssue("asi_loader_missing", "error",
                                      "OpenRPF is installed but no ASI loader was detected.",
                                      str(gta_path)))
        elif not valid_loaders:
            details = ", ".join(
                f"{path.name}: {inspect_windows_binary(path).reason}"
                for path in present_loaders
            )
            issues.append(HealthIssue(
                "asi_loader_corrupt", "error",
                f"ASI loader files are present but invalid ({details}).", str(gta_path),
            ))
    preview_dir = gta_path / "mods/update/x64/dlcpacks/allin1_previews"
    if preview_dir.exists():
        preview_rpf = preview_dir / "dlc.rpf"
        if not preview_rpf.is_file() or preview_rpf.stat().st_size == 0:
            issues.append(HealthIssue(
                "preview_dlc_invalid", "error",
                "The ALLIN1 preview DLC is incomplete; run Install / Repair.",
                str(preview_dir),
            ))
    archive_names = ("update.rpf", "update2.rpf") if edition == "enhanced" else ("update.rpf",)
    for archive_name in archive_names:
        mods_update = gta_path / "mods/update" / archive_name
        base_update = gta_path / "update" / archive_name
        if ((gta_path / loader).is_file() and mods_update.is_file() and base_update.is_file()
                and mods_update.stat().st_mtime_ns + 1_000_000_000 < base_update.stat().st_mtime_ns):
            issues.append(HealthIssue(
                "rpf_mod_archive_stale", "error",
                f"mods/update/{archive_name} predates the installed game update and may crash "
                "the RPF loader; run Install / Repair before launching.",
                str(mods_update),
            ))

    scripts = gta_path / "scripts"
    dll = scripts / "ALLIN1.dll"
    if not dll.is_file():
        issues.append(HealthIssue("mod_missing", "error", "ALLIN1.dll is not installed.", str(dll)))
    else:
        inspection = inspect_windows_binary(dll)
        if not inspection.valid:
            issues.append(HealthIssue(
                "mod_corrupt", "error", f"ALLIN1.dll is invalid ({inspection.reason}).", str(dll),
            ))
    duplicates = sorted(
        path for path in gta_path.rglob("ALLIN1.dll")
        if path != dll and "allin1_backups" not in {
            part.lower() for part in path.relative_to(gta_path).parts
        }
    )
    for duplicate in duplicates:
        issues.append(HealthIssue("duplicate_mod", "error", "Duplicate ALLIN1.dll may load twice.", str(duplicate)))
    for old_name in ("ALLIN1.asi", "ALLIN1-Launcher.exe"):
        old = gta_path / old_name
        if old.exists():
            issues.append(HealthIssue("legacy_file", "warning", f"Legacy file should be removed: {old_name}", str(old)))
    for conflict in ("PackfileLimitAdjuster.asi", "HeapAdjuster.asi"):
        path = gta_path / conflict
        if path.exists():
            issues.append(HealthIssue("review_conflict", "info", f"Detected {conflict}; verify its settings match your game build.", str(path)))
    for relative, expected in (expected_hashes or {}).items():
        path = gta_path / relative
        if not path.is_file() or sha256_file(path).lower() != expected.lower():
            issues.append(HealthIssue("checksum_mismatch", "error", f"Installed file failed verification: {relative}", str(path)))
    try:
        installed = read_installed_version(scripts)
    except (OSError, ValueError):
        installed = None
        issues.append(HealthIssue("version_invalid", "warning", "Installed version marker is missing or invalid.", str(scripts)))
    return HealthReport(edition, installed, tuple(issues))
