"""Read-only resource locations shared by source and frozen Launcher services."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from allin1 import __version__
from allin1.release_paths import no_links, strict_json, tree_files, unique_paths

SIDECAR_NAME = "ALLIN1-Launcher-Sidecar.exe"


def resource_root() -> Path:
    # Do not accept environment overrides in shipped processes. Keep the legacy
    # source/CLI location unchanged while its GUI remains a parity reference.
    if getattr(sys, "frozen", False) and Path(sys.executable).name == SIDECAR_NAME:
        return no_links(Path(sys.executable).parent.parent / "resources")
    return Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_resources(root: Path, identity: dict) -> None:
    """Validate the entire declared tree before a service can write anything.

    This detects corruption/build mixing, not publisher authenticity. Unsigned
    manual downloads still require an independent trusted checksum source.
    """
    if (type(identity.get("schema_version")) is not int or identity["schema_version"] != 1
            or identity.get("kind") != "launcher_desktop_build"
            or identity.get("version") != __version__
            or not isinstance(identity.get("resources"), dict) or not identity["resources"]):
        raise ValueError("Invalid Launcher resource identity or version")
    expected = identity["resources"]
    unique_paths(list(expected))
    files = tree_files(root)
    if set(files) != set(expected):
        raise ValueError("Launcher resources do not exactly match this build")
    for name, path in files.items():
        if sha256(path) != expected[name]:
            raise ValueError(f"Launcher resource checksum mismatch: {name}")


def frozen_identity(project: Path) -> dict | None:
    if not getattr(sys, "frozen", False):
        return None
    if no_links(project) != resource_root():
        raise ValueError("Packaged Launcher must use its own resource directory")
    identity = strict_json(Path(__file__).with_name("_desktop_build.json").read_bytes())
    verify_resources(project, identity)
    return {key: identity[key] for key in (
        "schema_version", "kind", "version", "build_id", "commit", "source_sha256",
        "source_dirty", "created_at", "resources_sha256",
    )}
