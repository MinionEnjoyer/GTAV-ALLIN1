"""Recovery helpers operate exclusively on disposable, inert map payloads."""
from pathlib import Path

import pytest

from allin1 import installer


SPARSE = b'<CGameConfig><Pools><Item/><Item><Name>CVehicle</Name><Size value="512"/></Item><Item><Name>CVehicleModelInfo</Name><Size value="900"/></Item><Item><Name>CHandlingDataMgr</Name><Size value="900"/></Item></Pools></CGameConfig>'


def override_path(tmp_path):
    path = tmp_path / "onigiri/common/data/gameconfig.xml"
    path.parent.mkdir(parents=True)
    return path


@pytest.mark.parametrize("payload", [b"", b"x" * 4097, b"<invalid", b"\xff",
    SPARSE.replace(b"CGameConfig", b"Other"), SPARSE.replace(b'<Size value="512"/>', b""),
    SPARSE.replace(b'<Name>CVehicle</Name>', b""), SPARSE.replace(b'value="512"', b'value="bad"'),
    SPARSE.replace(b'value="512"', b""), SPARSE.replace(b"CVehicleModelInfo", b"CVehicle"),
    SPARSE.replace(b"CVehicle</Name>", b"</Name>"), SPARSE.replace(b'"512"', b'"1024"')])
def test_unrecognized_override_is_preserved_exactly(tmp_path, payload):
    path = override_path(tmp_path)
    path.write_bytes(payload)
    with pytest.raises(RuntimeError): installer._retire_known_sparse_onigiri_gameconfig(tmp_path)
    assert path.read_bytes() == payload
    assert list(path.parent.iterdir()) == [path]


def test_missing_and_directory_overrides(tmp_path):
    assert installer._retire_known_sparse_onigiri_gameconfig(tmp_path) is None
    path = override_path(tmp_path)
    path.mkdir()
    with pytest.raises(RuntimeError, match="non-file"):
        installer._retire_known_sparse_onigiri_gameconfig(tmp_path)
    assert path.is_dir()


@pytest.mark.parametrize("backup", ["absent", "matching", "different", "directory"])
def test_sparse_override_backup_ownership_and_restore(tmp_path, backup):
    path = override_path(tmp_path)
    path.write_bytes(SPARSE)
    saved = path.with_name("gameconfig.xml.allin1-retired.bak")
    if backup == "directory": saved.mkdir()
    elif backup != "absent": saved.write_bytes(SPARSE if backup == "matching" else b"user backup")
    if backup in {"different", "directory"}:
        with pytest.raises(RuntimeError, match="occupied"):
            installer._retire_known_sparse_onigiri_gameconfig(tmp_path)
        assert path.read_bytes() == SPARSE
        return
    retired = installer._retire_known_sparse_onigiri_gameconfig(tmp_path)
    assert retired == (path, saved) and not path.exists()
    assert saved.read_bytes() == SPARSE
    installer._restore_retired_onigiri_gameconfig(retired)
    assert path.read_bytes() == SPARSE
    installer._restore_retired_onigiri_gameconfig(retired)
    assert path.read_bytes() == saved.read_bytes() == SPARSE


@pytest.mark.parametrize("damage", ["missing-backup", "different-override", "directory-override", "copy-corruption"])
def test_restore_never_overwrites_a_different_user_override(tmp_path, monkeypatch, damage):
    path = override_path(tmp_path)
    saved = path.with_name("gameconfig.xml.allin1-retired.bak")
    if damage != "missing-backup": saved.write_bytes(SPARSE)
    if damage == "different-override": path.write_bytes(b"user changed config")
    elif damage == "directory-override": path.mkdir()
    elif damage == "copy-corruption":
        monkeypatch.setattr(installer.shutil, "copy2", lambda source, target: Path(target).write_bytes(b"corrupt transfer"))
    with pytest.raises(RuntimeError): installer._restore_retired_onigiri_gameconfig((path, saved))
    if damage == "different-override": assert path.read_bytes() == b"user changed config"
    elif damage == "directory-override": assert path.is_dir()
    else: assert not path.exists()
    if saved.exists(): assert saved.read_bytes() == SPARSE
    assert not path.with_name(path.name + ".allin1-restore.tmp").exists()
    installer._restore_retired_onigiri_gameconfig(None)


def test_retirement_does_not_delete_source_if_backup_copy_is_corrupt(tmp_path, monkeypatch):
    path = override_path(tmp_path)
    path.write_bytes(SPARSE)
    monkeypatch.setattr(installer.shutil, "copy2", lambda source, target: Path(target).write_bytes(b"corrupt transfer"))
    with pytest.raises(RuntimeError, match="verify"):
        installer._retire_known_sparse_onigiri_gameconfig(tmp_path)
    assert list(path.parent.iterdir()) == [path] and path.read_bytes() == SPARSE


@pytest.mark.parametrize("failures", [set(), {0}, {1}, {0, 1}])
def test_archive_recovery_attempts_both_original_payloads(tmp_path, monkeypatch, failures):
    calls = []
    def replace(tool, args, *, operation):
        index = len(calls)
        calls.append((tool, args, operation))
        if index in failures: raise OSError(f"synthetic restore {index}")
    monkeypatch.setattr(installer, "_map_patcher_command", replace)
    args = [tmp_path / name for name in ("tool", "game", "archive", "config", "list")]
    if failures:
        with pytest.raises(RuntimeError) as error:
            installer._restore_map_update_payloads(*args, archive_created=False)
        for index in failures: assert f"synthetic restore {index}" in str(error.value)
    else: installer._restore_map_update_payloads(*args, archive_created=False)
    assert len(calls) == 2
    assert [call[1][-1] for call in calls] == [str(args[3]), str(args[4])]
    assert all(call[1][:3] == ["replace-entry", str(args[1]), str(args[2])] for call in calls)


def test_new_archive_recovery_removes_only_owned_archive(tmp_path):
    archive = tmp_path / "new.rpf"
    canary = tmp_path / "original.rpf"
    archive.write_bytes(b"new")
    canary.write_bytes(b"preserve")
    installer._restore_map_update_payloads(tmp_path / "tool", tmp_path, archive, canary, canary, archive_created=True)
    assert not archive.exists() and canary.read_bytes() == b"preserve"


def test_dlclist_names_normalize_only_actual_registered_items():
    text = '<r xmlns="urn:gta"><Item> DLCpacks:\\MyPack\\ </Item><Item>dlcpacks:/OTHER/</Item><Item>dlcpacks:/</Item><Item/><Name>dlcpacks:/not-an-item</Name><Item>platform:/not-dlc</Item></r>'
    assert installer._dlclist_registered_pack_names(text) == {"mypack", "other"}
    assert not installer._dlclist_registers_allin1_maps(text)
    assert installer._dlclist_registers_allin1_maps('<r><Item>DLCpacks:/ALLIN1_MAPS/</Item></r>')
    for parse in (installer._dlclist_registered_pack_names, installer._dlclist_registers_allin1_maps):
        with pytest.raises(ValueError, match="Invalid dlclist"): parse("<broken")
