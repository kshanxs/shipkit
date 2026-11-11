---
name: harden
description: "Build a change test-first, then try to break it on purpose and prove every flaw with a failing test before fixing it: hostile input, another tenant's data and another role's actions, requests racing each other, retries and replays, offline changes arriving late, a failing database or cache, and bounded load. Uses a shared test matrix (which combinations to try, pairwise for the rest), an OpenAPI-driven isolation sweep, an HTTP fuzz and concurrency runner, and the attack log. Use when building or changing an endpoint, a service, a money flow or a screen that writes; when the user says 'harden', 'break it', 'attack', 'adversarial', 'fuzz', 'IDOR', 'tenant isolation', 'race condition', 'double submit', 'security review', 'TDD' or 'test first'; and before a feature on a path that takes money or personal records is called done."
---

# Harden: build, test, break, fix

A feature is not done when it works once. It is done when the tests show it works, a deliberate
attempt to break it has been made and written down, and every flaw found is held off by a test
that failed before the fix.

- **Nothing is claimed without a run.** "Tested edge cases" is not a result; the test file, the
  command and what it printed are.
- **A flaw is a failing test first.** Write the test that shows it, watch it fail, fix the cause,
  watch it pass, keep it. A test that has never failed has not shown it can catch anything.
- **Fix the cause, not the symptom.** Before a fix, say why the flaw happens (the line, the
  missing constraint, the shared state) and test one hypothesis at a time. If three fixes for the
  same flaw have failed, stop patching: report it as a design problem (what keeps breaking, where)
  and ask before a fourth attempt.

`$SK` is the skills folder this skill is installed in. Works with stack-backend (how the API is
built and tested), docsync (a flaw found is a bug: its number, its register row, its changelog
line), bug-sweep, load-sim, perf-watch and triage-report, which read the same
[test matrix](references/test_matrix.md). **How** to try one attack is in the
[attack matrix](references/attack_matrix.md); **how** to make requests really race is in
[concurrency recipes](references/concurrency_recipes.md).

## The loop

| Step | What | Done when |
|---|---|---|
| 1. Plan | Acceptance criteria; the rules the feature keeps (whose data, which roles, which states, what may happen twice); the attacks: the feature's cells in the matrix (`matrix.py coverage --feature N`), pairwise cases for its axes (`matrix.py pairs who network timing --feature N`), and the attack matrix's rows for each | Written in the plan or brief |
| 2. Test first | Tests for the criteria, failing because the code is not there | Run, failing for that reason |
| 3. Build | The smallest change that passes them | Run, passing |
| 4. Break | The attacks from step 1, one test each, against the real API | Each attack has a test and a result |
| 5. Prove | Each attack that got through stays red until the cause is fixed; then green | Red seen, then green |
| 6. Check the test | Undo the fix (or remove the guard) and run once more: it must fail. Put the fix back | Seen failing without the guard |
| 7. Record | A bug number, the register row, the changelog line (docsync); every attack's row in the attack log (`attacks.py add`), whatever its result; the run (`attacks.py run`); the matrix cell's "Covered by" | In the same piece of work |
| 8. Report | `attacks.py report RUN-NNN`, plus the before and after of each fix | Given to the user |

A flaw found in code nobody asked you to change is still recorded (a register row under Open,
with its severity), even if it is not fixed in this sitting.

## The project's files

| What | Default path | Start from |
|---|---|---|
| Test matrix | `docs/testing/test_matrix.md` (`[harden] matrix`) | [references/test_matrix.md](references/test_matrix.md), the generic SaaS example |
| Axes | `docs/testing/axes.toml` (`[harden] axes`) | [references/axes.toml](references/axes.toml) |
| Attack log and bug register | `docs/testing/attack_log.md`, `docs/testing/bug_report.md` (`[docsync]`) | written by docsync's `attacks.py` |
| Isolation sweep config | `sweep.toml` | [references/sweep.example.toml](references/sweep.example.toml) |

```bash
M="python3 $SK/harden/scripts/matrix.py"
$M coverage [--feature 3.1] [--missing]     # every cell: covered (its test or attack exists) or not yet
$M stale                                     # built features with no cell; features changed since the review
$M pairs who network timing --feature 3.1    # every pair of these axes' values in a few cases
```

## Whole-codebase mode

Asked to harden "everything" or to "penetration test" it, work from the gaps, worst first:

1. `matrix.py stale`: a built feature with no cell gets one first.
2. `matrix.py coverage --missing`, ordered: money and another tenant's data (Critical if they
   break), then sign-in and roles, then offline and sync, then the rest.
3. The machine sweeps, which cover every route at once:
   `isolation_sweep.py --config sweep.toml` (every record route x another tenant), then the same
   with B as each role.
4. One cell at a time through the loop; a run is a group of cells (`attacks.py run`).
5. Load at the end, with load-sim.

Say at the start how many cells the run will take, and at the end how many it covered.

