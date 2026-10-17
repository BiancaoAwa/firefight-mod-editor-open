"""`pack` and the archive the game installs.

The package carries the stock layout: documents rendered back to XML, ``ModSetting.toml``
as ``Mod/mod.txt``, unmanaged files copied, and the project's README and LICENSE at the
archive root.  ``EditorCache/`` and a document's stale ``.txt`` twin stay out
(docs/cli.md section 4.8, docs/project-layout.md section 5).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path

from core import convert, journal, textio, toml as toml_core, xml
from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_pack"
PROJECT = SCRATCH / "project"
OUT = SCRATCH / "out"

MOD_TOML = """[mod]

name = "Pack Fixture"
version_name = "0.0.1"
version_code = 1
update_code = 2640
game_version = "13.2.0.0"
authors = ["a fixture"]
license = "GPL-3.0"
"""

MOD_TXT = """<mod>
\t<name>Pack Fixture</name>
\t<author>a fixture</author>

\t<show_scenarios>no</show_scenarios>

\t<minimum_commonness>25</minimum_commonness>

\t<nationality>
\t\t<name>America</name>
\t\t<surnames>surnames_american.txt</surnames>

\t\t<equipment>news_main.txt</equipment>

\t\t<voice>US</voice>
\t</nationality>
</mod>
"""

WEAPON_XML = "<weapon>\r\n\t<name>Seed Gun</name>\r\n\t<type>rifle</type>\r\n</weapon>\r\n"

ARCHIVE = OUT / "Pack Fixture-0.0.1.zip"


def write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write fixture text with LF endings and no BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))


def render(text: str, name: str) -> str:
    """The project document a stock file maps to, through the editor's own converter."""
    return toml_core.render(convert.xml_to_toml(xml.parse(text, name)))


def members(archive: Path) -> dict[str, bytes]:
    """Every member of an archive, by name."""
    with zipfile.ZipFile(archive) as bundle:
        return {item.filename: bundle.read(item) for item in bundle.infolist()}


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


def settle() -> None:
    """Put a fixture project into the state packing requires: ``mod.txt`` equals its rendering.

    The first render also settles the fixture into the blank-line shape the two translators
    produce between them, so the stock file becomes their fixed point.
    """
    for extra in (("op=render",), ("op=emit", "overwrite=1")):
        code, _, err = run("Mod", "settings", *extra, "--write", cwd=PROJECT)
        if code != 0:
            raise AssertionError(err)


