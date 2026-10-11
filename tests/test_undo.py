"""End-to-end tests for the event log, ``log``, ``undo`` and ``redo``.

The fixture is a project with two documents and two sound files, so a revert can be checked
against the bytes on disk, across documents and across a segment boundary.  Every case asserts
what the log holds as well as what the disk holds, because the log is the only record of a
write and the baseline is the only copy of what it replaced (docs/project-layout.md section 8).
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from core import convert, journal, schema, toml, xml
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_undo"
PROJECT = SCRATCH / "project"
STOCK = SCRATCH / "stock"

SQUAD = PROJECT / "Mod" / "Data" / "Infantry" / "DEMO_SQUAD.toml"
WEAPON = PROJECT / "Mod" / "Data" / "Weapons" / "WEAPON_DEMO.txt"

SQUAD_XML = """<squad>
\t<description>
\t\t<type>TYPE_INFANTRY_SECTION</type>
\t\t<long_name>Demo Squad</long_name>
\t\t<quality>QUALITY_REGULAR</quality>
\t\t<nationality>NATIONALITY_GERMAN</nationality>
\t</description>
</squad>
"""

WEAPON_XML = """<weapon>
\t<name>Demo Rifle</name>
\t<type>WEAPON_RIFLE</type>
\t<shoot>
\t\t<rof>12</rof>
\t\t<sound_shoot>SOUND_RIFLE</sound_shoot>
\t</shoot>
</weapon>
"""

SEGMENT_START = 1000000.0

FIXTURES: dict[str, bytes] = {}


def toml_document(xml_text: str, root_tag: str) -> str:
    """The TOML a document is stored as, rendered the way the exporter renders it."""
    document = xml.parse(xml_text, "fixture")
    return toml.render(convert.xml_to_toml(document, schema.schema_for(root_tag)))


def run(*argv: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Invoke the CLI in-process; returns the exit code and both streams."""
    out, err = io.StringIO(), io.StringIO()
    previous = Path.cwd()
    try:
        if cwd is not None:
            os.chdir(cwd)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
    finally:
        os.chdir(previous)
    return code, out.getvalue(), err.getvalue()


def run_json(*argv: str, cwd: Path | None = None) -> tuple[int, dict, str]:
    """Invoke the CLI in-process with ``--json``; returns the parsed payload."""
    code, out, err = run(*argv, "--json", cwd=cwd)
    return code, (json.loads(out) if out.strip() else {}), err


