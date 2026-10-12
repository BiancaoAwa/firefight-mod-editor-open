"""Cross-reference tables of a project: build them once, read them back.

``Mod index --write`` writes ``.editor/index.toml`` (the documents of the scope)
and ``.editor/refs.toml`` (the outgoing references of each of them).  Both start
with a fingerprint of the files they were built from, so a reader that finds a
different fingerprint ignores them and walks the documents again; a stale table
never changes an answer (docs/cli.md section 4.6).

The two files are a cache under ``.editor/``: the editor is their only writer
and their only reader, so the reader below understands the shape the writer
emits and nothing else.
"""

import hashlib
from datetime import datetime
from pathlib import Path

from core import journal

INDEX_NAME = "index.toml"
REFS_NAME = "refs.toml"

HEADER = (
    "# Cross-reference table of this project.  Written by `index --write`.\n"
    "# It is a cache: a table whose fingerprint does not match the documents on\n"
    "# disk is ignored and rebuilt (docs/cli.md section 4.6).\n"
)


def stamp(moment: float | None = None, pattern: str = "%Y-%m-%dT%H:%M:%S%z") -> str:
    """Local timestamp of one moment, in the shape the log uses."""
    if moment is None:
        return datetime.now().astimezone().strftime(pattern)
    return datetime.fromtimestamp(moment).astimezone().strftime(pattern)


def fingerprint(items: list[tuple[str, Path]]) -> str:
    """Digest of the relative names, sizes and write times of a scope.

    A file that cannot be stat-ed still contributes its name, so a scope that
    gains or loses one always changes the digest.
    """
    digest = hashlib.sha256()
    for relative, path in sorted(items):
        try:
            stat = path.stat()
        except OSError:
            digest.update(f"{relative}\t-\t-\n".encode("utf-8"))
            continue
        digest.update(f"{relative}\t{stat.st_size}\t{stat.st_mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()


def signature(kind: str, document_path: str, value: str) -> str:
    """One reference as a single line, so a table row stays one line."""
    return f"{kind}|{document_path}|{value}"


def decode(line: str) -> tuple[str, str, str] | None:
    """The kind, document path and value of one stored reference line."""
    parts = line.split("|", 2)
    if len(parts) != 3:
        return None
    kind, document_path, value = parts
    if not kind or not value:
        return None
    return kind, document_path, value


def _quote(text: str) -> str:
    """One TOML basic string; the reader unescapes exactly these two characters."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _built(built: dict) -> list[str]:
    """The ``[built]`` table of either file."""
    return [
        "[built]",
        f"at = {_quote(built['at'])}",
        f"scope = {_quote(built['scope'])}",
        f"fingerprint = {_quote(built['fingerprint'])}",
        f"documents = {built['documents']}",
        f"references = {built['references']}",
    ]


def render_index(built: dict, documents: dict[str, str]) -> str:
    """``.editor/index.toml``: every document of the scope and its root element."""
    lines = [HEADER, ""] + _built(built) + ["", "[documents]"]
    for relative in sorted(documents):
        lines.append(f"{_quote(relative)} = {_quote(documents[relative])}")
    return "\n".join(lines) + "\n"


def render_refs(built: dict, by_source: dict[str, list[str]]) -> str:
    """``.editor/refs.toml``: the outgoing references of each document."""
    lines = [HEADER, ""] + _built(built) + ["", "[by_source]"]
    for relative in sorted(by_source):
        items = ", ".join(_quote(item) for item in by_source[relative])
        lines.append(f"{_quote(relative)} = [{items}]")
    return "\n".join(lines) + "\n"


def write(project_root: Path, built: dict, documents: dict[str, str], by_source: dict[str, list[str]]) -> list[Path]:
    """Write both tables under the project's ``.editor/`` and return their paths."""
    directory = journal.editor_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (
        (INDEX_NAME, render_index(built, documents)),
        (REFS_NAME, render_refs(built, by_source)),
    ):
        path = directory / name
        journal.write_atomic(path, text.encode("utf-8"))
        written.append(path)
    return written


def _unquote(text: str) -> str | None:
    """The value of one quoted TOML string, or None when the text is not one."""
    text = text.strip()
    if not text.startswith('"'):
        return None
    out: list[str] = []
    index = 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 >= len(text):
                return None
            out.append(text[index + 1])
            index += 2
            continue
        if char == '"':
            return "".join(out) if not text[index + 1 :].strip() else None
        out.append(char)
        index += 1
    return None


def _array(text: str) -> list[str] | None:
    """The items of one quoted-string array, or None when the text is not one."""
    body = text.strip()
    if not (body.startswith("[") and body.endswith("]")):
        return None
    inner = body[1:-1].strip()
    if not inner:
        return []
    items = []
    for part in inner.split(","):
        value = _unquote(part)
        if value is None:
            return None
        items.append(value)
    return items


def read_table(path: Path) -> dict[str, dict[str, object]] | None:
    """Parse one table this module wrote, or None when it is not that shape."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    tables: dict[str, dict[str, object]] = {}
    section: dict[str, object] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = tables.setdefault(line[1:-1].strip(), {})
            continue
        if section is None or "=" not in line:
            return None
        key, _, value = line.partition("=")
        name = _unquote(key)
        if name is None:
            bare = key.strip()
            if not bare or '"' in bare or " " in bare:
                return None
            name = bare
        quoted = _unquote(value)
        if quoted is not None:
            section[name] = quoted
            continue
        if value.strip().lstrip("-").isdigit():
            section[name] = int(value.strip())
            continue
        items = _array(value)
        if items is None:
            return None
        section[name] = items
    return tables


def load(project_root: Path) -> tuple[dict, dict] | None:
    """Both tables of a project, or None when either is missing or unreadable."""
    directory = journal.editor_dir(project_root)
    index_tables = read_table(directory / INDEX_NAME)
    refs_tables = read_table(directory / REFS_NAME)
    if index_tables is None or refs_tables is None:
        return None
    return index_tables, refs_tables
