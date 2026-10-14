"""Tests for the MCP surface: protocol transcripts, the tool table and the permission gate.

The transcript cases start the server as a subprocess and script its stdin, because the
surface under test is the stdio protocol itself; the remaining cases drive the same server
in process.  The tool table is compared with the plugin table in ``dsh-firefight-mod-tools``
``lib/specs.js`` when that file is reachable, and always with the exact names written down
here, so a rename on either side fails the suite (docs/mcp.md section 8).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from core.cli import specs
from core.mcp import resources, tools
from core.mcp.server import PROTOCOL_VERSIONS, SERVER_NAME, STATELESS_VERSION, Server, parse_argv

REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path(__file__).resolve().parent / "_scratch_mcp"
PROJECT = SCRATCH / "project"
STOCK = SCRATCH / "stock"
BROKEN = SCRATCH / "broken"
OUT = SCRATCH / "out"

WEAPON_XML = """<weapon>
\t<name>Demo Rifle</name>
\t<type>WEAPON_RIFLE</type>
\t<shoot>
\t\t<rof>12</rof>
\t\t<sound_shoot>SOUND_RIFLE</sound_shoot>
\t</shoot>
</weapon>
"""

BROKEN_XML = WEAPON_XML.replace("SOUND_RIFLE", "SOUND_MISSING")

EXPECTED_READ_TOOLS = {
    "ff_list": {"scope": False, "selector": False, "type": False, "root": False, "workspace": False},
    "ff_show": {"scope": False, "selector": True, "as": False, "root": False, "workspace": False},
    "ff_get": {"scope": False, "selector": True, "field": False, "root": False, "workspace": False},
    "ff_find": {
        "scope": False, "selector": False, "tag": False, "value": False, "path": False,
        "ignoreCase": False, "limit": False, "root": False, "workspace": False,
    },
    "ff_stats": {"scope": False, "selector": False, "root": False, "workspace": False},
    "ff_refs": {"scope": False, "selector": True, "kind": False, "root": False, "workspace": False},
    "ff_deps": {"scope": False, "value": True, "kind": False, "root": False, "workspace": False},
    "ff_check": {"scope": False, "selector": False, "root": False, "workspace": False},
}

EXPECTED_WRITE_TOOLS = {
    "ff_export": {
        "scope": False, "selector": False, "to": True, "overwrite": False, "dryRun": False,
        "root": False, "workspace": False,
    },
    "ff_set": {
        "scope": False, "selector": True, "field": True, "value": False, "op": False,
        "from": False, "dryRun": False, "root": False, "workspace": False,
    },
    "ff_add": {
        "scope": False, "selector": True, "type": False, "from": False, "dryRun": False,
        "root": False, "workspace": False,
    },
    "ff_remove": {
        "scope": False, "selector": True, "dryRun": False, "root": False, "workspace": False,
    },
    "ff_index": {
        "scope": False, "selector": False, "dryRun": False, "root": False, "workspace": False,
    },
    "ff_convert": {
        "scope": False, "selector": False, "to": True, "overwrite": False, "dryRun": False,
        "root": False, "workspace": False,
    },
    "ff_settings": {
        "scope": False, "op": False, "overwrite": False, "dryRun": False,
        "root": False, "workspace": False,
    },
    "ff_undo": {
        "scope": False, "count": False, "dryRun": False, "root": False, "workspace": False,
    },
    "ff_redo": {
        "scope": False, "count": False, "dryRun": False, "root": False, "workspace": False,
    },
}

PLUGIN_CANDIDATES = (
    os.environ.get("FIREFIGHT_PLUGIN_SPECS", ""),
    str(REPO.parent / "dsh-firefight-mod-tools" / "lib" / "specs.js"),
    str(REPO.parents[2] / "firefight-mod-editor-open" / "ffplugin" / "lib" / "specs.js"),
)

FIXTURES: dict[str, bytes] = {}
_ENV: dict[str, str | None] = {}


def setUpModule() -> None:
    """Build the scratch scopes once for every class in this module."""
    global _ENV
    shutil.rmtree(SCRATCH, ignore_errors=True)
    _ENV = {name: os.environ.pop(name, None) for name in ("FIREFIGHT_DATA", "FIREFIGHT_MODS")}
    FIXTURES["project/mod.toml"] = b'name = "Mcp Fixture"\n'
    FIXTURES["project/Mod/Data/Weapons/WEAPON_DEMO.txt"] = WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
    FIXTURES["project/Mod/Sounds/SOUND_RIFLE.ogg"] = b"OggS\x00fixture\n"
    FIXTURES["stock/Data/Weapons/WEAPON_STOCK.txt"] = WEAPON_XML.replace("\n", "\r\n").encode("cp1252")
    FIXTURES["broken/mod.toml"] = b'name = "Mcp Broken"\n'
    FIXTURES["broken/Mod/Data/Weapons/WEAPON_BROKEN.txt"] = BROKEN_XML.replace("\n", "\r\n").encode("cp1252")
    write_fixtures()


def tearDownModule() -> None:
    """Drop the scratch scopes and restore the environment."""
    shutil.rmtree(SCRATCH, ignore_errors=True)
    for name, value in _ENV.items():
        if value is not None:
            os.environ[name] = value


def write_fixtures() -> None:
    """Build the scratch scopes the transcript cases run against."""
    for relative, data in FIXTURES.items():
        path = SCRATCH / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    shutil.rmtree(OUT, ignore_errors=True)


def plugin_specs_path() -> Path | None:
    """The plugin's ``lib/specs.js``, when it is reachable from this checkout."""
    for candidate in PLUGIN_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def plugin_table(path: Path) -> dict[str, dict[str, bool]]:
    """Tool name -> parameter name -> required, read out of the plugin's JavaScript table."""
    text = path.read_text(encoding="utf-8")
    constants = dict(re.findall(r"const\s+(\w+)\s*=\s*'(ff_\w+)'", text))
    found: dict[str, dict[str, bool]] = {}
    for match in re.finditer(r"name\s*:\s*'?([\w.]+)'?", text):
        name = constants.get(match.group(1), match.group(1))
        if not name.startswith("ff_"):
            continue
        block = _braced(text, match.end(), "parameters:")
        if block is None:
            continue
        found[name] = _parameters(block)
    return found