def digest(path: Path) -> str:
    """The sha256 of a file as it stands."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(project: Path = PROJECT) -> list[dict]:
    """Every record of the project log, in append order."""
    return journal.read_events(project)


class UndoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        cls._env = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}
        FIXTURES["project/mod.toml"] = 'name = "Undo Fixture"\n'.encode("cp1252")
        FIXTURES["stock/Data/Weapons/WEAPON_STOCK.txt"] = WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
        FIXTURES["project/Mod/Data/Infantry/DEMO_SQUAD.toml"] = toml_document(SQUAD_XML, "squad").encode("cp1252")
        FIXTURES["project/Mod/Data/Weapons/WEAPON_DEMO.txt"] = WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
        FIXTURES["project/Mod/Sounds/SOUND_RIFLE.ogg"] = b"OggS\x00rifle\n"
        FIXTURES["project/Mod/Sounds/SOUND_CARBINE.ogg"] = b"OggS\x00carbine\n"
        cls.write_fixtures()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        for name, value in cls._env.items():
            if value is not None:
                os.environ[name] = value

    @classmethod
    def write_fixtures(cls) -> None:
        """Restore every fixture file and drop the editor state of the previous test."""
        for relative, data in FIXTURES.items():
            path = SCRATCH / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        shutil.rmtree(PROJECT / ".editor", ignore_errors=True)

    def setUp(self) -> None:
        self.write_fixtures()

    def set_field(self, document: str, field: str, value: str, *extra: str) -> dict:
        """One accepted ``set``, with the payload it printed."""
        code, payload, err = run_json("Mod", "set", document, f"field={field}", f"value={value}", "--write", *extra, cwd=PROJECT)
        self.assertEqual((code, err), (0, ""), payload)
        self.assertTrue(payload["written"])
        return payload

    # --- the log itself -----------------------------------------------------

    def test_b12_a_write_leaves_one_record_and_the_bytes_it_replaced(self) -> None:
        before = WEAPON.read_bytes()
        payload = self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Demo Rifle II")
        found = records()
        self.assertEqual(len(found), 1)
        event = found[0]
        self.assertEqual(
            sorted(event),
            sorted(
                {
                    "id", "segment", "timestamp", "actor", "result", "target", "document", "entity",
                    "field", "before", "after", "digest_before", "digest_after", "bytes_before",
                    "bytes_after", "dry_run",
                }
            ),
        )
        self.assertEqual(event["segment"], f"{Path(event['segment']).stem}.jsonl")
        self.assertEqual(Path(event["segment"]).stem, event["id"].split(":")[0])
        self.assertRegex(Path(event["segment"]).stem, r"^\d{8}T\d{6}$")
        self.assertEqual(event["id"], f"{Path(event['segment']).stem}:1")
        self.assertRegex(event["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertEqual(event["actor"], "cli")
        self.assertEqual(event["result"], "set")
        self.assertIsNone(event["target"])
        self.assertEqual(event["document"], "Mod/Data/Weapons/WEAPON_DEMO.txt")
        self.assertEqual(event["entity"], "Demo Rifle")
        self.assertEqual(event["field"], "name")
        self.assertEqual((event["before"], event["after"]), ("Demo Rifle", "Demo Rifle II"))
        self.assertEqual(event["digest_before"], hashlib.sha256(before).hexdigest())
        self.assertEqual(event["digest_after"], digest(WEAPON))
        self.assertEqual(event["bytes_before"], len(before))
        self.assertEqual(event["bytes_after"], WEAPON.stat().st_size)
        self.assertFalse(event["dry_run"])
        self.assertEqual(payload["event"], event["id"])
        blob = PROJECT / ".editor" / "baseline" / event["digest_before"]
        self.assertEqual(blob.read_bytes(), before)

    def test_a_dry_run_leaves_no_log_and_no_editor_state(self) -> None:
        code, _, err = run(
            "Mod", "set", "Data/Weapons/WEAPON_DEMO.txt", "field=name", "value=Nope", "--write", "--dry-run",
            cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertFalse((PROJECT / ".editor").exists())
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Demo Rifle II")
        code, out, err = run("Mod", "log", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("1 record(s)", out)

    def test_records_share_a_segment_until_it_goes_idle(self) -> None:
        with mock.patch.object(journal, "CLOCK", return_value=SEGMENT_START):
            self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        with mock.patch.object(journal, "CLOCK", return_value=SEGMENT_START + journal.SEGMENT_IDLE_SECONDS - 1):
            self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Second")
        with mock.patch.object(journal, "CLOCK", return_value=SEGMENT_START + 2 * journal.SEGMENT_IDLE_SECONDS):
            self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Third")
        found = records()
        self.assertEqual([event["id"].split(":")[1] for event in found], ["1", "2", "1"])
        self.assertEqual(len({event["segment"] for event in found}), 2)
        self.assertEqual(
            [Path(event["segment"]).stem for event in found],
            sorted(Path(event["segment"]).stem for event in found),
        )

    def test_log_lists_segments_and_records_and_writes_nothing(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        self.set_field("Data/Infantry/DEMO_SQUAD.toml", "description.quality", "QUALITY_ELITE")
        revision = {path: path.read_bytes() for path in PROJECT.rglob("*") if path.is_file()}
        code, payload, err = run_json("Mod", "log", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["shown"], 2)
        self.assertEqual(len(payload["segments"]), 1)
        self.assertEqual(payload["segments"][0]["records"], 2)
        self.assertEqual([event["result"] for event in payload["events"]], ["set", "set"])
        self.assertFalse(
            [path for path in PROJECT.rglob("*") if path.is_file() and path.read_bytes() != revision.get(path)],
            "log changed a file",
        )
        code, payload, err = run_json("Mod", "log", "1", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((payload["total"], payload["shown"]), (2, 1))
        self.assertEqual(payload["events"][0]["document"], "Mod/Data/Infantry/DEMO_SQUAD.toml")

    def test_log_reads_a_project_without_a_log(self) -> None:
        code, out, err = run("Mod", "log", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("0 record(s)", out)
        self.assertFalse((PROJECT / ".editor").exists())

    # --- undo and redo ------------------------------------------------------

    def test_b13_undo_restores_the_pre_edit_bytes(self) -> None:
        before = WEAPON.read_bytes()
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Demo Rifle II")
        code, payload, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["result"], "undo")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(WEAPON.read_bytes(), before)
        self.assertEqual(payload["documents"][0]["before"], "Demo Rifle II")
        self.assertEqual(payload["documents"][0]["after"], "Demo Rifle")
        found = records()
        self.assertEqual([event["result"] for event in found], ["set", "undo"])
        self.assertEqual(found[-1]["target"], found[0]["id"])
        self.assertEqual(found[-1]["id"], f"{found[0]['segment'].split('.')[0]}:2")
        self.assertFalse((PROJECT / ".editor" / "lock").exists())

    def test_b14_undo_redo_undo_is_byte_identical(self) -> None:
        start = WEAPON.read_bytes()
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Demo Rifle II")
        edited = WEAPON.read_bytes()
        self.assertNotEqual(edited, start)
        for step, expected in (("undo", start), ("redo", edited), ("undo", start)):
            code, payload, err = run_json("Mod", step, "1", "--write", cwd=PROJECT)
            self.assertEqual((code, err), (0, ""), payload)
            self.assertEqual(WEAPON.read_bytes(), expected, step)
        self.assertEqual([event["result"] for event in records()], ["set", "undo", "redo", "undo"])

    def test_undo_across_a_segment_boundary_reverts_newest_first(self) -> None:
        squad_before = SQUAD.read_bytes()
        weapon_before = WEAPON.read_bytes()
        with mock.patch.object(journal, "CLOCK", return_value=SEGMENT_START):
            self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
            self.set_field("Data/Infantry/DEMO_SQUAD.toml", "description.quality", "QUALITY_ELITE")
        with mock.patch.object(journal, "CLOCK", return_value=SEGMENT_START + 10 * journal.SEGMENT_IDLE_SECONDS):
            code, payload, err = run_json("Mod", "undo", "2", "--write", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["targets"], [event["id"] for event in records()[:2]][::-1])
        self.assertEqual(WEAPON.read_bytes(), weapon_before)
        self.assertEqual(SQUAD.read_bytes(), squad_before)
        found = records()
        self.assertEqual([event["result"] for event in found], ["set", "set", "undo", "undo"])
        first, second = found[2], found[3]
        self.assertEqual(first["target"], found[1]["id"])
        self.assertEqual(second["target"], found[0]["id"])
        self.assertEqual(first["segment"], second["segment"])
        self.assertNotEqual(first["segment"], found[0]["segment"])
        self.assertEqual([event["field"] for event in (first, second)], ["description.quality", "name"])

    def test_undo_touches_only_the_document_of_the_change(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        squad = SQUAD.read_bytes()
        self.set_field("Data/Infantry/DEMO_SQUAD.toml", "description.quality", "QUALITY_ELITE")
        code, payload, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["documents"][0]["document"], "Mod/Data/Infantry/DEMO_SQUAD.toml")
        self.assertEqual(SQUAD.read_bytes(), squad)
        self.assertIn(b"First", WEAPON.read_bytes())

    def test_a_new_change_discards_what_could_be_redone(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        code, _, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual((code, err), (0, ""))
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "Second")
        code, _, err = run_json("Mod", "redo", "1", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("no change to redo", err)

    # --- refusals -----------------------------------------------------------

    def test_b16_editing_a_reference_field_keeps_check_clean(self) -> None:
        code, before, _ = run_json("Mod", "check", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(before["dangling"], [])
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "shoot.sound_shoot", "SOUND_CARBINE")
        code, after, _ = run_json("Mod", "check", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(after["dangling"], [])
        self.assertEqual(after["errors"], [])
        code, payload, _ = run_json("Mod", "deps", "value=SOUND_CARBINE", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)

    def test_undo_without_write_is_refused(self) -> None:
        before = WEAPON.read_bytes()
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        edited = WEAPON.read_bytes()
        code, out, err = run("Mod", "undo", "1", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("undo needs --write", err)
        self.assertEqual(WEAPON.read_bytes(), edited)
        self.assertEqual([event["result"] for event in records()], ["set"])
        self.assertNotEqual(before, edited)

    def test_redo_without_write_is_refused(self) -> None:
        code, _, err = run("Mod", "redo", "1", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("redo needs --write", err)
        self.assertFalse((PROJECT / ".editor").exists())

    def test_the_stock_scope_is_never_reverted(self) -> None:
        before = (STOCK / "Data" / "Weapons" / "WEAPON_STOCK.txt").read_bytes()
        code, _, err = run("Firefight", "undo", "1", "--write", f"root={STOCK}")
        self.assertEqual(code, 2)
        self.assertIn("read-only", err)
        self.assertEqual((STOCK / "Data" / "Weapons" / "WEAPON_STOCK.txt").read_bytes(), before)
        self.assertFalse((STOCK / ".editor").exists())

    def test_an_empty_log_refuses_undo(self) -> None:
        code, _, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("no change to undo", err)
        self.assertFalse((PROJECT / ".editor").exists())

    def test_a_count_beyond_the_log_is_refused_without_writing(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        edited = WEAPON.read_bytes()
        code, _, err = run_json("Mod", "undo", "2", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("only 1 change(s) can be undone", err)
        self.assertEqual(WEAPON.read_bytes(), edited)
        self.assertEqual(len(records()), 1)

    def test_a_count_that_is_not_a_number_is_refused(self) -> None:
        for command in ("undo", "redo", "log"):
            code, _, err = run("Mod", command, "all", "--write", cwd=PROJECT)
            self.assertEqual(code, 2, command)
            self.assertIn("takes a count of at least 1", err)
        self.assertFalse((PROJECT / ".editor").exists())

    def test_a_document_changed_by_hand_is_not_reverted(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        WEAPON.write_bytes(WEAPON.read_bytes().replace(b"First", b"Theirs"))
        code, _, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("changed after that change", err)
        self.assertIn(b"Theirs", WEAPON.read_bytes())
        self.assertEqual([event["result"] for event in records()], ["set"])

    def test_a_missing_baseline_fails_without_writing(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        event = records()[0]
        (PROJECT / ".editor" / "baseline" / event["digest_before"]).unlink()
        edited = WEAPON.read_bytes()
        code, _, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual(code, 1)
        self.assertIn("recorded bytes of this change are missing", err)
        self.assertEqual(WEAPON.read_bytes(), edited)
        self.assertEqual(len(records()), 1)

    def test_a_held_lock_refuses_a_revert(self) -> None:
        self.set_field("Data/Weapons/WEAPON_DEMO.txt", "name", "First")
        edited = WEAPON.read_bytes()
        (PROJECT / ".editor" / "lock").write_text(json.dumps({"pid": 4321}), encoding="utf-8")
        code, _, err = run_json("Mod", "undo", "1", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn(".editor/lock is held", err)
        self.assertIn("pid=4321", err)
        self.assertEqual(WEAPON.read_bytes(), edited)
        self.assertEqual(len(records()), 1)


class StacksTest(unittest.TestCase):
    """The replay that decides what can be undone and redone."""

    def events(self, *spec) -> list[dict]:
        """Events from ``(id, result, target)`` triples."""
        return [
            {"id": name, "result": result, "target": target} for name, result, target in spec
        ]

    def test_a_set_applies_and_an_undo_takes_it_off(self) -> None:
        applied, undone = journal.stacks(self.events(("a", "set", None), ("b", "undo", "a")))
        self.assertEqual([event["id"] for event in applied], [])
        self.assertEqual([event["id"] for event in undone], ["a"])

    def test_a_redo_puts_it_back(self) -> None:
        applied, undone = journal.stacks(
            self.events(("a", "set", None), ("b", "undo", "a"), ("c", "redo", "a"))
        )
        self.assertEqual([event["id"] for event in applied], ["a"])
        self.assertEqual([event["id"] for event in undone], [])

    def test_a_new_set_clears_what_was_reverted(self) -> None:
        applied, undone = journal.stacks(
            self.events(("a", "set", None), ("b", "undo", "a"), ("c", "set", None))
        )
        self.assertEqual([event["id"] for event in applied], ["c"])
        self.assertEqual([event["id"] for event in undone], [])

    def test_two_documents_keep_their_order(self) -> None:
        applied, _ = journal.stacks(self.events(("a", "set", None), ("b", "set", None)))
        self.assertEqual([event["id"] for event in applied], ["a", "b"])
