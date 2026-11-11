#!/usr/bin/env python3
"""
The open questions register: check it, count it, and write each document's list from it.

    python3 open_loops.py            # check
    python3 open_loops.py --write    # check, and rewrite the counts and every document's list
    python3 open_loops.py --list     # every question: id, kind, status, area, title
    python3 open_loops.py --list --kind Decision --area Billing
    python3 open_loops.py --for apps/api/app/billing docs/features/billing.md
    python3 open_loops.py --changed  # open questions that touch what this change set changed
    python3 open_loops.py --show Q-012   # one entry, with the code its Lines point at

The register is `register` in the [open_loops] table of shipkit.toml (default
docs/open_questions.md), between `<!-- questions:start -->` and
`<!-- questions:end -->`. Inside it:

    ## Billing                             an area; the last one is "Answered"

    ### Q-012                              a question; its number is never reused

    **Who pays the card fee on a refund?** its title
    Decision · Open · raised 2026-10-06 · checked 2026-10-16 · needed with Q-003

    - **Context:** why the question exists: what raised it, and why it is not settled
    - **Today:** what the code does now
    - **If the customer:** what that answer would change
    - **Recommended:** the answer advised, if there is one
    - **Where:** [Billing §3](features/billing.md#3-refunds) · [Terms](features/legal.md)
    - **Code:** `apps/api/app/billing/`
    - **Lines:**
      - `apps/api/app/billing/refunds.py:77` `amount = sum(`: the amount refunded is the charge

The second line is `kind · status · raised date`, then optionally
` · checked date` (the day Context, Today and Lines were last read against the
code) and ` · needed …`. An answered question reads `Answered 2026-10-14` (or
`Dropped 2026-10-14`), carries an `Answer` field, and sits under `## Answered`.

A Lines anchor is `` `path:line` `text` ``: the text is found on that line of
the file. When the code moves, `--write` moves the line number to the nearest
line that still holds the text; when the text is gone, the check says so, since
the code the question rests on has changed.

Each document a question names under `Where` carries a list of the questions
open on it, between `<!-- open-questions:start -->` and
`<!-- open-questions:end -->`. `--write` puts the list at the end of a document
that has none, and keeps it wherever the markers are moved to. A start marker
written `<!-- open-questions:start bare -->` gets the list with no heading, for
a section that already has one.

Checks:
  format     a line in the register is not an area, a question or a field
  ids        a number is used twice, or is not `Q-` and three digits
  words      a kind or a status is not one of the register's words
  place      an answered question is outside "Answered", or an open one is in it
  fields     an open question lacks Context, Today, an "If …" line or Where, or has Code and no Lines;
             an answered one lacks Answer
  where      a Where link points at a file that does not exist
  code       a Code path does not exist
  lines      a Lines anchor names no file, or its text is not on its line (--write moves the number
             when the text is elsewhere in the file; text that is gone means the question needs reading again)
  refs       a document names a question the register does not have
  lists      a document's list is not what the register says (--write fixes it)
  counts     the counts table is not what the register adds up to (--write fixes it)

Exit status is 1 when anything is reported. `--changed` and `--for` only
report; they always exit 0. SHIPKIT_ROOT points the script at another tree.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
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


def _config() -> dict:
    path = ROOT / "shipkit.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


_CFG = _config()
DOCS = _CFG.get("docsync", {}).get("docs_dir", "docs")
REGISTER = Path(_CFG.get("open_loops", {}).get("register", f"{DOCS}/open_questions.md"))

KINDS = tuple(_CFG.get("open_loops", {}).get("kinds", ("Decision", "Confirmation", "Advice", "Fact")))
STATUSES = ("Open", "Answered", "Dropped")
ANSWERED = "Answered"
# A list is written into documents, never into logs or the register itself.
NO_LIST = {REGISTER.as_posix(), f"{DOCS}/bugs_fixed_and_improvements.md", *_CFG.get("open_loops", {}).get("no_list", [])}
PRUNE = {"node_modules", ".git", "assets"}

BODY = re.compile(r"<!-- questions:start -->\n(.*?)<!-- questions:end -->", re.S)
COUNTS = re.compile(r"(<!-- counts:start -->\n).*?(<!-- counts:end -->)", re.S)
LIST = re.compile(r"<!-- open-questions:start( bare)? -->\n(?:.*?\n)?<!-- open-questions:end -->\n?", re.S)
ID = re.compile(r"\bQ-\d{3}\b")
# A field is `- **Name:** text`; a field whose text is a list below it (Lines) ends at the colon.
FIELD = re.compile(r"^- \*\*(?P<name>[^*]+?):\*\*(?: (?P<text>.+))?$")
LINK = re.compile(r"\]\(([^)\s]+)\)")
DATE = r"\d{4}-\d{2}-\d{2}"
STATE = re.compile(rf"^(?P<status>\w+)(?: (?P<date>{DATE}))?$")
ANCHOR = re.compile(r"`(?P<path>[^`\s]+?):(?P<line>\d+)` `(?P<text>[^`]+)`")


@dataclass
class Question:
    id: str
    area: str
    line: int
    title: str = ""
    kind: str = ""
    status: str = ""
    closed: str = ""
    raised: str = ""
    checked: str = ""
    needed: str = ""
    fields: list[tuple[str, str]] = field(default_factory=list)

    def get(self, name: str) -> str:
        return next((text for key, text in self.fields if key == name), "")

    @property
    def open(self) -> bool:
        return self.status == "Open"

    @property
    def where(self) -> list[str]:
        """The files this question names under Where, as paths from the repository root."""
        targets = (target.partition("#")[0] for target in LINK.findall(self.get("Where")))
        return [os.path.normpath((REGISTER.parent / target).as_posix()) for target in targets if target]

    @property
    def code(self) -> list[str]:
        return [path.rstrip("/") for path in re.findall(r"`([^`]+)`", self.get("Code"))]

    @property
    def anchors(self) -> list[tuple[str, int, str]]:
        """(path, line, text) for each anchor under Lines."""
        return [(found["path"], int(found["line"]), found["text"]) for found in ANCHOR.finditer(self.get("Lines"))]

    @property
    def touches(self) -> list[str]:
        """The paths a change to which is a cue to read this question again: Code folders and Lines files."""
        return list(dict.fromkeys(self.code + [path for path, _, _ in self.anchors]))


def parse(text: str) -> tuple[list[Question], list[str]]:
    """The questions of the register, and what is wrong with its lines."""
    match = BODY.search(text)
    if not match:
        return [], [f"{REGISTER}: no `<!-- questions:start -->` … `<!-- questions:end -->` block"]
    first_line = text[: match.start(1)].count("\n") + 1
    questions: list[Question] = []
    problems: list[str] = []
    area = ""
    current: Question | None = None
    for offset, raw in enumerate(match.group(1).splitlines()):
        number = first_line + offset
        where = f"{REGISTER}:{number}"
        if not raw.strip():
            continue
        if raw.startswith("## "):
            area, current = raw[3:].strip(), None
        elif raw.startswith("### "):
            name = raw[4:].strip()
            if not re.fullmatch(r"Q-\d{3}", name):
                problems.append(f"{where}: ids: `{name}` is not `Q-` and three digits, alone on its heading")
            current = Question(name, area, number)
            questions.append(current)
        elif current is None:
            problems.append(f"{where}: format: text outside a question: {raw.strip()[:70]}")
        elif not current.title:
            if raw.startswith("**") and raw.endswith("**"):
                current.title = raw.strip("*").strip()
            else:
                problems.append(f"{where}: format: the line after `### {current.id}` is the title, in bold")
                current.title = raw.strip()
        elif not current.kind:
            problems += [f"{where}: {problem}" for problem in read_state(current, raw)]
        elif FIELD.match(raw):
            found = FIELD.match(raw)
            current.fields.append((found["name"].strip(), (found["text"] or "").strip()))
        elif raw.startswith("  ") and current.fields:
            name, so_far = current.fields[-1]
            current.fields[-1] = (name, f"{so_far} {raw.strip()}".strip())
        else:
            problems.append(f"{where}: format: not a field (`- **Name:** text`) or its continuation: {raw.strip()[:70]}")
    return questions, problems


def read_state(question: Question, raw: str) -> list[str]:
    """Fill a question from its `kind · status · raised date · needed …` line."""
    parts = [part.strip() for part in raw.split(" · ")]
    question.kind = parts[0]
    problems = []
    if question.kind not in KINDS:
        problems.append(f"words: `{question.kind}` is not one of {', '.join(KINDS)}")
    state = STATE.match(parts[1]) if len(parts) > 1 else None
    if not state or state["status"] not in STATUSES:
        problems.append(f"words: the second part is one of {', '.join(STATUSES)}, with its date when not Open")
    else:
        question.status, question.closed = state["status"], state["date"] or ""
        if question.open == bool(question.closed):
            problems.append("words: Open carries no date; Answered and Dropped carry the date of the answer")
    for part in parts[2:]:
        if re.fullmatch(rf"raised {DATE}", part):
            question.raised = part[7:]
        elif re.fullmatch(rf"checked {DATE}", part):
            question.checked = part[8:]
        elif part.startswith("needed "):
            question.needed = part[7:]
        else:
            problems.append(f"format: `{part}` is not `raised YYYY-MM-DD`, `checked YYYY-MM-DD` or `needed …`")
    if not question.raised:
        problems.append("format: the line needs `raised YYYY-MM-DD`")
    elif question.checked and question.checked < question.raised:
        problems.append("format: a question cannot be checked before it was raised")
    return problems


def check_register(questions: list[Question]) -> list[str]:
    problems = []
    seen: dict[str, int] = {}
    for question in questions:
        where = f"{REGISTER}:{question.line}"
        if question.id in seen:
            problems.append(f"{where}: ids: {question.id} is also on line {seen[question.id]}")
        seen[question.id] = question.line
        if not question.status:
            continue
        if question.open == (question.area == ANSWERED):
            problems.append(f"{where}: place: {question.id} is {question.status}, so it belongs {'above' if question.open else 'under'} `## {ANSWERED}`")
        names = [name for name, _ in question.fields]
        needed = ["Context", "Today", "Where"] if question.open else ["Answer"]
        if question.open and question.code:
            needed.append("Lines")
        problems += [f"{where}: fields: {question.id} has no `{name}` line" for name in needed if name not in names]
        if "Lines" in names and not question.anchors:
            problems.append(f"{where}: lines: {question.id} has a Lines field with no `` `path:line` `text` `` anchor")
        if question.open and not any(name.startswith("If ") or name == "Until answered" for name in names):
            problems.append(f"{where}: fields: {question.id} says nothing of what an answer changes; add an `If …` or `Until answered` line")
        if question.open and "Where" in names and not question.where:
            problems.append(f"{where}: where: {question.id} links to no document")
        for target in question.where:
            if not (ROOT / target).is_file():
                problems.append(f"{where}: where: {question.id} links to {target}, which does not exist")
        for path in question.code:
            if not (ROOT / path).exists():
                problems.append(f"{where}: code: {question.id} names `{path}`, which does not exist")
    return problems


def check_lines(text: str, questions: list[Question], write: bool) -> tuple[str, list[str]]:
    """Hold every open question's anchors to the code; with `write`, move a line number to where its text went."""
    problems: list[str] = []
    moves: dict[str, str] = {}
    files: dict[str, list[str] | None] = {}
    for question in questions:
        if not question.open:
            continue
        where = f"{REGISTER}:{question.line}"
        for path, line, wanted in question.anchors:
            if path not in files:
                target = ROOT / path
                files[path] = target.read_text(encoding="utf-8", errors="replace").split("\n") if target.is_file() else None
            lines = files[path]
            if lines is None:
                problems.append(f"{where}: lines: {question.id} names `{path}`, which is not a file")
                continue
            if 0 < line <= len(lines) and wanted in lines[line - 1]:
                continue
            found = [number for number, text_ in enumerate(lines, 1) if wanted in text_]
            if not found:
                problems.append(
                    f"{where}: lines: {question.id}: `{wanted}` is no longer in {path}; the code this question rests on "
                    "changed, so read it again and update Context, Today and Lines"
                )
                continue
            nearest = min(found, key=lambda number: abs(number - line))
            if write:
                moves[f"`{path}:{line}` `{wanted}`"] = f"`{path}:{nearest}` `{wanted}`"
            else:
                problems.append(f"{where}: lines: {question.id}: `{wanted}` moved from {path}:{line} to line {nearest}; run open_loops.py --write")
    for old, new in moves.items():
        text = text.replace(old, new)
    return text, problems


