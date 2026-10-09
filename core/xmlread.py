"""Tolerant XML reader for the stock dialect.

A scanner rather than a grammar: no attributes, no entities (``&`` is an
ordinary character), ``//`` comments, ragged nesting.  Only input with no
recoverable root raises; everything else becomes a warning on the document
(docs/m1-design.md section 3.3).
"""

import re

from core.errors import XmlStructureError
from core.xmlmodel import XmlDocument, XmlElement

NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*|[0-9]+")
COMMENT_PREFIX = " \t>"


def find_comment(line: str) -> int | None:
    """Index of a ``//`` comment start, or None.

    ``//`` only starts a comment at the start of a line or after whitespace or
    ``>``; every occurrence in the corpus satisfies this, so no value is
    truncated (docs/m1-design.md section 3.3 rule 3).
    """
    start = 0
    while True:
        index = line.find("//", start)
        if index == -1:
            return None
        if index == 0 or line[index - 1] in COMMENT_PREFIX:
            return index
        start = index + 1


def strip_comments(text: str) -> tuple[str, int]:
    """Remove ``//`` comments line by line and count them."""
    lines = []
    count = 0
    for line in text.split("\n"):
        index = find_comment(line)
        if index is None:
            lines.append(line)
        else:
            count += 1
            lines.append(line[:index])
    return "\n".join(lines), count


def parse(text: str, origin: str) -> XmlDocument:
    """Parse source text into a document; never raises on ragged structure."""
    stripped, comments = strip_comments(text)
    warnings: list[str] = []
    root: XmlElement | None = None
    stack: list[XmlElement] = []
    buffer: list[str] = []
    line = 1
    index = 0
    size = len(stripped)
    while index < size:
        if stripped[index] != "<":
            nxt = stripped.find("<", index)
            if nxt == -1:
                nxt = size
            line += stripped.count("\n", index, nxt)
            buffer.append(stripped[index:nxt])
            index = nxt
            continue
        close = stripped.find(">", index + 1)
        if close == -1:
            warnings.append(f"line {line}: unterminated '<' kept as text")
            buffer.append(stripped[index:])
            break
        open_line = line
        line += stripped.count("\n", index, close + 1)
        token = stripped[index + 1:close]
        index = close + 1
        _flush(buffer, stack, open_line, warnings)
        if token.startswith("?") or token.startswith("!"):
            warnings.append(f"line {open_line}: skipped declaration <{token}>")
            continue
        if token.startswith("/"):
            _close_tag(token[1:].strip(), open_line, stack, warnings)
            continue
        self_closing = token.endswith("/")
        name = token[:-1].strip() if self_closing else token
        if NAME_RE.fullmatch(name) is None:
            warnings.append(f"line {open_line}: skipped unreadable tag <{token}>")
            continue
        element = XmlElement(tag=name, line=open_line)
        if stack:
            stack[-1].children.append(element)
        elif root is None:
            root = element
        else:
            warnings.append(f"line {open_line}: second top-level element <{name}> kept under <{root.tag}>")
            root.children.append(element)
        if not self_closing:
            stack.append(element)
    _flush(buffer, stack, line, warnings)
    if stack:
        warnings.append(f"line {stack[-1].line}: unclosed element <{stack[-1].tag}>")
    if root is None:
        raise XmlStructureError(origin, 1, "no root element")
    if comments:
        warnings.append(f"{comments} comment line(s) removed")
    _warn_stray_text(root, warnings)
    return XmlDocument(origin=origin, root=root, source=text, warnings=warnings, comments=comments)


def _warn_stray_text(root: XmlElement, warnings: list[str]) -> None:
    """Warn about text in an element that also holds children; export drops it."""
    stack = [root]
    while stack:
        element = stack.pop()
        if element.children and element.value:
            warnings.append(f"line {element.line}: stray text {element.value!r} in <{element.tag}> is dropped on export")
        stack.extend(element.children)


def _close_tag(name: str, line: int, stack: list[XmlElement], warnings: list[str]) -> None:
    for depth in range(len(stack) - 1, -1, -1):
        if stack[depth].tag == name:
            if depth != len(stack) - 1:
                skipped = ", ".join(f"<{e.tag}>" for e in stack[depth + 1:])
                warnings.append(f"line {line}: </{name}> closed while {skipped} was open")
            del stack[depth:]
            return
    warnings.append(f"line {line}: unmatched closing tag </{name}>")


def _flush(buffer: list[str], stack: list[XmlElement], line: int, warnings: list[str]) -> None:
    if not buffer:
        return
    chunk = "".join(buffer).strip()
    buffer.clear()
    if not chunk:
        return
    if not stack:
        warnings.append(f"line {line}: text outside the root element dropped")
        return
    element = stack[-1]
    element.value = f"{element.value} {chunk}".strip() if element.value else chunk
