"""Explicit, bounded import of legacy Launcher preferences; never game writes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from allin1.config import Config
from allin1.profiles import ProfileStore
from allin1.release_paths import contained, no_links, unique_paths

MAX_PROFILES = 128
MAX_BYTES = 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> bytes:
    path = no_links(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError(f"Expected a preference file no larger than 1 MiB: {path.name}")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError("Preference file grew beyond 1 MiB")
    return data


def prepare(source: Path, state: Path) -> tuple[dict, dict[str, bytes]]:
    source, state = no_links(source), no_links(state)
    if not source.is_dir() or source == state or source.is_relative_to(state) or state.is_relative_to(source):
        raise ValueError("Choose a separate previous Launcher folder")
    names = []
    if contained(source, "config.toml").exists():
        names.append("config.toml")
    profiles = contained(source, "profiles")
    if profiles.exists():
        if not profiles.is_dir():
            raise ValueError("Legacy profiles must be a directory")
        for path in profiles.iterdir():
            if path.suffix.casefold() != ".toml":
                continue
            if path.stem != ProfileStore.validate_name(path.stem):
                raise ValueError("Legacy profile name is not normalized")
            names.append("profiles/" + path.name)
            if len(names) > MAX_PROFILES + int("config.toml" in names):
                raise ValueError("Legacy preferences exceed 128 profiles")
    if not names:
        raise ValueError("No config.toml or named profiles found in that folder")
    unique_paths(names)
    payloads, rows = {}, []
    # Parse the exact copied bytes, not a second potentially changed source read.
    with tempfile.TemporaryDirectory(prefix="allin1-preference-validation-") as temporary:
        check = Path(temporary) / "preferences.toml"
        for name in sorted(names):
            incoming = _read(contained(source, name))
            check.write_bytes(incoming)
            Config.load(check).validate()
            target = contained(state, name)
            existing = _read(target) if target.exists() else None
            rows.append({"path": name, "source_sha256": _sha(incoming),
                         "destination_sha256": _sha(existing) if existing is not None else None,
                         "action": "preserve" if existing is not None else "copy"})
            if existing is None:
                payloads[name] = incoming
    plan = {"schema_version": 1, "kind": "launcher_preference_import",
            "source": str(source), "destination": str(state), "files": rows,
            "copy_count": len(payloads), "preserve_count": len(rows) - len(payloads)}
    plan["plan_sha256"] = _sha(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode())
    return plan, payloads


def apply(source: Path, state: Path, expected_sha256: str) -> dict:
    plan, payloads = prepare(source, state)
    if plan["plan_sha256"] != expected_sha256:
        raise ValueError("Legacy preferences or destination changed; review again")
    if not payloads:
        raise ValueError("All selected preferences already exist; nothing will be overwritten")
    state = no_links(state)
    receipt_name = "migrations/" + uuid.uuid4().hex + ".json"
    receipt = {**plan, "kind": "launcher_preferences_imported"}
    payloads[receipt_name] = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    targets = {name: contained(state, name) for name in payloads}
    if any(path.exists() for path in targets.values()):
        raise FileExistsError("Import destination appeared; review again")
    created = []
    state.mkdir(parents=True, exist_ok=True)
    # Stage complete bytes on the same volume, then publish exclusively. Linking
    # is atomic and never overwrites a concurrently created destination. Remove
    # each staging link immediately so retained preferences have one hard link.
    try:
        with tempfile.TemporaryDirectory(prefix=".preference-import-", dir=state) as temporary:
            stage = Path(temporary)
            for index, data in enumerate(payloads.values()):
                (stage / str(index)).write_bytes(data)
            for index, (name, target) in enumerate(targets.items()):
                no_links(target).parent.mkdir(parents=True, exist_ok=True)
                staged = stage / str(index)
                os.link(staged, no_links(target))
                created.append((target, _sha(payloads[name])))
                staged.unlink()
    except BaseException:
        # TemporaryDirectory first removes any retained staging link, including
        # a failure between publication and unlink. Final files are then checked
        # with the normal no-hardlink boundary before rollback.
        for target, expected in reversed(created):
            # Preserve concurrent edits; never delete someone else's bytes.
            if no_links(target).is_file() and _sha(target.read_bytes()) == expected:
                target.unlink()
        raise
    return {"copied": [row["path"] for row in plan["files"] if row["action"] == "copy"],
            "preserved": [row["path"] for row in plan["files"] if row["action"] == "preserve"],
            "receipt": str(targets[receipt_name])}
