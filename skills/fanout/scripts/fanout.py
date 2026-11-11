#!/usr/bin/env python3
"""Parallel feature work in git worktrees: plan, start, test, land, clean up. Standard library only.

    fanout.py new <run> [--base main]           a run plan in .fanout/<run>/plan.json, and its integration branch
    fanout.py ids [--run <run>]                 the next free migration number, question number and bug number
    fanout.py check <run>                       the plan is safe to start: no shared paths, no reused numbers
    fanout.py hotspots                          the files every feature touches, and how each is merged
    fanout.py brief <run> <task>                the brief to hand the agent for one task
    fanout.py start <run> <task> [--path DIR]   make the task's worktree, then `join` in it
    fanout.py join <run> <task>                 inside a worktree made by anyone: take the task's branch, set it up
    fanout.py test [args]                       the full test suite, one checkout at a time on this machine
    fanout.py land <run> <task> [--full]        rebase, re-chain migrations, regenerate, check, move integration on
    fanout.py status <run>                      every task: branch, worktree, commits, landed or not
    fanout.py cleanup <run> <task>              remove a landed task's worktree, branch and services

Plans live in the main checkout's .fanout/ (add it to .gitignore), found from any worktree.
Everything project-specific comes from the [fanout] table of shipkit.toml (references/config.md).
The workflow and its rules: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SKILLS = SKILL.parent

# How each shared file is merged when two branches change it.
#   append     both sides add lines; keep both, in the file's order (alphabetical where it is)
#   union      git keeps both sides' lines itself (.gitattributes: CHANGELOG.md merge=union)
#   generated  never merged by hand: take either side, then the generator rewrites it at landing
#   serial     one task a wave may change it; anything else waits for the next wave
# These are the defaults for any repository; [fanout.hotspots] in shipkit.toml adds or overrides.
DEFAULT_HOTSPOTS: dict[str, tuple[str, str]] = {
    "CHANGELOG.md": ("union", "product-level summary"),
    "apps/*/CHANGELOG.md": ("union", ""),
    "packages/*/CHANGELOG.md": ("union", ""),
    "services/*/CHANGELOG.md": ("union", ""),
    "README.md": ("append", ""),
    "docs/README.md": ("append", ""),
    "docs/feature_status.md": ("append", "the task's own rows only"),
    "docs/feature_catalog.md": ("append", "the task's own lines; tiers are the product owner's"),
    "docs/features/README.md": ("append", ""),
    "docs/testing/bug_report.md": ("append", "reserved BUG numbers only"),
    "docs/open_questions.md": ("append", "reserved Q numbers only; the lists in other documents are generated"),
    "docs/bugs_fixed_and_improvements.md": ("append", "a log: add, never rewrite"),
    "uv.lock": ("generated", "take the integration side, then uv lock"),
    "apps/*/uv.lock": ("generated", "take the integration side, then uv lock"),
    "package-lock.json": ("generated", "take the integration side, then npm install"),
    "pnpm-lock.yaml": ("generated", "take the integration side, then pnpm install"),
    "yarn.lock": ("generated", "take the integration side, then yarn install"),
    "bun.lock": ("generated", "take the integration side, then bun install"),
    "apps/*/bun.lock": ("generated", "take the integration side, then bun install"),
    "apps/*/package-lock.json": ("generated", "take the integration side, then npm install"),
    "package.json": ("serial", "a new dependency or script"),
    "apps/*/package.json": ("serial", "a new dependency"),
    "pyproject.toml": ("serial", "a new dependency"),
    "apps/*/pyproject.toml": ("serial", "a new dependency"),
    "tsconfig.json": ("serial", ""),
    "packages/": ("serial", "shared code: its own wave"),
}
# Where an Alembic chain usually lives; the first that exists is used unless [fanout] migrations says.
MIGRATION_DIRS = ("migrations/versions", "alembic/versions", "apps/*/migrations/versions", "services/*/migrations/versions", "backend/migrations/versions")
DEFAULT_PORTS = {"API_PORT": 8000, "WEB_PORT": 5173}


def _config() -> dict:
    try:
        root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        root = Path.cwd()
    path = root / "shipkit.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def settings() -> dict:
    """The [fanout] table, with the docs paths of [docsync] and [open_loops] for the number registers."""
    cfg = _config()
    fan = cfg.get("fanout", {})
    docs = cfg.get("docsync", {}).get("docs_dir", "docs")
    hotspots = dict(DEFAULT_HOTSPOTS)
    for path, value in fan.get("hotspots", {}).items():
        hotspots[path] = (value[0], value[1] if len(value) > 1 else "") if isinstance(value, list) else (str(value), "")
    return {
        "max_parallel": int(fan.get("max_parallel", 3)),
        "prefix": fan.get("branch_prefix", "fanout"),
        "worktree_root": fan.get("worktree_root", ""),
        "hotspots": hotspots,
        "migrations": fan.get("migrations", ""),
        "questions": cfg.get("open_loops", {}).get("register", f"{docs}/open_questions.md"),
        "bugs": cfg.get("docsync", {}).get("bug_register", f"{docs}/testing/bug_report.md"),
        "ports": fan.get("ports", DEFAULT_PORTS),
        "redis": bool(fan.get("redis", False)),
        "redis_env_file": fan.get("redis_env_file", ""),
        "install": fan.get("install"),
        "regenerate": fan.get("regenerate", []),
        "checks": fan.get("checks", []),
        "path_checks": fan.get("path_checks", {}),
        "test": fan.get("test", ""),
        "copy_env": bool(fan.get("copy_env", True)),
    }


class Stop(Exception):
    """A step that cannot go on; the message says what to do."""


# ── git and paths ────────────────────────────────────────────────────────────


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    if not quiet:
        print("$ " + " ".join(cmd), file=sys.stderr)
    done = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and done.returncode != 0:
        raise Stop(f"{' '.join(cmd)} failed:\n{done.stdout}{done.stderr}")
    return done


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    return run(["git", *args], cwd=cwd, check=check, quiet=True).stdout.strip()


def toplevel(cwd: Path | None = None) -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd))


def main_checkout() -> Path:
    """The checkout that owns .git (plans live there), from any worktree."""
    return Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def branch_exists(name: str) -> bool:
    return run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], check=False, quiet=True).returncode == 0


def is_ancestor(a: str, b: str) -> bool:
    return run(["git", "merge-base", "--is-ancestor", a, b], check=False, quiet=True).returncode == 0


def worktrees() -> dict[str, Path]:
    """Branch name -> the worktree it is checked out in."""
    found: dict[str, Path] = {}
    path: Path | None = None
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1])
        elif line.startswith("branch refs/heads/") and path:
            found[line.removeprefix("branch refs/heads/")] = path
    return found


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def migrations_dir(root: Path) -> str | None:
    """The Alembic versions folder, relative to the root, or None when the project has none."""
    configured = settings()["migrations"]
    if configured:
        return configured
    for pattern in MIGRATION_DIRS:
        found = sorted(p for p in root.glob(pattern) if p.is_dir())
        if found:
            return found[0].relative_to(root).as_posix()
    return None


# ── the plan ─────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    path: Path
    data: dict

    @property
    def run(self) -> str:
        return self.data["run"]

    @property
    def integration(self) -> str:
        return self.data["integration"]

    @property
    def tasks(self) -> list[dict]:
        return self.data["tasks"]

    @property
    def prefix(self) -> str:
        return self.data.get("prefix", settings()["prefix"])

    def task(self, task_id: str) -> dict:
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        raise Stop(f"No task {task_id!r} in {self.path}; tasks: {', '.join(t['id'] for t in self.tasks)}")

    def branch(self, task: dict) -> str:
        return f"{self.prefix}/{self.run}/{task['id']}"

    def start_point(self, task: dict) -> str:
        """A stacked task starts from the task it builds on; any other from the integration branch."""
        under = task.get("stack_on")
        return self.branch(self.task(under)) if under else self.integration

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")


def plans_dir() -> Path:
    return main_checkout() / ".fanout"


def load(run_name: str) -> Plan:
    path = plans_dir() / run_name / "plan.json"
    if not path.exists():
        raise Stop(f"No plan at {path}. Make one: fanout.py new {run_name}")
    return Plan(path, json.loads(path.read_text()))


def state_path(run_name: str) -> Path:
    return plans_dir() / run_name / "state.json"


def load_state(run_name: str) -> dict:
    path = state_path(run_name)
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(run_name: str, state: dict) -> None:
    state_path(run_name).write_text(json.dumps(state, indent=2) + "\n")


# ── numbers that must never repeat ───────────────────────────────────────────


def refs_outside(run_name: str | None) -> list[str]:
    """Local and remote branches, leaving out the run's own (they hold its reserved numbers)."""
    refs = git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").splitlines()
    skip = f"refs/heads/{settings()['prefix']}/{run_name}/" if run_name else None
    return [r for r in refs if not (skip and r.startswith(skip)) and not r.endswith("/HEAD")]


