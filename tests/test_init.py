"""`init`: the one command that makes a project instead of resolving one.

It writes ``mod.toml`` from the schema skeleton and an empty ``Mod/Data``, refuses a
directory that already carries a ``mod.toml``, and records the new document like any other
new document so ``undo`` takes it away again (docs/cli.md section 4.9,
docs/project-layout.md section 3).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core import journal, toml as toml_core
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_init"
PROJECT = SCRATCH / "my-mod"


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


class InitTestCase(unittest.TestCase):
    """An empty directory, and the project `init` makes of it."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        PROJECT.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def init(self, *extra: str) -> tuple[int, dict, str]:
        return run_json("Mod", "init", f"root={PROJECT}", "--write", *extra)

    def manifest(self) -> Path:
        return PROJECT / "mod.toml"

    # --- the gate ---------------------------------------------------------------

    def test_init_needs_write(self) -> None:
        code, _, err = run("Mod", "init", f"root={PROJECT}", cwd=SCRATCH)
        self.assertEqual(code, 2)
        self.assertIn("init needs --write", err)
        self.assertFalse(self.manifest().exists())

    def test_init_refuses_the_stock_scope(self) -> None:
        code, _, err = run("Firefight", "init", f"root={PROJECT}", "--write", cwd=SCRATCH)
        self.assertEqual(code, 2)
        self.assertIn("init creates a project under Mod", err)

    def test_init_refuses_a_project_that_is_already_there(self) -> None:
        code, _, err = self.init()
        self.assertEqual(code, 0, err)
        code, _, err = self.init()
        self.assertEqual(code, 2)
        self.assertIn("a project is already here", err)

    # --- what it writes ---------------------------------------------------------

    def test_a_dry_run_writes_nothing(self) -> None:
        code, payload, err = self.init("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(list(PROJECT.iterdir()), [])
        self.assertFalse((PROJECT / ".editor").exists())

    def test_init_writes_the_manifest_and_the_data_folder(self) -> None:
        code, payload, err = self.init()
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["name"], "my-mod")
        self.assertTrue((PROJECT / "Mod" / "Data").is_dir())
        self.assertTrue(self.manifest().is_file())
        raw = self.manifest().read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "mod.toml has a BOM")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "mod.toml has a bare line feed")
        self.assertTrue(raw.endswith(b"\r\n"))
        table = toml_core.parse(raw.decode("utf-8"), "mod.toml")
        self.assertEqual(table.get("mod").get("name").value, "my-mod")

    def test_the_name_option_beats_the_directory_name(self) -> None:
        code, payload, err = self.init("name=Another Mod")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["name"], "Another Mod")
        table = toml_core.parse(self.manifest().read_text(encoding="utf-8"), "mod.toml")
        self.assertEqual(table.get("mod").get("name").value, "Another Mod")

    def test_the_skeleton_keeps_the_list_leaf_readable(self) -> None:
        self.init()
        table = toml_core.parse(self.manifest().read_text(encoding="utf-8"), "mod.toml")
        self.assertEqual(table.get("mod").get("authors").value, [])

    def test_the_working_directory_is_the_default_target(self) -> None:
        code, payload, err = run_json("Mod", "init", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(Path(payload["project"]).resolve(), PROJECT.resolve())
        self.assertTrue(self.manifest().is_file())

    # --- the project it leaves behind -------------------------------------------

    def test_the_new_document_is_recorded_and_undo_takes_it_away(self) -> None:
        code, payload, err = self.init()
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["id"])
        found = [event for event in journal.read_events(PROJECT) if event.get("result") == "add"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["document"], "mod.toml")
        self.assertEqual(found[0]["actor"], "cli")
        code, _, err = run("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertFalse(self.manifest().exists())

    def test_a_new_project_reads_back(self) -> None:
        self.init()
        code, payload, err = run_json("Mod", "stats", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["files"], 0)
        code, payload, err = run_json("Mod", "get", "mod.toml", "field=name", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["values"][0]["value"], "my-mod")
