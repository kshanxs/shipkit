# handoff

**Group:** Docs & Flow · **Commands:** `/handoff`

The shared memory between agent sessions in `HANDOFF.md`: read Now, Next up, Waiting, Blocked and the newest work log at the start; add one work log row and update the sections at the end. Never invents content it could not read. Notion (or another tool) is an optional adapter (`references/notion-adapter.md`).

## When to use it

Every session start and end, after a usage limit, when switching tools, "where did we leave off?".

## Example

In Claude Code:

```
/handoff where did we leave off?
```

In Cursor, Codex or Trae, name it in the message: `@handoff where did we leave off?`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/handoff/scripts/handoff.py init
python3 .claude/skills/handoff/scripts/handoff.py log --entry "Search API" --agent Claude --changed "Search endpoint and tests" --next "Wire the search page" --status "In progress"
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