def used_numbers(run_name: str | None = None) -> dict[str, int]:
    """The highest migration, question and bug number on any branch, and in the working tree."""
    top = {"migration": 0, "question": 0, "bug": 0}
    conf = settings()

    def note(kind: str, text: str, pattern: str) -> None:
        for match in re.findall(pattern, text):
            top[kind] = max(top[kind], int(match))

    root = toplevel()
    versions = migrations_dir(root)
    questions, bugs = conf["questions"], conf["bugs"]
    if versions:
        note("migration", "\n".join(p.name for p in (root / versions).glob("*.py")), r"(?m)^(\d{3})_")
    note("question", (root / questions).read_text() if (root / questions).exists() else "", r"### Q-(\d+)")
    note("bug", (root / bugs).read_text() if (root / bugs).exists() else "", r"BUG-(\d+)")
    for ref in refs_outside(run_name):
        if versions:
            note("migration", git("ls-tree", "--name-only", f"{ref}:{versions}", check=False), r"(?m)^(\d{3})_")
        note("question", git("show", f"{ref}:{questions}", check=False), r"### Q-(\d+)")
        note("bug", git("show", f"{ref}:{bugs}", check=False), r"BUG-(\d+)")
    return top


def reserved_numbers(skip_run: str | None = None) -> dict[str, set[int]]:
    """Numbers held by every plan (but skip_run), landed or not."""
    held: dict[str, set[int]] = {"migration": set(), "question": set(), "bug": set()}
    for path in plans_dir().glob("*/plan.json"):
        data = json.loads(path.read_text())
        if data.get("run") == skip_run:
            continue
        for task in data.get("tasks", []):
            held["migration"] |= {int(m[:3]) for m in task.get("ids", {}).get("migrations", [])}
            held["question"] |= {int(q[2:]) for q in task.get("ids", {}).get("questions", [])}
            held["bug"] |= {int(b[4:]) for b in task.get("ids", {}).get("bugs", [])}
    return held


