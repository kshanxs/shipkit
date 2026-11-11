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
            ("switchboard/scripts/kit.py", ["plan", "break", "--tier", "full"]),
            ("switchboard/scripts/kit.py", ["auto", "--request", "run shipkit"]),
        ):
            done = subprocess.run([sys.executable, str(self.target / ".claude/skills" / script), *args], capture_output=True, text=True, cwd=self.target, env=env)
            self.assertEqual(done.returncode, 0, f"{script}: {done.stdout}{done.stderr}")

    def test_a_partial_install_always_brings_the_router(self) -> None:
        result = install(self.target, "--agents", "--skills", "docsync,harden")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        names = sorted(p.parent.name for p in (self.target / ".agents/skills").glob("*/SKILL.md"))
        self.assertEqual(names, ["docsync", "harden", "profile", "switchboard"])
        self.assertFalse((self.target / ".claude").exists())

    def test_a_kit_brings_the_skills_it_runs(self) -> None:
        result = install(self.target, "--claude", "--skills", "kit-break")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        names = sorted(p.parent.name for p in (self.target / ".claude/skills").glob("*/SKILL.md"))
        self.assertEqual(names, ["bug-sweep", "docsync", "harden", "kit-break", "load-sim", "perf-watch", "profile", "ship-check", "switchboard", "triage-report"])
        self.assertTrue((self.target / ".claude/commands/break.md").exists())

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

    def test_the_config_is_written_from_what_the_project_is(self) -> None:
        for path, text in {
            "server/pyproject.toml": '[project]\nname = "x"\ndependencies = ["fastapi"]\n',
            "server/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "web/package.json": '{"name": "web", "private": true, "devDependencies": {"vite": "7"}}\n',
            "web/vite.config.ts": "export default {}\n",
        }.items():
            (self.target / path).parent.mkdir(parents=True, exist_ok=True)
            (self.target / path).write_text(text)
        result = install(self.target, "--claude")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = (self.target / "shipkit.toml").read_text()
        self.assertIn('api_dir = "server"', config)
        self.assertIn('web_dirs = ["web"]', config)
        self.assertIn('money = "none"', config)
        self.assertIn('tenancy = "single-user"', config)
        self.assertIn("tiers = []", config)
        self.assertNotIn("Enterprise", config)
        self.assertIn("/profile", result.stdout)

    def test_the_saas_preset_is_opt_in(self) -> None:
        result = install(self.target, "--claude", "--preset", "saas")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.target / "shipkit.toml").read_text(), (REPO / "shipkit.example.toml").read_text())
        self.assertNotEqual(install(self.target, "--preset", "enterprise").returncode, 0)

    def test_dry_run_changes_nothing(self) -> None:
        result = install(self.target, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
