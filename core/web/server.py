"""Local web UI: one page per command, rendered on the server from the CLI payloads.

GET only, and one inline script that only lays the workbench out; a page may run a writing
command, and the command's own gate (`--write`, project confinement, the stock-scope rule)
is what decides (docs/web.md).
"""

import json
import os
import shlex
import socket
import sys
import threading
import time
import traceback
import urllib.request
import contextvars
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import edit, journal, textio
from core.errors import FfError
from core.journal import EDITOR_DIR
from core.web import mcp_listener, tables
from core.web.i18n import DEFAULT as LANGUAGE_DEFAULT, current, html_lang, tr, use

from core.cli.commands import (
    ALIASES,
    DEFAULT_LIMIT,
    VERSION,
    Context,
    command_names,
    declared_lists,
    is_list_file,
    run_command,
)
from core.cli import specs
from core.cli.main import parse_argv
from core.cli.scope import UsageError, Scope, resolve_all, resolve_scope, split_spec
# the two resolvers that recognise a project and an editor folder; using them keeps the
# rules in one place (docs/project-layout.md section 10.1)
from core.cli.scope import _editor_root, _project_root
import re
from html import escape
from urllib.parse import parse_qsl, urlencode


STYLE = """
:root { --tree: 290px; --props: 350px; --output: 180px; --line: #a8a8a8; --face: #e6e6e6;
        --font: Tahoma, "Arial Narrow", "Microsoft YaHei UI", "Segoe UI", Arial, sans-serif;
        --mono: Consolas, "Courier New", monospace; --size: 15px; }
* { box-sizing: border-box; }
body { background: #efefef; color: #000; font-family: var(--font);
       font-size: var(--size); margin: 0; height: 100vh; overflow: hidden; display: grid;
       grid-template-columns: var(--tree) 5px minmax(0, 1fr) 5px var(--props);
       grid-template-rows: auto auto minmax(0, 1fr) 5px var(--output) auto;
       grid-template-areas: "menu menu menu menu menu"
                            "tool tool tool tool tool"
                            "tree g1 doc g2 props"
                            "g3 g3 g3 g3 g3"
                            "out out out out out"
                            "stat stat stat stat stat"; }
body.folded-tree { --tree: 0px; }
body.folded-props { --props: 0px; }
body.folded-output { --output: 0px; }
body.folded-tree .pane-tree, body.folded-tree [data-gutter="tree"],
body.folded-props .pane-props, body.folded-props [data-gutter="props"],
body.folded-output .pane-output, body.folded-output [data-gutter="output"] { display: none; }
h1 { font-size: 18px; margin: 0 0 3px 0; }
h2 { font-size: 16px; margin: 16px 0 7px 0; border-bottom: 1px solid #999; padding-bottom: 3px; }
h3 { font-size: 15px; margin: 14px 0 5px 0; }
a { color: #0000cc; }
a:visited { color: #660099; }
.head { margin-bottom: 8px; }
.sub { color: #444; }
.nav a { margin-right: 10px; }
hr { border: 0; border-top: 1px solid #bbb; margin: 12px 0; }
table { border-collapse: collapse; background: #fff; margin: 8px 0; }
th, td { border: 1px solid #999; padding: 3px 8px; text-align: left; vertical-align: top; }
th { background: #ddd; font-weight: bold; }
td.num, th.num { text-align: right; }
pre { background: #fff; border: 1px solid #999; padding: 8px; margin: 8px 0;
      font-family: var(--mono); font-size: 13px;
      white-space: pre; overflow-x: auto; }
code { font-family: var(--mono); font-size: 13px; background: #e6e6e6;
       padding: 0 3px; }
form { background: #f7f7f7; border: 1px solid #bbb; padding: 8px; margin: 8px 0; }
label { margin-right: 12px; }
input[type=text] { border: 1px solid #888; font-family: inherit; font-size: var(--size);
                   padding: 2px 5px; }
input[type=submit] { font-family: inherit; font-size: var(--size); padding: 2px 10px; }
select { font-family: inherit; font-size: var(--size); }
.note { color: #444; }
.warn { background: #fff8d0; border: 1px solid #c8b45a; padding: 8px; margin: 8px 0; }
.bad { background: #ffd9d9; border: 1px solid #c86a6a; padding: 8px; margin: 8px 0; }
.ok { background: #dff5df; border: 1px solid #6ac86a; padding: 8px; margin: 8px 0; }
.empty { color: #666; }
.foot { color: #666; font-size: 14px; }
.crumbs { margin-bottom: 8px; color: #444; }
/* workbench: menu bar, tool bar, three side panes, status bar */
.menubar { grid-area: menu; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
           background: var(--face); border-bottom: 1px solid var(--line); padding: 4px 10px; }
.menubar .brand { font-weight: bold; }
.menubar .menu { display: flex; gap: 12px; flex-wrap: wrap; }
.toolbar { grid-area: tool; display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
           background: #f4f4f4; border-bottom: 1px solid #c8c8c8; padding: 4px 10px; }
.tbtn { border: 1px solid #b0b0b0; background: #fbfbfb; padding: 2px 10px; text-decoration: none;
        color: #000; font-family: inherit; font-size: 14px; }
.tbtn[aria-pressed="true"] { background: #d6d6d6; border-color: #808080; }
.pane { overflow: auto; background: #fff; min-height: 0; }
.pane-h { position: sticky; top: 0; background: var(--face); border-bottom: 1px solid #c8c8c8;
          padding: 3px 8px; font-weight: bold; }
.pane-b { padding: 5px 8px; }
.pane-tree { grid-area: tree; border-right: 1px solid #c8c8c8; }
.pane-props { grid-area: props; border-left: 1px solid #c8c8c8; }
.pane-output { grid-area: out; border-top: 1px solid #c8c8c8;
               font-family: var(--mono); font-size: 14px; }
.pane-doc { grid-area: doc; display: flex; flex-direction: column; min-height: 0; background: #efefef; }
.tabs { display: flex; gap: 3px; padding: 4px 8px 0 8px; background: var(--face);
        border-bottom: 1px solid #c8c8c8; overflow-x: auto; }
.tabs a { border: 1px solid #b0b0b0; border-bottom: none; background: #f4f4f4; padding: 3px 12px;
          text-decoration: none; color: #000; white-space: nowrap; }
.tabs a[aria-current="true"] { background: #fff; font-weight: bold; }
.doc-body { overflow: auto; padding: 10px 12px; background: #fff; flex: 1; min-height: 0; }
.gutter { background: #dcdcdc; }
.gutter:hover { background: #c0c0c0; }
[data-gutter="tree"] { grid-area: g1; cursor: col-resize; }
[data-gutter="props"] { grid-area: g2; cursor: col-resize; }
[data-gutter="output"] { grid-area: g3; cursor: row-resize; }
.statusbar { grid-area: stat; display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
             background: var(--face); border-top: 1px solid var(--line); padding: 3px 10px; }
.tree-dir { margin-top: 5px; font-weight: bold; }
.tree-file { margin-left: 14px; }
details.tree-dir > summary { cursor: pointer; font-weight: bold; }
details.tree-dir > details { margin-left: 14px; }
.tree-search { display: flex; gap: 4px; align-items: center; margin-bottom: 5px; }
.tree-search input[type=text] { flex: 1; min-width: 0; }
.gallery { display: flex; flex-wrap: wrap; gap: 10px; }
.tile { margin: 0; width: 160px; background: #fff; border: 1px solid var(--line); padding: 5px; }
.tile figcaption { font-size: 13px; word-break: break-all; margin-top: 4px; }
.thumb { display: block; width: 148px; height: 112px; object-fit: contain; background:
         repeating-conic-gradient(#f4f4f4 0% 25%, #e6e6e6 0% 50%) 50% / 14px 14px; }
.tile audio { width: 148px; }
.preview { margin: 8px 0; }
.preview img { max-width: 100%; max-height: 260px; background:
               repeating-conic-gradient(#f4f4f4 0% 25%, #e6e6e6 0% 50%) 50% / 14px 14px; }
label.wide { display: block; margin: 8px 0; }
label.wide textarea { display: block; width: 100%; margin-top: 4px; font-family: var(--mono);
                      font-size: 13px; white-space: pre; }
""".strip()


SCRIPT = """
(function () {
  "use strict";
  var root = document.documentElement;
  var KEY = "ff.workbench";
  var WIDE = { tree: 290, props: 350, output: 180 };
  var state = { tree: WIDE.tree, props: WIDE.props, output: WIDE.output };
  try {
    var saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    for (var key in state) {
      if (typeof saved[key] === "number" && saved[key] >= 0 && saved[key] < 900) state[key] = saved[key];
    }
  } catch (error) { /* a locked-down browser simply keeps the defaults */ }

  function apply() {
    root.style.setProperty("--tree", state.tree + "px");
    root.style.setProperty("--props", state.props + "px");
    root.style.setProperty("--output", state.output + "px");
    var body = document.body;
    body.classList.toggle("folded-tree", state.tree < 8);
    body.classList.toggle("folded-props", state.props < 8);
    body.classList.toggle("folded-output", state.output < 8);
    var buttons = document.querySelectorAll("[data-fold]");
    for (var i = 0; i < buttons.length; i++) {
      var name = buttons[i].getAttribute("data-fold");
      buttons[i].setAttribute("aria-pressed", String(state[name] < 8));
    }
  }

  function remember() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (error) { /* nothing to keep */ }
  }

  var drag = null;
  document.addEventListener("pointerdown", function (event) {
    var handle = event.target.closest ? event.target.closest("[data-gutter]") : null;
    if (!handle) return;
    var name = handle.getAttribute("data-gutter");
    drag = { name: name, x: event.clientX, y: event.clientY, start: state[name] };
    handle.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  document.addEventListener("pointermove", function (event) {
    if (!drag) return;
    var size;
    if (drag.name === "tree") size = drag.start + (event.clientX - drag.x);
    else if (drag.name === "props") size = drag.start - (event.clientX - drag.x);
    else size = drag.start - (event.clientY - drag.y);
    state[drag.name] = Math.max(0, Math.min(880, Math.round(size)));
    apply();
  });
  document.addEventListener("pointerup", function () {
    if (!drag) return;
    drag = null;
    if (state.tree < 40) state.tree = 0;
    if (state.props < 40) state.props = 0;
    if (state.output < 30) state.output = 0;
    apply();
    remember();
  });

  function filterTree(text) {
    var wanted = (text || "").toLowerCase();
    var files = document.querySelectorAll(".tree-file");
    for (var i = 0; i < files.length; i++) {
      var path = (files[i].getAttribute("data-path") || "").toLowerCase();
      files[i].style.display = wanted && path.indexOf(wanted) < 0 ? "none" : "";
    }
    if (!wanted) return;
    var dirs = document.querySelectorAll("details.tree-dir");
    for (var j = 0; j < dirs.length; j++) dirs[j].open = true;
  }

  document.addEventListener("input", function (event) {
    var box = event.target;
    if (!box || !box.getAttribute || box.getAttribute("data-filter") !== "tree") return;
    filterTree(box.value);
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-fold]") : null;
    if (button) {
      var name = button.getAttribute("data-fold");
      state[name] = state[name] < 8 ? WIDE[name] : 0;
      apply();
      remember();
      event.preventDefault();
      return;
    }
    var tab = event.target.closest ? event.target.closest(".tabs a") : null;
    if (!tab || !window.fetch) return;
    var href = tab.getAttribute("href");
    event.preventDefault();
    fetch(href + (href.indexOf("?") < 0 ? "?" : "&") + "pane=doc", { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        return response.text();
      })
      .then(function (html) {
        var panes = document.querySelectorAll(".doc-body");
        if (panes.length !== 1) throw new Error("one document pane expected");
        panes[0].innerHTML = html;
        var tabs = document.querySelectorAll(".tabs a");
        for (var i = 0; i < tabs.length; i++) tabs[i].setAttribute("aria-current", String(tabs[i] === tab));
        document.title = tab.textContent + " \\u00b7 " + document.title.split("\\u00b7")[0].trim();
        history.pushState({ pane: true }, "", href);
      })
      .catch(function () { window.location.href = href; });
  });

  window.addEventListener("popstate", function () { window.location.reload(); });
  apply();
})();
""".strip()

def footer() -> str:
    """The line at the right of the status bar, in the language of this request."""
    return tr("数据与 <code>ff --json</code> 完全一致 · 写入由命令自身的门决定")


def esc(value) -> str:
    """Escape data for a page body."""
    return escape(str(value))


def att(value) -> str:
    """Escape data for an attribute value."""
    return escape(str(value), quote=True)


class Url:
    """Builds links that keep the current scope, access token and language."""

    def __init__(self, scope: str = "", token: str = "", lang: str = "") -> None:
        self.scope = scope
        self.token = token
        self.lang = lang

    def __call__(self, route: str = "index", **params) -> str:
        query = {key: value for key, value in params.items() if value not in (None, "")}
        if self.scope:
            query.setdefault("scope", self.scope)
        if self.token:
            query.setdefault("t", self.token)
        if self.lang and self.lang != LANGUAGE_DEFAULT:
            query.setdefault("lang", self.lang)
        encoded = urlencode(query)
        path = "" if route in ("", "index") else route
        return f"/{path}" + (f"?{encoded}" if encoded else "")


