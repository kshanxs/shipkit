# kit-flow

**Group:** Kits · **Commands:** `/flow`

The Docs & Flow group in one command. At the end of a session: docsync, feature-map, open-loops, then a handoff work log row. At the start (`/flow start`): read the handoff and the open questions. Only documentation is touched.

## When to use it

The end of every session, "wrap up", "close the loop"; `/flow start` when a session begins.

## Example

In Claude Code:

```
/flow
/flow start
```

In Cursor, Codex or Trae, name it in the message: `@flow wrap up`.

See what it would run, without running anything (paths shown for a `.claude/skills` install):

```bash
python3 .claude/skills/switchboard/scripts/kit.py plan flow --mode start
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
