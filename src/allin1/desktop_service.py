"""Display-independent Launcher boundary shared by the React UI and tests.

Read operations never rebuild registries or save configuration. Writes require
an unexpired, one-use review bound to the exact request and current file state.
The process owner, not a WebView payload, grants game-write/launch authority.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, fields, is_dataclass
import hashlib
import json
import os
from pathlib import Path, PurePath
import shutil
import subprocess
import tempfile
import time
import uuid

from allin1 import __version__
from allin1.config import Config, GeneralConfig, TrafficConfig, VehiclesConfig, ScriptConfig
from allin1.manager import ModManager
from allin1.profiles import ProfileStore
from allin1.release_paths import contained, no_links, strict_json, tree_files
from allin1.launch_cancellation import LaunchCancellation, LaunchCancelled, checkpoint, commit_dispatch

NAVIGATION = [("setup", "Setup"), ("gameplay", "Gameplay"), ("content", "Content"),
              ("input", "Input"), ("mods", "Packages"), ("characters", "Characters"),
              ("sdk", "SDK Manager"), ("activity", "Activity"), ("help", "Help Center")]
GAME_ACTIONS = {"sync_config", "install", "uninstall", "package_install", "package_enable", "package_disable", "package_uninstall",
                "content_settings", "content_enable", "content_disable", "characters_save", "garages_save", "garages_repair", "launch", "prepare_previews", "download_previews"}
POPULATION_MODULES = {"vehicle_manager": "traffic"}
POPULATION_ACTIONS = {kind + "_population_save": kind for kind in POPULATION_MODULES.values()}
GAME_ACTIONS.update(POPULATION_ACTIONS)
LOCAL_ACTIONS = {"save_config", "save_profile", "delete_profile", "export_profile", "import_preferences", "save_content_preferences", "diagnostics", "sdk_install", "sdk_install_release", "sdk_uninstall", "sdk_open", "garages_export"}
LOCAL_ACTIONS |= {"assistant_save", "assistant_install_archive", "assistant_install_qwen", "assistant_uninstall"}
GEAR = {"ARMOR_SUPER_LIGHT", "ARMOR_LIGHT", "ARMOR_STANDARD", "ARMOR_HEAVY", "ARMOR_SUPER_HEAVY", "ARMOR_JUGGERNAUT",
        "GADGET_PARACHUTE", "WEAPON_SMOKEGRENADE", "WEAPON_FIREEXTINGUISHER", "WEAPON_PETROLCAN", "WEAPON_HAZARDCAN", "WEAPON_NIGHTVISION"}


def serializable(value):
    if is_dataclass(value): return serializable(asdict(value))
    if isinstance(value, PurePath): return str(value)
    if isinstance(value, dict): return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)): return [serializable(v) for v in sorted(value)]
    if isinstance(value, (list, tuple)): return [serializable(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(serializable(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fingerprint(path):
    path = no_links(path)
    if not path.exists(): return None
    if not path.is_file(): raise ValueError(f"Expected a file: {path}")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checkpoint()
            sha.update(chunk)
    return sha.hexdigest()


def population_backend(kind):
    # Keep the public action surface closed and frozen builds aware of the
    # single supported ambient-population policy.
    from allin1 import traffic_population
    if kind != "traffic":
        raise ValueError("Unknown population policy")
    return traffic_population


def configuration(document):
    types = {"general": GeneralConfig, "traffic": TrafficConfig, "vehicles": VehiclesConfig, "script": ScriptConfig}
    if not isinstance(document, dict) or set(document) != set(types): raise ValueError("Invalid configuration sections")
    sections = {}
    for section, cls in types.items():
        values = document[section]
        if section == "general" and isinstance(values, dict):
            values = {k: v for k, v in values.items() if k != "enable_rpf_previews"}
        if section == "script" and isinstance(values, dict):
            # Accept saved API documents while retiring obsolete UI selections.
            # Copy rather than mutate the caller's request/review evidence.
            values = {k: v for k, v in values.items()
                      if k not in {
                          "gbay_menu_enabled",
                          "gbay_ui_backend",
                          "enhanced_police_ai",
                          "gta_iv_npc_physics",
                          "gta_iv_npc_physics_debug",
                      }}
        defaults = asdict(cls())
        if not isinstance(values, dict) or set(values) != set(defaults): raise ValueError(f"Invalid {section} configuration fields")
        for key, value in values.items():
            expected = type(defaults[key])
            if (expected is float and type(value) not in (int, float)) or (expected is not float and type(value) is not expected):
                raise ValueError(f"Invalid type for {section}.{key}")
            strings = value if isinstance(value, list) else [value] if isinstance(value, str) else []
            if any(not isinstance(item, str) or len(item) > 4096 or any(c in item for c in '\r\n\0') for item in strings):
                raise ValueError(f"Invalid text for {section}.{key}")
        sections[section] = cls(**values)
    result = Config(**sections); result.validate()
    return result


class SelectedManager(ModManager):
    """Never silently switch to a different installed GTA edition."""
    def save_config(self, config, *, sync_runtime=True):
        super().save_config(config, sync_runtime=sync_runtime, cleanup_inactive_editions=False)

    def resolve_paths(self, config):
        result = {}
        for edition, value in (("legacy", config.general.gta_legacy_path), ("enhanced", config.general.gta_enhanced_path)):
            if value and value.lower() != "auto": result[edition] = no_links(Path(value))
        if config.general.gta_path and config.general.gta_path.lower() != "auto":
            path = no_links(Path(config.general.gta_path))
            edition = "enhanced" if (path / "GTA5_Enhanced.exe").is_file() else "legacy"
            result.setdefault(edition, path)
        return result


class LauncherService:
    def __init__(self, project_root, state_root, *, allow_game_writes=False, allow_launch=False, progress=None, sdk_root=None, package_library_root=None, assistant_root=None):
        self.project = no_links(Path(project_root))
        self.state = no_links(Path(state_root))
        self.sdk_root = no_links(Path(sdk_root)) if sdk_root else contained(self.state, "SDK")
        self.package_library_root = no_links(Path(package_library_root)) if package_library_root else contained(self.state, "packages")
        self.assistant_root = no_links(Path(assistant_root)) if assistant_root else contained(self.state, "Assistant")
        self.manager = SelectedManager(self.project)
        self.manager.config_path = contained(self.state, "config.toml")
        self.profiles = ProfileStore(contained(self.state, "profiles"))
        self.allow_game_writes, self.allow_launch = allow_game_writes, allow_launch
        self.progress = progress or (lambda percent, message: None)
        self.rpf_progress = None
        self.reviews = {}
        self.activity = []
        self.sdk_release = None
        self.launcher_release = None
        self.startup_monitor = None
        self.launch_target = None
        self.diagnostic_session = None
        self.launch_cancellation = LaunchCancellation()
        from allin1.preview_render_control import PreviewRenderControl
        self.preview_render_control = PreviewRenderControl()

    def config(self):
        if self.manager.config_path.is_file(): return Config.load(no_links(self.manager.config_path))
        # Import existing Launcher preferences in memory; migration writes only
        # happen after a user saves a reviewed configuration.
        legacy = self.project / "config.toml"
        return Config.load(no_links(legacy)) if legacy.is_file() else Config.default()

    def game(self, config, *, required=True):
        game = self.manager.resolve_path(config)
        if game is None:
            if required: raise ValueError("Select a GTA installation in Setup first")
            return None
        game = no_links(game)
        if not game.is_dir() or not any((game / name).is_file() for name in ("GTA5.exe", "GTA5_Enhanced.exe")):
            if required: raise ValueError("Selected folder does not contain a GTA executable")
            return None
        return game

    def snapshot(self, request):
        config = configuration(request["config"]) if "config" in request else self.config()
        state = {"config": serializable(config), "saved": fingerprint(self.manager.config_path)}
        game = self.game(config, required=False)
        if game:
            owned = [game / "scripts" / name for name in ("ALLIN1.toml", "ALLIN1_characters.json", "ALLIN1_garage.json")]
            state["game"] = str(game)
            state["owned"] = {str(p): fingerprint(p) for p in owned}
            registry = game / "scripts" / ".allin1"
            if registry.is_dir(): state["registry"] = self.tree_identity(registry)
            population = POPULATION_ACTIONS.get(request.get("action")) or POPULATION_MODULES.get(request.get("module"))
            if population:
                # Bind installed catalog authorization as well as the policy.
                # Catalog payloads can live outside scripts/.allin1.
                state["population"] = population_backend(population).inspect_population(game)
        if request.get("source"):
            source = self.input_path(request["source"])
            if request.get("action") == "import_preferences":
                from allin1.preference_migration import prepare
                state["migration"] = prepare(source, self.state)[0]["plan_sha256"]
            else:
                if (request.get("action") == "package_install" or request.get("module") == "package") and source.suffix.lower() == ".toml": source = source.parent
                state["source"] = self.tree_identity(source) if source.is_dir() else fingerprint(source)
        if request.get("name"):
            state["profile"] = fingerprint(contained(self.profiles.directory, ProfileStore.validate_name(request["name"]) + ".toml"))
        if request.get("destination"): state["destination"] = fingerprint(self.output_path(request["destination"]))
        if request.get("action") in {"save_content_preferences", "content_settings", "content_enable", "content_disable"}:
            from allin1.desktop_content import catalog
            state["content"] = catalog(self.manager, game, config)
        if str(request.get("action", "")).startswith("sdk_"):
            state["sdk"] = self.tree_identity(self.sdk_root) if self.sdk_root.exists() else None
            if request.get("action") == "sdk_install_release": state["release"] = serializable(self.sdk_release)
        if str(request.get("action", "")).startswith("assistant_"):
            from allin1.assistant_manager import ASSISTANT_SOURCES
            state["assistant"] = self.tree_identity(self.assistant_root) if self.assistant_root.exists() else None
            state["assistant_sources"] = serializable(ASSISTANT_SOURCES)
        return digest(state)

    @staticmethod
    def tree_identity(root):
        files = tree_files(root)
        if len(files) > 10000: raise ValueError("Selected tree exceeds 10,000 files")
        return {name: fingerprint(path) for name, path in files.items()}

    @staticmethod
    def input_path(value):
        if not isinstance(value, str) or not Path(value).is_absolute() or '..' in Path(value).parts: raise ValueError("Choose an absolute source path")
        path = no_links(Path(value))
        if not path.exists(): raise FileNotFoundError(path)
        return path

    def output_path(self, value):
        if not isinstance(value, str) or not Path(value).is_absolute() or '..' in Path(value).parts: raise ValueError("Choose an absolute output path")
        target = no_links(Path(value))
        for root in [target.parent, *target.parents]:
            if any((root / exe).is_file() for exe in ("GTA5.exe", "GTA5_Enhanced.exe")):
                raise ValueError("Export reports outside the game installation")
        if target.exists(): raise FileExistsError("Choose a new output file")
        if not target.parent.is_dir(): raise ValueError("Choose an existing output folder")
        return target

    def catalog(self):
        from allin1.help_topics import HELP_TOPICS
        return {"schema_version": 1, "version": __version__, "desktop_version": __version__,
                "build_identity": getattr(self, "build_identity", None),
                "navigation": [{"id": key, "label": label, "shortcut": f"Ctrl+{i + 1}"} for i, (key, label) in enumerate(NAVIGATION)],
                "help_topics": serializable(HELP_TOPICS), "defaults": serializable(Config.default()),
                "capabilities": {"game_writes": self.allow_game_writes, "launch": self.allow_launch}}

    def inspect(self, request):
        module = request.get("module", "setup")
        config = configuration(request["config"]) if "config" in request else self.config()
        result = {"kind": "launcher_session", "module": module, "config": serializable(config), "state_sha256": self.snapshot(request), "read_only": True}
        game = self.game(config, required=False)
        if module in {"setup", "gameplay", "input"}:
            result.update(status=serializable(self.manager.status(config)), profiles=self.profiles.list())
            if module == "setup":
                from allin1.reactor_bootstrap import inspect_reactor_installation
                result['reactor'] = serializable(inspect_reactor_installation(game)) if game else {
                    'available': False, 'reason': 'Select a GTA installation to check Reactor V.',
                }
        elif module == "content":
            from allin1.desktop_content import catalog
            result["content"] = catalog(self.manager, game, config)
        elif module in POPULATION_MODULES:
            kind = POPULATION_MODULES[module]
            result[kind + "_population"] = population_backend(kind).inspect_population(self.game(config))
            if self.snapshot(request) != result["state_sha256"]:
                raise ValueError("Population policy or installed catalogs changed during inspection; reload")
        elif module == "mods":
            from allin1.mods import ModIntegrationService, ModCatalog
            from allin1.addon_sdk import AddonSdkCatalog
            from allin1.desktop_content import catalog as content_catalog
            catalog = ModCatalog(self.project / "mods" / "catalog", self.package_library_root)
            result["packages"] = [serializable(m) for m in catalog.discover()]
            result["installed"] = serializable(ModIntegrationService(game).list_installed()) if game else []
            result["builtin_packages"] = [item for item in content_catalog(self.manager, game, config) if item["source"] == "built-in"]
            result["sdk_examples"] = [{"id": item.addon_id, "name": item.name, "summary": item.summary,
                                       "editions": list(item.editions)} for item in AddonSdkCatalog(self.project).discover()]
        elif module == "package":
            from allin1.mods import open_mod_package
            from allin1.desktop_packages import describe
            source = self.input_path(request.get("source"))
            with open_mod_package(source) as manifest:
                manifest.validate_payload()
                result.update(source=str(source), package=describe(manifest, game))
            if self.snapshot(request) != result["state_sha256"]:
                raise ValueError("Package changed during inspection; inspect it again")
        elif module == "characters":
            if game:
                result.update(self.characters(config))
                if self.snapshot(request) != result["state_sha256"]:
                    raise ValueError("Character files changed during inspection; reload")
        elif module == "sdk":
            from allin1.sdk_manager import read_sdk_status
            from allin1.desktop_assistant import catalog as assistant_catalog
            result["sdk"] = serializable(read_sdk_status(self.sdk_root))
            result["assistant"] = serializable(assistant_catalog(self.assistant_root))
        elif module == "assistant_hardware":
            from allin1.desktop_assistant import hardware
            source = self.input_path(request["source"]) if request.get("source") else None
            result["hardware"] = serializable(hardware(request.get("profile", "recommended"), self.assistant_root, source))
        elif module == "activity":
            from allin1.desktop_activity import read
            result["activity"] = read(self.state)
        elif module == "help": result["help_topics"] = self.catalog()["help_topics"]
        else: raise ValueError("Unknown Launcher module")
        return result

    def characters(self, config):
        from allin1.customization import LoadoutStore, GarageSaveStore
        from allin1.vehicles.database import VehicleDatabase
        from allin1.config import tomllib
        game = self.game(config)
        models = sorted(v.model for v in VehicleDatabase.load(self.project / "data/vehicles.toml"))
        with (self.project / "data/weapons.toml").open("rb") as stream: weapons = sorted(v["name"] for v in tomllib.load(stream)["weapons"])
        character_file = no_links(game / "scripts/ALLIN1_characters.json")
        garage_file = no_links(game / "scripts/ALLIN1_garage.json")
        garage_error = None
        try: garages = GarageSaveStore(garage_file, set(models)).load()
        except (OSError, ValueError) as error: garages, garage_error = None, str(error)
        return {"document_sha256": {"loadouts": self.character_identity(config, "characters_save"),
                                    "garages": self.character_identity(config, "garages_save")},
                "loadouts": serializable(LoadoutStore(character_file, set(weapons), GEAR).load()),
                "garages": garages, "garage_error": garage_error, "models": models, "weapons": weapons, "gear": sorted(GEAR)}

    def character_identity(self, config, action):
        name = "ALLIN1_garage.json" if action == "garages_save" else "ALLIN1_characters.json"
        path = no_links(self.game(config) / "scripts" / name)
        return digest({"path": str(path), "sha256": fingerprint(path)})

    def read(self, operation, payload):
        if operation == "catalog": return self.catalog()
        if operation == "inspect": return self.inspect(payload)
        if operation == "open_activity_folder":
            path = contained(self.state, "logs")
            if not path.is_dir(): raise ValueError("No activity folder yet; complete a reviewed action first")
            if os.name != "nt": raise ValueError("Opening the activity folder requires Windows")
            os.startfile(path)
            return {"opened": str(path)}
        if operation == "load_profile":
            no_links(self.profiles.path_for(payload.get("name", "")))
            return {"config": serializable(self.profiles.load(payload.get("name", "")))}
        if operation == "health":
            from allin1.health import scan_installation
            return serializable(scan_installation(self.game(self.config())))
        if operation == "check_update":
            from allin1.versioning import fetch_latest_release
            self.launcher_release = fetch_latest_release()
            return serializable(self.launcher_release)
        if operation == "open_launcher_release":
            if self.launcher_release is None: raise ValueError("Check Launcher releases first")
            if os.name != "nt": raise ValueError("Opening a release page requires Windows")
            # Never dispatch a protocol/URL supplied by release metadata or the
            # WebView to the OS. This is the existing manual-download channel.
            url = "https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/latest"
            os.startfile(url)
            return {"opened": url}
        if operation == "check_sdk_update":
            from allin1.sdk_manager import fetch_latest_sdk_release
            self.sdk_release = fetch_latest_sdk_release()
            return serializable(self.sdk_release)
        if operation == "startup_status":
            if self.startup_monitor is None: return {"active": False}
            from allin1.game_launcher import probe_gta_runtime
            from allin1.reactor_bootstrap import MILESTONE_LABELS
            state = self.startup_monitor.sample(process_running=bool(probe_gta_runtime(self.launch_target).process_ids))
            result = {"schema_version": 1, "event": "launcher.reactor.startup", **serializable(state),
                "active": not state.terminal and not state.story_ready, "milestones": serializable(MILESTONE_LABELS)}
            if not result["active"]: self.startup_monitor = None
            return result
        if operation == "read_garages":
            source = self.input_path(payload.get("source"))
            if source.stat().st_size > 8 * 1024**2: raise ValueError("Garage input exceeds 8 MiB")
            from allin1.customization import CHARACTERS, GarageSaveStore
            from allin1.vehicles.database import VehicleDatabase
            raw = strict_json(source.read_bytes())
            if not isinstance(raw, dict): raise ValueError("Garage document must be an object")
            garages = {name: raw.get(name, []) for name in CHARACTERS}
            if any(not isinstance(rows, list) or any(not isinstance(row, dict) or type(row.get("slot")) is not int for row in rows) for rows in garages.values()):
                raise ValueError("Garage characters must contain lists of vehicle objects with integer slots")
            models = {v.model for v in VehicleDatabase.load(self.project / "data/vehicles.toml")}
            GarageSaveStore(source, models).validate(garages)
            return {"garages": garages}
        raise ValueError("Unknown read operation")

    def review(self, request):
        if not isinstance(request, dict) or len(json.dumps(request)) > 512 * 1024: raise ValueError("Invalid review request")
        action = request.get("action")
        if action not in GAME_ACTIONS | LOCAL_ACTIONS: raise ValueError("Unknown Launcher action")
        config = configuration(request["config"]) if "config" in request else self.config()
        game = self.game(config) if action in GAME_ACTIONS or action == "garages_export" else None
        if action in GAME_ACTIONS and not self.allow_game_writes: raise ValueError("This service does not have game-write authority")
        if action == "launch" and not self.allow_launch: raise ValueError("This service does not have launch authority")
        if action in {"launch", "prepare_previews"} and type(request.get("skip_previews", False)) is not bool:
            raise ValueError("skip_previews must be a boolean")
        if action in {"launch", "prepare_previews"}:
            if type(request.get("missing_previews_only", False)) is not bool:
                raise ValueError("missing_previews_only must be a boolean")
            from allin1.preview_policy import validate_skip_categories
            validate_skip_categories(request.get("skip_preview_categories", []))
        if action == "launch" and type(request.get("quick_launch", False)) is not bool:
            raise ValueError("quick_launch must be a boolean")
        evidence = {"action": action, "target": str(game or self.state), "game_write": action in GAME_ACTIONS,
                    "state_sha256": self.snapshot(request), "request": copy.deepcopy(request)}
        if action in POPULATION_ACTIONS:
            kind = POPULATION_ACTIONS[action]
            backend = population_backend(kind)
            before = backend.inspect_population(game)
            if request.get("expected_document_sha256") != before["document_sha256"]:
                raise ValueError("Population policy changed; reload before reviewing")
            document = backend.validate_document(game, request.get("document"))
            evidence[kind + "_population"] = {"before": before["document"], "after": document}
            evidence["request"]["document"] = document
            evidence["preservation"] = "Changes ambient population policy only. Original game assets, player inventory and saves are preserved. Takes effect on the next game/script start."
            if self.snapshot(request) != evidence["state_sha256"]:
                raise ValueError("Population policy or catalogs changed during review; reload")
        if action in {"launch", "prepare_previews"}:
            from allin1.preview_inventory import preview_counts
            evidence["preview_counts"] = preview_counts(self.project, game)
        if action.startswith("sdk_"): evidence["target"] = str(self.sdk_root)
        if action == "download_previews":
            from allin1.default_previews import plan
            evidence["preview_download"] = plan(self.project, request.get("categories"))
            evidence["request"]["preview_plan_sha256"] = hashlib.sha256(json.dumps(evidence["preview_download"], sort_keys=True).encode()).hexdigest()
            evidence["preservation"] = "Installs vanilla default images only. Generated/custom previews, game models and saves are preserved. Both editions can reuse the verified download cache."
        if action in {"install", "uninstall"}:
            from allin1.installer import _preflight_installation_roots
            _preflight_installation_roots(game)
        if action == "uninstall":
            evidence["preservation"] = "Character and garage saves, customization, GBAY preferences, configuration and legacy ALLIN1 user data remain in place. Runtime payloads are removed; this is not a data purge."
        if action.startswith("assistant_"):
            from allin1 import assistant_manager
            from allin1.desktop_assistant import configuration as assistant_config, hardware
            evidence["target"] = str(self.assistant_root)
            if action == "assistant_save":
                evidence["request"]["assistant_config"] = serializable(assistant_config(request.get("assistant_config"), self.assistant_root))
            elif action in {"assistant_install_archive", "assistant_install_qwen"}:
                source = self.input_path(request.get("source")) if action == "assistant_install_archive" else None
                report = hardware(request.get("profile", "recommended"), self.assistant_root, source)
                assistant_manager.require_assistant_hardware(report)
                evidence["assistant_hardware"] = serializable(report)
                if source is None:
                    selected = assistant_manager.assistant_source(request.get("profile", "recommended"))
                    evidence["assistant_download"] = {**serializable(selected), "total_download_bytes": selected.total_download_bytes}
                else:
                    evidence["package"] = serializable(assistant_manager.inspect_assistant_archive(source))
        if action == "import_preferences":
            from allin1.preference_migration import prepare
            migration, _ = prepare(self.input_path(request.get("source")), self.state)
            if not migration["copy_count"]:
                raise ValueError("All selected preferences already exist; nothing will be overwritten")
            evidence["migration"] = migration
            evidence["request"]["migration_sha256"] = migration["plan_sha256"]
        if action == "save_content_preferences":
            from allin1.desktop_content import prepare_local_settings
            prepare_local_settings(self.manager, request.get("id"), request.get("settings"), copy.deepcopy(config))
        if action in {"characters_save", "garages_save"}:
            expected = request.get("expected_document_sha256") if "expected_document_sha256" in request else request.get("expected_state_sha256")
            actual = self.character_identity(config, action) if "expected_document_sha256" in request else self.snapshot({"config": serializable(config)})
            if expected != actual:
                raise ValueError("Character files changed; reload before reviewing")
            self.character_bytes(request, config)
        if action == "sdk_install":
            from allin1.sdk_manager import inspect_sdk_archive
            evidence["package"] = serializable(inspect_sdk_archive(self.input_path(request.get("source"))))
        if action == "sdk_install_release":
            if self.sdk_release is None: raise ValueError("Check the latest SDK release before reviewing installation")
            evidence["release"] = serializable(self.sdk_release)
        if action == "sdk_open":
            if request.get("workspace", "linker") not in {"linker", "assets", "rpf", "models", "assistant"}: raise ValueError("Unknown SDK workspace")
        if action == "package_install":
            from allin1.mods import open_mod_package
            from allin1.desktop_packages import describe, settings
            if "expected_state_sha256" in request and request["expected_state_sha256"] != evidence["state_sha256"]:
                raise ValueError("Package or installation changed; inspect the package again")
            with open_mod_package(self.input_path(request.get("source"))) as manifest:
                from allin1.mods import ModIntegrationService
                bundle_info = describe(manifest, game)
                manifest = manifest.select_component(ModIntegrationService(game).edition, request.get("component_id"))
                evidence["package"] = describe(manifest, game) if bundle_info["schema_version"] == 6 else bundle_info
                if bundle_info["schema_version"] == 6:
                    evidence["package"]["bundle"] = {"id": bundle_info["id"], "selected_edition": bundle_info["selected_edition"]}
                    component = next(item for item in bundle_info["components"] if item["id"] == manifest.mod_id)
                    if component["install_blocked_reason"]:
                        raise ValueError(component["install_blocked_reason"])
                manifest.validate_payload()
                evidence["request"]["settings"] = settings(manifest, request.get("settings"))
            if self.snapshot(request) != evidence["state_sha256"]:
                raise ValueError("Package changed during review; inspect it again")
        if action in {"content_settings", "content_enable", "content_disable"}:
            from allin1.extensions import ExtensionRegistry
            registry = ExtensionRegistry(game)
            extension_ids = {item["id"] for item in registry.inspect()["extensions"]}
            package_id = request.get("id")
            if package_id in extension_ids:
                manifest = registry.installed_manifest(package_id)
                if action == "content_settings":
                    for key, value in request.get("settings", {}).items(): manifest.setting(key).validate(value)
            else:
                from allin1.mods import ModIntegrationService
                installed_ids = {item.mod_id for item in ModIntegrationService(game).list_installed()}
                if package_id not in installed_ids:
                    raise ValueError("Installed content package not found")
                if action == "content_settings":
                    raise ValueError("This managed package has no package-owned settings")
        token = uuid.uuid4().hex
        self.reviews = {k: v for k, v in self.reviews.items() if time.monotonic() - v[0] < 300}
        if len(self.reviews) >= 32: self.reviews.pop(next(iter(self.reviews)))
        evidence["review_id"] = token; evidence["review_sha256"] = digest(evidence)
        self.reviews[token] = (time.monotonic(), evidence)
        return {"kind": "launcher_review", **evidence}

    def apply(self, payload):
        stored = self.reviews.get(payload.get("review_id"))
        if stored is None or stored[1]["request"]["action"] != "launch":
            return self._apply(payload)
        with self.launch_cancellation.preparing(payload["review_id"]):
            try:
                return self._apply(payload)
            except LaunchCancelled:
                event = {"schema_version": 1, "event": "launcher.action.cancelled", "action": "launch",
                         "time": time.time(), "review_id": payload["review_id"]}
                self.activity.append(event)
                from allin1.desktop_activity import append
                try: append(self.state, event)
                except (OSError, ValueError): pass
                self.progress(None, "Launch cancelled. GTA was not started; completed previews remain cached.")
                return {"schema_version": 1, "kind": "launcher_cancelled", "action": "launch",
                        "review_id": payload["review_id"], "result": {"status": "cancelled", "game_started": False},
                        "saved_config": serializable(self.config())}

    def cancel_launch(self, payload):
        return self.launch_cancellation.request(payload)

    def set_preview_workers(self, payload):
        if self.launch_cancellation.status().get('cancel_requested'):
            raise ValueError('Launch cancellation is already requested')
        return self.preview_render_control.request(payload)

    def _apply(self, payload):
        if payload.get("confirmed") is not True: raise ValueError("Explicit confirmation is required")
        stored = self.reviews.pop(payload.get("review_id"), None)
        if stored is None: raise ValueError("Review expired or already used; review again")
        created, review = stored
        if time.monotonic() - created >= 300 or payload.get("review_sha256") != review["review_sha256"]:
            raise ValueError("Review expired or does not match")
        request = review["request"]
        if request["action"] == "launch": self.progress(None, "Checking reviewed launch")
        checkpoint()
        if self.snapshot(request) != review["state_sha256"]: raise ValueError("Files changed after review; review again")
        config = configuration(request["config"]) if "config" in request else self.config()
        action = request["action"]
        if action in GAME_ACTIONS:
            if not self.allow_game_writes: raise ValueError("Game-write authority is required")
            self.require_closed()
        self.progress(None if action in {"launch", "prepare_previews"} else 0, f"Starting {action.replace('_', ' ')}")
        from allin1.rpf_progress import RpfProgress
        if action.startswith("package_") or action in {"content_enable", "content_disable"}:
            self.rpf_progress = RpfProgress(self.progress)
        try:
            if action in {'launch', 'prepare_previews'}:
                with self.preview_render_control.session(review['review_id']):
                    result = self.perform(request, config)
            else:
                result = self.perform(request, config)
        finally:
            self.rpf_progress = None
        receipt = {"schema_version": 1, "kind": "launcher_applied", "action": action,
                   "review_id": review["review_id"], "review_sha256": review["review_sha256"], "result": serializable(result)}
        if action in {"save_config", "sync_config", "install", "launch", "content_settings", "save_content_preferences", "import_preferences"}:
            receipt["saved_config"] = serializable(self.config())
        event = {"schema_version": 1, "event": "launcher.action.completed", "action": action, "time": time.time(), "review_id": review["review_id"]}
        self.activity.append(event)
        from allin1.desktop_activity import append
        try:
            append(self.state, event)
        except (OSError, ValueError) as error:
            # The requested mutation already succeeded. A journal failure must
            # not imply that retrying the mutation is safe or necessary.
            receipt["warning"] = "Action completed, but activity could not be saved: " + str(error)
        self.progress(None if action in {"launch", "prepare_previews"} else 100, f"Completed {action.replace('_', ' ')}")
        return receipt

    @staticmethod
    def require_closed():
        import csv
        from allin1.processes import run_hidden
        if os.name != "nt": raise ValueError("Game writes require Windows process checks")
        result = run_hidden([str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/tasklist.exe"), "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=15)
        if result.returncode or not result.stdout.strip(): raise ValueError("Could not verify that GTA V is closed")
        rows = list(csv.reader(result.stdout.splitlines()))
        if any(len(row) < 2 for row in rows): raise ValueError("Invalid process inventory; cannot authorize a game write")
        if any(row[0].casefold() in {"gta5.exe", "gta5_enhanced.exe", "playgtav.exe"} for row in rows):
            raise ValueError("Close GTA V before applying Launcher changes")

    def character_bytes(self, request, config):
        from allin1.customization import CharacterLoadout, CharacterOutfit, CharacterProgress, OutfitVariation, LoadoutStore, GarageSaveStore
        context = self.characters(config)
        with tempfile.TemporaryDirectory(prefix="allin1-character-review-") as temporary:
            path = Path(temporary) / "characters.json"
            if request["action"] == "garages_save":
                GarageSaveStore(path, set(context["models"])).save(request["document"])
            else:
                loadouts = copy.deepcopy(request["document"])
                for character, value in loadouts.items():
                    outfit = value["outfit"]
                    outfit["components"] = [OutfitVariation(**v) for v in outfit["components"]]
                    outfit["props"] = [OutfitVariation(**v) for v in outfit["props"]]
                    value["outfit"] = CharacterOutfit(**outfit)
                    value["progress"] = CharacterProgress(**value["progress"])
                    loadouts[character] = CharacterLoadout(**value)
                store = LoadoutStore(path, set(context["weapons"]), GEAR)
                original = self.game(config) / "scripts/ALLIN1_characters.json"
                if original.is_file(): shutil.copy2(no_links(original), path)
                store.save(loadouts)
            return path.read_bytes()

    def perform(self, request, config):
        action = request["action"]
        if action in POPULATION_ACTIONS:
            return population_backend(POPULATION_ACTIONS[action]).save_population(
                self.game(config), request["document"], request["expected_document_sha256"])
        if action.startswith("assistant_"):
            from allin1 import assistant_manager
            from allin1.desktop_assistant import configuration as assistant_config
            if action == "assistant_save":
                return {"saved": str(assistant_manager.save_assistant_config(
                    assistant_config(request["assistant_config"], self.assistant_root), self.assistant_root))}
            if action == "assistant_install_archive":
                return assistant_manager.install_assistant_archive(self.input_path(request["source"]), self.assistant_root)
            if action == "assistant_install_qwen":
                return assistant_manager.install_qwen_source(request.get("profile", "recommended"), self.assistant_root,
                    progress=lambda message, done, total: self.progress(int(100 * done / max(1, total)), message))
            return {"removed": assistant_manager.uninstall_assistant(self.assistant_root)}
        if action == "save_content_preferences":
            from allin1.desktop_content import prepare_local_settings
            prepare_local_settings(self.manager, request["id"], request["settings"], config)
            self.state.mkdir(parents=True, exist_ok=True)
            config.save(no_links(self.manager.config_path))
            return {"saved": str(self.manager.config_path), "game_write": False}
        if action == "import_preferences":
            from allin1.preference_migration import apply
            return apply(self.input_path(request["source"]), self.state, request["migration_sha256"])
        if action == "save_config":
            self.state.mkdir(parents=True, exist_ok=True); config.save(no_links(self.manager.config_path)); return {"saved": str(self.manager.config_path)}
        if action == "sync_config":
            self.state.mkdir(parents=True, exist_ok=True)
            self.manager.save_config(config); return {"saved": True}
        if action == "save_profile":
            no_links(self.profiles.directory).mkdir(parents=True, exist_ok=True)
            return {"profile": str(self.profiles.save(request["name"], config))}
        if action == "delete_profile": self.profiles.delete(request["name"]); return {"deleted": request["name"]}
        if action == "export_profile": return {"output": self.profiles.export(request["name"], self.output_path(request["destination"]))}
        if action == "install":
            self.state.mkdir(parents=True, exist_ok=True)
            return self.manager.install(config, progress=self.progress,
                reactor_consent=lambda *_: request.get("reactor_consent") is True,
                rpf_loader_consent=lambda *_: request.get("rpf_loader_consent") is True)
        if action == "uninstall": return self.manager.uninstall(config)
        if action.startswith("package_"):
            from allin1.mods import ModIntegrationService, open_mod_package
            service = ModIntegrationService(self.game(config), rpf_progress=self.rpf_progress)
            if action == "package_install":
                with open_mod_package(self.input_path(request["source"])) as manifest:
                    return service.install(manifest, initial_settings=request.get("settings"),
                                           component_id=request.get("component_id"))
            if action == "package_uninstall": return service.uninstall(request["id"])
            return service.set_enabled(request["id"], action == "package_enable")
        if action.startswith("content_"):
            from allin1.extensions import ExtensionRegistry, apply_settings_to_config
            registry = ExtensionRegistry(self.game(config))
            if action == "content_settings":
                manifest = registry.installed_manifest(request["id"])
                apply_settings_to_config(manifest, config, request["settings"])
                self.state.mkdir(parents=True, exist_ok=True)
                self.manager.save_config(config)
                return registry.set_settings(request["id"], request["settings"])
            installed = next((item for item in registry.inspect()["extensions"] if item["id"] == request["id"]), None)
            if installed is not None and installed["source"] == "built-in":
                return registry.set_builtin_enabled(request["id"], action == "content_enable")
            from allin1.mods import ModIntegrationService
            return ModIntegrationService(self.game(config), rpf_progress=self.rpf_progress).set_enabled(request["id"], action == "content_enable")
        if action in {"characters_save", "garages_save"}:
            content = self.character_bytes(request, config)
            target = no_links(self.game(config) / "scripts" / ("ALLIN1_characters.json" if action == "characters_save" else "ALLIN1_garage.json"))
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + "." + uuid.uuid4().hex)
            try:
                with temporary.open("xb") as stream: stream.write(content)
                temporary.replace(no_links(target))
            finally: temporary.unlink(missing_ok=True)
            return {"saved": str(target), "sha256": fingerprint(target)}
        if action in {"garages_repair", "garages_export"}:
            from allin1.customization import GarageSaveStore
            context = self.characters(config)
            store = GarageSaveStore(no_links(self.game(config) / "scripts/ALLIN1_garage.json"), set(context["models"]))
            return store.repair() if action == "garages_repair" else store.export_file(self.output_path(request["destination"]))
        if action == "diagnostics":
            from allin1.diagnostics import create_diagnostic_bundle
            game = self.game(config, required=False)
            return create_diagnostic_bundle(self.output_path(request["destination"]), self.project, game / "scripts" if game else None)
        if action == "sdk_install":
            from allin1.sdk_manager import install_sdk_archive
            return install_sdk_archive(self.input_path(request["source"]), self.sdk_root)
        if action == "sdk_install_release":
            from allin1.sdk_manager import install_sdk_release
            return install_sdk_release(self.sdk_release, self.sdk_root,
                progress=lambda message, done, total: self.progress(int(100 * done / max(1, total)), message))
        if action == "sdk_uninstall":
            from allin1.sdk_manager import uninstall_sdk
            return uninstall_sdk(self.sdk_root)
        if action == "sdk_open":
            from allin1.sdk_manager import read_sdk_status
            from allin1.processes import hidden_process_options
            status = read_sdk_status(self.sdk_root)
            if not status.healthy: raise ValueError(status.detail)
            from allin1.sdk_installation import SHELL
            command = [str(status.executable)]
            if status.executable.name == SHELL: command.extend(["--workspace", request.get("workspace", "linker")])
            return {"pid": subprocess.Popen(command, cwd=status.root, **hidden_process_options()).pid}
        if action == "download_previews":
            from allin1.default_previews import install, plan
            current = hashlib.sha256(json.dumps(plan(self.project, request.get("categories")), sort_keys=True).encode()).hexdigest()
            if current != request.get("preview_plan_sha256"):
                raise ValueError("Preview download changed after review; review again")
            return install(self.project, self.game(config), self.state / "default-previews", categories=request.get("categories"), progress=self.progress)
        if action == "prepare_previews": return self.prepare_previews(config, skip=request.get("skip_previews", False), skip_categories=request.get("skip_preview_categories", []), missing_only=request.get("missing_previews_only", False))
        if action == "launch": return self.launch(config, skip_previews=request.get("skip_previews", False), skip_preview_categories=request.get("skip_preview_categories", []), quick_launch=request.get("quick_launch", False), missing_previews_only=request.get("missing_previews_only", False))
        raise ValueError("Unsupported Launcher action")

    def prepare_previews(self, config, *, skip=False, skip_categories=(), missing_only=False):
        from allin1.prelaunch_previews import prepare_all
        try:
            return prepare_all(self.project, self.game(config), self.state/"weapon-previews", skip=skip, skip_categories=skip_categories, progress=self.progress, missing_only=missing_only)
        except (OSError, ValueError, RuntimeError) as error:
            self.progress(None, f"Optional catalog previews unavailable: {error}")
            return {"status":"unavailable", "errors":[{"reason":str(error)}]}

    def launch(self, config, *, skip_previews=False, skip_preview_categories=(), quick_launch=False, missing_previews_only=False):
        if not self.allow_launch: raise ValueError("Launch authority is required")
        from allin1.health import scan_launch_hazards, consume_rpf_canary
        from allin1.game_launcher import launch_gta, observe_gta_launch
        from allin1.runtime_diagnostic_session import RuntimeSession
        from allin1.garage_map_detection import refresh_garage_map_detection
        from allin1.reactor_bootstrap import inspect_reactor_installation, start_reactor_preloader, ReactorStartupMonitor
        game = self.game(config)
        checkpoint()
        self.progress(None, "Checking launch safety and enabled packages")
        hazards = [i.message for i in scan_launch_hazards(game) if i.severity == "error"]
        if hazards: raise ValueError("Launch blocked: " + "; ".join(hazards))
        checkpoint()
        self.manager.save_config(config)
        checkpoint()
        if quick_launch:
            self.progress(None, "Quick Launch: keeping existing artwork; skipping preview discovery and rendering")
            previews = {"status": "skipped", "reason": "quick_launch", "rendered": 0, "cached": 0, "pending": 0, "categories": {}}
        else:
            previews = self.prepare_previews(config, skip=skip_previews, skip_categories=skip_preview_categories, missing_only=missing_previews_only)
        checkpoint()
        self.progress(None, "Checking garage map data")
        try: refresh_garage_map_detection(game)
        except (OSError, RuntimeError, ValueError) as error: self.progress(None, f"Garage map refresh: {error}")
        checkpoint()
        self.progress(None, "Preparing Reactor startup monitoring")
        installation = inspect_reactor_installation(game)
        self.startup_monitor = ReactorStartupMonitor(game) if installation.available else None
        preloader = None
        trace = None
        def record(kind, data):
            if trace is not None:
                try: trace.event(kind, data)
                except (OSError, ValueError) as error: self.progress(None, f"Runtime diagnostic recording unavailable: {error}")
        def pending(item):
            self.progress(None, item.message)
            record("launch_observation", serializable(item))
            # Bind the first observable game process, not only a stable launch.
            # The observer can then correlate crashes during the startup window.
            if trace is not None and trace.process is None and item.process_id is not None:
                try:
                    if trace.observe(item.process_id): trace.watch(item.process_id)
                except (OSError,ValueError,KeyError,TypeError,RuntimeError) as error:
                    record("observer_error",{"reason":str(error)[:300]})
        try:
            preloader = start_reactor_preloader(game, installation=installation)
            checkpoint()
            try:
                trace = RuntimeSession(game, self.state)
                self.diagnostic_session = trace
            except (OSError, ValueError) as error:
                self.progress(None, f"Runtime diagnostic capture unavailable: {error}")
            commit_dispatch()
            self.progress(None, "Requesting GTA launch — launch preparation is complete")
            target = launch_gta(game)
            self.launch_target = target
            if self.startup_monitor: self.startup_monitor.mark_launch_requested()
            consume_rpf_canary(game, "allin1_smoke")
            self.progress(None, f"Waiting for {target.description}")
            observation = observe_gta_launch(target, on_pending=pending)
            record("launch_observation", serializable(observation))
            if observation.status != "success": raise RuntimeError(observation.message)
            if trace is not None and observation.process_id is not None:
                try:
                    if trace.observe(observation.process_id): trace.watch(observation.process_id)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    record("observer_error", {"reason":str(error)[:300]})
            return {**serializable(observation), "startup_monitoring": self.startup_monitor is not None,
                "catalog_previews": previews, "weapon_previews": previews.get("categories", {}).get("weapons", previews),
                "diagnostic_session_id":trace.value["session_id"] if trace else None,
                "diagnostic_session_path":str(trace.path) if trace else None}
        except Exception as error:
            if trace is not None:
                trace.value["status"] = "launch_cancelled" if isinstance(error, LaunchCancelled) else "launch_failed"
                record("session_end", {"reason":str(error)[:500],"crash_cause":"not_established"})
                trace.stop.set()
            self.startup_monitor = None
            if preloader is not None: preloader.stop()
            raise
