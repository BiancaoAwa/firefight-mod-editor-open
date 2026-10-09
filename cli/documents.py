"""Uniform access to one entity file, in either storage format.

A document always carries both views: the TOML table and the XML tree, converted
from whichever format is on disk.  Commands therefore never branch on format,
except where the caller asked for the raw text.
"""

from dataclasses import dataclass
from pathlib import Path

from core import convert, textio, tomlread, tomlwrite, xmlread
from core.schema import schema_for
from core.tomlmodel import TomlArrayEntry, TomlEntry, TomlTable, TomlValue
from core.xmlmodel import XmlElement

SUFFIX_TOML = ".toml"
SUFFIX_XML = ".txt"
CATEGORY_BY_FOLDER = {
    "Infantry": "infantry",
    "Vehicles": "vehicle",
    "Weapons": "weapon",
    "AT Guns": "at_gun",
    "Aircraft": "aircraft",
}


@dataclass
class Document:
    """One entity file with both of its views."""

    path: Path
    relative: str
    format: str
    text: str
    table: TomlTable
    root: XmlElement
    warnings: tuple[str, ...] = ()
    encoding: str = textio.CODE_PAGE

    @property
    def category(self) -> str:
        """Editor category of this entity, from its folder or file name."""
        return category_of_path(self.relative)

    @property
    def root_tag(self) -> str:
        return self.root.tag

    def toml_text(self) -> str:
        """The TOML rendering of this document."""
        return tomlwrite.render(self.table)

    def xml_text(self, warnings: list[str] | None = None) -> str:
        """The stock XML rendering of this document."""
        return convert.toml_to_xml(
            self.table, schema_for(self.root.tag), origin=str(self.path), warnings=warnings
        )


def category_of_path(relative: str) -> str:
    """Editor category of a scope-relative entity path, without reading the file."""
    parts = relative.replace("\\", "/").split("/")
    name = parts[-1]
    if name.startswith("equipment_"):
        return "equipment"
    if name.startswith("surnames_"):
        return "surnames"
    folder = parts[1] if len(parts) >= 3 and parts[0] == "Data" else None
    if folder in ("Surnames",):
        return "surnames"
    if folder is not None and folder.startswith("equipment"):
        return "equipment"
    if folder in CATEGORY_BY_FOLDER:
        return CATEGORY_BY_FOLDER[folder]
    return "other"


def load_document(path: Path, relative: str | None = None) -> Document:
    """Read one entity file and build both views; raises the core errors as is."""
    warnings: list[str] = []
    source = textio.read_source(path, warnings)
    if path.suffix.lower() == SUFFIX_TOML:
        table = tomlread.parse(source.text, str(path))
        root_tag = table.entries[0][0] if table.entries else ""
        xml_text = convert.toml_to_xml(table, schema_for(root_tag), origin=str(path), warnings=warnings)
        reparsed = xmlread.parse(xml_text, str(path))
        root = reparsed.root
        warnings.extend(reparsed.warnings)
        storage = "toml"
    else:
        parsed = xmlread.parse(source.text, str(path))
        root = parsed.root
        table = convert.xml_to_toml(parsed)
        warnings.extend(parsed.warnings)
        storage = "xml"
    return Document(
        path=path,
        relative=relative if relative is not None else path.name,
        format=storage,
        text=source.text,
        table=table,
        root=root,
        warnings=tuple(warnings),
        encoding=source.encoding,
    )


def walk(root: XmlElement) -> list[tuple[tuple[str, ...], XmlElement]]:
    """Every element with its path from the document root, in document order."""
    found: list[tuple[tuple[str, ...], XmlElement]] = []
    _walk(root, (), found)
    return found


def _walk(element: XmlElement, path: tuple[str, ...], found: list[tuple[tuple[str, ...], XmlElement]]) -> None:
    here = path + (element.tag,)
    found.append((here, element))
    for child in element.children:
        _walk(child, here, found)


def select(root: XmlElement, doc_path: tuple[str, ...]) -> list[tuple[tuple[str, ...], XmlElement]]:
    """Elements matching a document path; repeats return every match."""
    if not doc_path:
        return [(root.tag, root)]
    matches: list[tuple[tuple[str, ...], XmlElement]] = []
    for path, element in walk(root):
        if len(path) == len(doc_path) + 1 and path[1:] == doc_path:
            matches.append((path, element))
    return matches


def select_table(table: TomlTable, keys: tuple[str, ...]) -> list[TomlEntry]:
    """TOML entries matching a key path; arrays contribute each of their items."""
    current: list[TomlEntry] = [table]
    for key in keys:
        following: list[TomlEntry] = []
        for entry in current:
            if isinstance(entry, TomlArrayEntry):
                for item in entry.items:
                    following.extend(_entries(item, key))
            elif isinstance(entry, TomlTable):
                following.extend(_entries(entry, key))
        current = following
    return current


def _entries(table: TomlTable, key: str) -> list[TomlEntry]:
    return [entry for name, entry in table.entries if name == key]


def flatten(table: TomlTable, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], TomlValue]]:
    """Every scalar of a TOML document with its key path."""
    found: list[tuple[tuple[str, ...], TomlValue]] = []
    for name, entry in table.entries:
        here = prefix + (name,)
        if isinstance(entry, TomlValue):
            found.append((here, entry))
        elif isinstance(entry, TomlTable):
            found.extend(flatten(entry, here))
        else:
            for index, item in enumerate(entry.items):
                found.extend(flatten(item, here + (str(index),)))
    return found


def element_value(element: XmlElement) -> str | None:
    """Leaf text of an element, or None when it is a branch."""
    return element.value if not element.children else None
