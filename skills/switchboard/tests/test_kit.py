"""kit.py: the kits' plans and the autopilot, decided from a repository's state.

    uv run pytest skills/switchboard
"""

from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import kit  # noqa: E402
import route  # noqa: E402

CONFIG = """
[stack]
api_dir = "apps/api"
web_dirs = ["apps/web"]
native_dir = "apps/mobile"
"""


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(root), *args],
        check=True, capture_output=True,
    )  # fmt: skip


class Repo(unittest.TestCase):
    """A project on a feature branch off main: an API and a web app, no mobile app."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "shipkit.toml").write_text(CONFIG)
        for path in ("apps/api/app/main.py", "apps/web/src/main.ts", "docs/README.md"):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        git(self.root, "checkout", "-q", "-b", "feat")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, path: str, text: str = "y\n") -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)

    def commit(self, *paths: str) -> None:
        for p in paths:
            self.write(p)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "change")

    def facts(self, request: str = "") -> kit.Facts:
        return kit.gather(self.root, request)

    def states(self, name: str, request: str = "", **kw) -> dict[str, str]:
        return {s.skill: s.state for s in kit.plan(name, self.facts(request), **kw)}

    def now(self, request: str = "") -> list[str]:
        return [x["run"] for x in kit.advise(self.facts(request)).now]


class Facts(Repo):
    def test_changes_against_the_default_branch_and_the_working_tree(self):
        self.commit("apps/api/app/invoices.py")
        self.write("apps/web/src/invoices.ts")
        self.write("docs/invoices.md")
        f = self.facts()
        self.assertEqual(f.base, "main")
        self.assertEqual(f.ahead, 1)
        self.assertEqual(f.code_changed, ["apps/api/app/invoices.py", "apps/web/src/invoices.ts"])
        self.assertEqual(f.docs_changed, ["docs/invoices.md"])
        self.assertEqual(f.touches("api"), ["apps/api/app/invoices.py"])

    def test_a_migration_is_a_schema_change(self):
        self.commit("apps/api/migrations/versions/0007_invoices.py")
        self.assertEqual(self.facts().schema_changed, ["apps/api/migrations/versions/0007_invoices.py"])


class BreakKit(Repo):
    def test_nothing_changed_nothing_to_break(self):
        s = self.states("break")
        self.assertEqual(s, {"harden": "skip", "bug-sweep": "skip", "triage-report": "skip"})

    def test_a_change_is_hardened_swept_and_reported(self):
        self.commit("apps/api/app/invoices.py")
        self.assertEqual(self.states("break"), {"harden": "run", "bug-sweep": "run", "triage-report": "run"})

    def test_tiers_add_load_and_the_launch_audit(self):
        self.commit("apps/api/app/invoices.py")
        self.assertNotIn("load-sim", self.states("break", tier="quick"))
        full = self.states("break", tier="full")
        self.assertEqual(full["load-sim"], "blocked")  # no load-scenario.toml
        self.assertNotIn("ship-check", full)
        self.assertEqual(self.states("break", tier="launch")["ship-check"], "run")

    def test_full_sweeps_an_area_when_there_are_no_new_commits(self):
        self.assertEqual(self.states("break", tier="full")["bug-sweep"], "run")


class LoadTarget(Repo):
    def scenario(self, url: str) -> None:
        self.write("load-scenario.toml", f'[target]\nbase_url = "{url}"\n')

    def test_a_local_stack_that_answers_can_be_loaded(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            self.scenario(f"http://127.0.0.1:{server.getsockname()[1]}")
            state, reason = kit.cond_load_ready(self.facts())
        self.assertEqual(state, "run", reason)

    def test_a_stack_that_is_down_is_blocked_with_the_fix(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.scenario(f"http://127.0.0.1:{port}")
        state, reason = kit.cond_load_ready(self.facts())
        self.assertEqual(state, "blocked")
        self.assertIn("start the local stack", reason)

    def test_a_remote_target_is_never_loaded(self):
        self.scenario("https://app.example.com")
        state, reason = kit.cond_load_ready(self.facts())
        self.assertEqual(state, "blocked")
        self.assertIn("never production", reason)


class BuildKit(Repo):
    def test_only_the_stacks_the_work_touches(self):
        self.commit("apps/api/app/invoices.py")
        s = self.states("build")
        self.assertEqual(s["stack-backend"], "run")
        self.assertEqual(s["stack-web"], "skip")
        self.assertEqual(s["stack-native"], "skip")  # no apps/mobile
        self.assertEqual(s["wire-api"], "skip")

    def test_an_api_and_a_screen_bring_wire_api_and_a_model_brings_seedbed(self):
        s = self.states("build", request="add an invoices endpoint and its screen with a new table")
        self.assertEqual((s["stack-backend"], s["stack-web"], s["wire-api"], s["seedbed"]), ("run", "run", "run", "run"))

    def test_parallel_work_brings_fanout(self):
        self.assertEqual(self.states("build", request="build these three in parallel")["fanout"], "run")
        self.assertEqual(self.states("build")["fanout"], "skip")


class FlowKit(Repo):
    def test_end_and_start(self):
        self.assertEqual(list(self.states("flow", mode="end")), ["docsync", "feature-map", "open-loops", "handoff"])
        self.assertEqual(list(self.states("flow", mode="start")), ["handoff", "open-loops"])
        self.assertEqual(self.states("flow")["handoff"], "run")  # end: init, then log
        self.assertEqual(self.states("flow", mode="start")["handoff"], "skip")  # nothing to read yet
        self.write("HANDOFF.md", "# Handoff\n")
        self.assertEqual(self.states("flow", mode="start")["handoff"], "run")


class FeatureKit(Repo):
    def test_build_then_break_then_flow(self):
        steps = kit.plan("feature", self.facts("add invoices"))
        kits = list(dict.fromkeys(s.kit for s in steps))
        self.assertEqual(kits, ["build", "break", "flow"])
        self.assertNotIn("load-sim", [s.skill for s in steps])  # break runs at its quick tier


class Autopilot(Repo):
    def test_a_fresh_session_opens_the_flow(self):
        self.assertEqual(self.now(), ["/flow start"])

    def test_unproven_code_is_broken_then_recorded(self):
        self.commit("apps/api/app/invoices.py")
        self.assertEqual(self.now(), ["/break", "/flow"])

    def test_a_schema_change_brings_seed_data(self):
        self.commit("apps/api/migrations/versions/0007_invoices.py")
        self.assertEqual(self.now(), ["/break", "/seed", "/flow"])

    def test_only_docs_changed(self):
        self.write("docs/notes.md")
        self.assertEqual(self.now(), ["/flow"])

    def test_asking_for_the_autopilot_never_answers_with_itself(self):
        for request in ("run shipkit", "/shipkit", "@auto what should I run?"):
            self.assertEqual(self.now(request), ["/flow start"], request)

    def test_the_request_decides_first(self):
        self.assertEqual(self.now("/break full")[0], "/break")
        self.assertEqual(self.now("are we ready to launch?"), ["/break launch"])
        self.assertEqual(self.now("add an invoices endpoint"), ["/feature"])
        self.assertEqual(self.now("let's wrap up"), ["/flow"])

    def test_full_is_offered_or_held_back_with_the_reason(self):
        a = kit.advise(self.facts())
        self.assertIn("/break full", [x["run"] for x in a.not_now])


class Wiring(unittest.TestCase):
    def test_members_for_the_installer(self):
        self.assertEqual(kit.members("kit-flow"), ["handoff", "open-loops", "docsync", "feature-map"])
        self.assertIn("docsync", kit.members("kit-break"))  # harden hands its attack log to docsync
        feature = kit.members("kit-feature")
        for name in ("kit-build", "kit-break", "kit-flow", "stack-backend", "harden", "docsync"):
            self.assertIn(name, feature)
        self.assertEqual(set(kit.members("autopilot")) | {"autopilot", "switchboard"}, set(route.load()))
        self.assertEqual(kit.members("docsync"), [])

    def test_every_step_names_a_skill_and_a_known_condition(self):
        installed = route.installed()
        for name, table in kit.kits().items():
            self.assertIn(table["skill"], installed, name)
            for step in table.get("steps", []):
                self.assertIn(step["skill"], installed, f"{name}: {step}")
                self.assertIn(step["when"], kit.CONDITIONS, f"{name}: {step}")

    def test_a_named_kit_comes_alone(self):
        self.assertEqual([p.skill.name for p in route.route("/break the checkout endpoint against double submit")], ["kit-break"])
        self.assertEqual([p.skill.name for p in route.route("@shipkit check this")], ["autopilot"])

    def test_a_step_whose_skill_is_not_installed_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = kit.gather(Path(tmp))
            f.installed = f.installed - {"harden"}
            step = kit.plan("break", f)[0]
            self.assertEqual((step.skill, step.state), ("harden", "skip"))
            self.assertIn("not installed", step.reason)


if __name__ == "__main__":
    unittest.main()
