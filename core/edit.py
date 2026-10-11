"""One-field writes: addressing, schema and enum checks, fidelity, locking, atomic replace.

A write changes one leaf of one document and leaves every other byte as it stands.  An XML
document is re-rendered from the layout the reader recorded (the same renderer ``export``
uses); a TOML document is rewritten on the value's own source line.  The plan is computed
first and nothing is touched until ``apply_plan`` re-checks the file fingerprint, so a
refused edit leaves the disk unchanged (docs/cli.md section 4).
"""

import contextlib
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from core import textio, toml, xml
from core.enums import Enums, categories_of, split_value
from core.errors import FfError
from core.schema import schema_for
from core.toml import TomlArrayEntry, TomlEntry, TomlTable, TomlValue

EDITOR_DIR = ".editor"
LOCK_NAME = "lock"
MOD_FOLDER = "Mod"  # docs/project-layout.md section 2
LOCK_STALE_SECONDS = 1800
INTEGER_RE = toml.INTEGER_RE
FLOAT_RE = toml.FLOAT_RE
BOOLEANS = {
    "yes": True,
    "true": True,
    "1": True,
    "on": True,
    "no": False,
    "false": False,
    "0": False,
    "off": False,
}
XML_BOOLEAN_STYLES = ("true", "false")


class EditRefused(FfError):
    """A write the editor refuses; the CLI reports it as a usage error, exit code 2."""


@dataclass(frozen=True)
class EditPlan:
    """A validated change that has not been written yet."""

    path: Path
    relative: str
    field: str
    before: str
    after: str
    text: str
    data: bytes
    encoding: str
    newline: str
    had_bom: bool
    size_before: int
    digest: str
    enum: dict
    warnings: tuple[str, ...]


def project_root_of(data_root: Path) -> Path:
    """The directory that holds the project's editor state.

    A project keeps its data under ``Mod/``, so the editor directory sits one
    level above the data root; a project without ``Mod/`` uses its own root
    (docs/project-layout.md section 2).
    """
    return data_root.parent if data_root.name == MOD_FOLDER else data_root


def plan_set(
    document,
    field: str,
    value: str,
    *,
    enums: Enums | None = None,
    declared: Callable[[], dict[str, set[str]]] | None = None,
) -> EditPlan:
    """Validate one field change and render the file it would produce.

    ``document`` is a loaded ``core.cli.commands.Document``; the file is read
    again so the plan carries the fingerprint of the bytes it was computed from.
    ``declared`` is called only when a value misses the table, so a project scan
    stays off the path of every other edit.
    """
    enums = enums if enums is not None else Enums()
    segments = _segments(field)
    if not segments:
        raise EditRefused("field= needs a path such as description.quality")
    if "\n" in value or "\r" in value:
        raise EditRefused(f"{field}: a value may not contain a line break")
    search = tuple(part for part in segments if not part.isdigit())
    node = _schema_node(document, search, field)
    if node.shape != "leaf":
        raise EditRefused(f"{field}: {node.shape} is not a field")
    warnings: list[str] = []
    source = textio.read_source(document.path, warnings)
    if document.format == "toml":
        target = _resolve_toml(root_table(document.table, document.root_tag), segments, field)
        old_raw = target.raw
        before = _display(old_raw, toml_document=True)
        new_raw = _format_value(node, old_raw, value, toml_document=True)
        text = _splice_toml(source, target.line, old_raw, new_raw, document, field)
    else:
        element = _resolve_xml(document.root, segments, field)
        old_raw = element.text()
        before = _display(old_raw, toml_document=False)
        new_raw = _format_value(node, old_raw, value, toml_document=False)
        _set_xml_leaf(element, new_raw)
        text = document.xml_text()
    enum_report = _check_enum(document.root_tag, search, field, value, enums, declared)
    newline = "crlf" if "\r\n" in source.raw else "lf"
    data = textio.encode_export(text, file=str(document.path), encoding=document.encoding, newline="")
    if source.had_bom:
        data = textio.BOM + data
    return EditPlan(
        path=document.path,
        relative=document.relative,
        field=field,
        before=before,
        after=value,
        text=text,
        data=data,
        encoding=document.encoding,
        newline=newline,
        had_bom=source.had_bom,
        size_before=document.path.stat().st_size,
        digest=hashlib.sha256(document.path.read_bytes()).hexdigest(),
        enum=enum_report,
        warnings=tuple(warnings),
    )


