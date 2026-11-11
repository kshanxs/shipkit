# Offline-first sync: the device database and the protocol

Drizzle on Expo SQLite gives a typed schema, generated migrations and live queries; it has no sync
engine. This is the engine to build, and the contract the API must offer. It does not depend on
the database: the same protocol fits WatermelonDB, op-sqlite or PowerSync-style stores.

## Layout

```
src/db/
├── index.ts            # opens the database (enableChangeListener: true) and exports `db`
├── schema/             # one file per table, and index.ts re-exporting them
├── queries/            # typed queries and the only writes; screens import these
├── sync/
│   ├── run.ts          # the one sync run: pull, then push; never two at once
│   ├── pull.ts         # applies a pull in one transaction
│   ├── push.ts         # collects pending rows and tombstones, sends them
│   ├── scope.ts        # what this role pulls
│   └── triggers.ts     # foreground, connectivity back, after a write (debounced)
└── testing.ts          # the same schema and migrations in memory, for Jest
drizzle/                # generated migrations and their journal
drizzle.config.ts       # dialect 'sqlite', driver 'expo'
```

## Schema rules

1. Table and column names are the API's. TypeScript keys are the camelCase form, nothing else.
2. Enums are the API's strings, declared once and given to the column (`text('status').$type<Status>()`).
3. Nullability matches the API's schema.
4. The primary key is a text `id` that never changes. A record made on the device gets a UUID
   there; the server keeps it as its `sync_id`. The server's own integer id travels as `server_id`.
5. Every syncable server table has `updated_at` (set by the server) and is soft-deleted
   (`is_deleted`), so a deletion reaches devices that were offline.
6. Index every foreign key and every column a screen filters by (a date, `sync_status`).
7. A schema change is made in `src/db/schema/`, then `drizzle-kit generate`; both are committed.
   A shipped migration is never edited.
8. Dates as `YYYY-MM-DD` text, datetimes as integer `timestamp_ms`, money as decimal strings.

## The run

```typescript
export async function runSync() {
  const cursor = await readLastPulledAt()
  const { changes, timestamp } = await api.pull({ last_pulled_at: cursor ?? 0, schema_version: SCHEMA_VERSION })
  await applyPull(changes, timestamp)            // one transaction; saves the new cursor
  const pending = await collectPending()         // rows with sync_status = 'pending', and tombstones
  if (!isEmpty(pending)) await api.push({ changes: pending, last_pulled_at: timestamp })
}
```

| Piece | How |
|---|---|
| Pull cursor | `sync_state.last_pulled_at`, written in the same transaction as the pulled rows |
| Local changes | `sync_status = 'pending'`, set by every local write |
| Applying a pull | Upsert `created` and `updated`, delete `deleted`, in one transaction. A local row still pending is not overwritten |
| Local deletes | A nullable `deleted_at` tombstone, pushed under `deleted`, then removed |
| After a push | Rows stay pending until the next pull returns them `synced` or `conflict`; the push is idempotent, so sending twice is harmless |

## The API's side

**`GET /api/v1/sync/pull`**: query `last_pulled_at` (ms) and `schema_version`; answers
`{ "changes": { "<table>": { "created": [], "updated": [], "deleted": ["<id>"] } }, "timestamp": <ms> }`.
`timestamp` is read before the queries run, so a row changed during the pull is sent again next
time. The server decides the scope from the verified tenant and role, never from the device.

**`POST /api/v1/sync/push`**: body `{ "changes": {...}, "last_pulled_at": <ms> }`. One transaction,
applied whole or not at all. Idempotent: a created row whose `sync_id` exists counts as applied.
Only device-writable tables are accepted (anything else: 403). 409 when a server-owned record
changed after `last_pulled_at` (the client pulls and retries).

## Conflict rules

| Kind of data | Rule |
|---|---|
| Server-owned records (accounts, catalogues, prices) | Server wins. The device never pushes them |
| Submissions made on the device (a form, a check-in, a task update) | The device's change is queued; the server rules on arrival with the same checks as the online route. Accepted comes back `synced`; refused comes back `conflict` with a reason the user sees. Nothing is dropped silently, and one refused row never fails the whole push |
| Append-only telemetry (locations, events) | Client wins, always appended, ordered by the device's `recorded_at`; never pulled; deleted from the device after a successful push |

Money is never queued offline: a payment needs the network, and fails and says so without it.

## What each role keeps

Write a table per project: role, what it pulls, what it may write, and the window (the last 14
days, the current month). A role that needs nothing offline keeps nothing.
