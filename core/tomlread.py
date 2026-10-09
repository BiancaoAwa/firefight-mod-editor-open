"""In-house TOML reader for the documented subset.

Accepts tables, arrays of tables, basic and literal strings, quoted keys,
integers, floats and booleans.  Everything else raises TomlSyntaxError with a
position: inline tables, arrays, dates, multi-line strings and dotted bare keys
that jump levels (docs/toml-mapping.md section 6).
"""

import re

from core.errors import TomlSyntaxError
from core.tomlmodel import TomlArrayEntry, TomlEntry, TomlTable, TomlValue

BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
INTEGER_RE = re.compile(r"[+-]?[0-9]+")
FLOAT_RE = re.compile(r"[+-]?(?:[0-9]+\.[0-9]+|[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+)")
ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


def parse(text: str, origin: str) -> TomlTable:
    """Parse a TOML text into the document table."""
    root = TomlTable()
    current = root
    declared: set[int] = set()
    for number, raw in enumerate(text.split("\n"), start=1):
        body = _strip_comment(raw)
        stripped = body.strip()
        if not stripped:
            continue
        offset = len(body) - len(body.lstrip())
        if stripped.startswith("[["):
            if not stripped.endswith("]]"):
                _fail(origin, number, offset + 1, "array-of-tables header must end with ']]'")
            path = _parse_path(stripped[2:-2], origin, number, offset + 3)
            container = _resolve(root, path[:-1], declared, origin, number, offset)
            current = _open_array(container, path[-1], origin, number, offset + 1)
        elif stripped.startswith("["):
            if not stripped.endswith("]"):
                _fail(origin, number, offset + 1, "table header must end with ']'")
            path = _parse_path(stripped[1:-1], origin, number, offset + 2)
            container = _resolve(root, path[:-1], declared, origin, number, offset)
            current = _open_table(container, path[-1], declared, origin, number, offset + 1)
        else:
            key, raw_value = _split_assignment(stripped, origin, number, offset)
            if current.get(key) is not None:
                _fail(origin, number, offset + 1, f"duplicate key {key!r}")
            current.entries.append((key, _parse_value(raw_value, origin, number, offset + len(key) + 1)))
    return root


def _strip_comment(line: str) -> str:
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#":
            return line[:index]
        index += 1
    return line


def _fail(origin: str, line: int, column: int, hint: str) -> None:
    raise TomlSyntaxError(origin, line, column, hint)


def _parse_path(text: str, origin: str, line: int, column: int) -> list[str]:
    parts: list[str] = []
    index = 0
    size = len(text)
    while index < size:
        char = text[index]
        if char in "\"'":
            part, index = _read_quoted(text, index, origin, line, column + index)
            parts.append(part)
        else:
            start = index
            while index < size and text[index] not in ".]":
                index += 1
            part = text[start:index].strip()
            if BARE_KEY_RE.fullmatch(part) is None:
                _fail(origin, line, column + start, f"unsupported key {part!r}")
            parts.append(part)
        while index < size and text[index] in " \t":
            index += 1
        if index < size:
            if text[index] != ".":
                _fail(origin, line, column + index, "expected '.' between key parts")
            index += 1
            while index < size and text[index] in " \t":
                index += 1
    if not parts:
        _fail(origin, line, column, "empty key")
    return parts


def _read_quoted(text: str, index: int, origin: str, line: int, column: int) -> tuple[str, int]:
    quote = text[index]
    index += 1
    out: list[str] = []
    while index < len(text):
        char = text[index]
        if char == quote:
            return "".join(out), index + 1
        if char == "\\" and quote == '"':
            escaped, index = _read_escape(text, index, origin, line, column + index)
            out.append(escaped)
            continue
        out.append(char)
        index += 1
    return _fail(origin, line, column, "unterminated quoted string")


