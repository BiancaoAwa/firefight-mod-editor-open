"""`index` writes the cross-reference tables, and `refs` and `deps` read them.

The tables are a cache of the scope, so the tests check both halves: what the
command reports and writes, and that the readers fall back to a scan when the
cache is missing or stale (docs/cli.md section 4.6).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core import convert, schema, toml, xml
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_index"
PROJECT = SCRATCH / "project"

WEAPON_XML = """<weapon>
\t<name>Test Gun</name>
\t<type>WEAPON_RIFLE</type>
</weapon>
"""

SQUAD_XML = """<squad>
\t<name>Rifle Squad</name>
\t<man>
\t\t<weapon>
\t\t\t<type>WEAPON_TEST_GUN</type>
\t\t</weapon>
\t</man>
</squad>
"""

EQUIPMENT_LIST = """; an equipment list, skipped by every command that walks entities
[WEAPON_TEST_GUN]
"""

PLAIN_TEXT = """; a plain-text data file without an XML root
"""


def write(path: Path, text: str) -> None:
    """Write fixture text as cp1252 with LF endings and no BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("cp1252"))


def run(*argv: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run the CLI in a directory and capture its exit code and streams."""
    out, err = io.StringIO(), io.StringIO()
    previous = Path.cwd()
    try:
        os.chdir(cwd or SCRATCH)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
    finally:
        os.chdir(previous)
    return code, out.getvalue(), err.getvalue()


def run_json(*argv: str, cwd: Path | None = None) -> tuple[int, dict, str]:
    """Run the CLI with --json and parse the payload."""
    code, out, err = run(*argv, "--json", cwd=cwd)
    return code, json.loads(out) if out.strip() else {}, err


class IndexTestCase(unittest.TestCase):
    """A small project, rebuilt for every test because the tables live in it."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        write(PROJECT / "ModInformation.toml", 'name = "Index Fixture"\n')
        document = xml.parse(WEAPON_XML, "fixture")
        table = convert.xml_to_toml(document, schema.schema_for("weapon"))
        write(PROJECT / "Data/Weapons/WEAPON_TEST_GUN.toml", toml.render(table))
        write(PROJECT / "Data/Infantry/American-Rifle Squad.txt", SQUAD_XML)
        write(PROJECT / "Data/equipment_fixture.txt", EQUIPMENT_LIST)
        write(PROJECT / "Data/Manufacturers/notes.txt", PLAIN_TEXT)

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def test_index_needs_write(self) -> None:
        code, _, err = run("Mod", "index", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("index needs --write", err)

    def test_index_refuses_the_stock_scope(self) -> None:
        # The scope only has to resolve; the command refuses before it reads anything.
        code, _, err = run("Firefight", "index", f"root={PROJECT}", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("read-only", err)

    def test_index_writes_both_tables(self) -> None:
        code, payload, _ = run_json("Mod", "index", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["documents"], 2)
        self.assertEqual(payload["references"], 1)
        self.assertEqual(payload["skipped"], 2)
        self.assertEqual(payload["errors"], [])
        self.assertFalse(payload["dry_run"])
        editor = PROJECT / "EditorCache"
        self.assertTrue((editor / "index.toml").is_file())
        self.assertTrue((editor / "refs.toml").is_file())
        self.assertEqual(sorted(Path(item).name for item in payload["written"]), ["index.toml", "refs.toml"])

    def test_index_dry_run_writes_nothing(self) -> None:
        code, payload, _ = run_json("Mod", "index", "--write", "--dry-run", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["written"], [])
        self.assertFalse((PROJECT / "EditorCache").exists())

    def test_refs_read_the_stored_table(self) -> None:
        _, scanned, _ = run_json("Mod", "refs", cwd=PROJECT)
        self.assertEqual(scanned["origin"], "scan")
        self.assertEqual(run_json("Mod", "index", "--write", cwd=PROJECT)[0], 0)
        code, payload, _ = run_json("Mod", "refs", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["origin"], "index")
        self.assertEqual(payload["count"], scanned["count"])
        self.assertEqual(sorted(payload["by_kind"]), sorted(scanned["by_kind"]))

    def test_deps_read_the_stored_table(self) -> None:
        _, scanned, _ = run_json("Mod", "deps", "value=WEAPON_TEST_GUN", cwd=PROJECT)
        self.assertEqual(scanned["origin"], "scan")
        self.assertEqual(scanned["count"], 1)
        self.assertEqual(run_json("Mod", "index", "--write", cwd=PROJECT)[0], 0)
        code, payload, _ = run_json("Mod", "deps", "value=WEAPON_TEST_GUN", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["origin"], "index")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["references"][0]["source"], "Mod/Data/Infantry/American-Rifle Squad.txt")
        self.assertEqual(payload["resolved"], ["Data/Weapons/WEAPON_TEST_GUN.toml"])

    def test_a_changed_document_makes_the_table_stale(self) -> None:
        self.assertEqual(run_json("Mod", "index", "--write", cwd=PROJECT)[0], 0)
        write(PROJECT / "Data/Infantry/Second Squad.txt", SQUAD_XML)
        code, payload, _ = run_json("Mod", "refs", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["origin"], "scan")
        self.assertEqual(payload["count"], 2)

    def test_refs_fall_back_when_the_tables_are_gone(self) -> None:
        self.assertEqual(run_json("Mod", "index", "--write", cwd=PROJECT)[0], 0)
        (PROJECT / "EditorCache/refs.toml").unlink()
        code, payload, _ = run_json("Mod", "refs", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["origin"], "scan")


if __name__ == "__main__":
    unittest.main()
