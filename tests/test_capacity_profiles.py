"""Tests for bounded, export-only capacity profile construction."""

from hashlib import sha256

import pytest

from allin1.capacity_profiles import build_profile, inspect_config, preset_targets


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _legacy_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- retain comment -->
<CGameConfig custom="retain"><pools>
  <Item><Name>CVehicle</Name><Size value="128" extra="keep"/><Unknown value="yes"/></Item>
  <Item><Name>CObject</Name><Size value="2048"/></Item>
</pools><Unrelated x="keep"/></CGameConfig>"""


def _enhanced_xml() -> str:
    return """<fwAllConfigs><ConfigArray><Item><Build>Any</Build><Platforms>Any</Platforms><SubPlatforms>Any</SubPlatforms><Config type="CGameConfig"><PoolSizes><Entries>
<Item><PoolName>FragmentStore</PoolName><PoolSize value="42000"/></Item>
<Item><PoolName>MetaDataStore</PoolName><PoolSize value="3200"/></Item>
</Entries></PoolSizes></Config></Item></ConfigArray></fwAllConfigs>"""


def _scoped_enhanced_xml(*, duplicate_x64: bool = False) -> str:
    duplicate = (
        "<Item><PoolName>Shared</PoolName><PoolSize value=\"31\"/></Item>"
        if duplicate_x64 else ""
    )
    return f"""<fwAllConfigs><ConfigArray>
<Item><Build>Any</Build><Platforms>Any</Platforms><SubPlatforms>Any</SubPlatforms><Config type="CGameConfig"><PoolSizes><Entries>
<Item><PoolName>Shared</PoolName><PoolSize value="10"/></Item>
<Item><PoolName>BaseOnly</PoolName><PoolSize value="20"/></Item>
</Entries></PoolSizes></Config></Item>
<Item><Build>any</Build><Platforms>x64</Platforms><SubPlatforms>any</SubPlatforms><Config type="CGameConfig"><PoolSizes><Entries>
<Item><PoolName>Shared</PoolName><PoolSize value="30"/></Item>{duplicate}
</Entries></PoolSizes></Config></Item>
<Item><Build>any</Build><Platforms>ps5</Platforms><SubPlatforms>any</SubPlatforms><Config type="CGameConfig"><PoolSizes><Entries>
<Item><PoolName>Shared</PoolName><PoolSize value="900"/></Item>
</Entries></PoolSizes></Config></Item>
<Item><Build>debug</Build><Platforms>any</Platforms><SubPlatforms>any</SubPlatforms><Config type="CGameConfig"><PoolSizes><Entries>
<Item><PoolName>Shared</PoolName><PoolSize value="800"/></Item>
</Entries></PoolSizes></Config></Item>
</ConfigArray></fwAllConfigs>"""


def test_inspect_detects_both_supported_schemas_and_hash():
    legacy = inspect_config(_legacy_xml())
    enhanced = inspect_config(_enhanced_xml())
    assert legacy["edition"] == "legacy"
    assert legacy["pools"] == {"CVehicle": 128, "CObject": 2048}
    assert legacy["source_sha256"] == _hash(_legacy_xml())
    assert enhanced["edition"] == "enhanced"
    assert enhanced["pools"]["FragmentStore"] == 42000


def test_build_only_changes_requested_attribute_and_preserves_document_content():
    source = _legacy_xml()
    output, receipt = build_profile(
        source, edition="legacy", game_build="b3258", targets={"CVehicle": 512},
        expected_source_sha256=_hash(source),
    )
    assert 'Size value="512" extra="keep"' in output
    assert "retain comment" in output and 'Unknown value="yes"' in output
    assert 'CObject</Name><Size value="2048"' in output
    assert receipt["changes"] == {"CVehicle": {"before": 128, "after": 512}}
    assert receipt["source_sha256"] == _hash(source)
    assert receipt["output_sha256"] == _hash(output)
    assert receipt["export_only"] is True and receipt["runtime_qualified"] is False
    assert receipt["schema_version"] == 1


def test_noop_is_deterministic_and_byte_identical():
    source = _legacy_xml()
    kwargs = dict(edition="legacy", game_build="b3258", targets={"CObject": 100}, expected_source_sha256=_hash(source))
    first = build_profile(source, **kwargs)
    second = build_profile(source, **kwargs)
    assert first == second
    assert first[0] == source
    assert first[1]["changes"] == {"CObject": {"before": 2048, "after": 2048}}


def test_presets_are_copies_and_stock_is_empty():
    assert preset_targets("legacy", "stock") == {}
    targets = preset_targets("enhanced", "addon-headroom")
    assert targets["FragmentStore"] == 52000
    targets["FragmentStore"] = 1
    assert preset_targets("enhanced", "addon-headroom")["FragmentStore"] == 52000


def test_enhanced_windows_release_resolves_base_then_x64_and_preserves_other_scopes():
    source = _scoped_enhanced_xml()
    inspected = inspect_config(source)
    assert inspected["pools"] == {"Shared": 30, "BaseOnly": 20}
    assert inspected["target_scope"] == "windows-release"
    assert [scope["scope"] for scope in inspected["scopes"]] == ["base", "x64"]
    output, receipt = build_profile(
        source, edition="enhanced", game_build="b3258", targets={"Shared": 40},
        expected_source_sha256=_hash(source),
    )
    assert '<Platforms>Any</Platforms>' in output and 'value="10"' in output
    assert '<Platforms>x64</Platforms>' in output and 'value="40"' in output
    assert '<Platforms>ps5</Platforms>' in output and 'value="900"' in output
    assert '<Build>debug</Build>' in output and 'value="800"' in output
    assert receipt["target_scope"] == "windows-release"


def test_enhanced_rejects_duplicate_only_within_one_scope():
    with pytest.raises(ValueError, match="duplicate"):
        inspect_config(_scoped_enhanced_xml(duplicate_x64=True))


def test_enhanced_rejects_unknown_windows_release_selector():
    source = _scoped_enhanced_xml().replace("<Platforms>x64</Platforms>", "<Platforms>win64</Platforms>")
    with pytest.raises(ValueError, match="unknown applicable Platforms"):
        inspect_config(source)


@pytest.mark.parametrize("selector", ["Build", "Platforms", "SubPlatforms"])
def test_enhanced_rejects_missing_scope_selectors(selector):
    source = _scoped_enhanced_xml().replace(
        f"<{selector}>Any</{selector}>", "", 1
    )
    with pytest.raises(ValueError, match=f"missing {selector} selector"):
        inspect_config(source)


@pytest.mark.parametrize("platform", ["Any", "x64"])
def test_enhanced_rejects_duplicate_applicable_scope_precedence(platform):
    scope = f"""<Item><Build>Any</Build><Platforms>{platform}</Platforms><SubPlatforms>Any</SubPlatforms><Config type="CGameConfig"><PoolSizes><Entries>
