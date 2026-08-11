"""Command-level tests for every public CLI operation."""

from pathlib import Path
from unittest.mock import Mock

from click.testing import CliRunner

from allin1 import cli
from allin1.config import Config
from allin1.installer import InstallResult


VEHICLES = '''
[[vehicles]]
model="alpha"
name="Alpha"
class="super"
manufacturer="Maker"
traffic=["veh_rich"]
'''


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
