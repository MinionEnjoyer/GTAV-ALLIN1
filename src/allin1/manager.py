"""Testable application service used by the CLI and desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from allin1.config import Config
from allin1 import __version__
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.installer import InstallResult, install, uninstall
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
        install_fn: Callable[[Config, VehicleDatabase], InstallResult] = install,
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
        config.save(self.config_path)
        gta_path = self.resolve_path(config)
        if gta_path is not None:
            scripts = gta_path / "scripts"
            if scripts.is_dir():
                config.save(scripts / "ALLIN1.toml")

    def resolve_path(self, config: Config) -> Path | None:
        if config.general.gta_path != "auto":
            try:
                return validate_gta_path(config.general.gta_path)
            except (FileNotFoundError, ValueError):
                return Path(config.general.gta_path).expanduser()
        return detect_gta_path()

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
        rpf_installed = rpf_plugin.is_file() and rpf_plugin.stat().st_size > 0
        disabled_plugin = (
            gta_path / "allin1_backups" / "DisabledPlugins" /
            (rpf_plugin.name + ".disabled")
        )
        asi_loader = any((gta_path / name).is_file() for name in
                         ("dinput8.dll", "dsound.dll", "xinput1_4.dll"))
        if rpf_installed:
            rpf_status = "Installed"
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
            mod_installed=(scripts / "ALLIN1.dll").exists(),
            scripthookv_installed=(gta_path / "ScriptHookV.dll").exists(),
            shvdn_installed=(gta_path / "ScriptHookVDotNet.asi").exists(),
            openrpf_installed=rpf_installed,
            installed_version=installed_version,
            rpf_loader_status=rpf_status,
        )

    def install(self, config: Config) -> InstallResult:
        self.save_config(config)
        database = VehicleDatabase.load(self.database_path)
        return self._install(config, database)

    def uninstall(self, config: Config) -> list[Path]:
        return self._uninstall(config)
