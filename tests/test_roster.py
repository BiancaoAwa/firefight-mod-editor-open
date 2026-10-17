"""Tests for the plain-text rosters and the ``roster`` command.

A roster is one entry per line, the entry names a document under ``Data/``, and ``//`` starts a
comment -- the whole line, or a note trailing the entry.  Which files are rosters comes from the
project's own settings, so the fixture declares one in ``mod.txt``.  The two directions of the
check matter: an entry no document answers is a hole the game shows as a missing unit, and a unit
no roster names is a document the game cannot reach (docs/cli.md section 4.14).
"""

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path

from core import roster
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_roster"
PROJECT = SCRATCH / "project"

MOD_TXT = """<mod>
\t<name>Demo Mod</name>
\t<nationality>
\t\t<name>NATION_AMERICAN</name>
\t\t<equipment>equipment_american.txt</equipment>
\t</nationality>
</mod>
"""

SQUAD_XML = """<squad>
\t<name>Demo Squad</name>
</squad>
"""

WEAPON_XML = """<weapon>
\t<name>Demo Rifle</name>
\t<type>WEAPON_RIFLE</type>
</weapon>
"""

MOD_INFO = """[mod]
\tname = "Demo Mod"
\tversion_name = "0.0.1"
"""

# One comment line that names the group, one entry with a note, one entry no document answers.
ROSTER = "// units\nDEMO_SQUAD_A\t\t// riflemen\nDEMO_SQUAD_MISSING\n"


def write_fixtures() -> None:
    """Rebuild the project from scratch."""
    shutil.rmtree(SCRATCH, ignore_errors=True)
    (PROJECT / "Data" / "Infantry").mkdir(parents=True)
    (PROJECT / "Data" / "Weapons").mkdir(parents=True)
    (PROJECT / "mod.txt").write_text(MOD_TXT, encoding="utf-8", newline="")
    (PROJECT / "ModInformation.toml").write_text(MOD_INFO, encoding="utf-8", newline="")
    for name in ("DEMO_SQUAD_A", "DEMO_SQUAD_B"):
        (PROJECT / "Data" / "Infantry" / f"{name}.txt").write_bytes(
            SQUAD_XML.replace("\n", "\r\n").encode("cp1252")
        )
    (PROJECT / "Data" / "Weapons" / "WEAPON_DEMO.txt").write_bytes(
        WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
    )
    (PROJECT / "Data" / "equipment_american.txt").write_bytes(
        ROSTER.replace("\n", "\r\n").encode("cp1252")
    )


