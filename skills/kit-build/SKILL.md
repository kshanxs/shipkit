---
name: kit-build
description: "The Build kit: one command that builds a feature by running the build skills in order (handoff and open-loops to start, fanout when the work is parallel, then only the stack skills the work touches: stack-backend, stack-web, stack-native, then wire-api when an API and a screen both change, and seedbed when the data model changes), skipping each step that does not apply, with the reason, and stopping when a stack's tests fail. Use when the user says /build, 'build this', 'run the build kit', 'implement this feature' or 'build it with shipkit'."
---

# Build kit

One command for the Build group. `kit.py` reads the request, `shipkit.toml` and what changed, and
decides which build skills apply; you run them in order. `$SK` is the skills folder this skill is
installed in.

## 0. Frame

Before planning, write in a few lines:

- **The request** in your own words, and the **assumptions** you are making. If it can be read two
  ways, say both and ask; do not pick one silently.
- **Success criteria** as checks: `<step> -> verify: <the test or command that proves it>`. "Make
  it work" is not a criterion; "a test for each new rule passes and the old suite still passes" is.
- **The smallest change** that meets them. No features, options or abstractions nobody asked for.

A new feature whose shape is not yet agreed is designed with the user first, before any code (a
design or planning skill, if one is installed, such as superpowers' brainstorming and
writing-plans). A plan that already exists is followed, not rewritten.

## 1. Plan

```bash
python3 $SK/switchboard/scripts/kit.py plan build --request "<the user's words>"
```

Show the plan as it is. Each step is **run**, **skip** (why) or **blocked** (what is missing).

| Step | Runs when |
|---|---|
| handoff | `HANDOFF.md` exists: read Now, Next up, Waiting and the newest rows |
| open-loops | the register exists: the questions this work touches |
| fanout | the request asks for parallel work |
| stack-backend / stack-web / stack-native | the request or the changes touch that stack (`[stack]` in shipkit.toml) |
| wire-api | an API and a screen are both in scope |
| seedbed | the schema, a model or a migration changes |

## 2. Run each "run" step, in order

Load each skill only when its step starts (the Skill tool, or `$SK/<skill>/SKILL.md`) and follow it.

- **handoff, open-loops** first: build around undecided questions, do not answer them yourself.
- **fanout**, when it runs, splits the stack steps across agents; each agent then follows the
  stack skills for its own task.
- **Stack steps**, backend before front ends. **Gate:** each stack's tests and checks must pass
  before the next step; if they cannot, stop and report.
- **wire-api** after the API and the screen exist; **seedbed** after the schema settles.

If a step marked run turns out not to apply (the feature does not touch that stack after all), skip
it and say why.

Inside each step: a test for each new behaviour first, seen failing, then the code; and every
changed line traces to the request. Do not tidy, reformat or refactor neighbouring code; mention it
instead. Remove only what your own change left unused.

## 3. Report

**Evidence rule:** a step is **done** only when its evidence was produced in this session: the
command that was run and what it printed (test counts, exit code, the report's path). A step whose
result you did not see is **not verified**, never done. Report a failure as it is.

One table: step, result (**done**, **skipped** why, **blocked** how to unblock, **failed** what
broke) and evidence (files, test counts). Then suggest `/break` to prove it and `/flow` to record
it, or `/feature` next time to do all three.
