"""XML to TOML conversion and back, with the path-keyed schema deciding shape.

Leaf text is kept verbatim and a repeated table element becomes an array (docs/toml-mapping.md sections 2, 3).
"""

import re

from core.errors import SchemaError
from core.schema import Node, Schema, schema_for
from core.toml import TomlArrayEntry, TomlTable, TomlValue
from core.toml import quote_string
from core.xml import XmlDocument, XmlElement

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


def _grouped_children(element: XmlElement, node: Node | None = None) -> list[str]:
    """Return tags in source order: first appearance wins, same tag stays grouped.

    The schema no longer decides sibling order, because that reordered 1792 of
    1840 shipped files on export (docs/toml-mapping.md section 5).  Same-named
    siblings stay together, as the TOML mapping requires.
    """
    names: list[str] = []
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


def tree_to_xml(
    root: XmlElement,
    header: str = "",
    footer: str = "",
    newline: str = "\r\n",
    indent: str = INDENT,
) -> str:
    """Render a parsed tree back to stock XML, keeping the source layout.

    Used for stock entities: everything the reader recorded (blank lines,
    comments, indentation, inline branches, the file's own newlines) is written
    back verbatim, so an untouched entity round-trips byte for byte.  Elements
    without recorded layout (built from a TOML document) fall back to the
    canonical shape of :func:`toml_to_xml`.
    """
    parts: list[str] = [header]
    _render_tree(root, 0, parts, newline, indent)
    parts.append(footer)
    return "".join(parts)


def _render_tree(element: XmlElement, depth: int, parts: list[str], newline: str, indent: str) -> None:
    parts.append(element.prefix if element.prefix is not None else (newline + indent * depth if depth else ""))
    if element.self_closing and not element.children:
        parts.append(f"<{element.tag}/>")
        return
    if not element.children:
        parts.append(f"<{element.tag}>{element.text()}</{element.tag}>")
        return
    parts.append(f"<{element.tag}>")
    for child in element.children:
        _render_tree(child, depth + 1, parts, newline, indent)
    parts.append(element.suffix if element.suffix is not None else newline + indent * depth)
    parts.append(f"</{element.tag}>")
