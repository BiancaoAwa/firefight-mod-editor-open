"""Commands over one scope: read-only queries, the writing commands and ``export``.

Each command returns a JSON payload and its text rendering; ``set`` changes one field of one
project document, ``log``, ``undo`` and ``redo`` read and revert the event log, ``index``
builds the cross-reference tables under ``.editor/``, and ``export`` writes XML under ``to=``
(docs/cli.md).
"""

import platform
from dataclasses import dataclass
from pathlib import Path

from core import __version__ as core_version
from core import convert, index as index_core, journal, refs as refs_core, textio, toml, xml
from core.errors import FfError, SchemaError, XmlStructureError
from core.schema import schema_for
from core.toml import TomlArrayEntry, TomlEntry, TomlTable, TomlValue
from core.xml import XmlElement

from core.cli.scope import DATA_FOLDER, MOD_FOLDER, PROJECT_FILE, Scope, UsageError, entity_files


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
        relative=relative if relative is not None else path.name,
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


def reference_rows(ctx: Context, scope: Scope, files: list[Path]) -> tuple[list[dict], list[dict], str]:
    """The references of the selected files, from the stored tables or a fresh walk."""
    stored = stored_index(ctx, scope)
    if stored is not None:
        _, refs_tables = stored
        by_source = refs_tables["by_source"]
        collected: list[dict] = []
        for path in files:
            relative = relative_of(scope, path)
            if not is_entity(relative):
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
        if not is_entity(relative):
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
    for relative, path in items:
        if not is_entity(relative):
            skipped += 1
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
    if not is_entity(relative):
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
        {"path": relative, "field": "/".join(keys), "count": len(rows), "shown": len(shown), "values": shown},
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
        {"path": relative, "field": "", "count": len(rows), "shown": len(shown), "values": shown},
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
    matches: list[dict] = []
    total = 0
    for path in files:
        relative = relative_of(ctx.scope, path)
        if not is_entity(relative):
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
    for path in files:
        relative = relative_of(scope, path)
        category = category_of_path(relative)
        by_category[category] = by_category.get(category, 0) + 1
        by_format[path.suffix.lstrip(".")] = by_format.get(path.suffix.lstrip("."), 0) + 1
        bytes_total += path.stat().st_size
        if not is_entity(relative):
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
    files = [path for path in entity_files(scope) if is_entity(relative_of(scope, path))]
    collected, errors, origin = reference_rows(ctx, scope, files)
    incoming = [
        item
        for item in collected
        if item["value"] == value and (kind is None or item["kind"] == kind)
    ]
    index = refs_core.TargetIndex(scope.root)
    resolved: list[str] = []
    for item in incoming:
        for target in index.find(item["kind"], item["value"]):
            resolved.append(relative_of(scope, target))
    shown = incoming[: row_limit(ctx)]
    rows = [[item["source"], item["kind"], item["document_path"]] for item in shown]
    summary = f"{tally(len(shown), len(incoming))} incoming reference(s); resolved: {', '.join(sorted(set(resolved))) or 'none'}"
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


def cmd_check(ctx: Context) -> Result:
    """Load every selected entity, then report load errors, warnings and dangling references."""
    scope = ctx.scope
    files = filter_category(targets(ctx), ctx, scope)
    errors: list[dict] = []
    warned: list[dict] = []
    warnings_total = 0
    warning_files = 0
    graph = refs_core.RefGraph()
    loaded = 0
    skipped = 0
    for path in files:
        relative = relative_of(scope, path)
        if not is_entity(relative):
            skipped += 1
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
    index = refs_core.TargetIndex(scope.root)
    dangling = [
        {"source": item.source, "kind": item.kind, "value": item.value, "document_path": "/".join(item.path)}
        for item in refs_core.unresolved(graph, index)
    ]
    rows = [[item["path"], item["error"]] for item in errors]
    rows += [[item["source"], f"unresolved {item['kind']}={item['value']}"] for item in dangling[:limit]]
    summary = (
        f"{loaded}/{len(files)} loaded, {skipped} list file(s) skipped, {len(errors)} error(s), "
        f"{warnings_total} warning(s) in {warning_files} file(s), {len(dangling)} dangling reference(s)"
    )
    text = table_of(["file", "issue"], rows, summary)
    code = 1 if errors or dangling else 0
    return Result(
        {
            "scope": scope.name,
            "files": len(files),
            "loaded": loaded,
            "skipped": skipped,
            "errors": errors,
            "warnings_total": warnings_total,
            "warning_files": warning_files,
            "warning_samples": warned[:limit],
            "dangling": dangling[:limit],
            "dangling_total": len(dangling),
            "ok": code == 0,
        },
        text,
        code,
    )


