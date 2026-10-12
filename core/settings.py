"""Render the stock ``Mod\\mod.txt`` into the project file ``mod_setting.toml``.

``mod.txt`` is what the game loads; ``mod_setting.toml`` is the editor's form of it
(docs/project-layout.md section 4).  The stock file is the source of truth, so the renderer
reads it and never writes back: the way to the game stays the packager's export.
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
