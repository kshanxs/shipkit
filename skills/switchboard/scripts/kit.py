#!/usr/bin/env python3
"""Kits and the autopilot: which shipkit skills to run now, in what order, and which cannot run yet.
Standard library only (Python 3.11+).

    kit.py plan build   [--request "add invoices"]          the build kit's steps for this repository
    kit.py plan break   [--tier quick|full|launch]           the break kit (quick by default)
    kit.py plan flow    [--mode start|end]                   close the loop (end, the default) or open a session
    kit.py plan feature [--request "..."]                    build, then break (quick), then flow (end)
    kit.py auto         [--request "..."]                    what fits right now: the autopilot
    kit.py facts                                             what the plans are decided from
    kit.py members kit-break                                 the skills a kit needs (for install.sh --skills)
    --json                                                   machine-readable output (plan, auto, facts)

Every step comes out as one of:
    run       it applies now
    skip      it does not apply (the reason says why, and how to make it apply)
    blocked   it applies, but cannot run yet (the reason says what is missing)

The kits are in ../kits.toml. Everything is decided from the repository: what changed against the
default branch (and in the working tree), which stacks shipkit.toml names, which registers exist,
whether the load target in load-scenario.toml is this machine and answers. Nothing is changed and
nothing but a local TCP connect is sent anywhere.
"""

from __future__ import annotations

import fnmatch
import json
import re
import socket
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route  # noqa: E402

KITS_FILE = route.SKILL / "kits.toml"
TIERS = ["quick", "full", "launch"]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}  # the same rule as load-sim's sim.py

SCHEMA_PATHS = [
    "**/migrations/**", "**/alembic/**", "**/versions/*.py", "**/models/**", "**/models.py", "**/schema*.py",
    "**/schemas/**", "**/*.prisma", "**/drizzle/**", "**/schema.ts", "**/entities/**", "**/*.sql",
]  # fmt: skip
DOC_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}
BUILD_INTENT = re.compile(
    r"\b(add|build|implement|create|make|ship|introduce|develop|write)\b.*\b(feature|endpoint|screen|page|"
    r"api|table|model|flow|form|module|service|component|app)s?\b|\bnew (feature|endpoint|screen|page|module)\b",
    re.I,
)
LAUNCH_INTENT = re.compile(r"\b(launch|go[- ]live|release|production|ship it|ready to ship|readiness)\b", re.I)
START_INTENT = re.compile(r"\b(start(ing)? (the|a|my) (day|session)|where (did )?we (leave|left) off|what('?s| is) next)\b", re.I)
END_INTENT = re.compile(r"\b(wrap(ping)? up|close (out|the loop)|end of (the )?(day|session)|done for (the )?day)\b", re.I)


# ── the repository's state ───────────────────────────────────────────────────


@dataclass
class Facts:
    root: Path
    request: str = ""
    git: bool = False
    base: str | None = None
    ahead: int = 0
    changed: list[str] = field(default_factory=list)  # against the base, plus the working tree
    uncommitted: list[str] = field(default_factory=list)
    stacks: dict[str, str | list[str]] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    installed: set[str] = field(default_factory=set)
    routed: list[str] = field(default_factory=list)  # what the switchboard picks for the request
    load: dict = field(default_factory=dict)

    # derived
    @property
    def code_changed(self) -> list[str]:
        return [p for p in self.changed if Path(p).suffix.lower() not in DOC_SUFFIXES and not self._is_docs(p)]

    @property
    def docs_changed(self) -> list[str]:
        return [p for p in self.changed if p not in self.code_changed]

    @property
    def schema_changed(self) -> list[str]:
        return [p for p in self.code_changed if any(fnmatch.fnmatch(p, g) for g in SCHEMA_PATHS)]

    def _is_docs(self, path: str) -> bool:
        docs = str(self.config.get("docsync", {}).get("docs_dir", "docs")).rstrip("/")
        return path == docs or path.startswith(docs + "/")

    def path(self, section: str, key: str, default: str) -> Path:
        return self.root / str(self.config.get(section, {}).get(key, default))

    def touches(self, stack: str) -> list[str]:
        dirs = self.stacks.get(stack) or []
        dirs = [dirs] if isinstance(dirs, str) else dirs
        out = []
        for d in dirs:
            d = d.rstrip("/")
            out += [p for p in self.code_changed if p == d or p.startswith(d + "/") or fnmatch.fnmatch(p, d + "/**")]
        return out

    def stack_exists(self, stack: str) -> bool:
        dirs = self.stacks.get(stack) or []
        dirs = [dirs] if isinstance(dirs, str) else dirs
        return any((self.root / d).is_dir() for d in dirs if "*" not in d) or any(
            any(self.root.glob(d)) for d in dirs if "*" in d
        )


