# bug-sweep

**Group:** Break & Test · **Commands:** `/sweep`, `/hunt`

Reviews new commits, or sweeps a branch area by area, for bugs, cross-tenant leaks, permission gaps, sync, race, idempotency and money errors, starting from the test matrix's gaps; verifies each finding with a repro before it is reported through triage-report. Read-only on the remote.

## When to use it

"Review the new commits", "hunt for bugs", "sweep the billing area", a penetration test of your own app.

## Example

In Claude Code:

```
/sweep review the commits since last week and the billing area
```

In Cursor, Codex or Trae, name it in the message: `@sweep review the commits since last week and the billing area`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
git log --oneline <last-reviewed>..main
python3 .claude/skills/harden/scripts/matrix.py coverage --missing
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
