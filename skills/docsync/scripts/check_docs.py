#!/usr/bin/env python3
"""Documentation checks for any repository. Standard library only (Python 3.11+).

    python3 check_docs.py            # all checks
    python3 check_docs.py --strict   # warnings fail too
    python3 check_docs.py --changed  # also check this change set
    python3 check_docs.py --changed --base main
    python3 check_docs.py --changed --staged   # what a commit would contain
    python3 check_docs.py --map      # who links to what

Every path and rule comes from the `[docsync]` table of `shipkit.toml` at the
project root (see references/config.md). A check whose files are absent or not
configured is skipped, so a small project gets only the checks it can use.
Exit status is 1 when any error is found (or any warning with --strict).

Errors
  links      a relative link or image points at a missing file or heading
  fences     a file has an unclosed ``` code fence
  escapes    a table row or SQL line holds a literal "\\n" instead of a line break
  naming     a file or folder under the docs folder breaks the naming rule
  scratch    a task.md / TODO.md sits in a package folder
  stale      a retired name, price, path or term (configured under `stale`) is used
  coverage   a code folder under `code_roots` is missing from the tracker's code map
  status     a feature specification has no dated status line
  plan       a feature specification is linked from none of `plan_sources`
  emoji      a document uses an emoji, a tick or cross symbol, or a coloured dot
  unreleased a change log's Unreleased section is malformed
  bugs       the bug register repeats an ID, an open bug has no severity, or a bug a change log
             records as fixed is still open
  attacks    the attack log is malformed, names a test that does not exist, or disagrees with
             the bug register
  changelog  (--changed) a package's code changed and its CHANGELOG.md did not
  policy     (--changed) a policy page changed and its "last updated" stamp file did not

Warnings
  orphans    a document under the docs folder that no other document links to
  index      a folder under the docs folder that its README.md does not mention
  pairs      (--changed) one file of a configured pair changed and the other did not
  docs       (--changed) code changed and nothing under the docs folder did
  matrix     the harden skill's test matrix names a test or attack that does not exist
  spec       (--changed) a module changed and the document the code map names for it did not
  tests      (--changed) a change log gained a line under Fixed and no test in that package changed
  attacks    (--changed) a test matching `racing_markers` changed and the attack log did not
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import attacks  # noqa: E402
import changelog  # noqa: E402


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

# Directories never walked.
PRUNE = {"node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".git", ".next", ".expo", "coverage"}

DEFAULT_STATUSES = ["Built", "Partly built", "Backend only", "Frontend only", "In progress", "Next", "Planned", "Coming soon"]
SEVERITIES = ("Critical", "High", "Medium", "Low")
BUG_ID = re.compile(r"\bBUG-\d+\b")
FOUND_BY_ATTACK = re.compile(r"Found by [^.|]*\battack", re.I)
# A path that is a test: a tests folder, a *.test.* or *.spec.* file, a test_*.py or *_test.py file.
TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|e2e)/|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)test_[^/]+\.py$|_test\.(py|go)$")

DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*\.md$")
NAMES = {
    "snake": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*\.md$"),
    "kebab": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$"),
    "lower": re.compile(r"^[a-z0-9]+([_-][a-z0-9]+)*\.md$"),
}
DIRNAME = re.compile(r"^[a-z0-9]+([_.-][a-z0-9]+)*$")

LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HTML_ANCHOR = re.compile(r"<a\s+(?:id|name)=[\"']([^\"']+)[\"']")
EXTERNAL = re.compile(r"^(https?:|mailto:|tel:|file:|data:)")


# ── configuration ────────────────────────────────────────────────────────────


def config() -> dict:
    """The [docsync] table of shipkit.toml, with defaults filled in."""
    path = ROOT / "shipkit.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8")).get("docsync", {}) if path.is_file() else {}
    docs = raw.get("docs_dir", "docs")
    return {
        "docs_dir": docs,
        "packages": raw.get("packages", ["apps/*", "packages/*", "services/*"]),
        "tracker": raw.get("tracker", f"{docs}/feature_status.md"),
        "features_dir": raw.get("features_dir", f"{docs}/features"),
        "code_roots": raw.get("code_roots", []),
        "statuses": raw.get("statuses", DEFAULT_STATUSES),
        "bug_register": raw.get("bug_register", f"{docs}/testing/bug_report.md"),
        "attack_log": raw.get("attack_log", f"{docs}/testing/attack_log.md"),
        "attack_log_start": raw.get("attack_log_start", ""),
        "racing_markers": raw.get("racing_markers", []),
        "naming": raw.get("naming", "snake"),
        "plans_dir": raw.get("plans_dir", f"{docs}/plans"),
        "plan_sources": raw.get("plan_sources", []),
        "no_plan": raw.get("no_plan", []),
        "policy_pages": raw.get("policy_pages", []),
        "policy_stamp": raw.get("policy_stamp", ""),
        "pairs": raw.get("pairs", []),
        "stale": raw.get("stale", []),
        "logs_extra": raw.get("logs", [f"{docs}/bugs_fixed_and_improvements.md"]),
        "scratch_names": raw.get("scratch_names", ["task.md", "todo.md", "tasks.md"]),
        "emoji": raw.get("emoji", True),
        "matrix": raw.get("matrix", True),
    }


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def walk(base: Path, suffixes: tuple[str, ...]):
    if not base.is_dir():
        return
    for directory, names, files in os.walk(base):
        names[:] = sorted(n for n in names if n not in PRUNE)
        for name in sorted(files):
            if name.endswith(suffixes):
                yield Path(directory) / name


def package_dirs(cfg: dict) -> list[Path]:
    """Every folder matched by the `packages` globs: each keeps its own CHANGELOG.md."""
    found: list[Path] = []
    for pattern in cfg["packages"]:
        found += [p for p in sorted(ROOT.glob(pattern)) if p.is_dir() and p.name not in PRUNE]
    return list(dict.fromkeys(found))


def log_files(cfg: dict) -> set[str]:
    """Change logs record history, so retired names may appear in them."""
    names = {"CHANGELOG.md", *cfg["logs_extra"]}
    names |= {rel(p / "CHANGELOG.md") for p in package_dirs(cfg)}
    return names


def markdown_files(cfg: dict) -> list[Path]:
    """Every document the checks cover: root README and CHANGELOG, the docs folder, each package's top-level .md."""
    found = [p for p in (ROOT / "README.md", ROOT / "CHANGELOG.md") if p.exists()]
    found += list(walk(ROOT / cfg["docs_dir"], (".md",)))
    for package in package_dirs(cfg):
        found += sorted(package.glob("*.md"))
    return list(dict.fromkeys(found))


