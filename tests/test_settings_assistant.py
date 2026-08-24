from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from allin1 import cli
import allin1.settings_assistant as settings_contract
from allin1.extensions import ExtensionManifest, ExtensionRegistry
from allin1.settings_assistant import (
    PROPOSAL_KIND,
    StaleSettingsProposal,
    apply_settings_proposal,
    build_settings_catalog,
    build_settings_request,
    preview_settings_proposal,
    validate_settings_proposal,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def gta_v_fpv_install(tmp_path: Path) -> tuple[Path, Path]:
    """Portable shape-equivalent fixture for GTA-V-FPV's real 87 settings."""
    game = tmp_path / "Grand Theft Auto V Enhanced"
    package = game / "scripts" / "GTA-V-FPV"
    package.mkdir(parents=True)
    dll = b"GTA-V-FPV managed runtime fixture"
    descriptor_bytes = b"GTA-V-FPV descriptor fixture"
    (package / "GTA-V-FPV.dll").write_bytes(dll)
    (package / "allin1.content.json").write_bytes(descriptor_bytes)

    settings: list[dict[str, object]] = []
    settings.extend({
        "key": f"boolean_{index:02d}", "label": f"Boolean {index}",
        "type": "boolean", "default": bool(index % 2),
    } for index in range(19))
    settings.extend({
        "key": f"choice_{index:02d}", "label": f"Choice {index}",
        "type": "choice", "default": "balanced",
        "choices": ["cinematic", "balanced", "responsive"],
    } for index in range(36))
    settings.extend({
        "key": f"integer_{index:02d}", "label": f"Integer {index}",
        "type": "integer", "default": 5, "minimum": 0, "maximum": 10,
    } for index in range(4))
    settings.extend({
        "key": f"number_{index:02d}", "label": f"Number {index}",
        "type": "number", "default": 1.0, "minimum": 0.0, "maximum": 2.0,
        "step": 0.05,
    } for index in range(28))
    assert len(settings) == 87
    systems = []
    for index in range(8):
        start = index * 11
        end = 87 if index == 7 else start + 11
        systems.append({
            "id": f"fpv-system-{index}", "name": f"FPV System {index}",
            "category": "Flight", "settings": settings[start:end],
        })
    extension = {
        "schema_version": 1, "api_version": 1, "id": "gta-v-fpv",
        "name": "GTA-V-FPV", "version": "0.1.0",
        "description": "87-setting integration fixture",
        "capabilities": ["launcher.settings", "flight.fpv"],
        "systems": systems, "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": [{
            "path": "scripts/GTA-V-FPV/GTA-V-FPV.dll",
            "entry_point": "GTAVFPV.FpvDroneController",
        }]},
    }
    receipt = {
        "schema_version": 2, "id": "gta-v-fpv", "name": "GTA-V-FPV",
        "version": "0.1.0", "enabled": True, "requires": [],
        "extension": extension,
        "files": [
            {"destination": "scripts/GTA-V-FPV/GTA-V-FPV.dll", "sha256": _sha256(dll)},
            {"destination": "scripts/GTA-V-FPV/allin1.content.json", "sha256": _sha256(descriptor_bytes)},
        ],
    }
    receipt_path = game / "scripts" / ".allin1" / "mods" / "gta-v-fpv.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return game, receipt_path


def _proposal(game: Path, **change: object) -> dict[str, object]:
    catalog = build_settings_catalog(game, "gta-v-fpv")
    return {
        "schema_version": 1,
        "kind": PROPOSAL_KIND,
        "package_id": "gta-v-fpv",
        "basis": catalog["basis"],
        "changes": [{
            "setting_id": change.get("setting_id", "number_00"),
            "value": change.get("value", 1.5),
            "reason": "Tune the requested flight feel.",
        }],
        "summary": "One advisory FPV tuning change.",
    }


