from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath

from allin1 import __version__

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / "allin1.workspace.json"


def _data() -> dict:
    return json.loads(DESCRIPTOR.read_text(encoding="utf-8"))


def _relative_path(value: str) -> PurePosixPath:
    assert "\\" not in value
    path = PurePosixPath(value)
    assert not path.is_absolute()
    assert path.parts
    assert all(part not in {"", ".", ".."} for part in path.parts)
    assert ":" not in path.parts[0]
    return path


def test_workspace_descriptor_maps_core_components_and_relationships() -> None:
    data = _data()
    assert data["schema_version"] == 1
    assert data["id"] == "allin1.core"
    assert data["version"] == __version__
    assert data["kind"] == "product_workspace"
    assert data["editions"] == ["legacy", "enhanced"]

    components = {item["id"]: item for item in data["components"]}
    assert len(components) == len(data["components"])
    assert {key: item["role"] for key, item in components.items()} == {
        "launcher.host": "launcher_host",
        "runtime.shared": "story_runtime",
        "content.online": "official_content_pack",
        "content.experimental": "official_content_pack",
        "tool.rpfpatcher": "build_tool",
        "example.colored-smokes": "sdk_example",
        "package.realistic-suppressors": "optional_package",
        "evidence.tests": "test_evidence",
        "evidence.docs": "documentation_evidence",
    }
    assert components["content.online"]["package_id"] == "allin1.online-content"
    assert components["content.experimental"]["package_id"] == (
        "allin1.experimental-gameplay"
    )
    assert components["runtime.shared"]["runtime_artifact"] == "scripts/ALLIN1.dll"
    assert components["runtime.shared"]["api_contract"] == (
        "data/runtime_api_contract.json"
    )
    assert components["content.online"]["package_discovery"] is False
    assert components["content.experimental"]["package_discovery"] is False
    assert components["example.colored-smokes"]["role"] == "sdk_example"
    assert components["package.realistic-suppressors"]["role"] == "optional_package"
    assert components["package.realistic-suppressors"]["package_discovery"] is True
    assert components["package.realistic-suppressors"]["paths"] == [
        "mods/realistic-suppressors",
        "mods/realistic-suppressors/mod.toml",
        "mods/realistic-suppressors/allin1.content.json",
    ]
    assert (
        ROOT / "mods/realistic-suppressors/RealisticSuppressors.csproj"
    ).is_file()
    assert (
        ROOT / "mods/realistic-suppressors/src/RealisticSuppressorController.cs"
    ).is_file()
    assert components["evidence.tests"]["package_discovery"] is False
    assert components["evidence.docs"]["package_discovery"] is False

    relationships = {
        (item["source"], item["target"], item["type"])
        for item in data["relationships"]
    }
    assert all(
        source in components and target in components
        for source, target, _relationship in relationships
    )
    assert ("content.online", "runtime.shared", "uses_shared_runtime") in relationships
    assert (
        "content.experimental", "runtime.shared", "uses_shared_runtime"
    ) in relationships
    assert (
        "example.colored-smokes", "content.online", "documents_system"
    ) in relationships

    manifests = {
        "content.online": json.loads(
            (ROOT / components["content.online"]["manifest"]).read_text(
                encoding="utf-8"
            )
        )["id"],
        "content.experimental": json.loads(
            (ROOT / components["content.experimental"]["manifest"]).read_text(
                encoding="utf-8"
            )
        )["id"],
        "example.colored-smokes": json.loads(
            (ROOT / components["example.colored-smokes"]["manifest"]).read_text(
                encoding="utf-8"
            )
        )["id"],
    }
    with (ROOT / components["package.realistic-suppressors"]["manifest"]).open(
        "rb"
    ) as stream:
        manifests["package.realistic-suppressors"] = tomllib.load(stream)["id"]
    assert manifests == {
        component_id: components[component_id]["package_id"]
        for component_id in manifests
    }

    runtime_contract = json.loads(
        (ROOT / components["runtime.shared"]["api_contract"]).read_text(
            encoding="utf-8"
        )
    )
    assert runtime_contract["schema_version"] == 1
    assert runtime_contract["api_version"] == 1
    assert runtime_contract["assembly"] == components["runtime.shared"][
        "runtime_artifact"
    ]
    assert runtime_contract["public_type"] == "ALLIN1.Allin1ExtensionApi"
    assert runtime_contract["source"] == "script/src/ExtensionRuntime.cs"
    assert {item["name"] for item in runtime_contract["symbols"]}.issuperset({
        "RegistryAvailable",
        "GetEnabledPackageIds",
        "TryGetSetting",
        "MapDescriptorDeclaration",
        "GetMapDescriptors",
        "ReloadRegistry",
        "RegisterStorySaveParticipant",
        "RegisterWeaponComponentLifecycleParticipant",
    })
    runtime_symbols = {
        item["name"]: item for item in runtime_contract["symbols"]
    }
    assert runtime_symbols["MapDescriptorDeclaration"] == {
        "name": "MapDescriptorDeclaration",
        "kind": "type",
        "capability": "world.maps",
    }
    assert runtime_symbols["GetMapDescriptors"] == {
        "name": "GetMapDescriptors",
        "kind": "method",
        "capability": "world.maps",
        "return_type": "IReadOnlyList<MapDescriptorDeclaration>",
        "parameters": [{"name": "packageId", "type": "string"}],
    }