def documents() -> list[Path]:
    found = []
    for directory, names, files in os.walk(ROOT / DOCS):
        names[:] = sorted(name for name in names if name not in PRUNE)
        found += [Path(directory) / name for name in sorted(files) if name.endswith(".md")]
    return found


def takes_list(path: str) -> bool:
    return path.startswith(f"{DOCS}/") and path not in NO_LIST


def render(document: str, questions: list[Question], bare: bool) -> str:
    """The list a document carries: the questions open on it, each linked to the register."""
    register = os.path.relpath(REGISTER.as_posix(), os.path.dirname(document))
    link = f"[open questions register]({register})"
    start = f"<!-- open-questions:start{' bare' if bare else ''} -->\n"
    end = "<!-- open-questions:end -->\n"
    if not questions:
        return f"{start}No question is open here; see the {link}.\n{end}" if bare else ""
    heading = "" if bare else "## Open questions\n\n"
    intro = (
        f"Each of these waits for an answer and can change what this page says. The {link} says what the code "
        "does today and what each answer would change. This list is written from it; change it there.\n\n"
    )
    rows = "".join(f"- [{q.id}]({register}#{q.id.lower()}) · {q.kind} · {q.title}\n" for q in questions)
    return f"{start}{heading}{intro}{rows}{end}"


