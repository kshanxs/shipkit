# Attack matrix

What to try against a change, what a flaw looks like, and what holds. Each row
is a test to write (see [the skill](../SKILL.md) for the loop and the tools).
"Holds" is the behaviour to assert; write where your code does it next to each
row you adopt.

## 1. Input

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Size | A text field of 100,000 characters; a list of 10,000 items | 500, a slow answer, a column error | 422 from a `max_length` / `max_items` on the schema |
| Empty and blank | `""`, `"   "`, `null` in a required field, `[]` | Saved as blank, or 500 | 422; trim before checking "already exists" |
| Numbers | `0`, `-1`, `2**63`, a float where an integer goes, `NaN` | Negative amounts, overflow 500, `NaN` in JSON | `ge=` / `le=` on the field; money in `Decimal` |
| Text | A null byte `\x00`, right-to-left marks, emoji, `<script>`, `' OR '1'='1` | 500 from the driver; markup shown as HTML | 422 or stored as text and escaped on screen (the ORM binds parameters; the UI framework escapes) |
| Unknown fields | `{"workspace_id": 2, "role": "owner", "is_active": true}` | The service uses a field the schema does not declare | The schema ignores or refuses unknown fields; the attack is whether the service reads the raw body or takes the tenant from it. The tenant always comes from the verified context |
| Files | A CSV import with 50,000 rows, a wrong type, a formula (`=HYPERLINK(...)`) | Memory, a hang, a formula run in a spreadsheet | The import's row limit and preview; values that start with `=`, `+`, `-`, `@` exported as text |

## 2. Whose data, which role

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Another tenant's record | Tenant A's token and header, tenant B's record id in the path or the body | 200 with B's data, or 403 (which says the id exists) | **404**, as for an id that does not exist |
| Another tenant's header | Tenant A's user, the tenant header of B | 200 | **403** (a role there is required) |
| Missing permission | A viewer calls a write route; a member an admin route | The action runs | **403** from the permission check, and nothing written |
| Outside the scope | A guest asks for a project they were not invited to; a member edits another team's record | 200 | **403** |
| A platform operator writing | An operator token on a tenant's write route | The write runs | Refused, or only through audited support access |
| Ids in lists | A list endpoint filtered by `project_id` of another tenant | An empty 200 (which confirms nothing but leaks the shape) | 404 for the foreign id |

## 3. Twice, together, out of order

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Double submit | The same create five times at once (`racing_client`, `all_read_before_any_writes`) | More than one row | A unique constraint (409), or a row lock |
| The same change resent | The same body and `Idempotency-Key` twice; then once more while the first runs | Done twice | The kept answer, `Idempotency-Replayed: true`; 409 with `Retry-After` while running |
| Lost update | Two edits of one record at once with different fields | One silently lost | The later stands, on purpose; or a version check (`If-Match`, a version column) where losing one is wrong |
| Out of order | Pay before the invoice is issued; publish before review; edit after delete | A state that should not exist | The service checks the state and refuses (400 or 409); a deleted record is out of every read |
| Replay | A used one-time code, a used invite link, a payment webhook twice | Accepted again | Marked used in the same transaction; the webhook's event id kept |
| Late offline write | A change sent from a device's outbox long after it was made | Silently accepted or silently lost | Judged by the spec's rule (accepted and flagged, refused with a reason, or sent for approval) |

## 4. Failures

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Cache down | Patch the cache call to raise `ConnectionError` | 500 on a read | Safe helpers answer from the database; critical ones (one-time codes) fail visibly |
| Error halfway | Raise inside a service after its first write | A half-made record | The request's transaction rolls back; assert no rows, on a fresh session |
| A slow or failing provider | The SMS, email or payment call times out | The request hangs, or the change is lost | A timeout; the change kept and retried, or refused with a reason |
| Commit fails after the answer | Make the commit raise | 2xx answered, nothing saved | The commit happens before the answer is sent, on every route, held by a test |

## 5. Load

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| A burst | 200 requests, 20 at once, on one route | 5xx, pool exhausted | No 5xx; latency within the stated p95 |
| An expensive route | A report or export with the widest filters, repeated | Seconds per request, the pool held | Pagination, limits, an index (`EXPLAIN ANALYZE`), the rate limit |
| Sign-in | Many codes for one address; many accounts from one IP | Codes sent without limit | The rate limit and CAPTCHA, counted wrong codes |

## 6. Offline and sync

The combinations to run are test matrix section 3.2.

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Replay a device's change | The same idempotency key and body again, from the same and from another account | Done twice; another account given the first answer | The kept answer, for the same account only |
| Backdate a change | A queued-at time in the past with a key made now, or a key that is not time-ordered (UUIDv7) | Taken by the device's word | Device time believed only when the key's own time agrees |
| Forward-date | A queued-at time ahead of the server | Changes dated in the future | 422 |
| Someone else's change | Another member, another tenant, at every timing | Any timing opens it | Refused at every timing |
| The world changed meanwhile | Role removed, record archived, plan downgraded, between making the change and sending it | Written as if nothing changed | Judged on arrival by the route's own rules |
| Lost answer | The server commits, the answer is lost, the outbox sends again | Two rows, two audit entries | The replay |
| Reconnect storm | Many outboxes drain at once after an outage | 5xx, pool exhausted, out-of-order rows for one device | No 5xx; per device, oldest first |
| The device after sign-out | Sign out offline with changes waiting; read the device storage | Another person's data or changes left behind | Empty; a shared computer writes nothing |
| Money offline | A payment with no connection | Queued, then paid twice | Fails and says so; money is never queued |

## 7. Identity and sessions

Sign-in bugs are the most often Critical: a session issued for someone other than the person who
proved the code.

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Session for another account | A verified code with another user's id or email in the body | A session as that person | The session belongs to what the code proved, only |
| Sign-up over an existing account | Sign-up naming an email that has an account | Takeover | 409, or the sign-in flow |
| Codes | Two live codes for one address; guesses together; the right code twice at once | The old code works; extra guesses; two sessions | Issuing one ends the others; tries counted under a lock |
| Deactivated | Sign in, refresh, use an old access token | It works | 403 / 401; refresh tokens revoked |
| Second factor | One TOTP or recovery code sent twice at once | Two sessions | Row locked while checked |
| Invites and resets | A link twice, expired, by another email; after the inviter lost the right | Account changed or joined | Refused; same answer for every account state |
| Roles | Giving a role one does not hold, or in another tenant; acting past it | Granted | 403 |

## 8. Money

| Attack | Try | A flaw looks like | Holds |
|---|---|---|---|
| Another tenant's account | A checkout that routes money to another tenant's payout account | Money in the wrong account | The account comes from the server, never the request |
| Webhook | Twice, late, out of order, bad signature, for another tenant's order | Paid twice; changed by an unsigned call | One payment per provider payment id; signature checked first |
| Refunds | Two at once, more than paid, while one is pending | Refunded twice or over | One; never over; pending counted as such |
| Reconciliation | A settlement line missing, repeated, or of another tenant | Matched silently | Flagged for a person |
| Provider down | The provider fails or times out mid-payment | Marked paid without a confirmed payment | Paid only on confirmation; the checkout can be tried again |
