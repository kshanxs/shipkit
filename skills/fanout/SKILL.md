---
name: fanout
description: "Orchestrating several agents building features at the same time, each in its own git worktree, and landing their work without merge trouble: splitting the work into tasks that share no files, reserving migration, question and bug numbers before anyone starts, giving each worktree its own ports, env files and dependencies, briefing each agent, and landing branches one at a time onto an integration branch (rebase, re-chained Alembic migrations, regenerated sections, checks). Use when the user asks for features, fixes or a plan's items to be built in parallel, by several agents or subagents, in worktrees, or 'at the same time'; when landing, checking or cleaning up a parallel run (`.fanout/`, branches `fanout/<run>/*`); and when two branches conflict on a changelog, a migration or a shared registry file."
---

# Fanout

Several agents can build features at once only if three things are true: **their tasks share no
files**, **they never take the same number** (a migration, an open question, a bug), and **one
orchestrator lands their work, one branch at a time**. This skill is how the orchestrator makes
those true. Everything mechanical is in one script:

```bash
F="python3 $SK/fanout/scripts/fanout.py"     # $SK: .claude/skills, .agents/skills or .trae/skills
$F new <run>              # plan + integration branch fanout/<run>/integration
$F ids                    # next free migration / Q / BUG numbers, across every branch
$F check <run>            # the plan is safe: no shared paths, no reused numbers
$F hotspots               # the shared files and how each one merges
$F brief <run> <task>     # the brief an agent is given
$F start <run> <task>     # make the worktree and set it up (or `join` from inside one)
$F status <run>
$F land <run> <task> [--full]
$F cleanup <run> <task>
$F test                   # the full suite, one checkout at a time
```

Plans and state live in `.fanout/<run>/` in the main checkout (add `.fanout/` to `.gitignore`).
The script finds them from any worktree. Project specifics (extra hot spots, ports, install and
check commands, the migrations folder) go in the `[fanout]` table of `shipkit.toml`; see
[references/config.md](references/config.md). Add `CHANGELOG.md merge=union` (and
`apps/*/CHANGELOG.md merge=union`) to `.gitattributes`, so changelog lines from two branches merge
themselves.

## 1. Decide whether to run in parallel

Use it for two or more tasks that are each a few hours of work and touch different code. Not for:

- one feature (one agent is faster);
- shared code (a shared package, a model several modules use, roles and permissions, config):
  that is foundation work and runs alone, first, in its own wave;
- two tasks on the same tables or screens: one agent does both, or the second is stacked on the
  first.

Size it to the machine: `max_parallel` (default 3) agents at once, and one full test suite at a
time (`fanout.py test` waits its turn).

## 2. Plan

1. `$F new <run>` (run names like `2026-11-12-search`). The integration branch starts from the
   branch you are on unless `--base` says otherwise.
2. Read each feature's tracker row, spec, and `open_loops.py --for <paths>` first.
3. One task per feature in `.fanout/<run>/plan.json`:

| Field | Means |
|---|---|
| `id` | lowercase, hyphens; the branch is `fanout/<run>/<id>` |
| `title`, `goal` | what it builds; what is true when it is done and how that is checked |
| `wave` | 1, 2, ...; a wave starts when the one before it has landed |
| `stack_on` | a task this one builds on; it starts from that branch and lands after it |
| `owns` | paths only this task changes: its module folder, feature folder, spec, tests |
| `hotspots` | shared files it adds to (`$F hotspots`): the router registry, nav, changelogs, the tracker |
| `ids` | `migrations` (`040_search`), `questions` (`Q-099`), `bugs` (`BUG-044`), from `$F ids` |
| `skills` | the skills its agent follows |
| `checks` | commands that prove the goal (targeted tests, not the full suite) |
| `notes` | anything else: an API contract, a decision already made |

4. `$F check <run>` until it reports no errors. Read the warnings.

