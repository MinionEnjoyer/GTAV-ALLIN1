import json
from pathlib import Path

from tools.build_reactor_consumer_ui import allowed_asset


def test_only_known_noninteractive_hud_contract_is_allowed(tmp_path):
    path = tmp_path / "reactor-fpv-hud-v1.json"
    contract = dict(schema_version=1, component="reactor-fpv-hud", transport="hud.frame",
                    frame_kind="speedometer", fpv_schema=1, interactive=False)
    path.write_text(json.dumps(contract), encoding="utf-8")
    assert allowed_asset(path, Path(path.name))
    assert not allowed_asset(path, Path("other.json"))
    assert not allowed_asset(path, Path("nested") / path.name)
    contract["interactive"] = True
    path.write_text(json.dumps(contract), encoding="utf-8")
    assert not allowed_asset(path, Path(path.name))
    path.write_text("not-json", encoding="utf-8")
    assert not allowed_asset(path, Path(path.name))


def test_presentation_asset_size_and_type_remain_bounded(tmp_path):
    path = tmp_path / "asset.js"
    path.write_bytes(b"safe")
    assert allowed_asset(path, Path(path.name))
    path.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    assert not allowed_asset(path, Path(path.name))
    binary = tmp_path / "plugin.dll"
    binary.write_bytes(b"MZ")
    assert not allowed_asset(binary, Path(binary.name))
