"""Safely increase GTA V gameconfig.xml pool sizes.

Legacy and Enhanced use different XML shapes for the same concept. This
module patches an existing, complete gameconfig document in place; it never
builds a replacement document from a small pool-only fragment.
"""

from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
import logging

from lxml import etree

log = logging.getLogger("allin1.generators.gameconfig")

# Pool sizes needed for large vehicle collections in the Legacy Name/Size
# schema. Keep the historical public name as an alias for callers that import
# POOL_OVERRIDES directly.
LEGACY_POOL_OVERRIDES = {
    "CVehicle": 512,
    "CVehicleStreamRequest": 100,
    "CVehicleStreamRender": 512,
    "CVehicleStruct": 512,
    "CHandlingDataMgr": 900,
    "CVehicleModelInfo": 900,
    "CBaseModelInfo": 1400,
    "CMapData": 1024,
    "CMapDataContents": 200,
    "CPickup": 400,
    "CObject": 2048,
    "fwArchetypeDef": 1800,
    "fwArchetypePooledMap": 600,
    "fwDrawableDef": 1200,
    "FragInst": 300,
    "phBoundComposite": 500,
    "phBound": 1500,
}
POOL_OVERRIDES = LEGACY_POOL_OVERRIDES

# Enhanced's stock asset pools were observed at or very near capacity while
# loading the ALLIN1 map archive (notably FragmentStore 41630/42000,
# MetaDataStore 3199/3200, TxdStore 78490/80200, and DwdStore 19422/20500).
# These conservative targets provide roughly 20-25% headroom for the affected
# stores without replacing a user's larger, already-tuned values.
ENHANCED_POOL_OVERRIDES = {
    "DrawableStore": 90000,
    "DwdStore": 25000,
    "FragmentStore": 52000,
    "InteriorProxy": 1500,
    "IplStore": 3600,
    "MaxLoadedInfo": 40000,
    "MapDataStore": 12000,
    "MetaDataStore": 4000,
    "StaticBounds": 18000,
    "TxdStore": 100000,
}


def _local_name(element: etree._Element) -> str:
    """Return an element's local tag name, including namespace-safe input."""

    return etree.QName(element).localname


def _direct_child(element: etree._Element, name: str) -> etree._Element | None:
    for child in element:
        if isinstance(child.tag, str) and _local_name(child) == name:
            return child
    return None


def _is_enhanced_pool_item(item: etree._Element) -> bool:
    """Return whether ``item`` is inside Config/PoolSizes/Entries."""

    entries = item.getparent()
    pool_sizes = entries.getparent() if entries is not None else None
    config = pool_sizes.getparent() if pool_sizes is not None else None
    return bool(
        entries is not None
        and pool_sizes is not None
        and config is not None
        and _local_name(entries) == "Entries"
        and _local_name(pool_sizes) == "PoolSizes"
        and _local_name(config) == "Config"
        and config.get("type") == "CGameConfig"
    )


def _pool_entries(
    root: etree._Element,
) -> tuple[
    list[tuple[etree._Element, etree._Element]],
    list[tuple[etree._Element, etree._Element]],
]:
    """Collect and validate Legacy and Enhanced pool entry pairs."""

    legacy: list[tuple[etree._Element, etree._Element]] = []
    enhanced: list[tuple[etree._Element, etree._Element]] = []

    root_name = _local_name(root)
    if root_name not in {"CGameConfig", "fwAllConfigs"}:
        raise ValueError(
            f"Unsupported gameconfig.xml root {root_name!r}; expected "
            "CGameConfig (Legacy) or fwAllConfigs (Enhanced)"
        )

    for item in root.iter():
        if not isinstance(item.tag, str) or _local_name(item) != "Item":
            continue

        pool_name = _direct_child(item, "PoolName")
        pool_size = _direct_child(item, "PoolSize")
        if pool_name is not None or pool_size is not None:
            if root_name != "fwAllConfigs" or not _is_enhanced_pool_item(item):
                continue
            if pool_name is None or pool_size is None:
                raise ValueError(
                    "Malformed Enhanced gameconfig pool entry: PoolName and "
                    "PoolSize must both be present"
                )
            enhanced.append((pool_name, pool_size))

        name = _direct_child(item, "Name")
        size = _direct_child(item, "Size")
        if name is not None or size is not None:
            # A complete Enhanced gameconfig contains other Item/Name records.
            # Only the Legacy CGameConfig root defines Name/Size as pool data.
            if root_name != "CGameConfig":
                continue
            if name is None or size is None:
                raise ValueError(
                    "Malformed Legacy gameconfig pool entry: Name and Size "
                    "must both be present"
                )
            legacy.append((name, size))

    return legacy, enhanced


