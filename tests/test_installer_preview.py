"""End-to-end orchestration tests for preview packaging and helper tools."""

import io
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from allin1 import installer
from allin1.preview_assets import PreviewMergeResult


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
    ("ytd", "YTDToolio.exe missing"),
    ("rpf", "RpfPatcher.exe missing"),
])
def test_preview_deploy_reports_missing_inputs(tmp_path, monkeypatch, missing, warning):
    _project, dist, tools = _layout(tmp_path, monkeypatch)
    if missing == "previews":
        (dist / "previews").rename(dist / "gone")
    elif missing == "ytd":
        (tools / "YTDToolio.exe").unlink()
    else:
        (tools / "RpfPatcher" / "RpfPatcher.exe").unlink()
    result = installer.InstallResult(tmp_path)
    installer._deploy_preview_dlc(tmp_path, result)
    assert any(warning in item for item in result.warnings)


def test_preview_deploy_builds_and_deploys_with_captured_override(tmp_path, monkeypatch):
    _layout(tmp_path, monkeypatch)
    from allin1 import preview_assets
    from allin1.generators import dlc_previews, ytd_builder

    merge = Mock(return_value=PreviewMergeResult(1, ("bad.png",), ()))
    monkeypatch.setattr(preview_assets, "merge_previews", merge)

    def build(_source, _logo, output, _tools, models):
        output.mkdir(parents=True)
        ytd = output / "allin1_prev_01.ytd"
        ytd.write_bytes(b"ytd")
        assert models == ["alpha"]
        return [ytd]
    monkeypatch.setattr(ytd_builder, "build_ytd_files", build)

    create = Mock(return_value=(tmp_path / "dlc-root", tmp_path / "staging"))
    deploy = Mock()
    monkeypatch.setattr(dlc_previews, "create_dlc_pack", create)
    monkeypatch.setattr(dlc_previews, "deploy_dlc_rpf", deploy)

    def run(args, **_kwargs):
        if "build-dlc" in args:
            Path(args[3]).write_bytes(b"rpf")
        return Mock(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=True)

    installer._deploy_preview_dlc(tmp_path, result)

    assert "Ignored 1 invalid preview capture(s)." in result.warnings
    assert merge.call_args.args[0][1] == tmp_path / "scripts" / "previews"
    deploy.assert_called_once()


@pytest.mark.parametrize("stage", ["convert-gen9", "build-dlc"])
def test_preview_deploy_surfaces_tool_failures(tmp_path, monkeypatch, stage):
    _layout(tmp_path, monkeypatch)
    from allin1 import preview_assets
    from allin1.generators import dlc_previews, ytd_builder
    monkeypatch.setattr(preview_assets, "merge_previews",
                        Mock(return_value=PreviewMergeResult(1, (), ())))
    monkeypatch.setattr(ytd_builder, "build_ytd_files",
                        lambda _a, _b, output, _d, _e: [output / "one.ytd"])
    monkeypatch.setattr(dlc_previews, "create_dlc_pack",
                        Mock(return_value=(tmp_path / "root", tmp_path / "staging")))
    monkeypatch.setattr(installer.subprocess, "run",
                        lambda args, **_kwargs: Mock(returncode=1 if stage in args else 0,
                                                     stdout="", stderr="boom"))
    result = installer.InstallResult(tmp_path, is_enhanced=(stage == "convert-gen9"))
    with pytest.raises(RuntimeError, match=stage):
        installer._deploy_preview_dlc(tmp_path, result)


def test_openrpf_download_success_and_failure(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("release/OpenRPF.asi", b"asi")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = archive.getvalue()
    monkeypatch.setattr(installer, "urlopen", lambda *_a, **_k: response)
    assert installer._check_openrpf(tmp_path, enhanced=True) is True
    (tmp_path / "OpenRPF.asi").unlink()
    monkeypatch.setattr(installer, "urlopen", Mock(side_effect=OSError("offline")))
    assert installer._check_openrpf(tmp_path, enhanced=True) is False


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