# ── document checks ──────────────────────────────────────────────────────────


def strip_fences(text: str) -> str:
    """Text with fenced code blocks blanked, line numbers preserved."""
    out, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append("")
        else:
            out.append("" if fenced else line)
    return "\n".join(out)


def slug(heading: str) -> str:
    """GitHub's heading anchor."""
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"[`*]", "", heading).strip().lower()
    return "".join(c if c.isalnum() or c in "-_" else "-" if c == " " else "" for c in heading)


_anchor_cache: dict[Path, set[str]] = {}


def anchors(path: Path) -> set[str]:
    if path not in _anchor_cache:
        seen: dict[str, int] = {}
        found: set[str] = set()
        text = strip_fences(path.read_text(encoding="utf-8"))
        for line in text.split("\n"):
            match = HEADING.match(line)
            if match:
                base = slug(match.group(2))
                count = seen.get(base, 0)
                seen[base] = count + 1
                found.add(base if count == 0 else f"{base}-{count}")
            found.update(HTML_ANCHOR.findall(line))
        _anchor_cache[path] = found
    return _anchor_cache[path]


def links(path: Path):
    """(line number, target) for each relative link outside code fences."""
    text = strip_fences(path.read_text(encoding="utf-8"))
    for number, line in enumerate(text.split("\n"), 1):
        line = re.sub(r"`[^`]*`", "", line)  # inline code is not a link
        for match in LINK.finditer(line):
            target = match.group(1)
            if not EXTERNAL.match(target):
                yield number, target


