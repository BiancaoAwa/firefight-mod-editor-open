"""`add`, `remove` and the undo of a whole document.

A document that appears or disappears is one more logged change, so the tests
check the bytes on disk and that ``undo`` and ``redo`` move the file back and
forth (docs/cli.md sections 4.2 and 4.7).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_documents"
PROJECT = SCRATCH / "project"
SEED = "Data/Weapons/WEAPON_SEED.toml"

SEED_TOML = """[weapon]

name = "Seed Gun"

type = "WEAPON_RIFLE"
"""


def write(path: Path, text: str) -> None:
    """Write fixture text as UTF-8 with LF endings and no BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


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


class DocumentTestCase(unittest.TestCase):
    """A project with one weapon, rebuilt for every test."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        write(PROJECT / "ModInformation.toml", 'name = "Document Fixture"\n')
        write(PROJECT / SEED, SEED_TOML)

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def document(self, name: str) -> Path:
        """The path of a document in the fixture project."""
        return PROJECT / "Data/Weapons" / name

    def test_add_writes_the_schema_skeleton(self) -> None:
        code, payload, _ = run_json("Mod", "add", "Data/Weapons/WEAPON_NEW.toml", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["root"], "weapon")
        self.assertEqual(payload["result"], "add")
        self.assertFalse(payload["existed_before"])
        raw = self.document("WEAPON_NEW.toml").read_bytes()
        self.assertNotIn(b"\xef\xbb\xbf", raw)
        self.assertIn(b"[weapon]\r\n", raw)
        self.assertIn(b'name = ""\r\n', raw)
        self.assertNotIn(b"\n\n\n", raw)

    def test_add_from_copies_a_document(self) -> None:
        code, payload, _ = run_json(
            "Mod", "add", "Data/Weapons/WEAPON_COPY.toml", f"from={SEED}", "--write", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["entity"], "Seed Gun")
        code, copy, _ = run_json("Mod", "get", "Data/Weapons/WEAPON_COPY.toml", cwd=PROJECT)
        self.assertEqual(code, 0)
        _, seed, _ = run_json("Mod", "get", SEED, cwd=PROJECT)
        self.assertEqual(
            [(row["path"], row["value"]) for row in copy["values"]],
            [(row["path"], row["value"]) for row in seed["values"]],
        )

    def test_add_dry_run_writes_nothing(self) -> None:
        code, payload, _ = run_json(
            "Mod", "add", "Data/Weapons/WEAPON_NEW.toml", "--write", "--dry-run", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(self.document("WEAPON_NEW.toml").exists())
        self.assertFalse((PROJECT / "EditorCache").exists())

    def test_add_needs_write(self) -> None:
        code, _, err = run("Mod", "add", "Data/Weapons/WEAPON_NEW.toml", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("add needs --write", err)

    def test_add_refuses_a_document_that_is_there(self) -> None:
        code, _, err = run("Mod", "add", SEED, "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("already there", err)
        self.assertEqual((PROJECT / SEED).read_bytes(), SEED_TOML.encode("utf-8"))

    def test_add_refuses_the_stock_scope(self) -> None:
        code, _, err = run("Firefight", "add", "Data/Weapons/WEAPON_NEW.toml", f"root={PROJECT}", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("read-only", err)

    def test_add_refuses_a_folder_it_cannot_type(self) -> None:
        code, _, err = run("Mod", "add", "Data/Widgets/THING.toml", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("cannot tell which root element", err)

    def test_remove_deletes_and_undo_puts_it_back(self) -> None:
        target = self.document("WEAPON_SEED.toml")
        code, payload, _ = run_json("Mod", "remove", SEED, "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["existed_before"])
        self.assertFalse(target.exists())
        code, payload, _ = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "undo")
        self.assertEqual(target.read_bytes(), SEED_TOML.encode("utf-8"))

    def test_undo_of_an_added_document_deletes_it(self) -> None:
        added = self.document("WEAPON_NEW.toml")
        self.assertEqual(run_json("Mod", "add", "Data/Weapons/WEAPON_NEW.toml", "--write", cwd=PROJECT)[0], 0)
        self.assertTrue(added.exists())
        code, payload, _ = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "undo")
        self.assertFalse(added.exists())

    def test_redo_removes_the_document_again(self) -> None:
        added = self.document("WEAPON_NEW.toml")
        self.assertEqual(run_json("Mod", "add", "Data/Weapons/WEAPON_NEW.toml", "--write", cwd=PROJECT)[0], 0)
        before = added.read_bytes()
        self.assertEqual(run_json("Mod", "undo", "--write", cwd=PROJECT)[0], 0)
        self.assertFalse(added.exists())
        code, payload, _ = run_json("Mod", "redo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "redo")
        self.assertEqual(added.read_bytes(), before)

    def test_remove_needs_write(self) -> None:
        code, _, err = run("Mod", "remove", SEED, cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("remove needs --write", err)

    def test_remove_refuses_a_document_that_is_not_there(self) -> None:
        code, _, err = run("Mod", "remove", "Data/Weapons/WEAPON_NEW.toml", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())
        self.assertFalse(self.document("WEAPON_NEW.toml").exists())


if __name__ == "__main__":
    unittest.main()
