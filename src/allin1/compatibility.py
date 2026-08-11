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


def load_content_compatibility(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def build_compatible(build: int, edition: str, manifest: dict) -> tuple[bool, str]:
    """Evaluate an edition/build against declarative supported ranges."""
    rule = manifest.get("editions", {}).get(edition.lower())
    if not rule:
        return False, f"Unsupported GTA edition: {edition}"
    minimum = int(rule.get("min_build", 0))
    maximum = int(rule.get("max_build", 0))
    if build < minimum:
        return False, f"GTA build {build} is older than supported build {minimum}"
    if maximum and build > maximum:
        return False, f"GTA build {build} is newer than tested build {maximum}"
    return True, "supported"
