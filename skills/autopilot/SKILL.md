---
name: autopilot
description: "The shipkit autopilot: works out which shipkit skills and kits fit right now and whether each can run, from the repository's state (what changed against the default branch and in the working tree, new commits, schema changes, which registers and configs exist, whether the local stack answers) and the request, then runs the ones that fit without being told which. Use when the user says /shipkit or /auto, 'run shipkit', 'use the shipkit skills', 'run the skills', 'what should I run', 'check this with shipkit', or names no skill but wants shipkit applied to the current work."
---

# Autopilot

The user should not have to name skills. Read the state, decide, run, report. `$SK` is the skills
folder this skill is installed in.

## 1. Decide

```bash
python3 $SK/switchboard/scripts/kit.py auto --request "<the user's words>"
```

It answers in three parts:

| Part | Meaning | What you do |
|---|---|---|
| **Now** | fits the current state | run it, in order, without asking |
| **Ready when you want** | can run, but costs time or is a launch step | offer it in one line; run it only if asked |
| **Not now** | cannot run yet | say why and how to unblock it |

How it decides (first match wins for **Now**):

| State | Now |
|---|---|
| shipkit.toml has no `[project]` | `/profile` first (fill in the profile from the repository), then the rest |
| the request names a skill or kit | that one |
| the request is about launching | `/break launch` |
| the session is starting / ending | `/flow start` / `/flow` |
| the request asks for new work | `/feature` |
| code changed and is not proven | `/break`, then `/seed` if the schema changed, then `/flow` |
| only docs changed | `/flow` |
| nothing changed | `/flow start`, then the skill the request fits |

`/break full` is offered when the project is multi-tenant, `load-scenario.toml` points at this
machine and the stack answers; otherwise it is listed under Not now with the reason. The first line
of the answer is the project profile; every kit skips the steps it does not fit (a step's `needs`
in kits.toml), with the reason.

## 2. Run

Show the three parts, then run each **Now** item in order by loading its kit or skill
(`/break` is `kit-break`, `/flow` is `kit-flow`, `/feature` is `kit-feature`, `/build` is
`kit-build`; any other `/<short>` is that skill) and following it. Each kit plans its own steps and
skips what does not apply, so nothing runs that is not feasible now.

## 3. Report

One combined table (kit or skill, step, result: **done**, **skipped** why, **blocked** how to
unblock, **failed** what broke) and the **Ready when you want** line.

## Rules

- Decide from the state, never guess: run `kit.py auto` every time, even when the answer seems clear.
- Never run a blocked step, never against production, never deploy.
- When the user names a skill or kit, that wins over the autopilot.
