# docsync

**Group:** Docs & Flow · **Commands:** `/docs`, `/ds`

The documentation contract: every change in its package's changelog, every feature with a spec, a tracker row and a place in the feature map, bug and attack registers that agree with the changelogs, releases cut from the changelogs. `check_docs.py` enforces it from config, as a script, a Claude Code stop hook, and git pre-commit and commit-msg hooks.

## When to use it

The start and end of every code change, a bug fix, a release, any docs edit.

## Example

In Claude Code:

```
/docs record this fix and check the docs
```

In Cursor, Codex or Trae, name it in the message: `@docs record this fix and check the docs`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/docsync/scripts/changelog.py add api fixed "Invoices were charged twice"
python3 .claude/skills/docsync/scripts/check_docs.py --changed
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
