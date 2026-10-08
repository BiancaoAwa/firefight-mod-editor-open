#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原版《交战 Firefight》数据基线勘察脚本（M0 阶段产物）。

用途
----
对指定游戏版本的 `Data/` 目录做**只读**统计，产出可复现的基线工件：

  <out>/tag-inventory.tsv   每个根元素下每个 XML 标签的出现次数与覆盖文件数
  <out>/summary.json        目录/编码/换行/缩进/可解析性等聚合统计
  stdout                    人读报告

设计约束（见 docs/m0-baseline.md）
--------------------------------
* 只用标准库，零依赖（本仓库硬约束）。
* 全程按 Windows-1252(cp1252) 解码，不做 BOM 猜测——原版全是 cp1252 无 BOM。
* **不**使用 `xml.etree` 作为统计入口：原版存在含裸 `&` 的非合法 XML 文件，
  本脚本用自研的宽松分词器，才能如实统计这些文件。严格可解析性另行单独统计。

用法
----
    python tools/recon/baseline_stats.py --data "<游戏目录>/Data" --out docs/baseline
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

# 宽松分词器：标签名允许大小写与数字（offsetX / HE / AA），但不允许以数字开头
# （`<1>`..`<7>` 只出现在 mod.txt 的 <ranks> 里，数据目录不涉及）。
TOKEN_RE = re.compile(r"<(/?)([A-Za-z_][A-Za-z0-9_\-]*)>")
FIRST_ROOT_RE = re.compile(r"\s*<([A-Za-z_][A-Za-z0-9_\-]*)>")

# 原版中非 XML 的纯文本清单文件（每行一个名字，可带 `// 注释`）
PLAINTEXT_PREFIXES = ("equipment_", "surnames_")

ENCODING = "cp1252"

# 非法的裸 &（不是 &amp; / &#38; 这类实体引用）
BARE_AMP_RE = re.compile(r"&(?!(?:#[0-9]+|[A-Za-z][A-Za-z0-9]*);)")


