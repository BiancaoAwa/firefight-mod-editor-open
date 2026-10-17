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

import ipaddress
import json
import secrets
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.cli.scope import UsageError
from core.mcp import server as mcp_server
from core.web.i18n import tr

HOSTS = {"local": "127.0.0.1", "lan": "0.0.0.0"}
DEFAULT_PORT = 8790
MAX_BODY = 1_000_000
TOKEN_HEADER = "X-Ff-Token"
PUBLIC_SERVICES = ("https://api.ipify.org", "https://ifconfig.me/ip")
PUBLIC_TIMEOUT = 4.0


def bind_address(host: str) -> str:
    """The address to bind: a named choice, or the IP address the caller gave."""
    if host in HOSTS:
        return HOSTS[host]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise UsageError(tr("监听地址是 local、lan 或一个 IP 地址，不是 {}。", host)) from None
    return host


def local_addresses(bind: str) -> list[str]:
    """The addresses a client can dial through a socket listening on ``bind``.

    A socket on ``0.0.0.0`` has no single address to show, so the list names the interfaces
    this machine holds. The outbound one comes first because that is the address a remote
    client can actually reach.
    """
    if bind not in ("0.0.0.0", "::"):
        return [bind]
    found: list[str] = []

    def keep(address: str) -> None:
        if _dialable(address) and address not in found:
            found.append(address)

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 53))
        keep(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            keep(info[4][0])
    except OSError:
        pass
    if "127.0.0.1" not in found:
        found.append("127.0.0.1")
    return found


def _dialable(address: str) -> bool:
    """Whether another machine can reach this address: no loopback, no link-local, no wildcard."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified)


def public_address(timeout: float = PUBLIC_TIMEOUT) -> str | None:
    """The address this network presents to the outside, as a remote service reports it.

    The machine's own interfaces only carry the private address, so the public one is read
    from outside. Offline, or with every service down, this returns None and the page says
    the address could not be read.
    """
    for service in PUBLIC_SERVICES:
        try:
            with urllib.request.urlopen(service, timeout=timeout) as answer:
                text = answer.read(64).decode("ascii", "replace").strip()
            address = ipaddress.ip_address(text)
        except (OSError, ValueError):
            continue
        return str(address)
    return None


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
        self._public: str | None = None
        self._public_checked = False

    def state(self) -> dict:
        with self._lock:
            state = dict(self._state)
            if state:
                state["public"] = self._public
                state["public_checked"] = self._public_checked
            return state

    def refresh_public(self) -> str | None:
        """Read the outward address again, in the caller's thread, and report it."""
        found = public_address()
        with self._lock:
            self._public = found
            self._public_checked = True
        return found

    def _probe_public(self) -> None:
        found = public_address()
        with self._lock:
            self._public = found
            self._public_checked = True

    def running(self) -> bool:
        with self._lock:
            return self._server is not None

    def start(self, *, host: str, port: int, write: bool, defaults: dict, cwd: Path) -> dict:
        """Open the listener, or raise UsageError with the reason it cannot open."""
        bind = bind_address(host)
        if not 1 <= port <= 65535:
            raise UsageError(tr("端口要在 1 到 65535 之间，不是 {}。", port))
        with self._lock:
            if self._server is not None:
                raise UsageError(tr("已经有一个监听在 {} 上。", self._state.get("url", "")))
            token = secrets.token_urlsafe(18)
            try:
                server = McpHttpServer((bind, port), write=write, defaults=defaults,
                                       cwd=cwd, token=token)
            except OSError as error:
                raise UsageError(tr("监听打不开 {}:{}：{}", bind, port, error)) from None
            thread = threading.Thread(target=server.serve_forever, name="mcp-listener", daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            chosen = server.server_address[1]
            addresses = [f"http://{address}:{chosen}/" for address in local_addresses(bind)]
            self._state = {
                "host": host,
                "bind": bind,
                "port": chosen,
                "url": addresses[0],
                "addresses": addresses,
                "token": token,
                "write": write,
                "at": time.strftime("%H:%M:%S"),
            }
            self._public = None
            self._public_checked = False
            threading.Thread(target=self._probe_public, name="mcp-public", daemon=True).start()
            # The lock above is held here, so ``state()`` would deadlock on a plain Lock.
            opened = dict(self._state)
            opened["public"] = self._public
            opened["public_checked"] = self._public_checked
            return opened

    def stop(self) -> dict:
        with self._lock:
            if self._server is None:
                raise UsageError(tr("现在没有在监听。"))
            server, self._server = self._server, None
            self._thread = None
            state = dict(self._state)
            self._state = {}
            self._public = None
            self._public_checked = False
        server.shutdown()
        server.server_close()
        return state
