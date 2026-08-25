from __future__ import annotations

import json
from pathlib import Path

import pytest

from allin1.mods import ModManifest
from allin1.generators.story_vehicle_catalog import build_story_catalog
from allin1.vehicle_catalog import (
    MAX_VEHICLE_CATALOG_BYTES,
    MAX_VEHICLE_CATALOG_ENTRIES,
    VehicleCatalog,
    VehicleTrafficPolicy,
    vehicle_model_hash,
)


ROOT = Path(__file__).resolve().parents[1]


def _catalog(*, model: str = "examplecar", traffic: bool = False) -> dict:
    return {
        "schema_version": 1,
        "id": "example-vehicles",
        "name": "Example Vehicles",
        "vehicles": [{
            "model": model,
            "name": "Example Car",
            "manufacturer": "Example",
            "category": "sports",
            "price": 125_000,
            "storage": "garage",
            "source_pack": "examplepack",
            "size_tier": 0,
            "preview_dictionary": "example_preview",
            "preview_texture": "examplecar_card",
            "traffic": {
                "enabled": traffic,
                "weight": 1.5,
            },
        }],
    }


def _package(
    tmp_path: Path,
    *,
    catalog: dict | None = None,
    traffic_capability: bool = True,
    traffic_setting: bool = True,
    traffic_default: bool = False,
    dependency: bool = True,
    dependency_spec: str = "allin1.online-content>=0.5.5",
) -> Path:
    package = tmp_path / "example.vehicle"
    payload = package / "payload"
    payload.mkdir(parents=True)
    (payload / "dlc.rpf").write_bytes(b"RPF7 example")
    (payload / "vehicles.json").write_text(
        json.dumps(catalog or _catalog()), encoding="utf-8",
    )
    capabilities = ["gbay.catalogs"]
    if traffic_capability:
        capabilities.extend(["launcher.settings", "traffic.catalog"])
    settings = []
    if traffic_setting:
        settings.append({
            "key": "traffic_enabled",
            "label": "Allow these vehicles in ambient traffic",
            "type": "boolean",
            "default": traffic_default,
        })
    content = {
        "schema_version": 1,
        "api_version": 1,
        "id": "example.vehicle",
        "name": "Example Vehicle",
        "version": "1.0.0",
        "capabilities": capabilities,
        "systems": [{
            "id": "vehicle-distribution",
            "name": "Vehicle Distribution",
            "settings": settings,
        }],
        "gbay": {"sections": [], "catalogs": [{
            "id": "example-vehicles",
            "kind": "vehicle",
            "source": "scripts/ALLIN1/Catalogs/example.vehicle/vehicles.json",
        }]},
        "runtime": {"assemblies": []},
    }
    (package / "allin1.content.json").write_text(
        json.dumps(content), encoding="utf-8",
    )
    requires = (
        f'requires = ["{dependency_spec}"]\n' if dependency else ""
    )
    (package / "mod.toml").write_text(
        """schema_version = 2
id = "example.vehicle"
name = "Example Vehicle"
version = "1.0.0"
type = "mixed"
editions = ["enhanced"]
dependencies = ["openrpf"]
dlc_packs = ["examplepack"]

[[files]]
source = "payload/dlc.rpf"
destination = "mods/update/x64/dlcpacks/examplepack/dlc.rpf"

[[files]]
source = "payload/vehicles.json"
destination = "scripts/ALLIN1/Catalogs/example.vehicle/vehicles.json"

[allin1]
api_version = 1
content = "allin1.content.json"
""" + requires,
        encoding="utf-8",
    )
    return package


def test_vehicle_catalog_round_trips_preview_and_independent_traffic() -> None:
    catalog = VehicleCatalog.from_dict(_catalog(traffic=True))
    vehicle = catalog.vehicles[0]
    assert vehicle.model == "examplecar"
    assert vehicle.preview_dictionary == "example_preview"
    assert vehicle.preview_texture == "examplecar_card"
    assert vehicle.traffic.enabled is True
    assert VehicleCatalog.from_dict(catalog.to_dict()) == catalog


