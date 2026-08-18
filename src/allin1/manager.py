"""Testable application service used by the CLI and desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from allin1.config import Config
from allin1 import __version__
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.installer import InstallResult, install, uninstall
from allin1.health import inspect_windows_binary
from allin1.launch_policy import configure_story_mode_only
from allin1.vehicles.database import VehicleDatabase
from allin1.versioning import read_installed_version


@dataclass(frozen=True)
class InstallationStatus:
    gta_path: Path | None
    valid_game: bool
    edition: str
    mod_installed: bool
    scripthookv_installed: bool
    shvdn_installed: bool
    openrpf_installed: bool
    installed_version: str | None = None
    manager_version: str = __version__
    rpf_loader_status: str = "Missing"


class ModManager:
    """Coordinates configuration and install operations for front ends."""

    def __init__(
        self,
        project_root: Path,
        *,
        install_fn: Callable[..., InstallResult] = install,
        uninstall_fn: Callable[[Config], list[Path]] = uninstall,
    ) -> None:
        self.project_root = project_root
        self.config_path = project_root / "config.toml"
        self.database_path = project_root / "data" / "vehicles.toml"
        self._install = install_fn
        self._uninstall = uninstall_fn

    def load_config(self) -> Config:
        if self.config_path.exists():
            return Config.load(self.config_path)
        example = self.project_root / "config.example.toml"
        return Config.load(example) if example.exists() else Config.default()

    def save_config(self, config: Config) -> None:
        config.validate()
        gta_path = self.resolve_path(config)
        runtime_scripts_present = bool(
            gta_path is not None and (gta_path / "scripts").is_dir()
        )
        if gta_path is not None and gta_path.is_dir() and (
            (gta_path / "GTA5.exe").is_file()
            or (gta_path / "GTA5_Enhanced.exe").is_file()
        ):
            configure_story_mode_only(
                gta_path, config.general.story_mode_only,
            )
        if not config.general.story_mode_only:
            # A global opt-out must also clear any ALLIN1-owned policy left on
            # the other configured edition after the player switched targets.
            for other_path in set(self.resolve_paths(config).values()):
                if other_path == gta_path or not other_path.is_dir():
                    continue
                if not (
                    (other_path / "GTA5.exe").is_file()
                    or (other_path / "GTA5_Enhanced.exe").is_file()
                ):
                    continue
                configure_story_mode_only(other_path, False)
        config.save(self.config_path)
        if gta_path is not None and runtime_scripts_present:
            scripts = gta_path / "scripts"
            config.save(scripts / "ALLIN1.toml")

    @staticmethod
    def _path_value(value: str) -> Path | None:
        if not value.strip() or value.strip().lower() == "auto":
            return None
        try:
            return validate_gta_path(value)
        except (FileNotFoundError, ValueError):
            return Path(value).expanduser()

    def resolve_paths(self, config: Config) -> dict[str, Path]:
        """Resolve independently configured game roots for both GTA editions."""
        paths: dict[str, Path] = {}
        for edition, value in (
            ("legacy", config.general.gta_legacy_path),
            ("enhanced", config.general.gta_enhanced_path),
        ):
            candidate = self._path_value(value)
            if candidate is not None:
                paths[edition] = candidate

        old_value = config.general.gta_path.strip()
        if old_value and old_value.lower() != "auto":
            fallback = self._path_value(old_value)
            if fallback is not None:
                if (fallback / "GTA5_Enhanced.exe").is_file():
                    paths.setdefault("enhanced", fallback)
                elif (fallback / "GTA5.exe").is_file():
                    paths.setdefault("legacy", fallback)
                else:
                    selected = config.general.target_edition.lower()
                    if selected in {"legacy", "enhanced"}:
                        paths.setdefault(selected, fallback)

        detected = detect_gta_path()
        if detected is not None:
            edition = (
                "enhanced" if (detected / "GTA5_Enhanced.exe").is_file()
                else "legacy"
            )
            paths.setdefault(edition, detected)
        return paths

    def resolve_path(self, config: Config) -> Path | None:
        target = config.general.target_edition.strip().lower()
        paths = self.resolve_paths(config)
        if target in {"legacy", "enhanced"}:
            return paths.get(target)
        if config.general.gta_path != "auto":
            return self._path_value(config.general.gta_path)
        return paths.get("enhanced") or paths.get("legacy")

    def resolve_mod_path(self, config: Config, editions: tuple[str, ...]) -> Path:
        """Choose a configured game root compatible with a package manifest."""
        paths = self.resolve_paths(config)
        preferred = config.general.target_edition.strip().lower()
        if preferred in editions and preferred in paths:
            return paths[preferred]
        compatible = [
            edition for edition in ("enhanced", "legacy")
            if edition in editions and edition in paths
        ]
        if compatible:
            return paths[compatible[0]]
        supported = " / ".join(value.title() for value in editions)
        raise ValueError(
            f"No configured {supported} GTA V installation is available for this package."
        )

    def status(self, config: Config | None = None) -> InstallationStatus:
        config = config or self.load_config()
        gta_path = self.resolve_path(config)
        if gta_path is None:
            return InstallationStatus(None, False, "Unknown", False, False, False, False)

        legacy_exe = gta_path / "GTA5.exe"
        enhanced_exe = gta_path / "GTA5_Enhanced.exe"
        valid = legacy_exe.exists() or enhanced_exe.exists()
        edition = "Enhanced" if enhanced_exe.exists() else "Legacy" if legacy_exe.exists() else "Unknown"
        scripts = gta_path / "scripts"
        try:
            installed_version = read_installed_version(scripts)
        except (OSError, ValueError):
            installed_version = None
        rpf_plugin = gta_path / ("OpenRPF.asi" if edition == "Enhanced" else "OpenIV.asi")
        rpf_installed = inspect_windows_binary(rpf_plugin).valid
        disabled_plugin = (
            gta_path / "allin1_backups" / "DisabledPlugins" /
            (rpf_plugin.name + ".disabled")
        )
        asi_loader = any(inspect_windows_binary(gta_path / name).valid for name in
                         ("dinput8.dll", "dsound.dll", "xinput1_4.dll"))
        if rpf_installed:
            rpf_status = "Installed (file validated)"
        elif disabled_plugin.is_file():
            rpf_status = "Disabled"
        elif asi_loader:
            rpf_status = "Plug-in missing"
        else:
            rpf_status = "Missing"

        return InstallationStatus(
            gta_path=gta_path,
            valid_game=valid,
            edition=edition,
            mod_installed=inspect_windows_binary(scripts / "ALLIN1.dll").valid,
            scripthookv_installed=inspect_windows_binary(gta_path / "ScriptHookV.dll").valid,
            shvdn_installed=inspect_windows_binary(gta_path / "ScriptHookVDotNet.asi").valid,
            openrpf_installed=rpf_installed,
            installed_version=installed_version,
            rpf_loader_status=rpf_status,
        )

    def install(
        self,
        config: Config,
        progress: Callable[[int, str], None] | None = None,
    ) -> InstallResult:
        self.save_config(config)
        database = VehicleDatabase.load(self.database_path)
        if progress is None:
            return self._install(config, database)
        return self._install(config, database, progress=progress)

    def uninstall(self, config: Config) -> list[Path]:
        return self._uninstall(config)
