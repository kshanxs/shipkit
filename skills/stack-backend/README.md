# stack-backend

**Group:** Build · **Commands:** `/api`, `/be`

Conventions and the test workflow for a multi-tenant backend API: module layout, tenant isolation (404 for another tenant's record, 403 for another tenant's header), one transaction per request, races held by constraints or locks, permission data migrations, reviewed migrations, cache rules, tenant time zones, and running everything through `uv`. Node equivalents in `references/node.md`.

## When to use it

Adding or changing an endpoint, service, model, migration, permission or test in the API.

## Example

In Claude Code:

```
/api add an endpoint that archives a project, with its isolation tests
```

In Cursor, Codex or Trae, name it in the message: `@api add an endpoint that archives a project, with its isolation tests`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
uv run pytest -k projects -v
uv run alembic revision --autogenerate -m "archive projects"   # then review it
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
