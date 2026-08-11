"""Tests for generated C# and preview/DLC artifact pipelines."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from lxml import etree

from allin1.generators import dlc_previews, vehiclelist, weaponlist, ytd_builder
from allin1.vehicles.database import Vehicle, VehicleDatabase


def test_preview_dict_chunks_are_stable():
    models = [f"car{i:03d}" for i in range(130)]
    mapping = vehiclelist.build_preview_dict(models, textures_per_ytd=64)
    assert mapping["car000"] == "allin1_prev_01"
    assert mapping["car063"] == "allin1_prev_01"
    assert mapping["car064"] == "allin1_prev_02"
    assert mapping["car129"] == "allin1_prev_03"


def test_vehicle_generator_escapes_names_and_deduplicates():
    vehicles = [
        Vehicle("alpha", 'Maker "Alpha"', "super", "Maker", ["veh_rich"], True),
        Vehicle("alpha", "Duplicate", "super", "Maker"),
        Vehicle("beta", "Beta", "unknown", "Maker"),
    ]
    source = vehiclelist.generate(VehicleDatabase(vehicles), {"alpha": 123})
    assert 'Maker \\"Alpha\\"' in source
    assert source.count('{ "alpha", "Maker') == 1
    assert '{ "alpha", 123 }' in source
    assert 'internal static readonly string[] Weaponized' in source


def test_vehicle_generate_file(tmp_path):
    vehicles = tmp_path / "vehicles.toml"
    vehicles.write_text('[[vehicles]]\nmodel="a"\nname="A"\nclass="super"\nmanufacturer="M"\n')
    prices = tmp_path / "prices.toml"
    prices.write_text('[super]\na=42\n')
    output = tmp_path / "VehicleList.cs"
    assert vehiclelist.generate_file(vehicles, prices, output) == 1
    assert '{ "a", 42 }' in output.read_text()


def test_vehicle_generate_file_preserves_calibration_suffix(tmp_path):
    vehicles = tmp_path / "vehicles.toml"
    vehicles.write_text('[[vehicles]]\nmodel="a"\nname="A"\nclass="super"\nmanufacturer="M"\n')
    prices = tmp_path / "prices.toml"
    prices.write_text('[super]\na=42\n')
    output = tmp_path / "VehicleList.cs"
    marker = "        //  Vehicle size data (generated from HeightChecker measurements)"
    output.write_text("old generated data\n" + marker + "\n        internal static int Calibration = 1;\n    }\n}\n")

    vehiclelist.generate_file(vehicles, prices, output)

    source = output.read_text()
    assert 'internal static int Calibration = 1;' in source
    assert source.count(marker) == 1


def test_weapon_generator_and_file(tmp_path):
    weapons = tmp_path / "weapons.toml"
    weapons.write_text('[[weapons]]\nname="WEAPON_TEST"\nlabel="Test \\\"Gun\\\""\ncategory="pistols"\nprice=10\n')
    prices = tmp_path / "prices.toml"
    prices.write_text('[pistols]\nWEAPON_TEST=99\n')
    source = weaponlist.generate(weapons, {"WEAPON_TEST": 99})
    assert 'Test \\"Gun\\"' in source
    assert '{ "WEAPON_TEST", 99 }' in source
    assert '{ "WEAPON_TEST", 2 }' in source
    output = tmp_path / "WeaponList.cs"
    assert weaponlist.generate_file(weapons, prices, output) == 1


def test_run_handles_success_failure_and_crash(monkeypatch):
    monkeypatch.setattr(subprocess, "run", Mock(return_value=Mock(returncode=0, stdout="ok", stderr="")))
    ytd_builder._run(["tool"], "tool")
    subprocess.run.return_value = Mock(returncode=2, stdout="", stderr="bad")
    with pytest.raises(RuntimeError, match="tool failed"):
        ytd_builder._run(["tool"], "tool")
    subprocess.run.return_value = Mock(returncode=0, stdout="", stderr="Unhandled exception")
    with pytest.raises(RuntimeError, match="tool crashed"):
        ytd_builder._run(["tool"], "tool")


def test_build_ytd_files_chunks_and_cleans_temp(tmp_path, monkeypatch):
    previews = tmp_path / "previews"
    previews.mkdir()
    for model in ("a", "b", "c"):
        (previews / f"{model}.png").write_bytes(b"png")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"logo")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "YTDToolio.exe").touch()

    def fake_pack(_png, output, _tool):
        output.write_bytes(b"ytd")
    monkeypatch.setattr(ytd_builder, "_pack_ytd", fake_pack)
    output = tmp_path / "out"
    files = ytd_builder.build_ytd_files(previews, logo, output, tools, ["c", "a", "b"], 2)
    assert [p.name for p in files] == ["allin1_prev_01.ytd", "allin1_prev_02.ytd", "allin1_logo.ytd"]
    assert not list(output.glob("_tmp_*"))


def test_build_ytd_requires_tool(tmp_path):
    with pytest.raises(FileNotFoundError, match="YTDToolio"):
        ytd_builder.build_ytd_files(tmp_path, None, tmp_path / "out", tmp_path, [])


def test_build_ytd_keeps_catalog_chunk_numbers_when_previews_are_missing(tmp_path, monkeypatch):
    previews = tmp_path / "previews"
    previews.mkdir()
    (previews / "c.png").write_bytes(b"png")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "YTDToolio.exe").touch()
    monkeypatch.setattr(ytd_builder, "_pack_ytd",
                        lambda _source, output, _tool: output.write_bytes(b"ytd"))

    files = ytd_builder.build_ytd_files(
        previews, None, tmp_path / "out", tools, ["a", "b", "c"], 2
    )

    assert [path.name for path in files] == ["allin1_prev_02.ytd"]


def test_build_ytd_recovers_tool_output_from_alternate_location(tmp_path, monkeypatch):
    previews = tmp_path / "previews"
    previews.mkdir()
    (previews / "a.png").write_bytes(b"png")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "YTDToolio.exe").touch()

    def misplaced(source, _output, _tool):
        (source / "allin1_prev_01.ytd").write_bytes(b"ytd")
    monkeypatch.setattr(ytd_builder, "_pack_ytd", misplaced)
    files = ytd_builder.build_ytd_files(previews, None, tmp_path / "out", tools, ["a"])
    assert files[0].read_bytes() == b"ytd"


def test_build_ytd_raises_when_tool_reports_success_without_output(tmp_path, monkeypatch):
    previews = tmp_path / "previews"
    previews.mkdir()
    (previews / "a.png").write_bytes(b"png")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "YTDToolio.exe").touch()
    monkeypatch.setattr(ytd_builder, "_pack_ytd", lambda *_args: None)
    with pytest.raises(FileNotFoundError, match="was not created"):
        ytd_builder.build_ytd_files(previews, None, tmp_path / "out", tools, ["a"])


def test_dlc_metadata_staging_deploy_and_remove(tmp_path):
    ytd = tmp_path / "preview.ytd"
    ytd.write_bytes(b"texture")
    root, staging = dlc_previews.create_dlc_pack([ytd], tmp_path / "build")
    content = etree.parse(str(root / "content.xml"))
    assert content.findtext(".//fileType") == "RPF_FILE"
    assert (staging / ytd.name).read_bytes() == b"texture"
    rpf = tmp_path / "dlc.rpf"
    rpf.write_bytes(b"rpf")
    game = tmp_path / "game"
    old = game / "update/x64/dlcpacks/allin1_previews"
    old.mkdir(parents=True)
    destination = dlc_previews.deploy_dlc_rpf(rpf, game)
    assert (destination / "dlc.rpf").read_bytes() == b"rpf"
    assert not old.exists()
    assert dlc_previews.remove_dlc_pack(game) is True
    assert dlc_previews.remove_dlc_pack(game) is False


def test_dlc_deploy_preserves_backup_and_rolls_back_on_failure(tmp_path, monkeypatch):
    game = tmp_path / "game"
    dest = game / "mods/update/x64/dlcpacks/allin1_previews/dlc.rpf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old")
    built = tmp_path / "new.rpf"
    built.write_bytes(b"new")
    dlc_previews.deploy_dlc_rpf(built, game)
    assert dest.read_bytes() == b"new"
    assert (dest.parent / "dlc.rpf.bak").read_bytes() == b"old"

    built.write_bytes(b"newer")
    monkeypatch.setattr(Path, "replace", lambda *_a: (_ for _ in ()).throw(OSError("locked")))
    with pytest.raises(OSError, match="locked"):
        dlc_previews.deploy_dlc_rpf(built, game)
    assert dest.read_bytes() == b"new"
