"""Tests for feature_map.py: a small repository that passes, then one thing broken per test."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "feature_map.py"

CATALOG = """# Tree

<!-- counts:start -->
<!-- counts:end -->

<!-- tree:start -->
## Free: record and run

### Billing
- **Invoices** · Built · [Billing](features/billing.md)
- **Online payments** · Partly
  - Pay links · Built
  - Refunds · Planned
- **Data export** · Planned

## Pro: compare and automate

### Workflow
- **Usage alerts** · Built
- **Chat** · Next

## Enterprise: predict and advise

### Analytics
- **Live forecasts** · Coming soon

## Plan to be decided

- **Agent sign-in** · Planned · added 2026-10-08
<!-- tree:end -->
"""

PRICING = """export const COMING_SOON = 'Coming soon'
export const COMPARISON: { group: string; rows: [string, string, string, string][] }[] = [
  {
    group: 'Billing',
    rows: [
      ['Invoices', 'yes', 'yes', 'yes'],
      ['Pay links', 'yes', 'yes', 'yes'],
      ['Data export', COMING_SOON, COMING_SOON, COMING_SOON],
      ['Usage alerts', 'no', 'yes', 'yes'],
      ['Chat', 'no', COMING_SOON, COMING_SOON],
      ['Live forecasts', 'no', 'no', COMING_SOON],
    ],
  },
]

