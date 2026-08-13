"""End-to-end orchestration tests for preview packaging and helper tools."""

from pathlib import Path
import struct
from unittest.mock import Mock

import pytest

from allin1 import installer
from allin1.preview_assets import PreviewMergeResult


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def _layout(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    previews = dist / "previews"
    previews.mkdir(parents=True)
    (previews / "alpha.png").touch()
    data = project / "data"
    data.mkdir()
    (data / "vehicles.toml").write_text(
        '[[vehicles]]\nmodel="alpha"\nname="Alpha"\nclass="super"\nmanufacturer="A"\n'
    )
    (data / "weapons.toml").write_text(
        '[[weapons]]\nname="WEAPON_TEST"\nlabel="Test"\ncategory="pistols"\nprice=10\n'
    )
    tools = project / "tools"
    (tools / "RpfPatcher").mkdir(parents=True)
    (tools / "YTDToolio.exe").touch()
    (tools / "RpfPatcher" / "RpfPatcher.exe").touch()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    return project, dist, tools


@pytest.mark.parametrize("missing,warning", [
    ("previews", "Preview images not found"),
    ("rpf", "RpfPatcher.exe missing"),
])
def test_preview_deploy_reports_missing_inputs(tmp_path, monkeypatch, missing, warning):
    _project, dist, tools = _layout(tmp_path, monkeypatch)
    if missing == "previews":
        (dist / "previews").rename(dist / "gone")
    else:
        (tools / "RpfPatcher" / "RpfPatcher.exe").unlink()
    result = installer.InstallResult(tmp_path)
    installer._deploy_preview_dlc(tmp_path, result)
    assert any(warning in item for item in result.warnings)


def test_preview_deploy_builds_and_deploys_curated_assets(tmp_path, monkeypatch):
    _project, dist, _tools = _layout(tmp_path, monkeypatch)
    from allin1 import preview_assets
    from allin1.generators import ytd_builder

    merge = Mock(return_value=PreviewMergeResult(1, ("bad.png",), ()))
    monkeypatch.setattr(preview_assets, "merge_previews", merge)

    def build(_source, _logo, output, _tools, models, **_kwargs):
        output.mkdir(parents=True)
        ytd = output / "allin1_prev_01.ytd"
        ytd.write_bytes(b"ytd")
        assert models == ["alpha"]
        return [ytd]
    monkeypatch.setattr(ytd_builder, "build_ytd_files", build)

    calls = []
    def run(args, **_kwargs):
        calls.append(args)
        if "build-dlc" in args:
            Path(args[3]).write_bytes(b"valid-dlc-rpf")
        return Mock(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=True)

    assert installer._deploy_preview_dlc(tmp_path, result) is True

    assert "Ignored 1 invalid preview capture(s)." in result.warnings
    assert merge.call_args_list[0].args[0] == [dist / "previews"]
    assert merge.call_args_list[1].args[0] == [dist / "weapon_previews"]
    assert merge.call_args_list[2].args[0] == [dist / "equipment_previews"]
    assert any("build-dlc" in args for args in calls)
    assert any("verify-dlc" in args for args in calls)
    assert any("patch" in args for args in calls)
    assert (tmp_path / "mods/update/x64/dlcpacks/allin1_previews/dlc.rpf").exists()


@pytest.mark.parametrize("stage", ["convert-gen9", "build-dlc", "verify-dlc", "patch"])
def test_preview_deploy_surfaces_tool_failures(tmp_path, monkeypatch, stage):
    _layout(tmp_path, monkeypatch)
    from allin1 import preview_assets
    from allin1.generators import ytd_builder
    monkeypatch.setattr(preview_assets, "merge_previews",
                        Mock(return_value=PreviewMergeResult(1, (), ())))
    def build(_a, _b, output, _d, _e, **_kwargs):
        output.mkdir(parents=True, exist_ok=True)
        ytd = output / "one.ytd"
        ytd.write_bytes(b"ytd")
        return [ytd]
    monkeypatch.setattr(ytd_builder, "build_ytd_files", build)
    def run(args, **_kwargs):
        if "build-dlc" in args and stage != "build-dlc":
            Path(args[3]).write_bytes(b"valid-dlc-rpf")
        return Mock(returncode=1 if stage in args else 0, stdout="", stderr="boom")
    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=(stage == "convert-gen9"))
    with pytest.raises(RuntimeError, match=stage):
        installer._deploy_preview_dlc(tmp_path, result)