def git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def base_ref(root: Path) -> str | None:
    head = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    candidates = [head] if head else []
    candidates += ["origin/main", "origin/master", "main", "master"]
    current = git(root, "branch", "--show-current")
    for ref in candidates:
        if ref and ref != current and git(root, "rev-parse", "--verify", "--quiet", ref) is not None:
            return ref
    return None


def load_target(root: Path) -> dict:
    scenario = root / "load-scenario.toml"
    out: dict = {"scenario": scenario.exists(), "base_url": None, "local": False, "answers": False}
    if not scenario.exists():
        return out
    try:
        target = tomllib.loads(scenario.read_text()).get("target", {})
    except (tomllib.TOMLDecodeError, OSError) as e:
        out["error"] = f"load-scenario.toml does not parse: {e}"
        return out
    base = target.get("base_url", "http://localhost:8000")
    parts = urlsplit(base)
    host = parts.hostname or ""
    out["base_url"] = base
    out["local"] = host in LOCAL_HOSTS | set(target.get("allow_hosts", []))
    if out["local"]:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            with socket.create_connection((host, port), timeout=1.0):
                out["answers"] = True
        except OSError:
            out["answers"] = False
    return out


def gather(root: Path | None = None, request: str = "") -> Facts:
    root = (root or route.ROOT).resolve()
    f = Facts(root=root, request=request)
    cfg = root / "shipkit.toml"
    if cfg.exists():
        try:
            f.config = tomllib.loads(cfg.read_text())
        except tomllib.TOMLDecodeError:
            f.config = {}
    stack = f.config.get("stack", {})
    f.stacks = {
        "api": stack.get("api_dir", "apps/api"),
        "web": stack.get("web_dirs", ["apps/web"]),
        "native": stack.get("native_dir", "apps/mobile"),
    }
    f.installed = route.installed()
    if request.strip():
        f.routed = [p.skill.name for p in route.route(request, route.load())]
    f.git = git(root, "rev-parse", "--is-inside-work-tree") == "true"
    if f.git:
        status = git(root, "status", "--porcelain", "--untracked-files=all") or ""
        f.uncommitted = [line[3:].split(" -> ")[-1].strip('"') for line in status.splitlines() if line.strip()]
        f.base = base_ref(root)
        committed: list[str] = []
        if f.base:
            f.ahead = int(git(root, "rev-list", "--count", f"{f.base}..HEAD") or 0)
            committed = (git(root, "diff", "--name-only", f"{f.base}...HEAD") or "").splitlines()
        f.changed = sorted(set(committed) | set(f.uncommitted))
    f.load = load_target(root)
    return f


# ── conditions: (state, reason) for one step ─────────────────────────────────

RUN, SKIP, BLOCKED = "run", "skip", "blocked"


def _n(items: list, one: str, many: str | None = None) -> str:
    return f"{len(items)} {one if len(items) == 1 else (many or one + 's')}"


def scope(f: Facts, stack: str, skill: str) -> tuple[str, str]:
    if skill in f.routed:
        return RUN, "the request is about it"
    hits = f.touches(stack)
    if hits:
        return RUN, f"{_n(hits, 'changed file')} under {hits[0].split('/')[0]}/"
    if not f.stack_exists(stack):
        return SKIP, f"no {stack} folder ([stack] in shipkit.toml)"
    if not f.request.strip() and not f.code_changed:
        return RUN, f"the {stack} exists and nothing narrows the work yet; skip it if the feature does not touch it"
    return SKIP, f"the work does not touch the {stack}"


def cond_scope_wire(f: Facts) -> tuple[str, str]:
    api = scope(f, "api", "stack-backend")[0] == RUN
    screen = scope(f, "web", "stack-web")[0] == RUN or scope(f, "native", "stack-native")[0] == RUN
    if "wire-api" in f.routed:
        return RUN, "the request is about wiring"
    if api and screen:
        return RUN, "both an API and a screen are in scope"
    return SKIP, "not both an API and a screen in this work"


