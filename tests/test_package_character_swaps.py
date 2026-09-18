"""Focused fail-closed coverage for the private exact-member packager."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("package_character_swaps",ROOT/"tools"/"package_character_swaps.py")
assert SPEC and SPEC.loader
tool=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=tool;SPEC.loader.exec_module(tool)

def test_targets_require_exact_complete_inventory(tmp_path: Path):
    path=tmp_path/"targets.json";path.write_text(json.dumps({"schema_version":1,"targets":[]}),encoding="utf-8")
    with pytest.raises(ValueError,match="exactly 50"):
        tool._targets(path)

def test_containment_rejects_source_outside_build_root(tmp_path: Path):
    root=tmp_path/"root";root.mkdir();outside=tmp_path/"outside";outside.mkdir()
    with pytest.raises(ValueError,match="escapes"):
        tool._inside(root,outside)

def test_nested_entry_contract_rejects_ambiguous_archive_path():
    with pytest.raises(ValueError):
        tool.split_nested_rpf_entry("not-an-rpf!member.bin")

def test_output_rejects_game_and_nested_build_even_when_named_packages(tmp_path):
    build = tmp_path / "build"
    game = tmp_path / "game"
    for destination in (game / "packages", build / "player_one" / "packages", tmp_path):
        with pytest.raises(ValueError):
            tool._validate_output(destination, build, game)
    tool._validate_output(build / "packages-test", build, game)

def test_preflight_requires_all_resource_hashes(tmp_path):
    build = tmp_path / "player_one"
    build.mkdir()
    (build / "report.json").write_text(json.dumps({
        "target_model": "player_one", "nonstreamed": False,
        "compiled_sha256": {}, "outputs": {},
    }))
    with pytest.raises(ValueError, match="all four"):
        tool._preflight_builds([{"model": "player_one"}], tmp_path)

def test_preflight_rejects_wrong_streamed_mode(tmp_path):
    build = tmp_path / "ig_stretch"
    build.mkdir()
    (build / "report.json").write_text(json.dumps({"target_model": "ig_stretch", "nonstreamed": True}))
    with pytest.raises(ValueError, match="streamed mode"):
        tool._preflight_builds([{"model": "ig_stretch"}], tmp_path)


@pytest.mark.parametrize("value", ("1", "1.0", "v1.0.0", "1.0.0-beta", "01.0.0", "1.0.-1"))
def test_version_rejects_non_safe_semver(value: str):
    with pytest.raises(ValueError, match="numeric x.y.z"):
        tool._version(value)


def test_version_accepts_safe_numeric_semver():
    assert tool._version("1.0.1") == "1.0.1"


def test_preflight_rejects_geometry_evidence_that_fails_even_with_matching_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    model = "player_one"
    build = tmp_path / model
    compiled = build / "authoring" / "compiled"
    authored = build / "authoring" / "authored"
    verified = build / "authoring" / "verified"
    resources = {
        "ydd": f"{model}/head_000_r.ydd", "yft": f"{model}.yft",
        "ymt": f"{model}.ymt", "ytd": "head_diff_000_a_bla.ytd",
    }
    hashes = {}
    for name in resources.values():
        path = compiled / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        hashes[name] = tool.digest(path)
    for name, root in ((resources["ydd"], "DrawableDictionary"), (resources["yft"], "Fragment")):
        for folder in (authored, verified):
            path = folder / (name + ".xml")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"<{root}/>", encoding="utf-8")
    (build / "report.json").write_text(json.dumps({
        "target_model": model, "nonstreamed": False,
        "compiled_sha256": hashes, "outputs": resources,
    }), encoding="utf-8")
    monkeypatch.setattr(tool, "verify_geometry_roundtrip", lambda *_: (_ for _ in ()).throw(
        ValueError("vertex values collapsed")))
    with pytest.raises(ValueError, match="vertex values collapsed"):
        tool._preflight_builds([{"model": model, "member_role": "head_drawable"}], tmp_path)
