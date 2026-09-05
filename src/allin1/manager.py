"""Testable application service used by the CLI and desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from allin1.config import Config
from allin1 import __version__
from allin1.detector import (
    inspect_detected_gta_path as detect_gta_path,
    inspect_gta_path as validate_gta_path,
)
from allin1.extensions import (
    ExtensionCatalog,
    ExtensionRegistry,
    settings_from_config,
)
from allin1.installer import InstallResult, install, uninstall
from allin1.health import inspect_windows_binary, is_shvdn_runtime_ready
from allin1.launch_policy import remove_retired_offline_policy
from allin1.rpf_loader import inspect_rpf_loader
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
        self.extension_catalog = ExtensionCatalog(project_root / "content")
        self._install = install_fn
        self._uninstall = uninstall_fn

    def load_config(self) -> Config:
        if self.config_path.exists():
            return Config.load(self.config_path)
        example = self.project_root / "config.example.toml"
        return Config.load(example) if example.exists() else Config.default()

    def save_config(self, config: Config, *, sync_runtime: bool = True, cleanup_inactive_editions: bool = True) -> None:
        config.validate()
        gta_path = self.resolve_path(config)
        runtime_scripts_present = bool(
            gta_path is not None and (gta_path / "scripts").is_dir()
        )
        # The 0.5.0 offline-launch experiment was removed before release.
        # Clean up only arguments proven to have been inserted by ALLIN1,
        # including markers left under the inactive configured edition.
        cleanup_paths = set(self.resolve_paths(config).values()) if cleanup_inactive_editions else set()
        if gta_path is not None:
            cleanup_paths.add(gta_path)
        for candidate in cleanup_paths:
            if not candidate.is_dir() or not (
                (candidate / "GTA5.exe").is_file()
                or (candidate / "GTA5_Enhanced.exe").is_file()
            ):
                continue
            remove_retired_offline_policy(candidate)
        config.save(self.config_path)
        if sync_runtime and gta_path is not None and runtime_scripts_present:
            scripts = gta_path / "scripts"
            config.save(scripts / "ALLIN1.toml")
            registry = ExtensionRegistry(gta_path)
            for manifest in self.extension_catalog.discover():
                installed = registry.builtin_root / f"{manifest.extension_id}.json"
                if installed.is_file():
                    registry.settings.update(
                        manifest, settings_from_config(manifest, config)
                    )
            registry.rebuild()

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
        rpf_dependency = inspect_rpf_loader(
            gta_path, edition == "Enhanced",
        ) if edition != "Unknown" else None
        rpf_installed = bool(rpf_dependency and rpf_dependency.ready)
        disabled_names = (
            "RageOpenV.asi.disabled",
            ("OpenRPF.asi.disabled" if edition == "Enhanced"
             else "OpenIV.asi.disabled"),
        )
        disabled_plugin = any(
            (
                gta_path / "allin1_backups" / "DisabledPlugins" / name
            ).is_file()
            for name in disabled_names
        )
        if rpf_installed and rpf_dependency is not None:
            plugin_name = rpf_dependency.plugin.name if rpf_dependency.plugin else "loader"
            rpf_status = f"Installed ({plugin_name} validated)"
        elif disabled_plugin:
            rpf_status = "Disabled"
        elif rpf_dependency is not None:
            rpf_status = rpf_dependency.reason
        else:
            rpf_status = "Missing"

        return InstallationStatus(
            gta_path=gta_path,
            valid_game=valid,
            edition=edition,
            mod_installed=inspect_windows_binary(scripts / "ALLIN1.dll").valid,
            scripthookv_installed=inspect_windows_binary(gta_path / "ScriptHookV.dll").valid,
            shvdn_installed=is_shvdn_runtime_ready(gta_path),
            openrpf_installed=rpf_installed,
            installed_version=installed_version,
            rpf_loader_status=rpf_status,
        )

    def install(
        self,
        config: Config,
        progress: Callable[[int, str], None] | None = None,
        rpf_loader_consent: Callable[[Path, bool], bool] | None = None,
        reactor_consent: Callable[[Path, bool], bool] | None = None,
    ) -> InstallResult:
        # The installer deploys the same saved configuration and creates the
        # extension registry transactionally. Avoid touching a detected live
        # installation twice before that operation begins.
        self.save_config(config, sync_runtime=False)
        database = VehicleDatabase.load(self.database_path)
        if progress is None and rpf_loader_consent is None and reactor_consent is None:
            return self._install(config, database)
        kwargs = {}
        if progress is not None:
            kwargs["progress"] = progress
        if rpf_loader_consent is not None:
            kwargs["rpf_loader_consent"] = rpf_loader_consent
        if reactor_consent is not None:
            kwargs["reactor_consent"] = reactor_consent
        return self._install(config, database, **kwargs)

    def uninstall(self, config: Config) -> list[Path]:
        return self._uninstall(config)
