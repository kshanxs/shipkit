"""Tests for the test matrix script (matrix.py). Standard library only.

    uv run pytest skills/harden
"""

from __future__ import annotations

import itertools
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import matrix  # noqa: E402

MATRIX = """# Test matrix

Reviewed: 2026-11-01

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-001 | 1.1 | Two at once | One | ATK-001 |
| M-002 | 1.1, 2.1 | Replayed | Kept answer | `tests/test_alpha.py::TestA::test_once` |
| M-003 | 2.1 | Late | Refused | Not yet |
| M-004 | 2.1 | Pending | Held | `tests/test_beta.py` (PR #9) |
| M-005 | 2.1 | Wrong | Held | ATK-999 |
| M-006 | 2.1 | Gone | Held | `tests/test_alpha.py::test_missing` |
"""

TRACKER = """# Tracker

| 1.1 Sign-in | Built | Built 2026-10-01 |
| 2.1 Projects | Built | Built 2026-11-02 |
| 3.1 Billing | Partly | |
| 9.9 Later | Planned | |
"""

LOG = """| Attack | Date | Area | What was tried | Test | Result |
|---|---|---|---|---|---|
| ATK-001 | 2026-10-28 | Sign-in | Two at once | None | Held |
"""


class Repo(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        (root / "tests").mkdir(parents=True)
        (root / "tests/test_alpha.py").write_text("class TestA:\n    def test_once(self):\n        pass\n")
        (root / "docs/testing").mkdir(parents=True)
        (root / "docs/feature_status.md").write_text(TRACKER)
        (root / "docs/testing/attack_log.md").write_text(LOG)
        (root / "test_matrix.md").write_text(MATRIX)
        (root / "shipkit.toml").write_text('[harden]\nmatrix = "test_matrix.md"\n')
        self.saved = matrix.ROOT
        matrix.ROOT = root

    def tearDown(self) -> None:
        matrix.ROOT = self.saved
        self.dir.cleanup()


class TestCells(Repo):
    def states(self) -> dict[str, str]:
        attacks = matrix.attack_ids()
        return {c.id: c.state(attacks)[0] for c in matrix.cells()}

    def test_each_cell_is_read_with_its_features(self) -> None:
        cells = matrix.cells()
        self.assertEqual([c.id for c in cells], ["M-001", "M-002", "M-003", "M-004", "M-005", "M-006"])
        self.assertEqual(cells[1].features, ["1.1", "2.1"])

    def test_a_cell_is_covered_only_by_what_exists(self) -> None:
        self.assertEqual(
            self.states(),
            {
                "M-001": "covered",
                "M-002": "covered",
                "M-003": "not yet",
                "M-004": "pending",
                "M-005": "broken",
                "M-006": "broken",
            },
        )

    def test_lint_names_each_broken_cell_and_sums_up_the_gaps(self) -> None:
        problems = matrix.lint()
        self.assertTrue(any("ATK-999" in p for p in problems))
        self.assertTrue(any("test_missing" in p for p in problems))
        self.assertTrue(any("1 features Built or Partly have no cell" in p for p in problems))
        self.assertTrue(any("1 features changed since" in p for p in problems))


class TestGaps(Repo):
    def test_a_planned_feature_is_not_a_gap_and_a_partly_one_is(self) -> None:
        missing, changed = matrix.gaps()
        self.assertEqual(missing, ["3.1 Billing (Partly)"])
        self.assertEqual(len(changed), 1)
        self.assertIn("2.1 Projects", changed[0])


class TestPairwise(unittest.TestCase):
    AXES: ClassVar[dict[str, list[str]]] = {
        "who": ["owner", "member", "viewer", "admin"],
        "network": ["online", "offline", "flaky"],
        "timing": ["once", "twice", "race", "late", "ahead"],
        "device": ["one tab", "two tabs"],
    }

    def test_every_pair_of_values_appears_in_some_case(self) -> None:
        cases = matrix.pairwise(self.AXES)
        for a, b in itertools.combinations(self.AXES, 2):
            seen = {(c[a], c[b]) for c in cases}
            self.assertEqual(seen, set(itertools.product(self.AXES[a], self.AXES[b])), f"{a} x {b}")

    def test_far_fewer_cases_than_every_combination(self) -> None:
        cases = matrix.pairwise(self.AXES)
        self.assertLess(len(cases), 4 * 3 * 5 * 2 // 2)
        self.assertGreaterEqual(len(cases), 4 * 5)  # at least the largest pair of axes

    def test_the_same_seed_gives_the_same_cases(self) -> None:
        self.assertEqual(matrix.pairwise(self.AXES, seed=3), matrix.pairwise(self.AXES, seed=3))

    def test_the_shipped_axes_load(self) -> None:
        axes = matrix.load_axes()
        self.assertIn("network", axes)
        self.assertIn("offline", axes["network"])

    def test_the_shipped_matrix_template_parses(self) -> None:
        text = (matrix.SKILL / "references" / "test_matrix.md").read_text(encoding="utf-8")
        cells = matrix.cells(text)
        self.assertGreater(len(cells), 10)
        self.assertEqual(len({c.id for c in cells}), len(cells))


if __name__ == "__main__":
    unittest.main()