def with_list(text: str, document: str, questions: list[Question]) -> str:
    """A document's text with its list brought up to date, added at the end, or taken out."""
    found = LIST.search(text)
    block = render(document, questions, bool(found and found.group(1)))
    if not found:
        return f"{text.rstrip(chr(10))}\n\n{block}" if block else text
    if block:
        return text[: found.start()] + block + text[found.end() :]
    head, tail = text[: found.start()].rstrip("\n"), text[found.end() :].lstrip("\n")
    return f"{head}\n\n{tail}" if tail else f"{head}\n"


def sync_lists(questions: list[Question], write: bool) -> list[str]:
    """Hold every document's list to the register; with `write`, rewrite the ones that differ."""
    known = {question.id for question in questions}
    problems = []
    for path in documents():
        name = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if name != REGISTER.as_posix():
            for number, line in enumerate(text.split("\n"), 1):
                problems += [f"{name}:{number}: refs: {found} is not in the register" for found in ID.findall(line) if found not in known]
        if not takes_list(name):
            continue
        mine = [question for question in questions if question.open and name in question.where]
        wanted = with_list(text, name, mine)
        if wanted == text:
            continue
        if write:
            path.write_text(wanted, encoding="utf-8")
        else:
            problems.append(f"{name}: lists: the open questions list is out of date; run open_loops.py --write")
    return problems


