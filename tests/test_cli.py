"""Command-level tests for every public CLI operation."""

import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import Mock

from click.testing import CliRunner
from PIL import Image, ImageDraw

from allin1 import cli
from allin1.config import Config
from allin1.installer import InstallResult
from allin1.release import ReleaseReport


VEHICLES = '''
[[vehicles]]
model="alpha"
name="Alpha"
class="super"
manufacturer="Maker"
traffic=["veh_rich"]
'''


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def _project(tmp_path: Path, monkeypatch) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "vehicles.toml").write_text(VEHICLES)
    (data / "weapons.toml").write_text(
        '[[weapons]]\nname="WEAPON_TEST"\nlabel="Test"\ncategory="pistols"\nprice=10\n'
    )
    (tmp_path / "prices_vehicles.toml").write_text('[super]\nalpha=100\n')
    (tmp_path / "prices_weapons.toml").write_text('[pistols]\nWEAPON_TEST=10\n')
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "DATA_DIR", data)
    monkeypatch.setattr(cli, "DEFAULT_CONFIG", tmp_path / "config.toml")
    monkeypatch.setattr(cli, "VEHICLES_DB", data / "vehicles.toml")
    monkeypatch.setattr(cli, "setup_logging", Mock())
    return data


def test_list_status_and_catalog_commands(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    runner = CliRunner()
    listed = runner.invoke(cli.main, ["list"])
    assert listed.exit_code == 0
    assert "Alpha" in listed.output and "Total: 1" in listed.output
    missing = runner.invoke(cli.main, ["list", "--class", "boats"])
    assert missing.exit_code == 0 and "No vehicles found" in missing.output
    status = runner.invoke(cli.main, ["status"])
    assert status.exit_code == 0 and "Vehicle database: 1" in status.output
    output = tmp_path / "catalog.json"
    exported = runner.invoke(cli.main, ["export-catalog", "-o", str(output)])
    assert exported.exit_code == 0 and output.exists()
    assert '"model": "alpha"' in output.read_text()


def test_generate_commands(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    runner = CliRunner()
    vehicles = tmp_path / "VehicleList.cs"
    weapons = tmp_path / "WeaponList.cs"
    assert runner.invoke(cli.main, ["generate-vehiclelist", "-o", str(vehicles)]).exit_code == 0
    assert runner.invoke(cli.main, ["generate-weaponlist", "-o", str(weapons)]).exit_code == 0
    assert '"alpha"' in vehicles.read_text()
    assert '"WEAPON_TEST"' in weapons.read_text()


def test_install_command_reports_result(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    game = tmp_path / "game"
    result = InstallResult(
        game, is_enhanced=True, dll_deployed=True,
        scripthookv_found=True, shvdn_found=True, openrpf_found=True,
        battleye_status="set",
    )
    monkeypatch.setattr(cli, "install", Mock(return_value=result))
    invoked = CliRunner().invoke(cli.main, ["install"])
    assert invoked.exit_code == 0
    assert "Edition: Enhanced" in invoked.output
    assert "ALLIN1.dll deployed" in invoked.output


def test_install_command_rpf_loader_consent_modes(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    game = tmp_path / "game"
    approvals = []

    def fake_install(_config, _database, *, rpf_loader_consent):
        approvals.append(rpf_loader_consent(game, True))
        return InstallResult(game, is_enhanced=True, openrpf_found=True)

    monkeypatch.setattr(cli, "install", fake_install)
    runner = CliRunner()

    prompted = runner.invoke(cli.main, ["install"], input="y\n")
    installed = runner.invoke(
        cli.main, ["install", "--rpf-loader", "install"],
    )
    skipped = runner.invoke(cli.main, ["install", "--rpf-loader", "skip"])

    assert prompted.exit_code == installed.exit_code == skipped.exit_code == 0
    assert "Install these optional third-party dependencies?" in prompted.output
    assert "pinned RageOpenV release" in prompted.output
    assert approvals == [True, True, False]


def test_install_and_uninstall_failures_are_user_facing(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "install", Mock(side_effect=FileNotFoundError("no game")))
    failed = CliRunner().invoke(cli.main, ["install"])
    assert failed.exit_code == 1 and "no game" in failed.output
    monkeypatch.setattr(cli, "uninstall", Mock(side_effect=ValueError("bad path")))
    failed = CliRunner().invoke(cli.main, ["uninstall"])
    assert failed.exit_code == 1 and "bad path" in failed.output


def test_uninstall_command_lists_removed_files(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    removed = tmp_path / "game/scripts/ALLIN1.dll"
    monkeypatch.setattr(cli, "uninstall", Mock(return_value=[removed]))
    result = CliRunner().invoke(cli.main, ["uninstall"])
    assert result.exit_code == 0
    assert str(removed) in result.output
    assert "Uninstall complete" in result.output


def test_install_command_reports_all_missing_prerequisites(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = InstallResult(tmp_path / "game", warnings=["preview warning"])
    monkeypatch.setattr(cli, "install", Mock(return_value=result))
    output = CliRunner().invoke(cli.main, ["install"]).output
    assert "preview warning" in output
    assert "ALLIN1.dll not found" in output
    assert "ScriptHookV not found" in output
    assert "ScriptHookVDotNet not found" in output
    assert "Legacy RPF loader not detected" in output


def test_status_reports_filters_and_import_previews(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    config = Config.default()
    config.traffic.enabled = False
    config.vehicles.disabled_classes = ["boats"]
    config.vehicles.disabled_vehicles = ["alpha"]
    config.save(tmp_path / "config.toml")
    status = CliRunner().invoke(cli.main, ["--config", str(tmp_path / "config.toml"), "status"])
    assert "Traffic: disabled" in status.output
    assert "Disabled classes: boats" in status.output
    assert "Disabled vehicles: 1" in status.output

    source = tmp_path / "captures"
    source.mkdir()
    image = Image.new("RGB", (800, 450), "black")
    ImageDraw.Draw(image).rectangle((200, 100, 600, 350), fill="red")
    image.save(source / "alpha.png")
    imported = CliRunner().invoke(cli.main, ["import-previews", str(source)])
    assert imported.exit_code == 0
    assert "Imported 1" in imported.output
    with Image.open(tmp_path / "script/dist/previews/alpha.png") as packaged:
        assert packaged.size == (512, 288)

    weapon_source = tmp_path / "weapon-captures"
    weapon_source.mkdir()
    image.save(weapon_source / "weapon_test.png")
    imported = CliRunner().invoke(cli.main, [
        "import-previews", str(weapon_source), "--kind", "weapon",
    ])
    assert imported.exit_code == 0
    assert "valid weapon preview" in imported.output
    weapon_preview = tmp_path / "script/dist/weapon_previews/weapon_test.png"
    assert weapon_preview.exists()
    with Image.open(weapon_preview) as packaged:
        assert packaged.size == (512, 288)


def test_verify_preview_artifacts_success_and_failure(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    built = tmp_path / "ytd"
    built.mkdir()
    failed = CliRunner().invoke(cli.main, ["verify-preview-artifacts", str(built)])
    assert failed.exit_code == 1 and "Missing" in failed.output
    (built / "allin1_prev_01.ytd").write_bytes(b"ytd")
    passed = CliRunner().invoke(cli.main, ["verify-preview-artifacts", str(built)])
    assert passed.exit_code == 0 and "Verified 1" in passed.output


def test_analyze_client_log_command_writes_failure_report(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    log = tmp_path / "client.log"
    log.write_text('{"component":"VehicleHelper","message":"vehicle_created"}\n')
    report = tmp_path / "report.json"
    result = CliRunner().invoke(cli.main, [
        "analyze-client-log", str(log), "--edition", "legacy", "--output", str(report)
    ])
    assert result.exit_code == 1 and "FAIL" in result.output
    assert report.exists()


def test_diagnostics_command(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    output = tmp_path / "diagnostics.zip"
    result = CliRunner().invoke(cli.main, ["diagnostics", "-o", str(output)])
    assert result.exit_code == 0
    assert output.exists() and "Diagnostic bundle created" in result.output


def test_audit_previews_command_reports_failure_and_success(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    previews = tmp_path / "previews"; previews.mkdir()
    Image.new("RGB", (800, 450), "black").save(previews / "alpha.png")
    failed = CliRunner().invoke(cli.main, ["audit-previews", str(previews)])
    assert failed.exit_code == 1 and "need recapture" in failed.output
    image = Image.new("RGB", (800, 450), "black")
    ImageDraw.Draw(image).rectangle((200, 100, 600, 350), fill="red")
    image.save(previews / "alpha.png")
    passed = CliRunner().invoke(cli.main, ["audit-previews", str(previews)])
    assert passed.exit_code == 0 and "0 need recapture" in passed.output


def test_health_repair_and_qualification_commands(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    game = tmp_path / "game"; game.mkdir()
    failed = CliRunner().invoke(cli.main, ["health-check", str(game), "--json-output", str(tmp_path / "health.json")])
    assert failed.exit_code == 1 and (tmp_path / "health.json").exists()

    garage = tmp_path / "garage.json"
    garage.write_text('{"michael":[{"model":"alpha","slot":0},{"model":"bad","slot":1}]}')
    repaired = CliRunner().invoke(cli.main, ["repair-garage", str(garage)])
    assert repaired.exit_code == 0 and "quarantined 1" in repaired.output

    report = tmp_path / "qualification.json"
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 92.0}}))
    assembly = tmp_path / "ALLIN1.dll"
    _write_pe(assembly)
    source_log = tmp_path / "client.log"
    source_log.write_text("qualified session")
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({
        "schema": 2, "passed": True, "session": "session-1",
        "source_log": str(source_log.resolve()),
        "source_log_sha256": hashlib.sha256(source_log.read_bytes()).hexdigest(),
        "checks": [{"name": "session_integrity", "passed": True}],
    }))
    passed = CliRunner().invoke(cli.main, ["qualification-report", str(report),
        "--coverage-report", str(coverage), "--script-assembly", str(assembly),
        "--smoke-report", str(smoke)])
    assert passed.exit_code == 0 and "PASS" in passed.output
    coverage.write_text(json.dumps({"totals": {"percent_covered": 80.0}}))
    failed = CliRunner().invoke(cli.main, ["qualification-report", str(report),
        "--coverage-report", str(coverage), "--script-assembly", str(assembly),
        "--smoke-report", str(smoke)])
    assert failed.exit_code == 1 and "FAIL" in failed.output


def test_public_release_commands(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    archive = tmp_path / "release.zip"
    build = Mock(return_value=ReleaseReport("0.3.0", 42, 10 * 1024 * 1024, archive))
    verify = Mock(return_value=ReleaseReport("0.3.0", 42, 10 * 1024 * 1024, archive))
    monkeypatch.setattr("allin1.release.build_public_release", build)
    monkeypatch.setattr("allin1.release.verify_public_release", verify)

    built = CliRunner().invoke(cli.main, ["build-release", "--output", str(archive)])
    assert built.exit_code == 0 and "42 files" in built.output
    build.assert_called_once_with(tmp_path, archive)

    archive.write_bytes(b"zip")
    checked = CliRunner().invoke(cli.main, ["verify-release", str(archive)])
    assert checked.exit_code == 0 and "Verified ALLIN1 0.3.0" in checked.output
    verify.assert_called_once_with(archive)
