"""Standalone package and launcher lifecycle coverage for Suppressors Enhanced."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree

from allin1.extensions import ExtensionRegistry
from allin1.gui import ManagerWindow
from allin1.mods import ModIntegrationService, ModManifest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "mods" / "realistic-suppressors"
PACKAGE_ID = "realistic-suppressors"
HEAT_DLC = PACKAGE / "payload" / "rs_suppressor_heat" / "dlc.rpf"
HEAT_ASSET_MANIFEST = (
    PACKAGE / "payload" / "rs_suppressor_heat" / "asset-manifest.json"
)
STANDALONE = PACKAGE / "standalone"
STANDALONE_DLL = STANDALONE / "payload" / "RealisticSuppressors.dll"
STANDALONE_OIV = (
    STANDALONE / "dist" / "Suppressors-Enhanced-Standalone-1.1.0.oiv"
)
SUPERSEDED_STANDALONE_OIV = (
    STANDALONE / "dist" / "RealisticSuppressors-Standalone-1.1.0.oiv"
)
RELEASE_DIST = PACKAGE / "dist"
ALLIN1_RELEASE = RELEASE_DIST / "Suppressors-Enhanced-ALLIN1-1.1.0.zip"
STANDALONE_RELEASE = (
    RELEASE_DIST / "Suppressors-Enhanced-Standalone-1.1.0.oiv"
)
COMBINED_RELEASE = (
    RELEASE_DIST / "Suppressors-Enhanced-1.1.0-Release.zip"
)
MANAGED_DESTINATIONS = {
    "scripts/RealisticSuppressors/RealisticSuppressors.dll",
    "scripts/RealisticSuppressors/allin1.content.json",
    "mods/update/x64/dlcpacks/rs_suppressor_heat/dlc.rpf",
}


def _write_pe(path: Path) -> None:
    payload = bytearray(4096)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _game(tmp_path: Path, edition: str) -> Path:
    game = tmp_path / edition
    game.mkdir()
    executable = "GTA5.exe" if edition == "legacy" else "GTA5_Enhanced.exe"
    (game / executable).write_bytes(b"synthetic GTA V executable")
    _write_pe(game / "ScriptHookVDotNet.asi")
    if edition == "enhanced":
        _write_pe(game / "OpenRPF.asi")
        _write_pe(game / "xinput1_4.dll")
    return game


def _installed_paths(game: Path) -> dict[str, Path]:
    return {
        destination: game / Path(destination)
        for destination in MANAGED_DESTINATIONS
    }


def test_realistic_suppressors_is_a_standalone_schema_v2_package() -> None:
    manifest = ModManifest.load(PACKAGE)

    assert manifest.mod_id == PACKAGE_ID
    assert manifest.name == "Suppressors Enhanced"
    assert manifest.version == "1.1.0"
    assert manifest.mod_type == "mixed"
    assert manifest.editions == ("enhanced",)
    assert manifest.dependencies == ("shvdn", "openrpf")
    assert manifest.dlc_packs == ("rs_suppressor_heat",)
    assert manifest.conflicts == ()
    assert manifest.package_requirements == ()
    assert {
        item.destination.as_posix() for item in manifest.files
    } == MANAGED_DESTINATIONS
    assert sum(
        item.destination.as_posix().startswith("scripts/RealisticSuppressors/")
        for item in manifest.files
    ) == 2
    assert all(
        item.destination.as_posix().casefold() != "scripts/allin1.dll"
        for item in manifest.files
    )

    extension = manifest.extension
    assert extension is not None
    assert extension.extension_id == PACKAGE_ID
    assert set(extension.capabilities) == {
        "launcher.settings",
        "story-save.transactions",
        "weapon.components.lifecycle",
    }


    assert [assembly.path.as_posix() for assembly in extension.runtime_assemblies] == [
        "scripts/RealisticSuppressors/RealisticSuppressors.dll"
    ]
    assert extension.runtime_assemblies[0].entry_point == (
        "RealisticSuppressors.RealisticSuppressorController"
    )

    stealth = extension.setting("realistic_suppressors")
    assert stealth.setting_type == "boolean"
    assert stealth.default is True
    assert stealth.config_key is None

    breakage = extension.setting("suppressor_breakage")
    assert breakage.setting_type == "boolean"
    assert breakage.default is True
    assert breakage.config_key is None

    durability = extension.setting("suppressor_durability_scale")
    assert durability.setting_type == "number"
    assert durability.default == 1.0
    assert durability.minimum == 0.5
    assert durability.maximum == 3.0
    assert durability.step == 0.25
    assert durability.config_key is None

    heat_smoke = extension.setting("suppressor_heat_smoke")
    assert heat_smoke.label == "Suppressor heat smoke"
    assert heat_smoke.setting_type == "boolean"
    assert heat_smoke.default is True
    assert heat_smoke.group == "Visuals"
    assert heat_smoke.config_key is None

    smoke_intensity = extension.setting("suppressor_smoke_intensity")
    assert smoke_intensity.label == "Heat smoke intensity"
    assert smoke_intensity.setting_type == "number"
    assert smoke_intensity.default == 1.0
    assert smoke_intensity.minimum == 0.5
    assert smoke_intensity.maximum == 2.0
    assert smoke_intensity.step == 0.25
    assert smoke_intensity.group == "Visuals"
    assert smoke_intensity.config_key is None

    temperature_debug = extension.setting("suppressor_temperature_debug")
    assert temperature_debug.label == "Temperature debug"
    assert temperature_debug.setting_type == "boolean"
    assert temperature_debug.default is False
    assert temperature_debug.group == "Diagnostics"
    assert temperature_debug.config_key is None

    builtin_descriptor = (
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    ).read_text(encoding="utf-8")
    assert "realistic_suppressors" not in builtin_descriptor
    assert "suppressor_breakage" not in builtin_descriptor
    assert not (ROOT / "script" / "src" / "RealisticSuppressorController.cs").exists()


def test_realistic_suppressors_declares_complete_workbench_relationships() -> None:
    manifest = ModManifest.load(PACKAGE)
    extension = manifest.extension
    assert extension is not None
    assert len(extension.workbench_weapon_enhancements) == 1

    enhancement = extension.workbench_weapon_enhancements[0]
    assert enhancement.enhancement_id == (
        "realistic-suppressors.thermal-components"
    )
    assert enhancement.mode == "scripted_vanilla_components"
    assert enhancement.script_entry_points == (
        "RealisticSuppressors.RealisticSuppressorController",
    )

    component_names = {
        "0x837445AA": "COMPONENT_AT_AR_SUPP",
        "0xA73D4664": "COMPONENT_AT_AR_SUPP_02",
        "0xC304849A": "COMPONENT_AT_PI_SUPP",
        "0x65EA7EBB": "COMPONENT_AT_PI_SUPP_02",
        "0xE608B35E": "COMPONENT_AT_SR_SUPP",
        "0xAC42DF71": "COMPONENT_AT_SR_SUPP_03",
        "0x9307D6FA": "COMPONENT_CERAMICPISTOL_SUPP",
        "0x1E02B7E0": "COMPONENT_WM29_PISTOL_SUPP",
    }
    authored = {
        (link.weapon_name, link.weapon_hash): (
            link.component_name, link.component_hash,
        )
        for link in enhancement.weapon_components
    }
    assert len(authored) == 39
    assert {
        link.component_hash: link.component_name
        for link in enhancement.weapon_components
    } == component_names

    policy = (PACKAGE / "src" / "SuppressorThermalPolicy.cs").read_text(
        encoding="utf-8"
    )
    profiled = {
        (match.group("weapon"), f'0x{match.group("weapon_hash")}'): (
            component_names[f'0x{match.group("component_hash")}'],
            f'0x{match.group("component_hash")}',
        )
        for match in re.finditer(
            r'P\("(?P<weapon>WEAPON_[A-Z0-9_]+)",\s*'
            r'0x(?P<weapon_hash>[0-9A-F]{8}),\s*'
            r'0x(?P<component_hash>[0-9A-F]{8})',
            policy,
        )
    }
    assert authored == profiled

    assert len(enhancement.visual_assets) == 1
    progression = enhancement.visual_assets[0]
    assert progression.dlc_pack == "rs_suppressor_heat"
    assert progression.archive == "x64/models/cdimages/rs_suppressor_heat.rpf"
    assert progression.families == ("ar", "ar02", "pi", "sr", "sr03")
    assert progression.levels == 24
    assert progression.model_pattern == (
        "rs_suppressor_heat_{family}_{level:02d}.ydr"
    )
    assert progression.base_model_pattern == "rs_suppressor_heat_{family}.ydr"
    assert progression.texture_dictionary == "rs_suppressor_heat.ytd"
    assert progression.texture_pattern == (
        "rs_suppressor_heat_gradient_{level:02d}"
    )
    assert progression.archetype_dictionary == "rs_suppressor_heat.ytyp"
    assert progression.base_level_uses_unsuffixed is True


def test_launcher_independent_build_and_oiv_are_separate_and_complete() -> None:
    project = (PACKAGE / "RealisticSuppressors.csproj").read_text(
        encoding="utf-8"
    )
    controller = (
        PACKAGE / "src" / "RealisticSuppressorController.cs"
    ).read_text(encoding="utf-8")

    assert "<StandaloneBuild" in project
    assert "ALLIN1_HOST" in project
    assert "STANDALONE_RUNTIME" in project
    assert "'$(StandaloneBuild)' != 'true'" in project
    assert "#if ALLIN1_HOST" in controller
    assert '"runtime_mode", "standalone"' in controller
    assert "TryCommitStandaloneState" in controller

    assert STANDALONE_DLL.is_file()
    assert STANDALONE_DLL.read_bytes() != (
        PACKAGE / "payload" / "RealisticSuppressors.dll"
    ).read_bytes()
    assert STANDALONE_OIV.is_file()
    assert not SUPERSEDED_STANDALONE_OIV.exists()

    with zipfile.ZipFile(STANDALONE_OIV) as package:
        names = set(package.namelist())
        assembly = ElementTree.fromstring(package.read("assembly.xml"))
        adds = {
            (node.attrib["source"], (node.text or "").strip())
            for node in assembly.findall("./content/add")
        }
        assert assembly.findtext("./metadata/gameversion") == "Enhanced"
        assert assembly.findtext("./metadata/name") == (
            "Suppressors Enhanced — Standalone"
        )
        assert assembly.findtext("./metadata/author/displayName") == (
            "MinionEnjoyer"
        )
        assert assembly.findtext("./metadata/version/tag") == "1.1.0"
        assert adds == {
            (
                "scripts/RealisticSuppressors/RealisticSuppressors.dll",
                "scripts/RealisticSuppressors/RealisticSuppressors.dll",
            ),
            (
                "scripts/RealisticSuppressors/RealisticSuppressors.ini.example",
                "scripts/RealisticSuppressors/RealisticSuppressors.ini.example",
            ),
            (
                "mods/update/x64/dlcpacks/rs_suppressor_heat/dlc.rpf",
                "mods/update/x64/dlcpacks/rs_suppressor_heat/dlc.rpf",
            ),
        }
        registration = assembly.find(
            "./content/archive/xml/add/Item"
        )
        assert registration is not None
        assert registration.text == "dlcpacks:/rs_suppressor_heat/"
        assert (
            assembly.find("./content/archive/xml/add").attrib["xpath"]
            == "/SMandatoryPacksData/Paths"
        )
        dll_entry = (
            "content/scripts/RealisticSuppressors/RealisticSuppressors.dll"
        )
        dlc_entry = (
            "content/mods/update/x64/dlcpacks/rs_suppressor_heat/dlc.rpf"
        )
        assert {"assembly.xml", dll_entry, dlc_entry}.issubset(names)
        assert package.read(dll_entry) == STANDALONE_DLL.read_bytes()
        assert package.read(dlc_entry) == HEAT_DLC.read_bytes()


def test_public_release_archives_are_clean_credited_and_self_describing() -> None:
    credits = (PACKAGE / "CREDITS.md").read_text(encoding="utf-8")
    project = (PACKAGE / "RealisticSuppressors.csproj").read_text(
        encoding="utf-8"
    )
    assert "Creator and maintainer:** MinionEnjoyer" in credits
    assert "<Authors>MinionEnjoyer</Authors>" in project
    assert "<Company>MinionEnjoyer</Company>" in project
    assert "GPL-3.0-or-later" in project

    with zipfile.ZipFile(ALLIN1_RELEASE) as package:
        assert set(package.namelist()) == {
            "mod.toml",
            "allin1.content.json",
            "README.md",
            "CREDITS.md",
            "LICENSE.txt",
            "payload/RealisticSuppressors.dll",
            "payload/rs_suppressor_heat/dlc.rpf",
        }
        assert b"MinionEnjoyer" in package.read("CREDITS.md")
        assert package.read("payload/RealisticSuppressors.dll") == (
            PACKAGE / "payload" / "RealisticSuppressors.dll"
        ).read_bytes()
        assert package.read("payload/rs_suppressor_heat/dlc.rpf") == (
            HEAT_DLC.read_bytes()
        )

    assert STANDALONE_RELEASE.read_bytes() == STANDALONE_OIV.read_bytes()
    with zipfile.ZipFile(STANDALONE_RELEASE) as package:
        names = set(package.namelist())
        assert {"CREDITS.md", "LICENSE.txt", "README-Standalone.md"}.issubset(
            names
        )
        assert b"MinionEnjoyer" in package.read("CREDITS.md")

    with zipfile.ZipFile(COMBINED_RELEASE) as package:
        assert set(package.namelist()) == {
            "README.md",
            "CREDITS.md",
            "LICENSE.txt",
            "SHA256SUMS.txt",
            "Suppressors-Enhanced-Cover.png",
            ALLIN1_RELEASE.name,
            STANDALONE_RELEASE.name,
        }
        assert package.read(ALLIN1_RELEASE.name) == ALLIN1_RELEASE.read_bytes()
        assert package.read(STANDALONE_RELEASE.name) == (
            STANDALONE_RELEASE.read_bytes()
        )

    forbidden_fragments = {
        ".csproj",
        ".pdb",
        ".log",
        "/src/",
        "/tests/",
        "asset-manifest.json",
        "build-releasepackage.ps1",
        "build-standalonepackage.ps1",
    }
    for archive in (ALLIN1_RELEASE, STANDALONE_RELEASE, COMBINED_RELEASE):
        with zipfile.ZipFile(archive) as package:
            normalized = "\n".join(package.namelist()).casefold()
        assert not any(fragment in normalized for fragment in forbidden_fragments)

    expected = {}
    for line in (RELEASE_DIST / "SHA256SUMS.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    for archive in (ALLIN1_RELEASE, STANDALONE_RELEASE, COMBINED_RELEASE):
        assert expected[archive.name] == hashlib.sha256(
            archive.read_bytes()
        ).hexdigest().upper()


def test_allin1_release_archive_installs_and_uninstalls_cleanly(
    tmp_path: Path, monkeypatch,
) -> None:
    extracted = tmp_path / "package"
    with zipfile.ZipFile(ALLIN1_RELEASE) as package:
        package.extractall(extracted)

    manifest = ModManifest.load(extracted)
    assert manifest.mod_id == PACKAGE_ID
    assert manifest.name == "Suppressors Enhanced"

    game = _game(tmp_path, "enhanced")
    service = ModIntegrationService(game)
    registrations: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        service,
        "_set_dlc_registration",
        lambda pack, enabled: registrations.append((pack, enabled)) or True,
    )

    status = service.install(manifest)
    assert status.installed is True
    assert status.enabled is True
    for destination, target in _installed_paths(game).items():
        source = extracted / next(
            item.source
            for item in manifest.files
            if item.destination.as_posix() == destination
        )
        assert target.read_bytes() == source.read_bytes()

    service.uninstall(PACKAGE_ID)
    assert not any(path.exists() for path in _installed_paths(game).values())
    assert registrations == [
        ("rs_suppressor_heat", True),
        ("rs_suppressor_heat", False),
    ]


def test_glow_renderer_is_a_bone_attached_asset_not_world_geometry() -> None:
    controller = (PACKAGE / "src" / "RealisticSuppressorController.cs").read_text(
        encoding="utf-8"
    )

    assert "World.DrawMarker" not in controller
    assert "MarkerType.DebugSphere" not in controller
    assert "DrawLightWithRange" not in controller
    assert "Notification.Show" not in controller
    assert "Screen.ShowSubtitle" not in controller
    assert "Hash.DRAW_POLY" not in controller
    assert "World.CreatePropNoOffset" in controller
    assert "overlay.AttachTo" in controller
    assert '"bone_attached_steady_material_overlay"' in controller
    assert "SET_ENTITY_FLAG_SUPPRESS_SHADOW" in controller
    assert '"suppressor_temperature_debug", false' in controller
    assert "BEGIN_TEXT_COMMAND_DISPLAY_TEXT" in controller


def test_heat_smoke_is_bone_attached_scaled_rate_limited_and_cleaned_up() -> None:
    controller = (PACKAGE / "src" / "RealisticSuppressorController.cs").read_text(
        encoding="utf-8"
    )

    assert '"suppressor_heat_smoke", true' in controller
    assert '"suppressor_smoke_intensity", 1d' in controller
    assert '"muz_smoking_barrel"' in controller
    assert "Hash.START_PARTICLE_FX_LOOPED_ON_ENTITY_BONE" in controller
    assert "Hash.SET_PARTICLE_FX_LOOPED_SCALE" in controller
    assert "Hash.SET_PARTICLE_FX_LOOPED_ALPHA" in controller
    assert "Hash.STOP_PARTICLE_FX_LOOPED" in controller
    assert "SmokeStartRetryMs = 750" in controller
    assert "SmokeVisualUpdateMs = 125" in controller
    assert "bone_attached_looped_particle" in controller
    assert controller.count("DestroySuppressorSmoke();") >= 10

    smoke_start = controller.index("private static int StartSuppressorSmokeEmitter")
    smoke_end = controller.index("private bool TryGetSuppressorAttachment", smoke_start)
    smoke_section = controller[smoke_start:smoke_end]
    stop_start = smoke_section.index(
        "private static void StopSuppressorSmokeEmitter"
    )
    destroy_start = smoke_section.index(
        "private void DestroySuppressorSmoke", stop_start
    )
    stop_section = smoke_section[stop_start:destroy_start]
    destroy_section = smoke_section[destroy_start:]
    # A positive loop handle must never be abandoned because a cosmetic
    # colour or existence query failed. Cleanup stops first and clears each
    # stored handle only after that native returns successfully.
    assert "catch (Exception)" in smoke_section
    assert "SmokeEmitterExists" not in stop_section
    assert destroy_section.index(
        "StopSuppressorSmokeEmitter(_primaryHeatSmokeHandle);"
    ) < destroy_section.index("_primaryHeatSmokeHandle = 0;")
    assert destroy_section.index(
        "StopSuppressorSmokeEmitter(_secondaryHeatSmokeHandle);"
    ) < destroy_section.index("_secondaryHeatSmokeHandle = 0;")
    smoke_render_start = controller.index(
        "private void RenderSuppressorSmoke"
    )
    identity_reset = controller.index(
        "if (!identityMatches)", smoke_render_start
    )
    cleanup_retry_guard = controller.index(
        "if (_primaryHeatSmokeHandle > 0 ||", identity_reset
    )
    assert controller.index(
        "DestroySuppressorSmoke();", identity_reset
    ) < cleanup_retry_guard < controller.index(
        "_primaryHeatSmokeHandle = StartSuppressorSmokeEmitter(",
        cleanup_retry_guard,
    )
    harmful_natives = {
        "ADD_EXPLOSION",
        "SHOOT_SINGLE_BULLET",
        "APPLY_DAMAGE",
        "APPLY_FORCE_TO_ENTITY",
    }
    assert not harmful_natives.intersection(smoke_section)


def test_heat_asset_is_the_validated_outward_facing_tarkov_style_build() -> None:
    asset = json.loads(HEAT_ASSET_MANIFEST.read_text(encoding="utf-8"))
    payload = HEAT_DLC.read_bytes()

    assert asset["edition"] == "enhanced"
    assert asset["dlc_size"] == len(payload) == 1_805_824
    assert asset["dlc_sha256"] == hashlib.sha256(payload).hexdigest()
    assert asset["geometry"] == {
        "radial_segments": 64,
        "axial_rings": 17,
        "vertices_per_model": 1105,
        "indices_per_model": 6144,
        "triangle_order": ["a", "c", "b", "c", "d", "b"],
        "first_triangle": [0, 1, 65],
        "face_orientation": "outward",
        "radial_cross_dot": "positive",
    }
    assert asset["gradient"] == {
        "end_rgba_at_level_24": [101, 11, 1, 56],
        "center_rgba_at_level_24": [255, 150, 28, 255],
        "shape": "center_first_diffusion",
        "texture_levels": 24,
        "tier_texture_samples": [
            {
                "level": 1,
                "center_rgba": [7, 0, 0, 1],
                "emissive_multiplier": 0.0045044404,
            },
            {
                "level": 6,
                "center_rgba": [54, 2, 0, 20],
                "emissive_multiplier": 0.09473228,
            },
            {
                "level": 12,
                "center_rgba": [117, 16, 1, 72],
                "emissive_multiplier": 0.3077861,
            },
            {
                "level": 18,
                "center_rgba": [185, 60, 7, 151],
                "emissive_multiplier": 0.6132028,
            },
            {
                "level": 24,
                "center_rgba": [255, 150, 28, 255],
                "emissive_multiplier": 1.0,
            },
        ],
        "opacity_curve": {
            "type": "quadratic_ease_in",
            "formula": "round(255 * intensity^2)",
            "samples": [
                {"intensity": 0.00, "opacity": 0},
                {"intensity": 0.10, "opacity": 3},
                {"intensity": 0.25, "opacity": 16},
                {"intensity": 0.50, "opacity": 64},
                {"intensity": 0.75, "opacity": 143},
                {"intensity": 0.90, "opacity": 207},
                {"intensity": 1.00, "opacity": 255},
            ],
        },
        "runtime_fade": {
            "fade_in_half_life_seconds": 4.0,
            "fade_out_half_life_seconds": 6.0,
            "material_levels": 24,
            "material_level_hysteresis": 0.65,
            "entity_alpha": 255,
            "brightness_driver": (
                "steady_authored_emissive_multiplier_and_tier_texture"
            ),
            "temporal_dithering": False,
        },
    }
    assert asset["archive_model_count"] == 120
    assert set(asset["models"]) == {
        "rs_suppressor_heat_ar",
        "rs_suppressor_heat_ar02",
        "rs_suppressor_heat_pi",
        "rs_suppressor_heat_sr",
        "rs_suppressor_heat_sr03",
    }


def test_break_effect_is_one_shot_cosmetic_and_precedes_component_removal() -> None:
    controller = (PACKAGE / "src" / "RealisticSuppressorController.cs").read_text(
        encoding="utf-8"
    )
    start = controller.index("private void EnsureBrokenSuppressorRemoved")
    end = controller.index("private static void DeactivateCurrentSuppressorComponent", start)
    break_section = controller[start:end]

    assert break_section.index("state.BreakEventLogged = true") < (
        break_section.index("TryEmitSuppressorBreakEffect")
    )
    assert break_section.index("TryEmitSuppressorBreakEffect") < (
        break_section.index("Hash.REMOVE_WEAPON_COMPONENT_FROM_PED")
    )
    assert break_section.index("Hash.REMOVE_WEAPON_COMPONENT_FROM_PED") < (
        break_section.index("DestroyHeatOverlay();")
    )
    assert "Hash.START_PARTICLE_FX_NON_LOOPED_AT_COORD" in break_section
    assert '"bul_carmetal"' in controller
    assert "Hash.START_PARTICLE_FX_NON_LOOPED_ON_ENTITY_BONE" not in controller
    assert "Hash.PLAY_SOUND_FROM_COORD" in break_section
    assert '"Drill_Pin_Break"' in controller

    harmful_natives = {
        "ADD_EXPLOSION",
        "ADD_OWNED_EXPLOSION",
        "ADD_EXPLOSION_WITH_USER_VFX",
        "SHOOT_SINGLE_BULLET",
        "APPLY_DAMAGE",
        "APPLY_FORCE_TO_ENTITY",
    }
    for native in harmful_natives:
        assert native not in controller


def test_launcher_round_trip_preserves_core_and_unowned_files(
    tmp_path: Path, monkeypatch,
) -> None:
    edition = "enhanced"
    game = _game(tmp_path, edition)
    scripts = game / "scripts"
    package_runtime = scripts / "RealisticSuppressors"
    package_runtime.mkdir(parents=True)

    sentinels = {
        scripts / "ALLIN1.dll": b"ALLIN1 core sentinel",
        scripts / "OtherMod.dll": b"unrelated mod sentinel",
        package_runtime / "runtime-state.json": b'{"condition":"retained"}',
    }
    for path, payload in sentinels.items():
        path.write_bytes(payload)

    manifest = ModManifest.load(PACKAGE)
    service = ModIntegrationService(game)
    registrations: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        service,
        "_set_dlc_registration",
        lambda pack, enabled: registrations.append((pack, enabled)) or True,
    )
    installed = service.install(manifest)
    targets = _installed_paths(game)

    assert installed.installed is True
    assert installed.enabled is True
    assert service.edition == edition
    assert service.list_installed() == [installed]
    source_by_destination = {
        item.destination.as_posix(): PACKAGE / Path(*item.source.parts)
        for item in manifest.files
    }
    for destination, target in targets.items():
        assert target.read_bytes() == source_by_destination[destination].read_bytes()

    receipt_path = service.state_root / f"{PACKAGE_ID}.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert receipt["id"] == PACKAGE_ID
    assert receipt["version"] == "1.1.0"
    assert receipt["type"] == "mixed"
    assert receipt["enabled"] is True
    assert receipt["dependencies"] == ["shvdn", "openrpf"]
    assert receipt["dlc_packs"] == ["rs_suppressor_heat"]
    assert receipt["owned_dlc_packs"] == ["rs_suppressor_heat"]
    assert receipt["requires"] == []
    assert receipt["extension"]["id"] == PACKAGE_ID
    assert {item["destination"] for item in receipt["files"]} == (
        MANAGED_DESTINATIONS
    )
    for item in receipt["files"]:
        source = source_by_destination[item["destination"]]
        assert item["backup"] is None
        assert item["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    registry_entry = ExtensionRegistry(game).installed()[0]
    assert registry_entry["id"] == PACKAGE_ID
    assert registry_entry["version"] == "1.1.0"
    assert registry_entry["source"] == "package"
    assert registry_entry["enabled"] is True
    assert registry_entry["settings"] == {
        "realistic_suppressors": True,
        "suppressor_breakage": True,
        "suppressor_durability_scale": 1.0,
        "suppressor_heat_smoke": True,
        "suppressor_smoke_intensity": 1.0,
        "suppressor_temperature_debug": False,
    }
    assert registry_entry["runtime_files"] == [{
        "path": "scripts/RealisticSuppressors/RealisticSuppressors.dll",
        "sha256": hashlib.sha256(
            targets[
                "scripts/RealisticSuppressors/RealisticSuppressors.dll"
            ].read_bytes()
        ).hexdigest(),
    }]
    assert all(path.read_bytes() == payload for path, payload in sentinels.items())

    registry = ExtensionRegistry(game)
    registry.set_setting(
        PACKAGE_ID, "suppressor_temperature_debug", True
    )
    assert registry.installed()[0]["settings"][
        "suppressor_temperature_debug"
    ] is True

    disabled = service.set_enabled(PACKAGE_ID, False)
    assert disabled.enabled is False
    for target in targets.values():
        assert not target.exists()
        assert target.with_name(target.name + ".disabled").is_file()
    disabled_entry = ExtensionRegistry(game).installed()[0]
    assert disabled_entry["id"] == PACKAGE_ID
    assert disabled_entry["enabled"] is False
    assert all(path.read_bytes() == payload for path, payload in sentinels.items())

    enabled = service.set_enabled(PACKAGE_ID, True)
    assert enabled.enabled is True
    for destination, target in targets.items():
        assert target.read_bytes() == source_by_destination[destination].read_bytes()
        assert not target.with_name(target.name + ".disabled").exists()
    reenabled_entry = ExtensionRegistry(game).installed()[0]
    assert reenabled_entry["enabled"] is True
    assert reenabled_entry["settings"]["suppressor_temperature_debug"] is True

    service.uninstall(PACKAGE_ID)

    assert service.list_installed() == []
    assert not receipt_path.exists()
    assert ExtensionRegistry(game).installed() == []
    for target in targets.values():
        assert not target.exists()
        assert not target.with_name(target.name + ".disabled").exists()
    assert all(path.read_bytes() == payload for path, payload in sentinels.items())
    assert package_runtime.is_dir()
    assert set(package_runtime.iterdir()) == {package_runtime / "runtime-state.json"}
    assert registrations == [
        ("rs_suppressor_heat", True),
        ("rs_suppressor_heat", False),
        ("rs_suppressor_heat", True),
        ("rs_suppressor_heat", False),
    ]


def test_launcher_gui_routes_standalone_package_lifecycle(monkeypatch) -> None:
    manifest = ModManifest.load(PACKAGE, validate_payload=False)
    service = Mock()
    window = ManagerWindow.__new__(ManagerWindow)
    window._selected_mod_id = Mock(return_value=PACKAGE_ID)
    window.builtin_package_manifests = {}
    window.builtin_package_entries = {}
    window.sdk_manifests = {}
    window.mod_manifests = {PACKAGE_ID: manifest}
    window.installed_mod_ids = {PACKAGE_ID}
    window._mod_service = Mock(return_value=service)
    window._run = Mock(side_effect=lambda _label, action: action())
    monkeypatch.setattr("allin1.gui.messagebox.askyesno", lambda *_args: True)

    window.install_selected_mod()
    window.toggle_selected_mod(False)
    window.toggle_selected_mod(True)
    window.uninstall_selected_mod()

    service.install.assert_called_once_with(manifest)
    assert service.set_enabled.call_args_list == [
        ((PACKAGE_ID, False),),
        ((PACKAGE_ID, True),),
    ]
    service.uninstall.assert_called_once_with(PACKAGE_ID)
