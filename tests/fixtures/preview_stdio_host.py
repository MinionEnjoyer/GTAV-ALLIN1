"""Exercise production stdio dispatch and preview subprocess boundaries, no GTA."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

from allin1 import prelaunch_previews as previews
from allin1.desktop_host import serve


def main():
    work=Path(sys.argv[1]);worker=sys.argv[2];mode=sys.argv[3]
    reading=Event()
    class Incoming:
        calls=0
        def readline(self,limit):
            self.calls+=1
            if self.calls>1:reading.set()
            return sys.stdin.readline(limit)
    class Service:
        def read(self,operation,payload):
            assert operation=='health'
            assert reading.wait(2)
            # Ensure the synchronous stdin read is pending, not merely queued.
            time.sleep(.1)
            project=work/'project';project.mkdir()
            (project/'data').mkdir()
            (project/'data/weapons.toml').write_text('[[weapons]]\nname="WEAPON_PISTOL"\ncategory="pistols"\n')
            cache=work/'cache';cache.mkdir()
            game=work/'game';game.mkdir()
            frozen=mode=='frozen'
            command=[worker] if frozen else [sys.executable,worker]
            if frozen:project=Path(os.environ['ALLIN1_PREVIEW_TEST_RESOURCES'])
            if mode=='inherited-negative-control':
                real=previews.subprocess.Popen
                def inherited(*args,**kwargs):
                    kwargs.pop('stdin',None)
                    return real(*args,**kwargs)
                previews.subprocess.Popen=inherited
                target=work/'negative';target.mkdir()
                try:previews.render(command,{},target,2)
                except TimeoutError:return {'blocked':True}
                raise AssertionError('Negative control did not reproduce the hang')
            categories=[]
            for category in ('weapons','vehicles','gear'):
                result=previews.stock_items(command,project,game,cache,[],lambda *_:None,category=category)
                assert 'items' in result and 'errors' in result
                if not frozen:assert result['category']==category
                categories.append(category)
            target=work/'render';target.mkdir()
            job=json.loads(Path(os.environ['ALLIN1_PREVIEW_TEST_JOB']).read_text()) if frozen else {}
            image=previews.render(command,job,target,40 if frozen else 5)
            return {'categories':categories,'png_bytes':len(image)}
    serve(Service(),Incoming(),sys.stdout)


if __name__=='__main__':main()