def test_workspace_descriptor_is_data_only_and_uses_tracked_relative_allowlists() -> None:
    data = _data()
    policy = data["source_policy"]
    assert policy["inventory"] == "git_tracked_allowlist"
    assert policy["follow_symlinks"] is False
    assert policy["execute_sources"] is False

    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    tracked = {
        item for item in completed.stdout.decode("utf-8").split("\0") if item
    }

    listed = (
        list(policy["allowlisted_roots"])
        + list(policy["allowlisted_files"])
        + [
            value
            for component in data["components"]
            for value in component["paths"]
        ]
    )
    for value in listed:
        path = _relative_path(value)
        relative = path.as_posix()
        assert (ROOT / relative).exists(), relative
        assert relative in tracked or any(
            candidate.startswith(relative + "/") for candidate in tracked
        ), relative

    forbidden_roots = {
        ".artifacts", ".git", ".pytest_cache", ".tmp", ".venv",
        "build", "dist", "htmlcov", "logs", "output",
        "script/bin", "script/obj", "script/out",
        "mods/realistic-suppressors/bin",
        "mods/realistic-suppressors/obj",
        "mods/realistic-suppressors/dist",
        "mods/realistic-suppressors/standalone/bin",
        "mods/realistic-suppressors/standalone/obj",
        "mods/realistic-suppressors/standalone/dist",
        "mods/realistic-suppressors/standalone/payload",
    }
    component_paths = {
        value
        for component in data["components"]
        for value in component["paths"]
    }
    assert not component_paths.intersection(forbidden_roots)
    assert forbidden_roots.issubset(set(policy["excluded_roots"]))

    forbidden_executable_fields = {"command", "commands", "exec", "hooks"}

    def assert_data_only(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden_executable_fields.intersection(value)
            for child in value.values():
                assert_data_only(child)
        elif isinstance(value, list):
            for child in value:
                assert_data_only(child)

    assert_data_only(data)


def test_workspace_descriptor_preserves_experimental_opt_in_defaults() -> None:
    data = _data()
    components = {item["id"]: item for item in data["components"]}
    experimental = components["content.experimental"]
    smoke = components["example.colored-smokes"]
    assert experimental["experimental"] is True
    assert experimental["defaults"] == {
        "systems_enabled": False,
        "diagnostics_enabled": False,
    }
    assert smoke["experimental"] is True
    assert smoke["defaults"]["enabled"] is False

    manifest = json.loads(
        (ROOT / experimental["manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["id"] == experimental["package_id"]
    assert manifest["systems"]
    assert all(system["experimental"] is True for system in manifest["systems"])
    assert all(
        system["enabled_by_default"] is False
        for system in manifest["systems"]
    )
    assert all(
        setting["default"] is False
        for system in manifest["systems"]
        for setting in system.get("settings", [])
    )

    online = components["content.online"]
    online_manifest = json.loads(
        (ROOT / online["manifest"]).read_text(encoding="utf-8")
    )
    online_experiments = [
        system for system in online_manifest["systems"]
        if system.get("experimental", False)
    ]
    assert online["defaults"]["experimental_systems_enabled"] is False
    assert online_experiments
    assert all(
        system.get("enabled_by_default", True) is False
        for system in online_experiments
    )
    assert all(
        setting["default"] is False
        for system in online_experiments
        for setting in system.get("settings", [])
    )
