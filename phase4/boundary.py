"""Phase 4 exact output layout and no-overwrite directory boundaries.

Lexical/component validation does not eliminate filesystem TOCTOU. Controlled
workspaces must not be mutated by another process during an authorized session.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
import re
import stat

from .contracts import frozen_cases

REPOSITORY = Path(__file__).resolve().parents[1]
P3_PROTECTED_ROOTS = (
    Path("D:/AIBL_Phase3/phase3_trusted"),
    Path("D:/AIBL_Phase3/formal_control"),
    Path("D:/AIBL_Phase3/formal_workspace"),
)


class BoundaryError(ValueError):
    pass


def _parts(path):
    return tuple(part.casefold() for part in PureWindowsPath(str(path)).parts)


def overlaps(left, right):
    a, b = _parts(left), _parts(right)
    return a[:len(b)] == b or b[:len(a)] == a


def safe_segment(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise BoundaryError("unsafe path component")
    if value.split(".")[0].casefold() in {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1,10)), *(f"lpt{i}" for i in range(1,10))}:
        raise BoundaryError("reserved device name")
    return value


def absolute_path(value):
    path = Path(value)
    win = PureWindowsPath(str(value))
    if (not path.is_absolute() or not win.is_absolute() or str(value).startswith(("\\\\", "//"))
            or any(p in (".", "..") or p.endswith((" ", ".")) or ":" in p
                   for p in str(value).replace("\\", "/").split("/")[1:] if p)):
        raise BoundaryError("unsafe/non-local absolute path")
    return path


def inspect_directory(path):
    """lstat each exact component; access failure never means absence."""
    path = absolute_path(path)
    result = []
    for component in (*reversed(path.parents), path):
        try:
            info = os.lstat(component)
        except OSError as exc:
            raise BoundaryError(f"cannot inspect directory: {component}") from exc
        if not stat.S_ISDIR(info.st_mode) or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise BoundaryError(f"directory/reparse violation: {component}")
        # Windows may report inode 0 for a volume root. Require a stable ID
        # for the directory being bound, while still inspecting every ancestor.
        if component == path and not info.st_ino:
            raise BoundaryError("stable directory identity unavailable")
        result.append((str(component), info.st_dev, info.st_ino))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class WorkspaceAuthorization:
    root: Path
    authorization_id: str
    protected_roots: tuple[Path, ...]

    def __post_init__(self):
        object.__setattr__(self, "root", absolute_path(self.root))
        roots = tuple(absolute_path(p) for p in self.protected_roots)
        object.__setattr__(self, "protected_roots", roots)
        safe_segment(self.authorization_id)
        if not roots:
            raise BoundaryError("protected roots required")
        for protected in (REPOSITORY, *P3_PROTECTED_ROOTS, *roots):
            if overlaps(self.root, protected):
                raise BoundaryError("workspace overlaps a protected root")


@dataclass(frozen=True, slots=True)
class DirectoryBinding:
    path: Path
    chain: tuple[tuple[str, int, int], ...]

    @classmethod
    def capture(cls, path):
        path = absolute_path(path)
        return cls(path, inspect_directory(path))

    def validate(self):
        if inspect_directory(self.path) != self.chain:
            raise BoundaryError("directory identity changed")


@dataclass(frozen=True, slots=True)
class SessionBoundary:
    authorization: WorkspaceAuthorization
    root_binding: DirectoryBinding
    directory: DirectoryBinding
    session_id: str

    def validate(self):
        self.root_binding.validate()
        self.directory.validate()
        expected = self.authorization.root / safe_segment(self.session_id)
        if self.directory.path != expected:
            raise BoundaryError("session/root binding mismatch")


@dataclass(frozen=True, slots=True)
class AttemptBoundary:
    session: SessionBoundary
    directory: DirectoryBinding
    case_id: str
    attempt_number: int
    batch_id: str

    def validate(self):
        self.session.validate()
        expected = attempt_path(self.session, self.case_id, self.attempt_number)
        if expected != self.directory.path or self.batch_id != batch_id(self.session.session_id, self.case_id):
            raise BoundaryError("attempt mapping mismatch")
        self.directory.validate()


def batch_id(session_id, case_id):
    safe_segment(session_id)
    case = next((c for c in frozen_cases() if c.case_id == case_id), None)
    if case is None:
        raise BoundaryError("unknown case")
    return f"{session_id}-B{case.order:02}-{case_id[3:]}"


def attempt_path(session, case_id, attempt_number):
    if type(attempt_number) is not int or attempt_number not in (1, 2, 3):
        raise BoundaryError("attempt must be 1..3")
    return (session.directory.path / batch_id(session.session_id, case_id) /
            case_id / f"attempt-{attempt_number:02}")


def create_session_directory(authorization, session_id):
    if type(authorization) is not WorkspaceAuthorization:
        raise BoundaryError("workspace authorization required")
    safe_segment(session_id)
    root = DirectoryBinding.capture(authorization.root)
    path = authorization.root / session_id
    # mkdir without exist_ok is the exclusive creation operation.
    os.mkdir(path)
    result = SessionBoundary(authorization, root, DirectoryBinding.capture(path), session_id)
    result.validate()
    return result


def create_attempt_directory(session, case_id, attempt_number):
    session.validate()
    path = attempt_path(session, case_id, attempt_number)
    for parent in (path.parent.parent, path.parent):
        try:
            os.mkdir(parent)
        except FileExistsError:
            inspect_directory(parent)
    os.mkdir(path)
    result = AttemptBoundary(session, DirectoryBinding.capture(path), case_id,
                             attempt_number, batch_id(session.session_id, case_id))
    result.validate()
    return result
