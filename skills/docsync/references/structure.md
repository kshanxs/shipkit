# Structure: where documents live, how they are named, how they move

Reference for the docsync skill. The paths are the defaults; `[docsync]` in shipkit.toml renames
any of them.

## Folder map

```
README.md                  Project entry: stack, structure, quick start
CHANGELOG.md               Product-level summary (Keep a Changelog)
AGENTS.md / CLAUDE.md      The instructions every agent reads (the switchboard can keep a skill table in AGENTS.md)
HANDOFF.md                 The handoff between sessions (handoff skill)
docs/
  README.md                Index and folder map: add every new folder here
  feature_status.md        The tracker: every feature, its status, the code map
  feature_catalog.md       The feature map: tiers, features, sub-features (feature-map skill)
  open_questions.md        What waits for an answer (open-loops skill)
  bugs_fixed_and_improvements.md   Dated change history with the reasoning
  architecture/            Overview, schema, decisions
  deployment/              Hosting, environments, runbooks
  features/                One spec per feature
  roles/                   One page per role, and the data map
  plans/                   Dated plans and design notes (YYYY-MM-DD-title.md)
  testing/                 Bug register, attack log, test matrix
<package>/README.md        Setup, scripts, tests and package-level notes only
<package>/CHANGELOG.md     Every code change in that package
```

Package folders hold only what a developer needs to work on that package. A spec, roadmap, status
table or price found in a package moves to `docs/` and is replaced by a link.

## Naming

| Kind | Rule (default `naming = "snake"`) | Example |
|---|---|---|
| Document under `docs/` | lowercase `snake_case.md` | `unit_economics.md` |
| Plan or design note | `YYYY-MM-DD-kebab-title.md`, in `docs/plans/` only | `2026-10-01-search-plan.md` |
| Folder index | `README.md` | `docs/features/README.md` |
| Folder | lowercase, words joined by `-` or `_` | `admin_console/` |

Name a file for its subject, not for the moment it was written: no `new_`, `final_`, `v2`. Do not
create `task.md`, `TODO.md` or `notes.md` in a package.

## Renaming and moving

1. `git mv old new` (a case-only rename on macOS takes two steps through a temporary name).
2. Rewrite every inbound link (`check_docs.py` lists the broken ones), and the moved file's own
   relative links if its folder changed.
3. Search code, scripts, CI and skills for the old name: `git grep -n "old_name"`.
4. Add the old name to `[[docsync.stale]]` so it cannot come back, and update the folder map here
   and in `docs/README.md` if a folder was added or removed.
5. Record the old and new names in `docs/bugs_fixed_and_improvements.md`.