def counts_table(questions: list[Question]) -> str:
    live = [question for question in questions if question.open]
    areas = list(dict.fromkeys(question.area for question in live))
    rows = [f"| Area | Open | {' | '.join(KINDS)} |", "|---|---|" + "---|" * len(KINDS)]
    for area in areas:
        mine = [question for question in live if question.area == area]
        rows.append(f"| {area} | {len(mine)} | {' | '.join(str(sum(q.kind == kind for q in mine)) for kind in KINDS)} |")
    totals = " | ".join(f"**{sum(q.kind == kind for q in live)}**" for kind in KINDS)
    rows.append(f"| **All** | **{len(live)}** | {totals} |")
    return "\n".join(rows) + f"\n\nAnswered or dropped, and kept below: {len(questions) - len(live)}.\n"


def check_counts(text: str, questions: list[Question]) -> list[str]:
    match = COUNTS.search(text)
    if not match:
        return [f"{REGISTER}: counts: no `<!-- counts:start -->` … `<!-- counts:end -->` block"]
    current = text[match.end(1) : match.start(2)]
    return [] if current == counts_table(questions) else [f"{REGISTER}: counts: the table is out of date; run open_loops.py --write"]


def touching(questions: list[Question], paths: list[str]) -> dict[str, list[str]]:
    """Open question id -> the given paths it touches, by a Where document or a Code path."""
    hits: dict[str, list[str]] = {}
    for question in questions:
        if not question.open:
            continue
        for path in paths:
            path = path.rstrip("/")
            in_code = any(path == code or path.startswith(code + "/") or code.startswith(path + "/") for code in question.touches)
            in_where = any(path == target or target.startswith(path + "/") for target in question.where)
            if in_code or in_where:
                hits.setdefault(question.id, []).append(path)
    return hits


def changed_files(base: str | None = None, staged: bool = False) -> set[str]:
    def git(*args: str) -> list[str]:
        done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
        return done.stdout.splitlines() if done.returncode == 0 else []

    if staged:
        return set(git("diff", "--cached", "--name-only"))
    found = {line[3:].split(" -> ")[-1].strip('"') for line in git("status", "--porcelain", "--untracked-files=all")}
    if base:
        found |= set(git("diff", "--name-only", f"{base}...HEAD"))
    return found


def reminders(questions: list[Question], changed: set[str]) -> list[str]:
    """What to look at again: open questions that touch a changed file, when the register did not change."""
    if REGISTER.as_posix() in changed:
        return []
    by_id = {question.id: question for question in questions}
    hits = touching(questions, sorted(changed))
    return [f"{name} ({by_id[name].title}) touches {', '.join(paths[:3])}{' and more' if len(paths) > 3 else ''}" for name, paths in sorted(hits.items())]


def load() -> tuple[str, list[Question], list[str]]:
    path = ROOT / REGISTER
    if not path.exists():
        return "", [], [f"{REGISTER} is missing"]
    text = path.read_text(encoding="utf-8")
    questions, problems = parse(text)
    return text, questions, problems