def apply_plan(plan: EditPlan, project_root: Path, *, dry_run: bool = False) -> dict:
    """Write a plan under the project lock, or report it when ``dry_run``.

    A dry run creates nothing, including the lock and the editor directory.  A
    real write re-checks the fingerprint recorded in the plan and refuses when
    the document changed meanwhile.
    """
    if dry_run:
        return report(plan, written=False, dry_run=True)
    _confine(plan.path, project_root)
    editor = project_root / EDITOR_DIR
    editor.mkdir(parents=True, exist_ok=True)
    with _lock(editor):
        _check_unchanged(plan)
        _atomic_write(plan)
    return report(plan, written=True, dry_run=False)


def report(plan: EditPlan, *, written: bool, dry_run: bool) -> dict:
    """The machine payload of a set invocation."""
    payload = {
        "path": plan.relative,
        "field": plan.field,
        "before": plan.before,
        "after": plan.after,
        "encoding": plan.encoding,
        "newline": plan.newline,
        "bom": plan.had_bom,
        "bytes_before": plan.size_before,
        "bytes_after": len(plan.data),
        "digest_before": plan.digest,
        "enum": plan.enum,
        "dry_run": dry_run,
        "written": written,
        "warnings": list(plan.warnings),
    }
    return payload


# --- addressing -------------------------------------------------------------


def _segments(field: str) -> tuple[str, ...]:
    """The field's segments, accepting both ``a.b.c`` and ``a/b/c``."""
    return tuple(part for part in field.replace("/", ".").split(".") if part)


def _schema_node(document, segments: tuple[str, ...], field: str):
    """The schema node of a field, refusing fields the schema does not declare."""
    schema = schema_for(document.root_tag)
    if schema is None:
        raise EditRefused(f"{field}: no schema for <{document.root_tag}> documents")
    node = schema.lookup((document.root_tag, *segments))
    if node is None:
        raise EditRefused(f"{field}: not declared by the schema of <{document.root_tag}>")
    return node


def _resolve_xml(root: xml.XmlElement, segments: tuple[str, ...], field: str) -> xml.XmlElement:
    """Walk to one element; a repeated tag needs an index segment."""
    current = [root]
    position = 0
    while position < len(segments):
        tag = segments[position]
        if tag.isdigit():
            raise EditRefused(f"{field}: an index must follow the element it selects")
        matches = [child for node in current for child in node.children if child.tag == tag]
        position += 1
        if position < len(segments) and segments[position].isdigit():
            wanted = int(segments[position])
            if wanted >= len(matches):
                raise EditRefused(f"{field}: index {wanted} is out of range for <{tag}> ({len(matches)} match(es))")
            matches = [matches[wanted]]
            position += 1
        if not matches:
            raise EditRefused(f"{field}: no <{tag}> under {_where(current)}")
        current = matches
    if len(current) != 1:
        raise EditRefused(f"{field}: {len(current)} matches; add an index, for example {field}.0")
    element = current[0]
    if element.children:
        raise EditRefused(f"{field}: <{element.tag}> has child elements, it is not a field")
    return element


def _where(nodes: list[xml.XmlElement]) -> str:
    """Human name of the element a field was looked up in."""
    tags = sorted({node.tag for node in nodes})
    return " or ".join(f"<{tag}>" for tag in tags) if tags else "the document root"


def root_table(table: TomlTable, root_tag: str) -> TomlTable:
    """The table a TOML document keeps its fields in.

    A document is stored as one top-level table named after the root element,
    and ``field=`` is written relative to that element (docs/cli.md section 4).
    """
    entries = table.entries
    if len(entries) == 1 and entries[0][0] == root_tag and isinstance(entries[0][1], TomlTable):
        return entries[0][1]
    return table


def _resolve_toml(table: TomlTable, segments: tuple[str, ...], field: str) -> TomlValue:
    """Walk to one scalar; a repeated key needs an index segment."""
    current: list[TomlEntry] = [table]
    position = 0
    while position < len(segments):
        key = segments[position]
        if key.isdigit():
            raise EditRefused(f"{field}: an index must follow the key it selects")
        following: list[TomlEntry] = []
        for entry in current:
            if isinstance(entry, TomlArrayEntry):
                for item in entry.items:
                    following.extend(_named(item, key))
            elif isinstance(entry, TomlTable):
                following.extend(_named(entry, key))
        position += 1
        if position < len(segments) and segments[position].isdigit():
            wanted = int(segments[position])
            items: list[TomlEntry] = []
            for entry in following:
                items.extend(entry.items if isinstance(entry, TomlArrayEntry) else [entry])
            if wanted >= len(items):
                raise EditRefused(f"{field}: index {wanted} is out of range for {key} ({len(items)} match(es))")
            following = [items[wanted]]
            position += 1
        if not following:
            raise EditRefused(f"{field}: no key {key!r} in {_toml_where(current)}")
        current = following
    if len(current) != 1:
        raise EditRefused(f"{field}: {len(current)} matches; add an index, for example {field}.0")
    entry = current[0]
    if not isinstance(entry, TomlValue):
        raise EditRefused(f"{field}: {field} is a table, not a field")
    return entry


