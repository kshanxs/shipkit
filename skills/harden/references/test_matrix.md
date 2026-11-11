# Test matrix

Reviewed: 2026-11-11

The combinations this project is tested against, shared by the harden, bug-sweep, load-sim,
perf-watch and triage-report skills. The [attack matrix](attack_matrix.md) says how to try one
attack; this page says which combinations of who, where, when and how must be tried, and which
have been.

This copy is the generic SaaS example (a workspace is the tenant). Copy it to
`docs/testing/test_matrix.md` (or the path in `[harden] matrix` of `shipkit.toml`), replace the
feature numbers with your tracker's, and keep it current.

```bash
M=<skills dir>/harden/scripts/matrix.py
python3 $M coverage            # every cell: covered (its test or attack exists) or not yet
python3 $M stale               # features Built or Partly with no cell, and features changed since the review date
python3 $M pairs network timing device --feature 3.1    # the pairwise cases to write for these axes
python3 $M pairs --all-axes --limit 40                  # every axis, pairwise
```

## 1. How many combinations, and which

Every combination of every axis is millions of tests. That cannot run, and most of it would test
the same code path again. The matrix uses three rules:

| Rule | Where | What it means |
|---|---|---|
| **Full** | Who x whose data x action, on every route | Every route, every role, every tenant relation. Done by machine: `isolation_sweep.py` over the OpenAPI document, and a role-policy test in the app |
| **Full** | Every change that may be queued offline x network x timing x device | Offline routes are few and their bugs are silent. Every combination is a case |
| **Pairwise** | Everything else | Every pair of axis values appears in at least one case. Most bugs need two conditions at once, rarely three; `matrix.py pairs` generates the set |

A cell names its feature by tracker number (`docs/feature_status.md`, rows written
`| 2.1 Name | Status | note |`). A feature marked Built, Partly or Backend only with no cell here
is a gap: `matrix.py stale` lists it.

## 2. The axes

The values `matrix.py pairs` combines are in [axes.toml](axes.toml): who, data, network, timing,
device, meanwhile, dependency, change and scale.

## 3. Cells

Covered by: an attack in the attack log (`ATK-NNN`), a test (`path::name`), or `Not yet`.
`matrix.py coverage` checks that what is named exists. Write `Not yet` rather than leaving a cell
out: a cell not yet covered is the next thing to try.

### 3.1 Every route

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-001 | 1.2 | Every workspace route x another workspace's records, with B's owner and B's header, reads and writes | No 2xx; 404 for a foreign ID | Not yet |
| M-002 | 1.2 | Every workspace route x owner, admin, member, viewer, guest inside one workspace | Only what the role policy allows | Not yet |
| M-003 | 1.1, 1.2 | Switch into a workspace or role the person does not hold | 403 | Not yet |
| M-004 | 1.2 | A platform operator token on every workspace write route | Refused, or audited support access only | Not yet |
| M-005 | 1.3 | An API key used past its scopes, after revocation, from another workspace | 403 / 401 | Not yet |
| M-006 | 1.2 | Every changing route x the same `Idempotency-Key` from a second account of the same workspace | Runs as a new change; not the first account's answer | Not yet |

### 3.2 Offline and queued changes (mobile and PWA clients)

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-101 | 4.1 | Sent twice in a row, same key and body | Second is the kept answer; nothing runs again | Not yet |
| M-102 | 4.1 | Same key, different body | 422 | Not yet |
| M-103 | 4.1 | Same key twice at once, each request on its own connection | One runs; the other 409 or the replay | Not yet |
| M-104 | 4.1 | Answer lost after the server committed, then resent | Replay; one row, one audit entry | Not yet |
| M-105 | 4.1 | Device clock 10 min ahead | Refused or server time used, as the spec says | Not yet |
| M-106 | 4.1, 1.2 | Queued, then the member is removed before it arrives | 403; kept as refused on the device | Not yet |
| M-107 | 4.1 | Session expired with changes waiting; another person signs in on the device | Nothing of the first account is sent or shown | Not yet |
| M-108 | 4.1, 5.1 | A payment made offline | Fails and says so; never queued | Not yet |

### 3.3 Sign-in and identity

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-201 | 1.1 | Wrong codes or passwords together; the right code twice at once | Tries counted under a lock; one session | Not yet |
| M-202 | 1.1 | A verified code with another account's ID or email in the body | The session belongs to what the code proved, only | Not yet |
| M-203 | 1.1 | Sign-up naming an email that already has an account | No takeover; 409 or the sign-in flow | Not yet |
| M-204 | 1.1 | Deactivated user signs in, refreshes, uses an old access token | 403 / 401; refresh tokens revoked | Not yet |
| M-205 | 1.4 | Invite link used twice, after expiry, by another email, after the inviter lost the right | Refused | Not yet |
| M-206 | 1.1 | Reset link used twice, expired, to an unconfirmed address | Refused; same answer for every account state | Not yet |

### 3.4 Money

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-301 | 5.1 | Two upgrades of one subscription at once | Charged once | Not yet |
| M-302 | 5.1 | Amounts finer than the currency's smallest unit, or over the column | 422 | Not yet |
| M-303 | 5.2 | Payment webhook twice, late, out of order, with a bad signature | Paid once; a bad signature changes nothing | Not yet |
| M-304 | 5.2 | Refund twice at once; refund more than paid; refund while pending | One refund; refused; counted as pending | Not yet |
| M-305 | 5.1 | Downgrade with more seats in use than the new plan allows | Refused or seats chosen; never silently over | Not yet |
| M-306 | 5.2 | Payment provider failing or slow during checkout | No paid state without a confirmed payment | Not yet |

### 3.5 Records, imports and files

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-401 | 2.1 | CSV import saved twice at once | One import | Not yet |
| M-402 | 2.2 | Formula in a name, in every export | Exported as text | Not yet |
| M-403 | 2.3 | `javascript:` and other schemes in links, markup in rich text | Refused or escaped | Not yet |
| M-404 | 2.4 | Upload with a path in its name, an SVG with script, a file over the limit | Refused or sanitised | Not yet |

### 3.6 Load and failure

| Cell | Features | Combination | Expected | Covered by |
|---|---|---|---|---|
| M-501 | 2.1, 3.1 | 500 workspaces, the Monday-morning peak (load-sim `peak` profile) | No 5xx; p95 under 800 ms; pool under 80% | Not yet |
| M-502 | 5.1 | 500 workspaces, billing day: renewals and upgrades at once | No duplicate charge or invoice | Not yet |
| M-503 | 1.2 | Rate limits behind one office address | Each person their own limit; an address ceiling | Not yet |
| M-504 | 4.1 | Cache down while changes are replayed | Keys still claimed in the database; no duplicate | Not yet |
| M-505 | 3.2 | One notification to every member of a large workspace | Queued, not sent inside the request; each member once | Not yet |
