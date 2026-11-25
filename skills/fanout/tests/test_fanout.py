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


class RepoCase(unittest.TestCase):
    """A throwaway repository with a migration, registers and a hotspot; no tests of its own."""

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


class ParallelRun(RepoCase):
    def test_next_free_numbers(self) -> None:
        self.assertEqual(parallel.next_free(), {"migration": 40, "question": 99, "bug": 44, "attack": 1})

    def test_attack_numbers_come_from_every_branch_and_every_plan(self) -> None:
        sh("git", "switch", "-q", "-c", "other", cwd=self.root)
        self.write("docs/testing/attack_log.md", "| ATK-110 | 2026-10-01 | A | B | None | Not a flaw |\n")
        self.commit(self.root, "docs: an attack")
        sh("git", "switch", "-q", "main", cwd=self.root)
        self.assertEqual(parallel.next_free()["attack"], 111)
        self.plan([self.task("one", ["apps/api/app/one/"], ids={"attacks": ["ATK-111"]})])
        self.assertEqual(parallel.next_free()["attack"], 112)
        path = self.root / ".fanout/demo/plan.json"
        data = json.loads(path.read_text())
        data["tasks"] = [self.task("two", ["apps/api/app/two/"], ids={"attacks": ["ATK-110"]})]
        path.write_text(json.dumps(data))
        code, out = self.cli("check", "demo")
        self.assertEqual(code, 1)
        self.assertIn("attack 110 is already used", out)

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

    def test_land_refuses_a_committed_dependency_link(self) -> None:
        self.write(".gitignore", ".fanout/\nnode_modules/\n")
        self.commit(self.root, "chore: ignore dependencies")
        self.plan([self.task("library", ["apps/api/app/library/"])])
        tree = self.start("library")
        self.write("apps/api/app/library/__init__.py", "", tree)
        (tree / "node_modules").symlink_to(self.root / "node_modules")
        self.commit(tree, "feat: library")
        code, out = self.cli("land", "demo", "library")
        self.assertNotEqual(code, 0)
        self.assertIn("commits dependency paths: node_modules", out)

    def test_cleanup_refuses_work_that_has_not_landed(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"])])
        root = self.start("aa")
        self.write("apps/api/app/aa/x.py", "", root)
        self.commit(root, "feat(api): aa")
        code, out = self.cli("cleanup", "demo", "aa")
        self.assertEqual(code, 2)
        self.assertIn("has not landed", out)


STUB_DOCKER = """#!/bin/sh
# A stand-in for docker: lists the containers in $STUB_PS, answers DBSIZE from $STUB_KEYS, logs every call.
echo "$*" >> "$STUB_LOG"
case "$1" in
  info) exit 0 ;;
  ps) cat "$STUB_PS" ;;
  exec)
    keys=$(grep "^$2 " "$STUB_KEYS" | cut -d' ' -f2)
    [ -n "$keys" ] || { echo "Error: container $2 is not running" >&2; exit 1; }
    echo "$keys" ;;
  *) exit 1 ;;
esac
"""


class Leftovers(RepoCase):
    """`fanout.py leftovers` reports what an abandoned or finished run left behind, and changes nothing."""

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.bin / "docker"
        stub.write_text(STUB_DOCKER)
        stub.chmod(0o755)
        self.ps, self.keys, self.log = self.tmp / "ps.txt", self.tmp / "keys.txt", self.tmp / "docker.log"
        for path in (self.ps, self.keys, self.log):
            path.write_text("")
        env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "STUB_PS": str(self.ps), "STUB_KEYS": str(self.keys), "STUB_LOG": str(self.log)}
        self.stub_env = mock.patch.dict(os.environ, env)
        self.stub_env.start()

    def tearDown(self) -> None:
        self.stub_env.stop()
        super().tearDown()

    def container(self, name: str, hours_old: float, keys: int | None = None) -> None:
        from datetime import datetime, timedelta, timezone

        created = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).strftime("%Y-%m-%d %H:%M:%S +0000 UTC")
        with self.ps.open("a") as out:
            out.write(f"{name}\t{created}\n")
        if keys is not None:
            with self.keys.open("a") as out:
                out.write(f"{name} {keys}\n")

    def leftovers(self, *argv: str, docker: list[str] | None = None) -> tuple[int, str]:
        with mock.patch.object(parallel, "docker", return_value=docker):
            return self.cli("leftovers", *argv)

    def old_commit(self, root: Path, message: str, hours_old: int) -> None:
        sh("git", "add", "-A", cwd=root)
        date = f"@{int(__import__('time').time()) - hours_old * 3600} +0000"
        with mock.patch.dict(os.environ, {"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date}):
            sh("git", "commit", "-q", "-m", message, cwd=root)

    def test_containers_of_a_missing_plan_a_landed_task_or_too_old_are_listed_with_keys(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"]), self.task("bb", ["apps/api/app/bb/"]), self.task("dd", ["apps/api/app/dd/"])])
        sh("git", "branch", "fanout/demo/aa", "fanout/demo/integration", cwd=self.root)
        (self.root / ".fanout/demo/state.json").write_text(json.dumps({"aa": {"landed": "abc", "redis": "fanout-demo-aa"}}))
        self.container("fanout-demo-aa", 1, keys=3)
        self.container("fanout-demo-bb", 30, keys=12)  # its task is still working, but the container is old
        self.container("fanout-demo-dd", 1, keys=5)  # in use: not a leftover
        self.container("fanout-gone-x", 72, keys=0)  # no plan for run "gone"
        self.container("fanout-gone-y", 72)  # not reachable: no DBSIZE
        self.container("someone-else", 500)  # not ours
        code, out = self.leftovers(docker=["docker"])
        self.assertEqual(code, 0, out)
        self.assertIn("fanout-demo-aa", out)
        self.assertIn("task landed", out)
        self.assertIn("fanout.py cleanup demo aa", out)
        self.assertIn("fanout-demo-bb", out)
        self.assertIn("older than 24h", out)
        self.assertIn("docker rm -f fanout-demo-bb", out)
        self.assertIn("12 keys", out)
        self.assertNotIn("fanout-demo-dd", out)
        self.assertIn("run plan missing", out)
        self.assertIn("docker rm -f fanout-gone-x", out)
        self.assertIn("0 keys", out)
        self.assertIn("fanout-gone-y", out)
        self.assertIn("not reachable", out)
        self.assertNotIn("someone-else", out)
        code, out = self.leftovers("--hours", "48", docker=["docker"])
        self.assertNotIn("fanout-demo-bb", out)

    def test_worktrees_and_branches_of_landed_abandoned_and_planless_tasks_are_listed(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"]), self.task("bb", ["apps/api/app/bb/"]), self.task("cc", ["apps/api/app/cc/"])])
        trees = {t: self.start(t) for t in ("aa", "bb", "cc")}
        self.write("apps/api/app/aa/x.py", "", trees["aa"])
        self.commit(trees["aa"], "feat: aa")
        self.assertEqual(self.cli("land", "demo", "aa")[0], 0)
        self.write("apps/api/app/bb/x.py", "", trees["bb"])
        self.old_commit(trees["bb"], "feat: bb", hours_old=72)
        self.write("apps/api/app/bb/y.py", "", trees["bb"])  # uncommitted work
        self.write("apps/api/app/cc/x.py", "", trees["cc"])
        self.commit(trees["cc"], "feat: cc")  # fresh: still being worked on
        sh("git", "branch", "fanout/old/zz", "main", cwd=self.root)  # a run whose plan is gone
        code, out = self.leftovers()
        self.assertEqual(code, 0, out)
        self.assertIn("fanout/demo/aa", out)
        self.assertIn("fanout.py cleanup demo aa", out)
        self.assertIn(str(trees["aa"]), out)
        self.assertIn("fanout/demo/bb", out)
        self.assertIn("abandoned", out)
        self.assertIn("1 unlanded commit", out)
        self.assertIn("uncommitted changes", out)
        self.assertIn("fanout.py cleanup demo bb --force", out)
        self.assertNotIn("fanout/demo/cc", out)
        self.assertIn("fanout/old/zz", out)
        self.assertIn("git branch -D fanout/old/zz", out)
        self.assertNotIn("fanout/demo/integration", out)

    def test_json_is_valid_and_docker_missing_is_reported(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"])])
        sh("git", "branch", "fanout/demo/aa", "fanout/demo/integration", cwd=self.root)  # started, no commits, no worktree
        code, out = self.leftovers("--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["docker"])
        [item] = data["leftovers"]
        self.assertEqual((item["kind"], item["run"], item["task"]), ("branch", "demo", "aa"))
        self.assertEqual(item["command"], "fanout.py cleanup demo aa")
        self.container("fanout-gone-x", 72, keys=0)
        code, out = self.leftovers("--json", docker=["docker"])
        data = json.loads(out)
        [box] = [i for i in data["leftovers"] if i["kind"] == "container"]
        self.assertEqual((box["name"], box["keys"], box["command"]), ("fanout-gone-x", 0, "docker rm -f fanout-gone-x"))

    def test_nothing_is_removed(self) -> None:
        self.plan([self.task("aa", ["apps/api/app/aa/"])])
        tree = self.start("aa")
        self.write("apps/api/app/aa/x.py", "", tree)
        self.commit(tree, "feat: aa")
        self.assertEqual(self.cli("land", "demo", "aa")[0], 0)
        self.container("fanout-demo-aa", 100, keys=1)
        before = sh("git", "for-each-ref", cwd=self.root), sh("git", "worktree", "list", cwd=self.root)
        self.assertEqual(self.leftovers(docker=["docker"])[0], 0)
        self.assertEqual((sh("git", "for-each-ref", cwd=self.root), sh("git", "worktree", "list", cwd=self.root)), before)
        self.assertTrue(tree.exists())
        calls = self.log.read_text().split()
        self.assertNotIn("rm", calls)
        self.assertNotIn("stop", calls)

    def test_no_leftovers_says_so(self) -> None:
        code, out = self.leftovers(docker=["docker"])
        self.assertEqual(code, 0)
        self.assertIn("No leftovers", out)


if __name__ == "__main__":
    unittest.main()