def _toml_where(entries: list[TomlEntry]) -> str:
    """Human name of the table a key was looked up in."""
    names = ["the document root" for entry in entries if isinstance(entry, TomlTable)]
    return " or ".join(names) if names else "the document"


def _named(table: TomlTable, key: str) -> list[TomlEntry]:
    """Entries stored under one key, in order."""
    return [entry for name, entry in table.entries if name == key]


# --- value handling ---------------------------------------------------------


def _display(raw: str, *, toml_document: bool) -> str:
    """A value as it reads in the report: no quotes, no trailing comment, no spacing."""
    text = raw
    index = xml.find_comment(text)
    if index is not None:
        text = text[:index]
    text = text.strip()
    if toml_document and len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    return text


def _format_value(node, old_raw: str, value: str, *, toml_document: bool) -> str:
    """Render a value the way this document already writes that field."""
    kind = node.type
    if kind == "auto":
        kind = _infer_kind(old_raw, toml_document)
    if kind == "bool":
        return _format_bool(old_raw, value, toml_document=toml_document)
    if kind == "int":
        return str(_parse_int(value, node.name))
    if kind == "float":
        return _format_float(old_raw, _parse_float(value, node.name))
    if toml_document:
        return toml.quote_string(value)
    if "<" in value or ">" in value:
        raise EditRefused(f"{node.name}: a value may not contain '<' or '>'")
    return value


def _infer_kind(old_raw: str, toml_document: bool) -> str:
    """The value type of a field the schema leaves open, from its current spelling."""
    text = old_raw.strip()
    if toml_document and text[:1] in ('"', "'"):
        return "str"
    if text.lower() in ("yes", "no", "true", "false"):
        return "bool"
    if INTEGER_RE.fullmatch(text):
        return "int"
    if FLOAT_RE.fullmatch(text):
        return "float"
    return "str"


def _format_bool(old_raw: str, value: str, *, toml_document: bool) -> str:
    """A boolean in the document's own spelling: ``yes``/``no`` or ``true``/``false``."""
    text = value.strip().lower()
    if text not in BOOLEANS:
        raise EditRefused(f"{value!r} is not a boolean; use yes or no")
    flag = BOOLEANS[text]
    if toml_document:
        return "true" if flag else "false"
    style = old_raw.strip().lower()
    if style in XML_BOOLEAN_STYLES:
        return "true" if flag else "false"
    return "yes" if flag else "no"


def _parse_int(value: str, name: str) -> int:
    """An integer value, refusing anything else."""
    try:
        return int(value, 10)
    except ValueError:
        raise EditRefused(f"{name}: {value!r} is not an integer") from None


def _parse_float(value: str, name: str) -> float:
    """A numeric value, refusing anything else."""
    try:
        return float(value)
    except ValueError:
        raise EditRefused(f"{name}: {value!r} is not a number") from None


def _format_float(old_raw: str, value: float) -> str:
    """A number in the document's own style: integral stays integral unless it was not."""
    float_style = "." in old_raw or "e" in old_raw.lower()
    if float_style or not value.is_integer():
        return repr(value)
    return str(int(value))


# --- enum check -------------------------------------------------------------


def _check_enum(
    root_tag: str,
    segments: tuple[str, ...],
    field: str,
    value: str,
    enums: Enums,
    declared: Callable[[], dict[str, set[str]]] | None,
) -> dict:
    """Refuse an enumeration value no table and no document of the project declares."""
    categories = categories_of(root_tag, segments)
    if not categories:
        return {"category": None, "table": False, "source": enums.source}
    known = enums.checked(categories)
    label = "/".join(categories)
    extra: dict[str, set[str]] | None = None
    for category in categories:
        if not known:
            continue
        for part in split_value((category,), value):
            if enums.accepts((category,), part):
                continue
            if extra is None:
                extra = declared() if declared is not None else {}
            if part in extra.get(category, ()):
                continue
            raise EditRefused(
                f"{field}: {part!r} is not one of the {category} values"
                f" ({enums.table_size((category,))} known in {enums.source or 'the enum table'})"
            )
    if not known:
        return {"category": label, "table": False, "source": enums.source}
    return {"category": label, "table": True, "values": enums.table_size(categories), "source": enums.source}