def resolve(source: Path, target: str) -> tuple[Path, str]:
    path, _, fragment = target.partition("#")
    resolved = (source.parent / path).resolve() if path else source
    return resolved, fragment


def check_links(files: list[Path]) -> list[str]:
    problems = []
    for source in files:
        for number, target in links(source):
            resolved, fragment = resolve(source, target)
            if not resolved.exists():
                problems.append(f"{rel(source)}:{number}: missing file: {target}")
            elif fragment and resolved.is_file() and resolved.suffix == ".md":
                if fragment.lower() not in anchors(resolved):
                    problems.append(f"{rel(source)}:{number}: missing heading: {target}")
    return problems


def check_fences(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        count = sum(1 for line in path.read_text(encoding="utf-8").split("\n") if line.lstrip().startswith("```"))
        if count % 2:
            problems.append(f"{rel(path)}: {count} code fence lines; one block is not closed")
    return problems


# Emoji and pictographs, the variation selector and joiner that build them, and keycaps.
# Arrows, box-drawing lines and the down-pointing triangle are not in these ranges and stay.
EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⬀-⯿⌀-⏿️‍⃣]")


def check_emoji(files: list[Path]) -> list[str]:
    """Documents are written in words: no emoji, ticks or coloured dots."""
    problems = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            found = EMOJI.findall(line)
            if found:
                shown = " ".join(f"U+{ord(c):04X}" for c in dict.fromkeys(found) if ord(c) not in (0xFE0F, 0x200D)) or "U+FE0F"
                problems.append(f"{rel(path)}:{number}: emoji ({shown}); write the word instead (Yes, No, Done, Warning)")
    return problems


