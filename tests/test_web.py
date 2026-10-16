"""Tests for the local web UI over a small fixture scope tree.

The server runs on an ephemeral port and every page is fetched over a real socket, so
routing, escaping, filtering and the token check are exercised as a browser would hit them.
"""

import ast
import contextlib
import io
import json
import re
import shutil
import socket
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

from core.cli import specs
from core.cli.main import main
from core.errors import FfError
from core.web import i18n, server
from core.web.server import App, make_server


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report a 302 as it came back; the panel's buttons answer with one."""

    def redirect_request(self, *args, **kwargs):
        return None


SCRATCH = Path(__file__).resolve().parent / "_scratch_web"
STOCK = SCRATCH / "stock"
PROJECT = SCRATCH / "project"
WORKSPACE = SCRATCH / "workspace"
MEDIA = SCRATCH / "media"

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

# A picture and a sound as bytes: the asset route sends files, not rendered text.
PICTURE = b"\x89PNG\r\n\x1a\nfixture-pixels"
SOUND = b"OggS-fixture-bytes"

# One document whose image field names a file that is really there, and one whose
# image field dangles: only the first may draw a preview.
MEDIA_XML = """<weapon>
\t<name>Preview Rifle</name>
\t<type>WEAPON_PREVIEW</type>
\t<image_view>Images/units/rifleman.png</image_view>
</weapon>
"""

MEDIA_MISSING_XML = """<weapon>
\t<name>Missing Rifle</name>
\t<type>WEAPON_MISSING</type>
\t<image_view>Images/units/gone.png</image_view>
</weapon>
"""


