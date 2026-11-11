"""Tests for the documentation checker. Standard library only.

    uv run pytest skills/docsync

Each test builds a small repository in a temporary folder that satisfies every
check, breaks one thing, and asserts that exactly that check reports it. The
repository's shipkit.toml turns on every configurable check.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_docs  # noqa: E402

STATUS = "> **Status (2026-10-06): Built.** Works."
LEGAL = "apps/web/src/features/public/legal/"

CONFIG = r"""
[docsync]
packages = ["apps/*"]
code_roots = ["apps/api/app", "apps/web/src/features", "apps/admin/src/features"]
plan_sources = ["docs/finance/pricing.md", "docs/feature_catalog.md"]
no_plan = ["docs/features/admin/*", "docs/features/public_site.md"]
policy_pages = ["apps/web/src/features/public/legal/*Page.tsx"]
policy_stamp = "apps/web/src/features/public/legal/company.ts"
pairs = [["apps/web/src/features/public/pricing.ts", "docs/finance/pricing.md"]]
racing_markers = ["racing_client"]
attack_log_start = "2026-10-28"

[[docsync.stale]]
label = "retired document name"
pattern = 'FEATURE_STATUS\.md'

[[docsync.stale]]
label = "retired plan price"
pattern = '\$49/seat|Pro \(\$49\)'

[[docsync.stale]]
label = "retired hosting name"
pattern = 'LegacyDB'

[[docsync.stale]]
label = "retired folder path"
pattern = '\bcd (backend|frontend)\b'

[[docsync.stale]]
label = "retired mobile stack"
pattern = '\bCordova\b'
allowed = ["docs/architecture/technical_decisions.md"]
"""

FILES = {
    "shipkit.toml": CONFIG,
    "README.md": "# Project\n\nSee the [docs](docs/README.md).\n",
    "CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n",
    "docs/README.md": (
        "# Docs\n\n[Tracker](feature_status.md) · [Pricing](finance/pricing.md)\n\n"
        "Folders: `features/`, `finance/`, `plans/`.\n"
    ),
    "docs/feature_status.md": (
        "# Tracker\n\n## Code map\n\n| Code | Described in |\n|------|--------------|\n"
        "| `apps/api/app/alpha` | [features/alpha.md](features/alpha.md) |\n"
        "| `apps/web/src/features/alpha` | [features/alpha.md](features/alpha.md) |\n"
        "| `apps/web/src/features/public` | [finance/pricing.md](finance/pricing.md) |\n"
    ),
    "docs/finance/pricing.md": "# Pricing\n\n## 7. Matrix\n\n| Feature | Status |\n|---|---|\n| [Alpha](../features/alpha.md) | Built |\n",
    "docs/features/alpha.md": f"# Alpha\n\n{STATUS}\n\n## 1. What it does\n\nThings.\n",
    "docs/plans/2026-10-06-alpha-design.md": "# Alpha design\n\nSee [Alpha](../features/alpha.md).\n",
    "docs/plans/README.md": "# Plans\n\n- [Alpha design](2026-10-06-alpha-design.md)\n",
    "apps/api/CHANGELOG.md": "# Changelog: API\n\n## [Unreleased]\n",
    "apps/api/app/alpha/models.py": 'class Alpha:\n    __tablename__ = "alpha_items"\n',
    "apps/web/CHANGELOG.md": "# Changelog: Web\n\n## [Unreleased]\n",
    "apps/web/src/features/alpha/AlphaPage.tsx": "export const Alpha = () => null\n",
    "apps/web/src/features/public/pricing.ts": "export const SEAT_PRICE = 29\n",
}
FILES["docs/README.md"] += "\n[Plans](plans/README.md) · [Alpha](features/alpha.md)\n"


class Repo(unittest.TestCase):
    """A temporary repository that passes every check."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        for name, text in FILES.items():
            self.write(name, text)
        self._root_before = check_docs.ROOT
        check_docs.ROOT = self.root
        check_docs._anchor_cache.clear()

    def tearDown(self) -> None:
        check_docs.ROOT = self._root_before
        check_docs._anchor_cache.clear()
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def append(self, name: str, text: str) -> None:
        path = self.root / name
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def errors(self, **options) -> dict[str, list[str]]:
        found, _, _ = check_docs.run(**options)
        return {name: problems for name, problems in found.items() if problems}

    def warnings(self, **options) -> dict[str, list[str]]:
        _, found, _ = check_docs.run(**options)
        return {name: problems for name, problems in found.items() if problems}


