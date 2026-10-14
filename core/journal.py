"""Editor state under ``.editor/``: the write lock, the baseline store and the event log.

Every write appends one JSONL record naming the bytes it replaced and the bytes it left, and
keeps both in a content-addressed baseline, so a rollback restores recorded bytes instead of
a re-serialisation.  Segments follow docs/project-layout.md section 8: a segment is sealed
after five idle minutes and the next event opens a new one, so filename order is time order.
"""

import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from core.errors import EditRefused, FfError

EDITOR_DIR = ".editor"
LOCK_NAME = "lock"
LOG_DIR = "log"
BASELINE_DIR = "baseline"
SEGMENT_SUFFIX = ".jsonl"
SEGMENT_IDLE_SECONDS = 300
LOCK_STALE_SECONDS = 1800
RESULTS = ("set", "add", "remove", "pack", "undo", "redo")

CLOCK: Callable[[], float] = time.time


# --- paths and byte-level writes --------------------------------------------


def editor_dir(project_root: Path) -> Path:
    """The editor state directory of a project."""
    return project_root / EDITOR_DIR


def log_dir(project_root: Path) -> Path:
    """The directory holding the log segments."""
    return editor_dir(project_root) / LOG_DIR


def baseline_dir(project_root: Path) -> Path:
    """The directory holding the recorded document bytes."""
    return editor_dir(project_root) / BASELINE_DIR


def confine(path: Path, project_root: Path) -> str:
    """Refuse a target outside the project or inside the editor directory.

    Returns the project-relative POSIX path, which is what a log record stores.
    """
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        raise EditRefused(f"{path.name} is outside the project directory {project_root.name!r}") from None
    if EDITOR_DIR in relative.parts:
        raise EditRefused(f"{path.name}: the editor directory is not editable")
    return relative.as_posix()


