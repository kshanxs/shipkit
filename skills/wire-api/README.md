# wire-api

**Group:** Build · **Commands:** `/wire`

The five-step protocol for wiring a screen to an API endpoint without drift: read the contract, send tenant headers through the one client, generate or mirror the types from OpenAPI, key queries by everything they depend on and invalidate after writes, then move the tracker row (Frontend only, Backend only, Built).

## When to use it

Connecting a screen to a route, replacing a mock with the real API, or a screen needing a route that does not exist yet.

## Example

In Claude Code:

```
/wire connect the invoices page to GET /api/v1/invoices
```

In Cursor, Codex or Trae, name it in the message: `@wire connect the invoices page to GET /api/v1/invoices`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.gen.ts
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