class CleanRepository(Repo):
    def test_passes_every_check(self) -> None:
        self.assertEqual(self.errors(), {})
        self.assertEqual(self.warnings(), {})

    def test_a_repository_with_no_config_and_no_docs_passes_quietly(self) -> None:
        for name in list(FILES):
            (self.root / name).unlink()
        self.write("README.md", "# Tiny\n")
        self.assertEqual(self.errors(), {})
        self.assertEqual(self.warnings(), {})


class Slugs(unittest.TestCase):
    def test_follow_github_heading_anchors(self) -> None:
        cases = {
            "7. Feature Comparison Matrix": "7-feature-comparison-matrix",
            "12. Achievements & Trophies Tables": "12-achievements--trophies-tables",
            "4.4 Billing, Online Payments & Refunds": "44-billing-online-payments--refunds",
            "Pro Plan (2 Seats / $30)": "pro-plan-2-seats--30",
            "`code` and [a link](x.md)": "code-and-a-link",
        }
        for heading, anchor in cases.items():
            self.assertEqual(check_docs.slug(heading), anchor)

class Links(Repo):
    def test_reports_a_missing_file_and_a_missing_heading(self) -> None:
        self.append("docs/features/alpha.md", "\n[gone](nowhere.md) and [bad](../finance/pricing.md#no-such-heading)\n")
        problems = self.errors()["links"]
        self.assertEqual(len(problems), 2)
        self.assertIn("missing file: nowhere.md", problems[0])
        self.assertIn("missing heading: ../finance/pricing.md#no-such-heading", problems[1])

    def test_accepts_a_heading_that_exists(self) -> None:
        self.append("docs/features/alpha.md", "\n[matrix](../finance/pricing.md#7-matrix)\n")
        self.assertEqual(self.errors(), {})

    def test_numbers_repeated_headings_as_github_does(self) -> None:
        self.append("docs/features/alpha.md", "\n## Notes\n\n## Notes\n\n[second](#notes-1) [third](#notes-2)\n")
        self.assertEqual(len(self.errors()["links"]), 1)

    def test_ignores_links_inside_code(self) -> None:
        self.append("docs/features/alpha.md", "\n```markdown\n[example](not_a_file.md)\n```\n\nAlso `[inline](nope.md)`.\n")
        self.assertEqual(self.errors(), {})

    def test_ignores_web_links(self) -> None:
        self.append("docs/features/alpha.md", "\n[site](https://example.com/x) [mail](mailto:a@b.c)\n")
        self.assertEqual(self.errors(), {})


class Formatting(Repo):
    def test_reports_an_unclosed_code_fence(self) -> None:
        self.append("docs/features/alpha.md", "\n```sql\nSELECT 1;\n")
        self.assertIn("docs/features/alpha.md", self.errors()["fences"][0])

    def test_reports_emoji_and_leaves_arrows_and_box_lines(self) -> None:
        self.append("docs/features/alpha.md", "\n| Built | \u2705 |\n\nA \u2192 B, \u2502 box \u2502, menu \u25bc\n\n\u26a0\ufe0f Careful \U0001F680\n")
        found = self.errors()["emoji"]
        self.assertEqual(len(found), 2)
        self.assertIn("emoji (U+2705)", found[0])
        self.assertIn("U+26A0 U+1F680", found[1])

    def test_reports_a_literal_newline_escape_in_a_table_or_sql(self) -> None:
        self.append("docs/features/alpha.md", "\n| a | b |\\n|---|---|\n\n```sql\nCREATE TABLE t (\\n  id INT\n);\n```\n")
        self.assertEqual(len(self.errors()["escapes"]), 2)

    def test_allows_the_escape_in_ordinary_code(self) -> None:
        self.append("docs/features/alpha.md", '\n```python\nprint("a\\nb")\n```\n')
        self.assertEqual(self.errors(), {})


class Naming(Repo):
    def test_rejects_uppercase_and_kebab_names_outside_plans(self) -> None:
        self.write("docs/features/Beta_Feature.md", f"# Beta\n\n{STATUS}\n")
        self.write("docs/features/gamma-feature.md", f"# Gamma\n\n{STATUS}\n")
        problems = "\n".join(self.errors()["naming"])
        self.assertIn("Beta_Feature.md", problems)
        self.assertIn("gamma-feature.md", problems)

    def test_keeps_dated_files_in_plans(self) -> None:
        self.write("docs/features/2026-10-06-beta-notes.md", f"# Notes\n\n{STATUS}\n")
        self.assertIn("dated files belong in docs/plans/", "\n".join(self.errors()["naming"]))

    def test_rejects_an_uppercase_folder(self) -> None:
        self.write("docs/Guides/intro.md", "# Intro\n")
        self.assertIn("docs/Guides/", "\n".join(self.errors()["naming"]))

    def test_rejects_scratch_files_under_apps(self) -> None:
        self.write("apps/web/TODO.md", "- [ ] things\n")
        self.assertIn("apps/web/TODO.md", self.errors()["scratch"][0])


