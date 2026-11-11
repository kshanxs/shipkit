"""ship_check.py: the scaffold from the example checklist, and the rules a filled report is held to."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ship_check.py"
PROFILE = """[project]
kind = "{kind}"
tenancy = "{tenancy}"
money = "{money}"
plans = "{plans}"
auth = "{auth}"
surfaces = {surfaces}
offline = false
"""
SAAS = PROFILE.format(kind="saas", tenancy="multi-tenant", money="payments", plans="tiers", auth="accounts", surfaces='["api", "web"]')
SELF_HOSTED = PROFILE.format(kind="self-hosted", tenancy="single-user", money="none", plans="none", auth="local", surfaces='["api", "web", "container"]')
LIBRARY = PROFILE.format(kind="library", tenancy="none", money="none", plans="none", auth="none", surfaces='["library"]')


class ShipCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        for path, text in {
            "app/audit.py": "def record(): ...\n",
            "app/rate_limit.py": "LIMIT = 100\n",
            ".github/workflows/ci.yml": "on: push\n",
            "docs/testing/bug_report.md": "# Bugs\n",
            "shipkit.toml": SAAS,
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

    def test_init_copies_the_checklist_and_scaffold_uses_it(self) -> None:
        self.assertEqual(self.run_script("init").returncode, 0)
        path = self.root / "ship-check.toml"
        path.write_text(path.read_text().replace('name = "" ', 'name = "Widget Cloud" '))
        self.assertIn("# Launch readiness: Widget Cloud", self.scaffold())


if __name__ == "__main__":
    unittest.main()


class Profiles(ShipCheck):
    """The checklist keeps only what the project profile needs, and says what it left out."""

    def test_a_self_hosted_app_gets_no_billing_tenants_or_pricing(self) -> None:
        (self.root / "shipkit.toml").write_text(SELF_HOSTED)
        text = self.scaffold()
        for absent in ("Billing operations", "Choosing a plan and paying", "Tenant isolation", "## 4. Pricing", "Sign-up and email verification"):
            self.assertNotIn(f"| {absent}", text.replace("## 4. Pricing", "| ## 4. Pricing"))
        self.assertNotIn("## 4. Pricing", text)
        for present in ("DNS rebinding refused", "Cross-site requests refused", "Install and first run", "Data safety for self-hosted users"):
            self.assertIn(present, text)
        self.assertIn("Left out, not in this project's profile:", text)
        self.assertIn("Billing operations (refunds, credits, plan changes) (needs money)", text)

    def test_a_saas_keeps_everything_hosted_and_drops_self_hosted_items(self) -> None:
        text = self.scaffold()
        for present in ("Billing operations", "Tenant isolation", "## 4. Pricing", "Sign-up and email verification"):
            self.assertIn(present, text)
        self.assertNotIn("| DNS rebinding refused", text)
        self.assertNotIn("### Releases and distribution", text)

    def test_a_library_gets_releases_not_operations(self) -> None:
        (self.root / "shipkit.toml").write_text(LIBRARY)
        text = self.scaffold()
        self.assertIn("### Releases and distribution", text)
        self.assertIn("Install and the first import", text)
        for absent in ("### Operations", "### Observability", "| Rate limiting", "| Uptime and health"):
            self.assertNotIn(absent, text)
        self.assertEqual(self.run_script("check", "report.md").returncode, 0)
