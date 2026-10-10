"""Local web UI: one page per command, rendered on the server from the CLI payloads.

Single-threaded, GET only, no JavaScript and no writes; the route table is in ``docs/web.md``.
"""

import json
import shlex
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from core.errors import FfError

from core.cli.commands import ALIASES, DEFAULT_LIMIT, VERSION, Context, command_names, run_command
from core.cli.main import parse_argv
from core.cli.scope import UsageError, resolve_all, resolve_scope, split_spec
import re
from html import escape
from urllib.parse import parse_qsl, urlencode


STYLE = """
body { background: #efefef; color: #000; font-family: Verdana, Geneva, Arial, sans-serif;
       font-size: 13px; margin: 12px; }
h1 { font-size: 18px; margin: 0 0 2px 0; }
h2 { font-size: 14px; margin: 18px 0 6px 0; border-bottom: 1px solid #999; padding-bottom: 2px; }
h3 { font-size: 13px; margin: 14px 0 4px 0; }
a { color: #0000cc; }
a:visited { color: #660099; }
.head { margin-bottom: 6px; }
.sub { color: #444; }
.nav a { margin-right: 8px; }
hr { border: 0; border-top: 1px solid #bbb; margin: 10px 0; }
table { border-collapse: collapse; background: #fff; margin: 6px 0; }
th, td { border: 1px solid #999; padding: 2px 6px; text-align: left; vertical-align: top; }
th { background: #ddd; font-weight: bold; }
td.num, th.num { text-align: right; }
pre { background: #fff; border: 1px solid #999; padding: 6px; margin: 6px 0;
      font-family: Consolas, "Courier New", monospace; font-size: 12px;
      white-space: pre; overflow-x: auto; }
code { font-family: Consolas, "Courier New", monospace; font-size: 12px; background: #e6e6e6;
       padding: 0 2px; }
form { background: #f7f7f7; border: 1px solid #bbb; padding: 6px; margin: 6px 0; }
label { margin-right: 10px; }
input[type=text] { border: 1px solid #888; font-family: inherit; font-size: 13px; padding: 1px 3px; }
input[type=submit] { font-family: inherit; font-size: 13px; }
select { font-family: inherit; font-size: 13px; }
.note { color: #444; }
.warn { background: #fff8d0; border: 1px solid #c8b45a; padding: 6px; margin: 6px 0; }
.bad { background: #ffd9d9; border: 1px solid #c86a6a; padding: 6px; margin: 6px 0; }
.ok { background: #dff5df; border: 1px solid #6ac86a; padding: 6px; margin: 6px 0; }
.empty { color: #666; }
.foot { color: #666; font-size: 12px; }
.crumbs { margin-bottom: 6px; color: #444; }
""".strip()

FOOTER = "服务端渲染 · 无 JavaScript · 数据与 <code>ff --json</code> 完全一致 · 本界面只读"


def esc(value) -> str:
    """Escape data for a page body."""
    return escape(str(value))


def att(value) -> str:
    """Escape data for an attribute value."""
    return escape(str(value), quote=True)


class Url:
    """Builds links that keep the current scope and access token."""

    def __init__(self, scope: str = "", token: str = "") -> None:
        self.scope = scope
        self.token = token

    def __call__(self, route: str = "index", **params) -> str:
        query = {key: value for key, value in params.items() if value not in (None, "")}
        if self.scope:
            query.setdefault("scope", self.scope)
        if self.token:
            query.setdefault("t", self.token)
        encoded = urlencode(query)
        path = "" if route in ("", "index") else route
        return f"/{path}" + (f"?{encoded}" if encoded else "")


def layout(title: str, body: str, nav: str = "", subtitle: str = "") -> str:
    """One complete page."""
    head = f'<div class="head"><h1>{esc(title)}</h1>'
    if subtitle:
        head += f'<div class="sub">{esc(subtitle)}</div>'
    head += "</div>"
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>\n{STYLE}\n</style>\n</head>\n<body>\n"
        f"{head}\n"
        + (f'<div class="nav">{nav}</div>\n' if nav else "")
        + "<hr>\n"
        f"{body}\n"
        "<hr>\n"
        f'<div class="foot">{FOOTER}</div>\n'
        "</body>\n</html>\n"
    )


def nav_bar(url: Url, links: dict[str, str] | None = None) -> str:
    """The line of section links, with the current scope and the exit link."""
    links = links or {"index": "首页", "list": "实体列表", "find": "查找", "deps": "引用查询", "check": "体检", "stats": "统计", "cmd": "命令行", "help": "帮助"}
    parts = [f'<a href="{att(url(route))}">{esc(label)}</a>' for route, label in links.items()]
    parts.append(f'<span class="sub">作用域 {esc(url.scope or "-")}</span>')
    parts.append(f'<span class="sub">| <a href="{att(url("quit"))}">退出</a></span>')
    return " ".join(parts)


def h2(text: str) -> str:
    """A section heading."""
    return f"<h2>{esc(text)}</h2>"


def h3(text: str) -> str:
    """A sub-heading."""
    return f"<h3>{esc(text)}</h3>"


def note(text: str) -> str:
    """A grey explanatory line."""
    return f'<p class="note">{esc(text)}</p>'


def note_html(markup: str) -> str:
    """A grey explanatory line that already contains markup."""
    return f'<p class="note">{markup}</p>'


def warn(text: str) -> str:
    """A highlighted warning box."""
    return f'<div class="warn">{esc(text)}</div>'


