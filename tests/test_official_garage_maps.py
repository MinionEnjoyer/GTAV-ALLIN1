"""Repository contracts for the SDK-authored built-in garage descriptors."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP_ROOT = ROOT / "data" / "maps" / "allin1-online-content"

EXPECTED_GARAGES = {
    "eclipse-garage": ("eclipse", 10),
    "harmony-garage": ("three_floor", 25),
    "davis-auto-shop": ("davis", 10),
    "garment-factory-garage": ("garment_factory", 10),
    "grapeseed-garage": ("rural", 6),
    "paleto-garage": ("paleto", 10),
}

EXPECTED_IPLS = {
    "eclipse-garage": [],
    "harmony-garage": [
        "ba_int_placement_ba_interior_1_dlc_int_02_ba_milo_",
    ],
    "davis-auto-shop": [
        "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_",
    ],
    "garment-factory-garage": [
        "m24_2_int_placement",
        "m24_2_int_placement_interior_int_hacker_garage_milo_",
    ],
    "grapeseed-garage": [
        "hei_hw1_blimp_interior_v_garagem_milo_",
    ],
    "paleto-garage": ["vw_casino_garage"],
}


def _projects() -> dict[str, dict]:
    projects: dict[str, dict] = {}
    for path in sorted(MAP_ROOT.glob("*.maps.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["id"] not in projects
        projects[payload["id"]] = payload
    return projects


def test_every_land_garage_has_one_portable_sdk_descriptor() -> None:
    projects = _projects()
    assert set(projects) == set(EXPECTED_GARAGES)

    for project_id, (garage_id, capacity) in EXPECTED_GARAGES.items():
        project = projects[project_id]
        assert project["schema_version"] == 1
        assert project["package_id"] == "allin1.online-content"
        if project_id == "grapeseed-garage":
            assert project["editions"] == ["enhanced"]
        else:
            assert project["editions"] == ["legacy", "enhanced"]
        assert len(project["garages"]) == 1

        garage = project["garages"][0]
        assert garage["id"] == garage_id
        assert garage["capacity"] == capacity
        assert garage["vehicle_types"] == ["land"]
        assert len(garage["slots"]) == capacity
        assert len({slot["id"] for slot in garage["slots"]}) == capacity
        assert garage["rules"] == {
            "allow_store": True,
            "allow_retrieve": True,
            "save_policy": "story_save_only",
        }

        portal_ids = {portal["id"] for portal in project["portals"]}
        assert garage["entrance_portal_id"] in portal_ids
        assert {portal["mode"] for portal in project["portals"]} >= {
            "vehicle",
            "ped",
        }


def test_only_base_game_eclipse_skips_ipl_streaming() -> None:
    projects = _projects()
    for project_id, project in projects.items():
        streaming = project["streaming"]
        level_ipls = [
            ipl
            for level in project["levels"]
            for ipl in level.get("ipls", [])
        ]
        if project_id == "eclipse-garage":
            assert streaming["mode"] == "none"
            assert streaming["content_group"] is None
            assert streaming["ipls"] == []
            assert level_ipls == []
        else:
            assert streaming["mode"] == "ipl"
            assert streaming["ipls"] or level_ipls
        assert streaming["ipls"] == EXPECTED_IPLS[project_id]
        assert level_ipls == EXPECTED_IPLS[project_id]


def test_grapeseed_declares_its_supported_residency_semantics() -> None:
    grapeseed = _projects()["grapeseed-garage"]
    assert grapeseed["editions"] == ["enhanced"]
    assert grapeseed["streaming"]["keep_resident"] is True
    assert "activation_radius" not in grapeseed["streaming"]
    assert "release_radius" not in grapeseed["streaming"]


def test_online_content_declares_world_map_ownership() -> None:
    manifest = json.loads(
        (
            ROOT
            / "content"
            / "allin1-online-content"
            / "allin1.content.json"
        ).read_text(encoding="utf-8")
    )
    assert "world.maps" in manifest["capabilities"]
