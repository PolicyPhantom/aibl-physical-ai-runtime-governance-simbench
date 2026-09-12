"""Development session/crash workers; never a Formal session entry."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from phase3.identity import canonical_bytes,raw_sha256
from phase4.boundary import WorkspaceAuthorization
from phase4.contracts import SPEC_SHA256
from phase4.session import ControlExpectation,preflight,run_session,inspect_session,dry_plan

_spec=importlib.util.spec_from_file_location("p4_session_bridge_fixtures",Path(__file__).with_name("test_governance_bridge.py"))
helpers=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(helpers)
BASE_HEAD="272c3ad5de7cf2f55d0bb6090d690e2cce59166b"

def control_fixture(tmp_path):
    sources,approved=helpers.p4_materials()
    auth=WorkspaceAuthorization(tmp_path,"DEV-WORKSPACE",(tmp_path.parent/"protected",))
    raws={"manifest":approved.raw,"plan":helpers.p4_plan(approved)}
    raws["procedure"]=canonical_bytes({"schema_id":"P4-PROCEDURE-v1","procedure_id":"DEV-PROCEDURE",
        "frozen_spec_sha256":SPEC_SHA256,"no_retry":True,"claim_boundary":"SIMULATION_LIMITED"},exclude_volatile=False)
    raws["workspace"]=canonical_bytes({"schema_id":"P4-WORKSPACE-AUTH-v1",
        "authorization_id":auth.authorization_id,"root":str(auth.root),
        "protected_roots":[str(p) for p in auth.protected_roots],
        "procedure_sha256":raw_sha256(raws["procedure"])},exclude_volatile=False)
    common={"code_head":BASE_HEAD,"plan_sha256":raw_sha256(raws["plan"]),
        "manifest_sha256":raw_sha256(raws["manifest"]),"workspace_sha256":raw_sha256(raws["workspace"]),
        "procedure_sha256":raw_sha256(raws["procedure"])}
    raws["preflight"]=canonical_bytes({"schema_id":"P4-PREFLIGHT-v1","status":"PASS",**common},exclude_volatile=False)
    raws["human_go"]=canonical_bytes({"schema_id":"P4-HUMAN-GO-v1","decision":"APPROVED",
        "session_id":"DEV-S01","preflight_sha256":raw_sha256(raws["preflight"]),**common},exclude_volatile=False)
    expected=ControlExpectation(tuple((k,raw_sha256(v)) for k,v in raws.items()),BASE_HEAD)
    return raws,expected,auth,sources

def checked_fixture(tmp_path):
    raws,expected,auth,sources=control_fixture(tmp_path)
    return preflight(raws,expected,auth,sources,current_head=BASE_HEAD)

def save_worker_packet(tmp_path):
    raws,expected,auth,sources=control_fixture(tmp_path)
    packet={"root":str(tmp_path),"controls":{k:base64.b64encode(v).decode() for k,v in raws.items()},
        "sources":{k:base64.b64encode(v).decode() for k,v in sources.items()},
        "hashes":list(expected.hashes),"code_head":expected.code_head}
    path=tmp_path/"worker-packet.json"
    path.write_bytes(canonical_bytes(packet,exclude_volatile=False))
    return path

def worker(packet_path,mode):
    packet=json.loads(Path(packet_path).read_bytes())
    root=Path(packet["root"])
    raws={k:base64.b64decode(v) for k,v in packet["controls"].items()}
    sources={k:base64.b64decode(v) for k,v in packet["sources"].items()}
    expected=ControlExpectation(tuple(tuple(e) for e in packet["hashes"]),packet["code_head"])
    auth=WorkspaceAuthorization(root,"DEV-WORKSPACE",(root.parent/"protected",))
    checked=preflight(raws,expected,auth,sources,current_head=BASE_HEAD,inspection_only=mode=="INSPECT")
    if mode=="INSPECT":
        result=inspect_session(checked)
        try:run_session(checked)
        except ValueError:result["inspection_context_execution"]="REJECTED"
        else:raise AssertionError("inspector executed")
        print(json.dumps(result));return
    import phase4.runner as runner
    original=runner.evaluate_action
    def counted(*args,**kwargs):
        with (root/"worker-governance-calls.txt").open("a",encoding="ascii") as f:
            f.write("called\n");f.flush();os.fsync(f.fileno())
        if mode=="E":os._exit(71)
        return original(*args,**kwargs)
    runner.evaluate_action=counted
    def crash(window):
        if window==mode:
            if window=="C":
                partial=root/"DEV-S01"/"DEV-S01-B01-CTRL-01"/"P4-CTRL-01"/"attempt-01"/"00_spec"
                partial.mkdir()
                with (partial/"attempt_start.json").open("xb") as f:
                    f.write(b'{"partial":');f.flush();os.fsync(f.fileno())
            os._exit(71)
    run_session(checked,_fault_hook=crash)

def invoke_worker(packet,mode):
    code="import runpy,sys; module=runpy.run_path(sys.argv[1]); module['worker'](sys.argv[2],sys.argv[3])"
    return subprocess.run([sys.executable,"-B","-X","utf8","-c",code,str(Path(__file__).resolve()),str(packet),mode],
        capture_output=True,text=True,encoding="utf-8",check=False)

class TestSession:
    def test_completed_42_slots_and_no_second_session(self,tmp_path):
        checked=checked_fixture(tmp_path)
        result=run_session(checked).value
        assert result["status"]=="COMPLETED"
        assert result["governance_call_count"]==42
        assert result["retry_count"]==0
        assert len(result["slot_statuses"])==42
        assert set(result["slot_statuses"].values())=={"COMPLETED"}
        assert inspect_session(checked)["status"]=="COMPLETED"
        with pytest.raises((ValueError,FileExistsError)):run_session(checked)

    def test_first_runtime_failure_stops_later_slots(self,tmp_path,monkeypatch):
        import phase4.runner as runner
        checked=checked_fixture(tmp_path)
        calls=[]
        def fail(*a,**k):calls.append(1);raise RuntimeError("injected runtime failure")
        monkeypatch.setattr(runner,"evaluate_action",fail)
        result=run_session(checked).value
        assert result["status"]=="STOPPED_RUNTIME_OR_VERIFICATION"
        assert len(calls)==1
        assert list(result["slot_statuses"].values()).count("NOT_RUN_AFTER_STOP")==41
        assert result["failure"]["error"].startswith("RuntimeError")
        with pytest.raises((ValueError,FileExistsError)):run_session(checked)
        assert len(calls)==1

    def test_start_failure_never_invokes_governance(self,tmp_path,monkeypatch):
        import phase4.session as session
        import phase4.runner as runner
        checked=checked_fixture(tmp_path)
        monkeypatch.setattr(session,"_new_json",lambda *a,**k:(_ for _ in ()).throw(OSError("injected start failure")))
        monkeypatch.setattr(runner,"evaluate_action",lambda *a,**k:pytest.fail("governance called"))
        with pytest.raises(OSError):run_session(checked)
        assert inspect_session(checked)["status"]=="STOPPED_CRASH_OR_INCOMPLETE_ATTEMPT"

class TestCrash:
    @pytest.mark.parametrize("window",list("ABCDEFG"))
    def test_crash_and_separate_restart_inspector_never_reruns(self,tmp_path,window):
        packet=save_worker_packet(tmp_path)
        failed=invoke_worker(packet,window)
        assert failed.returncode==71,(failed.stdout,failed.stderr)
        calls=tmp_path/"worker-governance-calls.txt"
        before=calls.read_bytes() if calls.exists() else b""
        inspected=invoke_worker(packet,"INSPECT")
        assert inspected.returncode==0,inspected.stderr
        report=json.loads(inspected.stdout)
        assert report["status"]==("NOT_STARTED" if window=="A" else "STOPPED_CRASH_OR_INCOMPLETE_ATTEMPT")
        assert report["resumable"] is False
        assert report["inspection_context_execution"]=="REJECTED"
        assert (calls.read_bytes() if calls.exists() else b"")==before
        assert len(before.splitlines())==(1 if window in "EFG" else 0)
        if window not in "AB":
            assert list(report["slot_statuses"].values()).count("EXECUTION_STATUS_INDETERMINATE")==1
        if window=="G":
            result=tmp_path/"DEV-S01"/"DEV-S01-B01-CTRL-01"/"P4-CTRL-01"/"attempt-01"/"08_reconstruction"/"core_result.json"
            assert result.is_file()

class TestDryPlan:
    def test_42_unique_ordered_slots_without_governance(self,tmp_path,monkeypatch):
        import phase4.runner as runner
        checked=checked_fixture(tmp_path)
        monkeypatch.setattr(runner,"evaluate_action",lambda *a,**k:pytest.fail("governance called"))
        monkeypatch.setattr(runner,"evaluate_reentry",lambda *a,**k:pytest.fail("governance called"))
        plan=dry_plan(checked)
        assert plan["governance_call_count"]==0
        assert plan["standard_attempt_count"]==42 and plan["hard_max"]==60
        assert len({s["slot_id"] for s in plan["slots"]})==42
        assert [s["attempt_number"] for s in plan["slots"]]==[1,2,3]*14
        assert not (tmp_path/"DEV-S01").exists()


class TestSessionBoundaryFailures:
    def test_pre_governance_marker_failure_counts_zero(self,tmp_path,monkeypatch):
        import phase4.session as session
        checked=checked_fixture(tmp_path)
        original=session.initialize_attempt
        def tamper(*args,**kwargs):
            permit=original(*args,**kwargs)
            (permit.boundary.directory.path/"00_spec"/"attempt_start.json").write_bytes(b"{}")
            return permit
        monkeypatch.setattr(session,"initialize_attempt",tamper)
        result=run_session(checked).value
        assert result["status"]=="STOPPED_RUNTIME_OR_VERIFICATION"
        assert result["governance_call_count"]==0

    def test_unexpected_session_item_rejects_recovery_completion(self,tmp_path):
        checked=checked_fixture(tmp_path)
        root=tmp_path/"DEV-S01";root.mkdir()
        (root/"unapproved.txt").write_bytes(b"unexpected")
        result=inspect_session(checked)
        assert result["status"]=="STOPPED_CRASH_OR_INCOMPLETE_ATTEMPT"
        assert result["resumable"] is False
