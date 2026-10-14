"""Translate between the stock ``Mod\\mod.txt`` and the project file ``mod_setting.toml``.

``mod.txt`` is what the game loads; ``mod_setting.toml`` is the editor's form of it
(docs/project-layout.md section 4).  :func:`render` reads the stock file and :func:`emit`
writes it back, so a project can be edited in TOML and still reach the game.
"""

from pathlib import Path

from core import toml, xml
from core.errors import FfError
from core.schema import MOD_SETTING, schema_for
from core.toml import TomlArrayEntry, TomlTable, TomlValue

MOD_TXT = "mod.txt"


def source_path(project: Path) -> Path:
    """The stock settings file a project would render from."""
    return project / "Mod" / MOD_TXT


def render(text: str, origin: str) -> tuple[TomlTable, list[str]]:
    """Turn the text of a ``mod.txt`` into the ``mod_setting`` table of a project file."""
    document = xml.parse(text, origin)
    warnings = list(document.warnings)
    schema = schema_for(MOD_SETTING.name)
    table = TomlTable([(MOD_SETTING.name, _table(document.root, (MOD_SETTING.name,), schema, warnings))])
    return table, warnings


def _table(element, path: tuple[str, ...], schema, warnings: list[str]) -> TomlTable:
    """One element's children as a TOML table, typed by the ``mod_setting`` schema."""
    table = TomlTable()
    order: list[str] = []
    for child in element.children:
        if child.tag not in order:
            order.append(child.tag)
    for name in order:
        kids = [child for child in element.children if child.tag == name]
        keys = path + (name,)
        node = schema.lookup(keys) if schema is not None else None
        if node is None:
            raise FfError(f"{'/'.join(keys)}: not declared by the mod_setting schema")
        if node.shape == "array":
            table.entries.append((name, TomlArrayEntry(items=[_table(kid, keys, schema, warnings) for kid in kids])))
            continue
        if node.type == "list":
            values = [kid.value for kid in kids]
            raw = "[" + ", ".join(toml.quote_string(value) for value in values) + "]"
            table.entries.append((name, TomlValue(raw=raw, value=values, line=kids[0].line)))
            continue
        if kids[0].children:
            if len(kids) > 1:
                warnings.append(f"{'/'.join(keys)}: repeats, stored as an array")
                table.entries.append(
                    (name, TomlArrayEntry(items=[_table(kid, keys, schema, warnings) for kid in kids]))
                )
            else:
                table.entries.append((name, _table(kids[0], keys, schema, warnings)))
            continue
        if len(kids) > 1:
            raise FfError(f"{'/'.join(keys)}: a leaf repeats and the TOML form has no scalar array for it")
        value = kids[0].value
        table.entries.append((name, TomlValue(raw=_raw(node.type, value), value=_value(node.type, value), line=kids[0].line)))
    return table


def _raw(kind: str, text: str) -> str:
    if kind == "bool":
        return "true" if text == "yes" else "false"
    if kind in ("int", "float"):
        return text
    return toml.quote_string(text)


def _value(kind: str, text: str):
    if kind == "bool":
        return text == "yes"
    if kind == "int":
        return int(text)
    if kind == "float":
        return float(text)
    return text


# The element order of a mod.txt.  The schema sorts children for the TOML writer, which is
# not the order the game reads, so the two orders are kept apart (docs/toml-mapping.md
# section 4).
MOD_TXT_ORDER = (
    "name",
    "author",
    "years",
    "credits",
    "show_scenarios",
    "choose_unique_rifle_squad",
    "allow_vehicles",
    "allow_infantry",
    "allow_at_guns",
    "allow_artillery",
    "minimum_commonness",
    "minimum_commonness_to_upgrade",
    "text_colours",
    "nationality",
)

