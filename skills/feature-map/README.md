# feature-map

**Group:** Docs & Flow · **Commands:** `/fmap`, `/features`

Keeps one map of every feature, its sub-features, its tier (Free, Pro, Enterprise or your own) and what is built, with counts by what is left; holds a pricing page's comparison table to it and generates a public catalog for the roadmap.

## When to use it

A feature added, finished, split or moved between tiers; "what is built?", "what is left?", "update the pricing page".

## Example

In Claude Code:

```
/fmap mark usage alerts as built and show what is left in Pro
```

In Cursor, Codex or Trae, name it in the message: `@fmap mark usage alerts as built and show what is left in Pro`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/feature-map/scripts/feature_map.py --list --plan Pro
python3 .claude/skills/feature-map/scripts/feature_map.py --write
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
