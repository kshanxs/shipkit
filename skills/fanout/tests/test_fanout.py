"""fanout.py in a throwaway repository: plan, check, start, land, re-chain, conflicts, clean up.

    uv run pytest skills/fanout
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import fanout as parallel  # noqa: E402

# Change logs only gain lines: two branches adding under one heading keep both.
GITATTRIBUTES = "CHANGELOG.md merge=union\napps/*/CHANGELOG.md merge=union\n"

MIGRATION = '''"""{name}

Revision ID: {rev}
Revises: {down_label}
"""
from typing import Union

revision: str = "{rev}"
down_revision: Union[str, None] = {down}
'''

CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- An older line (2026-10-01)\n"
MAIN = "from app.a.router import router as a_router\nfrom app.c.router import router as c_router\n"


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def migration(rev: str, down: str | None) -> str:
    return MIGRATION.format(name=rev, rev=rev, down=f'"{down}"' if down else "None", down_label=down or "")


class ParallelRun(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "repo"
        self.root.mkdir()
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        sh("git", "init", "-q", "-b", "main", cwd=self.root)
        self.write("apps/api/migrations/versions/039_index_tuning.py", migration("039_index_tuning", None))
        self.write("docs/open_questions.md", "### Q-098\n")
        self.write("docs/testing/bug_report.md", "| BUG-043 | Closed |\n")
        self.write("apps/api/CHANGELOG.md", CHANGELOG)
        self.write("apps/api/app/main.py", MAIN)
        self.write("shipkit.toml", '[fanout.hotspots]\n"apps/api/app/main.py" = ["append", "one import and one include_router a module"]\n')
        self.write(".gitattributes", GITATTRIBUTES)
        self.write(".gitignore", ".fanout/\n")
        self.commit(self.root, "chore: start")
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.patches = [
            mock.patch.object(parallel, "docker", return_value=None),
            mock.patch.object(parallel, "regenerate", return_value=None),
            mock.patch.object(parallel, "land_checks", return_value=[]),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in self.patches:
            patch.stop()
        os.chdir(self.cwd)
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers

    def write(self, rel: str, text: str, root: Path | None = None) -> None:
        path = (root or self.root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, root: Path, message: str) -> None:
        sh("git", "add", "-A", cwd=root)
        sh("git", "commit", "-q", "-m", message, cwd=root)

    def cli(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = parallel.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def plan(self, tasks: list[dict]) -> None:
        self.assertEqual(self.cli("new", "demo")[0], 0)
        path = self.root / ".fanout/demo/plan.json"
        data = json.loads(path.read_text())
        data["tasks"] = tasks
        path.write_text(json.dumps(data))

    def task(self, task_id: str, owns: list[str], **extra) -> dict:
        return {"id": task_id, "title": task_id, "goal": "", "wave": 1, "owns": owns, "hotspots": [], "ids": {}, **extra}

    def start(self, task_id: str) -> Path:
        path = self.tmp / f"wt-{task_id}"
        code, out = self.cli("start", "demo", task_id, "--path", str(path), "--no-install")
        self.assertEqual(code, 0, out)
        return path

    # tests

    def test_next_free_numbers(self) -> None:
        self.assertEqual(parallel.next_free(), {"migration": 40, "question": 99, "bug": 44})

    def test_check_accepts_separate_tasks(self) -> None:
        self.plan(
            [
                self.task("library", ["apps/api/app/library/"], ids={"migrations": ["040_library"], "questions": ["Q-099"]}),
                self.task("transport", ["apps/api/app/transport/"], ids={"migrations": ["041_transport"]}),
            ]
        )
        code, out = self.cli("check", "demo")
        self.assertEqual(code, 0, out)

    def test_check_refuses_shared_paths_used_numbers_and_owned_hotspots(self) -> None:
        self.plan(
            [
                self.task("one", ["apps/api/app/fees/"], ids={"migrations": ["039_again"]}),
                self.task("two", ["apps/api/app/fees/online.py", "apps/api/app/main.py"], ids={"questions": ["Q-099", "Q-099"]}),
            ]
        )
        code, out = self.cli("check", "demo")
        self.assertEqual(code, 1)
        self.assertIn("both change apps/api/app/fees", out)
        self.assertIn("migration 039 is already used", out)
        self.assertIn("question 099 is also reserved", out)
        self.assertIn("main.py is a shared file", out)

    def test_stacked_tasks_may_share_paths(self) -> None:
        self.plan([self.task("api", ["apps/api/app/library/"]), self.task("screens", ["apps/api/app/library/schemas.py"], stack_on="api")])
        self.assertEqual(self.cli("check", "demo")[0], 0)

    def test_brief_names_branch_paths_and_numbers(self) -> None:
        self.plan([self.task("library", ["apps/api/app/library/"], hotspots=["apps/api/app/main.py"], ids={"migrations": ["040_library"]})])
        code, out = self.cli("brief", "demo", "library")
        self.assertEqual(code, 0, out)
        self.assertIn("fanout/demo/library", out)
        self.assertIn("`apps/api/app/library/`", out)
        self.assertIn("apps/api/app/main.py (append", out)
        self.assertIn("040_library", out)

    def test_two_tasks_land_with_changelogs_merged_and_migrations_chained(self) -> None:
        self.plan(
            [
                self.task("library", ["apps/api/app/library/"], ids={"migrations": ["040_library"]}),
                self.task("transport", ["apps/api/app/transport/"], ids={"migrations": ["041_transport"]}),
            ]
        )
        trees = {t: self.start(t) for t in ("library", "transport")}
        self.assertTrue((trees["library"] / ".fanout-env").exists())
        for task_id, rev in (("library", "040_library"), ("transport", "041_transport")):
            root = trees[task_id]
            self.write(f"apps/api/app/{task_id}/__init__.py", "", root)
            self.write(f"apps/api/migrations/versions/{rev}.py", migration(rev, "039_index_tuning"), root)
            log = CHANGELOG.replace("### Added\n\n", f"### Added\n\n- The {task_id} module (2026-10-23)\n")
            self.write("apps/api/CHANGELOG.md", log, root)
            self.commit(root, f"feat(api): {task_id}")

        code, out = self.cli("land", "demo", "library")
        self.assertEqual(code, 0, out)
        code, out = self.cli("land", "demo", "transport")
        self.assertEqual(code, 0, out)
        self.assertIn("Re-chained", out)

        integration = "fanout/demo/integration"
        log = sh("git", "show", f"{integration}:apps/api/CHANGELOG.md", cwd=self.root)
        self.assertIn("The library module", log)
        self.assertIn("The transport module", log)
        self.assertNotIn("<<<<<<<", log)
        moved = sh("git", "show", f"{integration}:apps/api/migrations/versions/041_transport.py", cwd=self.root)
        self.assertIn('down_revision: Union[str, None] = "040_library"', moved)
        self.assertIn("Revises: 040_library", moved)
        self.assertIn("landed", self.cli("status", "demo")[1])

        code, out = self.cli("cleanup", "demo", "library")
        self.assertEqual(code, 0, out)
        self.assertFalse(trees["library"].exists())

    def test_conflict_on_a_hotspot_stops_with_how_to_resolve(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"]), self.task("bb", ["apps/api/app/bb/"])])
        trees = {t: self.start(t) for t in ("aa", "bb")}
        for task_id, root in trees.items():
            self.write("apps/api/app/main.py", MAIN.replace("from app.c", f"from app.{task_id}.router import router as {task_id}_router\nfrom app.c"), root)
            self.commit(root, f"feat(api): {task_id}")
        self.assertEqual(self.cli("land", "demo", "aa")[0], 0)
        code, out = self.cli("land", "demo", "bb")
        self.assertEqual(code, 2)
        self.assertIn("apps/api/app/main.py: append", out)
        sh("git", "rebase", "--abort", cwd=trees["bb"])

    def test_install_commands_come_from_the_lock_files(self) -> None:
        self.write("uv.lock", "")
        self.write("apps/web/pnpm-lock.yaml", "")
        found = [(cmd[0], path.relative_to(self.root).as_posix() or ".") for cmd, path in parallel.install_commands(self.root)]
        if shutil.which("uv"):
            self.assertIn(("uv", "."), found)
        if shutil.which("pnpm"):
            self.assertIn(("pnpm", "apps/web"), found)
        self.write("shipkit.toml", '[fanout]\ninstall = ["echo hi"]\n')
        self.assertEqual(parallel.install_commands(self.root), [(["sh", "-c", "echo hi"], self.root)])

    def test_a_project_without_migrations_has_no_migration_number(self) -> None:
        shutil.rmtree(self.root / "apps/api/migrations")
        self.assertIsNone(parallel.migrations_dir(self.root))
        self.assertEqual(parallel.next_free()["migration"], 1)

    def test_cleanup_refuses_work_that_has_not_landed(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"])])
        root = self.start("aa")
        self.write("apps/api/app/aa/x.py", "", root)
        self.commit(root, "feat(api): aa")
        code, out = self.cli("cleanup", "demo", "aa")
        self.assertEqual(code, 2)
        self.assertIn("has not landed", out)


if __name__ == "__main__":
    unittest.main()
