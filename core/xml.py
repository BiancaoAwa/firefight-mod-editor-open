"""XML document model plus the tolerant reader for the stock dialect.

Elements keep the surrounding disk text, so an unedited entity exports byte for byte (docs/toml-mapping.md).
"""

from dataclasses import dataclass, field
import re
from core.errors import XmlStructureError


@dataclass
class XmlElement:
    """One element plus the source layout that belongs to it.

    ``prefix`` is the raw text between the previous tag and this start tag
    (indentation, blank lines, comments), ``suffix`` is the raw text before
    this element's end tag and ``raw_value`` is that text when the element has
    no children.  ``None`` means "no source layout was recorded" and makes the
    writer fall back to the canonical shape; ``""`` means "the source had
    nothing here" and is written back as-is.
    """

    tag: str
    line: int
    value: str = ""
    children: list["XmlElement"] = field(default_factory=list)
    prefix: str | None = None
    suffix: str | None = None
    raw_value: str | None = None
    self_closing: bool = False
    raw_tag: str = ""  # the start tag as written when it carried attributes

    def by_tag(self, tag: str) -> list["XmlElement"]:
        """Return the direct children with this tag, in source order."""
        return [child for child in self.children if child.tag == tag]

    def text(self) -> str:
        """The leaf text: the source spelling when known, else the parsed value."""
        return self.value if self.raw_value is None else self.raw_value


@dataclass
class XmlDocument:
    """A parsed source file plus everything recovered-tolerant about it."""

    origin: str
    root: XmlElement
    source: str
    warnings: list[str] = field(default_factory=list)
    comments: int = 0
    header: str = ""
    footer: str = ""
    newline: str = "\r\n"
    indent: str = "\t"


def signature(element: XmlElement) -> tuple:
    """Canonical form: different names unordered, same-name blocks ordered.

    This is the equivalence predicate of docs/toml-mapping.md section 8.1, so
    indentation, blank lines and sibling order across different tags do not
    count as a difference.
    """
    groups: dict[str, list[XmlElement]] = {}
    for child in element.children:
        groups.setdefault(child.tag, []).append(child)
    parts = tuple((tag, tuple(signature(kid) for kid in kids)) for tag, kids in sorted(groups.items()))
    return element.tag, element.value, parts


NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*|[0-9]+")
COMMENT_PREFIX = " \t>"


