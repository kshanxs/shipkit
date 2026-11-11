# stack-web

**Group:** Build · **Commands:** `/web`, `/fe`

Conventions and checks for a web front end on **Vite** or **Vite+** (`vp`): one API client with tenant headers, typed routes and search params, server state vs client state, query keys that include the tenant, forms with a schema, offline outbox rules, accessibility, and the commands to validate. `references/vite.md` and `references/vite-plus.md` cover each toolchain.

## When to use it

Building or fixing a page, component, hook, store, route or form in a Vite or Vite+ app.

## Example

In Claude Code:

```
/web add a settings page with a form that saves the workspace name
```

In Cursor, Codex or Trae, name it in the message: `@web add a settings page with a form that saves the workspace name`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
pnpm run typecheck && pnpm run test && pnpm run build     # plain Vite
vp check && vp test && vp build                           # Vite+
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
