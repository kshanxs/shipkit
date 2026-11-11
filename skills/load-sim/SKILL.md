---
name: load-sim
description: "Simulate real usage of a multi-tenant app at many tenants on a throwaway local stack or a test server, driven by a scenario config (load-scenario.toml): open-model Poisson traffic, profiles for parts of the day, idempotent changes sent twice, cross-tenant abuse probes that must all be refused, thresholds that pass or fail the run, and a demand estimate for N tenants' busiest hour. Standard-library driver, a stub server to prove the harness, and the cheap way to seed hundreds of tenants. Use when asked to load-test, stress-test or simulate many tenants, workspaces or customers."
---

# Load simulation

Adapted from public load-testing skill patterns (grafana k6, perf analysis; Apache-2.0 and MIT).
Builds on harden (its test matrix names the load cells) and seedbed; use perf-watch during a run
and triage-report after it. `$SK` is the skills folder this skill is installed in.

**Applies to multi-tenant projects.** Run `python3 $SK/switchboard/scripts/project.py has
multi-tenant` first; when it says no, this simulation of many tenants does not fit the project:
say so, and the kits skip it. For a single-user or multi-user server, a bounded burst with harden's
`adversarial_runner.py --concurrency` answers "does it hold under load" without tenants.

## Hard rules (repeat them in every delegated agent's prompt)

- A local stack or a named test server only, on a **scratch database**. Never production, a
  hosted shared database, a deployed customer URL, or real people's data. `sim.py` refuses any
  host that is not this machine unless the scenario's `allow_hosts` (or `--allow-host`) names it.
- Test credentials only: tokens minted locally, seeded `.test` people, every outside provider
  (email, SMS, payments) in mock mode. Never copy secrets out of `.env` files into reports.
- Run outputs (`sim-out/`) are not committed. A fix happens only when the user asks.
- Never drop or clean a database you did not create.

## The scenario

```bash
S="python3 $SK/load-sim/scripts/sim.py"
$S init                                  # writes load-scenario.toml: the generic SaaS example
python3 $SK/load-sim/scripts/stub_server.py --port 8077 &   # a stand-in API that behaves well
$S plan --profile peak --count 10        # the calls a run would make; nothing is sent
$S run --profile peak --rps 20 --duration 10                 # against the stub: a clean result
$S demand --tenants 500                  # the busiest hour for 500 tenants, estimated
```

`load-scenario.toml` ([references/scenario.example.toml](references/scenario.example.toml)) holds
everything about the product, so the driver holds none of it:

| Section | Says |
|---|---|
| `[target]` | `base_url`, `allow_hosts`, extra headers |
| `[auth]` | How a request is signed: `none`, `env` (`SIM_TOKEN_<ROLE>`), `tokens_file` (tenant to role to token), or `template` |
| `[tenants]` | The tenant ids, the tenant header, one address per tenant (`X-Forwarded-For`), and `[tenants.vars]` placeholders |
| `[population]`, `[peak]` | People per tenant by role, their requests in the busiest hour, the share active: what `demand` multiplies |
| `[[requests]]` | Each request kind: method, path and body with placeholders, `idempotency`, `replay` (share sent twice with one key), `cross_tenant` and `expect = "4xx"` for leak probes |
| `[profiles]` | Relative weights of request kinds for a part of the day (`peak`, `evening`, `mixed`, `abuse`) |
| `[thresholds]` | `error_rate`, `p95_ms`, `p99_ms`, `abuse_2xx`, `not_replayed`: the run exits 1 when one fails |

Point it at your app: change `base_url`, mint tokens on the test stack and use `auth.mode = "env"`
or `tokens_file`, list your routes as `[[requests]]`, and weight them in profiles from what your
analytics say people do.

## How it stays cheap

| Cost | How it is avoided |
|---|---|
| Seeding hundreds of tenants through the seed script, one by one | Seed one tenant fully once, then clone it inside the database: [references/clone-seeding.md](references/clone-seeding.md) |
| Re-seeding for every run | Keep the seeded database as a template (`CREATE DATABASE run TEMPLATE seeded500`): a fresh copy in seconds |
| One coroutine or virtual user per person | An open model: requests arrive at a rate, each picked as a person of a tenant doing a thing |
| Signing thousands of people in | Tokens minted on the test stack, loaded from the environment or a file |
| Measuring capacity you do not need | `demand` estimates what N real tenants ask in their busiest hour; a run reports what the machine achieved. Compare them; never claim capacity a run did not show |
| Waiting for the busy hour | If behaviour depends on the time of day, give the app a clock you can pin in the test environment (an env var read by its clock function) |

## Shapes, in order

Stop at the first that fails its threshold and report it.

| Test | Shape | Goal |
|---|---|---|
| Smoke | 3 tenants, `--rps 15 --duration 10`, every profile | The harness is right; 0 errors |
| Baseline | All tenants, `--rps 50 --duration 120` | Reference p95 with all the data |
| Demand | `--rps` = the `demand` estimate, 10 minutes | A normal busiest hour |
| Spike | The peak profile at twice the estimate | The burst |
| Breakpoint | Raise `--rps` by half each run until 5xx > 1% or p95 > 2 s | Where it breaks, and why (perf-watch) |
| Soak (optional) | `mixed` at the estimate, 30 to 60 minutes | Leaks, pool exhaustion |

Run the abuse profile at every size: every leak probe must come back 4xx. One address per tenant
means a tenant's normal use tripping the rate limit **is a finding**.

Lessons that make a run measure the API instead of the harness:

- **One signing key for the server and the token minting**, or every request is 401.
- **The connection pool within the database's limit.** Workers x (pool size + overflow) must not
  pass the pooler's or the database's connection limit; run once with the defaults to show it.
- **Production logging.** Pretty development tracebacks under errors can eat a worker's CPU and turn
  a few errors into a stall.
- **Stop the server by its port, not its name** (`ss -ltnp | grep :<port>`).

Output: `sim-out/<time>-<profile>/requests.csv` (time, request, status, ms, queued ms, tenant, code)
and `summary.md` (per request kind, slowest p95 first, with the thresholds PASS or FAIL).

## Correctness after load (same database)

- `isolation_sweep.py` between two of the seeded tenants (harden skill).
- The app's race, isolation and idempotency tests, on the test database (not the simulation one).
- Row counts before and after: no duplicate rows for one natural key; replays wrote nothing.

## Extending

- A new profile is a line under `[profiles]`; a new kind of request is a `[[requests]]` entry. Name
  the matrix cell it covers.
- A new feature adds its busiest request to `mixed`, and to the profile of the time of day it is
  used.
- k6 or Locust still work for HTTP-only runs; name requests the same way so the reports line up.

## Hand-off

Return `sim-out/` (summary, requests, perf-watch snapshots, log excerpts) and turn every anomaly
into an issue with triage-report, with a "Not tried / blocked" list and the matrix cells covered.
