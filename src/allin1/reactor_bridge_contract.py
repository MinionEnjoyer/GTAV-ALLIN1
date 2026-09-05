"""Compatibility contract for the ALLIN1 core and Reactor bridge binaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


CORE_FILENAME = "ALLIN1.dll"
BRIDGE_FILENAME = "ALLIN1.ReactorBridge.plugin"
CONTRACT_FILENAME = "ALLIN1.ReactorBridge.contract.json"


@dataclass(frozen=True)
class ReactorBridgePair:
    version: str
    core_sha256: str
    bridge_sha256: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_reactor_bridge_pair_payloads(
    core: bytes,
    bridge: bytes,
    contract: bytes,
    *,
    expected_version: str | None = None,
) -> ReactorBridgePair:
    """Validate that the two binaries are the exact pair staged by MSBuild."""
    try:
        # MSBuild's WriteLinesToFile emits a UTF-8 BOM on .NET Framework.
        # Accept that canonical output while still rejecting non-UTF-8 data.
        document = json.loads(contract.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Reactor bridge contract: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("unsupported Reactor bridge contract schema")
    if document.get("core_file") != CORE_FILENAME:
        raise ValueError("Reactor bridge contract names an unexpected core file")
    if document.get("bridge_file") != BRIDGE_FILENAME:
        raise ValueError("Reactor bridge contract names an unexpected bridge file")

    version = str(document.get("version", "")).strip()
    if not version:
        raise ValueError("Reactor bridge contract is missing its version")
    if expected_version is not None and version != expected_version:
        raise ValueError(
            "Reactor bridge contract version mismatch "
            f"(expected {expected_version}, found {version})"
        )

    expected_core = str(document.get("core_sha256", "")).lower()
    expected_bridge = str(document.get("bridge_sha256", "")).lower()
    actual_core = _sha256(core)
    actual_bridge = _sha256(bridge)
    if expected_core != actual_core:
        raise ValueError(
            "ALLIN1.dll does not match the Reactor bridge contract; rebuild "
            "the core and bridge together"
        )
    if expected_bridge != actual_bridge:
        raise ValueError(
            "ALLIN1.ReactorBridge.plugin does not match the Reactor bridge "
            "contract; rebuild the core and bridge together"
        )
    return ReactorBridgePair(version, actual_core, actual_bridge)


def validate_reactor_bridge_pair(
    directory: Path, *, expected_version: str | None = None,
) -> ReactorBridgePair:
    """Validate a staged pair on disk without accepting missing artifacts."""
    directory = Path(directory)
    required = {
        CORE_FILENAME: directory / CORE_FILENAME,
        BRIDGE_FILENAME: directory / BRIDGE_FILENAME,
        CONTRACT_FILENAME: directory / CONTRACT_FILENAME,
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ValueError(
            "Reactor bridge pair is incomplete: " + ", ".join(sorted(missing))
        )
    return validate_reactor_bridge_pair_payloads(
        required[CORE_FILENAME].read_bytes(),
        required[BRIDGE_FILENAME].read_bytes(),
        required[CONTRACT_FILENAME].read_bytes(),
        expected_version=expected_version,
    )
