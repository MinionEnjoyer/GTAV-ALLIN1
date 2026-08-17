import json
import zipfile

from allin1.diagnostics import _redact, create_diagnostic_bundle


def test_redact_hides_game_path_and_user_names():
    text = 'gta_path = "C:\\Users\\Alice\\GTAV"\n/Users/bob/project\n/home/carol/mod'
    redacted = _redact(text)
    assert "Alice" not in redacted and "bob" not in redacted and "carol" not in redacted
    assert 'gta_path = "<redacted>"' in redacted


def test_bundle_contains_redacted_files_and_manifest(tmp_path):
    project = tmp_path / "project"; scripts = tmp_path / "game" / "scripts"
    project.mkdir(); scripts.mkdir(parents=True)
    (project / "config.toml").write_text('gta_path = "/Users/private/GTAV"')
    (scripts / "ALLIN1_client.log").write_text('/home/secret/crash')
    (scripts / "ALLIN1_vehicle_grounding.json").write_text(
        '{"Entries":{"jester":{"RootOffset":0.31}}}'
    )
    output = tmp_path / "bundle.zip"
    assert create_diagnostic_bundle(output, project, scripts) == output
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "files/config.toml" in names
        assert "files/ALLIN1_vehicle_grounding.json" in names
        assert "private" not in archive.read("files/config.toml").decode()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == 1
        assert len(manifest["files"]) == 3