class PackTestCase(unittest.TestCase):
    """A project whose stock settings file and one weapon agree with each other."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        write(PROJECT / "ModInformation.toml", MOD_TOML)
        write(PROJECT / "mod.txt", MOD_TXT)
        write(PROJECT / "Data/Weapons/WEAPON_SEED.txt", WEAPON_XML)
        write(PROJECT / "Data/Weapons/WEAPON_SEED.toml", render(WEAPON_XML, "WEAPON_SEED"))
        write(PROJECT / "README.md", "the fixture readme\n")
        write(PROJECT / "LICENSE", "the fixture licence\n")
        self.ready()
        self.stock = (PROJECT / "mod.txt").read_bytes()

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def ready(self) -> None:
        """Put the project into the state packing requires."""
        settle()

    def build(self, *extra: str) -> tuple[int, dict, str]:
        return run_json(
            "Mod", "pack", f"to={OUT}", "--write", *extra, cwd=PROJECT
        )

    # --- the gate ---------------------------------------------------------------

    def test_pack_needs_write(self) -> None:
        code, _, err = run("Mod", "pack", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("pack needs --write", err)

    def test_pack_refuses_the_stock_scope(self) -> None:
        code, _, err = run("Firefight", "pack", f"root={PROJECT}", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("read-only", err)

    def test_pack_needs_a_mod_name(self) -> None:
        self.ready()
        write(PROJECT / "ModInformation.toml", '[mod]\n\nversion_name = "0.0.1"\n')
        code, _, err = self.build()
        self.assertEqual(code, 2)
        self.assertIn("no [mod] name", err)

    def test_a_document_that_cannot_be_rendered_is_reported_and_left_out(self) -> None:
        self.ready()
        write(PROJECT / "Data/Weapons/WEAPON_BROKEN.toml", "this is not toml\n")
        code, payload, err = self.build()
        self.assertEqual(code, 0, err)
        self.assertEqual(
            [item["path"] for item in payload["errors"]], ["Data/Weapons/WEAPON_BROKEN.toml"]
        )
        self.assertFalse([name for name in members(ARCHIVE) if "WEAPON_BROKEN" in name])
        self.assertEqual(payload["check"], {"errors": 1, "dangling": 0})

    def test_the_pack_output_names_what_it_left_out(self) -> None:
        # The skipped count alone hides which file was dropped, and a dropped .txt twin is
        # the case a reader has to notice.
        self.ready()
        code, out, err = run("Mod", "pack", f"to={OUT}", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertIn("skipped: Data/Weapons/WEAPON_SEED.txt (a toml document covers it)", out)
        self.assertIn("skipped: mod.txt (rendered from ModSetting.toml)", out)

    def test_the_pack_output_names_a_warning(self) -> None:
        self.ready()
        write(PROJECT / "Data/Weapons/WEAPON_BROKEN.toml", "this is not toml\n")
        code, out, err = run("Mod", "pack", f"to={OUT}", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertIn("warning: Data/Weapons/WEAPON_BROKEN.toml:", out)

    def test_strict_refuses_a_document_that_cannot_be_rendered(self) -> None:
        self.ready()
        write(PROJECT / "Data/Weapons/WEAPON_BROKEN.toml", "this is not toml\n")
        code, _, err = self.build("strict=1")
        self.assertEqual(code, 2)
        self.assertIn("strict=1", err)
        self.assertFalse(ARCHIVE.exists())

    # --- what goes in -----------------------------------------------------------

    def test_pack_builds_the_archive(self) -> None:
        self.ready()
        code, payload, err = self.build()
        self.assertEqual(code, 0, err)
        self.assertTrue(ARCHIVE.is_file())
        self.assertEqual(
            sorted(members(ARCHIVE)),
            ["LICENSE", "Mod/Data/Weapons/WEAPON_SEED.txt", "Mod/mod.txt", "README.md"],
        )
        self.assertEqual(payload["archive"], str(ARCHIVE))
        self.assertEqual(payload["count"], 4)

    def test_a_document_is_rendered_back_to_the_xml_it_came_from(self) -> None:
        self.ready()
        self.build()
        self.assertEqual(members(ARCHIVE)["Mod/Data/Weapons/WEAPON_SEED.txt"], WEAPON_XML.encode("utf-8"))

    def test_the_readme_and_license_go_to_the_archive_root(self) -> None:
        self.ready()
        self.build()
        found = members(ARCHIVE)
        self.assertEqual(found["README.md"], b"the fixture readme\n")
        self.assertEqual(found["LICENSE"], b"the fixture licence\n")

    def test_the_stock_txt_twin_is_not_copied_again(self) -> None:
        self.ready()
        _, payload, _ = self.build()
        reasons = {item["path"]: item["reason"] for item in payload["skipped"]}
        self.assertEqual(reasons["Data/Weapons/WEAPON_SEED.txt"], "a toml document covers it")
        self.assertIn("rendered from ModSetting.toml", reasons["mod.txt"])

    def test_the_editor_cache_never_enters_the_package(self) -> None:
        self.ready()
        write(PROJECT / "EditorCache/junk.txt", "cache\n")
        write(PROJECT / "EditorCache/junk.txt", "state\n")
        self.build()
        names = members(ARCHIVE)
        self.assertNotIn("Mod/EditorCache/junk.txt", names)
        self.assertNotIn("Mod/EditorCache/junk.txt", names)

    def test_an_unmanaged_file_is_copied_as_it_stands(self) -> None:
        self.ready()
        write(PROJECT / "Data/equipment_fixture.txt", "plain list\n")
        self.build()
        self.assertEqual(members(ARCHIVE)["Mod/Data/equipment_fixture.txt"], b"plain list\n")

    def test_a_rendered_document_keeps_the_encoding_of_its_twin(self) -> None:
        self.ready()
        text = "<weapon>\r\n\t<name>K\u00f6nig</name>\r\n\t<type>rifle</type>\r\n</weapon>\r\n"
        write(PROJECT / "Data/Weapons/WEAPON_UMTEXT.txt", text, encoding="cp1252")
        write(PROJECT / "Data/Weapons/WEAPON_UMTEXT.toml", render(text, "WEAPON_UMTEXT"))
        self.build()
        self.assertEqual(
            members(ARCHIVE)["Mod/Data/Weapons/WEAPON_UMTEXT.txt"], text.encode("cp1252")
        )

    # --- writing ----------------------------------------------------------------

    def test_a_dry_run_writes_nothing(self) -> None:
        self.ready()
        code, payload, _ = run_json("Mod", "pack", f"to={OUT}", "--write", "--dry-run", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(OUT.exists())

    def test_packing_twice_gives_the_same_bytes(self) -> None:
        self.ready()
        self.build()
        first = ARCHIVE.read_bytes()
        self.build()
        self.assertEqual(ARCHIVE.read_bytes(), first)

    def test_an_existing_archive_is_replaced_by_default(self) -> None:
        self.ready()
        OUT.mkdir(parents=True, exist_ok=True)
        ARCHIVE.write_bytes(b"stale")
        code, payload, _ = self.build()
        self.assertEqual(code, 0)
        self.assertGreater(payload["archive_bytes"], 0)
        self.assertNotEqual(ARCHIVE.read_bytes(), b"stale")

    def test_overwrite_zero_leaves_an_existing_archive_alone(self) -> None:
        self.ready()
        OUT.mkdir(parents=True, exist_ok=True)
        ARCHIVE.write_bytes(b"stale")
        code, payload, _ = self.build("overwrite=0")
        self.assertEqual(code, 0)
        self.assertEqual(ARCHIVE.read_bytes(), b"stale")
        self.assertIn("overwrite=1", payload["skipped"][-1]["reason"])

    # --- mod.txt and its rendering ----------------------------------------------

    def test_pack_refuses_when_mod_txt_disagrees_with_the_rendering(self) -> None:
        self.ready()
        write(PROJECT / "mod.txt", MOD_TXT.replace("<name>Pack Fixture</name>", "<name>Other</name>"))
        code, _, err = self.build()
        self.assertEqual(code, 2)
        self.assertIn("settings op=emit --write overwrite=1", err)
        self.assertFalse(ARCHIVE.exists())

    def test_pack_renders_mod_txt_when_the_project_has_none(self) -> None:
        self.ready()
        (PROJECT / "mod.txt").unlink()
        code, _, err = self.build()
        self.assertEqual(code, 0, err)
        self.assertEqual(members(ARCHIVE)["Mod/mod.txt"], self.stock)

    # --- strict -----------------------------------------------------------------

    def test_strict_passes_on_a_project_without_dangling_references(self) -> None:
        self.ready()
        code, _, err = self.build("strict=1")
        self.assertEqual(code, 0, err)

    def test_strict_refuses_a_project_with_dangling_references(self) -> None:
        self.ready()
        write(
            PROJECT / "Data/Weapons/WEAPON_DANGLING.txt",
            "<weapon>\r\n\t<name>Dangling</name>\r\n\t<image_view>nope.png</image_view>\r\n</weapon>\r\n",
        )
        code, _, err = self.build("strict=1")
        self.assertEqual(code, 2)
        self.assertIn("dangling", err)
        self.assertFalse(ARCHIVE.exists())

    def test_a_project_with_a_dangling_reference_packs_without_strict(self) -> None:
        self.ready()
        write(
            PROJECT / "Data/Weapons/WEAPON_DANGLING.txt",
            "<weapon>\r\n\t<name>Dangling</name>\r\n\t<image_view>nope.png</image_view>\r\n</weapon>\r\n",
        )
        code, _, err = self.build()
        self.assertEqual(code, 0, err)


class PackPlanTestCase(unittest.TestCase):
    """The planning half, without a command line in the way."""

    def test_archive_name_drops_unsafe_characters(self) -> None:
        from core import pack

        self.assertEqual(pack.archive_name("World War III", "2.3.0"), "World War III-2.3.0.zip")
        self.assertEqual(pack.archive_name('a/b:c*d', "1"), "a-b-c-d-1.zip")

    def test_archive_name_needs_a_name(self) -> None:
        from core import pack

        with self.assertRaises(ValueError):
            pack.archive_name("///")

    def test_metadata_reads_the_mod_table(self) -> None:
        from core import pack

        table = toml_core.parse(MOD_TOML, "ModInformation.toml")
        self.assertEqual(pack.metadata(table), {"name": "Pack Fixture", "version_name": "0.0.1"})


class EncodingTest(unittest.TestCase):
    """textio's two encodings, so the fidelity test above rests on a real difference."""

    def test_cp1252_and_utf8_differ_for_an_umlaut(self) -> None:
        text = "K\u00f6nig"
        self.assertNotEqual(text.encode("cp1252"), text.encode("utf-8"))
        self.assertEqual(textio.decode_source(text.encode("cp1252"), "x")[1], "cp1252")


