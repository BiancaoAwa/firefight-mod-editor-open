"""Temporary files of the packager under tools/FirefightModPackager.

The packager is not part of the editor core: these tests cover only the temporary-file
contract, which needs no Android SDK and no APK.
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGER = ROOT / "tools" / "FirefightModPackager"
sys.path.insert(0, str(PACKAGER))

import ffpack                                        # noqa: E402


class PackagerTempFileTest(unittest.TestCase):
    def test_the_helper_returns_a_fresh_empty_file(self):
        path = ffpack._new_temp_path(".xml")
        try:
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith(".xml"))
            self.assertEqual(os.path.getsize(path), 0)
        finally:
            os.remove(path)

    def test_two_calls_do_not_share_a_path(self):
        first = ffpack._new_temp_path(".xml")
        second = ffpack._new_temp_path(".xml")
        try:
            self.assertNotEqual(first, second)
        finally:
            os.remove(first)
            os.remove(second)

    def test_no_module_asks_for_a_predictable_temp_file(self):
        """`mktemp` names a path without creating it; the file may already be there."""
        named = []
        for path in sorted(PACKAGER.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "mktemp(" in text or "tempnam(" in text:
                named.append(path.relative_to(PACKAGER).as_posix())
        self.assertEqual(named, [])
