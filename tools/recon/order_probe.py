"""Read-only probes over the stock data directory that constrain the M1 design.

Three questions are answered, all from measured data:

V1  TOML cannot put a bare key after a sub-table header, so a parent whose
    source order places a leaf after a branch cannot be written in source order.
V2  TOML cannot declare a table twice, so a branch name that reappears after a
    different sibling name cannot be written in source order.
M   The maximum number of occurrences of each child per parent instance, which
    decides whether a child becomes a table (max 1) or an array of tables (max >1).

Run:
    python tools/recon/order_probe.py --data "<game>/Data"
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys

TOKEN_RE = re.compile(r"<(/?)([A-Za-z_][A-Za-z0-9_\-]*)>")
PLAINTEXT_PREFIXES = ("equipment_", "surnames_")


def scan_tree(text: str):
    """Parse into [tag, [child, ...]] nodes, tolerating ragged or illegal input."""
    roots, stack = [], []
    for match in TOKEN_RE.finditer(text):
        closing, tag = match.group(1), match.group(2)
        if not closing:
            node = [tag, []]
            (stack[-1][1] if stack else roots).append(node)
            stack.append(node)
        elif stack and stack[-1][0] == tag:
            stack.pop()
        else:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    del stack[i:]
                    break
    return roots


def iter_nodes(roots):
    pending = list(roots)
    while pending:
        node = pending.pop()
        yield node
        pending.extend(node[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="stock Data directory (read-only)")
    args = ap.parse_args()

    files = []
    for root, _dirs, names in os.walk(args.data):
        for name in names:
            if name.lower().endswith(".txt"):
                files.append(os.path.join(root, name))
    files.sort()

    xml_files = 0
    leaf_after_branch_files = []
    reopened_branch_files = []
    leaf_after_branch_parents = collections.Counter()
    reopened_branch_parents = collections.Counter()
    max_child = collections.defaultdict(lambda: collections.Counter())

    for path in files:
        if os.path.basename(path).startswith(PLAINTEXT_PREFIXES):
            continue
        with open(path, "rb") as handle:
            text = handle.read().decode("cp1252")
        xml_files += 1

        v1 = v2 = None
        for node in iter_nodes(scan_tree(text)):
            tag, kids = node[0], node[1]
            if not kids:
                continue
            names = [child[0] for child in kids]

            seen_branch = False
            for child in kids:
                if child[1]:
                    seen_branch = True
                elif seen_branch:
                    if v1 is None:
                        v1 = (tag, child[0], tuple(names))
                    leaf_after_branch_parents[tag] += 1
                    break

            if v2 is None:
                for name in dict.fromkeys(names):
                    idxs = [i for i, n in enumerate(names) if n == name]
                    if idxs[-1] - idxs[0] + 1 != len(idxs):
                        v2 = (tag, name, tuple(names))
                        reopened_branch_parents[tag] += 1
                        break

            counts = collections.Counter(names)
            for name, count in counts.items():
                if count > max_child[tag][name]:
                    max_child[tag][name] = count

        rel = os.path.relpath(path, args.data)
        if v1:
            leaf_after_branch_files.append((rel, v1))
        if v2:
            reopened_branch_files.append((rel, v2))

    print(f"xml files scanned: {xml_files}")
    print()
    print(f"V1 leaf-after-branch: {len(leaf_after_branch_files)} files")
    for rel, hit in leaf_after_branch_files[:10]:
        print(f"    {rel}  parent={hit[0]} leaf={hit[1]} order={hit[2]}")
    if len(leaf_after_branch_files) > 10:
        print(f"    ... {len(leaf_after_branch_files) - 10} more")
    print("  parents affected:")
    for tag, count in leaf_after_branch_parents.most_common():
        print(f"    {tag:24s} {count}")
    print()
    print(f"V2 branch reopened after another name: {len(reopened_branch_files)} files")
    for rel, hit in reopened_branch_files:
        print(f"    {rel}  parent={hit[0]} branch={hit[1]} order={hit[2]}")
    print()
    print("M max occurrences of each child per parent instance")
    for parent in sorted(max_child):
        items = sorted(max_child[parent].items(), key=lambda kv: (-kv[1], kv[0]))
        print(f"    {parent:22s} " + ", ".join(f"{n}:{c}" for n, c in items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
