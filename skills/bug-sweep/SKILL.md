---
name: bug-sweep
description: "Review new commits, or sweep a whole branch area by area, for bugs, crashes, cross-tenant data leaks, permission gaps, offline and sync errors, race conditions, idempotency and money errors, cross-site requests and DNS rebinding on self-hosted servers (only the kinds the project profile has), starting from the test matrix's gaps; verify every finding before reporting it, and report through triage-report. Read-only on the remote. Use when asked to review new commits, hunt for bugs, sweep the codebase, find bugs, or penetration test the project."
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

## The project profile

Run `python3 $SK/switchboard/scripts/project.py show` first (`$SK` is the skills folder this skill is
installed in). An area or checklist item marked
**[multi-tenant]**, **[money]**, **[accounts]**, **[offline]**, **[hosted]**, **[self-hosted]**,
**[cli]** or **[shell]** applies only when the profile lists that trait: skip the others, and name
what you skipped in the report's "not tried" list. Unmarked items apply to every project.

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

| Area | Applies when | Look at |
|---|---|---|
| Sign-in and identity | **[accounts]** | Sign-up, codes, sessions, refresh, second factor, invites, password reset, account linking |
| Access control | **[auth]** | The one password, token or API key: where it is checked, stored and compared; routes that skip it |
| Tenant context and dependencies | **[multi-tenant]** | How the tenant is resolved and checked on every route |
| Local network exposure | **[self-hosted]** | Bind address, Origin or CSRF checks on every change, the Host header (DNS rebinding), what answers without a password |
| Offline cache and sync | **[offline]** | Outbox, idempotency keys, device time, sign-out wipe, shared devices |
| Billing and money | **[money]** | Checkout, webhooks, refunds, reconciliation, plan changes, seats |
| Core records | every project | The main entities or files: create, edit, archive, delete, export |
| Imports, exports and files | every project | CSV import, exports, uploads, generated documents, paths built from input |
| Search, reports and analytics | **[server]** | Global search, dashboards, aggregates that cross users or tenants |
| Notifications and messages | **[server]** | Email, push, in-app, fan-out to many recipients |
| Operator console and support access | **[hosted]** | Admin routes, impersonation, demo and test routes |
| Command line and scripts | **[cli]** or **[shell]** | Arguments reaching a shell, unsafe temp files, exit codes, running twice, partial failure |
| Background jobs and scale | every project | Jobs crossing users or tenants, unbounded loops, work that grows with the data |

References: the bug register (do not re-report known ids; check closed ones for regressions), the
attack log, and the two matrices.

## C. Checklist (every item, every file)

- **Tenant isolation** **[multi-tenant]** (the most important): settle the enforcement model first (how the tenant
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
- **Sign-in and sessions** **[accounts]** (attack matrix section 7): a session issued for anyone but who proved the
  code; sign-up over an existing account; old codes still live; tries counted without a lock;
  deactivated users refreshing; reused second-factor codes; test-auth gating.
- **Offline and sync** **[offline]** (section 6): a queued route that is not idempotent without its key, or moves
  money; a key not scoped to account and tenant; a device time believed without proof; a queued
  change not checked again on arrival; device data left after sign-out.
- **Races:** read-then-write without a constraint or row lock: counters, a record or upload saved
  twice, two runs of one job at once; with **[money]**, a double payment, refund or invoice.
- **Idempotency:** replay gives `Idempotency-Replayed: true`; in flight gives 409 and `Retry-After`;
  same key with another body gives 422; keys scoped per tenant and user.
- **Local network** **[self-hosted]**: a state change accepted from another website (no Origin or
  CSRF check on every POST, PUT, PATCH and DELETE); a Host header not checked against an allow-list
  (DNS rebinding turns a browser on the LAN into an attacker); listening on every interface without
  a password; secrets or tokens readable by other users on the machine, or written to logs.
- **Scripts and the command line** **[cli]** **[shell]**: input reaching `sh -c`, `eval` or an
  unquoted variable; temp files in a shared folder with a guessable name; a failure halfway that
  leaves the machine broken; a second run that does damage; `set -euo pipefail` missing.
- **Money** **[money]** (section 8): decimals everywhere (no float), rounding, partial payments, refunds (twice,
  over, pending), the account from the server, the mock provider refused in production, webhook
  signature, replay and order.
- **Time:** the user's or tenant's today instead of `date.today()`; day boundaries across time zones; a change
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