def page_head(title: str, subtitle: str = "") -> str:
    """The heading block at the top of the centre pane."""
    html = f'<div class="head"><h1>{esc(title)}</h1>'
    if subtitle:
        html += f'<div class="sub">{esc(subtitle)}</div>'
    return html + "</div>"


def document_region(title: str, subtitle: str, body: str) -> str:
    """The centre pane on its own, the shape the tab loader drops into place."""
    return page_head(title, subtitle) + body


def panel(title: str, body: str, pane: str) -> str:
    """One side pane with a heading that stays put while it scrolls."""
    return (
        f'<aside class="pane pane-{pane}" id="pane-{pane}">'
        f'<div class="pane-h">{esc(title)}</div><div class="pane-b">{body}</div></aside>'
    )


def gutter(pane: str, label: str, axis: str = "v") -> str:
    """The drag handle between two panes; the script gives it its meaning."""
    return (
        f'<div class="gutter {axis}" data-gutter="{pane}" title="{att(label)}" '
        'role="separator" aria-orientation="vertical"></div>'
    )


def layout(
    title: str,
    body: str,
    nav: str = "",
    subtitle: str = "",
    *,
    tabs: str = "",
    toolbar: str = "",
    panes: dict[str, str] | None = None,
    status: str = "",
    script: bool = True,
) -> str:
    """One complete page: menu bar, tool bar, panes, centre document, status bar.

    The panes are named areas of a CSS grid, so their order in the markup only
    matters to a screen reader, not to the browser laying them out.
    """
    panes = panes or {}
    tree, props, output = panes.get("tree", ""), panes.get("props", ""), panes.get("output", "")
    document = (
        '<main class="pane-doc">'
        + (f'<div class="tabs">{tabs}</div>' if tabs else "")
        + f'<div class="doc-body">{page_head(title, subtitle)}{body}</div>'
        + "</main>"
    )
    middle = (
        f"{tree}{gutter('tree', tr('拖动改变左栏宽度')) if tree else ''}"
        f"{document}"
        f"{gutter('props', tr('拖动改变右栏宽度')) if props else ''}{props}"
        f"{gutter('output', tr('拖动改变底栏高度'), 'h') if output else ''}{output}"
    )
    return (
        f'<!DOCTYPE html>\n<html lang="{html_lang()}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>\n{STYLE}\n</style>\n</head>\n<body>\n"
        + (f'<div class="menubar">{nav}</div>\n' if nav else "")
        + (f'<div class="toolbar">{toolbar}</div>\n' if toolbar else "")
        + middle
        + "\n"
        + (f'<div class="statusbar">{status}</div>\n' if status else "")
        + (f"<script>\n{SCRIPT}\n</script>\n" if script else "")
        + "</body>\n</html>\n"
    )


def section_links() -> dict[str, str]:
    """The sections of the tool, in menu order, in the language of this request."""
    return {
        "index": tr("首页"),
        "list": tr("实体列表"),
        "edit": tr("编辑"),
        "source": tr("源码"),
        "tables": tr("表格"),
        "find": tr("查找"),
        "deps": tr("引用查询"),
        "assets": tr("资源"),
        "check": tr("体检"),
        "stats": tr("统计"),
        "log": tr("日志"),
        "ops": tr("操作"),
        "mcp": tr("MCP"),
        "cmd": tr("命令行"),
        "help": tr("帮助"),
    }


def nav_bar(url: Url, links: dict[str, str] | None = None) -> str:
    """The menu bar: section links, the current scope, the language and the exit."""
    links = links or section_links()
    parts = [f'<a href="{att(url(route))}">{esc(label)}</a>' for route, label in links.items()]
    menu = " ".join(parts)
    tail = [tr("<span class=\"sub\">作用域 {}</span>", esc(url.scope or "-"))]
    other = "zh" if current() == "en" else "en"
    name = "中文" if other == LANGUAGE_DEFAULT else "English"
    tail.append(f'<span class="sub">| <a href="{att(url(_ROUTE.get(), lang=other))}">{name}</a></span>')
    tail.append(tr("<span class=\"sub\">| <a href=\"{}\">退出</a></span>", att(url("quit"))))
    return (
        f'<span class="brand">{esc(tr("Firefight 模组编辑器"))}</span>'
        f'<span class="menu">{" ".join(parts)}</span>'
        f'<span class="sub">{" ".join(tail)}</span>'
    )


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


# How much of one table row the row list shows before it cuts the text off.
ROW_CHARS = 120


def one_line(text: str, limit: int = ROW_CHARS) -> str:
    """One table row's text, tabs widened and the tail cut off past ``limit`` characters."""
    text = text.replace("\t", "    ")
    return text if len(text) <= limit else text[:limit] + "…"


def folder_tree(paths: list[str]) -> dict:
    """Group project-relative paths into nested folders.

    A node is ``{"files": [path, ...], "folders": {name: node}}``; ``files`` holds
    the full relative path so a link can be built from the leaf alone.
    """
    root: dict = {"files": [], "folders": {}}
    for path in sorted(paths):
        node = root
        for part in path.split("/")[:-1]:
            node = node["folders"].setdefault(part, {"files": [], "folders": {}})
        node["files"].append(path)
    return root


def count_files(node: dict) -> int:
    """Every file below one node, folders included."""
    return len(node["files"]) + sum(count_files(child) for child in node["folders"].values())


def render_tree(node: dict, render_file, *, depth: int = 0, open_depth: int = 2) -> str:
    """Folders as ``<details>`` and files as links; opening one needs no script.

    A folder summarises itself and links to its slice of the list page; only the
    first ``TREE_ROWS`` files of a folder are drawn, so a big project stays cheap.
    """
    parts = []
    for name in sorted(node["folders"]):
        child = node["folders"][name]
        opened = " open" if depth < open_depth else ""
        parts.append(
            f'<details class="tree-dir"{opened}><summary>{esc(name)} '
            f'<span class="sub">{esc(tr("{} 项", count_files(child)))}</span></summary>'
            + render_tree(child, render_file, depth=depth + 1, open_depth=open_depth)
            + "</details>"
        )
    for path in node["files"][:TREE_ROWS]:
        parts.append(f'<div class="tree-file" data-path="{att(path)}">{render_file(path)}</div>')
    if len(node["files"]) > TREE_ROWS:
        parts.append(note(tr("只显示前 {} 项", TREE_ROWS)))
    return "".join(parts)


ASSET_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tga": "image/x-tga",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


class AssetNotFound(Exception):
    """The requested asset is not a readable file inside the project."""


def asset_type(relative: str) -> str:
    """The content type of one asset, by extension; unknown files are opaque."""
    return ASSET_TYPES.get(Path(relative).suffix.lower(), "application/octet-stream")


def is_previewable(relative: str) -> bool:
    """Whether a browser can show this file on its own (image or sound)."""
    return Path(relative).suffix.lower() in ASSET_TYPES


def asset_path(scope: Scope, relative: str) -> Path:
    """Resolve a project-relative asset path, refusing anything outside the project.

    The path is confined to the project directory, so ``../``, an absolute path
    and a drive letter all end up as a refusal rather than as a read.
    """
    base = scope.project.resolve()
    candidate = (base / relative).resolve()
    if candidate != base and base not in candidate.parents:
        raise AssetNotFound(tr("{} 指向工程目录之外", relative))
    return candidate


def table(headers: list[str], rows: list[list[str]], empty: str = tr("没有数据")) -> str:
    """A bordered table; cells are markup and must be escaped by the caller."""
    if not rows:
        return f'<p class="empty">{esc(empty)}</p>'
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table><tr>{head}</tr>{body}</table>'


def kv(pairs: list[tuple[str, str]]) -> str:
    """A two-column table of label/value pairs; values are markup."""
    rows = [[esc(label), value] for label, value in pairs]
    return table([tr("项"), tr("值")], rows)


def pager(url: Url, route: str, page: int, total: int, size: int, last: int, **params) -> str:
    """First/previous/next/last links when the list runs over one page."""
    if last <= 1:
        return note(tr("共 {} 条", total))
    def href(target: int) -> str:
        return att(url(route, page=target, **params))
    parts = [tr("共 {} 条，第 {} / {} 页", total, page, last)]
    if page > 1:
        parts.append(tr("<a href=\"{}\">首页</a>", href(1)))
        parts.append(tr("<a href=\"{}\">上一页</a>", href(page - 1)))
    if page < last:
        parts.append(tr("<a href=\"{}\">下一页</a>", href(page + 1)))
        parts.append(tr("<a href=\"{}\">末页</a>", href(last)))
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


def form(action: str, fields: list[str], submit: str = tr("查询"), css: str = "") -> str:
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
    room = f' class="{att(css)}"' if css else ""
    return f'<form method="get"{room} action="{att(path)}">{body} <input type="submit" value="{att(submit)}"></form>'


def text_field(name: str, label: str, value: str = "", size: int = 30) -> str:
    """A labelled text input."""
    return f'<label>{esc(label)} <input type="text" name="{att(name)}" value="{att(value)}" size="{size}"></label>'


def text_area(name: str, label: str, value: str = "", rows: int | None = None) -> str:
    """A labelled multi-line box, for one document's whole text."""
    rows = SOURCE_ROWS if rows is None else rows
    return f'<label class="wide">{esc(label)}<textarea name="{att(name)}" rows="{rows}" spellcheck="false">{esc(value)}</textarea></label>'


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


class Operation:
    """One writing command as the UI offers it: what it does and what it asks for."""

    __slots__ = ("command", "title", "selector", "note", "fields")

    def __init__(self, command: str, title: str, selector: str, note: str, fields: tuple) -> None:
        self.command = command
        self.title = title
        self.selector = selector
        self.note = note
        self.fields = fields


def operations() -> tuple:
    """Every writing command, with the form the UI shows for it.

    Built per request so each label goes through the language in force. A field is
    ``(option, label, kind, default)``; the kinds are ``text``, ``check`` and
    ``select:<value>|<value>``, where an empty value is the default choice.
    """
    return (
        Operation(
            "set",
            tr("改字段"),
            tr("文档"),
            tr("改一个字段的值；数组或表条目用「数组动作」追加或删除。"),
            (
                ("field", tr("字段路径"), "text", ""),
                ("value", tr("新值"), "text", ""),
                ("op", tr("数组动作"), "select:|append|delete", ""),
                ("from", tr("新值取自文档字段"), "text", ""),
            ),
        ),
        Operation(
            "add",
            tr("新建文档"),
            tr("新文档路径"),
            tr("按 schema 建一份骨架；填「复制来源」则复制那份文档。"),
            (("from", tr("复制来源"), "text", ""),),
        ),
        Operation("remove", tr("删除文档"), tr("文档"), tr("把一份文档从工程里删掉；撤销会把它放回。"), ()),
        Operation("index", tr("建索引"), "", tr("重建 EditorCache/index.toml 与 refs.toml。"), ()),
        Operation(
            "convert",
            tr("转换原版数据"),
            "",
            tr("把当前作用域的数据转成工程文档；assets=1 时连 Images/ 与 Sounds/ 一起复制。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("type", tr("存储形态"), "select:|toml|txt", ""),
                ("assets", tr("一并复制素材"), "check", ""),
                ("overwrite", tr("覆盖已有文件"), "check", ""),
            ),
        ),
        Operation(
            "settings",
            tr("工程设置"),
            "",
            tr("render 读 Mod/mod.txt 写 ModSetting.toml；emit 反向写回原版文件。"),
            (
                ("op", tr("方向"), "select:render|emit", "render"),
                ("overwrite", tr("覆盖已有文件"), "check", ""),
            ),
        ),
        Operation(
            "export",
            tr("导出文档"),
            "",
            tr("把工程里的文档按工程相对路径导出到目录；overwrite=0 跳过已存在的文件。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("overwrite", tr("覆盖已有文件"), "check", ""),
            ),
        ),
        Operation(
            "pack",
            tr("打包"),
            "",
            tr("打成可安装的 zip；strict=1 时加载错误与悬空引用会拒绝写入。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("strict", tr("严格模式"), "check", ""),
                ("overwrite", tr("覆盖已有归档"), "check", ""),
            ),
        ),
        Operation("init", tr("新建工程"), "", tr("把当前目录建成一个模组工程。"), (("name", tr("工程名"), "text", ""),)),
        Operation("undo", tr("撤销"), "", tr("把最近几次写入换回原来的字节。"), (("count", tr("条数"), "text", "1"),)),
        Operation("redo", tr("重做"), "", tr("重新应用最近撤销掉的写入。"), (("count", tr("条数"), "text", "1"),)),
    )


def operation_field(spec: tuple, value: str = "") -> str:
    """One control of an operation form."""
    name, label, kind, default = spec
    if kind == "text":
        return text_field(name, label, value or default, 40)
    if kind == "check":
        return checkbox(name, label, value == "1")
    if kind.startswith("select:"):
        options = [
            ("" if item == "" else item, tr("默认") if item == "" else item)
            for item in kind[len("select:"):].split("|")
        ]
        return select_field(name, label, options, value or default)
    raise ValueError(f"unknown field kind {kind!r}")


def operation_options(operation: Operation, query: dict) -> dict:
    """The options a query asks for; a blank control means the option is not sent."""
    options = {}
    for name, _label, kind, _default in operation.fields:
        raw = query.get(name, "")
        if kind == "check":
            if raw in ("1", "yes", "true"):
                options[name] = "1"
        elif raw.strip():
            options[name] = raw.strip()
    return options


