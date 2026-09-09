"""Edition bundle contract, isolation, archive safety and lifecycle regression."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from allin1.mods import ModManifest, ModIntegrationService, ModCatalog, open_mod_package
from allin1.cli import main
from allin1.desktop_packages import describe


def make_bundle(root, *, editions=("legacy", "enhanced"), wrong=None, identity=None, checksum=True):
    root.mkdir(parents=True, exist_ok=True)
    rows = ['schema_version = 5', 'id = "test.bundle"', 'name = "Test bundle"',
            'version = "1.0"', 'type = "bundle"', f"editions = {json.dumps(editions)}"]
    for edition in editions:
        child = root / edition
        child.mkdir()
        payload = edition.encode()
        (child / "payload.bin").write_bytes(payload)
        (child / "mod.toml").write_text(
            'schema_version = 1\nid = "' + (identity or "test.bundle") + '"\nname = "Test bundle"\n'
            'version = "1.0"\ntype = "config"\neditions = ["' + (wrong or edition) + '"]\n'
            '[[files]]\nsource = "payload.bin"\ndestination = "scripts/test.ini"\n'
            + (f'sha256 = "{hashlib.sha256(payload).hexdigest()}"\n' if checksum else ""),
            encoding="utf-8",
        )
        rows += [f"[variants.{edition}]", f'manifest = "{edition}/mod.toml"',
                 f'sha256 = "{hashlib.sha256((child / "mod.toml").read_bytes()).hexdigest()}"']
    (root / "mod.toml").write_text("\n".join(rows), encoding="utf-8")
    return root


def archive_bundle(root, output, prefix=""):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, prefix + path.relative_to(root).as_posix())
    return output


def game_root(path, edition):
    path.mkdir()
    (path / ("GTA5_Enhanced.exe" if edition == "enhanced" else "GTA5.exe")).write_bytes(b"fixture")
    (path / "scripts").mkdir()
    (path / "scripts/test.ini").write_bytes(b"original")
    return path


@pytest.mark.parametrize("edition", ["legacy", "enhanced"])
@pytest.mark.parametrize("prefix", ["", "download/"])
def test_zip_selection_install_uninstall_preserves_original(tmp_path, edition, prefix):
    source = archive_bundle(make_bundle(tmp_path / "bundle"), tmp_path / "both.zip", prefix)
    game = game_root(tmp_path / "game", edition)
    service = ModIntegrationService(game)
    with open_mod_package(source) as bundle:
        assert bundle.schema_version == 5
        assert not bundle.files
        selected = bundle.for_edition(edition)
        assert selected.editions == (edition,)
        info = describe(bundle, game)
        assert info["selected_edition"] == edition
        assert info["bundle_editions"] == ["legacy", "enhanced"]
        service.install(bundle)
        assert (game / "scripts/test.ini").read_bytes() == edition.encode()
        receipt = json.loads((service.state_root / "test.bundle.json").read_text())
        assert len(receipt["files"]) == 1
        assert receipt["schema_version"] == 1
    service.set_enabled("test.bundle", False)
    service.set_enabled("test.bundle", True)
    assert (game / "scripts/test.ini").read_bytes() == edition.encode()
    service.uninstall("test.bundle")
    assert (game / "scripts/test.ini").read_bytes() == b"original"


def test_missing_variant_fails_before_writes(tmp_path):
    bundle = ModManifest.load(make_bundle(tmp_path / "bundle", editions=("legacy",)))
    game = game_root(tmp_path / "game", "enhanced")
    with pytest.raises(ValueError, match="no enhanced variant"):
        ModIntegrationService(game).install(bundle)
    assert not (game / "scripts/.allin1").exists()
    assert (game / "scripts/test.ini").read_bytes() == b"original"


@pytest.mark.parametrize("kw,match", [
    ({"wrong": "legacy"}, "matching edition"), ({"identity": "other.id"}, "must match"),
    ({"checksum": False}, "require SHA-256"),
])
def test_invalid_variant_rejected(tmp_path, kw, match):
    with pytest.raises(ValueError, match=match):
        ModManifest.load(make_bundle(tmp_path / "bundle", **kw))


@pytest.mark.parametrize("target", ["mod.toml", "payload.bin"])
def test_tampering_rejected(tmp_path, target):
    root = make_bundle(tmp_path / "bundle")
    with (root / "enhanced" / target).open("ab") as stream:
        stream.write(b"\n# tampered")
    with pytest.raises(ValueError, match="checksum mismatch|SHA-256 mismatch"):
        ModManifest.load(root)


@pytest.mark.parametrize("mutation", [
    ('manifest = "legacy/mod.toml"', 'manifest = "../legacy/mod.toml"'),
    ('manifest = "legacy/mod.toml"', 'manifest = "legacy.oiv"'),
    ('[variants.enhanced]', '[variants.unknown]'),
    ('type = "bundle"', 'type = "mixed"'),
])
def test_invalid_envelope_rejected(tmp_path, mutation):
    root = make_bundle(tmp_path / "bundle")
    path = root / "mod.toml"
    path.write_text(path.read_text().replace(*mutation))
    with pytest.raises(ValueError):
        ModManifest.load(root)


def test_extra_manifest_is_not_guessed(tmp_path):
    root = make_bundle(tmp_path / "bundle")
    (root / "unrelated").mkdir()
    (root / "unrelated/mod.toml").write_text('schema_version = 1')
    archive = archive_bundle(root, tmp_path / "extra.zip")
    with pytest.raises(ValueError, match="undeclared"):
        with open_mod_package(archive):
            pass


def test_nested_bundles_rejected_before_recursion(tmp_path):
    root = make_bundle(tmp_path / "bundle")
    child = root / "legacy/mod.toml"
    child.write_bytes((root / "mod.toml").read_bytes())
    path = root / "mod.toml"
    text = path.read_text()
    start = text.index('sha256 = "') + len('sha256 = "')
    path.write_text(text[:start] + hashlib.sha256(child.read_bytes()).hexdigest() + text[start + 64:])
    with pytest.raises(ValueError, match="Nested edition bundles"):
        ModManifest.load(root)


def test_catalog_and_cli(tmp_path):
    root = make_bundle(tmp_path / "catalog/bundle")
    assert ModCatalog(root.parent).discover()[0].schema_version == 5
    assert describe(ModManifest.load(root), None)["selected_edition"] is None
    archive = archive_bundle(root, tmp_path / "both.zip")
    result = CliRunner().invoke(main, ["content", "validate", str(archive)])
    assert result.exit_code == 0, result.output
    assert "schema 5" in result.output
    result = CliRunner().invoke(main, ["content", "validate", str(archive), "--edition", "enhanced"])
    assert result.exit_code == 0, result.output
    assert "1 file(s)" in result.output


def test_bundle_revalidates_children_at_install(tmp_path):
    root = make_bundle(tmp_path / "bundle")
    bundle = ModManifest.load(root)
    (root / "legacy/payload.bin").write_bytes(b"tampered")
    game = game_root(tmp_path / "game", "enhanced")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ModIntegrationService(game).install(bundle)
    assert (game / "scripts/test.ini").read_bytes() == b"original"
