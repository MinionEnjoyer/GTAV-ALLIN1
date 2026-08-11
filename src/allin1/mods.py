"""Manifest-driven installation for optional, user-supplied GTA V mods."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SUPPORTED_MOD_TYPES = frozenset({"asi", "script", "rpf", "config"})
SUPPORTED_EDITIONS = frozenset({"legacy", "enhanced"})
SUPPORTED_DEPENDENCIES = frozenset({"scripthookv", "shvdn", "openrpf"})
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RESERVED_DESTINATIONS = frozenset({
    "dinput8.dll",
    "openiv.asi",
    "openrpf.asi",
    "scripthookv.dll",
    "scripthookvdotnet.asi",
    "scripthookvdotnet.ini",
    "scripthookvdotnet2.dll",
    "scripthookvdotnet3.dll",
    "scripts/allin1.dll",
    "scripts/allin1.toml",
})


def _relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must not be absolute or contain traversal segments")
    if ":" in path.parts[0]:
        raise ValueError(f"{label} must not contain a drive letter")
    return path


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(dict.fromkeys(item.strip().lower() for item in value if item.strip()))


def _contained_path(root: Path, relative: str | PurePosixPath) -> Path:
    base = root.resolve()
    candidate = (base / Path(*PurePosixPath(relative).parts)).resolve(strict=False)
    if not candidate.is_relative_to(base):
        raise ValueError(f"Path escapes the allowed root: {relative}")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ModFile:
    source: PurePosixPath
    destination: PurePosixPath
    sha256: str | None = None


@dataclass(frozen=True)
class ModManifest:
    """A validated local mod package manifest."""

    manifest_path: Path
    mod_id: str
    name: str
    version: str
    mod_type: str
    description: str
    editions: tuple[str, ...]
    dependencies: tuple[str, ...]
    conflicts: tuple[str, ...]
    files: tuple[ModFile, ...]

    @property
    def package_root(self) -> Path:
        return self.manifest_path.parent

    @classmethod
    def load(
        cls, manifest_path: str | Path, *, validate_payload: bool = True
    ) -> "ModManifest":
        path = Path(manifest_path).resolve()
        if path.is_dir():
            path = path / "mod.toml"
        if not path.is_file():
            raise FileNotFoundError(f"Mod manifest not found: {path}")
        with path.open("rb") as stream:
            data = tomllib.load(stream)

        if data.get("schema_version") != 1:
            raise ValueError("mod.toml schema_version must be 1")
        mod_id = str(data.get("id", "")).strip().lower()
        if not _ID_PATTERN.fullmatch(mod_id):
            raise ValueError("Mod id must be 2-64 lowercase letters, numbers, dots, dashes, or underscores")
        name = str(data.get("name", "")).strip()
        version = str(data.get("version", "")).strip()
        mod_type = str(data.get("type", "")).strip().lower()
        if not name or not version:
            raise ValueError("Mod name and version are required")
        if mod_type not in SUPPORTED_MOD_TYPES:
            raise ValueError(f"Unsupported mod type '{mod_type}'")

        editions = _string_list(data.get("editions", list(SUPPORTED_EDITIONS)), "editions")
        if not editions or not set(editions).issubset(SUPPORTED_EDITIONS):
            raise ValueError("editions may contain only 'legacy' and 'enhanced'")
        dependencies = _string_list(data.get("dependencies"), "dependencies")
        unknown_dependencies = set(dependencies) - SUPPORTED_DEPENDENCIES
        if unknown_dependencies:
            raise ValueError(f"Unsupported dependencies: {', '.join(sorted(unknown_dependencies))}")
        conflicts = _string_list(data.get("conflicts"), "conflicts")
        if mod_id in conflicts:
            raise ValueError("A mod package may not conflict with itself")

        raw_files = data.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueError("A mod package must contain at least one [[files]] entry")
        files: list[ModFile] = []
        destinations: set[str] = set()
        for index, raw_file in enumerate(raw_files, start=1):
            if not isinstance(raw_file, dict):
                raise ValueError(f"files entry {index} must be a table")
            source = _relative_path(raw_file.get("source"), f"files[{index}].source")
            destination = _relative_path(
                raw_file.get("destination"), f"files[{index}].destination"
            )
            destination_key = destination.as_posix().lower()
            if (destination_key in _RESERVED_DESTINATIONS
                    or destination_key.startswith("scripts/.allin1/")):
                raise ValueError(f"Destination is reserved by the ALLIN1 launcher: {destination}")
            if destination_key in destinations:
                raise ValueError(f"Duplicate destination: {destination}")
            destinations.add(destination_key)
            checksum = raw_file.get("sha256")
            if checksum is not None:
                checksum = str(checksum).strip().lower()
                if not _SHA256_PATTERN.fullmatch(checksum):
                    raise ValueError(f"Invalid SHA-256 for {source}")
            files.append(ModFile(source, destination, checksum))

        cls._validate_destinations(mod_type, files)
        manifest = cls(
            path,
            mod_id,
            name,
            version,
            mod_type,
            str(data.get("description", "")).strip(),
            editions,
            dependencies,
            conflicts,
            tuple(files),
        )
        if validate_payload:
            manifest.validate_payload()
        return manifest

    @staticmethod
    def _validate_destinations(mod_type: str, files: Iterable[ModFile]) -> None:
        for item in files:
            parts = tuple(part.lower() for part in item.destination.parts)
            suffix = item.destination.suffix.lower()
            if mod_type == "asi" and len(parts) != 1:
                raise ValueError("ASI mod files must install in the GTA V root")
            if mod_type == "asi" and suffix not in {".asi", ".dll", ".ini", ".toml"}:
                raise ValueError("ASI packages may contain only .asi, .dll, .ini, or .toml files")
            if mod_type == "script" and (not parts or parts[0] != "scripts"):
                raise ValueError("Script mod destinations must be below scripts/")
            if mod_type == "rpf" and (not parts or parts[0] != "mods"):
                raise ValueError("RPF mod destinations must be below mods/")
            if mod_type == "rpf" and suffix != ".rpf":
                raise ValueError("RPF packages may install only .rpf files")
            if mod_type == "config" and (not parts or parts[0] not in {"scripts", "mods"}):
                raise ValueError("Config/data mod destinations must be below scripts/ or mods/")

    def validate_payload(self) -> None:
        package_root = self.package_root.resolve()
        for item in self.files:
            unresolved_source = package_root / Path(*item.source.parts)
            if unresolved_source.is_symlink():
                raise ValueError(f"Package payload may not use symbolic links: {item.source}")
            source = _contained_path(package_root, item.source)
            if not source.is_file():
                raise FileNotFoundError(f"Package payload is missing: {item.source}")
            if item.sha256 and _sha256(source) != item.sha256:
                raise ValueError(f"SHA-256 mismatch for {item.source}")


@dataclass(frozen=True)
class ModStatus:
    mod_id: str
    name: str
    version: str
    mod_type: str
    installed: bool
    enabled: bool


class ModCatalog:
    """Discovers optional packages checked into or copied beside the launcher."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def discover(self) -> list[ModManifest]:
        if not self.root.is_dir():
            return []
        manifests: list[ModManifest] = []
        for path in sorted(self.root.glob("*/mod.toml"), key=lambda value: str(value).lower()):
            # Defer payload existence and checksum work until installation. RPF
            # archives can be large enough that hashing them would freeze refresh.
            manifests.append(ModManifest.load(path, validate_payload=False))
        return manifests


