import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("documentation_audit", ROOT / "tools/documentation_audit.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def fixture(tmp_path, text="[Guide](guide.md#install)", status="current"):
    directory = tmp_path / "docs"; directory.mkdir()
    (directory / "README.md").write_text(text, encoding="utf-8")
    (directory / "guide.md").write_text("# Guide\n\n## Install\n", encoding="utf-8")
    (directory / "catalog.json").write_text(json.dumps({"schema_version": 1, "documents": {
        "docs/README.md": status, "docs/guide.md": "current"}}), encoding="utf-8")
    return directory


def test_owned_documentation_and_generated_references_match_source():
    result = docs.audit(ROOT, expected_references={
        "docs/configuration-reference.md": docs.render_config(),
        "docs/cli-reference.md": docs.render_cli("launcher"),
    })
    assert result["status"] == "PASS", result["errors"]
    assert result["external_urls"] == "NOT TESTED"
    assert result["release_ready"] is False
    from allin1.release import PUBLIC_ROOT_FILES
    catalog = json.loads((ROOT / "docs/catalog.json").read_text())
    public_docs = {name for name in catalog["documents"] if not name.startswith(("tests/", "native/"))}
    assert public_docs <= set(PUBLIC_ROOT_FILES)


def test_live_checklist_covers_the_current_acceptance_schema():
    from allin1.release_acceptance import CHECKS
    text = (ROOT / "tests/IN_GAME_CHECKLIST.md").read_text()
    current = text.split("## Historical feature and fixture checklist")[0]
    for checks in CHECKS.values():
        assert all(f"`{name}`" in current for name in checks)
    assert "explicit approval" in current and "independent acceptance" in current


def test_release_notes_are_current_only_and_disclose_unsigned_distribution():
    from allin1 import __version__
    text = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert [line for line in text.splitlines() if line.startswith("# ")] == [f"# GTA V ALLIN1 {__version__} — unsigned portable release"]
    assert "v0.6.5" in text and f"**Release `v{__version__}`.**" in text
    assert "release_qualified" in text and "incomplete" in text
    assert [line for line in text.splitlines() if line.startswith("## ")] == ["## What's new", "## Download and trust", "## Release status"]
    assert "**Unsigned manual download.**" in text
    assert "SHA-256" in text and "signature verification" in text
    assert len(text.split()) < 450
    history = (ROOT / "docs/archive/release-notes-before-0.6.4.md").read_text(encoding="utf-8")
    assert "# GTA V ALLIN1 0.6.1" in history


def test_full_release_milestone_requires_tkinter_removal():
    guide = (ROOT / "docs/release-0.6.4.md").read_text(encoding="utf-8")
    milestone = guide.split("## Mandatory 0.6.4 full-release milestone")[1].split("## Release scope")[0]
    for requirement in ("both", "Tkinter", "_tkinter", "91%", "80%", "unsigned manual", "signature verification"):
        assert requirement.lower() in milestone.lower()


@pytest.mark.parametrize("link", ["[missing](gone.md)", "[anchor](guide.md#absent)", "[escape](../../outside.md)", '[reference][ref]\n\n[ref]: gone.md', '<img src="missing.png" />'])
def test_missing_links_headings_and_outside_paths_fail(tmp_path, link):
    fixture(tmp_path, link)
    assert docs.audit(tmp_path)["status"] == "FAIL"


def test_code_examples_and_external_urls_are_not_fetched(tmp_path):
    fixture(tmp_path, '[Guide](guide.md#install)\n[Web](https://example.invalid)\n```md\n[fake](absent.md)\n```\n')
    assert docs.audit(tmp_path)["status"] == "PASS"


def test_percent_encoded_local_names_and_heading_duplicates(tmp_path):
    directory = fixture(tmp_path, '[Guide](<guide%20with%20spaces.md#same-1>)')
    (directory / "guide with spaces.md").write_text("# Same\n## Same\n", encoding="utf-8")
    catalog = json.loads((directory / "catalog.json").read_text())
    catalog["documents"]["docs/guide with spaces.md"] = "reference"
    (directory / "catalog.json").write_text(json.dumps(catalog))
    assert docs.audit(tmp_path)["status"] == "PASS"


def test_new_document_requires_classification(tmp_path):
    directory = fixture(tmp_path)
    (directory / "unreviewed.md").write_text("# New guide")
    assert "Unclassified" in docs.audit(tmp_path)["errors"][0]


def test_generated_reference_drift_is_not_a_pass(tmp_path):
    fixture(tmp_path)
    result = docs.audit(tmp_path, expected_references={"docs/guide.md": "new source"})
    assert "differs from current source" in result["errors"][0]


def test_historical_material_requires_a_prominent_notice(tmp_path):
    directory = fixture(tmp_path, "Old instructions", "historical")
    assert docs.audit(tmp_path)["status"] == "FAIL"
    (directory / "README.md").write_text("# Historical evidence\n\n[old fixture](gone.md)")
    assert docs.audit(tmp_path)["status"] == "PASS"


@pytest.mark.parametrize("case", ["empty", "bad-schema", "missing-document", "unknown-status"])
def test_catalog_fails_closed(tmp_path, case):
    directory = fixture(tmp_path)
    path = directory / "catalog.json"
    value = json.loads(path.read_text())
    if case == "empty": value["documents"] = {}
    elif case == "bad-schema": value["schema_version"] = True
    elif case == "missing-document": value["documents"]["docs/absent.md"] = "current"
    else: value["documents"]["docs/guide.md"] = "probably-current"
    path.write_text(json.dumps(value))
    if case in {"empty", "bad-schema"}:
        with pytest.raises(ValueError): docs.audit(tmp_path)
    else: assert docs.audit(tmp_path)["status"] == "FAIL"


def test_reference_generation_never_executes_cli_callbacks(monkeypatch):
    from allin1.cli import main
    monkeypatch.setattr(main, "callback", lambda **_: pytest.fail("Documentation executed a command"))
    output = docs.render_cli("launcher")
    assert "allin1 install" in output and "allin1 uninstall" in output
    assert docs.cell("a|b\nc") == "a\\|b c"
