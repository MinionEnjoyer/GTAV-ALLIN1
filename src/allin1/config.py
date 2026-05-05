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


VALID_DENSITIES = ("none", "low", "medium", "high")


@dataclass
class GeneralConfig:
    gta_path: str = "auto"
    free_mode: bool = False
    backup: bool = True


@dataclass
class TrafficConfig:
    enabled: bool = True
    density: str = "medium"
    rich_areas_only_supers: bool = True


@dataclass
class VehiclesConfig:
    enable_all: bool = True
    disabled_classes: list[str] = field(default_factory=list)
    disabled_vehicles: list[str] = field(default_factory=list)


@dataclass
class Config:
    general: GeneralConfig
    traffic: TrafficConfig
    vehicles: VehiclesConfig

    @classmethod
    def load(cls, path: Path) -> Config:
        """Load and validate a config.toml file."""
        with open(path, "rb") as f:
            raw = tomllib.load(f)

        general = GeneralConfig(**raw.get("general", {}))
        traffic = TrafficConfig(**raw.get("traffic", {}))
        vehicles = VehiclesConfig(**raw.get("vehicles", {}))

        if traffic.density not in VALID_DENSITIES:
            raise ValueError(
                f"Invalid traffic density '{traffic.density}'. "
                f"Must be one of: {', '.join(VALID_DENSITIES)}"
            )

        return cls(general=general, traffic=traffic, vehicles=vehicles)

    @classmethod
    def default(cls) -> Config:
        return cls(
            general=GeneralConfig(),
            traffic=TrafficConfig(),
            vehicles=VehiclesConfig(),
        )


def load_prices(path: Path) -> dict[str, int]:
    """Load the prices.toml file. Returns a dict of model_name -> price."""
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
