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

## Buttons, dialogs and focus

- A shared `Button` takes `onClick: () => unknown` and, when the handler returns a promise, shows
  a pending state (disabled, a spinner) until it settles. Pass the action straight through
  (`onClick={save}` or `onClick={() => save(id)}`); never `onClick={() => void save()}`, which
  throws the promise away so the button cannot show that anything is happening.
- Give buttons and tappable rows `touch-action: manipulation` and an `:active` style, so a tap
  shows at once on a phone.
- An effect that moves focus (a dialog or focus trap saving the focused element, focusing the
  first field, giving focus back on cleanup) must not list callback props (`onClose`) as
  dependencies. Callers pass a new arrow on every render, so the effect re-runs on each render:
  on a page that polls, open dropdowns close by themselves and typing jumps to another field.
  Read the callback through `useEffectEvent` (React 19.2+) or a ref updated in an effect, so the
  effect runs once each time the dialog opens. The same holds in React Native.
- When a report says "typing gets interrupted", "I can't type" or "a dropdown closes by itself",
  look first for focus effects that re-run on each render, before blaming keyboard shortcuts.
  Check it in a browser: open the dialog on a page that polls, focus a select, wait through two
  polls and check that `document.activeElement` has not changed; type, wait, type again and check
  that the field holds both halves.

## Long text from outside the app

Text the app did not write has no break points: file paths, emails used as names
(`name-12345@example.com.json`), URLs, tokens, IDs, provider and machine error messages, stack
traces. In a flex or grid item the default `min-width: auto` makes the item at least as wide as its
longest word, so such a value spills out of its card; `overflow-wrap: break-word` alone does not
fix a flex child.

- Base styles: `overflow-wrap: break-word` on `body`, so every block of text breaks long words.
- Every flex or grid child that shows outside text gets `min-width: 0` and
  `overflow-wrap: anywhere` (Tailwind v4: `min-w-0 wrap-anywhere`). Unlike `break-word`,
  `anywhere` lowers the element's min-content width, so the item can shrink. Use `truncate` with a
  `title` only where the full value is not needed.
- When a spill is reported on one screen, search every screen for flex and grid children that
  render such fields without `min-w-0`.
- Mocks and seeds hold one long, unbroken, realistic value for each field that shows outside text
  (seedbed); tidy short mock strings hide this bug.

## Accessibility

- Set `type` on every button in a form. Keep native attributes, refs, labels (`htmlFor`/`id`) and
  keyboard focus.
- Decorative elements get `aria-hidden="true"`; icon-only buttons get an `aria-label`.
- Check keyboard focus, a phone-width viewport and dark mode for every changed screen. At 360 and
  390 px wide, no page is wider than the screen, and every page and tab is reachable without a
  hamburger menu (a bottom tab bar with a "More" sheet works well).
- A global reduced-motion rule (`* { animation-duration: 0.01ms !important }`) fits one-shot
  transitions but makes an `infinite` animation (a pulse, a spinner, a flowing SVG dash) run
  thousands of cycles a second, which flickers. Give looping animations a class and set
  `animation: none !important` on it under `prefers-reduced-motion: reduce`, and keep the state
  readable without motion (colour, shape, an icon). Check with Playwright's
  `reducedMotion: 'reduce'` page option.
- With several themes or palettes, run the contrast check in a real browser once per theme, not only
  on the default. Measure text against the background it actually sits on: status text on its own
  tinted chip (red on red at 15%) often passes on the page and fails on the chip, and palettes
  derived from another source need their text roles lifted until every one passes.
- Avoid a vertical scroll box inside a scrolling page on touch screens: a swipe on it can trap the
  page. Cap the rows with "Show more", or release the box under `@media (pointer: coarse)`
  (`max-height: none; overflow-y: visible; overscroll-behavior: auto`). Use `overscroll-contain`
  only on overlays (sheets, dialogs, viewers).
- When this is reported on one page, search every page for `overflow-y-auto`, `overflow-auto`,
  `max-h-` and `overscroll`. Check with touch emulation (Chrome DevTools Protocol
  `Emulation.setTouchEmulationEnabled` and `Emulation.setEmitTouchEventsForMouse`), then confirm
  `matchMedia('(pointer: coarse)').matches`.

## Validate

Run the app's own scripts (see the reference for your toolchain): install from the lock file,
typecheck, test, lint (compare with the baseline count), build. Tests run in a DOM environment
(happy-dom or jsdom); a file that needs none says so (`// @vitest-environment node`). If the app
has no formatter configured, do not run one: it would rewrite every file. Run Vite+ through the
project's script or `node_modules/.bin/vp`: `npx vp` without the local install fetches an unrelated
npm package named `vp`.

**Checking in a real browser on a Linux server.** A headless Chromium on a fresh server often fails
to start with `error while loading shared libraries`. Run `ldd <chromium binary> | grep "not found"`
to list what is missing and install only those packages (or `npx playwright install-deps`, which
installs many more). Use a browser build that is already in the Playwright cache through
`executablePath` (from an environment variable, never a hard-coded path) rather than downloading
another. Measure layout after CSS transitions finish, and select the exact element under test (give a
decorative SVG a data attribute): an icon's `<svg>` matches a bare `svg` selector.

**Overflow checks at each width.** Comparing `document.documentElement.scrollWidth` with
`clientWidth` misses a child spilling out of its card when an ancestor clips it or a grid track
absorbs it. Also check each bordered box, at every width you test:

```js
// Run with page.evaluate(auditSpill) in Playwright; expect an empty list.
function auditSpill() {
  return [...document.querySelectorAll("body *")].filter((el) => {
    const s = getComputedStyle(el);
    const bordered = parseFloat(s.borderLeftWidth) > 0 || parseFloat(s.borderRightWidth) > 0;
    return bordered && s.overflowX === "visible" && el.scrollWidth > el.clientWidth + 1;
  }).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join(".")}`);
}
```

For a wider sweep, append a long unbroken token (`/srv/app/data/subfolder/a-long-file-name.json`)
to each text leaf and run the check again; it finds every place that would spill. Expect noise
from short fixed labels (counts, times, badges) and keep the places that can hold outside text.

**Vite returns 403 for assets in a worktree.** A `node_modules` symlinked into a worktree resolves
to a real path outside the worktree root, and Vite's dev server refuses to serve files from it
("outside of Vite serving allow list"), such as font files. Browser checks then fail on console
errors that have nothing to do with the change. Install dependencies in the worktree from the lock
file instead (fanout); if it must stay a link, add the real `node_modules` path to
`server.fs.allow`. When a browser check fails only on 403s for assets, read the Vite log for that
message before debugging the change.

## Finishing a change

1. The validation above, for each app you changed.
2. A changelog line under Unreleased in that app's `CHANGELOG.md` (docsync: `changelog.py add`).
3. The feature's spec and tracker row; `check_docs.py --changed`.