def test_gta_v_fpv_catalog_has_87_typed_settings_and_receipt_state(
    gta_v_fpv_install: tuple[Path, Path],
) -> None:
    game, receipt = gta_v_fpv_install
    catalog = build_settings_catalog(game, "gta-v-fpv")

    assert catalog["package"] == {
        "id": "gta-v-fpv", "name": "GTA-V-FPV", "version": "0.1.0",
        "source": "package", "blocked_reason": "",
    }
    assert catalog["setting_count"] == 87
    assert len(catalog["settings"]) == 87
    assert catalog["basis"]["receipt_sha256"] == _sha256(receipt.read_bytes())
    assert catalog["basis"]["receipt_enabled"] is True
    assert catalog["basis"]["effective_enabled"] is True
    assert catalog["choice_sets"]
    assert all(
        "enum_ref" in item
        for item in catalog["settings"] if item["type"] == "choice"
    )
    assert all(len(catalog["basis"][key]) == 64 for key in (
        "catalog_sha256", "settings_sha256", "installed_files_sha256",
    ))
    assert {item["type"] for item in catalog["settings"]} == {
        "boolean", "choice", "integer", "number",
    }


def test_portable_fixture_records_the_inspected_source_and_install_contract() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "gta-v-fpv-settings-summary.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["package_id"] == "gta-v-fpv"
    assert fixture["receipt_enabled"] is True
    assert fixture["system_count"] == 8
    assert fixture["setting_count"] == 87
    assert fixture["type_counts"] == {
        "boolean": 19, "choice": 36, "integer": 4, "number": 28,
    }
    assert fixture["source_descriptor_sha256"] == fixture["receipt_files"][1]["sha256"]


def test_request_contains_only_intent_catalog_and_typed_output_contract(
    gta_v_fpv_install: tuple[Path, Path],
) -> None:
    game, _ = gta_v_fpv_install
    request = build_settings_request(
        game, "gta-v-fpv", "Make the drone more cinematic without changing controls.",
    )
    assert request["advisory_only"] is True
    assert request["operation"] == "propose_settings_diff"
    assert request["intent"].startswith("Make the drone")
    assert request["catalog"]["setting_count"] == 87
    assert request["required_output"]["kind"] == PROPOSAL_KIND
    assert set(request) == {
        "schema_version", "kind", "operation", "advisory_only", "intent",
        "catalog", "required_output",
    }


@pytest.mark.parametrize("setting_id,value,message", [
    ("invented", 1, "Unknown setting"),
    ("boolean_00", 1, "true or false"),
    ("integer_00", 11, "at most"),
    ("choice_00", "turbo", "one of"),
    ("number_00", 1.0, "already has"),
])
def test_proposal_deterministically_rejects_ids_types_ranges_and_enums(
    gta_v_fpv_install: tuple[Path, Path], setting_id: str, value: object,
    message: str,
) -> None:
    game, _ = gta_v_fpv_install
    with pytest.raises(ValueError, match=message):
        validate_settings_proposal(
            game, _proposal(game, setting_id=setting_id, value=value),
        )


def test_preview_never_writes_and_apply_requires_explicit_authorization(
    gta_v_fpv_install: tuple[Path, Path],
) -> None:
    game, _ = gta_v_fpv_install
    proposal = _proposal(game)
    settings_path = game / "scripts" / ".allin1" / "extensions" / "settings.json"
    before = settings_path.read_bytes() if settings_path.is_file() else None

    preview = preview_settings_proposal(game, proposal)

    assert preview["requires_explicit_apply"] is True
    assert preview["changes"][0]["before"] == 1.0
    assert preview["changes"][0]["after"] == 1.5
    assert (settings_path.read_bytes() if settings_path.is_file() else None) == before
    with pytest.raises(PermissionError, match="exact preview proposal_id"):
        apply_settings_proposal(game, proposal, confirmed_proposal_id=None)

    result = apply_settings_proposal(
        game, proposal, confirmed_proposal_id=preview["proposal_id"],
    )
    assert result["applied"] is True
    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert stored["extensions"]["gta-v-fpv"]["number_00"] == 1.5