def next_free(run_name: str | None = None) -> dict[str, int]:
    used = used_numbers(run_name)
    held = reserved_numbers()
    return {kind: max([used[kind], *held[kind]]) + 1 for kind in used}


# ── checking a plan ──────────────────────────────────────────────────────────


def overlaps(a: str, b: str) -> bool:
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _matches(path: str, spot: str) -> bool:
    if any(ch in spot for ch in "*?["):
        import fnmatch

        return fnmatch.fnmatch(path.rstrip("/"), spot.rstrip("/")) or fnmatch.fnmatch(path, spot.rstrip("/") + "/*")
    return overlaps(path, spot)


def hotspot_of(path: str) -> str | None:
    for spot in settings()["hotspots"]:
        if _matches(path, spot):
            return spot
    return None


def hotspot_kind(path: str) -> tuple[str, str] | None:
    spot = hotspot_of(path)
    return settings()["hotspots"][spot] if spot else None


def stacked(plan: Plan, a: dict, b: dict) -> bool:
    """True when one task is built on the other (directly or further down)."""

    def chain(task: dict) -> set[str]:
        seen: set[str] = set()
        while task.get("stack_on") and task["stack_on"] not in seen:
            seen.add(task["stack_on"])
            task = plan.task(task["stack_on"])
        return seen

    return a["id"] in chain(b) or b["id"] in chain(a)


def check_plan(plan: Plan, landed: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Errors and warnings. Tasks already landed are not checked against the repository's numbers."""
    errors: list[str] = []
    warnings: list[str] = []
    landed = landed or set()
    limit = plan.data.get("max_parallel", settings()["max_parallel"])
    ids = [t["id"] for t in plan.tasks]
    for task_id in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"task id {task_id} is used twice")
    for task in plan.tasks:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", task["id"]):
            errors.append(f"{task['id']}: a task id is lowercase letters, digits and hyphens")
        under = task.get("stack_on")
        if under and under not in ids:
            errors.append(f"{task['id']}: stack_on names no task ({under})")
        elif under and plan.task(under).get("wave", 1) > task.get("wave", 1):
            errors.append(f"{task['id']}: stacked on {under}, which is in a later wave")
        if not task.get("owns"):
            errors.append(f"{task['id']}: owns no paths")
        for path in task.get("owns", []):
            kind = hotspot_kind(path)
            if kind and kind[0] != "serial":
                errors.append(f"{task['id']}: {path} is a shared file ({kind[0]}); list it under hotspots, not owns")
        for path in task.get("hotspots", []):
            if not hotspot_of(path):
                warnings.append(f"{task['id']}: {path} is not a known hot spot; if only this task changes it, list it under owns")

    def serial_paths(task: dict) -> list[str]:
        return [h for h in task.get("hotspots", []) if (hotspot_kind(h) or ("",))[0] == "serial"]

    waves: dict[int, list[dict]] = {}
    for task in plan.tasks:
        waves.setdefault(task.get("wave", 1), []).append(task)
    for wave, tasks in sorted(waves.items()):
        side_by_side = [t for t in tasks if not t.get("stack_on")]
        if len(side_by_side) > limit:
            warnings.append(f"wave {wave}: {len(side_by_side)} tasks at once with max_parallel {limit}")
        for i, a in enumerate(tasks):
            for b in tasks[i + 1 :]:
                if stacked(plan, a, b):
                    continue
                for pa in a.get("owns", []) + serial_paths(a):
                    for pb in b.get("owns", []) + serial_paths(b):
                        if overlaps(pa, pb):
                            errors.append(f"wave {wave}: {a['id']} and {b['id']} both change {pa if len(pa) <= len(pb) else pb}; stack one on the other or move it to another wave")
        serial_tasks = [t for t in tasks if any((hotspot_kind(p) or ("",))[0] == "serial" for p in t.get("owns", []) + t.get("hotspots", []))]
        if serial_tasks and len(tasks) > 1 and any(not stacked(plan, s, o) for s in serial_tasks for o in tasks if o is not s):
            names = ", ".join(t["id"] for t in serial_tasks)
            warnings.append(f"wave {wave}: {names} changes foundation files (shared packages, dependencies, config); the other tasks build on code that is moving")

    used = used_numbers(plan.run)
    held = reserved_numbers(skip_run=plan.run)
    seen: dict[str, str] = {}
    shapes = {"migrations": (r"\d{3}_[a-z0-9_]+", "migration"), "questions": (r"Q-\d{3}", "question"), "bugs": (r"BUG-\d{3}", "bug")}
    for task in plan.tasks:
        for key, (shape, kind) in shapes.items():
            for value in task.get("ids", {}).get(key, []):
                if not re.fullmatch(shape, value):
                    errors.append(f"{task['id']}: {value} is not a {kind} id ({shape})")
                    continue
                number = int(re.search(r"\d+", value).group())
                tag = f"{kind} {number:03d}"
                if tag in seen:
                    errors.append(f"{task['id']}: {tag} is also reserved by {seen[tag]}")
                seen[tag] = task["id"]
                if task["id"] not in landed and number <= used[kind]:
                    errors.append(f"{task['id']}: {tag} is already used on a branch (highest is {used[kind]:03d}); run fanout.py ids")
                if number in held[kind]:
                    errors.append(f"{task['id']}: {tag} is reserved by another run's plan")
    return errors, warnings


