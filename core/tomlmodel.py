"""Ordered TOML document model.

``entries`` is a list of pairs, never a dict, so key order survives a read and a
write; a dict view is offered for lookups (docs/m1-design.md section 3.4).
"""

from dataclasses import dataclass, field


@dataclass
class TomlValue:
    """A scalar: the literal as written plus the parsed value."""

    raw: str
    value: object
    line: int = 0


@dataclass
class TomlTable:
    """A table: ordered entries of scalars, sub-tables and arrays of tables."""

    entries: list[tuple[str, "TomlEntry"]] = field(default_factory=list)

    def get(self, key: str) -> "TomlEntry | None":
        """Return the entry stored under ``key``, or None."""
        for name, entry in self.entries:
            if name == key:
                return entry
        return None

    def view(self) -> dict[str, "TomlEntry"]:
        """Return a dict view; only valid while no duplicate keys exist."""
        return dict(self.entries)


@dataclass
class TomlArrayEntry:
    """An array of tables; the only array form this editor writes."""

    items: list[TomlTable] = field(default_factory=list)


TomlEntry = TomlValue | TomlTable | TomlArrayEntry
