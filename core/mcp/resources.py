"""Resources and prompts of the MCP surface.

Resources are read-only: the editor's existing read commands render the content, and the
result is plain text, so a client re-reads a resource instead of subscribing to it
(docs/mcp.md section 4).  ``firefight://<scope>/log`` is served by the ``log`` command, which
has no tool of its own.
"""

from pathlib import Path

from core.cli.scope import UsageError, resolve_all
from core.mcp.tools import CallRefused, run_command_call, success

SCHEME = "firefight://"
INVALID_PARAMS = -32602
PROMPT_NAME = "firefight-editor-workflow"

RESOURCE_TEMPLATES = (
    {
        "uriTemplate": f"{SCHEME}{{scope}}/entity/{{path}}",
        "name": "entity",
        "description": "One document of a scope, rendered the way ff_show renders it.",
        "mimeType": "text/plain",
    },
    {
        "uriTemplate": f"{SCHEME}{{scope}}/list/{{category}}",
        "name": "category",
        "description": "The entities of one editor category, as ff_list returns them.",
        "mimeType": "text/plain",
    },
    {
        "uriTemplate": f"{SCHEME}{{scope}}/log",
        "name": "log",
        "description": "The event-log segments and records of a project scope, read-only.",
        "mimeType": "text/plain",
    },
)

PROCEDURE = """\
Procedure for one edit, over the tools of this server:

1. Locate the document: ff_stats or ff_list to find the entity path, ff_check to see the
   state of the scope before the change.
2. Read it: ff_show for the document as stored (as=toml converts), ff_get for one field,
   ff_refs and ff_deps for the references in and out.
3. Stage the change with ff_set and dryRun=true, and report the printed before/after pair
   and the enum check to the caller.
4. Validate: the staged value must be declared by the schema, by the editor's enum table or
   by another document of the same project. An unknown value is refused; do not retry it.
5. Confirm with the caller, then call ff_set without dryRun. It writes one field: every
   other byte of the document stays as it was.
6. Verify with ff_check and ff_get, and read firefight://<scope>/log for the recorded event.
   A wrong change is taken back with ff_undo, never by editing the file by hand.

A refusal is final: no partial write happened, and retrying the identical call is not useful.
"""

PROMPT_ARGUMENTS = (
    {"name": "scope", "description": 'Data scope to work in, for example "Mod".', "required": True},
    {"name": "selector", "description": "Entity or folder to work on, if the task names one.", "required": False},
    {"name": "goal", "description": "What the caller wants changed, in one sentence.", "required": False},
)


def listing(cwd: Path, defaults: dict) -> list[dict]:
    """The resources that exist without naming a path: the log of every scope that resolves."""
    options = dict(defaults)
    try:
        found = resolve_all(options, cwd)
    except UsageError:
        return []
    return [
        {
            "uri": f"{SCHEME}{name}/log",
            "name": f"{name} log",
            "description": f"The event-log segments of the {name} scope.",
            "mimeType": "text/plain",
        }
        for name in sorted(found)
    ]


def read(uri: str, cwd: Path, defaults: dict) -> list[dict]:
    """The contents of one resource URI, or a refused call when it names nothing.

    A resource URI names a scope but no root, so the server's start-up defaults are what make
    a scope readable that the working directory cannot resolve (docs/mcp.md section 4).
    """
    scope, kind, target = _parse(uri)
    options = {name: value for name, value in defaults.items() if name in ("root", "workspace", "firefight")}
    if kind == "entity":
        result = run_command_call("show", scope, target, dict(options), cwd, defaults=defaults)
    elif kind == "list":
        result = run_command_call("list", scope, "", {**options, "type": target}, cwd, defaults=defaults)
    elif kind == "log":
        result = run_command_call("log", scope, "", dict(options), cwd, defaults=defaults)
    else:
        raise CallRefused(INVALID_PARAMS, f"{uri}: no such resource")
    result = success(result)
    return [{"uri": uri, "mimeType": "text/plain", "text": result["content"][0]["text"]}]


def _parse(uri: str) -> tuple[str, str, str]:
    """Split ``firefight://<scope>/<kind>[/<target>]`` into its parts.

    ``log`` names no target: it is the whole log of one scope.
    """
    if not uri.startswith(SCHEME):
        raise CallRefused(INVALID_PARAMS, f"{uri}: not a firefight resource")
    parts = uri[len(SCHEME) :].split("/", 2)
    if len(parts) < 2 or not parts[0]:
        raise CallRefused(INVALID_PARAMS, f"{uri}: a resource names a scope and a kind")
    scope, kind = parts[0], parts[1]
    target = parts[2] if len(parts) > 2 else ""
    if kind == "log":
        return scope, kind, target or "-"
    if not target:
        raise CallRefused(INVALID_PARAMS, f"{uri}: the target is empty")
    return scope, kind, target


def prompts() -> list[dict]:
    """The prompts this server offers."""
    return [
        {
            "name": PROMPT_NAME,
            "description": "How to change one field of one document with the tools of this server, from locating it to verifying the result.",
            "arguments": list(PROMPT_ARGUMENTS),
        }
    ]


def prompt(name: str, arguments: dict) -> dict:
    """One prompt rendered for the caller's arguments."""
    if name != PROMPT_NAME:
        raise CallRefused(-32601, f"unknown prompt {name!r}")
    heading = "Edit one field of one Firefight document."
    if arguments.get("scope"):
        heading = f"Edit one field of one document in scope {arguments['scope']}."
    if arguments.get("selector"):
        heading += f" Target: {arguments['selector']}."
    if arguments.get("goal"):
        heading += f" Goal: {arguments['goal']}"
    return {
        "description": "The editor workflow: locate, read, stage, validate, confirm, write, verify.",
        "messages": [{"role": "user", "content": {"type": "text", "text": f"{heading}\n\n{PROCEDURE}"}}],
    }
