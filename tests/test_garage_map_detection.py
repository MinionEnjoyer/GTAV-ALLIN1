from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from allin1.garage_map_detection import (
    CACHE_RELATIVE_PATH,
    MAX_DESCRIPTOR_BYTES,
    MAX_MAPPINGS_TOTAL,
    _cached_projects_match,
    _write_envelope,
    refresh_garage_map_detection,
)
from allin1.installer import _ensure_full_mods_update_archive


REQUESTED = "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_"
RENAMED = "tr_int_placement_tr_interior_1_tuner_mod_garage_milo_"


def _game(tmp_path: Path, *, requested: str = REQUESTED):
    game = tmp_path / "Grand Theft Auto V Enhanced"
    (game / "GTA5_Enhanced.exe").parent.mkdir(parents=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"game")
    source = game / "update/x64/dlcpacks/mptuner/dlc.rpf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"rpf")
    descriptor = game / (
        "scripts/ALLIN1/Maps/allin1.online-content/davis.maps.json"
    )
    descriptor.parent.mkdir(parents=True)
    descriptor_payload = {
        "schema_version": 1,
        "id": "davis-auto-shop",
        "editions": ["legacy", "enhanced"],
        "streaming": {
            "mode": "ipl", "pack_name": "mptuner", "ipls": [requested],
        },
        "levels": [{"id": "davis", "ipls": [requested]}],
    }
    descriptor.write_text(json.dumps(descriptor_payload), encoding="utf-8")
    digest = hashlib.sha256(descriptor.read_bytes()).hexdigest()
    registry = game / "scripts/.allin1/extensions/registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({
        "schema_version": 1,
        "extensions": [{
            "id": "allin1.online-content",
            "enabled": True,
            "map_files": [{
                "path": descriptor.relative_to(game).as_posix(),
                "sha256": digest,
            }],
        }],
    }), encoding="utf-8")
    patcher = tmp_path / "tools/RpfPatcher/RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.write_bytes(b"patcher")
    return game, descriptor, patcher