def write_atomic(path: Path, data: bytes) -> None:
    """Write a sibling temporary file and replace the target with it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".ff-edit-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def digest_of(data: bytes) -> str:
    """The digest a byte string is stored and recorded under."""
    return hashlib.sha256(data).hexdigest()


# --- lock -------------------------------------------------------------------


def lock_state(project_root: Path) -> dict:
    """The current lock as recorded, with its age; never removes it."""
    lock = editor_dir(project_root) / LOCK_NAME
    state: dict = {"path": f"{EDITOR_DIR}/{LOCK_NAME}", "held": lock.exists()}
    if not lock.exists():
        return state
    state["age_seconds"] = round(time.time() - lock.stat().st_mtime, 1)
    state["stale"] = state["age_seconds"] > LOCK_STALE_SECONDS
    try:
        state.update(json.loads(lock.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        state["content"] = "unreadable"
    return state


def _holder(project_root: Path) -> str:
    """One-line description of the lock holder, for a refusal message."""
    state = lock_state(project_root)
    parts = [f"{key}={state[key]}" for key in ("pid", "started") if key in state]
    if not parts:
        parts = [state.get("content", "unknown owner")]
    if state.get("stale"):
        parts.append("stale")
    return " ".join(str(part) for part in parts)


@contextmanager
def hold_lock(project_root: Path, *, tool: str) -> Iterator[None]:
    """Hold ``.editor/lock`` for one write; a held lock refuses, it is never stolen."""
    editor = editor_dir(project_root)
    editor.mkdir(parents=True, exist_ok=True)
    lock = editor / LOCK_NAME
    payload = {
        "pid": os.getpid(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": tool,
    }
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise EditRefused(f"{EDITOR_DIR}/{LOCK_NAME} is held ({_holder(project_root)}); nothing was written") from None
    try:
        os.write(handle, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        yield
    finally:
        os.close(handle)
        lock.unlink(missing_ok=True)


# --- baseline ---------------------------------------------------------------


def store_blob(project_root: Path, data: bytes) -> str:
    """Keep a document version under its own digest; returns the digest."""
    digest = digest_of(data)
    path = baseline_dir(project_root) / digest
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, data)
    return digest


def load_blob(project_root: Path, digest: str) -> bytes:
    """Read back a recorded version, verifying that it is still the bytes it names."""
    path = baseline_dir(project_root) / digest
    if not path.is_file():
        raise FfError(f"{EDITOR_DIR}/{BASELINE_DIR}/{digest}: the recorded bytes of this change are missing")
    data = path.read_bytes()
    if digest_of(data) != digest:
        raise FfError(f"{EDITOR_DIR}/{BASELINE_DIR}/{digest}: the recorded bytes do not match their digest")
    return data


# --- event log --------------------------------------------------------------


def segments(project_root: Path) -> list[Path]:
    """Segment files in filename order, which is chronological order."""
    directory = log_dir(project_root)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(f"*{SEGMENT_SUFFIX}") if path.is_file())


def read_events(project_root: Path) -> list[dict]:
    """Every record of every segment, in append order."""
    events: list[dict] = []
    for path in segments(project_root):
        events.extend(_read_segment(path))
    return events


def append(project_root: Path, record: dict, *, now: float | None = None) -> dict:
    """Append one record, opening a new segment when the current one went idle."""
    moment = CLOCK() if now is None else now
    directory = log_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = _open_segment(directory, moment)
    index = len(_read_segment(path)) + 1 if path.is_file() else 1
    event = {
        "id": f"{path.stem}:{index}",
        "segment": path.name,
        "timestamp": _stamp(moment),
    }
    event.update(record)
    with open(path, "a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def stacks(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split the log into the changes currently applied and those last reverted.

    A ``set``, an ``add`` or a ``remove`` applies a change, an ``undo`` takes the change it
    names off the applied stack and leaves it on the reverted one, a ``redo`` moves it back.
    A new change of any of those three kinds clears the reverted stack, as a fresh edit
    discards what could be redone.  A ``pack`` record is kept in the log but reverts nothing,
    so it appears on neither stack.
    """
    by_id = {event["id"]: event for event in events if event.get("id")}
    applied: list[str] = []
    undone: list[str] = []
    for event in events:
        result = event.get("result")
        target = event.get("target")
        if result == "undo" and target:
            if target in applied:
                applied.remove(target)
            if target in by_id:
                undone.append(target)
        elif result == "redo" and target:
            if target in undone:
                undone.remove(target)
            if target in by_id:
                applied.append(target)
        elif result in ("set", "add", "remove"):
            applied.append(event["id"])
            undone.clear()
    return [by_id[item] for item in applied], [by_id[item] for item in undone]


def _read_segment(path: Path) -> list[dict]:
    """Records of one segment; a line that is not a JSON object is a hard error."""
    events: list[dict] = []
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            raise FfError(f"{EDITOR_DIR}/{LOG_DIR}/{path.name}:{number}: not a JSON record") from None
        if not isinstance(record, dict):
            raise FfError(f"{EDITOR_DIR}/{LOG_DIR}/{path.name}:{number}: not a JSON record")
        events.append(record)
    return events


def _open_segment(directory: Path, moment: float) -> Path:
    """The segment to append to: the newest one while it is fresh, else a new file."""
    found = sorted(path for path in directory.glob(f"*{SEGMENT_SUFFIX}") if path.is_file())
    if found:
        last = found[-1]
        events = _read_segment(last)
        since = _epoch(events[-1].get("timestamp")) if events else None
        if since is None:
            try:
                since = last.stat().st_mtime
            except OSError:
                since = None
        if since is not None and moment - since < SEGMENT_IDLE_SECONDS:
            return last
    return directory / (_stamp(moment, "%Y%m%dT%H%M%S") + SEGMENT_SUFFIX)


def _stamp(moment: float, pattern: str = "%Y-%m-%dT%H:%M:%S%z") -> str:
    """Local time of an epoch, as an ISO timestamp or a segment name."""
    if pattern != "%Y-%m-%dT%H:%M:%S%z":
        return time.strftime(pattern, time.localtime(moment))
    return datetime.fromtimestamp(moment).astimezone().isoformat(timespec="seconds")


def _epoch(stamp) -> float | None:
    """Epoch of a recorded timestamp, or ``None`` when it is missing or unreadable."""
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None
