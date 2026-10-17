"""Record the full text of the Firefight .mht documentation as one markdown file.

Each .mht is an MHTML archive whose first text/html part is the saved page.  The
converter keeps the reading order, turns headings into markdown headings, links
into markdown links, code blocks into fences and notes where the page showed a
screenshot (the archives are picture-heavy; the images themselves are not
transcribed).

Usage: python extract_docs_md.py <out.md> <page.mht> [...]
"""

from __future__ import annotations

import email
import html
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

HEADINGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}
BLOCK = {"p", "div", "section", "article", "li", "tr", "table", "ul", "ol", "blockquote", "hr"}
SKIP = {"script", "style", "head"}
CODE = {"pre", "code"}


class Markdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.pre = 0
        self.link: str | None = None
        self.link_text: list[str] = []

    # -- helpers ---------------------------------------------------------
    def _newline(self, count: int = 1) -> None:
        tail = "".join(self.out[-3:])
        if not tail.endswith("\n" * count):
            self.out.append("\n" * count)

    # -- parser hooks ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag in SKIP:
            self.skip += 1
        elif tag in HEADINGS:
            self._newline(2)
            self.out.append("\n" + HEADINGS[tag] + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("pre",):
            self.pre += 1
            self._newline(2)
            self.out.append("\n```\n")
        elif tag == "br":
            self.out.append("\n")
        elif tag == "img":
            src = attrs.get("src") or ""
            alt = attrs.get("alt") or ""
            if src:
                name = src.rsplit("/", 1)[-1]
                self.out.append(f"\n[图片: {alt or name}]\n")
        elif tag == "a" and attrs.get("href"):
            self.link = attrs["href"]
            self.link_text = []
        elif tag in BLOCK:
            self._newline(1)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag in HEADINGS or tag in BLOCK:
            self._newline(1)
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```\n")
        elif tag == "a" and self.link is not None:
            text = "".join(self.link_text).strip()
            href = self.link
            if text and text not in href:
                self.out.append(f"[{text}]({href})")
            elif text:
                self.out.append(f"<{href}>")
            self.link = None
            self.link_text = []

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.link is not None:
            self.link_text.append(data)
        else:
            self.out.append(data)

    # -- result ----------------------------------------------------------
    def text(self) -> str:
        raw = "".join(self.out)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def read_page(path: Path) -> tuple[str, str]:
    """Return (source url, page html)."""
    with path.open("rb") as handle:
        message = email.message_from_binary_file(handle)
    url = message.get("Snapshot-Content-Location", "")
    html_text = ""
    for part in message.walk():
        if part.get_content_type() != "text/html":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if not url:
            url = part.get("Content-Location", "")
        charset = part.get_content_charset() or "utf-8"
        for candidate in (charset, "windows-1252", "utf-8", "gbk", "cp1252"):
            try:
                html_text = payload.decode(candidate)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if html_text:
            break
    return url, html_text


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out_path = Path(argv[1])
    sources = [Path(name) for name in argv[2:]]

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        "# Firefight 官方模组文档（全文记录）",
        "",
        "来源：Sean O'Connor 的 Firefight 官网页面（windowsgames.co.uk），共 4 页，"
        "由浏览器「另存为」生成的 MHTML 存档。",
        "",
        f"存档包：`模组文档.zip`（5.3 MB，2026-10-11 02:44）",
        f"原件：`Firefight-Mod-Manager-Android\\FirefightMod\\_docs\\模组文档\\*.mht`（用户提供的浏览器存档）"
        f"　转换脚本：`firefight-mod-editor-open\\docs\\firefight-docs\\extract_docs_md.py`",
        f"记录时间：{stamp}",
        "",
        "说明：以下为页面正文的逐字记录（保留了标题层级、链接与代码块）。"
        "原页面还内嵌截图，图片本身未被转录，出现位置以 `[图片: …]` 标出。",
        "",
        "---",
    ]

    for index, source in enumerate(sources, start=1):
        url, html_text = read_page(source)
        parser = Markdown()
        parser.feed(html_text)
        body = parser.text()
        title = re.search(r"<title>(.*?)</title>", html_text, re.S)
        parts += [
            "",
            f"## {index}. {html.unescape(title.group(1)).strip() if title else source.stem}",
            "",
            f"- 页面地址：{url or '（存档未记录）'}",
            f"- 本地存档：`{source.name}`",
            "",
            body,
            "",
            "---",
        ]

    out_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(sources)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
