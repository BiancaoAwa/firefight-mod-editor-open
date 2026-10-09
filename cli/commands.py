"""Commands over one scope: read-only queries plus export.

Each command returns a JSON payload and a text rendering of the same data; the
entry point picks one.  Nothing here writes into a scope: ``export`` is the only
writer and it writes rendered XML under an explicit ``to=`` directory
(docs/cli.md).
"""

import platform
from dataclasses import dataclass
from pathlib import Path

from core import refs as refs_core
from core import textio, tomlread, xmlread
from core.errors import FfError, SchemaError, XmlStructureError
from core.tomlmodel import TomlTable
from core.xmlmodel import XmlElement

from cli.documents import (
    category_of_path,
    load_document,
    select,
    select_table,
    walk,
)
from cli.scope import Scope, UsageError, entity_files

VERSION = "0.1.0"
CATEGORIES = ("infantry", "vehicle", "weapon", "at_gun", "aircraft", "equipment", "surnames", "other")
DEFAULT_LIMIT = 200


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
    """Scope-relative POSIX path of a file."""
    try:
        return path.relative_to(scope.root).as_posix()
    except ValueError:
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
    rows = [[item["path"], item["category"], item["format"], item["bytes"]] for item in entities]
    text = table_of(["path", "category", "format", "bytes"], rows, f"{len(entities)} entity file(s) in {scope.describe()}")
    return Result({"scope": scope.name, "root": str(scope.root), "count": len(entities), "entities": entities}, text)


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
        text = tomlwrite.render(wrapper)
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
    """Read the value of one field, named by a field= key path or a document path."""
    path, relative = single_document(ctx)
    document = load_document(path, relative)
    field = ctx.options.get("field")
    if field:
        keys = tuple(part for part in field.split(".") if part)
    elif ctx.doc_path:
        keys = ctx.doc_path
    else:
        raise UsageError("nothing to read; pass a document path or field=<a.b.c>")
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
    if not rows:
        raise UsageError(f"{document_path(ctx.scope, relative)}: no field {'/'.join(keys)}")
    text = table_of(["path", "line", "value"], [[row["path"], row["line"], row["value"]] for row in rows])
    return Result({"path": relative, "field": "/".join(keys), "count": len(rows), "values": rows}, text)


def cmd_find(ctx: Context) -> Result:
    """Search tags, document paths and values across a scope."""
    tag = ctx.options.get("tag")
    value = ctx.options.get("value")
    prefix = ctx.options.get("path")
    ignore_case = ctx.options.get("ignore_case", "0") not in ("0", "false", "no")
    limit = int(ctx.options.get("limit", DEFAULT_LIMIT))
    if tag is None and value is None and prefix is None:
        raise UsageError("nothing to search for; pass tag=<name>, value=<text> or path=<a/b>")
    needle = value.casefold() if (value and ignore_case) else value
    files = filter_category(targets(ctx), ctx, ctx.scope)
    matches: list[dict] = []
    truncated = False
    for path in files:
        relative = relative_of(ctx.scope, path)
        if not is_entity(relative):
            continue
        try:
            document = load_document(path, relative)
        except FfError as error:
            matches.append({"path": relative, "error": str(error)})
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
            if len(matches) >= limit:
                truncated = True
                break
            matches.append(
                {
                    "path": relative,
                    "line": element.line,
                    "tag": element.tag,
                    "document_path": joined,
                    "value": element.value,
                }
            )
        if truncated:
            break
    rows = [[item["path"], item.get("line", ""), item.get("tag", ""), item.get("value", "")] for item in matches]
    summary = f"{len(matches)} match(es)" + (" (limit reached)" if truncated else "")
    text = table_of(["path", "line", "tag", "value"], rows, summary)
    query = {"tag": tag, "value": value, "path": prefix, "ignore_case": ignore_case}
    return Result({"query": query, "count": len(matches), "truncated": truncated, "matches": matches}, text)


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
        table = tomlread.parse(text, str(path))
        if not table.entries:
            raise SchemaError((), f"{path}: empty document")
        return table.entries[0][0]
    return xmlread.parse(text, str(path)).root.tag


def cmd_refs(ctx: Context) -> Result:
    """Outgoing references of the selected entities."""
    kind = ctx.options.get("kind")
    scope = ctx.scope
    files = filter_category(targets(ctx), ctx, scope)
    collected: list[dict] = []
    errors: list[dict] = []
    for path in files:
        relative = relative_of(scope, path)
        if not is_entity(relative):
            continue
        try:
            document = load_document(path, relative)
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        for reference in refs_core.references_in(document.root, document_path(scope, relative)):
            if kind is not None and reference.kind != kind:
                continue
            collected.append(
                {
                    "source": reference.source,
                    "kind": reference.kind,
                    "value": reference.value,
                    "document_path": "/".join(reference.path),
                }
            )
    counts: dict[str, int] = {}
    for item in collected:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    rows = [[item["source"], item["kind"], item["value"], item["document_path"]] for item in collected[:DEFAULT_LIMIT]]
    summary = f"{len(collected)} reference(s) " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    text = table_of(["source", "kind", "value", "document_path"], rows, summary)
    return Result({"scope": scope.name, "count": len(collected), "by_kind": counts, "references": collected, "errors": errors}, text)


