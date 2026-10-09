"""M1 corpus harness: XML -> TOML -> XML over the stock data tree.

Read-only with respect to the game directory.  Writes one TSV report and exits
non-zero if any modelled file fails (docs/toml-mapping.md section 8).

Usage:
    python tools/m1_roundtrip.py --data "<Firefight>/Data" --out docs
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import textio, xmlread  # noqa: E402
from core.convert import toml_to_xml, xml_to_toml  # noqa: E402
from core.errors import FfError  # noqa: E402
from core.schema import schema_for  # noqa: E402
from core.tomlmodel import TomlTable  # noqa: E402
from core.tomlread import parse as toml_parse  # noqa: E402
from core.tomlwrite import render as toml_render  # noqa: E402
from core.xmlmodel import signature  # noqa: E402

SKIP_PREFIXES = ("equipment_", "surnames_")
HEADER = "file\tsize\troot\txml_to_toml\ttoml_reparse\ttoml_to_xml\tcp1252\torder_match\twarnings\tnote"


def run_file(path: Path) -> tuple[list[str], bool]:
    """Run the round trip for one file; returns a report row and a pass flag."""
    source = textio.read_source(path)
    document = xmlread.parse(source.text, str(path))
    schema = schema_for(document.root.tag)
    if schema is None:
        return [], False
    warnings = len(document.warnings)
    try:
        table = xml_to_toml(document, schema)
    except FfError as error:
        return [f"{path.name}\t{len(source.text)}\t{document.root.tag}\t{error.__class__.__name__}\t-\t-\t-\t{warnings}\t{error}"], False
    rendered = toml_render(table)
    try:
        reparsed = toml_parse(rendered, str(path) + " (toml)")
    except FfError as error:
        return [f"{path.name}\t{len(source.text)}\t{document.root.tag}\tok\t{error.__class__.__name__}\t-\t-\t{warnings}\t{error}"], False
    stable = toml_render(reparsed) == rendered
    exported = toml_to_xml(reparsed, schema, str(path))
    encoded = "ok"
    try:
        textio.encode_export(exported, str(path))
    except FfError as error:
        encoded = error.__class__.__name__
    exported_document = xmlread.parse(exported, str(path) + " (export)")
    equivalent = signature(exported_document.root) == signature(document.root)
    order_match = textio.normalize_newlines(exported) == textio.normalize_newlines(source.text)
    note = "" if stable else "TOML text not idempotent"
    row = "\t".join([
        path.name,
        str(len(source.text)),
        document.root.tag,
        "ok",
        "ok" if stable else "unstable",
        "ok" if equivalent else "different",
        encoded,
        "yes" if order_match else "no",
        str(warnings),
        note,
    ])
    return [row], stable and equivalent and encoded == "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="stock Data directory (read-only)")
    parser.add_argument("--out", default="docs", help="directory for m1-roundtrip.tsv")
    parser.add_argument("--limit", type=int, default=0, help="stop after N modelled files")
    parser.add_argument("--verbose", action="store_true", help="print failures as they happen")
    args = parser.parse_args(argv)

    data = Path(args.data)
    if not data.is_dir():
        print(f"data directory not found: {data}", file=sys.stderr)
        return 2

    rows: list[str] = []
    failures: list[str] = []
    skipped = 0
    modelled = 0
    for path in sorted(p for p in data.rglob("*.txt") if p.is_file()):
        if path.name.startswith(SKIP_PREFIXES):
            skipped += 1
            continue
        row, passed = run_file(path)
        if not row:
            skipped += 1
            continue
        modelled += 1
        rows.append(row[0])
        if not passed:
            failures.append(row[0])
            if args.verbose:
                print("FAIL " + row[0])
        if args.limit and modelled >= args.limit:
            break

    out = Path(args.out) / "m1-roundtrip.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8", newline="\n")
    print(f"modelled {modelled}, skipped {skipped}, failures {len(failures)}")
    for failure in failures[:20]:
        print("  " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
