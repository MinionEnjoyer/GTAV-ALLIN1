import hashlib
import json
from pathlib import Path

import pytest

from allin1.reactor_bridge_contract import (
    validate_reactor_bridge_pair_payloads,
    validate_reactor_bridge_pair,
)


ROOT = Path(__file__).resolve().parents[1]


def _stage_pair(directory: Path, core: bytes, bridge: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ALLIN1.dll").write_bytes(core)
    (directory / "ALLIN1.ReactorBridge.plugin").write_bytes(bridge)
    (directory / "ALLIN1.ReactorBridge.contract.json").write_text(json.dumps({
        "schema_version": 1,
        "version": "0.6.1",
        "core_file": "ALLIN1.dll",
        "core_sha256": hashlib.sha256(core).hexdigest(),
        "bridge_file": "ALLIN1.ReactorBridge.plugin",
        "bridge_sha256": hashlib.sha256(bridge).hexdigest(),
    }), encoding="utf-8")


def test_pair_contract_rejects_independently_replaced_binary(tmp_path):
    _stage_pair(tmp_path, b"core", b"bridge")
    validate_reactor_bridge_pair(tmp_path, expected_version="0.6.1")

    (tmp_path / "ALLIN1.dll").write_bytes(b"stale-or-independent-core")
    with pytest.raises(ValueError, match="rebuild the core and bridge together"):
        validate_reactor_bridge_pair(tmp_path)


def test_pair_contract_rejects_incomplete_and_malformed_payloads(tmp_path):
    with pytest.raises(ValueError, match="incomplete"):
        validate_reactor_bridge_pair(tmp_path)

    with pytest.raises(ValueError, match="invalid Reactor bridge contract"):
        validate_reactor_bridge_pair_payloads(b"core", b"bridge", b"not-json")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"schema_version": 2}, "schema"),
        ({"core_file": "Other.dll"}, "unexpected core"),
        ({"bridge_file": "Other.plugin"}, "unexpected bridge"),
        ({"version": ""}, "missing its version"),
    ],
)
def test_pair_contract_rejects_invalid_identity_fields(override, message):
    core = b"core"
    bridge = b"bridge"
    contract = {
        "schema_version": 1,
        "version": "0.6.1",
        "core_file": "ALLIN1.dll",
        "core_sha256": hashlib.sha256(core).hexdigest(),
        "bridge_file": "ALLIN1.ReactorBridge.plugin",
        "bridge_sha256": hashlib.sha256(bridge).hexdigest(),
    }
    contract.update(override)
    with pytest.raises(ValueError, match=message):
        validate_reactor_bridge_pair_payloads(
            core, bridge, json.dumps(contract).encode("utf-8")
        )


def test_pair_contract_rejects_version_and_bridge_hash_mismatch(tmp_path):
    _stage_pair(tmp_path, b"core", b"bridge")
    with pytest.raises(ValueError, match="version mismatch"):
        validate_reactor_bridge_pair(tmp_path, expected_version="9.9.9")

    (tmp_path / "ALLIN1.ReactorBridge.plugin").write_bytes(b"different")
    with pytest.raises(ValueError, match="bridge together"):
        validate_reactor_bridge_pair(tmp_path)


def test_bridge_build_is_the_single_lockstep_dist_staging_owner():
    project = (
        ROOT / "script/reactor-bridge/ALLIN1.ReactorBridge.csproj"
    ).read_text(encoding="utf-8")
    build_workflow = (
        ROOT / ".github/workflows/build-asi.yml"
    ).read_text(encoding="utf-8")
    test_workflow = (
        ROOT / ".github/workflows/test.yml"
    ).read_text(encoding="utf-8")
    local_gate = (ROOT / "test-all.ps1").read_text(encoding="utf-8")

    assert "StageCompatibleClientPair" in project
    assert "$(Allin1CoreOutput)" in project
    assert "$(TargetPath)" in project
    assert "ALLIN1.ReactorBridge.contract.json" in project
    assert "dotnet build script/reactor-bridge/ALLIN1.ReactorBridge.csproj" in (
        build_workflow
    )
    assert "script/dist/ALLIN1.ReactorBridge.contract.json" in build_workflow
    assert "script/dist/ALLIN1.ReactorBridge.contract.json" in test_workflow
    assert "script/dist/ALLIN1.ReactorBridge.contract.json" in local_gate
    independent_core_copy = (
        'Copy-Item -Path "script/out/ALLIN1.dll" '
        '-Destination "script/dist/ALLIN1.dll"'
    )
    assert independent_core_copy not in build_workflow
    assert (
        'Copy-Item -LiteralPath "script/bin/Release/ALLIN1.dll" '
        '-Destination "script/dist/ALLIN1.dll"'
    ) not in local_gate
