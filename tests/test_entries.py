"""Adding and removing one array-of-tables entry with ``set op=``.

An entry is spliced into the source lines, so the tests check both the new block
and the bytes around it (docs/cli.md section 4.5).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_entries"
PROJECT = SCRATCH / "project"
DOCUMENT = "Data/Weapons/WEAPON_DEMO.toml"

MAPPED = """[weapon]
name = "Demo Rifle"
type = "WEAPON_RIFLE"

[weapon.ammo]

[[weapon.ammo.type]]
flavour = "FLAVOUR_HE"
speed = 800
mass = 0.012
HE = 0
name = "HE"

[weapon.shoot]
muzzle_flash = false
range = 800

[weapon.magazine]
capacity = 5
"""


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


class EntryTestCase(unittest.TestCase):
    """A project holding one weapon with one ammo entry."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        (PROJECT / "Data/Weapons").mkdir(parents=True)
        (PROJECT / "ModInformation.toml").write_bytes(b'name = "Entry Fixture"\n')
        self.write(MAPPED)

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def write(self, text: str, *, newline: str = "\n") -> None:
        """Write the fixture document with the given line ending."""
        body = text.replace("\n", newline)
        (PROJECT / DOCUMENT).write_bytes(body.encode("utf-8"))

    def text(self) -> str:
        """The fixture document as it stands."""
        return (PROJECT / DOCUMENT).read_bytes().decode("utf-8")

    def test_append_writes_a_new_entry(self) -> None:
        code, payload, _ = run_json("Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["after"], "ammo.type.1")
        body = self.text()
        self.assertEqual(body.count("[[weapon.ammo.type]]"), 2)
        self.assertIn('flavour = ""\n', body)
        self.assertIn('[weapon.shoot]\n', body)

    def test_append_copies_an_entry(self) -> None:
        code, _, _ = run_json(
            "Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "from=0", "--write", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.text().count('flavour = "FLAVOUR_HE"'), 2)

    def test_append_leaves_the_other_lines_alone(self) -> None:
        before = self.text().splitlines()
        self.assertEqual(
            run_json("Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "--write", cwd=PROJECT)[0], 0
        )
        after = self.text().splitlines()
        for row in before:
            self.assertIn(row, after)

    def test_delete_removes_one_entry(self) -> None:
        self.assertEqual(
            run_json("Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "from=0", "--write", cwd=PROJECT)[0], 0
        )
        code, _, _ = run_json("Mod", "set", DOCUMENT, "field=ammo.type.0", "op=delete", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        body = self.text()
        self.assertEqual(body.count("[[weapon.ammo.type]]"), 1)
        self.assertEqual(body.count('flavour = "FLAVOUR_HE"'), 1)

    def test_append_refuses_a_leaf(self) -> None:
        code, _, err = run("Mod", "set", DOCUMENT, "field=name", "op=append", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("is not an array of tables", err)
        self.assertEqual(self.text(), MAPPED)

    def test_delete_refuses_an_index_out_of_range(self) -> None:
        code, _, err = run("Mod", "set", DOCUMENT, "field=ammo.type.4", "op=delete", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("out of range", err)
        self.assertEqual(self.text(), MAPPED)

    def test_delete_refuses_a_path_without_an_index(self) -> None:
        code, _, err = run("Mod", "set", DOCUMENT, "field=ammo.type", "op=delete", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("name the entry to delete", err)

    def test_append_dry_run_writes_nothing(self) -> None:
        code, payload, _ = run_json(
            "Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "--write", "--dry-run", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(self.text(), MAPPED)
        self.assertFalse((PROJECT / "EditorCache").exists())

    def test_a_crlf_document_keeps_crlf(self) -> None:
        self.write(MAPPED, newline="\r\n")
        self.assertEqual(
            run_json("Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "--write", cwd=PROJECT)[0], 0
        )
        raw = (PROJECT / DOCUMENT).read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertEqual(raw.count(b"[[weapon.ammo.type]]\r\n"), 2)

    def test_get_reaches_an_indexed_field(self) -> None:
        code, payload, _ = run_json("Mod", "get", DOCUMENT, "field=ammo.type.0.name", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["values"][0]["path"], "ammo.type.0.name")
        self.assertEqual(payload["values"][0]["value"], '"HE"')

    def test_set_changes_a_field_of_an_added_entry(self) -> None:
        self.assertEqual(
            run_json("Mod", "set", DOCUMENT, "field=ammo.type", "op=append", "--write", cwd=PROJECT)[0], 0
        )
        code, _, _ = run_json(
            "Mod", "set", DOCUMENT, "field=ammo.type.1.name", "value=AP", "--write", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        _, payload, _ = run_json("Mod", "get", DOCUMENT, "field=ammo.type.1.name", cwd=PROJECT)
        self.assertEqual(payload["values"][0]["value"], '"AP"')


if __name__ == "__main__":
    unittest.main()
