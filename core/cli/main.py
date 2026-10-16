"""Command line entry point: usage, argument parsing, output and exit codes.

Shape: ``python -m core.cli <scope> <command> [selector] [key=value ...] [--json]``, scope first (docs/cli.md).
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from core.errors import FfError

from core.cli.commands import VERSION, Context, Result, command_names, run_command
from core.cli.scope import UsageError, init_scope, resolve_all, resolve_scope, split_spec

USAGE = """python -m core.cli <scope> <command> [selector] [key=value ...] [--json]

Scopes
  Mod              the mod project this directory belongs to (ModInformation.toml), or root=<dir>
  Firefight        stock game data, or root=<dir>
  <name>           another mod folder under the workspace Mod/

Commands
  list   (ls)      entities with category, format and size
  show   (cat)     one entity as stored, or as=raw|toml|xml
  get              field values from a document path or field=<a.b.c>
  find   (grep)    search tag=<name>, value=<text> or path=<a/b>
  stats            counts by category, root element and format
  refs   (graph)   outgoing references of the selection
  deps             incoming references of value=<token>
  check  (lint)    load every entity, report errors, warnings and dangling references
  schema           list the declared fields of one root element, or enum=<name>
  roster           read the rosters the project declares, edit one entry, or check both
                   directions between the entries and the documents (docs/cli.md section 4.14)
  index            build the cross-reference tables under EditorCache/ (needs --write)
  init             create a project: ModInformation.toml and an empty Data/ (needs --write)
  add              create one entity document (needs --write)
  clone            copy one entity document under a new token (needs --write)
  remove  (rm)     delete one entity document (needs --write)
  settings         translate between the stock mod.txt and ModSetting.toml (needs --write)
  set              change one field of one document (needs --write)
  convert          turn the selection into project working files under to= (needs --write)
  log              log segments and the newest records inside them
  undo             put back what the last writes replaced (needs --write)
  redo             re-apply what the last undo reverted (needs --write)
  export (emit)    render stock XML under to=<directory>
  pack             build the installable mod-zip (needs --write)
  diff             compare two documents, or two trees lined up by entity path
  verify           read every selected document back and report what does not survive
  version          editor, interpreter and resolvable scopes
  web    (serve)   serve the web UI on 127.0.0.1 (blocks until Ctrl-C)

Options
  root=<dir>       scope root override
  workspace=<dir>  directory holding Mod/ (default: current directory)
  to=<dir>         export destination, the project convert writes into, or where pack
                   leaves the archive (default: the project directory)
  as=raw|toml|xml  how show renders a document
  field=<a.b.c>    field path for get; without it get lists every field
  type=<category>  filter by editor category
  kind=<name>      filter by reference kind
  path=<a/b>       document path prefix for find
  name=<text>      init: the mod name the new ModInformation.toml carries (default: the directory name)
  limit=<n>        cap the rows printed (default 200; 0 prints every row)
  ignore_case=1    case-insensitive find
  left=<scope:path>   diff: one side, the scope name optional (default: this scope)
  right=<scope:path>  diff: the other side
  from=<path>      add: copy this document instead of writing the schema skeleton
  as=<token>       clone: the name the copy declares
  into=<scope>     clone: the scope the copy lands in (default: this scope)
  enum=<name>      schema: list the values of this enum table
  section=<text>   roster: only the entries whose group comment is this text
  line=<number>    roster op=add|remove|set: the physical line to write at, delete or rewrite
  as=<token>       roster op=set: the name that replaces the entry on the line
  op=<name>        set: set (default), append or delete one array-of-tables entry;
                   settings: render (default, stock mod.txt to TOML) or emit (TOML to mod.txt)
  from=<n>         set op=append: copy this array entry instead of an empty one
  overwrite=1      convert: replace a working file that is already there
  assets=1         convert: also copy the scope's Images/ and Sounds/ trees as they are
  assets=1         check: name the file a missing image or a missing sound would have to be
  rosters=1        check: also compare the rosters against the documents
  against=<root>   check: a second root that answers references this project does not hold
  overwrite=0      export: leave a file that is already there untouched
  overwrite=1      settings: replace an existing ModSetting.toml, or an existing mod.txt
  overwrite=0      pack: leave an archive that is already there untouched
  strict=1         pack: refuse to write while the project has load errors or dangling
                   references; without it both are reported and the pack goes ahead
  document=<text>  log: keep records whose document contains this text
  actor=cli|mcp|web  log: keep records written by this actor
  result=<name>    log: keep set, undo or redo records
  since=<stamp>    log: keep records at or after this timestamp text
  until=<stamp>    log: keep records at or before this timestamp text
  port=<n>         web UI port; without it the first free port at or above 8765 is used,
                   unless an instance is already running and is reused instead
  token=<text>     web UI access token; links then need ?t=<text>
  pagesize=<n>     web UI rows per page (default 200)
  lang=zh|en       web UI language (default zh); a page can override it with ?lang=
  browser=1        web UI: open the default browser on start
  --write          set, add, remove, convert, index, settings, pack, undo and redo: write the change
  --dry-run        set, add, remove, convert, export, index, settings, pack, undo and redo: report it
  --json           print the machine payload instead of the text table
