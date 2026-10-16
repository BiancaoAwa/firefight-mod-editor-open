"""A second, opt-in listener that answers MCP JSON-RPC over HTTP.

The MCP panel teaches clients to run ``python -m core.mcp`` over stdio. Some clients
only speak HTTP, so the panel can open one more socket in this process and answer the
same protocol there. The listener is off until it is asked for, binds exactly one host
and port, and carries its own token: the workbench pages need the web token, this
listener needs its own, and neither hands back anything but the protocol.

The socket is deliberately small: POST one JSON-RPC message, get one answer. No
streaming, no session ids beyond what the protocol itself carries, no file serving.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.cli.scope import UsageError
from core.mcp import server as mcp_server
from core.web.i18n import tr

HOSTS = {"local": "127.0.0.1", "lan": "0.0.0.0"}
DEFAULT_PORT = 8790
MAX_BODY = 1_000_000
TOKEN_HEADER = "X-Ff-Token"


class McpHttpServer(ThreadingHTTPServer):
    """The listener itself: one MCP server behind one HTTP endpoint."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, write: bool, defaults: dict, cwd: Path,
                 token: str) -> None:
        super().__init__(address, _Handler)
        self.protocol = mcp_server.Server(write=write, defaults=defaults, cwd=cwd)
        self.token = token
        self.writes_allowed = write


class _Handler(BaseHTTPRequestHandler):
    server_version = "firefight-mod-editor-mcp"

    def do_POST(self) -> None:  # noqa: N802 - the name http.server calls
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._refuse(413, f"body over {MAX_BODY} bytes")
            return
        if not self._token_is_right():
            self._refuse(403, "the token is missing or wrong")
            return
        raw = self.rfile.read(length)
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self._answer(400, {"jsonrpc": "2.0", "id": None,
                               "error": {"code": mcp_server.PARSE_ERROR, "message": str(error)}})
            return
        answer = self.server.protocol.handle(message)  # type: ignore[attr-defined]
        if answer is None:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._answer(200, answer)

    def do_GET(self) -> None:  # noqa: N802 - the name http.server calls
        self._refuse(405, "POST one JSON-RPC message; this endpoint serves nothing else")

    def _token_is_right(self) -> bool:
        token = self.headers.get(TOKEN_HEADER) or ""
        return secrets.compare_digest(token, self.server.token)  # type: ignore[attr-defined]

    def _answer(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, status: int, message: str) -> None:
        self._answer(status, {"jsonrpc": "2.0", "id": None,
                              "error": {"code": mcp_server.INVALID_REQUEST, "message": message}})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - the signature http.server calls
        """Stay quiet: the web server owns the log."""


class McpService:
    """The panel's listener, at most one at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: McpHttpServer | None = None
        self._thread: threading.Thread | None = None
        self._state: dict = {}

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def running(self) -> bool:
        with self._lock:
            return self._server is not None

    def start(self, *, host: str, port: int, write: bool, defaults: dict, cwd: Path) -> dict:
        """Open the listener, or raise UsageError with the reason it cannot open."""
        if host not in HOSTS:
            raise UsageError(tr("监听地址是 local 或 lan，不是 {}。", host))
        if not 1 <= port <= 65535:
            raise UsageError(tr("端口要在 1 到 65535 之间，不是 {}。", port))
        with self._lock:
            if self._server is not None:
                raise UsageError(tr("已经有一个监听在 {} 上。", self._state.get("url", "")))
            token = secrets.token_urlsafe(18)
            try:
                server = McpHttpServer((HOSTS[host], port), write=write, defaults=defaults,
                                       cwd=cwd, token=token)
            except OSError as error:
                raise UsageError(tr("监听打不开 {}:{}：{}", HOSTS[host], port, error)) from None
            thread = threading.Thread(target=server.serve_forever, name="mcp-listener", daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            self._state = {
                "host": host,
                "bind": HOSTS[host],
                "port": server.server_address[1],
                "url": f"http://{HOSTS[host]}:{server.server_address[1]}/",
                "token": token,
                "write": write,
                "at": time.strftime("%H:%M:%S"),
            }
            return dict(self._state)

    def stop(self) -> dict:
        with self._lock:
            if self._server is None:
                raise UsageError(tr("现在没有在监听。"))
            server, self._server = self._server, None
            self._thread = None
            state = dict(self._state)
            self._state = {}
        server.shutdown()
        server.server_close()
        return state