# --- rendering --------------------------------------------------------------


def _replace_text(raw: str, new: str) -> str:
    """New leaf text, keeping the surrounding spacing and any trailing ``//`` comment."""
    comment = ""
    index = xml.find_comment(raw)
    if index is not None:
        raw, comment = raw[:index], raw[index:]
    lead = raw[: len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    return f"{lead}{new}{trail}{comment}"


def _set_xml_leaf(element: xml.XmlElement, new_raw: str) -> None:
    """Replace one leaf's text in place; a self-closing element becomes a pair."""
    if element.self_closing:
        element.self_closing = False
        element.raw_value = new_raw
        element.value = new_raw
        return
    element.raw_value = _replace_text(element.text(), new_raw)
    element.value = new_raw


def _splice_toml(source: textio.SourceText, line: int, old_raw: str, new_raw: str, document, field: str) -> str:
    """Rewrite the value on its own source line, leaving every other byte alone."""
    if "\r" in source.raw.replace("\r\n", ""):
        raise EditRefused(f"{field}: the document uses bare carriage returns; not supported")
    lines = source.raw.split("\n")
    if line < 1 or line > len(lines):
        raise EditRefused(f"{field}: source line {line} is outside the document")
    row = lines[line - 1]
    column = _assignment_at(row)
    if column is None:
        raise EditRefused(f"{field}: no assignment on source line {line}")
    rest = row[column + 1:]
    at = rest.find(old_raw)
    if at < 0:
        raise EditRefused(f"{field}: the value {old_raw!r} is not on source line {line}")
    lines[line - 1] = row[: column + 1] + rest[:at] + new_raw + rest[at + len(old_raw):]
    return "\n".join(lines)


def _assignment_at(line: str) -> int | None:
    """Index of the ``=`` that separates a key from its value, ignoring quoted keys."""
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "=":
            return index
        index += 1
    return None


# --- writing ----------------------------------------------------------------


def _confine(path: Path, project_root: Path) -> None:
    """Refuse a target outside the project, and a target inside the editor directory."""
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        raise EditRefused(f"{path.name} is outside the project directory {project_root.name!r}") from None
    if EDITOR_DIR in relative.parts:
        raise EditRefused(f"{path.name}: the editor directory is not editable")


def _check_unchanged(plan: EditPlan) -> None:
    """Refuse when the document changed after the plan was staged."""
    if hashlib.sha256(plan.path.read_bytes()).hexdigest() != plan.digest:
        raise EditRefused(f"{plan.relative}: the document changed after the change was staged; nothing was written")


def _atomic_write(plan: EditPlan) -> None:
    """Write a sibling temporary file and replace the target with it."""
    handle, name = tempfile.mkstemp(prefix=".ff-edit-", suffix=".tmp", dir=plan.path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(plan.data)
        os.replace(name, plan.path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def lock_state(project_root: Path) -> dict:
    """The current lock as recorded, with its age; never removes it."""
    lock = project_root / EDITOR_DIR / LOCK_NAME
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


def _holder(editor: Path) -> str:
    """One-line description of the lock holder, for a refusal message."""
    state = lock_state(editor.parent)
    parts = [f"{key}={state[key]}" for key in ("pid", "started") if key in state]
    if not parts:
        parts = [state.get("content", "unknown owner")]
    if state.get("stale"):
        parts.append("stale")
    return " ".join(str(part) for part in parts)


@contextlib.contextmanager
def _lock(editor: Path) -> Iterator[None]:
    """Hold ``.editor/lock`` for one write; a held lock refuses, it is never stolen."""
    lock = editor / LOCK_NAME
    payload = {
        "pid": os.getpid(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": "core.cli set",
    }
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise EditRefused(f"{EDITOR_DIR}/{LOCK_NAME} is held ({_holder(editor)}); nothing was written") from None
    try:
        os.write(handle, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        yield
    finally:
        os.close(handle)
        lock.unlink(missing_ok=True)
