"""Build export-only capacity profiles from an existing ``gameconfig.xml``.

This is deliberately a document transformer, not an installer.  Callers can
write the returned XML wherever they choose, but this module never opens game
files, archives, or an RPF.
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re

from lxml import etree

from allin1.generators.gameconfig import (
    ENHANCED_POOL_OVERRIDES,
    LEGACY_POOL_OVERRIDES,
    _pool_entries,
)


SCHEMA_VERSION = 1
MAX_XML_BYTES = 4 * 1024 * 1024
_INT32_MAX = 2_147_483_647
_BUILD_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def preset_targets(edition: str, preset: str) -> dict[str, int]:
    """Return a copy of an explicitly experimental export preset.

    ``addon-headroom`` is derived from ALLIN1's existing gameconfig override
    dictionaries.  It is a convenience starting point, *not* a researched or
    runtime-qualified safe limit for a particular GTA build or mod list.
    """

    normalized_edition = _validate_edition(edition)
    if not isinstance(preset, str):
        raise ValueError("preset must be a string")
    if preset == "stock":
        return {}
    if preset != "addon-headroom":
        raise ValueError("unknown capacity preset")
    source = (
        LEGACY_POOL_OVERRIDES
        if normalized_edition == "legacy"
        else ENHANCED_POOL_OVERRIDES
    )
    return dict(source)


def inspect_config(xml: str) -> dict[str, object]:
    """Inspect a bounded, safe gameconfig document without changing it."""

    tree, edition = _parse_config(xml)
    entries, scopes = _entries_for_edition(tree.getroot(), edition)
    parsed_pools = _read_pools(entries, edition)
    result: dict[str, object] = {
        "edition": edition,
        "pools": {name: record[0] for name, record in parsed_pools.items()},
        "source_sha256": _source_hash(xml),
    }
    if edition == "enhanced":
        result["target_scope"] = "windows-release"
        result["scopes"] = scopes
    return result


def build_profile(
    xml: str,
    *,
    edition: str,
    game_build: str,
    targets: dict[str, int],
    expected_source_sha256: str,
) -> tuple[str, dict[str, object]]:
    """Return a monotonic, export-only pool profile and an auditable receipt.

    The requested source hash binds a profile to the document the user
    inspected.  Existing pool values are never reduced.
    """

    requested_edition = _validate_edition(edition)
    _validate_build_label(game_build)
    _validate_expected_hash(expected_source_sha256)
    source_hash = _source_hash(xml)
    if source_hash != expected_source_sha256.lower():
        raise ValueError("source SHA-256 does not match expected_source_sha256")
    if not isinstance(targets, dict):
        raise ValueError("targets must be a dictionary of pool sizes")

    tree, detected_edition = _parse_config(xml)
    if detected_edition != requested_edition:
        raise ValueError(
            f"edition mismatch: document is {detected_edition}, requested {requested_edition}"
        )
    entries, scopes = _entries_for_edition(tree.getroot(), detected_edition)
    pools = _read_pools(entries, detected_edition)
    normalized_targets = _validate_targets(targets)
    missing = sorted(set(normalized_targets).difference(pools))
    if missing:
        raise ValueError("requested target pools are missing: " + ", ".join(missing))

    changes: dict[str, dict[str, int]] = {}
    for name, target in normalized_targets.items():
        before, size_el = pools[name]
        after = max(before, target)
        if after != before:
            # This is intentionally the only mutation: unrelated attributes,
            # fields, comments, and formatting nodes remain part of the tree.
            size_el.set("value", str(after))
        changes[name] = {"before": before, "after": after}

    changed = any(record["before"] != record["after"] for record in changes.values())
    output = xml if not changed else _serialize(tree)
    receipt: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_hash,
        "output_sha256": _source_hash(output),
        "edition": detected_edition,
        "game_build": game_build,
        "changes": {name: changes[name] for name in sorted(changes)},
        # ``pools`` retains the conventional receipt name while ``changes``
        # makes the mutation intent explicit for new consumers.
        "pools": {name: changes[name] for name in sorted(changes)},
        "warnings": [
            "Export-only profile; no game files, archives, or RPFs were modified.",
            "This profile is not runtime-qualified; native pool limits are unknown.",
            "Targets are experimental and are not researched safe values for this build.",
        ],
        "export_only": True,
        "runtime_qualified": False,
    }
    if detected_edition == "enhanced":
        receipt["target_scope"] = "windows-release"
        receipt["scopes"] = scopes
    return output, receipt


def _validate_edition(edition: str) -> str:
    if not isinstance(edition, str):
        raise ValueError("edition must be 'legacy' or 'enhanced'")
    normalized = edition.lower()
    if normalized not in {"legacy", "enhanced"}:
        raise ValueError("edition must be 'legacy' or 'enhanced'")
    return normalized


def _validate_build_label(game_build: str) -> None:
    if not isinstance(game_build, str) or not _BUILD_LABEL.fullmatch(game_build):
        raise ValueError("game_build must be a 1-64 character build label")


def _validate_expected_hash(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("expected_source_sha256 must be a SHA-256 hex digest")


def _validate_targets(targets: dict[str, int]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for name, value in targets.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("target pool names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"target for {name!r} must be an integer")
        if not 0 < value <= _INT32_MAX:
            raise ValueError(f"target for {name!r} must be a positive int32")
        normalized[name] = value
    return normalized


def _parse_config(xml: str) -> tuple[etree._ElementTree, str]:
    if not isinstance(xml, str) or not xml.strip():
        raise ValueError("gameconfig.xml must be non-empty XML text")
    try:
        raw = xml.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("gameconfig.xml is not valid UTF-8 text") from exc
    if len(raw) > MAX_XML_BYTES:
        raise ValueError(f"gameconfig.xml exceeds {MAX_XML_BYTES} byte limit")
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        dtd_validation=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
        recover=False,
    )
    try:
        tree = etree.parse(BytesIO(raw), parser)
    except (etree.XMLSyntaxError, UnicodeError) as exc:
        raise ValueError(f"Invalid gameconfig.xml: {exc}") from exc
    if tree.docinfo.doctype:
        raise ValueError("DTD and entity declarations are not allowed")
    if any(isinstance(node, etree._Entity) for node in tree.iter()):
        raise ValueError("entity references are not allowed")
    root = tree.getroot()
    root_name = etree.QName(root).localname
    if root_name == "CGameConfig":
        return tree, "legacy"
    if root_name == "fwAllConfigs":
        return tree, "enhanced"
    # Let the established helper retain its detailed root/schema diagnostic.
    _pool_entries(root)
    raise AssertionError("unreachable")


def _entries_for_edition(
    root: etree._Element, edition: str
) -> tuple[list[tuple[etree._Element, etree._Element]], list[dict[str, str]]]:
    legacy, enhanced = _pool_entries(root)
    if edition == "enhanced":
        return _windows_release_entries(root, enhanced)
    entries = legacy
    if not entries:
        raise ValueError("gameconfig.xml has no legacy Name/Size pool entries")
    return entries, []


def _windows_release_entries(
    root: etree._Element,
    entries: list[tuple[etree._Element, etree._Element]],
) -> tuple[list[tuple[etree._Element, etree._Element]], list[dict[str, str]]]:
    """Resolve the effective Windows release pools from ConfigArray scopes.

    Rockstar's Enhanced file has a generic ``Any`` scope and an ``x64``
    override scope.  A pool in the latter supersedes the former.  Console and
    non-release scopes are deliberately not candidates and are never changed.
    """

    if _local_name(root) != "fwAllConfigs":  # defensive: _pool_entries checked this
        raise ValueError("Enhanced gameconfig.xml must use fwAllConfigs")
    by_scope: dict[int, list[tuple[etree._Element, etree._Element]]] = {}
    scope_elements: dict[int, etree._Element] = {}
    for pair in entries:
        scope = _scope_item_for_entry(pair[0])
        if scope is None:
            raise ValueError("Enhanced pool entry is not in a ConfigArray scope")
        key = id(scope)
        by_scope.setdefault(key, []).append(pair)
        scope_elements[key] = scope

    applicable: list[tuple[str, list[tuple[etree._Element, etree._Element]], dict[str, str]]] = []
    for key, scope_entries in by_scope.items():
        # Validate each scope separately: duplicate names across scopes are
        # normal overrides, duplicates within one scope are ambiguous.
        _read_pools(scope_entries, "enhanced")
        scope = scope_elements[key]
        build = _selector(scope, "Build")
        platforms = _selector(scope, "Platforms")
        sub_platforms = _selector(scope, "SubPlatforms")
        classification = _classify_windows_scope(build, platforms, sub_platforms)
        if classification is not None:
            if any(kind == classification for kind, _, _ in applicable):
                raise ValueError(
                    f"duplicate applicable Windows release {classification} scope"
                )
            applicable.append((classification, scope_entries, {
                "scope": classification,
                "build": build,
                "platforms": platforms,
                "sub_platforms": sub_platforms,
            }))

    if not applicable:
        raise ValueError("gameconfig.xml has no applicable Windows release pool scope")
    # Generic Any values form the base.  x64 values override names they carry.
    applicable.sort(key=lambda record: 0 if record[0] == "base" else 1)
    effective: dict[str, tuple[etree._Element, etree._Element]] = {}
    reports: list[dict[str, str]] = []
    for _kind, scope_entries, report in applicable:
        reports.append(report)
        for name_el, size_el in scope_entries:
            name = (name_el.text or "").strip()
            effective[name] = (name_el, size_el)
    return list(effective.values()), reports


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _scope_item_for_entry(name_el: etree._Element) -> etree._Element | None:
    """Return the outer ConfigArray/Item for a validated Enhanced entry."""

    item = name_el.getparent()
    entries = item.getparent() if item is not None else None
    pool_sizes = entries.getparent() if entries is not None else None
    config = pool_sizes.getparent() if pool_sizes is not None else None
    scope = config.getparent() if config is not None else None
    if not all((item is not None, entries is not None, pool_sizes is not None, config is not None, scope is not None)):
        return None
    if (
        _local_name(item) != "Item"
        or _local_name(entries) != "Entries"
        or _local_name(pool_sizes) != "PoolSizes"
        or _local_name(config) != "Config"
        or config.get("type") != "CGameConfig"
        or _local_name(scope) != "Item"
    ):
        return None
    container = scope.getparent()
    return scope if container is not None and _local_name(container) == "ConfigArray" else None


def _selector(scope: etree._Element, name: str) -> str:
    for child in scope:
        if isinstance(child.tag, str) and _local_name(child) == name:
            value = (child.text or "").strip()
            if not value:
                raise ValueError(f"Windows release scope has an empty {name} selector")
            return value.casefold()
    raise ValueError(f"Windows release scope is missing {name} selector")


def _classify_windows_scope(build: str, platforms: str, sub_platforms: str) -> str | None:
    if build in {"debug", "beta", "nonfinal"} or platforms in {"xbsx", "ps5"}:
        return None
    if build != "any":
        raise ValueError(f"unknown applicable Build selector {build!r}")
    if platforms not in {"any", "x64"}:
        raise ValueError(f"unknown applicable Platforms selector {platforms!r}")
    if sub_platforms != "any":
        raise ValueError(f"unknown applicable SubPlatforms selector {sub_platforms!r}")
    return "base" if platforms == "any" else "x64"


def _read_pools(
    entries: list[tuple[etree._Element, etree._Element]], edition: str
) -> dict[str, tuple[int, etree._Element]]:
    pools: dict[str, tuple[int, etree._Element]] = {}
    for name_el, size_el in entries:
        name = (name_el.text or "").strip()
        if not name:
            raise ValueError(f"Malformed {edition} gameconfig pool entry: pool name is empty")
        if name in pools:
            raise ValueError(f"duplicate pool name {name!r}")
        raw_size = size_el.get("value")
        try:
            size = int(raw_size) if raw_size is not None else None
        except ValueError as exc:
            raise ValueError(f"Malformed pool {name!r}: invalid size {raw_size!r}") from exc
        if size is None or not 0 <= size <= _INT32_MAX:
            raise ValueError(f"Malformed pool {name!r}: size must be a non-negative int32")
        pools[name] = (size, size_el)
    return pools


def _source_hash(xml: str) -> str:
    return sha256(xml.encode("utf-8")).hexdigest()


def _serialize(tree: etree._ElementTree) -> str:
    return etree.tostring(
        tree, encoding="UTF-8", xml_declaration=True, pretty_print=False
    ).decode("utf-8")
