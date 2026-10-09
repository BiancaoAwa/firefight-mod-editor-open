"""XML ↔ TOML conversion.

Shape comes from the path-keyed schema, never from a single file's data, so a
field cannot change shape between files (docs/toml-mapping.md section 2).  One
deliberate exception: a table element that repeats in one parent instance is
stored as an array with a warning, because shipped mods do this.  Leaf text is
kept verbatim next to its parsed value, so an export never rewrites a decimal
(docs/toml-mapping.md section 3).
"""

import re

from core.errors import SchemaError
from core.schema import Node, Schema, schema_for
from core.tomlmodel import TomlArrayEntry, TomlTable, TomlValue
from core.tomlwrite import quote_string
from core.xmlmodel import XmlDocument, XmlElement

INTEGER_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
INDENT = "\t"


def xml_to_toml(doc: XmlDocument, schema: Schema | None = None) -> TomlTable:
    """Convert a parsed document into a TOML document (root tag as a table)."""
    if schema is None:
        schema = schema_for(doc.root.tag)
    node = schema.root if schema is not None else None
    root = TomlTable()
    root.entries.append((doc.root.tag, _element_table(doc.root, node, (doc.root.tag,), doc.warnings)))
    return root


def toml_to_xml(table: TomlTable, schema: Schema | None = None, origin: str = "<export>", warnings: list[str] | None = None) -> str:
    """Render a TOML document back to stock-standard XML (tabs, CRLF)."""
    if len(table.entries) != 1 or not isinstance(table.entries[0][1], TomlTable):
        raise SchemaError((), f"{origin}: expected exactly one top-level table")
    tag, body = table.entries[0]
    if not isinstance(body, TomlTable):
        raise SchemaError((tag,), "top-level entry is not a table")
    if schema is None:
        schema = schema_for(tag)
    node = schema.root if schema is not None else None
    sink = warnings if warnings is not None else []
    element = _table_element(tag, body, node, (tag,), sink)
    lines: list[str] = []
    _render(element, 0, lines)
    return "\r\n".join(lines) + "\r\n"


def _child_node(node: Node | None, name: str) -> Node | None:
    if node is None:
        return None
    wildcard: Node | None = None
    for child in node.children:
        if child.name == name:
            return child
        if child.name == "*":
            wildcard = child
    return wildcard


def _grouped_children(element: XmlElement, node: Node | None) -> list[str]:
    """Return tags in canonical order: schema order first, then the rest."""
    counts: dict[str, int] = {}
    for child in element.children:
        counts[child.tag] = counts.get(child.tag, 0) + 1
    names: list[str] = []
    if node is not None:
        for child_node in node.children:
            if child_node.name != "*" and child_node.name in counts:
                names.append(child_node.name)
    for child in element.children:
        if child.tag not in names:
            names.append(child.tag)
    return names


def _element_table(element: XmlElement, node: Node | None, path: tuple[str, ...], warnings: list[str]) -> TomlTable:
    table = TomlTable()
    counts: dict[str, int] = {}
    for child in element.children:
        counts[child.tag] = counts.get(child.tag, 0) + 1
    for name in _grouped_children(element, node):
        count = counts[name]
        child_path = path + (name,)
        child_node = _child_node(node, name)
        kids = [child for child in element.children if child.tag == name]
        shape = child_node.shape if child_node is not None else None
        has_children = any(kid.children for kid in kids)
        if shape is None:
            shape = "table" if has_children else "leaf"
            if count > 1 and not has_children:
                raise SchemaError(child_path, "unknown leaf element repeats; M1 has no scalar arrays")
            warnings.append(f"{'/'.join(child_path)}: unknown element, kept as {shape}")
        if shape == "leaf":
            if count > 1:
                raise SchemaError(child_path, f"leaf element occurs {count} times in one parent instance")
            table.entries.append((name, _leaf_value(kids[0], child_node, child_path, warnings)))
        elif shape == "array":
            items = [_element_table(kid, child_node, child_path, warnings) for kid in kids]
            table.entries.append((name, TomlArrayEntry(items=items)))
        else:
            if count > 1:
                warnings.append(f"{'/'.join(child_path)}: table repeats {count} times, stored as an array")
                items = [_element_table(kid, child_node, child_path, warnings) for kid in kids]
                table.entries.append((name, TomlArrayEntry(items=items)))
                continue
            table.entries.append((name, _element_table(kids[0], child_node, child_path, warnings)))
    return table


def _leaf_value(element: XmlElement, node: Node | None, path: tuple[str, ...], warnings: list[str]) -> TomlValue:
    text = element.value
    kind = node.type if node is not None else "auto"
    if kind == "bool":
        return TomlValue(raw="true" if text == "yes" else "false", value=text == "yes", line=element.line)
    if kind == "str":
        return TomlValue(raw=quote_string(text), value=text, line=element.line)
    if kind == "int":
        return TomlValue(raw=text, value=int(text), line=element.line)
    if kind == "float":
        return TomlValue(raw=text, value=float(text), line=element.line)
    if INTEGER_RE.match(text):
        return TomlValue(raw=text, value=int(text), line=element.line)
    if FLOAT_RE.match(text):
        return TomlValue(raw=text, value=float(text), line=element.line)
    if text in ("yes", "no"):
        return TomlValue(raw="true" if text == "yes" else "false", value=text == "yes", line=element.line)
    return TomlValue(raw=quote_string(text), value=text, line=element.line)


def _table_element(tag: str, table: TomlTable, node: Node | None, path: tuple[str, ...], warnings: list[str]) -> XmlElement:
    element = XmlElement(tag=tag, line=0)
    for name, entry in table.entries:
        child_path = path + (name,)
        child_node = _child_node(node, name)
        if isinstance(entry, TomlValue):
            element.children.append(XmlElement(tag=name, line=0, value=_leaf_text(entry)))
        elif isinstance(entry, TomlArrayEntry):
            for item in entry.items:
                element.children.append(_table_element(name, item, child_node, child_path, warnings))
        else:
            element.children.append(_table_element(name, entry, child_node, child_path, warnings))
    return element


def _leaf_text(value: TomlValue) -> str:
    if isinstance(value.value, bool):
        return "yes" if value.value else "no"
    if isinstance(value.value, str):
        return value.value
    return value.raw


def _render(element: XmlElement, depth: int, lines: list[str]) -> None:
    prefix = INDENT * depth
    if not element.children:
        lines.append(f"{prefix}<{element.tag}>{element.value}</{element.tag}>")
        return
    lines.append(f"{prefix}<{element.tag}>")
    for child in element.children:
        _render(child, depth + 1, lines)
    lines.append(f"{prefix}</{element.tag}>")
