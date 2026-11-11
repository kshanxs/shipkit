# kit-build

**Group:** Kits · **Commands:** `/build`

The Build group in one command: handoff and open-loops to start, fanout when the work is parallel, then only the stack skills the work touches (backend, web, mobile), wire-api when an API and a screen both change, and seedbed when the data model changes. Each stack's tests gate the next step.

## When to use it

Building a feature or a change that spans the stack.

## Example

In Claude Code:

```
/build add invoices with a list screen
```

In Cursor, Codex or Trae, name it in the message: `@build add invoices with a list screen`.

See what it would run, without running anything (paths shown for a `.claude/skills` install):

```bash
python3 .claude/skills/switchboard/scripts/kit.py plan build --request "add invoices with a list screen"
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
