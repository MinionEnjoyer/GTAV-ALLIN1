"""Real uninstall and preflight regressions in disposable game trees only."""
import os
import subprocess
from unittest.mock import Mock

import pytest

from allin1 import installer
from allin1.config import Config
from tests.test_desktop_service import service, apply


SAVES = (
    "ALLIN1.toml", "ALLIN1.ini", "ALLIN1_characters.json", "ALLIN1_garage.json",
    "ALLIN1_garages.json", "ALLIN1_floor_garage.json", "ALLIN1_floor_themes.json",
    "ALLIN1_davis_garage.json", "ALLIN1_davis_customization.json",
    "ALLIN1_garment_factory_garage.json", "ALLIN1_rural_garage.json",
    "ALLIN1_paleto_garage.json", "ALLIN1_yacht_helipad.json",
    "ALLIN1_gbay_preferences.json", "ALLIN1_garage.quarantine.json",
    "ALLIN1_future_user_data.json",
)


def test_reviewed_uninstall_keeps_every_save_and_backup(service, monkeypatch):
    game = service.game(service.config())
    scripts = game / "scripts"; scripts.mkdir()
    canaries = {}
    for name in SAVES:
        for suffix in ("", ".bak"):
            path = scripts / (name + suffix)
            content = b"# retained preferences\n" if name.endswith(("toml", "ini")) else b'{"user":"saved"}'
            path.write_bytes(content); canaries[path] = content
    legacy = game / "ALLIN1/User authored project/notes.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy private work"); canaries[legacy] = legacy.read_bytes()
    (scripts / "ALLIN1.dll").write_bytes(b"inert client fixture")
    unrelated = scripts / "unrelated-mod.dll"
    unrelated.write_bytes(b"another mod"); canaries[unrelated] = unrelated.read_bytes()
    # No archive writer is exercised against a game. These fixtures contain no
    # real RPFs; the rest of the actual uninstall domain executes unmodified.
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())
    review = service.review({"action": "uninstall"})
    assert "not a data purge" in review["preservation"]
    service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert not (scripts / "ALLIN1.dll").exists()
    assert all(path.read_bytes() == content for path, content in canaries.items())
    # A second removal must be harmless to retained data as well.
    apply(service, "uninstall")
    assert all(path.read_bytes() == content for path, content in canaries.items())


@pytest.mark.parametrize("operation", ["install", "uninstall"])
@pytest.mark.parametrize("location", ["scripts/client.dll", "mods/user.rpf", "plugins/ui/index.html", "ALLIN1/notes.json", "commandline.txt"])
def test_linked_installation_file_refuses_all_writes(tmp_path, monkeypatch, operation, location):
    game = tmp_path / "game with spaces"; game.mkdir()
    (game / "GTA5.exe").write_bytes(b"not executable")
    outside = tmp_path / "outside"; outside.write_bytes(b"outside canary")
    link = game / location; link.parent.mkdir(parents=True, exist_ok=True)
    os.link(outside, link)
    old = game / "ALLIN1.dll"; old.write_bytes(b"must survive preflight")
    monkeypatch.setattr(installer, "resolve_gta_path", lambda _: game)
    config = Config.default()
    with pytest.raises(ValueError, match="linked"):
        if operation == "install": installer.install(config, Mock())
        else: installer.uninstall(config)
    assert outside.read_bytes() == b"outside canary"
    assert old.read_bytes() == b"must survive preflight"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction boundary")
@pytest.mark.parametrize("location", ["root", "scripts", "mods", "plugins", "ALLIN1"])
def test_junctions_are_rejected_before_install_or_uninstall(tmp_path, monkeypatch, location):
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "canary").write_bytes(b"preserve")
    game = tmp_path / "game"
    if location != "root": game.mkdir()
    link = game if location == "root" else game / location
    result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    monkeypatch.setattr(installer, "resolve_gta_path", lambda _: game)
    try:
        for operation in (lambda: installer.install(Config.default(), Mock()), lambda: installer.uninstall(Config.default())):
            with pytest.raises(ValueError, match="junction"):
                operation()
            assert list(outside.iterdir()) == [outside / "canary"]
            assert (outside / "canary").read_bytes() == b"preserve"
    finally:
        assert link.is_relative_to(tmp_path) and link.lstat().st_file_attributes & 0x400
        os.rmdir(link)  # Remove our junction only, never its target.


def test_directory_file_collision_is_read_only(tmp_path, monkeypatch):
    game = tmp_path / "game"; game.mkdir()
    (game / "scripts").write_bytes(b"user file")
    monkeypatch.setattr(installer, "resolve_gta_path", lambda _: game)
    with pytest.raises(ValueError, match="not a directory"):
        installer.uninstall(Config.default())
    assert (game / "scripts").read_bytes() == b"user file"
