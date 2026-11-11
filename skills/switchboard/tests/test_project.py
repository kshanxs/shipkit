"""project.py: the project profile detected from a repository, the shipkit.toml it writes, and merging.

    uv run pytest skills/switchboard
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project  # noqa: E402

SAAS = {
    "apps/api/pyproject.toml": '[project]\nname = "api"\ndependencies = ["fastapi", "sqlalchemy", "stripe"]\n',
    "apps/api/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    "apps/api/app/projects/models.py": "class Project:\n    tenant_id: int\n",
    "apps/api/app/members/models.py": "class Member:\n    tenant_id: int\n",
    "apps/api/app/deps.py": "def tenant(x_tenant_id: str): ...\n",
    "apps/api/app/billing/invoices.py": "def refund(invoice): ...\n",
    "apps/api/app/auth/router.py": "def sign_up(): ...\ndef reset_password(): ...\n",
    "apps/web/package.json": '{"name": "web", "private": true, "dependencies": {"vite": "7", "@clerk/clerk-react": "5"}}\n',
    "apps/web/vite.config.ts": "export default { server: { port: 5180 } }\n",
    "apps/web/src/pricing.ts": "export const COMPARISON = []\n",
}
SELF_HOSTED = {
    "backend/pyproject.toml": '[project]\nname = "sync"\ndependencies = ["fastapi", "uvicorn"]\n[project.scripts]\nsync = "cli:main"\n',
    "backend/cli.py": "import argparse\nPASSWORD = 'from env'\n",
    "backend/server.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    "web/package.json": '{"name": "web", "private": true, "devDependencies": {"vite": "7"}}\n',
    "web/vite.config.ts": "export default {}\n",
    "web/src/main.ts": "navigator.serviceWorker.register('/sw.js')\n",
    "Dockerfile": "FROM python:3.12\nCMD uvicorn server:app --port 8527\n",
    "docs/README.md": "# Docs\n",
}
SHELL = {
    "install.sh": "#!/usr/bin/env bash\nset -euo pipefail\n",
    "scripts/tune.sh": "#!/usr/bin/env bash\n",
    "README.md": "# Setup\n",
}
LIBRARY = {
    "pyproject.toml": '[project]\nname = "astro"\ndependencies = []\n',
    "src/astro/__init__.py": "def chart(): ...\n",
    # a tool that talks about tenants and invoices is still not multi-tenant
    "src/astro/notes.py": "TENANT = 'tenant_id'\nINVOICE = 'invoice'\n# workspace_id org_id tenant\n",
    "src/astro/more.py": "tenant_id = 1\n",
    "src/astro/again.py": "x_tenant_id = 2\n",
}


def make(files: dict[str, str]) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return tmp


class Detect(unittest.TestCase):
    def values(self, files: dict[str, str]) -> tuple[dict, project.Profile, project.Detected]:
        with make(files) as tmp:
            d = project.detect(Path(tmp))
            p = project.profile(Path(tmp), cfg={}, detected=d)
            return {k: v.value for k, v in p.values.items()}, p, d

    def test_a_multi_tenant_saas_with_payments_and_plans(self):
        v, p, d = self.values(SAAS)
        self.assertEqual(v["kind"], "saas")
        self.assertEqual(v["tenancy"], "multi-tenant")
        self.assertEqual(v["money"], "payments")
        self.assertEqual(v["plans"], "tiers")
        self.assertEqual(v["auth"], "accounts")
        self.assertEqual(d.stack, {"api_dir": "apps/api", "web_dirs": ["apps/web"], "native_dir": ""})
        self.assertEqual(d.packages, ["apps/*"])
        self.assertEqual(d.ports["WEB_PORT"], 5180)
        self.assertTrue(p.has("multi-tenant", "money", "plans", "server", "hosted"))

    def test_a_self_hosted_single_user_app_has_no_money_tenants_or_plans(self):
        v, p, d = self.values(SELF_HOSTED)
        self.assertEqual(v["kind"], "self-hosted")
        self.assertEqual(v["tenancy"], "single-user")
        self.assertEqual((v["money"], v["plans"]), ("none", "none"))
        self.assertFalse(v["offline"], "a service worker is not offline sync")
        self.assertEqual(set(v["surfaces"]), {"api", "web", "cli", "container"})
        self.assertEqual(d.stack["api_dir"], "backend")
        self.assertEqual(d.ports["API_PORT"], 8527)
        self.assertTrue(p.has("self-hosted", "server", "!money", "!multi-tenant", "!hosted"))

    def test_shell_scripts_are_infra(self):
        v, p, _ = self.values(SHELL)
        self.assertEqual(v["kind"], "infra")
        self.assertIn("shell", v["surfaces"])
        self.assertFalse(p.has("server"))

    def test_a_library_that_mentions_tenants_is_not_multi_tenant(self):
        v, p, _ = self.values(LIBRARY)
        self.assertEqual(v["kind"], "library")
        self.assertEqual(v["tenancy"], "none")
        self.assertEqual(v["money"], "none")
        self.assertFalse(p.has("server"))


class Configured(unittest.TestCase):
    def test_shipkit_toml_wins_over_detection_and_problems_are_named(self):
        with make(SAAS) as tmp:
            root = Path(tmp)
            (root / "shipkit.toml").write_text('[project]\nmoney = "none"\nkind = "spaceship"\n')
            p = project.profile(root)
            self.assertEqual(p.get("money"), "none")
            self.assertEqual(p.values["money"].source, "shipkit.toml")
            self.assertEqual(p.get("tenancy"), "multi-tenant")  # still detected
            self.assertIn("kind = 'spaceship'", " ".join(project.problems(project.config(root))))

    def test_has_takes_negations(self):
        with make(SHELL) as tmp:
            p = project.profile(Path(tmp), cfg={})
            self.assertTrue(p.has("!money", "shell"))
            self.assertEqual(p.missing("money", "!shell"), ["money", "!shell"])


class Write(unittest.TestCase):
    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "project.py"), *args, "--root", str(root)], capture_output=True, text=True)

    def test_a_new_file_is_complete_and_parses(self):
        with make(SELF_HOSTED) as tmp:
            root = Path(tmp)
            done = self.run_cli(root, "write")
            self.assertEqual(done.returncode, 0, done.stderr)
            cfg = tomllib.loads((root / "shipkit.toml").read_text())
            self.assertEqual(cfg["project"]["money"], "none")
            self.assertEqual(cfg["stack"], {"api_dir": "backend", "web_dirs": ["web"], "native_dir": ""})
            self.assertEqual(cfg["feature_map"]["tiers"], [])
            self.assertNotIn("plan_sources", cfg["docsync"])
            self.assertIn("check these guesses", done.stdout)
            self.assertEqual(self.run_cli(root, "show").returncode, 0)

    def test_an_existing_file_only_gains_what_it_lacks(self):
        with make(SAAS) as tmp:
            root = Path(tmp)
            mine = '# my notes\n[project]\nmoney = "none"\n\n[handoff]\nowner = "Sam"\n'
            (root / "shipkit.toml").write_text(mine)
            done = self.run_cli(root, "write")
            self.assertEqual(done.returncode, 0, done.stderr)
            text = (root / "shipkit.toml").read_text()
            cfg = tomllib.loads(text)
            self.assertTrue(text.startswith("# my notes\n"))
            self.assertEqual(cfg["project"]["money"], "none")  # kept
            self.assertEqual(cfg["project"]["tenancy"], "multi-tenant")  # added
            self.assertEqual(cfg["handoff"]["owner"], "Sam")
            self.assertEqual(cfg["handoff"]["file"], "HANDOFF.md")
            self.assertIn("stack", cfg)
            again = self.run_cli(root, "write")
            self.assertIn("nothing written", again.stdout)

    def test_the_saas_preset_and_has(self):
        with make(SHELL) as tmp:
            root = Path(tmp)
            cfg = tomllib.loads(self.run_cli(root, "toml", "--preset", "saas").stdout)
            self.assertEqual(cfg["project"]["tenancy"], "multi-tenant")
            self.assertEqual(self.run_cli(root, "has", "shell").returncode, 0)
            no = self.run_cli(root, "has", "money")
            self.assertEqual(no.returncode, 1)
            self.assertIn("lacks money", no.stdout)


if __name__ == "__main__":
    unittest.main()
