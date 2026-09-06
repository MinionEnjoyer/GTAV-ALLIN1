# Launcher configuration reference — 0.6.4

Generated from `Config.default()` by `documentation_audit.py`; these are source defaults, not your saved settings.

The UI and `Config.validate()` enforce accepted ranges and combinations. Unknown or invalid values are not a migration shortcut.
Use reviewed profile/configuration actions; edit live game configuration only with the game closed and a recoverable backup.

GBAY requires Reactor V on both GTA editions. Imported `gbay_menu_enabled` and `gbay_ui_backend` keys are retired; saving removes them without changing gameplay settings. Install/Repair requires a verified Reactor installation or explicit download approval.
There is no legacy menu fallback. Native character/camera previews remain available inside the Reactor customizer.

## [general]

| Field | Type | Default |
| --- | --- | --- |
| `gta_path` | `str` | `"auto"` |
| `gta_legacy_path` | `str` | `"auto"` |
| `gta_enhanced_path` | `str` | `"auto"` |
| `target_edition` | `str` | `"auto"` |
| `free_mode` | `bool` | `false` |
| `backup` | `bool` | `true` |

## [traffic]

| Field | Type | Default |
| --- | --- | --- |
| `enabled` | `bool` | `true` |
| `rich_areas_only_supers` | `bool` | `true` |
| `max_driven` | `int` | `20` |
| `spawn_distance_min` | `float` | `80.0` |
| `spawn_distance_max` | `float` | `200.0` |
| `cleanup_distance` | `float` | `350.0` |
| `driven_cooldown_ms` | `int` | `5000` |
| `scan_cooldown_ms` | `int` | `3000` |
| `scan_radius` | `float` | `200.0` |
| `minimum_replace_distance` | `float` | `50.0` |
| `replacement_chance` | `float` | `0.3` |
| `adaptive_performance` | `bool` | `true` |
| `minimum_fps` | `int` | `40` |

## [vehicles]

| Field | Type | Default |
| --- | --- | --- |
| `enable_all` | `bool` | `true` |
| `disabled_classes` | `list[str]` | `[]` |
| `disabled_vehicles` | `list[str]` | `[]` |

## [script]

| Field | Type | Default |
| --- | --- | --- |
| `enable_logging` | `bool` | `false` |
| `enable_dlc_police` | `bool` | `false` |
| `gbay_key` | `str` | `"F9"` |
| `night_vision_key` | `str` | `"N"` |
| `seat_selector_enabled` | `bool` | `true` |
| `seat_selector_key` | `str` | `"L"` |
| `safe_mode` | `bool` | `false` |
| `ui_scale` | `float` | `1.0` |
| `reduced_motion` | `bool` | `false` |
| `colorblind_mode` | `bool` | `false` |
| `hold_duration_ms` | `int` | `350` |
| `gbay_free_mode` | `bool` | `false` |
| `garages_always_accessible` | `bool` | `false` |
| `enhanced_police_ai` | `bool` | `false` |
| `gta_iv_npc_physics` | `bool` | `false` |
| `gta_iv_npc_physics_debug` | `bool` | `false` |
| `enhanced_smoke_effects` | `bool` | `false` |
| `controller_enabled` | `bool` | `true` |
| `controller_open_gbay` | `str` | `"FrontendRdown"` |
| `controller_open_gbay_modifier` | `str` | `"FrontendLb"` |
| `controller_night_vision` | `str` | `"FrontendLeft"` |
| `controller_night_vision_modifier` | `str` | `"FrontendLb"` |
| `controller_seat_selector` | `str` | `"FrontendRight"` |
| `controller_seat_selector_modifier` | `str` | `"FrontendLb"` |
| `controller_accept` | `str` | `"FrontendAccept"` |
| `controller_back` | `str` | `"FrontendCancel"` |
| `controller_up` | `str` | `"FrontendUp"` |
| `controller_down` | `str` | `"FrontendDown"` |
| `controller_left` | `str` | `"FrontendLeft"` |
| `controller_right` | `str` | `"FrontendRight"` |
| `controller_page_left` | `str` | `"FrontendLb"` |
| `controller_page_right` | `str` | `"FrontendRb"` |
| `controller_category_prev` | `str` | `"FrontendLt"` |
| `controller_category_next` | `str` | `"FrontendRt"` |
| `controller_filter` | `str` | `"FrontendY"` |
| `controller_search` | `str` | `"FrontendX"` |
| `controller_favorite` | `str` | `"FrontendRdown"` |
