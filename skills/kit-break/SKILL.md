---
name: kit-break
description: "The Break & Test kit: one command that proves a change by running the break-and-test skills in order (harden, bug-sweep, load-sim with perf-watch, ship-check, then one triage-report), skipping each step that does not apply and holding back each one that cannot run yet, with the reason. Three tiers: quick (default: harden the changed areas, review the new commits, one report), full (adds a load simulation and performance stats on the local stack) and launch (adds the launch-readiness audit). Use when the user says /break, 'break and test', 'run all the tests skills', 'prove it', 'test everything' or 'is this solid', or after building a feature."
---

# Break & Test kit

One command for the whole group. `kit.py` decides which steps apply **now** from the repository's
state; you run them in order and report once. `$SK` is the skills folder this skill is installed in.

## 1. Plan

```bash
K="python3 $SK/switchboard/scripts/kit.py"
$K plan break --tier quick  --request "<the user's words>"    # /break        (default)
$K plan break --tier full   --request "<the user's words>"    # /break full
$K plan break --tier launch --request "<the user's words>"    # /break launch
```

Show the plan to the user as it is: every step is **run**, **skip** (does not apply, and why) or
**blocked** (applies, but cannot run yet, and what is missing).

| Tier | Steps it can run |
|---|---|
| quick | harden → bug-sweep → triage-report |
| full | + load-sim with perf-watch alongside (local stack only) |
| launch | + ship-check |

## 2. Run each "run" step, in order

For each step marked run: load that skill (the Skill tool, or read `$SK/<skill>/SKILL.md`) and do
what its row says, following that skill's own rules. Load a skill only when its step starts.

- **harden** first: test first, then break the changed areas; every flaw a failing test, then the
  fix. **Gate:** if the tests cannot be made to pass, stop here and report; the later steps would
  only measure a broken build.
- **bug-sweep**: review the new commits (mode A); in full and launch with no new commits, sweep one
  area (mode B). Verify every finding before it is reported.
- **load-sim** and **perf-watch** together: perf-watch collects while load-sim runs, on the local
  stack and a scratch database only.
- **ship-check**: read-only; its report is its own.
- **triage-report** last: one report covering everything that ran.

If a step marked run turns out not to apply once you are in it, skip it and say why.

## 3. Blocked steps

Never work around a blocked step. Report it with its reason, which says how to unblock it (start
the local stack, `sim.py init`, ...), and carry on with the rest.

## 4. Report

End with one table, then the next step:

| # | Step | Result | Evidence |
|---|---|---|---|
| 1 | harden | done: 3 flaws found and fixed, 14 tests added | tests/..., attack log ATK-0xx |
| 2 | bug-sweep | done: 2 findings | triage report |
| 3 | load-sim | blocked: nothing answers at http://localhost:8000 | start the local stack |

Results are **done**, **skipped** (why), **blocked** (how to unblock) or **failed** (what broke).
Then suggest `/flow` to record it.

## Rules

- Never against production, a hosted shared database or real people's data; never deploy.
- Every skill's own safety rules still apply inside the kit.
- The kit adds no checks of its own: what a step does is what its skill says.