def _runner(stems: list[str], calls: list[list[str]]):
    def run(command, **_kwargs):
        calls.append([str(item) for item in command])
        output = Path(command[-1])
        entries = [{
            "id": f"x64/levels/interiors.rpf::{stem}.ymap",
            "archive_path": "x64/levels/interiors.rpf",
            "path": f"{stem}.ymap",
            "name": f"{stem}.ymap",
            "kind": "resource",
        } for stem in stems]
        output.write_text(json.dumps({
            "schema_version": 1,
            "source": r"C:\Users\developer\private\mptuner\dlc.rpf",
            "entries": entries,
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


def _payload(game: Path) -> tuple[dict, dict]:
    cache = game / Path(*CACHE_RELATIVE_PATH.parts)
    envelope = json.loads(cache.read_text(encoding="utf-8"))
    payload_json = envelope["payload_json"]
    assert envelope["payload_sha256"] == hashlib.sha256(
        payload_json.encode("utf-8")
    ).hexdigest()
    return envelope, json.loads(payload_json)


def _replace_descriptor_ipls(
    game: Path, descriptor: Path, requested: list[str],
) -> None:
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    payload["streaming"]["ipls"] = requested
    payload["levels"][0]["ipls"] = requested
    descriptor.write_text(json.dumps(payload), encoding="utf-8")
    registry_path = game / "scripts/.allin1/extensions/registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["extensions"][0]["map_files"][0]["sha256"] = hashlib.sha256(
        descriptor.read_bytes()
    ).hexdigest()
    registry_path.write_text(json.dumps(registry), encoding="utf-8")


def test_refresh_verifies_exact_ipl_and_reuses_unchanged_cache(tmp_path: Path):
    game, _descriptor, patcher = _game(tmp_path)
    calls: list[list[str]] = []
    first = refresh_garage_map_detection(
        game, patcher=patcher, runner=_runner([REQUESTED], calls),
    )
    second = refresh_garage_map_detection(
        game, patcher=patcher,
        runner=lambda *_args, **_kwargs: pytest.fail("cache hit re-indexed the RPF"),
    )

    assert not first.cache_hit
    assert second.cache_hit
    assert len(calls) == 1
    envelope, payload = _payload(game)
    project = payload["projects"][0]
    assert project["status"] == "verified"
    assert project["ipl_mappings"] == [{
        "archive_path": "x64/levels/interiors.rpf",
        "entry_path": f"{REQUESTED}.ymap",
        "match": "exact",
        "requested": REQUESTED,
        "resolved": REQUESTED,
        "source_rpf": "update/x64/dlcpacks/mptuner/dlc.rpf",
    }]
    serialized = json.dumps(envelope)
    assert "developer" not in serialized
    assert str(game) not in serialized


def test_refresh_accepts_only_one_high_confidence_semantic_name(tmp_path: Path):
    game, _descriptor, patcher = _game(tmp_path)
    result = refresh_garage_map_detection(
        game, patcher=patcher, runner=_runner([RENAMED], []),
    )
    _, payload = _payload(game)
    mapping = payload["projects"][0]["ipl_mappings"][0]
    assert result.verified_projects == 1
    assert mapping["match"] == "semantic_unique"
    assert mapping["resolved"] == RENAMED


def test_refresh_indexes_enhanced_split_dlc_archives(tmp_path: Path):
    game, _descriptor, patcher = _game(tmp_path)
    (game / "update/x64/dlcpacks/mptuner/dlc1.rpf").write_bytes(b"map split")
    calls: list[str] = []

    def runner(command, **_kwargs):
        source = Path(command[3])
        calls.append(source.name)
        stems = [REQUESTED] if source.name.casefold() == "dlc1.rpf" else []
        entries = [{
            "archive_path": "x64/levels/interiors.rpf",
            "path": f"{stem}.ymap",
            "name": f"{stem}.ymap",
        } for stem in stems]
        Path(command[-1]).write_text(json.dumps({
            "schema_version": 1, "entries": entries,
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    refresh_garage_map_detection(game, patcher=patcher, runner=runner)
    _, payload = _payload(game)

    assert calls == ["dlc.rpf", "dlc1.rpf"]
    mapping = payload["projects"][0]["ipl_mappings"][0]
    assert mapping["source_rpf"].endswith("/mptuner/dlc1.rpf")


def test_refresh_resolves_partial_mod_overlay_per_root_archive_sibling(
    tmp_path: Path,
):
    game, _descriptor, patcher = _game(tmp_path)
    (game / "update/x64/dlcpacks/mptuner/dlc1.rpf").write_bytes(
        b"stock split",
    )
    overlay = game / "mods/update/x64/dlcpacks/mptuner/dlc.rpf"
    overlay.parent.mkdir(parents=True)
    overlay.write_bytes(b"mod primary")
    calls: list[str] = []

    def runner(command, **_kwargs):
        source = Path(command[3])
        calls.append(source.relative_to(game).as_posix())
        stems = [REQUESTED] if source.name.casefold() == "dlc1.rpf" else []
        Path(command[-1]).write_text(json.dumps({
            "schema_version": 1,
            "entries": [{
                "archive_path": "x64/levels/interiors.rpf",
                "path": f"{stem}.ymap",
                "name": f"{stem}.ymap",
            } for stem in stems],
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    refresh_garage_map_detection(game, patcher=patcher, runner=runner)
    _, payload = _payload(game)

    assert calls == [
        "mods/update/x64/dlcpacks/mptuner/dlc.rpf",
        "update/x64/dlcpacks/mptuner/dlc1.rpf",
    ]
    mapping = payload["projects"][0]["ipl_mappings"][0]
    assert mapping["source_rpf"] == (
        "update/x64/dlcpacks/mptuner/dlc1.rpf"
    )
    assert payload["projects"][0]["source"]["archive_path"] == (
        "mods/update/x64/dlcpacks/mptuner/dlc.rpf"
    )


def test_refresh_fails_closed_when_exact_ipl_exists_in_two_effective_siblings(
    tmp_path: Path,
):
    game, _descriptor, patcher = _game(tmp_path)
    (game / "update/x64/dlcpacks/mptuner/dlc1.rpf").write_bytes(
        b"split duplicate",
    )

    result = refresh_garage_map_detection(
        game, patcher=patcher, runner=_runner([REQUESTED], []),
    )
    _, payload = _payload(game)

    project = payload["projects"][0]
    assert result.unresolved_projects == 1
    assert project["status"] == "unresolved"
    assert project["ipl_mappings"] == []


def test_cache_invalidates_when_mod_overlay_appears_changes_and_disappears(
    tmp_path: Path,
):
    game, _descriptor, patcher = _game(tmp_path)
    overlay = game / "mods/update/x64/dlcpacks/mptuner/dlc.rpf"
    indexed_sources: list[str] = []

    def runner(command, **_kwargs):
        source = Path(command[3])
        indexed_sources.append(source.relative_to(game).as_posix())
        Path(command[-1]).write_text(json.dumps({
            "schema_version": 1,
            "entries": [{
                "archive_path": "x64/levels/interiors.rpf",
                "path": f"{REQUESTED}.ymap",
                "name": f"{REQUESTED}.ymap",
            }],
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    stock = refresh_garage_map_detection(
        game, patcher=patcher, runner=runner,
    )
    assert not stock.cache_hit
    assert indexed_sources[-1].startswith("update/")

    overlay.parent.mkdir(parents=True)
    overlay.write_bytes(b"overlay-v1")
    appeared = refresh_garage_map_detection(
        game, patcher=patcher, runner=runner,
    )
    assert not appeared.cache_hit
    assert indexed_sources[-1].startswith("mods/update/")

    cached = refresh_garage_map_detection(
        game, patcher=patcher,
        runner=lambda *_args, **_kwargs: pytest.fail(
            "unchanged overlay re-indexed the RPF"
        ),
    )
    assert cached.cache_hit

    overlay.write_bytes(b"overlay-version-two")
    changed = refresh_garage_map_detection(
        game, patcher=patcher, runner=runner,
    )
    assert not changed.cache_hit
    assert indexed_sources[-1].startswith("mods/update/")

    overlay.unlink()
    disappeared = refresh_garage_map_detection(
        game, patcher=patcher, runner=runner,
    )
    assert not disappeared.cache_hit
    assert indexed_sources[-1].startswith("update/")


@pytest.mark.parametrize(
    "archive_path, expected_suffix",
    [
        ("", "update/x64/dlcpacks/mptuner/dlc.rpf"),
        (
            "x64/levels/interiors.rpf!nested/maps.rpf",
            "x64/levels/interiors.rpf!nested/maps.rpf",
        ),
    ],
)
def test_refresh_normalizes_root_and_accepts_safe_nested_virtual_archives(
    tmp_path: Path, archive_path: str, expected_suffix: str,
):
    game, _descriptor, patcher = _game(tmp_path)

    def runner(command, **_kwargs):
        Path(command[-1]).write_text(json.dumps({
            "schema_version": 1,
            "entries": [{
                "archive_path": archive_path,
                "path": f"maps/{REQUESTED}.ymap",
                "name": f"{REQUESTED}.ymap",
            }],
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    refresh_garage_map_detection(game, patcher=patcher, runner=runner)
    _, payload = _payload(game)

    mapping = payload["projects"][0]["ipl_mappings"][0]
    assert mapping["archive_path"] == expected_suffix


def test_refresh_fails_project_closed_when_two_names_resolve_to_one_placement(
    tmp_path: Path,
):
    second = "tr_int_placement_tr_interior_9_tuner_mod_garage_milo_"
    game, descriptor, patcher = _game(tmp_path)
    _replace_descriptor_ipls(game, descriptor, [REQUESTED, second])

    result = refresh_garage_map_detection(
        game, patcher=patcher, runner=_runner([RENAMED], []),
    )
    _, payload = _payload(game)

    assert result.unresolved_projects == 1
    assert payload["projects"][0]["status"] == "unresolved"
    assert payload["projects"][0]["ipl_mappings"] == []


def test_cached_contract_rejects_more_than_1024_total_mappings():
    requested = [f"map_{index:02d}" for index in range(64)]
    expected = []
    cached = []
    for project_index in range(MAX_MAPPINGS_TOTAL // len(requested) + 1):
        project_id = f"project-{project_index:02d}"
        expected.append({
            "id": project_id,
            "descriptor_sha256": "a" * 64,
            "pack_name": f"pack_{project_index:02d}",
            "ipls": tuple(requested),
        })
        cached.append({
            "id": project_id,
            "descriptor_sha256": "a" * 64,
            "pack_name": f"pack_{project_index:02d}",
            "status": "verified",
            "source": {
                "archive_path": (
                    f"update/x64/dlcpacks/pack_{project_index:02d}/dlc.rpf"
                ),
                "size": 1,
                "mtime_ns": 1,
            },
            "ipl_mappings": [{
                "requested": name,
                "resolved": f"{name}_{project_index:02d}",
                "match": "semantic_unique",
                "archive_path": "x64/maps.rpf",
                "entry_path": f"{name}.ymap",
            } for name in requested],
        })

    assert not _cached_projects_match(cached, expected)


def test_envelope_larger_than_one_megabyte_is_not_written(tmp_path: Path):
    destination = tmp_path / "runtime-detected.json"
    with pytest.raises(ValueError, match="1 MiB"):
        _write_envelope(
            {"padding": "x" * MAX_DESCRIPTOR_BYTES}, destination,
        )
    assert not destination.exists()


def test_refresh_fails_closed_when_semantic_match_is_ambiguous(tmp_path: Path):
    game, _descriptor, patcher = _game(tmp_path)
    other = "tr_int_placement_tr_interior_2_tuner_mod_garage_milo_"
    result = refresh_garage_map_detection(
        game, patcher=patcher, runner=_runner([RENAMED, other], []),
    )
    _, payload = _payload(game)
    project = payload["projects"][0]
    assert result.unresolved_projects == 1
    assert project["status"] == "unresolved"
    assert project["ipl_mappings"] == []


def test_refresh_rejects_descriptor_that_no_longer_matches_registry(tmp_path: Path):
    game, descriptor, patcher = _game(tmp_path)
    descriptor.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="failed its registry hash"):
        refresh_garage_map_detection(
            game, patcher=patcher,
            runner=lambda *_args, **_kwargs: pytest.fail("tampered map was indexed"),
        )


def test_full_mods_archive_creation_returns_created_state(tmp_path: Path):
    stock = tmp_path / "update/update.rpf"
    stock.parent.mkdir(parents=True)
    stock.write_bytes(b"complete-stock-update")

    archive, created = _ensure_full_mods_update_archive(tmp_path)

    assert created is True
    assert archive == tmp_path / "mods/update/update.rpf"
    assert archive.read_bytes() == stock.read_bytes()
