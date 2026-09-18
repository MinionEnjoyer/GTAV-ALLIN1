"""Isolated native-service fixture for React tests. Never uses real game paths."""
from pathlib import Path
import importlib.abc
import json
import os
import socket
import shutil
import sys
import tempfile

class NoTk(importlib.abc.MetaPathFinder):
    """A React workflow may not fall back to the legacy presentation layer."""
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"tkinter", "_tkinter"}:
            raise AssertionError("React fixture imported Tkinter: " + fullname)

sys.meta_path.insert(0, NoTk())

project_source = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_source / "src"))
from allin1.config import Config
from allin1.desktop_host import serve
from allin1.desktop_service import LauncherService
from allin1.extensions import ExtensionManifest, ExtensionRegistry


def main():
    root = Path(sys.argv[1]).resolve()
    if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not root.name.startswith("allin1-react-test-"):
        raise ValueError("React fixture requires an isolated temporary directory")
    if list(root.iterdir()): raise ValueError("React fixture root must be empty")
    project = root / "project"; (project / "data").mkdir(parents=True)
    for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        os.environ[key] = str(root / "isolated-user" / key)
    def no_network(*_args, **_kwargs):
        raise AssertionError("React fixture attempted a network connection")
    socket.socket.connect = no_network
    socket.create_connection = no_network
    from allin1 import detector, manager
    detector._project_root = lambda: project
    manager.detect_gta_path = lambda: None  # Never scan this host's real games.
    for name in ("vehicles.toml", "weapons.toml"):
        shutil.copy2(project_source / "data" / name, project / "data" / name)
    game = root / "Synthetic game with spaces"; (game / "scripts").mkdir(parents=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"nonexecutable test fixture")
    config = Config.default(); config.general.gta_enhanced_path = str(game); config.general.target_edition = "enhanced"
    config.save(project / "config.toml")
    # This test-only built-in preserves generic Content settings coverage after
    # the retired Experimental Gameplay package left the shipped catalog.
    descriptor = project / "content/test-fixture/allin1.content.json"
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text(json.dumps({
        "schema_version": 1,
        "api_version": 1,
        "id": "test.fixture-content",
        "name": "Synthetic Content Fixture",
        "version": "1.0.0",
        "description": "Non-shipping React content-settings fixture.",
        "capabilities": ["launcher.settings"],
        "systems": [{
            "id": "fixture-settings",
            "name": "Fixture Settings",
            "category": "Testing",
            "experimental": False,
            "enabled_by_default": False,
            "settings": [{
                "key": "enabled",
                "label": "Fixture enabled",
                "type": "boolean",
                "default": True,
                "config_key": "script.enable_logging",
            }],
        }],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    }, indent=2) + "\n", encoding="utf-8")
    ExtensionRegistry(game).register_builtin(ExtensionManifest.load(descriptor))
    online = project / "content/allin1-online-content/allin1.content.json"
    online.parent.mkdir(parents=True)
    shutil.copy2(project_source / "content/allin1-online-content/allin1.content.json", online)
    from test_sdk_tauri_installation import archive, tauri_payload
    archive(project / "SDK-fixture.zip", tauri_payload())
    package = project / "mods/catalog/react-fixture"; package.mkdir(parents=True)
    (package / "payload.ini").write_text("fixture = true")
    (package / "mod.toml").write_text('schema_version = 1\nid = "react-fixture"\nname = "React fixture"\nversion = "1.0.0"\ntype = "script"\neditions = ["enhanced"]\n[[files]]\nsource = "payload.ini"\ndestination = "scripts/react-fixture.ini"\n')
    from test_extensions import _content_package
    from test_component_bundles import write_bundle
    write_bundle(project / "component-fixture")
    _content_package(project / "mods/catalog", "acme.react-content", runtime=False)
    shutil.copytree(project_source / "sdk/examples", project / "sdk/examples")
    from test_assistant_manager import _write_package, _hardware
    from allin1 import assistant_manager
    _write_package(project / "assistant-fixture.zip")
    # Deterministic hardware evidence for a tiny nonexecutable test pack. No
    # production network download or real runtime is ever used by this fixture.
    assistant_manager.assess_assistant_hardware = lambda *a, **k: assistant_manager.AssistantHardwareReport(
        "low", True, "low", 8, 12, 1, (), (), _hardware())
    from allin1 import versioning
    versioning.fetch_latest_release = lambda: versioning.ReleaseInfo("0.6.7", "https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/latest", True, "Synthetic next release")
    service = LauncherService(project, root / "state", allow_game_writes=True)
    service.require_closed = lambda: None  # No executable or process exists in this isolated fixture.
    serve(service, sys.stdin, sys.stdout)


if __name__ == "__main__": main()
