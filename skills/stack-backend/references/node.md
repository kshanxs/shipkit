# The backend rules in Node

The same rules as SKILL.md, for an API in Node (Express, Fastify or NestJS) with Prisma or Drizzle.

| Rule | Python (FastAPI) | Node |
|---|---|---|
| Module layout | `router.py`, `service.py`, `schemas.py`, `models.py` | `*.routes.ts` or `*.controller.ts`, `*.service.ts`, `*.schema.ts` (zod), the ORM schema |
| Tenant context | A dependency that resolves the header against the caller's roles | A middleware or guard that sets `req.ctx = { workspaceId, permissions }`; services take `ctx`, never `req` |
| Validation | Pydantic v2 | zod (`schema.parse(req.body)`); unknown keys stripped or refused on purpose |
| One transaction a request | `get_db` commits on return, rolls back on raise | `prisma.$transaction(async (tx) => ...)` or `db.transaction(...)` around the service call; never commit after the answer is sent |
| Races | Unique constraint or `SELECT ... FOR UPDATE` | The same in SQL: `@@unique` in Prisma, `uniqueIndex` in Drizzle, `FOR UPDATE` through `$queryRaw` or `.for('update')` |
| Migrations | Alembic, reviewed | `prisma migrate dev --create-only` then review, or `drizzle-kit generate` then review; never edit a shipped migration |
| Time | `tenant_today()` | one `tenantToday(tz)` helper (`Intl.DateTimeFormat` or date-fns-tz) |
| Tests | `uv run pytest` | `vitest run` or `node --test`; a database per worker (`VITEST_POOL_ID`) |
| Lint | `uv run ruff check` | `eslint .` or `oxlint`, and `tsc --noEmit` |

Run Python tooling for scripts in a mixed repository through uv (`uv run python scripts/x.py`),
so the scripts get the project's pinned interpreter and dependencies.
