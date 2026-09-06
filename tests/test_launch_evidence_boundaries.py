"""Launch diagnostics and SDK provenance reject malformed evidence safely."""
import os
import subprocess
from types import SimpleNamespace as NS
import pytest
from allin1 import artifact_contract as c, runtime_process_evidence as r
from tests.test_sdk_provenance import traced


@pytest.mark.parametrize('value',[{},[],{'../escape':'a'*64},{1:'a'*64},{'a':'a'*64,'A':'b'*64},
    {'a':'a'*64,'a/b':'a'*64},{'x'*1025:'a'*64},{'ok':'wrong'}])
def test_invalid_artifact_inventory(value):
    with pytest.raises(ValueError):c.inventory(value)


@pytest.mark.parametrize('field,value',[('kind','wrong'),('schema_version',True),('mode','unknown'),('sdk_version',''),('source',None)])
def test_sealed_but_unsupported_build_identity(tmp_path,field,value):
    _,a=traced(tmp_path);b=a['build'];b.pop('build_fingerprint');b[field]=value
    with pytest.raises(ValueError):c.validate_build(c.seal(b,'build_fingerprint'))


@pytest.mark.parametrize('field,value',[('kind','wrong'),('schema_version',True),('edition','unknown'),('validation_reports',{}),('validation_reports',['a'*64]*65)])
def test_sealed_but_unsupported_manifest(tmp_path,field,value):
    _,a=traced(tmp_path);a.pop('artifact_id');a[field]=value
    with pytest.raises(ValueError):c.validate_manifest(c.seal(a,'artifact_id'))


def test_seals_cannot_be_replaced_or_malformed():
    with pytest.raises(ValueError):c.seal({'id':'already'},'id')
    with pytest.raises(ValueError):c.verify_seal([], 'id')
    with pytest.raises(ValueError):c.verify_seal({'id':'a'*64},'id')
    with pytest.raises(ValueError):c.validate_manifest({})


@pytest.mark.parametrize('pid',[0,-1,True,'42',2**32])
def test_observer_rejects_invalid_pid(pid):
    with pytest.raises(ValueError):r.probe(pid)


@pytest.mark.parametrize('stdout,code,status',[
    ('{"status":"absent"}',0,'absent'),('{"status":"observed"}',0,'observed'),
    ('{"status":"unavailable"}',0,'unavailable'),('[]',0,'unavailable'),
    ('{"status":"bad"}',0,'unavailable'),('invalid',0,'unavailable'),
    ('',1,'unavailable'),('x'*(512*1024+1),0,'unavailable')],
    ids=['absent','observed','unavailable','array','bad-status','bad-json','failed-exit','oversized'])
def test_observer_never_invents_process_state(monkeypatch,tmp_path,stdout,code,status):
    # Replace the module's OS facade, not global os.name (Path is platform-aware).
    monkeypatch.setattr(r,'os',NS(name='nt',environ={'SystemRoot':str(tmp_path)}))
    commands=[]
    def run(args,**kwargs):commands.append((args,kwargs));return NS(returncode=code,stdout=stdout)
    monkeypatch.setattr(r,'run_hidden',run)
    assert r.probe(42)['status']==status
    assert '-NonInteractive' in commands[0][0] and 'Get-Process -Id 42' in commands[0][0][-1]
    assert commands[0][1]['timeout']==10


@pytest.mark.parametrize('error',[OSError('no access'),subprocess.TimeoutExpired('probe',10)])
def test_observer_access_failure_is_not_process_exit(monkeypatch,tmp_path,error):
    monkeypatch.setattr(r,'os',NS(name='nt',environ={'SystemRoot':str(tmp_path)}))
    shell=tmp_path/'Sysnative/WindowsPowerShell/v1.0/powershell.exe';shell.parent.mkdir(parents=True);shell.touch()
    def run(args,**kwargs):assert args[0]==str(shell);raise error
    monkeypatch.setattr(r,'run_hidden',run)
    assert r.probe(42)=={'status':'unavailable','reason':type(error).__name__}


def test_nonwindows_observer_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(r,'os',NS(name='posix'))
    assert r.probe(42)['status']=='unavailable'