def cond_scope_seed(f: Facts) -> tuple[str, str]:
    if "seedbed" in f.routed:
        return RUN, "the request is about seed data"
    if f.schema_changed:
        return RUN, f"the schema changed ({f.schema_changed[0]})"
    if re.search(r"\b(table|column|model|schema|migration|entity)\b", f.request, re.I):
        return RUN, "the request changes the data model"
    return SKIP, "no model, schema or migration change"


def cond_code_changes(f: Facts) -> tuple[str, str]:
    if any(s in f.routed for s in ("harden", "stack-backend", "stack-web", "stack-native", "wire-api")):
        return RUN, "the request names code to prove"
    if not f.git:
        return BLOCKED, "not a git repository: nothing to compare against; name an area to harden"
    if f.code_changed:
        return RUN, f"{_n(f.code_changed, 'changed code file')} against {f.base or 'the last commit'}"
    return SKIP, f"no code changes against {f.base or 'the last commit'}; name an area to harden it"


def cond_sweep_target(f: Facts, tier: str) -> tuple[str, str]:
    if not f.git:
        return BLOCKED, "not a git repository"
    code_uncommitted = [p for p in f.uncommitted if p in f.code_changed]
    if f.ahead and f.code_changed:
        return RUN, f"{_n(range(f.ahead), 'new commit')} on this branch"
    if code_uncommitted:
        return RUN, f"{_n(code_uncommitted, 'uncommitted code file')}"
    if tier != "quick":
        return RUN, "no new commits: sweep one area of the whole branch"
    return SKIP, "no new commits or code changes to review (break full sweeps an area)"


def cond_load_ready(f: Facts) -> tuple[str, str]:
    t = f.load
    if t.get("error"):
        return BLOCKED, t["error"]
    if not t.get("scenario"):
        return BLOCKED, "no load-scenario.toml: `sim.py init` writes the generic one; point [target] at the local stack"
    if not t.get("local"):
        return BLOCKED, f"{t.get('base_url')} is not this machine (or in [target] allow_hosts): never production"
    if not t.get("answers"):
        return BLOCKED, f"nothing answers at {t.get('base_url')}: start the local stack on a scratch database"
    return RUN, f"the local stack answers at {t['base_url']}"


def cond_file(f: Facts, path: Path, what: str, how: str) -> tuple[str, str]:
    if path.exists():
        return RUN, f"{path.relative_to(f.root).as_posix()} exists"
    return SKIP, f"no {what} yet ({how})"


CONDITIONS = {
    "always": lambda f, **_: (RUN, ""),
    "handoff_file": lambda f, **_: cond_file(f, f.path("handoff", "file", "HANDOFF.md"), "HANDOFF.md", "`handoff.py init` starts one"),
    "handoff_end": lambda f, **_: (
        (RUN, "add the work log row")
        if f.path("handoff", "file", "HANDOFF.md").exists()
        else (RUN, "no HANDOFF.md: `handoff.py init` first, then log")
    ),
    "open_loops_register": lambda f, **_: cond_file(
        f, f.path("open_loops", "register", "docs/open_questions.md"), "open questions register", "open-loops starts one"
    ),
    "feature_catalog": lambda f, **_: cond_file(
        f, f.path("feature_map", "catalog", "docs/feature_catalog.md"), "feature map", "feature-map starts one"
    ),
    "docs_present": lambda f, **_: (
        (RUN, "docs or changelogs exist")
        if f.path("docsync", "docs_dir", "docs").is_dir() or any(f.root.glob("**/CHANGELOG.md"))
        else (SKIP, "no docs folder or changelog yet (docsync sets them up)")
    ),
    "parallel": lambda f, **_: (
        (RUN, "the request asks for parallel work")
        if "fanout" in f.routed
        else (SKIP, "one agent; say 'in parallel' to split the work")
    ),
    "scope_api": lambda f, **_: scope(f, "api", "stack-backend"),
    "scope_web": lambda f, **_: scope(f, "web", "stack-web"),
    "scope_native": lambda f, **_: scope(f, "native", "stack-native"),
    "scope_wire": lambda f, **_: cond_scope_wire(f),
    "scope_seed": lambda f, **_: cond_scope_seed(f),
    "code_changes": lambda f, **_: cond_code_changes(f),
    "sweep_target": lambda f, tier="quick", **_: cond_sweep_target(f, tier),
    "load_ready": lambda f, **_: cond_load_ready(f),
    "report_due": lambda f, **_: (RUN, ""),  # decided after the other steps
}


