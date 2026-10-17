"""Commands over one scope: read-only queries, the writing commands and ``export``.

Each command returns a JSON payload and its text rendering; ``set`` changes one field of one
project document, ``log``, ``undo`` and ``redo`` read and revert the event log, ``index``
builds the cross-reference tables under ``EditorCache/``, and ``export`` writes XML under ``to=``
(docs/cli.md).
"""

import difflib
import platform
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core import __version__ as core_version
from core import convert, index as index_core, journal, refs as refs_core, roster as roster_core, textio, toml, xml
from core.errors import FfError, SchemaError, XmlStructureError
from core.schema import PROJECT_SCHEMAS, SCHEMAS, schema_for
from core.toml import TomlArrayEntry, TomlEntry, TomlTable, TomlValue
from core.xml import XmlElement

from core.cli.scope import DATA_FOLDER, MOD_FOLDER, PROJECT_FILE, SETTING_FILE, Scope, UsageError, entity_files, resolve_scope


SUFFIX_TOML = ".toml"
SUFFIX_XML = ".txt"
CATEGORY_BY_FOLDER = {
    "Infantry": "infantry",
    "Vehicles": "vehicle",
    "Weapons": "weapon",
    "AT Guns": "at_gun",
    "Aircraft": "aircraft",
}

# Only units are named by a roster; a weapon or an engine sound is pulled in by the document
# that uses it, so counting them as unlisted units would report every one of them as an orphan.
ROSTER_CATEGORIES = ("infantry", "vehicle", "at_gun", "aircraft")


def unit_folders() -> tuple[str, ...]:
    """The ``Data/`` folders a roster entry can name, in the order the map declares them."""
    return tuple(
        folder for folder, category in CATEGORY_BY_FOLDER.items() if category in ROSTER_CATEGORIES
    )


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
    header: str = ""
    footer: str = ""
    newline: str = "\r\n"
    indent: str = "\t"

    @property
    def category(self) -> str:
        """Editor category of this entity, from its folder or file name."""
        return category_of_path(self.relative)

    @property
    def root_tag(self) -> str:
        return self.root.tag

    def toml_text(self) -> str:
        """The TOML rendering of this document."""
        return toml.render(self.table)

    def xml_text(self, warnings: list[str] | None = None) -> str:
        """The stock XML rendering of this document.

        A stock file is written back with the layout the reader captured, so an
        untouched entity is byte-identical to what is on disk; a document that
        only exists as TOML is rendered canonically (tabs, CRLF).
        """
        if self.format == "xml":
            return convert.tree_to_xml(self.root, self.header, self.footer, self.newline, self.indent)
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
    return document_from_source(path, relative if relative is not None else path.name, source, warnings)


