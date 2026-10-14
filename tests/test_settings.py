"""`settings` and the two files that sit in the project directory.

``mod.toml`` and ``mod_setting.toml`` are not data documents, but they are editable
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
        write(PROJECT / "mod.toml", MOD_TOML)
        write(PROJECT / "Mod" / "mod.txt", MOD_TXT)
        write(PROJECT / "Mod" / "Data/Weapons/WEAPON_SEED.toml", '[weapon]\n\nname = "Seed Gun"\n')

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def settings(self) -> Path:
        """The project file the renderer writes."""
        return PROJECT / "mod_setting.toml"

    # --- the two project files are addressable ---------------------------------

    def test_mod_toml_is_readable(self) -> None:
        code, payload, _ = run_json("Mod", "get", "mod.toml", "field=version_name", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["values"][0]["value"], "0.0.1")

    def test_mod_toml_lists_every_field(self) -> None:
        code, payload, _ = run_json("Mod", "get", "mod.toml", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual([row["path"] for row in payload["values"]][0], "name")

    def test_an_inline_array_survives_a_round_trip(self) -> None:
        code, payload, _ = run_json(
            "Mod", "set", "mod.toml", "field=authors", 'value=["a", "b"]', "--write", cwd=PROJECT
        )
        self.assertEqual(code, 0)
        self.assertIn('authors = ["a", "b"]', (PROJECT / "mod.toml").read_text(encoding="utf-8"))

    def test_a_write_to_mod_toml_is_logged_and_can_be_undone(self) -> None:
        before = (PROJECT / "mod.toml").read_bytes()
        code, _, _ = run_json("Mod", "set", "mod.toml", "field=version_name", "value=9.9.9", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        code, payload, _ = run_json("Mod", "log", "count=1", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["events"][0]["document"], "mod.toml")
        code, _, _ = run_json("Mod", "undo", "--write", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual((PROJECT / "mod.toml").read_bytes(), before)

    # --- the renderer ----------------------------------------------------------

    def test_settings_needs_write(self) -> None:
        code, _, err = run("Mod", "settings", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("settings needs --write", err)
        self.assertFalse(self.settings().exists())

    def test_settings_refuses_the_stock_scope(self) -> None:
        code, _, err = run("Firefight", "settings", "root=" + str(PROJECT / "Mod"), "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("stock scope is read-only", err)

    def test_a_dry_run_writes_nothing(self) -> None:
        code, payload, _ = run_json("Mod", "settings", "--write", "--dry-run", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(self.settings().exists())
        self.assertFalse((PROJECT / ".editor").exists())

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
        (PROJECT / "Mod" / "mod.txt").unlink()
        code, _, err = run("Mod", "settings", "--write", cwd=PROJECT)
        self.assertEqual(code, 2)
        self.assertIn("nothing to render from", err)


if __name__ == "__main__":
    unittest.main()
