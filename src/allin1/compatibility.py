"""Edition compatibility rules for content exposed by GBAY."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def load_weapon_compatibility(path: Path) -> dict[str, frozenset[str]]:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    return {
        name: frozenset(value.get("editions", ("legacy", "enhanced")))
        for name, value in raw.get("weapons", {}).items()
    }


def weapon_available(name: str, edition: str,
                     manifest: dict[str, frozenset[str]]) -> bool:
    return edition.lower() in manifest.get(
        name, frozenset(("legacy", "enhanced"))
    )
