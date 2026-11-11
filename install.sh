#!/usr/bin/env bash
# Install shipkit skills into a project.
#
#   ./install.sh <target-project> [--claude|--agents|--trae|--all] [options]
#
# Layouts (any combination; default --all):
#   --claude    <target>/.claude/skills/<name>/ and slash commands in <target>/.claude/commands/
#   --agents    <target>/.agents/skills/<name>/ (Cursor, Codex) and a skill table in <target>/AGENTS.md
#   --trae      <target>/.trae/skills/<name>/
#   --all       all three
#
# Options:
#   --skills a,b,c   only these skills (the switchboard router is always added)
#   --link           with --agents: make the .claude and .trae copies symlinks to .agents/skills
#   --hooks          add the router hook and the docsync stop hook to <target>/.claude/settings.json
#   --force          replace a skill folder that shipkit did not install
#   --no-config      do not write <target>/shipkit.toml (the generic SaaS example) when it is missing
#   --dry-run        print what would be done, change nothing
#
# Re-running updates the skills it installed before. Needs bash and python3 (3.11+).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skills"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$HERE/pyproject.toml" | head -1)"

usage() { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

[ $# -ge 1 ] || usage 1
case "$1" in -h|--help) usage 0 ;; esac
TARGET="$1"; shift
[ -d "$TARGET" ] || { echo "install.sh: $TARGET is not a folder" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"
[ "$TARGET" != "$HERE" ] || { echo "install.sh: install into a project, not into shipkit itself" >&2; exit 1; }

CLAUDE=0; AGENTS=0; TRAE=0; LINK=0; HOOKS=0; FORCE=0; CONFIG=1; DRY=0; ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --claude) CLAUDE=1 ;;
    --agents) AGENTS=1 ;;
    --trae) TRAE=1 ;;
    --all) CLAUDE=1; AGENTS=1; TRAE=1 ;;
    --skills) ONLY="${2:?--skills needs a comma-separated list}"; shift ;;
    --skills=*) ONLY="${1#--skills=}" ;;
    --link) LINK=1 ;;
    --hooks) HOOKS=1 ;;
    --force) FORCE=1 ;;
    --no-config) CONFIG=0 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage 0 ;;
    *) echo "install.sh: unknown option $1" >&2; usage 1 ;;
  esac
  shift
done
[ $((CLAUDE + AGENTS + TRAE)) -gt 0 ] || { CLAUDE=1; AGENTS=1; TRAE=1; }
command -v python3 >/dev/null || { echo "install.sh: python3 is required" >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "install.sh: python3 3.11 or newer is required (tomllib)" >&2; exit 1; }

ALL=$(cd "$SRC" && for d in */; do [ -f "$d/SKILL.md" ] && printf '%s\n' "${d%/}"; done)
if [ -n "$ONLY" ]; then
  SKILLS=$(printf '%s\n' "$ONLY" | tr ',' '\n' | sed '/^$/d')
  for s in $SKILLS; do
    printf '%s\n' "$ALL" | grep -qx "$s" || { echo "install.sh: no skill named $s; there are: $(echo $ALL)" >&2; exit 1; }
  done
  printf '%s\n' "$SKILLS" | grep -qx switchboard || SKILLS="$SKILLS
switchboard"
else
  SKILLS="$ALL"
fi

run() { if [ "$DRY" = 1 ]; then echo "would: $*"; else "$@"; fi; }

copy_skill() {  # copy_skill <name> <dest-skills-dir>
  local name="$1" dest="$2/$1"
  if [ -e "$dest" ] && [ ! -L "$dest" ] && [ ! -f "$dest/.shipkit" ] && [ "$FORCE" != 1 ]; then
    echo "  skip  $dest: exists and was not installed by shipkit (use --force to replace it)"
    return
  fi
  run rm -rf "$dest"
  run mkdir -p "$dest"
  if [ "$DRY" = 1 ]; then echo "would: copy $SRC/$name -> $dest"; return; fi
  (cd "$SRC/$name" && tar cf - --exclude=tests --exclude=__pycache__ --exclude='*.pyc' .) | (cd "$dest" && tar xf -)
  printf 'shipkit %s\n' "$VERSION" > "$dest/.shipkit"
}

link_skill() {  # link_skill <name> <dest-skills-dir> <relative target>
  local name="$1" dest="$2/$1" rel="$3"
  if [ -e "$dest" ] && [ ! -L "$dest" ] && [ ! -f "$dest/.shipkit" ] && [ "$FORCE" != 1 ]; then
    echo "  skip  $dest: exists and was not installed by shipkit (use --force to replace it)"
    return
  fi
  run rm -rf "$dest"
  run ln -s "$rel/$name" "$dest"
}

