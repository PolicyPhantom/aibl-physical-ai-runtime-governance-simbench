from dataclasses import replace
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import pytest
import phase4.boundary as boundary
from phase4.boundary import (
    BoundaryError, WorkspaceAuthorization, attempt_path, batch_id,
    create_attempt_directory, create_session_directory, overlaps, safe_segment,
)

def workspace(tmp_path):
    return WorkspaceAuthorization(tmp_path, "DEV-WORKSPACE", (tmp_path.parent / "protected",))

class TestBoundary:
    def test_exact_case_batch_attempt_mapping_and_exclusive_creation(self, tmp_path):
        session = create_session_directory(workspace(tmp_path), "DEV-S01")
        attempt = create_attempt_directory(session, "P4-PHY-01", 3)
        assert attempt.directory.path == tmp_path / "DEV-S01" / "DEV-S01-B09-PHY-01" / "P4-PHY-01" / "attempt-03"
        attempt.validate()
        with pytest.raises(FileExistsError):
            create_attempt_directory(session, "P4-PHY-01", 3)
        with pytest.raises(FileExistsError):
            create_session_directory(workspace(tmp_path), "DEV-S01")

    @pytest.mark.parametrize("value", ["../x", "x/y", "x\\y", "x:ads", "CON", "NUL", "COM1", "x.", "x ", ".", ""])
    def test_unsafe_components(self, value):
        with pytest.raises(BoundaryError):safe_segment(value)

    @pytest.mark.parametrize("attempt", [0, 4, True, "1", -1])
    def test_attempt_bounds(self, tmp_path, attempt):
        session = create_session_directory(workspace(tmp_path), "DEV-S01")
        with pytest.raises(BoundaryError):attempt_path(session, "P4-CTRL-01", attempt)

    def test_wrong_case_mapping(self, tmp_path):
        session = create_session_directory(workspace(tmp_path), "DEV-S01")
        with pytest.raises(BoundaryError):attempt_path(session, "P3-CTRL-01", 1)
        item = create_attempt_directory(session, "P4-CTRL-01", 1)
        with pytest.raises(BoundaryError):replace(item,case_id="P4-CTRL-02").validate()

    def test_casefold_component_overlap(self, tmp_path):
        assert overlaps(Path("D:/Protected"), Path("d:/protected/child"))
        assert not overlaps(Path("D:/Protected"), Path("D:/ProtectedElse"))
        for protected in (tmp_path, tmp_path.parent, tmp_path/"child"):
            with pytest.raises(BoundaryError):
                WorkspaceAuthorization(tmp_path,"DEV",(protected,))

    def test_repository_overlap_is_always_rejected(self):
        with pytest.raises(BoundaryError):
            WorkspaceAuthorization(boundary.REPOSITORY/"scratch","DEV",(Path("D:/other"),))

    def test_reparse_detection_uses_lstat_and_stops(self,tmp_path,monkeypatch):
        original=boundary.os.lstat
        def reparse(path):
            info=original(path)
            if Path(path)==tmp_path:
                return SimpleNamespace(st_mode=info.st_mode,st_ino=info.st_ino,
                    st_dev=info.st_dev,st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return info
        monkeypatch.setattr(boundary.os,"lstat",reparse)
        with pytest.raises(BoundaryError):create_session_directory(workspace(tmp_path),"DEV")

    def test_access_denied_not_absent(self,tmp_path,monkeypatch):
        original=boundary.os.lstat
        def denied(path):
            if Path(path)==tmp_path:raise PermissionError("injected denial")
            return original(path)
        monkeypatch.setattr(boundary.os,"lstat",denied)
        with pytest.raises(BoundaryError):create_session_directory(workspace(tmp_path),"DEV")
        assert not (tmp_path/"DEV").exists()

    def test_directory_replacement_identity(self,tmp_path,monkeypatch):
        session=create_session_directory(workspace(tmp_path),"DEV")
        original=boundary.os.lstat
        def replaced(path):
            info=original(path)
            if Path(path)==session.directory.path:
                return SimpleNamespace(st_mode=info.st_mode,st_ino=info.st_ino+1,
                    st_dev=info.st_dev,st_file_attributes=info.st_file_attributes)
            return info
        monkeypatch.setattr(boundary.os,"lstat",replaced)
        with pytest.raises(BoundaryError):create_attempt_directory(session,"P4-CTRL-01",1)

    def test_existing_file_is_not_directory(self,tmp_path):
        (tmp_path/"DEV").write_text("collision")
        with pytest.raises(FileExistsError):create_session_directory(workspace(tmp_path),"DEV")

    @pytest.mark.parametrize("protected",boundary.P3_PROTECTED_ROOTS)
    def test_p3_roots_rejected_lexically_even_if_caller_omits_them(self,protected,monkeypatch):
        monkeypatch.setattr(boundary.os,"lstat",lambda *a,**k:pytest.fail("protected filesystem accessed"))
        with pytest.raises(BoundaryError):
            WorkspaceAuthorization(protected/"candidate","DEV",(Path("C:/unrelated"),))
