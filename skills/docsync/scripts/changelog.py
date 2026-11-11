#!/usr/bin/env python3
"""The change logs: add an entry, group the entries, cut a release, check the format. Standard library only.

    python3 changelog.py add api fixed "An invoice was charged twice" --doc docs/features/billing.md
    python3 changelog.py add root added "Customers can pay an invoice online"
    python3 changelog.py tidy              # one heading per type; no entry reworded
    python3 changelog.py release 0.3.0     # Unreleased becomes [0.3.0] - today
    python3 changelog.py check             # exit 1 on a format problem

A log is named `root` (CHANGELOG.md) or by its package folder's name (`api`,
`web`: <package>/CHANGELOG.md for each folder matching `packages` in the
[docsync] table of shipkit.toml; default apps/*, packages/*, services/*).
`tidy`, `release` and `check` take every log when none is named.

An entry is written by the person or agent who made the change: a script can
see which files changed, not what the change means to the person using it. The
script does the rest: it puts the line under the right heading with its date
and its link, keeps one heading per type, and cuts the release.

The format is Keep a Changelog 1.1.0. `check_docs.py` runs `lint` as its
`unreleased` check, so the stop hook, the commit hook and CI all enforce it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from collections import Counter
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
DEFAULT_PACKAGES = ["apps/*", "packages/*", "services/*"]

# Keep a Changelog's types, in the order they are written.
TYPES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
UNRELEASED = "## [Unreleased]"
RELEASE = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})(?: \[YANKED\])?\s*$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.]+)?$")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class ChangelogError(Exception):
    """A request the script refuses, with the reason as its message."""


def packages_of(root: Path) -> list[str]:
    path = root / "shipkit.toml"
    if path.is_file():
        return tomllib.loads(path.read_text(encoding="utf-8")).get("docsync", {}).get("packages", DEFAULT_PACKAGES)
    return DEFAULT_PACKAGES


def logs(root: Path | None = None, packages: list[str] | None = None) -> dict[str, Path]:
    """Every change log that exists, by the name used on the command line: `root`, then each package's folder name."""
    root = root or ROOT
    found = {"root": root / "CHANGELOG.md"}
    folders = [p for pattern in (packages if packages is not None else packages_of(root)) for p in sorted(root.glob(pattern)) if p.is_dir()]
    names = [p.name for p in folders]
    for folder in dict.fromkeys(folders):
        # Two packages with one folder name (apps/web, packages/web) are named by their path instead.
        name = folder.name if names.count(folder.name) == 1 else folder.relative_to(root).as_posix()
        found[name] = folder / "CHANGELOG.md"
    return {name: path for name, path in found.items() if path.exists()}


def trim(lines: list[str]) -> list[str]:
    """The lines without the blank ones at either end."""
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def split(text: str) -> tuple[list[str], list[str], list[str]] | None:
    """(lines before the Unreleased heading, its block, lines from the next `## ` on), or None without one."""
    lines = text.split("\n")
    start = next((index for index, line in enumerate(lines) if line.strip() == UNRELEASED), None)
    if start is None:
        return None
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return lines[:start], lines[start + 1 : end], lines[end:]


