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
    enable_rpf_previews: bool = True


@dataclass
class TrafficConfig:
    enabled: bool = True
    rich_areas_only_supers: bool = True
    max_driven: int = 20
    spawn_distance_min: float = 80.0
    spawn_distance_max: float = 200.0
    cleanup_distance: float = 350.0
    driven_cooldown_ms: int = 5000
    scan_cooldown_ms: int = 3000
    scan_radius: float = 200.0
    minimum_replace_distance: float = 50.0
    replacement_chance: float = 0.30
    adaptive_performance: bool = True
    minimum_fps: int = 40


@dataclass
class VehiclesConfig:
    enable_all: bool = True
    disabled_classes: list[str] = field(default_factory=list)
    disabled_vehicles: list[str] = field(default_factory=list)


@dataclass
class ScriptConfig:
    enable_logging: bool = False
    enable_dlc_police: bool = False
    gbay_key: str = "F9"
    night_vision_key: str = "N"
    world_vector_key: str = "F10"
    seat_selector_enabled: bool = True
    seat_selector_key: str = "L"
    safe_mode: bool = False
    ui_scale: float = 1.0
    reduced_motion: bool = False
    colorblind_mode: bool = False
    hold_duration_ms: int = 350
    gbay_free_mode: bool = False
    garages_always_accessible: bool = False
    gta_iv_npc_physics: bool = False


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
        if "gbay_free_mode" not in script_raw:
            script.gbay_free_mode = general.free_mode

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
        self.validate()
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
            f"backup = {boolean(self.general.backup)}\n"
            f"enable_rpf_previews = {boolean(self.general.enable_rpf_previews)}\n\n"
            "[traffic]\n"
            f"enabled = {boolean(self.traffic.enabled)}\n"
            "rich_areas_only_supers = "
            f"{boolean(self.traffic.rich_areas_only_supers)}\n"
            f"max_driven = {self.traffic.max_driven}\n"
            f"spawn_distance_min = {self.traffic.spawn_distance_min}\n"
            f"spawn_distance_max = {self.traffic.spawn_distance_max}\n"
            f"cleanup_distance = {self.traffic.cleanup_distance}\n"
            f"driven_cooldown_ms = {self.traffic.driven_cooldown_ms}\n"
            f"scan_cooldown_ms = {self.traffic.scan_cooldown_ms}\n"
            f"scan_radius = {self.traffic.scan_radius}\n"
            f"minimum_replace_distance = {self.traffic.minimum_replace_distance}\n"
            f"replacement_chance = {self.traffic.replacement_chance}\n\n"
            f"adaptive_performance = {boolean(self.traffic.adaptive_performance)}\n"
            f"minimum_fps = {self.traffic.minimum_fps}\n\n"
            "[vehicles]\n"
            f"enable_all = {boolean(self.vehicles.enable_all)}\n"
            f"disabled_classes = {string_list(self.vehicles.disabled_classes)}\n"
            f"disabled_vehicles = {string_list(self.vehicles.disabled_vehicles)}\n\n"
            "[script]\n"
            f"enable_logging = {boolean(self.script.enable_logging)}\n"
            f"enable_dlc_police = {boolean(self.script.enable_dlc_police)}\n"
            f"gbay_key = {quote(self.script.gbay_key)}\n"
            f"night_vision_key = {quote(self.script.night_vision_key)}\n"
            f"world_vector_key = {quote(self.script.world_vector_key)}\n"
            f"seat_selector_enabled = {boolean(self.script.seat_selector_enabled)}\n"
            f"seat_selector_key = {quote(self.script.seat_selector_key)}\n"
            f"safe_mode = {boolean(self.script.safe_mode)}\n"
            f"ui_scale = {self.script.ui_scale}\n"
            f"reduced_motion = {boolean(self.script.reduced_motion)}\n"
            f"colorblind_mode = {boolean(self.script.colorblind_mode)}\n"
            f"hold_duration_ms = {self.script.hold_duration_ms}\n"
            f"gbay_free_mode = {boolean(self.script.gbay_free_mode)}\n"
            "garages_always_accessible = "
            f"{boolean(self.script.garages_always_accessible)}\n"
            f"gta_iv_npc_physics = {boolean(self.script.gta_iv_npc_physics)}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def validate(self) -> None:
        """Reject invalid or conflicting launcher-controlled key bindings."""
        keys = {
            "gbay_key": self.script.gbay_key,
            "night_vision_key": self.script.night_vision_key,
            "world_vector_key": self.script.world_vector_key,
            "seat_selector_key": self.script.seat_selector_key,
        }
        allowed = ({f"F{i}" for i in range(1, 13)} |
                   {chr(i) for i in range(ord("A"), ord("Z") + 1)} |
                   {f"NUMPAD{i}" for i in range(10)})
        normalized: dict[str, str] = {}
        for setting, value in keys.items():
            key = value.strip().upper()
            if key not in allowed:
                raise ValueError(f"Unsupported {setting}: {value!r}")
            if key in normalized:
                raise ValueError(
                    f"Key {key} is assigned to both {normalized[key]} and {setting}"
                )
            normalized[key] = setting
        traffic = self.traffic
        if not 0 <= traffic.max_driven <= 100:
            raise ValueError("traffic.max_driven must be between 0 and 100")
        if traffic.spawn_distance_min < 20 or traffic.spawn_distance_max <= traffic.spawn_distance_min:
            raise ValueError("traffic spawn distances must be ordered and at least 20 metres")
        if traffic.cleanup_distance <= traffic.spawn_distance_max:
            raise ValueError("traffic.cleanup_distance must exceed spawn_distance_max")
        if not 0 <= traffic.replacement_chance <= 1:
            raise ValueError("traffic.replacement_chance must be between 0 and 1")
        if min(traffic.driven_cooldown_ms, traffic.scan_cooldown_ms) < 250:
            raise ValueError("traffic cooldowns must be at least 250 ms")
        if traffic.scan_radius <= traffic.minimum_replace_distance:
            raise ValueError("traffic.scan_radius must exceed minimum_replace_distance")
        if not 20 <= traffic.minimum_fps <= 120:
            raise ValueError("traffic.minimum_fps must be between 20 and 120")
        if not 0.75 <= self.script.ui_scale <= 1.5:
            raise ValueError("script.ui_scale must be between 0.75 and 1.5")
        if not 100 <= self.script.hold_duration_ms <= 2000:
            raise ValueError("script.hold_duration_ms must be between 100 and 2000")


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
