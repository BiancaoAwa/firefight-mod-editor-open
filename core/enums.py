"""Enumeration tables for the fields an edit may set (docs/cli.md section 4).

Values come from ``enums_ext.txt``: the copy next to the project, else the copy shipped with
the editor.  A field whose category has no table in the file is accepted without an enum
check, so an incomplete table never blocks an edit.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

ENUM_FILE = "enums_ext.txt"

# One rule per checked field: (root tag or "*", path tail, categories).  "*" matches one
# segment; numeric index segments are dropped before matching.  Fields absent from this table
# are not enum-checked.  Categories are the left-hand names of enums_ext.txt.
RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("squad", ("description", "type"), ("type", "vehicle_type")),
    ("squad", ("description", "nationality"), ("nationality",)),
    ("squad", ("description", "quality"), ("quality",)),
    ("squad", ("description", "language"), ("lang",)),
    ("weapon", ("type",), ("weapon_class",)),
    ("weapon", ("usage", "countries"), ("country",)),
    ("*", ("job",), ("job",)),
    ("*", ("flavour",), ("flavour",)),
    ("*", ("era",), ("era",)),
    ("*", ("guided",), ("guided",)),
    ("*", ("period",), ("period",)),
    ("*", ("sound_shoot",), ("sound",)),
    ("*", ("reliability",), ("reliability",)),
    ("*", ("steering",), ("steering",)),
    ("*", ("mount",), ("mount",)),
)

# Categories whose value is a list separated by this character rather than a single token.
LIST_SEPARATOR = {"country": "|"}


@dataclass(frozen=True)
class Enums:
    """The loaded table plus where it came from."""

    values: dict[str, frozenset[str]] = field(default_factory=dict)
    source: str = ""

    def table_size(self, categories: tuple[str, ...]) -> int:
        """Number of values known for a field, across its categories."""
        return sum(len(self.values.get(category, ())) for category in categories)

    def accepts(self, categories: tuple[str, ...], value: str) -> bool:
        """Whether a value is in one of the field's tables; False when no table exists."""
        return any(value in self.values.get(category, ()) for category in categories)

    def checked(self, categories: tuple[str, ...]) -> bool:
        """Whether at least one category of the field has a non-empty table."""
        return any(self.values.get(category) for category in categories)


def categories_of(root_tag: str, path: tuple[str, ...]) -> tuple[str, ...]:
    """Enum categories declared for one field path, empty when the field is not checked."""
    segments = tuple(part for part in path if not part.isdigit())
    for root_pattern, tail, categories in RULES:
        if root_pattern != "*" and root_pattern != root_tag:
            continue
        if len(tail) > len(segments):
            continue
        if all(pattern == "*" or pattern == actual for pattern, actual in zip(tail, segments[-len(tail):])):
            return categories
    return ()


def split_value(categories: tuple[str, ...], value: str) -> tuple[str, ...]:
    """The parts of a value that each have to be a member of the table."""
    separator = next((LIST_SEPARATOR[name] for name in categories if name in LIST_SEPARATOR), "")
    if not separator:
        return (value,)
    return tuple(part.strip() for part in value.split(separator) if part.strip())


def load_enums(project_root: Path | None = None) -> Enums:
    """Load enums_ext.txt for a project, else the copy shipped with the editor."""
    values: dict[str, set[str]] = {}
    used = ""
    for path in _candidates(project_root):
        if not path.is_file():
            continue
        found = _read(path, values)
        if found and not used:
            used = path.name
        if used:
            break
    return Enums(values={name: frozenset(table) for name, table in values.items()}, source=used)


def _candidates(project_root: Path | None) -> list[Path]:
    """Project copies first, then the copy that travels with the editor."""
    found: list[Path] = []
    if project_root is not None:
        found.append(project_root / ENUM_FILE)
        found.append(project_root / "Data" / ENUM_FILE)
    shipped = Path(__file__).resolve().parents[1] / "tools" / "FirefightModPackager" / ENUM_FILE
    found.append(shipped)
    return found


def _read(path: Path, values: dict[str, set[str]]) -> int:
    """Add every ``category:value`` line of one table; returns the count added."""
    added = 0
    with open(path, encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            category, _, value = line.partition(":")
            value = value.split("#")[0].strip()
            if not value:
                continue
            values.setdefault(category.strip().lower(), set()).add(value)
            added += 1
    return added
