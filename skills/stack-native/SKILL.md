---
name: stack-native
description: "Architecture and conventions for a React Native app on Expo (TypeScript): Expo Router, dev client and prebuild, where each kind of state lives, an offline-first database on the device (Drizzle on Expo SQLite, or another) with a pull-then-push sync protocol, conflict rules, secure token storage, long lists, native modules, EAS builds, and tests. Use when planning or building anything in a React Native or Expo app, when a backend change touches an entity the app keeps offline, and when the user says 'mobile', 'iOS', 'Android', 'Expo', 'React Native', 'EAS' or 'offline-first'."
---

# React Native and Expo

Find the app: the `[stack]` table of `shipkit.toml` may name it (`native_dir = "apps/mobile"`);
otherwise look for `app.json` or `app.config.*` with an `expo` key. The app's README and code win
over this file.

## The stack, and why

| Part | Default choice | Note |
|---|---|---|
| Framework | Expo, TypeScript | Same language and libraries as the web app |
| Workflow | Development build (`npx expo run:ios`, `run:android`) and `expo prebuild` when a native module needs it | Expo Go cannot load custom native code (background location, some push setups) |
| Navigation | Expo Router | File-based routes, deep links, typed routes |
| Server state | TanStack Query | Its cache is never the offline database |
| App state | Zustand | Selections, filters, sync status, flags. Never a table of data, never the session's source of truth |
| Forms | React Hook Form + zod | Share schemas with the web where a form exists on both |
| Offline database | Drizzle on Expo SQLite (`drizzle-orm/expo-sqlite`) | Typed schema, generated migrations, `useLiveQuery`; see [references/offline-sync.md](references/offline-sync.md) |
| Long lists | FlashList | For rosters, feeds, history; a plain list for a handful of rows |
| Animation and gestures | Reanimated, Gesture Handler | Only where they earn it |
| Tokens | `expo-secure-store` | Never in SQLite, AsyncStorage or a persisted store |
| Builds | EAS Build and Update | `eas.json` per profile |

Record a change to this table as a decision in the project's decision log, with the reason and
the trade-off.

## Where each kind of state lives

| Kind | Home |
|---|---|
| App and UI state | Zustand |
| Server state fetched online and not kept | TanStack Query |
| Durable offline data | The device database |
| Identity and session | The auth provider's SDK, tokens in secure store |
| Form state | React Hook Form |

The API checks every request on its own: the app shows or hides screens from the permissions the
API returned; it never grants one.

## Conventions

- A route file in `src/app/` stays thin: it reads its params and renders a screen from
  `src/features/<feature>/`.
- Every write to a device-writable table goes through a function in `src/db/queries/` that sets
  `sync_status = 'pending'` in the same statement. Screens never call `insert` or `update`.
- Offline data is read from the device database (`useLiveQuery`), not from the query cache. Keep
  live queries narrow (one list, one day).
- A list that can be long is a FlashList fed by a paged query (`limit` and a cursor), memoised rows
  with stable keys.
- Column names are the API's (`snake_case`), the TypeScript key their camelCase form; enums are
  the API's strings; nullability matches the API's schema; dates and money as the API sends them.
- On sign-out the device database is deleted; the device holds only what a role needs offline.
- App-side endpoints (Expo API Routes) are thin adapters only: never business rules, never the
  database, never a permission decision.

## Commands

```bash
npx expo install <package>              # versions that match the SDK
npx expo start                          # dev server; --port when several worktrees run
npx expo run:ios | run:android          # development build
npx expo prebuild --clean               # regenerate native folders (they are generated: do not hand-edit)
npx expo-doctor                         # dependency and config problems
npx drizzle-kit generate                # a migration from a schema change; commit both
npx tsc --noEmit && npx jest            # types and tests (Jest with jest-expo; SQLite in memory via better-sqlite3)
eas build --profile preview --platform android
```

## Finishing a change

1. Types, tests, `expo-doctor`; a development build when native code changed.
2. A changelog line in the app's `CHANGELOG.md` (docsync).
3. An entity added or changed on the device: seedbed skill (schema parity with the API, the data
   map's offline column). Background location, push tokens and personal data kept on the device go
   through the project's privacy policy check.
