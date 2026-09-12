from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest
from phase3.identity import canonical_bytes,raw_sha256
from phase4.contracts import JsonSnapshot
from phase4.runner import evaluate_once
from phase4.evidence import EvidenceWriter,INVENTORY,list_artifacts
from phase4.verification import verify_attempt,compare_attempts

# Reuse only development fixture builders, never production approval generation.
spec=importlib.util.spec_from_file_location("p4_test_bridge_fixtures",Path(__file__).with_name("test_governance_bridge.py"))
helpers=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

def completed(tmp_path,case_id="P4-PHY-02"):
    sources,approved=helpers.p4_materials()
    prepared=helpers.p4_prepared(case_id,sources,approved)
    permit=helpers.p4_started(tmp_path,prepared)
    writer=EvidenceWriter(permit);writer.persist_pre_evaluation()
    result=evaluate_once(permit)
    writer.persist_result(result)
    writer.reconcile_and_finalize()
    return writer,approved,result

class TestEvidence:
    def test_inventory_last_and_no_further_write(self,tmp_path):
        writer,approved,result=completed(tmp_path)
        root=writer.root
        raw=(root/INVENTORY).read_bytes()
        inventory=json.loads(raw)
        assert INVENTORY not in {e["path"] for e in inventory["artifacts"]}
        assert set(list_artifacts(root))=={e["path"] for e in inventory["artifacts"]}|{INVENTORY}
        with pytest.raises(ValueError):writer.record_failure("after inventory")
        assert (root/INVENTORY).read_bytes()==raw
        assert verify_attempt(root,approved,raw_sha256(raw))["transition_match"]

    def test_complete_result_precedes_reconciliation(self,tmp_path,monkeypatch):
        import phase4.verification as verification
        sources,approved=helpers.p4_materials()
        permit=helpers.p4_started(tmp_path,helpers.p4_prepared("P4-CTRL-01",sources,approved))
        writer=EvidenceWriter(permit);writer.persist_pre_evaluation()
        result=evaluate_once(permit);writer.persist_result(result)
        assert (writer.root/"08_reconstruction/core_result.json").exists()
        assert not (writer.root/INVENTORY).exists()
        def failure(*a,**k):raise ValueError("injected reconstruction error")
        monkeypatch.setattr(verification,"verify_core",failure)
        with pytest.raises(ValueError):writer.reconcile_and_finalize()
        inventory=json.loads((writer.root/INVENTORY).read_bytes())
        assert inventory["status"]=="FAILED"
        assert "09_findings/failure.json" in {e["path"] for e in inventory["artifacts"]}
        assert (writer.root/"08_reconstruction/core_result.json").exists()

    @pytest.mark.parametrize("kind",["missing","tamper","extra","inventory"])
    def test_missing_extra_tampered_artifacts_rejected(self,tmp_path,kind):
        writer,approved,result=completed(tmp_path)
        root=writer.root
        if kind=="missing":(root/"04_governance/decision_receipt.json").unlink()
        elif kind=="tamper":(root/"04_governance/decision_receipt.json").write_bytes(b"{}")
        elif kind=="extra":(root/"03_context/unapproved.json").write_bytes(b"{}")
        else:
            inv=json.loads((root/INVENTORY).read_bytes());inv["artifacts"].append(inv["artifacts"][0])
            (root/INVENTORY).write_bytes(canonical_bytes(inv,exclude_volatile=False))
        with pytest.raises((ValueError,OSError)):verify_attempt(root,approved)

    def test_same_case_replay_without_governance(self,tmp_path,monkeypatch):
        import phase4.runner as runner
        a=tmp_path/"a";b=tmp_path/"b";a.mkdir();b.mkdir()
        left,approved,result=completed(a)
        right,other,result2=completed(b)
        monkeypatch.setattr(runner,"evaluate_action",lambda *a,**k:pytest.fail("governance rerun"))
        monkeypatch.setattr(runner,"evaluate_reentry",lambda *a,**k:pytest.fail("governance rerun"))
        assert compare_attempts(left.root,right.root,approved)["replay"]=="PASS"

    def test_cross_case_not_replay_equivalent(self,tmp_path):
        a=tmp_path/"a";b=tmp_path/"b";a.mkdir();b.mkdir()
        left,approved,result=completed(a,"P4-PHY-02")
        right,other,result2=completed(b,"P4-PHY-03")
        with pytest.raises(ValueError):compare_attempts(left.root,right.root,approved)

    def test_pre_spec_never_appends_observed_result(self,tmp_path):
        sources,approved=helpers.p4_materials()
        permit=helpers.p4_started(tmp_path,helpers.p4_prepared("P4-REM-01",sources,approved))
        writer=EvidenceWriter(permit);writer.persist_pre_evaluation()
        before=(writer.root/"00_spec/spec.json").read_bytes()
        writer.persist_result(evaluate_once(permit));writer.reconcile_and_finalize()
        assert (writer.root/"00_spec/spec.json").read_bytes()==before
        assert verify_attempt(writer.root,approved)["transition_match"]

class TestEvidenceBinding:
    def test_saved_map_is_exact_runtime_map(self,tmp_path):
        writer,approved,result=completed(tmp_path)
        context=json.loads((writer.root/"03_context/decision_basis.json").read_bytes())["validation_context"]
        assert context["physical_identity_expectation"]==writer.permit.prepared.physical_expectation.to_dict()
        assert context["approved_input_manifest_identity"]==approved.expected_raw_sha256
        assert verify_attempt(writer.root,approved)["identity"]=="PASS"

    @pytest.mark.parametrize("field",["physical_identity_expectation","case_id","resulting_payload_sha256","approved_input_manifest_identity"])
    def test_saved_expectation_binding_tamper_rejected_even_if_result_rehashed(self,tmp_path,field):
        from phase4.verification import verify_core
        from phase3.identity import canonical_sha256
        writer,approved,result=completed(tmp_path)
        value=result.value
        context=value["decision_basis"]["validation_context"]
        if field=="physical_identity_expectation":context[field]["route_clearance"]="0"*64
        elif field=="case_id":context[field]="P4-PHY-03"
        else:context[field]="0"*64
        value["result_sha256"]=canonical_sha256({k:v for k,v in value.items() if k!="result_sha256"},exclude_volatile=False)
        raw=canonical_bytes(value,exclude_volatile=False)
        (writer.root/"08_reconstruction/core_result.json").write_bytes(raw)
        (writer.root/"08_reconstruction/core_result_artifact.json").write_bytes(canonical_bytes({"raw_sha256":raw_sha256(raw),"bytes":len(raw)},exclude_volatile=False))
        with pytest.raises(ValueError):verify_core(writer.root,approved)

    def test_missing_saved_expectation_is_rejected(self,tmp_path):
        from phase4.verification import verify_core
        writer,approved,result=completed(tmp_path)
        path=writer.root/"03_context/decision_basis.json"
        value=json.loads(path.read_bytes());del value["validation_context"]["physical_identity_expectation"]
        path.write_bytes(canonical_bytes(value,exclude_volatile=False))
        with pytest.raises(ValueError):verify_core(writer.root,approved)