def check_escapes(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if "\\n" not in line:
                continue
            if line.startswith("|") or re.match(r"\s*CREATE (TABLE|INDEX)", line) or "```" in line:
                problems.append(f'{rel(path)}:{number}: literal "\\n" where a line break was meant')
    return problems


def check_naming(cfg: dict) -> list[str]:
    if cfg["naming"] == "any":
        return []
    docs = ROOT / cfg["docs_dir"]
    plans = ROOT / cfg["plans_dir"]
    rule = NAMES.get(cfg["naming"], NAMES["snake"])
    problems = []
    if not docs.is_dir():
        return []
    for directory, names, files in os.walk(docs):
        names[:] = [n for n in names if n not in PRUNE]
        here = Path(directory)
        for name in names:
            if not DIRNAME.match(name):
                problems.append(f"{rel(here / name)}/: folder names are lowercase words joined by - or _")
        for name in files:
            if not name.endswith(".md") or name in ("README.md", "CHANGELOG.md"):
                continue
            path = here / name
            in_plans = here == plans
            if DATED.match(name):
                if not in_plans:
                    problems.append(f"{rel(path)}: dated files belong in {cfg['plans_dir']}/")
            elif in_plans:
                if not NAMES["lower"].match(name):
                    problems.append(f"{rel(path)}: use YYYY-MM-DD-kebab-title.md in {cfg['plans_dir']}/")
            elif not rule.match(name):
                problems.append(f"{rel(path)}: use lowercase {cfg['naming']} names ({'snake_case' if cfg['naming'] == 'snake' else 'kebab-case'}.md)")
    return problems


def check_scratch(cfg: dict) -> list[str]:
    scratch = {n.lower() for n in cfg["scratch_names"]}
    return [
        f"{rel(path)}: scratch file; status belongs in {cfg['tracker']}"
        for package in package_dirs(cfg)
        for path in walk(package, (".md",))
        if path.name.lower() in scratch
    ]


def stale_rules(cfg: dict) -> list[tuple[str, re.Pattern, set[str]]]:
    logs = log_files(cfg)
    rules = []
    for item in cfg["stale"]:
        allowed = logs | set(item.get("allowed", []))
        rules.append((item.get("label", "retired term"), re.compile(item["pattern"]), allowed))
    return rules


def check_stale(cfg: dict, files: list[Path]) -> list[str]:
    rules = stale_rules(cfg)
    if not rules:
        return []
    problems = []
    for path in files:
        name = rel(path)
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for label, pattern, allowed in rules:
                if name not in allowed and pattern.search(line):
                    problems.append(f"{name}:{number}: {label}: {pattern.search(line).group(0)}")
    return problems


def code_map(cfg: dict) -> dict[str, str]:
    """Code folder -> the document the tracker's code map names for it."""
    tracker = ROOT / cfg["tracker"]
    if not tracker.exists():
        return {}
    rows = re.findall(r"^\| `([^`]+)` \| \[[^\]]*\]\(([^)#\s]+)", tracker.read_text(encoding="utf-8"), re.M)
    return {folder: rel((tracker.parent / target).resolve()) for folder, target in rows if (tracker.parent / target).exists()}


def check_coverage(cfg: dict) -> list[str]:
    """Every feature folder under `code_roots` is named in the tracker's code map."""
    roots = tuple(cfg["code_roots"])
    if not roots:
        return []
    tracker = ROOT / cfg["tracker"]
    if not tracker.exists():
        return [f"{cfg['tracker']} is missing; it holds the code map for {', '.join(roots)}"]
    mapped = set(re.findall(r"^\| `([^`]+)` \| \[", tracker.read_text(encoding="utf-8"), re.M))
    present = set()
    for base in roots:
        root = ROOT / base
        if root.is_dir():
            present |= {f"{base}/{e.name}" for e in sorted(root.iterdir()) if e.is_dir() and e.name not in PRUNE and not e.name.startswith((".", "_"))}
    problems = [f"{name}: not in the code map of {cfg['tracker']}; name the document that describes it" for name in sorted(present - mapped)]
    problems += [f"{cfg['tracker']}: the code map lists {name}, which no longer exists" for name in sorted(mapped - present) if name.startswith(roots)]
    return problems


def feature_specs(cfg: dict) -> list[Path]:
    return [p for p in walk(ROOT / cfg["features_dir"], (".md",)) if p.name != "README.md"]


def status_line(cfg: dict) -> re.Pattern:
    return re.compile(r"^> \*\*Status \(\d{4}-\d{2}-\d{2}\): (" + "|".join(map(re.escape, cfg["statuses"])) + r")\b", re.M)


def check_status_lines(cfg: dict) -> list[str]:
    pattern = status_line(cfg)
    return [
        f"{rel(path)}: no status line; add `> **Status (YYYY-MM-DD): <{' | '.join(cfg['statuses'])}>.**` under the title"
        for path in feature_specs(cfg)
        if not pattern.search(path.read_text(encoding="utf-8"))
    ]


def exempt(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or name.startswith(p.rstrip("/") + "/") for p in patterns)


def check_plans(cfg: dict) -> list[str]:
    """Every feature specification is linked from a plan source (the feature map, a pricing page, a roadmap)."""
    sources = [ROOT / s for s in cfg["plan_sources"]]
    if not sources:
        return []
    present = [s for s in sources if s.exists()]
    if not present:
        return [f"none of the plan sources exists: {', '.join(cfg['plan_sources'])}"]
    linked = {rel(resolve(s, t)[0]) for s in present for _, t in links(s) if resolve(s, t)[0].exists()}
    return [
        f"{rel(path)}: linked from none of {', '.join(cfg['plan_sources'])}; add it there (under a plan, or the queue of features waiting for one)"
        for path in feature_specs(cfg)
        if not exempt(rel(path), cfg["no_plan"]) and rel(path) not in linked
    ]


def change_logs(cfg: dict) -> dict[str, Path]:
    return changelog.logs(ROOT, cfg["packages"])


def check_unreleased(cfg: dict) -> list[str]:
    """Each change log keeps Keep a Changelog's form where new entries are written."""
    return [problem for path in change_logs(cfg).values() for problem in changelog.lint(path, rel(path))]


def bug_register(cfg: dict) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The register's rows as cells, keyed by bug ID: (open, closed)."""
    path = ROOT / cfg["bug_register"]
    found: tuple[dict[str, list[str]], dict[str, list[str]]] = ({}, {})
    if not path.exists():
        return found
    section = None
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.startswith("## "):
            section = {"open": 0, "closed": 1}.get(line[3:].strip().lower())
        elif section is not None and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if BUG_ID.fullmatch(cells[0]):
                found[section].setdefault(cells[0], []).extend(cells[1:] or [""])
    return found


def check_bugs(cfg: dict) -> list[str]:
    """One row per bug, a severity on each open one, and no fixed bug left open."""
    name = cfg["bug_register"]
    path = ROOT / name
    if not path.exists():
        return []
    problems = []
    rows = [m.group(1) for m in re.finditer(r"^\| *(BUG-\d+) *\|", path.read_text(encoding="utf-8"), re.M)]
    for bug in sorted({b for b in rows if rows.count(b) > 1}):
        problems.append(f"{name}: {bug} has {rows.count(bug)} rows; a bug has one, under Open or under Closed")
    still_open, _ = bug_register(cfg)
    for bug, cells in still_open.items():
        if cells[0] not in SEVERITIES:
            problems.append(f"{name}: {bug} has no severity; write one of {', '.join(SEVERITIES)}")
    for log in change_logs(cfg).values():
        found = changelog.entries(log.read_text(encoding="utf-8"))
        for entry in found.get("Fixed", []) + found.get("Security", []):
            for bug in BUG_ID.findall(entry):
                if bug in still_open:
                    problems.append(f"{name}: {bug} is recorded as fixed in {rel(log)} and is still under Open; move its row to Closed")
    return problems


def check_attacks(cfg: dict) -> list[str]:
    """The attack log's form and tests, and its agreement with the bug register."""
    log = cfg["attack_log"]
    problems = attacks.lint(ROOT, log)
    if not (ROOT / log).exists():
        return problems
    still_open, closed = bug_register(cfg)
    _, logged, _ = attacks.read(ROOT, log)
    named: set[str] = set()
    for attack in logged:
        result = attacks.RESULT.match(attack.result)
        if not result:
            continue
        fixed, unfixed = result.group(2), result.group(3)
        if fixed:
            named.add(fixed)
            if fixed not in closed:
                problems.append(f"{log}: {attack.id} says {fixed} is fixed, and the register has it {'under Open' if fixed in still_open else 'nowhere'}")
        if unfixed:
            named.add(unfixed)
            if unfixed not in still_open:
                problems.append(f"{log}: {attack.id} says {unfixed} is open, and the register has it {'under Closed' if unfixed in closed else 'nowhere'}")
    start = cfg["attack_log_start"]
    if start:
        for bug, cells in closed.items():
            row = " | ".join(cells)
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", row)
            if bug not in named and FOUND_BY_ATTACK.search(row) and dates and dates[0] >= start:
                problems.append(f"{cfg['bug_register']}: {bug} was found by an attack and has no row in {log}; add it with attacks.py add ... --fixed {bug}")
    return problems


# ── change-set checks ────────────────────────────────────────────────────────


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.split("\n") if line.strip()]