def sections(block: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """The text above the first `### ` heading, and each (heading, body) in the order written."""
    preamble: list[str] = []
    found: list[tuple[str, list[str]]] = []
    for line in block:
        if line.startswith("### "):
            found.append((line[4:].strip(), []))
        elif found:
            found[-1][1].append(line)
        else:
            preamble.append(line)
    return preamble, found


def group(found: list[tuple[str, list[str]]]) -> dict[str, list[str]]:
    """One body per heading: the six types in order, then any other heading as written.

    Bodies under a repeated heading are joined in the order they were written,
    which keeps the newest first.
    """
    grouped: dict[str, list[str]] = {name: [] for name in TYPES}
    for name, body in found:
        grouped.setdefault(name, []).extend(trim(body))
    return grouped


def render(preamble: list[str], grouped: dict[str, list[str]]) -> list[str]:
    """The Unreleased block's lines, after its heading."""
    out = [""]
    if trim(preamble):
        out += [*trim(preamble), ""]
    for name, body in grouped.items():
        if body:
            out += [f"### {name}", "", *body, ""]
    return out


def join(before: list[str], middle: list[str], after: list[str]) -> str:
    return "\n".join([*before, *middle, *after]).rstrip("\n") + "\n"


def entries(text: str) -> dict[str, list[str]]:
    """The Unreleased entries by heading: each top-level `- ` line."""
    parts = split(text)
    if parts is None:
        return {}
    found: dict[str, list[str]] = {}
    for name, body in sections(parts[1])[1]:
        found.setdefault(name, []).extend(line for line in body if line.startswith("- "))
    return found


def tidied(text: str) -> str:
    """The log with one heading per type under Unreleased. No entry is reworded or dropped."""
    parts = split(text)
    if parts is None:
        raise ChangelogError(f"no `{UNRELEASED}` section")
    before, block, after = parts
    preamble, found = sections(block)
    result = join(before, [UNRELEASED, *render(preamble, group(found))], after)

    def words(value: str) -> Counter:
        return Counter(line for line in value.split("\n") if line.strip() and not line.startswith("### "))

    if words(result) != words(text):
        raise ChangelogError("grouping would change an entry; nothing was written")
    return result


def link(log: Path, doc: str, title: str | None, root: Path) -> str:
    """` — [Title](relative path)` for the document that describes the change."""
    name, _, fragment = doc.partition("#")
    target = (root / name).resolve()
    if not target.is_file():
        raise ChangelogError(f"{name}: no such document (give the path from the repository root)")
    if not title:
        heading = re.search(r"^# +(.+?)\s*$", target.read_text(encoding="utf-8"), re.M)
        title = heading.group(1) if heading else target.stem
    relative = Path(os.path.relpath(target, log.parent)).as_posix()
    return f" — [{title}]({relative}{'#' + fragment if fragment else ''})"


def add(log: Path, kind: str, text: str, *, doc: str | None = None, title: str | None = None,
        day: str | None = None, root: Path | None = None) -> str:
    """Write one entry at the top of its type under Unreleased. Returns the line written."""
    root = root or ROOT
    name = next((known for known in TYPES if known.lower() == kind.strip().lower()), None)
    if name is None:
        raise ChangelogError(f"`{kind}` is not a type; use one of: {', '.join(TYPES).lower()}")
    text = " ".join(text.split()).rstrip(".")
    if not text:
        raise ChangelogError("the entry is empty; say what changed for the person using it")
    day = day or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ChangelogError(f"`{day}` is not a date; write YYYY-MM-DD")
    line = f"- {text} ({day}){link(log, doc, title, root) if doc else ''}"

    parts = split(log.read_text(encoding="utf-8"))
    if parts is None:
        raise ChangelogError(f"{log.name}: no `{UNRELEASED}` section")
    before, block, after = parts
    preamble, found = sections(block)
    grouped = group(found)
    grouped[name].insert(0, line)
    log.write_text(join(before, [UNRELEASED, *render(preamble, grouped)], after), encoding="utf-8")
    return line


def tidy(log: Path) -> bool:
    """Group the log's Unreleased entries. True when the file changed."""
    text = log.read_text(encoding="utf-8")
    result = tidied(text)
    if result == text:
        return False
    log.write_text(result, encoding="utf-8")
    return True


def release(log: Path, version: str, day: str | None = None) -> bool:
    """Turn Unreleased into `## [version] - date` and open an empty Unreleased. False when there is nothing to release."""
    if not VERSION.match(version):
        raise ChangelogError(f"`{version}` is not a version; write three numbers, as in 0.3.0 or 2026.10.0")
    day = day or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ChangelogError(f"`{day}` is not a date; write YYYY-MM-DD")
    text = tidied(log.read_text(encoding="utf-8"))
    if re.search(rf"^## \[{re.escape(version)}\]", text, re.M):
        raise ChangelogError(f"{log.name}: [{version}] is already released")
    before, block, after = split(text)  # type: ignore[misc]  (tidied() has checked the heading is there)
    preamble, found = sections(block)
    if not any(trim(body) for _, body in found):
        return False
    released = [f"## [{version}] - {day}", *render(preamble, group(found))]
    log.write_text(join(before, [UNRELEASED, "", *released], after), encoding="utf-8")
    return True


def lint(log: Path, name: str | None = None) -> list[str]:
    """Format problems in one log, as `file:line: problem`."""
    name = name or log.name
    lines = log.read_text(encoding="utf-8").split("\n")
    problems: list[str] = []

    def problem(number: int, text: str) -> None:
        problems.append(f"{name}:{number}: {text}")

    opened = [index for index, line in enumerate(lines) if line.strip() == UNRELEASED]
    if not opened:
        return [f"{name}: no `{UNRELEASED}` section; new entries have nowhere to go"]
    for index in opened[1:]:
        problem(index + 1, f"a second `{UNRELEASED}` section")

    # Releases: `## [version] - date`, below Unreleased, newest first, each version once.
    seen: dict[str, int] = {}
    previous = ""
    for index, line in enumerate(lines):
        if not line.startswith("## [") or line.strip() == UNRELEASED:
            continue
        match = RELEASE.match(line)
        if not match:
            problem(index + 1, "a release heading is written `## [version] - YYYY-MM-DD`")
            continue
        if index < opened[0]:
            problem(index + 1, f"[{match['version']}] is above `{UNRELEASED}`; the newest comes first")
        if match["version"] in seen:
            problem(index + 1, f"[{match['version']}] is released twice (line {seen[match['version']]})")
        seen[match["version"]] = index + 1
        if previous and match["date"] > previous:
            problem(index + 1, f"[{match['version']}] is dated after the release above it; the newest comes first")
        previous = match["date"]

    # Unreleased: the six types, each once, holding dated list items.
    end = next((index for index in range(opened[0] + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    headings: dict[str, int] = {}
    current: tuple[str, int, int] | None = None  # heading, its line, entries under it

    def close() -> None:
        if current and current[2] == 0:
            problem(current[1], f"`### {current[0]}` has no entries")

    for index in range(opened[0] + 1, end):
        line = lines[index]
        if line.startswith("### "):
            close()
            heading = line[4:].strip()
            if heading not in TYPES:
                problem(index + 1, f"`### {heading}` is not a type; use one of: {', '.join(TYPES)}")
            elif heading in headings:
                problem(index + 1, f"`### {heading}` is also on line {headings[heading]}; run `changelog.py tidy`")
            headings.setdefault(heading, index + 1)
            current = (heading, index + 1, 0)
        elif line.startswith("- "):
            if current is None:
                problem(index + 1, "an entry under no heading; put it under its type")
                continue
            current = (current[0], current[1], current[2] + 1)
            if not DATE.search(line):
                problem(index + 1, "an entry with no date; end it with (YYYY-MM-DD)")
        elif line.strip() and current is not None and not line.startswith((" ", "\t")):
            problem(index + 1, "not a list item; an entry is one `- ` line")
    close()
    return problems


def chosen(names: list[str], root: Path) -> dict[str, Path]:
    known = logs(root)
    if not names:
        return known
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ChangelogError(f"no change log named {', '.join(unknown)}; there are: {', '.join(known)}")
    return {name: known[name] for name in names}


def shown(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Add to, group, release and check the change logs.")
    commands = parser.add_subparsers(dest="command", required=True)

    adding = commands.add_parser("add", help="write one entry under Unreleased")
    adding.add_argument("log", help="root, or a package folder name (api, web, ...)")
    adding.add_argument("type", help=", ".join(TYPES).lower())
    adding.add_argument("text", help="what changed, for the person using it")
    adding.add_argument("--doc", help="the document that describes it, from the repository root; may end in #heading")
    adding.add_argument("--title", help="the link's words; the document's title when left out")
    adding.add_argument("--date", help="YYYY-MM-DD; today when left out")

    tidying = commands.add_parser("tidy", help="one heading per type under Unreleased; no entry is reworded")
    tidying.add_argument("logs", nargs="*")

    releasing = commands.add_parser("release", help="turn Unreleased into a dated release")
    releasing.add_argument("version", help="three numbers: 0.3.0, or 2026.10.0")
    releasing.add_argument("logs", nargs="*")
    releasing.add_argument("--date", help="YYYY-MM-DD; today when left out")

    checking = commands.add_parser("check", help="report format problems; exit 1 when there are any")
    checking.add_argument("logs", nargs="*")

    args = parser.parse_args()
    try:
        if args.command == "add":
            (log,) = chosen([args.log], ROOT).values()
            print(f"{shown(log, ROOT)}: {add(log, args.type, args.text, doc=args.doc, title=args.title, day=args.date)}")
        elif args.command == "tidy":
            for log in chosen(args.logs, ROOT).values():
                print(f"{shown(log, ROOT)}: {'grouped' if tidy(log) else 'already grouped'}")
        elif args.command == "release":
            done = [log for log in chosen(args.logs, ROOT).values() if release(log, args.version, args.date)]
            for log in done:
                print(f"{shown(log, ROOT)}: [{args.version}] released")
            if not done:
                print("Nothing to release: no log has an entry under Unreleased.")
            else:
                print(f"Review the logs, commit them, then tag the commit: git tag -a v{args.version} -m \"Release {args.version}\"")
        else:
            found = [problem for log in chosen(args.logs, ROOT).values() for problem in lint(log, shown(log, ROOT))]
            for problem in found:
                print(problem)
            print(f"{len(chosen(args.logs, ROOT))} change logs checked: {len(found)} problems")
            return 1 if found else 0
    except ChangelogError as error:
        print(f"changelog: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
