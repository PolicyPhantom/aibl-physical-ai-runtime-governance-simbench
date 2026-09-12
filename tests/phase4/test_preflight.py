import importlib.util
from pathlib import Path
import json
import pytest
from phase3.identity import canonical_bytes,raw_sha256
from phase4.session import ControlExpectation,preflight
_spec=importlib.util.spec_from_file_location("p4_preflight_session_fixtures",Path(__file__).with_name("test_session.py"))
helpers=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(helpers)

class TestPreflight:
    @pytest.mark.parametrize("name",["plan","manifest","procedure","workspace","preflight","human_go"])
    def test_missing_control_rejected(self,tmp_path,name):
        raws,expected,auth,sources=helpers.control_fixture(tmp_path)
        del raws[name]
        with pytest.raises(ValueError):preflight(raws,expected,auth,sources,current_head=helpers.BASE_HEAD)
        assert not (tmp_path/"DEV-S01").exists()

    @pytest.mark.parametrize("name",["plan","manifest","procedure","workspace","preflight","human_go"])
    def test_tampered_raw_control_rejected(self,tmp_path,name):
        raws,expected,auth,sources=helpers.control_fixture(tmp_path)
        raws[name]+=b" "
        with pytest.raises(ValueError):preflight(raws,expected,auth,sources,current_head=helpers.BASE_HEAD)

    @pytest.mark.parametrize("name,field,value",[
        ("human_go","decision","REJECTED"),("human_go","session_id","OTHER"),
        ("preflight","status","FAIL"),("workspace","root","D:/unapproved"),
        ("procedure","no_retry",False),("plan","attempt_count",60)])
    def test_rehashed_but_inconsistent_control_rejected(self,tmp_path,name,field,value):
        raws,expected,auth,sources=helpers.control_fixture(tmp_path)
        doc=json.loads(raws[name]);doc[field]=value
        raws[name]=canonical_bytes(doc,exclude_volatile=False)
        hashes=dict(expected.hashes);hashes[name]=raw_sha256(raws[name])
        expected=ControlExpectation(tuple(hashes.items()),helpers.BASE_HEAD)
        with pytest.raises(ValueError):preflight(raws,expected,auth,sources,current_head=helpers.BASE_HEAD)

    def test_code_head_mismatch_rejected(self,tmp_path):
        raws,expected,auth,sources=helpers.control_fixture(tmp_path)
        with pytest.raises(ValueError):preflight(raws,expected,auth,sources,current_head="0"*40)

    def test_existing_partial_session_not_unstarted(self,tmp_path):
        raws,expected,auth,sources=helpers.control_fixture(tmp_path)
        (tmp_path/"DEV-S01").mkdir()
        with pytest.raises(ValueError):preflight(raws,expected,auth,sources,current_head=helpers.BASE_HEAD)
