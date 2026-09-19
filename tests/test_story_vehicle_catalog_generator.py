"""Behavior tests for the standalone trusted story-vehicle catalog generator."""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from allin1.generators import story_vehicle_catalog as generator


def test_extract_base_vehicle_meta_returns_only_the_inspected_section(tmp_path, monkeypatch):
    game = tmp_path / "game"
    archive = game / "update" / "update.rpf"
    marker = str(archive / "common" / "data" / "levels" / "gta5" / "vehicles.meta").replace("/", "\\").casefold()
    output = "\n".join((
        "--- unrelated",
        "ignore this",
        "--- " + marker,
        "<CVehicleModelInfo__InitDataList />",
        "--- next section",
        "ignore this too",
    ))
    calls = []

    def inspect(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(generator.subprocess, "run", inspect)
    assert generator.extract_base_vehicle_meta(tmp_path / "RpfPatcher.exe", game) == "<CVehicleModelInfo__InitDataList />"
    assert calls[0][0][1] == "inspect"
    assert calls[0][1]["check"] is True


def test_extract_base_vehicle_meta_rejects_inspection_without_vehicle_section(tmp_path, monkeypatch):
    monkeypatch.setattr(generator.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout="--- other"))
    with pytest.raises(ValueError, match="Could not locate"):
        generator.extract_base_vehicle_meta(tmp_path / "RpfPatcher.exe", tmp_path / "game")


def test_generator_main_writes_the_catalog_from_resolved_inputs(tmp_path, monkeypatch, capsys):
    game = tmp_path / "game"
    output = tmp_path / "generated" / "story.json"
    observed = {}
    monkeypatch.setattr(generator, "extract_base_vehicle_meta", lambda patcher, gta: observed.update(patcher=patcher, gta=gta) or "<xml />")
    monkeypatch.setattr(generator, "build_story_catalog", lambda xml: {"vehicles": [{"model": "adder"}]})
    monkeypatch.setattr(sys, "argv", ["generate", str(game), str(output)])

    generator.main()

    assert observed == {"patcher": (Path("tools/RpfPatcher/RpfPatcher.exe")).resolve(), "gta": game.resolve()}
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert "Generated 1 Story vehicle listings" in capsys.readouterr().out