def write_bytes(path: Path, payload: bytes) -> None:
    """Write fixture bytes, for the files the browser is meant to render itself."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


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
        write(PROJECT / "ModInformation.toml", 'name = "Fixture Mod"\n')
        write(WORKSPACE / "Mod/other-mod/Data/Weapons/WEAPON_OTHER.txt", WEAPON_XML)
        write_bytes(STOCK / "Images/units/rifleman.png", PICTURE)
        write_bytes(STOCK / "Sounds/shoot_pistol.ogg", SOUND)
        write_bytes(STOCK / "Images/notes.txt", b"a list, not a picture")
        write(MEDIA / "ModInformation.toml", 'name = "Media Mod"\n')
        write(MEDIA / "Data/Weapons/WEAPON_PREVIEW.txt", MEDIA_XML)
        write(MEDIA / "Data/Weapons/WEAPON_MISSING.txt", MEDIA_MISSING_XML)
        write_bytes(MEDIA / "Images/units/rifleman.png", PICTURE)
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

    def setUp(self) -> None:
        # The bottom pane and the status bar keep their state with the server, so every test
        # starts from an empty session.
        self.app.last_command = None
        self.app.checks.clear()
        # The MCP listener is the one socket a test may open; never leave it open for the next one.
        if self.app.mcp.running():
            self.app.mcp.stop()

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
        """The request a browser sends for the centre pane's first GET form.

        A GET submission keeps the path of the action, drops its query and sends the form's
        own successful controls instead - which is why `server.form` re-emits the scope and the
        token as hidden inputs instead of leaving them in the action.
        """
        where = page.find('<div class="doc-body">')
        assert where >= 0, "the page has no document pane"
        page = page[where:]
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
        # pane=doc is the centre pane alone: the tree lists the whole project by design.
        _, body = self.fetch("/list", prefix="vehicles", pane="doc")
        self.assertIn("Hungarian-TK3", body)
        self.assertNotIn("WEAPON_PISTOL_P38", body)

    def test_list_filters_by_category(self) -> None:
        _, body = self.fetch("/list", type="weapon", pane="doc")
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

    def test_each_entity_row_carries_the_three_writes(self) -> None:
        _, body = self.fetch("/list", prefix="WEAPON_PISTOL_P38", pane="doc")
        document = "Data%2FWeapons%2FWEAPON_PISTOL_P38.txt"
        # edit goes straight to the field grid; copy and delete go through the check step
        self.assertIn(f'href="/edit?path={document}&amp;scope=Firefight"', body)
        self.assertIn(f'href="/ops?command=add&amp;from={document}&amp;scope=Firefight"', body)
        self.assertIn(f'href="/ops?command=remove&amp;selector={document}&amp;confirm=1&amp;scope=Firefight"', body)

    def test_the_entity_list_offers_a_new_document_form(self) -> None:
        _, body = self.fetch("/list", pane="doc")
        self.assertIn('<form method="get" action="/ops">', body)
        self.assertIn('<input type="hidden" name="command" value="add">', body)
        self.assertIn('name="selector"', body)
        self.assertIn('name="from"', body)

    def test_a_delete_link_shows_the_check_and_writes_nothing(self) -> None:
        """Following the delete link runs the check only; the file is still there afterwards."""
        target = MEDIA / "Data/Weapons/WEAPON_PREVIEW.txt"
        before = target.read_bytes()
        with self.running(MEDIA) as base:
            status, body = self.fetch_from(base, "/ops", command="remove", selector="Data/Weapons/WEAPON_PREVIEW.txt", confirm="1")
            self.assertEqual(status, 200, body[:400])
            self.assertIn("--write --dry-run", body)
            self.assertIn("尚未写入", body)
            self.assertIn('href="/ops?command=remove', body)
        self.assertEqual(target.read_bytes(), before)

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
        self.assertEqual(body.count("<script"), 1, "data markup became a second script")
        _, weapon = self.fetch("/show", path="Data/Weapons/WEAPON_EVIL.txt", **{"as": "toml"})
        self.assertEqual(weapon.count("<script"), 1)

    def test_show_rejects_a_bad_view(self) -> None:
        status, body = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt", **{"as": "yaml"})
        self.assertEqual(status, 400)
        self.assertIn("不是 raw", body)

    def test_show_rejects_missing_entity(self) -> None:
        status, body = self.fetch("/show", path="Data/Weapons/NOPE.txt", **{"as": "toml"})
        self.assertEqual(status, 400)
        self.assertIn("用法错误", body)

    def test_show_rejects_path_traversal(self) -> None:
        for attempt in ("../ModInformation.toml", "..\\ModInformation.toml", "/etc/passwd", "C:/Windows/win.ini"):
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
        self.assertIn("写入由命令自身的门决定", body)

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

    def test_cmd_refuses_only_the_command_that_would_bind_a_port(self) -> None:
        """`web` cannot run inside a request; the writing commands are the command's own call."""
        for line in ("web port=8899", "serve"):
            status, body = self.fetch("/cmd", line=line)
            self.assertEqual(status, 400, line)
            self.assertIn("不能在页面里运行", body, line)

    def test_json_route_also_refuses_web(self) -> None:
        status, body = self.fetch("/json", command="web", port="8899")
        self.assertEqual(status, 400)
        self.assertIn("不能在页面里运行", body)

    def test_a_page_may_run_a_writing_command(self) -> None:
        """The UI can change a project document; the command's own gate still applies."""
        document = PROJECT / "Data" / "Weapons" / "WEAPON_WEB.txt"
        write(document, WEAPON_XML)
        before = document.read_bytes()
        app = App({"workspace": str(WORKSPACE)}, PROJECT, "Mod")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            query = urlencode(
                {
                    "command": "set",
                    "selector": "Data/Weapons/WEAPON_WEB.txt",
                    "field": "name",
                    "value": "Web Pistol",
                    "write": "1",
                }
            )
            with urllib.request.urlopen(f"{base}/json?{query}", timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["written"])
            self.assertIn(b"Web Pistol", document.read_bytes())
            self.assertNotEqual(document.read_bytes(), before)
            without = f"{base}/json?" + urlencode(
                {"command": "set", "selector": "Data/Weapons/WEAPON_WEB.txt", "field": "name", "value": "Nope"}
            )
            try:
                urllib.request.urlopen(without, timeout=20)
                self.fail("a write without the flag was accepted")
            except urllib.error.HTTPError as error:
                self.assertEqual(error.code, 400)
                self.assertIn("set needs --write", error.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            document.unlink(missing_ok=True)

    def test_a_page_may_build_a_package_without_writing_it(self) -> None:
        """`pack` runs from a page too; its own gates decide what reaches the disk."""
        write(PROJECT / "ModInformation.toml", '[mod]\n\tname = "Web Mod"\n\tversion_name = "0.0.1"\n')
        (PROJECT / "Data").mkdir(parents=True, exist_ok=True)
        app = App({"workspace": str(WORKSPACE)}, PROJECT, "Mod")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            query = urlencode({"command": "pack", "write": "1", "dry-run": "1"})
            with urllib.request.urlopen(f"{base}/json?{query}", timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["archive"].endswith("Web Mod-0.0.1.zip"))
            self.assertFalse(Path(payload["archive"]).exists(), "a dry run wrote the archive")
            without = f"{base}/json?" + urlencode({"command": "pack"})
            try:
                urllib.request.urlopen(without, timeout=20)
                self.fail("pack without the flag was accepted")
            except urllib.error.HTTPError as error:
                self.assertEqual(error.code, 400)
                self.assertIn("pack needs --write", error.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    # --- editing, the event log and the operation page ----------------------

    @contextlib.contextmanager
    def running(self, root: Path):
        """Serve a second app whose default scope is a real project directory."""
        app = App({"workspace": str(WORKSPACE)}, root, "Mod")
        server = make_server(app, 0)
        server.quiet = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    @staticmethod
    def fetch_from(base: str, route: str = "", **params) -> tuple[int, str]:
        """GET a route of a server other than the class-wide one."""
        url = base + route
        if params:
            url += "?" + urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def fetch_asset(self, route: str = "/asset", etag: str = "", **params) -> tuple[int, bytes, dict]:
        """GET an asset and return the raw bytes with the response headers.

        The body is not decoded: an asset is a file, and a decoding step would hide
        both a wrong content type and a truncated file.
        """
        url = self.base + route + ("?" + urlencode(params) if params else "")
        request = urllib.request.Request(url, headers={"If-None-Match": etag} if etag else {})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_edit_lists_every_field_of_a_document(self) -> None:
        status, body = self.fetch("/edit", path="Data/Weapons/WEAPON_PISTOL_P38.txt")
        self.assertEqual(status, 200, body[:400])
        self.assertIn('<form method="get" action="/edit">', body)
        for field in ("name", "type", "shoot.sound_shoot", "ammo.type.0.flavour"):
            self.assertIn(field, body)
        self.assertIn("P38 Pistol", body)

    def test_edit_asks_for_a_document_before_listing_fields(self) -> None:
        status, body = self.fetch("/edit")
        self.assertEqual(status, 200)
        self.assertIn('name="path"', body)
        self.assertNotIn("当前值", body)

    def test_edit_saves_one_field_through_the_operation_page(self) -> None:
        """Each row posts to /ops, so the write still passes the operation page's check."""
        _, body = self.fetch("/edit", path="Data/Weapons/WEAPON_PISTOL_P38.txt")
        self.assertIn('action="/ops"', body)
        for name in ("command", "selector", "field", "value"):
            self.assertIn(f'name="{name}"', body)

    def test_the_log_page_carries_the_undo_and_redo_forms(self) -> None:
        status, body = self.fetch("/log")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("事件日志", body)
        self.assertIn("撤销与重做", body)
        self.assertIn('name="count"', body)

    def test_ops_lists_every_writing_command(self) -> None:
        status, body = self.fetch("/ops")
        self.assertEqual(status, 200, body[:400])
        for command in ("set", "add", "remove", "index", "convert", "settings", "export", "pack", "init", "undo", "redo"):
            self.assertIn(f"command={command}", body, f"/ops does not offer {command}")

    def test_ops_rejects_a_command_that_cannot_write(self) -> None:
        status, body = self.fetch("/ops", command="rmdir")
        self.assertEqual(status, 400)
        self.assertIn("没有这条写入命令", body)

    def test_the_check_step_shows_the_line_and_writes_nothing(self) -> None:
        """The check runs the command with --dry-run, so the page can promise nothing was written."""
        project = SCRATCH / "ops-project"
        shutil.rmtree(project, ignore_errors=True)
        write(project / "ModInformation.toml", '[mod]\n\tname = "Ops Mod"\n\tversion_name = "0.0.1"\n')
        document = project / "Data" / "Weapons" / "WEAPON_OPS.txt"
        write(document, WEAPON_XML)
        before = document.read_bytes()
        try:
            with self.running(project) as base:
                asked = {"command": "set", "selector": "Data/Weapons/WEAPON_OPS.txt",
                         "field": "name", "value": "Ops Pistol", "confirm": "1"}
                status, body = self.fetch_from(base, "/ops", **asked)
                self.assertEqual(status, 200, body[:400])
                self.assertIn("--write --dry-run", body)
                self.assertIn("尚未写入", body)
                self.assertIn("write=1", body)
                self.assertEqual(document.read_bytes(), before, "the check step wrote the document")
                status, body = self.fetch_from(base, "/ops", **asked, write="1")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("写入结果", body)
                self.assertIn(b"Ops Pistol", document.read_bytes())
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_refused_check_offers_no_write_link(self) -> None:
        """A refusal is a normal outcome of a check, not an error page."""
        project = SCRATCH / "ops-refused"
        shutil.rmtree(project, ignore_errors=True)
        write(project / "ModInformation.toml", '[mod]\n\tname = "Refused Mod"\n')
        (project / "Data").mkdir(parents=True, exist_ok=True)
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/ops", command="undo", count="1", confirm="1")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("there is no change to undo", body)
                self.assertIn("命令拒绝了这次检查", body)
                self.assertNotIn("write=1", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    # --- ports and the running-instance record ------------------------------

    def test_free_port_skips_a_port_that_is_taken(self) -> None:
        taken = self.server.server_port
        self.assertTrue(server.port_is_taken(taken))
        self.assertFalse(server.port_is_taken(0))
        chosen = server.free_port(taken)
        self.assertNotEqual(chosen, taken)
        self.assertFalse(server.port_is_taken(chosen))
        self.assertEqual(server.free_port(0), 0)

    def test_a_recorded_instance_is_reused_instead_of_starting_a_second_server(self) -> None:
        root = SCRATCH / "editor-root"
        record = {"pid": 4321, "host": "127.0.0.1", "port": self.server.server_port, "url": self.base + "/", "scope": "Firefight"}
        server.write_instance(root, record)
        try:
            self.assertEqual(server.read_instance(root), record)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(server, "state_root", lambda cwd: root):
                address = server.serve({}, root, "Firefight")
            self.assertEqual(address, self.base + "/")
            self.assertIn("已有实例在运行", out.getvalue())
            self.assertIn(f"pid {record['pid']}", out.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_stale_record_does_not_block_a_new_server(self) -> None:
        root = SCRATCH / "editor-stale"
        dead = server.free_port(self.server.server_port + 1)
        server.write_instance(root, {"pid": 1, "port": dead, "url": f"http://127.0.0.1:{dead}/"})
        try:
            self.assertIsNone(server.read_instance(root), "a dead record must not look alive")
            self.assertFalse(server.answers(f"http://127.0.0.1:{dead}/", timeout=0.2))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_instance_record_is_only_cleared_by_its_owner(self) -> None:
        root = SCRATCH / "editor-owner"
        mine = {"pid": 11, "port": 1, "url": "http://127.0.0.1:1/"}
        other = {"pid": 22, "port": 2, "url": "http://127.0.0.1:2/"}
        try:
            server.write_instance(root, mine)
            server.clear_instance(root, other)
            self.assertTrue(server.instance_path(root).is_file(), "another owner's record was removed")
            server.clear_instance(root, mine)
            self.assertFalse(server.instance_path(root).is_file())
            server.clear_instance(root, mine)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_state_root_is_the_editor_folder_when_there_is_one(self) -> None:
        self.assertEqual(server.state_root(WORKSPACE), server._editor_root(WORKSPACE))
        record = server.instance_path(WORKSPACE)
        self.assertEqual(record.name, "web.json")
        self.assertEqual(record.parent.name, "EditorCache")

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

    def test_pages_carry_one_inline_script_and_load_nothing(self) -> None:
        """The workbench script is the only one, and it is inline: no outside file is fetched."""
        for route in ("/", "/list", "/find", "/deps", "/check", "/stats", "/edit", "/log", "/ops", "/help", "/quit"):
            _, body = self.fetch(route)
            self.assertEqual(body.count("<script"), 1, f"{route} does not carry exactly one script")
            self.assertNotIn("<script src", body, f"{route} loads an outside script")
            self.assertNotIn("<link", body, f"{route} loads an outside style sheet")

    def test_a_page_can_ask_for_the_document_pane_alone(self) -> None:
        """The tab strip fetches this fragment and drops it into the pane it already has."""
        _, full = self.fetch("/list")
        status, fragment = self.fetch("/list", pane="doc")
        self.assertEqual(status, 200)
        self.assertNotIn("<script", fragment)
        self.assertNotIn("<html", fragment)
        self.assertIn('<div class="doc-body">', full)
        self.assertNotIn('<div class="doc-body">', fragment)
        self.assertLess(len(fragment), len(full))

    # --- the tree and the property pane -------------------------------------

    def test_the_tree_groups_documents_by_their_folders(self) -> None:
        """A folder per level, each with its file count, and links nested under it."""
        _, body = self.fetch("/", scope="Firefight")
        self.assertIn('<details class="tree-dir" open>', body)
        self.assertIn("Weapons", body)
        self.assertIn("2 项", body)
        self.assertIn("WEAPON_PISTOL_P38.txt", body)
        self.assertIn("6 个文件", body)

    def test_the_tree_lists_the_plain_text_tables_too(self) -> None:
        """An equipment list is a document a person edits, so the tree offers it."""
        _, body = self.fetch("/", scope="Firefight")
        self.assertIn("equipment_american_WW2.txt", body)

    def test_the_property_pane_lists_the_selected_document(self) -> None:
        """The pane reads the same payload `get` returns, and links into the field editor."""
        _, body = self.fetch("/show", path="Data/Weapons/WEAPON_PISTOL_P38.txt")
        self.assertIn("当前文档", body)
        self.assertIn("P38 Pistol", body)
        self.assertIn("/edit?", body)
        self.assertIn("ff Firefight get Data/Weapons/WEAPON_PISTOL_P38.txt --json", body)

    def test_the_property_pane_asks_for_a_document_first(self) -> None:
        _, body = self.fetch("/")
        self.assertIn("从左边打开一个文件", body)

    def test_the_workbench_face_and_size_come_from_the_stylesheet(self) -> None:
        """The narrow industrial face and the larger base size, both in one place."""
        _, body = self.fetch("/")
        self.assertIn("--font: Tahoma", body)
        self.assertIn("--size: 15px", body)
        self.assertIn("font-size: var(--size)", body)

    def test_the_tree_carries_a_search_box(self) -> None:
        """One field in the tree pane, and every file carries the path the script filters on."""
        _, body = self.fetch("/", scope="Firefight")
        self.assertIn('data-filter="tree"', body)
        self.assertIn('name="q"', body)
        self.assertIn('<div class="tree-file" data-path="Data/Weapons/WEAPON_PISTOL_P38.txt">', body)

    def test_the_tree_shows_only_what_the_search_matched(self) -> None:
        """The query is answered on the server as well, so the page works without the script."""
        _, body = self.fetch("/", scope="Firefight", q="equipment_american")
        self.assertIn("equipment_american_WW2.txt", body)
        self.assertNotIn("WEAPON_PISTOL_P38.txt", body)
        self.assertIn("6 个文件里有 1 个匹配 equipment_american。", body)

    def test_a_search_that_matches_nothing_says_so(self) -> None:
        _, body = self.fetch("/", scope="Firefight", q="nothing-like-this")
        self.assertIn("没有匹配 nothing-like-this 的文件。", body)
        self.assertNotIn("WEAPON_PISTOL_P38.txt", body)

    def test_the_search_offers_the_same_search_on_the_list_page(self) -> None:
        _, body = self.fetch("/", scope="Firefight", q="weapon")
        self.assertIn("在列表页里搜索", body)
        self.assertIn("/list?selector=weapon", body)

    def test_the_search_form_carries_the_scope_and_not_a_query(self) -> None:
        """The tree form obeys the same rule as every other form on the page."""
        _, body = self.fetch("/", scope="Firefight")
        search = re.search(r'<form[^>]*class="tree-search"[^>]*action="([^"]*)"', body)
        self.assertIsNotNone(search, "the tree pane has no search form")
        self.assertEqual(search.group(1), "/")
        self.assertIn('<input type="hidden" name="scope" value="Firefight">', body)

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
        for route in ("/", "/find", "/get", "/deps", "/edit", "/ops", "/quit"):
            _, body = self.fetch(route)
            for action in re.findall(r'<form[^>]*action="([^"]*)"', body):
                self.assertNotIn("?", action, f"{route} form action still carries a query: {action}")

    def test_a_page_never_spells_a_parameter_twice(self) -> None:
        """The carried scope must not be repeated by a field of the form itself."""
        for route in ("/find", "/deps", "/edit", "/quit"):
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


    # --- the interface language ---------------------------------------------

    # a language is named in its own language, so these stay as they are in either mode
    LANGUAGE_NAMES = {"中文", "English"}

    @staticmethod
    def templates() -> set[str]:
        """Every template the web layer hands to tr() as a literal."""
        found = set()
        for path in sorted(Path(server.__file__).parent.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "tr":
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    found.add(node.args[0].value)
        return found

    def test_every_template_has_an_english_entry(self) -> None:
        missing = sorted(text for text in self.templates() if text not in i18n.ENGLISH)
        self.assertEqual(missing, [], "no English wording for these templates")

    def test_an_unused_entry_is_reported_as_well(self) -> None:
        known = self.templates()
        unused = sorted(text for text in i18n.ENGLISH if text not in known)
        self.assertEqual(unused, [], "these entries match no template in the server")

    def test_the_pages_are_chinese_by_default(self) -> None:
        status, body = self.fetch("/help")
        self.assertEqual(status, 200)
        self.assertIn("页面与等价命令", body)
        self.assertIn('lang="zh-CN"', body)

    def test_a_page_can_be_asked_for_in_english(self) -> None:
        status, body = self.fetch("/help", lang="en")
        self.assertEqual(status, 200)
        self.assertIn("Pages and their equivalent commands", body)
        self.assertIn('lang="en"', body)
        self.assertNotIn("页面与等价命令", body)

    def test_a_second_page_follows_the_same_language(self) -> None:
        status, body = self.fetch("/list", lang="en")
        self.assertEqual(status, 200)
        self.assertIn("entity file(s)", body)

    def test_links_keep_the_language(self) -> None:
        status, body = self.fetch("/help", lang="en")
        self.assertEqual(status, 200)
        self.assertIn("lang=en", body)

    def test_a_language_the_server_does_not_know_is_refused(self) -> None:
        status, body = self.fetch("/help", lang="de")
        self.assertEqual(status, 400)
        self.assertIn("lang=", body)

    # --- the assets: pictures and sounds the browser draws itself ------------

    def test_asset_route_serves_a_picture_with_its_own_type(self) -> None:
        status, body, headers = self.fetch_asset(path="Images/units/rifleman.png")
        self.assertEqual(status, 200)
        self.assertEqual(body, PICTURE)
        self.assertEqual(headers.get("Content-Type"), "image/png")
        self.assertTrue(headers.get("ETag"))

    def test_a_sound_gets_the_audio_type(self) -> None:
        status, body, headers = self.fetch_asset(path="Sounds/shoot_pistol.ogg")
        self.assertEqual(status, 200)
        self.assertEqual(body, SOUND)
        self.assertEqual(headers.get("Content-Type"), "audio/ogg")

    def test_asset_route_answers_304_when_the_file_has_not_changed(self) -> None:
        _status, _body, headers = self.fetch_asset(path="Images/units/rifleman.png")
        status, body, _headers = self.fetch_asset(path="Images/units/rifleman.png", etag=headers["ETag"])
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")

    def test_asset_route_refuses_a_path_outside_the_project(self) -> None:
        for outside in ("../ModInformation.toml", "../../stock/Images/units/rifleman.png", "/etc/passwd"):
            with self.subTest(path=outside):
                status, _body, _headers = self.fetch_asset(path=outside)
                self.assertEqual(status, 404, outside)

    def test_asset_route_answers_404_for_a_file_that_is_not_there(self) -> None:
        status, body, _headers = self.fetch_asset(path="Images/units/no-such-picture.png", lang="en")
        self.assertEqual(status, 404)
        self.assertIn("no such file", body.decode("utf-8"))

    def test_asset_route_refuses_a_folder(self) -> None:
        status, body, _headers = self.fetch_asset(path="Images", lang="en")
        self.assertEqual(status, 400)
        self.assertIn("is a folder", body.decode("utf-8"))

    def test_asset_route_needs_a_path(self) -> None:
        status, _body, _headers = self.fetch_asset()
        self.assertEqual(status, 400)

    def test_the_assets_page_draws_the_pictures_and_the_sounds(self) -> None:
        status, body = self.fetch("/assets")
        self.assertEqual(status, 200, body[:400])
        self.assertIn('class="thumb"', body)
        self.assertIn("<audio", body)
        # the tile points at the asset route, so the browser asks for the file itself
        self.assertIn("/asset?path=Images%2Funits%2Frifleman.png", body)
        self.assertIn("shoot_pistol.ogg", body)
        # a .txt inside Images is not something a browser can draw
        self.assertNotIn("notes.txt", body)

    def test_the_tree_offers_the_asset_folders(self) -> None:
        status, body = self.fetch("/index")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("folder=Images", body)
        self.assertIn("folder=Sounds", body)

    def test_a_field_that_names_a_picture_is_previewed(self) -> None:
        with self.running(MEDIA) as base:
            status, body = self.fetch_from(base, "/show", path="Data/Weapons/WEAPON_PREVIEW.txt")
            self.assertEqual(status, 200, body[:400])
            self.assertIn('class="preview"', body)
            self.assertIn("/asset?path=Images%2Funits%2Frifleman.png", body)

    def test_a_field_that_names_a_file_that_is_not_there_is_not_previewed(self) -> None:
        with self.running(MEDIA) as base:
            status, body = self.fetch_from(base, "/show", path="Data/Weapons/WEAPON_MISSING.txt")
            self.assertEqual(status, 200, body[:400])
            self.assertNotIn('class="preview"', body)

    # --- the plain-text tables ----------------------------------------------

    def table_project(self) -> Path:
        """A project whose settings declare one table, with two rows to change."""
        project = SCRATCH / "table-project"
        shutil.rmtree(project, ignore_errors=True)
        write(project / "ModInformation.toml", '[mod]\n\tname = "Table Mod"\n\tversion_name = "0.0.1"\n')
        write(project / "ModSetting.toml", '[mod]\n\tname = "Table Mod"\n\tequipment = ["equipment_demo.txt"]\n')
        write(project / "Data/Weapons/WEAPON_TABLE.txt", WEAPON_XML)
        write(project / "Data/equipment_demo.txt", "// demo list\nRifle Squad.txt\n")
        return project

    def test_the_table_page_lists_the_rows_of_a_declared_table(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/tables", path="Data/equipment_demo.txt")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("// demo list", body)
                self.assertIn("Rifle Squad.txt", body)
                self.assertIn("追加一行", body)
                self.assertIn('name="value"', body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_table_page_asks_for_a_table_first(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/tables")
                self.assertEqual(status, 200, body[:400])
                self.assertIn('name="path"', body)
                self.assertIn("equipment_demo.txt", body, "a declared table is not offered")
                self.assertNotIn("追加一行", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_row_is_rewritten_only_after_the_check_step(self) -> None:
        """The check step stages the change without writing, as the operation page does."""
        project = self.table_project()
        document = project / "Data" / "equipment_demo.txt"
        before = document.read_bytes()
        try:
            with self.running(project) as base:
                asked = {"path": "Data/equipment_demo.txt", "op": "set", "line": "2",
                         "value": "Marksman.txt", "confirm": "1"}
                status, body = self.fetch_from(base, "/tables", **asked)
                self.assertEqual(status, 200, body[:400])
                self.assertIn("操作后", body)
                self.assertIn("Marksman.txt", body)
                self.assertIn("actor=web", body)
                self.assertIn("尚未写入", body)
                self.assertEqual(document.read_bytes(), before, "the check step wrote the table")
                status, body = self.fetch_from(base, "/tables", **asked, write="1")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("写入结果", body)
                written = document.read_text("cp1252")
                self.assertIn("Marksman.txt", written)
                self.assertIn("// demo list", written, "the comment row was lost")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_row_can_be_appended_and_deleted(self) -> None:
        project = self.table_project()
        document = project / "Data" / "equipment_demo.txt"
        try:
            with self.running(project) as base:
                asked = {"path": "Data/equipment_demo.txt", "op": "add", "value": "Sniper.txt", "confirm": "1"}
                status, body = self.fetch_from(base, "/tables", **asked, write="1")
                self.assertEqual(status, 200, body[:400])
                self.assertEqual(document.read_text("cp1252"), "// demo list\nRifle Squad.txt\nSniper.txt\n")
                asked = {"path": "Data/equipment_demo.txt", "op": "delete", "line": "2", "confirm": "1"}
                status, body = self.fetch_from(base, "/tables", **asked, write="1")
                self.assertEqual(status, 200, body[:400])
                self.assertEqual(document.read_text("cp1252"), "// demo list\nSniper.txt\n")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_log_names_the_web_as_the_actor(self) -> None:
        """A write that came from a page is recorded as ``web``, not as ``cli``."""
        project = self.table_project()
        try:
            with self.running(project) as base:
                asked = {"path": "Data/equipment_demo.txt", "op": "set", "line": "2",
                         "value": "Marksman.txt", "confirm": "1", "write": "1"}
                self.fetch_from(base, "/tables", **asked)
                status, body = self.fetch_from(base, "/json", command="log", actor="web")
                self.assertEqual(status, 200, body[:400])
                events = json.loads(body)["events"]
                self.assertEqual([event["document"] for event in events], ["Data/equipment_demo.txt"])
                self.assertEqual([event["result"] for event in events], ["set"])
                status, body = self.fetch_from(base, "/json", command="log", actor="cli")
                self.assertEqual(status, 200, body[:400])
                self.assertEqual(json.loads(body)["events"], [])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_undo_puts_a_table_row_back(self) -> None:
        project = self.table_project()
        document = project / "Data" / "equipment_demo.txt"
        before = document.read_bytes()
        try:
            with self.running(project) as base:
                asked = {"path": "Data/equipment_demo.txt", "op": "set", "line": "2",
                         "value": "Marksman.txt", "confirm": "1", "write": "1"}
                self.fetch_from(base, "/tables", **asked)
                self.assertNotEqual(document.read_bytes(), before)
                status, body = self.fetch_from(base, "/ops", command="undo", count="1", confirm="1", write="1")
                self.assertEqual(status, 200, body[:400])
                self.assertEqual(document.read_bytes(), before, "undo did not restore the table")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_file_that_is_not_a_declared_table_is_refused(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/tables", path="Data/Weapons/WEAPON_TABLE.txt")
                self.assertEqual(status, 400)
                self.assertIn("不是工程设置的表格文件", body)
                status, body = self.fetch_from(base, "/tables", path="../ModInformation.toml")
                self.assertEqual(status, 400)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_table_row_number_that_is_not_there_is_refused(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                asked = {"path": "Data/equipment_demo.txt", "op": "delete", "line": "99", "confirm": "1"}
                status, body = self.fetch_from(base, "/tables", **asked)
                self.assertEqual(status, 400)
                self.assertIn("line 99", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_show_page_links_a_table_to_its_row_editor(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/show", path="Data/equipment_demo.txt")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("/tables?path=Data%2Fequipment_demo.txt", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    # --- the source page -----------------------------------------------------

    def test_the_source_page_shows_a_document_as_its_own_text(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/source", path="Data/Weapons/WEAPON_TABLE.txt")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("<textarea", body)
                self.assertIn("WEAPON_TABLE", body)
                self.assertIn("体检", body, "the check result is not on the page")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_source_page_asks_for_a_document_first(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/source")
                self.assertEqual(status, 200, body[:400])
                self.assertIn('name="path"', body)
                self.assertNotIn("<textarea", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_source_save_writes_nothing_before_the_write_step(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        before = document.read_bytes()
        try:
            with self.running(project) as base:
                edited = WEAPON_XML.replace("P38 Pistol", "P38 Carbine")
                status, body = self.fetch_from(base, "/source", path="Data/Weapons/WEAPON_TABLE.txt", text=edited, confirm="1")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("尚未写入", body)
                self.assertEqual(document.read_bytes(), before, "the check step wrote the file")
                self.assertNotIn("写入结果", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_source_save_writes_and_is_recorded_as_the_web(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        before = document.read_bytes()
        try:
            with self.running(project) as base:
                edited = WEAPON_XML.replace("P38 Pistol", "P38 Carbine")
                asked = {"path": "Data/Weapons/WEAPON_TABLE.txt", "text": edited, "confirm": "1", "write": "1"}
                status, body = self.fetch_from(base, "/source", **asked)
                self.assertEqual(status, 200, body[:400])
                self.assertIn("写入结果", body)
                self.assertIn("写入之后", body, "the check result after the write is missing")
                self.assertNotEqual(document.read_bytes(), before)
                self.assertIn(b"P38 Carbine", document.read_bytes())
                status, log = self.fetch_from(base, "/json", command="log", actor="web")
                events = json.loads(log)["events"]
                self.assertEqual([event["document"] for event in events], ["Data/Weapons/WEAPON_TABLE.txt"])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_source_save_keeps_the_line_endings_of_the_file(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        crlf = WEAPON_XML.replace("\n", "\r\n").encode("utf-8")
        document.write_bytes(crlf)
        try:
            with self.running(project) as base:
                edited = WEAPON_XML.replace("P38 Pistol", "P38 Carbine")
                asked = {"path": "Data/Weapons/WEAPON_TABLE.txt", "text": edited, "confirm": "1", "write": "1"}
                status, body = self.fetch_from(base, "/source", **asked)
                self.assertEqual(status, 200, body[:400])
                after = document.read_bytes()
                self.assertIn(b"\r\n", after)
                # every line ends CRLF: after removing them no bare LF may be left
                self.assertNotIn(b"\n", after.replace(b"\r\n", b""))
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_source_save_keeps_a_byte_order_mark(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        document.write_bytes(b"\xef\xbb\xbf" + WEAPON_XML.encode("utf-8"))
        try:
            with self.running(project) as base:
                edited = WEAPON_XML.replace("P38 Pistol", "P38 Carbine")
                asked = {"path": "Data/Weapons/WEAPON_TABLE.txt", "text": edited, "confirm": "1", "write": "1"}
                status, body = self.fetch_from(base, "/source", **asked)
                self.assertEqual(status, 200, body[:400])
                self.assertTrue(document.read_bytes().startswith(b"\xef\xbb\xbf"), "the BOM was dropped")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_source_save_that_changes_nothing_offers_no_write(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                asked = {"path": "Data/Weapons/WEAPON_TABLE.txt", "text": WEAPON_XML, "confirm": "1"}
                status, body = self.fetch_from(base, "/source", **asked)
                self.assertEqual(status, 200, body[:400])
                self.assertIn("没有变化", body)
                self.assertNotIn("写入结果", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_source_page_refuses_a_suffix_it_does_not_edit(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/source", path="ModInformation.toml")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("<textarea", body, "a TOML project file is not editable")
                status, body = self.fetch_from(base, "/source", path="Data/Weapons/WEAPON_TABLE.txt")
                self.assertEqual(status, 200)
                status, body = self.fetch_from(base, "/source", path="README.md")
                self.assertEqual(status, 400)
                self.assertIn("源码页只打开", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_source_page_refuses_a_path_outside_the_project(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                # the sibling project really exists; the point is that it is not this one
                status, body = self.fetch_from(base, "/source", path="../project/ModInformation.toml")
                self.assertEqual(status, 400, body[:400])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_source_page_refuses_a_document_over_the_limit(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_DOCUMENT.txt"
        document.write_text("<weapon>\n" + "x" * 17000 + "\n</weapon>\n", encoding="utf-8")
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/source", path="Data/Weapons/WEAPON_DOCUMENT.txt")
                self.assertEqual(status, 400, body[:400])
                self.assertIn("16000", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_show_page_links_a_source_document(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/show", path="Data/Weapons/WEAPON_TABLE.txt")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("/source?path=Data%2FWeapons%2FWEAPON_TABLE.txt", body)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    # --- the MCP panel ------------------------------------------------------

    def test_the_mcp_page_lists_every_registered_tool(self) -> None:
        status, body = self.fetch("/mcp")
        self.assertEqual(status, 200, body[:400])
        for spec in specs.TOOLS:
            self.assertIn(specs.exposed_name(spec.name), body)
        self.assertIn("python -m core.mcp", body)
        self.assertIn("--write", body)
        self.assertIn('name="tool"', body)
        self.assertIn('name="arguments"', body)

    def test_the_mcp_page_carries_the_english_wording(self) -> None:
        status, body = self.fetch("/mcp", lang="en")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("trial run", body)
        self.assertIn("read only", body)

    def test_a_read_only_trial_answers_json_rpc(self) -> None:
        status, body = self.fetch("/mcp", tool="mcp_ff_stats", arguments='{"scope": "Firefight"}')
        self.assertEqual(status, 200, body[:400])
        # the answer is printed in a <pre>, so its quotes arrive escaped
        self.assertIn("&quot;jsonrpc&quot;: &quot;2.0&quot;", body)
        self.assertIn("&quot;isError&quot;: false", body, body[-1200:])

    def test_a_tool_that_is_not_registered_is_reported(self) -> None:
        status, body = self.fetch("/mcp", tool="mcp_ff_nope", arguments="{}")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("没有这个工具", body)

    def test_arguments_that_are_not_json_are_reported(self) -> None:
        status, body = self.fetch("/mcp", tool="mcp_ff_list", arguments="not json")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("参数不是 JSON", body)

    def test_a_writing_tool_trial_checks_instead_of_writing(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        before = document.read_bytes()
        arguments = json.dumps(
            {"scope": "Mod", "selector": "Data/Weapons/WEAPON_TABLE.txt", "field": "name", "value": "P38 Carbine"}
        )
        try:
            with self.running(project) as base:
                status, body = self.fetch_from(base, "/mcp", tool="mcp_ff_set", arguments=arguments)
                self.assertEqual(status, 200, body[:400])
                self.assertIn("dryRun", body)
                self.assertIn("什么也没有写", body)
                self.assertIn("按原样再跑一次", body)
                self.assertEqual(document.read_bytes(), before, "the trial wrote the file")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_writing_tool_trial_writes_only_when_told_to(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        before = document.read_bytes()
        arguments = json.dumps(
            {"scope": "Mod", "selector": "Data/Weapons/WEAPON_TABLE.txt", "field": "name", "value": "P38 Carbine"}
        )
        try:
            with self.running(project) as base:
                asked = {"tool": "mcp_ff_set", "arguments": arguments, "confirm": "1", "write": "1"}
                status, body = self.fetch_from(base, "/mcp", **asked)
                self.assertEqual(status, 200, body[:400])
                self.assertIn("写入已经发生", body)
                self.assertNotEqual(document.read_bytes(), before)
                # the call goes through the same journal as every other write, under actor=mcp
                status, log = self.fetch_from(base, "/json", command="log", actor="mcp")
                self.assertEqual(status, 200, log[:400])
                events = json.loads(log)["events"]
                self.assertEqual([event["document"] for event in events], ["Data/Weapons/WEAPON_TABLE.txt"])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    # --- the optional MCP listener -----------------------------------------

    def no_redirect(self) -> urllib.request.OpenerDirector:
        """An opener that reports a 302 instead of following it."""
        return urllib.request.build_opener(_NoRedirect)

    def status_of(self, opener: urllib.request.OpenerDirector, url: str) -> tuple[int, str]:
        try:
            with opener.open(url, timeout=20) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def free_port(self) -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def call_listener(self, url: str, message: dict, token: str = "") -> tuple[int, str]:
        """POST one JSON-RPC message at the listener, as an MCP client would."""
        request = urllib.request.Request(url, data=json.dumps(message).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("X-Ff-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def tool_names_of(self, answer: str) -> list[str]:
        return [tool["name"] for tool in json.loads(answer)["result"]["tools"]]

    def test_the_panel_opens_and_closes_the_listener(self) -> None:
        port = self.free_port()
        status, _ = self.status_of(self.no_redirect(), f"{self.base}/mcpstart?host=local&port={port}")
        self.assertEqual(status, 302)
        state = self.app.mcp.state()
        self.assertEqual(state["port"], port)
        self.assertTrue(state["token"])

        status, page = self.fetch("/mcp")
        self.assertEqual(status, 200, page[:400])
        self.assertIn(state["url"], page)
        self.assertIn(state["token"], page)
        self.assertIn("关闭监听", page)

        status, answer = self.call_listener(
            state["url"], {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, state["token"]
        )
        self.assertEqual(status, 200, answer[:200])
        self.assertEqual(self.tool_names_of(answer),
                         [specs.exposed_name(spec.name) for spec in specs.registered(write=False)])

        # the token is its own door: without it nothing is answered, and it serves only messages
        status, _ = self.call_listener(state["url"], {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(status, 403)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(state["url"], timeout=20)
        self.assertEqual(caught.exception.code, 405)

        status, _ = self.status_of(self.no_redirect(), f"{self.base}/mcpstop")
        self.assertEqual(status, 302)
        self.assertEqual(self.app.mcp.state(), {})
        self.assertIn("现在没有在监听。", self.fetch("/mcp")[1])
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1).close()

    def test_the_listener_registers_the_writing_tools_only_when_asked(self) -> None:
        port = self.free_port()
        status, _ = self.status_of(self.no_redirect(),
                                   f"{self.base}/mcpstart?host=local&port={port}&write=1")
        self.assertEqual(status, 302)
        state = self.app.mcp.state()
        self.assertTrue(state["write"])
        status, answer = self.call_listener(
            state["url"], {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, state["token"]
        )
        self.assertEqual(status, 200, answer[:200])
        names = self.tool_names_of(answer)
        self.assertEqual(sorted(names), sorted(specs.exposed_name(spec.name) for spec in specs.registered(write=True)))
        self.assertIn(specs.exposed_name("ff_set"), names)
        self.app.mcp.stop()

    def test_the_listener_refuses_a_port_that_is_taken(self) -> None:
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen(1)
            port = taken.getsockname()[1]
            status, body = self.status_of(self.no_redirect(), f"{self.base}/mcpstart?host=local&port={port}")
        self.assertEqual(status, 400)
        self.assertIn("监听打不开", body)
        self.assertEqual(self.app.mcp.state(), {})

    def test_the_listener_refuses_a_bind_address_it_does_not_know(self) -> None:
        status, body = self.status_of(self.no_redirect(),
                                      f"{self.base}/mcpstart?host=everywhere&port={self.free_port()}")
        self.assertEqual(status, 400)
        self.assertIn("local 或 lan", body)
        self.assertEqual(self.app.mcp.state(), {})

    # --- the status bar and the bottom pane ---------------------------------

    def test_the_status_bar_carries_the_project_counts(self) -> None:
        payload = self.payload(command="check", scope="Firefight")
        status, body = self.fetch("/")
        self.assertEqual(status, 200, body[:400])
        self.assertIn(f"文件 {payload['files']}", body)
        self.assertIn(f"错误 {len(payload['errors'])}", body)
        self.assertIn(f"悬空 {payload['dangling_total']}", body)

    def test_the_status_bar_dates_the_counts_it_shows(self) -> None:
        # A check parses every document in the project, so the pane holds the result for a few
        # seconds; the time it was taken is printed, which keeps a held number visibly dated.
        first = re.search(r"as of ([0-9]{2}:[0-9]{2}:[0-9]{2})", self.fetch("/", lang="en")[1])
        self.assertIsNotNone(first, "the status bar does not date its counts")
        second = re.search(r"as of ([0-9]{2}:[0-9]{2}:[0-9]{2})", self.fetch("/list", lang="en")[1])
        self.assertIsNotNone(second, "the second page has no counts")
        self.assertEqual(first.group(1), second.group(1), "the second page ran its own check")

    def test_the_bottom_pane_starts_with_no_command(self) -> None:
        status, body = self.fetch("/")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("本次会话还没有运行过命令", body)

    def test_the_bottom_pane_keeps_the_last_command(self) -> None:
        status, body = self.fetch("/cmd", line="stats")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("最近一次命令", body)
        # another page still shows it: the pane belongs to the session, not to one page
        status, body = self.fetch("/list")
        self.assertEqual(status, 200, body[:400])
        self.assertIn("Firefight stats", body)
        self.assertIn("file(s)", body)
        self.assertIn("重跑", body)

    def test_the_bottom_pane_still_lists_the_event_log(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                # a value with a space is quoted as a whole token: the line reader keeps quotes
                # only where a word starts with one
                line = 'set Data/Weapons/WEAPON_TABLE.txt field=name "value=P38 Carbine" --write'
                status, body = self.fetch_from(base, "/cmd", line=line)
                self.assertEqual(status, 200, body[:400])
                status, body = self.fetch_from(base, "/")
                self.assertEqual(status, 200, body[:400])
                self.assertIn("事件日志", body)
                self.assertRegex(body, r"\d{8}T\d{6}:\d+")
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_write_from_the_command_line_is_recorded_as_the_web(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        try:
            with self.running(project) as base:
                line = 'set Data/Weapons/WEAPON_TABLE.txt field=name "value=P38 Carbine" --write'
                status, body = self.fetch_from(base, "/cmd", line=line)
                self.assertEqual(status, 200, body[:400])
                status, body = self.fetch_from(base, "/json", command="log", actor="web")
                self.assertEqual(status, 200, body[:400])
                events = json.loads(body)["events"]
                self.assertEqual([event["result"] for event in events], ["set"])
                self.assertEqual([event["document"] for event in events], ["Data/Weapons/WEAPON_TABLE.txt"])
                self.assertIn(b"P38 Carbine", document.read_bytes())
                status, body = self.fetch_from(base, "/json", command="log", actor="cli")
                self.assertEqual(status, 200, body[:400])
                self.assertEqual(json.loads(body)["events"], [])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_a_write_from_the_operation_page_is_recorded_as_the_web(self) -> None:
        project = self.table_project()
        try:
            with self.running(project) as base:
                asked = {"command": "set", "selector": "Data/Weapons/WEAPON_TABLE.txt",
                         "field": "name", "value": "P38 Carbine", "confirm": "1", "write": "1"}
                status, body = self.fetch_from(base, "/ops", **asked)
                self.assertEqual(status, 200, body[:400])
                status, body = self.fetch_from(base, "/json", command="log", actor="web")
                events = json.loads(body)["events"]
                self.assertEqual([event["result"] for event in events], ["set"])
                status, body = self.fetch_from(base, "/json", command="log", actor="cli")
                self.assertEqual(json.loads(body)["events"], [])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_json_link_of_a_write_previews_it(self) -> None:
        project = self.table_project()
        document = project / "Data" / "Weapons" / "WEAPON_TABLE.txt"
        try:
            with self.running(project) as base:
                line = 'set Data/Weapons/WEAPON_TABLE.txt field=name "value=P38 Carbine" --write'
                status, body = self.fetch_from(base, "/cmd", line=line)
                self.assertEqual(status, 200, body[:400])
                written = document.read_bytes()
                self.assertIn(b"P38 Carbine", written)
                # the link that reads like a read must not write a second time
                found = re.search(r'href="(/json\?[^"]*dry-run[^"]*)"', body)
                self.assertIsNotNone(found, "the JSON link of a write carries no dry run")
                link = found.group(1).replace("&amp;", "&")
                # the link belongs to this project's server, not to the class-wide one
                status, body = self.fetch_from(base, link)
                self.assertEqual(status, 200, f"{link} :: {body.split('</style>', 1)[-1][:400]}")
                self.assertEqual(json.loads(body)["dry_run"], True)
                self.assertEqual(document.read_bytes(), written)
                events = json.loads(self.fetch_from(base, "/json", command="log")[1])["events"]
                self.assertEqual([event["result"] for event in events], ["set"])
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_the_english_wording_never_keeps_chinese(self) -> None:
        for route in ("", "/list", "/find", "/stats", "/check", "/assets", "/tables", "/source", "/mcp", "/help", "/cmd", "/quit"):
            status, body = self.fetch(route, lang="en")
            self.assertEqual(status, 200, route)
            found = sorted(set(re.findall(r"[\u4e00-\u9fff]+", body)) - self.LANGUAGE_NAMES)
            # the fixture data carries no Chinese, so any of it left is an untranslated string
            self.assertEqual(found, [], f"{route} still shows Chinese in English mode")


if __name__ == "__main__":
    unittest.main()
