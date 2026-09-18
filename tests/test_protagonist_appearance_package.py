"""Lifecycle coverage for a managed protagonist-appearance DLC package.

The fixture deliberately carries only inert bytes.  Appearance conversion and
native asset validity belong to their own tests; this proves that a schema-1
package (with no content descriptor) is surfaced as managed Content lifecycle
and owns DLC registration plus reversible payload state.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from allin1.mods import ModIntegrationService, ModManifest
from tests.test_desktop_service import apply, service as desktop_service


@pytest.fixture
def launcher_service(tmp_path: Path):
    """Reuse the synthetic writable launcher/game fixture in this module."""
    return desktop_service.__wrapped__(tmp_path)


def _package(root: Path) -> Path:
    package = root / "private.franklin-spongebob"
    package.mkdir()
    dlc = b"synthetic appearance dlc"
    (package / "dlc.rpf").write_bytes(dlc)
    (package / "mod.toml").write_text(
        "schema_version = 1\n"
        'id = "private.franklin-spongebob"\n'
        'name = "Private Franklin Appearance"\n'
        'version = "1.0.0"\n'
        'type = "mixed"\n'
        'editions = ["enhanced"]\n'
        'dependencies = ["openrpf"]\n'
        'conflicts = []\n'
        'dlc_packs = ["franklin_spongebob"]\n\n'
        '[[files]]\n'
        'source = "dlc.rpf"\n'
        'destination = "mods/update/x64/dlcpacks/franklin_spongebob/dlc.rpf"\n'
        f'sha256 = "{hashlib.sha256(dlc).hexdigest()}"\n',
        encoding="utf-8",
    )
    return package


def test_schema1_appearance_dlc_has_managed_content_lifecycle(
    launcher_service, tmp_path: Path, monkeypatch,
) -> None:
    game = launcher_service.game(launcher_service.config())
    registrations: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        ModIntegrationService, "_check_dependencies", lambda _self, _manifest: None,
    )
    monkeypatch.setattr(
        ModIntegrationService, "_set_dlc_registration",
        lambda _self, pack, enabled: registrations.append((pack, enabled)) or True,
    )

    manifest = ModManifest.load(_package(tmp_path))
    assert manifest.schema_version == 1
    assert manifest.extension is None
    assert manifest.dlc_packs == ("franklin_spongebob",)

    apply(launcher_service, "package_install", source=str(manifest.manifest_path))
    payload = game / "mods/update/x64/dlcpacks/franklin_spongebob/dlc.rpf"
    receipt = game / "scripts/.allin1/mods/private.franklin-spongebob.json"
    assert payload.is_file() and receipt.is_file()
    row = next(item for item in launcher_service.inspect({"module": "content"})["content"]
               if item["id"] == manifest.mod_id)
    assert row["managed_package"] is True
    assert row["settings"] == {"enabled": True}
    assert row["schema_settings"] == [{
        "key": "enabled", "label": "Enabled", "type": "boolean",
        "default": True,
        "description": (
            "Apply or restore this component's managed files. GTA V must be "
            "closed when the reviewed change is applied."
        ),
        "group": "Lifecycle",
    }]

    apply(launcher_service, "content_disable", id=manifest.mod_id)
    assert not payload.exists()
    assert payload.with_name("dlc.rpf.disabled").is_file()
    row = next(item for item in launcher_service.inspect({"module": "content"})["content"]
               if item["id"] == manifest.mod_id)
    assert row["settings"] == {"enabled": False}

    apply(launcher_service, "content_enable", id=manifest.mod_id)
    assert payload.is_file()
    apply(launcher_service, "package_uninstall", id=manifest.mod_id)
    assert not payload.exists()
    assert not receipt.exists()
    assert registrations == [
        ("franklin_spongebob", True),
        ("franklin_spongebob", False),
        ("franklin_spongebob", True),
        ("franklin_spongebob", False),
    ]
