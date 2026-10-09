"""Command line entry point: usage, argument parsing, output and exit codes.

Shape: ``ff <scope> <command> [selector] [key=value ...] [--json]``; the scope is
always first, so a path can never be mistaken for a command (docs/cli.md).
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from core.errors import FfError

from cli.commands import VERSION, Context, Result, command_names, run_command
from cli.scope import UsageError, resolve_all, resolve_scope, split_spec

USAGE = """ff <scope> <command> [selector] [key=value ...] [--json]

Scopes
  Mod              the mod project this directory belongs to (mod.toml), or root=<dir>
  Firefight        stock game data, or root=<dir>
  <name>           another mod folder under the workspace Mods/

Commands
  list   (ls)      entities with category, format and size
  show   (cat)     one entity as stored, or as=raw|toml|xml
  get              field values from a document path or field=<a.b.c>
  find   (grep)    search tag=<name>, value=<text> or path=<a/b>
  stats            counts by category, root element and format
  refs   (graph)   outgoing references of the selection
  deps             incoming references of value=<token>
  check  (lint)    load every entity, report errors, warnings and dangling references
  export (emit)    render stock XML under to=<directory>
  version          editor, interpreter and resolvable scopes

Options
  root=<dir>       scope root override
  workspace=<dir>  directory holding Mods/ (default: current directory)
  to=<dir>         export destination
  as=raw|toml|xml  how show renders a document
  field=<a.b.c>    field path for get
  type=<category>  filter by editor category
  kind=<name>      filter by reference kind
  path=<a/b>       document path prefix for find
  limit=<n>        cap the rows printed (default 200)
  ignore_case=1    case-insensitive find
  --json           print the machine payload instead of the text table
"""


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
        elif token.startswith("--") and "=" in token:
            name, value = token[2:].split("=", 1)
            options[name] = value
        elif "=" in token and not token.startswith("-"):
            name, value = token.split("=", 1)
            options[name] = value
        elif token.startswith("-") and token != "-":
            raise UsageError(f"unknown flag {token!r}; options use key=value, plus --json and --help")
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
        scope = resolve_scope(scope_name, invocation.options, cwd)
        context = Context(scope=scope, selector=relative, doc_path=doc_path, options=invocation.options, cwd=cwd)
        result = run_command(command, context)
        _emit(_render(result, invocation.json))
        return result.code
    except UsageError as error:
        _emit(str(error), stream=sys.stderr)
        _emit("run 'ff help' for usage", stream=sys.stderr)
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
    from cli.commands import cmd_version

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
