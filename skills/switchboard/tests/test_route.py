"""route.py: which skills a request gets, the checks on skills.toml, and every skill resolving.

    uv run pytest skills/switchboard
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import route  # noqa: E402

EXPECTED = {
    "stack-backend", "stack-web", "stack-native", "wire-api", "seedbed", "fanout", "harden", "bug-sweep",
    "load-sim", "perf-watch", "triage-report", "ship-check", "docsync", "feature-map", "open-loops", "handoff", "switchboard",
    "kit-build", "kit-break", "kit-flow", "kit-feature", "autopilot",
}  # fmt: skip


def names(text: str) -> list[str]:
    return [p.skill.name for p in route.route(text)]


class Picking(unittest.TestCase):
    def test_a_short_name_with_at_names_the_skill_first(self):
        self.assertEqual(names("@docs sync the docs after the billing fix")[0], "docsync")
        self.assertEqual(names("please @seed the projects and @web their page")[:2], ["seedbed", "stack-web"])

    def test_a_slash_command_at_the_start_names_the_skill(self):
        picks = route.route("/api add an endpoint for invoices")
        self.assertEqual(picks[0].skill.name, "stack-backend")
        self.assertTrue(picks[0].named)

    def test_an_email_address_is_not_a_short_name(self):
        self.assertNotIn("stack-backend", names("write to admin@api.example"))

    def test_triggers_pick_skills(self):
        self.assertIn("feature-map", names("what is left in the Pro tier?"))
        self.assertIn("fanout", names("build search and billing in parallel"))
        self.assertIn("open-loops", names("Q-012: who pays the card fee"))
        self.assertIn("harden", names("harden the checkout endpoint against double submit"))
        self.assertIn("stack-native", names("the Expo app crashes on Android"))
        self.assertIn("stack-web", names("the vite+ build fails"))
        self.assertIn("ship-check", names("are we ready to launch?"))

    def test_a_path_picks_the_skill_that_owns_it(self):
        self.assertIn("stack-backend", names("change apps/api/app/billing/refunds.py"))
        self.assertIn("stack-web", names("the bug is in apps/web/src/app/nav.ts"))

    def test_a_code_skill_brings_docsync(self):
        picks = {p.skill.name: p for p in route.route("/api add an endpoint")}
        self.assertEqual(picks["docsync"].companion_of, "stack-backend")

    def test_short_replies_get_nothing(self):
        for text in ("yes", "commit", "do it", "thanks", "continue"):
            self.assertEqual(names(text), [], text)

    def test_the_hook_answers_in_claude_codes_format_and_is_silent_without_a_match(self):
        for prompt, expect in (("fix the sidebar component", True), ("yes", False)):
            out = io.StringIO()
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": prompt}))), redirect_stdout(out):
                self.assertEqual(route.hook(), 0)
            if expect:
                context = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
                self.assertIn("stack-web (web)", context)
            else:
                self.assertEqual(out.getvalue(), "")


class Checking(unittest.TestCase):
    def test_every_skill_is_catalogued_and_installed(self):
        self.assertEqual(set(route.load()), EXPECTED)

    def test_the_repository_is_in_step(self):
        self.assertEqual(route.check(route.load()), [])

    def test_every_skill_and_short_name_resolves(self):
        lines, ok = route.resolve_all(route.load())
        self.assertTrue(ok, "\n".join(lines))
        self.assertEqual(len(lines), len(EXPECTED))

    def test_a_short_name_used_twice_or_hiding_a_built_in_is_refused(self):
        skills = route.load()
        skills["feature-map"] = replace(skills["feature-map"], short=["docs", "help"])
        errors = "\n".join(route.check(skills))
        self.assertIn("'docs' is also docsync's", errors)
        self.assertIn("hides Claude Code's /help", errors)

    def test_a_skill_missing_from_skills_toml_is_reported(self):
        skills = route.load()
        del skills["handoff"]
        self.assertTrue(any("handoff" in e for e in route.check(skills)))


class Installed(unittest.TestCase):
    """The router inside a project, as install.sh leaves it: only the installed skills, commands in .claude/commands."""

    def test_a_partial_install_routes_and_checks_only_what_is_there(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            target = project / ".claude" / "skills"
            for name in ("switchboard", "docsync", "harden"):
                shutil.copytree(SKILLS / name, target / name, ignore=shutil.ignore_patterns("tests", "__pycache__"))
            script = target / "switchboard" / "scripts" / "route.py"
            env = {"PATH": "/usr/bin:/bin"}
            wrote = subprocess.run([sys.executable, str(script), "--write"], capture_output=True, text=True, env=env, cwd=project)
            self.assertEqual(wrote.returncode, 0, wrote.stdout + wrote.stderr)
            self.assertTrue((project / ".claude/commands/docs.md").exists())
            self.assertFalse((project / ".claude/commands/api.md").exists())
            checked = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, env=env, cwd=project)
            self.assertEqual(checked.returncode, 0, checked.stdout)
            self.assertIn("3 skills", checked.stdout)
            resolved = subprocess.run([sys.executable, str(script), "--resolve"], capture_output=True, text=True, env=env, cwd=project)
            self.assertEqual(resolved.returncode, 0, resolved.stdout)
            picked = subprocess.run([sys.executable, str(script), "add an endpoint for invoices"], capture_output=True, text=True, env=env, cwd=project)
            self.assertNotIn("stack-backend", picked.stdout)


if __name__ == "__main__":
    unittest.main()