CHILD_ORDER = {
    "years": ("start", "end", "increment"),
    "credits": tuple(f"{kind}{index}" for kind in ("attack", "defend") for index in range(1, 5)),
    "text_colours": (
        "map_description",
        "custom_heading",
        "custom_option",
        "custom_unit_description",
        "game",
        "friend",
        "enemy",
    ),
    "flags": ("static", "animated"),
    "ranks": tuple(str(rank) for rank in range(1, 8)),
    "default_images": ("infantry", "tank_crew", "infantry_profile", "tank_crew_profile", "ranks"),
    "nationality": (
        "name",
        "surnames",
        "flags",
        "equipment",
        "voice",
        "units",
        "filename",
        "ranks",
        "default_images",
    ),
}

INDENT = "\t"

# A mod.txt puts a blank line before every element except the first two: the stock file has
# <name> and <author>, or <name> and <surnames>, next to each other.
ADJACENT = 2


def emit(table: TomlTable, *, newline: str = "\n") -> tuple[str, list[str]]:
    """Turn a ``mod_setting`` table back into the text of a ``mod.txt``.

    ``table`` is the inner table, as ``core.edit.root_table`` returns it.  Values are
    written as they are, with no XML escaping; a value carrying a character the stock form
    cannot hold literally is reported.

    The element order, the tab indentation and the blank lines are the shape the shipped
    ``mod.txt`` files use, so a file already in that shape round-trips byte for byte.
    ``render`` does not keep the layout of a file that was written differently, so such a
    file comes back in this shape (docs/cli.md section 4.7).
    """
    warnings: list[str] = []
    lines = ["<mod>"]
    _elements(table, MOD_TXT_ORDER, (MOD_SETTING.name,), 1, lines, warnings)
    lines.append("</mod>")
    return newline.join(lines) + newline, warnings


def _elements(table, order: tuple[str, ...], path: tuple[str, ...], depth: int, lines: list[str], warnings: list[str]) -> None:
    """One table's children as elements of a mod.txt, in the stock order.

    A parent that carries a nested element separates its children with blank lines; one
    whose children are all leaves, such as ``<years>`` or ``<flags>``, writes them next to
    each other, as the stock files do.
    """
    groups = _ordered(table, order, path, warnings)
    spaced = any(isinstance(value, (TomlTable, TomlArrayEntry)) for _, value in groups)
    for index, (name, value) in enumerate(groups):
        if spaced and index >= ADJACENT:
            lines.append("")
        _element(name, value, path + (name,), depth, lines, warnings)


def _ordered(table, order: tuple[str, ...], path: tuple[str, ...], warnings: list[str]) -> list[tuple[str, object]]:
    """The entries of one table, in the stock order, dropping what it has no element for."""
    found: dict[str, list] = {}
    for name, value in table.entries:
        found.setdefault(name, []).append(value)
    groups: list[tuple[str, object]] = []
    for name in order:
        for value in found.pop(name, []):
            groups.append((name, value))
    for name in sorted(found):
        warnings.append(f"{'/'.join(path + (name,))}: not an element of a mod.txt; left out")
    return groups


def _element(name: str, value, path: tuple[str, ...], depth: int, lines: list[str], warnings: list[str]) -> None:
    """One element, its repeats, or its table body."""
    pad = INDENT * depth
    if isinstance(value, TomlArrayEntry):
        for index, item in enumerate(value.items):
            if index:
                lines.append("")
            lines.append(f"{pad}<{name}>")
            _elements(item, CHILD_ORDER.get(name, ()), path, depth + 1, lines, warnings)
            lines.append(f"{pad}</{name}>")
        return
    if isinstance(value, TomlTable):
        lines.append(f"{pad}<{name}>")
        _elements(value, CHILD_ORDER.get(name, ()), path, depth + 1, lines, warnings)
        lines.append(f"{pad}</{name}>")
        return
    if isinstance(value.value, list):
        for item in value.value:
            lines.append(f"{pad}<{name}>{_text(item, path, warnings)}</{name}>")
        return
    lines.append(f"{pad}<{name}>{_text(value.value, path, warnings)}</{name}>")


def _text(value, path: tuple[str, ...], warnings: list[str]) -> str:
    """One value as the game writes it: yes/no for a boolean, the number, else the text."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    if "<" in text or "&" in text:
        warnings.append(f"{'/'.join(path)}: {text!r} carries < or &, which a mod.txt cannot hold literally")
    return text