def shell_line(scope_name: str, command: str, selector: str, options: dict) -> str:
    """The shell command equivalent to one operation, for the confirmation step.

    The ``key=value`` options come first and the two flags last, which is the order the usage
    text and the documentation use.
    """
    parts = ["ff", scope_name, command]
    if selector:
        parts.append(f'"{selector}"' if " " in selector else selector)
    flags = {"write": "--write", "dry-run": "--dry-run"}
    for key in sorted(options):
        if key not in flags:
            parts.append(f"{key}={options[key]}")
    for key, flag in flags.items():
        if key in options:
            parts.append(flag)
    return " ".join(parts)


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RESERVED = ("scope", "t", "command", "selector", "page", "lang", "pane", "q")

# The route of the request being answered, so the language switch can stay on the page.
_ROUTE = contextvars.ContextVar("web_route", default="index")

# pane=doc asks for the centre pane alone; the tab strip fetches it and drops it in place.
_FRAGMENT = contextvars.ContextVar("web_fragment", default=False)

# The document the request is about, so the property pane can follow the centre pane.
_SELECTION = contextvars.ContextVar("web_selection", default="")
_SEARCH = contextvars.ContextVar("web_search", default="")

# The sections the tab strip offers; every route still works as a plain page load.
TABS = ("index", "list", "edit", "source", "tables", "assets", "log", "ops", "mcp", "cmd", "help")

# How much of the project and of the log the side panes show on one page.
TREE_ROWS = 40
OUTPUT_ROWS = 12
# How many fields the property pane lists for the selected document.
PROP_ROWS = 40
# How many pictures or sounds the asset page draws at once.
ASSET_ROWS = 60
# How many rows of a plain-text table the table page draws at once.
TABLE_ROWS = 200
# How much of the last command's output the bottom pane keeps.
ECHO_CHARS = 2000
# How long the status bar may keep a check result. A check parses every document in the project
# (about 1.2 s on a 765 file project), which is too much for every page load.
CHECK_SECONDS = 20.0

# What the source page will open, and how much of it. The UI answers GET only, so the edited
# text travels in the query string; 16000 bytes of document leaves room for the percent
# encoding inside the 64 KiB request line the server accepts.
SOURCE_SUFFIXES = (".xml", ".toml", ".txt")
SOURCE_BYTES = 16_000
SOURCE_ROWS = 24

# The project folders the asset page walks; both hold files the game loads as they are.
ASSET_FOLDERS = ("Images", "Sounds")

# The MCP panel starts a server from the options this web session was started with, so a trial
# call resolves the same scopes a client would (docs/mcp.md). The argument box is capped: the
# request line is the only carrier the GET-only UI has.
MCP_KEYS = ("workspace", "root", "firefight")
MCP_ARGUMENTS = 4_000

TEXT_VIEWS = ("raw", "toml", "xml")

# Commands the UI refuses: `web` would try to bind a second port inside a request. Everything
# else, writing commands included, may be run from a page; the command's own gate decides
# whether the write happens (docs/cli.md section 4).
REFUSED_COMMANDS = ("web",)

# The permission flag of the writing commands: a page that means to write passes it on.
WRITE_OPTION = "write"


def web_command(name: str) -> str:
    """Canonical name of a command a page may run, or a UsageError."""
    canonical = ALIASES.get(name, name)
    if canonical not in command_names():
        raise UsageError(tr("没有这个命令：{}；可用：{}", name, ', '.join(command_names())))
    if canonical in REFUSED_COMMANDS:
        raise UsageError(tr("{} 不能在页面里运行（它会在一次请求里再起一个服务）；请在命令行里运行", canonical))
    return canonical


