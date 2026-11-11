# kit-feature

**Group:** Kits · **Commands:** `/feature`

A feature from request to recorded in one command: the Build kit, then the Break & Test kit (quick), then the Docs & Flow kit, with each kit skipping what does not apply and a failing gate stopping the run.

## When to use it

New feature work you want built, proven and documented in one go.

## Example

In Claude Code:

```
/feature add invoices with a list screen
```

In Cursor, Codex or Trae, name it in the message: `@feature add invoices with a list screen`.

See what it would run, without running anything (paths shown for a `.claude/skills` install):

```bash
python3 .claude/skills/switchboard/scripts/kit.py plan feature --request "add invoices with a list screen"
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
