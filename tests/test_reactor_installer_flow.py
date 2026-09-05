from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from allin1 import cli, installer
from allin1.config import Config
from allin1 import reactor_dependency as dep


@pytest.mark.parametrize("backend,approved", [("reactor", False), ("reactor", True), ("auto", True)])
def test_dependency_rejection_precedes_all_game_mutation(tmp_path, monkeypatch, backend, approved):
    (tmp_path / "GTA5.exe").touch()
    config = Config.default()
    config.general.gta_path = str(tmp_path)
    config.script.gbay_ui_backend = backend
    cleanup = Mock()
    deploy = Mock()
    monkeypatch.setattr(installer, "_clean_legacy_files", cleanup)
    monkeypatch.setattr(installer, "_deploy_script", deploy)
    monkeypatch.setattr(installer, "validate_reactor_bridge_pair", Mock())
    monkeypatch.setattr(dep, "install_dependency", Mock(side_effect=dep.ReactorInstallError("unsupported game")))
    with pytest.raises(dep.ReactorInstallError):
        installer.install(config, Mock(), reactor_consent=lambda *_: approved)
    cleanup.assert_not_called()
    deploy.assert_not_called()
    # conftest redirects the launcher's path cache into this same temporary
    # directory. Selecting a game may update that cache, not the game payload.
    assert {p.name for p in tmp_path.iterdir()} <= {"GTA5.exe", ".gta_path"}
    assert not (tmp_path / "scripts").exists()


@pytest.mark.parametrize("mode,answer,expected", [("install", None, True), ("skip", None, False), ("ask", "y\n", True), ("ask", "n\n", False)])
def test_cli_reactor_consent_is_explicit(tmp_path, monkeypatch, mode, answer, expected):
    monkeypatch.setattr(cli, "setup_logging", Mock())
    monkeypatch.setattr(cli.VehicleDatabase, "load", Mock(return_value=[]))
    observed = []
    def fake_install(config, db, **kwargs):
        observed.append(kwargs["reactor_consent"](tmp_path, False))
        return installer.InstallResult(tmp_path)
    monkeypatch.setattr(cli, "install", fake_install)
    result = CliRunner().invoke(cli.main, ["--config", str(tmp_path / "config.toml"), "install", "--reactor", mode, "--rpf-loader", "skip"], input=answer)
    assert result.exit_code == 0, result.output
    assert observed == [expected]
    if mode != "ask":
        assert "Download and install" not in result.output


def test_cli_dependency_failure_has_distinct_batch_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "setup_logging", Mock())
    monkeypatch.setattr(cli.VehicleDatabase, "load", Mock(return_value=[]))
    monkeypatch.setattr(cli, "install", Mock(side_effect=dep.ReactorInstallError("unsupported executable")))
    result = CliRunner().invoke(cli.main, ["--config", str(tmp_path / "config.toml"), "install", "--reactor", "install"])
    assert result.exit_code == 3
    assert "unsupported executable" in result.output
    batch = (Path(__file__).resolve().parents[1] / "install.bat").read_text()
    assert batch.count("if errorlevel 3 goto :dependency_failure") == 2


def test_manager_forwards_reactor_consent(tmp_path):
    from allin1.manager import ModManager
    from unittest.mock import patch
    manager = ModManager(tmp_path)
    callback = Mock(return_value=True)
    with patch.object(manager, "save_config"), patch.object(manager, "_install", return_value="ok") as deploy, patch("allin1.manager.VehicleDatabase.load", return_value="database"):
        assert manager.install(Config.default(), reactor_consent=callback) == "ok"
    assert deploy.call_args.kwargs["reactor_consent"] is callback
