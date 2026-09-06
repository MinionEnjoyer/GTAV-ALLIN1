"""Local Launcher session anchors for SDK lineage, processes and module paths.

This records observations, not crash diagnoses. A process disappearing is not
called a crash, and an observed module path plus file hash is not a memory hash.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import sys
import uuid

from allin1.artifact_contract import digest, validate_manifest
from allin1.release_paths import contained, no_links, strict_json
from allin1.sdk_provenance import file_hash
from allin1.runtime_process_evidence import probe
from allin1.runtime_crash_evidence import collect as collect_crash


def now():
    return datetime.now(timezone.utc).isoformat()


def installed_snapshot(game):
    """Verify bounded current loose-file evidence without loading any mods."""
    game = no_links(Path(game))
    receipts = contained(game,"scripts/.allin1/mods")
    result, budget = [], 2*1024**3
    if not receipts.is_dir():
        return result
    files = sorted(receipts.glob("*.json"))
    if len(files)>128:
        raise ValueError("Runtime diagnostic receipts exceed 128 packages")
    total_files = 0
    for file in files:
        try:
            no_links(file)
            if file.stat().st_size>4*1024**2:
                raise ValueError("Receipt exceeds 4 MiB")
            data = file.read_bytes(); receipt = strict_json(data)
            lineage = receipt.get("sdk_provenance")
            if lineage is None:
                continue
            artifact = validate_manifest(lineage["artifact"])
            if lineage["artifact_id"]!=artifact["artifact_id"] or lineage["build_fingerprint"]!=artifact["build"]["build_fingerprint"]:
                raise ValueError("Installation lineage identities disagree")
            if type(receipt.get("enabled")) is not bool:
                raise ValueError("Unknown package enable state")
            rows=[]
            for item in lineage["files"]:
                total_files += 1
                if total_files>512:
                    raise ValueError("Runtime diagnostic file count exceeds 512")
                expected = artifact["outputs"][item["source"]]
                if expected!=item["sha256"] or not any(record.get("destination")==item["destination"] and record.get("sha256")==expected for record in receipt["files"]):
                    raise ValueError("Receipt file mapping disagrees with its artifact")
                name = item["destination"] + ("" if receipt["enabled"] else ".disabled")
                target = contained(game,name)
                row={"destination":name,"expected_sha256":expected,"status":"missing"}
                if target.is_file():
                    size=target.stat().st_size
                    if size>budget:
                        row["status"]="not_checked";row["reason"]="Hash budget exceeded"
                    else:
                        budget-=size
                        row["actual_sha256"]=file_hash(target)
                        row["status"]="match" if row["actual_sha256"]==expected else "mismatch"
                rows.append(row)
            result.append({"package_id":receipt["id"],"enabled":receipt["enabled"],"receipt_sha256":hashlib.sha256(data).hexdigest(),
                "artifact_id":artifact["artifact_id"],"build_fingerprint":lineage["build_fingerprint"],"files":rows,
                "rpf_members_status":"not_checked" if lineage.get("rpf_members") else "not_applicable",
                "rpf_member_count":len(lineage.get("rpf_members",[]))})
        except (OSError,ValueError,KeyError,TypeError) as exc:
            result.append({"receipt":file.name,"status":"unavailable","reason":str(exc)[:300]})
    return result


class RuntimeSession:
    def __init__(self, game, state, *, process_probe=probe, crash_probe=collect_crash):
        self.game=no_links(Path(game)).resolve(strict=True)
        directory=contained(no_links(Path(state)),"runtime-traces")
        directory.mkdir(parents=True,exist_ok=True)
        self.path=contained(directory,uuid.uuid4().hex+".json")
        self.probe=process_probe
        self.crash_probe=crash_probe
        self.crash_capture_started=False
        self.lock=threading.RLock()
        self.process=None
        self.modules=set()
        self.stop=threading.Event()
        self.thread=None
        if getattr(sys,"frozen",False):
            from allin1.runtime_resources import frozen_identity,resource_root
            # Frozen Python modules live in the sidecar's archive, not readable
            # sibling .py files. Bind its real bytes and verified build instead.
            observer_build={"mode":"frozen_verified_resources","identity":frozen_identity(resource_root())}
            observer_components={"sidecar_executable":file_hash(no_links(Path(sys.executable)))}
        else:
            observer_build={"mode":"source_components","scope":"Selected observer implementation files, not a signed full Launcher release."}
            observer_components={name:file_hash(Path(__file__).with_name(name)) for name in ("runtime_diagnostic_session.py","runtime_process_evidence.py","runtime_crash_evidence.py","sdk_provenance.py","artifact_contract.py")}
        self.value={"schema_version":1,"kind":"launcher_runtime_session","session_id":self.path.stem,
            "created_at":now(),"game_path":str(self.game),"installed":installed_snapshot(self.game),"events":[],
            "observer_sha256":digest({"components":observer_components,"build":observer_build}),"observer_components":observer_components,"observer_build":observer_build,"status":"launch_requested",
            "scope":"Local observation record, not a signature. Module paths come from the OS native module list, not managed-assembly or asset-use telemetry. Module hashes describe on-disk files at observation, not mapped memory. Missing process or module evidence is not proof of a crash or successful asset use."}
        with self.path.open("x",encoding="utf-8") as stream:
            json.dump(self.value,stream)
        self.event("session_start",{})

    def event(self, kind, data):
        with self.lock:
            events=self.value["events"]
            if len(events)>=64:
                self.stop.set();self.value["status"]="event_limit"
            else:
                event={"sequence":len(events),"timestamp":now(),"type":kind,"data":data,
                    "previous_sha256":events[-1]["event_sha256"] if events else None}
                event["event_sha256"]=digest(event)
                events.append(event)
            self.value["record_sha256"]=digest({key:value for key,value in self.value.items() if key!="record_sha256"})
            temporary=contained(self.path.parent,self.path.name+".tmp")
            created=False
            try:
                with temporary.open("x",encoding="utf-8") as stream:
                    created=True
                    json.dump(self.value,stream,allow_nan=False)
                    stream.flush();os.fsync(stream.fileno())
                no_links(self.path)
                temporary.replace(self.path)
            finally:
                if created:
                    temporary.unlink(missing_ok=True)

    def observe(self, pid):
        observation=self.probe(pid)
        if observation.get("status")!="observed":
            self.event("process_observation",observation)
            if observation.get("status")=="absent" and self.process:
                self.value["status"]="process_disappeared"
                self.event("session_end",{"reason":"Process no longer observed; exit/crash cause not established"})
                self.stop.set()
            return False
        executable=no_links(Path(observation["executable_path"]))
        expected={self.game/"GTA5.exe",self.game/"GTA5_Enhanced.exe"}
        token={"pid":observation["pid"],"started_at":observation["started_at"],"executable_path":str(executable)}
        if executable not in expected:
            self.event("wrong_installation_process",token)
            return False
        if self.process and token!=self.process:
            self.value["status"]="process_identity_changed"
            self.event("session_end",{"reason":"PID/executable/creation identity changed"})
            self.stop.set();return False
        if not self.process:
            self.process=token
            self.value["status"]="process_observed"
            self.event("process_identity",{**token,"executable_sha256":file_hash(executable)})
        rows=[]
        module_limit=False
        for value in observation.get("modules",[]):
            if value in self.modules:
                continue
            if len(self.modules)>=512:
                module_limit=True
                break
            self.modules.add(value)
            file=Path(value)
            # Hash only game-local modules. System/driver modules stay observed
            # paths, not an invitation to read arbitrary outside package files.
            row={"path":value,"hash_status":"outside_game_scope"}
            try:
                file=no_links(file)
                if file.is_relative_to(self.game):
                    if file.stat().st_size>128*1024**2:
                        row["hash_status"]="size_limit"
                    else:
                        row["file_sha256"]=file_hash(file);row["hash_status"]="on_disk_at_observation"
            except (OSError,ValueError):
                row["hash_status"]="unavailable"
            rows.append(row)
        if rows or observation.get("modules_status")!="observed" or observation.get("modules_truncated") or module_limit:
            self.event("module_paths",{"modules":rows,"status":observation.get("modules_status"),"truncated":bool(observation.get("modules_truncated")) or module_limit})
        return True

    def capture_crash(self, *, retry_wait=None):
        if not self.process or self.crash_capture_started: return
        self.crash_capture_started=True
        wait=retry_wait or threading.Event().wait
        for attempt in range(3):
            if attempt: wait(10)
            if len(self.value["events"])>=64: return
            try:
                observation=self.crash_probe(dict(self.process))
            except (OSError,ValueError,KeyError,TypeError):
                observation={"status":"unavailable","reason":"Crash observer failed","events":[]}
            self.event("crash_observation",{"attempt":attempt+1,**observation})
            if observation.get("events"): return

    def watch(self,pid):
        if self.thread is not None:
            return
        def worker():
            failures=0
            while not self.stop.wait(10):
                try:
                    observed=self.observe(pid)
                    failures=0 if observed else failures+1
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    failures+=1;self.event("observer_error",{"reason":str(exc)[:300]})
                if failures>=3 and not self.stop.is_set():
                    self.value["status"]="observer_unavailable"
                    self.event("session_end",{"reason":"Three unavailable observations; process exit is not established"})
                    self.stop.set()
            if self.value["status"] in {"process_disappeared","launch_failed","process_identity_changed"}:
                self.capture_crash()
        self.thread=threading.Thread(target=worker,name="allin1-runtime-evidence",daemon=True)
        self.thread.start()
