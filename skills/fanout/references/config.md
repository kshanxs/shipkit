# fanout: the `[fanout]` table of shipkit.toml

Every key is optional. Without the table, fanout works on any git repository with the defaults
below.

```toml
[fanout]
max_parallel = 3                          # agents at once; the plan warns past it
branch_prefix = "fanout"                  # branches are <prefix>/<run>/<task>
worktree_root = ""                        # default: ../<repo>-wt/
migrations = ""                           # an Alembic versions folder; default: the first of
                                          # migrations/versions, alembic/versions, apps/*/migrations/versions, ...
ports = { API_PORT = 8000, WEB_PORT = 5173 }   # each worktree gets base + its slot (1..39), written to .fanout-env
redis = false                             # true: a redis:7-alpine container per worktree on 6380 + slot
redis_env_file = "apps/api/.env"          # where REDIS_URL is written when redis = true
copy_env = true                           # copy the main checkout's ignored .env files into each worktree
install = ["uv sync --frozen", "pnpm install --frozen-lockfile"]   # default: one install per lock file found
regenerate = ["uv run python scripts/export_openapi.py"]           # run after each rebase, before the checks
checks = ["uv run ruff check"]            # run at every landing
test = "uv run pytest -q"                 # what `fanout.py test` runs (default: uv run pytest, or npm test)

[fanout.path_checks]                      # run when the landing task changed files under the prefix
"apps/api/" = ["cd apps/api && uv run pytest -q -x"]
"apps/web/" = ["cd apps/web && pnpm run typecheck && pnpm run test"]

[fanout.hotspots]                         # added to (or overriding) the defaults: path or glob = [kind, note]
"apps/api/app/main.py" = ["append", "one import and one include_router a module, alphabetical"]
"apps/web/src/app/nav.ts" = ["append", "one entry a page"]
"apps/api/app/config.py" = ["serial", ""]
```

Kinds: `append` (keep both sides' lines), `union` (git merges it; changelogs), `generated` (take
either side, then regenerate), `serial` (one task a wave). `fanout.py hotspots` prints the merged
list. The numbers fanout reserves are read from the open questions register (`[open_loops]
register`) and the bug register (`[docsync] bug_register`), so they follow the docs skills' paths.
