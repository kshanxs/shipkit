#!/usr/bin/env python3
"""The test matrix: which combinations are covered, which features have none, and the pairwise
cases still to write. Standard library only (Python 3.11+).

    python3 matrix.py coverage [--feature 2.1] [--missing]
    python3 matrix.py stale
    python3 matrix.py pairs network timing device [--feature 2.1]
    python3 matrix.py pairs --all-axes --limit 40

Paths come from shipkit.toml at the project root:

    [harden]
    matrix = "docs/testing/test_matrix.md"   # the cells (start from references/test_matrix.md)
    axes = "docs/testing/axes.toml"           # the axes (start from references/axes.toml)
    counted = ["Built", "Partly built", "Backend only"]   # tracker statuses that need a cell

    [docsync]
    tracker = "docs/feature_status.md"        # features: rows `| 2.1 Name | Status | note |`
    attack_log = "docs/testing/attack_log.md"

Without a project axes file, `pairs` uses the skill's references/axes.toml. The docsync checker
calls lint() and warns while a cell names something that does not exist or a built feature has
no cell.
"""

from __future__ import annotations

import argparse
import itertools
import os
import random
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    """SHIPKIT_ROOT, else the nearest folder up from here holding shipkit.toml, else the git root, else here."""
    if os.environ.get("SHIPKIT_ROOT"):
        return Path(os.environ["SHIPKIT_ROOT"]).resolve()
    here = Path.cwd().resolve()
    for marker in ("shipkit.toml", ".git"):
        for folder in (here, *here.parents):
            if (folder / marker).exists():
                return folder
    return here


ROOT = project_root()


def _config() -> dict:
    path = ROOT / "shipkit.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _docs() -> str:
    return _config().get("docsync", {}).get("docs_dir", "docs")


def matrix_path() -> Path:
    return ROOT / _config().get("harden", {}).get("matrix", f"{_docs()}/testing/test_matrix.md")


def axes_path() -> Path:
    project = ROOT / _config().get("harden", {}).get("axes", f"{_docs()}/testing/axes.toml")
    return project if project.exists() else SKILL / "references" / "axes.toml"


def tracker_path() -> Path:
    return ROOT / _config().get("docsync", {}).get("tracker", f"{_docs()}/feature_status.md")


def attack_log_path() -> Path:
    return ROOT / _config().get("docsync", {}).get("attack_log", f"{_docs()}/testing/attack_log.md")


def counted() -> set[str]:
    return set(_config().get("harden", {}).get("counted", ["Built", "Partly", "Partly built", "Backend only"]))


CELL_ROW = re.compile(r"^\| (M-\d{3}) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|\s*$")
FEATURE_ROW = re.compile(r"^\| (\d+\.\d+) ([^|]+?) \| ([^|]+?) \|(.*)$")
ATTACK = re.compile(r"\bATK-\d{3,}\b")
TEST_REF = re.compile(r"`([^`]+)`")
DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
REVIEWED = re.compile(r"^Reviewed: (20\d\d-\d\d-\d\d)", re.M)


@dataclass
class Cell:
    id: str
    features: list[str]
    combination: str
    expected: str
    covered_by: str

    def state(self, attacks: set[str]) -> tuple[str, list[str]]:
        """('covered' | 'pending' | 'not yet' | 'broken', problems)."""
        text = self.covered_by.strip()
        if text.lower().startswith("not yet"):
            return "not yet", []
        if "(PR #" in text:
            return "pending", []
        problems = [f"{self.id}: {a} is not in the attack log" for a in ATTACK.findall(text) if a not in attacks]
        for ref in TEST_REF.findall(text):
            problems += [f"{self.id}: {p}" for p in _check_test(ref)]
        if not ATTACK.findall(text) and not TEST_REF.findall(text):
            problems.append(f"{self.id}: 'Covered by' names no attack, no test and is not 'Not yet'")
        return ("broken" if problems else "covered"), problems