class PackLogTestCase(unittest.TestCase):
    """Packing writes a note of its own into the project log, and nothing reverts it."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        write(PROJECT / "ModInformation.toml", MOD_TOML)
        write(PROJECT / "mod.txt", MOD_TXT)
        write(PROJECT / "Data/Weapons/WEAPON_SEED.txt", WEAPON_XML)
        write(PROJECT / "Data/Weapons/WEAPON_SEED.toml", render(WEAPON_XML, "WEAPON_SEED"))
        write(PROJECT / "README.md", "the fixture readme\n")
        write(PROJECT / "LICENSE", "the fixture licence\n")
        settle()

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def build(self, *extra: str) -> tuple[int, dict, str]:
        return run_json("Mod", "pack", f"to={OUT}", "--write", *extra, cwd=PROJECT)

    def packs(self) -> list[dict]:
        return [event for event in journal.read_events(PROJECT) if event.get("result") == "pack"]

    def test_a_written_pack_is_recorded(self) -> None:
        code, payload, err = self.build()
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["recorded"], payload)
        found = self.packs()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["actor"], "cli")
        self.assertEqual(found[0]["after"], f"{payload['count']} member(s) in {ARCHIVE.name}")
        self.assertEqual(found[0]["bytes_after"], payload["archive_bytes"])
        self.assertEqual(found[0]["document"], "")
        self.assertEqual(found[0]["target"], None)

    def test_a_pack_record_reverts_nothing(self) -> None:
        code, payload, err = self.build()
        self.assertEqual(code, 0, err)
        applied, undone = journal.stacks(journal.read_events(PROJECT))
        self.assertNotIn(payload["recorded"], [event["id"] for event in applied])
        self.assertNotIn(payload["recorded"], [event["id"] for event in undone])

    def test_a_dry_run_pack_records_nothing(self) -> None:
        code, payload, err = self.build("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["recorded"], "")
        self.assertEqual(self.packs(), [])

    def test_a_skipped_archive_records_nothing(self) -> None:
        self.build()
        before = len(self.packs())
        code, payload, err = self.build("overwrite=0")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["recorded"], "")
        self.assertEqual(len(self.packs()), before)

    def test_the_log_can_be_filtered_by_the_pack_result(self) -> None:
        self.build()
        code, payload, err = run_json("Mod", "log", "result=pack", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["selected"], 1)
