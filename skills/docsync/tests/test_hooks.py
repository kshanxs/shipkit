"""Tests for the stop hook's decision and the git hooks. Standard library only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import stop_hook  # noqa: E402


class StopHookDecision(unittest.TestCase):
    def test_lets_the_session_end_when_there_are_no_errors(self) -> None:
        self.assertIsNone(stop_hook.decide({}, {"links": [], "changelog": []}))

    def test_blocks_and_names_each_problem(self) -> None:
        answer = stop_hook.decide({}, {"changelog": ["apps/api/CHANGELOG.md: not updated"], "links": []})
        self.assertEqual(answer["decision"], "block")
        self.assertIn("- [changelog] apps/api/CHANGELOG.md: not updated", answer["reason"])
        self.assertIn("check_docs.py --changed", answer["reason"])

    def test_blocks_only_once(self) -> None:
        errors = {"changelog": ["apps/api/CHANGELOG.md: not updated"]}
        self.assertIsNone(stop_hook.decide({"stop_hook_active": True}, errors))

    def test_blocks_for_open_questions_alone_and_names_them(self) -> None:
        answer = stop_hook.decide({}, {"links": []}, ["Q-003 (Payments) touches apps/api/app/billing/router.py"])
        self.assertEqual(answer["decision"], "block")
        self.assertIn("- Q-003 (Payments) touches apps/api/app/billing/router.py", answer["reason"])
        self.assertIn("open_loops.py --write", answer["reason"])
        self.assertNotIn("documentation contract", answer["reason"])
        self.assertIsNone(stop_hook.decide({"stop_hook_active": True}, {}, ["Q-003 touches x"]))

    def test_caps_a_long_list(self) -> None:
        errors = {"links": [f"file{n}.md: missing" for n in range(stop_hook.LIMIT + 7)]}
        reason = stop_hook.decide({}, errors)["reason"]
        self.assertEqual(reason.count("- [links]"), stop_hook.LIMIT)
        self.assertIn("- and 7 more", reason)


class StopHookProcess(unittest.TestCase):
    """The script as Claude Code runs it: JSON on stdin, a decision on stdout, always exit 0."""

    def run_hook(self, root: Path, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "stop_hook.py")], input=payload,
            capture_output=True, text=True, check=False, env={**os.environ, "SHIPKIT_ROOT": str(root)},
        )

    def test_blocks_on_a_broken_repository_and_never_fails(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "docs").mkdir()
            (root / "docs" / "README.md").write_text("# Docs\n\n[gone](nowhere.md)\n", encoding="utf-8")
            result = self.run_hook(root, "{}")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["decision"], "block")
            again = self.run_hook(root, '{"stop_hook_active": true}')
            self.assertEqual((again.returncode, again.stdout), (0, ""))

    def test_survives_input_that_is_not_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_hook(Path(folder), "not json")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("docsync stop hook skipped", result.stderr)


class PreCommitHook(unittest.TestCase):
    """The real hook in a real repository: git refuses the commit, then accepts it."""

    def setUp(self) -> None:
        from test_check_docs import FILES

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        for name, text in FILES.items():
            self.write(name, text)
        scripts = self.root / ".agents" / "skills" / "docsync" / "scripts"
        shutil.copytree(SCRIPTS, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        hook = self.root / ".githooks" / "pre-commit"
        hook.parent.mkdir()
        shutil.copy(HOOKS / "pre-commit", hook)
        hook.chmod(0o755)
        for args in (["init", "-q"], ["config", "user.email", "test@example.com"], ["config", "user.name", "Test"],
                     ["config", "commit.gpgsign", "false"], ["config", "core.hooksPath", ".githooks"], ["add", "-A"]):
            self.git(*args)
        self.assertEqual(self.git("commit", "-q", "-m", "baseline").returncode, 0)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, text: str, mode: str = "w") -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(text)

    def git(self, *args: str) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if key != "SHIPKIT_ROOT"}
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=False, env=env)

    def commits(self) -> int:
        return int(self.git("rev-list", "--count", "HEAD").stdout)

    def test_refuses_code_without_a_changelog_line_then_accepts_it_with_one(self) -> None:
        self.write("apps/api/app/alpha/models.py", "\n\n# a fix\n", mode="a")
        self.git("add", "-A")
        refused = self.git("commit", "-m", "fix")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("ERROR [changelog] apps/api/CHANGELOG.md", refused.stdout + refused.stderr)
        self.assertIn("Commit stopped by the documentation contract", refused.stderr)
        self.assertEqual(self.commits(), 1)

        self.write("apps/api/CHANGELOG.md", "\n### Fixed\n\n- A fix (2026-10-06)\n", mode="a")
        self.git("add", "-A")
        accepted = self.git("commit", "-m", "fix")
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertEqual(self.commits(), 2)

    def test_refuses_a_broken_link_in_a_document(self) -> None:
        self.write("docs/features/alpha.md", "\n[gone](nowhere.md)\n", mode="a")
        self.git("add", "-A")
        refused = self.git("commit", "-m", "docs")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("ERROR [links]", refused.stdout + refused.stderr)

    def test_can_be_bypassed_on_purpose(self) -> None:
        self.write("apps/api/app/alpha/models.py", "# a fix\n", mode="a")
        self.git("add", "-A")
        self.assertEqual(self.git("commit", "--no-verify", "-m", "fix").returncode, 0)


class CommitMessageHook(unittest.TestCase):
    """The real commit-msg hook, given the file git would hand it."""

    def verdict(self, message: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "COMMIT_EDITMSG"
            path.write_text(message, encoding="utf-8")
            return subprocess.run(["sh", str(HOOKS / "commit-msg"), str(path)], capture_output=True, text=True, check=False)

    def test_accepts_conventional_commits(self) -> None:
        for message in (
            "fix(billing): charge a late fee once\n",
            "feat: billing hub, document engine and roles\n\nA body.\n",
            "refactor(repo)!: move apps under apps/\n",
            "docs!: one feature tree\n",
            "chore(deps): update dependencies\n",
            "# a comment git strips\n\nfeat(web): project picker\n",
        ):
            self.assertEqual(self.verdict(message).returncode, 0, message)

    def test_accepts_what_git_writes_itself(self) -> None:
        for message in ("Merge branch 'main' into develop\n", 'Revert "feat: project picker"\n', "fixup! fix(billing): charge a late fee once\n"):
            self.assertEqual(self.verdict(message).returncode, 0, message)

    def test_refuses_a_message_with_no_type_and_shows_the_form(self) -> None:
        for message in ("fixed the billing bug\n", "Fix: billing bug\n", "fix:no space\n", "update(billing) late fee\n"):
            result = self.verdict(message)
            self.assertEqual(result.returncode, 1, message)
            self.assertIn("type(scope): summary", result.stderr)

    def test_leaves_an_empty_message_for_git_to_refuse(self) -> None:
        self.assertEqual(self.verdict("# only a comment\n").returncode, 0)


if __name__ == "__main__":
    unittest.main()