def _check_test(ref: str) -> list[str]:
    path, _, name = ref.partition("::")
    file = ROOT / path
    if not file.exists():
        return [f"{path} does not exist"]
    if name:
        last = name.split("::")[-1].split("[")[0]
        if not re.search(rf"\b(def|class) {re.escape(last)}\b", file.read_text(encoding="utf-8")):
            return [f"{last} is not in {path}"]
    return []


def cells(text: str | None = None) -> list[Cell]:
    text = matrix_path().read_text(encoding="utf-8") if text is None else text
    out = []
    for line in text.splitlines():
        m = CELL_ROW.match(line)
        if m:
            feats = [f.strip() for f in m.group(2).split(",") if f.strip()]
            out.append(Cell(m.group(1), feats, m.group(3).strip(), m.group(4).strip(), m.group(5).strip()))
    return out


def features() -> dict[str, tuple[str, str, str]]:
    """{number: (name, status, note)} from the tracker's feature rows."""
    out = {}
    if not tracker_path().exists():
        return out
    for line in tracker_path().read_text(encoding="utf-8").splitlines():
        m = FEATURE_ROW.match(line)
        if m:
            out[m.group(1)] = (m.group(2).strip(), m.group(3).strip(), m.group(4))
    return out


def attack_ids() -> set[str]:
    if not attack_log_path().exists():
        return set()
    return {m.group(1) for m in re.finditer(r"^\| (ATK-\d{3,}) \|", attack_log_path().read_text(encoding="utf-8"), re.M)}


def reviewed() -> str:
    m = REVIEWED.search(matrix_path().read_text(encoding="utf-8"))
    return m.group(1) if m else "0000-00-00"


def gaps() -> tuple[list[str], list[str]]:
    """(features counted with no cell, features whose tracker note is dated after the review)."""
    named = {f for c in cells() for f in c.features}
    since = reviewed()
    missing, changed = [], []
    needs_cell = counted()
    for number, (name, status, note) in features().items():
        if status not in needs_cell:
            continue
        if number not in named:
            missing.append(f"{number} {name} ({status})")
        dates = DATE.findall(note)
        if dates and max(dates) > since:
            changed.append(f"{number} {name}: noted {max(dates)}, matrix reviewed {since}")
    return missing, changed


def lint() -> list[str]:
    """Warnings for check_docs.py: one line per broken cell, one summary line for the gaps."""
    attacks = attack_ids()
    problems = [p for c in cells() for p in c.state(attacks)[1]]
    missing, changed = gaps()
    if missing:
        problems.append(
            f"{len(missing)} features Built or Partly have no cell in the test matrix "
            "(the harden skill's matrix.py stale)"
        )
    if changed:
        problems.append(f"{len(changed)} features changed since the test matrix was reviewed (matrix.py stale)")
    return problems


# Pairwise ------------------------------------------------------------------------------------


def load_axes() -> dict[str, list[str]]:
    return tomllib.loads(axes_path().read_text(encoding="utf-8"))["axes"]


def pairwise(axes: dict[str, list[str]], seed: int = 7, tries: int = 40) -> list[dict[str, str]]:
    """A small set of cases in which every pair of values of any two axes appears at least once
    (greedy, deterministic for a seed)."""
    names = list(axes)
    if len(names) == 1:
        return [{names[0]: v} for v in axes[names[0]]]
    todo = {(a, va, b, vb) for a, b in itertools.combinations(names, 2) for va in axes[a] for vb in axes[b]}
    rng = random.Random(seed)
    cases: list[dict[str, str]] = []

    def gain(case: dict[str, str]) -> int:
        return sum(
            (a, case[a], b, case[b]) in todo for a, b in itertools.combinations(names, 2) if a in case and b in case
        )

    while todo:
        # Start each case from a pair still to cover, so every round makes progress.
        a, va, b, vb = min(todo)
        best, best_gain = None, -1
        for _ in range(tries):
            case = {a: va, b: vb}
            rest = [n for n in names if n not in case]
            rng.shuffle(rest)
            for n in rest:
                case[n] = max(axes[n], key=lambda v: (gain({**case, n: v}), rng.random()))
            g = gain(case)
            if g > best_gain:
                best, best_gain = case, g
        assert best is not None
        for x, y in itertools.combinations(names, 2):
            todo.discard((x, best[x], y, best[y]))
        cases.append({n: best[n] for n in names})
    return cases


