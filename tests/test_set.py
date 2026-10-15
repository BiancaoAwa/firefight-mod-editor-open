"""End-to-end tests for ``set``: one field of one document, every other byte kept.

The fixture is a small project (``ModInformation.toml`` plus documents under ``Data``) so the write
path, the refusal paths and the project lock are exercised without the retail corpus.  Text
and binary comparisons are byte-level, because the promise of a write is that the bytes
outside the edited field do not move (docs/cli.md section 4).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core import convert, edit, schema, toml, xml
from core.cli.commands import load_document
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_set"
PROJECT = SCRATCH / "project"
MANY = SCRATCH / "many"
STOCK = SCRATCH / "stock"

SQUAD = PROJECT / "Data" / "Infantry" / "DEMO_SQUAD.toml"
WEAPON = PROJECT / "Data" / "Weapons" / "WEAPON_DEMO.txt"
WEAPON_LF = PROJECT / "Data" / "Weapons" / "WEAPON_LF.txt"
SQUAD_UTF8 = PROJECT / "Data" / "Infantry" / "DEMO_UTF8.toml"
STOCK_WEAPON = STOCK / "Data" / "Weapons" / "WEAPON_STOCK.txt"

SQUAD_XML = """<squad>
\t<description>
\t\t<type>TYPE_INFANTRY_SECTION</type>
\t\t<long_name>Demo Squad</long_name>
\t\t<quality>QUALITY_REGULAR</quality>
\t\t<nationality>NATIONALITY_GERMAN</nationality>
\t</description>
\t<availability>
\t\t<data>
\t\t\t<year>1940</year>
\t\t\t<month>5</month>
\t\t\t<number>12</number>
\t\t</data>
\t\t<data>
\t\t\t<year>1944</year>
\t\t\t<month>6</month>
\t\t\t<number>3</number>
\t\t</data>
\t</availability>
\t<vehicle>
\t\t<attributes>
\t\t\t<is_amphibious>no</is_amphibious>
\t\t\t<weight>20000</weight>
\t\t</attributes>
\t</vehicle>
\t<man>
\t\t<job>JOB_SQUAD_LEADER</job>
\t</man>
</squad>
"""

UTF8_SQUAD_XML = SQUAD_XML.replace("<long_name>Demo Squad</long_name>", "<long_name>Ünïque Sqwad</long_name>")

WEAPON_XML = """<weapon>
\t<name>Demo Rifle</name>
\t<type>WEAPON_RIFLE</type>
\t<comments>Büchse</comments>
\t<shoot>
\t\t<rof>12</rof>
\t\t<muzzle_flash>no</muzzle_flash>
\t\t<sound_shoot>SOUND_RIFLE</sound_shoot>
\t</shoot>
\t<magazine>
\t\t<capacity>5</capacity>
\t\t<single_shot>yes</single_shot>
\t\t<sound_eject_clip/>
\t</magazine>
\t<ammo>
\t\t<type>
\t\t\t<flavour>FLAVOUR_HE // high explosive</flavour>
\t\t</type>
\t</ammo>
</weapon>
"""

MANY_XML = """<weapon>
\t<name>Scale Rifle</name>
\t<type>WEAPON_RIFLE</type>
</weapon>
"""

MANY_COUNT = 59

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


def changed_lines(before: bytes, after: bytes) -> list[tuple[bytes, bytes]]:
    """The lines that differ between two byte strings; the line count must not move."""
    old = before.split(b"\n")
    new = after.split(b"\n")
    if len(old) != len(new):
        raise AssertionError(f"line count changed: {len(old)} -> {len(new)}")
    return [(left, right) for left, right in zip(old, new) if left != right]


def many_target() -> Path:
    """The file the scale test edits."""
    return MANY / "Data" / "Weapons" / "WEAPON_00.toml"


class SetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        cls._env = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}
        FIXTURES.clear()
        FIXTURES["project/ModInformation.toml"] = 'name = "Set Fixture"\n'.encode("cp1252")
        FIXTURES["many/ModInformation.toml"] = 'name = "Scale Fixture"\n'.encode("cp1252")
        FIXTURES["stock/Data/Weapons/WEAPON_STOCK.txt"] = WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
        FIXTURES["project/Sounds/SOUND_RIFLE.ogg"] = b"OggS\x00fixture\n"

        squad = "# Demo squad\n\n" + toml_document(SQUAD_XML, "squad")
        marked = squad.replace('quality = "QUALITY_REGULAR"', 'quality = "QUALITY_REGULAR"  # tier')
        if marked == squad:
            raise AssertionError("fixture text is missing the quality assignment")
        FIXTURES["project/Data/Infantry/DEMO_SQUAD.toml"] = marked.encode("cp1252")
        FIXTURES["project/Data/Infantry/DEMO_UTF8.toml"] = toml_document(UTF8_SQUAD_XML, "squad").encode("utf-8")
        FIXTURES["project/Data/Weapons/WEAPON_DEMO.txt"] = WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
        FIXTURES["project/Data/Weapons/WEAPON_LF.txt"] = WEAPON_XML.encode("cp1252")
        many = toml_document(MANY_XML, "weapon").encode("cp1252")
        for index in range(MANY_COUNT):
            FIXTURES[f"many/Data/Weapons/WEAPON_{index:02d}.toml"] = many
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
        shutil.rmtree(PROJECT / "EditorCache", ignore_errors=True)
        shutil.rmtree(MANY / "EditorCache", ignore_errors=True)

    def setUp(self) -> None:
        self.write_fixtures()

    def assert_no_editor_state(self, project: Path) -> None:
        self.assertFalse((project / "EditorCache").exists(), f"{project.name}/EditorCache was created")

    # --- accepted writes ----------------------------------------------------

    def test_b1_only_the_target_field_changes(self) -> None:
        before = SQUAD.read_bytes()
        code, payload, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.quality", "value=QUALITY_ELITE",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(payload["written"])
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["field"], "description.quality")
        self.assertEqual(payload["before"], "QUALITY_REGULAR")
        self.assertEqual(payload["after"], "QUALITY_ELITE")
        self.assertEqual(payload["encoding"], "cp1252")
        self.assertEqual(payload["newline"], "lf")
        self.assertEqual(payload["bytes_before"], len(before))
        self.assertEqual(payload["enum"], {"category": "quality", "table": True, "values": 6, "source": "enums_ext.txt"})
        after = SQUAD.read_bytes()
        self.assertEqual(payload["bytes_after"], len(after))
        changed = changed_lines(before, after)
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b'quality = "QUALITY_ELITE"  # tier')

    def test_b2_the_project_still_checks_clean(self) -> None:
        code, before, _ = run_json("Mod", "check", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(before["errors"], [])
        self.assertEqual(before["dangling"], [])
        code, payload, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.quality", "value=QUALITY_ELITE",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        after_code, after, _ = run_json("Mod", "check", cwd=PROJECT)
        self.assertEqual(after_code, 0)
        self.assertEqual(len(after["errors"]), len(before["errors"]))
        self.assertEqual(len(after["dangling"]), len(before["dangling"]))
        self.assertEqual(after["loaded"], before["loaded"])

    def test_b4_a_number_keeps_the_document_style(self) -> None:
        before = SQUAD.read_bytes()
        code, payload, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=availability.data.0.year", "value=1941",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["before"], "1940")
        self.assertEqual(payload["enum"], {"category": None, "table": False, "source": "enums_ext.txt"})
        changed = changed_lines(before, SQUAD.read_bytes())
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b"year = 1941")

    def test_b5_a_boolean_keeps_the_document_style(self) -> None:
        before = SQUAD.read_bytes()
        code, _, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=vehicle.attributes.is_amphibious", "value=yes",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        changed = changed_lines(before, SQUAD.read_bytes())
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b"is_amphibious = true")

    def test_b6_a_cp1252_document_keeps_its_other_bytes(self) -> None:
        before = WEAPON.read_bytes()
        self.assertIn("Büchse".encode("cp1252"), before)
        code, payload, err = run_json(
            "Mod", "set", "Data/Weapons/WEAPON_DEMO.txt", "field=name", "value=Demo Rifle II",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["encoding"], "cp1252")
        self.assertEqual(payload["newline"], "crlf")
        after = WEAPON.read_bytes()
        self.assertIn("Büchse".encode("cp1252"), after)
        changed = changed_lines(before, after)
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b"\t<name>Demo Rifle II</name>\r")
        self.assertNotIn(b"\n", after.replace(b"\r\n", b""))

    def test_b7_a_utf8_document_stays_utf8(self) -> None:
        before = SQUAD_UTF8.read_bytes()
        self.assertFalse(before.startswith(b"\xef\xbb\xbf"))
        code, payload, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_UTF8.toml", "field=description.nationality", "value=NATIONALITY_FRENCH",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["encoding"], "utf-8")
        after = SQUAD_UTF8.read_bytes()
        self.assertFalse(after.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Ünïque Sqwad".encode("utf-8"), after)
        changed = changed_lines(before, after)
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b'nationality = "NATIONALITY_FRENCH"')

    def test_b8_a_line_feed_document_stays_line_feed(self) -> None:
        before = WEAPON_LF.read_bytes()
        self.assertNotIn(b"\r", before)
        code, payload, err = run_json(
            "Mod", "set", "Data/Weapons/WEAPON_LF.txt", "field=shoot.rof", "value=15",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["newline"], "lf")
        after = WEAPON_LF.read_bytes()
        self.assertNotIn(b"\r", after)
        changed = changed_lines(before, after)
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b"\t\t<rof>15</rof>")

    def test_b9_comments_and_free_text_survive(self) -> None:
        before = SQUAD.read_bytes()
        code, _, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.nationality", "value=NATIONALITY_ITALIAN",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        after = SQUAD.read_bytes()
        self.assertTrue(after.startswith(b"# Demo squad\n\n"))
        self.assertIn(b"# tier", after)
        changed = changed_lines(before, after)
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b'nationality = "NATIONALITY_ITALIAN"')

        before = WEAPON.read_bytes()
        code, _, err = run_json(
            "Mod", "set", "Data/Weapons/WEAPON_DEMO.txt", "field=ammo.type.0.flavour", "value=FLAVOUR_AP",
            "--write", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        changed = changed_lines(before, WEAPON.read_bytes())
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b"\t\t\t<flavour>FLAVOUR_AP // high explosive</flavour>\r")

    def test_b11_a_dry_run_writes_nothing(self) -> None:
        before = SQUAD.read_bytes()
        stat = SQUAD.stat()
        code, payload, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.quality", "value=QUALITY_ELITE",
            "--write", "--dry-run", cwd=PROJECT,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["written"])
        self.assertEqual(SQUAD.read_bytes(), before)
        self.assertEqual(SQUAD.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assert_no_editor_state(PROJECT)

    def test_the_usage_lists_set(self) -> None:
        code, out, _ = run("help")
        self.assertEqual(code, 0)
        self.assertIn("set", out)
        self.assertIn("--write", out)

    # --- refusals -----------------------------------------------------------

    def test_b3_an_unknown_enum_value_is_refused_in_place(self) -> None:
        before = SQUAD.read_bytes()
        code, out, err = run(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.quality", "value=QUALITY_BOGUS",
            "--write", cwd=PROJECT,
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("'QUALITY_BOGUS' is not one of the quality values", err)
        self.assertEqual(SQUAD.read_bytes(), before)
        self.assert_no_editor_state(PROJECT)

    def test_b10_a_value_the_encoding_cannot_hold_is_refused(self) -> None:
        before = WEAPON.read_bytes()
        code, out, err = run(
            "Mod", "set", "Data/Weapons/WEAPON_DEMO.txt", "field=name", "value=日本語",
            "--write", cwd=PROJECT,
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("cp1252", err)
        self.assertEqual(WEAPON.read_bytes(), before)
        self.assert_no_editor_state(PROJECT)

    def test_b19_a_write_without_the_flag_is_refused(self) -> None:
        before = SQUAD.read_bytes()
        for extra in ((), ("--dry-run",)):
            code, out, err = run(
                "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.quality", "value=QUALITY_ELITE",
                *extra, cwd=PROJECT,
            )
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("set needs --write", err)
        self.assertEqual(SQUAD.read_bytes(), before)
        self.assert_no_editor_state(PROJECT)

    def test_b19_the_stock_scope_is_never_written(self) -> None:
        before = STOCK_WEAPON.read_bytes()
        code, out, err = run(
            "Firefight", "set", "Data/Weapons/WEAPON_STOCK.txt", "field=name", "value=Nope", "--write",
            f"root={STOCK}",
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("read-only", err)
        self.assertEqual(STOCK_WEAPON.read_bytes(), before)
        self.assert_no_editor_state(STOCK)

    def test_b17_a_held_lock_refuses_the_second_writer(self) -> None:
        editor = PROJECT / "EditorCache"
        editor.mkdir(parents=True, exist_ok=True)
        lock = editor / "lock"
        lock.write_text(json.dumps({"pid": 4321, "started": "2026-10-11T10:00:00+0800"}), encoding="utf-8")
        before = SQUAD.read_bytes()
        code, out, err = run_json(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.quality", "value=QUALITY_ELITE",
            "--write", cwd=PROJECT,
        )
        self.assertEqual(code, 2)
        self.assertIn("EditorCache/lock is held", err)
        self.assertIn("pid=4321", err)
        self.assertEqual(SQUAD.read_bytes(), before)
        self.assertTrue(lock.exists(), "the lock of the holder was removed")

    def test_b18_a_document_changed_after_staging_is_not_overwritten(self) -> None:
        document = load_document(SQUAD)
        plan = edit.plan_set(document, "description.quality", "QUALITY_ELITE")
        self.assertEqual(plan.before, "QUALITY_REGULAR")
        SQUAD.write_bytes(SQUAD.read_bytes() + b"# someone else was here\n")
        with self.assertRaises(edit.EditRefused) as raised:
            edit.apply_plan(plan, PROJECT)
        self.assertIn("changed after the change was staged", str(raised.exception))
        self.assertTrue(SQUAD.read_bytes().endswith(b"# someone else was here\n"))
        self.assertFalse((PROJECT / "EditorCache" / "lock").exists())

    def test_an_unknown_field_is_refused(self) -> None:
        code, _, err = run(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=description.nickname", "value=X", "--write",
            cwd=PROJECT,
        )
        self.assertEqual(code, 2)
        self.assertIn("not declared by the schema", err)

    def test_a_missing_index_is_refused(self) -> None:
        code, _, err = run(
            "Mod", "set", "Data/Infantry/DEMO_SQUAD.toml", "field=availability.data.year", "value=1941", "--write",
            cwd=PROJECT,
        )
        self.assertEqual(code, 2)
        self.assertIn("add an index", err)

    # --- scale --------------------------------------------------------------

    def test_b20_only_the_target_of_many_files_changes(self) -> None:
        files = sorted((MANY / "Data" / "Weapons").glob("*.toml"))
        self.assertEqual(len(files), MANY_COUNT)
        before = {path: path.read_bytes() for path in files}
        self.assertEqual(len(before), MANY_COUNT)
        code, payload, err = run_json(
            "Mod", "set", "Data/Weapons/WEAPON_00.toml", "field=type", "value=WEAPON_CARBINE", "--write",
            cwd=MANY,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(payload["written"])
        moved = []
        for path, data in before.items():
            if path.read_bytes() != data:
                moved.append(path.name)
        self.assertEqual(moved, ["WEAPON_00.toml"])
        changed = changed_lines(before[many_target()], many_target().read_bytes())
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1], b'type = "WEAPON_CARBINE"')
        _, after, _ = run_json("Mod", "check", cwd=MANY)
        self.assertEqual(after["errors"], [])
        self.assertEqual(after["dangling"], [])


if __name__ == "__main__":
    unittest.main()
