---
name: perf-watch
description: "Collect API and system stats while a load run, soak, simulation or bug sweep is going: requests per endpoint, p50/p95/p99, errors by status, throughput, slow and N+1 queries, the connection pool, cache, CPU and memory, rate-limit hits, idempotency and sync numbers, growth per tenant, and outside-provider calls; then write stats.md for triage-report. On a local throwaway stack only. Use when a load test or simulation needs monitoring, or the user asks about latency, p95, N+1, slow queries, pg_stat_statements, memory leaks or the connection pool."
---

# Performance watch

Adapted from public performance-analysis skill patterns (results analysis, N+1 and unbounded-query
reviews, k6, OpenTelemetry ideas; MIT and Apache-2.0). Same safety rules as load-sim: a local
scratch database only, test credentials only, outputs outside the repository (`sim-out/monitor/`),
no commits, no secrets in output. The load cells it measures are in the harden skill's test matrix;
findings go to triage-report.

Sections about tenants (rows and p95 per tenant, tenant segments in keys, "Growth with the number
of tenants") apply only when the project profile is multi-tenant (`project.py has multi-tenant`);
otherwise measure growth with the size of the data instead.

## Start monitoring before the load, stop it after

A snapshot at t0, a sample every 10 seconds during the run, a final snapshot. Save everything
under `sim-out/monitor/`.

### 1. Client side (the load generator is the source of truth for users)

- `sim.py run` writes `requests.csv` and `summary.md`. With k6: `--out json=run.json`, every request
  tagged with its route template, role and tenant.
- Build per endpoint: count, RPS, p50, p95, p99, max, error % and a status histogram (2xx; 401, 403,
  404, 409, 422, 429; 5xx). Per role and per tenant too, and a time series every 30 seconds to see
  the shape: a slow climb points to a leak or a queue, a cliff to the pool or a lock, a saw-tooth to
  GC or a cache.
- Count 429s per tenant address, `Idempotency-Replayed: true`, and replays that were not replayed.

### 2. Server side

- The app's own metrics endpoint if it has one (route latency, pool use, backlog), sampled every
  10 to 30 seconds. An in-memory window is per worker: treat the client numbers as authoritative.
- Recent 5xx with their exception class, joined to the logs for tracebacks. Grep the logs for
  `Traceback`, `TimeoutError`, `pool limit`, `deadlock detected`, `IntegrityError`, `Event loop is
  blocked` and `Task was destroyed`.

### 3. Idempotency and sync (during a reconnect or peak profile)

- The share of replayed changes answered `replayed`; any `NOT-REPLAYED` is a finding (done twice).
- The idempotency claims table: rows and size at t0 and after, rows per minute under the burst,
  keys older than the retention still there (the purge is not running).
- 409 in-flight answers per minute: a rise under load means requests outlive their claim.
- Duplicates: `SELECT <natural key>, count(*) FROM <table> GROUP BY 1 HAVING count(*) > 1` must be
  empty for every table a replay writes.

### 4. Growth with the number of tenants

- Rows per tenant of the busiest tables, and the database size, at 3, 50 and 500 tenants. A table
  that grows faster than the number of tenants is a finding.
- The same endpoint's p95 at 50 and 500 tenants with the same `--rps`: a route whose time grows with
  the number of tenants scans across them (a missing tenant column in an index, a query without the
  tenant filter).

### 5. Postgres

- Run it with `shared_preload_libraries=pg_stat_statements`, `pg_stat_statements.track=all`,
  `log_min_duration_statement=200`, `log_lock_waits=on` (a compose override outside the repository).
  `CREATE EXTENSION pg_stat_statements; SELECT pg_stat_statements_reset();` at t0.
- After the run: the top 25 by `total_exec_time` and by `mean_exec_time`, the top by `calls`,
  `rows/calls` (unbounded lists), `shared_blks_read` (cache misses); `pg_stat_activity` samples
  (waiting, idle in transaction), lock waits, `seq_scan` against `idx_scan` on big tables, deadlocks.
- **N+1:** a query whose `calls` is about k times one endpoint's request count; or count queries per
  request with an ORM event hook (SQLAlchemy `before_cursor_execute`, Prisma's query event). Flag a
  route over 15 queries a request, or one whose count grows with the page size. Confirm with
  `EXPLAIN (ANALYZE, BUFFERS)`.
- **ORM smells:** lazy loads in loops (no `selectinload`/`include`), a `get` per row in a loop, list
  endpoints without a limit, counting with `len(all())`, unbatched write loops, filters on unindexed
  columns (the tenant column plus a date).

### 6. Process and host

- `docker stats --no-stream` for the database and cache, and `pidstat -rud 5` (or `psutil`) for the
  app's processes: CPU, RSS, threads, open files. Memory that keeps climbing in a soak is a leak.
- Event-loop blocking (Python): `PYTHONASYNCIODEBUG=1` with a 0.1 s slow-callback threshold; and
  `uv run ruff check --select ASYNC`.
- Pool sizing: workers x (pool + overflow) against the database's `max_connections`. Saturation over
  80%, or pool timeouts, is a finding.
- Cache: `redis-cli INFO stats memory clients` (ops/s, hits and misses, evictions, memory) and
  `SLOWLOG GET 20`; sample keys (`--scan`) to check each carries a tenant segment.

### 7. Outside providers

Everything in mock mode (email, SMS, push, payments, storage). Count calls per provider; flag any
**real outbound host** (`ss -tnp`, proxy logs), duplicate sends for one action, and fan-out done
inside the request (one announcement sending N messages synchronously).

## Output: stats.md (it feeds triage-report)

Every table states the profile, the number of tenants, the `--rps` asked and achieved, and where it
ran.

1. Run summary (profile, duration, total requests, RPS, error %, thresholds)
2. Top 20 endpoints by p95, with count, RPS, p50, p95, p99, error %
3. Status codes, per role and per tenant
4. 429s per tenant address
5. Database: top slow queries (normalised SQL, calls, mean, total, rows/call), N+1 routes, pool peak,
   lock waits and deadlocks
6. Cache, CPU and RSS peaks, and their trend
7. Outside-provider calls
8. Idempotency and sync: replays, in-flight 409s, claim rows and size, duplicates (none expected)
9. Growth: rows per tenant, and the same routes' p95 at two sizes

Attach the raw files (`requests.csv`, metric samples, `pg_stat_statements` export, log excerpts).
Every number states its source and its time window, with the time zone.
