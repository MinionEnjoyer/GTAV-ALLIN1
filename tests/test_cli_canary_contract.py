"""CLI review/dispatch contracts; native writers are replaced before invocation."""
import importlib
import json
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from allin1.cli import main


FAMILIES = [
    ("", "map_canary", "davis_registration_canary", ""),
    ("streaming-", "map_canary", "davis_streaming_canary", "STREAMING_"),
    ("startup-", "map_startup_canary", "davis_startup_canary", ""),
    ("stock-boot-", "map_stock_bridge_canary", "davis_stock_reference_boot_canary", ""),
    ("stock-black-", "map_stock_bridge_black_canary", "davis_stock_reference_black_transition_canary", ""),
    ("grapeseed-stock-boot-", "map_grapeseed_stock_bridge_canary", "grapeseed_stock_reference_boot_canary", ""),
    ("grapeseed-stock-black-", "map_grapeseed_stock_bridge_black_canary", "grapeseed_stock_reference_black_transition_canary", ""),
]


@pytest.mark.parametrize("prefix,module_name,stem,token_prefix", FAMILIES)
@pytest.mark.parametrize("action", ["install", "status", "rollback"])
def test_canary_cli_dispatch_and_recovery_errors(tmp_path, monkeypatch, prefix, module_name, stem, token_prefix, action):
    module = importlib.import_module("allin1." + module_name)
    if "black" in prefix and action == "install":
        action = "promote"
    function = "read_" + stem + "_status" if action == "status" else action + "_" + stem
    service = Mock(return_value={"synthetic": True, "action": action})
    monkeypatch.setattr(module, function, service)
    args = ["map-canary", prefix + action, "--gta-path", str(tmp_path)]
    kwargs = {}
    if action == "promote":
        args += ["--session", "012345abcdef"]
        kwargs["session"] = "012345abcdef"
    runner = CliRunner()
    if action != "status":
        token = getattr(module, token_prefix + action.upper() + "_CONFIRMATION")
        # Neither a matching token alone nor --yes alone grants write authority.
        for flags in ([], ["--yes"], ["--confirm-canary", token], ["--yes", "--confirm-canary", "wrong"]):
            denied = runner.invoke(main, args + flags)
            assert denied.exit_code == 1 and "requires" in denied.output
            service.assert_not_called()
        args += ["--yes", "--confirm-canary", token]
        kwargs["confirmation"] = token
    result = runner.invoke(main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"synthetic": True, "action": action}
    service.assert_called_once_with(tmp_path, **kwargs)
    for failure in (FileNotFoundError, PermissionError, RuntimeError, TypeError, ValueError):
        service.reset_mock()
        service.side_effect = failure("synthetic dependency failure")
        result = runner.invoke(main, args)
        assert result.exit_code == 1
        assert result.output.strip() == "Error: synthetic dependency failure"
        service.assert_called_once_with(tmp_path, **kwargs)
    assert list(tmp_path.iterdir()) == []
