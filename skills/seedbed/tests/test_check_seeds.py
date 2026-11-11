"""Tests for check_seeds.py and the example seed: a small tree that passes every check; each test breaks one thing."""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "check_seeds.py"
EXAMPLE_SEED = SKILL / "references" / "example_seed.py"
EXAMPLE_CONFIG = SKILL / "references" / "seedbed.example.toml"

DEVICE_DB = "apps/web/src/db/index.ts"
DATA_MAP = "docs/data_map.md"

FILES = {
    DEVICE_DB: """
class AppCache extends Dexie {
  constructor() {
    super('app_cache')
    this.version(1).stores({
      cache: '&key, scope',
      outbox: '&id, scope',
      meta: 'key',
    })
    this.version(2).stores({ drafts: '&id' })
  }
}
""",
    DATA_MAP: "# Data map\n\n`cache`, `outbox` and `drafts` are on the web device. `tasks` and `sync_state` are on the phone.\n",
    "docs/roles/README.md": "# Roles\n",
    "docs/roles/owner.md": "# Owner\n\n## Data and API Access\n\n| Entity |\n",
}


def load():
    spec = importlib.util.spec_from_file_location("check_seeds", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckSeeds(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        for path, text in FILES.items():
            self.write(path, text)
        shutil.copy(EXAMPLE_CONFIG, self.root / "seedbed.toml")
        (self.root / "scripts").mkdir()
        shutil.copy(EXAMPLE_SEED, self.root / "scripts" / "seed.py")
        os.environ["SHIPKIT_ROOT"] = str(self.root)
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(os.environ.pop, "SHIPKIT_ROOT", None)

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def edit(self, path, old, new):
        text = (self.root / path).read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.write(path, text.replace(old, new))

    def report(self):
        module = load()
        report = module.Report()
        module.run_checks(report)
        return report

    def errors(self):
        return self.report().errors

    def assertFails(self, check, fragment):
        errors = self.errors()
        self.assertTrue(any(name == check and fragment in message for name, message in errors), errors)

    def test_the_example_tree_passes(self):
        self.assertEqual(self.errors(), [])

    # ---- catalogue ----

    def test_a_module_nothing_seeds(self):
        self.edit("seedbed.toml", 'modules = ["projects", "tasks", "comments", "billing"]', 'modules = ["projects", "tasks", "comments", "billing", "reports"]')
        self.assertFails("catalogue", "module `reports` is in the catalogue")

    def test_the_seed_filling_a_module_the_catalogue_does_not_have(self):
        self.edit("scripts/seed.py", 'if wants("billing"):', 'if wants("audit"):\n        pass\n    if wants("billing"):')
        self.assertFails("catalogue", "the seed fills `audit`")

    def test_a_scenario_with_no_implementation(self):
        self.edit("scripts/seed.py", "def scenario_fresh_signup(", "def fresh_signup(")
        self.assertFails("catalogue", "scenario `fresh_signup` is in the catalogue and has no implementation")

    def test_an_implementation_for_a_scenario_the_catalogue_does_not_have(self):
        self.write("scripts/seed.py", (self.root / "scripts/seed.py").read_text() + "\ndef scenario_outage(db):\n    pass\n")
        self.assertFails("catalogue", "the seed stages `outage`")

    def test_a_scenario_that_needs_a_module_that_does_not_exist(self):
        self.edit("seedbed.toml", 'trial_ending = "billing"', 'trial_ending = "payments"')
        self.assertFails("catalogue", "needs module `payments`")

    def test_a_missing_seed_file(self):
        (self.root / "scripts/seed.py").unlink()
        self.assertFails("catalogue", "scripts/seed.py is missing")

    # ---- personas ----

    def test_a_required_persona_missing(self):
        self.edit("seedbed.toml", 'required = ["owner", "admin", "member", "viewer"]', 'required = ["owner", "admin", "member", "viewer", "billing"]')
        self.assertFails("personas", "offers `billing`")

    def test_a_persona_declared_twice(self):
        self.edit("seedbed.toml", 'slug = "viewer"', 'slug = "member"')
        self.assertFails("personas", "`member` is declared twice")

    def test_a_persona_with_a_real_looking_login(self):
        self.edit("seedbed.toml", 'login = "viewer@demo.test"', 'login = "vic@gmail.com"')
        self.assertFails("personas", "does not match")

    def test_personas_read_from_a_file(self):
        self.write("scripts/personas.py", 'PERSONAS = (\n    Persona("owner", "owner@demo.test"),\n    Persona("owner", "x@demo.test"),\n)\n')
        self.edit("seedbed.toml", "[personas]\n", '[personas]\nfile = "scripts/personas.py"\n')
        self.assertFails("personas", "`owner` is declared twice")

    # ---- retired paths ----

    def test_a_retired_folder_coming_back(self):
        self.edit("seedbed.toml", "[retired]\npaths = []", '[retired]\npaths = [{ path = "apps/web/src/demo/db", why = "the demo runs on the server now" }]')
        self.write("apps/web/src/demo/db/index.ts", "export {}\n")
        self.assertFails("retired", "the demo runs on the server now")

    # ---- the data map ----

    def test_a_device_table_missing_from_the_map(self):
        self.edit(DEVICE_DB, "      outbox: '&id, scope',\n", "      outbox: '&id, scope',\n      uploads: '&id',\n")
        self.assertFails("map", "Web device table `uploads`")

    def test_a_table_listed_by_hand_counts(self):
        self.edit("seedbed.toml", 'tables = ["tasks", "sync_state"]', 'tables = ["tasks", "sync_state", "attachments"]')
        self.assertFails("map", "Mobile table `attachments`")

    def test_a_bookkeeping_table_needs_no_entry(self):
        self.assertNotIn("`meta`", (self.root / DATA_MAP).read_text())
        self.assertEqual(self.errors(), [])

    def test_no_map(self):
        (self.root / DATA_MAP).unlink()
        self.assertFails("map", "is missing")

    # ---- role pages ----

    def test_a_role_page_without_its_section(self):
        self.write("docs/roles/viewer.md", "# Viewer\n\nNothing yet.\n")
        self.assertFails("roles", "viewer.md has no")

    # ---- config ----

    def test_no_config_says_how_to_start(self):
        (self.root / "seedbed.toml").unlink()
        self.assertFails("config", "--init")

    def test_init_writes_the_example_and_never_overwrites(self):
        (self.root / "seedbed.toml").unlink()
        env = {**os.environ, "SHIPKIT_ROOT": str(self.root)}
        made = subprocess.run([sys.executable, str(SCRIPT), "--init"], env=env, capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual((self.root / "seedbed.toml").read_text(), EXAMPLE_CONFIG.read_text())
        again = subprocess.run([sys.executable, str(SCRIPT), "--init"], env=env, capture_output=True, text=True)
        self.assertIn("exists; nothing written", again.stdout)

    def test_run_executes_the_seed_tests(self):
        env = {**os.environ, "SHIPKIT_ROOT": str(self.root)}
        self.edit("seedbed.toml", 'command = "uv run python scripts/seed.py --check"', f'command = "{sys.executable} scripts/seed.py --check"')
        result = subprocess.run([sys.executable, str(SCRIPT), "--run"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 errors", result.stdout)


class ExampleSeed(unittest.TestCase):
    def run_seed(self, *args):
        return subprocess.run([sys.executable, str(EXAMPLE_SEED), *args], capture_output=True, text=True)

    def test_a_second_run_adds_nothing(self):
        result = self.run_seed("--check", "--scenarios", "busy_monday,trial_ending,fresh_signup")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("second run added 0", result.stdout)

    def test_modules_and_unknown_names(self):
        self.assertEqual(self.run_seed("--modules", "projects").returncode, 0)
        self.assertEqual(self.run_seed("--modules", "nonsense").returncode, 2)


if __name__ == "__main__":
    unittest.main()