def document_from_source(
    path: Path, relative: str, source: textio.SourceText, warnings: list[str] | None = None
) -> Document:
    """Build both views from text that is already decoded, without a disk read.

    ``batch`` uses this to carry a document forward from the text an earlier entry
    would leave behind (docs/cli.md section 4.15).
    """
    warnings = warnings if warnings is not None else []
    if path.suffix.lower() == SUFFIX_TOML:
        table = toml.parse(source.text, str(path))
        root_tag = table.entries[0][0] if table.entries else ""
        xml_text = convert.toml_to_xml(table, schema_for(root_tag), origin=str(path), warnings=warnings)
        reparsed = xml.parse(xml_text, str(path))
        root = reparsed.root
        warnings.extend(reparsed.warnings)
        storage = "toml"
        layout = reparsed
    else:
        parsed = xml.parse(source.raw, str(path))
        root = parsed.root
        table = convert.xml_to_toml(parsed)
        warnings.extend(parsed.warnings)
        storage = "xml"
        layout = parsed
    return Document(
        path=path,
        relative=relative,
        format=storage,
        text=source.text,
        table=table,
        root=root,
        warnings=tuple(warnings),
        encoding=source.encoding,
        header=layout.header,
        footer=layout.footer,
        newline=layout.newline,
        indent=layout.indent,
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


VERSION = core_version
CATEGORIES = ("infantry", "vehicle", "weapon", "at_gun", "aircraft", "equipment", "surnames", "other")
DEFAULT_LIMIT = 200
LOG_ROWS = 20
CHECK_SAMPLES = 20
# The two trees a mod carries beside Data/; `convert assets=1` copies them as they are.
ASSET_FOLDERS = ("Images", "Sounds")


@dataclass
class Context:
    """One resolved invocation."""

    scope: Scope
    selector: str
    doc_path: tuple[str, ...]
    options: dict[str, str]
    cwd: Path


@dataclass
class Result:
    """Command output: machine payload, human text, exit code."""

    payload: dict
    text: str
    code: int = 0


def command_names() -> tuple[str, ...]:
    """Canonical command names, sorted for help output."""
    return tuple(sorted({ALIASES.get(name, name) for name in COMMANDS}))


def run_command(name: str, ctx: Context) -> Result:
    """Look up a command (accepting aliases) and run it."""
    canonical = ALIASES.get(name, name)
    handler = COMMANDS.get(canonical)
    if handler is None:
        raise UsageError(f"unknown command {name!r}; try 'help'")
    return handler(ctx)


def row_limit(ctx: Context, default: int = DEFAULT_LIMIT) -> int | None:
    """How many rows a command prints, from ``limit=``; ``None`` means every row.

    Every command that enumerates rows honours the option and keeps its own
    default, so the text of a small query is not padded and the text of a large
    one stays short; ``limit=0`` asks for all rows (docs/cli.md section 4).
    Commands that print aggregates rather than rows ignore it.
    """
    raw = ctx.options.get("limit")
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise UsageError(f"limit= needs a whole number, not {raw!r}") from None
    if value < 0:
        raise UsageError(f"limit= cannot be negative: {raw!r}")
    return None if value == 0 else value


def tally(shown: int, total: int) -> str:
    """``7 of 200`` when rows were capped, else ``200``."""
    return f"{shown} of {total}" if shown != total else str(total)


def write_actor(ctx: Context) -> str:
    """Who is recording a change: the command line, or the MCP server that set ``actor``.

    ``core/mcp/tools.py`` sets ``actor=mcp`` on a writing call, so the log names the face that
    made the change (docs/project-layout.md section 8).
    """
    return ctx.options.get("actor") or "cli"


# --- shared helpers ---------------------------------------------------------


def targets(ctx: Context) -> list[Path]:
    """Entity files this invocation selects."""
    selector = ctx.selector
    if selector in ("", "all") or selector in CATEGORIES or "type" in ctx.options:
        return entity_files(ctx.scope)
    return entity_files(ctx.scope, selector)


def category_filter(ctx: Context) -> str | None:
    """Category named by the selector or ``type=``, if any."""
    if ctx.selector in CATEGORIES:
        return ctx.selector
    return ctx.options.get("type")


def filter_category(files: list[Path], ctx: Context, scope: Scope) -> list[Path]:
    """Keep only the files of the requested category."""
    wanted = category_filter(ctx)
    if wanted is None:
        return files
    return [path for path in files if category_of_path(relative_of(scope, path)) == wanted]


def relative_of(scope: Scope, path: Path) -> str:
    """Scope-relative POSIX path of a file; project files are relative to the project."""
    for base in (scope.root, scope.project):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def is_entity(relative: str) -> bool:
    """Whether a file is an entity document; equipment and surname lists are not."""
    return category_of_path(relative) not in ("equipment", "surnames")


def is_plain_text(path: Path) -> bool:
    """Whether a .txt file carries no XML root, i.e. it is a plain-text data file.

    The format keeps some tables as plain text: ``equipment_*`` and ``surnames_*``
    are named as lists, and the project's ``mod.txt`` names the rest, so this is
    the content rule ``is_list_file`` falls back on (docs/cli.md section 4.3).  A
    file that cannot be decoded counts as a document, so the caller still reports it.
    """
    if path.suffix.lower() != ".txt":
        return False
    try:
        xml.parse(textio.read_source(path).text, str(path))
    except XmlStructureError:
        return True
    except FfError:
        return False
    return False


LIST_KEYS = ("equipment", "surnames")


def declared_lists(scope: Scope) -> set[str]:
    """The plain-text table names the project's settings declare.

    ``<equipment>`` and ``<surnames>`` in the project's ``mod.txt`` name the
    tables the game keeps as text; a project that carries only ``ModSetting.toml``
    declares the same names there.  A scope that declares neither has no list of its
    own and the name conventions decide alone (docs/cli.md section 4.3).
    """
    from core import settings

    names: set[str] = set()
    table: toml.TomlTable | None = None
    stock = scope.root / settings.MOD_TXT
    project_file = scope.project / SETTING_FILE
    try:
        if stock.is_file():
            source = textio.read_source(stock)
            table, _ = settings.render(source.text, str(stock))
        elif project_file.is_file():
            source = textio.read_source(project_file)
            table = toml.parse(source.text, str(project_file))
    except (FfError, OSError):
        return set()
    stack: list[toml.TomlEntry] = [table]
    while stack:
        entry = stack.pop()
        if isinstance(entry, toml.TomlTable):
            for key, child in entry.entries:
                if key in LIST_KEYS:
                    value = getattr(child, "value", None)
                    if isinstance(value, list):
                        names.update(str(item) for item in value if str(item))
                    elif isinstance(value, str) and value:
                        names.add(value)
                stack.append(child)
        elif isinstance(entry, toml.TomlArrayEntry):
            stack.extend(entry.items)
    return names


def is_list_file(relative: str, declared: set[str], path: Path | None = None) -> bool:
    """Whether a file is a plain-text table rather than an entity document.

    A name the project declares under ``<equipment>`` or ``<surnames>`` is a table
    whatever the file holds; the name conventions cover a scope that declares
    nothing, and a ``.txt`` with no XML root is a table by its content
    (docs/cli.md section 4.3).
    """
    if not is_entity(relative):
        return True
    if relative.rsplit("/", 1)[-1] in declared:
        return True
    return path is not None and is_plain_text(path)


def single_document(ctx: Context) -> tuple[Path, str]:
    """The one file an entity command needs, with a clear error when ambiguous."""
    files = targets(ctx)
    if len(files) != 1:
        raise UsageError(f"expected one file, got {len(files)}; name the file explicitly")
    return files[0], relative_of(ctx.scope, files[0])


def new_document(ctx: Context) -> Path:
    """The file an ``add`` creates; nothing is read or written here."""
    scope = ctx.scope
    raw = ctx.selector if ctx.selector not in ("", "all") else "/".join(ctx.doc_path)
    raw = raw.strip().strip("/")
    if not raw:
        raise UsageError("add needs a document path, for example Data/Weapons/WEAPON_NEW.toml")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise UsageError(f"{raw}: the path must stay inside the project")
    if candidate.suffix != SUFFIX_TOML:
        raise UsageError(f"{raw}: a working document is a {SUFFIX_TOML} file")
    relative = raw if raw.startswith(f"{DATA_FOLDER}/") else f"{DATA_FOLDER}/{raw}"
    return scope.root / relative


def root_tag_for(relative: str) -> str | None:
    """The root element a new document in this folder carries, from its category."""
    from core.edit import ROOT_BY_CATEGORY

    return ROOT_BY_CATEGORY.get(category_of_path(relative))


def table_of(headers: list[str], rows: list[list[object]], summary: str = "") -> str:
    """Render an aligned text table with an optional summary line."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    widths = [min(width, 60) for width in widths]

    def line(cells: list[object]) -> str:
        padded = [str(cell)[:width].ljust(width) for cell, width in zip(cells, widths)]
        return "  ".join(padded).rstrip()

    body = [line(headers), line(["-" * width for width in widths])]
    body.extend(line(row) for row in rows)
    if summary:
        body.append("")
        body.append(summary)
    return "\n".join(body)


def document_path(scope: Scope, relative: str) -> str:
    """Where a file sits inside a scope, as ``Scope/relative``."""
    return f"{scope.name}/{relative}"


def scope_items(scope: Scope) -> list[tuple[str, Path]]:
    """Every file of a scope with its relative name, for a fingerprint."""
    return [(relative_of(scope, path), path) for path in entity_files(scope)]


def stored_index(ctx: Context, scope: Scope):
    """The stored cross-reference tables, when they describe exactly these files.

    A project that has no tables, or whose tables were built from a different
    set of files, returns None and the caller walks the documents instead
    (docs/cli.md section 4.6).
    """
    from core import edit

    if scope.name == "Firefight":
        return None
    try:
        project_root = edit.project_root_of(scope.root)
    except FfError:
        return None
    loaded = index_core.load(project_root)
    if loaded is None:
        return None
    index_tables, refs_tables = loaded
    built = index_tables.get("built")
    if not isinstance(built, dict):
        return None
    if built.get("fingerprint") != index_core.fingerprint(scope_items(scope)):
        return None
    if not isinstance(index_tables.get("documents"), dict):
        return None
    if not isinstance(refs_tables.get("by_source"), dict):
        return None
    return index_tables, refs_tables


def is_roster(relative: str, declared: set[str]) -> bool:
    """Whether a list file is a unit roster: named like one and declared by the project.

    Only the equipment lists name documents that must exist under ``Data/``; a surname list
    names people, not files, so its entries are not references and would only read as noise
    (docs/refs.md).  A file merely recognised by the "no XML root" fallback is not declared
    and contributes nothing.
    """
    return relative.rsplit("/", 1)[-1] in declared and category_of_path(relative) == "equipment"


def roster_entries(path: Path) -> list[tuple[int, str]]:
    """The numbered entries of a plain-text roster; comments and blank lines are left out."""
    try:
        text = textio.read_source(path).text
    except (FfError, OSError):
        return []
    return [(row["line"], row["value"]) for row in roster_core.parse(text) if row["value"]]


def roster_references(scope: Scope, relative: str, path: Path, declared: set[str]) -> list[dict]:
    """The entries of one plain-text roster, as references of that file.

    An entry names a unit document, so it is a reference like the ones a leaf tag carries
    and belongs in the same graph; the line it sits on is what the reference names instead
    of a field path (docs/refs.md).
    """
    if not is_roster(relative, declared):
        return []
    source = document_path(scope, relative)
    return [
        {
            "source": source,
            "kind": refs_core.ROSTER_KIND,
            "value": name,
            "document_path": f"line {line}",
        }
        for line, name in roster_entries(path)
    ]


def reference_rows(ctx: Context, scope: Scope, files: list[Path]) -> tuple[list[dict], list[dict], str]:
    """The references of the selected files, from the stored tables or a fresh walk."""
    declared = declared_lists(scope)
    stored = stored_index(ctx, scope)
    if stored is not None:
        _, refs_tables = stored
        by_source = refs_tables["by_source"]
        collected: list[dict] = []
        for path in files:
            relative = relative_of(scope, path)
            if is_list_file(relative, declared):
                collected.extend(roster_references(scope, relative, path, declared))
                continue
            lines = by_source.get(relative)
            if not isinstance(lines, list):
                continue
            for line in lines:
                decoded = index_core.decode(str(line))
                if decoded is None:
                    continue
                kind, document_path_text, value = decoded
                collected.append(
                    {
                        "source": document_path(scope, relative),
                        "kind": kind,
                        "value": value,
                        "document_path": document_path_text,
                    }
                )
        return collected, [], "index"
    collected = []
    errors: list[dict] = []
    for path in files:
        relative = relative_of(scope, path)
        if is_list_file(relative, declared, path):
            collected.extend(roster_references(scope, relative, path, declared))
            continue
        try:
            document = load_document(path, relative)
        except XmlStructureError:
            # A .txt without an XML root is a plain-text data file, as elsewhere in the format.
            continue
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        for reference in refs_core.references_in(document.root, document_path(scope, relative)):
            collected.append(
                {
                    "source": reference.source,
                    "kind": reference.kind,
                    "value": reference.value,
                    "document_path": "/".join(reference.path),
                }
            )
    return collected, errors, "scan"


def cmd_index(ctx: Context) -> Result:
    """Build the cross-reference tables; needs --write.

    The tables cover the whole scope whatever the selector says, because they are
    a cache of the scope rather than of one query (docs/cli.md section 4.6).
    """
    from core import edit, journal

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; index refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("index needs --write; add --dry-run to inspect the result without writing")
    project_root = edit.project_root_of(scope.root)
    items = scope_items(scope)
    documents: dict[str, str] = {}
    by_source: dict[str, list[str]] = {}
    errors: list[dict] = []
    references = 0
    skipped = 0
    declared = declared_lists(scope)
    for relative, path in items:
        if is_list_file(relative, declared, path):
            # A roster is not an XML document; it still contributes its entries, so the table
            # answers for the units a project declares (docs/refs.md).
            skipped += 1
            lines = [
                index_core.signature(item["kind"], item["document_path"], item["value"])
                for item in roster_references(scope, relative, path, declared)
            ]
            if lines:
                by_source[relative] = lines
            references += len(lines)
            continue
        try:
            document = load_document(path, relative)
        except XmlStructureError:
            # A .txt without an XML root is a plain-text data file, as elsewhere in the format.
            skipped += 1
            continue
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        documents[relative] = document.root.tag
        lines = [
            index_core.signature(reference.kind, "/".join(reference.path), reference.value)
            for reference in refs_core.references_in(document.root, document_path(scope, relative))
        ]
        if lines:
            by_source[relative] = lines
        references += len(lines)
    dry_run = ctx.options.get("dry-run") == "1"
    built = {
        "at": index_core.stamp(),
        "scope": scope.name,
        "fingerprint": index_core.fingerprint(items),
        "documents": len(documents),
        "references": references,
    }
    written: list[str] = []
    if not dry_run:
        with journal.hold_lock(project_root, tool="core.cli index"):
            written = [str(path) for path in index_core.write(project_root, built, documents, by_source)]
    where = f"{journal.EDITOR_DIR}/{index_core.INDEX_NAME} and {journal.EDITOR_DIR}/{index_core.REFS_NAME}"
    summary = (
        f"{len(documents)} document(s), {references} reference(s) in {len(by_source)} file(s), "
        f"{skipped} file(s) skipped (lists and plain text), {len(errors)} unreadable; "
        f"{'would write' if dry_run else 'written to'} {where}"
    )
    text = table_of(
        ["document", "references"],
        [[name, len(by_source[name])] for name in sorted(by_source)][: row_limit(ctx)],
        summary,
    )
    return Result(
        {
            "scope": scope.name,
            "root": str(project_root),
            "documents": len(documents),
            "references": references,
            "sources": len(by_source),
            "skipped": skipped,
            "errors": errors,
            "dry_run": dry_run,
            "written": written,
            "fingerprint": built["fingerprint"],
        },
        text,
        _index_code(errors),
    )


def _index_code(errors: list[dict]) -> int:
    """One unreadable document still leaves a usable table; report it as a failure."""
    return 1 if errors else 0


# --- commands ---------------------------------------------------------------


def cmd_list(ctx: Context) -> Result:
    """List entities with category, storage format and size."""
    scope = ctx.scope
    files = filter_category(targets(ctx), ctx, scope)
    entities = []
    for path in files:
        relative = relative_of(scope, path)
        entities.append(
            {
                "path": relative,
                "category": category_of_path(relative),
                "format": path.suffix.lstrip("."),
                "bytes": path.stat().st_size,
            }
        )
    rows_entities = entities[: row_limit(ctx)]
    rows = [[item["path"], item["category"], item["format"], item["bytes"]] for item in rows_entities]
    summary = f"{tally(len(rows_entities), len(entities))} entity file(s) in {scope.describe()}"
    text = table_of(["path", "category", "format", "bytes"], rows, summary)
    return Result(
        {
            "scope": scope.name,
            "root": str(scope.root),
            "count": len(entities),
            "shown": len(rows_entities),
            "entities": rows_entities,
        },
        text,
    )


def cmd_show(ctx: Context) -> Result:
    """Show one entity, as stored or in the other representation."""
    path, relative = single_document(ctx)
    if is_list_file(relative, declared_lists(ctx.scope), path):
        text = textio.read_source(path).text
        return Result({"path": relative, "format": "list", "text": text, "warnings": []}, text.rstrip("\n"))
    document = load_document(path, relative)
    view = ctx.options.get("as", "raw")
    if ctx.doc_path:
        return _show_subtree(ctx, document, relative, view)
    if view == "raw":
        payload = {"path": relative, "format": document.format, "text": document.text}
        body = document.text
    elif view == "toml":
        payload = {"path": relative, "format": document.format, "toml": document.toml_text()}
        body = document.toml_text()
    elif view == "xml":
        rendered = document.xml_text()
        payload = {"path": relative, "format": document.format, "xml": rendered}
        body = rendered
    else:
        raise UsageError(f"unknown as={view}; use raw, toml or xml")
    payload["warnings"] = list(document.warnings)
    note = f"\n-- {len(document.warnings)} warning(s)" if document.warnings else ""
    return Result(payload, body.rstrip("\n") + note)


def _show_subtree(ctx: Context, document, relative: str, view: str) -> Result:
    """Show the elements a document path selects."""
    key = "/".join((document.root.tag, *ctx.doc_path))
    if view == "toml":
        entries = select_table(document.table, ctx.doc_path)
        if not entries:
            raise UsageError(f"{document_path(ctx.scope, relative)}/{'/'.join(ctx.doc_path)}: no such key")
        from core import tomlwrite

        wrapper = TomlTable(entries=[(ctx.doc_path[-1], entries[0])])
        text = toml.render(wrapper)
        return Result({"path": relative, "key": key, "toml": text}, text.rstrip("\n"))
    matches = select(document.root, ctx.doc_path)
    if not matches:
        raise UsageError(f"{document_path(ctx.scope, relative)}/{'/'.join(ctx.doc_path)}: no such element")
    if view == "xml":
        body = "\n".join(_subtree_xml(element, 0) for _, element in matches)
        return Result({"path": relative, "key": key, "count": len(matches), "xml": body}, body)
    rows = []
    values = []
    for path_tuple, element in matches:
        for leaf_path, leaf in _leaves(path_tuple[:-1], element):
            rows.append(["/".join(leaf_path), leaf.line, leaf.value])
            values.append({"path": "/".join(leaf_path), "line": leaf.line, "value": leaf.value})
    text = table_of(["path", "line", "value"], rows, f"{key} matched {len(matches)} element(s)")
    return Result(
        {"path": relative, "key": key, "count": len(matches), "values": values},
        text,
    )


def _leaves(prefix: tuple[str, ...], element: XmlElement) -> list[tuple[tuple[str, ...], XmlElement]]:
    """Every leaf under an element, with its full path from the document root."""
    here = prefix + (element.tag,)
    if not element.children:
        return [(here, element)]
    found: list[tuple[tuple[str, ...], XmlElement]] = []
    for child in element.children:
        found.extend(_leaves(here, child))
    return found


def _subtree_xml(element: XmlElement, depth: int) -> str:
    indent = "\t" * depth
    if not element.children:
        return f"{indent}<{element.tag}>{element.value}</{element.tag}>"
    body = "\n".join(_subtree_xml(child, depth + 1) for child in element.children)
    return f"{indent}<{element.tag}>\n{body}\n{indent}</{element.tag}>"


def cmd_get(ctx: Context) -> Result:
    """Read a field, a subtree, or every field of one document.

    ``field=<a.b.c>`` or a document path selects a part of the document; with
    neither, the document's own fields are listed under the names ``set`` takes
    (docs/cli.md section 4).
    """
    path, relative = single_document(ctx)
    document = load_document(path, relative)
    field = ctx.options.get("field")
    if field:
        keys = tuple(part for part in field.replace("/", ".").split(".") if part)
    elif ctx.doc_path:
        keys = ctx.doc_path
    else:
        return _get_all(ctx, document, relative)
    rows = []
    for path_tuple, element in select(document.root, keys):
        for leaf_path, leaf in _leaves(path_tuple[:-1], element):
            rows.append(
                {
                    "path": "/".join(leaf_path),
                    "line": leaf.line,
                    "value": leaf.value,
                }
            )
    if not rows and document.format == "toml":
        rows = toml_rows(document, keys)
    if not rows:
        raise UsageError(f"{document_path(ctx.scope, relative)}: no field {'/'.join(keys)}")
    shown = rows[: row_limit(ctx)]
    text = table_of(
        ["path", "line", "value"],
        [[row["path"], row["line"], row["value"]] for row in shown],
        f"{tally(len(shown), len(rows))} value(s)",
    )
    return Result(
        {
            "path": relative,
            "field": "/".join(keys),
            "root": document.root_tag,
            "format": document.format,
            "count": len(rows),
            "shown": len(shown),
            "values": shown,
        },
        text,
    )


def toml_rows(document, keys: tuple[str, ...]) -> list[dict]:
    """Fields a key path selects in a working document, index segments included.

    The element walk names tags, so it cannot reach ``ammo.type.1.name``; the key
    path is the same one ``set`` takes (docs/cli.md section 4).
    """
    from core.edit import root_table

    wanted = tuple(keys)
    rows = []
    for key_path, value in flatten(root_table(document.table, document.root_tag)):
        if key_path[: len(wanted)] != wanted:
            continue
        rows.append({"path": ".".join(key_path), "line": value.line, "value": value.raw})
    return rows


def _get_all(ctx: Context, document, relative: str) -> Result:
    """Every field of one document, named the way ``set`` names fields."""
    from core.edit import root_table

    found = flatten(root_table(document.table, document.root_tag))
    if not found:
        raise UsageError(f"{document_path(ctx.scope, relative)}: the document declares no fields")
    rows = [
        {"path": ".".join(key_path), "line": value.line, "value": value.raw}
        for key_path, value in found
    ]
    shown = rows[: row_limit(ctx)]
    text = table_of(
        ["field", "value"],
        [[row["path"], row["value"]] for row in shown],
        f"{tally(len(shown), len(rows))} field(s)",
    )
    return Result(
        {
            "path": relative,
            "field": "",
            "root": document.root_tag,
            "format": document.format,
            "count": len(rows),
            "shown": len(shown),
            "values": shown,
        },
        text,
    )


def cmd_find(ctx: Context) -> Result:
    """Search tags, document paths and values across a scope.

    The whole scope is searched whatever ``limit=`` says, so ``count`` is the
    number of matches and not merely the number of rows printed (docs/cli.md
    section 4).
    """
    tag = ctx.options.get("tag")
    value = ctx.options.get("value")
    prefix = ctx.options.get("path")
    ignore_case = ctx.options.get("ignore_case", "0") not in ("0", "false", "no")
    limit = row_limit(ctx)
    if tag is None and value is None and prefix is None:
        raise UsageError("nothing to search for; pass tag=<name>, value=<text> or path=<a/b>")
    needle = value.casefold() if (value and ignore_case) else value
    files = filter_category(targets(ctx), ctx, ctx.scope)
    declared = declared_lists(ctx.scope)
    matches: list[dict] = []
    total = 0
    for path in files:
        relative = relative_of(ctx.scope, path)
        if is_list_file(relative, declared, path):
            continue
        try:
            document = load_document(path, relative)
        except FfError as error:
            matches.append({"path": relative, "error": str(error)})
            total += 1
            continue
        for element_path, element in walk(document.root):
            joined = "/".join(element_path)
            if tag is not None and element.tag != tag:
                continue
            if prefix is not None and not joined.startswith(prefix.strip("/")):
                continue
            if needle is not None:
                haystack = element.value.casefold() if ignore_case else element.value
                if needle not in haystack:
                    continue
            total += 1
            if limit is None or len(matches) < limit:
                matches.append(
                    {
                        "path": relative,
                        "line": element.line,
                        "tag": element.tag,
                        "document_path": joined,
                        "value": element.value,
                    }
                )
    rows = [[item["path"], item.get("line", ""), item.get("tag", ""), item.get("value", "")] for item in matches]
    summary = f"{tally(len(matches), total)} match(es)"
    text = table_of(["path", "line", "tag", "value"], rows, summary)
    query = {"tag": tag, "value": value, "path": prefix, "ignore_case": ignore_case}
    return Result(
        {
            "query": query,
            "count": total,
            "shown": len(matches),
            "truncated": len(matches) < total,
            "matches": matches,
        },
        text,
    )


def cmd_stats(ctx: Context) -> Result:
    """Counts by category, root element and storage format."""
    scope = ctx.scope
    files = filter_category(targets(ctx), ctx, scope)
    by_category: dict[str, int] = {}
    by_root: dict[str, int] = {}
    by_format: dict[str, int] = {}
    bytes_total = 0
    errors: list[dict] = []
    lists = 0
    declared = declared_lists(scope)
    for path in files:
        relative = relative_of(scope, path)
        category = category_of_path(relative)
        by_category[category] = by_category.get(category, 0) + 1
        by_format[path.suffix.lstrip(".")] = by_format.get(path.suffix.lstrip("."), 0) + 1
        bytes_total += path.stat().st_size
        if is_list_file(relative, declared, path):
            lists += 1
            continue
        try:
            root = _root_tag(path)
        except XmlStructureError:
            lists += 1
            continue
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        by_root[root] = by_root.get(root, 0) + 1
    rows = [[category, count] for category, count in sorted(by_category.items(), key=lambda item: (-item[1], item[0]))]
    rows += [["", ""]]
    rows += [[f"root <{root}>", count] for root, count in sorted(by_root.items(), key=lambda item: (-item[1], item[0]))]
    summary = (
        f"{len(files)} file(s), {bytes_total} bytes, {lists} list file(s), {len(errors)} unreadable, "
        f"scope {scope.describe()}"
    )
    text = table_of(["category", "count"], rows, summary)
    payload = {
        "scope": scope.name,
        "root": str(scope.root),
        "files": len(files),
        "bytes": bytes_total,
        "lists": lists,
        "by_category": by_category,
        "by_format": by_format,
        "by_root": by_root,
        "errors": errors,
    }
    return Result(payload, text)


def _root_tag(path: Path) -> str:
    """Root element name of one file, without a full model build."""
    text = textio.read_source(path).text
    if path.suffix.lower() == ".toml":
        table = toml.parse(text, str(path))
        if not table.entries:
            raise SchemaError((), f"{path}: empty document")
        return table.entries[0][0]
    return xml.parse(text, str(path)).root.tag


def cmd_refs(ctx: Context) -> Result:
    """Outgoing references of the selected entities."""
    kind = ctx.options.get("kind")
    scope = ctx.scope
    files = filter_category(targets(ctx), ctx, scope)
    collected, errors, origin = reference_rows(ctx, scope, files)
    if kind is not None:
        collected = [item for item in collected if item["kind"] == kind]
    counts: dict[str, int] = {}
    for item in collected:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    shown = collected[: row_limit(ctx)]
    rows = [[item["source"], item["kind"], item["value"], item["document_path"]] for item in shown]
    summary = f"{tally(len(shown), len(collected))} reference(s) " + ", ".join(
        f"{name}={count}" for name, count in sorted(counts.items())
    )
    text = table_of(["source", "kind", "value", "document_path"], rows, summary)
    return Result(
        {
            "scope": scope.name,
            "origin": origin,
            "count": len(collected),
            "shown": len(shown),
            "by_kind": counts,
            "references": shown,
            "errors": errors,
        },
        text,
    )


def cmd_deps(ctx: Context) -> Result:
    """Who references a value or a file, and whether the target exists."""
    scope = ctx.scope
    value = ctx.options.get("value") or (ctx.selector if ctx.selector and ctx.selector != "all" else None)
    kind = ctx.options.get("kind")
    if not value:
        raise UsageError("name what to look for: value=<token>")
    files = entity_files(scope)
    collected, errors, origin = reference_rows(ctx, scope, files)
    incoming = [
        item
        for item in collected
        if item["value"] == value and (kind is None or item["kind"] == kind)
    ]
    index = refs_core.TargetIndex(scope.root, unit_folders=unit_folders())
    resolved: list[str] = []
    resolving = 0
    for item in incoming:
        targets = index.find(item["kind"], item["value"])
        if targets:
            resolving += 1
            resolved.extend(relative_of(scope, target) for target in targets)
    shown = incoming[: row_limit(ctx)]
    rows = [[item["source"], item["kind"], item["document_path"]] for item in shown]
    found = sorted(set(resolved))
    summary = (
        f"{tally(len(shown), len(incoming))} incoming reference(s); "
        f"{resolving} of {len(incoming)} point at a file that is there"
    )
    if found:
        summary += f": {', '.join(found)}"
    text = table_of(["source", "kind", "document_path"], rows, summary)
    return Result(
        {
            "scope": scope.name,
            "origin": origin,
            "value": value,
            "count": len(incoming),
            "shown": len(shown),
            "references": [
                {"source": item["source"], "kind": item["kind"], "document_path": item["document_path"]}
                for item in shown
            ],
            "resolved": sorted(set(resolved)),
            "unresolved": not resolved,
            "errors": errors,
        },
        text,
    )


ASSET_KINDS = ("image", "sound", "uniform", "engine_sound")


def other_root(raw: str, ctx: Context) -> Path:
    """The root ``against=`` names: a directory, ``scope:path``, or a scope name.

    ``stock`` is the installation the editor setting points at, which is the root an imported
    project wants answered. A one-letter name before the colon is a drive letter rather than a
    scope, as in a diff side (docs/cli.md section 4.10).
    """
    wanted = raw.replace("\\", "/").strip()
    options = {key: value for key, value in ctx.options.items() if key not in ("against",)}
    if wanted.lower() == "stock":
        return resolve_scope("Firefight", options, ctx.cwd).root
    if ":" in wanted:
        head = wanted.split(":", 1)[0]
        if len(head) > 1 and all(character.isalnum() or character in "_-" for character in head):
            return resolve_scope(head, options, ctx.cwd).root
    candidate = Path(wanted)
    if not candidate.is_absolute():
        candidate = ctx.cwd / candidate
    if candidate.is_dir():
        return candidate
    return resolve_scope(wanted, options, ctx.cwd).root


def cmd_check(ctx: Context) -> Result:
    """Load every selected entity, then report load errors, warnings and dangling references.

    ``against=`` resolves references the project itself does not hold against a second root,
    which is what an imported project needs; ``assets=1`` names the file a missing image or
    sound would have to be; ``rosters=1`` folds the roster comparison in (docs/cli.md
    section 4.6).
    """
    from core import roster as roster_core

    scope = ctx.scope
    files = filter_category(targets(ctx), ctx, scope)
    errors: list[dict] = []
    warned: list[dict] = []
    warnings_total = 0
    warning_files = 0
    graph = refs_core.RefGraph()
    loaded = 0
    skipped = 0
    declared = declared_lists(scope)
    for path in files:
        relative = relative_of(scope, path)
        if is_list_file(relative, declared, path):
            # A roster is not an XML document, so it stays "skipped" in the counters, but the
            # entries of a declared unit roster are references and join the graph (docs/refs.md).
            skipped += 1
            if is_roster(relative, declared):
                graph.add_roster(document_path(scope, relative), roster_entries(path))
            continue
        try:
            document = load_document(path, relative)
        except XmlStructureError:
            # A .txt without an XML root is a plain-text data file, as elsewhere in the format.
            skipped += 1
            continue
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        loaded += 1
        if document.warnings:
            warnings_total += len(document.warnings)
            warning_files += 1
            warned.append({"path": relative, "warnings": list(document.warnings)})
        graph.add(document_path(scope, relative), document.root)
    limit = row_limit(ctx, default=CHECK_SAMPLES)
    index = refs_core.TargetIndex(scope.root, unit_folders=unit_folders())
    against = ctx.options.get("against")
    extra = refs_core.TargetIndex(other_root(against, ctx)) if against else None
    assets = ctx.options.get("assets") == "1"
    resolved_elsewhere = 0
    dangling: list[dict] = []
    for item in refs_core.unresolved(graph, index):
        if extra is not None and extra.find(item.kind, item.value):
            resolved_elsewhere += 1
            continue
        dangling.append(
            {
                "source": item.source,
                "kind": item.kind,
                "value": item.value,
                "document_path": "/".join(item.path),
                "expected": list(index.expected(item.kind, item.value)),
            }
        )
    roster_report: dict | None = None
    roster_rows: list[list[str]] = []
    if ctx.options.get("rosters") == "1":
        listed = {
            relative: roster_core.names(roster_core.parse(textio.read_source(path).text))
            for relative, path in roster_paths(scope)
        }
        gaps = roster_core.gaps(listed, roster_documents(scope))
        roster_report = {
            "files": len(listed),
            "missing": len(gaps["missing"]),
            "orphans": len(gaps["orphans"]),
        }
        roster_rows = [[f"{item['roster']}: {item['name']}", "no document"] for item in gaps["missing"]]
        roster_rows += [[item["name"], "no roster names it"] for item in gaps["orphans"]]
    # Warnings are issues too: the summary counts them, so the table has to name them.
    # Otherwise a project can report "2 warning(s) in 1 file(s)" above an empty table.
    shown_warned = warned if limit is None else warned[:limit]
    shown_dangling = dangling if limit is None else dangling[:limit]
    rows = [[item["path"], item["error"]] for item in errors]
    rows += [
        [item["path"], warning] for item in shown_warned for warning in item["warnings"]
    ]
    for item in shown_dangling:
        if assets and item["kind"] in ASSET_KINDS and item["expected"]:
            issue = "missing " + " or ".join(item["expected"])
        else:
            issue = f"unresolved {item['kind']}={item['value']}"
        rows.append([item["source"], issue])
    rows += roster_rows
    hidden = len(dangling) - len(shown_dangling)
    if hidden:
        rows.append(["...", f"{hidden} more dangling reference(s) not shown; raise limit= or pass limit=0"])
    missing_assets = sum(1 for item in dangling if item["kind"] in ASSET_KINDS)
    kinds: dict[str, int] = {}
    for item in dangling:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    summary = (
        f"{loaded}/{len(files)} loaded, {skipped} list file(s) skipped, {len(errors)} error(s), "
        f"{warnings_total} warning(s) in {warning_files} file(s), {len(dangling)} dangling reference(s)"
    )
    if len(kinds) > 1:
        ranked = sorted(kinds.items(), key=lambda pair: (-pair[1], pair[0]))
        summary += ", by kind: " + ", ".join(f"{kind} {count}" for kind, count in ranked[:4])
    if against:
        summary += f", {resolved_elsewhere} answered by the other root"
    if assets:
        summary += f", {missing_assets} missing asset reference(s)"
    if roster_report is not None:
        summary += (
            f", {roster_report['missing']} roster entry(s) no document answers, "
            f"{roster_report['orphans']} document(s) no roster names"
        )
    text = table_of(["file", "issue"], rows, summary)
    code = 1 if errors or dangling or roster_rows else 0
    return Result(
        {
            "scope": scope.name,
            "files": len(files),
            "loaded": loaded,
            "skipped": skipped,
            "errors": errors,
            "warnings_total": warnings_total,
            "warning_files": warning_files,
            "warning_samples": shown_warned,
            "warnings_shown": sum(len(item["warnings"]) for item in shown_warned),
            "dangling": shown_dangling,
            "dangling_total": len(dangling),
            "dangling_shown": len(shown_dangling),
            "truncated": bool(hidden),
            "assets_missing": missing_assets,
            "dangling_kinds": kinds,
            "against": str(extra.root) if extra is not None else "",
            "dangling_answered_elsewhere": resolved_elsewhere,
            "rosters": roster_report,
            "ok": code == 0,
        },
        text,
        code,
    )


def cmd_init(ctx: Context) -> Result:
    """Create a project: ``ModInformation.toml`` and an empty ``Data/`` (docs/cli.md section 4.9).

    ``root=`` or ``workspace=`` names the directory to create the project in, the working
    directory when neither is given; that directory may be empty and is created when it is
    missing.  Every other command resolves a scope that already exists — ``init`` is the one
    that makes one.  An existing ``ModInformation.toml`` is refused, so an initialised
    project is never overwritten.  ``name=`` fills the mod name in, the directory name
    otherwise.  The record goes into the log like any other new document, so ``undo`` takes
    the manifest away again; the empty ``Data`` is a directory, not a document, and no
    record reverts it.
    """
    from core import edit

    if ctx.scope.name != "Mod":
        raise UsageError(f"init creates a project under Mod, not {ctx.scope.name}")
    if ctx.options.get("write") != "1":
        raise UsageError("init needs --write; add --dry-run to inspect the result without writing")
    dry_run = ctx.options.get("dry-run") == "1"
    project = Path(ctx.scope.root)
    manifest = project / PROJECT_FILE
    if manifest.is_file():
        raise UsageError(f"{manifest}: a project is already here; nothing was written")
    name = (ctx.options.get("name") or "").strip() or project.name
    if not name:
        raise UsageError("init needs a name: this directory has none, so pass name=<name>")

    data_root = project / DATA_FOLDER
    plan = edit.plan_create(manifest, PROJECT_FILE, edit.project_skeleton(name), entity=name)
    if dry_run:
        payload = edit.apply_document(plan, project, dry_run=True)
    else:
        data_root.mkdir(parents=True, exist_ok=True)
        payload = edit.apply_document(plan, project, actor=write_actor(ctx))
    payload = payload | {
        "scope": ctx.scope.name,
        "project": str(project),
        "name": name,
        "data_root": str(data_root),
        "files": [PROJECT_FILE],
    }
    return Result(payload, _init_text(payload), 0)


def _init_text(payload: dict) -> str:
    """One line for a created project."""
    state = "would be created" if payload.get("dry_run") else "created"
    tail = f" [{payload['id']}]" if payload.get("id") else ""
    return (
        f"{payload['project']}: {payload['name']} {state} "
        f"({PROJECT_FILE} and an empty {DATA_FOLDER}/){tail}"
    )


#: The trees an import brings across; the editor's own cache is not one of them.
IMPORT_TREES = ("Data", "Images", "Sounds")
#: The files an import brings across from the root of the mod it reads.
IMPORT_FILES = ("mod.txt", "README.md", "LICENSE", PROJECT_FILE, SETTING_FILE)


def _import_root(names: list[str]) -> str:
    """The prefix inside an import source that holds the mod, ``""`` for the top.

    An archive made by ``pack`` has everything under ``Mod/``; an extracted one often has a
    directory of its own above that.  Both are accepted, matching the packager's own search
    (docs/cli.md section 4.16).
    """
    if any(name.startswith("Data/") for name in names):
        return ""
    heads = sorted({name.split("/", 1)[0] for name in names})
    for head in heads:
        if any(name.startswith(f"{head}/Data/") for name in names):
            return f"{head}/"
    for head in heads:
        if any(name.startswith(f"{head}/Mod/Data/") for name in names):
            return f"{head}/Mod/"
    return ""


def _import_keeps(relative: str) -> bool:
    """Whether one path inside a mod belongs in the project."""
    return relative.split("/", 1)[0] in IMPORT_TREES or relative in IMPORT_FILES


def _import_members(source: Path) -> tuple[list[tuple[str, bytes]], str, str]:
    """Every file to copy out of a mod, the prefix it came from, and an error or ``""``."""
    if source.is_file() and source.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(source) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
                root = _import_root(names)
                picked = [
                    (name[len(root):], archive.read(name))
                    for name in names
                    if name.startswith(root) and _import_keeps(name[len(root):])
                ]
        except (OSError, zipfile.BadZipFile) as failure:
            return [], "", f"{source}: {failure}"
    elif source.is_dir():
        names = sorted(path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file())
        root = _import_root(names)
        picked = [
            (name[len(root):], (source / name).read_bytes())
            for name in names
            if name.startswith(root) and _import_keeps(name[len(root):])
        ]
    else:
        return [], "", f"{source}: an import source is a directory or a .zip file"
    if not any(relative.startswith(f"{DATA_FOLDER}/") for relative, _ in picked):
        return [], root, f"{source}: no {DATA_FOLDER}/ folder inside; nothing to import"
    return picked, root, ""


def cmd_import(ctx: Context) -> Result:
    """Create a project from a mod that already exists, as a directory or a zip.

    The source is walked for a mod root — the directory holding ``Mod/`` or ``Data/``, or the
    one holding it one level down, which is how an extracted archive usually looks.  The data
    tree, ``Images/`` and ``Sounds/`` are copied byte for byte, ``mod.txt`` comes along when it
    is there, and ``ModSetting.toml`` is rendered from it when the source does not already
    carry one.  The destination must hold no project unless ``overwrite=1``, and nothing is
    written without ``--write`` (docs/cli.md section 4.16).
    """
    from core import edit, journal, settings

    if ctx.scope.name != "Mod":
        raise UsageError(f"import creates a project under Mod, not {ctx.scope.name}")
    raw = ctx.selector or ""
    if not raw:
        raise UsageError("import needs a source: import <directory or zip>")
    target_raw = ctx.options.get("to")
    if not target_raw:
        raise UsageError("import needs a destination project: to=<directory>")
    if ctx.options.get("write") != "1":
        raise UsageError("import needs --write; add --dry-run to inspect the result without writing")
    source = Path(raw)
    if not source.exists():
        raise UsageError(f"{source}: there is nothing to import from")
    destination = Path(target_raw)
    overwrite = ctx.options.get("overwrite")
    replace = overwrite == "1"
    keep = overwrite == "0"
    dry_run = ctx.options.get("dry-run") == "1"
    manifest = destination / PROJECT_FILE
    if manifest.is_file() and not (replace or keep):
        raise UsageError(
            f"{manifest}: a project is already here; pass overwrite=1 to replace it, "
            "or overwrite=0 to keep what is there"
        )

    members, root, error = _import_members(source)
    if error:
        raise UsageError(error)
    copies = dict(members)

    written: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    for relative, data in members:
        out = destination / Path(relative)
        if out.is_file() and not replace:
            skipped.append({"path": relative, "reason": "exists"})
            continue
        if dry_run:
            written.append({"path": relative, "bytes": len(data)})
            continue
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            journal.write_atomic(out, data)
        except (FfError, OSError) as failure:
            errors.append({"path": relative, "error": str(failure)})
            continue
        written.append({"path": relative, "bytes": len(data)})

    copied = set(copies)
    if settings.MOD_TXT in copies and SETTING_FILE not in copied:
        target = destination / SETTING_FILE
        if target.is_file() and not replace:
            skipped.append({"path": SETTING_FILE, "reason": "exists"})
        else:
            try:
                text, _encoding = textio.decode_source(copies[settings.MOD_TXT], settings.MOD_TXT)
                table, _warnings = settings.render(text, settings.MOD_TXT)
                rendered = toml.render(table)
                if not dry_run:
                    plan = edit.plan_render(target, SETTING_FILE, rendered, entity="mod_setting")
                    edit.apply_document(plan, destination, actor=write_actor(ctx))
                written.append({"path": SETTING_FILE, "bytes": len(rendered)})
            except (FfError, ValueError) as failure:
                errors.append({"path": SETTING_FILE, "error": str(failure)})

    if PROJECT_FILE not in copied:
        name = destination.name or "mod"
        if manifest.is_file() and not replace:
            skipped.append({"path": PROJECT_FILE, "reason": "exists"})
        else:
            try:
                if not dry_run:
                    skeleton = edit.project_skeleton(name)
                    plan = (
                        edit.plan_render(manifest, PROJECT_FILE, skeleton, entity=name)
                        if manifest.is_file()
                        else edit.plan_create(manifest, PROJECT_FILE, skeleton, entity=name)
                    )
                    edit.apply_document(plan, destination, actor=write_actor(ctx))
                written.append({"path": PROJECT_FILE, "bytes": 0})
            except FfError as failure:
                errors.append({"path": PROJECT_FILE, "error": str(failure)})

    limit = row_limit(ctx)
    payload = {
        "scope": ctx.scope.name,
        "source": str(source),
        "root": root,
        "to": str(destination),
        "overwrite": replace,
        "dry_run": dry_run,
        "count": len(written),
        "shown": written if limit is None else written[:limit],
        "files": len(copied),
        "has_settings": SETTING_FILE in copied,
        "skipped": skipped,
        "errors": errors,
        "ok": not errors,
    }
    return Result(payload, _import_text(payload), 1 if errors else 0)


def _import_text(payload: dict) -> str:
    """The summary line for an import, plus anything it left out."""
    state = "planned for" if payload.get("dry_run") else "written to"
    lines = [
        f"{payload['source']}: {payload['count']} file(s) {state} {payload['to']} "
        f"({payload['files']} file(s) in the source)"
    ]
    for item in payload.get("skipped", []):
        lines.append(f"skipped: {item['path']} ({item['reason']})")
    for item in payload.get("errors", []):
        lines.append(f"error: {item['path']}: {item['error']}")
    if not payload.get("ok"):
        lines.append(f"{len(payload['errors'])} file(s) could not be written")
    return "\n".join(lines)


def cmd_add(ctx: Context) -> Result:
    """Create one entity document; needs --write and never writes the stock scope.

    Without ``from=`` the body is the schema skeleton for the folder's root
    element; with it the body is a copy of that document (docs/cli.md section 4.5).
    """
    from core import edit

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; add refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("add needs --write; add --dry-run to inspect the result without writing")
    path = new_document(ctx)
    relative = relative_of(scope, path)
    project_root = edit.project_root_of(scope.root)
    source = ctx.options.get("from")
    if source:
        files = entity_files(scope, source)
        if len(files) != 1:
            raise UsageError(f"from= names {len(files)} file(s); name the source document")
        origin_relative = relative_of(scope, files[0])
        origin = load_document(files[0], origin_relative)
        root_tag = origin.root_tag
        entity = edit.entity_of(origin, origin_relative)
        text = origin.text if origin.format == "toml" else origin.toml_text()
    else:
        root_tag = root_tag_for(relative)
        if root_tag is None:
            raise UsageError(
                f"{relative}: cannot tell which root element a document in this folder carries; "
                "add from=<an existing document> instead"
            )
        entity = Path(relative).stem
        text = edit.skeleton(root_tag)
    try:
        plan = edit.plan_create(path, relative, text, entity=entity)
        payload = edit.apply_document(
        plan, project_root, dry_run=ctx.options.get("dry-run") == "1", actor=write_actor(ctx)
    )
    except edit.EditRefused as error:
        raise UsageError(str(error)) from None
    payload["scope"] = scope.name
    payload["root"] = root_tag
    return Result(payload, _document_text(payload, "added"))


def _renamed_token(text: str, token: str) -> str:
    """The document text with the root table's own ``name`` set to ``token``.

    Only the first table's direct keys are searched: a later ``name`` belongs to a
    sub-table or to an array entry, and rewriting one of those would change something
    other than the name the document declares (docs/cli.md section 4.12).
    """
    lines = text.split("\n")
    start = 0
    for index, line in enumerate(lines):
        if line.strip().startswith("["):
            start = index + 1
            break
    for index in range(start, len(lines)):
        if lines[index].strip().startswith("["):
            break
        key, separator, _ = lines[index].partition("=")
        if separator and key.strip() == "name":
            lines[index] = f"{key}= {toml.quote_string(token)}"
            return "\n".join(lines)
    raise UsageError(
        "the source document declares no name to rename; the copy would keep the source token"
    )


def cmd_clone(ctx: Context) -> Result:
    """Copy one entity document under a new token; needs --write.

    The source may name another scope (``Firefight:Data/Weapons/WEAPON_X.txt``), which is
    how a project borrows a document from the stock data; the copy lands in the current
    scope unless ``into=`` names another one.  The new token is given up front, so a copy
    never competes with the document it came from (docs/cli.md section 4.12).
    """
    from core import edit

    source_scope, source_selector = split_side(ctx.selector, ctx)
    token = (ctx.options.get("as") or "").strip()
    project_file = Path(source_selector).name in (PROJECT_FILE, SETTING_FILE)
    if token and project_file:
        raise UsageError("clone copies a project file under its own name; as= names one document")
    if not token and not project_file:
        raise UsageError("clone needs as=<the new token>; it is the name the copy declares")
    if token and (
        any(character in token for character in "/\\:")
        or any(character.isspace() for character in token)
    ):
        raise UsageError(f"as= is one token without a path or a space, not {token!r}")
    if ctx.options.get("write") != "1":
        raise UsageError("clone needs --write; add --dry-run to inspect the copy without writing")

    target = ctx.scope
    into = ctx.options.get("into")
    if into:
        candidate = Path(into)
        if candidate.is_dir():
            target = resolve_scope("Mod", {"root": str(candidate)}, ctx.cwd)
        else:
            target = resolve_scope(into, {}, ctx.cwd)
    if target.name == "Firefight":
        raise UsageError("the stock scope is read-only; clone refuses to write under Firefight")

    if project_file:
        source_file = source_scope.project / Path(source_selector).name
        if not source_file.is_file():
            raise UsageError(f"no {source_file.name} in the project {source_scope.project}")
        source = textio.read_source(source_file)
        relative = source_file.name
        destination = target.project / relative
        project_root = edit.project_root_of(target.root)
        try:
            plan = edit.plan_render(
                destination,
                relative,
                source.text,
                entity=Path(relative).stem,
                newline="",
                encoding="utf-8-sig" if source.had_bom else source.encoding,
            )
            payload = edit.apply_document(
                plan,
                project_root,
                dry_run=ctx.options.get("dry-run") == "1",
                actor=write_actor(ctx),
            )
        except edit.EditRefused as error:
            raise UsageError(str(error)) from None
        payload["scope"] = target.name
        payload["source"] = f"{source_scope.name}:{relative}"
        return Result(payload, _document_text(payload, "cloned"))

    files = entity_files(source_scope, source_selector)
    if len(files) != 1:
        raise UsageError(
            f"{source_selector!r} names {len(files)} file(s) in scope {source_scope.name}; "
            "name one document"
        )
    origin_path = files[0]
    origin_relative = relative_of(source_scope, origin_path)
    if is_list_file(origin_relative, declared_lists(source_scope), origin_path):
        raise UsageError(f"{origin_relative} is a list file; clone copies an entity document")
    origin = load_document(origin_path, origin_relative)
    text = origin.text if origin.format == "toml" else origin.toml_text()

    relative = str(Path(origin_relative).with_name(f"{token}.toml"))
    path = target.root / relative
    project_root = edit.project_root_of(target.root)
    try:
        plan = edit.plan_create(path, relative, _renamed_token(text, token), entity=token)
        payload = edit.apply_document(
            plan,
            project_root,
            dry_run=ctx.options.get("dry-run") == "1",
            actor=write_actor(ctx),
        )
    except edit.EditRefused as error:
        raise UsageError(str(error)) from None
    payload["scope"] = target.name
    payload["source"] = f"{source_scope.name}:{origin_relative}"
    return Result(payload, _document_text(payload, "cloned"))


def cmd_remove(ctx: Context) -> Result:
    """Delete one entity document; needs --write and never writes the stock scope.

    The bytes leave the project; ``undo`` puts them back from the baseline
    (docs/cli.md section 4.5).
    """
    from core import edit

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; remove refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("remove needs --write; add --dry-run to inspect the result without writing")
    path, relative = single_document(ctx)
    document = load_document(path, relative)
    project_root = edit.project_root_of(scope.root)
    try:
        plan = edit.plan_remove(path, relative, entity=edit.entity_of(document, relative))
        payload = edit.apply_document(
        plan, project_root, dry_run=ctx.options.get("dry-run") == "1", actor=write_actor(ctx)
    )
    except edit.EditRefused as error:
        raise UsageError(str(error)) from None
    payload["scope"] = scope.name
    return Result(payload, _document_text(payload, "removed"))


def _document_text(payload: dict, verb: str) -> str:
    """The one-line report of an add or a remove."""
    where = f"would be {verb}" if payload.get("dry_run") else verb
    event = payload.get("id")
    tail = f" [{event}]" if event else ""
    return f"{payload['path']}: {payload['entity']} {where}{tail}"


def cmd_set(ctx: Context) -> Result:
    """Change one field of one document; needs --write and never writes the stock scope.

    The change is validated and rendered before anything is touched; ``--dry-run``
    reports it without writing.  ``op=append`` and ``op=delete`` add or remove one
    array-of-tables entry instead of a value (docs/cli.md section 4.1).
    """
    from core import edit, enums as enums_core

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; set refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("set needs --write; add --dry-run to inspect the change without writing")
    field = ctx.options.get("field", "")
    if not field:
        raise UsageError("set needs field=<a.b.c>")
    op = ctx.options.get("op", "set")
    if op not in ("set", "append", "delete"):
        raise UsageError(f"op= is set, append or delete, not {op!r}")
    if op == "set" and "value" not in ctx.options:
        raise UsageError("set needs value=<text>")
    path, relative = single_document(ctx)
    project_root = edit.project_root_of(scope.root)
    document = load_document(path, relative)
    try:
        if op == "set":
            plan = edit.plan_set(
                document,
                field,
                ctx.options["value"],
                enums=enums_core.load_enums(project_root),
                declared=lambda: declared_enum_values(scope),
            )
        else:
            plan = edit.plan_entry(document, field, op, copy_from=entry_index(ctx))
        report = edit.apply_plan(
        plan, project_root, dry_run=ctx.options.get("dry-run") == "1", actor=write_actor(ctx)
    )
    except edit.EditRefused as error:
        raise UsageError(str(error)) from None
    report["scope"] = scope.name
    return Result(report, _set_text(report))


def entry_index(ctx: Context) -> int | None:
    """The entry an append copies, from ``from=``; None means the schema skeleton."""
    raw = ctx.options.get("from")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        raise UsageError(f"from= needs an entry index, not {raw!r}") from None
    if value < 0:
        raise UsageError(f"from= cannot be negative: {raw!r}")
    return value


def declared_enum_values(scope: Scope) -> dict[str, set[str]]:
    """Enumeration values the documents of this project already declare.

    The packager validator learns values from the files instead of rejecting
    everything outside its own tables; an edit accepts the same set.
    """
    from core.enums import categories_of, split_value

    found: dict[str, set[str]] = {}
    for path in entity_files(scope):
        try:
            document = load_document(path)
        except FfError:
            continue
        for key_path, entry in flatten(document.table):
            if not isinstance(entry.value, str):
                continue
            for category in categories_of(document.root_tag, key_path):
                for part in split_value((category,), entry.value):
                    if part:
                        found.setdefault(category, set()).add(part)
    return found


def _set_text(report: dict) -> str:
    """Rows of one set invocation."""
    rows = [
        ["path", report["path"]],
        ["field", report["field"]],
        ["before", report["before"]],
        ["after", report["after"]],
        ["encoding", report["encoding"]],
        ["newline", report["newline"]],
        ["bytes", f"{report['bytes_before']} -> {report['bytes_after']}"],
    ]
    enum = report.get("enum") or {}
    if enum.get("category"):
        detail = f"{enum['category']}: {enum['values']} value(s)" if enum.get("table") else f"{enum['category']}: not checked"
        rows.append(["enum", detail])
    if report.get("event"):
        rows.append(["event", report["event"]])
    state = "written" if report["written"] else "not written (dry run)"
    return table_of(["item", "value"], rows, f"{report['path']}: {state}")


PATCH_KEYS = ("document", "field", "op", "value", "from")


def read_patch(path: Path) -> list[dict[str, str]]:
    """The ``[[edit]]`` entries of a batch patch, in the order they were written.

    The document is ordinary TOML, so the same parser reads it and a misplaced
    key is reported rather than ignored (docs/cli.md section 4.15).
    """
    source = textio.read_source(path)
    table = toml.parse(source.text, str(path))
    edits = table.get("edit")
    if edits is None:
        raise UsageError(f"{path.name}: no [[edit]] entry in the patch")
    if not isinstance(edits, TomlArrayEntry):
        raise UsageError(f"{path.name}: edit must be an array of tables, [[edit]]")
    found: list[dict[str, str]] = []
    for index, item in enumerate(edits.items, start=1):
        if not isinstance(item, TomlTable):
            raise UsageError(f"{path.name}: [[edit]] {index} is not a table")
        entry: dict[str, str] = {}
        for key, value in item.entries:
            if key not in PATCH_KEYS:
                raise UsageError(
                    f"{path.name}: [[edit]] {index} has an unknown key {key!r}; the keys are {', '.join(PATCH_KEYS)}"
                )
            entry[key] = str(value.value) if isinstance(value, TomlValue) else ""
        found.append(entry)
    if not found:
        raise UsageError(f"{path.name}: the patch has no [[edit]] entry")
    return found


def patch_index(name: str, index: int, raw: str | None) -> int | None:
    """The entry an append copies, from a patch ``from`` value."""
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        raise UsageError(f"{name}: [[edit]] {index}: from needs an entry index, not {raw!r}") from None
    if value < 0:
        raise UsageError(f"{name}: [[edit]] {index}: from cannot be negative: {raw!r}")
    return value


def cmd_batch(ctx: Context) -> Result:
    """Apply several field changes to several documents from one patch file.

    Every entry is planned against the text the earlier entries would leave behind, so
    one document can be changed more than once and is still written once.  Nothing is
    written until the whole patch has been planned: a refused entry aborts the batch
    and leaves every document as it was (docs/cli.md section 4.15).
    """
    from core import edit, enums as enums_core, journal

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; batch refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("batch needs --write; add --dry-run to inspect the changes without writing")
    raw = ctx.selector
    if raw in ("", "all"):
        raise UsageError("batch needs a patch file: batch <file>")
    patch = Path(raw)
    if not patch.is_absolute():
        patch = ctx.cwd / patch
    if not patch.is_file():
        raise UsageError(f"batch needs a patch file: {raw} is not there")
    edits = read_patch(patch)

    project_root = edit.project_root_of(scope.root)
    enums = enums_core.load_enums(project_root)
    declared = declared_enum_values(scope)
    order: list[Path] = []
    staged: dict[Path, dict] = {}
    rows: list[dict] = []
    for index, entry in enumerate(edits, start=1):
        document_name = entry.get("document", "")
        if not document_name:
            raise UsageError(f"{patch.name}: [[edit]] {index} needs document=<path>")
        field = entry.get("field", "")
        if not field:
            raise UsageError(f"{patch.name}: [[edit]] {index} needs field=<a.b.c>")
        op = entry.get("op") or "set"
        if op not in ("set", "append", "delete"):
            raise UsageError(f"{patch.name}: [[edit]] {index}: op is set, append or delete, not {op!r}")
        if op == "set" and "value" not in entry:
            raise UsageError(f"{patch.name}: [[edit]] {index} needs value=<text>")
        files = entity_files(scope, document_name)
        if len(files) != 1:
            raise UsageError(
                f"{patch.name}: [[edit]] {index}: {document_name!r} names {len(files)} file(s); name one document"
            )
        path = files[0]
        relative = relative_of(scope, path)
        if path in staged:
            # The earlier entries already decided what this file will hold, so
            # the next one plans against that text instead of what is on disk.
            source = staged[path]["after"]
            document = document_from_source(path, relative, source)
        else:
            warnings: list[str] = []
            source = textio.read_source(path, warnings)
            document = document_from_source(path, relative, source, warnings)
            order.append(path)
        try:
            if op == "set":
                plan = edit.plan_set(
                    document, field, entry["value"], enums=enums, declared=lambda: declared, source=source
                )
            else:
                plan = edit.plan_entry(
                    document, field, op, copy_from=patch_index(patch.name, index, entry.get("from")), source=source
                )
        except edit.EditRefused as error:
            raise UsageError(f"{patch.name}: [[edit]] {index}: {error}") from None
        data = plan.data
        had_bom = data.startswith(textio.BOM)
        body = data[len(textio.BOM):] if had_bom else data
        text, encoding = textio.decode_source(body, str(path))
        staged[path] = {
            "data": data,
            "entity": plan.entity,
            "after": textio.SourceText(
                path=path, text=textio.normalize_newlines(text), had_bom=had_bom, encoding=encoding, raw=text
            ),
        }
        rows.append(
            {
                "edit": index,
                "document": relative,
                "field": field,
                "op": op,
                "before": plan.before,
                "after": plan.after,
                "bytes": [plan.size_before, len(data)],
            }
        )

    dry_run = ctx.options.get("dry-run") == "1"
    written: list[dict] = []
    for path in order:
        record = staged[path]
        before = path.read_bytes()
        staged_plan = edit.DocumentPlan(
            result="set",
            path=path,
            relative=relative_of(scope, path),
            entity=record["entity"],
            data=record["data"],
            before=f"{len(before)} byte(s)",
            after=f"{len(record['data'])} byte(s)",
            digest_before=journal.digest_of(before),
            digest_after=journal.digest_of(record["data"]),
            bytes_before=len(before),
            before_data=before,
        )
        try:
            written.append(edit.apply_document(staged_plan, project_root, dry_run=dry_run, actor=write_actor(ctx)))
        except edit.EditRefused as error:
            raise UsageError(str(error)) from None

    limit = row_limit(ctx)
    shown = rows if limit is None else rows[:limit]
    payload = {
        "scope": scope.name,
        "patch": patch.name,
        "edits": len(edits),
        "documents": len(order),
        "dry_run": dry_run,
        "rows": shown,
        "shown": len(shown),
        "total": len(rows),
        "written": written,
        "ok": True,
    }
    return Result(payload, _batch_text(payload))


def _batch_text(payload: dict) -> str:
    """Rows of one batch invocation."""
    rows = [
        [str(item["edit"]), item["document"], item["field"], item["op"], item["before"], item["after"]]
        for item in payload["rows"]
    ]
    state = "planned for" if payload["dry_run"] else "written to"
    summary = (
        f"{tally(payload['shown'], payload['total'])} edit(s) {state} "
        f"{payload['documents']} document(s) from {payload['patch']}"
    )
    return table_of(["edit", "document", "field", "op", "before", "after"], rows, summary)


def cmd_log(ctx: Context) -> Result:
    """List the log segments of this project and the newest records inside them.

    ``document=``, ``field=``, ``actor=``, ``result=``, ``since=`` and ``until=``
    narrow which records are selected; ``limit=`` caps how many of the newest
    selected records are printed (docs/cli.md section 4.2).  ``since=`` and
    ``until=`` compare against the timestamp as written, so they share the
    offset of the machine that wrote the log.
    """
    from core import edit, journal

    project_root = edit.project_root_of(ctx.scope.root)
    limit = row_limit(ctx, default=LOG_ROWS)
    count = _count(ctx, default=0, name="log")
    if count:
        limit = count if limit is None else min(limit, count)
    filters = {
        "document": ctx.options.get("document"),
        "field": ctx.options.get("field"),
        "actor": ctx.options.get("actor"),
        "result": ctx.options.get("result"),
        "since": ctx.options.get("since"),
        "until": ctx.options.get("until"),
    }
    actor = filters["actor"]
    outcome = filters["result"]
    if actor is not None and actor not in journal.ACTORS:
        raise UsageError(f"actor= is {', '.join(journal.ACTORS[:-1])} or {journal.ACTORS[-1]}, not {actor!r}")
    if outcome is not None and outcome not in journal.RESULTS:
        raise UsageError(f"result= is {', '.join(journal.RESULTS[:-1])} or {journal.RESULTS[-1]}, not {outcome!r}")
    events = journal.read_events(project_root)
    found: dict[str, list[dict]] = {}
    for event in events:
        found.setdefault(str(event.get("segment", "")), []).append(event)
    selected = [event for event in events if _log_keeps(event, filters)]
    shown = selected if limit is None else selected[-limit:]
    segment_rows = [
        [
            name,
            sum(1 for event in items if _log_keeps(event, filters)),
            items[0].get("timestamp", ""),
            items[-1].get("timestamp", ""),
        ]
        for name, items in found.items()
    ]
    record_rows = [
        [
            event.get("timestamp", ""),
            event.get("result", ""),
            event.get("document", ""),
            event.get("field", ""),
            f"{event.get('before', '')} -> {event.get('after', '')}",
            event.get("id", ""),
        ]
        for event in shown
    ]
    summary = (
        f"{tally(len(shown), len(selected))} of {len(events)} record(s) in {len(found)} segment(s) "
        f"under {journal.EDITOR_DIR}/{journal.LOG_DIR}"
    )
    text = "\n\n".join(
        [
            table_of(["segment", "records", "first", "last"], segment_rows, summary),
            table_of(["time", "result", "document", "field", "before -> after", "id"], record_rows),
        ]
    )
    return Result(
        {
            "scope": ctx.scope.name,
            "root": str(project_root),
            "filters": {name: value for name, value in filters.items() if value is not None},
            "segments": [
                {"segment": name, "records": sum(1 for event in items if _log_keeps(event, filters))}
                for name, items in found.items()
            ],
            "events": shown,
            "shown": len(shown),
            "selected": len(selected),
            "total": len(events),
        },
        text,
    )


def _log_keeps(event: dict, filters: dict[str, str | None]) -> bool:
    """Whether one log record passes every filter that was given."""
    if filters["actor"] is not None and event.get("actor") != filters["actor"]:
        return False
    if filters["result"] is not None and event.get("result") != filters["result"]:
        return False
    if filters["document"] is not None and filters["document"] not in str(event.get("document", "")):
        return False
    if filters["field"] is not None and filters["field"] not in str(event.get("field", "")):
        return False
    stamp = str(event.get("timestamp", ""))
    if filters["since"] is not None and stamp < filters["since"]:
        return False
    if filters["until"] is not None and stamp > filters["until"]:
        return False
    return True


def cmd_undo(ctx: Context) -> Result:
    """Put back what the last writes replaced; needs --write."""
    return _restore(ctx, "undo")


def cmd_redo(ctx: Context) -> Result:
    """Re-apply what the last undo reverted; needs --write."""
    return _restore(ctx, "redo")


def _restore(ctx: Context, result: str) -> Result:
    """Run one undo or redo, or refuse it before anything is written."""
    from core import edit, history

    if ctx.scope.name == "Firefight":
        raise UsageError(f"the stock scope is read-only; {result} refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError(f"{result} needs --write; add --dry-run to inspect what would change")
    count = _count(ctx, default=1, name=result)
    project_root = edit.project_root_of(ctx.scope.root)
    try:
        restores = history.plan_undo(project_root, count) if result == "undo" else history.plan_redo(project_root, count)
        payload = history.apply(
            project_root, restores, dry_run=ctx.options.get("dry-run") == "1", actor=write_actor(ctx)
        )
    except edit.EditRefused as error:
        raise UsageError(str(error)) from None
    payload["scope"] = ctx.scope.name
    return Result(payload, _restore_text(payload))


def _restore_text(payload: dict) -> str:
    """Rows of one undo or redo invocation."""
    rows = [
        [item["document"], item["field"], item["before"], item["after"], item["event"], item["target"]]
        for item in payload["documents"]
    ]
    done = "undone" if payload["result"] == "undo" else "redone"
    summary = f"{payload['count']} document(s) {done}"
    if payload.get("dry_run"):
        summary += "; not written (dry run)"
    return table_of(["document", "field", "before", "after", "event", "target"], rows, summary)


def _count(ctx: Context, *, default: int, name: str) -> int:
    """The record or change count named by the selector, else ``default``."""
    selector = ctx.selector.strip()
    if not selector:
        return default
    if not selector.isdigit() or int(selector) < 1:
        raise UsageError(f"{name} takes a count of at least 1, not {selector!r}")
    return int(selector)


def cmd_convert(ctx: Context) -> Result:
    """Convert the selected source files into project working files under to=.

    A stock ``.txt`` entity becomes the ``.toml`` a project works with (UTF-8 without BOM,
    the canonical layout of the TOML writer); a file that is already there is skipped unless
    ``overwrite=1``.  ``assets=1`` also copies the scope's ``Images/`` and ``Sounds/`` trees
    byte for byte.  Nothing is written without ``--write`` (docs/cli.md section 4.3).
    """
    from core import journal

    scope = ctx.scope
    target = ctx.options.get("to")
    if not target:
        raise UsageError("convert needs a destination project: to=<directory>")
    if ctx.options.get("write") != "1":
        raise UsageError("convert needs --write; add --dry-run to inspect the result without writing")
    destination = Path(target)
    data_root = destination
    overwrite = ctx.options.get("overwrite") == "1"
    assets = ctx.options.get("assets") == "1"
    dry_run = ctx.options.get("dry-run") == "1"
    written: list[dict] = []
    copied: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    declared = declared_lists(scope)
    for path in filter_category(targets(ctx), ctx, scope):
        relative = relative_of(scope, path)
        if is_list_file(relative, declared, path):
            skipped.append({"path": relative, "reason": "list file"})
            continue
        out = data_root / Path(relative).with_suffix(SUFFIX_TOML)
        if out.exists() and not overwrite:
            skipped.append({"path": relative, "reason": "exists"})
            continue
        if dry_run:
            written.append({"path": relative, "out": str(out), "bytes": 0})
            continue
        try:
            document = load_document(path, relative)
            data = textio.encode_export(document.toml_text(), file=str(out), encoding="utf-8", newline="\r\n")
            out.parent.mkdir(parents=True, exist_ok=True)
            journal.write_atomic(out, data)
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        written.append({"path": relative, "out": str(out), "bytes": len(data)})
    if assets:
        for folder in ASSET_FOLDERS:
            source_root = scope.root / folder
            if not source_root.is_dir():
                continue
            for path in sorted(source_root.rglob("*")):
                if not path.is_file():
                    continue
                relative_asset = f"{folder}/{path.relative_to(source_root).as_posix()}"
                out = data_root / Path(relative_asset)
                if out.exists() and not overwrite:
                    skipped.append({"path": relative_asset, "reason": "exists"})
                    continue
                if dry_run:
                    copied.append({"path": relative_asset, "out": str(out), "bytes": 0})
                    continue
                data = path.read_bytes()
                out.parent.mkdir(parents=True, exist_ok=True)
                journal.write_atomic(out, data)
                copied.append({"path": relative_asset, "out": str(out), "bytes": len(data)})
    payload = {
        "scope": scope.name,
        "to": str(destination),
        "data_root": str(data_root),
        "count": len(written) + len(copied) + len(skipped) + len(errors),
        "written": len(written),
        "assets": len(copied),
        "skipped": len(skipped),
        "errors": errors,
        "files": written,
        "asset_files": copied,
        "skipped_files": skipped,
        "dry_run": dry_run,
    }
    return Result(payload, _convert_text(payload), 1 if errors else 0)


def cmd_settings(ctx: Context) -> Result:
    """Translate between the stock ``mod.txt`` and ``ModSetting.toml``.

    ``op=render`` (the default) turns the stock file the game loads into the project file,
    ``op=emit`` turns the project file back into the stock one.  Either way an existing
    target is skipped unless ``overwrite=1``, and nothing is written without ``--write``
    (docs/cli.md section 4.7).
    """
    from core import edit, settings

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; settings refuses to write under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("settings needs --write; add --dry-run to inspect the result without writing")
    op = ctx.options.get("op", "render")
    if op not in ("render", "emit"):
        raise UsageError(f"op= is render or emit, not {op!r}")
    project = scope.project
    stock = settings.source_path(project)
    if op == "render":
        source, target = stock, project / SETTING_FILE
    else:
        source, target = project / SETTING_FILE, stock
    if not source.is_file():
        raise UsageError(f"nothing to {op} from: {source} is not there")
    overwrite = ctx.options.get("overwrite") == "1"
    dry_run = ctx.options.get("dry-run") == "1"
    payload = {
        "scope": scope.name,
        "op": op,
        "from": str(source),
        "to": str(target),
        "skipped": False,
        "dry_run": dry_run,
    }
    if target.is_file() and not overwrite:
        return Result(payload | {"skipped": True}, _settings_text(payload | {"skipped": True}), 0)
    try:
        if op == "render":
            source_text = textio.read_source(source)
            table, warnings = settings.render(source_text.text, str(source))
            text = toml.render(table)
            plan = edit.plan_render(target, SETTING_FILE, text, entity="mod_setting")
        else:
            document = load_document(source, SETTING_FILE)
            text, warnings = settings.emit(edit.root_table(document.table, document.root_tag))
            newline, encoding = _stock_style(stock)
            plan = edit.plan_render(target, settings.MOD_TXT, text, entity="mod_setting", newline=newline, encoding=encoding)
        result = edit.apply_document(
        plan, edit.project_root_of(scope.root), dry_run=dry_run, actor=write_actor(ctx)
    )
    except FfError as error:
        raise UsageError(str(error)) from None
    payload = payload | result | {"warnings": len(warnings), "sample_warnings": warnings[:CHECK_SAMPLES]}
    return Result(payload, _settings_text(payload), 0)


def _stock_style(path: Path) -> tuple[str, str]:
    """The line ending and encoding a stock file already uses, or the model of the corpus.

    The shipped ``mod.txt`` files are UTF-8 with LF, so a project without one is written
    that way (docs/toml-mapping.md section 5).
    """
    if not path.is_file():
        return "\n", "utf-8"
    data = path.read_bytes()
    try:
        _, encoding = textio.decode_source(data, str(path))
    except FfError:
        encoding = "utf-8"
    return ("\r\n" if b"\r\n" in data else "\n"), encoding


def _settings_text(payload: dict) -> str:
    """One line for one settings render or emit."""
    if payload.get("skipped"):
        return f"{payload['to']}: already there; pass overwrite=1 to replace it"
    state = "would be written" if payload.get("dry_run") else "written"
    tail = f" [{payload['id']}]" if payload.get("id") else ""
    return f"{payload['to']}: {payload['bytes_after']} byte(s) {state} from {payload['from']}{tail}"


def _convert_text(payload: dict) -> str:
    """Rows of one convert invocation."""
    rows = [[item["path"], item["bytes"]] for item in payload["files"][:DEFAULT_LIMIT]]
    rows += [[item["path"], item["bytes"]] for item in payload["asset_files"][:DEFAULT_LIMIT]]
    rows += [[item["path"], f"skipped: {item['reason']}"] for item in payload["skipped_files"][:DEFAULT_LIMIT]]
    rows += [[item["path"], item["error"]] for item in payload["errors"][:DEFAULT_LIMIT]]
    state = "planned" if payload["dry_run"] else "written"
    summary = (
        f"{payload['written']} file(s) {state} to {payload['data_root']}, "
        f"{payload['assets']} asset(s), "
        f"{payload['skipped']} skipped, {len(payload['errors'])} error(s)"
    )
    return table_of(["path", "result"], rows, summary)


def cmd_pack(ctx: Context) -> Result:
    """Build the mod-zip the game installs (docs/cli.md section 4.8).

    Every managed document is rendered back to stock XML, ``ModSetting.toml`` becomes
    ``Mod/mod.txt``, unmanaged files are copied, and the archive is named after the
    project's ``ModInformation.toml``.  It goes to ``to=``, the project directory when that is not
    given; an archive that is already there is replaced unless ``overwrite=0``.  The whole
    package is rendered before anything is written.

    The project is checked first and the counts of load errors and dangling references go
    into the payload.  By default neither stops the pack, and a document that cannot be
    rendered is reported and left out of the archive; ``strict=1`` refuses instead, writing
    nothing while the project has a load error or a dangling reference.  A pack that writes
    appends one ``pack`` record to the project log, so the
    project keeps a note of what was built; a ``pack`` record names no document and nothing
    reverts it (docs/project-layout.md section 8).
    """
    from core import edit, pack as pack_core, settings as settings_core

    scope = ctx.scope
    if scope.name == "Firefight":
        raise UsageError("the stock scope is read-only; pack refuses to read under Firefight")
    if ctx.options.get("write") != "1":
        raise UsageError("pack needs --write; add --dry-run to inspect the package without writing")
    dry_run = ctx.options.get("dry-run") == "1"
    overwrite = ctx.options.get("overwrite", "1") == "1"
    limit = row_limit(ctx)
    project = edit.project_root_of(scope.root)

    manifest = project / pack_core.MANIFEST
    if not manifest.is_file():
        raise UsageError(f"pack needs {pack_core.MANIFEST} at the project root: {manifest}")
    found = pack_core.metadata(toml.parse(textio.read_source(manifest).text, str(manifest)))
    if not found.get("name"):
        raise UsageError(f"{manifest}: no [mod] name; the archive is named after it")
    archive = Path(ctx.options.get("to") or project) / pack_core.archive_name(
        found["name"], found.get("version_name", "")
    )

    strict = ctx.options.get("strict") == "1"
    checked = run_command(
        "check", Context(scope=scope, selector="", doc_path=(), options={}, cwd=ctx.cwd)
    )
    checked_errors = len(checked.payload.get("errors", []))
    dangling = int(checked.payload.get("dangling_total", 0))
    if strict and (checked_errors or dangling):
        raise UsageError(
            f"pack strict=1: the project has {checked_errors} load error(s) and "
            f"{dangling} dangling reference(s); nothing was written"
        )

    warnings: list[str] = []
    setting = project / pack_core.SETTING_FILE
    stock = project / pack_core.MOD_TXT
    setting_data: bytes | None = None
    if setting.is_file():
        newline, encoding = _stock_style(stock)
        source = textio.read_source(setting)
        inner = edit.root_table(toml.parse(source.text, str(setting)), "mod_setting")
        rendered, emitted = settings_core.emit(inner, newline=newline)
        setting_data = textio.encode_export(
            rendered, file=pack_core.MOD_TXT, encoding=encoding, newline=""
        )
        if stock.is_file() and stock.read_bytes() != setting_data:
            # Both directions are offered: changing mod.txt carries the content the settings
            # file does not hold, while changing the settings file carries what mod.txt has.
            raise UsageError(
                f"{stock}: {stock.stat().st_size} bytes on disk, {len(setting_data)} rendered from "
                f"{pack_core.SETTING_FILE}; the two disagree, so one of them would be lost. "
                f"Run 'settings op=emit --write overwrite=1' to rewrite mod.txt from the settings "
                f"file, or 'settings op=render --write overwrite=1' to rewrite the settings file "
                f"from mod.txt, then pack again"
            )
        warnings.extend(emitted)

    pieces, skipped = pack_core.plan(project)
    members: list[tuple[str, bytes]] = []
    errors: list[dict] = []
    for piece in pieces:
        if not piece.rendered:
            members.append((piece.name, piece.path.read_bytes()))
            continue
        relative = piece.path.relative_to(project).as_posix()
        try:
            text, encoding, item_warnings, newline = _export_text(piece.path, relative)
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        twin = piece.path.with_suffix(SUFFIX_XML)
        if twin.is_file():
            encoding = textio.read_source(twin).encoding
        warnings.extend(item_warnings)
        members.append(
            (
                piece.name,
                textio.encode_export(text, file=piece.name, encoding=encoding, newline=newline),
            )
        )
    if setting_data is not None:
        members.append((f"{pack_core.MOD_FOLDER}/{pack_core.MOD_TXT}", setting_data))
    members.sort(key=lambda member: member[0])

    if errors and strict:
        rows = [[item["path"], item["error"]] for item in errors]
        return Result(
            {
                "scope": scope.name,
                "project": str(project),
                "archive": str(archive),
                "dry_run": dry_run,
                "count": 0,
                "shown": 0,
                "files": [],
                "content_bytes": 0,
                "archive_bytes": 0,
                "skipped": list(skipped),
                "warnings": warnings,
                "errors": errors,
            },
            table_of(
                ["path", "error"],
                rows,
                f"pack strict=1: {len(errors)} document(s) could not be rendered; nothing was written",
            ),
            1,
        )
    # Without strict=1 a document that cannot be rendered is reported and left out of the
    # archive instead of stopping the pack (docs/cli.md section 4.8).
    warnings.extend(f"{item['path']}: {item['error']}" for item in errors)

    content_bytes = sum(len(data) for _, data in members)
    left_alone: list[dict] = []
    archive_bytes = 0
    recorded: dict | None = None
    if archive.exists() and not overwrite:
        left_alone.append(
            {"path": str(archive), "reason": "already there; pass overwrite=1 to replace it"}
        )
        state = "left alone"
    elif dry_run:
        state = "planned for"
    else:
        archive_bytes = pack_core.build(members, archive)
        state = "written to"
        recorded = journal.append(
            project,
            {
                "actor": write_actor(ctx),
                "result": "pack",
                "target": None,
                "document": "",
                "entity": "",
                "field": "",
                "before": "",
                "after": f"{len(members)} member(s) in {archive.name}",
                "digest_before": "",
                "digest_after": "",
                "bytes_before": 0,
                "bytes_after": archive_bytes,
                "dry_run": False,
            },
        )

    shown = members if limit is None else members[:limit]
    rows = [[name, len(data)] for name, data in shown]
    summary = (
        f"{len(members)} member(s) {state} {archive} "
        f"({content_bytes} bytes rendered, {archive_bytes} on disk), "
        f"{len(skipped) + len(left_alone)} file(s) skipped; "
        f"check: {checked_errors} error(s), {dangling} dangling reference(s)"
    )
    # A count is not enough: what was left out and what was reported has to be readable here,
    # or a dropped .txt twin and a document that could not be rendered stay invisible.
    notes = [f"skipped: {item['path']} ({item['reason']})" for item in [*skipped, *left_alone]]
    notes += [f"warning: {item}" for item in warnings]
    text = table_of(["member", "bytes"], rows, summary)
    if notes:
        text += "\n\n" + "\n".join(notes)
    return Result(
        {
            "scope": scope.name,
            "project": str(project),
            "archive": str(archive),
            "dry_run": dry_run,
            "count": len(members),
            "shown": len(shown),
            "files": [{"name": name, "bytes": len(data)} for name, data in shown],
            "content_bytes": content_bytes,
            "archive_bytes": archive_bytes,
            "recorded": recorded["id"] if recorded else "",
            "skipped": list(skipped) + left_alone,
            "warnings": warnings,
            "check": {"errors": checked_errors, "dangling": dangling},
            "errors": errors,
        },
        text,
        0,
    )


def cmd_export(ctx: Context) -> Result:
    """Render the selected entities as stock XML under the directory in to=.

    The destination is a rendered copy, so a file that is already there is
    replaced; ``overwrite=0`` leaves it alone instead and counts it as skipped.
    ``--dry-run`` renders every selected document and writes nothing
    (docs/cli.md section 4).
    """
    scope = ctx.scope
    target = ctx.options.get("to")
    if not target:
        raise UsageError("export needs a destination: to=<directory>")
    destination = Path(target)
    dry_run = ctx.options.get("dry-run") == "1"
    overwrite = ctx.options.get("overwrite", "1") == "1"
    limit = row_limit(ctx)
    files = filter_category(targets(ctx), ctx, scope)
    written: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    for path in files:
        relative = relative_of(scope, path)
        out = destination / relative
        try:
            text, encoding, warnings, newline = _export_text(path, relative)
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        if out.exists() and not overwrite:
            skipped.append({"path": relative, "out": str(out), "reason": "already there"})
            continue
        data = textio.encode_export(text, file=str(out), encoding=encoding, newline=newline)
        if not dry_run:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        written.append(
            {"path": relative, "out": str(out), "bytes": len(data), "warnings": warnings}
        )
    state = "planned for" if dry_run else "written to"
    summary = (
        f"{len(written)} file(s) {state} {destination}, {len(skipped)} skipped, {len(errors)} error(s)"
    )
    shown = written if limit is None else written[:limit]
    rows = [[item["path"], item["bytes"]] for item in shown]
    text = table_of(["path", "bytes"], rows, summary)
    return Result(
        {
            "scope": scope.name,
            "to": str(destination),
            "dry_run": dry_run,
            "count": len(written),
            "shown": len(shown),
            "files": shown,
            "skipped": skipped,
            "errors": errors,
        },
        text,
        1 if errors else 0,
    )


def _export_text(path: Path, relative: str) -> tuple[str, str, list[str], str]:
    """Stock XML for one entity, its source encoding and the ending to write.

    A plain list (no XML at all) is copied exactly as it stands; an entity is
    rendered with the layout the reader captured.  Either way the file keeps its
    own line endings, so an untouched source exports byte for byte (docs/toml-mapping.md
    section 5).
    """
    source = textio.read_source(path)
    if path.suffix.lower() == ".txt":
        try:
            xml.parse(source.text, relative)
        except FfError:
            return source.raw, source.encoding, [], ""
    warnings: list[str] = []
    document = load_document(path, relative)
    return document.xml_text(warnings), document.encoding, list(document.warnings) + warnings, ""


# --- diff and the round-trip check ------------------------------------------


def stock_text(document: Document) -> str:
    """The stock XML form of a document, whatever it is stored as.

    Both sides of a comparison go through this, so a project ``.toml`` and the
    ``.txt`` it was converted from are compared in the same shape.
    """
    return document.xml_text()


def normalized(text: str) -> str:
    """Text with one newline style, for a comparison that is about content."""
    return textio.normalize_newlines(text)


def first_difference(left: str, right: str) -> str:
    """The first line that differs, named by its number."""
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    for index in range(max(len(left_lines), len(right_lines))):
        here = left_lines[index] if index < len(left_lines) else None
        there = right_lines[index] if index < len(right_lines) else None
        if here != there:
            return f"line {index + 1}: {here!r} -> {there!r}"
    return ""


def diff_lines(
    left: str, right: str, left_label: str, right_label: str, limit: int | None
) -> list[str]:
    """Unified line diff of two texts, the body capped at ``limit`` lines."""
    rows = list(
        difflib.unified_diff(
            left.splitlines(), right.splitlines(), left_label, right_label, lineterm=""
        )
    )
    return rows if limit is None else rows[:limit]


def split_side(raw: str, ctx: Context) -> tuple[Scope, str]:
    """Split ``scope:path`` into a scope and a scope-relative path.

    A one-letter name before the colon is a drive letter rather than a scope, so
    an absolute Windows path stays a path (docs/cli.md section 4.10).
    """
    if ":" in raw:
        name, rest = raw.split(":", 1)
        if len(name) > 1 and all(character.isalnum() or character in "_-" for character in name):
            if name == ctx.scope.name:
                return ctx.scope, rest
            # The sides name their own files; the diff's own options are not roots.
            options = {
                key: value
                for key, value in ctx.options.items()
                if key not in ("left", "right", "root", "mod")
            }
            return resolve_scope(name, options, ctx.cwd), rest
    return ctx.scope, raw


def side_files(scope: Scope, relative: str) -> tuple[list[Path], bool]:
    """The files one side of a diff names, and whether that side is a directory."""
    wanted = relative.replace("\\", "/").strip("/")
    candidate = scope.root if wanted in ("", ".") else scope.root / wanted
    if candidate.is_file():
        return [candidate], False
    if not candidate.is_dir():
        raise UsageError(f"nothing at {relative!r} in scope {scope.name}")
    prefix = "" if wanted in ("", ".") else wanted + "/"
    found = [path for path in entity_files(scope) if relative_of(scope, path).startswith(prefix)]
    return found, True


def side_label(scope: Scope, relative: str) -> str:
    """``Mod:Data/Weapons/X.toml``; an absolute path inside the scope loses its root."""
    wanted = relative.replace(chr(92), "/").strip("/")
    root = scope.root.as_posix().rstrip("/")
    if wanted.startswith(root + "/"):
        wanted = wanted[len(root) + 1 :]
    return f"{scope.name}:{wanted}"


# A working file wins over the stock file it came from when both are present.
SUFFIX_ORDER = {".toml": 0, ".xml": 1, ".txt": 2}


def stem_key(scope: Scope, path: Path) -> str:
    """The entity path without its suffix, so ``X.txt`` and ``X.toml`` line up."""
    return relative_of(scope, path).rsplit(".", 1)[0]


def tree_index(scope: Scope, paths: list[Path]) -> dict[str, Path]:
    """One entry per entity path, preferring the working file over the source."""
    index: dict[str, Path] = {}
    for path in sorted(
        paths,
        key=lambda item: (
            stem_key(scope, item),
            SUFFIX_ORDER.get(item.suffix.lower(), 9),
            relative_of(scope, item),
        ),
    ):
        index.setdefault(stem_key(scope, path), path)
    return index


def stock_text_of(path: Path, relative: str) -> tuple[str, str]:
    """Stock XML for one document, or the reason it could not be read."""
    try:
        return normalized(stock_text(load_document(path, relative))), ""
    except FfError as error:
        return "", str(error)


def cmd_verify(ctx: Context) -> Result:
    """Read every selected document back and report what does not survive the trip.

    A stock XML file is compared with the layout the editor writes back, which is
    the layout the reader captured: a comment the reader drops shows up here.  A
    TOML file is written back as stock XML, read again and compared as TOML, so a
    file the editor only edits in place is not called lossy for its layout.  Line
    endings are normalised first.  A clean run over a converted project is what
    says the conversion can be packed back to what it came from (docs/cli.md
    section 4.11).
    """
    limit = row_limit(ctx)
    declared = declared_lists(ctx.scope)
    items: list[dict[str, object]] = []
    for path in targets(ctx):
        relative = relative_of(ctx.scope, path)
        if is_list_file(relative, declared, path):
            # A plain-text table is never parsed, so it is copied back as it stands.
            items.append(
                {
                    "path": relative,
                    "format": "list",
                    "result": "same",
                    "first_difference": "",
                    "warnings": [],
                }
            )
            continue
        try:
            document = load_document(path, relative)
        except FfError as error:
            items.append(
                {
                    "path": relative,
                    "format": "",
                    "result": "unreadable",
                    "first_difference": str(error),
                    "warnings": [],
                }
            )
            continue
        source = normalized(document.text)
        if document.format == "toml":
            # A TOML file is written back as stock XML; reading that back and
            # comparing the two TOML renderings leaves only content differences,
            # so a file the editor never rewrote in full is not called lossy.
            try:
                rebuilt = convert.xml_to_toml(
                    xml.parse(document.xml_text(), relative), schema_for(document.root_tag)
                )
            except FfError as error:
                items.append(
                    {
                        "path": relative,
                        "format": document.format,
                        "result": "unreadable",
                        "first_difference": str(error),
                        "warnings": list(document.warnings),
                    }
                )
                continue
            source = normalized(toml.render(document.table))
            rendered = normalized(toml.render(rebuilt))
        else:
            rendered = normalized(document.xml_text())
        same = source == rendered
        items.append(
            {
                "path": relative,
                "format": document.format,
                "result": "same" if same else "differs",
                "first_difference": "" if same else first_difference(source, rendered),
                "warnings": list(document.warnings),
            }
        )
    differ = [item for item in items if item["result"] != "same"]
    shown = differ if limit is None else differ[:limit]
    summary = (
        f"all {len(items)} document(s) round-trip without loss"
        if items and not differ
        else f"{tally(len(differ), len(items))} document(s) do not round-trip"
    )
    text = summary
    if shown:
        rows = [
            [str(item["path"]), str(item["format"]), str(item["first_difference"])]
            for item in shown
        ]
        text = table_of(["file", "format", "first difference"], rows, summary)
    payload = {
        "scope": ctx.scope.name,
        "root": str(ctx.scope.root),
        "files": len(items),
        "same": len(items) - len(differ),
        "differ": len(differ),
        "items": shown,
        "shown": len(shown),
        "total": len(differ),
        "ok": not differ,
    }
    return Result(payload, text, 1 if differ else 0)


def cmd_diff(ctx: Context) -> Result:
    """Compare two documents, or two trees lined up by their entity paths.

    Both sides are rendered as stock XML first, so a project TOML and the file it
    was converted from compare in the same shape; two directories are lined up by
    entity path with the suffix dropped.  A difference of any kind — content, or a
    document only one side carries — makes the exit code non-zero
    (docs/cli.md section 4.10).
    """
    left_raw = ctx.options.get("left", "")
    right_raw = ctx.options.get("right", "")
    if not left_raw or not right_raw:
        raise UsageError("diff needs both sides: left=<scope:path> right=<scope:path>")
    left_scope, left_relative = split_side(left_raw, ctx)
    right_scope, right_relative = split_side(right_raw, ctx)
    left_files, left_is_dir = side_files(left_scope, left_relative)
    right_files, right_is_dir = side_files(right_scope, right_relative)
    if left_is_dir != right_is_dir:
        raise UsageError("diff compares two files or two directories, not one of each")
    limit = row_limit(ctx)
    if not left_is_dir:
        return _diff_documents(
            ctx, left_scope, left_relative, left_files[0], right_scope, right_relative, right_files[0], limit
        )
    return _diff_trees(ctx, left_scope, left_files, right_scope, right_files, limit)


def _diff_documents(
    ctx: Context,
    left_scope: Scope,
    left_relative: str,
    left_path: Path,
    right_scope: Scope,
    right_relative: str,
    right_path: Path,
    limit: int | None,
) -> Result:
    """Line diff of two single documents, rendered in the stock shape first."""
    left_label = side_label(left_scope, left_relative)
    right_label = side_label(right_scope, right_relative)
    left, left_error = stock_text_of(left_path, relative_of(left_scope, left_path))
    right, right_error = stock_text_of(right_path, relative_of(right_scope, right_path))
    errors = {left_label: left_error, right_label: right_error}
    if left_error or right_error:
        text = "\n".join(f"{name}: {error}" for name, error in errors.items() if error)
        return Result(
            {
                "scope": ctx.scope.name,
                "left": left_label,
                "right": right_label,
                "same": False,
                "errors": {name: error for name, error in errors.items() if error},
                "ok": False,
            },
            text,
            2,
        )
    same = left == right
    text = f"{left_label} and {right_label} carry the same document"
    if not same:
        text = "\n".join(diff_lines(left, right, left_label, right_label, limit))
    payload = {
        "scope": ctx.scope.name,
        "left": left_label,
        "right": right_label,
        "same": same,
        "first_difference": "" if same else first_difference(left, right),
        "ok": same,
    }
    return Result(payload, text, 0 if same else 1)


def _diff_trees(
    ctx: Context,
    left_scope: Scope,
    left_paths: list[Path],
    right_scope: Scope,
    right_paths: list[Path],
    limit: int | None,
) -> Result:
    """Directory diff, lining the two sides up by entity path."""
    left = tree_index(left_scope, left_paths)
    right = tree_index(right_scope, right_paths)
    identical = 0
    differs: list[dict[str, str]] = []
    only_left: list[str] = []
    only_right: list[str] = []
    for key in sorted(set(left) | set(right)):
        if key not in left:
            only_right.append(key)
            continue
        if key not in right:
            only_left.append(key)
            continue
        here, here_error = stock_text_of(left[key], relative_of(left_scope, left[key]))
        there, there_error = stock_text_of(right[key], relative_of(right_scope, right[key]))
        if here_error or there_error:
            differs.append({"path": key, "first_difference": here_error or there_error})
            continue
        if here == there:
            identical += 1
            continue
        differs.append({"path": key, "first_difference": first_difference(here, there)})
    rows = [[item["path"], "differs", item["first_difference"]] for item in differs]
    rows.extend([key, "only on the left", ""] for key in only_left)
    rows.extend([key, "only on the right", ""] for key in only_right)
    summary = (
        f"{identical} identical, {len(differs)} differ(s), "
        f"{len(only_left)} only on the left, {len(only_right)} only on the right"
    )
    shown = rows if limit is None else rows[:limit]
    ok = not differs and not only_left and not only_right
    text = table_of(["document", "result", "first difference"], shown, summary) if shown else summary
    payload = {
        "scope": ctx.scope.name,
        "left": side_label(left_scope, str(left_scope.root)),
        "right": side_label(right_scope, str(right_scope.root)),
        "identical": identical,
        "differs": differs,
        "only_left": only_left,
        "only_right": only_right,
        "shown": shown,
        "ok": ok,
    }
    return Result(payload, text, 0 if ok else 1)


def schema_fields(root_tag: str, table) -> list[dict]:
    """Every declared field under one root element, in canonical emission order.

    ``table`` is the loaded enum table; a field whose path has enum categories carries
    the first category name and how many values that category holds, which is what a
    ``set`` reports as its hint (docs/cli.md section 4.13).
    """
    from core import enums as enums_core

    declared = schema_for(root_tag)
    if declared is None:
        return []
    fields: list[dict] = []

    def walk(node, prefix: tuple[str, ...]) -> None:
        for child in node.children:
            path = (*prefix, child.name)
            categories = enums_core.categories_of(root_tag, path)
            fields.append(
                {
                    "path": ".".join(path),
                    "shape": child.shape,
                    "type": child.type,
                    "required": child.required,
                    "enum": categories[0] if categories else "",
                    "values": table.table_size(categories) if categories else 0,
                }
            )
            if child.shape in ("table", "array"):
                walk(child, (*path[:-1], f"{child.name}[]") if child.shape == "array" else path)

    walk(declared.root, (root_tag,))
    return fields


def cmd_schema(ctx: Context) -> Result:
    """List the declared fields and enum values of one root element; read-only.

    ``schema weapon`` walks the declaration the editor validates against, so a document
    can be filled in without guessing from a sample; ``schema enum=country`` lists one
    enum table (docs/cli.md section 4.13).
    """
    from core import enums as enums_core

    table = enums_core.load_enums(ctx.scope.project)
    name = (ctx.options.get("enum") or "").strip()
    if name:
        values = sorted(table.values.get(name, ()))
        limit = row_limit(ctx)
        shown = values if limit is None else values[:limit]
        payload = {
            "enum": name,
            "table": bool(values),
            "count": len(values),
            "shown": len(shown),
            "values": shown,
            "source": table.source,
        }
        return Result(
            payload,
            table_of(
                ["value"],
                [[value] for value in shown],
                f"{name}: {tally(len(shown), len(values))} value(s)",
            ),
        )
    root_tag = (ctx.selector or "").strip()
    known = ", ".join(sorted(set(SCHEMAS) | set(PROJECT_SCHEMAS)))
    if not root_tag:
        raise UsageError(f"schema needs a root element or enum=<name>; the editor knows {known}")
    fields = schema_fields(root_tag, table)
    if not fields:
        raise UsageError(f"no schema for {root_tag!r}; the editor knows {known}")
    limit = row_limit(ctx)
    shown = fields if limit is None else fields[:limit]
    payload = {
        "root": root_tag,
        "count": len(fields),
        "shown": len(shown),
        "fields": shown,
        "required": [item["path"] for item in fields if item["required"]],
    }
    rows = [
        [
            item["path"],
            item["shape"],
            item["type"],
            "yes" if item["required"] else "-",
            f"{item['enum']} ({item['values']})" if item["enum"] else "-",
        ]
        for item in shown
    ]
    return Result(
        payload,
        table_of(
            ["field", "shape", "type", "required", "enum"],
            rows,
            f"{root_tag}: {tally(len(shown), len(fields))} field(s)",
        ),
    )


def roster_paths(scope: Scope) -> list[tuple[str, Path]]:
    """The roster files the project declares and that are on disk, in path order.

    A roster is found by its file name: the project settings declare ``equipment_russian.txt``
    and the file may sit anywhere under the project (docs/cli.md section 4.14).
    """
    declared = declared_lists(scope)
    if not declared:
        return []
    found = []
    for path in sorted(scope.root.rglob("*")):
        if path.is_file() and path.name in declared:
            found.append((relative_of(scope, path), path))
    return found


def roster_file(scope: Scope, selector: str) -> tuple[str, Path]:
    """The one roster a selector names, by relative path, file name or file stem."""
    wanted = selector.strip().replace("\\", "/").rstrip("/")
    for relative, path in roster_paths(scope):
        if wanted in (relative, path.name) or Path(relative).stem == wanted:
            return relative, path
    known = ", ".join(relative for relative, _ in roster_paths(scope)) or "nothing"
    raise UsageError(f"no declared roster named {selector!r}; the project has {known}")


def roster_documents(scope: Scope) -> dict[str, str]:
    """The documents a roster entry can name, keyed by file stem.

    Only units live in a roster: a weapon and an engine sound are pulled in by the document that
    uses them, so counting them as unlisted would report every one of them as an orphan.
    """
    found: dict[str, str] = {}
    for path in entity_files(scope, "all"):
        if category_of_path(relative_of(scope, path)) in ROSTER_CATEGORIES:
            found[path.stem] = relative_of(scope, path)
    return found


def cmd_roster(ctx: Context) -> Result:
    """Read and edit the rosters the project declares; writes need --write.

    A roster decides whether a unit reaches the game: the file lists document names, and a name
    with no document behind it is a hole the game shows as a missing unit.  ``check`` reports
    both directions — entries no document answers, and documents no roster names
    (docs/cli.md section 4.14).
    """
    from core import edit, roster
    from core.web import tables

    scope = ctx.scope
    selector = (ctx.selector or "").strip()
    op = (ctx.options.get("op") or "").strip()
    limit = row_limit(ctx)

    if selector == "check" and not op:
        listed: dict[str, list[str]] = {}
        for relative, path in roster_paths(scope):
            listed[relative] = roster.names(roster.parse(textio.read_source(path).text))
        found = roster.gaps(listed, roster_documents(scope))
        missing = found["missing"]
        orphans = found["orphans"]
        shown_missing = missing if limit is None else missing[:limit]
        shown_orphans = orphans if limit is None else orphans[:limit]
        rows = [[item["roster"], item["name"], "no document"] for item in shown_missing]
        rows += [[item["name"], "", "no roster names it"] for item in shown_orphans]
        payload = {
            "scope": scope.name,
            "count": len(missing) + len(orphans),
            "shown": len(rows),
            "total": len(rows),
            "rosters": len(listed),
            "entries": sum(len(entries) for entries in listed.values()),
            "missing": shown_missing,
            "missing_total": len(missing),
            "orphans": shown_orphans,
            "orphans_total": len(orphans),
            "ok": not missing and not orphans,
        }
        return Result(
            payload,
            table_of(
                ["roster", "entry", "problem"],
                rows,
                f"rosters: {len(listed)} file(s), {tally(len(rows), payload['count'])} problem(s)",
            ),
            1 if not payload["ok"] else 0,
        )

    if not selector:
        if op:
            raise UsageError(f"roster op={op} needs the roster to write to, e.g. roster equipment_russian.txt op={op}")
        files = roster_paths(scope)
        rows = []
        counted = []
        for relative, path in files:
            entries = roster.names(roster.parse(textio.read_source(path).text))
            counted.append({"path": relative, "entries": len(entries)})
            rows.append([relative, str(len(entries)), path.name])
        payload = {
            "scope": scope.name,
            "count": len(files),
            "shown": len(rows),
            "files": counted,
        }
        return Result(
            payload,
            table_of(
                ["roster", "entries", "path"],
                rows,
                f"{len(files)} roster file(s) with {sum(item['entries'] for item in counted)} entry(ies)"
                if files
                else "the project declares no roster",
            ),
        )

    relative, path = roster_file(scope, selector)
    rows = roster.parse(textio.read_source(path).text)
    entries = roster.names(rows)

    if not op:
        section = (ctx.options.get("section") or "").strip()
        kept = [
            row
            for row in rows
            if not row["blank"] and (not section or row["group"] == section or row["note"] == section)
        ]
        shown = kept if limit is None else kept[:limit]
        payload = {
            "scope": scope.name,
            "path": relative,
            "section": section,
            "count": len(entries),
            "entries": len(kept),
            "shown": len(shown),
            "total": len(kept),
            "lines": shown,
            "names": [row["value"] for row in shown],
        }
        return Result(
            payload,
            table_of(
                ["line", "entry", "group", "note"],
                [[str(row["line"]), row["value"], row["group"], row["note"]] for row in shown],
                f"{relative}: {tally(len(shown), len(kept))} entry of {len(entries)}",
            ),
        )

    if op not in ("add", "remove", "set"):
        raise UsageError(f"op is add, remove or set, not {op!r}")
    if ctx.options.get("write") != "1":
        raise UsageError(
            f"roster op={op} needs --write; add --dry-run to inspect the change without writing"
        )

    value = (ctx.options.get("value") or "").strip()
    line_option = ctx.options.get("line")
    if op == "add" and not value:
        raise UsageError("roster op=add needs value=<the document name to list>")
    if op in ("remove", "set") and not value and not line_option:
        raise UsageError(f"roster op={op} needs value=<name> or line=<number>")
    if op == "set" and not (ctx.options.get("as") or "").strip():
        raise UsageError("roster op=set needs as=<the new document name>")

    lines, encoding, newline = tables.read_rows(path)
    if op == "add":
        if value in entries:
            raise UsageError(f"{value!r} is already on line {roster.line_of(rows, value)} of {relative}")
        target = int(line_option) if line_option else len(lines) + 1
        if target < 1 or target > len(lines) + 1:
            raise UsageError(f"line {target} is not in 1..{len(lines) + 1}")
        if target <= len(lines):
            lines.insert(target - 1, value + newline)
        else:
            if lines and tables.ending(lines[-1]) == "":
                lines[-1] = lines[-1] + newline
            lines.append(value + newline)
        before, after = "", value
    elif op == "set":
        target = int(line_option) if line_option else roster.line_of(rows, value)
        if not target:
            raise UsageError(f"{value!r} is not in {relative}")
        if target < 1 or target > len(lines):
            raise UsageError(f"line {target} is not in 1..{len(lines)}")
        # Only the entry changes: the trailing note, the spacing before it and the ending stay,
        # because a note names the group the entry belongs to.
        raw = lines[target - 1]
        ending = tables.ending(raw)
        body = raw[: len(raw) - len(ending)] if ending else raw
        entry_text, marker, note = body.partition(roster.COMMENT)
        spacing = entry_text[len(entry_text.rstrip()) :]
        new_value = (ctx.options.get("as") or "").strip()
        lines[target - 1] = new_value + spacing + marker + note + ending
        before, after = rows[target - 1]["value"], new_value
    else:
        target = int(line_option) if line_option else roster.line_of(rows, value)
        if not target:
            raise UsageError(f"{value!r} is not in {relative}")
        try:
            lines, before, after = tables.row_change(lines, "delete", target, "", newline)
        except ValueError as error:
            raise UsageError(str(error)) from None
        after = ""

    data = path.read_bytes()
    had_bom = data.startswith(textio.BOM)
    project_root = edit.project_root_of(scope.root)
    # A roster is a plain-text list, so there is no entity document to read: the file name is
    # what the journal records.
    plan = edit.plan_render(
        path,
        relative,
        tables.encode(lines, encoding, had_bom),
        entity=path.stem,
        newline="",
        encoding=encoding,
    )
    try:
        applied = edit.apply_document(
            plan,
            project_root,
            dry_run=ctx.options.get("dry-run") == "1",
            actor=write_actor(ctx),
        )
    except edit.EditRefused as error:
        raise UsageError(str(error)) from None
    payload = {
        "scope": scope.name,
        "path": relative,
        "op": op,
        "line": target,
        "before": before,
        "after": after,
        "entries": len(entries) + (1 if op == "add" else -1 if op == "remove" else 0),
        **applied,
    }
    dry = ctx.options.get("dry-run") == "1"
    state = "would be" if dry else "is"
    detail = f"{value!r} -> {after!r}" if op == "set" else f"{value!r}"
    return Result(
        payload,
        f"{relative}: {detail} {state} on line {target} ({payload.get('bytes_before')} -> "
        f"{payload.get('bytes_after')} bytes, result={op}, actor={write_actor(ctx)})",
    )


# --- combined commands -----------------------------------------------------

DRY_RUNNABLE = frozenset({
    "add", "batch", "clone", "convert", "export", "import", "index", "init", "pack",
    "redo", "remove", "roster", "set", "settings", "undo",
})
STEP_KEYS = ("command", "selector", "with")


def run_sequence(ctx: Context, steps: list[dict]) -> Result:
    """Run the steps in order, stopping at the first one that reports a failure.

    A step is a dict with a command, an optional selector and its options. Under --dry-run
    every step that can report without writing is switched to its own dry run, so one
    invocation shows the whole sequence without touching a file.
    """
    dry_run = ctx.options.get("dry-run") == "1"
    done: list[dict] = []
    stopped = ""
    for step in steps:
        command = step["command"]
        options = dict(step.get("options") or {})
        if dry_run and command in DRY_RUNNABLE:
            options["write"] = "1"
            options["dry-run"] = "1"
        if step.get("scope_root"):
            scope = resolve_scope("Mod", {"root": step["scope_root"]}, ctx.cwd)
        else:
            scope = ctx.scope
        inner = Context(scope=scope, selector=step.get("selector", ""), doc_path=(),
                        options=options, cwd=ctx.cwd)
        try:
            result = run_command(command, inner)
            code, output = result.code, result.text or ""
        except (UsageError, FfError) as error:
            code, output = 2, str(error)
        lines = [line for line in output.splitlines() if line.strip()]
        done.append({
            "command": command,
            "selector": step.get("selector", ""),
            "code": code,
            "result": lines[-1].strip() if lines else "",
        })
        if code != 0:
            stopped = command
            break
    rows = [[str(index), item["command"], str(item["code"]), item["result"]]
            for index, item in enumerate(done, 1)]
    if stopped:
        summary = f"{len(done)} step(s) run, stopped at {stopped}"
    elif dry_run:
        summary = f"{len(done)} step(s) planned, nothing written"
    else:
        summary = f"{len(done)} step(s) run"
    payload = {
        "scope": ctx.scope.name,
        "steps": done,
        "count": len(done),
        "stopped": stopped,
        "dry_run": dry_run,
        "ok": not stopped,
    }
    return Result(payload, table_of(["step", "command", "code", "result"], rows, summary),
                  code=1 if stopped else 0)


def cmd_build(ctx: Context) -> Result:
    """index, check and pack in one run (docs/cli.md section 4.17)."""
    to = ctx.options.get("to")
    if not to:
        raise UsageError("build needs a destination directory: to=<directory>")
    return run_sequence(ctx, [
        {"command": "index", "options": {"write": "1"}},
        {"command": "check"},
        {"command": "pack", "options": {"to": to, "write": "1"}},
    ])


def cmd_audit(ctx: Context) -> Result:
    """Read every document back, then check with both gates on (docs/cli.md section 4.17)."""
    return run_sequence(ctx, [
        {"command": "verify"},
        {"command": "check", "options": {"assets": "1", "rosters": "1"}},
    ])


def cmd_adopt(ctx: Context) -> Result:
    """Import a tree or a zip as a project, then index it (docs/cli.md section 4.17)."""
    to = ctx.options.get("to")
    if not to:
        raise UsageError("adopt needs a destination directory: to=<directory>")
    return run_sequence(ctx, [
        {"command": "import", "selector": ctx.selector, "options": {"to": to, "write": "1"}},
        {"command": "index", "options": {"write": "1"}, "scope_root": to},
    ])


def cmd_unpack(ctx: Context) -> Result:
    """Write the project back out as the original XML and text (docs/cli.md section 4.17)."""
    to = ctx.options.get("to")
    if not to:
        raise UsageError("unpack needs a destination directory: to=<directory>")
    steps = [{"command": "export", "options": {"to": to, "write": "1"}}]
    if (ctx.scope.project / "mod.txt").is_file():
        steps.insert(0, {"command": "settings",
                         "options": {"op": "render", "write": "1", "overwrite": "1"}})
    return run_sequence(ctx, steps)


def read_steps(path: Path) -> list[dict]:
    """Read the [[step]] array of a step file into the shape run_sequence wants."""
    source = textio.read_source(path)
    table = toml.parse(source.text, path.name)
    entry = table.get("step")
    if entry is None:
        raise UsageError(f"{path.name}: no [[step]] array")
    items = list(entry.items) if isinstance(entry, toml.TomlArrayEntry) else [entry]
    steps: list[dict] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, toml.TomlTable):
            raise UsageError(f"{path.name}: [[step]] {index} is not a table")
        command = item.get("command")
        command = command.value if isinstance(command, toml.TomlValue) else ""
        if command not in COMMANDS:
            raise UsageError(f"{path.name}: [[step]] {index}: no command {command!r}")
        selector = item.get("selector")
        options: dict[str, str] = {}
        extra = item.get("with")
        if isinstance(extra, toml.TomlValue) and isinstance(extra.value, list):
            for pair in extra.value:
                key, _, value = str(pair).partition("=")
                if not key or not _:
                    raise UsageError(f"{path.name}: [[step]] {index}: {pair!r} is not key=value")
                options[key.strip()] = value.strip()
        steps.append({
            "command": command,
            "selector": selector.value if isinstance(selector, toml.TomlValue) else "",
            "options": options,
        })
    return steps


def cmd_run(ctx: Context) -> Result:
    """Run the steps a TOML file lists, in order (docs/cli.md section 4.17)."""
    if not ctx.selector:
        raise UsageError("run needs a step file: run <steps.toml>")
    paths = entity_files(ctx.scope, ctx.selector)
    if len(paths) != 1:
        raise UsageError(f"run needs one step file, not {len(paths)}")
    return run_sequence(ctx, read_steps(paths[0]))


def cmd_version(ctx: Context) -> Result:
    """Version of the editor, the interpreter and the resolved scope."""
    payload = {
        "editor": VERSION,
        "python": platform.python_version(),
        "scope": ctx.scope.name,
        "root": str(ctx.scope.root),
        "origin": ctx.scope.origin,
    }
    text = "\n".join(f"{key}: {value}" for key, value in payload.items())
    return Result(payload, text)


def cmd_web(ctx: Context) -> Result:
    """Serve the read-only web UI for this scope until Ctrl-C (docs/web.md)."""
    from core.web.server import serve

    address = serve(ctx.options, ctx.cwd, ctx.scope.name)
    payload = {"scope": ctx.scope.name, "root": str(ctx.scope.root), "url": address}
    return Result(payload, "")


COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "get": cmd_get,
    "find": cmd_find,
    "stats": cmd_stats,
    "refs": cmd_refs,
    "deps": cmd_deps,
    "check": cmd_check,
    "schema": cmd_schema,
    "roster": cmd_roster,
    "index": cmd_index,
    "init": cmd_init,
    "import": cmd_import,
    "add": cmd_add,
    "batch": cmd_batch,
    "clone": cmd_clone,
    "remove": cmd_remove,
    "set": cmd_set,
    "convert": cmd_convert,
    "settings": cmd_settings,
    "log": cmd_log,
    "undo": cmd_undo,
    "redo": cmd_redo,
    "export": cmd_export,
    "pack": cmd_pack,
    "diff": cmd_diff,
    "verify": cmd_verify,
    "build": cmd_build,
    "audit": cmd_audit,
    "adopt": cmd_adopt,
    "unpack": cmd_unpack,
    "run": cmd_run,
    "version": cmd_version,
    "web": cmd_web,
}

ALIASES = {
    "ls": "list",
    "cat": "show",
    "grep": "find",
    "graph": "refs",
    "lint": "check",
    "emit": "export",
    "serve": "web",
    "new": "add",
    "rm": "remove",
}