install_layout() {  # install_layout <dir> <label>
  local dir="$TARGET/$1/skills"
  run mkdir -p "$dir"
  for s in $SKILLS; do
    if [ "$LINK" = 1 ] && [ "$AGENTS" = 1 ] && [ "$1" != ".agents" ]; then
      link_skill "$s" "$dir" "../../.agents/skills"
    else
      copy_skill "$s" "$dir"
    fi
  done
  echo "  $2: $(printf '%s\n' "$SKILLS" | wc -l | tr -d ' ') skills in $1/skills"
}

echo "shipkit $VERSION -> $TARGET"
[ "$AGENTS" = 1 ] && install_layout .agents "Cursor / Codex"
[ "$CLAUDE" = 1 ] && install_layout .claude "Claude Code"
[ "$TRAE" = 1 ] && install_layout .trae "Trae"

# The project's config: the generic SaaS example, never over an existing file.
if [ "$CONFIG" = 1 ] && [ ! -e "$TARGET/shipkit.toml" ]; then
  run cp "$HERE/shipkit.example.toml" "$TARGET/shipkit.toml"
  echo "  wrote shipkit.toml (the generic SaaS example: edit the paths to match the project)"
fi

# AGENTS.md: Cursor and Codex read it. Add the skill table's markers once; the router fills them.
if [ "$AGENTS" = 1 ] && [ "$DRY" != 1 ]; then
  if [ ! -e "$TARGET/AGENTS.md" ]; then
    printf '# Agent instructions\n\n' > "$TARGET/AGENTS.md"
  fi
  if ! grep -q 'shipkit:skills:start' "$TARGET/AGENTS.md"; then
    cat >> "$TARGET/AGENTS.md" <<'EOF'

## Skills (shipkit)

Skills live in `.agents/skills/<name>/SKILL.md`. Read the one a task needs before starting; name one
with `@<short>` in a message. `python3 .agents/skills/switchboard/scripts/route.py "<request>"`
says which fit.

<!-- shipkit:skills:start (generated by switchboard/scripts/route.py --write) -->
<!-- shipkit:skills:end -->
EOF
  fi
fi

# Slash commands (Claude Code) and the AGENTS.md table, written by the installed router.
if [ "$DRY" != 1 ]; then
  if [ "$CLAUDE" = 1 ]; then
    python3 "$TARGET/.claude/skills/switchboard/scripts/route.py" --write >/dev/null
    echo "  slash commands in .claude/commands/"
  fi
  if [ "$AGENTS" = 1 ]; then
    python3 "$TARGET/.agents/skills/switchboard/scripts/route.py" --write --no-commands >/dev/null
    echo "  skill table in AGENTS.md"
  fi
fi

# Hooks: the router on every prompt, the documentation contract when an agent stops.
if [ "$HOOKS" = 1 ] && [ "$DRY" != 1 ]; then
  ROOTDIR=".claude/skills"; [ "$CLAUDE" = 1 ] || ROOTDIR=".agents/skills"
  python3 - "$TARGET" "$ROOTDIR" <<'PY'
import json, sys
from pathlib import Path
target, skills = Path(sys.argv[1]), sys.argv[2]
path = target / ".claude" / "settings.json"
path.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}
hooks = data.setdefault("hooks", {})

def add(event, script, args, timeout, message=None):
    if not (target / skills / script).exists():
        return
    command = f"sh -c 'f=\"${{CLAUDE_PROJECT_DIR:-.}}/{skills}/{script}\"; [ -f \"$f\" ] && exec python3 \"$f\"{args}; exit 0'"
    entries = hooks.setdefault(event, [])
    if any(script in h.get("command", "") for e in entries for h in e.get("hooks", [])):
        return
    hook = {"type": "command", "command": command, "timeout": timeout}
    if message:
        hook["statusMessage"] = message
    entries.append({"hooks": [hook]})

add("UserPromptSubmit", "switchboard/scripts/route.py", " hook", 10)
add("Stop", "docsync/scripts/stop_hook.py", "", 30, "Checking the documentation contract")
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  hooks in {path.relative_to(target)}")
PY
fi

# Prove it: every installed layout's router is in step and resolves every skill.
if [ "$DRY" != 1 ]; then
  for layout in .claude .agents .trae; do
    r="$TARGET/$layout/skills/switchboard/scripts/route.py"
    [ -f "$r" ] || continue
    flag=""; [ "$layout" = ".claude" ] || flag="--no-commands"
    python3 "$r" --check $flag >/dev/null && python3 "$r" --resolve $flag >/dev/null \
      && echo "  check $layout: in step, every skill resolves" \
      || { echo "  check $layout: FAILED (run: python3 $layout/skills/switchboard/scripts/route.py --check)" >&2; exit 1; }
  done
fi
echo "Done. Suggested .gitignore lines: .fanout/  sim-out/"