def _braced(text: str, start: int, key: str) -> str | None:
    """The text inside the first ``{...}`` after ``key``, or ``None`` when it is missing."""
    at = text.find(key, start)
    if at < 0:
        return None
    opening = text.find("{", at)
    if opening < 0:
        return None
    depth = 0
    index = opening
    while index < len(text):
        char = text[index]
        if char == "'":
            end = text.find("'", index + 1)
            index = len(text) if end < 0 else end + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
        index += 1
    return None


def _parameters(block: str) -> dict[str, bool]:
    """Parameter names and required flags of one ``parameters: {...}`` block."""
    found: dict[str, bool] = {}
    depth = 0
    index = 0
    current: str | None = None
    buffer: list[str] = []
    while index < len(block):
        char = block[index]
        if char == "'":
            end = block.find("'", index + 1)
            index = len(block) if end < 0 else end + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif depth == 0 and (char.isalpha() or char == "_"):
            match = re.match(r"(\w+)\s*:", block[index:])
            if match:
                if current is not None:
                    found[current] = "required: true" in "".join(buffer)
                current = match.group(1)
                buffer = []
                index += match.end()
                continue
        if current is not None:
            buffer.append(char)
        index += 1
    if current is not None:
        found[current] = "required: true" in "".join(buffer)
    return found


def session(messages: list[dict | str], *, cwd: Path = PROJECT, write: bool = False, timeout: int = 120):
    """Run one server subprocess over a scripted stdin; returns the exit code and the answers."""
    script = "".join(message if isinstance(message, str) else json.dumps(message) for message in messages)
    command = [sys.executable, "-m", "core.mcp"] + (["--write"] if write else [])
    environment = dict(os.environ, PYTHONPATH=str(REPO))
    done = subprocess.run(
        command,
        cwd=cwd,
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=timeout,
    )
    answers = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, answers, done.stderr


def call(identifier: int, method: str, params: dict | None = None) -> dict:
    """One JSON-RPC request line."""
    return {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or {}}


