"""The combined commands: build, audit, adopt, unpack and run."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path(__file__).resolve().parent / "_scratch_combined"

WEAPON = """<weapon>
\t<name>Probe Rifle</name>
\t<type>WEAPON_PISTOL</type>
</weapon>
"""


def run(*argv: str, cwd: Path) -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    done = subprocess.run(
        [sys.executable, "-m", "core.cli", *argv],
        cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return done.returncode, done.stdout, done.stderr


def run_json(*argv: str, cwd: Path) -> tuple[int, dict, str]:
    code, out, err = run(*argv, "--json", cwd=cwd)
    try:
        return code, json.loads(out), err
    except ValueError:
        return code, {}, err


class CombinedTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        SCRATCH.mkdir(parents=True)
        self.project = SCRATCH / "project"
        code, out, err = run("Mod", "init", f"root={self.project}", "name=Combined", "--write",
                             cwd=SCRATCH)
        self.assertEqual(code, 0, out + err)
        weapons = self.project / "Data" / "Weapons"
        weapons.mkdir(parents=True, exist_ok=True)
        (weapons / "WEAPON_A.txt").write_text(WEAPON, encoding="cp1252", newline="")
        self.out = SCRATCH / "out"

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def test_build_runs_the_three_steps_without_writing_under_dry_run(self) -> None:
        code, payload, err = run_json("Mod", "build", f"root={self.project}", f"to={self.out}",
                                      "--write", "--dry-run", cwd=SCRATCH)
        self.assertEqual(code, 0, err)
        self.assertEqual([step["command"] for step in payload["steps"]],
                         ["index", "check", "pack"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(self.out.exists())

    def test_build_writes_the_archive(self) -> None:
        code, payload, err = run_json("Mod", "build", f"root={self.project}", f"to={self.out}",
                                      "--write", cwd=SCRATCH)
        self.assertEqual(code, 0, err)
        self.assertFalse(payload["dry_run"])
        self.assertTrue(list(self.out.glob("*.zip")))

    def test_build_needs_a_destination(self) -> None:
        code, _, err = run("Mod", "build", f"root={self.project}", "--write", cwd=SCRATCH)
        self.assertEqual(code, 2)
        self.assertIn("build needs a destination directory", err)

    def test_audit_runs_verify_then_check(self) -> None:
        code, payload, err = run_json("Mod", "audit", f"root={self.project}", cwd=SCRATCH)
        self.assertEqual(code, 0, err + str(payload))
        self.assertEqual([step["command"] for step in payload["steps"]], ["verify", "check"])

    def test_unpack_exports_without_writing_under_dry_run(self) -> None:
        target = SCRATCH / "unpacked"
        code, payload, err = run_json("Mod", "unpack", f"root={self.project}", f"to={target}",
                                      "--write", "--dry-run", cwd=SCRATCH)
        self.assertEqual(code, 0, err)
        self.assertEqual([step["command"] for step in payload["steps"]], ["export"])
        self.assertFalse(target.exists())

    def test_run_follows_the_step_file(self) -> None:
        steps = SCRATCH / "steps.toml"
        steps.write_text(
            '[[step]]\ncommand = "check"\n\n[[step]]\ncommand = "verify"\n',
            encoding="utf-8", newline="",
        )
        code, payload, err = run_json("Mod", "run", str(steps), f"root={self.project}", cwd=SCRATCH)
        self.assertEqual(code, 0, err)
        self.assertEqual([step["command"] for step in payload["steps"]], ["check", "verify"])
        self.assertTrue(payload["ok"])

    def test_run_stops_at_a_step_that_fails(self) -> None:
        steps = SCRATCH / "steps.toml"
        steps.write_text(
            '[[step]]\ncommand = "set"\nselector = "Data/Weapons/WEAPON_A.txt"\n'
            'with = ["field=nope", "value=x"]\n\n[[step]]\ncommand = "check"\n',
            encoding="utf-8", newline="",
        )
        code, payload, err = run_json("Mod", "run", str(steps), f"root={self.project}",
                                      "--write", cwd=SCRATCH)
        self.assertEqual(code, 1, err)
        self.assertEqual([step["command"] for step in payload["steps"]], ["set"])
        self.assertEqual(payload["stopped"], "set")

    def test_run_refuses_a_step_with_an_unknown_command(self) -> None:
        steps = SCRATCH / "steps.toml"
        steps.write_text('[[step]]\ncommand = "nope"\n', encoding="utf-8", newline="")
        code, _, err = run("Mod", "run", str(steps), f"root={self.project}", cwd=SCRATCH)
        self.assertEqual(code, 2)
        self.assertIn("no command 'nope'", err)

    def test_run_needs_a_step_file(self) -> None:
        code, _, err = run("Mod", "run", f"root={self.project}", cwd=SCRATCH)
        self.assertEqual(code, 2)
        self.assertIn("run needs a step file", err)


if __name__ == "__main__":
    unittest.main()
