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
    gta_legacy_path: str = "auto"
    gta_enhanced_path: str = "auto"
    target_edition: str = "auto"
    free_mode: bool = False
    backup: bool = True


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
    # GBAY presentation requires Reactor V; there is no selectable backend.
    gbay_key: str = "F9"
    night_vision_key: str = "N"
    seat_selector_enabled: bool = True
    seat_selector_key: str = "L"
    safe_mode: bool = False
    speedometer_provider: str = "auto"
    speedometer_units: str = "kmh"
    driving_telemetry: str = "towing"
    shift_controls_enabled: bool = True
    ui_scale: float = 1.0
    reduced_motion: bool = False
    colorblind_mode: bool = False
    hold_duration_ms: int = 350
    gbay_free_mode: bool = False
    garages_always_accessible: bool = False
    enhanced_police_ai: bool = False
    gta_iv_npc_physics: bool = False
    gta_iv_npc_physics_debug: bool = False
    enhanced_smoke_effects: bool = False
    controller_enabled: bool = True
    controller_open_gbay: str = "FrontendRdown"
    controller_open_gbay_modifier: str = "FrontendLb"
    controller_night_vision: str = "FrontendLeft"
    controller_night_vision_modifier: str = "FrontendLb"
    controller_seat_selector: str = "FrontendRight"
    controller_seat_selector_modifier: str = "FrontendLb"
    controller_accept: str = "FrontendAccept"
    controller_back: str = "FrontendCancel"
    controller_up: str = "FrontendUp"
    controller_down: str = "FrontendDown"
    controller_left: str = "FrontendLeft"
    controller_right: str = "FrontendRight"
    controller_page_left: str = "FrontendLb"
    controller_page_right: str = "FrontendRb"
    controller_category_prev: str = "FrontendLt"
    controller_category_next: str = "FrontendRt"
    controller_filter: str = "FrontendY"
    controller_search: str = "FrontendX"
    controller_favorite: str = "FrontendRdown"


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

        general_raw = raw.get("general", {})
        general_fields = {f.name for f in GeneralConfig.__dataclass_fields__.values()}
        general = GeneralConfig(**{
            key: value for key, value in general_raw.items() if key in general_fields
        })

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
        # Retired backend/enable keys are ignored on import. Saving removes
        # them, without changing any gameplay, purchase, or character settings.

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
            f"gta_legacy_path = {quote(self.general.gta_legacy_path)}\n"
            f"gta_enhanced_path = {quote(self.general.gta_enhanced_path)}\n"
            f"target_edition = {quote(self.general.target_edition)}\n"
            f"free_mode = {boolean(self.general.free_mode)}\n"
            f"backup = {boolean(self.general.backup)}\n"
            "\n"
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
            f"seat_selector_enabled = {boolean(self.script.seat_selector_enabled)}\n"
            f"seat_selector_key = {quote(self.script.seat_selector_key)}\n"
            f"safe_mode = {boolean(self.script.safe_mode)}\n"
            f"speedometer_provider = {quote(self.script.speedometer_provider)}\n"
            f"speedometer_units = {quote(self.script.speedometer_units)}\n"
            f"driving_telemetry = {quote(self.script.driving_telemetry)}\n"
            f"shift_controls_enabled = {boolean(self.script.shift_controls_enabled)}\n"
            f"ui_scale = {self.script.ui_scale}\n"
            f"reduced_motion = {boolean(self.script.reduced_motion)}\n"
            f"colorblind_mode = {boolean(self.script.colorblind_mode)}\n"
            f"hold_duration_ms = {self.script.hold_duration_ms}\n"
            f"gbay_free_mode = {boolean(self.script.gbay_free_mode)}\n"
            "garages_always_accessible = "
            f"{boolean(self.script.garages_always_accessible)}\n"
            "enhanced_police_ai = "
            f"{boolean(self.script.enhanced_police_ai)}\n"
            f"gta_iv_npc_physics = {boolean(self.script.gta_iv_npc_physics)}\n"
            "gta_iv_npc_physics_debug = "
            f"{boolean(self.script.gta_iv_npc_physics_debug)}\n"
            "enhanced_smoke_effects = "
            f"{boolean(self.script.enhanced_smoke_effects)}\n"
            f"controller_enabled = {boolean(self.script.controller_enabled)}\n"
            f"controller_open_gbay = {quote(self.script.controller_open_gbay)}\n"
            f"controller_open_gbay_modifier = {quote(self.script.controller_open_gbay_modifier)}\n"
            f"controller_night_vision = {quote(self.script.controller_night_vision)}\n"
            f"controller_night_vision_modifier = {quote(self.script.controller_night_vision_modifier)}\n"
            f"controller_seat_selector = {quote(self.script.controller_seat_selector)}\n"
            f"controller_seat_selector_modifier = {quote(self.script.controller_seat_selector_modifier)}\n"
            f"controller_accept = {quote(self.script.controller_accept)}\n"
            f"controller_back = {quote(self.script.controller_back)}\n"
            f"controller_up = {quote(self.script.controller_up)}\n"
            f"controller_down = {quote(self.script.controller_down)}\n"
            f"controller_left = {quote(self.script.controller_left)}\n"
            f"controller_right = {quote(self.script.controller_right)}\n"
            f"controller_page_left = {quote(self.script.controller_page_left)}\n"
            f"controller_page_right = {quote(self.script.controller_page_right)}\n"
            f"controller_category_prev = {quote(self.script.controller_category_prev)}\n"
            f"controller_category_next = {quote(self.script.controller_category_next)}\n"
            f"controller_filter = {quote(self.script.controller_filter)}\n"
            f"controller_search = {quote(self.script.controller_search)}\n"
            f"controller_favorite = {quote(self.script.controller_favorite)}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def validate(self) -> None:
        """Reject invalid or conflicting launcher-controlled key bindings."""
        target_edition = self.general.target_edition.strip().lower()
        if target_edition not in {"auto", "legacy", "enhanced"}:
            raise ValueError(
                "general.target_edition must be 'auto', 'legacy', or 'enhanced'"
            )
        self.general.target_edition = target_edition
        for name, choices in {
            "speedometer_provider": {"auto", "builtin", "rex", "lefix", "off"},
            "speedometer_units": {"kmh", "mph"},
            "driving_telemetry": {"off", "towing", "all"},
        }.items():
            value = getattr(self.script, name)
            if not isinstance(value, str) or value not in choices:
                raise ValueError(f"script.{name} must be one of {sorted(choices)}")
        if type(self.script.shift_controls_enabled) is not bool:
            raise ValueError("script.shift_controls_enabled must be a boolean")
        keys = {
            "gbay_key": self.script.gbay_key,
            "night_vision_key": self.script.night_vision_key,
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
        controller_allowed = {
            "FrontendAccept", "FrontendCancel", "FrontendUp", "FrontendDown",
            "FrontendLeft", "FrontendRight", "FrontendLb", "FrontendRb",
            "FrontendLt", "FrontendRt", "FrontendY", "FrontendX", "FrontendRdown",
        }
        for setting in (
            "controller_open_gbay", "controller_open_gbay_modifier",
            "controller_night_vision", "controller_night_vision_modifier",
            "controller_seat_selector", "controller_seat_selector_modifier",
            "controller_accept", "controller_back", "controller_up", "controller_down",
            "controller_left", "controller_right", "controller_page_left",
            "controller_page_right", "controller_category_prev",
            "controller_category_next", "controller_filter", "controller_search",
            "controller_favorite",
        ):
            value = getattr(self.script, setting)
            if value not in controller_allowed:
                raise ValueError(f"Unsupported {setting}: {value!r}")


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