def find_comment(line: str) -> int | None:
    """Index of a ``//`` comment start, or None.

    ``//`` only starts a comment at the start of a line or after whitespace or
    ``>``; every occurrence in the corpus satisfies this, so no value is
    truncated (docs/toml-mapping.md).
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
    warnings: list[str] = []
    root: XmlElement | None = None
    stack: list[XmlElement] = []
    layout: list[str] = []  # raw characters since the previous tag
    content: list[str] = []  # the same characters, comment-free and LF-only
    comments = 0
    attributes: set[str] = set()
    header = ""
    line = 1
    index = 0
    size = len(text)
    while index < size:
        if text[index] != "<":
            nxt = text.find("<", index)
            if nxt == -1:
                nxt = size
            line += text.count("\n", index, nxt)
            layout.append(text[index:nxt])
            kept, found = _cut_comments(text[index:nxt])
            comments += found
            content.append(kept)
            index = nxt
            continue
        start = index
        if text.startswith("<![CDATA[", start):
            end = text.find("]]>", start + 9)
            if end == -1:
                warnings.append(f"line {line}: unterminated CDATA kept as text")
                end = size - 3
            block = text[start:end + 3]
            line += block.count("\n")
            layout.append(block)
            content.append(text[start + 9:end])
            index = end + 3
            continue
        close = text.find(">", start + 1)
        if close == -1:
            warnings.append(f"line {line}: unterminated '<' kept as text")
            layout.append(text[start:])
            kept, found = _cut_comments(text[start:])
            comments += found
            content.append(kept)
            break
        open_line = line
        line += text.count("\n", start, close + 1)
        raw = text[start:close + 1]
        token = text[start + 1:close]
        index = close + 1
        gap = "".join(layout)
        kept = "".join(content)
        layout.clear()
        content.clear()
        _flush(kept, stack, open_line, warnings)
        if token.startswith("?") or token.startswith("!"):
            warnings.append(f"line {open_line}: skipped declaration <{token}>")
            layout.append(gap + raw)
            continue
        if token.startswith("/"):
            closed = _close_tag(token[1:].strip(), open_line, stack, warnings)
            if closed is not None:
                _keep_layout(closed, gap)
            continue
        self_closing = token.endswith("/")
        head = token[:-1] if self_closing else token
        name = head.split()[0] if head.split() else ""
        if NAME_RE.fullmatch(name) is None or not head.startswith(name):
            warnings.append(f"line {open_line}: skipped unreadable tag <{token}>")
            layout.append(gap + raw)
            continue
        element = XmlElement(
            tag=name,
            line=open_line,
            prefix=gap,
            self_closing=self_closing,
            raw_tag=head if head != name else "",
        )
        if element.raw_tag:
            attributes.add(name)
        if stack:
            stack[-1].children.append(element)
        elif root is None:
            # whatever stood before the root (a declaration, a comment) is the header
            root = element
            header = gap
            element.prefix = ""
        else:
            warnings.append(f"line {open_line}: second top-level element <{name}> kept under <{root.tag}>")
            root.children.append(element)
        if not self_closing:
            stack.append(element)
    kept = "".join(content)
    footer = "".join(layout)
    _flush(kept, stack, line, warnings)
    if stack:
        warnings.append(f"line {stack[-1].line}: unclosed element <{stack[-1].tag}>")
    if root is None:
        raise XmlStructureError(origin, 1, "no root element")
    if comments:
        warnings.append(f"{comments} comment line(s) removed")
    for name in sorted(attributes):
        warnings.append(f"<{name}>: attributes are kept as written and stay out of the TOML view")
    _warn_stray_text(root, warnings)
    return XmlDocument(
        origin=origin,
        root=root,
        source=text,
        warnings=warnings,
        comments=comments,
        header=header,
        footer=footer,
        newline="\r\n" if "\r\n" in text else "\n",
        indent=_detect_indent(root),
    )


def _cut_comments(chunk: str) -> tuple[str, int]:
    """Comment-free, LF-only text for one raw chunk (meaning side of the scan)."""
    chunk = chunk.replace("\r\n", "\n").replace("\r", "\n")
    lines = chunk.split("\n")
    count = 0
    for position, line in enumerate(lines):
        index = find_comment(line)
        if index is not None:
            count += 1
            lines[position] = line[:index]
    return "\n".join(lines), count


def _keep_layout(element: XmlElement, gap: str) -> None:
    """Remember what stood between the last child (or the start tag) and ``</tag>``."""
    if element.children:
        element.suffix = gap
    else:
        element.raw_value = gap


def _detect_indent(root: XmlElement) -> str:
    """The whitespace the source used to indent one level, else a tab."""
    for child in root.children:
        if child.prefix is None:
            continue
        tail = child.prefix.rsplit("\n", 1)[-1]
        if tail and set(tail) <= {"\t", " "}:
            return tail
    return "\t"


def _warn_stray_text(root: XmlElement, warnings: list[str]) -> None:
    """Warn about text in an element that also holds children; export drops it."""
    stack = [root]
    while stack:
        element = stack.pop()
        if element.children and element.value:
            warnings.append(f"line {element.line}: stray text {element.value!r} in <{element.tag}> is dropped on export")
        stack.extend(element.children)


def _close_tag(name: str, line: int, stack: list[XmlElement], warnings: list[str]) -> XmlElement | None:
    for depth in range(len(stack) - 1, -1, -1):
        if stack[depth].tag == name:
            if depth != len(stack) - 1:
                skipped = ", ".join(f"<{e.tag}>" for e in stack[depth + 1:])
                warnings.append(f"line {line}: </{name}> closed while {skipped} was open")
            closed = stack[depth]
            del stack[depth:]
            return closed
    warnings.append(f"line {line}: unmatched closing tag </{name}>")
    return None


def _flush(buffer: str, stack: list[XmlElement], line: int, warnings: list[str]) -> None:
    chunk = buffer.strip()
    if not chunk:
        return
    if not stack:
        warnings.append(f"line {line}: text outside the root element dropped")
        return
    element = stack[-1]
    element.value = f"{element.value} {chunk}".strip() if element.value else chunk