def _read_escape(text: str, index: int, origin: str, line: int, column: int) -> tuple[str, int]:
    if index + 1 >= len(text):
        _fail(origin, line, column, "unterminated escape")
    escape = text[index + 1]
    if escape in ESCAPES:
        return ESCAPES[escape], index + 2
    if escape in ("u", "U"):
        width = 4 if escape == "u" else 8
        digits = text[index + 2:index + 2 + width]
        if len(digits) == width and all(char in "0123456789abcdefABCDEF" for char in digits):
            return chr(int(digits, 16)), index + 2 + width
        _fail(origin, line, column, f"malformed \\{escape} escape")
    _fail(origin, line, column, f"unsupported escape \\{escape}")
    raise AssertionError


def _resolve(root: TomlTable, path: list[str], declared: set[int], origin: str, line: int, offset: int) -> TomlTable:
    container = root
    for name in path:
        entry = container.get(name)
        if entry is None:
            entry = TomlTable()
            container.entries.append((name, entry))
        if isinstance(entry, TomlArrayEntry):
            if not entry.items:
                _fail(origin, line, offset + 1, f"{name!r} is an empty array of tables")
            container = entry.items[-1]
        elif isinstance(entry, TomlTable):
            container = entry
        else:
            _fail(origin, line, offset + 1, f"{name!r} is already a value")
    return container


def _open_table(container: TomlTable, name: str, declared: set[int], origin: str, line: int, offset: int) -> TomlTable:
    entry = container.get(name)
    if entry is None:
        table = TomlTable()
        container.entries.append((name, table))
    elif isinstance(entry, TomlTable):
        if id(entry) in declared:
            _fail(origin, line, offset + 1, f"table {name!r} is declared twice")
        table = entry
    else:
        _fail(origin, line, offset + 1, f"{name!r} was already declared as an array of tables")
    declared.add(id(table))
    return table


def _open_array(container: TomlTable, name: str, origin: str, line: int, offset: int) -> TomlTable:
    entry = container.get(name)
    if entry is None:
        entry = TomlArrayEntry()
        container.entries.append((name, entry))
    if not isinstance(entry, TomlArrayEntry):
        _fail(origin, line, offset + 1, f"{name!r} was already declared as a table")
    table = TomlTable()
    entry.items.append(table)
    return table


def _split_assignment(stripped: str, origin: str, line: int, offset: int) -> tuple[str, str]:
    index = 0
    if stripped.startswith(('"', "'")):
        key, index = _read_quoted(stripped, 0, origin, line, offset + 1)
        while index < len(stripped) and stripped[index] != "=":
            index += 1
    else:
        while index < len(stripped) and stripped[index] != "=":
            index += 1
        key = stripped[:index].strip()
    if index >= len(stripped):
        _fail(origin, line, offset + 1, "expected '='")
    if not stripped.startswith(('"', "'")) and BARE_KEY_RE.fullmatch(key) is None:
        _fail(origin, line, offset + 1, f"unsupported key {key!r}")
    return key, stripped[index + 1:].strip()


def _parse_value(text: str, origin: str, line: int, column: int) -> TomlValue:
    if text.startswith('"""') or text.startswith("'''"):
        _fail(origin, line, column, "multi-line strings are unsupported")
    if text.startswith(('"', "'")):
        value, end = _read_quoted(text, 0, origin, line, column)
        if text[end:].strip():
            _fail(origin, line, column + end, "trailing text after the value")
        return TomlValue(raw=text[:end], value=value, line=line)
    if text.startswith("{"):
        _fail(origin, line, column, "inline tables are unsupported")
    if text.startswith("["):
        _fail(origin, line, column, "arrays are unsupported")
    if text in ("true", "false"):
        return TomlValue(raw=text, value=text == "true", line=line)
    if INTEGER_RE.fullmatch(text):
        return TomlValue(raw=text, value=int(text), line=line)
    if FLOAT_RE.fullmatch(text):
        return TomlValue(raw=text, value=float(text), line=line)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}.*", text):
        _fail(origin, line, column, "dates and times are unsupported")
    _fail(origin, line, column, f"unrecognised value {text!r}")
    raise AssertionError


def entries_of(entry: TomlEntry) -> TomlTable:
    """Narrow an entry to a table, for callers that already know the shape."""
    assert isinstance(entry, TomlTable)
    return entry
