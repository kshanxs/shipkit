# fanout

**Group:** Build · **Commands:** `/fanout`, `/par`

Runs several agents building features at once, each in its own git worktree, and lands their work one branch at a time: a plan with owned paths and reserved numbers, a brief per task, per-worktree ports, env files and dependencies, rebase, re-chained Alembic migrations, regenerated sections and checks at landing.

## When to use it

Two or more independent features to build in parallel, or a parallel run to land or clean up.

## Example

In Claude Code:

```
/fanout build search and CSV export in parallel
```

In Cursor, Codex or Trae, name it in the message: `@fanout build search and CSV export in parallel`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/fanout/scripts/fanout.py new 2026-11-12-search
python3 .claude/skills/fanout/scripts/fanout.py check 2026-11-12-search
python3 .claude/skills/fanout/scripts/fanout.py land 2026-11-12-search search
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