# ── setting a worktree up ────────────────────────────────────────────────────


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def taken_slots() -> set[int]:
    slots: set[int] = set()
    for path in plans_dir().glob("*/state.json"):
        for entry in json.loads(path.read_text()).values():
            if isinstance(entry, dict) and entry.get("slot"):
                slots.add(entry["slot"])
    return slots


def slot_ports(slot: int) -> dict[str, int]:
    return {name: int(base) + slot for name, base in settings()["ports"].items()}


def pick_slot(already: int | None) -> int:
    if already:
        return already
    taken = taken_slots()
    for slot in range(1, 40):
        ports = [*slot_ports(slot).values(), 6380 + slot]
        if slot not in taken and all(port_free(p) for p in ports):
            return slot
    raise Stop("No free slot: every port from the bases in [fanout] ports + 1..39 is in use")


def docker() -> list[str] | None:
    for cmd in (["docker"], ["sudo", "-n", "docker"]):
        if shutil.which(cmd[0]) and run([*cmd, "info"], check=False, quiet=True).returncode == 0:
            return cmd
    return None


def start_redis(name: str, port: int) -> bool:
    cmd = docker()
    if not cmd:
        return False
    run([*cmd, "rm", "-f", name], check=False, quiet=True)
    return run([*cmd, "run", "-d", "--rm", "--name", name, "-p", f"{port}:6379", "redis:7-alpine"], check=False).returncode == 0