@pytest.mark.parametrize("drift", ["receipt", "settings", "file"])
def test_apply_rejects_stale_receipt_settings_or_installed_file_hashes(
    gta_v_fpv_install: tuple[Path, Path], drift: str,
) -> None:
    game, receipt = gta_v_fpv_install
    proposal = _proposal(game)
    proposal_id = preview_settings_proposal(game, proposal)["proposal_id"]
    if drift == "receipt":
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["enabled"] = False
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        runtime = game / "scripts" / "GTA-V-FPV" / "GTA-V-FPV.dll"
        runtime.replace(runtime.with_name(runtime.name + ".disabled"))
        descriptor = game / "scripts" / "GTA-V-FPV" / "allin1.content.json"
        descriptor.replace(descriptor.with_name(descriptor.name + ".disabled"))
    elif drift == "settings":
        settings = game / "scripts" / ".allin1" / "extensions" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({
            "schema_version": 1,
            "extensions": {"gta-v-fpv": {"number_01": 1.25}},
        }), encoding="utf-8")
    else:
        (game / "scripts" / "GTA-V-FPV" / "allin1.content.json").write_bytes(b"drift")

    with pytest.raises(StaleSettingsProposal, match="generate a new"):
        apply_settings_proposal(
            game, proposal, confirmed_proposal_id=proposal_id,
        )


def test_validated_proposal_id_covers_typed_contents(
    gta_v_fpv_install: tuple[Path, Path],
) -> None:
    game, _ = gta_v_fpv_install
    validated = validate_settings_proposal(game, _proposal(game))
    serialized = validated.to_dict()
    assert len(serialized["proposal_id"]) == 64
    assert validate_settings_proposal(game, serialized).proposal_id == serialized["proposal_id"]
    serialized["changes"][0]["value"] = 1.6
    with pytest.raises(ValueError, match="proposal_id"):
        validate_settings_proposal(game, serialized)


def test_launcher_cli_always_previews_and_binds_apply_to_proposal_id(
    gta_v_fpv_install: tuple[Path, Path], tmp_path: Path, monkeypatch,
) -> None:
    game, _ = gta_v_fpv_install
    proposal_path = tmp_path / "fpv-proposal.json"
    proposal_path.write_text(json.dumps(_proposal(game)), encoding="utf-8")
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    runner = CliRunner()

    previewed = runner.invoke(cli.main, [
        "content", "settings-preview", str(proposal_path), "--gta-path", str(game),
    ])
    assert previewed.exit_code == 0, previewed.output
    preview = json.loads(previewed.output[previewed.output.index("{"):])
    assert preview["requires_explicit_apply"] is True

    generic_yes = runner.invoke(cli.main, [
        "content", "settings-apply", str(proposal_path), "--gta-path", str(game),
        "--yes",
    ])
    assert generic_yes.exit_code != 0
    assert "matching the preview" in generic_yes.output
    settings_path = game / "scripts" / ".allin1" / "extensions" / "settings.json"
    assert not settings_path.is_file()

    applied = runner.invoke(cli.main, [
        "content", "settings-apply", str(proposal_path), "--gta-path", str(game),
        "--yes", "--confirm-proposal-id", preview["proposal_id"],
    ])
    assert applied.exit_code == 0, applied.output
    assert '"requires_explicit_apply": true' in applied.output
    assert '"applied": true' in applied.output


def test_launcher_qwen_proposal_wrapper_validates_and_does_not_apply(
    gta_v_fpv_install: tuple[Path, Path], tmp_path: Path, monkeypatch,
) -> None:
    game, _ = gta_v_fpv_install
    sdk_root = tmp_path / "sdk"
    sdk_root.mkdir()
    agent = sdk_root / "ALLIN1-SDK-Agent.exe"
    agent.write_bytes(b"fixture")
    output = tmp_path / "proposal.json"
    candidate = _proposal(game)
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)

    import allin1.sdk_manager
    import subprocess

    monkeypatch.setattr(
        allin1.sdk_manager, "read_sdk_status",
        lambda: SimpleNamespace(root=sdk_root, healthy=True),
    )
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=json.dumps({
                "ok": True, "result": {"output": json.dumps(candidate)},
            }) + "\n",
            stderr="", returncode=0,
        ),
    )
    invoked = CliRunner().invoke(cli.main, [
        "assistant", "settings-propose", "gta-v-fpv",
        "Make", "flight", "cinematic", "--gta-path", str(game),
        "--output", str(output),
    ])
    assert invoked.exit_code == 0, invoked.output
    proposal = json.loads(output.read_text(encoding="utf-8"))
    assert len(proposal["proposal_id"]) == 64
    assert proposal["package_id"] == "gta-v-fpv"
    assert not (game / "scripts" / ".allin1" / "extensions" / "settings.json").is_file()