def changed_files(base: str | None = None, staged: bool = False) -> set[str]:
    """Paths changed in the working tree (or only staged), and since `base` when one is given."""
    changed: set[str] = set()
    if staged:
        changed.update(git_lines("diff", "--cached", "--name-only"))
    else:
        for line in git_lines("status", "--porcelain", "--untracked-files=all"):
            for part in line[3:].split(" -> "):
                changed.add(part.strip().strip('"'))
    if base:
        changed.update(git_lines("diff", "--name-only", f"{base}...HEAD"))
    return {path for path in changed if not any(piece in PRUNE for piece in path.split("/"))}


def new_fixes(log: str, base: str | None = None, staged: bool = False) -> list[str]:
    """The lines under Fixed in this change set's copy of a change log that the copy before it lacks."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout

    start = (git("merge-base", base, "HEAD").strip() if base else "") or "HEAD"
    before = changelog.entries(git("show", f"{start}:{log}")).get("Fixed", [])
    path = ROOT / log
    now = git("show", f":{log}") if staged else path.read_text(encoding="utf-8") if path.exists() else ""
    return [entry for entry in changelog.entries(now).get("Fixed", []) if entry not in before]


def check_changed(cfg: dict, base: str | None = None, staged: bool = False) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """What must change together, judged on the files this change set touches."""
    changed = changed_files(base, staged)
    errors: dict[str, list[str]] = {"changelog": [], "policy": []}
    warnings: dict[str, list[str]] = {"pairs": [], "docs": [], "spec": [], "tests": [], "attacks": []}
    docs = cfg["docs_dir"].rstrip("/") + "/"

    code_changed = False
    packages = package_dirs(cfg)
    single = not packages  # a one-package repository: the root CHANGELOG.md covers the code
    groups = [(rel(p) + "/", rel(p / "CHANGELOG.md")) for p in packages] or [("", "CHANGELOG.md")]
    for prefix, log in groups:
        code = sorted(
            p for p in changed
            if p.startswith(prefix) and not p.endswith(".md") and not p.startswith(docs)
            and not (single and (p.startswith(".") or p == "shipkit.toml"))
        )
        if not code or (single and not (ROOT / "CHANGELOG.md").exists()):
            continue
        code_changed = True
        if log not in changed:
            sample = ", ".join(code[:3]) + (" ..." if len(code) > 3 else "")
            errors["changelog"].append(f"{log}: not updated, but code changed ({sample})")
        elif new_fixes(log, base, staged) and not any(TEST_FILE.search(p) for p in code):
            warnings["tests"].append(
                f"{log}: records a fix, and no test under {prefix or 'the repository'} changed; "
                "add the test that fails without the fix, or say in the change history why none can be written"
            )

    owed: dict[str, list[str]] = defaultdict(list)
    for folder, document in sorted(code_map(cfg).items()):
        touched = any(p.startswith(f"{folder}/") and not p.endswith(".md") and not TEST_FILE.search(p) for p in changed)
        if touched and document not in changed:
            owed[document].append(folder)
    for document, folders in owed.items():
        warnings["spec"].append(f"{document}: not updated, but {', '.join(folders)} changed; confirm it still describes the behaviour")

    stamp = cfg["policy_stamp"]
    policies = sorted(p for p in changed if any(fnmatch.fnmatch(p, g) for g in cfg["policy_pages"]) and p != stamp)
    if policies and stamp and stamp not in changed:
        errors["policy"].append(f"{stamp}: update the policies' last-updated date; changed: {', '.join(policies)}")

    for pair in cfg["pairs"]:
        a, b = pair[0], pair[1]
        if (a in changed) != (b in changed):
            there, missing = (a, b) if a in changed else (b, a)
            warnings["pairs"].append(f"{there} changed and {missing} did not; confirm they still agree")

    markers = cfg["racing_markers"]
    if markers:
        racing_re = re.compile(r"\b(" + "|".join(map(re.escape, markers)) + r")\b")
        racing = sorted(
            p for p in changed
            if TEST_FILE.search(p) and (ROOT / p).is_file() and racing_re.search((ROOT / p).read_text(encoding="utf-8", errors="ignore"))
        )
        if racing and cfg["attack_log"] not in changed:
            warnings["attacks"].append(
                f"{cfg['attack_log']}: not updated, but tests that make requests race changed ({', '.join(racing[:3])}); "
                "record each attack and its result with attacks.py add"
            )

    if code_changed and (ROOT / docs).is_dir() and not any(p.startswith(docs) for p in changed):
        warnings["docs"].append(f"code changed and nothing under {docs} did; confirm no document describes the changed behaviour")
    return errors, warnings


def check_matrix(cfg: dict) -> list[str]:
    """The harden skill's test matrix lint, as warnings: a gap in testing is not a broken document."""
    if not cfg["matrix"]:
        return []
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "harden" / "scripts" / "matrix.py"
    if not script.exists():
        return []
    spec = importlib.util.spec_from_file_location("shipkit_matrix", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["shipkit_matrix"] = module  # dataclasses look their module up by name
    try:
        spec.loader.exec_module(module)
        if not module.matrix_path().exists():
            return []
        return module.lint()
    except Exception as error:  # a broken matrix must not stop every other check
        return [f"matrix.py could not run: {error}"]


def link_graph(files: list[Path]) -> dict[str, set[str]]:
    """Target document -> documents that link to it."""
    inbound: dict[str, set[str]] = defaultdict(set)
    for source in files:
        for _, target in links(source):
            resolved, _ = resolve(source, target)
            if resolved.is_dir() and (resolved / "README.md").exists():
                resolved = resolved / "README.md"
            if resolved.is_file() and resolved != source and ROOT in resolved.parents:
                inbound[rel(resolved)].add(rel(source))
    return inbound


def check_orphans(cfg: dict, files: list[Path]) -> list[str]:
    docs = cfg["docs_dir"].rstrip("/") + "/"
    index = docs + "README.md"
    inbound = link_graph(files)
    return [
        f"{rel(p)}: no document links here; add it to an index or remove it"
        for p in files
        if rel(p).startswith(docs) and rel(p) != index and not inbound.get(rel(p))
    ]


def check_index(cfg: dict) -> list[str]:
    docs = ROOT / cfg["docs_dir"]
    if not docs.is_dir() or not any(walk(docs, (".md",))):
        return []
    index = docs / "README.md"
    if not index.exists():
        return [f"{cfg['docs_dir']}/README.md is missing; it is the index of the docs folder"]
    text = index.read_text(encoding="utf-8")
    return [
        f"{cfg['docs_dir']}/{e.name}/ is not mentioned in {cfg['docs_dir']}/README.md"
        for e in sorted(docs.iterdir())
        if e.is_dir() and e.name not in PRUNE and f"{e.name}/" not in text
    ]


def print_map(cfg: dict, files: list[Path]) -> None:
    docs = cfg["docs_dir"].rstrip("/") + "/"
    inbound = link_graph(files)
    print("| Document | Linked from |")
    print("|---|---|")
    for name in sorted(n for n in inbound if n.startswith(docs)):
        print(f"| `{name}` | {', '.join(f'`{s}`' for s in sorted(inbound[name]))} |")


def run(changed: bool = False, base: str | None = None, staged: bool = False) -> tuple[dict[str, list[str]], dict[str, list[str]], int]:
    """Every check. Returns (errors, warnings, documents checked), each keyed by check name."""
    _anchor_cache.clear()
    cfg = config()
    files = markdown_files(cfg)
    errors = {
        "links": check_links(files),
        "fences": check_fences(files),
        "escapes": check_escapes(files),
        "emoji": check_emoji(files) if cfg["emoji"] else [],
        "naming": check_naming(cfg),
        "scratch": check_scratch(cfg),
        "stale": check_stale(cfg, files),
        "coverage": check_coverage(cfg),
        "status": check_status_lines(cfg),
        "plan": check_plans(cfg),
        "unreleased": check_unreleased(cfg),
        "bugs": check_bugs(cfg),
        "attacks": check_attacks(cfg),
    }
    warnings = {"orphans": check_orphans(cfg, files), "index": check_index(cfg), "matrix": check_matrix(cfg)}
    if changed:
        change_errors, change_warnings = check_changed(cfg, base, staged)
        errors.update(change_errors)
        warnings.update(change_warnings)
    return errors, warnings, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the repository's documentation.")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--map", action="store_true", help="print the inbound link map and exit")
    parser.add_argument("--changed", action="store_true", help="also check what must change together in this change set")
    parser.add_argument("--base", help="with --changed: also count commits since this ref (for example main)")
    parser.add_argument("--staged", action="store_true", help="with --changed: judge only what is staged for commit")
    args = parser.parse_args()

    cfg = config()
    files = markdown_files(cfg)
    if args.map:
        print_map(cfg, files)
        return 0

    errors, warnings, _ = run(changed=args.changed, base=args.base, staged=args.staged)
    for kind, groups in (("ERROR", errors), ("WARN", warnings)):
        for name, problems in groups.items():
            for problem in problems:
                print(f"{kind} [{name}] {problem}")
    error_count = sum(len(v) for v in errors.values())
    warning_count = sum(len(v) for v in warnings.values())
    print(f"{len(files)} documents checked: {error_count} errors, {warning_count} warnings")
    return 1 if error_count or (args.strict and warning_count) else 0


if __name__ == "__main__":
    sys.exit(main())
