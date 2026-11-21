#!/usr/bin/env python3
"""Claude Code hook for a user-wide shipkit install. Runs only in a project that opted in.

    global_hook.py route     the skill router (UserPromptSubmit)
    global_hook.py stop      the documentation check (Stop)

A project opts in by having a shipkit.toml. A project with its own shipkit install has its own
hooks, so this stays out of it. A hook must never break a session: every problem exits 0.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
TARGETS = {
    "route": (SKILLS / "switchboard" / "scripts" / "route.py", ["hook"]),
    "stop": (SKILLS / "docsync" / "scripts" / "stop_hook.py", []),
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in TARGETS or sys.version_info < (3, 11):
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if not (project / "shipkit.toml").is_file() or (project / ".claude" / "skills" / "switchboard").exists():
        return 0
    script, args = TARGETS[argv[0]]
    if not script.is_file():
        return 0
    try:
        os.chdir(project)
        os.environ["SHIPKIT_ROOT"] = str(project)
        os.execv(sys.executable, [sys.executable, str(script), *args])
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
