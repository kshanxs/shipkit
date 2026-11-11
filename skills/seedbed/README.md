# seedbed

**Group:** Build · **Commands:** `/seed`

The seed-data protocol: every feature ships idempotent seed data dated relative to today with made-up people, and a scenario config (`seedbed.toml`) names the modules and scenarios a seed run may ask for, the demo personas, the client-side stores and the data map. `check_seeds.py` holds the code to the config; `references/example_seed.py` is a runnable generic SaaS seed.

## When to use it

A new or changed feature, model or persona; an empty or broken demo.

## Example

In Claude Code:

```
/seed add seed data for invoices: one paid, one open, one overdue
```

In Cursor, Codex or Trae, name it in the message: `@seed add seed data for invoices: one paid, one open, one overdue`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/seedbed/scripts/check_seeds.py --init   # writes seedbed.toml (generic SaaS)
python3 .claude/skills/seedbed/scripts/check_seeds.py --run
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
