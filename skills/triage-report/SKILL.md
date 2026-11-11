---
name: triage-report
description: "Turn a bug sweep, penetration test, load simulation or monitoring run into the final report, ranked by severity: every issue with evidence, a repro, file and line links at the exact commit, a suggested fix, stats tables, the test-matrix coverage the run achieved, and what was not tried. Read-only: the report goes to the user, never to an issue tracker unless asked. Use when a bug sweep, load-sim or perf-watch run is done, or the user asks for an issues report, a triage report, or findings ranked by severity."
---

# Triage report

Adapted from public report formats (getsentry `find-bugs`, claude-code-security-review finding
fields and false-positive discipline, perf results reporting; MIT and Apache-2.0). Read-only: the
report goes to the user in chat (or a document if asked). Never post issues, comments or pull
requests unless the user explicitly asks.

Works with bug-sweep, load-sim, perf-watch and harden, whose shared test matrix is what the
coverage section reports against. The repository's web address and the time zone come from
`[triage] repo_url` and `[triage] timezone` in `shipkit.toml` (default: the `origin` remote, UTC).

## Rules

- **Every issue needs evidence:** a request and its response, a test output, a log line, a query
  stat or a code line. Anything without it goes under "Suspected, unverified".
- **Link code at the exact SHA:** `<repo_url>/blob/<sha>/<path>#L40-L58`. Name the commit that
  introduced it when you know it.
- **Redact:** no tokens, one-time codes, passwords, `.env` values or real-looking personal data.
  Seeded `.test` people only.
- **Dedupe** against the bug register (cite `BUG-NNN` if it exists or regressed) and your previous
  reports.
- **Numbers no one else holds:** before naming a new BUG-NNN or ATK-NNN, check the register and the
  attack log on the branch **and on every open pull request**; say which you checked.
- **Say what ran and what is reasoning.** A load figure names its run (profile, tenants, rps,
  machine); a capacity no run showed is an estimate and is labelled so.

## Severity

| Level | Meaning |
|---|---|
| Critical | Cross-tenant read or write, auth bypass, money lost or duplicated, a production-only guard missing (test auth, mock payments) |
| High | Privilege escalation inside a tenant, personal data exposed, a race that corrupts records, 5xx above 1% under normal load, pool exhaustion |
| Medium | A crash on valid input, wrong data or totals, p95 over its target, N+1 or an unbounded query, one office's normal use throttled by the rate limit |
| Low | Hardening, logging, minor performance, an inconsistency |

Within a level, sort by blast radius: tenants affected x users x frequency.

## Report layout

```
# Triage report: <repo>@<branch> <short-sha> (<date and time zone>)
Scope: commits <a>..<b> | sweep area: <area> | load: <N> tenants, <profile> at <rps> | matrix: <covered>/<cells> cells
Verdict: <n> Critical, <n> High, <n> Medium, <n> Low | thresholds PASS/FAIL

## Top 3 to fix first
1. ...

## Issues
### [C-1] <one-line title>  (Critical | security/tenant-isolation)
- Where: <link#Lx-Ly> (introduced in <sha>, if known)
- What: <what is wrong, two or three sentences>
- Impact: <who can do what to whom; tenants and users affected>
- Evidence: <request + status + trimmed body / test output / stat with its window>
- Repro: <curl with $TOKEN_A placeholders, or a test, or the load profile>
- Expected vs actual: <404 vs 200 ...>
- Suggested fix: <concrete; a code sketch is fine; and the regression test>
- Confidence: high/medium   Related: BUG-NNN / ATK-NNN
```

## Matrix coverage

Run `matrix.py coverage` (harden skill) before and after, and report the change:

| Area (matrix section) | Cells | Covered before | Covered after | Held | Fixed | Open | Not tried |
|---|---|---|---|---|---|---|---|

Then list the cells this run tried, by id, with their result, and the cells still "Not yet" in the
areas it was asked to cover. A cell the run covered gets its "Covered by" updated in the same piece
of work.

## Offline and sync

A section of its own whenever the run touched an outbox, idempotency claims or device time: what
was sent (changes, timings, senders, deliveries), what came back, and any change written twice,
written as someone else, taken on the device's word when it should not have been, or lost.

## Stats appendix (from perf-watch)

1. Run summary: profile, rate, duration, total requests, RPS average and peak, error %, thresholds.
2. Endpoints: the top 20 by p95, then the worst 10 by error %:
   `| Endpoint (route template) | Role | Count | RPS | p50 | p95 | p99 | Max | Err % | Top status |`
3. Status codes by role and by tenant.
4. Rate limiting: 429s per tenant address, and when the first came under the realistic profile.
5. Database: slow queries, N+1 routes, pool peak, lock waits, sequential scans on big tables.
6. Runtime: CPU and RSS peaks, their trend, event-loop stalls, cache hit ratio and memory.
7. Outside providers (mocked): calls per provider; duplicates; any real outbound call.
8. Seed sanity: rows per tenant, number of tenants, database size; the isolation sweep's routes,
   passes and candidates.
9. Scale: the same routes' p95 at two sizes; the demand estimate against what the run achieved.

## Closing sections

- **Fixed since the last report / regressions**, with links.
- **Suspected, unverified:** each with why it is unconfirmed and how to confirm it.
- **Not tried / blocked:** areas skipped, tool failures, approvals needed.
- **Next run:** which area comes next, and which commits are still pending review.

Keep the chat summary short: the verdict line, the top 3, and the issue titles with severity. Put
the full report in a file or a document when it runs long.
