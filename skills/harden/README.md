# harden

**Group:** Break & Test · **Commands:** `/harden`, `/bth`

Test first, then break it on purpose: hostile input, other tenants' data, races, replays, offline changes, failing dependencies and bounded load. Every flaw is a failing test before it is fixed. Ships a test matrix template and `matrix.py` (coverage, gaps, pairwise cases), an OpenAPI-driven `isolation_sweep.py`, and `adversarial_runner.py` for fuzzing and bursts.

## When to use it

Building or changing anything that writes, takes money or holds personal data; a security review; "break it".

## Example

In Claude Code:

```
/harden the checkout endpoint against double submit and cross-tenant ids
```

In Cursor, Codex or Trae, name it in the message: `@harden the checkout endpoint against double submit and cross-tenant ids`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/harden/scripts/matrix.py pairs who network timing
python3 .claude/skills/harden/scripts/isolation_sweep.py --config sweep.toml --dry-run
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
