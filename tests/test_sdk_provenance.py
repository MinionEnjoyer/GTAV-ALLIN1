import json
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from allin1 import artifact_contract as contract, sdk_provenance as provenance
from allin1.mods import ModIntegrationService, ModManifest
from tests.test_mods import _game, _package


def traced(tmp_path, edition="Enhanced"):
    root = _package(tmp_path,"traced-sdk","config","scripts/owned.ini")
    inventory = {file.name:provenance.file_hash(file) for file in root.iterdir()}
    build = contract.seal({"schema_version":1,"kind":"sdk_execution_identity","sdk_version":"test","mode":"development_dirty",
        "source":{"source_tree_sha256":"a"*64},"executable_sha256":"b"*64,"resource_files":{"tools/RpfPatcher/RpfPatcher.exe":"c"*64}},"build_fingerprint")
    artifact = contract.seal({"schema_version":1,"kind":"sdk_artifact_manifest","build":build,"inputs":inventory,"outputs":inventory,
        "edition":edition,"validation_reports":["d"*64],"changes_sha256":"e"*64},"artifact_id")
    (root/"sdk-artifact.json").write_text(json.dumps(artifact))
    return root, artifact


def test_installer_binds_actual_installed_bytes_and_preserves_lineage_across_toggle(tmp_path):
    root, artifact = traced(tmp_path)
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    manifest = ModManifest.load(root/"mod.toml")
    service.install(manifest)
    receipt = service._read_receipt(manifest.mod_id)
    lineage = receipt["sdk_provenance"]
    assert lineage["artifact_id"] == artifact["artifact_id"]
    assert lineage["build_fingerprint"] == artifact["build"]["build_fingerprint"]
    assert lineage["files"] == [{"source":"payload.bin","destination":"scripts/owned.ini","sha256":provenance.file_hash(game/"scripts/owned.ini"),"verification":"installed_bytes"}]
    service.set_enabled(manifest.mod_id,False)
    assert service._read_receipt(manifest.mod_id)["sdk_provenance"] == lineage
    service.set_enabled(manifest.mod_id,True)
    assert provenance.file_hash(game/"scripts/owned.ini") == artifact["outputs"]["payload.bin"]


@pytest.mark.parametrize("fault",["changed","edition","unlisted","forged"])
def test_present_invalid_provenance_is_rejected_before_game_write(tmp_path,fault):
    root, artifact = traced(tmp_path,"Legacy" if fault=="edition" else "Enhanced")
    game = _game(tmp_path)
    if fault=="changed": (root/"mod.toml").write_text((root/"mod.toml").read_text()+"\n# modified\n")
    elif fault=="unlisted": (root/"extra.txt").write_text("unbuilt payload")
    elif fault=="forged":
        artifact["build"]["sdk_version"]="fake"
        (root/"sdk-artifact.json").write_text(json.dumps(artifact))
    with pytest.raises(ValueError):
        ModIntegrationService(game).install(ModManifest.load(root/"mod.toml"))
    assert not (game/"scripts/owned.ini").exists()


def test_post_copy_provenance_failure_uses_existing_installer_rollback(tmp_path,monkeypatch):
    root, _ = traced(tmp_path)
    game = _game(tmp_path); (game/"scripts").mkdir(); (game/"scripts/owned.ini").write_bytes(b"original")
    service = ModIntegrationService(game)
    def reject(*args): raise ValueError("Installed file differs from artifact")
    monkeypatch.setattr(provenance,"installed",reject)
    with pytest.raises(ValueError,match="differs"):
        service.install(ModManifest.load(root/"mod.toml"))
    assert (game/"scripts/owned.ini").read_bytes() == b"original"
    assert not service._receipt_path("traced-sdk").exists()


def test_ordinary_packages_do_not_acquire_invented_sdk_lineage(tmp_path):
    root = _package(tmp_path,"ordinary-package","config","scripts/ordinary.ini")
    service = ModIntegrationService(_game(tmp_path))
    service.install(ModManifest.load(root/"mod.toml"))
    assert "sdk_provenance" not in service._read_receipt("ordinary-package")


def test_lineage_rejects_incomplete_or_mismatched_install_evidence():
    loose = SimpleNamespace(source=PurePosixPath("payload.bin"), destination=PurePosixPath("scripts/owned.ini"))
    member = SimpleNamespace(source=PurePosixPath("inside.bin"), archive=PurePosixPath("update/update.rpf"), entry=PurePosixPath("data/inside.bin"))
    artifact = {"outputs": {"payload.bin": "a" * 64, "inside.bin": "b" * 64}}
    manifest = SimpleNamespace(files=(loose,), rpf_entries=(member,))

    with pytest.raises(ValueError, match="incomplete"):
        provenance.installed({"artifact": artifact}, manifest, [], [])
    with pytest.raises(ValueError, match="Installed file differs"):
        provenance.installed({"artifact": artifact}, manifest,
                             [{"sha256": "wrong", "destination": "scripts/owned.ini"}],
                             [{"sha256": "b" * 64, "archive": "update/update.rpf", "entry": "data/inside.bin"}])
    with pytest.raises(ValueError, match="Installed RPF member differs"):
        provenance.installed({"artifact": artifact}, manifest,
                             [{"sha256": "a" * 64, "destination": "scripts/owned.ini"}],
                             [{"sha256": "wrong", "archive": "update/update.rpf", "entry": "data/inside.bin"}])


def test_lineage_handles_absent_envelopes_and_records_reviewed_rpf_members(tmp_path):
    assert provenance.read(SimpleNamespace(package_root=tmp_path, files=(), rpf_entries=()), "Enhanced") is None

    member = SimpleNamespace(source=PurePosixPath("inside.bin"), archive=PurePosixPath("update/update.rpf"), entry=PurePosixPath("data/inside.bin"))
    artifact = {"artifact_id": "artifact", "build": {"build_fingerprint": "fingerprint"},
                "outputs": {"inside.bin": "b" * 64}}
    lineage = provenance.installed({"artifact": artifact}, SimpleNamespace(files=(), rpf_entries=(member,)), [],
                                   [{"sha256": "b" * 64, "archive": "update/update.rpf", "entry": "data/inside.bin"}])
    assert lineage["rpf_members"] == [{"source": "inside.bin", "archive": "update/update.rpf",
                                        "entry": "data/inside.bin", "sha256": "b" * 64,
                                        "verification": "extracted_member_bytes"}]


def test_lineage_rejects_oversized_envelopes_and_unreviewed_sources(tmp_path):
    oversized = tmp_path / provenance.ARTIFACT_FILE
    oversized.write_bytes(b"x" * (4 * 1024**2 + 1))
    with pytest.raises(ValueError, match="exceeds 4 MiB"):
        provenance.read(SimpleNamespace(package_root=tmp_path, files=(), rpf_entries=()), "Enhanced")

    root, _ = traced(tmp_path / "traced")
    unreviewed = SimpleNamespace(package_root=root,
                                 files=(SimpleNamespace(source=PurePosixPath("not-in-artifact.bin")),), rpf_entries=())
    with pytest.raises(ValueError, match="outside the SDK artifact inventory"):
        provenance.read(unreviewed, "Enhanced")
