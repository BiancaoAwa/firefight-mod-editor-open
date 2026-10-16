"""Row operations on the plain-text tables a project declares in its settings.

A list file is one entry per line and ``//`` starts a comment; which files those are is decided
by the project's own settings and not here (core/cli/commands.py, ``is_list_file``).  This module
only turns one row operation into the whole-document text.  The write itself goes through
``core.edit``, so it is planned, re-checked, journalled and undoable like every other change
(docs/web.md section 2.2).
"""

from pathlib import Path

from core import textio

OPS = ("set", "add", "delete")


def read_rows(path: Path) -> tuple[list[str], str, str]:
    """The physical lines with their own endings, the encoding, and the line ending in use.

    A byte-order mark is kept: the file is then pinned to UTF-8, because the mark itself says
    so and cp1252 could not carry it back.
    """
    data = path.read_bytes()
    body = data[len(textio.BOM):] if data.startswith(textio.BOM) else data
    text, encoding = textio.decode_source(body, str(path))
    if data.startswith(textio.BOM):
        encoding = "utf-8"
    return text.splitlines(keepends=True), encoding, ("\r\n" if b"\r\n" in body else "\n")


def ending(line: str) -> str:
    """The line ending a physical line carries, if any."""
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[-1]
    return ""


def content(line: str) -> str:
    """A physical line without its ending."""
    return line[: len(line) - len(ending(line))]


def encode(lines: list[str], encoding: str, bom: bool) -> str:
    """The text to write back: the lines as they are, with the mark in front when it was there."""
    return ("\ufeff" if bom else "") + "".join(lines)


def row_change(lines: list[str], op: str, line: int, value: str, newline: str) -> tuple[list[str], str, str]:
    """Apply one row operation to the lines; returns (new lines, before, after).

    ``line`` is 1-based and counts every physical line, including comments and blanks, which is
    the number the page prints.  A change keeps the ending the row already had.
    """
    if op not in OPS:
        raise ValueError(f"op is one of {', '.join(OPS)}, not {op!r}")
    lines = list(lines)
    if op == "add":
        if lines and ending(lines[-1]) == "":
            lines[-1] = lines[-1] + newline
        lines.append(value + newline)
        return lines, "", value
    if line < 1 or line > len(lines):
        raise ValueError(f"line {line} is not in 1..{len(lines)}")
    old = content(lines[line - 1])
    if op == "delete":
        del lines[line - 1]
        return lines, old, ""
    lines[line - 1] = value + ending(lines[line - 1])
    return lines, old, value


def rows(lines: list[str], cap: int) -> list[dict]:
    """The rows a page draws: number, text, and whether the row is a comment or blank."""
    drawn = []
    for number, raw in enumerate(lines, start=1):
        if number > cap:
            break
        text = content(raw)
        stripped = text.strip()
        drawn.append(
            {
                "line": number,
                "text": text,
                "comment": stripped.startswith("//"),
                "blank": stripped == "",
            }
        )
    return drawn
