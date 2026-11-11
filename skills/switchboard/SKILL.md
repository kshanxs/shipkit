---
name: switchboard
description: "The router for the shipkit skills: picks the skills a request needs (from @names, /slash commands, trigger phrases and file paths), runs as a Claude Code UserPromptSubmit hook so the right skills are suggested on every message, writes the slash-command shortcuts (/api, /web, /native, /docs, /harden, ...) and an optional skill table in AGENTS.md, and checks that everything is in step with the skills installed. Use when the user asks which skill fits, what the slash commands are, to add or rename a skill or a short name, or when route.py --check fails."
---

# Switchboard

One table of skills (`skills.toml`, beside this file) and one script (`scripts/route.py`). `$SK` is
the skills folder this skill is installed in.

```bash
R="python3 $SK/switchboard/scripts/route.py"
$R "add an endpoint and its screen"   # the skills that fit, and why
$R --list                             # every installed skill and its short names
$R --resolve                          # every skill by @name and every /short and @short resolves (exit 1 if not)
$R --write                            # write .claude/commands/<short>.md (and the AGENTS.md table, if marked)
$R --check                            # exit 1 when skills.toml, the commands or AGENTS.md are stale
```

## How a request picks a skill

1. **Named:** `@<short>` or `@<skill>` anywhere (`@api @seed add invoices`), or `/<short>` at the
   very start in Claude Code (`/docs sync the docs`). A named skill comes first.
2. **Triggers:** regular expressions in `skills.toml`, matched case-insensitively.
3. **Paths:** globs in `skills.toml`, matched against file paths in the request.
4. **Companions:** `with` brings related skills along (docsync after a code skill).

At most four skills are suggested; a short reply ("yes", "continue") gets none. Only installed
skills (folders beside this one with a `SKILL.md`) are ever picked, so a partial install routes
only to what it has.

## Other skill packs installed beside shipkit

Shipkit says **what this repository requires** (its conventions, registers, docs and gates).
General method packs say **how to work**, and the two are meant to be used together. Commonly
installed ones are superpowers (brainstorming, writing-plans, executing-plans,
test-driven-development, systematic-debugging, verification-before-completion, code review,
using-git-worktrees, dispatching-parallel-agents) and karpathy-guidelines (assumptions,
simplicity, surgical changes, success criteria). The router only picks shipkit skills; when one of
these overlaps a shipkit skill, the shipkit skill decides for this repository:

| Overlap | Who decides | Why |
|---|---|---|
| parallel agents, worktrees | fanout | it reserves migration, question and bug numbers and gives each worktree its own ports |
| test-first, breaking it | harden | its attack log and test matrix are what docsync and triage-report read |
| code review of new commits | bug-sweep | it reports through triage-report with the matrix coverage |
| finishing a branch, wrap-up | kit-flow | changelogs, feature map, open questions and the handoff row must move with it |

Use the method packs inside a shipkit step: design and plan before kit-build, root-cause debugging
inside a failing gate, verification before any step is reported done.

## The slash commands

| Group | Skill | Commands |
|---|---|---|
| Build | stack-backend | `/api`, `/be` |
| Build | stack-web | `/web`, `/fe` |
| Build | stack-native | `/native`, `/rn`, `/mobile` |
| Build | wire-api | `/wire` |
| Build | seedbed | `/seed` |
| Build | fanout | `/fanout`, `/par` |
| Break & Test | harden | `/harden`, `/bth` |
| Break & Test | bug-sweep | `/sweep`, `/hunt` |
| Break & Test | load-sim | `/load`, `/sim` |
| Break & Test | perf-watch | `/perf`, `/mon` |
| Break & Test | triage-report | `/triage`, `/report` |
| Break & Test | ship-check | `/ship`, `/ready` |
| Docs & Flow | docsync | `/docs`, `/ds` |
| Docs & Flow | feature-map | `/fmap`, `/features` |
| Docs & Flow | open-loops | `/loops`, `/oq` |
| Docs & Flow | handoff | `/handoff` |
| Docs & Flow | switchboard | `/sb`, `/route` |
| Kits | kit-build | `/build` |
| Kits | kit-break | `/break`, `/bt` |
| Kits | kit-flow | `/flow` |
| Kits | kit-feature | `/feature` |
| Kits | autopilot | `/shipkit`, `/auto` |

Each command file says "use the `<skill>` skill for this request" and passes the arguments on. In
agents without slash commands, write `@<short>` in the message instead.

## Kits and the autopilot

A kit runs a group's skills in order; the autopilot picks the kits that fit. Both are decided by
`scripts/kit.py` from [kits.toml](kits.toml) and the repository's state, never guessed:

```bash
K="python3 $SK/switchboard/scripts/kit.py"
$K plan break --tier full        # each step: run, skip (why) or blocked (what is missing)
$K plan flow --mode start
$K auto --request "run shipkit"  # Now / Ready when you want / Not now
$K facts                         # what the decisions rest on: changes, commits, schema, load target
$K members kit-break             # the skills a kit needs (install.sh --skills kit-break brings them)
```

A named kit or the autopilot comes alone: it picks its own skills, so the router adds none.

## The project profile

`scripts/project.py` says what kind of project this is (`[project]` in shipkit.toml, else
detected): kind, tenancy, money, plans, auth, surfaces, offline. A step in kits.toml with
`needs = ["multi-tenant"]` is skipped, with the reason, when the profile lacks the trait, and the
other skills' scripts filter their checklists the same way. The `profile` skill (`/profile`) fills
shipkit.toml in from the repository; the autopilot lists it first while `[project]` is missing.

```bash
P="python3 $SK/switchboard/scripts/project.py"
$P show              # the profile and where each value came from
$P has money plans   # exit 0 when the profile has every trait named
```

## Where things go

- The project is the folder above `.claude`, `.agents` or `.trae` (or `SHIPKIT_ROOT`).
- Commands go to `<project>/.claude/commands/` (`--commands-dir` or `SHIPKIT_COMMANDS_DIR` to change
  it). Generated files carry a marker line; `--write` removes a generated command whose short name
  is gone and never touches a command you wrote yourself.
- `AGENTS.md`: if it holds `<!-- shipkit:skills:start ... -->` and `<!-- shipkit:skills:end -->`,
  `--write` keeps the skill table between them (install.sh adds the markers).
- The hook: `install.sh --hooks` adds `route.py hook` to `.claude/settings.json` under
  `UserPromptSubmit`. It prints the skills that fit as context and is silent when none do.

## Adding or renaming a skill

1. Add or change its table in `skills.toml`: `short` (2 to 12 lowercase letters, digits, hyphens;
   the first is the main one), `summary`, `triggers`, `paths`, `with`.
2. `route.py --write`, then `route.py --check`.

The check refuses a short name used twice, one that is another skill's name, one that would hide a
Claude Code built-in command (`/help`, `/review`, `/init`, ...), a skill with no triggers and no
paths, a `with` naming no skill, and a stale command or table. Keep triggers specific: a skill
suggested for every message is noise. Add your own project's paths (`apps/billing/**`) to the
skills that own them.
