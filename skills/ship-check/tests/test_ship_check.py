"""ship_check.py: the scaffold from the example checklist, and the rules a filled report is held to."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ship_check.py"


class ShipCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        for path, text in {
            "app/audit.py": "def record(): ...\n",
            "app/rate_limit.py": "LIMIT = 100\n",
            ".github/workflows/ci.yml": "on: push\n",
            "docs/testing/bug_report.md": "# Bugs\n",
        }.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-qm", "start"], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.folder.cleanup()

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=self.root, env={**os.environ, "SHIPKIT_ROOT": str(self.root)})

    def scaffold(self) -> str:
        result = self.run_script("scaffold", "--out", "report.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        return (self.root / "report.md").read_text()

    def test_the_scaffold_has_every_section_the_sha_and_files_to_read(self) -> None:
        text = self.scaffold()
        for heading in ("## 1. Operator capabilities", "## 2. Onboarding flows", "## 3. Status checklist", "## 4. Pricing", "## 5. Bugs and risks", "## Top 5 before launch"):
            self.assertIn(heading, text)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True).stdout.strip()
        self.assertIn(f"`{sha}`", text)
        self.assertIn("`app/audit.py`", text)
        self.assertIn("| Rate limiting | UNKNOWN |", text)

    def test_an_untouched_scaffold_passes_the_check(self) -> None:
        self.scaffold()
        result = self.run_script("check", "report.md")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_done_needs_a_path_that_exists_and_words_are_fixed(self) -> None:
        text = self.scaffold()
        text = text.replace("| Audit logging | UNKNOWN | |", "| Audit logging | DONE | |", 1)
        text = text.replace("| Rate limiting | UNKNOWN | |", "| Rate limiting | PARTIAL | `app/ratelimit.py:3` |", 1)
        text = text.replace("| Metrics | UNKNOWN | |", "| Metrics | Done | `app/audit.py` |", 1)
        (self.root / "report.md").write_text(text)
        out = self.run_script("check", "report.md").stdout
        self.assertIn("Audit logging is DONE with no path as evidence", out)
        self.assertIn("cites `app/ratelimit.py`, which does not exist", out)
        self.assertIn("`Done` is not one of DONE, PARTIAL, MISSING, UNKNOWN", out)
        fixed = text.replace("| Audit logging | DONE | |", "| Audit logging | DONE | `app/audit.py:1` |").replace("app/ratelimit.py:3", "app/rate_limit.py:1").replace("| Metrics | Done |", "| Metrics | MISSING |")
        (self.root / "report.md").write_text(fixed)
        self.assertEqual(self.run_script("check", "report.md").returncode, 0)

    def test_capabilities_use_their_own_words(self) -> None:
        text = self.scaffold().replace("| Audit log | UNKNOWN | |", "| Audit log | PRESENT | `app/audit.py` |", 1)
        (self.root / "report.md").write_text(text)
        self.assertEqual(self.run_script("check", "report.md").returncode, 0)

    def test_a_report_without_its_sha_or_top_five_fails(self) -> None:
        (self.root / "report.md").write_text("# Readiness\n\n| Item | Status | Evidence | Note |\n|---|---|---|---|\n")
        out = self.run_script("check", "report.md").stdout
        self.assertIn("head SHA", out)
        self.assertIn("Top 5", out)

    def test_installed_skill_folders_are_not_project_evidence(self) -> None:
        for folder in (".claude/skills/docsync", ".agents/skills/docsync", ".trae/skills/docsync", "tools/skills/docsync"):
            target = self.root / folder / "references"
            target.mkdir(parents=True)
            (target / "config.md").write_text("# Config\n")
            (target / "audit.py").write_text("def record(): ...\n")
        (self.root / "tools/skills/docsync/.shipkit").write_text("shipkit 0.1.0\n")
        text = self.scaffold()
        for folder in (".claude/", ".agents/", ".trae/", "tools/skills/"):
            self.assertNotIn(f"`{folder}", text)
        self.assertIn("`app/audit.py`", text)
        cited = text.replace("| Audit logging | UNKNOWN | |", "| Audit logging | DONE | `.claude/skills/docsync/references/audit.py` |", 1)
        (self.root / "report.md").write_text(cited)
        out = self.run_script("check", "report.md").stdout
        self.assertIn("cites `.claude/skills/docsync/references/audit.py`, an installed skill, not project evidence", out)

    def test_a_repository_with_no_commits_says_so_and_passes(self) -> None:
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        root = Path(empty.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        env = {**os.environ, "SHIPKIT_ROOT": str(root)}
        made = subprocess.run([sys.executable, str(SCRIPT), "scaffold", "--out", "report.md"], capture_output=True, text=True, cwd=root, env=env)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(made.stderr, "")
        text = (root / "report.md").read_text()
        self.assertIn("Audited: `main`, no commits yet, on ", text)
        self.assertNotIn("not a git checkout", text)
        checked = subprocess.run([sys.executable, str(SCRIPT), "check", "report.md"], capture_output=True, text=True, cwd=root, env=env)
        self.assertEqual(checked.returncode, 0, checked.stdout)
        self.assertNotIn("<sha>", checked.stdout)

    def test_a_folder_that_is_not_a_git_checkout_says_so_and_passes(self) -> None:
        plain = tempfile.TemporaryDirectory()
        self.addCleanup(plain.cleanup)
        root = Path(plain.name)
        (root / "package.json").write_text('{"name": "vite-app"}\n')
        env = {**os.environ, "SHIPKIT_ROOT": str(root), "GIT_CEILING_DIRECTORIES": str(root.parent)}
        made = subprocess.run([sys.executable, str(SCRIPT), "scaffold", "--out", "report.md"], capture_output=True, text=True, cwd=root, env=env)
        self.assertEqual(made.returncode, 0, made.stderr)
        text = (root / "report.md").read_text()
        self.assertIn("Audited: not a git checkout (no branch or SHA to record), on ", text)
        self.assertNotIn("`unknown`", text)
        checked = subprocess.run([sys.executable, str(SCRIPT), "check", "report.md"], capture_output=True, text=True, cwd=root, env=env)
        self.assertEqual(checked.returncode, 0, checked.stdout)
        self.assertIn("note: report.md audits a folder with no git history; there is no head SHA to record", checked.stdout)
        self.assertNotIn("head SHA audited is not written", checked.stdout)

    def test_init_copies_the_checklist_and_scaffold_uses_it(self) -> None:
        self.assertEqual(self.run_script("init").returncode, 0)
        path = self.root / "ship-check.toml"
        path.write_text(path.read_text().replace('name = "Example SaaS"', 'name = "Widget Cloud"'))
        self.assertIn("# Launch readiness: Widget Cloud", self.scaffold())


if __name__ == "__main__":
    unittest.main()
