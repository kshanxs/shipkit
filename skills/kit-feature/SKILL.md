---
name: kit-feature
description: "The feature kit: one command that takes a feature from request to recorded: the Build kit (only the stack skills the work touches), then the Break & Test kit at its quick tier (harden, bug-sweep, one triage report), then the Docs & Flow kit (docsync, feature-map, open-loops, handoff), skipping each step that does not apply and stopping at a failing gate. Use when the user says /feature, 'build this end to end', 'do the whole thing', 'build, test and document it', or asks for a new feature with shipkit."
---

# Feature kit

Build, then break, then close the loop: the three kits in one run. `$SK` is the skills folder this
skill is installed in.

## 1. Plan

```bash
python3 $SK/switchboard/scripts/kit.py plan feature --request "<the user's words>"
```

The plan lists every step of the three kits, prefixed `build/`, `break/` and `flow/`, each **run**,
**skip** (why) or **blocked** (what is missing). Show it as it is.

## 2. Run the three kits in order

1. **build/**: follow the `kit-build` skill's section 2 for its steps.
2. **break/**: follow the `kit-break` skill's section 2 (quick tier). Re-plan this part after
   building (`kit.py plan break`): the build changed what there is to prove.
3. **flow/**: follow the `kit-flow` skill's section 2 (end).

**Gates:** a stack whose tests fail stops the run before break; harden that cannot get the tests
green stops it before flow. Stopping is a result, not a failure to hide: report it.

## 3. Report

One table for the whole run (kit, step, result, evidence), the triage report's top findings, and
what is next. `/break full` and `/break launch` stay for when the user asks.