"""

BARE_FLAGS = {"--write": "write", "--dry-run": "dry-run"}


@dataclass
class Invocation:
    """Parsed argv: flags, options and positional tokens."""

    options: dict[str, str]
    positionals: list[str]
    json: bool
    help: bool


def parse_argv(argv: list[str]) -> Invocation:
    """Split argv into options, flags and positionals."""
    options: dict[str, str] = {}
    positionals: list[str] = []
    json_flag = False
    help_flag = False
    for token in argv:
        if token == "--json":
            json_flag = True
        elif token in ("--help", "-h", "help"):
            help_flag = True
        elif token in BARE_FLAGS:
            options[BARE_FLAGS[token]] = "1"
        elif token.startswith("--") and "=" in token:
            name, value = token[2:].split("=", 1)
            options[name] = value
        elif "=" in token and not token.startswith("-"):
            name, value = token.split("=", 1)
            options[name] = value
        elif token.startswith("-") and token != "-":
            raise UsageError(f"unknown flag {token!r}; options use key=value, plus --json, --help, --write and --dry-run")
        else:
            positionals.append(token)
    return Invocation(options, positionals, json_flag, help_flag)


def main(argv: list[str] | None = None) -> int:
    """Run one invocation and return its exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    cwd = Path.cwd()
    try:
        invocation = parse_argv(argv)
        if invocation.help and not invocation.positionals:
            return _print_usage(invocation.options, cwd)
        positionals = invocation.positionals
        if not positionals:
            return _print_usage(invocation.options, cwd)
        if positionals[0] == "version" and len(positionals) == 1:
            return _print_versions(invocation)
        if invocation.help and len(positionals) < 2:
            return _print_usage(invocation.options, cwd)
        scope_name = positionals[0]
        if len(positionals) < 2:
            raise UsageError(f"scope {scope_name!r} needs a command; try 'help'")
        command = positionals[1]
        selector = " ".join(positionals[2:])
        spec = scope_name if not selector else f"{scope_name}/{selector}"
        _, relative, doc_path = split_spec(spec)
        scope = init_scope(scope_name, cwd, invocation.options) if command == "init" else resolve_scope(scope_name, invocation.options, cwd)
        context = Context(scope=scope, selector=relative, doc_path=doc_path, options=invocation.options, cwd=cwd)
        result = run_command(command, context)
        _emit(_render(result, invocation.json))
        return result.code
    except UsageError as error:
        _emit(str(error), stream=sys.stderr)
        _emit("run 'python -m core.cli help' for usage", stream=sys.stderr)
        return 2
    except FfError as error:
        _emit(str(error), stream=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _render(result: Result, as_json: bool) -> str:
    """Machine payload or human text for one result."""
    if not as_json:
        return result.text
    return json.dumps(result.payload, indent=2, ensure_ascii=False, default=str)


def _print_usage(options: dict[str, str], cwd: Path) -> int:
    """Usage text plus the scopes that resolve right now."""
    lines = [USAGE, "Resolved scopes"]
    try:
        found = resolve_all(options, cwd)
    except UsageError as error:
        found = {}
        lines.append(f"  (none: {error})")
    if not found:
        lines.append("  (none)")
    for name, scope in sorted(found.items()):
        lines.append(f"  {name}: {scope.root} ({scope.origin})")
    _emit("\n".join(lines))
    return 0


def _print_versions(invocation: Invocation) -> int:
    """Version line plus every resolvable scope."""
    from core.cli.commands import cmd_version

    _emit(f"editor: {VERSION}")
    _emit(f"python: {sys.version.split()[0]}")
    _emit("commands: " + ", ".join(command_names()))
    try:
        found = resolve_all(invocation.options, Path.cwd())
    except UsageError as error:
        _emit(f"scopes: none ({error})")
        return 0
    for name, scope in sorted(found.items()):
        context = Context(scope=scope, selector="all", doc_path=(), options=invocation.options, cwd=Path.cwd())
        _emit(f"{cmd_version(context).text}")
    return 0


def _emit(text: str, stream=None) -> None:
    """Write one block, degrading characters the console encoding cannot hold."""
    target = sys.stdout if stream is None else stream
    try:
        target.write(text + "\n")
    except UnicodeEncodeError:
        encoding = target.encoding or "utf-8"
        target.write(text.encode(encoding, "replace").decode(encoding, "replace") + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
