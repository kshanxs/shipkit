#!/usr/bin/env python3
"""Install shipkit once for this user: every project gets the skills. Standard library only.

    install.sh --global [--claude] [--codex] [--hooks] [--dry-run]
    install.sh --global --uninstall [--dry-run]

Skills are links into this checkout, so `git pull` updates them. With neither --claude nor --codex,
it uses each agent whose folder exists. A file or link that is not shipkit's is never replaced.
--hooks adds the router and the docs check to ~/.claude/settings.json; they act only in projects
with a shipkit.toml.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
COMMANDS = SKILLS / "switchboard" / "commands"
HOOK = SKILLS / "switchboard" / "scripts" / "global_hook.py"
HOOKS = {"UserPromptSubmit": ("route", 10), "Stop": ("stop", 30)}


def skill_names() -> list[str]:
    return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))


def ours(path: Path) -> bool:
    if not path.is_symlink():
        return False
    target = Path(os.path.normpath(path.parent / os.readlink(path)))
    return target == SKILLS or SKILLS in target.parents


class Run:
    def __init__(self, dry: bool) -> None:
        self.dry = dry
        self.changed = 0
        self.skipped: list[str] = []

    def link(self, dest: Path, target: Path) -> None:
        if dest.is_symlink() and Path(os.path.normpath(dest.parent / os.readlink(dest))) == target:
            return
        if (dest.exists() or dest.is_symlink()) and not ours(dest):
            self.skipped.append(str(dest))
            return
        self.changed += 1
        if self.dry:
            print(f"would link {dest} -> {target}")
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink():
            dest.unlink()
        dest.symlink_to(target)

    def unlink(self, dest: Path) -> None:
        if not ours(dest):
            return
        self.changed += 1
        if self.dry:
            print(f"would remove {dest}")
        else:
            dest.unlink()


def read_settings(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(json.dumps(data, indent=2) + "\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def is_our_hook(hook: dict) -> bool:
    return "global_hook.py" in str(hook.get("command", ""))


def add_hooks(data: dict) -> bool:
    hooks = data.setdefault("hooks", {})
    changed = False
    for event, (name, timeout) in HOOKS.items():
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(HOOK))} {name}"
        entries = hooks.setdefault(event, [])
        mine = [h for e in entries for h in e.get("hooks", []) if is_our_hook(h)]
        if mine:
            if mine[0].get("command") != command:
                mine[0]["command"] = command
                changed = True
            continue
        entries.append({"hooks": [{"type": "command", "command": command, "timeout": timeout}]})
        changed = True
    return changed


def remove_hooks(data: dict) -> bool:
    changed = False
    hooks = data.get("hooks", {})
    for event in list(hooks):
        kept = []
        for entry in hooks[event]:
            left = [h for h in entry.get("hooks", []) if not is_our_hook(h)]
            changed = changed or len(left) != len(entry.get("hooks", []))
            if left:
                kept.append({**entry, "hooks": left})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if "hooks" in data and not data["hooks"]:
        del data["hooks"]
    return changed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="install.sh --global", description="Install shipkit for this user.")
    parser.add_argument("--claude", action="store_true")
    parser.add_argument("--codex", action="store_true")
    parser.add_argument("--hooks", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    home = Path.home()
    claude, codex = home / ".claude", home / ".codex"
    use_claude, use_codex = args.claude, args.codex
    if not use_claude and not use_codex:
        use_claude, use_codex = claude.is_dir(), codex.is_dir()
    if args.uninstall:
        use_claude, use_codex = True, True
    if not use_claude and not use_codex:
        print("install.sh --global: found no ~/.claude or ~/.codex; pass --claude or --codex", file=sys.stderr)
        return 1
    if args.hooks and not use_claude:
        print("install.sh --global: --hooks needs Claude Code (--claude)", file=sys.stderr)
        return 2

    settings = claude / "settings.json"
    data: dict = {}
    if use_claude and (args.hooks or args.uninstall):
        try:
            data = read_settings(settings)
        except (ValueError, OSError) as error:
            print(f"install.sh --global: cannot read {settings}: {error}; nothing was changed", file=sys.stderr)
            return 1

    run = Run(args.dry_run)
    homes = [h / "skills" for h, on in ((claude, use_claude), (codex, use_codex)) if on]
    names = skill_names()
    command_files = sorted(COMMANDS.glob("*.md"))
    for home_dir in homes:
        for name in names:
            dest = home_dir / name
            run.unlink(dest) if args.uninstall else run.link(dest, SKILLS / name)
    if use_claude:
        for file in command_files:
            dest = claude / "commands" / file.name
            run.unlink(dest) if args.uninstall else run.link(dest, file)
    hooks_changed = False
    if args.uninstall and settings.exists():
        hooks_changed = remove_hooks(data)
    elif args.hooks:
        hooks_changed = add_hooks(data)
    if hooks_changed:
        run.changed += 1
        if args.dry_run:
            print(f"would update hooks in {settings}")
        else:
            write_settings(settings, data)

    verb = "would change" if args.dry_run else "changed"
    print(f"shipkit: {verb} {run.changed} item(s); {len(names)} skills, {len(command_files)} commands")
    for path in run.skipped:
        print(f"  skipped {path}: exists and is not shipkit's")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