def bad(text: str) -> str:
    """A highlighted failure box."""
    return f'<div class="bad">{esc(text)}</div>'


def good(text: str) -> str:
    """A highlighted success box."""
    return f'<div class="ok">{esc(text)}</div>'


def pre(text: str) -> str:
    """A monospace block with the given text, escaped."""
    return f"<pre>{esc(text)}</pre>"


def link(href: str, label: str) -> str:
    """A link with both parts escaped."""
    return f'<a href="{att(href)}">{esc(label)}</a>'


def mono(text: str) -> str:
    """Inline monospace."""
    return f"<code>{esc(text)}</code>"


def table(headers: list[str], rows: list[list[str]], empty: str = "没有数据") -> str:
    """A bordered table; cells are markup and must be escaped by the caller."""
    if not rows:
        return f'<p class="empty">{esc(empty)}</p>'
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table><tr>{head}</tr>{body}</table>'


def kv(pairs: list[tuple[str, str]]) -> str:
    """A two-column table of label/value pairs; values are markup."""
    rows = [[esc(label), value] for label, value in pairs]
    return table(["项", "值"], rows)


def pager(url: Url, route: str, page: int, total: int, size: int, last: int, **params) -> str:
    """First/previous/next/last links when the list runs over one page."""
    if last <= 1:
        return note(f"共 {total} 条")
    def href(target: int) -> str:
        return att(url(route, page=target, **params))
    parts = [f"共 {total} 条，第 {page} / {last} 页"]
    if page > 1:
        parts.append(f'<a href="{href(1)}">首页</a>')
        parts.append(f'<a href="{href(page - 1)}">上一页</a>')
    if page < last:
        parts.append(f'<a href="{href(page + 1)}">下一页</a>')
        parts.append(f'<a href="{href(last)}">末页</a>')
    return '<p class="note">' + " · ".join(parts) + "</p>"


def crumbs(items: list[tuple[str, str]]) -> str:
    """A breadcrumb line of (href, label) pairs; the last one is plain text."""
    parts = []
    for index, (href, label) in enumerate(items):
        if href and index < len(items) - 1:
            parts.append(link(href, label))
        else:
            parts.append(esc(label))
    return '<div class="crumbs">' + " › ".join(parts) + "</div>"


def form(action: str, fields: list[str], submit: str = "查询") -> str:
    """A GET form from pre-built field markup.

    A GET submission replaces the query string of the action with the form's own fields, so
    the persistent parameters that `Url` puts in the action (the scope and the access token)
    are re-emitted as hidden inputs and the action is reduced to its bare path. Without this a
    form on a non-default scope silently searched the stock data, and with a token configured
    every form answered 400.
    """
    path, _, query = action.partition("?")
    markup = " ".join(fields)
    named = set(re.findall(r'name="([^"]*)"', markup))
    carry = [
        hidden(name, value)
        for name, value in parse_qsl(query, keep_blank_values=False)
        if name not in named  # a field of the form itself wins, so no parameter is sent twice
    ]
    body = " ".join(carry + fields)
    return f'<form method="get" action="{att(path)}">{body} <input type="submit" value="{att(submit)}"></form>'


def text_field(name: str, label: str, value: str = "", size: int = 30) -> str:
    """A labelled text input."""
    return f'<label>{esc(label)} <input type="text" name="{att(name)}" value="{att(value)}" size="{size}"></label>'


def checkbox(name: str, label: str, checked: bool, value: str = "1") -> str:
    """A labelled checkbox."""
    mark = " checked" if checked else ""
    return f'<label><input type="checkbox" name="{att(name)}" value="{att(value)}"{mark}> {esc(label)}</label>'


def select_field(name: str, label: str, options: list[tuple[str, str]], selected: str = "") -> str:
    """A labelled drop-down; options are (value, label) pairs."""
    items = "".join(
        f'<option value="{att(value)}"' + (" selected" if value == selected else "") + f">{esc(text)}</option>"
        for value, text in options
    )
    return f'<label>{esc(label)} <select name="{att(name)}">{items}</select></label>'


def hidden(name: str, value: str) -> str:
    """A hidden input."""
    return f'<input type="hidden" name="{att(name)}" value="{att(value)}">'


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RESERVED = ("scope", "t", "command", "selector", "page")
TEXT_VIEWS = ("raw", "toml", "xml")

# Commands the UI refuses: one writes files outside the scope, the other would try to bind a
# second port. Everything else is read-only by construction (docs/cli.md).
WRITING_COMMANDS = ("export", "web")


def read_only_command(name: str) -> str:
    """Canonical name of a command the UI may run, or a UsageError."""
    canonical = ALIASES.get(name, name)
    if canonical not in command_names():
        raise UsageError(f"没有这个命令：{name}；可用：{', '.join(command_names())}")
    if canonical in WRITING_COMMANDS:
        raise UsageError(f"{canonical} 在浏览器里不可用（它会写文件）；请在命令行里运行")
    return canonical


def split_command_line(line: str) -> list[str]:
    """Tokens of one command line, keeping a quoted path such as "American-Rifle Squad" whole."""
    try:
        tokens = shlex.split(line, posix=False)
    except ValueError as error:
        raise UsageError(f"这一行读不出来：{error}")
    return [token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in "\"'" else token for token in tokens]


def _int_option(options: dict[str, str], name: str, default: int) -> int:
    """Read a positive integer option, with a readable error."""
    raw = options.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise UsageError(f"{name}={raw!r} is not a number") from None
    if value < 1:
        raise UsageError(f"{name}={raw!r} must be at least 1")
    return value