def run(*argv: str) -> tuple[int, str, str]:
    """Invoke the CLI in-process; returns the exit code and both streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def run_json(*argv: str) -> tuple[int, dict, str]:
    """Invoke the CLI in-process with ``--json``; returns the parsed payload."""
    code, out, err = run(*argv, "--json")
    return code, (json.loads(out) if out.strip() else {}), err


def root() -> str:
    return f"root={PROJECT}"


class RosterParseTest(unittest.TestCase):
    """The reader on its own, without a project."""

    def test_a_line_carries_its_number_its_entry_and_its_group(self) -> None:
        rows = roster.parse(ROSTER)
        self.assertEqual([row["line"] for row in rows], [1, 2, 3])
        self.assertEqual(rows[0]["group"], "units")
        self.assertTrue(rows[0]["blank"])
        self.assertEqual(rows[1]["value"], "DEMO_SQUAD_A")
        self.assertEqual(rows[1]["group"], "units")
        self.assertEqual(rows[1]["note"], "riflemen")

    def test_a_note_after_an_entry_is_kept_apart_from_the_group(self) -> None:
        rows = roster.parse(ROSTER)
        self.assertEqual(rows[2]["note"], "")
        self.assertEqual(rows[2]["group"], "units")

    def test_a_blank_line_has_no_entry(self) -> None:
        rows = roster.parse("DEMO_SQUAD_A\n\nDEMO_SQUAD_B\n")
        self.assertEqual([bool(row["blank"]) for row in rows], [False, True, False])

    def test_line_of_finds_an_entry_and_zero_when_it_is_absent(self) -> None:
        rows = roster.parse(ROSTER)
        self.assertEqual(roster.line_of(rows, "DEMO_SQUAD_A"), 2)
        self.assertEqual(roster.line_of(rows, "DEMO_SQUAD_Z"), 0)

    def test_gaps_reports_both_directions(self) -> None:
        listed = {"equipment_american.txt": roster.names(roster.parse(ROSTER))}
        found = roster.gaps(listed, {"DEMO_SQUAD_A": "Data/Infantry/DEMO_SQUAD_A.txt",
                                     "DEMO_SQUAD_B": "Data/Infantry/DEMO_SQUAD_B.txt"})
        self.assertEqual(found["missing"], [{"roster": "equipment_american.txt", "name": "DEMO_SQUAD_MISSING"}])
        self.assertEqual([item["name"] for item in found["orphans"]], ["DEMO_SQUAD_B"])


class RosterCommandTest(unittest.TestCase):
    """The command against a project that declares one roster."""

    @classmethod
    def setUpClass(cls) -> None:
        write_fixtures()

    def setUp(self) -> None:
        # The write tests change the roster, so every test starts from the same file.
        write_fixtures()

    def test_the_command_lists_the_declared_rosters(self) -> None:
        code, payload, _ = run_json("Mod", "roster", root())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["files"], [{"path": "Data/equipment_american.txt", "entries": 2}])

    def test_the_command_lists_the_entries_of_one_roster(self) -> None:
        code, payload, _ = run_json("Mod", "roster", "equipment_american.txt", root())
        self.assertEqual(code, 0)
        self.assertEqual(payload["names"], ["DEMO_SQUAD_A", "DEMO_SQUAD_MISSING"])
        self.assertEqual([row["line"] for row in payload["lines"]], [2, 3])
        self.assertEqual(payload["lines"][0]["group"], "units")

    def test_a_section_keeps_the_group_and_the_note(self) -> None:
        _, by_group, _ = run_json("Mod", "roster", "equipment_american.txt", root(), "section=units")
        self.assertEqual(by_group["names"], ["DEMO_SQUAD_A", "DEMO_SQUAD_MISSING"])
        _, by_note, _ = run_json("Mod", "roster", "equipment_american.txt", root(), "section=riflemen")
        self.assertEqual(by_note["names"], ["DEMO_SQUAD_A"])
        _, nothing, _ = run_json("Mod", "roster", "equipment_american.txt", root(), "section=tanks")
        self.assertEqual(nothing["names"], [])

    def test_check_reports_an_entry_with_no_document(self) -> None:
        code, payload, _ = run_json("Mod", "roster", "check", root())
        self.assertEqual(code, 1)
        self.assertEqual(payload["missing_total"], 1)
        self.assertEqual(payload["missing"][0]["name"], "DEMO_SQUAD_MISSING")
        self.assertFalse(payload["ok"])

    def test_check_reports_a_unit_no_roster_names(self) -> None:
        _, payload, _ = run_json("Mod", "roster", "check", root())
        self.assertEqual([item["name"] for item in payload["orphans"]], ["DEMO_SQUAD_B"])
        self.assertEqual(payload["orphans"][0]["path"], "Data/Infantry/DEMO_SQUAD_B.txt")

    def test_check_ignores_a_weapon(self) -> None:
        _, payload, _ = run_json("Mod", "roster", "check", root(), "limit=0")
        self.assertNotIn("WEAPON_DEMO", [item["name"] for item in payload["orphans"]])

    def test_an_entry_can_be_appended(self) -> None:
        code, payload, _ = run_json(
            "Mod", "roster", "equipment_american.txt", root(),
            "op=add", "value=DEMO_SQUAD_B", "--write",
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["line"], 4)
        self.assertTrue(payload["recorded"])
        _, after, _ = run_json("Mod", "roster", "equipment_american.txt", root())
        self.assertIn("DEMO_SQUAD_B", after["names"])

    def test_an_entry_can_be_rewritten_and_keeps_its_note(self) -> None:
        text = (PROJECT / "Data" / "equipment_american.txt").read_text(encoding="cp1252")
        self.assertIn("DEMO_SQUAD_A\t\t// riflemen", text)
        code, payload, _ = run_json(
            "Mod", "roster", "equipment_american.txt", root(),
            "op=set", "line=2", "as=DEMO_SQUAD_C", "--write",
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["before"], "DEMO_SQUAD_A")
        self.assertEqual(payload["after"], "DEMO_SQUAD_C")
        rewritten = (PROJECT / "Data" / "equipment_american.txt").read_text(encoding="cp1252")
        self.assertIn("DEMO_SQUAD_C\t\t// riflemen", rewritten)
        self.assertNotIn("DEMO_SQUAD_A\t", rewritten)

    def test_an_entry_can_be_removed(self) -> None:
        code, payload, _ = run_json(
            "Mod", "roster", "equipment_american.txt", root(),
            "op=remove", "value=DEMO_SQUAD_MISSING", "--write",
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["line"], 3)
        _, after, _ = run_json("Mod", "roster", "equipment_american.txt", root())
        self.assertNotIn("DEMO_SQUAD_MISSING", after["names"])

    def test_a_write_is_undone_by_undo(self) -> None:
        before = (PROJECT / "Data" / "equipment_american.txt").read_bytes()
        run_json(
            "Mod", "roster", "equipment_american.txt", root(),
            "op=add", "value=DEMO_SQUAD_C", "--write",
        )
        self.assertNotEqual((PROJECT / "Data" / "equipment_american.txt").read_bytes(), before)
        code, _, _ = run_json("Mod", "undo", "count=1", root(), "--write")
        self.assertEqual(code, 0)
        self.assertEqual((PROJECT / "Data" / "equipment_american.txt").read_bytes(), before)

    def test_a_dry_run_writes_nothing(self) -> None:
        before = (PROJECT / "Data" / "equipment_american.txt").read_bytes()
        code, payload, _ = run_json(
            "Mod", "roster", "equipment_american.txt", root(),
            "op=add", "value=DEMO_SQUAD_D", "--write", "--dry-run",
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual((PROJECT / "Data" / "equipment_american.txt").read_bytes(), before)

    def test_the_command_needs_write(self) -> None:
        code, _, err = run("Mod", "roster", "equipment_american.txt", root(), "op=add", "value=X")
        self.assertEqual(code, 2)
        self.assertIn("needs --write", err)

    def test_the_command_refuses_a_file_it_does_not_declare(self) -> None:
        code, _, err = run("Mod", "roster", "Data/Infantry/DEMO_SQUAD_A.txt", root())
        self.assertEqual(code, 2)
        self.assertIn("no declared roster named", err)

    def test_a_rewrite_needs_the_new_name(self) -> None:
        code, _, err = run(
            "Mod", "roster", "equipment_american.txt", root(), "op=set", "line=2", "--write"
        )
        self.assertEqual(code, 2)
        self.assertIn("as=<the new document name>", err)


if __name__ == "__main__":
    unittest.main()