class Stale(Repo):
    def test_rejects_retired_names_prices_and_paths(self) -> None:
        self.append(
            "docs/features/alpha.md",
            "\nSee FEATURE_STATUS.md. Pro ($49). Hosted on LegacyDB. Run `cd backend`.\n",
        )
        problems = "\n".join(self.errors()["stale"])
        for label in ("retired document name", "retired plan price", "retired hosting name", "retired folder path"):
            self.assertIn(label, problems)

    def test_rejects_the_retired_mobile_stack_outside_its_history(self) -> None:
        self.append("docs/features/alpha.md", "\nA Cordova app is planned.\n")
        self.assertIn("retired mobile stack: Cordova", self.errors()["stale"][0])
        self.write("docs/architecture/technical_decisions.md", "# Decisions\n\nExpo replaced Cordova on 2026-10-06.\n")
        self.append("docs/README.md", "\n[Decisions](architecture/technical_decisions.md)\n")
        self.assertEqual(len(self.errors()["stale"]), 1)

    def test_allows_them_in_change_logs(self) -> None:
        self.append("CHANGELOG.md", "\n### Changed\n\n- Renamed FEATURE_STATUS.md; Pro was $49/seat; left LegacyDB (2026-10-06)\n")
        self.assertEqual(self.errors(), {})

    def test_no_stale_rules_means_no_stale_check(self) -> None:
        self.write("shipkit.toml", "[docsync]\npackages = [\"apps/*\"]\n")
        self.append("docs/features/alpha.md", "\nSee FEATURE_STATUS.md.\n")
        self.assertNotIn("stale", self.errors())


class Coverage(Repo):
    def test_requires_a_new_module_in_the_code_map(self) -> None:
        self.write("apps/api/app/beta/router.py", "x = 1\n")
        self.assertIn("apps/api/app/beta: not in the code map", self.errors()["coverage"][0])

    def test_requires_a_new_frontend_feature_in_the_code_map(self) -> None:
        self.write("apps/admin/src/features/flags/FlagsPage.tsx", "export {}\n")
        self.assertIn("apps/admin/src/features/flags", self.errors()["coverage"][0])

    def test_reports_a_mapped_folder_that_no_longer_exists(self) -> None:
        self.append("docs/feature_status.md", "| `apps/api/app/removed` | [features/alpha.md](features/alpha.md) |\n")
        self.assertIn("apps/api/app/removed, which no longer exists", self.errors()["coverage"][0])


class StatusLines(Repo):
    def test_requires_a_dated_status_line_on_every_specification(self) -> None:
        self.write("docs/features/alpha.md", "# Alpha\n\nNo status here.\n")
        self.assertIn("docs/features/alpha.md: no status line", self.errors()["status"][0])

    def test_accepts_each_status_word(self) -> None:
        for word in check_docs.DEFAULT_STATUSES:
            self.write("docs/features/alpha.md", f"# Alpha\n\n> **Status (2026-10-06): {word}.** Note.\n")
            self.assertEqual(self.errors(), {}, word)

    def test_rejects_an_unknown_status_word_or_a_missing_date(self) -> None:
        for line in ("> **Status (2026-10-06): Done.**", "> **Status: Built.**"):
            self.write("docs/features/alpha.md", f"# Alpha\n\n{line}\n")
            self.assertIn("status", self.errors(), line)


