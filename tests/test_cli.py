"""End-to-end tests for the CLI over a small fixture scope tree.

The fixture mirrors the on-disk shape of a Firefight install (Data, Images,
Sounds) so scope resolution, both storage formats, the reference graph and the
export path are all exercised without the retail corpus.
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path

from core import convert, schema, tomlwrite, xmlread
from cli.main import main

SCRATCH = Path(__file__).resolve().parent / "_scratch_cli"
STOCK = SCRATCH / "stock"
PROJECT = SCRATCH / "project"
WORKSPACE = SCRATCH / "workspace"
OUT = SCRATCH / "out"

WEAPON_XML = """<weapon>
\t<name>P38 Pistol</name>
\t<type>WEAPON_PISTOL</type>
\t<shoot>
\t\t<sound_shoot>shoot_pistol</sound_shoot>
\t</shoot>
\t<magazine>
\t\t<sound_reload>reload_magazine</sound_reload>
\t</magazine>
\t<ammo>
\t\t<type>
\t\t\t<flavour>FLAVOUR_BALL</flavour>
\t\t\t<name>9x19mm Parabellum</name>
\t\t</type>
\t</ammo>
</weapon>
"""

VEHICLE_XML = """<squad>
\t<description>
\t\t<type>TYPE_TANK</type>
\t\t<long_name>M2 Medium Tank</long_name>
\t</description>
\t<vehicle>
\t\t<hull>
\t\t\t<image_view>Image-M2 Medium Tank.png</image_view>
\t\t\t<man>
\t\t\t\t<ammo>
\t\t\t\t\t<for>WEAPON_PISTOL_P38</for>
\t\t\t\t</ammo>
\t\t\t</man>
\t\t</hull>
\t</vehicle>
</squad>
"""

DANGLING_XML = """<squad>
\t<description>
\t\t<type>TYPE_TANK</type>
\t\t<long_name>TK3</long_name>
\t</description>
\t<vehicle>
\t\t<hull>
\t\t\t<man>
\t\t\t\t<ammo>
\t\t\t\t\t<for>WEAPON_PISTOL_WZ_35_VIS</for>
\t\t\t\t</ammo>
\t\t\t</man>
\t\t</hull>
\t</vehicle>
</squad>
"""

INFANTRY_XML = """<squad>
\t<description>
\t\t<type>TYPE_INFANTRY_SECTION</type>
\t\t<long_name>Rifle Squad</long_name>
\t\t<uniform>american_marines</uniform>
\t</description>
\t<man>
\t\t<job>JOB_SQUAD_LEADER</job>
\t\t<weapon>
\t\t\t<type>WEAPON_PISTOL_P38</type>
\t\t</weapon>
\t</man>
</squad>
"""

EQUIPMENT_LIST = """// Equipment list
American-M2 Medium Tank.txt
American-Rifle Squad.txt
"""

MOD_WEAPON_XML = """<weapon>
\t<name>Test Gun</name>
\t<type>WEAPON_MG</type>
\t<shoot>
\t\t<sound_shoot>shoot_test</sound_shoot>
\t</shoot>
</weapon>
"""

OTHER_MOD_XML = """<weapon>
\t<name>Other Pistol</name>
\t<type>WEAPON_PISTOL</type>
</weapon>
"""


def write(path: Path, text: str) -> None:
    """Write fixture text as cp1252 with LF endings and no BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("cp1252"))


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


