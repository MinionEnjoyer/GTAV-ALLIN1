"""Legacy preference import never mutates its source, game, or existing data."""
from pathlib import Path
import json
import os

import pytest

from allin1.config import Config
from allin1.desktop_service import LauncherService, serializable
from allin1 import preference_migration as migration
from allin1.release_paths import tree_files


def snapshot(root):
    return {name: path.read_bytes() for name, path in tree_files(root).items()}


@pytest.fixture
def layout(tmp_path):
    old = tmp_path / "Previous Launcher with spaces"
    (old / "profiles").mkdir(parents=True)
    config = Config.default()
    config.script.ui_scale = 1.25
    config.save(old / "config.toml")
    config.save(old / "profiles/Weekend setup.toml")
    (old / "config.toml").write_text((old / "config.toml").read_text() + '\n[future_preferences]\nkeep = "verbatim"\n')
    canary = tmp_path / "outside.canary"
    canary.write_bytes(b"preserved")
    return old, tmp_path / "New preferences"


def test_review_and_import_missing_preferences_preserve_source_bytes(layout, tmp_path):
    source, state = layout
    before = snapshot(tmp_path)
    source_before = snapshot(source)
    plan, _ = migration.prepare(source, state)
    assert snapshot(tmp_path) == before and not state.exists()
    assert plan["copy_count"] == 2
    result = migration.apply(source, state, plan["plan_sha256"])
    assert snapshot(source) == source_before
    assert (state / "config.toml").read_bytes() == before[source.name + "/config.toml"]
    assert (state / "profiles/Weekend setup.toml").read_bytes() == (source / "profiles/Weekend setup.toml").read_bytes()
    assert json.loads(Path(result["receipt"]).read_text())["kind"] == "launcher_preferences_imported"
    assert (tmp_path / "outside.canary").read_bytes() == b"preserved"
    assert (state / "config.toml").stat().st_nlink == 1


def test_existing_preferences_are_preserved_and_disclosed(layout):
    source, state = layout
    state.mkdir()
    Config.default().save(state / "config.toml")
    before = (state / "config.toml").read_bytes()
    plan, _ = migration.prepare(source, state)
    assert plan["copy_count"] == 1 and plan["preserve_count"] == 1
    result = migration.apply(source, state, plan["plan_sha256"])
    assert result["preserved"] == ["config.toml"]
    assert (state / "config.toml").read_bytes() == before
    plan, _ = migration.prepare(source, state)
    with pytest.raises(ValueError, match="nothing will be overwritten"):
        migration.apply(source, state, plan["plan_sha256"])


@pytest.mark.parametrize("changed", ["source", "destination", "new-profile"])
def test_changed_source_or_destination_requires_fresh_review(layout, changed):
    source, state = layout
    plan, _ = migration.prepare(source, state)
    if changed == "source":
        (source / "config.toml").write_text("# changed\n")
    elif changed == "destination":
        state.mkdir()
        (state / "config.toml").write_bytes(b"do not overwrite")
    else:
        Config.default().save(source / "profiles/New profile.toml")
    before = snapshot(source.parent)
    with pytest.raises(ValueError, match="changed"):
        migration.apply(source, state, plan["plan_sha256"])
    assert snapshot(source.parent) == before


def test_invalid_or_oversized_preferences_fail_before_destination_writes(layout):
    source, state = layout
    for data in (b"invalid = [", b"#" * (migration.MAX_BYTES + 1)):
        (source / "config.toml").write_bytes(data)
        with pytest.raises(ValueError):
            migration.prepare(source, state)
        assert not state.exists()


def test_duplicate_case_and_unsafe_profile_names_are_rejected(layout, monkeypatch):
    source, state = layout
    names = [source / "profiles/Weekend setup.toml", source / "profiles/weekend SETUP.toml"]
    original = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda path: iter(names) if path == source / "profiles" else original(path))
    with pytest.raises(ValueError, match="Duplicate"):
        migration.prepare(source, state)
    names[:] = [source / "profiles/ bad.toml"]
    with pytest.raises(ValueError, match="not normalized"):
        migration.prepare(source, state)
    assert not state.exists()


def test_linked_source_and_overlapping_roots_are_rejected(layout):
    source, state = layout
    os.link(source / "config.toml", source / "linked.toml")
    with pytest.raises(ValueError, match="Hard-linked"):
        migration.prepare(source, state)
    for destination in (source, source / "nested", source.parent):
        with pytest.raises(ValueError, match="separate"):
            migration.prepare(source, destination)
    assert not state.exists()


def test_mid_commit_failure_rolls_back_only_files_created_by_import(layout, monkeypatch):
    source, state = layout
    plan, _ = migration.prepare(source, state)
    original = os.link
    def fail_second(src, dst):
        if Path(dst).suffix == ".toml" and Path(dst).parent.name == "profiles":
            raise OSError("simulated publication failure")
        original(src, dst)
    monkeypatch.setattr(os, "link", fail_second)
    before = snapshot(source)
    with pytest.raises(OSError, match="simulated"):
        migration.apply(source, state, plan["plan_sha256"])
    assert snapshot(state) == {} and snapshot(source) == before


def test_reviewed_service_import_is_local_single_use_and_adopts_configuration(layout, tmp_path):
    source, state = layout
    project = tmp_path / "Current project"
    project.mkdir()
    service = LauncherService(project, state)
    request = {"action": "import_preferences", "source": str(source), "config": serializable(Config.default()), "migration_sha256": "forged"}
    review = service.review(request)
    assert not review["game_write"] and review["migration"]["copy_count"] == 2
    assert review["request"]["migration_sha256"] != "forged"
    result = service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert result["saved_config"]["script"]["ui_scale"] == 1.25
    assert service.profiles.list() == ["Weekend setup"]
    with pytest.raises(ValueError, match="already used"):
        service.apply({"review_id": review["review_id"], "confirmed": True})


def test_failure_unlinking_staged_link_still_rolls_back_publication(layout, monkeypatch):
    source, state = layout
    plan, _ = migration.prepare(source, state)
    original = Path.unlink
    failed = False
    def fail_once(path, *args, **kwargs):
        nonlocal failed
        if not failed and path.parent.name.startswith(".preference-import-"):
            failed = True
            raise OSError("staging unlink failed")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_once)
    with pytest.raises(OSError, match="staging unlink"):
        migration.apply(source, state, plan["plan_sha256"])
    assert failed and snapshot(state) == {}