class Plans(Repo):
    def test_requires_a_specification_in_the_matrix_or_the_queue(self) -> None:
        self.write("docs/features/beta.md", f"# Beta\n\n{STATUS}\n")
        self.append("docs/README.md", "\n[Beta](features/beta.md)\n")
        self.assertIn("docs/features/beta.md: linked from none of", self.errors()["plan"][0])

    def test_is_satisfied_by_a_row_in_the_queue(self) -> None:
        self.write("docs/features/beta.md", f"# Beta\n\n{STATUS}\n")
        self.append("docs/finance/pricing.md", "\n### 7.7 Plan to Be Decided\n\n| Feature | Specification |\n|---|---|\n| Beta | [beta.md](../features/beta.md) |\n")
        self.assertEqual(self.errors(), {})

    def test_accepts_a_specification_linked_from_the_feature_tree(self) -> None:
        self.write("docs/features/beta.md", f"# Beta\n\n{STATUS}\n")
        self.write("docs/feature_catalog.md", "# Tree\n\n## Plan to be decided\n\n- **Beta** · Planned · [Beta](features/beta.md)\n")
        self.append("docs/README.md", "\n[Tree](feature_catalog.md)\n")
        self.assertNotIn("plan", self.errors())

    def test_exempts_configured_pages(self) -> None:
        self.write("docs/features/admin/billing.md", f"# Billing\n\n{STATUS}\n")
        self.write("docs/features/public_site.md", f"# Public site\n\n{STATUS}\n")
        self.append("docs/README.md", "\n[Billing](features/admin/billing.md) [Public](features/public_site.md)\n")
        self.assertEqual(self.errors(), {})

    def test_no_plan_sources_means_no_plan_check(self) -> None:
        self.write("shipkit.toml", "[docsync]\npackages = [\"apps/*\"]\n")
        self.write("docs/features/beta.md", f"# Beta\n\n{STATUS}\n")
        self.append("docs/README.md", "\n[Beta](features/beta.md)\n")
        self.assertNotIn("plan", self.errors())


class Warnings(Repo):
    def test_warns_about_a_document_nothing_links_to(self) -> None:
        self.write("docs/architecture/lonely.md", "# Lonely\n")
        self.assertIn("docs/architecture/lonely.md", self.warnings()["orphans"][0])

    def test_warns_about_a_folder_missing_from_the_index(self) -> None:
        self.write("docs/roles/admin.md", "# Admin\n")
        self.append("docs/features/alpha.md", "\n[Admin](../roles/admin.md)\n")
        self.assertIn("docs/roles/", self.warnings()["index"][0])


class Unreleased(Repo):
    def test_reports_a_repeated_heading_in_any_change_log(self) -> None:
        self.append("apps/web/CHANGELOG.md", "\n### Added\n\n- One (2026-10-06)\n\n### Added\n\n- Two (2026-10-07)\n")
        (problem,) = self.errors()["unreleased"]
        self.assertIn("apps/web/CHANGELOG.md:9: `### Added` is also on line 5", problem)

    def test_reports_an_entry_with_no_date_in_the_root_log(self) -> None:
        self.append("CHANGELOG.md", "\n### Added\n\n- A feature\n")
        self.assertIn("CHANGELOG.md:7: an entry with no date", self.errors()["unreleased"][0])


REGISTER = (
    "# Bug Register\n\nSee the [tracker](../feature_status.md).\n\n## Open\n\n"
    "| Bug | Severity | Where | What is wrong | What closes it |\n|---|---|---|---|---|\n"
    "| BUG-002 | High | `config.py` | Starts without a key | Refuse to start |\n\n"
    "## Closed\n\n| Bug | Reported as | Closed |\n|---|---|---|\n"
    "| BUG-001 | Undefined name | Fixed 2026-10-09 |\n"
)


class Bugs(Repo):
    def setUp(self) -> None:
        super().setUp()
        self.write("docs/testing/bug_report.md", REGISTER)
        self.append("docs/README.md", "\n[Bugs](testing/bug_report.md) in `testing/`.\n")

    def test_accepts_a_register_with_one_row_a_bug(self) -> None:
        self.assertEqual(self.errors(), {})

    def test_reports_a_bug_with_two_rows(self) -> None:
        self.append("docs/testing/bug_report.md", "| BUG-002 | Starts without a key | Fixed 2026-10-10 |\n")
        self.assertIn("BUG-002 has 2 rows", self.errors()["bugs"][0])

    def test_requires_a_severity_on_an_open_bug(self) -> None:
        self.write("docs/testing/bug_report.md", REGISTER.replace("| High |", "| Urgent |"))
        self.assertIn("BUG-002 has no severity; write one of Critical, High, Medium, Low", self.errors()["bugs"][0])

    def test_reports_a_bug_recorded_as_fixed_and_still_open(self) -> None:
        self.append("apps/api/CHANGELOG.md", "\n### Fixed\n\n- BUG-002: production refuses to start without a key (2026-10-10)\n")
        (problem,) = self.errors()["bugs"]
        self.assertIn("BUG-002 is recorded as fixed in apps/api/CHANGELOG.md and is still under Open", problem)
        closed = REGISTER.replace("| BUG-002 | High | `config.py` | Starts without a key | Refuse to start |\n", "")
        self.write("docs/testing/bug_report.md", closed + "| BUG-002 | Starts without a key | Fixed 2026-10-10 |\n")
        self.assertEqual(self.errors(), {})

    def test_a_bug_named_outside_fixed_does_not_close_it(self) -> None:
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A warning is logged for BUG-002 (2026-10-10)\n")
        self.assertEqual(self.errors(), {})


