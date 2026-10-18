"""The command registry: one record per command, grouped by category."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from core import registry
from core.cli import commands

DOCS = Path(__file__).resolve().parent.parent / "docs" / "cli.md"


class RegistryTest(unittest.TestCase):
    """Every command is described once and the three faces read that description."""

    def test_every_command_has_a_category_and_a_summary(self):
        for command in registry.commands():
            with self.subTest(command=command.name):
                self.assertIn(command.category, registry.CATEGORIES)
                self.assertTrue(command.summary.strip())
                self.assertTrue(callable(registry.resolve(command.handler)))

    def test_the_categories_partition_the_commands(self):
        grouped = registry.by_category()
        listed = [member.name for members in grouped.values() for member in members]
        self.assertEqual(sorted(listed), sorted(command.name for command in registry.commands()))
        self.assertEqual(len(listed), len(set(listed)))

    def test_the_dispatcher_table_is_built_from_the_registry(self):
        self.assertEqual(sorted(commands.COMMANDS), sorted(command.name for command in registry.commands()))
        self.assertEqual(commands.ALIASES, registry.aliases())

    def test_aliases_do_not_shadow_a_command(self):
        names = {command.name for command in registry.commands()}
        for alias in registry.aliases():
            self.assertNotIn(alias, names)
            self.assertIsNotNone(registry.get(alias))

    def test_the_writer_list_matches_the_forms(self):
        writers = {command.name for command in registry.commands() if command.writes}
        forms = {command.name for command in registry.commands() if command.web_form}
        self.assertEqual(writers, forms)
        self.assertEqual(len(writers), 19)

    def test_the_tool_table_stays_read_only_for_its_twelve_reads(self):
        exposed = [command for command in registry.commands() if command.mcp]
        self.assertEqual(len(exposed), 31)
        missing = {command.name for command in registry.commands()} - {command.name for command in exposed}
        self.assertEqual(missing, {"doctor", "log", "version", "web"})

    def test_every_command_appears_in_the_cli_document(self):
        text = DOCS.read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `([a-z]+)` \|", text, re.M))
        self.assertEqual(documented, {command.name for command in registry.commands()})

    def test_an_extension_module_can_declare_a_command(self):
        declared = registry.Command(
            name="echo",
            handler="core.commands_ext.echo:run",
            category="inspect",
            summary="Repeat the selector.",
        )
        self.assertEqual(declared.category, "inspect")
        self.assertEqual(declared.aliases, ())
        self.assertFalse(declared.writes)
        self.assertTrue(declared.mcp)


if __name__ == "__main__":
    unittest.main()