def safe_selector(selector: str) -> str:
    """Refuse a selector that could name a file outside the scope root.

    The CLI resolves a selector against the scope root; a web request is
    untrusted input, so absolute paths, drive letters and ``..`` segments are
    rejected before the command ever sees them (docs/web.md section on limits).
    """
    cleaned = selector.replace("\\", "/").strip()
    if not cleaned:
        return selector
    if cleaned.startswith("/") or cleaned.startswith("~") or ":" in cleaned:
        raise UsageError(f"selector={selector!r} must be a path inside the scope")
    if ".." in cleaned.split("/"):
        raise UsageError(f"selector={selector!r} must not contain '..'")
    return selector


class App:
    """One web session: the resolved options, the scope and the CLI bridge."""

    def __init__(self, options: dict[str, str], cwd, scope_name: str, page_size: int = DEFAULT_LIMIT, token: str = "") -> None:
        self.options = {key: value for key, value in options.items() if value not in (None, "")}
        self.cwd = cwd
        self.default_scope = scope_name
        self.page_size = page_size
        self.token = token

    # --- scope and command plumbing -----------------------------------------

    def scopes(self) -> dict:
        """Every scope this invocation can name."""
        try:
            return resolve_all(self.options, self.cwd)
        except UsageError:
            return {}

    def scope(self, name: str = ""):
        """Resolve a scope name, defaulting to the one the tool was started with."""
        wanted = name or self.default_scope
        known = self.scopes()
        if wanted in known:
            return known[wanted]
        return resolve_scope(wanted, self.options, self.cwd)

    def url(self, scope_name: str = "") -> Url:
        """Link builder bound to an access token."""
        return Url(scope=scope_name or self.default_scope, token=self.token)

    def call(self, command: str, scope, selector: str = "", **options):
        """Run one CLI command in-process and return its Result."""
        clean = {key: str(value) for key, value in options.items() if value not in (None, "")}
        selector = safe_selector(selector)
        spec = scope.name if not selector else f"{scope.name}/{selector}"
        _, relative, doc_path = split_spec(spec)
        context = Context(scope=scope, selector=relative, doc_path=doc_path, options=clean, cwd=self.cwd)
        return run_command(command, context)

    def call_from_query(self, command: str, scope, query: dict[str, str]):
        """Run a command from a page query: selector plus every other key=value."""
        selector = query.get("selector", "")
        options = {key: value for key, value in query.items() if key not in RESERVED}
        return self.call(command, scope, selector, **options)


