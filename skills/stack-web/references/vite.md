# Plain Vite

A Vite app runs its tools through `package.json` scripts. Use the package manager its lock file
names.

```bash
pnpm install --frozen-lockfile     # or: npm ci, bun install --frozen-lockfile, yarn install --frozen-lockfile
pnpm run typecheck                 # usually: tsc --noEmit (or vue-tsc, svelte-check)
pnpm run test                      # usually: vitest run
pnpm run lint                      # eslint . or oxlint
pnpm run build                     # vite build (tsc -b && vite build in the React template)
pnpm run dev -- --port 5173        # vite; pass a free port when several worktrees run at once
```

If a script is missing, add it rather than typing the tool by hand in CI. Typical `package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "lint": "eslint ."
  }
}
```

Vitest config lives in `vite.config.ts` under `test` (`environment: 'happy-dom'`), or in
`vitest.config.ts`. Environment variables the browser may read start with `VITE_` and are public:
never a secret.
