"""Configuration loading and validation."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class GeneralConfig:
    gta_path: str = "auto"
    free_mode: bool = False
    backup: bool = True


@dataclass
class TrafficConfig:
    enabled: bool = True
    rich_areas_only_supers: bool = True


@dataclass
class VehiclesConfig:
    enable_all: bool = True
    disabled_classes: list[str] = field(default_factory=list)
    disabled_vehicles: list[str] = field(default_factory=list)


@dataclass
class ScriptConfig:
    enable_logging: bool = False
    enable_dlc_police: bool = False


@dataclass
class Config:
    general: GeneralConfig
    traffic: TrafficConfig
    vehicles: VehiclesConfig
    script: ScriptConfig

    @classmethod
    def load(cls, path: Path) -> Config:
        """Load and validate a config.toml file."""
        with open(path, "rb") as f:
            raw = tomllib.load(f)

        general = GeneralConfig(**raw.get("general", {}))

        # Filter unknown keys (e.g. removed 'density') for backwards compat.
        traffic_raw = raw.get("traffic", {})
        traffic_fields = {f.name for f in TrafficConfig.__dataclass_fields__.values()}
        traffic = TrafficConfig(**{k: v for k, v in traffic_raw.items() if k in traffic_fields})

        vehicles = VehiclesConfig(**raw.get("vehicles", {}))

        script_raw = raw.get("script", {})
        script_fields = {f.name for f in ScriptConfig.__dataclass_fields__.values()}
        script = ScriptConfig(**{k: v for k, v in script_raw.items() if k in script_fields})

        return cls(general=general, traffic=traffic, vehicles=vehicles, script=script)

    @classmethod
    def default(cls) -> Config:
        return cls(
            general=GeneralConfig(),
            traffic=TrafficConfig(),
            vehicles=VehiclesConfig(),
            script=ScriptConfig(),
        )

    def save(self, path: Path) -> None:
        """Write the configuration as TOML without requiring a TOML writer."""
        def quote(value: str) -> str:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'

        def boolean(value: bool) -> str:
            return "true" if value else "false"

        def string_list(values: list[str]) -> str:
            return "[" + ", ".join(quote(value) for value in values) + "]"

        text = (
            "[general]\n"
            f"gta_path = {quote(self.general.gta_path)}\n"
            f"free_mode = {boolean(self.general.free_mode)}\n"
            f"backup = {boolean(self.general.backup)}\n\n"
            "[traffic]\n"
            f"enabled = {boolean(self.traffic.enabled)}\n"
            "rich_areas_only_supers = "
            f"{boolean(self.traffic.rich_areas_only_supers)}\n\n"
            "[vehicles]\n"
            f"enable_all = {boolean(self.vehicles.enable_all)}\n"
            f"disabled_classes = {string_list(self.vehicles.disabled_classes)}\n"
            f"disabled_vehicles = {string_list(self.vehicles.disabled_vehicles)}\n\n"
            "[script]\n"
            f"enable_logging = {boolean(self.script.enable_logging)}\n"
            f"enable_dlc_police = {boolean(self.script.enable_dlc_police)}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def load_prices(path: Path) -> dict[str, int]:
    """Load a prices TOML file. Returns a dict of name -> price."""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    prices: dict[str, int] = {}
    for section in raw.values():
        if isinstance(section, dict):
            for model, price in section.items():
                prices[model] = int(price)
    return prices
