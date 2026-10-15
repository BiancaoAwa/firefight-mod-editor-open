"""Tests for the plain-text tables the project's settings declare.

``Mod/mod.txt`` names the tables the game keeps as text under ``<equipment>`` and
``<surnames>``; a name declared there is a table whatever the file holds, and a project
that carries only ``mod_setting.toml`` declares the same names.  A scope that declares
nothing falls back to the name conventions and to the file content (docs/cli.md
section 4.3).  The fixture keeps an XML root in the declared table, so only the
declaration can single it out.
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core.cli.commands import declared_lists
from core.cli.main import main
from core.cli.scope import Scope

SCRATCH = Path(__file__).resolve().parent / "_scratch_lists"
PROJECT = SCRATCH / "project"
TOML_ONLY = SCRATCH / "toml-only"
PLAIN = SCRATCH / "plain"
OUT = SCRATCH / "out"

WEAPON_XML = """<weapon>
\t<name>Demo Rifle</name>
\t<type>WEAPON_RIFLE</type>
</weapon>
"""

# The declared table carries a root element, so the content rule would call it a document.
TABLE_XML = """<table>
\t<row>one</row>
</table>
"""

MOD_TXT = """<mod>
\t<name>Demo Mod</name>
\t<nationality>
\t\t<name>NATION_AMERICAN</name>
\t\t<equipment>news_main.txt</equipment>
\t\t<equipment>equipment_american.txt</equipment>
\t\t<surnames>surnames_american.txt</surnames>
\t</nationality>
</mod>
"""

MOD_SETTING_TOML = """[mod_setting]
\tname = "Demo Mod"

[[mod_setting.nationality]]
\tname = "NATION_AMERICAN"
\tequipment = ["news_main.txt", "equipment_american.txt"]
\tsurnames = "surnames_american.txt"
"""

DECLARED = {"news_main.txt", "equipment_american.txt", "surnames_american.txt"}


def write_fixtures() -> None:
    """Restore the three scopes and drop the destination."""
    for base in (PROJECT, TOML_ONLY, PLAIN):
        shutil.rmtree(base, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    for base in (PROJECT, TOML_ONLY, PLAIN):
        (base / "Mod" / "Data" / "Weapons").mkdir(parents=True, exist_ok=True)
        (base / "Mod" / "Data" / "Weapons" / "WEAPON_A.txt").write_bytes(
            WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
        )
        (base / "Mod" / "Data" / "news_main.txt").write_bytes(
            TABLE_XML.replace("\n", "\r\n").encode("cp1252")
        )
    (PROJECT / "Mod" / "mod.txt").write_text(MOD_TXT, encoding="utf-8", newline="")
    (PROJECT / "Mod" / "Data" / "equipment_american.txt").write_bytes(b"WEAPON_A\n")
    (PROJECT / "Mod" / "Data" / "surnames_american.txt").write_bytes(b"Smith\n")
    (TOML_ONLY / "mod_setting.toml").write_text(MOD_SETTING_TOML, encoding="utf-8", newline="")
    (TOML_ONLY / "Mod" / "Data" / "equipment_american.txt").write_bytes(b"WEAPON_A\n")
    (TOML_ONLY / "Mod" / "Data" / "surnames_american.txt").write_bytes(b"Smith\n")


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


class DeclaredListsTest(unittest.TestCase):
    """The declaration is read from ``Mod/mod.txt`` or from ``mod_setting.toml``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._env = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        for name, value in cls._env.items():
            if value is not None:
                os.environ[name] = value

    def setUp(self) -> None:
        write_fixtures()

    def test_mod_txt_declares_the_tables(self) -> None:
        scope = Scope("Mod", PROJECT / "Mod", "test")
        self.assertEqual(declared_lists(scope), DECLARED)

    def test_mod_setting_toml_declares_the_same_names(self) -> None:
        scope = Scope("Mod", TOML_ONLY / "Mod", "test")
        self.assertEqual(declared_lists(scope), DECLARED)

    def test_a_scope_that_declares_nothing_returns_nothing(self) -> None:
        self.assertEqual(declared_lists(Scope("Mod", PLAIN / "Mod", "test")), set())


class DeclaredTableCommandTest(unittest.TestCase):
    """Every command that separates documents from tables honours the declaration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._env = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        for name, value in cls._env.items():
            if value is not None:
                os.environ[name] = value

    def setUp(self) -> None:
        write_fixtures()

    def test_show_prints_a_declared_table_as_a_list(self) -> None:
        code, payload, _ = run_json("Mod", "show", "Data/news_main.txt", f"root={PROJECT}")
        self.assertEqual(code, 0)
        self.assertEqual(payload["format"], "list")
        self.assertIn("<row>one</row>", payload["text"])

    def test_show_prints_a_declared_table_without_a_mod_txt(self) -> None:
        code, payload, _ = run_json("Mod", "show", "Data/news_main.txt", f"root={TOML_ONLY}")
        self.assertEqual(code, 0)
        self.assertEqual(payload["format"], "list")

    def test_an_undeclared_file_with_a_root_stays_a_document(self) -> None:
        code, payload, _ = run_json("Mod", "show", "Data/news_main.txt", f"root={PLAIN}")
        self.assertEqual(code, 0)
        self.assertNotEqual(payload["format"], "list")

    def test_convert_skips_the_declared_table(self) -> None:
        code, payload, _ = run_json("Mod", "convert", f"to={OUT}", f"root={PROJECT}", "--write")
        self.assertEqual(code, 0)
        self.assertIn({"path": "Data/news_main.txt", "reason": "list file"}, payload["skipped_files"])

    def test_find_does_not_look_inside_a_declared_table(self) -> None:
        code, payload, _ = run_json("Mod", "find", "tag=row", f"root={PROJECT}")
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 0)

    def test_check_counts_a_declared_table_as_a_list_file(self) -> None:
        code, payload, _ = run_json("Mod", "check", f"root={PROJECT}")
        self.assertEqual(payload["loaded"], 1)
        self.assertEqual(payload["skipped"], 3)

    def test_stats_counts_a_declared_table_as_a_list_file(self) -> None:
        code, payload, _ = run_json("Mod", "stats", f"root={PROJECT}")
        self.assertEqual(payload["files"], 4)
        self.assertEqual(payload["lists"], 3)
        self.assertEqual(payload["by_root"], {"weapon": 1})

    def test_index_skips_the_declared_table(self) -> None:
        code, payload, _ = run_json("Mod", "index", f"root={PROJECT}", "--write")
        self.assertEqual(code, 0)
        self.assertEqual(payload["skipped"], 3)
