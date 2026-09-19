import json
import os
import subprocess
from types import SimpleNamespace
import pytest

from allin1 import runtime_crash_evidence as crash
from allin1.runtime_diagnostic_session import RuntimeSession
from tests.test_runtime_diagnostic_session import setup,observation


@pytest.mark.parametrize("suffix", ["Z", "+00:00", "-07:00"])
def test_submicrosecond_timestamp_validation_preserves_original_identity(monkeypatch, suffix):
    original_datetime = crash.datetime
    parsed = []
    def strict_parse(value):
        parsed.append(value)
        assert ".1234567" not in value
        return original_datetime.fromisoformat(value)
    monkeypatch.setattr(crash, "datetime", SimpleNamespace(fromisoformat=strict_parse))
    monkeypatch.setattr(crash, "os", SimpleNamespace(name="nt", environ={}))
    calls = []
    def run(command, **kwargs):
        calls.append(json.loads(kwargs["input"]))
        return SimpleNamespace(returncode=0, stdout='{"status":"no_matching_event","events":[]}')
    monkeypatch.setattr(crash, "run_hidden", run)
    process = {"pid":42, "started_at":"2026-01-01T00:00:00.1234567" + suffix,
               "executable_path":"C:/Game/GTA5.exe"}
    assert crash.collect(process)["status"] == "no_matching_event"
    assert parsed == ["2026-01-01T00:00:00.123456" + suffix.replace("Z", "+00:00")]
    assert calls == [process]


@pytest.mark.skipif(os.name!="nt",reason="Windows PowerShell adapter")
def test_shell_keeps_path_and_identity_as_json_data_and_query_is_bounded(monkeypatch):
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,stdout=json.dumps({"status":"no_matching_event","events":[],"queried_events":0,"query_truncated":False}))
    monkeypatch.setattr(crash,"run_hidden",run)
    process={"pid":42,"started_at":"2026-01-01T00:00:00.1234567Z","executable_path":r"C:\Game'; Write-Output pwned\GTA5.exe"}
    assert crash.collect(process)["status"]=="no_matching_event"
    command,kwargs=calls[0]
    assert process["executable_path"] not in command[-1]
    assert json.loads(kwargs["input"])==process and kwargs["timeout"]==10
    assert "-MaxEvents 33" in command[-1] and "ProcessCreationTime" in command[-1]
    assert "Import-Module" in command[-1] and "Microsoft.PowerShell.Diagnostics.psd1" in command[-1]
    assert "-ComputerName" not in command[-1]


def test_failed_query_is_unavailable_not_normal_exit(monkeypatch):
    def fail(*args,**kwargs): raise subprocess.TimeoutExpired("test",10)
    monkeypatch.setattr(crash,"run_hidden",fail)
    result=crash.collect({"pid":42,"started_at":"2026-01-01T00:00:00Z","executable_path":r"C:\Game\GTA5.exe"})
    assert result["status"]=="unavailable" and not result["events"]


def test_session_retries_delayed_crash_event_without_reclassifying_disappearance(tmp_path):
    game,_=setup(tmp_path)
    responses=iter([{"status":"no_matching_event","events":[]},{"status":"observed","events":["<test-owned-event/>"]}])
    seen=[]
    def collect(process): seen.append(process);return next(responses)
    session=RuntimeSession(game,tmp_path/"state",process_probe=lambda pid:observation(game),crash_probe=collect)
    session.observe(42);session.value["status"]="process_disappeared"
    waits=[];session.capture_crash(retry_wait=waits.append)
    assert waits==[10] and len(seen)==2
    assert session.value["status"]=="process_disappeared"
    captured=[event for event in session.value["events"] if event["type"]=="crash_observation"]
    assert [event["data"]["attempt"] for event in captured]==[1,2]
    session.capture_crash(retry_wait=waits.append)
    assert len(seen)==2


def test_no_event_after_bounded_retries_is_only_missing_evidence(tmp_path):
    game,_=setup(tmp_path)
    session=RuntimeSession(game,tmp_path/"state",process_probe=lambda pid:observation(game),crash_probe=lambda process:{"status":"no_matching_event","events":[]})
    session.observe(42);waits=[];session.capture_crash(retry_wait=waits.append)
    assert waits==[10,10]
    assert len([event for event in session.value["events"] if event["type"]=="crash_observation"])==3


def test_watch_automatically_queries_after_an_observed_process_disappears(tmp_path,monkeypatch):
    from allin1 import runtime_diagnostic_session as runtime
    game,_=setup(tmp_path)
    values=iter([observation(game),{"status":"absent"}])
    session=RuntimeSession(game,tmp_path/"state",process_probe=lambda pid:next(values))
    session.observe(42)
    class Stop:
        stopped=False
        def wait(self,seconds):return self.stopped
        def is_set(self):return self.stopped
        def set(self):self.stopped=True
    session.stop=Stop();captures=[]
    session.capture_crash=lambda:captures.append(session.process)
    monkeypatch.setattr(runtime.threading,"Thread",lambda target,**kwargs:SimpleNamespace(start=target))
    session.watch(42)
    assert len(captures)==1 and captures[0]["pid"]==42
