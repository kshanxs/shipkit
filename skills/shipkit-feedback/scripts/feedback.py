#!/usr/bin/env python3
"""Learnings from project work, drafted locally and filed as issues for the maintainer to review.

    feedback.py draft --skill harden --title "..." --happened "..." --lesson "..." [--change "..."]
    feedback.py list                     the drafts on this machine
    feedback.py show <id>                a draft's issue text, exactly as it would be posted
    feedback.py discard <id>             delete a draft
    feedback.py file --all [--dry-run]   post drafts, when this user has turned filing on
    feedback.py file <id> --yes          post one draft the user has just approved
    feedback.py consent on|off|status [--repo OWNER/NAME]
    feedback.py review [--repo OWNER/NAME]   issues waiting for the maintainer's review
    feedback.py check [--file PATH]      check an issue or PR text written by hand (stdin by default)

Nothing is posted unless this user turned filing on, or passed --yes. That choice and the target
repository live in the user's own config, never in a project's shipkit.toml: a repository someone
else wrote must not be able to publish your notes or redirect them. Every draft is checked for
secrets, personal details, project names and names of skills from other packs installed beside
shipkit (a report is about shipkit's own skills) when it is written and again before it is posted.
Standard library only.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UPSTREAM = "kshanxs/shipkit"
MARKER = "shipkit-auto"
DAILY_LIMIT = 3
FIELD_LIMIT = 4000
SIMILAR = 0.6
SKILLS = Path(__file__).resolve().parents[2]
GENERIC = {
    "shipkit", "project", "projects", "repo", "repository", "code", "test", "tests", "demo", "main",
    "backend", "frontend", "server", "client", "root", "home", "user", "admin", "developer", "work",
    "worktree", "tmp", "temp", "local", "localhost", "ubuntu", "debian", "runner", "github", "origin",
}
PATTERNS = [
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("an API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("a signed token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("a secret value", re.compile(r"(?i)\b(pass(word|wd)?|secret|token|api[_-]?key)\b[\"']?\s*[=:]\s*[\"']?[^\s\"']{8,}")),
    ("an email address", re.compile(r"\b[\w.+-]+@(?!(?:[\w-]+\.)*example\.(?:com|org|net)\b)[\w-]+\.[\w.-]+\b")),
    ("a home path", re.compile(r"(?:/home|/Users|/root)/[^\s/]+|[A-Za-z]:\\Users\\[^\s\\]+")),
    ("a URL", re.compile(r"(?i)\b(?:https?|ssh|git)://(?!(?:localhost|127\.0\.0\.1|example\.(?:com|org|net))(?:[:/\s]|$))\S+")),
    ("an IP address", re.compile(r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("an internal hostname", re.compile(r"(?i)\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:internal|lan|corp|intranet|local|ts\.net)\b")),
]


class Refused(Exception):
    """The request cannot go on; the message says why and what to do."""


# ── where things live ────────────────────────────────────────────────────────


def _base(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value else Path.home() / fallback


def drafts_dir() -> Path:
    return _base("XDG_STATE_HOME", ".local/state") / "shipkit" / "feedback"


def consent_path() -> Path:
    return _base("XDG_CONFIG_HOME", ".config") / "shipkit" / "feedback.json"


def _load(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, dict) else default


def _save(path: Path, data: dict) -> None:
    """Written whole, readable only by this user."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def consent() -> dict:
    data = _load(consent_path(), {})
    return {"auto": data.get("auto") is True, "repo": data.get("repo") or UPSTREAM}


# ── keeping private details out ──────────────────────────────────────────────


def _git(*args: str) -> str:
    try:
        done = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def project_terms() -> list[str]:
    """Names that identify this user, machine or project."""
    terms: set[str] = set()
    top = os.environ.get("SHIPKIT_ROOT") or _git("rev-parse", "--show-toplevel")
    if top:
        terms.add(Path(top).name)
    for remote in _git("remote").split():
        url = _git("remote", "get-url", remote)
        terms |= set(re.findall(r"[^/:]+", re.sub(r"\.git$", "", url))[-2:])
    name = _git("config", "user.name")
    terms |= {name, *name.split()}
    terms.add(_git("config", "user.email"))
    with_errors = [getpass.getuser, socket.gethostname]
    for read in with_errors:
        try:
            terms.add(read().split(".")[0])
        except (OSError, KeyError):
            pass
    source = os.environ.get("SHIPKIT_PRIVATE_TERMS")
    if source and Path(source).is_file():
        lines = Path(source).read_text(encoding="utf-8", errors="ignore").splitlines()
        terms |= {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}
    return sorted(t for t in terms if len(t) >= 4 and t.lower() not in GENERIC)


