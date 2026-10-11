"""stdio JSON-RPC server for the MCP tool, resource and prompt surface.

The server answers both protocol families (docs/mcp.md section 2): the classic ``initialize``
handshake, and the stateless ``server/discover`` revision, whose results carry
``_meta.serverInfo`` and an explicit ``resultType``.  Every tool call runs the editor's own
command in process, so the permission gate and the exit-code semantics match the command line.
"""

import json
import sys
from pathlib import Path

from core.cli.commands import VERSION
from core.mcp import resources, tools
from core.mcp.tools import CallRefused

SERVER_NAME = "firefight-mod-editor"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-11-25")
STATELESS_VERSION = "2026-07-28"
SERVER_INFO = {"name": SERVER_NAME, "version": VERSION}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
UNSUPPORTED_VERSION = -32022

USAGE = """python -m core.mcp [--write] [workspace=<dir>] [root=<dir>] [firefight=<dir>]

Speaks MCP over stdin and stdout: tool calls, resources and prompts (docs/mcp.md).

Options
  --write            expose the writing tools; without it the server is read-only
  workspace=<dir>    directory holding Mods/, as the default for every tool call
  root=<dir>         scope root override, as the default for every tool call
  firefight=<dir>    stock game directory, as the default for the Firefight scope
  --version          print the server version and exit
  --help             print this text and exit
"""


class Server:
    """One stdio session: arguments in, JSON-RPC answers out."""

    def __init__(self, *, write: bool = False, defaults: dict | None = None, cwd: Path | None = None) -> None:
        self.write = write
        self.defaults = dict(defaults or {})
        self.cwd = Path(cwd) if cwd is not None else Path.cwd()
        self.stateless = False
        self.initialized = False

    def handle(self, message) -> dict | None:
        """Answer one JSON-RPC message; a notification has no answer."""
        if not isinstance(message, dict):
            return _error(None, INVALID_REQUEST, "a request must be a JSON object")
        identifier = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            return _error(identifier, INVALID_REQUEST, "a request needs a method")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _error(identifier, INVALID_REQUEST, "params must be an object")
        if identifier is None:
            # A notification: the handshake continuation needs no reply.
            return None
        try:
            result = self._dispatch(method, params)
        except CallRefused as refused:
            return _error(identifier, refused.code, str(refused))
        except Exception as error:  # noqa: BLE001 - a fault must not kill the session
            return _error(identifier, INTERNAL_ERROR, f"{type(error).__name__}: {error}")
        if self.stateless and isinstance(result, dict):
            result.setdefault("resultType", "complete")
            result.setdefault("_meta", {"serverInfo": SERVER_INFO})
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    def _dispatch(self, method: str, params: dict) -> dict:
        """Route one request to its handler."""
        if method == "initialize":
            return self._initialize(params)
        if method == "server/discover":
            return self._discover(params)
        if method in ("notifications/initialized", "notifications/cancelled"):
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": tools.listing(write=self.write)}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": resources.listing(self.cwd, self.defaults)}
        if method == "resources/templates/list":
            return {"resourceTemplates": list(resources.RESOURCE_TEMPLATES)}
        if method == "resources/read":
            uri = params.get("uri")
            if not isinstance(uri, str):
                raise CallRefused(tools.INVALID_PARAMS, "resources/read needs a uri")
            return {"contents": resources.read(uri, self.cwd, self.defaults)}
        if method == "prompts/list":
            return {"prompts": resources.prompts()}
        if method == "prompts/get":
            name = params.get("name")
            if not isinstance(name, str):
                raise CallRefused(tools.INVALID_PARAMS, "prompts/get needs a name")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise CallRefused(tools.INVALID_PARAMS, "prompts/get arguments must be an object")
            return resources.prompt(name, arguments)
        raise CallRefused(METHOD_NOT_FOUND, f"unknown method {method!r}")

    def _initialize(self, params: dict) -> dict:
        """The classic handshake: echo the revision the client asked for when it is known."""
        requested = params.get("protocolVersion")
        if requested not in PROTOCOL_VERSIONS:
            raise CallRefused(UNSUPPORTED_VERSION, f"unsupported protocol version {requested!r}")
        self.initialized = True
        return {
            "protocolVersion": requested,
            "capabilities": capabilities(write=self.write),
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        }

    def _discover(self, params: dict) -> dict:
        """The stateless revision: no handshake, and every result carries the server identity."""
        requested = _meta(params).get("io.modelcontextprotocol/protocolVersion")
        if requested is not None and requested != STATELESS_VERSION:
            raise CallRefused(UNSUPPORTED_VERSION, f"unsupported protocol version {requested!r}")
        self.stateless = True
        return {
            "protocolVersions": [*PROTOCOL_VERSIONS, STATELESS_VERSION],
            "capabilities": capabilities(write=self.write),
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        }

    def _call_tool(self, params: dict) -> dict:
        """One tool call: the name must be registered, the arguments must be an object."""
        name = params.get("name")
        if not isinstance(name, str):
            raise CallRefused(tools.INVALID_PARAMS, "tools/call needs a name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise CallRefused(tools.INVALID_PARAMS, "tools/call arguments must be an object")
        return tools.call(name, arguments, write=self.write, defaults=self.defaults, cwd=self.cwd)


INSTRUCTIONS = (
    "Read-only access to Firefight game data and mod projects. Every tool runs the same command "
    "as the editor CLI; a tool result with isError true carries the CLI exit code, and a refused "
    "call reports a JSON-RPC error. Writes are confined to the project directory and are refused "
    "for the stock scope."
)


def capabilities(*, write: bool) -> dict:
    """The capability block both protocol families report."""
    return {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
        "prompts": {"listChanged": False},
        "experimental": {"firefightEditorWrite": write},
    }


def _meta(params: dict) -> dict:
    """The ``_meta`` block of a request, else an empty one."""
    meta = params.get("_meta")
    return meta if isinstance(meta, dict) else {}


def _error(identifier, code: int, message: str) -> dict:
    """One JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def parse_argv(argv: list[str]) -> tuple[dict, bool, bool]:
    """Split the command line into options, a help flag and a version flag."""
    options: dict[str, str] = {}
    help_flag = False
    version_flag = False
    for token in argv:
        if token in ("--help", "-h", "help"):
            help_flag = True
        elif token == "--version":
            version_flag = True
        elif token == "--write":
            options["write"] = "1"
        elif "=" in token and not token.startswith("-"):
            name, value = token.split("=", 1)
            options[name] = value
        else:
            raise CallRefused(INVALID_REQUEST, f"unknown option {token!r}; try --help")
    return options, help_flag, version_flag


def main(argv: list[str] | None = None) -> int:
    """Run one stdio session, or print usage; returns the exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    stdout = sys.stdout
    try:
        options, help_flag, version_flag = parse_argv(argv)
    except CallRefused as refused:
        print(str(refused), file=sys.stderr)
        return 2
    if help_flag:
        print(USAGE)
        return 0
    if version_flag:
        print(f"{SERVER_NAME} {VERSION}")
        return 0
    defaults = {name: options[name] for name in ("root", "workspace", "firefight") if options.get(name)}
    server = Server(write=options.get("write") == "1", defaults=defaults)
    return serve(server, sys.stdin, stdout)


def serve(server: Server, stream, out) -> int:
    """Read one JSON-RPC message per line until the stream ends."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer = _error(None, PARSE_ERROR, "the line is not JSON")
        else:
            answer = server.handle(message)
        if answer is None:
            continue
        out.write(json.dumps(answer, ensure_ascii=False) + "\n")
        out.flush()
    return 0
