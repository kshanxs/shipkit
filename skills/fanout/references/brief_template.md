# Task {task}: {title}

You are one of several agents building features side by side, each in its own
git worktree. Run `{run}`. Other agents are changing other parts of the
repository at the same time; the rules below keep your work from colliding
with theirs.

## Goal

{goal}

## First step

From the root of your worktree (not the main checkout):

```bash
{script} join {run} {task}
```

It puts you on branch `{branch}` (from `{start_point}`), copies the ignored
`.env` files, installs the dependencies from the lock files, and writes your
ports to `.fanout-env`. If it stops, report why and stop.

## What you may change

Yours alone (no other agent touches these):

{owns}

Shared files: make only the small additions your feature needs, in the
file's own order (alphabetical where it is), and never reorder, reformat or
rewrite what is there:

{hotspots}

Anything else: do not change it. If the task cannot be done without it, stop
and say which file and why.

## Numbers reserved for you

Use these and no others; other agents hold the next ones.

- Migrations: {migrations}. Set `down_revision` to the head on your branch
  today; landing re-chains it after the migrations that land before yours.
- Open questions: {questions}
- Bugs: {bugs}

## Rules

- Follow the project's `AGENTS.md` or `CLAUDE.md` and the skills for this
  task: {skills}. Your changelog lines, your specification and your tracker
  rows are part of the task.
- Do not edit generated sections by hand (open-question lists, generated
  catalogs, lock files, generated API types). Landing rewrites them.
- Never choose a plan or a price, write a policy, or answer an open question.
  Write the question under your reserved number, saying what the code does
  meanwhile, and go on.
- You cannot ask the user anything while you work. Decide what is safe and
  reversible, note it, and put the rest in your report.
- Commit to `{branch}` as you go (Conventional Commits:
  `type(scope): summary`). Never push, never merge, never switch to another
  branch, never touch the main checkout.
- Dev servers use your ports from `.fanout-env`, never the defaults.
- Run targeted tests freely. Run the full suite only through
  `{script} test`, which waits its turn.

## Checks before you finish

{checks}
{docs_check}

Everything committed, `git status` clean.

## Notes from the orchestrator

{notes}

## Your report (your final message)

1. Branch and last commit (`git rev-parse HEAD`).
2. What was built, in three to six lines.
3. Files changed outside "Yours alone", one line each with why.
4. The checks you ran and their results; anything failing or skipped, and why.
5. Decisions you made where the brief was silent.
6. Open questions written (number and title), and anything the user must decide.