def test_settings_contract_helpers_fail_closed_on_malformed_authority_state(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="finite JSON"):
        settings_contract._json_copy({"value": float("nan")})
    with pytest.raises(ValueError, match="must be an object"):
        settings_contract._only_fields([], frozenset(), "fixture")
    with pytest.raises(ValueError, match="Unsupported fixture field"):
        settings_contract._only_fields({"invented": True}, frozenset(), "fixture")

    registry = ExtensionRegistry(tmp_path / "game")
    with pytest.raises(KeyError, match="not installed"):
        settings_contract._installed_entry(registry, "missing")
    package_entry = {"id": "package", "source": "package"}
    with pytest.raises(ValueError, match="authority record is missing"):
        settings_contract._authority_path(registry, package_entry)

    registry.builtin_root.mkdir(parents=True)
    builtin = registry.builtin_root / "builtin.json"
    builtin.write_text("{}", encoding="utf-8")
    builtin_entry = {"id": "builtin", "source": "built-in"}
    assert settings_contract._authority_path(registry, builtin_entry) == builtin
    assert settings_contract._installed_file_state(registry, builtin_entry, builtin) == []

    registry.receipt_root.mkdir(parents=True)
    receipt = registry.receipt_root / "package.json"
    receipt.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid package authority"):
        settings_contract._receipt_enabled(receipt)

    receipt.write_text(json.dumps({"files": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be an array"):
        settings_contract._installed_file_state(registry, package_entry, receipt)
    receipt.write_text(json.dumps({"files": ["bad"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="contain objects"):
        settings_contract._installed_file_state(registry, package_entry, receipt)
    receipt.write_text(json.dumps({"files": [{}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid file hash"):
        settings_contract._installed_file_state(registry, package_entry, receipt)


def test_compact_catalog_keeps_one_short_choice_list_inline() -> None:
    manifest = ExtensionManifest.from_dict({
        "schema_version": 1,
        "api_version": 1,
        "id": "inline-choice",
        "name": "Inline Choice",
        "version": "1.0.0",
        "description": "Coverage fixture",
        "capabilities": ["launcher.settings"],
        "systems": [{
            "id": "display",
            "name": "Display",
            "settings": [{
                "key": "mode",
                "label": "Mode",
                "type": "choice",
                "default": "small",
                "choices": ["small", "large"],
            }],
        }],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    })
    catalog, choice_sets = settings_contract._setting_catalog(
        manifest, {"mode": "small"},
    )
    assert catalog[0]["enum"] == ["small", "large"]
    assert "enum_ref" not in catalog[0]
    assert choice_sets == {}


def test_request_and_proposal_shape_errors_are_rejected_explicitly(
    gta_v_fpv_install: tuple[Path, Path],
) -> None:
    game, _ = gta_v_fpv_install
    with pytest.raises(ValueError, match="non-empty"):
        build_settings_request(game, "gta-v-fpv", "  ")
    with pytest.raises(ValueError, match="4000"):
        build_settings_request(game, "gta-v-fpv", "x" * 4001)

    def fresh() -> dict[str, object]:
        return json.loads(json.dumps(_proposal(game)))

    invalid = fresh()
    invalid["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["kind"] = "invented"
    with pytest.raises(ValueError, match="kind must be"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["package_id"] = ""
    with pytest.raises(ValueError, match="package_id"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    del invalid["basis"]["receipt_sha256"]
    with pytest.raises(ValueError, match="basis is missing"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["changes"] = [invalid["changes"][0]] * 65
    with pytest.raises(ValueError, match="bounded array"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["changes"][0]["setting_id"] = ""
    with pytest.raises(ValueError, match="setting_id is required"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["changes"].append({
        "setting_id": "number_00", "value": 1.6, "reason": "Duplicate",
    })
    with pytest.raises(ValueError, match="repeats setting_id"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    del invalid["changes"][0]["value"]
    with pytest.raises(ValueError, match="value is required"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["changes"][0]["reason"] = ""
    with pytest.raises(ValueError, match="reason must be"):
        validate_settings_proposal(game, invalid)
    invalid = fresh()
    invalid["summary"] = ""
    with pytest.raises(ValueError, match="summary must be"):
        validate_settings_proposal(game, invalid)