def test_openrpf_detection_requires_nonempty_plugin_and_loader(tmp_path):
    _write_pe(tmp_path / "OpenRPF.asi")
    assert installer._check_openrpf(tmp_path, enhanced=True) is False
    _write_pe(tmp_path / "xinput1_4.dll")
    assert installer._check_openrpf(tmp_path, enhanced=True) is True
    _write_pe(tmp_path / "OpenIV.asi")
    assert installer._check_openrpf(tmp_path, enhanced=True) is False


def test_remove_preview_pack_only_removes_owned_directories(tmp_path):
    owned = tmp_path / "mods/update/x64/dlcpacks/allin1_previews"
    unrelated = tmp_path / "mods/update/x64/dlcpacks/user_pack"
    owned.mkdir(parents=True); unrelated.mkdir(parents=True)
    removed = installer._remove_preview_pack(tmp_path)
    assert removed == [owned]
    assert not owned.exists() and unrelated.exists()


def test_preview_archive_rollback_restores_existing_bytes(tmp_path):
    archive = tmp_path / "mods/update/update.rpf"
    backup = tmp_path / "mods/update/update.rpf.allin1-previews.bak"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"damaged"); backup.write_bytes(b"original")
    installer._restore_preview_archive(archive, backup, True)
    assert archive.read_bytes() == b"original"


def test_preview_archive_rollback_removes_new_partial_archive(tmp_path):
    archive = tmp_path / "mods/update/update.rpf"
    archive.parent.mkdir(parents=True); archive.write_bytes(b"partial")
    installer._restore_preview_archive(archive, archive.with_suffix(".bak"), False)
    assert not archive.exists()


def test_refresh_stale_mods_archive_uses_current_base_transactionally(tmp_path):
    base = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    base.parent.mkdir(parents=True); mods.parent.mkdir(parents=True)
    base.write_bytes(b"current-game-archive")
    mods.write_bytes(b"old-mod-archive")
    import os
    os.utime(mods, ns=(1_000_000_000, 1_000_000_000))
    os.utime(base, ns=(5_000_000_000, 5_000_000_000))

    assert installer._refresh_stale_mods_archive(tmp_path, mods) is True
    assert mods.read_bytes() == b"current-game-archive"
    assert not mods.with_name("update.rpf.allin1-refresh.tmp").exists()


def test_refresh_current_mods_archive_leaves_it_untouched(tmp_path):
    base = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    base.parent.mkdir(parents=True); mods.parent.mkdir(parents=True)
    base.write_bytes(b"base"); mods.write_bytes(b"custom-current")
    import os
    os.utime(base, ns=(1_000_000_000, 1_000_000_000))
    os.utime(mods, ns=(5_000_000_000, 5_000_000_000))

    assert installer._refresh_stale_mods_archive(tmp_path, mods) is False
    assert mods.read_bytes() == b"custom-current"


@pytest.mark.parametrize("helper", [
    installer._patch_dlclist_rpf, installer._unpatch_dlclist_rpf,
    installer._remove_preview_ytds,
])
def test_rpf_helpers_handle_success_failure_and_exception(tmp_path, monkeypatch, helper):
    _layout(tmp_path, monkeypatch)
    result = installer.InstallResult(tmp_path)
    for response in (
        Mock(returncode=0, stdout="ok", stderr=""),
        Mock(returncode=2, stdout="", stderr="bad"),
    ):
        monkeypatch.setattr(installer.subprocess, "run", Mock(return_value=response))
        helper(tmp_path, result) if helper is installer._patch_dlclist_rpf else helper(tmp_path)
    monkeypatch.setattr(installer.subprocess, "run", Mock(side_effect=OSError("failed")))
    helper(tmp_path, result) if helper is installer._patch_dlclist_rpf else helper(tmp_path)