def remind_once() -> list[str]:
    """For the stop hook: this change set's reminders, given once for each distinct set."""
    _, questions, _ = load()
    found = reminders(questions, changed_files())
    marker = ROOT / ".git" / "open-questions-reminded"
    if not found or not marker.parent.is_dir():
        return found
    key = hashlib.sha1("\n".join(found).encode()).hexdigest()
    if marker.exists() and marker.read_text(encoding="utf-8") == key:
        return []
    marker.write_text(key, encoding="utf-8")
    return found


def show(question: Question) -> str:
    """One entry as the register has it, then each anchor with the line of code it points at today."""
    head = f"{question.id} · {question.kind} · {question.status}{' ' + question.closed if question.closed else ''} · {question.area}"
    dates = f"raised {question.raised}" + (f" · checked {question.checked}" if question.checked else " · not checked against the code")
    body = [head, question.title, dates, ""] + [f"{name}: {text}" for name, text in question.fields if name != "Lines"]
    if question.anchors:
        body += ["", "Lines, and the code on each today:"]
        for item in re.split(r"(?:^|\s)- (?=`)", question.get("Lines")):
            found = ANCHOR.match(item.strip())
            if not found:
                continue
            path, line = found["path"], int(found["line"])
            note = item.strip()[found.end() :].lstrip(": ").strip()
            target = ROOT / path
            lines = target.read_text(encoding="utf-8", errors="replace").split("\n") if target.is_file() else []
            code = lines[line - 1].strip() if 0 < line <= len(lines) else "(no such line)"
            body.append(f"  {path}:{line}{'  (' + note + ')' if note else ''}\n      {code}")
    return "\n".join(body)


def listing(questions: list[Question], kind: str | None, area: str | None, status: str | None) -> str:
    rows = [
        f"{q.id}  {q.kind:<13} {q.status:<9} {q.area:<28} {q.title}"
        for q in questions
        if (kind is None or q.kind == kind) and (status is None or q.status == status) and (area is None or area.lower() in q.area.lower())
    ]
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="rewrite the counts table and every document's list from the register")
    parser.add_argument("--list", action="store_true", help="print every question")
    parser.add_argument("--kind", choices=KINDS, help="with --list: only this kind")
    parser.add_argument("--status", choices=STATUSES, help="with --list: only this status")
    parser.add_argument("--area", help="with --list: only areas whose name contains this")
    parser.add_argument("--for", dest="paths", nargs="+", metavar="PATH", help="print the open questions that touch these files or folders")
    parser.add_argument("--changed", action="store_true", help="print the open questions that touch what this change set changed")
    parser.add_argument("--base", help="with --changed: also count commits since this ref")
    parser.add_argument("--staged", action="store_true", help="with --changed: judge only what is staged for commit")
    parser.add_argument("--show", metavar="Q-NNN", help="print one entry, with the code its Lines point at")
    args = parser.parse_args()

    if not (ROOT / REGISTER).exists():
        print(f"open questions: {REGISTER} does not exist yet; nothing to check (start one from the skill's references/open_questions.example.md)")
        return 0
    text, questions, problems = load()
    if not text:
        print(problems[0])
        return 1

    if args.list:
        print(listing(questions, args.kind, args.area, args.status))
        return 0
    if args.show:
        found = next((question for question in questions if question.id == args.show.upper()), None)
        print(show(found) if found else f"{args.show} is not in the register")
        return 0 if found else 1
    if args.paths:
        by_id = {question.id: question for question in questions}
        for name in sorted(touching(questions, [os.path.normpath(path) for path in args.paths])):
            question = by_id[name]
            print(f"{name} · {question.kind} · {question.title}\n    Why: {question.get('Context')}\n    Today: {question.get('Today')}")
        return 0
    if args.changed:
        found = reminders(questions, changed_files(args.base, args.staged))
        for line in found:
            print(line)
        print(f"open questions: {len(found)} touch this change set; for each, see whether it is answered or its Today line still holds")
        return 0

    text, moved = check_lines(text, questions, args.write)
    if args.write:
        if COUNTS.search(text):
            text = COUNTS.sub(lambda m: m.group(1) + counts_table(questions) + m.group(2), text)
        (ROOT / REGISTER).write_text(text, encoding="utf-8")

    problems += check_register(questions) + moved + sync_lists(questions, args.write) + check_counts(text, questions)
    for problem in problems:
        print(problem)
    live = sum(question.open for question in questions)
    print(f"open questions: {live} open, {len(questions) - live} answered or dropped, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
