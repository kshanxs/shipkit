#!/usr/bin/env python3
"""
The handoff between agent sessions, kept in a Markdown file in the repository. Standard library only.

    python3 handoff.py init                         # write HANDOFF.md from the template
    python3 handoff.py show [--log 8]               # Now, Next up, Waiting, Blocked, Rules and the newest log rows
    python3 handoff.py log --entry "Billing retries" --agent Claude --area Dev \\
        --changed "Payments retry twice on a timeout" --links "PR #12 (abc1234)" \\
        --next "Add the refund webhook test" --status "In progress"
    python3 handoff.py check                        # the file has its sections and its log rows are well formed

The file is `file` in the [handoff] table of shipkit.toml (default HANDOFF.md at the project root);
`timezone` (an IANA name, default the machine's) dates log rows, `owner` names who answers the
"Waiting on" items, and `statuses`/`areas` list the words a row may use. A session reads the file
first and writes it last; the repository wins when the two disagree.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tomllib
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SECTIONS = ("Now", "Next up", "Waiting on", "Blocked", "Rules", "Page map", "Work log")
LOG_HEADER = "| Date | Entry | Agent | Area | What changed | Links | Next step | Status |"
DEFAULT_STATUSES = ["Done", "In progress", "Blocked", "Waiting on owner"]
DEFAULT_AREAS = ["Dev", "Docs", "Research", "Ops", "Launch", "Other"]


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


def settings() -> dict:
    path = ROOT / "shipkit.toml"
    table = tomllib.loads(path.read_text(encoding="utf-8")).get("handoff", {}) if path.is_file() else {}
    return {
        "file": ROOT / table.get("file", "HANDOFF.md"),
        "timezone": table.get("timezone", ""),
        "owner": table.get("owner", "the owner"),
        "statuses": table.get("statuses", DEFAULT_STATUSES),
        "areas": table.get("areas", DEFAULT_AREAS),
    }


def now(zone: str) -> str:
    if zone:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(zone)).isoformat(timespec="minutes")
    return datetime.now().astimezone().isoformat(timespec="minutes")


def sections(text: str) -> dict[str, tuple[int, int]]:
    """Section name -> (first line index of its body, index after its last line). `## Waiting on X` counts as Waiting on."""
    lines = text.split("\n")
    heads = [(i, line[3:].strip()) for i, line in enumerate(lines) if line.startswith("## ")]
    found = {}
    for n, (i, name) in enumerate(heads):
        key = next((s for s in SECTIONS if name == s or name.startswith(s + " ")), name)
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        found[key] = (i + 1, end)
    return found


def cell(text: str) -> str:
    return " ".join(text.replace("|", "/").split())


def cmd_init(_: argparse.Namespace) -> int:
    conf = settings()
    target = conf["file"]
    if target.exists():
        print(f"{target} exists; nothing written")
        return 0
    text = (SKILL / "references" / "HANDOFF.template.md").read_text(encoding="utf-8").replace("{owner}", conf["owner"])
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target}")
    return 0


def read_file() -> tuple[Path, str]:
    path = settings()["file"]
    if not path.exists():
        raise SystemExit(f"{path} does not exist: run handoff.py init, or say 'handoff not read: no file' and carry on")
    return path, path.read_text(encoding="utf-8")


def cmd_show(args: argparse.Namespace) -> int:
    path, text = read_file()
    lines = text.split("\n")
    found = sections(text)
    for name in SECTIONS[:-1]:
        if name in found:
            start, end = found[name]
            body = "\n".join(lines[start:end]).strip()
            print(f"## {lines[start - 1][3:].strip()}\n{body or '(empty)'}\n")
    if "Work log" in found:
        start, end = found["Work log"]
        rows = [line for line in lines[start:end] if line.startswith("| ") and not line.startswith(("| Date", "|---"))]
        print(f"## Work log (newest {min(args.log, len(rows))} of {len(rows)})")
        print(LOG_HEADER)
        print("|---|---|---|---|---|---|---|---|")
        print("\n".join(rows[: args.log]))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    conf = settings()
    if args.status not in conf["statuses"]:
        raise SystemExit(f"status {args.status!r} is not one of {', '.join(conf['statuses'])}")
    unknown = [a for a in args.area if a not in conf["areas"]]
    if unknown:
        raise SystemExit(f"area {', '.join(unknown)} is not one of {', '.join(conf['areas'])}")
    if not args.next.strip():
        raise SystemExit("--next is the single next action, specific enough to start on without reading the chat")
    path, text = read_file()
    lines = text.split("\n")
    found = sections(text)
    if "Work log" not in found:
        raise SystemExit(f"{path} has no '## Work log' section")
    start, end = found["Work log"]
    try:
        header = next(i for i in range(start, end) if lines[i].startswith("| Date"))
    except StopIteration:
        raise SystemExit(f"{path}: the Work log has no table header ({LOG_HEADER})") from None
    row = "| " + " | ".join(cell(v) for v in (args.date or now(conf["timezone"]), args.entry, args.agent, ", ".join(args.area), args.changed, args.links or "-", args.next, args.status)) + " |"
    lines.insert(header + 2, row)  # newest first, under the separator
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"{path.name}: {args.entry} · {args.status} · next: {args.next}")
    return 0


def problems_in(text: str, conf: dict) -> list[str]:
    problems = []
    found = sections(text)
    for name in SECTIONS:
        if name not in found:
            problems.append(f"no `## {name}` section")
    if "Work log" in found:
        lines = text.split("\n")
        start, end = found["Work log"]
        for i in range(start, end):
            line = lines[i]
            if not line.startswith("| ") or line.startswith(("| Date", "|---")):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            where = f"line {i + 1}"
            if len(cells) != 8:
                problems.append(f"{where}: a log row has 8 cells, this one {len(cells)}")
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}", cells[0]):
                problems.append(f"{where}: the date is YYYY-MM-DD with the time and zone")
            if cells[7] not in conf["statuses"]:
                problems.append(f"{where}: status {cells[7]!r} is not one of {', '.join(conf['statuses'])}")
            if not cells[6] or cells[6] == "-":
                problems.append(f"{where}: no next step")
    return problems


def cmd_check(_: argparse.Namespace) -> int:
    path, text = read_file()
    problems = problems_in(text, settings())
    for problem in problems:
        print(f"{path.name}: {problem}")
    print(f"{path.name}: {len(problems)} problems")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The handoff file between agent sessions.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    p = sub.add_parser("show")
    p.add_argument("--log", type=int, default=8, help="newest work log rows to show")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("log", help="add one work log row, newest first")
    p.add_argument("--entry", required=True, help="a short name for the work, not 'Session 3'")
    p.add_argument("--agent", required=True, help="the tool or person: Claude, Cursor, Codex, Manual, ...")
    p.add_argument("--area", nargs="+", default=["Dev"])
    p.add_argument("--changed", required=True, help="one to three sentences: what is different now")
    p.add_argument("--links", default="", help="every file, branch or PR touched, with its commit SHA for code")
    p.add_argument("--next", required=True, help="the single next action")
    p.add_argument("--status", required=True)
    p.add_argument("--date", help="override the timestamp (YYYY-MM-DDTHH:MM+ZZ:ZZ)")
    p.set_defaults(func=cmd_log)
    sub.add_parser("check").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
