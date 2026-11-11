#!/usr/bin/env python3
"""The attack log: what has been tried against the project on purpose, and what held. Standard library only.

    python3 attacks.py add "Billing" "Two clerks take one invoice's balance at once" \\
        --test tests/test_payment_race.py::test_two_clerks_take_the_balance_once --held
    python3 attacks.py add "Billing" "One invoice issued twice at once" \\
        --test tests/test_payment_race.py::test_one_invoice_issued_twice_bills_once --fixed BUG-059
    python3 attacks.py add "Web" "A javascript: link in a comment" --not-a-flaw
    python3 attacks.py run "Billing and payments" --attacks ATK-012 ATK-030 \\
        --tests "uv run pytest: 412 passed" --load "..." --not-tried "..."
    python3 attacks.py report RUN-002   # the harden report, from the log
    python3 attacks.py check            # exit 1 on a problem

The log is `attack_log` in the [docsync] table of shipkit.toml (default
docs/testing/attack_log.md). Each attack is a row (ATK-NNN) with what was tried, the test that
holds it and its result: Held (it did not get through), Fixed BUG-NNN, Open BUG-NNN, or Not a flaw
(it looked like one and is not; the row says why). Each run of the harden skill is a section
(RUN-NNN) naming its attacks, the tests run, the load tried and what was not tried. The script
writes both with the next number and today's date; `check_docs.py` runs `lint` as its `attacks`
check, with the bug register beside it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path


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


def _setting(root: Path, key: str, default: str) -> str:
    path = root / "shipkit.toml"
    table = tomllib.loads(path.read_text(encoding="utf-8")).get("docsync", {}) if path.is_file() else {}
    docs = table.get("docs_dir", "docs")
    return table.get(key, default.replace("docs/", f"{docs}/", 1))


def log_name(root: Path | None = None) -> str:
    return _setting(root or ROOT, "attack_log", "docs/testing/attack_log.md")


def register_name(root: Path | None = None) -> str:
    return _setting(root or ROOT, "bug_register", "docs/testing/bug_report.md")


LOG = log_name()

ATTACK_ID = re.compile(r"^ATK-(\d{3,})$")
RUN_HEADING = re.compile(r"^### (RUN-(\d{3,})) · (\d{4}-\d{2}-\d{2}) · (.+)$")
RESULT = re.compile(r"^(Held|Not a flaw|Fixed (BUG-\d+)|Open (BUG-\d+))$")
TEST_REF = re.compile(r"`([^`]+)`")
ATTACKS_HEADER = "| Attack | Date | Area | What was tried | Test | Result |"
RUN_FIELDS = ("Attacks", "Tests run", "Load", "Not tried")

TEMPLATE = """# Attack log

> What has been tried against this project on purpose, and what held: one row an attack, and a
> record of each run of the harden skill. Written by the docsync skill's `attacks.py`, never by
> hand, and checked by `check_docs.py` (`attacks`): every test named exists, and every bug named
> agrees with the bug register.

A result is one of: **Held** (it did not get through; the test keeps it so), **Fixed BUG-NNN** (it
got through, the bug is closed, the test failed before the fix), **Open BUG-NNN** (it got through
and is not fixed yet), **Not a flaw** (it looked like one and is not; the row says why).

## Attacks

{header}
|---|---|---|---|---|---|

## Runs

