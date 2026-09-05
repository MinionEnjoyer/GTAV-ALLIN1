"""Versioned generic weapon/RPF contracts; no dependency on a separate mod."""
from copy import deepcopy

import pytest

from allin1.mod_package_contract import (
    parse_workbench_contract, rpf_targets_overlap, split_nested_rpf_entry,
    validate_mod_schema_envelope,
)


def exact(schema=3):
    return {"schema_version": schema, "type": "rpf", "dependencies": ["openrpf"],
            "editions": ["enhanced"], "rpf_entries": [{"source": "payload/a.xml",
            "archive": "mods/update/update.rpf", "entry": "common/a.xml" if schema == 3 else "inner.rpf!common/a.xml",
            "sha256": "a" * 64, "original_sha256": "b" * 64}]}


@pytest.mark.parametrize("schema", [3, 4])
def test_exact_rpf_schemas_accept_only_declared_replacements(schema):
    assert validate_mod_schema_envelope(exact(schema)) == (schema, None)


@pytest.mark.parametrize("field,value", [
    ("extra", True), ("type", "mixed"), ("files", [{}]), ("dlc_packs", ["extra"]),
    ("dependencies", []), ("editions", ["enhanced", "legacy"]), ("editions", "enhanced"),
    ("rpf_entries", []), ("rpf_entries", "bad"), ("rpf_entries", [{}] * 129),
    ("rpf_entries", [None]), ("rpf_entries", [{}]),
])
@pytest.mark.parametrize("schema", [3, 4])
def test_exact_rpf_envelope_rejects_ambiguous_scope(schema, field, value):
    data = exact(schema)
    data[field] = value
    with pytest.raises(ValueError):
        validate_mod_schema_envelope(data)


@pytest.mark.parametrize("field,value", [
    ("source", "../escape"), ("source", "C:\\absolute"), ("source", "\\\\server\\share"),
    ("source", "a//b"), ("source", "a/./b"), ("source", " payload/x"),
    ("source", "payload/x."), ("source", "payload/NUL.txt"), ("source", "a/x:ads"),
    ("source", "a/\x00"), ("source", None), ("source", ""),
    ("archive", "update/update.rpf"), ("archive", "mods/data.xml"), ("archive", "mods/a.rpf!b.rpf"),
    ("entry", "inner.rpf!a.xml"), ("entry", "inner.rpf/a.xml"),
    ("sha256", "A" * 64), ("sha256", 123), ("original_sha256", "bad"),
])
def test_exact_rpf_member_rejects_unsafe_or_incomplete_evidence(field, value):
    data = exact()
    data["rpf_entries"][0][field] = value
    with pytest.raises(ValueError):
        validate_mod_schema_envelope(data)


@pytest.mark.parametrize("value", [None, "x" * 2049, "a.xml", "a.rpf!" + "b.rpf!" * 8 + "x.xml",
                                  "a.xml!b.xml", "a.rpf!b.rpf", "a.rpf/b.rpf!x.xml", "a.rpf!!x.xml"])
def test_nested_entry_requires_bounded_explicit_archive_layers(value):
    with pytest.raises(ValueError):
        split_nested_rpf_entry(value)


def test_nested_rpf_overlap_includes_parent_ownership_but_not_siblings():
    assert split_nested_rpf_entry("a.rpf!b.rpf!common\\x.xml") == ("a.rpf", "b.rpf", "common/x.xml")
    for left, right, overlaps in [("A.RPF!x.xml", "a.rpf", True), ("a.rpf", "a.rpf!x.xml", True),
                                   ("a\\x", "A/x", True), ("a.rpf!x.xml", "a.rpf!y.xml", False)]:
        assert rpf_targets_overlap(left, right) is overlaps


def enhancement():
    return {"id": "test.effect", "name": "Generic component effect", "mode": "scripted_vanilla_components",
            "weapon_components": [{"weapon_name": "WEAPON_PISTOL", "weapon_hash": "1B06D571",
                "component_name": "COMPONENT_TEST", "component_hash": "1234ABCD"}],
            "script_entry_points": ["Example.Controller"], "visual_assets": [{"dlc_pack": "example",
                "archive": "x64/example.rpf", "families": ["small"], "levels": 2,
                "model_pattern": "{family}_{level:02d}.ydr", "texture_dictionary": "example.ytd",
                "texture_pattern": "gradient_{level:02d}", "archetype_dictionary": "example.ytyp"}]}


@pytest.mark.parametrize("section,field,value", [
    ("root", "extra", 1), ("root", "id", "!"), ("root", "name", ""),
    ("root", "mode", "replace"), ("root", "weapon_components", []),
    ("root", "weapon_components", [None]), ("root", "script_entry_points", []),
    ("root", "script_entry_points", ["NotAType"]), ("root", "script_entry_points", ["Other.Controller"]),
    ("root", "visual_assets", []), ("root", "visual_assets", [None]),
    ("link", "extra", 1), ("link", "weapon_name", "PISTOL"), ("link", "component_name", "TEST"),
    ("link", "weapon_hash", "nohash"), ("link", "component_hash", None),
    ("asset", "extra", 1), ("asset", "dlc_pack", "a/b"), ("asset", "families", []),
    ("asset", "families", ["a/b"]), ("asset", "levels", True), ("asset", "levels", 1),
    ("asset", "levels", 257), ("asset", "base_model_pattern", "no_family"),
    ("asset", "model_pattern", "{family}.ydr"), ("asset", "texture_pattern", "gradient"),
    ("asset", "model_pattern", "{family}_{level}_{missing}"),
    ("asset", "base_model_pattern", "{family}_{missing}"),
    ("asset", "texture_pattern", "{level:broken}"),
    ("asset", "base_level_uses_unsuffixed", 1), ("asset", "base_level_uses_unsuffixed", True),
])
def test_workbench_contract_rejects_bad_fields_at_their_boundary(section, field, value):
    record = enhancement()
    target = record if section == "root" else record["weapon_components" if section == "link" else "visual_assets"][0]
    target[field] = value
    with pytest.raises(ValueError):
        parse_workbench_contract({"weapon_enhancements": [record]}, runtime_entry_points=["Example.Controller"])


def test_workbench_duplicates_and_optional_defaults():
    record = enhancement()
    parsed = parse_workbench_contract({"weapon_enhancements": [record]})[0]
    assert parsed.visual_assets[0].base_model_pattern is None
    assert parsed.visual_assets[0].base_level_uses_unsuffixed is False
    assert parsed.weapon_components[0].component_hash == "0x1234ABCD"
    assert parse_workbench_contract(None) == ()
    for records in ([None], [record, deepcopy(record)]):
        with pytest.raises(ValueError):
            parse_workbench_contract({"weapon_enhancements": records})
    record["weapon_components"] *= 2
    with pytest.raises(ValueError, match="duplicate vanilla weapon hashes"):
        parse_workbench_contract({"weapon_enhancements": [record]})
    with pytest.raises(ValueError, match="Unsupported.*field"):
        validate_mod_schema_envelope({"schema_version": 2, "allin1": {"extra": True}})
