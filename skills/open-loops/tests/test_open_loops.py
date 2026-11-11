"""Tests for open_loops.py: a small repository that passes, then one thing broken per test."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "open_loops.py"

REGISTER = """# Open questions

<!-- counts:start -->
<!-- counts:end -->

<!-- questions:start -->
## Fees

### Q-001

**Who bears the gateway fee?**
Decision · Open · raised 2026-10-06 · checked 2026-10-16 · needed before payment work

- **Context:** the gateway takes its fee from each settlement.
- **Today:** the platform account pays it.
- **If the workspace:** the settlement report shows the fee,
  and the refund policy says so.
- **Recommended:** the workspace.
- **Where:** [Fees](features/fees.md#payments) · [Policies](features/public_site.md)
- **Code:** `apps/api/app/fees/`
- **Lines:**
  - `apps/api/app/fees/router.py:2` `amount = bill`: the amount charged is the bill

### Q-002

**One late-fee rule per workspace?**
Confirmation · Open · raised 2026-10-03

- **Context:** the brief asked for late fees and said nothing of fee types.
- **Today:** one rule per workspace.
- **Until answered:** fee types cannot carry their own rule.
- **Where:** [Fees](features/fees.md)

## Answered

### Q-003

**How long does a session last?**
Decision · Answered 2026-10-09 · raised 2026-10-06

- **Answer:** seven days for everyone.
<!-- questions:end -->
"""

FEES = "# Fees\n\n## Payments\n\nText.\n"
POLICIES = "# Policies\n\n## Gaps\n\n<!-- open-questions:start bare -->\n<!-- open-questions:end -->\n\n## Related\n"


class OpenQuestions(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.write("docs/open_questions.md", REGISTER)
        self.write("docs/features/fees.md", FEES)
        self.write("docs/features/public_site.md", POLICIES)
        self.write("docs/features/teams.md", "# Teams\n")
        self.write("apps/api/app/fees/router.py", "def pay():\n    amount = bill\n")
        self.run_script("--write")

    def tearDown(self) -> None:
        self.folder.cleanup()

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def read(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def replace(self, path: str, old: str, new: str) -> None:
        text = self.read(path)
        self.assertIn(old, text)
        self.write(path, text.replace(old, new))

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env={**os.environ, "SHIPKIT_ROOT": str(self.root)}
        )

    def problems(self) -> str:
        return self.run_script().stdout

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.test", "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True,
        )

    def test_a_sound_register_passes(self) -> None:
        done = self.run_script()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("2 open, 1 answered or dropped, 0 problems", done.stdout)

    def test_write_puts_a_list_at_the_end_of_each_document_a_question_names(self) -> None:
        fees = self.read("docs/features/fees.md")
        self.assertTrue(fees.startswith(FEES.rstrip("\n")))
        self.assertIn("## Open questions", fees)
        self.assertIn("- [Q-001](../open_questions.md#q-001) · Decision · Who bears the gateway fee?", fees)
        self.assertIn("- [Q-002](../open_questions.md#q-002) · Confirmation · One late-fee rule per workspace?", fees)
        self.assertNotIn("open-questions", self.read("docs/features/teams.md"))

    def test_a_bare_list_stays_where_its_markers_are_and_has_no_heading(self) -> None:
        policies = self.read("docs/features/public_site.md")
        self.assertNotIn("## Open questions", policies)
        self.assertLess(policies.index("Q-001"), policies.index("## Related"))
        self.assertNotIn("Q-002", policies)

    def test_write_is_stable_when_run_twice(self) -> None:
        before = {path: self.read(path) for path in ("docs/open_questions.md", "docs/features/fees.md", "docs/features/public_site.md")}
        self.run_script("--write")
        self.assertEqual(before, {path: self.read(path) for path in before})

    def test_an_answered_question_leaves_the_lists(self) -> None:
        text = self.read("docs/open_questions.md")
        entry = text[text.index("### Q-002") : text.index("## Answered")]
        moved = entry.replace("Confirmation · Open ·", "Confirmation · Answered 2026-10-14 ·").replace(
            "- **Where:**", "- **Answer:** yes, one rule.\n- **Where:**"
        )
        self.write("docs/open_questions.md", text.replace(entry, "").replace("<!-- questions:end -->", moved + "<!-- questions:end -->"))
        self.assertIn("lists: the open questions list is out of date", self.problems())
        self.run_script("--write")
        self.assertNotIn("Q-002", self.read("docs/features/fees.md"))
        self.assertEqual(self.run_script().returncode, 0)

    def test_a_list_goes_when_its_last_question_is_answered_and_a_bare_one_says_none(self) -> None:
        self.replace("docs/open_questions.md", " · [Policies](features/public_site.md)", "")
        self.replace("docs/open_questions.md", "[Fees](features/fees.md#payments)", "[Teams](features/teams.md)")
        self.replace("docs/open_questions.md", "- **Where:** [Fees](features/fees.md)", "- **Where:** [Teams](features/teams.md)")
        self.run_script("--write")
        self.assertEqual(self.read("docs/features/fees.md"), FEES)
        self.assertIn("No question is open here", self.read("docs/features/public_site.md"))
        self.assertIn("Q-001", self.read("docs/features/teams.md"))

    def test_a_list_edited_by_hand_is_reported(self) -> None:
        self.replace("docs/features/fees.md", "Who bears the gateway fee?", "Who pays?")
        self.assertIn("docs/features/fees.md: lists:", self.problems())

    def test_a_number_used_twice_is_reported(self) -> None:
        self.replace("docs/open_questions.md", "### Q-002", "### Q-001")
        self.assertIn("ids: Q-001 is also on line", self.problems())

    def test_an_unknown_kind_or_status_is_reported(self) -> None:
        self.replace("docs/open_questions.md", "Confirmation · Open", "Wish · Open")
        self.assertIn("words: `Wish` is not one of", self.problems())
        self.replace("docs/open_questions.md", "Wish · Open", "Confirmation · Pending")
        self.assertIn("words: the second part is one of", self.problems())

    def test_an_open_question_needs_today_an_implication_and_a_document(self) -> None:
        self.replace("docs/open_questions.md", "- **Today:** one rule per workspace.\n", "")
        self.replace("docs/open_questions.md", "- **Until answered:** fee types cannot carry their own rule.\n", "")
        self.replace("docs/open_questions.md", "- **Where:** [Fees](features/fees.md)\n", "- **Where:** the fees page\n")
        found = self.problems()
        self.assertIn("fields: Q-002 has no `Today` line", found)
        self.replace("docs/open_questions.md", "- **Context:** the brief asked for late fees and said nothing of fee types.\n", "")
        self.assertIn("fields: Q-002 has no `Context` line", self.problems())
        self.assertIn("fields: Q-002 says nothing of what an answer changes", found)
        self.assertIn("where: Q-002 links to no document", found)

    def test_an_answered_question_needs_its_answer_and_its_place(self) -> None:
        self.replace("docs/open_questions.md", "- **Answer:** seven days for everyone.\n", "")
        self.assertIn("fields: Q-003 has no `Answer` line", self.problems())
        self.replace("docs/open_questions.md", "Decision · Open · raised 2026-10-06 · checked 2026-10-16 · needed before payment work", "Decision · Answered 2026-10-14 · raised 2026-10-06")
        self.assertIn("place: Q-001 is Answered, so it belongs under `## Answered`", self.problems())

    def test_a_missing_document_or_code_path_is_reported(self) -> None:
        self.replace("docs/open_questions.md", "[Policies](features/public_site.md)", "[Policies](features/gone.md)")
        self.replace("docs/open_questions.md", "`apps/api/app/fees/`", "`apps/api/app/gone/`")
        found = self.problems()
        self.assertIn("where: Q-001 links to docs/features/gone.md, which does not exist", found)
        self.assertIn("code: Q-001 names `apps/api/app/gone`, which does not exist", found)

    def test_a_document_cannot_name_a_question_the_register_lacks(self) -> None:
        self.write("docs/features/teams.md", "# Teams\n\nSee Q-404.\n")
        self.assertIn("docs/features/teams.md:3: refs: Q-404 is not in the register", self.problems())

    def test_stale_counts_are_reported_and_written(self) -> None:
        self.assertIn("| Fees | 2 | 1 | 1 | 0 | 0 |", self.read("docs/open_questions.md"))
        self.replace("docs/open_questions.md", "| Fees | 2 |", "| Fees | 9 |")
        self.assertIn("counts: the table is out of date", self.problems())

    def test_for_finds_questions_by_code_folder_and_by_document(self) -> None:
        by_code = self.run_script("--for", "apps/api/app/fees/router.py").stdout
        self.assertIn("Q-001", by_code)
        self.assertNotIn("Q-002", by_code)
        self.assertIn("Today: the platform account pays it.", by_code)
        self.assertIn("Q-002", self.run_script("--for", "docs/features/fees.md").stdout)
        self.assertEqual(self.run_script("--for", "docs/features/teams.md").stdout, "")

    def test_changed_names_the_questions_a_change_touches_until_the_register_changes(self) -> None:
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore: start")
        self.assertIn("0 touch this change set", self.run_script("--changed").stdout)
        self.write("apps/api/app/fees/router.py", "def pay():\n    amount = bill\nchanged = True\n")
        found = self.run_script("--changed")
        self.assertEqual(found.returncode, 0)
        self.assertIn("Q-001 (Who bears the gateway fee?) touches apps/api/app/fees/router.py", found.stdout)
        self.replace("docs/open_questions.md", "the platform account pays it", "the platform account still pays it")
        self.assertIn("0 touch this change set", self.run_script("--changed").stdout)

    def test_the_stop_hook_is_reminded_once_for_each_set(self) -> None:
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore: start")
        self.write("apps/api/app/fees/router.py", "def pay():\n    amount = bill\nchanged = True\n")
        ask = "import open_loops as q; print(len(q.remind_once()))"
        run = lambda: subprocess.run(  # noqa: E731
            [sys.executable, "-c", ask], capture_output=True, text=True, cwd=SCRIPT.parent, env={**os.environ, "SHIPKIT_ROOT": str(self.root)}
        ).stdout.strip()
        self.assertEqual(run(), "1")
        self.assertEqual(run(), "0")
        self.write("docs/features/public_site.md", self.read("docs/features/public_site.md") + "\nMore.\n")
        self.assertEqual(run(), "1")


    def test_a_question_with_code_needs_lines_and_each_anchor_a_file(self) -> None:
        text = self.read("docs/open_questions.md")
        self.write("docs/open_questions.md", text.replace("- **Lines:**\n  - `apps/api/app/fees/router.py:2` `amount = bill`: the amount charged is the bill\n", ""))
        self.assertIn("fields: Q-001 has no `Lines` line", self.problems())
        self.write("docs/open_questions.md", text.replace("fees/router.py:2", "fees/gone.py:2"))
        self.assertIn("lines: Q-001 names `apps/api/app/fees/gone.py`, which is not a file", self.problems())

    def test_an_anchor_that_moved_is_reported_and_moved_by_write(self) -> None:
        self.write("apps/api/app/fees/router.py", "import x\n\ndef pay():\n    amount = bill\n")
        self.assertIn("`amount = bill` moved from apps/api/app/fees/router.py:2 to line 4; run open_loops.py --write", self.problems())
        self.run_script("--write")
        self.assertIn("`apps/api/app/fees/router.py:4` `amount = bill`", self.read("docs/open_questions.md"))
        self.assertEqual(self.run_script().returncode, 0)

    def test_an_anchor_whose_text_is_gone_asks_for_the_question_to_be_read_again(self) -> None:
        self.write("apps/api/app/fees/router.py", "def pay():\n    amount = total_with_fee\n")
        self.run_script("--write")
        found = self.problems()
        self.assertIn("lines: Q-001: `amount = bill` is no longer in apps/api/app/fees/router.py", found)
        self.assertIn("read it again and update Context, Today and Lines", found)
        self.assertNotEqual(self.run_script().returncode, 0)

    def test_a_checked_date_cannot_come_before_the_question(self) -> None:
        self.replace("docs/open_questions.md", "checked 2026-10-16", "checked 2026-10-01")
        self.assertIn("format: a question cannot be checked before it was raised", self.problems())

    def test_show_prints_the_entry_and_the_code_under_it(self) -> None:
        shown = self.run_script("--show", "q-001").stdout
        self.assertIn("raised 2026-10-06 · checked 2026-10-16", shown)
        self.assertIn("Context: the gateway takes its fee from each settlement.", shown)
        self.assertIn("apps/api/app/fees/router.py:2  (the amount charged is the bill)\n      amount = bill", shown)
        self.assertIn("not checked against the code", self.run_script("--show", "Q-002").stdout)
        self.assertEqual(self.run_script("--show", "Q-404").returncode, 1)

    def test_for_names_the_file_of_an_anchor_and_says_why(self) -> None:
        found = self.run_script("--for", "apps/api/app/fees/router.py").stdout
        self.assertIn("Why: the gateway takes its fee from each settlement.", found)


if __name__ == "__main__":
    unittest.main()
