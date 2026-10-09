"""Canonical TOML writer.

One fixed order so that a file written twice is byte-identical: scalars, then
single-instance sub-tables, then arrays of tables (docs/toml-mapping.md
section 4).  Values are emitted from ``TomlValue.raw``, so the reader's
literal survives a write untouched.
"""

from core.tomlmodel import TomlArrayEntry, TomlTable, TomlValue
from core.tomlread import BARE_KEY_RE


def render(table: TomlTable) -> str:
    """Render a document as text; LF line endings, trailing newline."""
    lines: list[str] = []
    _write_body(lines, table, [])
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def quote_string(text: str) -> str:
    """Wrap text in a basic string, escaping what TOML requires."""
    out = ['"']
    for char in text:
        if char in '"\\':
            out.append("\\" + char)
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _key(name: str) -> str:
    # A bare key may not be all digits, so numeric tag names are quoted
    # (docs/toml-mapping.md section 2.1).
    if BARE_KEY_RE.fullmatch(name) and not name[0].isdigit():
        return name
    return quote_string(name)


def _header(path: list[str], array: bool) -> str:
    inner = ".".join(_key(part) for part in path)
    return f"[[{inner}]]" if array else f"[{inner}]"


def _write_body(lines: list[str], table: TomlTable, path: list[str]) -> None:
    for name, entry in table.entries:
        if isinstance(entry, TomlValue):
            lines.append(f"{_key(name)} = {entry.raw}")
    for name, entry in table.entries:
        if isinstance(entry, TomlTable):
            lines.append(_header(path + [name], False))
            _write_body(lines, entry, path + [name])
        elif isinstance(entry, TomlArrayEntry):
            for item in entry.items:
                lines.append(_header(path + [name], True))
                _write_body(lines, item, path + [name])
