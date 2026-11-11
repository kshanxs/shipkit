# kit-break

**Group:** Kits · **Commands:** `/break`, `/bt`

The whole Break & Test group in one command. `kit.py` decides from the repository which steps apply now: harden the changed areas, review the new commits, and (in `full`) simulate load with performance stats on the local stack, or (in `launch`) add the readiness audit; then one triage report. Steps that do not apply are skipped and steps that cannot run yet are held back, each with the reason.

## When to use it

After building something, before a merge, "prove it", "break and test", "is this solid?"

## Example

In Claude Code:

```
/break
/break full the checkout flow
/break launch
```

In Cursor, Codex or Trae, name it in the message: `@break prove the invoices change`.

See what it would run, without running anything (paths shown for a `.claude/skills` install):

```bash
python3 .claude/skills/switchboard/scripts/kit.py plan break --tier full
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