| Work | Lane |
|---|---|
| A backend module | Its module folder, tests and spec; adds to the router registry, the seed and the API changelog |
| A web feature | Its feature folder; adds to nav and the route table |
| A feature from API to screen | One agent, one task, preferred. Split only when big: the API first and the screen stacked on it, or both at once with the contract written in `notes` and the screen on a mock until the API lands |
| A new feature | Its spec, tracker row and place in the feature map are the agent's; its tier and price are the owner's |
| Shared code | Wave 0, alone |
| Mobile | Its own lane; an entity it keeps offline is shared with the API, so the two are stacked |

Tasks of one wave may each add **their own tables**. Two tasks that add columns to the same table
are not parallel.

## 3. Start the agents

Commit what the tasks build on (a worktree starts from a commit). Then, for each task of the wave:

1. `$F brief <run> <task>`; give it to the agent, whole, as its prompt.
2. Start the agent in a worktree of its own: the harness's worktree isolation (the brief's first
   step, `join`, takes the task's branch and sets it up), or `$F start <run> <task>` and start the
   agent in that folder.
3. Run the wave in the background, at most `max_parallel` at once.

`join`/`start` gives each worktree its ignored `.env` files (copied, never linked), its own ports
(`.fanout-env`), its own dependencies installed from the lock files (`uv sync`, `pnpm install`,
`npm ci`, `bun install`: never a linked `.venv` or `node_modules`, which would run the main
checkout's code), and, if `redis = true`, a Redis of its own in Docker. Test databases: name them
after the worktree folder so two worktrees never drop each other's tables.

**Commits.** Starting a run is the user's permission for agents to commit on their own
`fanout/<run>/*` branches and for landing to move the integration branch. Bringing the
integration branch into the base, and pushing anything, still needs the user's word.

## 4. While they work

- Agents cannot ask the user anything: a question goes into the register under their reserved
  number, anything else in their report.
- An agent that needs a file outside its paths stops and says so. Allow it (if no other task of the
  wave owns it) or move the work to a later wave.
- Another number: take it from `$F ids`, add it to the plan, `$F check`, tell the agent.

## 5. Land, one branch at a time

```bash
$F land <run> <task>          # --full also runs the full suite
```

It rebases the task onto the integration branch (changelogs merge by `merge=union`), re-chains
Alembic migrations if another task's landed first (`down_revision` and `Revises:`), regenerates
what is generated (open-question lists, the feature catalog, your `[fanout] regenerate` commands),
runs the checks (docsync `check_docs.py --changed`, your `[fanout] checks` and `path_checks`, the
task's own), and moves the integration branch only if nobody moved it meanwhile.

Land in the plan's order: foundation first, stacked tasks after what they stand on, the smaller of
two tasks on one hot spot first. When the rebase stops, the script names each conflicted file and
how it merges:

| Kind | Resolve by |
|---|---|
| `append` (registries, nav, route tables, seeds, the tracker, indexes, registers) | keep both sides' lines, in the file's order |
| `generated` (lock files, generated catalogs and types) | take either side; landing regenerates it (`uv lock`, `pnpm install`), then commit |
| `union` (changelogs) | git does it; docsync reports a doubled heading |
| a file the task owns | the plan missed an overlap: resolve it as code, then add the path to the next plan |

Resolve in the task's worktree, `git add`, `git rebase --continue`, `$F land` again; then
`$F cleanup <run> <task>`. A failed check: fix it on the task's branch, commit, land again.

## 6. Finish

1. `check_docs.py --changed --base <base>` on the integration branch, and `$F test` once.
2. Tell the user what landed, the open questions the agents wrote, the decisions they made, and
   anything skipped.
3. With the user's word, bring the integration branch into the base (`git merge --ff-only` when
   the base has not moved; otherwise rebase it first and check again).
4. `$F cleanup` each task; delete the integration branch.

## Rules

- The plan owns who changes what. No path is owned by two tasks of one wave.
- Numbers come from the plan, never from "the next one I see".
- Agents never touch the main checkout, never push, never merge, never switch branches.
- Generated sections are never edited by hand in a worktree.
- Only the orchestrator lands, one branch at a time.
- Tiers, prices, policies and open questions stay with the owner.
