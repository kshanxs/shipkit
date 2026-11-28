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

## Nothing blocking on a request path

Node runs every request on one event loop, so one blocking call makes every request wait behind
it: each button in the app feels seconds slow, not only the one that calls it. Never call
`spawnSync`, `execSync`, `execFileSync`, `readFileSync` on a large file or any other synchronous
I/O in a route, a middleware or code they call.

- Slow outside state (a CLI that probes other machines, a remote status, a big file) is read in
  the background: async `execFile` or `spawn`, one run in flight at a time, a TTL, warmed at
  start-up. The route serves the last answer and its age.
- Check: time the main read endpoint, the one every action re-fetches. Over about 200 ms, profile
  it with `node --cpu-prof` and look for self time in synchronous calls.

Run Python tooling for scripts in a mixed repository through uv (`uv run python scripts/x.py`),
so the scripts get the project's pinned interpreter and dependencies.

## Embedded SQLite (node:sqlite)

For a dependency-free server or a local store, the built-in `node:sqlite` module replaces a driver.
The same rules as the Migrations section apply, plus these (a field report from a server with an
embedded database and a search index):

1. `node:sqlite` may still be a release candidate. Keep every call (open, migrate, check, hot copy)
   in one module, so an API change touches one file.
2. On open: `chmod 600` when the file is created, `PRAGMA journal_mode=WAL`, `PRAGMA
   foreign_keys=ON` and a `busy_timeout`. Use numbered `NNN_name.sql` migrations, each applied in a
   transaction with its version row in a `schema_migrations` table. Never edit an applied file.
3. Before applying a new migration to a database that holds data, run `VACUUM INTO
   '<backups>/db-<migration>.db'` and keep the last N copies.
4. Take hot copies with the `backup()` API, not `cp`: a copy made while a WAL is being written can
   be torn.
5. Give the project a `db check` command: `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, the
   journal mode, pending migrations, the file mode and, for FTS5, `INSERT INTO t(t) VALUES
   ('integrity-check')`.
6. A WAL streamer (Litestream or similar) needs a restore drill: write a marker, wait, restore to a
   scratch path and look for the marker. A restore that succeeds can still miss the latest write.
7. FTS5's bm25 ranks differently from a substring scorer. When the index must agree with an
   existing search, port that scorer, use FTS5 for snippets and stemmed matching, and keep a parity
   script that compares the top N results over sample queries.
8. Tests: point the state folder at a temporary directory **before** the first import of any module
   that reads it at load time. Run each `node --test` file in its own process.
