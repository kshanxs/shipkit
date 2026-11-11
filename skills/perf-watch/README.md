# perf-watch

**Group:** Break & Test · **Commands:** `/perf`, `/mon`

What to collect while load runs: per-endpoint latency and errors, slow and N+1 queries from `pg_stat_statements`, pool saturation, cache, CPU and memory, idempotency and duplicate checks, growth per tenant, and outside-provider calls; written up as `stats.md` for triage-report.

## When to use it

During a load-sim run, a soak, or when latency, N+1 queries or a leak is suspected.

## Example

In Claude Code:

```
/perf watch the database and the API during the next load run
```

In Cursor, Codex or Trae, name it in the message: `@perf watch the database and the API during the next load run`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
psql -c "SELECT pg_stat_statements_reset();"   # at t0, on the scratch database
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
