"""install.sh into throwaway projects: every layout, a partial install, links, hooks, re-runs and refusals."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
SKILLS = sorted(p.parent.name for p in (REPO / "skills").glob("*/SKILL.md"))


def install(target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(INSTALL), str(target), *args], capture_output=True, text=True)


class Install(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.target = Path(self.dir.name)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_all_layouts_get_every_skill_without_tests_and_the_router_resolves(self) -> None:
        result = install(self.target)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for layout in (".claude", ".agents", ".trae"):
            names = sorted(p.parent.name for p in (self.target / layout / "skills").glob("*/SKILL.md"))
            self.assertEqual(names, SKILLS, layout)
            self.assertFalse(list((self.target / layout / "skills").glob("*/tests")), layout)
            self.assertIn(f"check {layout}: in step, every skill resolves", result.stdout)
        self.assertTrue((self.target / ".claude/commands/docs.md").exists())
        self.assertIn("shipkit:skills:start", (self.target / "AGENTS.md").read_text())
        self.assertIn("`docsync`", (self.target / "AGENTS.md").read_text())
        self.assertTrue((self.target / "shipkit.toml").exists())

    def test_installed_scripts_run_from_the_project(self) -> None:
        install(self.target, "--claude")
        env = {**os.environ}
        env.pop("SHIPKIT_ROOT", None)
        for script, args in (
            ("docsync/scripts/check_docs.py", []),
            ("harden/scripts/matrix.py", ["pairs", "who", "network"]),
            ("load-sim/scripts/sim.py", ["plan", "--scenario", str(self.target / ".claude/skills/load-sim/references/scenario.example.toml"), "--profile", "peak", "--count", "3"]),
            ("ship-check/scripts/ship_check.py", ["scaffold"]),
            ("switchboard/scripts/route.py", ["add an endpoint for invoices"]),
        ):
            done = subprocess.run([sys.executable, str(self.target / ".claude/skills" / script), *args], capture_output=True, text=True, cwd=self.target, env=env)
            self.assertEqual(done.returncode, 0, f"{script}: {done.stdout}{done.stderr}")

    def test_a_partial_install_always_brings_the_router(self) -> None:
        result = install(self.target, "--agents", "--skills", "docsync,harden")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        names = sorted(p.parent.name for p in (self.target / ".agents/skills").glob("*/SKILL.md"))
        self.assertEqual(names, ["docsync", "harden", "switchboard"])
        self.assertFalse((self.target / ".claude").exists())

    def test_link_makes_claude_and_trae_point_at_agents(self) -> None:
        result = install(self.target, "--all", "--link")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        link = self.target / ".claude/skills/docsync"
        self.assertTrue(link.is_symlink())
        self.assertTrue((link / "SKILL.md").exists())

    def test_hooks_are_added_once(self) -> None:
        install(self.target, "--claude", "--hooks")
        install(self.target, "--claude", "--hooks")
        settings = json.loads((self.target / ".claude/settings.json").read_text())
        self.assertEqual(len(settings["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)

    def test_a_skill_shipkit_did_not_install_is_left_alone(self) -> None:
        mine = self.target / ".claude/skills/docsync"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("---\nname: docsync\ndescription: mine\n---\n")
        result = install(self.target, "--claude")
        self.assertIn("skip", result.stdout)
        self.assertEqual((mine / "SKILL.md").read_text(), "---\nname: docsync\ndescription: mine\n---\n")

    def test_an_existing_config_is_kept_and_unknown_skills_are_refused(self) -> None:
        (self.target / "shipkit.toml").write_text("# mine\n")
        install(self.target, "--claude")
        self.assertEqual((self.target / "shipkit.toml").read_text(), "# mine\n")
        self.assertNotEqual(install(self.target, "--skills", "nonsense").returncode, 0)

    def test_dry_run_changes_nothing(self) -> None:
        result = install(self.target, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_dry_run_says_would_and_never_claims_it_wrote(self) -> None:
        result = install(self.target, "--dry-run", "--hooks")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would write shipkit.toml", result.stdout)
        self.assertIn(f"Claude Code: would install {len(SKILLS)} of {len(SKILLS)} skills in .claude/skills", result.stdout)
        for line in result.stdout.splitlines():
            self.assertFalse(line.strip().startswith(("wrote", "installed")) or ": installed" in line, line)
            self.assertNotIn("Done.", line)
        self.assertIn("Dry run: nothing was written.", result.stdout)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_the_count_is_what_was_installed_and_skips_are_listed(self) -> None:
        mine = self.target / ".claude/skills/docsync"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("---\nname: docsync\ndescription: mine\n---\n")
        total = len(SKILLS)
        dry = install(self.target, "--claude", "--dry-run")
        self.assertIn(f"Claude Code: would install {total - 1} of {total} skills in .claude/skills (1 skipped)", dry.stdout)
        result = install(self.target, "--claude")
        self.assertIn(f"Claude Code: installed {total - 1} of {total} skills in .claude/skills (1 skipped)", result.stdout)
        self.assertIn("Skipped (exist and were not installed by shipkit; use --force to replace them):\n  .claude/skills/docsync\n", result.stdout)
        clean = install(self.target, "--agents")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn(f"Cursor / Codex: installed {total} of {total} skills in .agents/skills\n", clean.stdout)
        self.assertNotIn("Skipped", clean.stdout)


if __name__ == "__main__":
    unittest.main()
