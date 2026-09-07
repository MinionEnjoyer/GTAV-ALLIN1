"""Replay explicitly selected preview jobs into a NEW diagnostic folder only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'src')]
from allin1.preview_blender import select_blender
from allin1.prelaunch_previews import sha
from allin1.stock_weapon_previews import file_state
from tools.react_release_harness import write_new


def run(app, jobs):
    from PIL import Image, ImageStat
    output = ROOT/'build/shared-runtime-preview-tests'/uuid.uuid4().hex
    output.mkdir(parents=True)
    blender = select_blender(ROOT)
    results = []
    for index, source in enumerate(jobs):
        job = json.loads(source.read_text(encoding='utf-8'))
        job.update(project=str(app/'resources'),blender_executable=str(blender))
        game = Path(job['game'])
        # Old fixture source stamps are refreshed from read-only current inputs;
        # the worker still checks them again after rendering.
        if job.get('archive'): job['archive_sha256'] = sha(game/job['archive'])
        for asset in job.get('assets',[]): asset['state'] = file_state(game/asset['archive'])
        work = output/str(index); work.mkdir()
        write_new(work/'job.json',job)
        command = [str(app/'runtime/python.exe'),'-I','-B',str(app/'runtime/bootstrap.py'),'preview',str(work/'job.json')]
        with (work/'worker.log').open('xb') as log:
            result = subprocess.run(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,timeout=600,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode: raise RuntimeError(str(work/'worker.log'))
        with Image.open(work/'preview.png') as image:
            image.load()
            assert image.size == (512,320)
            assert max(ImageStat.Stat(image.convert('RGB')).stddev) > 8
        results.append({'model':job['weapon'],'image':str(work/'preview.png'),'sha256':sha(work/'preview.png')})
        print('PASS '+job['weapon'],flush=True)
    write_new(output/'report.json',{'status':'PASS','app':str(app),'renders':results,'game_started':False})
    return output/'report.json'


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app',type=Path)
    parser.add_argument('jobs',nargs='+',type=Path)
    args=parser.parse_args()
    print(run(args.app,args.jobs))
