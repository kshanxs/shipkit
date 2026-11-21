#!/usr/bin/env python3
"""Can shipkit run here? Read-only. Runs on old Python too, so it can say that Python is too old.

    doctor.py            a readable report
    doctor.py --json     {"ok": bool, "checks": [{"check", "status", "detail"}]} on stdout

Exit 0 when nothing fails (warnings are allowed), 1 when shipkit cannot run.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
MIN_PYTHON = (3, 11)
OPTIONAL = {
    "uv": "runs Python projects and shipkit's own tests",
    "gh": "pull requests and issues",
    "node": "web and Node projects",
    "shellcheck": "checks shell scripts",
}


def run(*cmd: str) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def row(check: str, status: str, detail: str) -> dict:
    return {"check": check, "status": status, "detail": detail}


def install_hint() -> str:
    if platform.system() == "Darwin":
        return "brew install python@3.13"
    for tool, hint in (("apt-get", "apt"), ("dnf", "dnf"), ("pacman", "pacman"), ("apk", "apk")):
        if shutil.which(tool):
            return f"{hint} install python3 (3.11 or newer), or `uv python install 3.13`"
    return "install Python 3.11 or newer, or `uv python install 3.13`"


def skill_home(home: Path, label: str, names: list[str]) -> list[dict]:
    base = home / "skills"
    if not home.is_dir():
        return []
    broken = sorted(p.name for p in base.iterdir() if p.is_symlink() and not p.exists()) if base.is_dir() else []
    missing = [n for n in names if not (base / n / "SKILL.md").exists()]
    out = []
    if broken:
        out.append(row(f"{label}_links", "fail", f"{len(broken)} broken: {', '.join(broken[:5])}"))
    if len(missing) == len(names):
        out.append(row(f"{label}_skills", "warn", "not installed for this user (install.sh --global)"))
    elif missing:
        out.append(row(f"{label}_skills", "warn", f"{len(missing)} missing: {', '.join(missing[:5])}"))
    else:
        out.append(row(f"{label}_skills", "ok", f"{len(names)} skills"))
    return out


def checks(cwd: Path | None = None) -> list[dict]:
    cwd = cwd or Path.cwd()
    version = ".".join(str(v) for v in sys.version_info[:3])
    out = [row("platform", "ok", f"{platform.system()} {platform.machine()}")]
    if sys.version_info[:2] >= MIN_PYTHON:
        out.append(row("python", "ok", version))
    else:
        out.append(row("python", "fail", f"{version}; shipkit needs 3.11 or newer: {install_hint()}"))
    git = run("git", "--version")
    out.append(row("git", "ok", git) if git else row("git", "fail", "missing"))
    if git:
        identity = run("git", "-C", str(cwd), "config", "user.name") and run("git", "-C", str(cwd), "config", "user.email")
        out.append(row("git_identity", "ok", "set") if identity else row("git_identity", "warn", "user.name or user.email is not set: commits will fail"))
    for tool, why in OPTIONAL.items():
        out.append(row(tool, "ok", "found") if shutil.which(tool) else row(tool, "warn", f"missing ({why})"))
    names = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
    home = Path.home()
    out += skill_home(home / ".claude", "claude", names) + skill_home(home / ".codex", "codex", names)
    return out


def main(argv: list[str]) -> int:
    if argv and argv != ["--json"]:
        print(__doc__, file=sys.stderr)
        return 0 if argv[0] in ("-h", "--help") else 2
    rows = checks()
    ok = not any(r["status"] == "fail" for r in rows)
    if argv:
        print(json.dumps({"ok": ok, "checks": rows}, indent=2))
    else:
        for r in rows:
            print(f"{r['status']:<5}{r['check']:<16}{r['detail']}")
        print("shipkit can run here" if ok else "shipkit cannot run here: fix the failures above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
