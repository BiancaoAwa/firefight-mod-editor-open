"""`settings` and the two files that sit in the project directory.

``ModInformation.toml`` and ``ModSetting.toml`` are not data documents, but they are editable
through the same commands, and a render creates and replaces one of them under the same
gates as every other write (docs/cli.md sections 4.5 and 4.7).
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core.cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_settings"
PROJECT = SCRATCH / "project"

MOD_TOML = """[mod]

name = "Settings Fixture"
version_name = "0.0.1"
version_code = 1
update_code = 2640
game_version = "13.2.0.0"
authors = ["a fixture"]
license = "GPL-3.0"
"""

# The blank lines are the shape the shipped mod.txt files use: one before every element
# except the first two.  ``emit`` writes that shape back, so this fixture round-trips
# byte for byte (core/settings.py, ``emit``).
MOD_TXT = """<mod>
\t<name>Settings Fixture</name>
\t<author>a fixture</author>

\t<show_scenarios>no</show_scenarios>

\t<allow_vehicles>yes</allow_vehicles>

\t<minimum_commonness>25</minimum_commonness>

\t<nationality>
\t\t<name>America</name>
\t\t<surnames>surnames_american.txt</surnames>

\t\t<equipment>news_main.txt</equipment>
\t\t<equipment>equipment_american.txt</equipment>

\t\t<voice>US</voice>

\t\t<ranks>
\t\t\t<1>Pvt</1>
\t\t\t<2>PFC</2>
\t\t</ranks>
\t</nationality>
</mod>
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