def _patch_entries(
    entries: list[tuple[etree._Element, etree._Element]],
    overrides: dict[str, int],
    *,
    schema_name: str,
) -> int:
    patched = 0
    for name_el, size_el in entries:
        pool_name = (name_el.text or "").strip()
        if not pool_name:
            raise ValueError(f"Malformed {schema_name} gameconfig pool entry: pool name is empty")

        raw_size = size_el.get("value")
        try:
            current = int(raw_size) if raw_size is not None else None
        except ValueError as exc:
            raise ValueError(
                f"Malformed {schema_name} gameconfig pool {pool_name!r}: "
                f"invalid size {raw_size!r}"
            ) from exc
        if current is None or current < 0:
            raise ValueError(
                f"Malformed {schema_name} gameconfig pool {pool_name!r}: "
                "size must be a non-negative integer"
            )

        target = overrides.get(pool_name)
        if target is None:
            continue
        if current < target:
            size_el.set("value", str(target))
            log.debug("%s pool %s: %d -> %d", schema_name, pool_name, current, target)
            patched += 1
        else:
            log.debug(
                "%s pool %s: already at %d (target %d)",
                schema_name,
                pool_name,
                current,
                target,
            )
    return patched


def patch_gameconfig(gameconfig_xml: str) -> str:
    """Increase known pool sizes in a complete Legacy or Enhanced gameconfig.

    Existing values are only raised, never lowered. Unsupported, incomplete,
    or malformed documents are rejected instead of emitting a partial override
    that GTA could silently ignore.
    """

    if not isinstance(gameconfig_xml, str) or not gameconfig_xml.strip():
        raise ValueError("gameconfig.xml must be non-empty XML text")

    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
    )
    try:
        tree = etree.parse(BytesIO(gameconfig_xml.encode("utf-8")), parser)
    except (UnicodeError, etree.XMLSyntaxError) as exc:
        raise ValueError(f"Invalid gameconfig.xml: {exc}") from exc

    root = tree.getroot()
    legacy_entries, enhanced_entries = _pool_entries(root)
    if not legacy_entries and not enhanced_entries:
        raise ValueError(
            "Unsupported gameconfig.xml: no Legacy Name/Size or Enhanced "
            "PoolName/PoolSize pool entries were found"
        )

    patched = _patch_entries(
        legacy_entries,
        LEGACY_POOL_OVERRIDES,
        schema_name="Legacy",
    )
    patched += _patch_entries(
        enhanced_entries,
        ENHANCED_POOL_OVERRIDES,
        schema_name="Enhanced",
    )

    log.info("Patched %d pool size(s) in gameconfig.xml", patched)
    return etree.tostring(
        tree,
        pretty_print=False,
        encoding="UTF-8",
        xml_declaration=True,
    ).decode("utf-8")


def restore_enhanced_pool_profile(
    gameconfig_xml: str,
    receipt_pools: Mapping[str, object],
) -> str:
    """Undo only pool values proven to have been written by ALLIN1.

    The retired startup-map transaction recorded each pool's ``before`` and
    ``after`` value.  A later Repair may lower a value only when the installed
    document still equals that exact ``after`` value.  Larger or otherwise
    customized values are preserved, so quarantining the map pack cannot undo
    another modder's subsequent gameconfig tuning.
    """

    if not isinstance(gameconfig_xml, str) or not gameconfig_xml.strip():
        raise ValueError("gameconfig.xml must be non-empty XML text")
    if not isinstance(receipt_pools, Mapping) or not receipt_pools:
        raise ValueError("map activation receipt has no pool profile")

    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
    )
    try:
        tree = etree.parse(BytesIO(gameconfig_xml.encode("utf-8")), parser)
    except (UnicodeError, etree.XMLSyntaxError) as exc:
        raise ValueError(f"Invalid gameconfig.xml: {exc}") from exc

    _legacy_entries, enhanced_entries = _pool_entries(tree.getroot())
    installed = {
        (name_el.text or "").strip(): size_el
        for name_el, size_el in enhanced_entries
    }
    restored = 0
    for name, raw_record in receipt_pools.items():
        if name not in ENHANCED_POOL_OVERRIDES:
            raise ValueError(
                f"map activation receipt contains an unknown pool {name!r}"
            )
        if not isinstance(raw_record, Mapping):
            raise ValueError(
                f"map activation receipt pool {name!r} is not an object"
            )
        before = raw_record.get("before")
        after = raw_record.get("after")
        if (
            isinstance(before, bool)
            or isinstance(after, bool)
            or not isinstance(before, int)
            or not isinstance(after, int)
            or before < 0
            or after < before
        ):
            raise ValueError(
                f"map activation receipt pool {name!r} is invalid"
            )
        size_el = installed.get(name)
        if size_el is None:
            raise ValueError(
                f"installed Enhanced gameconfig is missing pool {name!r}"
            )
        try:
            current = int(size_el.get("value", ""))
        except ValueError as exc:
            raise ValueError(
                f"installed Enhanced gameconfig pool {name!r} is invalid"
            ) from exc
        if current == after and after != before:
            size_el.set("value", str(before))
            restored += 1
        elif current != before:
            log.info(
                "Preserved user-tuned Enhanced pool %s at %d while retiring "
                "the ALLIN1 map profile (%d -> %d)",
                name, current, before, after,
            )

    log.info("Restored %d retired ALLIN1 map pool value(s)", restored)
    if restored == 0:
        return gameconfig_xml
    return etree.tostring(
        tree,
        pretty_print=False,
        encoding="UTF-8",
        xml_declaration=True,
    ).decode("utf-8")
