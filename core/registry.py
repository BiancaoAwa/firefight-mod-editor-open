"""The command registry: one record per command, its category and its flags.

A command lives in three places today: the handler, the metadata below and the
category it belongs to. Adding one means writing the handler and one Command
record; nothing in core.cli.commands, core.web.server or core.cli.main needs
to change. A module under core/commands_ext may declare extra commands and is
loaded at import time.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable

CATEGORIES = ("inspect", "check", "edit", "project", "build", "serve")

CATEGORY_LABELS = {
    "inspect": "read",
    "check": "check",
    "edit": "write",
    "project": "project",
    "build": "build",
    "serve": "serve",
}


@dataclass(frozen=True)
class Command:
    """One command: how to run it and what it is."""

    name: str
    handler: str  # "module:function", resolved on first use
    category: str
    summary: str
    aliases: tuple[str, ...] = ()
    writes: bool = False  # needs --write
    web_form: bool = False  # reachable as a form on /cmd
    mcp: bool = True  # exposed as an MCP tool
    section: str = ""  # docs/cli.md section


CORE_COMMANDS: tuple[Command, ...] = (
    Command(
        name="list",
        handler="core.cli.commands:cmd_list",
        category="inspect",
        summary="List entities with category, storage format and size.",
        aliases=("ls",),
    ),
    Command(
        name="show",
        handler="core.cli.commands:cmd_show",
        category="inspect",
        summary="Show one entity, as stored or in the other representation.",
        aliases=("cat",),
    ),
    Command(
        name="get",
        handler="core.cli.commands:cmd_get",
        category="inspect",
        summary="Read a field, a subtree, or every field of one document.",
    ),
    Command(
        name="find",
        handler="core.cli.commands:cmd_find",
        category="inspect",
        summary="Search tags, document paths and values across a scope.",
        aliases=("grep",),
    ),
    Command(
        name="stats",
        handler="core.cli.commands:cmd_stats",
        category="inspect",
        summary="Counts by category, root element and storage format.",
    ),
    Command(
        name="refs",
        handler="core.cli.commands:cmd_refs",
        category="inspect",
        summary="Outgoing references of the selected entities.",
        aliases=("graph",),
    ),
    Command(
        name="deps",
        handler="core.cli.commands:cmd_deps",
        category="inspect",
        summary="Who references a value or a file, and whether the target exists.",
    ),
    Command(
        name="check",
        handler="core.cli.commands:cmd_check",
        category="check",
        summary="Load every selected entity, then report load errors, warnings and dangling references.",
        aliases=("lint",),
    ),
    Command(
        name="schema",
        handler="core.cli.commands:cmd_schema",
        category="check",
        summary="List the declared fields and enum values of one root element; read-only.",
        section="4.13",
    ),
    Command(
        name="roster",
        handler="core.cli.commands:cmd_roster",
        category="edit",
        summary="Read and edit the rosters the project declares; writes need --write.",
        writes=True,
        web_form=True,
        section="4.14",
    ),
    Command(
        name="index",
        handler="core.cli.commands:cmd_index",
        category="build",
        summary="Build the cross-reference tables; needs --write.",
        writes=True,
        web_form=True,
        section="4.6",
    ),
    Command(
        name="init",
        handler="core.cli.commands:cmd_init",
        category="project",
        summary="Create a project: ``ModInformation.toml`` and an empty ``Data/`` (docs/cli.md section 4.9).",
        writes=True,
        web_form=True,
        section="4.9",
    ),
    Command(
        name="import",
        handler="core.cli.commands:cmd_import",
        category="project",
        summary="Create a project from a mod that already exists, as a directory or a zip.",
        writes=True,
        web_form=True,
        section="4.16",
    ),
    Command(
        name="add",
        handler="core.cli.commands:cmd_add",
        category="edit",
        summary="Create one entity document; needs --write and never writes the stock scope.",
        aliases=("new",),
        writes=True,
        web_form=True,
        section="4.5",
    ),
    Command(
        name="batch",
        handler="core.cli.commands:cmd_batch",
        category="edit",
        summary="Apply several field changes to several documents from one patch file.",
        writes=True,
        web_form=True,
        section="4.15",
    ),
    Command(
        name="clone",
        handler="core.cli.commands:cmd_clone",
        category="edit",
        summary="Copy one entity document under a new token; needs --write.",
        writes=True,
        web_form=True,
        section="4.12",
    ),
    Command(
        name="remove",
        handler="core.cli.commands:cmd_remove",
        category="edit",
        summary="Delete one entity document; needs --write and never writes the stock scope.",
        aliases=("rm",),
        writes=True,
        web_form=True,
        section="4.5",
    ),
    Command(
        name="set",
        handler="core.cli.commands:cmd_set",
        category="edit",
        summary="Change one field of one document; needs --write and never writes the stock scope.",
        writes=True,
        web_form=True,
        section="4.1",
    ),
    Command(
        name="convert",
        handler="core.cli.commands:cmd_convert",
        category="project",
        summary="Convert the selected source files into project working files under to=.",
        writes=True,
        web_form=True,
        section="4.3",
    ),
    Command(
        name="settings",
        handler="core.cli.commands:cmd_settings",
        category="project",
        summary="Translate between the stock ``mod.txt`` and ``ModSetting.toml``.",
        writes=True,
        web_form=True,
        section="4.7",
    ),
    Command(
        name="log",
        handler="core.cli.commands:cmd_log",
        category="inspect",
        summary="List the log segments of this project and the newest records inside them.",
        mcp=False,
        section="4.2",
    ),
    Command(
        name="undo",
        handler="core.cli.commands:cmd_undo",
        category="edit",
        summary="Put back what the last writes replaced; needs --write.",
        writes=True,
        web_form=True,
        section="4.2",
    ),
    Command(
        name="redo",
        handler="core.cli.commands:cmd_redo",
        category="edit",
        summary="Re-apply what the last undo reverted; needs --write.",
        writes=True,
        web_form=True,
        section="4.2",
    ),
    Command(
        name="export",
        handler="core.cli.commands:cmd_export",
        category="build",
        summary="Render the selected entities as stock XML under the directory in to=.",
        aliases=("emit",),
        writes=True,
        web_form=True,
    ),
    Command(
        name="pack",
        handler="core.cli.commands:cmd_pack",
        category="build",
        summary="Build the mod-zip the game installs (docs/cli.md section 4.8).",
        writes=True,
        web_form=True,
        section="4.8",
    ),
    Command(
        name="diff",
        handler="core.cli.commands:cmd_diff",
        category="check",
        summary="Compare two documents, or two trees lined up by their entity paths.",
        section="4.10",
    ),
    Command(
        name="verify",
        handler="core.cli.commands:cmd_verify",
        category="check",
        summary="Read every selected document back and report what does not survive the trip.",
        section="4.11",
    ),
    Command(
        name="build",
        handler="core.cli.commands:cmd_build",
        category="build",
        summary="index, check and pack in one run (docs/cli.md section 4.17).",
        writes=True,
        web_form=True,
        section="4.17",
    ),
    Command(
        name="doctor",
        handler="core.cli.commands:cmd_doctor",
        category="check",
        summary="Report the settings this machine needs: Setting.toml, the game directory, the project files and the cache.",
        aliases=("selfcheck",),
        mcp=False,
        section="4.18",
    ),
    Command(
        name="audit",
        handler="core.cli.commands:cmd_audit",
        category="check",
        summary="Read every document back, then check with both gates on (docs/cli.md section 4.17).",
        section="4.17",
    ),
    Command(
        name="adopt",
        handler="core.cli.commands:cmd_adopt",
        category="project",
        summary="Import a tree or a zip as a project, then index it (docs/cli.md section 4.17).",
        writes=True,
        web_form=True,
        section="4.17",
    ),
    Command(
        name="unpack",
        handler="core.cli.commands:cmd_unpack",
        category="project",
        summary="Write the project back out as the original XML and text (docs/cli.md section 4.17).",
        writes=True,
        web_form=True,
        section="4.17",
    ),
    Command(
        name="run",
        handler="core.cli.commands:cmd_run",
        category="build",
        summary="Run the steps a TOML file lists, in order (docs/cli.md section 4.17).",
        writes=True,
        web_form=True,
        section="4.17",
    ),
    Command(
        name="version",
        handler="core.cli.commands:cmd_version",
        category="inspect",
        summary="Version of the editor, the interpreter and the resolved scope.",
        mcp=False,
    ),
    Command(
        name="web",
        handler="core.cli.commands:cmd_web",
        category="serve",
        summary="Serve the read-only web UI for this scope until Ctrl-C (docs/web.md).",
        aliases=("serve",),
        mcp=False,
        section="4.4",
    ),
)

_extra: list[Command] = []
_loaded = False


def _load_extras() -> None:
    """Import every module under core/commands_ext once."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        package = importlib.import_module("core.commands_ext")
    except ModuleNotFoundError:
        return
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"core.commands_ext.{info.name}")
        declared = getattr(module, "COMMANDS", ())
        _extra.extend(declared)


def commands() -> tuple[Command, ...]:
    """Every registered command, core first, extras after."""
    _load_extras()
    return CORE_COMMANDS + tuple(_extra)


def resolve(spec: str) -> Callable:
    """Import a handler from its "module:function" spelling."""
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def handlers() -> dict[str, Callable]:
    """name to callable, the table core.cli.commands dispatches through."""
    return {command.name: resolve(command.handler) for command in commands()}


def aliases() -> dict[str, str]:
    """alias to canonical name."""
    table: dict[str, str] = {}
    for command in commands():
        for alias in command.aliases:
            table[alias] = command.name
    return table


def by_category() -> dict[str, tuple[Command, ...]]:
    """The commands grouped for help output and the tool table."""
    grouped: dict[str, list[Command]] = {name: [] for name in CATEGORIES}
    for command in commands():
        if command.category not in grouped:
            raise ValueError(f"unknown category {command.category!r} on {command.name}")
        grouped[command.category].append(command)
    return {name: tuple(items) for name, items in grouped.items()}


def get(name: str) -> Command | None:
    """One command by canonical name or alias."""
    canonical = aliases().get(name, name)
    for command in commands():
        if command.name == canonical:
            return command
    return None