def set_env_line(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


LOCKFILES = (
    ("uv.lock", ["uv", "sync", "--frozen", "--quiet"]),
    ("pnpm-lock.yaml", ["pnpm", "install", "--frozen-lockfile", "--silent"]),
    ("bun.lock", ["bun", "install", "--frozen-lockfile", "--silent"]),
    ("bun.lockb", ["bun", "install", "--frozen-lockfile", "--silent"]),
    ("yarn.lock", ["yarn", "install", "--frozen-lockfile", "--silent"]),
    ("package-lock.json", ["npm", "ci", "--silent"]),
)


def install_commands(root: Path) -> list[tuple[list[str], Path]]:
    """[fanout] install when given (each run from the worktree root), else one install per lock file found:
    at the root, then in each package folder that has its own (a JS workspace installs once, at the root)."""
    configured = settings()["install"]
    if configured is not None:
        return [(["sh", "-c", command], root) for command in configured]
    found: list[tuple[list[str], Path]] = []
    js_at_root = any((root / name).exists() for name, cmd in LOCKFILES if cmd[0] != "uv")
    for folder in [root, *sorted(p.parent for pattern in ("apps/*/", "packages/*/", "services/*/") for p in root.glob(pattern + "*") if p.is_file())]:
        for name, cmd in LOCKFILES:
            if (folder / name).exists() and shutil.which(cmd[0]) and not (folder != root and cmd[0] != "uv" and js_at_root):
                if (cmd, folder) not in found:
                    found.append((cmd, folder))
                break
    return found


def setup(plan: Plan, task: dict, root: Path, install: bool = True) -> dict:
    """Ignored env files from the main checkout, dependencies, ports (and, if asked, a Redis) of the worktree's own."""
    conf = settings()
    state = load_state(plan.run)
    entry = state.get(task["id"], {})
    slot = pick_slot(entry.get("slot"))
    main = main_checkout()

    # .env files are ignored by git, so a new worktree has none. Copy, never link.
    if conf["copy_env"]:
        for env in main.glob("**/.env*"):
            rel = env.relative_to(main)
            if "node_modules" in rel.parts or ".fanout" in rel.parts or env.name.endswith(".example") or not env.is_file():
                continue
            if run(["git", "check-ignore", "-q", str(rel)], cwd=main, check=False, quiet=True).returncode != 0:
                continue
            target = root / rel
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(env, target)

    redis_name = None
    redis_port = 6380 + slot
    if conf["redis"]:
        redis_name = f"fanout-{slug(plan.run)}-{task['id']}"
        if start_redis(redis_name, redis_port):
            if conf["redis_env_file"]:
                set_env_line(root / conf["redis_env_file"], "REDIS_URL", f"redis://localhost:{redis_port}/0")
        else:
            redis_name = None
            print("No Docker: this worktree shares Redis with the others. Run Redis-backed tests in one worktree at a time.", file=sys.stderr)

    ports = slot_ports(slot)
    lines = [f"FANOUT_RUN={plan.run}", f"FANOUT_TASK={task['id']}", f"FANOUT_SLOT={slot}"]
    lines += [f"{k}={v}" for k, v in ports.items()]
    if redis_name:
        lines.append(f"REDIS_URL=redis://localhost:{redis_port}/0")
    (root / ".fanout-env").write_text("\n".join(lines) + "\n")
    exclude = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")) / "info" / "exclude"
    if ".fanout-env" not in (exclude.read_text() if exclude.exists() else ""):
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a") as handle:
            handle.write("\n.fanout-env\n.fanout/\n")

    if install:
        # Each worktree gets its own environment from the tools' shared caches: a linked .venv or
        # node_modules holds absolute paths to the main checkout and would run its code instead.
        for cmd, cwd in install_commands(root):
            run(cmd, cwd=cwd)

    entry.update({"slot": slot, "worktree": str(root), "branch": plan.branch(task), "redis": redis_name, **ports})
    state[task["id"]] = entry
    save_state(plan.run, state)
    return entry


# ── migrations ───────────────────────────────────────────────────────────────

REVISION = re.compile(r'(?m)^revision(?::[^=]*)?=\s*["\']([^"\']+)["\']')
DOWN = re.compile(r'(?m)^(down_revision(?::[^=]*)?=\s*)(None|["\']([^"\']+)["\'])')


def migration_graph(root: Path) -> dict[str, tuple[str | None, Path]]:
    graph: dict[str, tuple[str | None, Path]] = {}
    versions = migrations_dir(root)
    if not versions:
        return graph
    for path in sorted((root / versions).glob("*.py")):
        text = path.read_text()
        rev, down = REVISION.search(text), DOWN.search(text)
        if rev and down:
            graph[rev.group(1)] = (down.group(3), path)
    return graph


def heads(graph: dict[str, tuple[str | None, Path]]) -> list[str]:
    parents = {down for down, _ in graph.values() if down}
    return sorted(rev for rev in graph if rev not in parents)


def rechain(root: Path, base_ref: str) -> list[str]:
    """Two heads after a rebase: put this branch's first new migration after the integration's head."""
    graph = migration_graph(root)
    tips = heads(graph)
    if len(tips) <= 1:
        return []
    versions = migrations_dir(root)
    known = set(git("ls-tree", "--name-only", f"{base_ref}:{versions}", cwd=root, check=False).splitlines())
    ours = {rev for rev, (_, path) in graph.items() if path.name not in known}
    theirs = [t for t in tips if t not in ours]
    if len(theirs) != 1 or len(tips) != 2:
        raise Stop(f"Migration heads {tips}: more than one branch to join. Chain them by hand, then land again.")
    first = [rev for rev in ours if graph[rev][0] not in ours]
    if len(first) != 1:
        raise Stop(f"This branch's migrations {sorted(ours)} do not form one chain. Fix them, then land again.")
    rev = first[0]
    old_down, path = graph[rev]
    text = path.read_text()
    text = DOWN.sub(lambda m: f'{m.group(1)}"{theirs[0]}"', text, count=1)
    if old_down:
        text = re.sub(rf"(?m)^(Revises:\s*){re.escape(old_down)}\s*$", rf"\g<1>{theirs[0]}", text, count=1)
    path.write_text(text)
    return [f"{path.name}: down_revision {old_down} -> {theirs[0]}"]


# ── commands ─────────────────────────────────────────────────────────────────


def cmd_new(args: argparse.Namespace) -> int:
    run_name = slug(args.run)
    folder = plans_dir() / run_name
    if (folder / "plan.json").exists():
        raise Stop(f"{folder / 'plan.json'} exists")
    folder.mkdir(parents=True)
    conf = settings()
    base = args.base or git("rev-parse", "--abbrev-ref", "HEAD")
    integration = f"{conf['prefix']}/{run_name}/integration"
    if not branch_exists(integration):
        git("branch", integration, base)
    free = next_free()
    plan = Plan(
        folder / "plan.json",
        {
            "run": run_name,
            "base": base,
            "integration": integration,
            "prefix": conf["prefix"],
            "max_parallel": conf["max_parallel"],
            "tasks": [
                {
                    "id": "example-task",
                    "title": "What this task builds, in one line",
                    "goal": "What is true when it is done, and how that is checked",
                    "wave": 1,
                    "stack_on": None,
                    "owns": ["apps/api/app/example/", "apps/web/src/features/example/", "docs/features/example.md"],
                    "hotspots": ["apps/api/CHANGELOG.md", "docs/feature_status.md"],
                    "ids": {"migrations": [f"{free['migration']:03d}_example"] if migrations_dir(toplevel()) else [], "questions": [], "bugs": []},
                    "skills": ["stack-backend", "stack-web", "docsync"],
                    "checks": ["uv run pytest tests/test_example.py -q"],
                }
            ],
        },
    )
    plan.save()
    print(f"Plan: {plan.path}\nIntegration branch: {integration} (from {base})\nNext free: {free}")
    return 0


def cmd_ids(args: argparse.Namespace) -> int:
    used = used_numbers(args.run)
    free = next_free(args.run)
    for kind in ("migration", "question", "bug"):
        label = {"migration": "migration", "question": "Q", "bug": "BUG"}[kind]
        print(f"{label:9} highest used {used[kind]:03d}, next free {free[kind]:03d}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    plan = load(args.run)
    landed = {t["id"] for t in plan.tasks if branch_exists(plan.branch(t)) and is_ancestor(plan.branch(t), plan.integration)}
    errors, warnings = check_plan(plan, landed)
    for line in warnings:
        print(f"warning: {line}")
    for line in errors:
        print(f"error: {line}")
    if not errors:
        print(f"{plan.run}: {len(plan.tasks)} tasks, safe to start" + (f" ({len(warnings)} warnings)" if warnings else ""))
    return 1 if errors else 0


def cmd_hotspots(args: argparse.Namespace) -> int:
    spots = settings()["hotspots"]
    for kind in ("union", "append", "generated", "serial"):
        print(f"\n{kind}")
        for path, (k, note) in spots.items():
            if k == kind:
                print(f"  {path}" + (f"  ({note})" if note else ""))
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    plan = load(args.run)
    task = plan.task(args.task)
    template = (SKILL / "references" / "brief_template.md").read_text()

    def bullets(items: list[str], empty: str = "none") -> str:
        return "\n".join(f"- `{i}`" for i in items) if items else f"- {empty}"

    def described(path: str) -> str:
        kind = hotspot_kind(path)
        return f"{path} ({kind[0]}{', ' + kind[1] if kind[1] else ''})" if kind else path

    ids = task.get("ids", {})
    docsync = SKILLS / "docsync" / "scripts" / "check_docs.py"
    values = {
        "run": plan.run,
        "task": task["id"],
        "title": task.get("title", ""),
        "goal": task.get("goal", ""),
        "branch": plan.branch(task),
        "start_point": plan.start_point(task),
        "script": f"python3 {Path(__file__).resolve()}",
        "owns": bullets(task.get("owns", [])),
        "hotspots": bullets([described(p) for p in task.get("hotspots", [])]),
        "migrations": ", ".join(ids.get("migrations", [])) or "none (ask the orchestrator if you need one)",
        "questions": ", ".join(ids.get("questions", [])) or "none (ask the orchestrator for a number)",
        "bugs": ", ".join(ids.get("bugs", [])) or "none",
        "skills": ", ".join(task.get("skills", [])) or "docsync",
        "checks": bullets(task.get("checks", []), "the checks of the stack skill for what you changed"),
        "docs_check": f"- `python3 {docsync} --changed --base {plan.start_point(task)}`" if docsync.exists() else "",
        "notes": task.get("notes", "") or "none",
    }
    print(template.format_map(values))
    return 0


def join(plan: Plan, task: dict, root: Path, install: bool) -> dict:
    branch = plan.branch(task)
    current = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    if current != branch:
        if git("status", "--porcelain", "--untracked-files=no", cwd=root):
            raise Stop(f"{root} has uncommitted changes; commit or stash them before taking {branch}")
        if branch_exists(branch):
            git("switch", branch, cwd=root)
        else:
            start = plan.start_point(task)
            if not branch_exists(start):
                raise Stop(f"{start} does not exist yet; land or start the task it builds on first")
            git("switch", "-c", branch, start, cwd=root)
    return setup(plan, task, root, install)


def cmd_start(args: argparse.Namespace) -> int:
    plan = load(args.run)
    task = plan.task(args.task)
    branch = plan.branch(task)
    where = worktrees()
    if branch in where:
        root = where[branch]
    else:
        base = settings()["worktree_root"]
        parent = Path(base).expanduser() if base else main_checkout().parent / f"{main_checkout().name}-wt"
        root = Path(args.path) if args.path else parent / f"{plan.run}-{task['id']}"
        root.parent.mkdir(parents=True, exist_ok=True)
        if branch_exists(branch):
            git("worktree", "add", str(root), branch)
        else:
            git("worktree", "add", "-b", branch, str(root), plan.start_point(task))
    entry = join(plan, task, root, install=not args.no_install)
    print(json.dumps(entry, indent=2))
    return 0


def cmd_join(args: argparse.Namespace) -> int:
    plan = load(args.run)
    root = toplevel()
    if root == main_checkout():
        raise Stop("This is the main checkout. Join from inside the task's worktree, or use fanout.py start.")
    entry = join(plan, plan.task(args.task), root, install=not args.no_install)
    print(json.dumps(entry, indent=2))
    return 0


def test_command(root: Path) -> str:
    configured = settings()["test"]
    if configured:
        return configured
    if (root / "pyproject.toml").exists():
        return "uv run pytest -q" if shutil.which("uv") else "python3 -m pytest -q"
    if (root / "package.json").exists():
        return "npm test --silent"
    raise Stop("No test command: set [fanout] test in shipkit.toml")


def cmd_test(args: argparse.Namespace) -> int:
    """The full suite, one checkout at a time: a lock per repository, so worktrees take turns."""
    root = toplevel()
    key = hashlib.sha1(str(main_checkout()).encode()).hexdigest()[:12]
    lock_path = Path(tempfile.gettempdir()) / f"shipkit-fanout-{key}.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another checkout is running the full suite; waiting for it.", file=sys.stderr)
            fcntl.flock(lock, fcntl.LOCK_EX)
        command = test_command(root) + "".join(f" {a}" for a in args.test_args)
        print(f"$ {command}", file=sys.stderr)
        return subprocess.call(["sh", "-c", command], cwd=root)


def changed_files(base: str, head: str, cwd: Path) -> list[str]:
    return git("diff", "--name-only", f"{base}...{head}", cwd=cwd).splitlines()


def commit_if_changed(root: Path, message: str) -> bool:
    if not git("status", "--porcelain", cwd=root):
        return False
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", message, cwd=root)
    return True


def regenerate(root: Path) -> None:
    """Rewrite every generated section from the code on this branch: shipkit's own writers, then [fanout] regenerate."""
    for script in (SKILLS / "open-loops" / "scripts" / "open_loops.py", SKILLS / "feature-map" / "scripts" / "feature_map.py"):
        if script.exists():
            run([sys.executable, str(script), "--write"], cwd=root, check=False)
    for command in settings()["regenerate"]:
        run(["sh", "-c", command], cwd=root, check=False)


def land_checks(root: Path, changed: list[str], integration: str, task: dict) -> list[tuple[list[str], Path]]:
    """The checks a landing runs: the documentation contract, [fanout] checks and path_checks, and the task's own."""
    conf = settings()
    checks: list[tuple[list[str], Path]] = []
    docsync = SKILLS / "docsync" / "scripts" / "check_docs.py"
    if docsync.exists():
        checks.append(([sys.executable, str(docsync), "--changed", "--base", integration], root))
    for command in conf["checks"]:
        checks.append((["sh", "-c", command], root))
    for prefix, commands in conf["path_checks"].items():
        if any(p.startswith(prefix) for p in changed):
            checks += [(["sh", "-c", command], root) for command in commands]
    for command in task.get("checks", []):
        checks.append((["sh", "-c", command], root))
    return checks


def cmd_land(args: argparse.Namespace) -> int:
    plan = load(args.run)
    task = plan.task(args.task)
    branch = plan.branch(task)
    integration = plan.integration
    if not branch_exists(branch):
        raise Stop(f"{branch} does not exist")
    if is_ancestor(branch, integration):
        print(f"{task['id']} has already landed on {integration}")
        return 0
    under = task.get("stack_on")
    if under and not is_ancestor(plan.branch(plan.task(under)), integration):
        raise Stop(f"{task['id']} is stacked on {under}; land {under} first")

    where = worktrees()
    if integration in where:
        raise Stop(f"{integration} is checked out at {where[integration]}; switch that checkout away so landing can move it")
    root = where.get(branch)
    temporary = root is None
    if temporary:
        root = plans_dir() / plan.run / "landing" / task["id"]
        git("worktree", "add", str(root), branch)
    if git("status", "--porcelain", "--untracked-files=no", cwd=root):
        raise Stop(f"{root} has uncommitted changes; the agent commits its work before it is landed")

    print(f"── Landing {task['id']} ({branch}) on {integration}")
    target = git("rev-parse", integration)

    # 1. Rebase onto the integration branch. Change logs merge themselves (.gitattributes).
    done = run(["git", "rebase", integration], cwd=root, check=False)
    if done.returncode != 0:
        conflicted = git("diff", "--name-only", "--diff-filter=U", cwd=root).splitlines()
        lines = [f"Rebase stopped in {root} on: {', '.join(conflicted) or 'see git status'}"]
        for path in conflicted:
            how = hotspot_kind(path) or ("owned", "two tasks changed the same file: the plan missed an overlap")
            lines.append(f"  {path}: {how[0]}" + (f" ({how[1]})" if how[1] else ""))
        lines.append("Resolve each (append: keep both sides; generated: take either side), git add, git rebase --continue, then land again.")
        raise Stop("\n".join(lines))

    # 2. One chain of migrations.
    fixes = rechain(root, integration)
    if fixes:
        print("Re-chained: " + "; ".join(fixes))
        commit_if_changed(root, f"fix(db): chain {task['id']}'s migration after the integration branch's head")
    tips = heads(migration_graph(root))
    if len(tips) > 1:
        raise Stop(f"Migration heads after landing: {tips}")

    # 3. Generated sections, rewritten from the merged code.
    regenerate(root)
    if commit_if_changed(root, f"docs: regenerate generated sections after {task['id']}"):
        print("Committed the regenerated sections")

    # 4. Checks on what this task changes against the integration branch.
    changed = changed_files(integration, "HEAD", root)
    for cmd, cwd in land_checks(root, changed, integration, task):
        done = run(cmd, cwd=cwd, check=False)
        if done.returncode != 0:
            raise Stop(f"Check failed in {cwd}: {' '.join(cmd)}\n{done.stdout[-4000:]}{done.stderr[-2000:]}\nFix it on {branch}, commit, and land again.")
    if args.full and subprocess.call([sys.executable, __file__, "test"], cwd=root) != 0:
        raise Stop(f"The full suite failed on {branch}. Fix it, commit, and land again.")

    # 5. Move the integration branch on, only if nobody moved it meanwhile.
    head = git("rev-parse", "HEAD", cwd=root)
    if not is_ancestor(integration, head):
        raise Stop(f"{integration} moved while landing; land {task['id']} again")
    git("update-ref", f"refs/heads/{integration}", head, target)
    state = load_state(plan.run)
    state.setdefault(task["id"], {})["landed"] = head
    save_state(plan.run, state)
    if temporary:
        git("worktree", "remove", "--force", str(root))
    print(f"Landed {task['id']}: {integration} is now {head[:10]}")
    waiting = [t["id"] for t in plan.tasks if t["id"] != task["id"] and not (branch_exists(plan.branch(t)) and is_ancestor(plan.branch(t), integration))]
    if waiting:
        print("Not landed yet: " + ", ".join(waiting) + ". Each rebases onto the new tip when it lands.")
    else:
        print(f"Every task has landed. Ask before bringing {integration} into {plan.data['base']}.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    plan = load(args.run)
    state = load_state(plan.run)
    where = worktrees()
    print(f"{plan.run}: integration {plan.integration} at {git('rev-parse', '--short', plan.integration, check=False) or '-'}, base {plan.data['base']}")
    for task in sorted(plan.tasks, key=lambda t: (t.get("wave", 1), t["id"])):
        branch = plan.branch(task)
        if not branch_exists(branch):
            mark, ahead = "not started", ""
        else:
            ahead = git("rev-list", "--count", f"{plan.integration}..{branch}")
            mark = "landed" if is_ancestor(branch, plan.integration) else "working"
        tree = where.get(branch)
        entry = state.get(task["id"], {})
        ports = "".join(f" {k}:{entry[k]}" for k in settings()["ports"] if entry.get(k))
        stacked_on = f" on {task['stack_on']}" if task.get("stack_on") else ""
        print(f"  wave {task.get('wave', 1)} {task['id']:24} {mark:12} {ahead and ahead + ' commits':12}{stacked_on}{ports}  {tree or ''}")
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    plan = load(args.run)
    task = plan.task(args.task)
    branch = plan.branch(task)
    if branch_exists(branch) and not is_ancestor(branch, plan.integration) and not args.force:
        raise Stop(f"{branch} has not landed; --force removes it with its work")
    state = load_state(plan.run)
    entry = state.get(task["id"], {})
    tree = worktrees().get(branch)
    if tree:
        git("worktree", "remove", *(["--force"] if args.force else []), str(tree))
    if entry.get("redis") and (cmd := docker()):
        run([*cmd, "rm", "-f", entry["redis"]], check=False)
    if branch_exists(branch):
        git("branch", "-D", branch)  # landed was checked above, against the integration branch
    for key in ("slot", "worktree", "redis"):
        entry.pop(key, None)
    state[task["id"]] = entry
    save_state(plan.run, state)
    print(f"Cleaned up {task['id']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new")
    p.add_argument("run")
    p.add_argument("--base")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("ids")
    p.add_argument("--run")
    p.set_defaults(func=cmd_ids)
    for name, func in (("check", cmd_check), ("status", cmd_status)):
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(func=func)
    sub.add_parser("hotspots").set_defaults(func=cmd_hotspots)
    p = sub.add_parser("brief")
    p.add_argument("run")
    p.add_argument("task")
    p.set_defaults(func=cmd_brief)
    p = sub.add_parser("start")
    p.add_argument("run")
    p.add_argument("task")
    p.add_argument("--path")
    p.add_argument("--no-install", action="store_true")
    p.set_defaults(func=cmd_start)
    p = sub.add_parser("join")
    p.add_argument("run")
    p.add_argument("task")
    p.add_argument("--no-install", action="store_true")
    p.set_defaults(func=cmd_join)
    p = sub.add_parser("test")
    p.add_argument("test_args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_test)
    p = sub.add_parser("land")
    p.add_argument("run")
    p.add_argument("task")
    p.add_argument("--full", action="store_true", help="also run the full test suite (one checkout at a time)")
    p.set_defaults(func=cmd_land)
    p = sub.add_parser("cleanup")
    p.add_argument("run")
    p.add_argument("task")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_cleanup)
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["test"]:
        # Everything after `test` is the test runner's, options included.
        args = argparse.Namespace(func=cmd_test, test_args=argv[1:])
    else:
        args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Stop as stop:
        print(f"stopped: {stop}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
