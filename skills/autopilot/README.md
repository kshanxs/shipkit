# autopilot

**Group:** Kits · **Commands:** `/shipkit`, `/auto`

Say "run shipkit" and nothing else: the autopilot reads the repository (what changed, new commits, schema changes, which registers exist, whether the local stack answers) and the request, decides which kits and skills fit right now, runs them, and lists what is ready on request and what cannot run yet, with the reason.

## When to use it

Any time you want shipkit applied without naming skills: "run shipkit", "what should I run?".

## Example

In Claude Code:

```
/shipkit
/auto what should I run?
```

In Cursor, Codex or Trae, name it in the message: `@shipkit check this branch`.

See what it would run, without running anything (paths shown for a `.claude/skills` install):

```bash
python3 .claude/skills/switchboard/scripts/kit.py auto
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