def read_text(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read().decode(ENCODING)


def collect(data_dir: str) -> dict:
    files: list[str] = []
    for root, _dirs, names in os.walk(data_dir):
        for name in names:
            files.append(os.path.join(root, name))
    files.sort()

    by_ext: collections.Counter[str] = collections.Counter()
    by_top: collections.Counter[str] = collections.Counter()
    by_dir: collections.Counter[str] = collections.Counter()
    first_root: collections.Counter[str] = collections.Counter()
    tag_count: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    tag_files: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    mixed_case: collections.Counter[str] = collections.Counter()

    bom = undecodable = crlf = lf_only = 0
    strict_ok = 0
    strict_bad: list[dict[str, str]] = []
    depth_hist: collections.Counter[int] = collections.Counter()
    depth_max = 0
    amp_bugs: list[str] = []

    for path in files:
        rel = os.path.relpath(path, data_dir)
        by_ext[os.path.splitext(path)[1].lower()] += 1
        by_top[rel.split(os.sep)[0] if os.sep in rel else "<root>"] += 1
        by_dir[os.path.dirname(rel).replace("\\", "/")] += 1

        raw = open(path, "rb").read()
        if raw.startswith(b"\xef\xbb\xbf"):
            bom += 1
        try:
            text = raw.decode(ENCODING)
        except UnicodeDecodeError:
            undecodable += 1
            text = raw.decode(ENCODING, errors="replace")
        if b"\r\n" in raw:
            crlf += 1
        else:
            lf_only += 1

        for line in text.splitlines():
            depth_hist[len(line) - len(line.lstrip("\t"))] += 1
            depth_max = max(depth_max, len(line) - len(line.lstrip("\t")))

        try:
            ET.fromstring(text)
            strict_ok += 1
        except ET.ParseError as exc:
            strict_bad.append({"file": rel, "error": str(exc)})
        if BARE_AMP_RE.search(text):
            amp_bugs.append(rel)

        top = rel.split(os.sep)[0]
        if rel.startswith(PLAINTEXT_PREFIXES) or top == "Surnames":
            continue
        match = FIRST_ROOT_RE.match(text)
        if not match:
            continue
        root_tag = match.group(1)
        first_root[root_tag] += 1

        stack: list[str] = []
        for token in TOKEN_RE.finditer(text):
            closing, tag = token.groups()
            if closing:
                if stack:
                    stack.pop()
                continue
            if re.search(r"[A-Z]", tag):
                mixed_case[tag] += 1
            tag_count[root_tag][tag] += 1
            tag_files[root_tag][tag] += 1
            stack.append(tag)

    return {
        "data_dir": os.path.abspath(data_dir),
        "file_count": len(files),
        "by_extension": dict(by_ext.most_common()),
        "by_top_dir": dict(by_top.most_common()),
        "by_dir": dict(sorted(by_dir.items())),
        "first_root": dict(first_root.most_common()),
        "encoding": {
            "name": ENCODING,
            "bom_files": bom,
            "undecodable_files": undecodable,
            "crlf_files": crlf,
            "lf_only_files": lf_only,
        },
        "indent": {
            "unit": "tab",
            "max_depth": depth_max,
            "depth_histogram": {str(k): v for k, v in sorted(depth_hist.items())},
        },
        "strict_xml": {
            "parsable": strict_ok,
            "unparsable": len(strict_bad),
            "unparsable_files": strict_bad,
            "bare_ampersand_files": amp_bugs,
        },
        "tag_inventory": {
            root: {tag: (tag_count[root][tag], tag_files[root][tag]) for tag in sorted(tag_count[root])}
            for root in sorted(tag_count)
        },
        "mixed_case_tags": dict(mixed_case.most_common()),
    }


def write_tsv(summary: dict, out_dir: str) -> str:
    path = os.path.join(out_dir, "tag-inventory.tsv")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("root\ttag\toccurrences\tfiles\n")
        for root, tags in summary["tag_inventory"].items():
            for tag, (count, files) in tags.items():
                fh.write(f"{root}\t{tag}\t{count}\t{files}\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="《交战》原版数据基线勘察（只读）")
    parser.add_argument("--data", default=r"D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data")
    parser.add_argument("--out", default="docs/baseline")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.data):
        print(f"[error] Data 目录不存在：{args.data}", file=sys.stderr)
        return 2

    summary = collect(args.data)
    os.makedirs(args.out, exist_ok=True)
    tsv = write_tsv(summary, args.out)
    json_path = os.path.join(args.out, "summary.json")
    with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")

    enc = summary["encoding"]
    strict = summary["strict_xml"]
    print(f"Data 目录      : {summary['data_dir']}")
    print(f"文件总数       : {summary['file_count']}")
    print(f"按扩展名       : {summary['by_extension']}")
    print(f"按顶层目录     : {summary['by_top_dir']}")
    print(f"首根元素       : {summary['first_root']}")
    print(f"编码           : {enc['name']}  BOM={enc['bom_files']}  无法解码={enc['undecodable_files']}")
    print(f"换行           : CRLF={enc['crlf_files']}  纯LF={enc['lf_only_files']}")
    print(f"缩进           : 制表符，最大深度={summary['indent']['max_depth']}")
    print(f"严格 XML 可解析: {strict['parsable']} / {summary['file_count']}"
          f"（不可解析 {strict['unparsable']}，其中裸 & 导致 {len(strict['bare_ampersand_files'])}）")
    print(f"大小写混合标签 : {summary['mixed_case_tags']}")
    for root, tags in summary["tag_inventory"].items():
        print(f"  root <{root}>: {len(tags)} 个不同标签，共 {sum(c for c, _ in tags.values())} 次出现")
    print(f"写出：{tsv}")
    print(f"写出：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
