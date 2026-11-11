# profile

Fills in `shipkit.toml` for the project it is in, so every other skill runs only what fits.

- Detects the kind of project (SaaS, self-hosted, app, CLI, library, infra, container app), its
  tenancy, whether it takes money or sells priced plans, its auth, its surfaces (API, web, mobile,
  CLI, shell, container, library), whether it works offline, and where the code, docs, packages and
  ports are.
- Marks each value as detected or a guess, with the files that show it; the agent checks the
  guesses in the code, asks only what the code cannot answer, and writes the file.
- Adds to an existing `shipkit.toml` without changing anything already set.

```bash
python3 .claude/skills/switchboard/scripts/project.py detect   # what the repository shows
python3 .claude/skills/switchboard/scripts/project.py toml     # the shipkit.toml it would write
python3 .claude/skills/switchboard/scripts/project.py write    # write it (adds only what is missing)
python3 .claude/skills/switchboard/scripts/project.py show     # the profile every skill uses
```

In Claude Code: `/profile`. In Cursor, Codex or Trae: `@profile`.

The script lives in the switchboard skill (always installed) so the kits, the autopilot and the
other skills' scripts can read the profile too.