def shipkit_skills() -> set[str]:
    """Shipkit's own skills: the tables of switchboard/skills.toml, else the folders beside this one."""
    listing = SKILLS / "switchboard" / "skills.toml"
    if listing.is_file():
        return set(re.findall(r"(?m)^\[([a-z0-9][a-z0-9-]*)\]\s*$", listing.read_text(encoding="utf-8")))
    return {path.parent.name for path in SKILLS.glob("*/SKILL.md")}


def skill_folders() -> list[Path]:
    """Where agents install skills. SHIPKIT_SKILL_DIRS (os.pathsep-separated) replaces the list."""
    if "SHIPKIT_SKILL_DIRS" in os.environ:
        return [Path(p) for p in os.environ["SHIPKIT_SKILL_DIRS"].split(os.pathsep) if p]
    home = Path.home()
    folders = [SKILLS, home / ".claude" / "skills", home / ".agents" / "skills", home / ".codex" / "skills", Path.cwd() / ".claude" / "skills"]
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        if os.environ.get(variable):
            folders.append(Path(os.environ[variable]) / "skills")
    return folders


def outside_skills() -> list[str]:
    """Installed skills that are not shipkit's: a report must not name them."""
    own = shipkit_skills()
    found: set[str] = set()
    for folder in skill_folders():
        try:
            found |= {path.parent.name for path in folder.glob("*/SKILL.md")}
        except OSError:
            continue
    return sorted(n for n in found - own if len(n) >= 4 and n.lower() not in GENERIC)


def problems(text: str, terms: list[str], outside: list[str] | None = None) -> list[str]:
    """What must come out of the text. Matched private values are not repeated, so they never reach a log."""
    found = [label for label, pattern in PATTERNS if pattern.search(text)]
    for index, term in enumerate(terms):
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I):
            found.append(f"a private name (term {index + 1}, starting {term[0]!r})")
    named = [n for n in (outside or []) if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I)]
    if named:
        found.append(f"a skill outside shipkit ({', '.join(named)}); report on shipkit's own skills only, or reword a plain word")
    return found


def quiet_mentions(text: str) -> str:
    """`@name` in an issue notifies that person; keep it as code."""
    return re.sub(r"(?<![\w`/])@[A-Za-z0-9][\w./-]*", lambda m: f"`{m.group()}`", text)


# ── drafts ───────────────────────────────────────────────────────────────────


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def fingerprint(skill: str, title: str) -> str:
    return hashlib.sha256(f"{skill}|{' '.join(sorted(words(title)))}".encode()).hexdigest()[:12]


def issue_title(draft: dict) -> str:
    return quiet_mentions(f"{draft['skill']}: {draft['title']}")


def issue_body(draft: dict) -> str:
    parts = [
        "## Field report",
        "",
        f"**Skill:** `{draft['skill']}`",
        "",
        "Drafted by a coding agent from real project work. It needs a maintainer's review before anyone acts on it.",
        "",
        "## What happened",
        "",
        draft["happened"],
        "",
        "## Lesson",
        "",
        draft["lesson"],
    ]
    if draft.get("change"):
        parts += ["", "## Proposed change", "", draft["change"]]
    return quiet_mentions("\n".join(parts)) + f"\n\n<!-- {MARKER}:{draft['id']} -->\n"