def cmd_deps(ctx: Context) -> Result:
    """Who references a value or a file, and whether the target exists."""
    scope = ctx.scope
    value = ctx.options.get("value") or (ctx.selector if ctx.selector and ctx.selector != "all" else None)
    kind = ctx.options.get("kind")
    if not value:
        raise UsageError("name what to look for: value=<token>")
    graph = refs_core.RefGraph()
    errors: list[dict] = []
    for path in entity_files(scope):
        relative = relative_of(scope, path)
        if not is_entity(relative):
            continue
        try:
            document = load_document(path, relative)
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        graph.add(document_path(scope, relative), document.root)
    incoming = [
        reference
        for reference in graph.references()
        if reference.value == value and (kind is None or reference.kind == kind)
    ]
    index = refs_core.TargetIndex(scope.root)
    resolved: list[str] = []
    for reference in incoming:
        for target in index.find(reference.kind, reference.value):
            resolved.append(relative_of(scope, target))
    rows = [[item.source, item.kind, "/".join(item.path)] for item in incoming]
    summary = f"{len(incoming)} incoming reference(s); resolved: {', '.join(sorted(set(resolved))) or 'none'}"
    text = table_of(["source", "kind", "document_path"], rows, summary)
    return Result(
        {
            "scope": scope.name,
            "value": value,
            "count": len(incoming),
            "references": [{"source": item.source, "kind": item.kind, "document_path": "/".join(item.path)} for item in incoming],
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
            if len(warned) < 20:
                warned.append({"path": relative, "warnings": list(document.warnings)})
        graph.add(document_path(scope, relative), document.root)
    index = refs_core.TargetIndex(scope.root)
    dangling = [
        {"source": item.source, "kind": item.kind, "value": item.value, "document_path": "/".join(item.path)}
        for item in refs_core.unresolved(graph, index)
    ]
    rows = [[item["path"], item["error"]] for item in errors]
    rows += [[item["source"], f"unresolved {item['kind']}={item['value']}"] for item in dangling[:20]]
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
            "warning_samples": warned,
            "dangling": dangling,
            "ok": code == 0,
        },
        text,
        code,
    )


def cmd_export(ctx: Context) -> Result:
    """Render the selected entities as stock XML under the directory in to=."""
    scope = ctx.scope
    target = ctx.options.get("to")
    if not target:
        raise UsageError("export needs a destination: to=<directory>")
    destination = Path(target)
    files = filter_category(targets(ctx), ctx, scope)
    written: list[dict] = []
    errors: list[dict] = []
    for path in files:
        relative = relative_of(scope, path)
        out = destination / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            text, encoding, warnings = _export_text(path, relative)
            out.write_bytes(textio.encode_export(text, file=str(out), encoding=encoding))
        except FfError as error:
            errors.append({"path": relative, "error": str(error)})
            continue
        written.append(
            {"path": relative, "out": str(out), "bytes": out.stat().st_size, "warnings": warnings}
        )
    summary = f"{len(written)} file(s) written to {destination}, {len(errors)} error(s)"
    rows = [[item["path"], item["bytes"]] for item in written[:DEFAULT_LIMIT]]
    text = table_of(["path", "bytes"], rows, summary)
    return Result(
        {"scope": scope.name, "to": str(destination), "count": len(written), "files": written, "errors": errors},
        text,
        1 if errors else 0,
    )


def _export_text(path: Path, relative: str) -> tuple[str, str, list[str]]:
    """Stock XML for one entity plus its source encoding; a plain list is copied verbatim."""
    source = textio.read_source(path)
    if path.suffix.lower() == ".txt":
        try:
            xmlread.parse(source.text, relative)
        except FfError:
            return textio.to_export_newlines(source.text), source.encoding, []
    warnings: list[str] = []
    document = load_document(path, relative)
    return document.xml_text(warnings), document.encoding, list(document.warnings) + warnings


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


COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "get": cmd_get,
    "find": cmd_find,
    "stats": cmd_stats,
    "refs": cmd_refs,
    "deps": cmd_deps,
    "check": cmd_check,
    "export": cmd_export,
    "version": cmd_version,
}

ALIASES = {
    "ls": "list",
    "cat": "show",
    "grep": "find",
    "graph": "refs",
    "deps": "deps",
    "lint": "check",
    "emit": "export",
}
