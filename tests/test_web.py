"""Tests for the local web UI over a small fixture scope tree.

The server runs on an ephemeral port and every page is fetched over a real socket, so
routing, escaping, filtering and the token check are exercised as a browser would hit them.
"""

import json
import re
import shutil
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from core.cli.main import main
from core.errors import FfError
from core.web import server
from core.web.server import App, make_server

SCRATCH = Path(__file__).resolve().parent / "_scratch_web"
STOCK = SCRATCH / "stock"
PROJECT = SCRATCH / "project"
WORKSPACE = SCRATCH / "workspace"

WEAPON_XML = """<weapon>
\t<name>P38 Pistol</name>
\t<type>WEAPON_PISTOL_P38</type>
\t<shoot>
\t\t<sound_shoot>shoot_pistol</sound_shoot>
\t</shoot>
\t<ammo>
\t\t<type>
\t\t\t<flavour>FLAVOUR_BALL</flavour>
\t\t\t<name>9x19mm Parabellum</name>
\t\t</type>
\t</ammo>
</weapon>
"""

EVIL_XML = """<weapon>
\t<name>&lt;script&gt;alert(1)&lt;/script&gt;</name>
\t<type>WEAPON_EVIL</type>
</weapon>
"""

EVIL_LIST = """// Equipment list
<script>alert(1)</script>.txt
"""

INFANTRY_XML = """<squad>
\t<description>
\t\t<type>TYPE_INFANTRY_SECTION</type>
\t\t<long_name>Rifle Squad</long_name>
\t</description>
\t<man>
\t\t<job>JOB_SQUAD_LEADER</job>
\t\t<weapon>
\t\t\t<type>WEAPON_PISTOL_P38</type>
\t\t</weapon>
\t</man>
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

EQUIPMENT_LIST = """// Equipment list
American-Rifle Squad.txt
"""


def write(path: Path, text: str) -> None:
    """Write fixture text as cp1252, like the retail files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("cp1252"))


