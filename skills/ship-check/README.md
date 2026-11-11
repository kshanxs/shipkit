# ship-check

**Group:** Break & Test · **Commands:** `/ship`, `/ready`

A read-only launch-readiness audit against a configurable checklist (operator capabilities, onboarding, privacy and the regulations you name, security, recovery, observability, delivery, supply chain, operations, pricing). `ship_check.py` scaffolds the report with files to read per item, then refuses a DONE without a real file path.

## When to use it

"Are we ready to launch?", a readiness report, the launch blockers.

## Example

In Claude Code:

```
/ship audit main against the checklist and list the top five blockers
```

In Cursor, Codex or Trae, name it in the message: `@ship audit main against the checklist and list the top five blockers`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/ship-check/scripts/ship_check.py init
python3 .claude/skills/ship-check/scripts/ship_check.py scaffold --out ship-check-report.md
python3 .claude/skills/ship-check/scripts/ship_check.py check ship-check-report.md
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
