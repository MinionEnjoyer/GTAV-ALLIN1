"""Shared-runtime boundary tests; no game, downloads, or installed state."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

import pytest
from allin1 import runtime_resources as resources
from tools import launcher_shared_runtime_candidate as build
from tools import launcher_desktop_candidate as candidate
from tools import shared_runtime_bootstrap as bootstrap


def test_standard_candidate_build_uses_shared_runtime(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(build, 'build', lambda *args, **kwargs: calls.append((args, kwargs)) or 'report')
    assert candidate.build(tmp_path, service_only=True, pnpm='manager', cargo='compiler') == 'report'
    assert calls == [((tmp_path, tmp_path.parent/'ALLIN1-SDK'),
                     {'service_only':True, 'pnpm':'manager', 'cargo':'compiler'})]


@pytest.mark.parametrize('obsolete', [None, 'sidecar/old.exe', 'resources/tools/WeaponPreview/WeaponPreview.exe'])
def test_shared_portable_exact_inventory_and_no_obsolete_helpers(tmp_path, obsolete):
    from allin1.updater import _archive_payloads
    app = tmp_path/'app'
    names = ['allin1-launcher-desktop.exe', 'runtime/python.exe', 'runtime/bootstrap.py',
             'runtime/runtime-manifest.json', 'resources/README.md']
    for name in names + ([obsolete] if obsolete else []):
        path = app/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic fixture')
    identity = {'version':'0.6.5', 'build_id':'test', 'runtime':{'kind':'shared-python'}}
    output = tmp_path/'portable.zip'
    if obsolete:
        with pytest.raises(ValueError, match='obsolete frozen helper'):
            candidate.write_portable(app, output, identity)
        assert not output.exists()
    else:
        candidate.write_portable(app, output, identity)
        with zipfile.ZipFile(output) as archive:
            assert set(_archive_payloads(archive)) == {*names, 'build-identity.json', 'release.json'}


def test_shared_service_command_and_resource_location(tmp_path, monkeypatch):
    app = tmp_path/'app with spaces'
    monkeypatch.setattr(sys, '_allin1_packaged_root', str(app), raising=False)
    assert resources.resource_root() == app/'resources'
    exe = app/'runtime/python.exe'
    assert candidate.service_command(exe) == [str(exe), '-I', '-B', str(exe.parent/'bootstrap.py'), 'service']
    assert candidate.service_command(app/'sidecar/old.exe') == [str(app/'sidecar/old.exe')]


@pytest.mark.parametrize('change', ['none','changed','missing','extra','schema','isolation'])
def test_bootstrap_integrity(tmp_path, monkeypatch, change):
    payload = tmp_path/'payload.py'
    payload.write_bytes(b'original')
    manifest = {'schema_version':1,'files':{'payload.py':hashlib.sha256(b'original').hexdigest()}}
    if change == 'changed': payload.write_bytes(b'corrupt')
    if change == 'missing': payload.unlink()
    if change == 'extra': (tmp_path/'stale.py').touch()
    if change == 'schema': manifest['schema_version'] = True
    (tmp_path/'runtime-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    monkeypatch.setattr(bootstrap, 'sys', SimpleNamespace(flags=SimpleNamespace(isolated=change!='isolation'),dont_write_bytecode=True))
    if change == 'none': bootstrap.verify(tmp_path)
    else:
        with pytest.raises(ValueError): bootstrap.verify(tmp_path)


def test_bootstrap_supports_python_310_hashing_and_junction_detection(tmp_path, monkeypatch):
    payload = tmp_path / "payload.py"
    content = b"original" * 300_000
    payload.write_bytes(content)
    manifest = {'schema_version':1, 'files':{'payload.py':hashlib.sha256(content).hexdigest()}}
    (tmp_path/'runtime-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    monkeypatch.setattr(bootstrap, 'sys', SimpleNamespace(flags=SimpleNamespace(isolated=True), dont_write_bytecode=True))

    bootstrap.verify(tmp_path)

    class LegacyPath:
        def is_symlink(self):
            return False

        def lstat(self):
            return SimpleNamespace(st_file_attributes=0x400)

    assert bootstrap._is_link_or_junction(LegacyPath())


@pytest.mark.parametrize('name', ['../outside', 'C:/outside', 'x/../../outside', 'x\\outside'])
def test_upstream_archive_rejects_unsafe_member_before_extract(tmp_path, name):
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('safe.py',b'safe')
        z.writestr(name,b'bad')
    if '\\' in name:
        # Windows ZipFile normalizes separators when writing; patch both ZIP
        # headers to represent an actual hostile upstream member instead.
        archive.write_bytes(archive.read_bytes().replace(name.replace('\\','/').encode(),name.encode()))
    with pytest.raises(ValueError): build.extract(archive,tmp_path/'destination')
    assert not (tmp_path/'destination').exists()


def test_sdk_closure_retains_lazy_dependencies_only(tmp_path):
    for name, text in {'__init__':'', 'native_assets':'def lazy():\n from allin1_sdk import helper',
        'compiled_render':'from allin1_sdk.native_assets import X', 'rpf_tools':'',
        'helper':'from .nested import value', 'nested':'', 'gui':'import tkinter'}.items():
        (tmp_path/(name+'.py')).write_text(text,encoding='utf-8')
    assert build.sdk_modules(tmp_path) == ['__init__','compiled_render','helper','native_assets','nested','rpf_tools']


def test_shared_resources_do_not_include_legacy_preview_executable(tmp_path, monkeypatch):
    from allin1 import release
    included = [
        tmp_path / "tools/RpfPatcher/RpfPatcher.exe",
        tmp_path / "tools/WeaponPreview/WeaponPreview.exe",
        tmp_path / "README.md",
    ]
    for path in included:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    monkeypatch.setattr(release, "collect_public_files", lambda *_args, **_kwargs: included)
    result = candidate.resource_inputs(tmp_path, shared_runtime=True)
    assert 'tools/RpfPatcher/RpfPatcher.exe' in result
    assert not any('WeaponPreview' in name for name in result)


def test_shared_runtime_excludes_pillow_tk_helpers_but_keeps_image_apis(tmp_path):
    wheel = tmp_path / "pillow-fixture.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in (
            "PIL/Image.py", "PIL/ImageDraw.py", "PIL/ImageTk.py",
            "PIL/_imagingtk.cp313-win_amd64.pyd", "PIL/_imagingtk.pyi",
            "PIL/_tkinter_finder.py",
        ):
            archive.writestr(name, b"fixture")
    runtime = tmp_path / "runtime"
    build.extract(wheel, runtime, skip=build.PILLOW_TK_HELPERS)
    assert (runtime / "PIL/Image.py").is_file()
    assert (runtime / "PIL/ImageDraw.py").is_file()
    assert not any((runtime / name).exists() for name in build.PILLOW_TK_HELPERS)


def test_shared_preview_command_does_not_import_sdk_or_numpy(tmp_path, monkeypatch):
    from allin1 import prelaunch_previews as p
    from allin1.preview_policy import STUDIO_BACKDROP, VEHICLE_TEXTURES, THROWABLE_TEXTURES
    app = tmp_path/'app'
    project = app/'resources'
    for name in [STUDIO_BACKDROP, *VEHICLE_TEXTURES, *THROWABLE_TEXTURES, 'tools/RpfPatcher/helper.dll']:
        path = project/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'fixture')
    runtime = app/'runtime'; runtime.mkdir()
    (runtime/'runtime-manifest.json').write_bytes(b'manifest')
    monkeypatch.setattr(sys,'_allin1_packaged_root',str(app),raising=False)
    command, identity = p.worker_command(project)
    assert command == [str(runtime/'python.exe'),'-I','-B',str(runtime/'bootstrap.py'),'preview']
    assert identity.startswith(p.sha(runtime/'runtime-manifest.json'))
