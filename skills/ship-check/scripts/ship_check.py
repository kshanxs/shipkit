#!/usr/bin/env python3
"""
The launch-readiness audit: scaffold the report from a checklist, then hold the filled report to
its rules. Read-only on the code: it never builds or fixes anything. Standard library only.

    python3 ship_check.py scaffold [--out ship-check-report.md]   # the report's skeleton, with files to read per item
    python3 ship_check.py check ship-check-report.md               # every status a word, every claim a real path
    python3 ship_check.py init                                     # write ship-check.toml (the generic SaaS checklist)

The checklist is `ship-check.toml` at the project root, or the path in `[ship_check] checklist` of
shipkit.toml; without one, the skill's references/checklist.example.toml (generic SaaS) is used.
Status words: DONE, PARTIAL, MISSING, UNKNOWN (never guessed). Capabilities: PRESENT, PARTIAL,
MISSING, UNKNOWN. `check` exits 1 when a row's status is not one of the words, a DONE, PARTIAL or
PRESENT row cites no path, a cited path does not exist, the head SHA is missing, or the report has
no top-five list.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
STATUS = ("DONE", "PARTIAL", "MISSING", "UNKNOWN")
CAPABILITY = ("PRESENT", "PARTIAL", "MISSING", "UNKNOWN")
NEEDS_EVIDENCE = {"DONE", "PARTIAL", "PRESENT"}
PRUNE = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next", ".expo", "coverage"}


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


def checklist_path() -> Path:
    shipkit = ROOT / "shipkit.toml"
    if shipkit.is_file():
        configured = tomllib.loads(shipkit.read_text(encoding="utf-8")).get("ship_check", {}).get("checklist")
        if configured and (ROOT / configured).is_file():
            return ROOT / configured
    own = ROOT / "ship-check.toml"
    return own if own.is_file() else SKILL / "references" / "checklist.example.toml"


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def matches(patterns: list[str], limit: int = 6) -> list[str]:
    """Files under the root matching any glob, nearest first, at most `limit`."""
    found: list[str] = []
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT)
            if any(part in PRUNE for part in rel.parts):
                continue
            name = rel.as_posix() + ("/" if path.is_dir() else "")
            if name not in found:
                found.append(name)
            if len(found) >= limit:
                return found
    return found


def hint_text(patterns: list[str]) -> str:
    hits = matches(patterns)
    return ", ".join(f"`{h}`" for h in hits) if hits else "nothing matched; look by hand"


def scaffold(cfg: dict) -> str:
    sha = git("rev-parse", "HEAD") or "unknown (not a git checkout)"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    deploy = cfg.get("target", {}).get("deploy_branch", "main")
    product = cfg.get("product", {}).get("name", ROOT.name)
    behind = git("rev-list", "--count", f"{deploy}..HEAD") if git("rev-parse", "--verify", "--quiet", deploy) else ""
    lines = [
        f"# Launch readiness: {product}",
        "",
        f"Audited: `{branch}` at `{sha}` on {date.today().isoformat()}. "
        + (f"{behind} commits on this branch are not on `{deploy}` yet." if behind else f"Compare with `{deploy}` by hand: which fixes are not deployed yet."),
        "",
        "Read-only audit. Every claim cites a path (with a line where there is one); what could not be verified is UNKNOWN.",
        "Status words: DONE, PARTIAL, MISSING, UNKNOWN. Capabilities: PRESENT, PARTIAL, MISSING, UNKNOWN.",
        "",
        "## Sources read",
        "",
    ]
    for group, patterns in cfg.get("sources", {}).items():
        lines.append(f"- {group}: {hint_text(patterns)}")
    lines += ["", "## 1. Operator capabilities", "", "| Capability | Status | Evidence | Note |", "|---|---|---|---|"]
    for item in cfg.get("capabilities", []):
        lines.append(f"| {item['name']} | UNKNOWN | | Read: {hint_text(item.get('hints', []))} |")
    lines += ["", "## 2. Onboarding flows", "", "| Flow | Status | Evidence | Gap against common practice |", "|---|---|---|---|"]
    for item in cfg.get("flows", []):
        lines.append(f"| {item['name']} | UNKNOWN | | Read: {hint_text(item.get('hints', []))} |")
    lines += ["", "## 3. Status checklist", ""]
    for group in cfg.get("checklist", []):
        note = f" ({group['note']})" if group.get("note") else ""
        lines += [f"### {group['group']}{note}", "", "| Item | Status | Evidence | Note |", "|---|---|---|---|"]
        for item in group.get("items", []):
            name, hints = (item["name"], item.get("hints", [])) if isinstance(item, dict) else (item, group.get("hints", []))
            lines.append(f"| {name} | UNKNOWN | | Read: {hint_text(hints)} |")
        lines.append("")
    pricing = cfg.get("pricing", {})
    if pricing:
        lines += ["## 4. Pricing", "", f"Read: {hint_text(pricing.get('hints', []))}. Exact values with paths; flag a stale document.", "",
                  "| Item | Value | Evidence |", "|---|---|---|"]
        lines += [f"| {item} | unknown | |" for item in pricing.get("items", [])]
        lines.append("")
    lines += [
        "## 5. Bugs and risks",
        "",
        f"Open bugs: {hint_text(cfg.get('bugs', {}).get('hints', ['docs/testing/bug_report.md']))}. In-flight pull requests: list them by number.",
        "",
        "### Launch blockers",
        "",
        "1. ",
        "",
        "### Other risks",
        "",
        "1. ",
        "",
        "### Unknowns",
        "",
        "1. ",
        "",
        "## Top 5 before launch",
        "",
        "1. ",
        "2. ",
        "3. ",
        "4. ",
        "5. ",
        "",
        "Nothing has been started. The owner picks what goes to the builder.",
        "",
    ]
    return "\n".join(lines)


ROW = re.compile(r"^\| *([^|]+?) *\| *([A-Za-z]+) *\| *([^|]*?) *\|")
CITED = re.compile(r"`([^`\s]+?)(?::\d+(?:-\d+)?)?`")


def check(report: Path) -> list[str]:
    text = report.read_text(encoding="utf-8")
    problems = []
    if not re.search(r"`[0-9a-f]{7,40}`", text):
        problems.append("the head SHA audited is not written at the top (`<sha>`)")
    if "## Top 5 before launch" not in text:
        problems.append("no `## Top 5 before launch` section")
    section = ""
    for number, line in enumerate(text.split("\n"), 1):
        if line.startswith("## "):
            section = line
        found = ROW.match(line)
        if not found or set(found.group(2)) <= set("-") or found.group(1) in ("Item", "Capability", "Flow"):
            continue
        status = found.group(2)
        words = CAPABILITY if "capabilit" in section.lower() else STATUS
        if "Pricing" in section:
            continue
        if status not in words:
            problems.append(f"{report.name}:{number}: `{status}` is not one of {', '.join(words)}")
            continue
        evidence = found.group(3)
        cited = CITED.findall(evidence)
        if status in NEEDS_EVIDENCE and not cited:
            problems.append(f"{report.name}:{number}: {found.group(1)} is {status} with no path as evidence")
        for path in cited:
            if not (ROOT / path.rstrip("/")).exists():
                problems.append(f"{report.name}:{number}: {found.group(1)} cites `{path}`, which does not exist")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold and check a launch-readiness report.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scaffold")
    p.add_argument("--out", help="write here instead of printing")
    p = sub.add_parser("check")
    p.add_argument("report")
    sub.add_parser("init")
    args = parser.parse_args(argv)
    if args.cmd == "init":
        target = ROOT / "ship-check.toml"
        if target.exists():
            print(f"{target} exists; nothing written")
            return 0
        shutil.copy(SKILL / "references" / "checklist.example.toml", target)
        print(f"wrote {target}; make the checklist yours (regulations, operator console, flows, pricing)")
        return 0
    if args.cmd == "scaffold":
        cfg = tomllib.loads(checklist_path().read_text(encoding="utf-8"))
        text = scaffold(cfg)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out} from {checklist_path()}")
        else:
            print(text)
        return 0
    problems = check(Path(args.report))
    for problem in problems:
        print(problem)
    print(f"{args.report}: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
