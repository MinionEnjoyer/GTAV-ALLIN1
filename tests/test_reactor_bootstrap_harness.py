from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "reactor_bootstrap_harness.py"


def test_developer_harness_self_check_covers_visual_contract():
    namespace = runpy.run_path(str(HARNESS), run_name="reactor_harness_test")

    result = namespace["self_check"]()

    assert result["ok"] is True
    assert all(result["checks"].values())


def test_developer_harness_does_not_register_shipping_test_hotkeys():
    source = HARNESS.read_text(encoding="utf-8")

    assert "bind_all" not in source
    assert "<F10>" not in source
    assert "<F11>" not in source
    assert "<F12>" not in source