class CliTestCase(unittest.TestCase):
    """Shared fixture tree."""

    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        cls._env = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}
        write(STOCK / "Data/Weapons/WEAPON_PISTOL_P38.txt", WEAPON_XML)
        write(STOCK / "Data/Vehicles/American-M2 Medium Tank.txt", VEHICLE_XML)
        write(STOCK / "Data/Vehicles/Hungarian-TK3.txt", DANGLING_XML)
        write(STOCK / "Data/Infantry/American-Rifle Squad.txt", INFANTRY_XML)
        write(STOCK / "Data/equipment_american_WW2.txt", EQUIPMENT_LIST)
        write(STOCK / "Sounds/shoot_pistol.ogg", "")
        write(STOCK / "Sounds/reload_magazine.ogg", "")
        write(STOCK / "Images/Units/Vehicles/Image-M2 Medium Tank.png", "")
        write(STOCK / "Images/Uniforms/uniform_american_marines/marine.png", "")
        write(PROJECT / "mod.toml", 'name = "Fixture Mod"\n')
        write(PROJECT / "Mod/Sounds/shoot_test.ogg", "")
        document = xmlread.parse(MOD_WEAPON_XML, "fixture")
        table = convert.xml_to_toml(document, schema.schema_for("weapon"))
        write(PROJECT / "Mod/Data/Weapons/WEAPON_TEST_GUN.toml", tomlwrite.render(table))
        write(WORKSPACE / "Mods/other-mod/Data/Weapons/WEAPON_OTHER.txt", OTHER_MOD_XML)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        for name, value in cls._env.items():
            if value is not None:
                os.environ[name] = value

    def stock(self) -> str:
        return f"root={STOCK}"

    def test_usage_without_arguments(self) -> None:
        code, out, _ = run()
        self.assertEqual(code, 0)
        self.assertIn("ff <scope> <command>", out)

    def test_help_lists_resolved_scope(self) -> None:
        code, out, _ = run("help", self.stock())
        self.assertEqual(code, 0)
        self.assertIn("Firefight:", out)
        self.assertIn(str(STOCK), out)

    def test_missing_stock_data_is_a_usage_error(self) -> None:
        code, _, err = run("Firefight", "list", cwd=SCRATCH)
        self.assertEqual(code, 2)
        self.assertIn("Firefight", err)

    def test_list_stock_weapons(self) -> None:
        code, payload, _ = run_json("Firefight", "list", "Weapons", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        entity = payload["entities"][0]
        self.assertEqual(entity["path"], "Data/Weapons/WEAPON_PISTOL_P38.txt")
        self.assertEqual(entity["category"], "weapon")
        self.assertEqual(entity["format"], "txt")

    def test_list_with_type_filter(self) -> None:
        code, payload, _ = run_json("Firefight", "list", "type=vehicle", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 2)

    def test_stats_counts_categories_and_roots(self) -> None:
        code, payload, _ = run_json("Firefight", "stats", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["files"], 5)
        self.assertEqual(payload["lists"], 1)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["by_category"]["weapon"], 1)
        self.assertEqual(payload["by_category"]["equipment"], 1)
        self.assertEqual(payload["by_root"]["squad"], 3)
        self.assertEqual(payload["by_root"]["weapon"], 1)

    def test_show_raw_matches_the_file(self) -> None:
        code, out, _ = run("Firefight", "show", "Data/Weapons/WEAPON_PISTOL_P38.txt", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(out.rstrip("\n"), WEAPON_XML.rstrip("\n"))

    def test_show_list_file_as_text(self) -> None:
        code, out, _ = run("Firefight", "show", "Data/equipment_american_WW2.txt", self.stock())
        self.assertEqual(code, 0)
        self.assertIn("American-M2 Medium Tank.txt", out)

    def test_show_as_xml_rerenders_the_document(self) -> None:
        code, payload, _ = run_json("Firefight", "show", "Data/Weapons/WEAPON_PISTOL_P38.txt", "as=xml", self.stock())
        self.assertEqual(code, 0)
        self.assertIn("<type>WEAPON_PISTOL</type>", payload["xml"])
        self.assertIn("<sound_shoot>shoot_pistol</sound_shoot>", payload["xml"])

    def test_show_toml_view_round_trips_through_the_parser(self) -> None:
        code, payload, _ = run_json("Firefight", "show", "Data/Vehicles/American-M2 Medium Tank.txt", "as=toml", self.stock())
        self.assertEqual(code, 0)
        self.assertIn("[squad.vehicle.hull.man.ammo]", payload["toml"])
        self.assertIn('for = "WEAPON_PISTOL_P38"', payload["toml"])
        self.assertEqual(payload["warnings"], [])

    def test_show_subtree_lists_leaves(self) -> None:
        code, payload, _ = run_json("Firefight", "show", "Data/Weapons/WEAPON_PISTOL_P38.txt/ammo", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(
            [(item["path"], item["value"]) for item in payload["values"]],
            [
                ("weapon/ammo/type/flavour", "FLAVOUR_BALL"),
                ("weapon/ammo/type/name", "9x19mm Parabellum"),
            ],
        )

    def test_show_subtree_as_xml(self) -> None:
        code, payload, _ = run_json(
            "Firefight", "show", "Data/Weapons/WEAPON_PISTOL_P38.txt/ammo", "as=xml", self.stock()
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["xml"].startswith("<ammo>"))
        self.assertIn("<flavour>FLAVOUR_BALL</flavour>", payload["xml"])

    def test_show_unknown_element_exits_2(self) -> None:
        code, _, err = run("Firefight", "show", "Data/Weapons/WEAPON_PISTOL_P38.txt/nope", self.stock())
        self.assertEqual(code, 2)
        self.assertIn("no such element", err)

    def test_show_ambiguous_selector_exits_2(self) -> None:
        code, _, err = run("Firefight", "show", "Data", self.stock())
        self.assertEqual(code, 2)
        self.assertIn("expected one file", err)

    def test_get_field_by_key_path(self) -> None:
        code, payload, _ = run_json("Firefight", "get", "Data/Weapons/WEAPON_PISTOL_P38.txt", "field=shoot.sound_shoot", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["values"][0]["value"], "shoot_pistol")

    def test_get_unknown_field_exits_2(self) -> None:
        code, _, err = run("Firefight", "get", "Data/Weapons/WEAPON_PISTOL_P38.txt", "field=ammo.missing", self.stock())
        self.assertEqual(code, 2)
        self.assertIn("no field", err)

    def test_find_by_tag_across_the_scope(self) -> None:
        code, payload, _ = run_json("Firefight", "find", "tag=long_name", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 3)
        self.assertFalse(payload["truncated"])

    def test_find_by_value_ignoring_case(self) -> None:
        code, payload, _ = run_json("Firefight", "find", "value=p38 pistol", "ignore_case=1", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual([match["path"] for match in payload["matches"]], ["Data/Weapons/WEAPON_PISTOL_P38.txt"])

    def test_find_without_a_query_exits_2(self) -> None:
        code, _, err = run("Firefight", "find", self.stock())
        self.assertEqual(code, 2)
        self.assertIn("nothing to search for", err)

    def test_refs_reports_kinds(self) -> None:
        code, payload, _ = run_json("Firefight", "refs", "Vehicles", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["by_kind"], {"weapon": 2, "image": 1})
        weapons = {item["value"] for item in payload["references"] if item["kind"] == "weapon"}
        self.assertEqual(weapons, {"WEAPON_PISTOL_P38", "WEAPON_PISTOL_WZ_35_VIS"})

    def test_refs_kind_filter(self) -> None:
        code, payload, _ = run_json("Firefight", "refs", "kind=uniform", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["by_kind"], {"uniform": 1})

    def test_deps_resolves_a_target(self) -> None:
        code, payload, _ = run_json("Firefight", "deps", "value=WEAPON_PISTOL_P38", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["resolved"], ["Data/Weapons/WEAPON_PISTOL_P38.txt"])
        self.assertFalse(payload["unresolved"])
        self.assertEqual(
            sorted(item["source"] for item in payload["references"]),
            [
                "Firefight/Data/Infantry/American-Rifle Squad.txt",
                "Firefight/Data/Vehicles/American-M2 Medium Tank.txt",
            ],
        )

    def test_deps_reports_the_dangling_reference(self) -> None:
        code, payload, _ = run_json("Firefight", "deps", "value=WEAPON_PISTOL_WZ_35_VIS", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["unresolved"])
        self.assertEqual(payload["references"][0]["source"], "Firefight/Data/Vehicles/Hungarian-TK3.txt")

    def test_check_finds_dangling_and_skips_lists(self) -> None:
        code, payload, _ = run_json("Firefight", "check", self.stock())
        self.assertEqual(code, 1)
        self.assertEqual(payload["loaded"], 4)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(len(payload["dangling"]), 1)
        self.assertFalse(payload["ok"])

    def test_check_exit_code_is_zero_on_a_clean_selection(self) -> None:
        code, payload, _ = run_json("Firefight", "check", "Weapons", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["loaded"], 1)
        self.assertTrue(payload["ok"])

    def test_export_writes_stock_xml(self) -> None:
        destination = OUT / "stock"
        shutil.rmtree(destination, ignore_errors=True)
        code, payload, _ = run_json("Firefight", "export", f"to={destination}", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 5)
        exported = destination / "Data/Weapons/WEAPON_PISTOL_P38.txt"
        raw = exported.read_bytes()
        self.assertNotIn(b"\xef\xbb\xbf", raw)
        self.assertTrue(raw.startswith(b"<weapon>\r\n"))
        self.assertIn(b"\r\n\t<name>P38 Pistol</name>\r\n", raw)
        self.assertEqual(
            (destination / "Data/equipment_american_WW2.txt").read_bytes(),
            EQUIPMENT_LIST.replace("\n", "\r\n").encode("cp1252"),
        )

    def test_export_needs_a_destination(self) -> None:
        code, _, err = run("Firefight", "export", self.stock())
        self.assertEqual(code, 2)
        self.assertIn("to=<directory>", err)

    def test_mod_scope_from_the_project_directory(self) -> None:
        code, payload, _ = run_json("Mod", "list", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entities"][0]["path"], "Data/Weapons/WEAPON_TEST_GUN.toml")
        self.assertEqual(payload["entities"][0]["format"], "toml")
        self.assertEqual(Path(payload["root"]), PROJECT / "Mod")

    def test_mod_entity_converts_back_to_its_source_xml(self) -> None:
        code, payload, _ = run_json("Mod", "show", "Data/Weapons/WEAPON_TEST_GUN.toml", "as=xml", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["xml"].rstrip("\r\n"), MOD_WEAPON_XML.replace("\n", "\r\n").rstrip("\r\n"))

    def test_mod_check_crosses_into_its_own_weapons(self) -> None:
        code, payload, _ = run_json("Mod", "check", cwd=PROJECT)
        self.assertEqual(code, 0)
        self.assertEqual(payload["loaded"], 1)
        self.assertEqual(payload["dangling"], [])

    def test_named_scope_from_the_workspace(self) -> None:
        code, payload, _ = run_json("other-mod", "list", f"workspace={WORKSPACE}")
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entities"][0]["path"], "Data/Weapons/WEAPON_OTHER.txt")

    def test_local_config_supplies_the_stock_root(self) -> None:
        config = SCRATCH / ".ff-editor.local.toml"
        write(config, f'firefight = "{STOCK.as_posix()}"\n')
        try:
            code, payload, _ = run_json("Firefight", "stats")
            self.assertEqual(code, 0)
            self.assertEqual(payload["files"], 5)
        finally:
            config.unlink()

    def test_unknown_command_exits_2(self) -> None:
        code, _, err = run("Firefight", "frobnicate", self.stock())
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_unknown_scope_exits_2(self) -> None:
        code, _, err = run("Nowhere", "list")
        self.assertEqual(code, 2)
        self.assertIn("Nowhere", err)

    def test_unknown_flag_exits_2(self) -> None:
        code, _, err = run("--frobnicate")
        self.assertEqual(code, 2)
        self.assertIn("unknown flag", err)

    def test_version_without_a_scope(self) -> None:
        code, out, _ = run("version", self.stock())
        self.assertEqual(code, 0)
        self.assertIn("editor: 0.1.0", out)

    def test_json_flag_before_the_scope(self) -> None:
        code, out, _ = run("--json", "Firefight", "list", "Weapons", self.stock())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 1)


if __name__ == "__main__":
    unittest.main()