# ── plans ────────────────────────────────────────────────────────────────────


@dataclass
class Step:
    kit: str
    skill: str
    do: str
    state: str
    reason: str


def kits() -> dict:
    return tomllib.loads(KITS_FILE.read_text())


def plan(name: str, f: Facts, tier: str = "quick", mode: str = "end") -> list[Step]:
    table = kits()
    if name not in table:
        raise SystemExit(f"kit.py: no kit named {name!r} (there are: {', '.join(table)})")
    kit = table[name]
    if "kits" in kit:
        steps: list[Step] = []
        for sub in kit["kits"]:
            steps += plan(sub, f, tier="quick" if sub == "break" else tier, mode="end" if sub == "flow" else mode)
        return steps
    steps = []
    for s in kit["steps"]:
        if name == "break" and TIERS.index(s.get("tier", "quick")) > TIERS.index(tier):
            continue
        if name == "flow" and s.get("mode", "end") != mode:
            continue
        if name != "flow" and s.get("mode", "end") != "end":
            continue
        if s["skill"] not in f.installed:
            steps.append(Step(name, s["skill"], s["do"], SKIP, f"not installed (install.sh --skills {s['skill']})"))
            continue
        state, reason = CONDITIONS[s["when"]](f, tier=tier, mode=mode)
        steps.append(Step(name, s["skill"], s["do"], state, reason))
    for step in steps:
        if step.skill == "triage-report" and step.state == RUN:
            fed = [x.skill for x in steps if x.state == RUN and x.skill in ("bug-sweep", "load-sim", "perf-watch", "harden")]
            if fed:
                step.reason = "one report from " + ", ".join(fed)
            else:
                step.state, step.reason = SKIP, "nothing ran that needs a report"
    return steps


# ── the autopilot ────────────────────────────────────────────────────────────


@dataclass
class Advice:
    now: list[dict] = field(default_factory=list)  # {"run": "/break", "why": ...}
    available: list[dict] = field(default_factory=list)
    not_now: list[dict] = field(default_factory=list)


def advise(f: Facts) -> Advice:
    a = Advice()
    req = f.request.strip()
    # naming the autopilot itself means "decide": it never answers with itself
    named = [p for p in route.route(req, route.load()) if p.named and p.skill.name != "autopilot"] if req else []
    if named:
        a.now.append({"run": f"/{named[0].skill.short[0]}", "why": f"you named {named[0].skill.name}"})
    elif req and LAUNCH_INTENT.search(req):
        a.now.append({"run": "/break launch", "why": "the request is about launching: prove it, then the readiness audit"})
    elif req and START_INTENT.search(req):
        a.now.append({"run": "/flow start", "why": "a session is starting: read the handoff and the open questions"})
    elif req and END_INTENT.search(req):
        a.now.append({"run": "/flow", "why": "the session is ending: docs, feature map, questions, handoff"})
    elif req and BUILD_INTENT.search(req):
        a.now.append({"run": "/feature", "why": "new work: build it, prove it, close the loop"})
    elif f.code_changed:
        where = f"{_n(f.code_changed, 'changed code file')}" + (f", {_n(range(f.ahead), 'new commit')}" if f.ahead else "")
        a.now.append({"run": "/break", "why": f"{where} not proven yet: harden, sweep, report"})
        if f.schema_changed:
            a.now.append({"run": "/seed", "why": f"the schema changed ({f.schema_changed[0]}): seed data must follow"})
        a.now.append({"run": "/flow", "why": "then record it: docs, feature map, questions, handoff"})
    elif f.docs_changed:
        a.now.append({"run": "/flow", "why": f"{_n(f.docs_changed, 'changed doc')}: check and record them"})
    else:
        a.now.append({"run": "/flow start", "why": "nothing changed yet: read where we left off and what is next"})
        if req:
            routed = [p for p in route.route(req, route.load()) if not p.companion_of and p.skill.name != "autopilot"]
            if routed:
                a.now.append({"run": f"/{routed[0].skill.short[0]}", "why": f"the request fits {routed[0].skill.name}"})

    load = cond_load_ready(f)
    if load[0] == RUN:
        a.available.append({"run": "/break full", "why": f"{load[1]}: load-sim and perf-watch can run"})
    elif f.load.get("scenario"):
        a.not_now.append({"run": "/break full", "why": load[1]})
    else:
        a.not_now.append({"run": "/break full", "why": "no load-scenario.toml yet (`sim.py init`)"})
    if not any(x["run"].startswith("/break launch") for x in a.now):
        a.available.append({"run": "/break launch", "why": "the launch-readiness audit, whenever you want it"})
    if not f.git:
        a.not_now.append({"run": "/sweep", "why": "not a git repository: no commits to review"})
    return a


