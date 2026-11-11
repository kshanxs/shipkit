---
name: kit-flow
description: "The Docs & Flow kit: one command that closes the loop at the end of a session (docsync for changelogs, specs and the tracker, feature-map, open-loops for the questions the change touched, then a handoff work log row) or opens one at the start (/flow start: read the handoff and the open questions), skipping each step whose files do not exist yet, with the reason. Use when the user says /flow, 'wrap up', 'close the loop', 'end of session', 'record this', 'update everything', or at the start of a session with 'start', 'where did we leave off'."
---

# Docs & Flow kit

One command for the Docs & Flow group. It only reads and writes documentation. `$SK` is the skills
folder this skill is installed in.

## 1. Plan

```bash
K="python3 $SK/switchboard/scripts/kit.py"
$K plan flow --mode end     # /flow        the end of a session (default)
$K plan flow --mode start   # /flow start  the start of a session
```

| Mode | Steps |
|---|---|
| end | docsync → feature-map → open-loops → handoff (log) |
| start | handoff (read) → open-loops |

Show the plan as it is: **run**, **skip** (why), **blocked** (what is missing).

## 2. Run each "run" step, in order

Load each skill only when its step starts (the Skill tool, or `$SK/<skill>/SKILL.md`).

- **docsync**: the change's changelog lines, specs and tracker rows; `check_docs.py --changed`
  must pass.
- **feature-map**: move what was built, recount, keep the pricing page in step.
- **open-loops**: update the questions this change touched (`open_loops.py --changed`); never
  answer one on the owner's behalf.
- **handoff** last: one work log row and updated Now, Next up, Waiting and Blocked (`handoff.py
  init` first if there is no `HANDOFF.md`).
- At the start: **handoff** (show), then **open-loops** (what waits on the owner), and say what is
  next.

## 3. Report

One short table: step, result (**done**, **skipped** why, **blocked**), and the files changed.