def draft_path(draft_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", draft_id):
        raise Refused(f"{draft_id!r} is not a draft id")
    return drafts_dir() / f"{draft_id}.json"


def read_draft(draft_id: str) -> dict:
    path = draft_path(draft_id)
    if not path.exists():
        raise Refused(f"no draft {draft_id}; `feedback.py list` shows them")
    return json.loads(path.read_text(encoding="utf-8"))


def all_drafts() -> list[dict]:
    folder = drafts_dir()
    if not folder.is_dir():
        return []
    found = [_load(path, {}) for path in sorted(folder.glob("*.json"))]
    return [d for d in found if d.get("id")]


def check_draft(draft: dict) -> None:
    text = "\n".join([issue_title(draft), issue_body(draft)])
    found = problems(text, sorted({*project_terms(), *draft.get("terms", [])}), outside_skills())
    if found:
        raise Refused(f"draft {draft['id']} contains {', '.join(found)}. Rewrite it in generic terms.")


# ── GitHub ───────────────────────────────────────────────────────────────────


def gh(*args: str, stdin: str | None = None) -> str:
    try:
        done = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Refused(f"gh could not run ({error.__class__.__name__}); the draft is kept") from error
    if done.returncode:
        raise Refused(f"gh {args[0]} {args[1]} failed: {done.stderr.strip()[:300]}; the draft is kept")
    return done.stdout.strip()


def duplicate(draft: dict, issues: list[dict]) -> dict | None:
    """The same report, in any state, or an open issue about the same skill with a similar title."""
    tag = f"<!-- {MARKER}:{draft['id']} -->"
    mine = words(draft["title"])
    for issue in issues:
        if tag in (issue.get("body") or ""):
            return issue
        title = issue.get("title") or ""
        if issue.get("state", "").upper() != "OPEN" or not title.lower().startswith(draft["skill"].lower()):
            continue
        theirs = words(title.split(":", 1)[-1])
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= SIMILAR:
            return issue
    return None


def filed_today(state: dict, now: float) -> list[float]:
    return [t for t in state.get("filed", []) if isinstance(t, (int, float)) and now - t < 86400]


# ── commands ─────────────────────────────────────────────────────────────────


def cmd_draft(args: argparse.Namespace) -> int:
    if args.skill != "new-skill" and args.skill not in shipkit_skills():
        raise Refused(f"{args.skill!r} is not a shipkit skill; report on shipkit's own skills, or use `new-skill` for one that does not exist yet")
    for label, value in (("title", args.title), ("happened", args.happened), ("lesson", args.lesson), ("change", args.change or "")):
        limit = 120 if label == "title" else FIELD_LIMIT
        if len(value) > limit:
            raise Refused(f"--{label} is longer than {limit} characters")
        if "<!--" in value:
            raise Refused(f"--{label} cannot contain an HTML comment")
    if not all(v.strip() for v in (args.title, args.happened, args.lesson)):
        raise Refused("--title, --happened and --lesson cannot be empty")
    draft = {
        "id": fingerprint(args.skill, args.title),
        "skill": args.skill,
        "title": " ".join(args.title.split()),
        "happened": args.happened.strip(),
        "lesson": args.lesson.strip(),
        "change": (args.change or "").strip(),
        "terms": project_terms(),
        "created": int(time.time()),
    }
    check_draft(draft)
    _save(draft_path(draft["id"]), draft)
    print(f"Draft {draft['id']} saved on this machine. Nothing was posted.")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    drafts = all_drafts()
    for draft in drafts:
        print(f"{draft['id']}  {issue_title(draft)}")
    print(f"{len(drafts)} draft(s). Filing is {'on' if consent()['auto'] else 'off'}.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    draft = read_draft(args.id)
    print(f"Title: {issue_title(draft)}\n\n{issue_body(draft)}")
    return 0


def cmd_discard(args: argparse.Namespace) -> int:
    read_draft(args.id)
    draft_path(args.id).unlink()
    print(f"Discarded {args.id}")
    return 0


def cmd_consent(args: argparse.Namespace) -> int:
    current = consent()
    if args.state != "status":
        repo = args.repo or current["repo"]
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise Refused(f"{repo!r} is not OWNER/NAME")
        current = {"auto": args.state == "on", "repo": repo}
        state = _load(consent_path(), {})
        _save(consent_path(), {**state, **current})
    print(f"Filing is {'on' if current['auto'] else 'off'}; repository {current['repo']}")
    return 0


def cmd_file(args: argparse.Namespace) -> int:
    if bool(args.ids) == bool(args.all):
        raise Refused("name draft ids, or pass --all")
    settings = consent()
    if not args.yes and not args.dry_run and not settings["auto"]:
        raise Refused("filing is off. Show the user the draft and pass --yes if they approve, or they can run `feedback.py consent on`.")
    if args.repo and args.repo != settings["repo"] and not args.yes and not args.dry_run:
        raise Refused(f"filing is turned on for {settings['repo']}, not {args.repo}; pass --yes if the user approved it")
    repo = args.repo or settings["repo"]
    drafts = all_drafts() if args.all else [read_draft(i) for i in args.ids]
    if not drafts:
        print("No drafts to file.")
        return 0
    state_file = drafts_dir() / "state" / "filed.json"
    state = _load(state_file, {})
    now = time.time()
    recent = filed_today(state, now)
    issues = json.loads(gh("issue", "list", "-R", repo, "--state", "all", "--limit", "500", "--json", "number,title,body,state,url") or "[]")
    failed = 0
    for draft in drafts:
        try:
            check_draft(draft)
        except Refused as error:
            print(f"Held: {error}", file=sys.stderr)
            failed += 1
            continue
        same = duplicate(draft, issues)
        if same:
            print(f"{draft['id']}: already reported in #{same.get('number')}; draft removed")
            if not args.dry_run:
                draft_path(draft["id"]).unlink(missing_ok=True)
            continue
        if args.dry_run:
            print(f"{draft['id']}: would open on {repo}: {issue_title(draft)}")
            continue
        if len(recent) >= DAILY_LIMIT:
            print(f"Daily limit of {DAILY_LIMIT} reached; {draft['id']} stays a draft")
            continue
        url = gh("issue", "create", "-R", repo, "--title", issue_title(draft), "--body-file", "-", stdin=issue_body(draft))
        issues.append({"number": url.rsplit("/", 1)[-1], "title": issue_title(draft), "body": issue_body(draft), "state": "OPEN"})
        recent.append(now)
        _save(state_file, {**state, "filed": recent})
        draft_path(draft["id"]).unlink(missing_ok=True)
        print(f"{draft['id']}: {url}")
    return 1 if failed else 0


def cmd_review(args: argparse.Namespace) -> int:
    repo = args.repo or consent()["repo"]
    rows = json.loads(gh("issue", "list", "-R", repo, "--label", "needs-review", "--state", "open", "--limit", "100", "--json", "number,title,url") or "[]")
    for row in rows:
        print(f"#{row['number']}  {row['title']}  {row['url']}")
    print(f"{len(rows)} waiting for review on {repo}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    except OSError as error:
        raise Refused(f"cannot read {args.file}: {error.strerror}") from error
    found = problems(text, project_terms(), outside_skills())
    if found:
        raise Refused(f"the text contains {', '.join(found)}. Rewrite it in generic terms.")
    print("Clean: no secrets, private details, project names or skills outside shipkit.")
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description="Draft and file skill learnings for review.")
    sub = top.add_subparsers(dest="command", required=True)
    p = sub.add_parser("draft", help="save a learning on this machine")
    p.add_argument("--skill", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--happened", required=True)
    p.add_argument("--lesson", required=True)
    p.add_argument("--change")
    p.set_defaults(func=cmd_draft)
    sub.add_parser("list", help="the drafts here").set_defaults(func=cmd_list)
    p = sub.add_parser("show", help="a draft as it would be posted")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("discard", help="delete a draft")
    p.add_argument("id")
    p.set_defaults(func=cmd_discard)
    p = sub.add_parser("consent", help="turn automatic filing on or off for this user")
    p.add_argument("state", choices=("on", "off", "status"))
    p.add_argument("--repo")
    p.set_defaults(func=cmd_consent)
    p = sub.add_parser("file", help="post drafts as issues")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--yes", action="store_true", help="the user approved posting these drafts")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--repo")
    p.set_defaults(func=cmd_file)
    p = sub.add_parser("check", help="check issue or PR text written by hand")
    p.add_argument("--file", help="the text to check (default: stdin)")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("review", help="issues waiting for the maintainer")
    p.add_argument("--repo")
    p.set_defaults(func=cmd_review)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except Refused as error:
        print(f"feedback.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
