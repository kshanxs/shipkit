---
name: bug-sweep
description: "Review new commits, or sweep a whole branch area by area, for bugs, crashes, cross-tenant data leaks, permission gaps, offline and sync errors, race conditions, idempotency and money errors, starting from the test matrix's gaps; verify every finding before reporting it, and report through triage-report. Read-only on the remote. Use when asked to review new commits, hunt for bugs, sweep the codebase, find bugs, or penetration test the project."
---

# Bug sweep: new commits, a whole-branch sweep, and the matrix

Adapted from public skill patterns (MIT and Apache-2.0): getsentry `find-bugs` and
`security-review` (full diff, attack surface, checklist, verify, pre-conclusion audit),
claude-code-security-review (high-confidence findings with exploit scenarios), multi-tenant
isolation audits (the enforcement model first, asymmetric paths, jobs and cache keys), IDOR hunts
and systematic debugging.

Works with the harden skill's [test matrix](../harden/references/test_matrix.md) and
[attack matrix](../harden/references/attack_matrix.md) (what to try), harden (how a flaw becomes a
failing test and a fix), load-sim and perf-watch (what breaks at scale), and triage-report (the
report). Project specifics live in the project's matrix and `[bug_sweep]` of `shipkit.toml`
(`branch`, `areas`).

## Rules

- **Read-only on the remote.** Do not push, comment, open issues or pull requests.
- Repros run on a throwaway local stack with seeded test data and dev-only test auth, never
  production, a hosted shared database or real people's data.
- A fix happens only when the user asks; it goes on a new branch with a pull request.
- Report only what you can evidence. If nothing significant turns up, say so.
- Before giving a bug a number (BUG-NNN, ATK-NNN), check the numbers taken on every open pull
  request, not only on the branch: two branches taking one number is a merge conflict later.

## A. New commits (every run)

1. Find the last-reviewed SHA in your notes (or the handoff file). Then
   `git log --oneline <last>..<branch>` and `git diff <last>..<branch> --stat`. Read every changed
   file in full at the head, not only the hunks.
2. Map the attack surface per file: inputs (path, query, body, headers: the tenant header,
   idempotency and queued-at headers), queries, permission checks, state writes, external calls
   (payments, email, storage), background jobs and cache keys.
3. The blast radius: callers of changed functions (`git grep`), routes sharing a changed
   dependency, migrations (data loss, NOT NULL without a default, a missing index or constraint),
   tests changed or deleted alongside.
4. A new feature or route: find its cells in the matrix (`matrix.py coverage --feature N`). If it
   has none, write them (or note them for the report) before checking it.
5. Run the checklist (C) for every changed file, then verify (D).
6. Record the new last-reviewed SHA.

## B. Whole-branch sweep (one area per run, or all on request)

Start from the gaps, not the top of the list:

```bash
M="python3 $SK/harden/scripts/matrix.py"
$M stale               # built features with no cell
$M coverage --missing  # cells nobody has tried; Critical-prone areas first
```

Areas, a generic SaaS list; replace with your own under `[bug_sweep] areas`:

| Area | Look at |
|---|---|
| Sign-in and identity | Sign-up, codes, sessions, refresh, second factor, invites, password reset, account linking |
| Tenant context and dependencies | How the tenant is resolved and checked on every route |
| Offline cache and sync | Outbox, idempotency keys, device time, sign-out wipe, shared devices |
| Billing and money | Checkout, webhooks, refunds, reconciliation, plan changes, seats |
| Core records | The main entities: create, edit, archive, delete, export |
| Imports, exports and files | CSV import, exports, uploads, generated documents |
| Search, reports and analytics | Global search, dashboards, cross-tenant aggregates |
| Notifications and messages | Email, push, in-app, fan-out to large tenants |
| Operator console and support access | Admin routes, impersonation, demo and test routes |
| Background jobs and scale | Jobs crossing tenants, unbounded loops, per-request work that grows with tenants |

References: the bug register (do not re-report known ids; check closed ones for regressions), the
attack log, and the two matrices.

## C. Checklist (every item, every file)

- **Tenant isolation** (the most important): settle the enforcement model first (how the tenant
  header is resolved against the token's memberships). Then look for:
  - a `select` or `get` by id without the tenant filter
  - a list scoped by tenant but its detail, update, delete, export or file download not
  - the tenant taken from the body or query instead of the context
  - cache keys, idempotency keys, file paths or search indexes without a tenant segment
  - jobs, webhooks and operator paths crossing tenants
  - expected: another tenant's id with your own header is 404, a foreign header is 403, an operator
    is read-only
- **Authorization:** a missing permission check, role escalation through a client header, a guest
  past their project, a member editing another's record, demo or test routes reachable outside
  development.
- **Sign-in and sessions** (attack matrix section 7): a session issued for anyone but who proved the
  code; sign-up over an existing account; old codes still live; tries counted without a lock;
  deactivated users refreshing; reused second-factor codes; test-auth gating.
- **Offline and sync** (section 6): a queued route that is not idempotent without its key, or moves
  money; a key not scoped to account and tenant; a device time believed without proof; a queued
  change not checked again on arrival; device data left after sign-out.
- **Races:** read-then-write without a constraint or row lock: double payment, refund or invoice;
  counters; imports saved twice.
- **Idempotency:** replay gives `Idempotency-Replayed: true`; in flight gives 409 and `Retry-After`;
  same key with another body gives 422; keys scoped per tenant and user.
- **Money** (section 8): decimals everywhere (no float), rounding, partial payments, refunds (twice,
  over, pending), the account from the server, the mock provider refused in production, webhook
  signature, replay and order.
- **Time:** the tenant's today instead of `date.today()`; day boundaries across time zones; a change
  queued before midnight and sent after.
- **Async:** blocking I/O in async code, a missing `await`, a session shared across tasks. Python:
  `uv run ruff check --select ASYNC,S,B`.
- **Data and injection:** raw SQL with f-strings, formula injection in exports and imports, path
  traversal on uploads, XSS where user HTML is rendered, personal data or secrets in logs or code.
- **Robustness and scale:** unbounded lists, N+1 (perf-watch), 500s from an unvalidated enum or
  `None`, migrations unsafe for big tables.
- **Front end:** token storage, role-gated UI the API does not enforce, cached data or a queued
  change surviving a sign-out and reaching another account.

## D. Verify before reporting (kill false positives)

- Check whether a dependency, base query or test already handles it (`git grep` the tests).
- Reproduce: a minimal test with the project's fixtures, a `curl` with locally minted tokens, or
  `isolation_sweep.py --only <regex>`. Keep the repro outside the repository (a temp folder) and
  paste it into the report; do not commit it.
- Numbers: list the ids on every open pull request before naming a new one.
- Severity: Critical (cross-tenant read or write, auth bypass, a session as someone else, money
  lost), High (privilege escalation inside a tenant, personal data leak, double-charge race),
  Medium (500, wrong data, an unbounded query), Low (hardening, logging).
- Pre-conclusion audit: the files read, each checklist item clean or with a finding, the matrix
  cells tried, and what could not be verified and why.

Report through triage-report. The cells tried go in its coverage table; a held cell is recorded
with `attacks.py add` once a test holds it.