# ── output ───────────────────────────────────────────────────────────────────

ICON = {RUN: "✅ run", SKIP: "⏭ skip", BLOCKED: "⛔ blocked"}


def show_plan(name: str, steps: list[Step], tier: str, mode: str) -> str:
    label = name + (f" ({tier})" if name == "break" else f" ({mode})" if name == "flow" else "")
    lines = [f"kit: {label}", ""]
    width = max((len(s.skill) for s in steps), default=10)
    for i, s in enumerate(steps, 1):
        prefix = f"{s.kit}/" if name == "feature" else ""
        lines.append(f"{i:>2}. {ICON[s.state]:<11} {prefix}{s.skill:<{width}}  {s.do}")
        if s.reason:
            lines.append(f"{'':>16}{'':<{len(prefix)}}{'':<{width}}  └ {s.reason}")
    run = sum(s.state == RUN for s in steps)
    blocked = [s for s in steps if s.state == BLOCKED]
    lines += ["", f"{run} to run, {sum(s.state == SKIP for s in steps)} skipped, {len(blocked)} blocked"]
    return "\n".join(lines)


def show_advice(a: Advice) -> str:
    out = ["Now:"]
    out += [f"  {x['run']:<14} {x['why']}" for x in a.now]
    if a.available:
        out += ["", "Ready when you want:"] + [f"  {x['run']:<14} {x['why']}" for x in a.available]
    if a.not_now:
        out += ["", "Not now:"] + [f"  {x['run']:<14} {x['why']}" for x in a.not_now]
    return "\n".join(out)


def members(skill: str) -> list[str]:
    table = kits()
    by_skill = {v["skill"]: k for k, v in table.items()}

    def of(kit: str) -> list[str]:
        k = table[kit]
        if "kits" in k:
            return [k2["skill"] for k2 in (table[s] for s in k["kits"])] + [m for s in k["kits"] for m in of(s)]
        return [s["skill"] for s in k["steps"]]

    if skill == "autopilot":
        out = [v["skill"] for v in table.values()] + [m for k in table for m in of(k)]
    elif skill in by_skill:
        out = of(by_skill[skill])
    else:
        return []
    # and the skills those hand work to (`with` in skills.toml: harden ends in docsync)
    catalog = route.load(only_installed=False)
    i = 0
    while i < len(out):
        out += [w for w in (catalog[out[i]].with_ if out[i] in catalog else []) if w not in out]
        i += 1
    return list(dict.fromkeys(out))


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    def opt(name: str, default: str) -> str:
        if name in argv:
            i = argv.index(name)
            value = argv[i + 1] if i + 1 < len(argv) else default
            del argv[i : i + 2]
            return value
        return default

    request = opt("--request", "")
    tier = opt("--tier", "quick")
    mode = opt("--mode", "end")
    if tier not in TIERS:
        raise SystemExit(f"kit.py: --tier is one of {', '.join(TIERS)}")
    if mode not in ("start", "end"):
        raise SystemExit("kit.py: --mode is start or end")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "members":
        print("\n".join(members(argv[1] if len(argv) > 1 else "")))
        return 0
    f = gather(request=request)
    if cmd == "facts":
        data = {
            "root": str(f.root), "git": f.git, "base": f.base, "ahead": f.ahead,
            "code_changed": f.code_changed, "docs_changed": f.docs_changed, "schema_changed": f.schema_changed,
            "uncommitted": f.uncommitted, "routed": f.routed, "load": f.load, "installed": sorted(f.installed),
        }  # fmt: skip
        print(json.dumps(data, indent=2))
        return 0
    if cmd == "plan":
        name = argv[1] if len(argv) > 1 else ""
        steps = plan(name, f, tier=tier, mode=mode)
        print(json.dumps([s.__dict__ for s in steps], indent=2) if as_json else show_plan(name, steps, tier, mode))
        return 0
    if cmd == "auto":
        a = advise(f)
        print(json.dumps(a.__dict__, indent=2) if as_json else show_advice(a))
        return 0
    raise SystemExit(f"kit.py: unknown command {cmd!r}; see --help")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