class GitRepo(Repo):
    """The fixture, committed, so a change set can be read from git."""

    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "baseline")

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True)
        return result.stdout


class ChangeSet(GitRepo):
    def test_is_clean_when_nothing_changed(self) -> None:
        self.assertEqual(self.errors(changed=True), {})
        self.assertEqual(self.warnings(changed=True), {})

    def test_requires_the_app_changelog_when_its_code_changes(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        problems = self.errors(changed=True)["changelog"]
        self.assertEqual(len(problems), 1)
        self.assertIn("apps/api/CHANGELOG.md: not updated", problems[0])

    def test_is_satisfied_by_a_changelog_line(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A change (2026-10-06)\n")
        self.append("docs/features/alpha.md", "\nChanged on 2026-10-06.\n")
        self.assertEqual(self.errors(changed=True), {})
        self.assertEqual(self.warnings(changed=True), {})

    def test_judges_each_app_separately(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        self.append("apps/web/src/features/alpha/AlphaPage.tsx", "// a fix\n")
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A fix (2026-10-06)\n")
        problems = self.errors(changed=True)["changelog"]
        self.assertEqual(len(problems), 1)
        self.assertIn("apps/web/CHANGELOG.md", problems[0])

    def test_does_not_ask_for_a_changelog_when_only_documents_changed(self) -> None:
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- Wording (2026-10-06)\n")
        self.append("docs/features/alpha.md", "\nMore detail.\n")
        self.assertEqual(self.errors(changed=True), {})

    def test_warns_when_code_changes_and_no_document_does(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A fix (2026-10-06)\n")
        self.assertIn("nothing under docs/ did", self.warnings(changed=True)["docs"][0])

    def test_warns_when_a_fix_is_recorded_and_no_test_changed(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        self.append("apps/api/CHANGELOG.md", "\n### Fixed\n\n- A fix (2026-10-06)\n")
        self.append("docs/features/alpha.md", "\nFixed on 2026-10-06.\n")
        (problem,) = self.warnings(changed=True)["tests"]
        self.assertIn("apps/api/CHANGELOG.md: records a fix, and no test under apps/api/ changed", problem)
        self.write("apps/api/tests/test_alpha.py", "def test_the_fix():\n    assert True\n")
        self.assertEqual(self.warnings(changed=True), {})

    def test_a_fix_recorded_before_this_change_set_asks_for_no_test(self) -> None:
        self.append("apps/api/CHANGELOG.md", "\n### Fixed\n\n- An earlier fix (2026-10-05)\n")
        self.git("commit", "-q", "-am", "an earlier fix")
        self.append("apps/api/app/alpha/models.py", "# a change\n")
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A change (2026-10-06)\n")
        self.append("docs/features/alpha.md", "\nChanged on 2026-10-06.\n")
        self.assertEqual(self.warnings(changed=True), {})

    def test_counts_a_frontend_test_file_as_a_test(self) -> None:
        self.append("apps/web/src/features/alpha/AlphaPage.tsx", "// a fix\n")
        self.append("apps/web/CHANGELOG.md", "\n### Fixed\n\n- A fix (2026-10-06)\n")
        self.append("docs/features/alpha.md", "\nFixed on 2026-10-06.\n")
        self.assertIn("tests", self.warnings(changed=True))
        self.write("apps/web/src/features/alpha/AlphaPage.test.tsx", "test('the fix', () => {})\n")
        self.assertEqual(self.warnings(changed=True), {})

    def test_warns_when_a_module_changes_and_its_document_does_not(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a change\n")
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A change (2026-10-06)\n")
        self.append("docs/README.md", "\nA note.\n")
        (problem,) = self.warnings(changed=True)["spec"]
        self.assertIn("docs/features/alpha.md: not updated, but apps/api/app/alpha changed", problem)
        self.append("docs/features/alpha.md", "\nChanged on 2026-10-06.\n")
        self.assertEqual(self.warnings(changed=True), {})

    def test_a_change_to_a_modules_tests_alone_owes_no_document(self) -> None:
        self.write("apps/api/app/alpha/tests/test_models.py", "def test_it():\n    assert True\n")
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- More tests (2026-10-06)\n")
        self.assertNotIn("spec", self.warnings(changed=True))

    def test_requires_the_policy_date_when_a_policy_page_changes(self) -> None:
        legal = LEGAL
        self.write(legal + "TermsPage.tsx", "export const Terms = 1\n")
        self.write(legal + "company.ts", "export const COMPANY = { lastUpdated: '2026-10-01' }\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "policies")
        self.append(legal + "TermsPage.tsx", "// new clause\n")
        self.append("apps/web/CHANGELOG.md", "\n### Changed\n\n- Terms (2026-10-06)\n")
        self.assertIn("update the policies' last-updated date", self.errors(changed=True)["policy"][0])
        self.append(legal + "company.ts", "// 2026-10-06\n")
        self.assertNotIn("policy", self.errors(changed=True))

    def test_warns_when_a_pair_changes_on_one_side_only(self) -> None:
        self.append("apps/web/src/features/public/pricing.ts", "// changed\n")
        self.append("apps/web/CHANGELOG.md", "\n### Changed\n\n- Pricing (2026-10-06)\n")
        self.assertIn("docs/finance/pricing.md did not", self.warnings(changed=True)["pairs"][0])
        self.append("docs/finance/pricing.md", "\nChanged.\n")
        self.assertNotIn("pairs", self.warnings(changed=True))

    def test_staged_mode_sees_only_what_a_commit_would_contain(self) -> None:
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        self.assertEqual(self.errors(changed=True, staged=True), {})
        self.git("add", "apps/api/app/alpha/models.py")
        self.assertIn("changelog", self.errors(changed=True, staged=True))
        self.append("apps/api/CHANGELOG.md", "\n### Changed\n\n- A fix (2026-10-06)\n")
        self.assertIn("changelog", self.errors(changed=True, staged=True), "an unstaged changelog does not count")
        self.git("add", "apps/api/CHANGELOG.md")
        self.assertEqual(self.errors(changed=True, staged=True), {})

    def test_base_counts_commits_since_the_branch_point(self) -> None:
        self.git("branch", "trunk")
        self.append("apps/api/app/alpha/models.py", "# a fix\n")
        self.git("commit", "-q", "-am", "fix without a changelog")
        self.assertEqual(self.errors(changed=True), {}, "the working tree is clean")
        self.assertIn("changelog", self.errors(changed=True, base="trunk"))


class SinglePackage(GitRepo):
    """A repository with no package folders: the root CHANGELOG.md covers its code."""

    def setUp(self) -> None:
        super().setUp()
        self.write("shipkit.toml", "[docsync]\npackages = []\n")
        self.write("src/app.py", "x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "single")

    def test_code_without_a_root_changelog_line_is_an_error(self) -> None:
        self.append("src/app.py", "y = 2\n")
        self.assertIn("CHANGELOG.md: not updated", self.errors(changed=True)["changelog"][0])
        self.append("CHANGELOG.md", "\n### Changed\n\n- y (2026-10-06)\n")
        self.assertNotIn("changelog", self.errors(changed=True))


class CommandLine(GitRepo):
    def run_checker(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "check_docs.py"), *args],
            capture_output=True, text=True, check=False, env={**os.environ, "SHIPKIT_ROOT": str(self.root)},
        )

    def test_exits_zero_on_a_clean_repository(self) -> None:
        result = self.run_checker("--changed")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("0 errors, 0 warnings", result.stdout)

    def test_exits_one_on_an_error_and_names_the_check(self) -> None:
        self.append("docs/features/alpha.md", "\n[gone](nowhere.md)\n")
        result = self.run_checker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR [links] docs/features/alpha.md", result.stdout)

    def test_strict_fails_on_a_warning(self) -> None:
        self.write("docs/architecture/lonely.md", "# Lonely\n")
        self.assertEqual(self.run_checker().returncode, 0)
        self.assertEqual(self.run_checker("--strict").returncode, 1)

    def test_map_lists_who_links_to_a_document(self) -> None:
        result = self.run_checker("--map")
        self.assertEqual(result.returncode, 0)
        self.assertIn("| `docs/features/alpha.md` |", result.stdout)
        self.assertIn("`docs/finance/pricing.md`", result.stdout)


if __name__ == "__main__":
    unittest.main()
