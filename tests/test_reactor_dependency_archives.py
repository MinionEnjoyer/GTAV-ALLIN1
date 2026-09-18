"""Opt-in real release ZIP lifecycle checks, isolated from installed games.

Set REACTOR_RELEASE_TEST_DIR to a directory containing both pinned releases.
Only the test GTA executable identity is substituted; archive and UI hashes,
ZIP inspection, ownership, copies, repair and uninstall are production code.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from allin1 import reactor_dependency as dep


@pytest.mark.packaged_integration
@pytest.mark.parametrize("enhanced", [False, True])
def test_published_archive_install_repair_and_uninstall(tmp_path, monkeypatch, enhanced):
    directory = os.environ.get("REACTOR_RELEASE_TEST_DIR")
    if not directory:
        pytest.skip("Set REACTOR_RELEASE_TEST_DIR for the real-release lifecycle test")
    pinned = dep.RELEASES[enhanced]
    archive = Path(directory) / f"ReactorV-{dep.VERSION}-{pinned.edition}-live-test.zip"
    assert archive.is_file()
    assert dep._sha(archive) == pinned.sha256
    assert archive.stat().st_size == pinned.size
    root = tmp_path / "fake GTA"
    root.mkdir()
    (root / pinned.game_executable).write_bytes(b"isolated game fixture")
    monkeypatch.setitem(dep.RELEASES, enhanced, replace(pinned, game_sha256=hashlib.sha256(b"isolated game fixture").hexdigest()))
    monkeypatch.setattr(dep, "_download", lambda *_a, **_kw: archive)
    monkeypatch.setattr(dep, "_assert_game_closed", lambda: None)
    other = root / "scripts/ReactorV/AnotherMod.plugin"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"independent mod")
    dep.install_dependency(root, enhanced)
    from allin1.reactor_bootstrap import inspect_reactor_installation
    startup = inspect_reactor_installation(root)
    assert startup.available and startup.native_bootstrap
    receipt = json.loads((root / dep.RECEIPT).read_text())
    owner = json.loads((root / dep.CONSUMER_RECEIPT).read_text())
    assert receipt["archive_sha256"] == pinned.sha256
    assert len(owner["files"]) >= 17
    assert any(name.startswith(dep.UI_ROOT + "assets/allin1/weapons/") for name in owner["files"])
    settings = root / "scripts/ReactorV/ReactorV.json"
    original = json.loads(settings.read_text(encoding="utf-8-sig"))
    original["renderer"] = "directx"
    settings.write_text(json.dumps(original), encoding="utf-8")
    expected_settings = settings.read_bytes()
    dep.install_dependency(root, enhanced)
    assert settings.read_bytes() == expected_settings
    dep.remove_consumer(root)
    assert inspect_reactor_installation(root).available
    assert other.read_bytes() == b"independent mod"
    assert settings.read_bytes() == expected_settings
    with zipfile.ZipFile(archive) as package:
        entries = {name.replace("\\", "/"): name for name in package.namelist()}
        for name, sha in receipt["files"].items():
            if name in dep.CONFIGS:
                continue
            assert dep._sha(root / name) == sha, name
            if name.startswith(dep.UI_ROOT):
                assert (root / name).read_bytes() == package.read(entries[name])
    assert not (root / dep.CONSUMER_RECEIPT).exists()