class TranscriptTest(unittest.TestCase):
    """The stdio protocol itself, as a subprocess."""

    def setUp(self) -> None:
        write_fixtures()

    def test_the_classic_handshake_and_one_read_call(self) -> None:
        code, answers, err = session(
            [
                json.dumps(call(1, "initialize", {"protocolVersion": "2025-06-18"})) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n",
                json.dumps(call(2, "tools/list")) + "\n",
                json.dumps(call(3, "tools/call", {"name": "ff_show", "arguments": {"scope": "Mod", "selector": "Data/Weapons/WEAPON_DEMO.txt"}})) + "\n",
                json.dumps(call(4, "tools/call", {"name": "ff_export", "arguments": {"scope": "Mod", "to": "out"}})) + "\n",
                "this line is not JSON\n",
            ]
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(answers), 5, "the notification must not be answered")
        self.assertEqual([answer["id"] for answer in answers], [1, 2, 3, 4, None])
        handshake = answers[0]["result"]
        self.assertEqual(handshake["protocolVersion"], "2025-06-18")
        self.assertEqual(handshake["serverInfo"]["name"], SERVER_NAME)
        self.assertIn("tools", handshake["capabilities"])
        names = [tool["name"] for tool in answers[1]["result"]["tools"]]
        self.assertEqual(names, list(EXPECTED_READ_TOOLS))
        shown = answers[2]["result"]
        self.assertFalse(shown["isError"])
        self.assertIn("<name>Demo Rifle</name>", shown["content"][0]["text"])
        self.assertEqual(shown["structuredContent"]["exit_code"], 0)
        self.assertEqual(shown["structuredContent"]["path"], "Data/Weapons/WEAPON_DEMO.txt")
        self.assertEqual(answers[3]["error"]["code"], -32601)
        self.assertIn("ff_export", answers[3]["error"]["message"])
        self.assertEqual(answers[4]["error"]["code"], -32700)
        self.assertFalse(OUT.exists(), "a refused export wrote something")

    def test_the_stateless_revision_carries_its_identity(self) -> None:
        meta = {"io.modelcontextprotocol/protocolVersion": STATELESS_VERSION, "clientInfo": {"name": "test"}}
        code, answers, err = session(
            [
                json.dumps(call(1, "server/discover", {"_meta": meta})) + "\n",
                json.dumps(call(2, "tools/list", {"_meta": meta})) + "\n",
                json.dumps(call(3, "resources/read", {"uri": "firefight://Mod/log", "_meta": meta})) + "\n",
                json.dumps(call(4, "server/discover", {"_meta": {"io.modelcontextprotocol/protocolVersion": "1999-01-01"}})) + "\n",
                json.dumps(call(5, "initialize", {"protocolVersion": "1999-01-01"})) + "\n",
                json.dumps(call(6, "no/such/method")) + "\n",
            ]
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(answers), 6)
        discovered = answers[0]["result"]
        self.assertEqual(discovered["resultType"], "complete")
        self.assertEqual(discovered["_meta"]["serverInfo"]["name"], SERVER_NAME)
        self.assertIn(STATELESS_VERSION, discovered["protocolVersions"])
        for answer in answers[:3]:
            self.assertEqual(answer["result"]["resultType"], "complete")
            self.assertEqual(answer["result"]["_meta"]["serverInfo"], discovered["serverInfo"])
        self.assertEqual(answers[2]["result"]["contents"][0]["uri"], "firefight://Mod/log")
        self.assertEqual(answers[3]["error"]["code"], -32022)
        self.assertEqual(answers[4]["error"]["code"], -32022)
        self.assertEqual(answers[5]["error"]["code"], -32601)

    def test_write_mode_exposes_the_writing_tools_and_refuses_the_stock_scope(self) -> None:
        before = sorted(path.name for path in STOCK.rglob("*"))
        refused_to = SCRATCH / "out-refused"
        code, answers, err = session(
            [
                json.dumps(call(1, "tools/list")) + "\n",
                json.dumps(
                    call(
                        2,
                        "tools/call",
                        {
                            "name": "ff_export",
                            "arguments": {"scope": "Firefight", "root": str(STOCK), "to": str(refused_to)},
                        },
                    )
                )
                + "\n",
                json.dumps(
                    call(
                        3,
                        "tools/call",
                        {"name": "ff_export", "arguments": {"scope": "Mod", "selector": "Data/Weapons", "to": str(OUT)}},
                    )
                )
                + "\n",
                json.dumps(call(4, "tools/call", {"name": "ff_nothing", "arguments": {"scope": "Mod"}})) + "\n",
            ],
            write=True,
        )
        self.assertEqual((code, err), (0, ""))
        names = [tool["name"] for tool in answers[0]["result"]["tools"]]
        self.assertEqual(names, list(EXPECTED_READ_TOOLS) + list(EXPECTED_WRITE_TOOLS))
        self.assertEqual(answers[1]["error"]["code"], -32000)
        self.assertIn("read-only", answers[1]["error"]["message"])
        self.assertEqual(sorted(path.name for path in STOCK.rglob("*")), before)
        self.assertFalse(refused_to.exists(), "the refused export created its destination")
        self.assertFalse(answers[2]["result"]["isError"])
        self.assertEqual(answers[2]["result"]["structuredContent"]["count"], 1)
        self.assertTrue((OUT / "Data" / "Weapons" / "WEAPON_DEMO.txt").is_file())
        self.assertEqual(answers[3]["error"]["code"], -32601, "a tool that is not in the table is unknown")


