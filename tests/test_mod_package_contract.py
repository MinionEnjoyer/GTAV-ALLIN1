from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

import allin1.mods as mods
from allin1.cli import main
from allin1.mod_package_contract import (
    parse_workbench_contract,
    validate_mod_schema_envelope,
)
from allin1.mods import ModManifest, open_mod_package


FIXTURES = Path(__file__).parent / "contract_fixtures" / "mod_packages"


@pytest.mark.parametrize(("folder", "schema"), [("schema_v1", 1), ("schema_v2", 2)])
def test_shared_schema_contract_fixtures(folder: str, schema: int) -> None:
    package = ModManifest.load(FIXTURES / folder)
    assert package.schema_version == schema
    assert (package.extension is not None) is (schema == 2)


def test_contract_fixture_bytes_match_sdk_copy() -> None:
    sdk_module = pytest.importorskip("allin1_sdk")
    SDK_FIXTURES = Path(sdk_module.__file__).resolve().parents[2] / "tests/contract_fixtures/mod_packages"
    if not SDK_FIXTURES.is_dir():
        pytest.skip("Installed SDK does not include source contract fixtures")
    local = {
        path.relative_to(FIXTURES): path.read_bytes()
        for path in FIXTURES.rglob("*") if path.is_file()
    }
    sdk = {
        path.relative_to(SDK_FIXTURES): path.read_bytes()
        for path in SDK_FIXTURES.rglob("*") if path.is_file()
    }
    assert local == sdk


def test_schema_envelope_and_scripted_weapon_relationship_contract() -> None:
    schema, extension = validate_mod_schema_envelope({
        "schema_version": 2,
        "allin1": {
            "api_version": 1,
            "content": "allin1.content.json",
            "requires": ["allin1.online-content>=0.5.5"],
        },
    })
    assert schema == 2
    assert extension is not None

    enhancements = parse_workbench_contract({
        "weapon_enhancements": [{
            "id": "test.suppressor-heat",
            "name": "Suppressor heat",
            "mode": "scripted_vanilla_components",
            "weapon_components": [{
                "weapon_name": "WEAPON_PISTOL",
                "weapon_hash": "0x1B06D571",
                "component_name": "COMPONENT_AT_PI_SUPP_02",
                "component_hash": "65EA7EBB",
            }],
            "script_entry_points": ["Test.Suppressor.Controller"],
            "visual_assets": [{
                "dlc_pack": "test_heat",
                "archive": "x64/models/cdimages/test_heat.rpf",
                "families": ["pi", "ar"],
                "levels": 24,
                "model_pattern": "test_{family}_{level:02d}.ydr",
                "base_model_pattern": "test_{family}.ydr",
                "texture_dictionary": "test_heat.ytd",
                "texture_pattern": "test_gradient_{level:02d}",
                "archetype_dictionary": "test_heat.ytyp",
                "base_level_uses_unsuffixed": True,
            }],
        }],
    }, runtime_entry_points=["Test.Suppressor.Controller"])
    enhancement = enhancements[0]
    assert enhancement.enhancement_id == "test.suppressor-heat"
    assert enhancement.weapon_components[0].weapon_hash == "0x1B06D571"
    assert enhancement.weapon_components[0].component_hash == "0x65EA7EBB"
    assert enhancement.visual_assets[0].levels == 24
    assert enhancement.to_dict()["id"] == "test.suppressor-heat"


@pytest.mark.parametrize("payload", [
    {"schema_version": 3},
    {"schema_version": 1, "allin1": {}},
    {"schema_version": 2},
    {"schema_version": 2, "allin1": []},
    {"schema_version": 2, "allin1": {"api_version": 9, "content": "x"}},
    {"schema_version": 2, "allin1": {"api_version": 1, "content": "", "requires": []}},
    {"schema_version": 2, "allin1": {"api_version": 1, "content": "x", "requires": "bad"}},
])
def test_schema_envelope_rejects_invalid_versions_and_extensions(payload) -> None:
    with pytest.raises(ValueError):
        validate_mod_schema_envelope(payload)


@pytest.mark.parametrize("workbench", [
    [],
    {"unknown": []},
    {"weapon_enhancements": "bad"},
    {"weapon_enhancements": [{}]},
    {"weapon_enhancements": [{
        "id": "test.bad", "name": "Bad", "mode": "replacement",
        "weapon_components": [], "script_entry_points": ["Test.Bad.Controller"],
        "visual_assets": [],
    }]},
])
def test_workbench_contract_fails_closed_on_malformed_relationships(workbench) -> None:
    with pytest.raises(ValueError):
        parse_workbench_contract(workbench)


def _zip_tree(archive: Path, root: Path, prefix: str = "") -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for source in root.rglob("*"):
            if source.is_file():
                package.write(source, prefix + source.relative_to(root).as_posix())


@pytest.mark.parametrize("prefix", ["", "source-repo/package/"])
def test_zip_import_accepts_one_root_or_nested_manifest(
    tmp_path: Path, prefix: str,
) -> None:
    archive = tmp_path / "package.zip"
    _zip_tree(archive, FIXTURES / "schema_v2", prefix)
    with open_mod_package(archive) as package:
        staged_root = package.package_root
        assert package.mod_id == "contract.schema-v2"
        assert package.schema_version == 2
        assert staged_root.is_dir()
    assert not staged_root.exists()


@pytest.mark.parametrize("entries", [[], ["one/mod.toml", "two/mod.toml"]])
def test_zip_import_rejects_zero_or_multiple_manifests(
    tmp_path: Path, entries: list[str],
) -> None:
    archive = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for entry in entries:
            package.writestr(entry, "schema_version = 1")
    with pytest.raises(ValueError, match="does not contain|multiple mod.toml"):
        with open_mod_package(archive):
            pass


def test_zip_import_rejects_traversal_and_symlinks(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as package:
        package.writestr("package/mod.toml", "schema_version = 1")
        package.writestr("../escape.txt", "escape")
    with pytest.raises(ValueError, match="traversal"):
        with open_mod_package(traversal):
            pass

    linked = tmp_path / "linked.zip"
    link = zipfile.ZipInfo("package/payload/link.dll")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(linked, "w") as package:
        package.writestr("package/mod.toml", "schema_version = 1")
        package.writestr(link, "target")
    with pytest.raises(ValueError, match="links or special files"):
        with open_mod_package(linked):
            pass


def test_zip_import_enforces_expansion_limit(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "large.zip"
    _zip_tree(archive, FIXTURES / "schema_v1")
    monkeypatch.setattr(mods, "MAX_PACKAGE_ARCHIVE_BYTES", 8)
    with pytest.raises(ValueError, match="size limit"):
        with open_mod_package(archive):
            pass


def test_launcher_cli_validates_zip_package(tmp_path: Path) -> None:
    archive = tmp_path / "package.zip"
    _zip_tree(archive, FIXTURES / "schema_v2", "source-repo/package/")
    result = CliRunner().invoke(main, ["content", "validate", str(archive)])
    assert result.exit_code == 0, result.output
    assert "schema 2" in result.output