Newest first.
"""


class AttackLogError(Exception):
    """A request the script refuses, with the reason as its message."""


@dataclass
class Attack:
    id: str
    date: str
    area: str
    tried: str
    test: str
    result: str
    line: int


@dataclass
class Run:
    id: str
    date: str
    scope: str
    fields: dict[str, str]
    line: int


def path(root: Path | None = None, log: str | None = None) -> Path:
    return (root or ROOT) / (log or log_name(root))


def _cell(text: str) -> str:
    """Text fit for a table cell: one line, no bar."""
    return " ".join(text.replace("|", "/").split())


def parse(text: str) -> tuple[list[Attack], list[Run]]:
    attacks: list[Attack] = []
    runs: list[Run] = []
    section = None
    current: Run | None = None
    for number, line in enumerate(text.split("\n"), 1):
        if line.startswith("## "):
            section = line[3:].strip().lower()
            current = None
            continue
        if section == "attacks" and line.startswith("| ATK-"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            cells += [""] * (6 - len(cells))
            attacks.append(Attack(*cells[:6], line=number))
        elif section == "runs":
            heading = RUN_HEADING.match(line)
            if heading:
                current = Run(heading.group(1), heading.group(3), heading.group(4), {}, number)
                runs.append(current)
            elif current and line.startswith("- **"):
                field = re.match(r"^- \*\*([^*]+?):?\*\*:? ?(.*)$", line)
                if field:
                    current.fields[field.group(1).rstrip(":")] = field.group(2).strip()
    return attacks, runs


def read(root: Path | None = None, log_file: str | None = None) -> tuple[str, list[Attack], list[Run]]:
    log = path(root, log_file)
    text = log.read_text(encoding="utf-8") if log.exists() else TEMPLATE.format(header=ATTACKS_HEADER)
    attacks, runs = parse(text)
    return text, attacks, runs


def tests_of(cell: str) -> list[tuple[str, str | None]]:
    """The tests a cell names: (file, the test's name or None)."""
    found = []
    for ref in TEST_REF.findall(cell):
        file, _, name = ref.partition("::")
        found.append((file, name.split("::")[-1].split("[")[0] or None))
    return found


def _next(ids: list[str], prefix: str) -> str:
    numbers = [int(i.split("-")[1]) for i in ids if re.fullmatch(rf"{prefix}-\d+", i)]
    return f"{prefix}-{max(numbers, default=0) + 1:03d}"


def add(area: str, tried: str, tests: list[str], result: str, root: Path | None = None, today: str | None = None) -> str:
    """A new attack row under the last one; its ID."""
    if not RESULT.match(result):
        raise AttackLogError(f"A result is Held, Fixed BUG-NNN, Open BUG-NNN or Not a flaw, not {result!r}")
    if result in ("Held",) or result.startswith("Fixed"):
        if not tests:
            raise AttackLogError(f"{result}: name the test that holds it (--test file::name)")
    text, attacks, _ = read(root)
    attack_id = _next([a.id for a in attacks], "ATK")
    test_cell = "; ".join(f"`{t}`" for t in tests) if tests else "None"
    row = f"| {attack_id} | {today or date.today().isoformat()} | {_cell(area)} | {_cell(tried)} | {test_cell} | {result} |"
    lines = text.split("\n")
    if attacks:
        at = attacks[-1].line  # after the last row (1-based line number = index of the next line)
    else:
        try:
            at = lines.index(ATTACKS_HEADER) + 2
        except ValueError as error:
            raise AttackLogError(f"{log_name(root)} has no attacks table; its header is {ATTACKS_HEADER!r}") from error
    lines.insert(at, row)
    _write(root, "\n".join(lines))
    return attack_id


def run(scope: str, attack_range: list[str], tests: str, load: str, not_tried: str, root: Path | None = None, today: str | None = None) -> str:
    """A new run section at the top of Runs; its ID."""
    text, attacks, runs = read(root)
    known = {a.id for a in attacks}
    for attack_id in attack_range:
        if attack_id not in known:
            raise AttackLogError(f"{attack_id} is not in the log; add the attack first")
    attacks_line = " to ".join(attack_range) if len(attack_range) == 2 else ", ".join(attack_range)
    run_id = _next([r.id for r in runs], "RUN")
    block = [
        f"### {run_id} · {today or date.today().isoformat()} · {' '.join(scope.split())}",
        "",
        f"- **Attacks:** {attacks_line}",
        f"- **Tests run:** {' '.join(tests.split())}",
        f"- **Load:** {' '.join(load.split())}",
        f"- **Not tried:** {' '.join(not_tried.split())}",
        "",
    ]
    lines = text.split("\n")
    try:
        start = lines.index("## Runs")
    except ValueError as error:
        raise AttackLogError(f"{log_name(root)} has no '## Runs' section") from error
    at = runs[0].line - 1 if runs else next(
        (i + 1 for i in range(start + 1, len(lines)) if lines[i].strip() == "Newest first."), start + 1
    )
    if not runs:
        block.insert(0, "")
    lines[at:at] = block
    _write(root, "\n".join(lines).rstrip("\n") + "\n")
    return run_id


def _write(root: Path | None, text: str) -> None:
    log = path(root)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(text, encoding="utf-8")


def expand(field: str, known: list[str]) -> list[str]:
    """A run's attacks: "ATK-012 to ATK-030" or "ATK-001, ATK-004"."""
    found = re.findall(r"ATK-\d+", field)
    if " to " in field and len(found) == 2:
        low, high = (int(i.split("-")[1]) for i in found)
        return [i for i in known if low <= int(i.split("-")[1]) <= high]
    return found


def lint(root: Path | None = None, log_file: str | None = None) -> list[str]:
    """What is wrong with the log's form and its references to tests. The bug register is checked by check_docs."""
    root = root or ROOT
    log_file = log_file or log_name(root)
    log = path(root, log_file)
    if not log.exists():
        return []
    LOG = log_file  # noqa: N806  (named as the module's, for the messages below)
    problems = []
    _, attacks, runs = read(root, log_file)
    seen: set[str] = set()
    for attack in attacks:
        where = f"{LOG}:{attack.line}"
        if not ATTACK_ID.match(attack.id):
            problems.append(f"{where}: {attack.id!r} is not an attack ID (ATK-NNN)")
        if attack.id in seen:
            problems.append(f"{where}: {attack.id} has two rows")
        seen.add(attack.id)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", attack.date):
            problems.append(f"{where}: {attack.id} has no date (YYYY-MM-DD)")
        if not attack.tried:
            problems.append(f"{where}: {attack.id} does not say what was tried")
        if not RESULT.match(attack.result):
            problems.append(f"{where}: {attack.id}'s result {attack.result!r} is not Held, Fixed BUG-NNN, Open BUG-NNN or Not a flaw")
        named = tests_of(attack.test)
        if (attack.result == "Held" or attack.result.startswith("Fixed")) and not named:
            problems.append(f"{where}: {attack.id} is {attack.result} and names no test; name the test that holds it")
        for file, name in named:
            target = root / file
            if not target.is_file():
                problems.append(f"{where}: {attack.id} names {file}, which does not exist")
            elif name and name not in target.read_text(encoding="utf-8"):
                problems.append(f"{where}: {attack.id} names the test {name}, which is not in {file}")
    known = [a.id for a in attacks]
    run_ids: set[str] = set()
    for item in runs:
        where = f"{LOG}:{item.line}"
        if item.id in run_ids:
            problems.append(f"{where}: {item.id} has two sections")
        run_ids.add(item.id)
        for field in RUN_FIELDS:
            if not item.fields.get(field):
                problems.append(f"{where}: {item.id} has no '{field}'")
        for attack_id in re.findall(r"ATK-\d+", item.fields.get("Attacks", "")):
            if attack_id not in known:
                problems.append(f"{where}: {item.id} names {attack_id}, which has no row")
    return problems


def report(run_id: str, bugs: dict[str, str] | None = None, root: Path | None = None) -> str:
    """The build-test-break-harden report for one run, from the log. ``bugs``: BUG ID -> severity."""
    _, attacks, runs = read(root)
    found = next((r for r in runs if r.id == run_id), None)
    if found is None:
        raise AttackLogError(f"{run_id} is not in {log_name(root)}")
    by_id = {a.id: a for a in attacks}
    chosen = [by_id[i] for i in expand(found.fields.get("Attacks", ""), list(by_id)) if i in by_id]
    lines = [
        f"## Build, test, break, harden: {found.scope}",
        "",
        f"**Tests run:** {found.fields.get('Tests run', '')}",
        "",
        "**Attacks**",
        "",
        "| Attack | Area | What was tried | Test | Result |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {a.id} | {a.area} | {a.tried} | {a.test} | {a.result} |" for a in chosen]
    named = sorted({m.group(2) or m.group(3) for a in chosen if (m := RESULT.match(a.result)) and (m.group(2) or m.group(3))})
    bug_line = ", ".join(f"{b} ({(bugs or {}).get(b, 'see the register')})" for b in named) or "none found"
    lines += ["", f"**Bugs:** {bug_line}.", f"**Load:** {found.fields.get('Load', '')}", f"**Not tried:** {found.fields.get('Not tried', '')}"]
    return "\n".join(lines)


def _severities(root: Path | None = None) -> dict[str, str]:
    """BUG ID -> severity, read from the register's rows (the severity is a cell, or ends the description)."""
    register = (root or ROOT) / register_name(root)
    if not register.exists():
        return {}
    out = {}
    for line in register.read_text(encoding="utf-8").split("\n"):
        match = re.match(r"^\| *(BUG-\d+) *\|(.*)$", line)
        if match:
            severity = re.search(r"\b(Critical|High|Medium|Low)\b", match.group(2))
            out[match.group(1)] = severity.group(1) if severity else "no severity"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Keep the attack log ({LOG}).")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("add", help="an attack and its result")
    one.add_argument("area", help="the part of the product attacked, e.g. Billing, Sign-in")
    one.add_argument("tried", help="what was tried, in a sentence")
    one.add_argument("--test", action="append", default=[], help="file::test that holds it (repeatable)")
    result = one.add_mutually_exclusive_group(required=True)
    result.add_argument("--held", action="store_true", help="it did not get through")
    result.add_argument("--fixed", metavar="BUG-NNN", help="it got through and the bug is fixed")
    result.add_argument("--open", metavar="BUG-NNN", help="it got through and is not fixed yet")
    result.add_argument("--not-a-flaw", action="store_true", help="it looked like one and is not")
    many = sub.add_parser("run", help="a run of the skill, at the top of Runs")
    many.add_argument("scope", help="what the run covered")
    many.add_argument("--attacks", nargs="+", required=True, help="FIRST LAST, or a list of attack IDs")
    many.add_argument("--tests", required=True, help="the command and what it printed")
    many.add_argument("--load", required=True, help="the load tried and its result, or why none")
    many.add_argument("--not-tried", required=True, help="what was not tried, and why")
    show = sub.add_parser("report", help="print a run's report")
    show.add_argument("run_id")
    sub.add_parser("check", help="exit 1 on a problem")
    args = parser.parse_args()
    try:
        if args.command == "add":
            outcome = (
                "Held" if args.held else f"Fixed {args.fixed}" if args.fixed else f"Open {args.open}" if args.open else "Not a flaw"
            )
            print(f"{LOG}: {add(args.area, args.tried, args.test, outcome)} {outcome}")
        elif args.command == "run":
            print(f"{LOG}: {run(args.scope, args.attacks, args.tests, args.load, args.not_tried)}")
        elif args.command == "report":
            print(report(args.run_id, _severities()))
        else:
            problems = lint()
            for problem in problems:
                print(problem)
            print(f"{LOG}: {len(problems)} problems")
            return 1 if problems else 0
    except AttackLogError as error:
        print(f"attacks.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
