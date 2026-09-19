"""Component bundle isolation, independent ownership, and failure-before-write checks."""
import hashlib
import json
from types import SimpleNamespace
import zipfile

import pytest

from allin1.mods import ModManifest, ModIntegrationService, open_mod_package
from allin1.mod_package_contract import validate_component_bundle


def write_bundle(root, *, mutate=None):
    root.mkdir(parents=True, exist_ok=True)
    raw = dict(schema_version=6, id="test.collection", name="Collection", version="2026.1",
               type="collection", editions=["legacy", "enhanced"], variants={})
    for edition in raw["editions"]:
        rows = []
        for index in range(2 if edition == "legacy" else 1):
            child = root / edition / str(index)
            child.mkdir(parents=True)
            payload = f"{edition}-{index}".encode()
            (child / "payload.bin").write_bytes(payload)
            data = dict(schema_version=1, id=f"{edition}.part{index}", name=f"Part {index}",
                        version="1.2" if edition == "legacy" else "1.3", type="config",
                        editions=[edition], files=[dict(source="payload.bin",
                            destination=f"scripts/part{index}.ini", sha256=hashlib.sha256(payload).hexdigest())])
            if mutate:
                mutate(edition, index, data)
            lines = [f"{key} = {json.dumps(value)}" for key, value in data.items() if key != "files"]
            for item in data["files"]:
                lines += ["[[files]]"] + [f"{key} = {json.dumps(value)}" for key, value in item.items()]
            manifest = child / "mod.toml"
            manifest.write_text("\n".join(lines), encoding="utf-8")
            rows.append(dict(manifest=manifest.relative_to(root).as_posix(),
                             sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()))
        raw["variants"][edition] = dict(components=rows)
    save_envelope(root, raw)
    return root


def save_envelope(root, raw):
    lines = [f"{key} = {json.dumps(value)}" for key, value in raw.items() if key != "variants"]
    for edition, variant in raw["variants"].items():
        for row in variant["components"]:
            lines += [f"[[variants.{edition}.components]]"] + [
                f"{key} = {json.dumps(value)}" for key, value in row.items()]
    (root / "mod.toml").write_text("\n".join(lines), encoding="utf-8")


def zip_bundle(root, output, prefix=""):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in root.rglob("*"):
            if item.is_file():
                archive.write(item, prefix + item.relative_to(root).as_posix())
    return output


def game_root(root, edition):
    root.mkdir()
    (root / ("GTA5.exe" if edition == "legacy" else "GTA5_Enhanced.exe")).write_bytes(b"fixture")
    (root / "scripts").mkdir()
    (root / "scripts/part0.ini").write_bytes(b"original")
    return root


@pytest.mark.parametrize("edition", ["legacy", "enhanced"])
@pytest.mark.parametrize("prefix", ["", "download/"])
def test_zip_components_install_independently_and_restore_original(tmp_path, edition, prefix):
    source = zip_bundle(write_bundle(tmp_path / "bundle"), tmp_path / "both.zip", prefix)
    game = game_root(tmp_path / "game", edition)
    service = ModIntegrationService(game)
    with open_mod_package(source) as bundle:
        assert bundle.schema_version == 6
        selected = bundle.for_edition(edition)
        assert len(selected.variants) == (2 if edition == "legacy" else 1)
        with pytest.raises(ValueError, match="Select one component"):
            service.install(bundle)
        assert not (game / "scripts/.allin1").exists()
        service.install(bundle, component_id=f"{edition}.part0")
    assert (game / "scripts/part0.ini").read_bytes() == f"{edition}-0".encode()
    assert not (game / "scripts/part1.ini").exists()
    assert [item.mod_id for item in service.list_installed()] == [f"{edition}.part0"]
    receipt = json.loads((service.state_root / f"{edition}.part0.json").read_text())
    assert receipt["schema_version"] == 1
    assert receipt["version"] == ("1.2" if edition == "legacy" else "1.3")
    service.uninstall(f"{edition}.part0")
    assert (game / "scripts/part0.ini").read_bytes() == b"original"