# Command line --------------------------------------------------------------------------------


def need_matrix() -> bool:
    if matrix_path().exists():
        return True
    print(f"No test matrix at {matrix_path()}. Start one: cp {SKILL / 'references' / 'test_matrix.md'} {matrix_path()}")
    return False


def cmd_coverage(args: argparse.Namespace) -> int:
    if not need_matrix():
        return 2
    attacks = attack_ids()
    rows = [c for c in cells() if not args.feature or args.feature in c.features]
    counts: dict[str, int] = {}
    broken = 0
    for c in rows:
        state, problems = c.state(attacks)
        counts[state] = counts.get(state, 0) + 1
        broken += bool(problems)
        if args.missing and state == "covered":
            continue
        print(f"{c.id:6} {state:8} [{', '.join(c.features)}] {c.combination}")
        for p in problems:
            print(f"         {p}")
    total = len(rows) or 1
    print(
        f"\n{len(rows)} cells: {counts.get('covered', 0)} covered ({100 * counts.get('covered', 0) // total}%), "
        f"{counts.get('pending', 0)} on an open PR, {counts.get('not yet', 0)} not yet, {broken} broken"
    )
    return 1 if broken else 0


def cmd_stale(_: argparse.Namespace) -> int:
    if not need_matrix():
        return 2
    missing, changed = gaps()
    print(f"Test matrix reviewed {reviewed()}.\n")
    print(f"Features Built, Partly or Backend only with no cell ({len(missing)}):")
    for line in missing:
        print(f"  {line}")
    print(f"\nFeatures whose tracker note is dated after the review ({len(changed)}):")
    for line in changed:
        print(f"  {line}")
    print(f"\nAdd a cell for each (or 'Not yet'), then set 'Reviewed:' in {matrix_path().name} to today.")
    return 0


def cmd_pairs(args: argparse.Namespace) -> int:
    axes = load_axes()
    chosen = list(axes) if args.all_axes else args.axes
    unknown = [a for a in chosen if a not in axes]
    if unknown or not chosen:
        print(f"Axes: {', '.join(axes)}. Unknown: {', '.join(unknown) or 'none given'}")
        return 2
    picked = {a: axes[a] for a in chosen}
    cases = pairwise(picked, seed=args.seed)
    full = 1
    for a in chosen:
        full *= len(axes[a])
    label = f" for feature {args.feature}" if args.feature else ""
    print(f"{len(cases)} cases cover every pair of {', '.join(chosen)}{label} (all combinations: {full}).\n")
    shown = cases[: args.limit] if args.limit else cases
    print("| # | " + " | ".join(chosen) + " |")
    print("|---|" + "---|" * len(chosen))
    for i, case in enumerate(shown, 1):
        print(f"| {i} | " + " | ".join(case[a] for a in chosen) + " |")
    if len(shown) < len(cases):
        print(f"\n({len(cases) - len(shown)} more; drop --limit to see them)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("coverage", help="every cell, covered or not")
    p.add_argument("--feature", help="only cells naming this feature number")
    p.add_argument("--missing", action="store_true", help="only cells not covered")
    p.set_defaults(func=cmd_coverage)
    p = sub.add_parser("stale", help="features with no cell, and features changed since the review")
    p.set_defaults(func=cmd_stale)
    p = sub.add_parser("pairs", help="pairwise cases for some axes")
    p.add_argument("axes", nargs="*")
    p.add_argument("--all-axes", action="store_true")
    p.add_argument("--feature", help="label the output with a feature number")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=cmd_pairs)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
