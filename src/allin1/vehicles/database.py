"""Vehicle database loader."""

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
class Vehicle:
    model: str
    name: str
    vehicle_class: str
    manufacturer: str
    traffic: list[str] = field(default_factory=list)
    weaponized: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> Vehicle:
        return cls(
            model=d["model"],
            name=d["name"],
            vehicle_class=d["class"],
            manufacturer=d["manufacturer"],
            traffic=d.get("traffic", []),
            weaponized=d.get("weaponized", False),
        )


class VehicleDatabase:
    """Loads and queries the vehicle database."""

    def __init__(self, vehicles: list[Vehicle]) -> None:
        self._vehicles = vehicles
        self._by_model = {v.model: v for v in vehicles}
        self._by_class: dict[str, list[Vehicle]] = {}
        for v in vehicles:
            self._by_class.setdefault(v.vehicle_class, []).append(v)

    @classmethod
    def load(cls, path: Path) -> VehicleDatabase:
        """Load the vehicle database from a TOML file."""
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        vehicles = [Vehicle.from_dict(entry) for entry in raw["vehicles"]]
        return cls(vehicles)

    @property
    def all_vehicles(self) -> list[Vehicle]:
        return list(self._vehicles)

    @property
    def classes(self) -> list[str]:
        return sorted(self._by_class.keys())

    def get(self, model: str) -> Vehicle | None:
        return self._by_model.get(model)

    def by_class(self, vehicle_class: str) -> list[Vehicle]:
        return list(self._by_class.get(vehicle_class, []))

    def filter(
        self,
        *,
        disabled_classes: list[str] | None = None,
        disabled_vehicles: list[str] | None = None,
    ) -> list[Vehicle]:
        """Return vehicles after applying exclusion filters."""
        disabled_cls = set(disabled_classes or [])
        disabled_mdl = set(disabled_vehicles or [])
        return [
            v
            for v in self._vehicles
            if v.vehicle_class not in disabled_cls and v.model not in disabled_mdl
        ]

    def __len__(self) -> int:
        return len(self._vehicles)

    def __iter__(self):
        return iter(self._vehicles)