@pytest.mark.parametrize("component", [None, "", "missing", "enhanced.part0", [], 1])
def test_invalid_or_cross_edition_selection_never_writes(tmp_path, component):
    bundle = ModManifest.load(write_bundle(tmp_path / "bundle"))
    game = game_root(tmp_path / "game", "legacy")
    with pytest.raises(ValueError, match="Select one component"):
        ModIntegrationService(game).install(bundle, component_id=component)
    assert not (game / "scripts/.allin1").exists()


@pytest.mark.parametrize("target", ["enhanced/0/payload.bin", "enhanced/0/mod.toml"])
def test_unselected_component_tampering_is_not_ignored(tmp_path, target):
    root = write_bundle(tmp_path / "bundle")
    child = ModManifest.load(root).select_component("legacy", "legacy.part0")
    (root / target).write_bytes(b"tampered")
    game = game_root(tmp_path / "game", "legacy")
    with pytest.raises(ValueError, match="checksum mismatch|SHA-256 mismatch"):
        ModIntegrationService(game).install(child)
    assert not (game / "scripts/.allin1").exists()


@pytest.mark.parametrize("mutation,match", [
    (lambda e, i, d: d.update(id="duplicate") if e == "legacy" else None, "unique"),
    (lambda e, i, d: d.update(editions=["enhanced"]) if e == "legacy" else None, "matching edition"),
    (lambda e, i, d: d.update(id="test.collection"), "differ"),
    (lambda e, i, d: d["files"][0].update(destination="scripts/shared.ini"), "overlapping file"),
    (lambda e, i, d: d["files"][0].pop("sha256"), "require SHA-256"),
    (lambda e, i, d: d.update(conflicts=["legacy.part1"]) if e == "legacy" and i == 0 else None, "conflict"),
])
def test_invalid_components_rejected(tmp_path, mutation, match):
    with pytest.raises(ValueError, match=match):
        ModManifest.load(write_bundle(tmp_path / "bundle", mutate=mutation))


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(type="mixed"),
    lambda d: d.update(files=[]),
    lambda d: d.update(editions=["legacy", "legacy"]),
    lambda d: d["variants"]["legacy"].update(components=[]),
    lambda d: d["variants"]["legacy"].update(components=[{}] * 33),
    lambda d: d["variants"]["legacy"]["components"][0].update(manifest="../escape/mod.toml"),
    lambda d: d["variants"]["legacy"]["components"][0].update(manifest="enhanced/0/mod.toml"),
    lambda d: d["variants"]["legacy"]["components"][0].update(manifest="legacy/0/more/mod.toml"),
    lambda d: d["variants"]["legacy"]["components"][0].update(sha256="invalid"),
    lambda d: d["variants"]["legacy"]["components"].append(d["variants"]["legacy"]["components"][0]),
])
def test_invalid_envelope(tmp_path, mutation):
    root = write_bundle(tmp_path / "bundle")
    from allin1.mods import tomllib
    data = tomllib.loads((root / "mod.toml").read_text())
    mutation(data)
    with pytest.raises(ValueError):
        validate_component_bundle(data)


def test_undeclared_manifest_rejected(tmp_path):
    root = write_bundle(tmp_path / "bundle")
    (root / "extra").mkdir()
    (root / "extra/mod.toml").write_text("schema_version = 1")
    source = zip_bundle(root, tmp_path / "bad.zip")
    with pytest.raises(ValueError, match="undeclared"):
        with open_mod_package(source):
            pass


def test_nested_collection_rejected_without_recursion(tmp_path):
    root = write_bundle(tmp_path / "bundle")
    from allin1.mods import tomllib
    data = tomllib.loads((root / "mod.toml").read_text())
    child = root / "legacy/0/mod.toml"
    child.write_bytes((root / "mod.toml").read_bytes())
    data["variants"]["legacy"]["components"][0]["sha256"] = hashlib.sha256(child.read_bytes()).hexdigest()
    save_envelope(root, data)
    with pytest.raises(ValueError, match="Nested edition bundles"):
        ModManifest.load(root)