const after = 1
"""


class FeatureTree(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.write("shipkit.toml", '[feature_map]\ncomparison = "apps/web/src/pricing.ts"\ncatalog_out = "apps/web/src/catalog.ts"\n')
        self.write("docs/feature_catalog.md", CATALOG)
        self.write("docs/features/billing.md", "# Billing\n")
        self.write("docs/features/README.md", "# Features\n")
        self.write("apps/web/src/pricing.ts", PRICING)
        self.run_script("--write")

    def tearDown(self) -> None:
        self.folder.cleanup()

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def replace(self, path: str, old: str, new: str) -> None:
        text = (self.root / path).read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.write(path, text.replace(old, new))

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env={**os.environ, "SHIPKIT_ROOT": str(self.root)}
        )

    def problems(self) -> str:
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout)
        return result.stdout

    def test_a_fresh_project_with_no_catalog_skips_with_one_line(self) -> None:
        (self.root / "docs/feature_catalog.md").unlink()
        for args in ((), ("--list",), ("--write",)):
            result = self.run_script(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
            self.assertIn("docs/feature_catalog.md does not exist yet; nothing to check", result.stdout)
        self.assertFalse((self.root / "docs/feature_catalog.md").exists())

    def test_passes_and_counts_features_by_what_is_left(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("7 features, 2 sub-features, 0 problems", result.stdout)
        text = (self.root / "docs/feature_catalog.md").read_text(encoding="utf-8")
        self.assertIn("| Free | 3 | 1 | 1 | 1 |", text)
        self.assertIn("| Plan to be decided | 1 | 0 | 0 | 1 |", text)
        self.assertIn("| **All** | **7** | **2** | **1** | **4** |", text)

    def test_reports_a_stale_counts_table(self) -> None:
        self.replace("docs/feature_catalog.md", "- **Chat** · Next", "- **Chat** · Built")
        self.replace("apps/web/src/pricing.ts", "['Chat', 'no', COMING_SOON, COMING_SOON]", "['Chat', 'no', 'yes', 'yes']")
        self.assertIn("counts: the table is out of date", self.problems())
        self.assertEqual(self.run_script("--write").returncode, 0)

    def test_rejects_an_unknown_status_and_a_malformed_line(self) -> None:
        self.replace("docs/feature_catalog.md", "- **Usage alerts** · Built", "- **Usage alerts** · Done\n- Alert snoozing")
        found = self.problems()
        self.assertIn("status: `Done` is not one of", found)
        self.assertIn("format: not a heading, a feature or a sub-feature: - Alert snoozing", found)

    def test_a_feature_follows_its_sub_features(self) -> None:
        self.replace("docs/feature_catalog.md", "- **Online payments** · Partly", "- **Online payments** · Built")
        self.assertIn("rollup: `Online payments` is Built, but its sub-features make it", self.problems())

    def test_rejects_a_name_used_twice(self) -> None:
        self.replace("docs/feature_catalog.md", "- **Chat** · Next", "- **Usage alerts** · Next")
        self.assertIn("names: `Usage alerts` is also on line", self.problems())

    def test_every_specification_is_linked_from_the_tree(self) -> None:
        self.write("docs/features/search.md", "# Search\n")
        self.assertIn("specs: docs/features/search.md is not linked from the tree", self.problems())

    def test_the_page_may_not_offer_what_is_not_built(self) -> None:
        self.replace("apps/web/src/pricing.ts", "['Chat', 'no', COMING_SOON, COMING_SOON]", "['Chat', 'no', 'yes', 'yes']")
        self.assertIn("site: `Chat` is Next in the tree, so the page may only say COMING_SOON", self.problems())

    def test_the_page_puts_a_feature_in_the_trees_plan(self) -> None:
        self.replace("apps/web/src/pricing.ts", "['Usage alerts', 'no', 'yes', 'yes']", "['Usage alerts', 'yes', 'yes', 'yes']")
        self.assertIn("site: `Usage alerts` is in Pro in the tree", self.problems())

    def test_the_page_uses_the_trees_names_and_only_plan_features(self) -> None:
        self.replace("apps/web/src/pricing.ts", "['Usage alerts',", "['Alerts',")
        self.assertIn("site: `Alerts` is not a feature of a plan in the tree", self.problems())
        self.replace("apps/web/src/pricing.ts", "['Alerts',", "['Agent sign-in',")
        self.assertIn("site: `Agent sign-in` is not a feature of a plan in the tree", self.problems())

    def test_a_built_feature_is_not_left_as_coming_soon(self) -> None:
        self.replace("apps/web/src/pricing.ts", "['Usage alerts', 'no', 'yes', 'yes']", "['Usage alerts', 'no', COMING_SOON, COMING_SOON]")
        self.assertIn("site: `Usage alerts` is Built in the tree, so the page should not say COMING_SOON", self.problems())

    def test_writes_the_public_catalog_from_the_plans_only(self) -> None:
        data = (self.root / "apps/web/src/catalog.ts").read_text(encoding="utf-8")
        self.assertIn("Generated by feature_map.py --write", data)
        self.assertIn("{ id: 'online-payments', title: 'Online payments', plan: 'free', category: 'Billing', status: 'under_development', subfeatures: [", data)
        self.assertIn("{ id: 'online-payments--refunds', title: 'Refunds', status: 'coming_soon' }", data)
        self.assertIn("title: 'Usage alerts', plan: 'pro', category: 'Workflow', status: 'built', subfeatures: []", data)
        self.assertIn("title: 'Live forecasts', plan: 'enterprise', category: 'Analytics', status: 'coming_soon'", data)
        # A note or a link is for the team; a feature outside the plans is not offered to customers.
        self.assertNotIn("features/billing.md", data)
        self.assertNotIn("Agent sign-in", data)

    def test_reports_a_stale_public_catalog(self) -> None:
        self.replace("docs/feature_catalog.md", "  - Refunds · Planned", "  - Refunds · In progress")
        self.run_script("--write")
        self.replace("apps/web/src/catalog.ts", "status: 'under_development' }", "status: 'coming_soon' }")
        self.assertIn("catalog: apps/web/src/catalog.ts is out of date", self.problems())
        self.assertEqual(self.run_script("--write").returncode, 0)

    def test_writes_json_when_the_output_is_json(self) -> None:
        self.write("shipkit.toml", '[feature_map]\ncatalog_out = "apps/web/src/catalog.json"\n')
        self.assertEqual(self.run_script("--write").returncode, 0)
        import json

        data = json.loads((self.root / "apps/web/src/catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(data["catalog"][0]["plan"], "free")

    def test_custom_tiers(self) -> None:
        text = (self.root / "docs/feature_catalog.md").read_text(encoding="utf-8")
        self.write("docs/feature_catalog.md", text.replace("## Free:", "## Starter:"))
        self.write("shipkit.toml", '[feature_map]\ntiers = ["Starter", "Pro", "Enterprise"]\n')
        result = self.run_script("--write")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Invoices", self.run_script("--list", "--plan", "Starter").stdout)

    def test_lists_by_plan_and_status(self) -> None:
        listed = self.run_script("--list", "--plan", "Free", "--status", "Planned").stdout
        self.assertIn("Data export", listed)
        self.assertIn("Refunds", listed)
        self.assertNotIn("Invoices", listed)


if __name__ == "__main__":
    unittest.main()
