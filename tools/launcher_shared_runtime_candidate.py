"""Build a source-bound shared-Python Launcher candidate in a fresh directory.

Official CPython embed ZIP and PyPI wheels are pinned by upstream SHA256.
No pip, PyInstaller bootloaders, Tk, or full SDK application is shipped.
Never installs or publishes; release approval remains a separate operation.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from allin1 import __version__
from allin1.release_paths import contained, tree_files, unique_paths
from allin1.runtime_resources import sha256
from tools import launcher_desktop_candidate as candidate
from tools.react_release_harness import source_identity, write_new


def fetch(record, cache):
    target = contained(cache, record["filename"])
    if not target.exists():
        with urllib.request.urlopen(record["url"], timeout=120) as incoming, target.open("xb") as output:
            shutil.copyfileobj(incoming, output)
    if sha256(target) != record["sha256"]:
        raise ValueError("Upstream download checksum mismatch: " + target.name)
    return target


def extract(archive, destination, *, skip=()):
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        unique_paths([item.orig_filename for item in infos if not item.is_dir()])
        if sum(item.file_size for item in infos) > 512*1024*1024:
            raise ValueError("Runtime archive exceeds size budget")
        for item in infos:
            contained(destination, item.orig_filename.rstrip('/'))
            if item.flag_bits & 1 or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("Unsupported runtime archive member")
        for item in infos:
            if item.is_dir() or item.filename in skip:
                continue
            path = contained(destination, item.filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(item) as incoming, path.open("xb") as output:
                shutil.copyfileobj(incoming, output)


def sdk_modules(source):
    """Static transitive closure of the renderer's SDK imports, including lazy ones."""
    pending = ["native_assets", "compiled_render", "rpf_tools"]
    selected = {"__init__"}
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        path = source / (name.replace('.', '/') + '.py')
        if not path.is_file():
            raise ValueError("Missing SDK renderer module: " + name)
        selected.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = node.module or ''
                if node.level:
                    prefix = 'allin1_sdk.' + prefix
                names = [prefix, *(prefix + '.' + alias.name for alias in node.names)]
            for imported in names:
                if imported.startswith('allin1_sdk.'):
                    child = imported.removeprefix('allin1_sdk.')
                    if (source / (child.replace('.', '/') + '.py')).is_file():
                        pending.append(child)
    return sorted(selected)


def stage_runtime(root, sdk, runtime, cache):
    lock = json.loads((root / 'tools/shared-runtime-lock.json').read_text(encoding='utf-8'))
    runtime.mkdir(parents=True)
    # Only the path configuration changes; all upstream executables stay intact.
    extract(fetch(lock['python'], cache), runtime, skip=('python313._pth',))
    (runtime / 'python313._pth').write_text('python313.zip\n.\nlib\n', encoding='utf-8')
    library = runtime / 'lib'
    for wheel in lock['wheels']:
        extract(fetch(wheel, cache), library,
                skip=('PIL/ImageTk.py', 'PIL/_imagingtk.cp313-win_amd64.pyd'))
    modules = sdk_modules(sdk / 'src/allin1_sdk')
    for package, source, names in (
        ('allin1', root/'src/allin1', [path.relative_to(root/'src/allin1').with_suffix('').as_posix().replace('/','.')
            for path in (root/'src/allin1').rglob('*.py') if '__pycache__' not in path.parts
            and 'allin1.'+path.stem not in candidate.LEGACY_MODULES]),
        ('allin1_sdk', sdk/'src/allin1_sdk', modules),
    ):
        for name in names:
            relative = name.replace('.', '/') + '.py'
            target = library / package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
    shutil.copytree(root/'src/allin1/assets', library/'allin1/assets')
    shutil.copy2(root/'tools/shared_runtime_bootstrap.py', runtime/'bootstrap.py')
    licenses = runtime/'licenses'
    licenses.mkdir()
    shutil.copy2(root/'LICENSE', licenses/'ALLIN1-LICENSE')
    shutil.copy2(sdk/'LICENSE', licenses/'SDK-LICENSE')
    candidate.assert_no_tk(tree_files(runtime))
    with zipfile.ZipFile(runtime/'python313.zip') as stdlib:
        candidate.assert_no_tk(stdlib.namelist())
    return {'kind':'shared-python', 'python':lock['python'], 'wheels':lock['wheels'],
            'sdk_modules':modules, 'sdk_commit':source_identity(sdk)['commit']}


