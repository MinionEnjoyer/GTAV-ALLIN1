"""Typed, advisory-only assistant contracts for managed package settings.

The model is deliberately kept outside the write path.  This module creates a
small host-authoritative catalog, validates a model's proposed diff, previews
it, and applies it only through :class:`ExtensionRegistry` after a second
stale-state check.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from allin1.extensions import ExtensionManifest, ExtensionRegistry


SETTINGS_ASSISTANT_SCHEMA_VERSION = 1
REQUEST_KIND = "allin1.settings-assistant.request"
PROPOSAL_KIND = "allin1.settings-assistant.proposal"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BASIS_FIELDS = frozenset({
    "receipt_sha256", "catalog_sha256", "settings_sha256",
    "installed_files_sha256", "receipt_enabled", "effective_enabled",
})


class StaleSettingsProposal(ValueError):
    """Raised when package state changed after the proposal was produced."""


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("settings assistant values must be finite JSON values") from exc


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _only_fields(value: object, allowed: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unsupported {label} field(s): {', '.join(sorted(unknown))}")
    return value


def _installed_entry(registry: ExtensionRegistry, package_id: str) -> dict[str, Any]:
    normalized = package_id.strip().casefold()
    for entry in registry.installed():
        if entry.get("id") == normalized:
            return entry
    raise KeyError(f"Content package is not installed: {normalized}")


def _authority_path(registry: ExtensionRegistry, entry: Mapping[str, Any]) -> Path:
    package_id = str(entry["id"])
    if entry.get("source") == "built-in":
        path = registry.builtin_root / f"{package_id}.json"
    else:
        path = registry.receipt_root / f"{package_id}.json"
    if not path.is_file():
        raise ValueError(f"Package authority record is missing: {package_id}")
    return path


def _receipt_enabled(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid package authority record: {path}") from exc
    return bool(payload.get("enabled", True))


def _installed_file_state(
    registry: ExtensionRegistry, entry: Mapping[str, Any], authority: Path,
) -> list[dict[str, Any]]:
    if entry.get("source") == "built-in":
        return []
    receipt = json.loads(authority.read_text(encoding="utf-8"))
    enabled = bool(receipt.get("enabled", True))
    result: list[dict[str, Any]] = []
    raw_files = receipt.get("files", [])
    if not isinstance(raw_files, list):
        raise ValueError("Package receipt files must be an array")
    for item in raw_files:
        if not isinstance(item, dict):
            raise ValueError("Package receipt files must contain objects")
        destination = str(item.get("destination", "")).replace("\\", "/")
        expected = str(item.get("sha256", "")).casefold()
        if not destination or not _SHA256.fullmatch(expected):
            raise ValueError("Package receipt contains an invalid file hash record")
        target = registry.gta_path / Path(*destination.split("/"))
        active = target if enabled else target.with_name(target.name + ".disabled")
        current = _file_sha256(active) if active.is_file() else None
        result.append({
            "destination": destination,
            "expected_sha256": expected,
            "current_sha256": current,
            "matches_receipt": current == expected,
        })
    return sorted(result, key=lambda item: str(item["destination"]).casefold())


def _setting_catalog(
    manifest: ExtensionManifest, current: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    choice_counts: dict[tuple[str, ...], int] = {}
    for setting in manifest.settings:
        if setting.choices:
            choice_counts[setting.choices] = choice_counts.get(setting.choices, 0) + 1
    result: list[dict[str, Any]] = []
    choice_sets: dict[str, list[str]] = {}
    for system in manifest.systems:
        for setting in system.settings:
            item: dict[str, Any] = {
                "id": setting.key,
                "system": system.system_id,
                "label": setting.label,
                "group": setting.group,
                "type": setting.setting_type,
                "current": _json_copy(current[setting.key]),
                "default": _json_copy(setting.default),
            }
            if setting.choices:
                # Large or repeated key/controller enums are interned once.  A
                # short unique choice list is cheaper and clearer inline.
                if len(setting.choices) > 8 or choice_counts[setting.choices] > 1:
                    choice_id = "choices-" + _json_sha256(list(setting.choices))[:16]
                    choice_sets[choice_id] = list(setting.choices)
                    item["enum_ref"] = choice_id
                else:
                    item["enum"] = list(setting.choices)
            if setting.minimum is not None:
                item["minimum"] = setting.minimum
            if setting.maximum is not None:
                item["maximum"] = setting.maximum
            if setting.step is not None:
                item["step"] = setting.step
            result.append(item)
    return result, dict(sorted(choice_sets.items()))


def build_settings_catalog(gta_path: str | Path, package_id: str) -> dict[str, Any]:
    """Create the compact, host-authoritative model input for one package."""
    registry = ExtensionRegistry(gta_path)
    entry = _installed_entry(registry, package_id)
    manifest = ExtensionManifest.from_registry_entry(entry)
    current = {
        setting.key: setting.validate(entry.get("settings", {}).get(
            setting.key, setting.default,
        ))
        for setting in manifest.settings
    }
    authority = _authority_path(registry, entry)
    settings, choice_sets = _setting_catalog(manifest, current)
    installed_files = _installed_file_state(registry, entry, authority)
    basis = {
        "receipt_sha256": _file_sha256(authority),
        "catalog_sha256": _json_sha256({
            "settings": settings, "choice_sets": choice_sets,
        }),
        "settings_sha256": _json_sha256(current),
        "installed_files_sha256": _json_sha256(installed_files),
        "receipt_enabled": _receipt_enabled(authority),
        "effective_enabled": bool(entry.get("enabled", False)),
    }
    return {
        "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
        "kind": "allin1.settings-assistant.catalog",
        "package": {
            "id": manifest.extension_id,
            "name": manifest.name,
            "version": manifest.version,
            "source": str(entry.get("source", "package")),
            "blocked_reason": str(entry.get("blocked_reason", "")),
        },
        "basis": basis,
        "setting_count": len(settings),
        "choice_sets": choice_sets,
        "settings": settings,
    }


def build_settings_request(
    gta_path: str | Path, package_id: str, intent: str,
) -> dict[str, Any]:
    """Build the only data supplied to Qwen: natural-language intent plus catalog."""
    if not isinstance(intent, str) or not intent.strip():
        raise ValueError("settings intent must be non-empty natural-language text")
    if len(intent) > 4000:
        raise ValueError("settings intent must be 4000 characters or fewer")
    catalog = build_settings_catalog(gta_path, package_id)
    return {
        "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
        "kind": REQUEST_KIND,
        "operation": "propose_settings_diff",
        "advisory_only": True,
        "intent": intent.strip(),
        "catalog": catalog,
        "required_output": {
            "kind": PROPOSAL_KIND,
            "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
            "package_id": str(catalog["package"]["id"]),
            "basis": _json_copy(catalog["basis"]),
            "changes": [{"setting_id": "<catalog id>", "value": "<typed JSON value>", "reason": "<brief>"}],
            "summary": "<brief preview summary>",
        },
    }


@dataclass(frozen=True)
class ValidatedSettingsProposal:
    package_id: str
    basis: Mapping[str, Any]
    changes: Mapping[str, Any]
    reasons: Mapping[str, str]
    summary: str
    proposal_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
            "kind": PROPOSAL_KIND,
            "proposal_id": self.proposal_id,
            "package_id": self.package_id,
            "basis": _json_copy(self.basis),
            "changes": [
                {
                    "setting_id": key,
                    "value": _json_copy(value),
                    "reason": self.reasons.get(key, ""),
                }
                for key, value in self.changes.items()
            ],
            "summary": self.summary,
        }


def validate_settings_proposal(
    gta_path: str | Path, proposal: object,
) -> ValidatedSettingsProposal:
    """Validate a Qwen diff and reject stale or invented package state."""
    data = _only_fields(proposal, frozenset({
        "schema_version", "kind", "proposal_id", "package_id", "basis",
        "changes", "summary",
    }), "settings proposal")
    if data.get("schema_version") != SETTINGS_ASSISTANT_SCHEMA_VERSION:
        raise ValueError("Unsupported settings proposal schema_version")
    if data.get("kind") != PROPOSAL_KIND:
        raise ValueError(f"settings proposal kind must be {PROPOSAL_KIND}")
    package_id = data.get("package_id")
    if not isinstance(package_id, str) or not package_id.strip():
        raise ValueError("settings proposal package_id must be non-empty text")
    current_catalog = build_settings_catalog(gta_path, package_id)
    expected_basis = current_catalog["basis"]
    basis = _only_fields(data.get("basis"), _BASIS_FIELDS, "settings proposal basis")
    missing = _BASIS_FIELDS - set(basis)
    if missing:
        raise ValueError(f"settings proposal basis is missing: {', '.join(sorted(missing))}")
    if dict(basis) != expected_basis:
        raise StaleSettingsProposal(
            "Package receipt, enabled state, setting state, catalog, or installed "
            "file hashes changed; generate a new settings proposal."
        )
    raw_changes = data.get("changes")
    if (
        not isinstance(raw_changes, list) or not raw_changes
        or len(raw_changes) > min(64, len(current_catalog["settings"]))
    ):
        raise ValueError("settings proposal changes must be a non-empty bounded array")
    manifest = ExtensionManifest.from_registry_entry(
        _installed_entry(ExtensionRegistry(gta_path), package_id)
    )
    changes: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    current_by_id = {
        str(item["id"]): item["current"] for item in current_catalog["settings"]
    }
    for index, raw_change in enumerate(raw_changes, start=1):
        change = _only_fields(
            raw_change, frozenset({"setting_id", "value", "reason"}),
            f"settings proposal changes[{index}]",
        )
        setting_id = change.get("setting_id")
        if not isinstance(setting_id, str) or not setting_id.strip():
            raise ValueError(f"settings proposal changes[{index}].setting_id is required")
        normalized = setting_id.strip().casefold()
        if normalized in changes:
            raise ValueError(f"settings proposal repeats setting_id: {normalized}")
        try:
            setting = manifest.setting(normalized)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if "value" not in change:
            raise ValueError(f"settings proposal changes[{index}].value is required")
        value = setting.validate(change["value"])
        if value == current_by_id[normalized]:
            raise ValueError(
                f"{normalized} already has the proposed value; settings proposals "
                "must contain changed values only"
            )
        changes[normalized] = value
        reason = change.get("reason", "")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError(
                f"settings proposal changes[{index}].reason must be 1-500 "
                "characters of text"
            )
        reasons[normalized] = reason.strip()
    summary = data.get("summary", "")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 1000:
        raise ValueError("settings proposal summary must be 1-1000 characters of text")
    normalized_body = {
        "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
        "kind": PROPOSAL_KIND,
        "package_id": package_id.strip().casefold(),
        "basis": expected_basis,
        "changes": [
            {"setting_id": key, "value": value, "reason": reasons[key]}
            for key, value in changes.items()
        ],
        "summary": summary.strip(),
    }
    proposal_id = _json_sha256(normalized_body)
    supplied_id = data.get("proposal_id")
    if supplied_id is not None and supplied_id != proposal_id:
        raise ValueError("settings proposal_id does not match its validated contents")
    return ValidatedSettingsProposal(
        package_id=normalized_body["package_id"], basis=expected_basis,
        changes=changes, reasons=reasons, summary=normalized_body["summary"],
        proposal_id=proposal_id,
    )


def preview_settings_proposal(gta_path: str | Path, proposal: object) -> dict[str, Any]:
    """Return an explicit, non-mutating preview of a valid proposal."""
    validated = validate_settings_proposal(gta_path, proposal)
    catalog = build_settings_catalog(gta_path, validated.package_id)
    by_id = {str(item["id"]): item for item in catalog["settings"]}
    changes = []
    for setting_id, value in validated.changes.items():
        item = by_id[setting_id]
        changes.append({
            "setting_id": setting_id,
            "label": item["label"],
            "before": _json_copy(item["current"]),
            "after": _json_copy(value),
            "reason": validated.reasons[setting_id],
            "changed": item["current"] != value,
        })
    return {
        "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
        "kind": "allin1.settings-assistant.preview",
        "advisory_only": True,
        "requires_explicit_apply": True,
        "proposal_id": validated.proposal_id,
        "package_id": validated.package_id,
        "summary": validated.summary,
        "changes": changes,
    }


def apply_settings_proposal(
    gta_path: str | Path, proposal: object, *, confirmed_proposal_id: str | None,
) -> dict[str, Any]:
    """Apply a proposal through the launcher registry after a fresh validation."""
    preview = preview_settings_proposal(gta_path, proposal)
    if confirmed_proposal_id != preview["proposal_id"]:
        raise PermissionError(
            "Applying settings requires confirmation of the exact preview proposal_id"
        )
    validated = validate_settings_proposal(gta_path, proposal)
    registry = ExtensionRegistry(gta_path)
    effective = registry.set_settings(validated.package_id, validated.changes)
    return {
        "schema_version": SETTINGS_ASSISTANT_SCHEMA_VERSION,
        "kind": "allin1.settings-assistant.applied",
        "proposal_id": validated.proposal_id,
        "package_id": validated.package_id,
        "applied": True,
        "changes": preview["changes"],
        "effective_settings_sha256": _json_sha256(effective),
    }
