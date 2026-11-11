---
name: stack-web
description: "Conventions and validation for a web front end on Vite or Vite+ (vite-plus, the `vp` command): layout, one API client (with tenant headers when the project is multi-tenant), routing with typed search params, server state vs client state, query keys, forms with a schema, offline outbox, sign-in, accessibility, tests and the checks to run. Use when building, fixing or refactoring a page, component, hook, store, route, form or mock in a web app; when touching vite.config.*; and when the user says 'frontend', 'UI', 'screen', 'page', 'component', 'Vite', 'Vite+', 'vp', 'typecheck' or 'vitest'."
---

# Web front end (Vite and Vite+)

The examples are React with TypeScript; the rules hold for Vue, Svelte or Solid. Read the app's
own README first. Find the app: the `[stack]` table of `shipkit.toml` may name it
(`web_dirs = ["apps/web"]`); otherwise look for `vite.config.*`.

**Which toolchain?** [references/vite.md](references/vite.md) for plain Vite (scripts in
`package.json` call `vite`, `vitest`, `tsc`, a linter); [references/vite-plus.md](references/vite-plus.md)
for Vite+ (the `vp` command: `vp dev`, `vp build`, `vp test`, `vp lint`, `vp fmt`, config in one
`vite.config.ts`, tests import from `vite-plus/test`). Use the package manager the lock file names
(`pnpm-lock.yaml`, `bun.lock`, `package-lock.json`, `yarn.lock`), never a different one.

## Layout

| Path | Holds |
|------|-------|
| `src/routes/` or `src/app/` | The route table and each page's search-param schema |
| `src/features/<feature>/` | Pages, feature components, feature hooks |
| `src/components/ui/` | Shared primitives; import them, never copy them into a feature |
| `src/lib/api.ts` | The one API client (auth refresh, tenant headers, idempotency keys) |
| `src/stores/` | Client state only: session, selected tenant, theme |

Two apps in one repository (a customer app and an operator console) never import from each
other; shared code goes in a package, and a boundary check in CI holds it.

## Talking to the API

- Use the one client (`api` from `@/lib/api`); never a second `fetch` wrapper or Axios instance,
  which would skip its auth refresh, its tenant header and its offline outbox.
- The API's route and schemas are the contract: match field names, query parameters and status
  codes exactly (wire-api skill). Prefer types generated from the OpenAPI document.
- **[multi-tenant]** Tenant-scoped calls send the tenant header (`X-Workspace-ID`). Headers are
  routing context, not authorization: the API enforces permissions. Skip this when the project
  profile (`project.py show`) is not multi-tenant.
- A change that may wait for a connection says so where it is made and handles a queued answer.
  Never queue a change that takes money, allocates a number, or would be wrong an hour later.
- **[self-hosted]** A web app served by a self-hosted server sends changes from its own origin
  only, with the same-origin credentials the server checks (Origin or a CSRF token); never turn
  those checks off for convenience in development builds that ship.

## Routing

- A page reads its own params and search through the router's typed API, never by parsing
  `window.location` or building a `URLSearchParams` by hand.
- Everything after the `?` is declared in a schema (zod); a bad value is dropped, never an error.
- Guards decide signed in or not (and, with tenants, tenant chosen or not); what a role may see follows the API's
  answer.
- A loader starts a request and never waits for it; the page's hook uses the same query options,
  or the request is made twice.

## State

- Server data lives in the server-state cache (TanStack Query or the framework's equivalent).
  Client stores (Zustand, Pinia) hold only client state: session, selections, theme. Never a whole
  dataset.
- Query keys include every input the answer depends on (user, tenant, role, filters, ids), so one
  tenant's data never shows for another.
- Invalidate the affected keys after every mutation.
- Data that must survive offline goes in IndexedDB (Dexie), not in the query cache, and is wiped
  on sign-out.
- Forms: one schema (zod) with a form library (React Hook Form); no hand-rolled form state.
- Sign-in: the identity provider owns the session; a store may read the user, never decide it.

## Accessibility

- Set `type` on every button in a form. Keep native attributes, refs, labels (`htmlFor`/`id`) and
  keyboard focus.
- Decorative elements get `aria-hidden="true"`; icon-only buttons get an `aria-label`.
- Check keyboard focus, a phone-width viewport and dark mode for every changed screen.

## Validate

Run the app's own scripts (see the reference for your toolchain): install from the lock file,
typecheck, test, lint (compare with the baseline count), build. Tests run in a DOM environment
(happy-dom or jsdom); a file that needs none says so (`// @vitest-environment node`). If the app
has no formatter configured, do not run one: it would rewrite every file.

## Finishing a change

1. The validation above, for each app you changed.
2. A changelog line under Unreleased in that app's `CHANGELOG.md` (docsync: `changelog.py add`).
3. The feature's spec and tracker row; `check_docs.py --changed`.