class SettingsTestCase(unittest.TestCase):
    """A project whose stock settings file is the source of truth."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        write(PROJECT / "ModInformation.toml", MOD_TOML)
        write(PROJECT / "mod.txt", MOD_TXT)
        write(PROJECT / "Data/Weapons/WEAPON_SEED.toml", '[weapon]\n\nname = "Seed Gun"\n')

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def settings(self) -> Path:
        """The project file the renderer writes."""
        return PROJECT / "ModSetting.toml"

    # --- the two project files are addressable ---------------------------------

    def test_mod_toml_is_readable(self) -> None:
        code, payload, _ = run_json("Mod", "get", "ModInformation.toml", "field=version_name", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["values"][0]["value"], "0.0.1")

    def test_mod_toml_lists_every_field(self) -> None:
        code, payload, _ = run_json("Mod", "get", "ModInformation.toml", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual([row["path"] for row in payload["values"]][0], "name")

    def test_an_inline_array_survives_a_round_trip(self) -> None:
        code, payload, _ = run_json(
            "Mod", "set", "ModInformation.toml", "field=authors", 'value=["a", "b"]', "--write", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        self.assertIn('authors = ["a", "b"]', (PROJECT / "ModInformation.toml").read_text(encoding="utf-8"))

    def test_a_write_to_mod_toml_is_logged_and_can_be_undone(self) -> None:
        before = (PROJECT / "ModInformation.toml").read_bytes()
        code, _, _ = run_json("Mod", "set", "ModInformation.toml", "field=version_name", "value=9.9.9", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        code, payload, _ = run_json("Mod", "log", "count=1", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["events"][0]["document"], "ModInformation.toml")
        code, _, _ = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual((PROJECT / "ModInformation.toml").read_bytes(), before)

    # --- the renderer ----------------------------------------------------------

    def test_settings_needs_write(self) -> None:
        code, _, err = run("Mod", "settings", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("settings needs --write", err)
        self.assertFalse(self.settings().exists())

    def test_settings_refuses_the_stock_scope(self) -> None:
        code, _, err = run("Firefight", "settings", "root=" + str(PROJECT), "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("stock scope is read-only", err)

    def test_a_dry_run_writes_nothing(self) -> None:
        code, payload, _ = run_json("Mod", "settings", "--write", "--dry-run", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(self.settings().exists())
        self.assertFalse((PROJECT / "EditorCache").exists())

    def test_settings_renders_the_stock_file(self) -> None:
        code, payload, _ = run_json("Mod", "settings", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        text = self.settings().read_text(encoding="utf-8")
        self.assertIn("[mod_setting]", text)
        self.assertIn('name = "Settings Fixture"', text)
        self.assertIn("show_scenarios = false", text)
        self.assertIn("allow_vehicles = true", text)
        self.assertIn('equipment = ["news_main.txt", "equipment_american.txt"]', text)
        self.assertIn('"1" = "Pvt"', text)
        self.assertNotIn("\ufeff", self.settings().read_text(encoding="utf-8"))

    def test_settings_skips_a_file_that_is_already_there(self) -> None:
        write(self.settings(), "keep me\n")
        code, payload, _ = run_json("Mod", "settings", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["skipped"])
        self.assertEqual(self.settings().read_text(encoding="utf-8"), "keep me\n")

    def test_overwrite_replaces_and_undo_puts_it_back(self) -> None:
        write(self.settings(), "keep me\n")
        code, _, _ = run_json("Mod", "settings", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertIn("[mod_setting]", self.settings().read_text(encoding="utf-8"))
        code, _, _ = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(self.settings().read_text(encoding="utf-8"), "keep me\n")

    def test_settings_without_a_stock_file_is_a_usage_error(self) -> None:
        (PROJECT / "mod.txt").unlink()
        code, _, err = run("Mod", "settings", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("nothing to render from", err)

    # --- the emit direction -----------------------------------------------------

    def stock(self) -> Path:
        """The stock settings file the emitter writes back."""
        return PROJECT / "mod.txt"

    def render(self) -> None:
        """Put the project file in place, as the render direction would."""
        code, _, err = run("Mod", "settings", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)

    def test_a_stock_file_round_trips_byte_for_byte(self) -> None:
        before = self.stock().read_bytes()
        self.render()
        code, payload, err = run_json("Mod", "settings", "op=emit", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["warnings"], 0)
        self.assertEqual(self.stock().read_bytes(), before)

    def test_emit_needs_write(self) -> None:
        self.render()
        code, _, err = run("Mod", "settings", "op=emit", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("settings needs --write", err)

    def test_emit_refuses_the_stock_scope(self) -> None:
        code, _, err = run("Firefight", "settings", "op=emit", "root=" + str(PROJECT), "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("stock scope is read-only", err)

    def test_emit_without_a_project_file_is_a_usage_error(self) -> None:
        code, _, err = run("Mod", "settings", "op=emit", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("nothing to emit from", err)

    def test_an_unknown_op_is_a_usage_error(self) -> None:
        code, _, err = run("Mod", "settings", "op=sideways", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("op= is render or emit", err)

    def test_emit_a_dry_run_writes_nothing(self) -> None:
        self.render()
        before = self.stock().read_bytes()
        code, payload, _ = run_json("Mod", "settings", "op=emit", "--write", "--dry-run", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(self.stock().read_bytes(), before)

    def test_emit_skips_a_stock_file_that_is_already_there(self) -> None:
        self.render()
        code, payload, _ = run_json("Mod", "settings", "op=emit", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["skipped"])

    def test_emit_keeps_the_line_endings_of_the_stock_file(self) -> None:
        crlf = MOD_TXT.replace("\n", "\r\n")
        write(self.stock(), crlf)
        self.render()
        code, _, err = run_json("Mod", "settings", "op=emit", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stock().read_bytes(), crlf.encode("utf-8"))

    def test_a_field_edited_in_the_project_file_reaches_the_stock_form(self) -> None:
        self.render()
        code, _, err = run_json("Mod", "set", "ModSetting.toml", "field=minimum_commonness", "value=40", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        code, _, err = run_json("Mod", "set", "ModSetting.toml", "field=allow_vehicles", "value=no", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(
            run_json("Mod", "settings", "op=emit", "--write", "overwrite=1", cwd=PROJECT)[0], 0
        )
        text = self.stock().read_text(encoding="utf-8")
        self.assertIn("<minimum_commonness>40</minimum_commonness>", text)
        self.assertIn("<allow_vehicles>no</allow_vehicles>", text)

    def test_emit_reports_a_field_the_stock_form_has_no_element_for(self) -> None:
        self.render()
        path = self.settings()
        write(path, path.read_text(encoding="utf-8").replace("[mod_setting]\n", "[mod_setting]\nmystery = 1\n", 1))
        code, payload, _ = run_json("Mod", "settings", "op=emit", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["warnings"], 1)
        self.assertIn("not an element of a mod.txt", payload["sample_warnings"][0])
        self.assertNotIn("mystery", self.stock().read_text(encoding="utf-8"))

    def test_an_emit_can_be_undone(self) -> None:
        self.render()
        before = self.stock().read_bytes()
        code, _, err = run_json("Mod", "settings", "op=emit", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        code, _, err = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stock().read_bytes(), before)
        code, _, err = run_json("Mod", "redo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)

    def test_an_empty_target_is_replaced_and_undo_restores_it(self) -> None:
        """An empty file is a file, not the "was not there yet" marker."""
        self.settings().write_bytes(b"")
        code, payload, err = run_json("Mod", "settings", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["existed_before"])
        self.assertEqual(payload["bytes_before"], 0)
        self.assertGreater(self.settings().stat().st_size, 0)
        code, _, err = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.settings().read_bytes(), b"")

    def test_an_empty_stock_file_is_replaced_by_emit(self) -> None:
        self.render()
        expected = self.stock().read_bytes()
        self.stock().write_bytes(b"")
        code, payload, err = run_json("Mod", "settings", "op=emit", "--write", "overwrite=1", cwd=PROJECT)
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["existed_before"])
        self.assertEqual(self.stock().read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