@pytest.mark.parametrize("kind", ["equal", "nested", "whole_archive", "parent_directory"])
def test_cross_component_rpf_ownership_collisions_are_rejected(tmp_path, kind):
    from dataclasses import replace
    from pathlib import PurePosixPath as P
    from allin1.mods import RpfEntryPatch, ModFile
    from allin1.component_bundles import validate_inventory
    children = ModManifest.load(write_bundle(tmp_path / "bundle")).for_edition("legacy").variants
    patch = RpfEntryPatch(P("payload.bin"), P("mods/x64e.rpf"), P("vehicles.rpf!taxi.ytd"), "1" * 64, "2" * 64)
    first = replace(children[0], files=(), rpf_entries=(patch,))
    if kind in {"equal", "nested"}:
        other = replace(patch, entry=P("vehicles.rpf") if kind == "nested" else patch.entry)
        second = replace(children[1], files=(), rpf_entries=(other,))
    else:
        destination = P("mods/x64e.rpf") if kind == "whole_archive" else P("mods")
        second = replace(children[1], files=(ModFile(P("payload.bin"), destination, "3" * 64),), rpf_entries=())
    for ordered in ([first, second], [second, first]):
        with pytest.raises(ValueError, match="overlap"):
            validate_inventory(ordered)


def test_internal_requirements_must_be_compatible_and_precede_dependents(tmp_path):
    from dataclasses import replace
    from allin1.mods import PackageRequirement
    from allin1.component_bundles import validate_inventory
    first, second = ModManifest.load(write_bundle(tmp_path / "bundle")).for_edition("legacy").variants
    second = replace(second, package_requirements=(PackageRequirement.parse("legacy.part0>=1.2"),))
    validate_inventory([first, second])
    with pytest.raises(ValueError, match="precede"):
        validate_inventory([second, first])
    with pytest.raises(ValueError, match="compatible"):
        validate_inventory([replace(first, version="1.1"), second])


@pytest.mark.parametrize("destination", ["CustomShaders/a.cso", "addonhelper.addon", "README.md"])
def test_reshade_component_destination_parity(tmp_path, destination):
    def mutate(edition, index, data):
        data["type"] = "mixed"
        # Different destinations for siblings; only the first tests the root payload.
        if index == 0:
            data["files"][0]["destination"] = destination
    assert ModManifest.load(write_bundle(tmp_path / "bundle", mutate=mutate)).schema_version == 6


def test_component_selection_revalidates_bundle_sources_and_legacy_boundaries(tmp_path):
    from allin1.component_bundles import installation_component, validate_inventory

    selected = SimpleNamespace(manifest_path=tmp_path / "component.toml")

    class Bundle:
        schema_version = 6

        @classmethod
        def load(cls, path):
            assert path == tmp_path / "bundle.toml"
            return cls()

        def select_component(self, edition, component_id):
            assert (edition, component_id) == ("legacy", "component")
            return selected

    child = Bundle()
    child.bundle_manifest_path = tmp_path / "bundle.toml"
    child.manifest_path = selected.manifest_path
    child.mod_id = "component"
    child.schema_version = 6
    assert installation_component(child, "legacy") is selected

    class TopLevel(Bundle):
        @classmethod
        def load(cls, path):
            assert path == tmp_path / "top-level.toml"
            return cls()

    top_level = TopLevel()
    top_level.bundle_manifest_path = None
    top_level.manifest_path = tmp_path / "top-level.toml"
    top_level.schema_version = 6
    assert installation_component(top_level, "legacy", "component") is selected

    legacy = SimpleNamespace(bundle_manifest_path=None, schema_version=4)
    with pytest.raises(ValueError, match="schema-6"):
        installation_component(legacy, "legacy", "component")
    assert installation_component(legacy, "legacy") is legacy

    first = SimpleNamespace(mod_id="first", conflicts=("second",))
    second = SimpleNamespace(mod_id="second")
    with pytest.raises(ValueError, match="conflict"):
        validate_inventory((first, second))

    first = SimpleNamespace(mod_id="first", conflicts=(), package_requirements=(), files=(),
                            rpf_entries=(), dlc_packs=("mp_test",))
    second = SimpleNamespace(mod_id="second", conflicts=(), package_requirements=(), files=(),
                             rpf_entries=(), dlc_packs=("MP_TEST",))
    with pytest.raises(ValueError, match="DLC ownership"):
        validate_inventory((first, second))
