"""Undo and redo: put back the bytes the log recorded, newest change first.

A revert is one more event naming the change it reverts, so the log stays the only source of
truth and the state is derived by replaying it (docs/project-layout.md section 8).  Every
change is planned before anything is written: a document that moved on disk, a missing
baseline or a missing document refuses the whole invocation instead of reverting a part of it.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from core import journal
from core.errors import EditRefused


@dataclass(frozen=True)
class Restore:
    """One document to put back, with the bytes and the state it must be in."""

    result: str
    target: str
    document: str
    entity: str
    field: str
    path: Path
    data: bytes
    expect: str
    before: str
    after: str
    bytes_before: int

    @property
    def digest(self) -> str:
        """Digest of the bytes this restore writes."""
        return journal.digest_of(self.data)


def plan_undo(project_root: Path, count: int = 1) -> list[Restore]:
    """The last ``count`` applied changes, newest first."""
    applied, _ = journal.stacks(journal.read_events(project_root))
    return _plan(project_root, applied, count, result="undo", label="undo")


def plan_redo(project_root: Path, count: int = 1) -> list[Restore]:
    """The last ``count`` reverted changes, most recently reverted first."""
    _, undone = journal.stacks(journal.read_events(project_root))
    return _plan(project_root, undone, count, result="redo", label="redo")


def apply(project_root: Path, restores: list[Restore], *, actor: str = "cli", now: float | None = None) -> dict:
    """Write every planned restore under the project lock and record one event each."""
    if not restores:
        raise EditRefused("nothing was restored")
    with journal.hold_lock(project_root, tool=f"core.cli {restores[0].result}"):
        current = []
        for item in restores:
            if not item.path.is_file():
                raise EditRefused(f"{item.document}: the document is gone; nothing was written")
            data = item.path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item.expect:
                raise EditRefused(
                    f"{item.document}: the document changed after that change; nothing was written"
                )
            current.append((item, data))
        events = []
        for item, data in current:
            journal.store_blob(project_root, data)
            journal.store_blob(project_root, item.data)
            journal.write_atomic(item.path, item.data)
            events.append(
                journal.append(
                    project_root,
                    {
                        "actor": actor,
                        "result": item.result,
                        "target": item.target,
                        "document": item.document,
                        "entity": item.entity,
                        "field": item.field,
                        "before": item.before,
                        "after": item.after,
                        "digest_before": item.expect,
                        "digest_after": item.digest,
                        "bytes_before": len(data),
                        "bytes_after": len(item.data),
                        "dry_run": False,
                    },
                    now=now,
                )
            )
    return {
        "result": restores[0].result,
        "count": len(restores),
        "targets": [item.target for item in restores],
        "events": [event["id"] for event in events],
        "documents": [
            {
                "document": item.document,
                "entity": item.entity,
                "field": item.field,
                "before": item.before,
                "after": item.after,
                "bytes_before": item.bytes_before,
                "bytes_after": len(item.data),
                "event": event["id"],
                "target": item.target,
            }
            for item, event in zip(restores, events)
        ],
    }


def _plan(project_root: Path, stack: list[dict], count: int, *, result: str, label: str) -> list[Restore]:
    """Turn the top ``count`` entries of a stack into verified restores."""
    if count < 1:
        raise EditRefused(f"{label} takes a count of at least 1")
    if not stack:
        raise EditRefused(f"there is no change to {label}")
    if count > len(stack):
        done = {"undo": "undone", "redo": "redone"}[result]
        raise EditRefused(f"only {len(stack)} change(s) can be {done}, {count} requested")
    return [_restore(project_root, event, result=result) for event in reversed(stack[-count:])]


def _restore(project_root: Path, event: dict, *, result: str) -> Restore:
    """Verify one recorded change and describe the write that reverts it."""
    document = event.get("document")
    if not isinstance(document, str) or not document:
        raise EditRefused(f"{event.get('id', 'a record')}: the record names no document")
    path = project_root / document
    journal.confine(path, project_root)
    if not path.is_file():
        raise EditRefused(f"{document}: the document is gone; nothing was written")
    if result == "undo":
        expect, want = event.get("digest_after"), event.get("digest_before")
        before, after = event.get("after"), event.get("before")
    else:
        expect, want = event.get("digest_before"), event.get("digest_after")
        before, after = event.get("before"), event.get("after")
    if not isinstance(expect, str) or not isinstance(want, str):
        raise EditRefused(f"{document}: the record of this change is incomplete; nothing was written")
    current = path.read_bytes()
    if hashlib.sha256(current).hexdigest() != expect:
        raise EditRefused(f"{document}: the document changed after that change; nothing was written")
    return Restore(
        result=result,
        target=event["id"],
        document=document,
        entity=event.get("entity") or Path(document).stem,
        field=event.get("field") or "",
        path=path,
        data=journal.load_blob(project_root, want),
        expect=expect,
        before=str(before) if before is not None else "",
        after=str(after) if after is not None else "",
        bytes_before=len(current),
    )