class ServerTest(unittest.TestCase):
    """The same server driven in process, for the paths a transcript does not need."""

    def setUp(self) -> None:
        write_fixtures()
        self.server = Server(write=False, cwd=PROJECT)
        self.writing = Server(write=True, cwd=PROJECT)

    def test_a_malformed_envelope_is_an_invalid_request(self) -> None:
        cases = (
            ([], None),
            ("text", None),
            ({"jsonrpc": "2.0", "id": 1}, 1),
            ({"jsonrpc": "2.0", "id": 2, "method": "x", "params": 5}, 2),
        )
        for message, identifier in cases:
            answer = self.server.handle(message)
            self.assertEqual(answer["error"]["code"], -32600, message)
            self.assertEqual(answer["id"], identifier, message)

    def test_a_read_tool_call_reports_a_report_as_a_result(self) -> None:
        answer = self.server.handle(call(1, "tools/call", {"name": "ff_check", "arguments": {"scope": "Mod"}}))
        self.assertFalse(answer["result"]["isError"])
        self.assertEqual(answer["result"]["structuredContent"]["exit_code"], 0)
        answer = self.server.handle(call(2, "tools/call", {"name": "ff_list", "arguments": {"scope": "Mod", "type": "weapon"}}))
        self.assertEqual(answer["result"]["structuredContent"]["count"], 1)

    def test_a_command_failure_is_a_tool_result_with_the_exit_code(self) -> None:
        broken = Server(write=False, cwd=BROKEN)
        answer = broken.handle(call(1, "tools/call", {"name": "ff_check", "arguments": {"scope": "Mod"}}))
        self.assertTrue(answer["result"]["isError"])
        self.assertEqual(answer["result"]["structuredContent"]["exit_code"], 1)
        self.assertTrue(answer["result"]["structuredContent"]["dangling"])

    def test_a_bad_parameter_is_an_invalid_params_error(self) -> None:
        answer = self.server.handle(call(1, "tools/call", {"name": "ff_show", "arguments": [1]}))
        self.assertEqual(answer["error"]["code"], -32602)
        answer = self.server.handle(call(2, "tools/call", {"name": "ff_show", "arguments": {"scope": "Nope", "selector": "x"}}))
        self.assertEqual(answer["error"]["code"], -32602)
        answer = self.server.handle(call(3, "tools/call", {"name": "ff_show", "arguments": {"selector": "Data/Weapons/NOPE.txt"}}))
        self.assertEqual(answer["error"]["code"], -32602)
        answer = self.server.handle(call(4, "tools/call", {"arguments": {}}))
        self.assertEqual(answer["error"]["code"], -32602)

    def test_an_unregistered_tool_is_unknown(self) -> None:
        for name in ("ff_nope", "ff_add_thing"):
            answer = self.writing.handle(call(1, "tools/call", {"name": name, "arguments": {}}))
            self.assertEqual(answer["error"]["code"], -32601, name)
        answer = self.server.handle(call(1, "tools/call", {"name": "ff_export", "arguments": {"to": OUT}}))
        self.assertEqual(answer["error"]["code"], -32601)
        answer = self.server.handle(call(1, "tools/call", {"name": "ff_set", "arguments": {}}))
        self.assertEqual(answer["error"]["code"], -32601, "a read-only server does not expose the writing tools")

    def test_resources_and_prompts(self) -> None:
        templates = self.server.handle(call(1, "resources/templates/list"))["result"]["resourceTemplates"]
        self.assertEqual(
            [template["uriTemplate"] for template in templates],
            ["firefight://{scope}/entity/{path}", "firefight://{scope}/list/{category}", "firefight://{scope}/log"],
        )
        listed = self.server.handle(call(2, "resources/list"))["result"]["resources"]
        self.assertIn("firefight://Mod/log", [item["uri"] for item in listed])
        for identifier, uri in enumerate(
            ("firefight://Mod/entity/Data/Weapons/WEAPON_DEMO.txt", "firefight://Mod/list/weapon", "firefight://Mod/log"),
            start=3,
        ):
            answer = self.server.handle(call(identifier, "resources/read", {"uri": uri}))
            contents = answer["result"]["contents"]
            self.assertEqual(contents[0]["uri"], uri)
            self.assertEqual(contents[0]["mimeType"], "text/plain")
        entity = self.server.handle(call(9, "resources/read", {"uri": "firefight://Mod/entity/Data/Weapons/WEAPON_DEMO.txt"}))
        self.assertIn("Demo Rifle", entity["result"]["contents"][0]["text"])
        category = self.server.handle(call(10, "resources/read", {"uri": "firefight://Mod/list/weapon"}))
        self.assertIn("WEAPON_DEMO.txt", category["result"]["contents"][0]["text"])
        for uri in ("http://example.com/x", "firefight://Mod", "firefight://Mod/entity/"):
            answer = self.server.handle(call(11, "resources/read", {"uri": uri}))
            self.assertEqual(answer["error"]["code"], -32602, uri)
        answer = self.server.handle(call(12, "resources/read", {}))
        self.assertEqual(answer["error"]["code"], -32602)
        prompt = resources.prompt(resources.PROMPT_NAME, {"scope": "Mod", "selector": "Data/Weapons", "goal": "raise rof"})
        self.assertIn("Data/Weapons", prompt["messages"][0]["content"]["text"])
        answer = self.server.handle(call(13, "prompts/get", {"name": "nope"}))
        self.assertEqual(answer["error"]["code"], -32601)
        answer = self.server.handle(call(14, "prompts/get", {}))
        self.assertEqual(answer["error"]["code"], -32602)
        listed = self.server.handle(call(15, "prompts/list"))["result"]["prompts"]
        self.assertEqual([item["name"] for item in listed], [resources.PROMPT_NAME])
        self.assertEqual([item["name"] for item in listed[0]["arguments"]], ["scope", "selector", "goal"])

    def test_a_notification_and_a_ping(self) -> None:
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}))
        self.assertEqual(self.server.handle(call(1, "ping"))["result"], {})

    def test_the_command_line_options(self) -> None:
        self.assertEqual(parse_argv([]), ({}, False, False))
        self.assertEqual(parse_argv(["--write", "workspace=Mods"]), ({"write": "1", "workspace": "Mods"}, False, False))
        self.assertEqual(parse_argv(["--help"]), ({}, True, False))
        self.assertEqual(parse_argv(["--version"]), ({}, False, True))
        with self.assertRaises(tools.CallRefused):
            parse_argv(["--nope"])

    def test_the_defaults_reach_the_call(self) -> None:
        server = Server(write=False, defaults={"root": str(STOCK)}, cwd=PROJECT)
        answer = server.handle(call(1, "tools/call", {"name": "ff_list", "arguments": {"scope": "Firefight"}}))
        self.assertFalse(answer["result"]["isError"])
        self.assertEqual(answer["result"]["structuredContent"]["count"], 1)
        self.assertEqual(answer["result"]["structuredContent"]["scope"], "Firefight")

    def test_the_stock_scope_is_reachable_when_the_server_names_its_directory(self) -> None:
        server = Server(write=False, defaults={"firefight": str(STOCK)}, cwd=PROJECT)
        answer = server.handle(call(1, "tools/call", {"name": "ff_stats", "arguments": {"scope": "Firefight"}}))
        self.assertFalse(answer["result"]["isError"])
        self.assertEqual(answer["result"]["structuredContent"]["files"], 1)
        answer = server.handle(call(2, "resources/read", {"uri": "firefight://Firefight/list/weapon"}))
        self.assertIn("WEAPON_STOCK.txt", answer["result"]["contents"][0]["text"])
        answer = server.handle(call(3, "resources/read", {"uri": "firefight://Firefight/log"}))
        self.assertIn("0 record(s)", answer["result"]["contents"][0]["text"])
        refused = self.server.handle(call(4, "resources/read", {"uri": "firefight://Firefight/list/weapon"}))
        self.assertEqual(refused["error"]["code"], -32602, "without a root the stock scope cannot resolve")
        self.assertIn("cannot find the stock Firefight data", refused["error"]["message"])

    def test_the_command_line_defaults_are_parsed(self) -> None:
        options, _, _ = parse_argv(["firefight=D:/game", "workspace=Mods", "--write"])
        self.assertEqual(options, {"firefight": "D:/game", "workspace": "Mods", "write": "1"})


