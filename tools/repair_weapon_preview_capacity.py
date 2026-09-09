"""Local test deployment for the combined weapon-preview queue limit repair."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

from allin1.runtime_resources import verify_resources

ROOT = Path(__file__).resolve().parents[1]
APP = Path('C:/Users/nivea/Applications/ALLIN1 Launcher')
GAME = Path('D:/Programs/Steam/steamapps/common/Grand Theft Auto V Enhanced')
OUT = ROOT / 'build/weapon-preview-capacity-20260908-v1'
MODULE = 'runtime/lib/allin1/prelaunch_previews.py'
EMBEDDED = 'runtime/lib/allin1/_desktop_build.json'
MANIFEST = 'runtime/runtime-manifest.json'
BASELINE = '917ac95795c1baf4793c4850efb1d99b352bf4a03f94c0d8ed1eed5b5c01a539'


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path): return json.loads(path.read_text(encoding='utf-8'))
def encode(data): return json.dumps(data, sort_keys=True, indent=2).encode()
def save(path, data): path.write_bytes(encode(data))


def deploy():
    status = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        '@(Get-Process allin1-launcher-desktop,blender -ErrorAction SilentlyContinue).Count'],
        capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    # Deployment writes only launcher files. Game previews are backed up read-only;
    # the separate reviewed generation operation still requires GTA to be closed.
    if status.stdout.strip() != '0': raise ValueError('Close the launcher and preview workers first')
    if sha(APP / MODULE) != BASELINE: raise ValueError('Installed module differs from inspected baseline')
    identity, embedded = load(APP/'build-identity.json'), load(APP/EMBEDDED)
    verify_resources(APP/'resources', identity)
    checksums, runtime = load(APP/'checksums.json'), load(APP/MANIFEST)
    files = [MODULE, EMBEDDED, MANIFEST, 'build-identity.json', 'checksums.json']
    for name in files[:-1]:
        if checksums[name] != sha(APP/name): raise ValueError('Installed file changed: '+name)
    for name in [MODULE, EMBEDDED]:
        if runtime['files'][name.removeprefix('runtime/')] != sha(APP/name): raise ValueError('Runtime mismatch: '+name)
    incoming = (ROOT/'src/allin1/prelaunch_previews.py').read_bytes()
    patch = {'installed_at': datetime.now(timezone.utc).isoformat(), 'kind': 'combined-weapon-preview-capacity',
        'old_module_sha256': BASELINE, 'new_module_sha256': hashlib.sha256(incoming).hexdigest(),
        'managed_limit': 128, 'combined_catalog_limit': 2048, 'published': False}
    for doc in [identity, embedded]:
        doc['source_dirty'] = True
        doc['local_preview_patch'] = patch
    outputs = {MODULE: incoming, EMBEDDED: encode(embedded), 'build-identity.json': encode(identity)}
    for name in [MODULE, EMBEDDED]:
        runtime['files'][name.removeprefix('runtime/')] = hashlib.sha256(outputs[name]).hexdigest()
    outputs[MANIFEST] = encode(runtime)
    for name, data in outputs.items(): checksums[name] = hashlib.sha256(data).hexdigest()
    outputs['checksums.json'] = encode(checksums)
    OUT.mkdir(exist_ok=False)
    originals = {}
    for name in outputs:
        dest = OUT/'launcher-backup'/name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP/name, dest); originals[name] = sha(dest)
    public = GAME/'plugins/ReactorV/ui/assets/allin1'
    inventory = {}
    for category in ['weapons', 'vehicles', 'gear']:
        folder = public/('generated-'+category)
        inventory[category] = {p.name: sha(p) for p in folder.iterdir() if p.is_file()}
        if category == 'weapons': shutil.copytree(folder, OUT/'weapon-preview-backup')
    save(OUT/'before.json', {'launcher': originals, 'generated_previews': inventory})
    applied = []
    try:
        for name, data in outputs.items():
            if sha(APP/name) != originals[name]: raise ValueError('Launcher changed during repair')
            target = APP/name; temp = target.with_name(target.name+'.preview-fix.tmp')
            if temp.exists(): raise FileExistsError(temp)
            temp.write_bytes(data); temp.replace(target); applied.append(name)
        verify_resources(APP/'resources', load(APP/'build-identity.json'))
        for name, data in outputs.items():
            if sha(APP/name) != hashlib.sha256(data).hexdigest(): raise ValueError('Deployed file mismatch')
    except Exception:
        for name in reversed(applied): shutil.copy2(OUT/'launcher-backup'/name, APP/name)
        raise
    save(OUT/'installation.json', patch)
    save(OUT/'request.json', {'action': 'prepare_previews', 'missing_previews_only': True,
        'skip_preview_categories': ['vehicles', 'gear']})
    print('Installed preview-capacity fix; existing previews and launcher backed up.', flush=True)


if __name__ == '__main__': deploy()