class WebTestCase(unittest.TestCase):
    """One fixture tree and one running server for the whole class."""

    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        write(STOCK / "Data/Weapons/WEAPON_PISTOL_P38.txt", WEAPON_XML)
        write(STOCK / "Data/Weapons/WEAPON_EVIL.txt", EVIL_XML)
        write(STOCK / "Data/Vehicles/Hungarian-TK3.txt", DANGLING_XML)
        write(STOCK / "Data/Infantry/American-Rifle Squad.txt", INFANTRY_XML)
        write(STOCK / "Data/equipment_american_WW2.txt", EQUIPMENT_LIST)
        write(STOCK / "Data/equipment_evil.txt", EVIL_LIST)
        write(PROJECT / "mod.toml", 'name = "Fixture Mod"\n')
        write(WORKSPACE / "Mods/other-mod/Data/Weapons/WEAPON_OTHER.txt", WEAPON_XML)
        cls.options = {"root": str(STOCK), "workspace": str(WORKSPACE)}
        cls.app = App(cls.options, SCRATCH, "Firefight")
        cls.server = make_server(cls.app, 0)
        cls.server.quiet = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(SCRATCH, ignore_errors=True)

    # --- helpers ------------------------------------------------------------

    def fetch(self, route: str = "", **params) -> tuple[int, str]:
        """GET a route and return its status code and body."""
        url = self.base + route
        if params:
            url += "?" + urlencode(params)
        request = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def payload(self, **params) -> dict:
        """Fetch the /json route and parse it."""
        status, body = self.fetch("/json", **params)
        self.assertEqual(status, 200, body[:400])
        return json.loads(body)

    def cli_payload(self, *argv: str) -> dict:
        """Run the CLI in-process and return its payload, for comparison."""
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([*argv, "--json"])
        self.assertEqual(code, 0, out.getvalue()[:400])
        return json.loads(out.getvalue())

    @staticmethod
    def browser_submission(page: str) -> str:
        """The request a browser sends for the page's first GET form.

        A GET submission keeps the path of the action, drops its query and sends the form's
        own successful controls instead - which is why `server.form` re-emits the scope and the
        token as hidden inputs instead of leaving them in the action.
        """
        action = re.search(r'<form[^>]*action="([^"]*)"', page)
        body = re.search(r"<form[^>]*>(.*?)</form>", page, re.S)
        assert action is not None and body is not None, "the page has no form"
        fields = re.findall(r'<(?:input|select)[^>]*name="([^"]*)"[^>]*value="([^"]*)"', body.group(1))
        query = urlencode(fields)
        return action.group(1) + (f"?{query}" if query else "")

    # --- index, scopes ------------------------------------------------------

    def test_index_lists_scopes_and_inventory(self) -> None:
        status, body = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("可用的作用域", body)
        self.assertIn("Firefight", body)
        self.assertIn(str(STOCK), body)
        self.assertIn("实体文件", body)
        self.assertIn("查找", body)

    def test_index_names_workspace_mods(self) -> None:
        _, body = self.fetch("/")
        self.assertIn("other-mod", body)

    def test_unknown_scope_is_a_usage_error(self) -> None:
        from core.cli.scope import UsageError

        app = App({"workspace": str(WORKSPACE)}, SCRATCH, "Firefight")
        with self.assertRaises(UsageError):
            app.scope("NoSuchScope")

    def test_a_busy_port_is_refused(self) -> None:
        # HTTPServer sets SO_REUSEADDR, and on Windows that lets a second bind of a port that
        # is already served succeed — two UIs would then share one port. make_server asks first.
        with self.assertRaises(FfError) as caught:
            make_server(self.app, self.server.server_port)
        self.assertIn("already in use", str(caught.exception))

    def test_a_free_port_is_accepted(self) -> None:
        server = make_server(self.app, 0)
        try:
            self.assertGreater(server.server_port, 0)
        finally:
            server.server_close()

    def test_unknown_route_is_404(self) -> None:
        status, _ = self.fetch("/no-such-page")
        self.assertEqual(status, 404)

    def test_favicon_is_empty(self) -> None:
        status, body = self.fetch("/favicon.ico")
        self.assertEqual(status, 204)
        self.assertEqual(body, "")

    def test_post_is_not_implemented(self) -> None:
        request = urllib.request.Request(self.base + "/", data=b"x=1", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=20)
        self.assertEqual(caught.exception.code, 501)
        self.assertIn("只支持 GET", caught.exception.read().decode("utf-8"))

    def test_other_methods_are_not_implemented(self) -> None:
        for method in ("PUT", "DELETE", "PATCH"):
            with self.subTest(method=method):
                request = urllib.request.Request(self.base + "/", data=b"x=1", method=method)
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=20)
                self.assertEqual(caught.exception.code, 501)

    def test_method_without_a_body_is_also_rejected(self) -> None:
        request = urllib.request.Request(self.base + "/", data=b"", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=20)
        self.assertEqual(caught.exception.code, 501)

    # --- list ---------------------------------------------------------------

    def test_list_shows_entities(self) -> None:
        status, body = self.fetch("/list")
        self.assertEqual(status, 200)
        self.assertIn("Data/Weapons/WEAPON_PISTOL_P38.txt", body)
        self.assertIn("Data/Infantry/American-Rifle Squad.txt", body)

    def test_list_filters_by_path_text(self) -> None:
        _, body = self.fetch("/list", prefix="vehicles")
        self.assertIn("Hungarian-TK3", body)
        self.assertNotIn("WEAPON_PISTOL_P38", body)

    def test_list_filters_by_category(self) -> None:
        _, body = self.fetch("/list", type="weapon")
        self.assertIn("WEAPON_PISTOL_P38", body)
        self.assertNotIn("Hungarian-TK3", body)

    def test_list_pages(self) -> None:
        app = App(self.options, SCRATCH, "Firefight", page_size=2)
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            def get(**params) -> str:
                with urllib.request.urlopen(base + "/list?" + urlencode(params), timeout=20) as response:
                    return response.read().decode("utf-8")

            first, second, beyond = get(page=1), get(page=2), get(page=99)
            self.assertIn("第 1 / 3 页", first)
            self.assertIn("第 2 / 3 页", second)
            self.assertNotEqual(first, second)
            self.assertIn("第 3 / 3 页", beyond)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_list_payload_matches_cli(self) -> None:
        payload = self.payload(command="list", selector="all")
        expected = self.cli_payload("Firefight", "list", "all", f"root={STOCK}")
        self.assertEqual(payload["count"], expected["count"])
        self.assertEqual(payload["root"], expected["root"])

    # --- show, get ----------------------------------------------------------

    def test_show_toml_view(self) -> None:
        status, body = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "toml"})
        self.assertEqual(status, 200)
        self.assertIn("P38 Pistol", body)
        self.assertIn("FLAVOUR_BALL", body)
        self.assertIn("TOML 视图 ←", body)

    def test_show_raw_and_xml_views(self) -> None:
        _, raw = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "raw"})
        self.assertIn("&lt;weapon&gt;", raw)
        _, xml = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "xml"})
        self.assertIn("&lt;weapon&gt;", xml)

    def test_show_escapes_data_markup(self) -> None:
        _, body = self.fetch("/show", path="Data/equipment_evil.txt", **{"as": "toml"})
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>", body)
        _, weapon = self.fetch("/show", path="Data/Weapons/WEAPON_EVIL.txt", **{"as": "toml"})
        self.assertNotIn("<script>", weapon)

    def test_show_rejects_a_bad_view(self) -> None:
        status, body = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "yaml"})
        self.assertEqual(status, 400)
        self.assertIn("不是 raw", body)

    def test_show_rejects_missing_entity(self) -> None:
        status, body = self.fetch("/show", path="Data/Weapons/NOPE.txt", **{"as": "toml"})
        self.assertEqual(status, 400)
        self.assertIn("用法错误", body)

    def test_show_rejects_path_traversal(self) -> None:
        for attempt in ("../mod.toml", "..\\mod.toml", "/etc/passwd", "C:/Windows/win.ini"):
            status, body = self.fetch("/show", path=attempt, **{"as": "raw"})
            self.assertEqual(status, 400, f"{attempt} was not refused")
            self.assertNotIn("Fixture Mod", body)

    def test_show_rejects_traversal_in_subtree(self) -> None:
        status, _ = self.fetch("/show", path="Data/Weapons/../Vehicles/Hungarian-TK3.txt", **{"as": "toml"})
        self.assertEqual(status, 400)

    def test_get_field_values(self) -> None:
        status, body = self.fetch("/get", path="Data/Weapons/WEAPON_PISTOL_P38.txt", field="ammo.type.flavour")
        self.assertEqual(status, 200)
        self.assertIn("FLAVOUR_BALL", body)
        self.assertIn("文档路径", body)

    def test_get_rejects_unknown_field(self) -> None:
        status, body = self.fetch("/get", path="Data/Weapons/WEAPON_PISTOL_P38.txt", field="nope.nothing")
        self.assertEqual(status, 400)
        self.assertIn("no field", body)

    def test_show_links_incoming_references(self) -> None:
        _, body = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "toml"})
        self.assertIn("谁引用了 WEAPON_PISTOL_P38", body)

    # --- find, refs, deps ---------------------------------------------------

    def test_find_by_tag(self) -> None:
        status, body = self.fetch("/find", selector="all", tag="sound_shoot")
        self.assertEqual(status, 200)
        self.assertIn("WEAPON_PISTOL_P38.txt", body)
        self.assertIn("shoot_pistol", body)

    def test_find_needs_a_condition(self) -> None:
        _, body = self.fetch("/find")
        self.assertIn("至少填一个条件", body)

    def test_find_ignore_case(self) -> None:
        _, body = self.fetch("/find", selector="all", value="p38", ignore_case="0")
        self.assertIn("没有命中", body)
        _, body = self.fetch("/find", selector="all", value="p38", ignore_case="1")
        self.assertIn("P38 Pistol", body)

    def test_refs_of_one_entity(self) -> None:
        status, body = self.fetch("/refs", path="Data/Weapons/WEAPON_PISTOL_P38.txt")
        self.assertEqual(status, 200)
        self.assertIn("本文件指向谁", body)
        self.assertIn("shoot_pistol", body)

    def test_deps_resolves_target(self) -> None:
        status, body = self.fetch("/deps", value="WEAPON_PISTOL_P38")
        self.assertEqual(status, 200)
        self.assertIn("American-Rifle Squad.txt", body)
        self.assertIn("解析到", body)

    def test_deps_unresolved_is_reported(self) -> None:
        _, body = self.fetch("/deps", value="WEAPON_NOPE")
        self.assertIn("没有解析到任何实体文件", body)

    def test_deps_without_value_asks_for_one(self) -> None:
        _, body = self.fetch("/deps")
        self.assertIn("填一个取值", body)

    # --- check, stats -------------------------------------------------------

    def test_check_reports_dangling(self) -> None:
        status, body = self.fetch("/check", selector="all")
        self.assertEqual(status, 200)
        self.assertIn("个文件读取成功", body)
        self.assertIn("悬空引用", body)
        self.assertIn("WEAPON_PISTOL_WZ_35_VIS", body)

    def test_check_narrowed_selector(self) -> None:
        _, body = self.fetch("/check", selector="Data/Weapons")
        self.assertIn("Data/Weapons", body)
        self.assertNotIn("WEAPON_PISTOL_WZ_35_VIS", body)

    def test_stats_counts(self) -> None:
        status, body = self.fetch("/stats")
        self.assertEqual(status, 200)
        self.assertIn("按分类", body)
        self.assertIn("按根元素", body)
        payload = self.payload(command="stats", selector="all")
        self.assertEqual(payload["by_category"].get("weapon"), 2)

    # --- json route ---------------------------------------------------------

    def test_json_route_matches_the_command(self) -> None:
        payload = self.payload(command="show", selector="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "toml"})
        self.assertIn("P38 Pistol", payload["toml"])

    def test_json_route_rejects_unknown_command(self) -> None:
        status, body = self.fetch("/json", command="rmdir")
        self.assertEqual(status, 400)
        self.assertIn("没有这个命令", body)

    def test_json_route_is_plain_text(self) -> None:
        with urllib.request.urlopen(f"{self.base}/json?{urlencode({'command': 'version', 'scope': 'Firefight'})}", timeout=20) as response:
            self.assertEqual(response.headers.get("Content-Type"), "text/plain; charset=utf-8")
            self.assertEqual(response.status, 200)

    # --- help, token --------------------------------------------------------

    def test_help_lists_pages(self) -> None:
        status, body = self.fetch("/help")
        self.assertEqual(status, 200)
        self.assertIn("页面与等价命令", body)
        self.assertIn("只读", body)

    # --- the command line page ----------------------------------------------

    def test_cmd_page_shows_a_form_and_examples(self) -> None:
        status, body = self.fetch("/cmd")
        self.assertEqual(status, 200)
        self.assertIn('<form method="get" action="/cmd">', body)
        self.assertIn('name="line"', body)
        self.assertIn("示例：", body)

    def test_cmd_runs_a_command_and_prints_its_text(self) -> None:
        status, body = self.fetch("/cmd", line="list weapon")
        self.assertEqual(status, 200)
        self.assertIn("WEAPON_PISTOL_P38.txt", body)
        self.assertIn("退出码", body)
        self.assertIn("ff Firefight list weapon", body)

    def test_cmd_output_matches_the_cli(self) -> None:
        """What the page prints is the text the CLI prints, not a re-rendering."""
        scope = self.app.scope("Firefight")
        expected = self.app.call("list", scope, "weapon").text
        _, body = self.fetch("/cmd", line="list weapon")
        self.assertIn(server.pre(expected), body)

    def test_cmd_json_checkbox_prints_the_payload(self) -> None:
        status, body = self.fetch("/cmd", line="stats", json="1")
        self.assertEqual(status, 200)
        self.assertIn(server.esc('"files": 6'), body)
        self.assertIn("ff Firefight stats --json", body)

    def test_cmd_keeps_a_quoted_path_together(self) -> None:
        status, body = self.fetch("/cmd", line='show "Data/Infantry/American-Rifle Squad.txt" as=toml')
        self.assertEqual(status, 200)
        self.assertIn("American-Rifle Squad", body)
        self.assertNotIn("用法错误", body)

    def test_cmd_accepts_a_scope_prefix(self) -> None:
        _, body = self.fetch("/cmd", line="Firefight stats")
        self.assertIn("file(s)", body)
        self.assertIn("ff Firefight stats", body)

    def test_cmd_rejects_unknown_commands(self) -> None:
        status, body = self.fetch("/cmd", line="rmdir /s")
        self.assertEqual(status, 400)
        self.assertIn("没有这个命令", body)

    def test_cmd_refuses_the_writing_commands(self) -> None:
        """export writes files and web would bind a second port; the UI stays read-only."""
        for line in ("export to=C:/tmp/nowhere", "emit to=C:/tmp/nowhere", "web port=8899", "serve"):
            status, body = self.fetch("/cmd", line=line)
            self.assertEqual(status, 400, line)
            self.assertIn("不可用", body, line)

    def test_json_route_refuses_the_writing_commands_too(self) -> None:
        status, body = self.fetch("/json", command="export", to="C:/tmp/nowhere")
        self.assertEqual(status, 400)
        self.assertIn("不可用", body)

    def test_token_is_required_and_carried_in_links(self) -> None:
        app = App(self.options, SCRATCH, "Firefight", token="s3cret")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = urllib.request.Request(base + "/")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=20)
            self.assertEqual(caught.exception.code, 400)
            with urllib.request.urlopen(f"{base}/?t=s3cret", timeout=20) as response:
                body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("t=s3cret", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_pages_render_without_script_tags(self) -> None:
        for route in ("/", "/list", "/find", "/deps", "/check", "/stats", "/help", "/quit"):
            _, body = self.fetch(route)
            self.assertNotIn("<script", body, f"{route} contains JavaScript")

    # --- quit ---------------------------------------------------------------

    def test_every_page_links_to_quit(self) -> None:
        for route in ("/", "/list", "/stats", "/help"):
            _, body = self.fetch(route)
            self.assertIn('href="/quit?', body, f"{route} has no exit link")

    def test_quit_asks_first_and_keeps_serving(self) -> None:
        status, body = self.fetch("/quit")
        self.assertEqual(status, 200)
        self.assertIn("退出 Web UI", body)
        self.assertIn('name="do" value="1"', body)
        self.assertFalse(self.server.quit_requested)
        again, _ = self.fetch("/")
        self.assertEqual(again, 200)

    def test_no_form_keeps_parameters_in_its_action(self) -> None:
        """A GET submission replaces the query of the action, so it must carry none."""
        for route in ("/", "/find", "/get", "/deps", "/quit"):
            _, body = self.fetch(route)
            for action in re.findall(r'<form[^>]*action="([^"]*)"', body):
                self.assertNotIn("?", action, f"{route} form action still carries a query: {action}")

    def test_a_page_never_spells_a_parameter_twice(self) -> None:
        """The carried scope must not be repeated by a field of the form itself."""
        for route in ("/find", "/deps", "/quit"):
            _, body = self.fetch(route)
            form = re.search(r"<form[^>]*>(.*?)</form>", body, re.S)
            self.assertIsNotNone(form, route)
            names = re.findall(r'name="([^"]*)"', form.group(1))
            self.assertEqual(len(names), len(set(names)), f"{route} sends a parameter twice: {names}")

    def test_forms_carry_the_scope_and_token_as_hidden_fields(self) -> None:
        app = App(self.options, SCRATCH, "Mod", token="s3cret")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base}/find?t=s3cret", timeout=20) as response:
                page = response.read().decode("utf-8")
            self.assertIn('<input type="hidden" name="t" value="s3cret">', page)
            self.assertIn('<input type="hidden" name="scope" value="Mod">', page)
            target = self.browser_submission(page)
            self.assertIn("t=s3cret", target)
            self.assertIn("scope=Mod", target)
            with urllib.request.urlopen(base + target, timeout=20) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("t=s3cret", response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_quit_button_stops_the_server_the_way_a_browser_sends_it(self) -> None:
        """The confirmation form must work when a browser submits it, not just by URL."""
        app = App(self.options, SCRATCH, "Firefight")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base}/quit", timeout=20) as response:
                page = response.read().decode("utf-8")
            target = self.browser_submission(page)
            self.assertTrue(target.startswith("/quit?"), target)
            self.assertIn("do=1", target)
            with urllib.request.urlopen(base + target, timeout=20) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
            self.assertIn("已退出", body)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "the serving loop did not stop")
            self.assertTrue(server.quit_requested)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_confirmed_quit_stops_the_server(self) -> None:
        app = App(self.options, SCRATCH, "Firefight")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base}/quit?do=1", timeout=20) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
            self.assertIn("已退出", body)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "the serving loop did not stop")
            self.assertTrue(server.quit_requested)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
