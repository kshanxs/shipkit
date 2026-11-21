"""install.sh --global, its opt-in hooks, and doctor.py, in a throwaway HOME."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills/switchboard/scripts"
SKILLS = sorted(p.parent.name for p in (REPO / "skills").glob("*/SKILL.md"))


class Global(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.home = Path(self.dir.name) / "home with space"
        (self.home / ".claude").mkdir(parents=True)
        self.env = {**os.environ, "HOME": str(self.home)}
        self.env.pop("SHIPKIT_ROOT", None)
        self.env.pop("CLAUDE_PROJECT_DIR", None)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def install(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(REPO / "install.sh"), "--global", *args], env=self.env, capture_output=True, text=True)

    def tree(self) -> dict[str, str]:
        out = {}
        for path in sorted(self.home.rglob("*")):
            out[str(path)] = os.readlink(path) if path.is_symlink() else (path.read_text() if path.is_file() else "dir")
        return out

    def test_installs_every_skill_and_a_second_run_changes_nothing(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(sorted(p.name for p in (self.home / ".claude/skills").iterdir()), SKILLS)
        self.assertTrue((self.home / ".claude/commands/cli.md").exists())
        before = self.tree()
        self.assertIn("changed 0 item", self.install().stdout)
        self.assertEqual(self.tree(), before)

    def test_dry_run_changes_nothing(self) -> None:
        before = self.tree()
        self.assertEqual(self.install("--dry-run", "--hooks").returncode, 0)
        self.assertEqual(self.tree(), before)

    def test_never_replaces_a_users_own_skill(self) -> None:
        mine = self.home / ".claude/skills/harden"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("mine")
        result = self.install()
        self.assertIn("is not shipkit's", result.stdout)
        self.assertEqual((mine / "SKILL.md").read_text(), "mine")

    def test_hooks_keep_other_settings_and_uninstall_restores_them(self) -> None:
        settings = self.home / ".claude/settings.json"
        original = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}
        settings.write_text(json.dumps(original))
        self.assertEqual(self.install("--hooks").returncode, 0)
        self.install("--hooks")
        data = json.loads(settings.read_text())
        self.assertEqual(sum("global_hook.py" in h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]), 1)
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(json.loads(settings.read_text()), original)
        self.assertEqual(list((self.home / ".claude/skills").iterdir()), [])

    def test_a_broken_settings_file_stops_before_any_change(self) -> None:
        (self.home / ".claude/settings.json").write_text("{broken")
        before = self.tree()
        self.assertEqual(self.install("--hooks").returncode, 1)
        self.assertEqual(self.tree(), before)

    def hook(self, project: Path, prompt: str) -> str:
        env = {**self.env, "CLAUDE_PROJECT_DIR": str(project)}
        done = subprocess.run([sys.executable, str(SCRIPTS / "global_hook.py"), "route"], input=json.dumps({"prompt": prompt}), env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_the_hook_acts_only_in_a_project_that_opted_in(self) -> None:
        project = Path(self.dir.name) / "project"
        project.mkdir()
        self.assertEqual(self.hook(project, "/harden the login"), "")
        (project / "shipkit.toml").write_text("")
        self.assertIn("harden", self.hook(project, "/harden the login"))
        (project / ".claude/skills/switchboard").mkdir(parents=True)
        self.assertEqual(self.hook(project, "/harden the login"), "")

    def test_doctor_json_is_clean_and_names_the_install_state(self) -> None:
        done = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--json"], env=self.env, cwd=self.home, capture_output=True, text=True)
        data = json.loads(done.stdout)
        rows = {r["check"]: r["status"] for r in data["checks"]}
        self.assertEqual(rows["python"], "ok")
        self.assertEqual(rows["claude_skills"], "warn")
        self.install()
        done = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--json"], env=self.env, cwd=self.home, capture_output=True, text=True)
        self.assertEqual({r["check"]: r["status"] for r in json.loads(done.stdout)["checks"]}["claude_skills"], "ok")

    def test_doctor_finds_a_tool_in_the_users_own_bin(self) -> None:
        tool = self.home / ".local/bin/shellcheck"
        tool.parent.mkdir(parents=True)
        tool.write_text("#!/bin/sh\n")
        tool.chmod(0o755)
        env = {**self.env, "PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin"}
        done = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--json"], env=env, cwd=self.home, capture_output=True, text=True)
        self.assertEqual({r["check"]: r["status"] for r in json.loads(done.stdout)["checks"]}["shellcheck"], "ok")


if __name__ == "__main__":
    unittest.main()
