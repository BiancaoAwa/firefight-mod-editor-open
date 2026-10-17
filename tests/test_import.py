"""`import`: make a project out of a mod that already exists.

The source is a directory or a zip, laid out the way ``pack`` writes it (``Mod/`` at the root)
or the way an extracted archive often looks (one directory of its own above that, or the mod
root at the top).  ``Data/``, ``Images/`` and ``Sounds/`` are copied byte for byte, ``mod.txt``
comes along, and ``ModSetting.toml`` is rendered from it unless the source already carries one
(docs/cli.md section 4.16, docs/project-layout.md section 3).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path

from core import textio
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_import"
SOURCE = SCRATCH / "source"
DESTINATION = SCRATCH / "made"

WEAPON = "<weapon>\n\t<name>Rifle A</name>\n\t<type>WEAPON_A</type>\n</weapon>\n"
STOCK = "<mod>\n\t<name>Probe Mod</name>\n\t<author>a fixture</author>\n</mod>\n"
PICTURE = b"\x89PNG\r\n\x1a\nnot really a picture\n"


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


def write(path: Path, text: str) -> None:
    """Write a text file, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def write_bytes(path: Path, data: bytes) -> None:
    """Write a binary file, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def packed(source: Path, names_and_text: dict[str, str]) -> None:
    """Lay a mod out under ``Mod/`` inside a source directory."""
    for name, text in names_and_text.items():
        write(source / "Mod" / name, text)


class ImportTestCase(unittest.TestCase):
    """A mod on disk, and the project `import` makes of it."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        SCRATCH.mkdir(parents=True)

    def tearDown(self) -> None:
        os.environ.pop("PYTHONPATH", None)
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def import_into(self, source: Path, destination: Path, *extra: str) -> tuple[int, dict, str]:
        return run_json("Mod", "import", str(source), f"to={destination}", "--write", *extra)

    def test_a_mod_under_mod_becomes_a_project(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON, "mod.txt": STOCK})
        code, payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["root"], "Mod/")
        self.assertEqual(payload["errors"], [])
        self.assertEqual(
            (DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").read_text("utf-8"), WEAPON
        )
        self.assertEqual((DESTINATION / "mod.txt").read_text("utf-8"), STOCK)
        self.assertIn("Probe Mod", (DESTINATION / "ModSetting.toml").read_text("utf-8"))
        self.assertIn("name", (DESTINATION / "ModInformation.toml").read_text("utf-8"))

    def test_a_mod_root_at_the_top_is_read_as_it_is(self) -> None:
        write(SOURCE / "Data" / "Weapons" / "WEAPON_A.txt", WEAPON)
        code, payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["root"], "")
        self.assertTrue((DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").is_file())
        self.assertTrue((DESTINATION / "ModInformation.toml").is_file())

    def test_a_wrapped_archive_is_read_too(self) -> None:
        packed(SOURCE / "MyMod", {"Data/Weapons/WEAPON_A.txt": WEAPON})
        code, payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["root"], "MyMod/Mod/")
        self.assertTrue((DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").is_file())

    def test_a_zip_is_read_like_a_directory(self) -> None:
        archive = SCRATCH / "probe-mod.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("Mod/Data/Weapons/WEAPON_A.txt", WEAPON)
            bundle.writestr("Mod/mod.txt", STOCK)
        code, payload, err = self.import_into(archive, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["root"], "Mod/")
        self.assertEqual(
            (DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").read_text("utf-8"), WEAPON
        )
        self.assertIn("Probe Mod", (DESTINATION / "ModSetting.toml").read_text("utf-8"))

    def test_the_assets_come_across_byte_for_byte(self) -> None:
        packed(
            SOURCE,
            {"Data/Weapons/WEAPON_A.txt": WEAPON, "Data/equipment_demo.txt": "// demo\nA.txt\n"},
        )
        write_bytes(SOURCE / "Mod" / "Images" / "units" / "rifleman.png", PICTURE)
        write_bytes(SOURCE / "Mod" / "Sounds" / "rifle.ogg", b"OggS-fixture\n")
        code, payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual((DESTINATION / "Images" / "units" / "rifleman.png").read_bytes(), PICTURE)
        self.assertEqual((DESTINATION / "Sounds" / "rifle.ogg").read_bytes(), b"OggS-fixture\n")
        self.assertEqual(
            (DESTINATION / "Data" / "equipment_demo.txt").read_text("utf-8"), "// demo\nA.txt\n"
        )

    def test_the_editor_cache_is_not_carried_over(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON, "EditorCache/index.toml": "x = 1\n"})
        code, payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertFalse((DESTINATION / "EditorCache" / "index.toml").exists())
        self.assertNotIn("EditorCache/index.toml", [item["path"] for item in payload["shown"]])

    def test_a_manifest_the_source_carries_is_kept(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON, "ModInformation.toml": 'name = "Kept"\n'})
        code, payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual((DESTINATION / "ModInformation.toml").read_text("utf-8"), 'name = "Kept"\n')
        self.assertEqual(payload["count"], 2)

    def test_import_needs_write(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON})
        code, _out, err = run("Mod", "import", str(SOURCE), f"to={DESTINATION}")
        self.assertEqual(code, 2)
        self.assertIn("import needs --write", err)
        self.assertFalse(DESTINATION.exists())

    def test_import_needs_a_destination(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON})
        code, _out, err = run("Mod", "import", str(SOURCE), "--write")
        self.assertEqual(code, 2)
        self.assertIn("to=<directory>", err)

    def test_a_dry_run_writes_nothing(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON, "mod.txt": STOCK})
        code, payload, err = run_json(
            "Mod", "import", str(SOURCE), f"to={DESTINATION}", "--write", "--dry-run"
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["dry_run"])
        self.assertGreater(payload["count"], 0)
        self.assertFalse(DESTINATION.exists())

    def test_an_existing_project_is_refused_unless_overwritten(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON})
        write(DESTINATION / "ModInformation.toml", 'name = "Already"\n')
        code, _out, err = run("Mod", "import", str(SOURCE), f"to={DESTINATION}", "--write")
        self.assertEqual(code, 2)
        self.assertIn("overwrite=1", err)
        code, payload, err = self.import_into(SOURCE, DESTINATION, "overwrite=1")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["skipped"], [])
        self.assertTrue((DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").is_file())

    def test_an_existing_file_is_skipped_without_overwrite(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON})
        write(DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt", "kept\n")
        write(DESTINATION / "ModInformation.toml", 'name = "Already"\n')
        code, payload, err = self.import_into(SOURCE, DESTINATION, "overwrite=0")
        self.assertEqual(code, 0, err)
        self.assertIn({"path": "Data/Weapons/WEAPON_A.txt", "reason": "exists"}, payload["skipped"])
        self.assertEqual(
            (DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").read_text("utf-8"), "kept\n"
        )

    def test_a_source_without_data_is_refused(self) -> None:
        write(SOURCE / "readme.md", "nothing to see\n")
        code, _out, err = run("Mod", "import", str(SOURCE), f"to={DESTINATION}", "--write")
        self.assertEqual(code, 2)
        self.assertIn("no Data/ folder inside", err)
        self.assertFalse(DESTINATION.exists())

    def test_a_source_that_is_not_there_is_refused(self) -> None:
        code, _out, err = run("Mod", "import", str(SCRATCH / "missing"), f"to={DESTINATION}", "--write")
        self.assertEqual(code, 2)
        self.assertIn("nothing to import from", err)

    def test_the_text_output_names_what_it_left_out(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON})
        write(DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt", "kept\n")
        write(DESTINATION / "ModInformation.toml", 'name = "Already"\n')
        code, out, err = run("Mod", "import", str(SOURCE), f"to={DESTINATION}", "--write", "overwrite=0")
        self.assertEqual(code, 0, err)
        self.assertIn("skipped: Data/Weapons/WEAPON_A.txt (exists)", out)

    def test_the_stock_scope_cannot_import(self) -> None:
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": WEAPON})
        code, _out, err = run("Firefight", "import", str(SOURCE), f"to={DESTINATION}", "--write")
        self.assertEqual(code, 2)
        self.assertIn("under Mod", err)

    def test_the_source_is_read_with_the_project_encoding(self) -> None:
        """A cp1252 source document keeps its bytes; only the setting file is rendered."""
        text = "<weapon>\n\t<name>Caf\xe9 Rifle</name>\n\t<type>WEAPON_A</type>\n</weapon>\n"
        packed(SOURCE, {"Data/Weapons/WEAPON_A.txt": text.encode("cp1252").decode("cp1252")})
        raw = "<weapon>\n\t<name>Caf\xe9 Rifle</name>\n</weapon>\n".encode("cp1252")
        write_bytes(SOURCE / "Mod" / "Data" / "Weapons" / "WEAPON_A.txt", raw)
        code, _payload, err = self.import_into(SOURCE, DESTINATION)
        self.assertEqual(code, 0, err)
        self.assertEqual((DESTINATION / "Data" / "Weapons" / "WEAPON_A.txt").read_bytes(), raw)
        self.assertEqual(textio.decode_source(raw, "probe")[1], "cp1252")


if __name__ == "__main__":
    unittest.main()