class ModIntegrationService:
    """Installs optional mod packages with receipts, backups, and rollback."""

    def __init__(self, gta_path: str | Path) -> None:
        candidate = Path(gta_path).expanduser().resolve()
        if not candidate.is_dir() or not (
            (candidate / "GTA5.exe").is_file()
            or (candidate / "GTA5_Enhanced.exe").is_file()
            or (candidate / "PlayGTAV.exe").is_file()
            or (candidate / "update" / "update.rpf").is_file()
        ):
            raise ValueError(f"'{candidate}' does not appear to be a valid GTA V installation")
        self.gta_path = candidate
        self.state_root = self.gta_path / "scripts" / ".allin1" / "mods"
        self.backup_root = self.gta_path / "ALLIN1_Backups" / "Mods"

    @property
    def edition(self) -> str:
        return "enhanced" if (self.gta_path / "GTA5_Enhanced.exe").exists() else "legacy"

    def _receipt_path(self, mod_id: str) -> Path:
        if not _ID_PATTERN.fullmatch(mod_id):
            raise ValueError("Invalid mod id")
        return self.state_root / f"{mod_id}.json"

    def _read_receipt(self, mod_id: str) -> dict[str, Any]:
        path = self._receipt_path(mod_id)
        if not path.is_file():
            raise FileNotFoundError(f"Mod '{mod_id}' is not installed")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid install receipt for '{mod_id}'") from exc
        if data.get("id") != mod_id or not isinstance(data.get("files"), list):
            raise ValueError(f"Invalid install receipt for '{mod_id}'")
        return data

    def _write_receipt(self, receipt: dict[str, Any]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        receipt_path = self._receipt_path(str(receipt["id"]))
        temporary = receipt_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        temporary.replace(receipt_path)

    def list_installed(self) -> list[ModStatus]:
        if not self.state_root.is_dir():
            return []
        statuses: list[ModStatus] = []
        for receipt_path in sorted(self.state_root.glob("*.json")):
            try:
                receipt = self._read_receipt(receipt_path.stem)
            except (OSError, ValueError):
                continue
            statuses.append(ModStatus(
                receipt["id"],
                str(receipt.get("name", receipt["id"])),
                str(receipt.get("version", "unknown")),
                str(receipt.get("type", "unknown")),
                True,
                bool(receipt.get("enabled", True)),
            ))
        return statuses

    def _check_dependencies(self, manifest: ModManifest) -> None:
        checks = {
            "scripthookv": self.gta_path / "ScriptHookV.dll",
            "shvdn": self.gta_path / "ScriptHookVDotNet.asi",
        }
        missing = [dependency for dependency in manifest.dependencies
                   if dependency in checks and not checks[dependency].is_file()]
        if "openrpf" in manifest.dependencies and not (
            (self.gta_path / "OpenRPF.asi").is_file()
            or (self.gta_path / "OpenIV.asi").is_file()
        ):
            missing.append("openrpf")
        if missing:
            raise ValueError(f"Missing required loader(s): {', '.join(missing)}")

    def _check_conflicts(self, manifest: ModManifest) -> None:
        installed_statuses = self.list_installed()
        installed = {status.mod_id for status in installed_statuses}
        conflicts = installed.intersection(manifest.conflicts)
        for status in installed_statuses:
            if status.mod_id == manifest.mod_id:
                continue
            try:
                receipt = self._read_receipt(status.mod_id)
            except (OSError, ValueError):
                continue
            if manifest.mod_id in receipt.get("conflicts", []):
                conflicts.add(status.mod_id)
        if conflicts:
            raise ValueError(f"Conflicts with installed mod(s): {', '.join(sorted(conflicts))}")

        owned_destinations: dict[str, str] = {}
        for status in installed_statuses:
            if status.mod_id == manifest.mod_id:
                continue
            receipt = self._read_receipt(status.mod_id)
            for item in receipt["files"]:
                owned_destinations[str(item["destination"]).lower()] = status.mod_id
        collisions = {
            owned_destinations[item.destination.as_posix().lower()]
            for item in manifest.files
            if item.destination.as_posix().lower() in owned_destinations
        }
        if collisions:
            raise ValueError(f"File destination is owned by: {', '.join(sorted(collisions))}")

    def install(self, manifest: ModManifest) -> ModStatus:
        manifest.validate_payload()
        if self.edition not in manifest.editions:
            raise ValueError(f"{manifest.name} does not support GTA V {self.edition.title()}")
        self._check_dependencies(manifest)
        self._check_conflicts(manifest)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_dir = self.backup_root / manifest.mod_id / timestamp
        previous_receipt: dict[str, Any] | None = None
        previous_payloads: list[tuple[Path, str]] = []
        records: list[dict[str, Any]] = []
        try:
            if self._receipt_path(manifest.mod_id).exists():
                previous_receipt = self._read_receipt(manifest.mod_id)
                snapshot_root = backup_dir / ".update-rollback"
                previous_enabled = bool(previous_receipt.get("enabled", True))
                for old_item in previous_receipt["files"]:
                    target = _contained_path(self.gta_path, old_item["destination"])
                    current = target if previous_enabled else target.with_name(
                        target.name + ".disabled"
                    )
                    if not current.is_file():
                        raise FileNotFoundError(f"Managed mod file is missing: {current}")
                    snapshot = _contained_path(snapshot_root, old_item["destination"])
                    snapshot.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(current, snapshot)
                    previous_payloads.append((snapshot, str(old_item["destination"])))
                self.uninstall(manifest.mod_id)

            for item in manifest.files:
                source = _contained_path(manifest.package_root, item.source)
                target = _contained_path(self.gta_path, item.destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                backup: Path | None = None
                if target.exists():
                    if not target.is_file() or target.is_symlink():
                        raise ValueError(f"Refusing to replace non-file destination: {item.destination}")
                    backup = _contained_path(backup_dir, item.destination)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                temporary = target.with_name(f".{target.name}.allin1-install")
                shutil.copy2(source, temporary)
                temporary.replace(target)
                records.append({
                    "destination": item.destination.as_posix(),
                    "backup": str(backup.relative_to(self.gta_path)).replace("\\", "/")
                    if backup else None,
                })

            receipt = {
                "schema_version": 1,
                "id": manifest.mod_id,
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.mod_type,
                "enabled": True,
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "source_manifest": str(manifest.manifest_path),
                "dependencies": list(manifest.dependencies),
                "conflicts": list(manifest.conflicts),
                "files": records,
            }
            self._write_receipt(receipt)
        except Exception:
            self._rollback_records(records)
            if previous_receipt is not None:
                previous_enabled = bool(previous_receipt.get("enabled", True))
                for snapshot, destination in previous_payloads:
                    target = _contained_path(self.gta_path, destination)
                    disabled = target.with_name(target.name + ".disabled")
                    target.unlink(missing_ok=True)
                    disabled.unlink(missing_ok=True)
                    restored = target if previous_enabled else disabled
                    restored.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snapshot, restored)
                self._write_receipt(previous_receipt)
            raise

        return ModStatus(
            manifest.mod_id, manifest.name, manifest.version, manifest.mod_type, True, True
        )

    def _rollback_records(self, records: Iterable[dict[str, Any]]) -> None:
        for item in reversed(list(records)):
            target = _contained_path(self.gta_path, item["destination"])
            target.unlink(missing_ok=True)
            if item.get("backup"):
                backup = _contained_path(self.gta_path, item["backup"])
                if backup.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)

    def set_enabled(self, mod_id: str, enabled: bool) -> ModStatus:
        receipt = self._read_receipt(mod_id)
        current = bool(receipt.get("enabled", True))
        if current == enabled:
            return ModStatus(
                mod_id, receipt["name"], receipt["version"], receipt["type"], True, enabled
            )

        moves: list[tuple[Path, Path]] = []
        try:
            for item in receipt["files"]:
                target = _contained_path(self.gta_path, item["destination"])
                disabled = target.with_name(target.name + ".disabled")
                source, destination = (disabled, target) if enabled else (target, disabled)
                if not source.is_file():
                    raise FileNotFoundError(f"Managed mod file is missing: {source}")
                if destination.exists():
                    raise FileExistsError(f"Cannot change mod state; destination exists: {destination}")
                source.replace(destination)
                moves.append((destination, source))
            receipt["enabled"] = enabled
            self._write_receipt(receipt)
        except Exception:
            for destination, source in reversed(moves):
                if destination.exists() and not source.exists():
                    destination.replace(source)
            raise
        return ModStatus(
            mod_id, receipt["name"], receipt["version"], receipt["type"], True, enabled
        )

    def uninstall(self, mod_id: str) -> None:
        receipt = self._read_receipt(mod_id)
        for item in reversed(receipt["files"]):
            target = _contained_path(self.gta_path, item["destination"])
            disabled = target.with_name(target.name + ".disabled")
            target.unlink(missing_ok=True)
            disabled.unlink(missing_ok=True)
            if item.get("backup"):
                backup = _contained_path(self.gta_path, item["backup"])
                if backup.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(f".{target.name}.allin1-restore")
                    shutil.copy2(backup, temporary)
                    temporary.replace(target)
        self._receipt_path(mod_id).unlink()
