"""handoff.py: init, log (newest first), show, check, and the words a row may use."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "handoff.py"


class Handoff(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self) -> None:
        self.folder.cleanup()

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env={**os.environ, "SHIPKIT_ROOT": str(self.root)})

    def log(self, entry: str, status: str = "Done", *extra: str) -> subprocess.CompletedProcess:
        return self.run_script("log", "--entry", entry, "--agent", "Claude", "--changed", f"{entry} changed", "--next", "Do the next thing", "--status", status, *extra)

    def test_init_writes_a_file_that_checks_clean(self) -> None:
        self.assertEqual(self.run_script("init").returncode, 0)
        self.assertTrue((self.root / "HANDOFF.md").exists())
        self.assertIn("## Waiting on the owner", (self.root / "HANDOFF.md").read_text())
        result = self.run_script("check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("nothing written", self.run_script("init").stdout)

    def test_log_puts_the_newest_row_first_and_show_reads_it(self) -> None:
        self.run_script("init")
        self.assertEqual(self.log("First piece").returncode, 0)
        self.assertEqual(self.log("Second piece", "In progress", "--links", "PR #3 (abc1234)").returncode, 0)
        text = (self.root / "HANDOFF.md").read_text()
        self.assertLess(text.index("Second piece"), text.index("First piece"))
        shown = self.run_script("show", "--log", "1").stdout
        self.assertIn("Second piece", shown)
        self.assertNotIn("First piece", shown)
        self.assertIn("## Now", shown)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_a_status_or_area_outside_the_words_is_refused(self) -> None:
        self.run_script("init")
        self.assertNotEqual(self.log("Bad", "Finished").returncode, 0)
        self.assertNotEqual(self.log("Bad", "Done", "--area", "Marketing").returncode, 0)

    def test_configured_file_owner_and_words(self) -> None:
        (self.root / "shipkit.toml").write_text('[handoff]\nfile = "docs/HANDOFF.md"\nowner = "Sam"\nstatuses = ["Done", "Paused"]\ntimezone = "UTC"\n')
        (self.root / "docs").mkdir()
        self.run_script("init")
        text = (self.root / "docs/HANDOFF.md").read_text()
        self.assertIn("## Waiting on Sam", text)
        self.assertEqual(self.log("Paused work", "Paused").returncode, 0)
        self.assertIn("+00:00", (self.root / "docs/HANDOFF.md").read_text())

    def test_check_names_a_broken_row_and_a_missing_section(self) -> None:
        self.run_script("init")
        path = self.root / "HANDOFF.md"
        text = path.read_text().replace("## Blocked", "## Stuck")
        text += "| yesterday | X | Claude | Dev | y | - | - | Finished |\n"
        path.write_text(text)
        out = self.run_script("check").stdout
        self.assertIn("no `## Blocked` section", out)
        self.assertIn("the date is YYYY-MM-DD", out)
        self.assertIn("status 'Finished'", out)
        self.assertIn("no next step", out)

    def test_no_file_says_so_and_how_to_start(self) -> None:
        result = self.run_script("show")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("handoff.py init", result.stderr)


if __name__ == "__main__":
    unittest.main()
