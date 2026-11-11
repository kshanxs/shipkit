# Vite+ (vite-plus, the `vp` command)

Vite+ puts the dev server, build, test runner, linter, formatter and task runner behind one
command, `vp`, configured in one `vite.config.ts`. Tell it apart from plain Vite by `vite-plus` in
`package.json` and `vp ...` in its scripts.

```bash
vp install                 # dependencies, with the package manager the project uses
vp dev                     # the dev server (vp dev --port 5180 when several worktrees run)
vp build                   # the production build
vp test                    # tests (tests import from 'vite-plus/test', not 'vitest')
vp lint .                  # lint (rules under `lint` in vite.config.ts)
vp fmt                     # format; only when the project has formatter settings
vp check                   # format, lint and types in one pass, where the project uses it
vp run <task>              # a package.json script or a task defined in vite.config.ts
```

Rules:

- Keep `vp` in the scripts (`"dev": "vp dev"`, `"test": "vp test"`); CI calls the scripts.
- Lint and format settings live in `vite.config.ts` (`lint: {...}`, `fmt: {...}`), not in separate
  `.eslintrc` or `.prettierrc` files. If an app has no `fmt` settings and is formatted by hand, do
  not run `vp fmt`: it rewrites every file.
- Tests: `import { describe, it, expect } from 'vite-plus/test'`. Environment per file as in Vitest
  (`// @vitest-environment node`).
- A new app: `vp create` (pick the template), then add the app's own `CHANGELOG.md`.
- If `vp` is not on the PATH, it may be installed per user (check the project's README); do not
  fall back to plain `vite` commands without saying so, since the configs differ.
