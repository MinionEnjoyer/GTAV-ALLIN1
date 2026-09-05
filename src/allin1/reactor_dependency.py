"""Pinned, shared Reactor V installation; ALLIN1 owns only its presentation.

Preview 2 has one host UI, not a dynamic skin loader. The ALLIN1 composition
also renders other extensions' typed menus. Its receipt and neutral-UI backup
are separate from the shared runtime, which ALLIN1 uninstall never removes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Callable
import urllib.request
import zipfile


TAG = "v0.2.0-preview.2"
RELEASE_PAGE = f"https://github.com/MinionEnjoyer/GTAV-REACTOR-V/releases/tag/{TAG}"
UI_ROOT = "plugins/ReactorV/ui/"
RECEIPT = "scripts/.reactorv/dependencies/reactor-v.json"
CONSUMER_RECEIPT = "scripts/.reactorv/consumers/allin1-ui.json"
BACKUP_ROOT = "scripts/.reactorv/dependencies/neutral-ui/"
from allin1.runtime_resources import resource_root

UI_SOURCE = resource_root() / "data/reactor/allin1-ui"
ART_SOURCE = resource_root() / "script/dist"
CONFIGS = frozenset({"scripts/ReactorV/ReactorV.json", "plugins/ReactorV/ReactorV.Preloader.json"})
ROOT_ASIS = frozenset({"ReactorV.Bootstrap.asi", "ReactorV.ScriptProbe.asi", "ReactorV.RenderHook.asi"})
MAX_UNPACKED = 600 * 1024 * 1024
MAX_FILES = 2048
UI_REQUIRED = frozenset({"index.html", "LICENSE", "THIRD_PARTY_NOTICES.txt", "reactor-ui.json",
                         "react-LICENSE.txt", "react-dom-LICENSE.txt", "scheduler-LICENSE.txt",
                         "fonts/OFL-Bebas-Neue.txt", "fonts/OFL-Oswald.txt"})


class ReactorInstallError(ValueError):
    """Actionable preflight, ownership, or integrity failure."""


@dataclass(frozen=True)
class ReactorRelease:
    edition: str
    size: int
    sha256: str
    game_executable: str
    game_version: str
    game_sha256: str

    @property
    def url(self) -> str:
        return (f"https://github.com/MinionEnjoyer/GTAV-REACTOR-V/releases/download/{TAG}/"
                f"ReactorV-0.2.0-{self.edition}-live-test.zip")


RELEASES = {
    False: ReactorRelease("legacy", 175143415,
        "56b841c4fc8b60fa844d5781f2536336ae99d3da0a7b58dfaf0acc87cb0cb1e9",
        "GTA5.exe", "1.0.3889.0", "677e4e355cfbdb13273b1d992407e3c261b3a108dc4dd5c8a0c4c1da651802e5"),
    True: ReactorRelease("enhanced", 175143088,
        "261325f08b6e63f73b51c14c34d0403f71996c1f78e5e1203a2606771da2a295",
        "GTA5_Enhanced.exe", "1.0.1158.13", "0c52864d4521d9c9d441348aa1156958792dde8825d0297c851753f167336401"),
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(value: str) -> str:
    value = value.replace("\\", "/")
    parts = value.split("/")
    if (not value or PurePosixPath(value).is_absolute() or any(
        not p or p in {".", ".."} or p.endswith((".", " "))
        or re.search(r'[<>:"|?*\x00-\x1f]', p)
        or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}
        for p in parts
    )):
        raise ReactorInstallError(f"Unsafe Reactor package path: {value!r}")
    return value


def _path(root: Path, relative: str) -> Path:
    """Refuse junctions/symlinks including existing ancestors of the game root."""
    path = root.absolute() / _relative(relative)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ReactorInstallError(f"Reparse point is not allowed: {part}")
    return path


def _json(path: Path) -> dict:
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("JSON exceeds size limit")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("expected a JSON object")
        return value
    except (OSError, ValueError) as exc:
        raise ReactorInstallError(f"Cannot read {path.name}: {exc}") from exc


def _inventory(root: Path, relative: str, *, consumer: bool = False) -> dict:
    path = _path(root, relative)
    if not path.exists():
        return {}
    receipt = _json(path)
    if receipt.get("schema_version") != 1 or receipt.get("product") != ("allin1-ui" if consumer else "reactor-v"):
        raise ReactorInstallError(f"Unrecognized ownership receipt: {relative}")
    files = receipt.get("files")
    if not isinstance(files, dict) or len(files) > 8192:
        raise ReactorInstallError(f"Invalid file inventory: {relative}")
    for name, digest in files.items():
        name = _relative(name)
        if not (name.startswith(UI_ROOT) if consumer else _runtime_path(name)):
            raise ReactorInstallError(f"Receipt claims a non-owned path: {name}")
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise ReactorInstallError(f"Invalid digest in {relative}")
    return receipt


def _runtime_path(name: str) -> bool:
    return name in ROOT_ASIS or name.startswith(("plugins/ReactorV/", "scripts/ReactorV/"))


def dependency_recorded(root: Path, enhanced: bool) -> bool:
    """Cheap consent hint only. Installation always re-verifies every file."""
    try:
        receipt = _inventory(root, RECEIPT)
        return receipt.get("archive_sha256") == RELEASES[enhanced].sha256 and receipt.get("edition") == RELEASES[enhanced].edition
    except ReactorInstallError:
        return False


def assert_package_paths_available(root: Path, paths) -> None:
    """Packages may use Reactor, but may not replace/disable/uninstall its owner."""
    reserved = set()
    for receipt, consumer in ((RECEIPT, False), (CONSUMER_RECEIPT, True)):
        reserved.update(name.casefold() for name in _inventory(root, receipt, consumer=consumer).get("files", {}))
    for value in paths:
        name = _relative(str(value)).casefold()
        if name in reserved or name.startswith(("scripts/.reactorv/dependencies/", "scripts/.reactorv/consumers/")):
            raise ReactorInstallError(f"Package cannot modify shared Reactor ownership: {value}. Use ALLIN1 Install/Repair for the dependency.")


def _assert_no_package_owner(root: Path, targets: set[str]) -> None:
    state = _path(root, "scripts/.allin1/mods")
    receipts = list(state.glob("*.json"))
    if len(receipts) > 512:
        raise ReactorInstallError("Too many package receipts to safely inspect Reactor ownership")
    targets = {name.casefold() for name in targets}
    for file in receipts:
        receipt = _json(_path(root, file.relative_to(root).as_posix()))
        files = receipt.get("files", [])
        if not isinstance(files, list):
            raise ReactorInstallError(f"Invalid package receipt: {file.name}")
        for item in files:
            if not isinstance(item, dict):
                raise ReactorInstallError(f"Invalid package file receipt: {file.name}")
            if str(item.get("destination", "")).replace("\\", "/").casefold() in targets:
                raise ReactorInstallError(
                    f"Reactor files are still owned by managed package '{file.stem}'. "
                    "Remove that old framework/UI package through Packages before installing "
                    "the shared dependency. No game files were changed."
                )


def _assert_game_closed() -> None:
    if os.name == "nt":
        from allin1.game_launcher import _windows_processes
        if any(name.casefold() in {"gta5.exe", "gta5_enhanced.exe", "gta5_be.exe"}
               for name in _windows_processes().values()):
            raise ReactorInstallError("Close GTA V before installing or repairing Reactor V.")


def _verify_game(root: Path, release: ReactorRelease) -> None:
    executable = _path(root, release.game_executable)
    if not executable.is_file() or _sha(executable) != release.game_sha256:
        raise ReactorInstallError(
            f"Reactor {TAG} is an edition-specific preview for GTA V {release.edition.title()} "
            f"{release.game_version}. This executable does not match its supported build. "
            "No files were changed. Update the dependency pin for a newer supported release; "
            "do not disable its native version gates."
        )


def _download(release: ReactorRelease, progress: Callable[[str], None], *, allow_download: bool = True) -> Path:
    cache = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "ALLIN1/downloads/reactor"
    target = _path(cache, release.sha256 + ".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size == release.size and _sha(target) == release.sha256:
        progress("Using verified cached Reactor V download")
        return target
    if not allow_download:
        raise ReactorInstallError("The verified Reactor cache is missing. Allow the Reactor download in Install/Repair (CLI: --reactor install).")
    request = urllib.request.Request(release.url, headers={"User-Agent": "ALLIN1-Dependency-Installer", "Accept": "application/octet-stream"})
    try:
        with tempfile.NamedTemporaryFile(dir=cache, suffix=".part", delete=False) as output:
            partial = Path(output.name)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    if not response.geturl().startswith("https://"):
                        raise ReactorInstallError("Refusing an insecure Reactor download redirect")
                    count = 0
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > release.size:
                            raise ReactorInstallError("Reactor download exceeds its pinned size")
                        output.write(chunk)
                        progress(f"Downloading Reactor V: {count * 100 // release.size}%")
                output.flush()
            except BaseException:
                output.close()
                partial.unlink(missing_ok=True)
                raise
        try:
            if partial.stat().st_size != release.size or _sha(partial) != release.sha256:
                raise ReactorInstallError("Reactor download failed its size/SHA-256 check")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        return target
    except (OSError, ValueError) as exc:
        raise ReactorInstallError(f"Reactor download failed; retry Install/Repair: {exc}") from exc


def _extract(archive: Path, stage: Path, release: ReactorRelease) -> dict[str, Path]:
    if archive.stat().st_size != release.size or _sha(archive) != release.sha256:
        raise ReactorInstallError("Reactor archive does not match the pinned size/SHA-256")
    files: dict[str, Path] = {}
    try:
        with zipfile.ZipFile(archive) as package:
            entries = package.infolist()
            if len(entries) > MAX_FILES or sum(i.file_size for i in entries) > MAX_UNPACKED:
                raise ReactorInstallError("Reactor archive exceeds inspection limits")
            seen: set[str] = set()
            for entry in entries:
                name = _relative(entry.filename.rstrip("/\\") if entry.is_dir() else entry.filename)
                if not _runtime_path(name) and not (entry.is_dir() and name in {"plugins", "scripts", "plugins/ReactorV", "scripts/ReactorV"}):
                    raise ReactorInstallError(f"Unexpected Reactor archive member: {name}")
                if name.casefold() in seen or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ReactorInstallError(f"Duplicate, linked, or encrypted archive member: {name}")
                seen.add(name.casefold())
                if entry.is_dir():
                    continue
                destination = _path(stage, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as src, destination.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                files[name] = destination
        required = {*ROOT_ASIS, "scripts/ReactorV/RageWebUI.Script.dll", "scripts/ReactorV/RageWebUI.Core.dll",
                    "plugins/ReactorV/RageWebUI.Core.dll", "scripts/ReactorV/ReactorV.contract.json",
                    "plugins/ReactorV/legal/LICENSE", UI_ROOT + "index.html", UI_ROOT + "reactor-ui.json"}
        if not required <= files.keys():
            raise ReactorInstallError("Reactor archive is incomplete")
        core = "scripts/ReactorV/RageWebUI.Core.dll"
        if _sha(files[core]) != _sha(files["plugins/ReactorV/RageWebUI.Core.dll"]):
            raise ReactorInstallError("Reactor Core copies disagree")
        contract = _json(files["scripts/ReactorV/ReactorV.contract.json"])
        if (contract.get("product"), contract.get("runtime_version"), contract.get("extension_api_version")) != ("reactor-v", "0.2.0", 1):
            raise ReactorInstallError("Unsupported Reactor extension API contract")
        marker = "plugins/ReactorV/ReactorV.LegacyCpuFrames.enabled"
        if (marker in files) != (release.edition == "legacy"):
            raise ReactorInstallError("Reactor archive targets the wrong edition")
        return files
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ReactorInstallError(f"Invalid Reactor archive: {exc}") from exc


def consumer_files(source: Path | None = None, *, artwork: bool = True) -> dict[str, Path]:
    source = source or UI_SOURCE
    manifest = _json(_path(source, "allin1-ui.json"))
    if (manifest.get("schema_version"), manifest.get("profile"), manifest.get("reactor_release")) != (1, "allin1-composition", TAG):
        raise ReactorInstallError("ALLIN1 UI does not match the pinned Reactor release")
    inventory = manifest.get("files")
    if not isinstance(inventory, dict) or not 1 <= len(inventory) <= 64:
        raise ReactorInstallError("Invalid ALLIN1 UI inventory")
    files = {}
    for name, expected in inventory.items():
        name = _relative(name)
        path = _path(source, name)
        if path.suffix.casefold() not in {".js", ".css", ".html", ".png", ".ttf", ".txt", ".json"} and name != "LICENSE":
            raise ReactorInstallError(f"Non-UI file in ALLIN1 composition: {name}")
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024 or _sha(path) != expected:
            raise ReactorInstallError(f"ALLIN1 UI payload missing or modified: {name}. Reinstall the launcher release.")
        files[UI_ROOT + name] = path
    if not {UI_ROOT + name for name in UI_REQUIRED} <= files.keys():
        raise ReactorInstallError("ALLIN1 UI payload or license notices are incomplete")
    actual_files = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    if actual_files != {*inventory, "allin1-ui.json"}:
        raise ReactorInstallError("Unexpected or missing file in ALLIN1 UI payload")
    if artwork:
        for kind, directory in {"vehicles": "previews", "weapons": "weapon_previews", "gear": "equipment_previews"}.items():
            for path in sorted((ART_SOURCE / directory).glob("*.png")):
                if path.is_file():
                    _path(ART_SOURCE, path.relative_to(ART_SOURCE).as_posix())
                    files[UI_ROOT + f"assets/allin1/{kind}/{path.name}"] = path
    return files


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _transaction(root: Path, writes: dict[str, Path], deletes: list[str] | None = None,
                 *, expected_targets: dict[str, str | None] | None = None,
                 expected_sources: dict[str, str] | None = None) -> None:
    """Disk-backed rollback, including receipts; never snapshot entire mod folders."""
    operations = [(name, source) for name, source in writes.items()] + [(name, None) for name in deletes or []]
    for name, expected in (expected_targets or {}).items():
        target = _path(root, name)
        if (_sha(target) if target.exists() else None) != expected:
            raise ReactorInstallError(f"File changed since preflight: {name}. Recheck before repairing.")
    source_hashes = {name: _sha(source) for name, source in writes.items()}
    for name, expected in (expected_sources or {}).items():
        if name in source_hashes and source_hashes[name] != expected:
            raise ReactorInstallError(f"Source changed since preflight: {name}")
    with tempfile.TemporaryDirectory(prefix="allin1-reactor-rollback-") as temporary:
        snapshots: list[tuple[Path, Path | None]] = []
        try:
            for number, (name, source) in enumerate(operations):
                target = _path(root, name)
                backup = Path(temporary) / str(number) if target.exists() else None
                if backup:
                    shutil.copyfile(target, backup)
                snapshots.append((target, backup))
                if source is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_copy(source, target)
                    if _sha(target) != source_hashes[name]:
                        raise ReactorInstallError(f"Copied file failed verification: {name}")
        except BaseException as exc:
            errors = []
            for target, backup in reversed(snapshots):
                try:
                    if backup is None:
                        target.unlink(missing_ok=True)
                    else:
                        # Do not reuse the potentially failing deployment primitive.
                        shutil.copyfile(backup, target)
                except OSError as rollback_error:
                    errors.append(str(rollback_error))
            if errors:
                # Preserve recovery copies if a file lock prevents rollback.
                recovery = root / "allin1_backups" / "ReactorRecovery"
                _path(recovery, "recovery-check")
                recovery.mkdir(parents=True, exist_ok=True)
                for target, backup in snapshots:
                    if backup is not None:
                        dest = _path(recovery, target.relative_to(root.absolute()).as_posix())
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(backup, dest)
                raise ReactorInstallError(f"Reactor install failed; rollback needs attention in {recovery}: {errors}") from exc
            raise


def install_dependency(root: Path, enhanced: bool, *, progress: Callable[[str], None] | None = None, allow_download: bool = True) -> str:
    progress = progress or (lambda _: None)
    root = root.absolute()
    release = RELEASES[enhanced]
    _assert_game_closed()
    _verify_game(root, release)
    other = "Legacy" if enhanced else "Enhanced"
    if _path(root, f"plugins/ReactorV/ReactorV.{other}LiveTest.json").exists():
        raise ReactorInstallError("Reactor files for the other edition are present; resolve them before installing")
    consumer = consumer_files()  # Fail before downloading or changing the game.
    old = _inventory(root, RECEIPT)
    owner = _inventory(root, CONSUMER_RECEIPT, consumer=True)
    if old and old.get("edition") != release.edition:
        raise ReactorInstallError("This folder contains Reactor for the other GTA edition")
    archive = _download(release, progress, allow_download=allow_download)
    with tempfile.TemporaryDirectory(prefix="allin1-reactor-stage-") as temporary:
        stage = Path(temporary)
        runtime = _extract(archive, stage / "runtime", release)
        hashes = {name: _sha(path) for name, path in runtime.items()}
        ui_hashes = {name: _sha(path) for name, path in consumer.items()}
        desired = {**runtime, **consumer}
        _assert_no_package_owner(root, set(desired))
        writes: dict[str, Path] = {}
        observed: dict[str, str | None] = {}
        for name, source in desired.items():
            destination = _path(root, name)
            expected = ui_hashes.get(name, hashes.get(name))
            observed[name] = _sha(destination) if destination.exists() else None
            if destination.exists():
                if name in CONFIGS:
                    _json(destination)  # Preserve valid user runtime settings verbatim.
                    continue
                actual = _sha(destination)
                if actual == expected:
                    continue
                allowed = {old.get("files", {}).get(name), owner.get("files", {}).get(name), hashes.get(name)} - {None}
                if actual not in allowed:
                    raise ReactorInstallError(
                        f"Unmanaged or modified Reactor file: {name}. Back it up and resolve its ownership "
                        "before retrying; the installer will not overwrite another mod's UI/runtime."
                    )
            writes[name] = source
        # Retire only unchanged files from our previous composition (hashed assets).
        deletes = []
        for name, digest in owner.get("files", {}).items():
            if name not in desired:
                path = _path(root, name)
                if path.exists():
                    observed[name] = _sha(path)
                    if _sha(path) != digest:
                        raise ReactorInstallError(f"Modified ALLIN1 UI file must be preserved: {name}")
                    deletes.append(name)
        for name, source in runtime.items():
            if name.startswith(UI_ROOT):
                backup_name = BACKUP_ROOT + name.removeprefix(UI_ROOT)
                backup = _path(root, backup_name)
                if backup.exists() and _sha(backup) != hashes[name]:
                    raise ReactorInstallError(f"Neutral Reactor UI backup was modified: {backup_name}")
                if not backup.exists():
                    writes[backup_name] = source
        shared = dict(schema_version=1, product="reactor-v", version="0.2.0", release=TAG,
                      edition=release.edition, archive_sha256=release.sha256, release_page=RELEASE_PAGE,
                      shared=True, files=hashes, mutable_files=sorted(CONFIGS))
        owned = dict(schema_version=1, product="allin1-ui", reactor_release=TAG, files=ui_hashes)
        for name, payload in ((RECEIPT, shared), (CONSUMER_RECEIPT, owned)):
            source = stage / Path(name).name
            source.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            writes[name] = source
        _assert_game_closed()
        progress("Installing verified shared Reactor V and ALLIN1 presentation")
        _transaction(root, writes, deletes, expected_targets=observed,
                     expected_sources={**hashes, **ui_hashes})
    return f"Reactor V 0.2.0 Preview 2 ({release.edition.title()})"


def remove_consumer(root: Path) -> list[Path]:
    """Restore the neutral host; never remove Reactor or other extensions."""
    root = root.absolute()
    owner = _inventory(root, CONSUMER_RECEIPT, consumer=True)
    if not owner:
        return []
    _assert_game_closed()
    shared = _inventory(root, RECEIPT)
    if not shared:
        raise ReactorInstallError("Cannot restore Reactor UI: shared dependency receipt is missing")
    writes: dict[str, Path] = {}
    deletes: list[str] = []
    observed: dict[str, str | None] = {}
    for name, digest in owner["files"].items():
        path = _path(root, name)
        observed[name] = _sha(path) if path.exists() else None
        if path.exists() and _sha(path) != digest:
            raise ReactorInstallError(f"ALLIN1 UI was edited: {name}. Back it up before uninstalling.")
        if name in shared["files"]:
            backup = _path(root, BACKUP_ROOT + name.removeprefix(UI_ROOT))
            if not backup.is_file() or _sha(backup) != shared["files"][name]:
                raise ReactorInstallError("Cannot restore Reactor's verified neutral UI backup")
            writes[name] = backup
        elif path.exists():
            deletes.append(name)
    deletes.append(CONSUMER_RECEIPT)
    _transaction(root, writes, deletes, expected_targets=observed,
                 expected_sources={name: shared["files"][name] for name in writes})
    return [root / name for name in deletes]
