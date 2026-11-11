---
name: stack-backend
description: "Conventions and test workflow for a backend API, single-user, multi-user or multi-tenant: module layout, tenant isolation when the project is multi-tenant (404 for another tenant's record, 403 for another tenant's header), access checks when it is not, the request's transaction, races held by constraints or locks, permissions and their data migrations, reviewed migrations, caching, time zones, linting, and running the tests with uv (Python) or the Node equivalents. Use when adding or changing a router, service, model, schema, migration, permission, cache, job or test in the API; and when the user says 'backend', 'API', 'endpoint', 'migration', 'test backend', 'run tests' or 'test <module>'."
---

# Backend API

The rules a backend API keeps, whatever the framework. The examples are FastAPI with
SQLAlchemy and Pydantic run through **uv**; [references/node.md](references/node.md) maps each rule
to Node (Express, Fastify or NestJS with Prisma or Drizzle). The project's own README and code
win over this file: when they disagree, follow the code and say so.

Find the API first: the `[stack]` table of `shipkit.toml` may name it (`api_dir = "apps/api"`);
otherwise look for `pyproject.toml` with fastapi, django or flask, or `package.json` with express,
fastify or @nestjs.

The project profile (`python3 $SK/switchboard/scripts/project.py show`, where `$SK` is the skills
folder this skill is installed in) says which sections apply: a section marked **[multi-tenant]**
applies only when `tenancy = "multi-tenant"`; **[self-hosted]** only for a server people run
themselves. With one user per install, scope by the authenticated user (or by nothing, when the
app has one user) and keep the access rules in "Access without tenants".

## Module layout

Each feature is one package (`app/<module>/` or `src/modules/<module>/`):

| File | Holds |
|------|-------|
| `router.py` | Thin handlers: auth, permission checks, 404s. No queries |
| `service.py` | Queries and business rules; takes the session and ids, never the request |
| `schemas.py` | Request and response models (Pydantic v2, or zod in Node) |
| `models.py` | ORM models |

Register a new router in one place (`main.py`) under `/api/v1/<module>`. Shared pieces live
together: the request context (the tenant, when there are tenants), permissions, rate limiting, the cache helpers, the session
dependency.

## Tenant isolation (non-negotiable) **[multi-tenant]**

Every tenant-scoped endpoint takes a verified tenant context. It reads the tenant header (for
example `X-Workspace-ID`), checks the caller holds an active role there, and loads their
permissions once.

```python
@router.post("/", response_model=schemas.ProjectOut, status_code=201)
async def create_project(data: schemas.ProjectIn, user: CurrentUser, db: DbSession, ctx: TenantContext):
    ctx.require("projects.create")
    return await service.create_project(db, workspace_id=ctx.workspace_id, owner_id=user.id, data=data)
```

- Authorize with `ctx.require(...)`, never with a role the client sends.
- Filter every query by the tenant id from the context, never from the body or query string.
- A record of another tenant, named by its id, answers **404** (as an id that does not exist), so
  tenants cannot probe each other's ids. Another tenant's header answers **403**. A missing
  permission, or a record outside the caller's scope inside their tenant, answers **403**.
- Platform operators (your own staff) get read-only access through an audited support path, never
  a silent bypass.

## Access without tenants

When the project is not multi-tenant:

- One dependency checks the caller (the password, token, API key or session) on every route that
  reads or changes data; health and the sign-in page are the only exceptions, and a test lists them.
- With several users, a record of another user answers **404**, as for tenants above.
- **[self-hosted]** Every state-changing route refuses a foreign or missing `Origin` (or checks a
  CSRF token); the `Host` header is checked against an allow-list (DNS rebinding); the server binds
  where the docs say; secrets and tokens are stored `0600` and never logged.

## The request's transaction

One request, one transaction: commit when the handler returns, roll back when it raises. In
FastAPI make sure the commit happens **before** the answer is sent (recent versions take
`Depends(get_db, scope="function")`; check yours), or a failed commit is already answered 2xx.
Hold every route to it with a test.

A check in Python ("does it already exist?") is not a guard when two requests arrive together. A
unique constraint or a row lock (`SELECT ... FOR UPDATE`) is. See the harden skill for how to make
two requests really race in a test.

## Permissions

Keep one catalogue of permissions and which roles hold them. A database that already exists does
not pick up a catalogue edit: a new or newly granted permission also needs a data migration that
inserts it idempotently (`INSERT ... ON CONFLICT DO NOTHING`).

## Migrations

- Every model change has a migration. Check the head first (`uv run alembic heads`); autogenerate
  is a draft (`uv run alembic revision --autogenerate -m "..."`), review it.
- Make upgrades safe on a database that may be partly migrated, and make every new migration go
  down and up again cleanly.
- Tests that build tables with `create_all` hide a missing migration: keep one test that runs the
  real chain and compares the result with the models (columns, checks, `ondelete`).

## Cache

The database is the source of truth. Two kinds of helper: ones that raise on a cache error (for
one-time codes and anything that must fail visibly) and safe ones that never raise and back off
(for read caches). Delete by pattern with `SCAN`, never `KEYS`. Version cache keys
(`proj:v1:*`) and put the tenant (or user, when there are several) in every key; invalidate on writes.

## Time

"Today" comes from one function that knows the right time zone (the tenant's, the user's, or the
install's: `tenant_today()`, `local_today()`),
never `date.today()` or `datetime.now()`: servers run on UTC, and a day boundary is a bug factory.
Test it.

## Running and testing (uv)

```bash
uv sync                                   # the environment, from uv.lock
uv run pytest -q                          # the suite
uv run pytest -n auto                     # in parallel with pytest-xdist: give each worker its own database
uv run pytest -k <module> -v              # focused
uv run ruff check --fix && uv run ruff format
uv run alembic upgrade head
```

- Tests use the real database and cache when the code does (start them with Docker Compose), with
  one test database per xdist worker, and per git worktree when agents run in parallel (put the
  worktree's folder name in the database name).
- Write test output files (PDFs, screenshots) to a gitignored folder.
- Lint and format must pass before a change is done; a deliberate exception gets
  `# noqa: <code> - <reason>` on its line.
- Local sign-in shortcuts for tests (test tokens, magic links) are refused in production by a
  check that has its own test.

After a model, router or permission change, always run the access tests and the migration-chain
test: **[multi-tenant]** another tenant's id, another tenant's header and each role; otherwise each
route without credentials and, with several users, another user's id. Add them for every new
endpoint.

## Finishing a change

1. Run the focused tests; report failures with their output.
2. Add a changelog line for every change, a bug fix included (docsync skill: `changelog.py add`).
3. Follow docsync for the rest: the feature's spec, its tracker row, `check_docs.py --changed`.
4. A new or changed entity: seedbed skill (the seed, the data map). A screen to wire: wire-api.