def split_command_line(line: str) -> list[str]:
    """Tokens of one command line, keeping a quoted path such as "American-Rifle Squad" whole."""
    try:
        tokens = shlex.split(line, posix=False)
    except ValueError as error:
        raise UsageError(tr("这一行读不出来：{}", error))
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

    def __init__(self, options: dict[str, str], cwd, scope_name: str, page_size: int = DEFAULT_LIMIT, token: str = "", language: str = LANGUAGE_DEFAULT) -> None:
        self.options = {key: value for key, value in options.items() if value not in (None, "")}
        self.cwd = cwd
        self.default_scope = scope_name
        self.page_size = page_size
        self.token = token
        self.language = language
        # The bottom pane keeps the last command line this session ran, and the status bar keeps
        # the check counts for a few seconds. Both live with the server, so browsing to another
        # page does not lose them.
        self.last_command: dict | None = None
        self.checks: dict[str, tuple[float, dict]] = {}
        # The one optional second socket, opened from the MCP panel and closed from it too.
        self.mcp = mcp_listener.McpService()

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
        """Link builder bound to an access token and the language of this request."""
        return Url(scope=scope_name or self.default_scope, token=self.token, lang=current())

    def call(self, command: str, scope, selector: str = "", **options):
        """Run one CLI command in-process and return its Result.

        A page that means to write passes ``write=1``; the command's own gate is what decides
        whether the write happens, so a refusal reads the same as it does on the command line.
        """
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
    routes = ("index", "list", "show", "get", "edit", "source", "tables", "find", "refs", "deps", "check", "stats", "log", "ops", "mcp", "mcpstart", "mcpstop", "assets", "asset", "cmd", "json", "help", "quit")

    # --- plumbing -----------------------------------------------------------

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        started = time.monotonic()
        parsed = urlparse(self.path)
        route = parsed.path.strip("/") or "index"
        _ROUTE.set(route)
        query = {key: value[0] for key, value in parse_qs(parsed.query, keep_blank_values=True).items()}
        _SELECTION.set(query.get("path") or query.get("selector") or "")
        _SEARCH.set(query.get("q", ""))
        try:
            use(query.get("lang") or self.app.language)
        except ValueError as error:
            self.respond(400, self._error_page(tr("用法错误"), str(error), tr("检查参数拼写；下面的表单给出可用取值。")))
            return
        if route == "favicon.ico":
            self.respond(204, "", "text/plain; charset=utf-8")
            return
        if route not in self.routes:
            self.respond(404, self._error_page(tr("没有这个页面"), f"/{route}", tr("从上面的导航栏回到首页。")))
            return
        if route == "asset":
            self.serve_asset(query, started)
            return
        if route in ("mcpstart", "mcpstop"):
            self.mcp_control(route, query)
            return
        status = 200
        body = ""
        fragment = query.get("pane") == "doc"
        try:
            self.check_token(query)
            _FRAGMENT.set(fragment)
            body = getattr(self, f"page_{route}")(query)
        except UsageError as error:
            _FRAGMENT.set(False)
            status, body = 400, self._error_page(tr("用法错误"), str(error), tr("检查参数拼写；下面的表单给出可用取值。"))
        except FfError as error:
            _FRAGMENT.set(False)
            status, body = 500, self._error_page(tr("读取失败"), str(error), tr("文件可能损坏或不可解码；用 CLI 的 check 命令定位。"))
        except Exception as error:  # keep the server alive and report what happened
            _FRAGMENT.set(False)
            traceback.print_exc(file=sys.stderr)
            status, body = 500, self._error_page(tr("内部错误"), f"{type(error).__name__}: {error}", tr("这是界面的问题，请把上面那段命令回报。"))
        if route == "json" and status == 200:
            self.respond(status, body, "text/plain; charset=utf-8")
        else:
            self.respond(status, body)
        self.note_request(status, started)

    def serve_asset(self, query: dict[str, str], started: float) -> None:
        """Send one project file as its own bytes, or an error page.

        The ETag is the file's size and modification time, so a browser that asks
        again with ``If-None-Match`` gets a 304 and the picture is not sent twice.
        """
        etag = ""
        try:
            self.check_token(query)
            scope = self.app.scope(query.get("scope") or "")
            relative = query.get("path") or ""
            if not relative:
                raise UsageError(tr("缺少 path=：给出工程内的相对路径，例如 Images/units/rifleman.png"))
            path = asset_path(scope, relative)
            if path.is_dir():
                raise UsageError(tr("{} 是一个目录，不是文件", relative))
            if not path.is_file():
                raise AssetNotFound(tr("工程里没有 {}", relative))
            data = path.read_bytes()
            content_type = asset_type(relative)
            stat = path.stat()
            etag = f'"{stat.st_size}-{int(stat.st_mtime)}"'
            status = 304 if self.headers.get("If-None-Match") == etag else 200
        except AssetNotFound as error:
            status, data, content_type = 404, self._error_page(tr("没有这个文件"), str(error), tr("从资源页选一个存在的文件。")).encode("utf-8"), "text/html; charset=utf-8"
        except UsageError as error:
            status, data, content_type = 400, self._error_page(tr("用法错误"), str(error), tr("检查参数拼写。")).encode("utf-8"), "text/html; charset=utf-8"
        except (FfError, OSError) as error:
            status, data, content_type = 500, self._error_page(tr("读取失败"), str(error), tr("文件可能损坏或不可读。")).encode("utf-8"), "text/html; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, no-cache")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if data:
            self.wfile.write(data)
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
            tr("只支持 GET"),
            tr("{} 不被支持", self.command),
            tr("这个界面只用 GET：用上面的导航栏浏览，或者在命令行页里运行命令。"),
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
            raise UsageError(tr("缺少访问令牌：请用启动时打印的完整网址打开"))

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
            tr("{} · Firefight 模组编辑器", title),
            bad(detail) + note(hint) + note_html(link(url("index"), tr("回到首页"))),
            nav_bar(url),
            tr("作用域 {}", self.app.default_scope),
        )

    # --- shared builders ----------------------------------------------------

    def shell(self, title: str, body: str, scope_name: str, subtitle: str = "") -> str:
        """A page inside the workbench: menu bar, tool bar, panes, status bar."""
        url = self.app.url(scope_name)
        line = subtitle or tr("作用域 {}", scope_name)
        if _FRAGMENT.get():
            return document_region(title, line, body)
        return layout(
            title,
            body,
            nav_bar(url),
            line,
            tabs=self.section_tabs(url),
            toolbar=self.tool_bar(url),
            panes={
                "tree": panel(tr("工程"), self.pane_tree(scope_name), "tree"),
                "props": panel(tr("属性"), self.pane_props(scope_name), "props"),
                "output": panel(tr("输出"), self.pane_output(scope_name), "output"),
            },
            status=self.status_bar(scope_name),
        )

    def section_tabs(self, url: Url) -> str:
        """The tab strip; without a script each tab is an ordinary link."""
        route = _ROUTE.get()
        labels = section_links()
        parts = []
        for name in TABS:
            here = ' aria-current="true"' if name == route else ""
            parts.append(f'<a href="{att(url(name))}"{here}>{esc(labels[name])}</a>')
        return "".join(parts)

    def tool_bar(self, url: Url) -> str:
        """Buttons that fold a pane, plus the sections the tabs do not carry."""
        folds = "".join(
            f'<button class="tbtn" type="button" data-fold="{pane}" aria-pressed="false">{esc(label)}</button>'
            for pane, label in (("tree", tr("左栏")), ("props", tr("右栏")), ("output", tr("输出")) )
        )
        links = " · ".join(
            link(url(route), label)
            for route, label in (("find", tr("查找")), ("deps", tr("引用查询")), ("check", tr("体检")), ("stats", tr("统计")))
        )
        return folds + f'<span class="sub">{links}</span>'

    def pane_tree(self, scope_name: str) -> str:
        """The project's documents as folders, from the same table the list page shows."""
        try:
            scope = self.app.scope(scope_name)
        except (UsageError, FfError) as error:
            return note(esc(str(error)))
        url = self.app.url(scope.name)
        search = _SEARCH.get().strip()
        field = (
            f'<input type="text" name="q" value="{att(search)}" size="12" '
            f'placeholder="{att(tr("搜索文件"))}" data-filter="tree">'
        )
        head = (
            form(url(_ROUTE.get()), [field], tr("搜索"), css="tree-search")
            + f'<div class="tree-dir">{link(url("index"), esc(scope.project.name))}</div>'
        )
        try:
            payload = self.app.call("list", scope, "all", limit="0").payload
        except (UsageError, FfError) as error:
            return bad(esc(str(error)))
        entities = payload.get("entities", [])
        if search:
            wanted = search.lower()
            entities = [item for item in entities if wanted in item["path"].lower()]
        assets = "".join(
            f'<div class="tree-file" data-path="{att(folder)}">'
            f'{link(url("assets", folder=folder), esc(tr("{} 目录", folder)))}</div>'
            for folder in ASSET_FOLDERS
            if (scope.project / folder).is_dir()
        )
        if not entities:
            if search:
                return head + assets + note(tr("没有匹配 {} 的文件。", search)) + self.tree_search_link(url, search)
            return head + assets + note(tr("这个工程还没有实体文件。"))
        body = render_tree(
            folder_tree([item["path"] for item in entities]),
            lambda path: link(url("show", path=path), esc(path.rsplit("/", 1)[-1])),
        )
        if search:
            counted = note(tr("{} 个文件里有 {} 个匹配 {}。", payload.get("count", 0), len(entities), search))
            return head + body + counted + self.tree_search_link(url, search) + assets
        return head + body + note(tr("{} 个文件", payload.get("count", len(entities)))) + assets

    def tree_search_link(self, url: Url, search: str) -> str:
        """The same search on the list page, where the selector filter is the command's own."""
        return note_html(link(url("list", selector=search), tr("在列表页里搜索")))

    def pane_props(self, scope_name: str) -> str:
        """The selected document's fields, and the way into each of them."""
        try:
            scope = self.app.scope(scope_name)
        except (UsageError, FfError) as error:
            return note(esc(str(error)))
        url = self.app.url(scope.name)
        body = kv(
            [
                (tr("名字"), esc(scope.name)),
                (tr("根目录"), esc(str(scope.root))),
                (tr("来源"), esc(scope.origin)),
            ]
        )
        path = _SELECTION.get()
        if not path:
            body += note(tr("从左边打开一个文件，或在列表页选一份文档，这里会显示它的字段。"))
            return body
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        body += h3(tr("当前文档"))
        body += note_html(
            f"{link(url('get', path=path), tr('字段'))} · "
            f"{link(url('edit', path=path), tr('编辑'))} · "
            f"{link(url('show', path=path), tr('原文'))} · "
            f"{link(url('list', prefix=folder), tr('同级文件'))}"
        )
        try:
            payload = self.app.call("get", scope, path, limit=str(PROP_ROWS)).payload
        except (UsageError, FfError) as error:
            body += note(esc(str(error)))
            return body
        rows = [[esc(item["path"]), esc(item["value"])] for item in payload.get("values", [])]
        body += table([tr("字段"), tr("值")], rows, tr("这份文档没有字段"))
        total = int(payload.get("count", 0))
        if total > len(rows):
            body += note(tr("只显示前 {} 项", len(rows)))
        body += self.field_preview(url, scope, payload.get("values", []))
        body += note_html(
            mono(f"ff {scope.name} get {path} --json") + " · " + self.json_link(scope.name, "get", selector=path)
        )
        return body

    def field_preview(self, url: Url, scope: Scope, values: list[dict]) -> str:
        """Draw the pictures a field points at, when the value names a project file.

        A texture or a sound is named by its path in the game data, not by a field
        the schema knows, so the values are matched against the asset folders and
        anything that is really there is shown. A name that stays dangling is left
        alone: it is a reference the project has not filled in yet (docs/refs.md).
        """
        base = scope.project.resolve()
        drawn = []
        for item in values:
            name = str(item.get("value") or "").strip()
            if len(name) >= 2 and name[0] == name[-1] and name[0] in "\"'":
                name = name[1:-1]  # the value column shows TOML text, quotes included
            if "/" not in name or not is_previewable(name):
                continue
            try:
                path = asset_path(scope, name)
            except AssetNotFound:
                continue
            if not path.is_file() or base not in path.parents:
                continue
            source = url("asset", path=name)
            if asset_type(name).startswith("image/"):
                drawn.append(
                    f'<a href="{att(source)}" target="_blank" rel="noopener">'
                    f'<img src="{att(source)}" alt="{att(name)}" loading="lazy"></a>'
                )
            else:
                drawn.append(f'<audio controls preload="none" src="{att(source)}"></audio>')
        if not drawn:
            return ""
        return f'<div class="preview"><div class="sub">{esc(tr("字段指向的文件"))}</div>{"".join(drawn)}</div>'

    def pane_output(self, scope_name: str) -> str:
        """The last command this session ran, above the tail of the event log.

        The last command is kept with the server, so the pane still shows it after the reader
        moves to another page; only the session's own runs appear here.
        """
        parts = [f'<div class="sub">{esc(tr("最近一次命令"))}</div>']
        echo = self.app.last_command
        if echo is None:
            parts.append(note(tr("本次会话还没有运行过命令")))
        else:
            parts.append(f"<div>{mono(echo['line'])}</div>")
            output = echo["output"]
            if len(output) > ECHO_CHARS:
                output = output[:ECHO_CHARS] + "…"
            parts.append(pre(output) if output.strip() else note(tr("这条命令没有文本输出")))
            parts.append(
                note_html(
                    tr("退出码 {}", echo["exit"])
                    + " · "
                    + f"{echo['elapsed']:.2f} s"
                    + " · "
                    + link(self.app.url(echo["scope"])("cmd", line=echo["line"]), tr("重跑"))
                )
            )
        parts.append(f'<div class="sub">{esc(tr("事件日志"))}</div>')
        try:
            scope = self.app.scope(scope_name)
            result = self.app.call("log", scope, "", limit=str(OUTPUT_ROWS))
        except (UsageError, FfError) as error:
            parts.append(note(str(error)))
            return "".join(parts)
        events = result.payload.get("events", [])
        if not events:
            parts.append(note(tr("还没有写入记录")))
            return "".join(parts)
        for event in events:
            words = [str(event.get(key) or "") for key in ("result", "document", "field")]
            parts.append(f'<div>{esc(event.get("id", ""))} {esc(" ".join(word for word in words if word))}</div>')
        return "".join(parts)

    def check_counts(self, scope_name: str) -> dict | None:
        """What the status bar reports, refreshed at most once every CHECK_SECONDS.

        The result carries the time it was taken, so a cached number is visibly dated rather
        than silently stale.
        """
        try:
            scope = self.app.scope(scope_name)
        except (UsageError, FfError):
            return None
        key = f"{scope.name}:{scope.root}"
        now = time.monotonic()
        held = self.app.checks.get(key)
        if held is not None and now - held[0] < CHECK_SECONDS:
            return held[1]
        try:
            result = self.app.call("check", scope, "")
        except (UsageError, FfError):
            return None
        counts = {
            "files": int(result.payload.get("files", 0) or 0),
            "errors": len(result.payload.get("errors", []) or []),
            "dangling": int(result.payload.get("dangling_total", 0) or 0),
            "at": time.strftime("%H:%M:%S"),
        }
        self.app.checks[key] = (now, counts)
        return counts

    def status_bar(self, scope_name: str) -> str:
        """The bottom line: the scope, the project's counts, the language and how a page is made."""
        parts = [f'<span>{esc(tr("作用域 {}", scope_name))}</span>']
        counts = self.check_counts(scope_name)
        if counts is None:
            parts.append(f'<span class="sub">{esc(tr("无法读取该作用域的计数"))}</span>')
        else:
            parts.append(
                f'<span>{esc(tr("文件 {}", counts["files"]))}</span>'
                f'<span>{esc(tr("错误 {}", counts["errors"]))}</span>'
                f'<span>{esc(tr("悬空 {}", counts["dangling"]))}</span>'
                f'<span class="sub">{esc(tr("数据于 {}", counts["at"]))}</span>'
            )
        parts.append(f'<span class="sub">{esc(current())}</span>')
        parts.append(f'<span class="foot">{footer()}</span>')
        return "".join(parts)

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
                    link(here("list"), tr("列表")),
                    link(here("edit"), tr("编辑")),
                    link(here("log"), tr("日志")),
                    link(here("ops"), tr("操作")),
                    link(here("stats"), tr("统计")),
                    link(here("check"), tr("体检")),
                ]
            )
            rows.append([link(here("index"), name), esc(str(found.root)), esc(found.origin), links])
        body = h2(tr("可用的作用域"))
        body += table([tr("作用域"), tr("根目录"), tr("来源"), tr("操作")], rows)
        if not rows:
            body += warn(tr("没有解析到任何作用域：用 root=<目录> 启动，或先建一个含 ModInformation.toml 的工程。"))

        listing = self.app.call("list", scope, "all")
        payload = listing.payload
        by_category: dict[str, int] = {}
        for entity in payload["entities"]:
            by_category[entity["category"]] = by_category.get(entity["category"], 0) + 1
        body += h2(tr("当前作用域：{}", scope.name))
        body += kv(
            [
                (tr("根目录"), esc(payload["root"])),
                (tr("实体文件"), esc(payload["count"])),
                (tr("来源"), esc(scope.origin)),
            ]
        )
        category_rows = [
            [link(url("list", type=category), category), esc(count)]
            for category, count in sorted(by_category.items(), key=lambda item: (-item[1], item[0]))
        ]
        body += table([tr("分类"), tr("数量")], category_rows, tr("这个作用域里没有实体文件"))
        body += h2(tr("查找"))
        body += form(
            url("find"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("selector", tr("文件前缀"), "", 24),
                text_field("tag", tr("标签"), "", 12),
                text_field("value", tr("取值含"), "", 16),
                checkbox("ignore_case", tr("忽略大小写"), True),
            ],
            tr("查找"),
        )
        body += note(tr("提示：列表页可以用路径片段过滤；统计、体检、引用查询都在导航栏里。"))
        return self.shell(tr("Firefight 模组编辑器"), body, scope.name)

    def entity_actions(self, url: Url, path: str) -> str:
        """The three writes that act on one document, each behind the check step.

        ``add`` keeps the document it copies in ``from=`` and takes the new path as its
        selector, so a copy starts as a prefilled form and not as a write. ``remove`` is
        linked with ``confirm=1``, which runs its check and nothing more: the write stays
        one deliberate click past the page that shows what it would do.
        """
        return " · ".join(
            [
                link(url("edit", path=path), tr("改")),
                link(url("ops", command="add", **{"from": path}), tr("复制")),
                link(url("ops", command="remove", selector=path, confirm="1"), tr("删除")),
            ]
        )

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
                link(url("show", path=item["path"], **{"as": "toml"}), item["path"]),
                link(url("list", type=item["category"]), item["category"]),
                esc(item["format"]),
                esc(item["bytes"]),
                self.entity_actions(url, item["path"]),
            ]
            for item in window
        ]
        body = h2(tr("实体列表"))
        body += form(
            url("list"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("prefix", tr("路径含"), prefix, 28),
                select_field(
                    "type",
                    tr("分类"),
                    [("", tr("全部"))] + [(name, name) for name in sorted({item["category"] for item in payload["entities"]})],
                    wanted,
                ),
            ],
            tr("过滤"),
        )
        body += note(tr("根目录 {} · 命中 {} / {} 个实体文件", payload['root'], len(entities), payload['count']))
        body += table([tr("路径"), tr("分类"), tr("格式"), tr("字节"), tr("操作")], rows, tr("没有匹配的实体"))
        body += h3(tr("新建文档"))
        body += form(
            url("ops", command="add"),
            [
                text_field("selector", tr("新文档路径"), "", 60),
                text_field("from", tr("复制来源（留空则按 schema 建骨架）"), "", 60),
            ],
            tr("检查"),
        )
        body += note_html(
            tr("每行的{}、{}、{}都通向操作页的检查步骤，写入前会先显示该命令的真实结果。",
               tr("改"), tr("复制"), tr("删除"))
        )
        body += pager(url, "list", page, len(entities), size, last, prefix=prefix, type=wanted)
        body += note_html(tr("等价命令：") + mono(f"ff {scope.name} list {prefix or 'all'} --json") + " · " + self.json_link(scope.name, "list", selector="all", type=wanted or None))
        return self.shell(tr("实体列表"), body, scope.name)

    def page_show(self, query: dict[str, str]) -> str:
        """One entity as raw text, TOML or XML, with its warnings."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        path = query.get("path", "")
        view = query.get("as", "toml")
        if view not in TEXT_VIEWS:
            raise UsageError(tr("as={} 不是 raw / toml / xml 之一", repr(view)))
        payload = self.app.call("show", scope, path, **{"as": view}).payload
        body = crumbs([(url("index"), tr("首页")), (url("list"), tr("列表")), ("", payload["path"])])
        body += h2(payload["path"])
        links = []
        for name in TEXT_VIEWS:
            label = {"raw": tr("原始内容"), "toml": tr("TOML 视图"), "xml": tr("XML 视图")}[name]
            links.append(link(url("show", path=payload["path"], **{"as": name}), f"[{label}]" if name != view else f"[{label} ←]"))
        links.append(link(url("refs", path=payload["path"]), tr("[本文件指向谁]")))
        if payload.get("format") == "list":
            links.append(link(url("tables", path=payload["path"]), tr("[行编辑]")))
        if Path(payload["path"]).suffix.lower() in SOURCE_SUFFIXES:
            links.append(link(url("source", path=payload["path"]), tr("[源码]")))
        links.append(self.json_link(scope.name, "show", selector=payload["path"], **{"as": view}))
        body += "<p>" + " ".join(links) + "</p>"
        warnings = payload.get("warnings") or []
        if warnings:
            body += warn(tr("{} 条解析警告：", len(warnings)) + "；".join(warnings[:5]) + ("；…" if len(warnings) > 5 else ""))
        if "text" in payload:
            body += pre(payload["text"])
        elif "toml" in payload:
            body += pre(payload["toml"])
        elif "xml" in payload:
            body += pre(payload["xml"])
        elif "values" in payload:
            body += h3(tr("子树 {}", payload.get('key', '')))
            body += table(
                [tr("路径"), tr("行"), tr("值")],
                [[esc(item["path"]), esc(item["line"]), esc(item["value"])] for item in payload["values"]],
            )
        else:
            body += note(tr("这是列表文件的内容。"))

        body += h2(tr("读取字段"))
        body += form(
            url("get"),
            [
                hidden("scope", scope.name),
                hidden("path", payload["path"]),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("field", tr("字段路径"), "", 24),
            ],
            tr("取值"),
        )
        body += note(tr("字段路径相对根元素，点分，例如 name 或 ammo.type。"))
        incoming = self.incoming_link(scope, payload["path"])
        if incoming:
            body += note_html(tr("被引用情况：") + incoming)
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
        return link(self.app.url(scope.name)("deps", value=token), tr("谁引用了 {}", token))

    def page_get(self, query: dict[str, str]) -> str:
        """The values of one field, with the document path and source line."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        path = query.get("path", "")
        field = query.get("field", "")
        payload = self.app.call("get", scope, path, field=field).payload
        body = crumbs([(url("index"), tr("首页")), (url("list"), tr("列表")), (url("show", path=payload["path"]), payload["path"]), ("", payload["field"])])
        body += h2(f"{payload['path']} · {payload['field']}")
        body += table(
            [tr("文档路径"), tr("行"), tr("值")],
            [[esc(item["path"]), esc(item["line"]), esc(item["value"])] for item in payload["values"]],
        )
        body += note_html(tr("等价命令：") + mono(f"ff {scope.name} get {payload['path']} field={field} --json") + " · " + self.json_link(scope.name, "get", selector=payload["path"], field=field))
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
                text_field("selector", tr("文件前缀(all)"), selector, 20),
                text_field("tag", tr("标签"), query.get("tag", ""), 12),
                text_field("value", tr("取值含"), query.get("value", ""), 16),
                text_field("path", tr("文档路径前缀"), query.get("path", ""), 16),
                checkbox("ignore_case", tr("忽略大小写"), query.get("ignore_case", "1") == "1"),
            ],
            tr("查找"),
        )
        body = h2(tr("查找"))
        body += form_html
        if not options.get("tag") and not options.get("value") and not options.get("path"):
            body += note(tr("至少填一个条件：标签名、取值包含、或文档路径前缀。"))
            return self.shell(tr("查找"), body, scope.name)
        payload = self.app.call("find", scope, selector, **options).payload
        body += note(tr("命中 {} 条", payload['count']) + (tr("（到达上限，请收窄条件）") if payload["truncated"] else ""))
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
        body += table([tr("文件"), tr("行"), tr("标签"), tr("取值")], rows, tr("没有命中"))
        return self.shell(tr("查找"), body, scope.name)

    def page_refs(self, query: dict[str, str]) -> str:
        """Outgoing references of one entity."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        path = query.get("path", "")
        payload = self.app.call("refs", scope, path).payload
        body = crumbs([(url("index"), tr("首页")), (url("list"), tr("列表")), (url("show", path=path), path), ("", tr("引用"))])
        body += h2(tr("本文件指向谁"))
        by_kind = "、".join(f"{name}={count}" for name, count in sorted(payload["by_kind"].items())) or tr("无")
        body += note(tr("{} 共 {} 条向外引用（{}）", path, payload['count'], by_kind))
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
        body += table([tr("来源"), tr("类型"), tr("取值"), tr("文档路径")], rows, tr("没有向外引用"))
        if len(payload["references"]) > len(shown):
            body += note(tr("另有 {} 条未显示，用 JSON 看全部。", len(payload['references']) - len(shown)))
        for item in payload.get("errors") or []:
            body += bad(f"{item['path']}: {item['error']}")
        body += note_html(tr("取值一列可以点开，看谁引用了它。") + " · " + self.json_link(scope.name, "refs", selector=path))
        return self.shell(tr("{} · 引用", path), body, scope.name)

    def page_deps(self, query: dict[str, str]) -> str:
        """Incoming references of a token, with the resolved target."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        value = query.get("value", "")
        kind = query.get("kind", "")
        body = h2(tr("谁引用了这个取值"))
        body += form(
            url("deps"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("value", tr("取值"), value, 30),
                text_field("kind", tr("类型(可空)"), kind, 12),
            ],
            tr("查询"),
        )
        if not value:
            body += note(tr("填一个取值，例如 WEAPON_PISTOL_P38。"))
            return self.shell(tr("引用查询"), body, scope.name)
        payload = self.app.call("deps", scope, "", **{"value": value, "kind": kind or None}).payload
        resolved = payload["resolved"]
        if payload["unresolved"]:
            body += warn(tr("{} 没有解析到任何实体文件。", value))
        else:
            targets = "、".join(link(url("show", path=target), target) for target in resolved)
            body += note_html(tr("解析到：{}", targets))
        body += note(tr("共 {} 条传入引用", payload['count']))
        shown = payload["references"][: self.app.page_size]
        rows = [
            [
                link(url("show", path=item["source"], **{"as": "toml"}), item["source"]),
                esc(item["kind"]),
                esc(item["document_path"]),
            ]
            for item in shown
        ]
        body += table([tr("来源文件"), tr("类型"), tr("文档路径")], rows, tr("没有传入引用"))
        if len(payload["references"]) > len(shown):
            body += note(tr("另有 {} 条未显示，用 JSON 看全部。", len(payload['references']) - len(shown)))
        for item in payload.get("errors") or []:
            body += bad(f"{item['path']}: {item['error']}")
        body += note_html(tr("等价命令：") + mono(f"ff {scope.name} deps value={value} --json") + " · " + self.json_link(scope.name, "deps", value=value, kind=kind or None))
        return self.shell(tr("引用 {}", value), body, scope.name)

    def page_check(self, query: dict[str, str]) -> str:
        """Load errors, warnings and dangling references of a selection."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        selector = query.get("selector", "") or "all"
        body = h2(tr("工程体检"))
        body += form(
            url("check"),
            [
                hidden("scope", scope.name),
                *([hidden("t", self.app.token)] if self.app.token else []),
                text_field("selector", tr("范围(目录前缀或 all)"), selector, 26),
            ],
            tr("开始体检"),
        )
        body += note(tr("体检会把范围内的每个实体读一遍；原版数据 1840 个文件需要几十秒。"))
        started = time.monotonic()
        payload = self.app.call("check", scope, selector).payload
        elapsed = time.monotonic() - started
        headline = (
            tr("{} / {} 个文件读取成功，跳过 {} 个列表文件，{} 个错误，{} 条警告，{} 条悬空引用", payload['loaded'], payload['files'], payload['skipped'], len(payload['errors']), payload['warnings_total'], len(payload['dangling']))
        )
        body += good(headline) if payload["ok"] else bad(headline)
        body += note(tr("耗时 {:.1f} 秒 · 作用域 {} · 范围 {}", elapsed, scope.name, selector))
        if payload["errors"]:
            body += h3(tr("读取错误"))
            body += table([tr("文件"), tr("错误")], [[esc(item["path"]), esc(item["error"])] for item in payload["errors"]])
        if payload["dangling"]:
            body += h3(tr("悬空引用"))
            body += table(
                [tr("来源"), tr("类型"), tr("取值"), tr("文档路径")],
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
                body += note(tr("另有 {} 条悬空引用未列出。", len(payload['dangling']) - 100))
        if payload["warning_samples"]:
            body += h3(tr("警告样本（{} 个文件共 {} 条）", payload['warning_files'], payload['warnings_total']))
            rows = [
                [link(url("show", path=item["path"], **{"as": "toml"}), item["path"]), esc("；".join(item["warnings"]))]
                for item in payload["warning_samples"]
            ]
            body += table([tr("文件"), tr("警告")], rows)
        body += note_html(tr("等价命令：") + mono(f"ff {scope.name} check {selector} --json") + " · " + self.json_link(scope.name, "check", selector=selector))
        return self.shell(tr("工程体检"), body, scope.name)

    def page_stats(self, query: dict[str, str]) -> str:
        """Counts by category, format and root element."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        payload = self.app.call("stats", scope, "all").payload
        body = h2(tr("统计"))
        body += kv(
            [
                (tr("作用域"), esc(payload["scope"])),
                (tr("根目录"), esc(payload["root"])),
                (tr("文件"), esc(payload["files"])),
                (tr("字节"), esc(payload["bytes"])),
                (tr("列表文件"), esc(payload["lists"])),
            ]
        )
        body += h3(tr("按分类"))
        body += table(
            [tr("分类"), tr("数量")],
            [[link(url("list", type=name), name), esc(count)] for name, count in sorted(payload["by_category"].items(), key=lambda item: (-item[1], item[0]))],
        )
        body += h3(tr("按格式"))
        body += table([tr("格式"), tr("数量")], [[esc(name), esc(count)] for name, count in sorted(payload["by_format"].items(), key=lambda item: (-item[1], item[0]))])
        body += h3(tr("按根元素"))
        body += table([tr("根元素"), tr("数量")], [[esc(name), esc(count)] for name, count in sorted(payload["by_root"].items(), key=lambda item: (-item[1], item[0]))])
        if payload["errors"]:
            body += h3(tr("读取失败"))
            body += table([tr("文件"), tr("错误")], [[esc(item["path"]), esc(item["error"])] for item in payload["errors"]])
        body += note_html(tr("等价命令：") + mono(f"ff {scope.name} stats --json") + " · " + self.json_link(scope.name, "stats", selector="all"))
        return self.shell(tr("统计"), body, scope.name)

    def page_json(self, query: dict[str, str]) -> str:
        """The raw payload of one command, for cross-checking against the CLI."""
        scope = self.app.scope(query.get("scope", ""))
        command = query.get("command", "")
        web_command(command)
        result = self.app.call_from_query(command, scope, query)
        return json.dumps(result.payload, indent=2, ensure_ascii=False, default=str) + "\n"

    def page_edit(self, query: dict[str, str]) -> str:
        """Every field of one document with its own input box."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        selector = query.get("path", "").strip()
        body = h2(tr("编辑文档"))
        body += note(tr("填一个文档路径，页面列出它的全部字段；改哪一行就改哪一行的输入框，然后按该行的「保存」。"))
        body += form(url("edit"), [text_field("path", tr("文档"), selector, 60)], tr("读取"))
        if not selector:
            return self.shell(tr("编辑文档"), body, scope.name)
        payload = self.app.call("get", scope, selector).payload
        values = payload.get("values") or []
        if not values:
            body += note(tr("这个文档没有可列出的字段。"))
            return self.shell(tr("编辑文档"), body, scope.name)
        document = payload["path"]
        body += crumbs([(url("index"), tr("首页")), (url("show", path=document), document), ("", tr("编辑"))])
        rows = []
        for item in values:
            actions = form(
                url("ops", command="set"),
                [hidden("selector", document), hidden("field", item["path"]), text_field("value", tr("新值"), "", 30)],
                tr("保存"),
            )
            rows.append([esc(item["path"]), pre(item["value"]), actions])
        body += table([tr("字段"), tr("当前值"), tr("改为")], rows)
        body += note_html(tr("也可以用{}一次给多个参数，或到{}看事件日志。", link(url("ops", command="set"), tr("操作页")), link(url("log"), tr("事件日志"))))
        return self.shell(tr("编辑文档"), body, scope.name)

    def source_path(self, scope, relative: str) -> Path:
        """The file behind a source path, or a UsageError naming the problem.

        Only the project's own text files are open here: the suffix has to be one the editor
        reads (``.xml``, ``.toml``, ``.txt``) and the path has to resolve inside the project
        directory (docs/web.md section 2.5).
        """
        name = relative.rsplit("/", 1)[-1]
        if not relative or Path(name).suffix.lower() not in SOURCE_SUFFIXES:
            raise UsageError(tr("源码页只打开 {} 文件，不是 {}。", "、".join(SOURCE_SUFFIXES), relative or tr("空路径")))
        path = scope.project / relative
        try:
            journal.confine(path, scope.project)
        except FfError as error:
            # a path outside the project is a bad request, not a broken server
            raise UsageError(str(error)) from None
        if not path.is_file():
            raise UsageError(tr("找不到 {}。", relative))
        return path

    def source_file(self, scope, relative: str) -> textio.SourceText:
        """The decoded document, refusing one the UI cannot carry in a query string."""
        path = self.source_path(scope, relative)
        if path.stat().st_size > SOURCE_BYTES:
            raise UsageError(
                tr("{} 有 {} 字节，超过源码页的 {} 字节上限。", relative, path.stat().st_size, SOURCE_BYTES)
            )
        return textio.read_source(path)

    def source_write(self, project: Path, source: textio.SourceText, relative: str, text: str, *, dry_run: bool) -> dict:
        """Stage and apply a whole-document rewrite of one source file, recorded as ``web``.

        The file's own encoding, BOM and line ending are kept: a UTF-8 file that carried a BOM
        is written back as ``utf-8-sig``, because ``textio.encode_export`` never adds one
        (core/textio.py).  The write goes through the same plan and journal as a command-line
        change, so it lands in the event log and ``undo`` puts it back.
        """
        encoding = "utf-8-sig" if source.had_bom else source.encoding
        newline = "\r\n" if "\r\n" in source.raw else "\n"
        plan = edit.plan_render(
            source.path,
            relative,
            text,
            entity=relative.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            newline=newline,
            encoding=encoding,
        )
        return edit.apply_document(plan, project, dry_run=dry_run, actor="web")

    def source_check(self, scope, relative: str) -> str:
        """What ``check`` says about this document, shown before and after a save.

        The result is reported and never used as a gate: a document that does not load is
        exactly the document someone wants to fix here (docs/web.md section 2.5).
        """
        try:
            payload = self.app.call("check", scope, relative).payload
        except (UsageError, FfError) as error:
            return bad(str(error))
        errors = len(payload.get("errors") or [])
        return pre(
            tr(
                "体检 {}：{} 个加载错误、{} 条警告、{} 条悬空引用。",
                relative,
                errors,
                payload.get("warnings_total", 0),
                payload.get("dangling_total", 0),
            )
        )

    def page_source(self, query: dict[str, str]) -> str:
        """One document as its own text, ready to be edited and saved as a whole.

        The save is the same two steps as the other writing pages: a check that touches
        nothing, then the write. ``check`` is run on both sides and never blocks.
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        wanted = query.get("path", "").strip()
        body = h2(tr("源码"))
        body += note(
            tr(
                "整份文档当文本改：TOML 或 XML 都能在这里直接编辑。保存走与其他写入相同的先计划、后应用，"
                "按文本原有的编码、换行与 BOM 写回，因此可以撤销。"
            )
        )
        body += form(url("source"), [text_field("path", tr("文档"), wanted, 60)], tr("读取"))
        if not wanted:
            return self.shell(tr("源码"), body, scope.name)
        source = self.source_file(scope, wanted)
        relative = journal.confine(source.path, scope.project)
        body += crumbs([(url("index"), tr("首页")), (url("show", path=relative), relative), ("", tr("源码"))])
        body += note(
            tr(
                "{} 字节，{} 编码，{} 换行，{} BOM。",
                len(source.path.read_bytes()),
                "utf-8-sig" if source.had_bom else source.encoding,
                "CRLF" if "\r\n" in source.raw else "LF",
                tr("带") if source.had_bom else tr("无"),
            )
        )
        body += self.source_check(scope, relative)
        if query.get("confirm") != "1":
            body += form(
                url("source", path=relative),
                [text_area("text", tr("文本"), source.text)],
                tr("检查"),
            )
            return self.shell(tr("源码"), body, scope.name)
        return self.shell(tr("源码"), body + self.source_change(scope, source, relative, query), scope.name)

    def source_change(self, scope, source: textio.SourceText, relative: str, query: dict) -> str:
        """The check step and the write step of one whole-document edit."""
        url = self.app.url(scope.name)
        text = query.get("text", "")
        if textio.normalize_newlines(text) == source.text:
            return note(tr("内容没有变化，因此没有可写入的东西。"))
        body = h3(tr("只检查不写入"))
        try:
            dry = self.source_write(scope.project, source, relative, text, dry_run=True)
        except (UsageError, FfError) as error:
            body += bad(str(error))
            body += note(tr("写入被拒绝；再试一次也不会不同，因此没有写入链接。"))
            return body
        body += pre(
            tr("{} 字节 → {} 字节，记录为 actor=web、动作 set、文档 {}。", dry["bytes_before"], dry["bytes_after"], dry["path"])
        )
        if query.get("write") != "1":
            body += warn(tr("尚未写入。核对上面的差别，确认无误后再按「写入」。"))
            body += note_html(
                link(url("source", path=relative, text=text, confirm="1", write="1"), tr("写入"))
            )
            return body
        written = self.source_write(scope.project, source, relative, text, dry_run=False)
        body += h3(tr("写入结果"))
        body += warn(tr("已写入 {} 字节，记录编号 {}。", written["bytes_after"], written.get("id") or ""))
        body += h3(tr("写入之后"))
        body += self.source_check(scope, relative)
        body += note_html(
            tr("到{}看这条记录，或到{}换回。", link(url("log"), tr("事件日志")), link(url("ops", command="undo"), tr("撤销")))
        )
        return body

    def list_files(self, scope) -> list[str]:
        """The project's plain-text tables, as the project settings declare them.

        The same rule the CLI applies to skip a file decides what is offered here, so a
        table that ``convert`` leaves alone is a table this page offers to edit
        (docs/cli.md section 4.3).
        """
        payload = self.app.call("list", scope, "all", limit="0").payload
        declared = declared_lists(scope)
        found = []
        for item in payload.get("entities") or []:
            relative = item.get("path") or ""
            if relative and is_list_file(relative, declared, scope.project / relative):
                found.append(relative)
        return found

    def list_path(self, scope, relative: str) -> Path:
        """The file behind a table path, or a UsageError naming the problem."""
        path = scope.project / relative
        if not is_list_file(relative, declared_lists(scope), path):
            raise UsageError(tr("{} 不是工程设置的表格文件", relative))
        if not path.is_file():
            raise UsageError(tr("找不到 {}。", relative))
        journal.confine(path, scope.project)
        return path

    def table_write(
        self, project: Path, path: Path, relative: str, lines: list[str], encoding: str, bom: bool, *, dry_run: bool
    ) -> dict:
        """Stage and apply a whole-document rewrite of one table, recorded as ``web``.

        The row operation only changes the text; the write goes through the same plan and
        journal as a command-line change, so it lands in the event log and ``undo`` puts it
        back (docs/project-layout.md section 8).
        """
        text = tables.encode(lines, encoding, bom)
        plan = edit.plan_render(
            path,
            relative,
            text,
            entity=relative.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            newline="",
            encoding=encoding,
        )
        return edit.apply_document(plan, project, dry_run=dry_run, actor="web")

    def page_tables(self, query: dict[str, str]) -> str:
        """The plain-text tables of the project, one row per line.

        A list file is one entry per line, so the page is a row list: every row has its own
        input box and its own delete link, and the bottom of the page appends a row.  The
        write follows the same two steps as the operations page -- a check that touches
        nothing, then the write (docs/web.md section 2.2).
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        wanted = query.get("path", "").strip()
        body = h2(tr("表格"))
        body += note(tr("工程设置的清单文件是一行一条。改哪一行就改哪一行的输入框，按该行的「保存」；写入与命令行一样先记账，可用日志页撤销。"))
        found = self.list_files(scope)
        body += form(url("tables"), [text_field("path", tr("清单文件"), wanted, 60)], tr("读取"))
        if found:
            body += note_html(
                tr("本工程声明的表格：")
                + " ".join(link(url("tables", path=item), item.rsplit("/", 1)[-1]) for item in found)
            )
        if not wanted:
            if not found:
                body += note(tr("这个工程没有声明任何清单文件。"))
            return self.shell(tr("表格"), body, scope.name)
        path = self.list_path(scope, wanted)
        relative = journal.confine(path, scope.project)
        content = path.read_bytes()
        lines, encoding, newline = tables.read_rows(path)
        bom = content.startswith(textio.BOM)
        body += crumbs([(url("index"), tr("首页")), (url("show", path=relative), relative), ("", tr("表格"))])
        body += note(tr("{} 行，{} 编码，{} 换行。", len(lines), encoding, "CRLF" if newline == "\r\n" else "LF"))
        op = query.get("op", "")
        line = query.get("line", "")
        if op:
            body += self.table_change(scope, path, relative, lines, encoding, bom, op, line, query)
            return self.shell(tr("表格"), body, scope.name)
        rows = []
        for row in tables.rows(lines, TABLE_ROWS):
            mark = tr("注释") if row["comment"] else (tr("空行") if row["blank"] else "")
            actions = form(
                url("tables", path=relative, op="set", line=str(row["line"]), confirm="1"),
                [text_field("value", tr("改为"), row["text"], 30)],
                tr("保存"),
            )
            actions += " " + link(
                url("tables", path=relative, op="delete", line=str(row["line"]), confirm="1"), tr("删除")
            )
            rows.append([esc(str(row["line"])), pre(one_line(row["text"])), esc(mark), actions])
        body += table([tr("行"), tr("内容"), tr("标记"), tr("改为")], rows)
        if len(lines) > TABLE_ROWS:
            body += note(tr("只显示前 {} 行，共 {} 行。", TABLE_ROWS, len(lines)))
        body += h3(tr("追加一行"))
        body += form(url("tables", path=relative, op="add", confirm="1"), [text_field("value", tr("内容"), "", 40)], tr("追加"))
        return self.shell(tr("表格"), body, scope.name)

    def table_change(
        self,
        scope,
        path: Path,
        relative: str,
        lines: list[str],
        encoding: str,
        bom: bool,
        op: str,
        line: str,
        query: dict,
    ) -> str:
        """The check step and the write step of one row operation."""
        url = self.app.url(scope.name)
        if op not in tables.OPS:
            raise UsageError(tr("op= 是 {} 之一，不是 {}。", "、".join(tables.OPS), op))
        number = 0
        if op != "add":
            try:
                number = int(line)
            except ValueError:
                raise UsageError(tr("line= 是行号，不是 {}。", line)) from None
        value = query.get("value", "")
        newline = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
        try:
            changed, before, after = tables.row_change(lines, op, number, value, newline)
        except ValueError as error:
            raise UsageError(f"{relative}: {error}") from None
        label = {"set": tr("改写第 {} 行", number), "add": tr("追加一行"), "delete": tr("删除第 {} 行", number)}[op]
        body = h3(label)
        body += table([tr("行"), tr("现在"), tr("操作后")], [[esc(str(number)), pre(one_line(before)), pre(one_line(after))]], "")
        if changed == lines:
            body += note(tr("内容没有变化，因此没有可写入的东西。"))
            return body
        body += h3(tr("只检查不写入"))
        try:
            dry = self.table_write(scope.project, path, relative, changed, encoding, bom, dry_run=True)
        except (UsageError, FfError) as error:
            body += bad(str(error))
            body += note(tr("写入被拒绝；再试一次也不会不同，因此没有写入链接。"))
            return body
        body += pre(
            tr("{} 字节 → {} 字节，记录为 actor=web、动作 set、文档 {}。", dry["bytes_before"], dry["bytes_after"], dry["path"])
        )
        if query.get("write") != "1":
            body += warn(tr("尚未写入。核对上面的差别，确认无误后再按「写入」。"))
            body += note_html(
                link(
                    url("tables", path=relative, op=op, line=str(number), value=value, confirm="1", write="1"),
                    tr("写入"),
                )
            )
            return body
        written = self.table_write(scope.project, path, relative, changed, encoding, bom, dry_run=False)
        body += h3(tr("写入结果"))
        body += warn(tr("已写入 {} 字节，记录编号 {}。", written["bytes_after"], written.get("id") or ""))
        body += note_html(
            tr("到{}看这条记录，或到{}换回。", link(url("log"), tr("事件日志")), link(url("ops", command="undo"), tr("撤销")))
        )
        return body

    def page_log(self, query: dict[str, str]) -> str:
        """The event log, with the undo and redo forms beside it."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        filters = {key: query[key] for key in ("document", "field", "actor", "result", "since", "until") if query.get(key)}
        filters["limit"] = str(self.app.page_size)
        payload = self.app.call("log", scope, **filters).payload
        body = crumbs([(url("index"), tr("首页")), ("", tr("事件日志"))])
        body += h2(tr("事件日志"))
        body += note_html(
            tr("每条记录是一次写入。{} 与 {} 把最近几次写入换回或重做；命令行页可以按 document=、field=、actor=、result=、since=、until= 过滤。",
               link(url("ops", command="undo"), "undo"), link(url("ops", command="redo"), "redo"))
        )
        rows = [
            [
                esc(item.get("id") or ""),
                esc(item.get("time") or ""),
                esc(item.get("result") or ""),
                esc(item.get("document") or ""),
                esc(item.get("field") or ""),
                pre(item.get("after") or ""),
            ]
            for item in payload.get("events") or []
        ]
        body += table([tr("编号"), tr("时间"), tr("动作"), tr("文档"), tr("字段"), tr("结果")], rows)
        body += note(tr("共 {} 条记录，显示 {} 条。", payload.get("selected", 0), payload.get("shown", 0)))
        body += h3(tr("撤销与重做"))
        body += form(url("ops", command="undo"), [text_field("count", tr("条数"), "1", 6)], tr("检查"))
        body += form(url("ops", command="redo"), [text_field("count", tr("条数"), "1", 6)], tr("检查"))
        return self.shell(tr("事件日志"), body, scope.name)

    def page_assets(self, query: dict[str, str]) -> str:
        """The pictures and sounds of the project, drawn from the files themselves.

        The bytes come from the read-only ``/asset`` route, so a thumbnail is the
        real file and not a copy: replacing it on disk changes what the page shows.
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        wanted = query.get("folder") or ""
        folders = [wanted] if wanted else list(ASSET_FOLDERS)
        body = crumbs([(url("index"), tr("首页")), ("", tr("资源"))])
        body += h2(tr("资源"))
        body += note(tr("这里画的是工程目录里的图片与声音文件本身；点图片打开原图，声音可以直接播放。"))
        drawn = 0
        for folder in folders:
            root = scope.project / folder
            if not root.is_dir():
                body += note(tr("工程里没有 {} 目录。", folder))
                continue
            found = sorted(
                path.relative_to(scope.project).as_posix()
                for path in root.rglob("*")
                if path.is_file() and is_previewable(path.name)
            )
            body += h3(tr("{} 目录（{} 个可预览）", folder, len(found)))
            if not found:
                body += note(tr("这个目录里没有可预览的文件。"))
                continue
            tiles = []
            for relative in found[:ASSET_ROWS]:
                source = url("asset", path=relative)
                name = esc(relative.rsplit("/", 1)[-1])
                if asset_type(relative).startswith("image/"):
                    tiles.append(
                        f'<figure class="tile"><a href="{att(source)}" target="_blank" rel="noopener">'
                        f'<img class="thumb" src="{att(source)}" alt="{name}" loading="lazy"></a>'
                        f"<figcaption>{name}</figcaption></figure>"
                    )
                else:
                    tiles.append(
                        f'<figure class="tile"><audio controls preload="none" src="{att(source)}"></audio>'
                        f"<figcaption>{name}</figcaption></figure>"
                    )
            body += f'<div class="gallery">{"".join(tiles)}</div>'
            if len(found) > ASSET_ROWS:
                body += note(tr("只显示前 {} 项，共 {} 项。", ASSET_ROWS, len(found)))
            drawn += min(len(found), ASSET_ROWS)
        body += note(tr("共显示 {} 项。", drawn))
        return self.shell(tr("资源"), body, scope.name, tr("图片与声音"))

    def page_ops(self, query: dict[str, str]) -> str:
        """Every writing command as a form, with a check step before the write.

        Nothing is written until the confirmation step is followed: this UI is GET-only, so a
        link can be prefetched or followed by accident, and the write is kept one deliberate
        click away from the page that shows what it would do.

        The check step passes ``write=1 dry-run=1``, which is the line a person would type:
        every writing command takes ``--write``, and ``--dry-run`` is what keeps it from
        touching the disk (docs/cli.md section 4).
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        offered = operations()
        wanted = query.get("command", "")
        if not wanted:
            body = h2(tr("写入操作"))
            body += note(tr("每条写入命令一张表。先按「检查」：下一步给出等价命令行和只检查不写入的真实结果，确认后再写入。"))
            rows = [
                [
                    link(url("ops", command=item.command), item.command),
                    esc(item.title),
                    esc(item.selector or tr("不需要文档")),
                ]
                for item in offered
            ]
            body += table([tr("命令"), tr("名称"), tr("文档参数")], rows)
            body += note_html(tr("要运行任意命令用{}。", link(url("cmd"), tr("命令行页"))))
            return self.shell(tr("写入操作"), body, scope.name)
        operation = next((item for item in offered if item.command == wanted), None)
        if operation is None:
            raise UsageError(tr("没有这条写入命令：{}", wanted))
        selector = query.get("selector", "").strip()
        options = operation_options(operation, query)
        body = crumbs([(url("index"), tr("首页")), (url("ops"), tr("写入操作")), ("", operation.command)])
        body += h2(f"{operation.command} · {operation.title}")
        body += note(operation.note)
        fields = []
        if operation.selector:
            fields.append(text_field("selector", operation.selector, selector, 60))
        fields.extend(operation_field(spec, query.get(spec[0], "")) for spec in operation.fields)
        body += form(url("ops", command=operation.command), fields, tr("检查"))
        if query.get("confirm") != "1":
            return self.shell(operation.title, body, scope.name)
        check = {"actor": "web", **options, "write": "1", "dry-run": "1"}
        body += h3(tr("将要运行"))
        body += pre(shell_line(scope.name, operation.command, selector, check))
        body += h3(tr("只检查不写入"))
        refused = ""
        try:
            dry = self.app.call(operation.command, scope, selector, **check)
        except (UsageError, FfError) as error:
            refused = str(error)
            body += bad(refused)
        else:
            body += pre(dry.text or tr("（这条命令没有文本输出，看载荷）"))
            if dry.code != 0:
                body += warn(tr("退出码 {}：命令报了失败项，写入前先看上面的输出。", dry.code))
        if not refused and query.get("write") == "1":
            # The journal records where a write came from; a form is the web surface, so it
            # writes as ``web`` unless the command line names an actor itself.
            result = self.app.call(operation.command, scope, selector, **{"actor": "web", "write": "1", **options})
            body += h3(tr("写入结果"))
            body += warn(tr("已写入，退出码 {}。", result.code))
            body += pre(result.text or tr("（这条命令没有文本输出，看载荷）"))
            body += note_html(
                tr("等价命令：") + mono(shell_line(scope.name, operation.command, selector, {**options, "write": "1"}))
                + " · " + self.json_link(scope.name, operation.command, selector=selector, **options)
            )
            return self.shell(operation.title, body, scope.name)
        if refused:
            body += note(tr("命令拒绝了这次检查；写入不会比它更宽容，因此没有写入链接。"))
            return self.shell(operation.title, body, scope.name)
        body += warn(tr("尚未写入。核对上面的结果，确认无误后再按「写入」。"))
        body += note_html(link(url("ops", command=operation.command, confirm="1", write="1", selector=selector, **options), tr("写入")))
        return self.shell(operation.title, body, scope.name)

    # --- MCP panel ----------------------------------------------------------

    def mcp_defaults(self) -> dict[str, str]:
        """The scope options this session was started with, handed to the in-process server."""
        return {key: value for key, value in self.app.options.items() if key in MCP_KEYS and value}

    def mcp_server(self, *, write: bool, scope_name: str = ""):
        """One MCP session in process, over the same specification table a client reads.

        The server is built per request with the options of this web session, so a trial call
        resolves the scopes of the page and produces the JSON-RPC answer a client would get.
        """
        from core.mcp.server import Server  # imported here so a plain web start never loads it

        defaults = dict(self.mcp_defaults())
        if scope_name:
            defaults["scope"] = scope_name
        return Server(write=write, defaults=defaults, cwd=self.app.cwd)

    def mcp_args(self, write: bool) -> list[str]:
        """The arguments of the command that starts a server for this workspace."""
        parts = ["-m", "core.mcp"]
        if write:
            parts.append("--write")
        parts.extend(f"{key}={value}" for key, value in sorted(self.mcp_defaults().items()))
        return parts

    def mcp_command(self, write: bool) -> str:
        """The command a person runs to start the server by hand; a path with a space is quoted."""
        return " ".join(f'"{part}"' if " " in part else part for part in ["python", *self.mcp_args(write)])

    def mcp_snippet(self) -> str:
        """The two command lines and the block a client's configuration takes."""
        block = json.dumps(
            {"mcpServers": {"firefight-mod-editor": {"command": "python", "args": self.mcp_args(True)}}},
            ensure_ascii=False,
            indent=2,
        )
        return pre(f"{self.mcp_command(False)}\n{self.mcp_command(True)}\n\n{block}")

    def mcp_tools_table(self) -> str:
        """Every registered tool: the exposed name, the command, read or write, its arguments."""
        rows = []
        for spec in specs.TOOLS:
            parameters = ", ".join(
                f"{parameter.name}=*" if parameter.required else parameter.name for parameter in spec.parameters
            )
            rows.append(
                [
                    mono(specs.exposed_name(spec.name)),
                    mono(spec.command),
                    tr("写入") if spec.writes else tr("只读"),
                    esc(parameters) if parameters else "—",
                ]
            )
        return table([tr("工具"), tr("命令"), tr("读或写"), tr("参数")], rows, tr("没有工具"))

    def mcp_trial(self, scope_name: str, query: dict[str, str]) -> str:
        """One ``tools/call`` answered by a server started in this request, printed as it came."""
        name = query.get("tool", "").strip()
        raw = query.get("arguments", "").strip() or "{}"
        if len(raw) > MCP_ARGUMENTS:
            return bad(tr("参数超过 {} 字节。", MCP_ARGUMENTS))
        try:
            arguments = json.loads(raw)
        except ValueError as error:
            return bad(tr("参数不是 JSON：{}", str(error)))
        if not isinstance(arguments, dict):
            return bad(tr("参数必须是一个 JSON 对象。"))
        canonical = specs.canonical_name(name)
        spec = specs.tool_named(canonical) if canonical else None
        if spec is None or not spec.available:
            return bad(tr("没有这个工具：{}（名字要带 {} 前缀）", name, specs.TOOL_PREFIX))
        url = self.app.url(scope_name)
        check_only = spec.writes and query.get("write") != "1"
        if check_only:
            # The check step is the line a person would type: the tool still runs with write on,
            # and dryRun is what stops it from writing (docs/mcp.md section 4).
            arguments = {**arguments, "dryRun": True}
        answer = self.mcp_server(write=True, scope_name=scope_name).handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        )
        body = ""
        if check_only:
            body += warn(tr("这是一个写入工具；这次试跑加了 dryRun，因此什么也没有写。"))
        elif spec.writes:
            body += bad(tr("已按原样运行，写入已经发生。"))
        body += pre(json.dumps(answer, ensure_ascii=False, indent=2, default=str))
        if check_only:
            body += note_html(
                link(
                    url("mcp", tool=name, arguments=query.get("arguments", "{}"), confirm="1", write="1"),
                    tr("按原样再跑一次（会写入）"),
                )
            )
        return body

    def mcp_listener_section(self, scope_name: str, query: dict[str, str]) -> str:
        """The optional second socket: its state when it is open, and the form that opens it.

        The listener binds one host and port in this process and answers the same protocol over
        HTTP POST with a token of its own. Opening it is a real bind, so it is refused with the
        reason when the port is taken; closing it shuts the socket down at once.
        """
        state = self.app.mcp.state()
        url = self.app.url(scope_name)
        body = h3(tr("监听"))
        body += note(tr("MCP 通常由客户端以 stdio 启动（上一节的两行）。只支持 HTTP 的客户端可以在这里另开一个端口，本进程用同一张工具表应答。"))
        if state:
            rows = [
                (tr("地址"), mono(state["url"])),
                (tr("绑定"), mono(f"{state['bind']}:{state['port']}")),
                (tr("令牌"), mono(state["token"])),
                (tr("写入"), tr("允许") if state["write"] else tr("只读")),
                (tr("开始于"), mono(state["at"])),
            ]
            body += kv(rows)
            body += pre(json.dumps(
                {"mcpServers": {"firefight-mod-editor": {
                    "url": state["url"],
                    "headers": {mcp_listener.TOKEN_HEADER: state["token"]},
                }}},
                ensure_ascii=False, indent=2))
            body += note(tr("监听开着的时候，局域网里的其它机器可以连到上面这个地址；令牌是它唯一的门，因此只在本机使用时选 127.0.0.1 更窄。"))
            body += note_html(link(url("mcpstop"), tr("关闭监听")))
            return body
        body += note(tr("现在没有在监听。"))
        body += form(
            url("mcpstart"),
            [
                select_field(
                    "host",
                    tr("监听地址"),
                    [("local", tr("127.0.0.1（仅本机）")), ("lan", tr("0.0.0.0（局域网）"))],
                    query.get("host", "local"),
                ),
                text_field("port", tr("端口"), query.get("port", str(mcp_listener.DEFAULT_PORT)), 8),
                checkbox("write", tr("允许写入（默认只读）"), False),
            ],
            tr("打开监听"),
        )
        body += note(tr("默认只读：不带写入开关时，写入类工具与不带 --write 的命令行服务器一样不会被登记。"))
        return body

    def mcp_control(self, route: str, query: dict[str, str]) -> None:
        """Open or close the panel's second socket, then go back to the panel."""
        back = self.app.url(self.app.default_scope)("mcp")
        try:
            self.check_token(query)
            if route == "mcpstart":
                self.app.mcp.start(
                    host=query.get("host", "local"),
                    port=int(query.get("port") or mcp_listener.DEFAULT_PORT),
                    write=query.get("write") == "1",
                    defaults=self.mcp_defaults(),
                    cwd=self.app.cwd,
                )
            else:
                self.app.mcp.stop()
        except ValueError as error:
            self.respond(400, self._error_page(tr("用法错误"), str(error), tr("端口要是一个整数。")))
            return
        except UsageError as error:
            self.respond(400, self._error_page(tr("用法错误"), str(error), tr("回到 MCP 页重新选择。")))
            return
        self.send_response(302)
        self.send_header("Location", back)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def page_mcp(self, query: dict[str, str]) -> str:
        """The MCP panel: the tool table, the connection snippet and one trial call.

        The tools are the ones the MCP server registers, which are one specification table
        (``core/cli/specs.py``) with the DSH plugin reading the same rows; the panel therefore
        shows what a client sees, and the trial runs the call in process instead of over stdio.
        """
        scope = self.app.scope(query.get("scope") or "")
        url = self.app.url(scope.name)
        body = h2(tr("MCP"))
        body += note(tr("MCP 服务与 DSH 插件读的是同一张工具规格表，这一页列的就是它登记的工具。"))
        body += h3(tr("连接"))
        body += note(tr("命令行启动的服务器把工具交给任何 MCP 客户端；下面两行只差 --write。"))
        body += self.mcp_snippet()
        body += self.mcp_listener_section(scope.name, query)
        body += h3(tr("工具"))
        body += self.mcp_tools_table()
        body += note(tr("参数名后带 * 的是必填项；不带 --write 的服务器只登记不写入的工具。"))
        body += h3(tr("试跑"))
        body += note(tr("在进程内跑一次 tools/call，原样显示 JSON-RPC 应答；不经过网络，也不另起进程。"))
        body += form(
            url("mcp"),
            [
                text_field("tool", tr("工具名"), query.get("tool", specs.exposed_name("ff_list")), 40),
                text_area("arguments", tr("参数（JSON 对象）"), query.get("arguments", "{}"), 6),
            ],
            tr("试跑"),
        )
        if query.get("tool"):
            body += self.mcp_trial(scope.name, query)
        return self.shell(tr("MCP"), body, scope.name)

    def page_cmd(self, query: dict[str, str]) -> str:
        """A command line: run one CLI command and print exactly what the CLI prints.

        The line is what you would type after `python -m core.cli`, optionally starting with a scope
        name (`Mod stats`). Quoting a path with a space works; writing commands run here too and the
        command's own gate decides whether they write; only `web` is refused, because it would bind a
        second port inside a request.
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        line = query.get("line", "").strip()
        as_json = query.get("json", "") in ("1", "yes", "true")
        body = h2(tr("命令行"))
        body += note(tr("输入 python -m core.cli 后面的部分即可，例如 list weapon、stats、show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml、deps value=WEAPON_PISTOL_P38。"))
        body += note(tr("可选在最前面写作用域（Firefight / Mod / 模组文件夹名）；路径带空格时用双引号。写入类命令会照常运行，是否落盘由命令自身的门决定；web 会被拒绝。"))
        body += form(url("cmd"), [text_field("line", tr("命令"), line, 80), checkbox("json", tr("JSON 输出"), as_json)], tr("运行"))
        examples = ["list weapon", "stats", "check", "deps value=WEAPON_PISTOL_P38", 'show "Data/Infantry/American-Rifle Squad.txt" as=toml']
        body += note_html(tr("示例：") + " · ".join(link(url("cmd", line=item), item) for item in examples))
        if not line:
            return self.shell(tr("命令行"), body, scope.name)
        tokens = split_command_line(line)
        known = self.app.scopes()
        if len(tokens) > 1 and tokens[0] in known:
            scope = self.app.scope(tokens.pop(0))
            url = self.app.url(scope.name)
        invocation = parse_argv(tokens)
        if not invocation.positionals:
            raise UsageError(tr("需要一个命令，例如 list weapon；把这一行补全再运行"))
        command = web_command(invocation.positionals[0])
        selector = " ".join(invocation.positionals[1:])
        started = time.monotonic()
        # A write reached through a page is recorded as ``web`` unless the line names an actor.
        result = self.app.call(command, scope, selector, **{"actor": "web", **invocation.options})
        elapsed = time.monotonic() - started
        shown = f"{scope.name} {command}" + (f" {selector}" if selector else "")
        self.app.last_command = {
            "line": shown + (" --json" if as_json else ""),
            "scope": scope.name,
            "exit": result.code,
            "elapsed": elapsed,
            "output": json.dumps(result.payload, indent=2, ensure_ascii=False, default=str) if as_json else (result.text or ""),
        }
        body += h2(tr("输出"))
        if as_json:
            body += pre(json.dumps(result.payload, indent=2, ensure_ascii=False, default=str))
        else:
            body += pre(result.text or tr("（这条命令没有文本输出；勾上 JSON 输出看载荷）"))
        rows = [(tr("作用域"), esc(scope.name)), (tr("命令"), esc(command)), (tr("选择器"), esc(selector or "all"))]
        if invocation.options:
            rows.append((tr("选项"), esc(", ".join(f"{key}={value}" for key, value in sorted(invocation.options.items())))))
        rows.append((tr("退出码"), tr("{}（0 成功，1 已执行但有失败）", result.code)))
        rows.append((tr("耗时"), f"{elapsed:.2f} s"))
        body += table([tr("项"), tr("值")], rows)
        # The JSON link previews the run. It must not carry ``write``: a link that reads like a
        # read would otherwise write a second time.
        json_options = dict(invocation.options)
        if json_options.get("write") == "1":
            json_options["dry-run"] = "1"
        body += note_html(
            tr("等价命令行：") + mono(f"ff {shown}" + (" --json" if as_json else ""))
            + " · " + link(url("json", command=command, selector=selector or "all", **json_options), tr("原始 JSON"))
            + " · " + link(url("cmd", line=shown + (" --json" if as_json else "")), tr("按 JSON 重跑"))
        )
        return self.shell(tr("命令行"), body, scope.name)

    def page_help(self, query: dict[str, str]) -> str:
        """What every page does and the CLI command behind it."""
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        body = h2(tr("页面与等价命令"))
        rows = [
            [link(url("index"), "/"), tr("作用域与清单"), mono(f"ff {scope.name} list")],
            [link(url("list"), "/list"), tr("实体表格，可按路径片段与分类过滤"), mono(tr("ff {} list <前缀>", scope.name))],
            [link(url("show", path=""), "/show"), tr("一个实体的原始 / TOML / XML 视图"), mono(tr("ff {} show <路径> as=toml", scope.name))],
            [link(url("get", path=""), "/get"), tr("某个字段的取值、文档路径与行号"), mono(tr("ff {} get <路径> field=<字段>", scope.name))],
            [link(url("edit"), "/edit"), tr("一个文档的全部字段，每行一个输入框"), mono(tr("ff {} get <路径>", scope.name))],
            [link(url("source"), "/source"), tr("一份文档的整段文本，可直接改 TOML 或 XML 后保存"), mono(tr("ff {} set <路径> field=<字段> value=<值> --write", scope.name))],
            [link(url("tables"), "/tables"), tr("工程设置的清单文件，一行一条，可改可删可追加"), mono(tr("ff {} show <路径>", scope.name))],
            [link(url("log"), "/log"), tr("事件日志，以及撤销与重做的入口"), mono(f"ff {scope.name} log")],
            [link(url("assets"), "/assets"), tr("工程里的图片与声音；缩略图就是文件本身"), mono(tr("ff {} convert <选择器> to=<目录> assets=1", scope.name))],
            [link(url("ops"), "/ops"), tr("11 条写入命令的表单；先检查，确认后才写入"), mono(tr("ff {} set <路径> field=<字段> value=<值> --write", scope.name))],
            [link(url("mcp"), "/mcp"), tr("MCP 工具表、连接片段，以及在进程内试跑一次 tools/call"), mono(tr("python -m core.mcp --write"))],
            [link(url("find"), "/find"), tr("按标签、取值或文档路径搜索"), mono(tr("ff {} find <前缀> tag=…", scope.name))],
            [link(url("refs", path=""), "/refs"), tr("一个实体指向谁"), mono(tr("ff {} refs <路径>", scope.name))],
            [link(url("deps"), "/deps"), tr("谁引用了某个取值"), mono(tr("ff {} deps value=<取值>", scope.name))],
            [link(url("check"), "/check"), tr("读取错误、警告与悬空引用"), mono(tr("ff {} check <前缀>", scope.name))],
            [link(url("stats"), "/stats"), tr("按分类、格式、根元素统计"), mono(f"ff {scope.name} stats")],
            [link(url("cmd"), "/cmd"), tr("一行命令，输出与 CLI 完全相同（写入的命令由它自己的门决定）"), mono(tr("ff {} <命令> <选择器> 键=值", scope.name))],
            [link(url("json", command="list", selector="all"), "/json"), tr("任何命令的原始 JSON"), mono(tr("加 --json 的同一个命令"))],
        ]
        body += table([tr("页面"), tr("做什么"), tr("等价命令")], rows)
        body += h2(tr("说明"))
        body += note(tr("页面跑的是与命令行相同的代码，写入类命令也一样：命令自身的门（--write、工程目录限制）决定是否落盘。只拒绝 web，因为它会在一次请求里再起一个服务。"))
        body += note(tr("链接里的 scope 参数指定作用域，t 参数是访问令牌（启动时带 token= 才需要）。"))
        body += note(tr("单线程服务，一次处理一个请求；Ctrl-C 或页面上的「退出」停止。"))
        return self.shell(tr("帮助"), body, scope.name)

    def page_quit(self, query: dict[str, str]) -> str:
        """Stop the server from the browser; /quit asks first, /quit?do=1 does it.

        A GET is the only verb this interface has (the script fetches and never
        posts), so the exit is a two-step page: a link can be followed by a
        prefetcher or by accident, a second deliberate click cannot.
        """
        scope = self.app.scope(query.get("scope", ""))
        url = self.app.url(scope.name)
        if query.get("do", "") not in ("1", "yes", "true"):
            body = h2(tr("退出 Web UI"))
            body += note(tr("这个按钮会停止 127.0.0.1 上的本地服务进程，然后你可以关掉这个窗口。"))
            body += note(tr("它不改任何数据文件，也不影响正在跑的编辑器 CLI。"))
            body += form(url("quit", do="1"), [], tr("退出 Web UI"))
            body += note_html(tr("返回 ") + link(url("index"), tr("首页")))
            return self.shell(tr("退出"), body, scope.name)
        self.server.request_quit()  # type: ignore[attr-defined]
        body = good(tr("已退出：服务正在停止，刷新这个页面也不会再有响应。"))
        body += note(tr("窗口里按 Ctrl-C 或直接关掉窗口即可；要重新打开界面，用启动器再启动一次。"))
        body += note_html(link(url("index"), tr("万一服务还在，回到首页")))
        return self.shell(tr("已退出"), body, scope.name)


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


INSTANCE_NAME = "web.json"
PROBE_TIMEOUT = 0.6
PORT_ATTEMPTS = 25


def state_root(cwd: Path) -> Path:
    """Where the running-instance record lives: the editor folder, else the project, else cwd."""
    editor = _editor_root(Path(cwd))
    if editor is not None:
        return Path(editor)
    project = _project_root(Path(cwd))
    return Path(project) if project is not None else Path(cwd)


def instance_path(root: Path) -> Path:
    """The record file of one editor folder or project."""
    return Path(root) / EDITOR_DIR / INSTANCE_NAME


def read_instance(root: Path) -> dict | None:
    """The recorded instance when it is still answering, else ``None``.

    A record left behind by a killed process is stale: the probe decides, so a crashed UI
    never keeps the next one from starting.
    """
    try:
        record = json.loads(instance_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url = record.get("url") if isinstance(record, dict) else None
    if not isinstance(url, str) or not url:
        return None
    return record if answers(url) else None


def answers(url: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """True when the recorded address answers with a page."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def free_port(start: int = DEFAULT_PORT, host: str = HOST, attempts: int = PORT_ATTEMPTS) -> int:
    """The first port at or above ``start`` that nothing is listening on."""
    for port in range(start, start + attempts):
        if not port_is_taken(port, host):
            return port
    raise FfError(f"no free port between {start} and {start + attempts - 1} on {host}")


