# triage-report

**Group:** Break & Test · **Commands:** `/triage`, `/report`

Turns a bug sweep, load run or monitoring run into one severity-ranked report: evidence, repro, links at the exact commit, a suggested fix per issue, the matrix coverage achieved, stats, and what was not tried. Read-only: it goes to the user, never to a tracker unless asked.

## When to use it

After bug-sweep, load-sim or perf-watch, or when findings need ranking.

## Example

In Claude Code:

```
/triage write the report for this sweep and last night's load run
```

In Cursor, Codex or Trae, name it in the message: `@triage write the report for this sweep and last night's load run`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/harden/scripts/matrix.py coverage   # before and after, for the coverage table
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
