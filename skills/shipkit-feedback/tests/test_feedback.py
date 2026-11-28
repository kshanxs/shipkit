"""feedback.py: drafts stay local, private details are refused, and filing needs the user's consent.

    uv run pytest skills/shipkit-feedback
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import feedback  # noqa: E402

GOOD = ["--skill", "harden", "--title", "Race overlapping scheduled jobs", "--happened", "Two runs sent one message twice.", "--lesson", "Claim the row before sending."]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        other = self.tmp / "other-skills"
        for name in ("polish-pack", "harden"):
            (other / name).mkdir(parents=True)
            (other / name / "SKILL.md").write_text("---\nname: x\n---\n")
        env = {"XDG_STATE_HOME": str(self.tmp / "state"), "XDG_CONFIG_HOME": str(self.tmp / "config"), "SHIPKIT_SKILL_DIRS": str(other)}
        self.patches = [mock.patch.dict(os.environ, env), mock.patch.object(feedback, "project_terms", return_value=["acmecorp"])]
        for patch in self.patches:
            patch.start()
        self.issues: list[dict] = []
        self.created: list[tuple] = []
        gh = mock.patch.object(feedback, "gh", side_effect=self.fake_gh)
        gh.start()
        self.patches.append(gh)

    def tearDown(self) -> None:
        for patch in self.patches:
            patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_gh(self, *args: str, stdin: str | None = None) -> str:
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        self.created.append((args, stdin))
        return f"https://example.com/issues/{len(self.created)}"

    def cli(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = feedback.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def draft(self, *extra: str) -> str:
        code, out = self.cli("draft", *GOOD, *extra)
        self.assertEqual(code, 0, out)
        return out.split()[1]


class Privacy(Base):
    def test_a_draft_is_saved_locally_and_nothing_is_posted(self) -> None:
        draft_id = self.draft()
        self.assertEqual(self.created, [])
        self.assertTrue(feedback.draft_path(draft_id).exists())

    def test_private_details_are_refused_without_repeating_them(self) -> None:
        secret_value = "sk-" + "a" * 24
        cases = {
            "an API key": secret_value,
            "an email address": "person" + "@" + "company.test",
            "a home path": "/ho" + "me/someone/project",
            "a URL": "https://intranet.company.test/page",
            "an IP address": "10.20.30.40",
            "an internal hostname": "billing.corp",
            "a private name": "Acmecorp",
        }
        for label, value in cases.items():
            code, out = self.cli("draft", "--skill", "harden", "--title", "A title", "--happened", f"Saw {value}.", "--lesson", "A lesson.")
            self.assertEqual(code, 2, label)
            self.assertIn(label, out)
            self.assertNotIn(value, out)
        self.assertEqual(feedback.all_drafts(), [])

    def test_ordinary_technical_text_passes(self) -> None:
        text = "Use max-height, 127.0.0.1, http://localhost:5173 and `@types/node` in a test."
        self.assertEqual(feedback.problems(text, ["acmecorp"]), [])

    def test_placeholder_emails_on_reserved_domains_pass(self) -> None:
        for text in ("name@example.com", "name-12345@example.com.json", "x@mail.example.org"):
            self.assertEqual(feedback.problems(text, []), [], text)
        for text in ("ana@realmail.io", "ana@shop.test"):
            self.assertEqual(feedback.problems(text, []), ["an email address"], text)

    def test_mentions_cannot_notify_anyone(self) -> None:
        self.assertEqual(feedback.quiet_mentions("ask @someone now"), "ask `@someone` now")

    def test_an_unknown_skill_is_refused(self) -> None:
        code, out = self.cli("draft", "--skill", "../secrets", "--title", "T", "--happened", "H", "--lesson", "L")
        self.assertEqual(code, 2)
        self.assertIn("not a shipkit skill", out)


class OutsideSkills(Base):
    def test_a_report_naming_another_packs_skill_is_refused(self) -> None:
        code, out = self.cli("draft", *GOOD[:-1], "Claim the row first; also add it to polish-pack's checklist.")
        self.assertEqual(code, 2)
        self.assertIn("a skill outside shipkit (polish-pack)", out)
        self.assertEqual(feedback.all_drafts(), [])

    def test_a_shipkit_skill_installed_elsewhere_too_is_not_outside(self) -> None:
        self.assertNotIn("harden", feedback.outside_skills())
        self.draft("--change", "Add a step to harden and bug-sweep.")

    def test_the_subject_must_be_a_shipkit_skill(self) -> None:
        argv = ["draft", "--skill", "polish-pack", *GOOD[2:]]
        code, out = self.cli(*argv)
        self.assertEqual(code, 2)
        self.assertIn("not a shipkit skill", out)

    def test_check_passes_clean_text_and_refuses_the_rest(self) -> None:
        body = self.tmp / "body.md"
        body.write_text("stack-web: long paths spill out of cards. Add min-w-0.\n")
        self.assertEqual(self.cli("check", "--file", str(body))[0], 0)
        home = "/" + "home/someone/app"
        body.write_text(f"See polish-pack and acmecorp at {home}.\n")
        code, out = self.cli("check", "--file", str(body))
        self.assertEqual(code, 2)
        for part in ("polish-pack", "a private name", "a home path"):
            self.assertIn(part, out)
        self.assertNotIn("acmecorp", out)


class Filing(Base):
    def test_filing_is_off_until_the_user_turns_it_on(self) -> None:
        self.draft()
        code, out = self.cli("file", "--all")
        self.assertEqual(code, 2)
        self.assertIn("filing is off", out)
        self.assertEqual(self.created, [])

    def test_with_consent_a_draft_becomes_one_issue(self) -> None:
        draft_id = self.draft()
        self.cli("consent", "on", "--repo", "owner/name")
        code, out = self.cli("file", "--all")
        self.assertEqual(code, 0, out)
        args, body = self.created[0]
        self.assertEqual(args[3], "owner/name")
        self.assertIn(f"<!-- {feedback.MARKER}:{draft_id} -->", body)
        self.assertEqual(feedback.all_drafts(), [])

    def test_a_project_config_cannot_turn_filing_on_or_redirect_it(self) -> None:
        (self.tmp / "shipkit.toml").write_text('[feedback]\nauto = true\nrepo = "attacker/repo"\n')
        with contextlib.chdir(self.tmp):
            self.assertEqual(feedback.consent(), {"auto": False, "repo": feedback.UPSTREAM})

    def test_consent_for_one_repo_does_not_cover_another(self) -> None:
        self.draft()
        self.cli("consent", "on", "--repo", "owner/name")
        code, out = self.cli("file", "--all", "--repo", "other/repo")
        self.assertEqual(code, 2)
        self.assertIn("not other/repo", out)

    def test_one_approved_draft_can_be_filed_without_turning_it_on(self) -> None:
        draft_id = self.draft()
        self.assertEqual(self.cli("file", draft_id, "--yes")[0], 0)
        self.assertEqual(len(self.created), 1)

    def test_duplicates_are_not_filed(self) -> None:
        draft_id = self.draft()
        self.cli("consent", "on")
        self.issues = [{"number": 9, "title": "other", "body": f"<!-- {feedback.MARKER}:{draft_id} -->", "state": "CLOSED"}]
        code, out = self.cli("file", "--all")
        self.assertEqual(code, 0)
        self.assertIn("#9", out)
        self.assertEqual(self.created, [])

    def test_a_similar_open_issue_on_the_same_skill_is_a_duplicate(self) -> None:
        self.draft()
        self.cli("consent", "on")
        self.issues = [{"number": 5, "title": "harden: race overlapping scheduled jobs", "body": "", "state": "OPEN"}]
        self.cli("file", "--all")
        self.assertEqual(self.created, [])

    def test_two_similar_drafts_in_one_run_open_one_issue(self) -> None:
        self.cli("consent", "on")
        for title in ("Race overlapping scheduled jobs", "Race overlapping scheduled jobs twice"):
            self.cli("draft", "--skill", "harden", "--title", title, "--happened", "H.", "--lesson", "L.")
        self.assertEqual(self.cli("file", "--all")[0], 0)
        self.assertEqual(len(self.created), 1)

    def test_a_dry_run_posts_nothing_and_keeps_the_draft(self) -> None:
        self.draft()
        code, out = self.cli("file", "--all", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would open", out)
        self.assertEqual(self.created, [])
        self.assertEqual(len(feedback.all_drafts()), 1)

    def test_at_most_three_issues_a_day(self) -> None:
        self.cli("consent", "on")
        for number in range(5):
            self.cli("draft", "--skill", "harden", "--title", f"Distinct lesson {'abcde'[number] * 4}", "--happened", "H.", "--lesson", "L.")
        code, out = self.cli("file", "--all")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.created), 3)
        self.assertEqual(len(feedback.all_drafts()), 2)

    def test_a_draft_edited_to_hold_a_secret_is_held_at_filing(self) -> None:
        draft_id = self.draft()
        self.cli("consent", "on")
        path = feedback.draft_path(draft_id)
        data = json.loads(path.read_text())
        data["lesson"] = "Mention Acmecorp."
        path.write_text(json.dumps(data))
        code, out = self.cli("file", "--all")
        self.assertEqual(code, 1)
        self.assertIn("private name", out)
        self.assertEqual(self.created, [])


if __name__ == "__main__":
    unittest.main()