def cmd_init(ctx: Context) -> Result:
    """Create a project: ``mod.toml`` and an empty ``Mod/Data`` (docs/cli.md section 4.9).

    ``root=`` or ``workspace=`` names the directory to create the project in, the working
    directory when neither is given; that directory may be empty and is created when it is
    missing.  Every other command resolves a scope that already exists — ``init`` is the one
    that makes one.  An existing ``mod.toml`` is refused, so an initialised project is never
    overwritten.  ``name=`` fills the mod name in, the directory name otherwise.  The record
    goes into the log like any other new document, so ``undo`` takes the ``mod.toml`` away
    again; the empty ``Mod/Data`` is a directory, not a document, and no record reverts it.
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

    data_root = project / MOD_FOLDER / DATA_FOLDER
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
        f"({PROJECT_FILE} and an empty {MOD_FOLDER}/{DATA_FOLDER}){tail}"
    )


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
    if actor is not None and actor not in ("cli", "mcp"):
        raise UsageError(f"actor= is cli or mcp, not {actor!r}")
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
    data_root = destination if destination.name == MOD_FOLDER else destination / MOD_FOLDER
    overwrite = ctx.options.get("overwrite") == "1"
    assets = ctx.options.get("assets") == "1"
    dry_run = ctx.options.get("dry-run") == "1"
    written: list[dict] = []
    copied: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    for path in filter_category(targets(ctx), ctx, scope):
        relative = relative_of(scope, path)
        if not is_entity(relative):
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
    """Translate between the stock ``Mod/mod.txt`` and ``mod_setting.toml``.

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
        source, target = stock, project / "mod_setting.toml"
    else:
        source, target = project / "mod_setting.toml", stock
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
            plan = edit.plan_render(target, "mod_setting.toml", text, entity="mod_setting")
        else:
            document = load_document(source, "mod_setting.toml")
            text, warnings = settings.emit(edit.root_table(document.table, document.root_tag))
            newline, encoding = _stock_style(stock)
            plan = edit.plan_render(target, f"{MOD_FOLDER}/{settings.MOD_TXT}", text, entity="mod_setting", newline=newline, encoding=encoding)
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

    Every managed document is rendered back to stock XML, ``mod_setting.toml`` becomes
    ``Mod/mod.txt``, unmanaged files are copied, and the archive is named after the
    project's ``mod.toml``.  It goes to ``to=``, the project directory when that is not
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
    stock = project / MOD_FOLDER / pack_core.MOD_TXT
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
            raise UsageError(
                f"{stock}: the bytes differ from what {pack_core.SETTING_FILE} renders "
                f"({stock.stat().st_size} vs {len(setting_data)} bytes); run "
                f"'settings op=emit --write overwrite=1' to reconcile the two, then pack again"
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
        table_of(["member", "bytes"], rows, summary),
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
    "index": cmd_index,
    "init": cmd_init,
    "add": cmd_add,
    "remove": cmd_remove,
    "set": cmd_set,
    "convert": cmd_convert,
    "settings": cmd_settings,
    "log": cmd_log,
    "undo": cmd_undo,
    "redo": cmd_redo,
    "export": cmd_export,
    "pack": cmd_pack,
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
