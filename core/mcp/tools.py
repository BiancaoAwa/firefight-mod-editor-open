"""The MCP tool surface: one listing entry per specification and one in-process command call.

A call builds a ``core.cli.commands.Context`` and runs ``run_command`` in process, so the
permission gate, the exit-code semantics and the payload shape are the same as the command
line; the CLI is never spawned (docs/mcp.md section 1).  A refused call raises
``CallRefused`` with the JSON-RPC code to answer with, while a command that ran and reported
a problem comes back as a normal result carrying ``isError`` and the CLI exit code.
"""

import json
from pathlib import Path

from core.cli import specs
from core.cli.commands import Context, Result, run_command
from core.cli.scope import UsageError, resolve_scope, split_spec
from core.errors import FfError

METHOD_NOT_FOUND = -32601
WRITE_REFUSED = -32000
INVALID_PARAMS = -32602


class CallRefused(Exception):
    """A refused call; ``code`` is the JSON-RPC error code the server answers with."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(message)


def listing(*, write: bool) -> list[dict]:
    """The ``tools/list`` entries of a server started with or without ``--write``."""
    return [
        {
            "name": specs.exposed_name(spec.name),
            "description": spec.description,
            "inputSchema": spec.inputs(),
            "annotations": {
                "title": specs.exposed_name(spec.name),
                "readOnlyHint": not spec.writes,
                "idempotentHint": not spec.writes,
                "openWorldHint": False,
            },
        }
        for spec in specs.registered(write=write)
    ]


def call(name: str, arguments: dict, *, write: bool, defaults: dict, cwd: Path) -> dict:
    """Run one tool and return its ``tools/call`` result."""
    canonical = specs.canonical_name(name)
    spec = specs.tool_named(canonical) if canonical else None
    if spec is None or not spec.available or (spec.writes and not write):
        raise CallRefused(METHOD_NOT_FOUND, f"unknown tool {name!r}")
    scope_name, selector, options = spec.call(arguments, defaults=defaults)
    try:
        result = run_command_call(spec.command, scope_name, selector, options, cwd, write=spec.writes, defaults=defaults)
    except FfError as error:
        return failure(str(error), code=1)
    return success(result)


def run_command_call(
    command: str,
    scope_name: str,
    selector: str,
    options: dict[str, str],
    cwd: Path,
    *,
    write: bool = False,
    defaults: dict | None = None,
) -> "Result":
    """Run one command in process, refusing an unusable call before the command sees it.

    A call keeps the CLI semantics: the scope is resolved the same way, the server's option
    defaults apply to every call, a usage error becomes an invalid-parameter refusal, and a
    write aimed at the stock scope is refused here rather than inside the command
    (docs/mcp.md section 5).
    """
    settings = {**(defaults or {}), **options}
    if write:
        settings["write"] = "1"
    try:
        text = scope_name if not selector else f"{scope_name}/{selector}"
        _, relative, doc_path = split_spec(text)
        scope = resolve_scope(scope_name, settings, cwd)
        if write and scope.name == "Firefight":
            raise CallRefused(WRITE_REFUSED, "the stock scope is read-only; this tool refuses to write under Firefight")
        context = Context(scope=scope, selector=relative, doc_path=doc_path, options=settings, cwd=cwd)
        return run_command(command, context)
    except UsageError as error:
        raise CallRefused(INVALID_PARAMS, str(error)) from None


def success(result) -> dict:
    """A command result as a ``tools/call`` result; a non-zero CLI code is a tool-level failure."""
    payload = dict(result.payload)
    payload["exit_code"] = result.code
    return {
        "content": [{"type": "text", "text": result.text or json.dumps(payload, ensure_ascii=False, default=str)}],
        "structuredContent": payload,
        "isError": result.code != 0,
    }


def failure(message: str, *, code: int) -> dict:
    """A command that raised as a ``tools/call`` result."""
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"status": "error", "message": message, "exit_code": code},
        "isError": True,
    }
