"""Tests for the attack log (attacks.py) and its check in check_docs.py. Standard library only.

    uv run pytest skills/docsync
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import attacks  # noqa: E402
from test_check_docs import REGISTER, GitRepo, Repo  # noqa: E402

TEST = "apps/api/tests/test_alpha.py"
NAME = "test_two_at_once_make_one"


class LogRepo(Repo):
    """The fixture repository with a bug register, an indexed attack log and a test to name."""

    def setUp(self) -> None:
        super().setUp()
        self.write("docs/testing/bug_report.md", REGISTER)
        self.write(TEST, f"async def {NAME}():\n    pass\n")
        self.append("docs/README.md", "\n[Bugs](testing/bug_report.md) and [attacks](testing/attack_log.md) in `testing/`.\n")
        attacks.add("Alpha", "Two at once", [f"{TEST}::{NAME}"], "Held", root=self.root, today="2026-10-28")

    def log(self) -> str:
        return (self.root / attacks.LOG).read_text(encoding="utf-8")


class Writing(LogRepo):
    def test_add_numbers_rows_in_turn_and_keeps_them_in_the_table(self) -> None:
        second = attacks.add("Alpha", "A fix", [f"{TEST}::{NAME}"], "Fixed BUG-001", root=self.root, today="2026-10-28")
        self.assertEqual(second, "ATK-002")
        found, _ = attacks.parse(self.log())
        self.assertEqual([a.id for a in found], ["ATK-001", "ATK-002"])
        self.assertEqual(found[1].result, "Fixed BUG-001")
        self.assertIn(f"`{TEST}::{NAME}`", found[1].test)

    def test_a_bar_in_the_text_does_not_break_the_row(self) -> None:
        attacks.add("Alpha", "A | B", [], "Not a flaw", root=self.root)
        found, _ = attacks.parse(self.log())
        self.assertEqual(found[-1].tried, "A / B")

    def test_held_or_fixed_needs_a_test_and_a_result_is_one_of_four(self) -> None:
        with self.assertRaises(attacks.AttackLogError):
            attacks.add("Alpha", "Nothing to hold it", [], "Held", root=self.root)
        with self.assertRaises(attacks.AttackLogError):
            attacks.add("Alpha", "Guessed", [], "Probably fine", root=self.root)

    def test_runs_go_newest_first_and_the_report_comes_from_the_log(self) -> None:
        attacks.add("Alpha", "A fix", [f"{TEST}::{NAME}"], "Fixed BUG-001", root=self.root)
        first = attacks.run("First", ["ATK-001"], "pytest: 1 passed", "not run: no server", "nothing", root=self.root, today="2026-10-27")
        second = attacks.run("Second", ["ATK-001", "ATK-002"], "pytest: 2 passed", "20 at once, no 5xx", "the mobile app", root=self.root, today="2026-10-28")
        self.assertEqual((first, second), ("RUN-001", "RUN-002"))
        _, runs = attacks.parse(self.log())
        self.assertEqual([r.id for r in runs], ["RUN-002", "RUN-001"])
        report = attacks.report("RUN-002", {"BUG-001": "Low"}, root=self.root)
        self.assertIn("## Build, test, break, harden: Second", report)
        self.assertIn("| ATK-002 | Alpha | A fix |", report)
        self.assertIn("**Bugs:** BUG-001 (Low).", report)
        self.assertIn("**Not tried:** the mobile app", report)

    def test_a_run_names_only_attacks_in_the_log(self) -> None:
        with self.assertRaises(attacks.AttackLogError):
            attacks.run("Scope", ["ATK-009"], "t", "l", "n", root=self.root)


class Checking(LogRepo):
    def test_a_clean_log_passes(self) -> None:
        self.assertEqual(self.errors(), {})
        self.assertEqual(self.warnings(), {})

    def test_a_missing_test_file_or_name(self) -> None:
        attacks.add("Alpha", "Gone", ["apps/api/tests/test_gone.py::test_x"], "Held", root=self.root)
        attacks.add("Alpha", "Renamed", [f"{TEST}::test_renamed"], "Held", root=self.root)
        problems = self.errors()["attacks"]
        self.assertTrue(any("names apps/api/tests/test_gone.py, which does not exist" in p for p in problems))
        self.assertTrue(any("names the test test_renamed, which is not in" in p for p in problems))

    def test_a_row_written_by_hand_with_a_bad_result_or_two_rows_of_one_id(self) -> None:
        text = self.log().replace("| Held |", "| Mostly fine |")
        (self.root / attacks.LOG).write_text(text, encoding="utf-8")
        self.assertIn("is not Held, Fixed BUG-NNN, Open BUG-NNN or Not a flaw", self.errors()["attacks"][0])

    def test_a_fixed_bug_must_be_closed_and_an_open_one_open(self) -> None:
        attacks.add("Alpha", "Called fixed, still open", [f"{TEST}::{NAME}"], "Fixed BUG-002", root=self.root)
        attacks.add("Alpha", "Called open, closed", [], "Open BUG-001", root=self.root)
        attacks.add("Alpha", "Unknown", [], "Open BUG-099", root=self.root)
        problems = self.errors()["attacks"]
        self.assertTrue(any("says BUG-002 is fixed, and the register has it under Open" in p for p in problems))
        self.assertTrue(any("says BUG-001 is open, and the register has it under Closed" in p for p in problems))
        self.assertTrue(any("says BUG-099 is open, and the register has it nowhere" in p for p in problems))

    def test_a_bug_an_attack_found_since_the_log_began_needs_its_row(self) -> None:
        self.append(
            "docs/testing/bug_report.md",
            "| BUG-003 | Two at once made two | Fixed 2026-10-28. Found by the attack on alpha |\n"
            "| BUG-004 | Older | Fixed 2026-10-26. Found by the attack on beta |\n",
        )
        (problem,) = self.errors()["attacks"]
        self.assertIn("BUG-003 was found by an attack and has no row", problem)
        attacks.add("Alpha", "Two at once", [f"{TEST}::{NAME}"], "Fixed BUG-003", root=self.root)
        self.assertEqual(self.errors(), {})

    def test_a_run_without_its_fields(self) -> None:
        attacks.run("Scope", ["ATK-001"], "t", "l", "n", root=self.root)
        text = self.log().replace("- **Load:** l\n", "")
        (self.root / attacks.LOG).write_text(text, encoding="utf-8")
        self.assertIn("RUN-001 has no 'Load'", self.errors()["attacks"][0])


class ChangeSet(GitRepo):
    def test_warns_when_a_race_test_changes_and_the_log_does_not(self) -> None:
        self.write("apps/api/tests/test_race.py", "from tests.racing import racing_client\n")
        self.append("apps/api/CHANGELOG.md", "\n### Added\n\n- A race test (2026-10-28)\n")
        self.append("docs/features/alpha.md", "\nTested on 2026-10-28.\n")
        (problem,) = self.warnings(changed=True)["attacks"]
        self.assertIn("tests that make requests race changed (apps/api/tests/test_race.py)", problem)
        self.write(attacks.LOG, attacks.TEMPLATE.format(header=attacks.ATTACKS_HEADER))
        self.append("docs/README.md", "\n[Attacks](testing/attack_log.md)\n")
        self.assertNotIn("attacks", self.warnings(changed=True))


class CommandLine(LogRepo):
    def test_add_and_check_from_the_command_line(self) -> None:
        env = {"SHIPKIT_ROOT": str(self.root), "PATH": "/usr/bin:/bin"}
        script = str(SCRIPTS / "attacks.py")
        made = subprocess.run(
            [sys.executable, script, "add", "Alpha", "Again", "--test", f"{TEST}::{NAME}", "--held"],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertIn("ATK-002 Held", made.stdout)
        refused = subprocess.run([sys.executable, script, "add", "Alpha", "No test", "--held"], env=env, capture_output=True, text=True, check=False)
        self.assertEqual(refused.returncode, 2)
        checked = subprocess.run([sys.executable, script, "check"], env=env, capture_output=True, text=True, check=False)
        self.assertEqual(checked.returncode, 0, checked.stdout)


if __name__ == "__main__":
    unittest.main()