@pytest.mark.parametrize(
    ("traffic", "message"),
    [
        ([], "must be an object"),
        ({"enabled": "yes"}, "enabled must be a boolean"),
        ({"weight": True}, "weight must be a number"),
        ({"weight": float("inf")}, "weight must be between"),
        ({"weight": 0.09}, "weight must be between"),
        ({"weight": 20.01}, "weight must be between"),
    ],
)
def test_vehicle_traffic_policy_rejects_unsafe_values(
    traffic: object, message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        VehicleTrafficPolicy.from_dict(traffic, "vehicle.traffic")


def test_vehicle_traffic_policy_and_minimal_entry_use_safe_defaults() -> None:
    assert VehicleTrafficPolicy.from_dict(None, "vehicle.traffic") == (
        VehicleTrafficPolicy()
    )
    payload = _catalog()
    vehicle = payload["vehicles"][0]
    vehicle.pop("traffic")
    vehicle.pop("manufacturer")
    vehicle.pop("size_tier")
    vehicle.pop("preview_dictionary")
    vehicle.pop("preview_texture")

    serialized = VehicleCatalog.from_dict(payload).to_dict()["vehicles"][0]

    assert serialized["manufacturer"] == ""
    assert serialized["size_tier"] == 0
    assert serialized["traffic"] == {"enabled": False, "weight": 1.0}
    assert "preview_dictionary" not in serialized
    assert "preview_texture" not in serialized


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value["vehicles"].__setitem__(0, "car"), "must be an object"),
        (
            lambda value: value["vehicles"][0].pop("model"),
            "model must be a non-empty string",
        ),
        (
            lambda value: value["vehicles"][0].update(model="bad model"),
            "model is invalid",
        ),
        (
            lambda value: value["vehicles"][0].update(category="unknown"),
            "category must be one of",
        ),
        (
            lambda value: value["vehicles"][0].update(storage="dock"),
            "storage must be one of",
        ),
        (
            lambda value: value["vehicles"][0].update(storage="helipad"),
            "storage must be garage",
        ),
        (
            lambda value: value["vehicles"][0].update(source_pack="bad pack"),
            "source_pack is invalid",
        ),
        (lambda value: value["vehicles"][0].update(size_tier=True), "size_tier must be"),
        (
            lambda value: value["vehicles"][0].update(manufacturer=7),
            "manufacturer must be a string",
        ),
        (
            lambda value: value["vehicles"][0].update(name="N" * 129),
            "name must not exceed",
        ),
        (
            lambda value: value["vehicles"][0].update(manufacturer="M" * 97),
            "manufacturer must not exceed",
        ),
        (
            lambda value: value["vehicles"][0].update(
                preview_dictionary="bad preview",
            ),
            "preview_dictionary is invalid",
        ),
        (
            lambda value: value["vehicles"][0].update(
                preview_texture="bad preview",
            ),
            "preview_texture is invalid",
        ),
    ],
)
def test_vehicle_catalog_rejects_invalid_entry_fields(mutate, message: str) -> None:
    payload = _catalog()
    mutate(payload)
    with pytest.raises(ValueError, match=message):
        VehicleCatalog.from_dict(payload)


def test_vehicle_catalog_rejects_invalid_files_and_envelopes(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid GBAY vehicle catalog"):
        VehicleCatalog.load(malformed)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_VEHICLE_CATALOG_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB safety limit"):
        VehicleCatalog.load(oversized)

    with pytest.raises(ValueError, match="must be a JSON object"):
        VehicleCatalog.from_dict([])

    bad_id = _catalog()
    bad_id["id"] = "Invalid ID"
    with pytest.raises(ValueError, match="catalog.id is invalid"):
        VehicleCatalog.from_dict(bad_id)

    empty = _catalog()
    empty["vehicles"] = []
    with pytest.raises(ValueError, match="non-empty array"):
        VehicleCatalog.from_dict(empty)

    too_many = _catalog()
    too_many["vehicles"] = [too_many["vehicles"][0]] * (
        MAX_VEHICLE_CATALOG_ENTRIES + 1
    )
    with pytest.raises(ValueError, match="more than"):
        VehicleCatalog.from_dict(too_many)

    long_name = _catalog()
    long_name["name"] = "C" * 129
    with pytest.raises(ValueError, match="catalog.name must not exceed"):
        VehicleCatalog.from_dict(long_name)


def test_vehicle_catalog_requires_explicit_base_game_authority() -> None:
    payload = _catalog(model="storycar")
    payload["vehicles"][0]["source_pack"] = "base"
    catalog = VehicleCatalog.from_dict(payload)

    with pytest.raises(ValueError, match="cannot claim base-game model"):
        catalog.validate_package_ownership(())

    catalog.validate_package_ownership((), allow_base_game=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update({"mystery": True}), "unsupported fields"),
        (lambda value: value["vehicles"].append(dict(value["vehicles"][0])), "duplicate"),
        (lambda value: value["vehicles"][0].update({"price": -1}), "price"),
        (lambda value: value["vehicles"][0].update({
            "category": "boats", "storage": "garage",
        }), "storage must be harbour"),
        (lambda value: value["vehicles"][0].update({
            "category": "helicopters", "storage": "helipad",
            "traffic": {"enabled": True},
        }), "cannot opt into ambient traffic"),
        (lambda value: value["vehicles"][0].update({
            "preview_dictionary": None, "preview_texture": "card",
        }), "preview_texture requires"),
        (lambda value: value.update({"schema_version": True}), "schema_version"),
        (lambda value: value["vehicles"][0]["traffic"].update({
            "zones": ["rich"],
        }), "unsupported fields"),
    ],
)
def test_vehicle_catalog_fails_closed(mutate, message: str) -> None:
    payload = _catalog()
    mutate(payload)
    with pytest.raises(ValueError, match=message):
        VehicleCatalog.from_dict(payload)


