"""XML document model.

The reader keeps the original text so later milestones can test "was this
entity edited" (docs/m1-design.md section 3.3).
"""

from dataclasses import dataclass, field


@dataclass
class XmlElement:
    """One element: its tag, its text value, its children and its source line."""

    tag: str
    line: int
    value: str = ""
    children: list["XmlElement"] = field(default_factory=list)

    def by_tag(self, tag: str) -> list["XmlElement"]:
        """Return the direct children with this tag, in source order."""
        return [child for child in self.children if child.tag == tag]


@dataclass
class XmlDocument:
    """A parsed source file plus everything recovered-tolerant about it."""

    origin: str
    root: XmlElement
    source: str
    warnings: list[str] = field(default_factory=list)
    comments: int = 0


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
