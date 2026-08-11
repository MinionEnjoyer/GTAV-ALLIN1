"""Pre-launch installation health and conflict checks."""

from __future__ import annotations

import hashlib
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
    loader = "OpenRPF.asi" if edition == "enhanced" else "OpenIV.asi"
    if edition != "unknown" and not (gta_path / loader).is_file():
        issues.append(HealthIssue("rpf_loader_missing", "warning", f"{loader} is missing; previews may not load.", str(gta_path / loader)))
    elif edition != "unknown" and (gta_path / loader).stat().st_size == 0:
        issues.append(HealthIssue("rpf_loader_corrupt", "error", f"{loader} is empty or corrupt.", str(gta_path / loader)))
    if edition == "enhanced" and (gta_path / "OpenRPF.asi").exists():
        if (gta_path / "OpenIV.asi").exists():
            issues.append(HealthIssue("rpf_loader_conflict", "error",
                                      "OpenIV.asi cannot be loaded alongside OpenRPF on Enhanced.",
                                      str(gta_path / "OpenIV.asi")))
        if not any((gta_path / name).exists() for name in
                   ("dsound.dll", "xinput1_4.dll", "dinput8.dll")):
            issues.append(HealthIssue("asi_loader_missing", "error",
                                      "OpenRPF is installed but no ASI loader was detected.",
                                      str(gta_path)))
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
