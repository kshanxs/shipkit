# stack-native

**Group:** Build · **Commands:** `/native`, `/rn`, `/mobile`

Architecture and conventions for a React Native app on **Expo**: Expo Router, dev builds and prebuild, where each kind of state lives, secure token storage, long lists, and an offline-first device database (Drizzle on Expo SQLite) with a pull-then-push sync protocol and conflict rules (`references/offline-sync.md`).

## When to use it

Anything in an Expo or React Native app, or a backend change to an entity the app keeps offline.

## Example

In Claude Code:

```
/native make the task list work offline and sync when the network returns
```

In Cursor, Codex or Trae, name it in the message: `@native make the task list work offline and sync when the network returns`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
npx expo install expo-sqlite drizzle-orm
npx drizzle-kit generate
npx tsc --noEmit && npx jest
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
