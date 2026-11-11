# switchboard

**Group:** Docs & Flow · **Commands:** `/sb`, `/route`

The router: picks the skills a request needs from @names, /slash commands, trigger phrases and file paths; runs as a Claude Code hook so the right skills are suggested on every message; writes the slash commands and an optional skill table in AGENTS.md; and checks everything is in step with what is installed.

## When to use it

Which skill fits a request, the list of commands, adding or renaming a skill.

## Example

In Claude Code:

```
/sb which skills fit 'add an endpoint and its screen'?
```

In Cursor, Codex or Trae, name it in the message: `@sb which skills fit 'add an endpoint and its screen'?`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/switchboard/scripts/route.py "add an endpoint and its screen"
python3 .claude/skills/switchboard/scripts/route.py --resolve
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