<Item><PoolName>Other</PoolName><PoolSize value="1"/></Item>
</Entries></PoolSizes></Config></Item>"""
    source = _scoped_enhanced_xml().replace("</ConfigArray>", scope + "</ConfigArray>")
    with pytest.raises(ValueError, match="duplicate applicable"):
        inspect_config(source)


@pytest.mark.parametrize("payload", [
    "<!DOCTYPE CGameConfig []><CGameConfig/>",
    "<!ENTITY x 'boom'><CGameConfig/>",
    "<CGameConfig><pools><Item><Name>x</Name><Size value='1'/></Item></pools>",
    "<Other/>",
])
def test_rejects_malicious_or_malformed_xml(payload):
    with pytest.raises(ValueError):
        inspect_config(payload)


def test_rejects_duplicate_names_and_stale_source():
    duplicate = "<CGameConfig><pools><Item><Name>x</Name><Size value='1'/></Item><Item><Name>x</Name><Size value='2'/></Item></pools></CGameConfig>"
    with pytest.raises(ValueError, match="duplicate"):
        inspect_config(duplicate)
    source = _legacy_xml()
    with pytest.raises(ValueError, match="does not match"):
        build_profile(source, edition="legacy", game_build="b3258", targets={}, expected_source_sha256="0" * 64)


@pytest.mark.parametrize("target", [True, 0, -1, 2_147_483_648, "512"])
def test_rejects_invalid_targets(target):
    source = _legacy_xml()
    with pytest.raises(ValueError):
        build_profile(source, edition="legacy", game_build="b3258", targets={"CVehicle": target}, expected_source_sha256=_hash(source))


def test_rejects_missing_target_edition_mismatch_and_bad_build_label():
    source = _legacy_xml()
    common = dict(targets={}, expected_source_sha256=_hash(source))
    with pytest.raises(ValueError, match="edition mismatch"):
        build_profile(source, edition="enhanced", game_build="b3258", **common)
    with pytest.raises(ValueError, match="build label"):
        build_profile(source, edition="legacy", game_build="bad build", **common)
    with pytest.raises(ValueError, match="missing"):
        build_profile(source, edition="legacy", game_build="b3258", targets={"Absent": 1}, expected_source_sha256=_hash(source))
