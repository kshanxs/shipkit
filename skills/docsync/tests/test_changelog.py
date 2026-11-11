"""Tests for the change log script. Standard library only.

    uv run pytest skills/docsync
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

import changelog  # noqa: E402

HEADER = "# Changelog: API\n\nEvery change.\n\n"
RELEASED = "## [0.2.1] - 2026-04-26\n\n### Fixed\n\n- An old fix (2026-04-26)\n"
# Headings as sessions left them: each one put a new block on top.
REPEATED = (
    HEADER
    + "## [Unreleased]\n\n"
    + "### Changed\n\n- Newest change (2026-10-09)\n\n"
    + "### Added\n\n- A feature (2026-10-07)\n  with a second line\n\n"
    + "### Changed\n\n- Older change (2026-10-06)\n\n"
    + RELEASED
)


class Logs(unittest.TestCase):
    """A repository with one app, its change log and one document."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.log = self.write("apps/api/CHANGELOG.md", HEADER + "## [Unreleased]\n\n" + RELEASED)
        self.write("CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n")
        self.write("docs/features/billing.md", "# Billing and Invoices\n\n## 3. Late fees\n\nRules.\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def text(self) -> str:
        return self.log.read_text(encoding="utf-8")


class Adding(Logs):
    def test_writes_the_entry_under_its_type_with_the_date(self) -> None:
        line = changelog.add(self.log, "fixed", "A late fee was charged twice.", day="2026-10-10", root=self.root)
        self.assertEqual(line, "- A late fee was charged twice (2026-10-10)")
        self.assertIn("## [Unreleased]\n\n### Fixed\n\n- A late fee was charged twice (2026-10-10)\n\n## [0.2.1]", self.text())
        self.assertEqual(changelog.lint(self.log), [])

    def test_puts_the_newest_entry_first_under_a_heading_that_exists(self) -> None:
        changelog.add(self.log, "Fixed", "First", day="2026-10-09", root=self.root)
        changelog.add(self.log, "Fixed", "Second", day="2026-10-10", root=self.root)
        self.assertEqual(self.text().count("### Fixed"), 2, "one under Unreleased, one in the release")
        self.assertLess(self.text().index("Second"), self.text().index("First"))

    def test_keeps_the_types_in_keep_a_changelog_order(self) -> None:
        for kind in ("security", "fixed", "added", "removed", "changed"):
            changelog.add(self.log, kind, f"A {kind} entry", day="2026-10-10", root=self.root)
        block = self.text().split("## [0.2.1]")[0]
        order = [line[4:] for line in block.split("\n") if line.startswith("### ")]
        self.assertEqual(order, ["Added", "Changed", "Removed", "Fixed", "Security"])

    def test_links_the_document_relative_to_the_log(self) -> None:
        line = changelog.add(self.log, "fixed", "A fix", doc="docs/features/billing.md#3-late-fees", day="2026-10-10", root=self.root)
        self.assertEqual(line, "- A fix (2026-10-10) — [Billing and Invoices](../../docs/features/billing.md#3-late-fees)")
        root_log = self.root / "CHANGELOG.md"
        line = changelog.add(root_log, "fixed", "A fix", doc="docs/features/billing.md", title="Billing", day="2026-10-10", root=self.root)
        self.assertTrue(line.endswith("— [Billing](docs/features/billing.md)"))

    def test_leaves_released_entries_alone(self) -> None:
        changelog.add(self.log, "added", "New", day="2026-10-10", root=self.root)
        self.assertTrue(self.text().endswith(RELEASED))

    def test_refuses_what_it_cannot_file(self) -> None:
        for kind, text, doc in (("bugfix", "A fix", None), ("fixed", "  ", None), ("fixed", "A fix", "docs/features/gone.md")):
            with self.assertRaises(changelog.ChangelogError):
                changelog.add(self.log, kind, text, doc=doc, root=self.root)
        with self.assertRaises(changelog.ChangelogError):
            changelog.add(self.log, "fixed", "A fix", day="10 October", root=self.root)
        self.assertEqual(self.text(), HEADER + "## [Unreleased]\n\n" + RELEASED, "a refusal writes nothing")


class Tidying(Logs):
    def test_joins_repeated_headings_and_keeps_every_entry(self) -> None:
        self.log.write_text(REPEATED, encoding="utf-8")
        self.assertTrue(changelog.tidy(self.log))
        block = self.text().split("## [0.2.1]")[0]
        self.assertEqual([line for line in block.split("\n") if line.startswith("### ")], ["### Added", "### Changed"])
        self.assertIn("- Newest change (2026-10-09)\n- Older change (2026-10-06)\n", block)
        self.assertIn("- A feature (2026-10-07)\n  with a second line\n", block)
        self.assertTrue(self.text().startswith(HEADER))
        self.assertTrue(self.text().endswith(RELEASED))
        self.assertEqual(changelog.lint(self.log), [])

    def test_changes_nothing_the_second_time(self) -> None:
        self.log.write_text(REPEATED, encoding="utf-8")
        changelog.tidy(self.log)
        self.assertFalse(changelog.tidy(self.log))

    def test_keeps_a_heading_that_is_not_a_type_for_the_check_to_report(self) -> None:
        self.log.write_text(HEADER + "## [Unreleased]\n\n### Bug Fixes\n\n- A fix (2026-10-10)\n", encoding="utf-8")
        changelog.tidy(self.log)
        self.assertIn("### Bug Fixes\n\n- A fix (2026-10-10)\n", self.text())

    def test_refuses_a_log_with_no_unreleased_section(self) -> None:
        self.log.write_text(HEADER + RELEASED, encoding="utf-8")
        with self.assertRaises(changelog.ChangelogError):
            changelog.tidy(self.log)


class Releasing(Logs):
    def test_moves_the_entries_under_the_version_and_opens_an_empty_unreleased(self) -> None:
        self.log.write_text(REPEATED, encoding="utf-8")
        self.assertTrue(changelog.release(self.log, "0.3.0", "2026-10-10"))
        text = self.text()
        self.assertIn("## [Unreleased]\n\n## [0.3.0] - 2026-10-10\n\n### Added\n\n- A feature (2026-10-07)", text)
        self.assertLess(text.index("## [0.3.0]"), text.index("## [0.2.1]"))
        self.assertEqual(changelog.entries(text), {})
        self.assertEqual(changelog.lint(self.log), [])

    def test_has_nothing_to_release_from_an_empty_unreleased(self) -> None:
        before = self.text()
        self.assertFalse(changelog.release(self.log, "0.3.0", "2026-10-10"))
        self.assertEqual(self.text(), before)

    def test_refuses_a_version_already_released_or_badly_written(self) -> None:
        changelog.add(self.log, "added", "New", day="2026-10-10", root=self.root)
        for version in ("0.2.1", "v0.3", "next"):
            with self.assertRaises(changelog.ChangelogError):
                changelog.release(self.log, version, "2026-10-10")

    def test_accepts_a_calendar_version(self) -> None:
        changelog.add(self.log, "added", "New", day="2026-10-10", root=self.root)
        self.assertTrue(changelog.release(self.log, "2026.10.0", "2026-10-10"))


class Linting(Logs):
    def problems(self, unreleased: str, rest: str = RELEASED) -> list[str]:
        self.log.write_text(HEADER + unreleased + rest, encoding="utf-8")
        return changelog.lint(self.log, "apps/api/CHANGELOG.md")

    def test_accepts_an_empty_and_a_well_formed_section(self) -> None:
        self.assertEqual(self.problems("## [Unreleased]\n\n"), [])
        self.assertEqual(self.problems("## [Unreleased]\n\n### Added\n\n- A feature (2026-10-07)\n  continued\n  - a detail\n\n"), [])

    def test_reports_a_missing_unreleased_section(self) -> None:
        self.assertIn("no `## [Unreleased]` section", self.problems("")[0])

    def test_reports_a_repeated_heading_and_names_the_fix(self) -> None:
        self.log.write_text(REPEATED, encoding="utf-8")
        (problem,) = changelog.lint(self.log, "apps/api/CHANGELOG.md")
        self.assertIn("apps/api/CHANGELOG.md:16: `### Changed` is also on line 7", problem)
        self.assertIn("changelog.py tidy", problem)

    def test_reports_a_heading_that_is_not_a_type(self) -> None:
        self.assertIn("`### Bug Fixes` is not a type", self.problems("## [Unreleased]\n\n### Bug Fixes\n\n- A fix (2026-10-10)\n\n")[0])

    def test_reports_an_entry_with_no_date_no_heading_or_no_bullet(self) -> None:
        self.assertIn("no date", self.problems("## [Unreleased]\n\n### Fixed\n\n- A fix\n\n")[0])
        self.assertIn("under no heading", self.problems("## [Unreleased]\n\n- A fix (2026-10-10)\n\n")[0])
        self.assertIn("not a list item", self.problems("## [Unreleased]\n\n### Fixed\n\n- A fix (2026-10-10)\nA paragraph.\n\n")[0])

    def test_reports_a_heading_with_no_entries(self) -> None:
        self.assertIn("`### Fixed` has no entries", self.problems("## [Unreleased]\n\n### Fixed\n\n")[0])

    def test_reports_releases_out_of_order_repeated_or_badly_headed(self) -> None:
        older_first = "## [0.2.0] - 2026-04-13\n\n- x\n\n## [0.2.1] - 2026-04-26\n\n- y\n"
        self.assertIn("dated after the release above it", self.problems("## [Unreleased]\n\n", older_first)[0])
        twice = "## [0.2.1] - 2026-04-26\n\n## [0.2.1] - 2026-04-20\n"
        self.assertIn("released twice", self.problems("## [Unreleased]\n\n", twice)[0])
        self.assertIn("`## [version] - YYYY-MM-DD`", self.problems("## [Unreleased]\n\n", "## [0.2.1] 26 April\n")[0])
        self.assertIn("above `## [Unreleased]`", self.problems(RELEASED + "\n## [Unreleased]\n", "")[0])

    def test_leaves_released_sections_and_older_headings_alone(self) -> None:
        legacy = "## Before this file\n\n## 2026-04-26 — v0.2.1 Hardening\n\n### Bug Fixes\n\nA paragraph, no date.\n"
        self.assertEqual(self.problems("## [Unreleased]\n\n", legacy), [])


class CommandLine(Logs):
    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "changelog.py"), *args],
            capture_output=True, text=True, check=False, env={**os.environ, "SHIPKIT_ROOT": str(self.root)},
        )

    def test_adds_checks_and_releases_by_log_name(self) -> None:
        added = self.run_script("add", "api", "fixed", "A late fee was charged twice", "--doc", "docs/features/billing.md", "--date", "2026-10-10")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("apps/api/CHANGELOG.md: - A late fee was charged twice (2026-10-10) — [Billing and Invoices]", added.stdout)
        self.assertEqual(self.run_script("check").returncode, 0)
        released = self.run_script("release", "0.3.0", "--date", "2026-10-10")
        self.assertIn("apps/api/CHANGELOG.md: [0.3.0] released", released.stdout)
        self.assertNotIn("CHANGELOG.md: [0.3.0] released\nCHANGELOG.md", released.stdout, "the root log had nothing to release")
        self.assertIn("git tag -a v0.3.0", released.stdout)

    def test_check_exits_one_on_a_problem(self) -> None:
        self.log.write_text(REPEATED, encoding="utf-8")
        result = self.run_script("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("2 change logs checked: 1 problems", result.stdout)
        self.assertEqual(self.run_script("tidy", "api").returncode, 0)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_names_the_logs_when_asked_for_one_that_does_not_exist(self) -> None:
        result = self.run_script("add", "backend", "fixed", "A fix")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no change log named backend; there are: root, api", result.stderr)


if __name__ == "__main__":
    unittest.main()