def build(root, sdk, *, service_only=False, pnpm='pnpm', cargo='cargo'):
    from allin1.release import validate_version_consistency
    from allin1.reactor_bridge_contract import validate_reactor_bridge_pair
    validate_version_consistency(root)
    validate_reactor_bridge_pair(root/'script/dist', expected_version=__version__)
    for name, version in (
        ('desktop/package.json', json.loads((root/'desktop/package.json').read_text())['version']),
        ('desktop/src-tauri/tauri.conf.json', json.loads((root/'desktop/src-tauri/tauri.conf.json').read_text())['version']),
        ('desktop/src-tauri/Cargo.toml', candidate.tomllib.loads((root/'desktop/src-tauri/Cargo.toml').read_text())['package']['version']),
    ):
        if version != __version__:
            raise ValueError('Stale desktop version: ' + name)
    before, sdk_before = source_identity(root), source_identity(sdk)
    folder = root/'build/launcher-candidates'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    cache = root/'build/shared-runtime-downloads'
    cache.mkdir(exist_ok=True)
    app = folder/'app'
    inputs = candidate.resource_inputs(root, shared_runtime=True)
    resources = app/'resources'
    hashes = candidate.stage_resources(inputs, resources)
    runtime = app/'runtime'
    runtime_info = stage_runtime(root, sdk, runtime, cache)
    identity = {'schema_version':1, 'kind':'launcher_desktop_build', 'version':__version__,
        'build_id':folder.name, 'commit':before['commit'], 'source_sha256':before['sha256'],
        'source_dirty':before['dirty'], 'created_at':datetime.now(timezone.utc).isoformat(),
        'resources':hashes, 'resources_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        'runtime':runtime_info, 'release_ready':False}
    write_new(folder/'source.json', before)
    write_new(folder/'sdk-source.json', sdk_before)
    write_new(runtime/'lib/allin1/_desktop_build.json', identity)
    write_new(runtime/'runtime-manifest.json', {'schema_version':1,
        'files':{name:sha256(path) for name,path in tree_files(runtime).items()}})
    # Same relocation, lifecycle, protocol, persistence and corruption checks as frozen builds.
    write_new(folder/'smoke.json', candidate.smoke(runtime/'python.exe', resources, identity))
    portable = None
    if not service_only:
        manager, compiler = shutil.which(pnpm), shutil.which(cargo)
        if not manager or not compiler:
            raise FileNotFoundError('Native candidate requires pnpm and cargo')
        command = [manager]
        if os.name == 'nt' and Path(manager).suffix.lower() in ('.cmd','.bat'):
            command = [os.environ['COMSPEC'],'/d','/c',manager]
        candidate.run_logged([*command,'build'], root/'desktop', folder/'frontend.log')
        env = dict(os.environ, ALLIN1_LAUNCHER_BUILD_ID=folder.name, ALLIN1_LAUNCHER_RUNTIME='shared-python')
        candidate.run_logged([compiler,'build','--release','--locked','--features','tauri/custom-protocol',
            '--manifest-path',str(root/'desktop/src-tauri/Cargo.toml')], root, folder/'native.log',env=env)
        shell = root/'desktop/src-tauri/target/release/allin1-launcher-desktop.exe'
        shutil.copy2(shell,app/shell.name)
        candidate.run_logged([str(app/shell.name),'--verify-embedded-frontend'],app,folder/'frontend-probe.json')
        probe = json.loads((folder/'frontend-probe.json').read_text(encoding='utf-8'))
        candidate.validate_frontend_probe(probe,identity,root/'desktop/dist')
        if probe.get('service_runtime') != 'shared-python':
            raise ValueError('Native shell was not compiled for the shared runtime')
        portable = candidate.write_portable(app,folder/f'ALLIN1-Launcher-{__version__}-portable.zip',identity)
        (folder / (portable['file'] + '.sha256')).write_text(
            f"{portable['sha256']}  {portable['file']}\n", encoding='utf-8')
    if before != source_identity(root) or sdk_before != source_identity(sdk):
        raise ValueError('Source changed while building candidate')
    write_new(folder/'report.json', {'schema_version':1,
        'kind':'launcher_service_candidate' if service_only else 'launcher_desktop_candidate','version':__version__,
        'build_id':folder.name,'service_smoke':'PASS','native_build':'NOT TESTED' if service_only else 'PASS',
        'source_commit':before['commit'],'source_sha256':before['sha256'],'source_dirty':before['dirty'],
        'sdk_source_sha256':sdk_before['sha256'],'sdk_source_dirty':sdk_before['dirty'],
        'no_tk_runtime':'PASS','resource_integrity':'PASS','smoke_sha256':sha256(folder/'smoke.json'),
        'embedded_frontend':'NOT TESTED' if service_only else 'PASS',
        'native_shell_acceptance':'NOT TESTED','installer_lifecycle':'NOT TESTED','live_acceptance':'NOT TESTED',
        'runtime':runtime_info,'files':{name:sha256(path) for name,path in tree_files(app).items()},
        'portable':portable,'release_ready':False,'published':False})
    return folder/'report.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,default=ROOT.parent/'ALLIN1-SDK')
    parser.add_argument('--service-only',action='store_true')
    parser.add_argument('--pnpm',default='pnpm')
    parser.add_argument('--cargo',default='cargo')
    args = parser.parse_args()
    print(build(ROOT,args.sdk,service_only=args.service_only,pnpm=args.pnpm,cargo=args.cargo))
