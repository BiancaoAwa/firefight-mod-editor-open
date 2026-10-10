"""Export fidelity harness: does `export` give the source bytes back?

Runs the real export command over a data directory and compares every file
byte for byte with the original.  Read-only with respect to the game
directory; the export goes into a scratch directory (deleted unless --keep).

Usage:
    python tools/export_fidelity.py --data "<Firefight>/Data" [--to <scratch>] [--limit N]

Exits non-zero when any file differs, so it can guard a regression the way
tools/m1_roundtrip.py does for the TOML round trip.
"""

import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli.main import main as cli_main  # noqa: E402

EXAMPLES = 5


def classify(source: bytes, exported: bytes) -> str:
    """Name the kind of difference, so a failure points at the layer."""
    if source == exported:
        return "identical"
    source_text = source.decode("cp1252", "replace")
    export_text = exported.decode("cp1252", "replace")
    if source_text.replace("\r\n", "\n") == export_text.replace("\r\n", "\n"):
        return "newline-only"
    source_lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    export_lines = [line.strip() for line in export_text.splitlines() if line.strip()]
    if sorted(source_lines) == sorted(export_lines):
        return "order-changed"
    return "content-changed"


def first_difference(source: bytes, exported: bytes) -> str:
    """A one-line hint: the first byte and the first differing line."""
    offset = next(
        (index for index, (left, right) in enumerate(zip(source, exported)) if left != right),
        min(len(source), len(exported)),
    )
    source_text = source.decode("cp1252", "replace").splitlines()
    export_text = exported.decode("cp1252", "replace").splitlines()
    line = 0
    for number, (left, right) in enumerate(zip(source_text, export_text), start=1):
        if left != right:
            line = number
            break
    else:
        line = min(len(source_text), len(export_text)) + 1
    def clip(text: str) -> str:
        return text if len(text) <= 70 else text[:67] + "..."

    source_line = source_text[line - 1] if line <= len(source_text) else "<end of file>"
    export_line = export_text[line - 1] if line <= len(export_text) else "<end of file>"
    return f"byte {offset}, line {line}: {clip(source_line)!r} -> {clip(export_line)!r}"


def run_export(root: Path, destination: Path) -> dict:
    """Call the CLI export in-process and return its JSON payload."""
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = cli_main(["Firefight", "export", f"root={root}", f"to={destination}", "--json"])
    output = captured.getvalue()
    try:
        payload = json.loads(output)
    except ValueError:
        print(output[-2000:], file=sys.stderr)
        raise SystemExit(f"export did not print JSON (exit {code})")
    if code not in (0, 1):
        raise SystemExit(f"export failed with exit {code}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="stock Data directory (read-only)")
    parser.add_argument("--to", default="", help="scratch directory for the export")
    parser.add_argument("--limit", type=int, default=0, help="stop after N files")
    parser.add_argument("--keep", action="store_true", help="keep the scratch export")
    parser.add_argument("--json", dest="report", default="", help="write the report as JSON here")
    args = parser.parse_args(argv)

    data = Path(args.data)
    if not data.is_dir():
        print(f"data directory not found: {data}", file=sys.stderr)
        return 2
    root = data.parent
    scratch = Path(args.to) if args.to else Path(tempfile.mkdtemp(prefix="ff-export-fidelity-"))

    payload = run_export(root, scratch)
    if payload.get("errors"):
        for error in payload["errors"][:EXAMPLES]:
            print("export error: " + str(error))
        return 1

    files = sorted(path for path in data.rglob("*.txt") if path.is_file())
    if args.limit:
        files = files[: args.limit]
    counts: dict[str, int] = {}
    failures: list[tuple[str, str]] = []
    rows: list[dict] = []
    for path in files:
        relative = path.relative_to(root)
        exported_path = scratch / relative
        if not exported_path.is_file():
            kind = "missing"
            hint = "the export did not write this file"
        else:
            source = path.read_bytes()
            exported = exported_path.read_bytes()
            kind = classify(source, exported)
            hint = "" if kind == "identical" else first_difference(source, exported)
        counts[kind] = counts.get(kind, 0) + 1
        rows.append({"file": str(relative).replace("\\", "/"), "kind": kind, "hint": hint})
        if kind != "identical":
            failures.append((str(relative), kind + (" - " + hint if hint else "")))

    print(f"files compared: {len(files)}")
    for kind in sorted(counts):
        share = 100.0 * counts[kind] / len(files) if files else 0.0
        print(f"  {kind:<16} {counts[kind]:>5}  {share:5.1f}%")
    if failures:
        print("not identical:")
        for name, why in failures[:EXAMPLES]:
            print(f"  {name}: {why}")
        if len(failures) > EXAMPLES:
            print(f"  ... {len(failures) - EXAMPLES} more")
    if args.report:
        Path(args.report).write_text(
            json.dumps({"compared": len(files), "counts": counts, "files": rows}, indent=2) + "\n",
            encoding="utf-8",
        )
    if not args.keep:
        shutil.rmtree(scratch, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