def test_mod_manifest_accepts_owned_addon_catalog_and_traffic_gate(
    tmp_path: Path,
) -> None:
    manifest = ModManifest.load(_package(tmp_path, catalog=_catalog(traffic=True)))
    assert manifest.dlc_packs == ("examplepack",)
    assert manifest.extension is not None
    assert manifest.extension.gbay_catalogs[0].kind == "vehicle"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"traffic_capability": False, "traffic_setting": False},
         "traffic.catalog capability"),
        ({"traffic_setting": False}, "traffic_enabled setting"),
        ({"traffic_default": True}, "defaults to false"),
        ({"dependency": False}, "require allin1.online-content"),
        ({"dependency_spec": "allin1.online-content"}, ">=0.5.5"),
        ({"dependency_spec": "allin1.online-content>=0.5.4"}, ">=0.5.5"),
        ({"dependency_spec": "allin1.online-content==0.5.5"}, ">=0.5.5"),
    ],
)
def test_mod_manifest_rejects_incomplete_vehicle_distribution_contract(
    tmp_path: Path, kwargs: dict, message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ModManifest.load(
            _package(tmp_path, catalog=_catalog(traffic=True), **kwargs)
        )


def test_mod_manifest_rejects_unowned_pack_and_official_model(tmp_path: Path) -> None:
    unowned = _catalog()
    unowned["vehicles"][0]["source_pack"] = "somebody_else"
    with pytest.raises(ValueError, match="unowned DLC pack"):
        ModManifest.load(_package(tmp_path / "unowned", catalog=unowned))

    collision = _catalog(model="adder")
    with pytest.raises(ValueError, match="official GTA model"):
        ModManifest.load(_package(tmp_path / "collision", catalog=collision))


def test_vehicle_catalog_rejects_model_hash_collisions() -> None:
    payload = _catalog()
    payload["vehicles"][0]["model"] = "xqe8v7fz"
    second = dict(payload["vehicles"][0])
    second["model"] = "xc7xaymx"
    payload["vehicles"].append(second)
    assert vehicle_model_hash("xqe8v7fz") == vehicle_model_hash("xc7xaymx")
    with pytest.raises(ValueError, match="duplicate model hashes"):
        VehicleCatalog.from_dict(payload)


def test_vehicle_catalog_rejects_reserved_model_hash_collision() -> None:
    payload = _catalog(model="xqe8v7fz")
    catalog = VehicleCatalog.from_dict(payload)
    with pytest.raises(ValueError, match="official GTA model"):
        catalog.validate_package_ownership(
            ("examplepack",), reserved_models=("xc7xaymx",),
        )


def test_story_catalog_is_curated_non_aircraft_and_never_duplicates_traffic() -> None:
    catalog = VehicleCatalog.load(ROOT / "data" / "story_vehicles.json")
    assert len(catalog.vehicles) == 256
    assert {"adder", "tailgater", "buffalo2", "bodhi2"}.issubset(
        {vehicle.model for vehicle in catalog.vehicles}
    )
    assert all(vehicle.source_pack == "base" for vehicle in catalog.vehicles)
    assert all(vehicle.storage != "hangar" for vehicle in catalog.vehicles)
    assert all(not vehicle.traffic.enabled for vehicle in catalog.vehicles)
    assert not {"freight", "cargoplane", "submersible", "blimp"}.intersection(
        {vehicle.model for vehicle in catalog.vehicles}
    )


def test_story_catalog_generator_keeps_supported_storage_and_excludes_planes() -> None:
    def item(model: str, vehicle_type: str, vehicle_class: str) -> str:
        return f"""
        <Item>
          <modelName>{model}</modelName>
          <gameName>{model.upper()}</gameName>
          <vehicleMakeName>OBEY</vehicleMakeName>
          <type>{vehicle_type}</type>
          <vehicleClass>{vehicle_class}</vehicleClass>
        </Item>
        """

    payload = build_story_catalog(
        "<CVehicleModelInfo__InitDataList><InitDatas>" +
        item("storycar", "VEHICLE_TYPE_CAR", "VC_SPORT") +
        item("storyboat", "VEHICLE_TYPE_BOAT", "VC_BOAT") +
        item("storyheli", "VEHICLE_TYPE_HELI", "VC_HELICOPTER") +
        item("storyplane", "VEHICLE_TYPE_PLANE", "VC_PLANE") +
        item("storytrailer", "VEHICLE_TYPE_TRAILER", "VC_COMMERCIAL") +
        "</InitDatas></CVehicleModelInfo__InitDataList>"
    )

    generated = {value["model"]: value for value in payload["vehicles"]}
    assert set(generated) == {"storycar", "storyboat", "storyheli"}
    assert generated["storycar"]["storage"] == "garage"
    assert generated["storyboat"]["storage"] == "harbour"
    assert generated["storyheli"]["storage"] == "helipad"