class ToolTableTest(unittest.TestCase):
    """The tool table itself, against the names written down here and against the plugin."""

    def test_the_read_only_surface_is_exact(self) -> None:
        self.assertEqual([spec.name for spec in specs.registered(write=False)], list(EXPECTED_READ_TOOLS))
        self.assertEqual(
            [spec.name for spec in specs.registered(write=True)],
            list(EXPECTED_READ_TOOLS) + list(EXPECTED_WRITE_TOOLS),
        )
        for spec in specs.registered(write=True):
            expected = {**EXPECTED_READ_TOOLS, **EXPECTED_WRITE_TOOLS}[spec.name]
            self.assertEqual({parameter.name: parameter.required for parameter in spec.parameters}, expected, spec.name)
            schema = spec.inputs()
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(list(schema["properties"]), list(expected))
            self.assertEqual(schema["required"], [name for name, required in expected.items() if required])

    def test_the_specifications_match_the_plugin_table(self) -> None:
        path = plugin_specs_path()
        if path is None:
            self.skipTest("dsh-firefight-mod-tools lib/specs.js is not reachable from this checkout")
        table = plugin_table(path)
        self.assertEqual(table, {**EXPECTED_READ_TOOLS, **EXPECTED_WRITE_TOOLS})
        for spec in specs.TOOLS:
            if spec.name not in table:
                self.assertFalse(spec.available, f"{spec.name} is exposed but is not in the plugin table")
                continue
            self.assertEqual(
                {parameter.name: parameter.required for parameter in spec.parameters},
                table[spec.name],
                spec.name,
            )

    def test_the_arguments_become_the_command_line_call(self) -> None:
        show = specs.tool_named("ff_show")
        self.assertEqual(
            show.call({"scope": "Mod", "selector": "Data/Weapons/WEAPON_DEMO.txt", "as": "toml"}),
            ("Mod", "Data/Weapons/WEAPON_DEMO.txt", {"as": "toml"}),
        )
        find = specs.tool_named("ff_find")
        self.assertEqual(find.call({"tag": "flavour", "ignoreCase": True, "limit": 5}), ("Mod", "", {"tag": "flavour", "ignore_case": "1", "limit": "5"}))
        self.assertEqual(find.call({"ignoreCase": False, "root": ""}), ("Mod", "", {"ignore_case": "0"}))
        self.assertEqual(specs.tool_named("ff_deps").call({"value": "WEAPON_PISTOL_P38"}), ("Mod", "", {"value": "WEAPON_PISTOL_P38"}))
        self.assertEqual(specs.tool_named("ff_undo").call({"count": 2}), ("Mod", "2", {}))
        self.assertEqual(specs.tool_named("ff_set").call({"selector": "x", "field": "name", "value": "", "dryRun": True}), ("Mod", "x", {"field": "name", "value": "", "dry-run": "1"}))
        self.assertEqual(specs.tool_named("ff_list").call({"type": "weapon"}, defaults={"workspace": "Mods"}), ("Mod", "", {"type": "weapon", "workspace": "Mods"}))
        self.assertEqual(specs.tool_named("ff_stats").call({"scope": ""}), ("Mod", "", {}))


if __name__ == "__main__":
    unittest.main()