def write_instance(root: Path, record: dict) -> None:
    """Record the running instance so a later `web` can reuse it."""
    path = instance_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_instance(root: Path, record: dict) -> None:
    """Drop the record, unless another process has already replaced it."""
    path = instance_path(root)
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if current.get("pid") == record.get("pid") and current.get("port") == record.get("port"):
        path.unlink(missing_ok=True)


def open_browser(options: dict[str, str], address: str) -> None:
    """Open the page when the caller asked for a browser; a browser is a convenience."""
    if options.get("browser") in (None, "", "0", "false", "no"):
        return
    try:
        import webbrowser

        webbrowser.open(address)
    except Exception as error:
        print(f"  (cannot open a browser automatically: {error})", flush=True)


def serve(options: dict[str, str], cwd, scope_name: str, host: str = HOST) -> str:
    """Serve the UI until Ctrl-C, or point at the instance that is already running.

    An explicit ``port=`` always starts a server.  Without one, a recorded instance that still
    answers is reused: its front end is opened and this process returns at once, so a second
    backend never starts by accident.  Otherwise the first free port at or above the default is
    taken (docs/cli.md section 4.4).
    """
    token = options.get("token", "")
    size = _int_option(options, "pagesize", DEFAULT_LIMIT)
    try:
        language = use(options.get("lang") or LANGUAGE_DEFAULT)
    except ValueError as error:
        raise UsageError(str(error)) from None
    root = state_root(cwd)
    if options.get("port") in (None, ""):
        running = read_instance(root)
        if running is not None:
            address = str(running.get("url") or "")
            print(tr("Firefight 模组编辑器 Web UI · 已有实例在运行"), flush=True)
            print(tr("  复用     pid {} · 作用域 {}", running.get('pid'), running.get('scope') or scope_name), flush=True)
            print(tr("  地址     {}", address), flush=True)
            open_browser(options, address)
            return address
        port = free_port(DEFAULT_PORT, host)
    else:
        port = _int_option(options, "port", DEFAULT_PORT)
    app = App(options, cwd, scope_name, page_size=size, token=token, language=language)
    try:
        server = make_server(app, port, host)
    except OSError as error:
        raise FfError(f"cannot listen on {host}:{port}: {error}") from error
    address = f"http://{host}:{server.server_port}/"
    if token:
        address += f"?t={token}"
    record = {
        "pid": os.getpid(),
        "host": host,
        "port": server.server_port,
        "url": address,
        "scope": scope_name,
        "token": token,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_instance(root, record)
    print(tr("Firefight 模组编辑器 Web UI · 作用域 {}", scope_name), flush=True)
    print(tr("  根目录   {}", app.scope(scope_name).root), flush=True)
    print(tr("  地址     {}", address), flush=True)
    print(tr("  实例记录 {}", instance_path(root)), flush=True)
    print(tr("  页面     服务端渲染，一个内联脚本只负责工作台布局"), flush=True)
    print(tr("  停止     Ctrl-C，或页面上的「退出」"), flush=True)
    open_browser(options, address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(tr("\n已停止。"), flush=True)
    else:
        if server.quit_requested:
            print(tr("\n已在浏览器里退出。"), flush=True)
            # an ASCII marker on purpose: the launcher's watchdog reads this log to tell a
            # graceful stop from a killed process, and ASCII survives any code page
            print("web: stopped by the quit link", flush=True)
    finally:
        server.server_close()
        clear_instance(root, record)
    return address