## The rules a multi-tenant API must keep

| Who asks | For what | Answer |
|---|---|---|
| Anyone | A record of another tenant, named by its id, with their own tenant's header | **404**, the same as an id that does not exist |
| Anyone | With another tenant's header (no role there) | **403** |
| A role without the permission | The action | **403**, nothing changed |
| A member | A record in their tenant outside their scope | **403** |
| A platform operator | A tenant's records | Read only, through audited support access |
| A client sending a change twice | The same idempotency key, account, tenant, method, path and body | The kept answer (`Idempotency-Replayed: true`); nothing runs again. While the first runs: 409 with `Retry-After`. Same key, other body: 422 |

Write these into the project's test matrix with the project's own words.

## Tools

| Need | Use |
|---|---|
| Every record route aimed at another tenant | `isolation_sweep.py --config sweep.toml [--writes] [--dry-run] [--base-url URL]`: reads the OpenAPI document; prints each 2xx for the attacker as a CANDIDATE |
| Hostile input on one route, and a burst on it | `adversarial_runner.py --url ... --fuzz` and `--concurrency 20 --requests 200` (this machine only unless `--allow-host`) |
| Requests that really race | Each request on its own session and connection, held at a gate until all have read: [concurrency recipes](references/concurrency_recipes.md) |
| A dependency failing | Patch the call to raise (cache, email, payment); safe helpers must degrade, critical ones fail visibly |
| The migrations, not `create_all` | A test that runs the real migration chain |
| Many tenants at once | load-sim |

**A check in Python is not a guard against a race; a constraint or a lock is.** Fixes, in order: a
unique constraint (and the 409 it gives), `SELECT ... FOR UPDATE` on the row being decided, an
idempotency claim.

## Offline and sync

Offline changes fail silently: the person sees "saved", and the server decides hours later. Every
change that may wait on a device is tested against every timing and every "meanwhile" (matrix
section 3.2), not pairwise: sent twice, sent together, the answer lost after the commit, the device
clock behind and ahead, the member removed meanwhile, another account signing in on the device.
Money is never queued.

## Load

Only against this machine or a test server, never production, and bounded (a number of requests,
a time limit). Say the expectation first (requests, concurrency, the acceptable p95, zero 5xx).
Report the load tried, not a capacity: "200 requests at 20 at once, p95 140 ms, no 5xx, on a
laptop" is a result; "handles 1,000 customers" is not, without a test at that size.

## Safety

- Attack only this repository's code on this machine, a test server, or a server the user named.
  Never production, never another party's system.
- Prove a flaw with the least that shows it: a test, a row count, a status code. No real personal
  data in tests or reports.
- A flaw that lets one tenant see another's data, or someone act without the permission, is
  Critical: tell the user at once, and record it under `Security` in the changelog when fixed.

## The attack log

Every attack is written down as it is made, so nothing tried is lost between sessions:

```bash
A="python3 $SK/docsync/scripts/attacks.py"
$A add "Billing" "One invoice paid twice at the same moment" --test tests/test_pay_race.py::test_paid_once --fixed BUG-059
$A add "Billing" "Two refunds at once" --test tests/test_refunds.py::test_two_at_once_refund_once --held
$A add "Web" "A javascript: link in a comment" --not-a-flaw
$A add "Search" "Another workspace's projects in results" --open BUG-070
$A run "Billing and payments" --attacks ATK-022 ATK-030 --tests "uv run pytest: 412 passed" \
    --load "160 at 20 at once, p95 180 ms, no 5xx, laptop" --not-tried "the provider's webhook signature"
$A report RUN-003
```

A result is **Held** (it did not get through; a test keeps it so), **Fixed BUG-NNN**, **Open
BUG-NNN** or **Not a flaw** (the row says why). Held and Fixed name their test; docsync's checker
refuses a test that does not exist.

## The report

```markdown
## Harden: <feature>

**Tests run:** `<command>`: <n> passed, <n> failed (<time>). New: `<file>::<test>`, ...

| Attack | Test | Before the fix | Fix | After |
|---|---|---|---|---|
| Five creates at once | `tests/test_concurrency.py::...` | 5 rows | unique index | 1 row, four 409 |

**Bugs:** BUG-0NN (severity): <one line each>, or none found.
**Load:** <requests, concurrency, p50/p95/p99, 5xx, where it ran>, or not run and why.
**Not tried:** <what, and why>.
```

Say which results were run and which are reasoning.

## Definition of done

- [ ] Acceptance criteria hold, shown by tests that were run
- [ ] Each rule above that the change touches has a test
- [ ] Each planned attack has a test and a result; each flaw was seen failing, fixed, passing, and failing again without the fix
- [ ] Each flaw has a bug number, a register row and a changelog line
- [ ] The suite still passes; what was not tried is in the report
- [ ] Every attack has its row in the attack log, and the matrix's cells say what covers them
