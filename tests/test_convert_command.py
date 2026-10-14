"""Tests for the ``convert`` command: stock source files become project working files.

The fixture is a small stock-shaped scope (XML ``.txt`` under ``Data/``) plus a destination
directory, so the conversion, the skip and overwrite rules, the dry run and the failure path
are exercised without the retail corpus.  The output is checked byte-wise, because the promise
is a working ``.toml`` the project can edit (UTF-8 without BOM, CRLF, non-ASCII kept).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core.cli.commands import flatten, load_document
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_convert_cmd"
STOCK = SCRATCH / "stock"
BROKEN = SCRATCH / "broken"
OUT = SCRATCH / "out"

WEAPON_XML = """<weapon>
\t<name>Demo Rifle</name>
\t<type>WEAPON_RIFLE</type>
\t<comments>Büchse</comments>
\t<shoot>
\t\t<rof>12</rof>
\t</shoot>
</weapon>
"""

SQUAD_XML = """<squad>
\t<description>
\t\t<type>TYPE_INFANTRY_SECTION</type>
\t\t<long_name>Demo Squad</long_name>
\t\t<quality>QUALITY_REGULAR</quality>
\t</description>
</squad>
"""

FIXTURES: dict[str, bytes] = {}


def build_fixtures() -> dict[str, bytes]:
    """The stock-shaped source trees, as the bytes they are written from."""
    return {
        "stock/Data/Weapons/WEAPON_A.txt": WEAPON_XML.replace("\n", "\r\n").encode("cp1252"),
        "stock/Data/Weapons/WEAPON_B.txt": WEAPON_XML.replace("Demo Rifle", "Demo Carbine").replace("\n", "\r\n").encode("cp1252"),
        "stock/Data/Infantry/SQUAD_A.txt": SQUAD_XML.replace("\n", "\r\n").encode("cp1252"),
        "stock/Data/equipment_german.txt": b"WEAPON_A\nWEAPON_B\n",
        "broken/Data/Weapons/WEAPON_C.txt": WEAPON_XML.replace("\n", "\r\n").encode("cp1252"),
        "broken/Data/Weapons/PLAIN.txt": b"this file is not XML at all\n",
    }


def write_fixtures() -> None:
    """Restore every fixture file and drop the destination."""
    for relative, data in FIXTURES.items():
        path = SCRATCH / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    shutil.rmtree(OUT, ignore_errors=True)


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


def fields_of(path: Path, relative: str) -> dict[str, object]:
    """Every leaf of a document as ``dotted/path -> value``."""
    document = load_document(path, relative)
    return {"/".join(parts): entry.value for parts, entry in flatten(document.table)}


class ConvertCommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        FIXTURES.update(build_fixtures())
        cls._env = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        for name, value in cls._env.items():
            if value is not None:
                os.environ[name] = value

    def setUp(self) -> None:
        write_fixtures()

    def convert(self, *extra: str, root: Path = STOCK) -> tuple[int, dict, str]:
        """One conversion of the whole fixture scope."""
        return run_json("Firefight", "convert", f"to={OUT}", f"root={root}", "--write", *extra)

    # --- the accepted conversion --------------------------------------------

    def test_c1_every_entity_becomes_a_working_file(self) -> None:
        code, payload, err = self.convert()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["written"], 3)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["data_root"], str(OUT / "Mod"))
        self.assertEqual(len(payload["files"]), 3)
        for relative in ("Data/Weapons/WEAPON_A.toml", "Data/Weapons/WEAPON_B.toml", "Data/Infantry/SQUAD_A.toml"):
            self.assertTrue((OUT / "Mod" / relative).is_file(), relative)
        self.assertFalse((OUT / "Mod" / "Data" / "equipment_german.toml").exists())
        self.assertEqual([item["reason"] for item in payload["skipped_files"]], ["list file"])

    def test_c2_a_converted_document_carries_the_same_fields(self) -> None:
        code, _, err = self.convert()
        self.assertEqual((code, err), (0, ""))
        for name in ("WEAPON_A", "SQUAD_A"):
            folder = "Weapons" if name.startswith("WEAPON") else "Infantry"
            source = fields_of(STOCK / "Data" / folder / f"{name}.txt", f"Data/{folder}/{name}.txt")
            relative = f"Data/{folder}/{name}.toml"
            target = fields_of(OUT / "Mod" / relative, relative)
            self.assertEqual(target, source, name)
        # The reader calls a pure-ASCII file encoding-neutral; non-ASCII decides.
        weapon = load_document(OUT / "Mod" / "Data" / "Weapons" / "WEAPON_A.toml", "Data/Weapons/WEAPON_A.toml")
        squad = load_document(OUT / "Mod" / "Data" / "Infantry" / "SQUAD_A.toml", "Data/Infantry/SQUAD_A.toml")
        self.assertEqual(weapon.encoding, "utf-8")
        self.assertEqual(squad.encoding, "cp1252")

    def test_c5_the_working_file_is_utf8_without_bom_and_crlf(self) -> None:
        code, _, err = self.convert("type=weapon")
        self.assertEqual((code, err), (0, ""))
        data = (OUT / "Mod" / "Data" / "Weapons" / "WEAPON_A.toml").read_bytes()
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", data)
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn("Büchse".encode("utf-8"), data)
        self.assertNotIn("Büchse".encode("cp1252"), data)
        text = data.decode("utf-8")
        self.assertIn("[weapon]", text)
        self.assertIn('name = "Demo Rifle"', text)

    def test_a_selector_and_a_category_narrow_the_conversion(self) -> None:
        code, payload, err = self.convert("Data/Weapons")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            sorted(item["path"] for item in payload["files"]),
            ["Data/Weapons/WEAPON_A.txt", "Data/Weapons/WEAPON_B.txt"],
        )
        self.assertFalse((OUT / "Mod" / "Data" / "Infantry").exists())
        shutil.rmtree(OUT)
        code, payload, err = self.convert("type=infantry")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([item["path"] for item in payload["files"]], ["Data/Infantry/SQUAD_A.txt"])

    def test_a_destination_that_is_already_a_mod_folder_is_used_as_it_is(self) -> None:
        code, payload, _ = run_json(
            "Firefight", "convert", f"to={OUT / 'Mod'}", f"root={STOCK}", "--write", "type=weapon"
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["data_root"], str(OUT / "Mod"))
        self.assertTrue((OUT / "Mod" / "Data" / "Weapons" / "WEAPON_A.toml").is_file())

    # --- skip, overwrite and dry run ----------------------------------------

    def test_c3_an_existing_file_is_skipped_unless_overwritten(self) -> None:
        code, _, _ = self.convert()
        self.assertEqual(code, 0)
        target = OUT / "Mod" / "Data" / "Weapons" / "WEAPON_A.toml"
        target.write_text("# edited by hand\n", encoding="utf-8")
        code, payload, err = self.convert()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["skipped"], 4)
        self.assertEqual(sorted(item["reason"] for item in payload["skipped_files"]), ["exists", "exists", "exists", "list file"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# edited by hand\n")
        code, payload, err = self.convert("overwrite=1")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(payload["written"], 3)
        self.assertIn('name = "Demo Rifle"', target.read_text(encoding="utf-8"))

    def test_c3_a_dry_run_writes_nothing(self) -> None:
        code, payload, err = self.convert("--dry-run")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["written"], 3)
        self.assertFalse(OUT.exists(), "the dry run created the destination")

    # --- refusals and failures ----------------------------------------------

    def test_c4_write_and_destination_are_required(self) -> None:
        code, _, err = run("Firefight", "convert", f"to={OUT}", f"root={STOCK}")
        self.assertEqual(code, 2)
        self.assertIn("convert needs --write", err)
        self.assertFalse(OUT.exists())
        code, _, err = run("Firefight", "convert", f"root={STOCK}", "--write")
        self.assertEqual(code, 2)
        self.assertIn("convert needs a destination project", err)
        self.assertFalse(OUT.exists())

    def test_c4_a_source_file_that_cannot_be_read_is_an_error(self) -> None:
        code, payload, err = run_json("Firefight", "convert", f"to={OUT}", f"root={BROKEN}", "--write")
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(payload["written"], 1)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertEqual(payload["errors"][0]["path"], "Data/Weapons/PLAIN.txt")
        self.assertTrue((OUT / "Mod" / "Data" / "Weapons" / "WEAPON_C.toml").is_file())


if __name__ == "__main__":
    unittest.main()