class Handler(BaseHTTPRequestHandler):
    """GET router; every route returns HTML, /json returns the raw payload."""

    server_version = f"ff-web/{VERSION}"
    routes = ("index", "list", "show", "get", "find", "refs", "deps", "check", "stats", "cmd", "json", "help", "quit")

    # --- plumbing -----------------------------------------------------------

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        started = time.monotonic()
        parsed = urlparse(self.path)
        route = parsed.path.strip("/") or "index"
        query = {key: value[0] for key, value in parse_qs(parsed.query, keep_blank_values=True).items()}
        if route == "favicon.ico":
            self.respond(204, "", "text/plain; charset=utf-8")
            return
        if route not in self.routes:
            self.respond(404, self._error_page("没有这个页面", f"/{route}", "从上面的导航栏回到首页。"))
            return
        status = 200
        body = ""
        try:
            self.check_token(query)
            body = getattr(self, f"page_{route}")(query)
        except UsageError as error:
            status, body = 400, self._error_page("用法错误", str(error), "检查参数拼写；下面的表单给出可用取值。")
        except FfError as error:
            status, body = 500, self._error_page("读取失败", str(error), "文件可能损坏或不可解码；用 CLI 的 check 命令定位。")
        except Exception as error:  # keep the server alive and report what happened
            traceback.print_exc(file=sys.stderr)
            status, body = 500, self._error_page("内部错误", f"{type(error).__name__}: {error}", "这是界面的问题，请把上面那段命令回报。")
        if route == "json" and status == 200:
            self.respond(status, body, "text/plain; charset=utf-8")
        else:
            self.respond(status, body)
        self.note_request(status, started)

    # --- everything that is not a GET ---------------------------------------

    def _discard_body(self) -> None:
        """Read the request body before answering.

        The default 501 handling leaves the body unread, and closing a socket
        with unread data can reset the connection, so the client may see a
        connection error instead of the 501. Draining it keeps the answer.
        """
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            while True:
                header = self.rfile.readline(65536).strip()
                if not header:
                    break
                try:
                    size = int(header.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    while self.rfile.readline(65536).strip():
                        pass
                    break
                self.rfile.read(size)
                self.rfile.readline(65536)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > 0:
            self.rfile.read(length)

    def _reject_method(self) -> None:
        self._discard_body()
        page = self._error_page(
            "只支持 GET",
            f"{self.command} 不被支持",
            "这个界面是只读的：用上面的导航栏浏览，或者退回命令行。",
        )
        self.respond(501, page)

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self._reject_method()

    def do_PUT(self) -> None:  # noqa: N802 - http.server naming
        self._reject_method()

    def do_DELETE(self) -> None:  # noqa: N802 - http.server naming
        self._reject_method()

    def do_PATCH(self) -> None:  # noqa: N802 - http.server naming
        self._reject_method()

    def do_HEAD(self) -> None:  # noqa: N802 - http.server naming
        self._discard_body()
        self.send_response(501)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def check_token(self, query: dict[str, str]) -> None:
        """Refuse requests without the token when the tool was started with one."""
        if self.app.token and query.get("t") != self.app.token:
            raise UsageError("缺少访问令牌：请用启动时打印的完整网址打开")

    def respond(self, status: int, body: str, content_type: str = "text/html; charset=utf-8") -> None:
        """Send one response and close the connection."""
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def note_request(self, status: int, started: float) -> None:
        """One access line on stderr, so Ctrl-C still leaves a readable log."""
        if getattr(self.server, "quiet", False):
            return
        elapsed = (time.monotonic() - started) * 1000
        print(f"  {status} {self.path} ({elapsed:.0f} ms)", file=sys.stderr, flush=True)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        """Silence the default logger; note_request already reports the line."""

    def _error_page(self, title: str, detail: str, hint: str) -> str:
        url = self.app.url()
        return layout(
            f"{title} · Firefight 模组编辑器",
            bad(detail) + note(hint) + note_html(link(url("index"), "回到首页")),
            nav_bar(url),
            f"作用域 {self.app.default_scope}",
        )

    # --- shared builders ----------------------------------------------------

    def shell(self, title: str, body: str, scope_name: str, subtitle: str = "") -> str:
        """A page with the standard navigation."""
        url = self.app.url(scope_name)
        return layout(title, body, nav_bar(url), subtitle or f"作用域 {scope_name}")

    def json_link(self, scope_name: str, command: str, **params) -> str:
        """A link to the same data as a raw payload."""
        return link(self.app.url(scope_name)("json", command=command, **params), "JSON")

    # --- pages --------------------------------------------------------------

    def page_index(self, query: dict[str, str]) -> str:
        """Scope inventory plus a cheap listing of the current scope."""
        scope = self.app.scope(query.get("scope", ""))
        known = self.app.scopes()
        url = self.app.url(scope.name)
        rows = []
        for name, found in sorted(known.items()):
            here = self.app.url(name)
            links = " · ".join(
                [
                    link(here("list"), "列表"),
                    link(here("stats"), "统计"),
                    link(here("check"), "体检"),
                ]
            )
            rows.append([link(here("index"), name), esc(str(found.root)), esc(found.origin), links])
        body = h2("可用的作用域")
        body += table(["作用域", "根目录", "来源", "操作"], rows)
        if not rows:
            body += warn("没有解析到任何作用域：用 root=<目录> 启动，或先建一个含 mod.toml 的工程。")

        listing = self.app.call("list", scope, "all")
        payload = listing.payload
        by_category: dict[str, int] = {}
        for entity in payload["entities"]:
            by_category[entity["category"]] = by_category.get(entity["category"], 0) + 1
        body += h2(f"当前作用域：{scope.name}")
        body += kv(
            [
                ("根目录", esc(payload["root"])),
                ("实体文件", esc(payload["count"])),
                ("来源", esc(scope.origin)),
            ]
        )
        category_rows = [
            [link(url("list", type=category), category), esc(count)]
            for category, count in sorted(by_category.items(), key=lambda item: (-item[1], item[0]))
        ]
        body += table(["分类", "数量"], category_rows, "这个作用域里没有实体文件")
        body += h2("查找")
        body += form(
            url("find"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("selector", "文件前缀", "", 24),
                text_field("tag", "标签", "", 12),
                text_field("value", "取值含", "", 16),
                checkbox("ignore_case", "忽略大小写", True),
            ],
            "查找",
        )
        body += note("提示：列表页可以用路径片段过滤；统计、体检、引用查询都在导航栏里。")
        return self.shell("Firefight 模组编辑器", body, scope.name)

    def page_list(self, query: dict[str, str]) -> str:
        """Entity table with a text filter, a category filter and paging."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        wanted = query.get("type", "")
        prefix = query.get("prefix", "")
        payload = self.app.call("list", scope, "all", type=wanted or None).payload
        entities = payload["entities"]
        if prefix:
            needle = prefix.casefold()
            entities = [item for item in entities if needle in item["path"].casefold()]
        page = max(1, _int_option(query, "page", 1))
        size = self.app.page_size
        last = max(1, (len(entities) + size - 1) // size)
        page = min(page, last)
        window = entities[(page - 1) * size : page * size]
        rows = [
            [
                link(url("show", path=item["path"], as_="toml"), item["path"]),
                link(url("list", type=item["category"]), item["category"]),
                esc(item["format"]),
                esc(item["bytes"]),
            ]
            for item in window
        ]
        body = h2("实体列表")
        body += form(
            url("list"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("prefix", "路径含", prefix, 28),
                select_field(
                    "type",
                    "分类",
                    [("", "全部")] + [(name, name) for name in sorted({item["category"] for item in payload["entities"]})],
                    wanted,
                ),
            ],
            "过滤",
        )
        body += note(f"根目录 {payload['root']} · 命中 {len(entities)} / {payload['count']} 个实体文件")
        body += table(["路径", "分类", "格式", "字节"], rows, "没有匹配的实体")
        body += pager(url, "list", page, len(entities), size, last, prefix=prefix, type=wanted)
        body += note_html("等价命令：" + mono(f"ff {scope.name} list {prefix or 'all'} --json") + " · " + self.json_link(scope.name, "list", selector="all", type=wanted or None))
        return self.shell("实体列表", body, scope.name)

    def page_show(self, query: dict[str, str]) -> str:
        """One entity as raw text, TOML or XML, with its warnings."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        path = query.get("path", "")
        view = query.get("as", "toml")
        if view not in TEXT_VIEWS:
            raise UsageError(f"as={view!r} 不是 raw / toml / xml 之一")
        payload = self.app.call("show", scope, path, **{"as": view}).payload
        body = crumbs([(url("index"), "首页"), (url("list"), "列表"), ("", payload["path"])])
        body += h2(payload["path"])
        links = []
        for name in TEXT_VIEWS:
            label = {"raw": "原始内容", "toml": "TOML 视图", "xml": "XML 视图"}[name]
            links.append(link(url("show", path=payload["path"], **{"as": name}), f"[{label}]" if name != view else f"[{label} ←]"))
        links.append(link(url("refs", path=payload["path"]), "[本文件指向谁]"))
        links.append(self.json_link(scope.name, "show", selector=payload["path"], **{"as": view}))
        body += "<p>" + " ".join(links) + "</p>"
        warnings = payload.get("warnings") or []
        if warnings:
            body += warn(f"{len(warnings)} 条解析警告：" + "；".join(warnings[:5]) + ("；…" if len(warnings) > 5 else ""))
        if "text" in payload:
            body += pre(payload["text"])
        elif "toml" in payload:
            body += pre(payload["toml"])
        elif "xml" in payload:
            body += pre(payload["xml"])
        elif "values" in payload:
            body += h3(f"子树 {payload.get('key', '')}")
            body += table(
                ["路径", "行", "值"],
                [[esc(item["path"]), esc(item["line"]), esc(item["value"])] for item in payload["values"]],
            )
        else:
            body += note("这是列表文件的内容。")

        body += h2("读取字段")
        body += form(
            url("get"),
            [
                hidden("scope", scope.name),
                hidden("path", payload["path"]),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("field", "字段路径", "", 24),
            ],
            "取值",
        )
        body += note("字段路径相对根元素，点分，例如 name 或 ammo.type。")
        incoming = self.incoming_link(scope, payload["path"])
        if incoming:
            body += note_html("被引用情况：" + incoming)
        return self.shell(payload["path"], body, scope.name)

    def incoming_link(self, scope, path: str) -> str:
        """Best-effort link to the incoming references of one entity's type token."""
        try:
            payload = self.app.call("get", scope, path, field="type").payload
        except (UsageError, FfError):
            return ""
        values = payload.get("values") or []
        if len(values) != 1:
            return ""
        token = str(values[0]["value"])
        return link(self.app.url(scope.name)("deps", value=token), f"谁引用了 {token}")

    def page_get(self, query: dict[str, str]) -> str:
        """The values of one field, with the document path and source line."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        path = query.get("path", "")
        field = query.get("field", "")
        payload = self.app.call("get", scope, path, field=field).payload
        body = crumbs([(url("index"), "首页"), (url("list"), "列表"), (url("show", path=payload["path"]), payload["path"]), ("", payload["field"])])
        body += h2(f"{payload['path']} · {payload['field']}")
        body += table(
            ["文档路径", "行", "值"],
            [[esc(item["path"]), esc(item["line"]), esc(item["value"])] for item in payload["values"]],
        )
        body += note_html("等价命令：" + mono(f"ff {scope.name} get {payload['path']} field={field} --json") + " · " + self.json_link(scope.name, "get", selector=payload["path"], field=field))
        return self.shell(f"{payload['path']} · {payload['field']}", body, scope.name)

    def page_find(self, query: dict[str, str]) -> str:
        """Tag, value and document-path search."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        selector = query.get("selector", "") or "all"
        options = {key: query[key] for key in ("tag", "value", "path", "ignore_case") if query.get(key)}
        options["limit"] = str(self.app.page_size)
        form_html = form(
            url("find"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("selector", "文件前缀(all)", selector, 20),
                text_field("tag", "标签", query.get("tag", ""), 12),
                text_field("value", "取值含", query.get("value", ""), 16),
                text_field("path", "文档路径前缀", query.get("path", ""), 16),
                checkbox("ignore_case", "忽略大小写", query.get("ignore_case", "1") == "1"),
            ],
            "查找",
        )
        body = h2("查找")
        body += form_html
        if not options.get("tag") and not options.get("value") and not options.get("path"):
            body += note("至少填一个条件：标签名、取值包含、或文档路径前缀。")
            return self.shell("查找", body, scope.name)
        payload = self.app.call("find", scope, selector, **options).payload
        body += note(f"命中 {payload['count']} 条" + ("（到达上限，请收窄条件）" if payload["truncated"] else ""))
        rows = []
        for item in payload["matches"]:
            if "error" in item:
                rows.append([esc(item["path"]), "", "", bad(item["error"])])
                continue
            rows.append(
                [
                    link(url("show", path=item["path"], **{"as": "toml"}), item["path"]),
                    esc(item["line"]),
                    esc(item["tag"]),
                    esc(item["value"]),
                ]
            )
        body += table(["文件", "行", "标签", "取值"], rows, "没有命中")
        return self.shell("查找", body, scope.name)

    def page_refs(self, query: dict[str, str]) -> str:
        """Outgoing references of one entity."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        path = query.get("path", "")
        payload = self.app.call("refs", scope, path).payload
        body = crumbs([(url("index"), "首页"), (url("list"), "列表"), (url("show", path=path), path), ("", "引用")])
        body += h2("本文件指向谁")
        by_kind = "、".join(f"{name}={count}" for name, count in sorted(payload["by_kind"].items())) or "无"
        body += note(f"{path} 共 {payload['count']} 条向外引用（{by_kind}）")
        shown = payload["references"][: self.app.page_size]
        rows = [
            [
                esc(item["source"]),
                esc(item["kind"]),
                link(url("deps", value=item["value"]), item["value"]),
                esc(item["document_path"]),
            ]
            for item in shown
        ]
        body += table(["来源", "类型", "取值", "文档路径"], rows, "没有向外引用")
        if len(payload["references"]) > len(shown):
            body += note(f"另有 {len(payload['references']) - len(shown)} 条未显示，用 JSON 看全部。")
        for item in payload.get("errors") or []:
            body += bad(f"{item['path']}: {item['error']}")
        body += note_html("取值一列可以点开，看谁引用了它。" + " · " + self.json_link(scope.name, "refs", selector=path))
        return self.shell(f"{path} · 引用", body, scope.name)

    def page_deps(self, query: dict[str, str]) -> str:
        """Incoming references of a token, with the resolved target."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        value = query.get("value", "")
        kind = query.get("kind", "")
        body = h2("谁引用了这个取值")
        body += form(
            url("deps"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("value", "取值", value, 30),
                text_field("kind", "类型(可空)", kind, 12),
            ],
            "查询",
        )
        if not value:
            body += note("填一个取值，例如 WEAPON_PISTOL_P38。")
            return self.shell("引用查询", body, scope.name)
        payload = self.app.call("deps", scope, "", **{"value": value, "kind": kind or None}).payload
        resolved = payload["resolved"]
        if payload["unresolved"]:
            body += warn(f"{value} 没有解析到任何实体文件。")
        else:
            targets = "、".join(link(url("show", path=target), target) for target in resolved)
            body += note_html(f"解析到：{targets}")
        body += note(f"共 {payload['count']} 条传入引用")
        shown = payload["references"][: self.app.page_size]
        rows = [
            [
                link(url("show", path=item["source"], **{"as": "toml"}), item["source"]),
                esc(item["kind"]),
                esc(item["document_path"]),
            ]
            for item in shown
        ]
        body += table(["来源文件", "类型", "文档路径"], rows, "没有传入引用")
        if len(payload["references"]) > len(shown):
            body += note(f"另有 {len(payload['references']) - len(shown)} 条未显示，用 JSON 看全部。")
        for item in payload.get("errors") or []:
            body += bad(f"{item['path']}: {item['error']}")
        body += note_html("等价命令：" + mono(f"ff {scope.name} deps value={value} --json") + " · " + self.json_link(scope.name, "deps", value=value, kind=kind or None))
        return self.shell(f"引用 {value}", body, scope.name)

    def page_check(self, query: dict[str, str]) -> str:
        """Load errors, warnings and dangling references of a selection."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        selector = query.get("selector", "") or "all"
        body = h2("工程体检")
        body += form(
            url("check"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("selector", "范围(目录前缀或 all)", selector, 26),
            ],
            "开始体检",
        )
        body += note("体检会把范围内的每个实体读一遍；原版数据 1840 个文件需要几十秒。")
        started = time.monotonic()
        payload = self.app.call("check", scope, selector).payload
        elapsed = time.monotonic() - started
        headline = (
            f"{payload['loaded']} / {payload['files']} 个文件读取成功，跳过 {payload['skipped']} 个列表文件，"
            f"{len(payload['errors'])} 个错误，{payload['warnings_total']} 条警告，{len(payload['dangling'])} 条悬空引用"
        )
        body += good(headline) if payload["ok"] else bad(headline)
        body += note(f"耗时 {elapsed:.1f} 秒 · 作用域 {scope.name} · 范围 {selector}")
        if payload["errors"]:
            body += h3("读取错误")
            body += table(["文件", "错误"], [[esc(item["path"]), esc(item["error"])] for item in payload["errors"]])
        if payload["dangling"]:
            body += h3("悬空引用")
            body += table(
                ["来源", "类型", "取值", "文档路径"],
                [
                    [
                        link(url("show", path=item["source"], **{"as": "toml"}), item["source"]),
                        esc(item["kind"]),
                        link(url("deps", value=item["value"]), item["value"]),
                        esc(item["document_path"]),
                    ]
                    for item in payload["dangling"][:100]
                ],
            )
            if len(payload["dangling"]) > 100:
                body += note(f"另有 {len(payload['dangling']) - 100} 条悬空引用未列出。")
        if payload["warning_samples"]:
            body += h3(f"警告样本（{payload['warning_files']} 个文件共 {payload['warnings_total']} 条）")
            rows = [
                [link(url("show", path=item["path"], **{"as": "toml"}), item["path"]), esc("；".join(item["warnings"]))]
                for item in payload["warning_samples"]
            ]
            body += table(["文件", "警告"], rows)
        body += note_html("等价命令：" + mono(f"ff {scope.name} check {selector} --json") + " · " + self.json_link(scope.name, "check", selector=selector))
        return self.shell("工程体检", body, scope.name)

    def page_stats(self, query: dict[str, str]) -> str:
        """Counts by category, format and root element."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        payload = self.app.call("stats", scope, "all").payload
        body = h2("统计")
        body += kv(
            [
                ("作用域", esc(payload["scope"])),
                ("根目录", esc(payload["root"])),
                ("文件", esc(payload["files"])),
                ("字节", esc(payload["bytes"])),
                ("列表文件", esc(payload["lists"])),
            ]
        )
        body += h3("按分类")
        body += table(
            ["分类", "数量"],
            [[link(url("list", type=name), name), esc(count)] for name, count in sorted(payload["by_category"].items(), key=lambda item: (-item[1], item[0]))],
        )
        body += h3("按格式")
        body += table(["格式", "数量"], [[esc(name), esc(count)] for name, count in sorted(payload["by_format"].items(), key=lambda item: (-item[1], item[0]))])
        body += h3("按根元素")
        body += table(["根元素", "数量"], [[esc(name), esc(count)] for name, count in sorted(payload["by_root"].items(), key=lambda item: (-item[1], item[0]))])
        if payload["errors"]:
            body += h3("读取失败")
            body += table(["文件", "错误"], [[esc(item["path"]), esc(item["error"])] for item in payload["errors"]])
        body += note_html("等价命令：" + mono(f"ff {scope.name} stats --json") + " · " + self.json_link(scope.name, "stats", selector="all"))
        return self.shell("统计", body, scope.name)

    def page_json(self, query: dict[str, str]) -> str:
        """The raw payload of one command, for cross-checking against the CLI."""
        scope = self.app.scope(query.get("scope", ""))
        command = query.get("command", "")
        read_only_command(command)
        result = self.app.call_from_query(command, scope, query)
        return json.dumps(result.payload, indent=2, ensure_ascii=False, default=str) + "\n"

    def page_cmd(self, query: dict[str, str]) -> str:
        """A command line: run one read-only ff command and print what the CLI prints.

        The line is what you would type after `ff`, optionally starting with a scope name
        (`Mod stats`). Quoting a path with a space works; `export` and `web` are refused
        because the page must stay read-only.
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        line = query.get("line", "").strip()
        as_json = query.get("json", "") in ("1", "yes", "true")
        body = h2("命令行")
        body += note("输入 ff 后面的部分即可，例如 list weapon、stats、show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml、deps value=WEAPON_PISTOL_P38。")
        body += note("可选在最前面写作用域（Firefight / Mod / 模组文件夹名）；路径带空格时用双引号。这里是只读界面：export 与 web 会被拒绝。")
        body += form(url("cmd"), [text_field("line", "命令", line, 80), checkbox("json", "JSON 输出", as_json)], "运行")
        examples = ["list weapon", "stats", "check", "deps value=WEAPON_PISTOL_P38", 'show "Data/Infantry/American-Rifle Squad.txt" as=toml']
        body += note_html("示例：" + " · ".join(link(url("cmd", line=item), item) for item in examples))
        if not line:
            return self.shell("命令行", body, scope.name)
        tokens = split_command_line(line)
        known = self.app.scopes()
        if len(tokens) > 1 and tokens[0] in known:
            scope = self.app.scope(tokens.pop(0))
            url = self.app.url(scope.name)
        invocation = parse_argv(tokens)
        if not invocation.positionals:
            raise UsageError("需要一个命令，例如 list weapon；把这一行补全再运行")
        command = read_only_command(invocation.positionals[0])
        selector = " ".join(invocation.positionals[1:])
        started = time.monotonic()
        result = self.app.call(command, scope, selector, **invocation.options)
        elapsed = time.monotonic() - started
        shown = f"{scope.name} {command}" + (f" {selector}" if selector else "")
        body += h2("输出")
        if as_json:
            body += pre(json.dumps(result.payload, indent=2, ensure_ascii=False, default=str))
        else:
            body += pre(result.text or "（这条命令没有文本输出；勾上 JSON 输出看载荷）")
        rows = [("作用域", esc(scope.name)), ("命令", esc(command)), ("选择器", esc(selector or "all"))]
        if invocation.options:
            rows.append(("选项", esc(", ".join(f"{key}={value}" for key, value in sorted(invocation.options.items())))))
        rows.append(("退出码", f"{result.code}（0 成功，1 已执行但有失败）"))
        rows.append(("耗时", f"{elapsed:.2f} s"))
        body += table(["项", "值"], rows)
        body += note_html(
            "等价命令行：" + mono(f"ff {shown}" + (" --json" if as_json else ""))
            + " · " + link(url("json", command=command, selector=selector or "all", **invocation.options), "原始 JSON")
            + " · " + link(url("cmd", line=shown + (" --json" if as_json else "")), "按 JSON 重跑")
        )
        return self.shell("命令行", body, scope.name)

    def page_help(self, query: dict[str, str]) -> str:
        """What every page does and the CLI command behind it."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        body = h2("页面与等价命令")
        rows = [
            [link(url("index"), "/"), "作用域与清单", mono(f"ff {scope.name} list")],
            [link(url("list"), "/list"), "实体表格，可按路径片段与分类过滤", mono(f"ff {scope.name} list <前缀>")],
            [link(url("show", path=""), "/show"), "一个实体的原始 / TOML / XML 视图", mono(f"ff {scope.name} show <路径> as=toml")],
            [link(url("get", path=""), "/get"), "某个字段的取值、文档路径与行号", mono(f"ff {scope.name} get <路径> field=<字段>")],
            [link(url("find"), "/find"), "按标签、取值或文档路径搜索", mono(f"ff {scope.name} find <前缀> tag=…")],
            [link(url("refs", path=""), "/refs"), "一个实体指向谁", mono(f"ff {scope.name} refs <路径>")],
            [link(url("deps"), "/deps"), "谁引用了某个取值", mono(f"ff {scope.name} deps value=<取值>")],
            [link(url("check"), "/check"), "读取错误、警告与悬空引用", mono(f"ff {scope.name} check <前缀>")],
            [link(url("stats"), "/stats"), "按分类、格式、根元素统计", mono(f"ff {scope.name} stats")],
            [link(url("cmd"), "/cmd"), "一行命令，输出与 CLI 完全相同（只读命令）", mono(f"ff {scope.name} <命令> <选择器> 键=值")],
            [link(url("json", command="list", selector="all"), "/json"), "任何命令的原始 JSON", mono("加 --json 的同一个命令")],
        ]
        body += table(["页面", "做什么", "等价命令"], rows)
        body += h2("说明")
        body += note("这个界面只读：所有页面都走同一套 CLI 查询代码，不写任何文件。写数据的能力还在设计里（事件日志与回滚里程碑）。")
        body += note("链接里的 scope 参数指定作用域，t 参数是访问令牌（启动时带 token= 才需要）。")
        body += note("单线程服务，一次处理一个请求；Ctrl-C 或页面上的「退出」停止。")
        return self.shell("帮助", body, scope.name)

    def page_quit(self, query: dict[str, str]) -> str:
        """Stop the server from the browser; /quit asks first, /quit?do=1 does it.

        A GET is the only verb this interface has (no JavaScript, no forms that
        POST), so the exit is a two-step page: a link can be followed by a
        prefetcher or by accident, a second deliberate click cannot.
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        if query.get("do", "") not in ("1", "yes", "true"):
            body = h2("退出 Web UI")
            body += note("这个按钮会停止 127.0.0.1 上的本地服务进程，然后你可以关掉这个窗口。")
            body += note("它不改任何数据文件，也不影响正在跑的编辑器 CLI。")
            body += form(url("quit", do="1"), [], "退出 Web UI")
            body += note_html("返回 " + link(url("index"), "首页"))
            return self.shell("退出", body, scope.name)
        self.server.request_quit()  # type: ignore[attr-defined]
        body = good("已退出：服务正在停止，刷新这个页面也不会再有响应。")
        body += note("窗口里按 Ctrl-C 或直接关掉窗口即可；要重新打开界面，用启动器再启动一次。")
        body += note_html(link(url("index"), "万一服务还在，回到首页"))
        return self.shell("已退出", body, scope.name)


class FfWebServer(ThreadingHTTPServer):
    """HTTP server that carries the App, one thread per connection.

    Threaded on purpose: a browser opens speculative connections and leaves them
    idle, and a single-threaded server would sit on such a socket, reading a
    request line that never comes, while every other request waits behind it —
    the page then looks frozen even though nothing is wrong. The threads are
    daemons and the server does not wait for them when it closes, so `退出` ends
    the process even with a connection still open.
    """

    daemon_threads = True
    block_on_close = False

    def __init__(self, address, app: App) -> None:
        self.app = app
        self.quit_requested = False
        super().__init__(address, Handler)

    def request_quit(self) -> None:
        """Stop serving after the current request, from inside a handler.

        ``shutdown()`` waits for ``serve_forever`` to return, and the handler
        runs on that same single thread, so calling it in place would deadlock;
        a helper thread does it instead, with a short delay so the goodbye page
        reaches the browser before the socket closes.
        """
        if self.quit_requested:
            return
        self.quit_requested = True
        threading.Thread(target=self._stop_soon, daemon=True).start()

    def _stop_soon(self) -> None:
        time.sleep(0.2)
        self.shutdown()


def port_is_taken(port: int, host: str = HOST, timeout: float = 0.5) -> bool:
    """True when something already accepts connections on that port.

    Needed because ``HTTPServer`` sets ``SO_REUSEADDR``, and on Windows that lets a
    second bind of the same port succeed instead of failing: without this check a
    second UI would quietly share the port with the first one, and which of the two
    answers a request would be luck. Port 0 asks the system for a free port, so it
    can never be taken.
    """
    if not port:
        return False
    with socket.socket() as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def make_server(app: App, port: int = DEFAULT_PORT, host: str = HOST) -> FfWebServer:
    """Bind the server without serving, so tests can use port 0."""
    if port_is_taken(port, host):
        raise FfError(f"cannot listen on {host}:{port}: the port is already in use")
    return FfWebServer((host, port), app)


def serve(options: dict[str, str], cwd, scope_name: str, host: str = HOST) -> str:
    """Serve the UI until Ctrl-C; returns the address it listened on."""
    token = options.get("token", "")
    size = _int_option(options, "pagesize", DEFAULT_LIMIT)
    port = _int_option(options, "port", DEFAULT_PORT)
    app = App(options, cwd, scope_name, page_size=size, token=token)
    try:
        server = make_server(app, port, host)
    except OSError as error:
        raise FfError(f"cannot listen on {host}:{port}: {error}") from error
    address = f"http://{host}:{server.server_port}/"
    if token:
        address += f"?t={token}"
    print(f"Firefight 模组编辑器 Web UI · 作用域 {scope_name}", flush=True)
    print(f"  根目录   {app.scope(scope_name).root}", flush=True)
    print(f"  地址     {address}", flush=True)
    print("  只读界面，无 JavaScript；Ctrl-C 停止，或点页面上的「退出」", flush=True)
    if options.get("browser") not in (None, "", "0", "false", "no"):
        try:
            import webbrowser

            webbrowser.open(address)
        except Exception as error:  # a browser is a convenience, not a requirement
            print(f"  (cannot open a browser automatically: {error})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
    else:
        if server.quit_requested:
            print("\n已在浏览器里退出。", flush=True)
            # an ASCII marker on purpose: the launcher's watchdog reads this log to tell a
            # graceful stop from a killed process, and ASCII survives any code page
            print("web: stopped by the quit link", flush=True)
    finally:
        server.server_close()
    return address
