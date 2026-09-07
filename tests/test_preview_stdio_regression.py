"""Keep launcher IPC alive while discovery/rendering start real subprocesses."""
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread

import pytest


@pytest.mark.parametrize('mode',['isolated','inherited-negative-control','frozen'])
def test_preview_workers_do_not_inherit_active_launcher_input(tmp_path,mode):
    if mode=='inherited-negative-control' and os.name!='nt':
        pytest.skip('Windows synchronous inherited-pipe startup regression')
    if mode=='frozen' and not all(os.environ.get(k) for k in (
        'ALLIN1_PREVIEW_TEST_WORKER','ALLIN1_PREVIEW_TEST_RESOURCES','ALLIN1_PREVIEW_TEST_JOB')):
        pytest.skip('Opt-in packaged worker and read-only real-asset render job')
    root=Path(__file__).resolve().parents[1]
    environment=dict(os.environ,PYTHONPATH=str(root/'src'))
    fixture=root/'tests/fixtures'
    with (tmp_path/'host.log').open('w') as log:
        host=subprocess.Popen([sys.executable,str(fixture/'preview_stdio_host.py'),str(tmp_path),
            os.environ['ALLIN1_PREVIEW_TEST_WORKER'] if mode=='frozen' else str(fixture/'preview_stdio_worker.py'),mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=log,text=True,encoding='utf-8',env=environment)
        responses=Queue()
        def collect():
            for line in host.stdout:responses.put(json.loads(line))
        reader=Thread(target=collect,daemon=True);reader.start()
        def send(identity,operation):
            host.stdin.write(json.dumps(dict(schema_version=1,request_id=identity,operation=operation,payload={}))+'\n')
            host.stdin.flush()
        try:
            send('probe','health')
            result=responses.get(timeout=60 if mode=='frozen' else 15)
            assert result['kind']=='result',result
            if mode!='inherited-negative-control':
                assert result['payload']['categories']==['weapons','vehicles','gear']
                assert result['payload']['png_bytes']>0
            else:assert result['payload']['blocked']
            # Still-open original IPC is usable after the child processes exit.
            send('stop','shutdown')
            assert responses.get(timeout=5)['payload']=={'closed':True}
            assert host.wait(timeout=5)==0
        finally:
            if host.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(host.pid),'/T','/F'],capture_output=True)
                else:host.kill()
                host.wait(timeout=5)
            host.stdin.close();host.stdout.close();reader.join(timeout=2)
