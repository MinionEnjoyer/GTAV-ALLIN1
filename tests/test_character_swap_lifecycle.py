"""Synthetic lifecycle coverage for a private protagonist asset override.

The test intentionally models archive members as an in-memory store.  It
proves package ownership and transactional lifecycle behavior without needing
GTA V assets or touching an installed game.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from allin1.mods import ModIntegrationService, ModManifest


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_schema1_dlc(root: Path, mod_id: str) -> Path:
    package = root / "schema1"
    package.mkdir()
    payload = b"old private appearance dlc"
    (package / "dlc.rpf").write_bytes(payload)
    (package / "mod.toml").write_text(
        "\n".join((
            "schema_version = 1",
            f'id = "{mod_id}"',
            'name = "Private Appearance DLC"',
            'version = "1.0.0"',
            'type = "mixed"',
            'editions = ["enhanced"]',
            'dependencies = ["openrpf"]',
            'dlc_packs = ["private_appearance"]',
            "",
            "[[files]]",
            'source = "dlc.rpf"',
            'destination = "mods/update/x64/dlcpacks/private_appearance/dlc.rpf"',
            f'sha256 = "{_digest(payload)}"',
            "",
        )),
        encoding="utf-8",
    )
    return package


def _write_schema4_override(root: Path, mod_id: str, original: bytes) -> Path:
    package = root / f"schema4-{mod_id}"
    package.mkdir()
    replacement = b"controlled exact character override"
    (package / "franklin.ymt").write_bytes(replacement)
    (package / "mod.toml").write_text(
        "\n".join((
            "schema_version = 4",
            f'id = "{mod_id}"',
            'name = "Private Exact Appearance Override"',
            'version = "2.0.0"',
            'type = "rpf"',
            'editions = ["enhanced"]',
            'dependencies = ["openrpf"]',
            'conflicts = []',
            "",
            "[[rpf_entries]]",
            'source = "franklin.ymt"',
            'archive = "mods/update/update.rpf"',
            'entry = "x64/levels/gta5/props.rpf!common/data/franklin.ymt"',
            f'sha256 = "{_digest(replacement)}"',
            f'original_sha256 = "{_digest(original)}"',
            "",
        )),
        encoding="utf-8",
    )
    return package


def test_same_id_dlc_to_nested_exact_override_is_fail_closed_then_new_id_is_reversible(
    tmp_path: Path, monkeypatch,
) -> None:
    """Exact entries need an explicit reviewed uninstall before a new package."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"synthetic executable")
    stock_archive = game / "update" / "update.rpf"
    stock_archive.parent.mkdir()
    stock_archive.write_bytes(b"unmodified stock archive")
    original = b"stock franklin entry"
    nested_entry = "x64/levels/gta5/props.rpf!common/data/franklin.ymt"
    entries = {nested_entry: original}
    registrations: list[tuple[str, bool]] = []
    service = ModIntegrationService(game)

    monkeypatch.setattr(service, "_check_dependencies", lambda _manifest: None)
    monkeypatch.setattr(
        service, "_set_dlc_registration",
        lambda pack, enabled: registrations.append((pack, enabled)) or True,
    )

    def extract(_archive, entry, output, *, allow_missing=False):
        value = entries.get(str(entry))
        if value is None:
            if allow_missing:
                return False
            raise RuntimeError("missing")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(value)
        return True

    def replace(_archive, entry, payload, *, expected_sha256=None):
        current = entries.get(str(entry))
        if expected_sha256 is not None:
            assert current is not None and _digest(current) == expected_sha256
        entries[str(entry)] = Path(payload).read_bytes()

    monkeypatch.setattr(service, "_extract_rpf_entry", extract)
    monkeypatch.setattr(service, "_replace_rpf_entry", replace)
    monkeypatch.setattr(service, "_delete_rpf_entry", lambda _a, entry: entries.pop(str(entry), None))

    mod_id = "private.franklin-spongebob"
    service.install(ModManifest.load(_write_schema1_dlc(tmp_path, mod_id)))
    old_payload = game / "mods/update/x64/dlcpacks/private_appearance/dlc.rpf"
    assert old_payload.is_file()

    # A same-id transition has no partial payload cleanup or archive writes. The user
    # must deliberately remove the older package first, rather than implicitly
    # changing a package's scope during an update.
    with pytest.raises(ValueError, match="requires uninstalling"):
        service.install(ModManifest.load(_write_schema4_override(tmp_path, mod_id, original)))
    assert old_payload.is_file()
    # The installer reasserts the prior enabled registration as rollback safety,
    # but does not deregister the old package or change its payload.
    assert registrations == [
        ("private_appearance", True),
        ("private_appearance", True),
    ]
    assert entries[nested_entry] == original
    assert (service.state_root / f"{mod_id}.json").is_file()

    service.uninstall(mod_id)
    assert not old_payload.exists()
    assert registrations == [
        ("private_appearance", True),
        ("private_appearance", True),
        ("private_appearance", False),
    ]

    exact_id = "private.franklin-spongebob-exact"
    service.install(ModManifest.load(_write_schema4_override(tmp_path, exact_id, original)))
    receipt = json.loads((service.state_root / f"{exact_id}.json").read_text(encoding="utf-8"))
    assert receipt["dlc_packs"] == []
    assert receipt["rpf_entries"][0]["original_sha256"] == _digest(original)
    assert entries[nested_entry] == b"controlled exact character override"
    assert stock_archive.read_bytes() == b"unmodified stock archive"

    service.set_enabled(exact_id, False)
    assert entries[nested_entry] == original
    service.set_enabled(exact_id, True)
    assert entries[nested_entry] == b"controlled exact character override"
    service.uninstall(exact_id)
    assert entries[nested_entry] == original
    assert not (service.state_root / f"{exact_id}.json").exists()
