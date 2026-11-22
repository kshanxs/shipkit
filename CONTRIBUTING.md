# Contributing to shipkit

Shipkit is a public set of skills for all kinds of software development. Bug reports, field reports,
new stacks and pull requests are welcome from anyone using it.

## Open an issue

[Choose a form](https://github.com/kshanxs/shipkit/issues/new/choose):

- **Bug report**: a script, installer, command or skill does the wrong thing.
- **Field report**: real project work showed that a skill is wrong, outdated or missing a lesson.
- **Feature or new skill**: a stack, project type, agent or capability shipkit should support.

Search the open issues first, and add to an existing one when it covers the same point. Report
security vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

## Keep it public and generic

Issues and pull requests are public. Leave out secrets, private paths, hostnames, and client or
project names.

A skill must work for someone else's project:

- Detect the operating system, user, paths and repository, or read them from `shipkit.toml`.
- Say which kinds of project a rule applies to, so that it is skipped where it does not fit.
- Write a lesson from one project as a general rule, with the symptom that lets others recognise it.

## Send a pull request

```bash
git clone https://github.com/<you>/shipkit
cd shipkit
git switch -c improve/<short-name>
uv run pytest
python3 skills/switchboard/scripts/route.py --check
```

1. Change the skill's `SKILL.md`, and its scripts, references and tests where they apply.
2. If triggers, names or commands changed, edit `skills/switchboard/skills.toml` and run
   `python3 skills/switchboard/scripts/route.py --write`.
3. Add a dated line under `## [Unreleased]` in `CHANGELOG.md`.
4. Run both checks above and open the pull request.

Scripts use the Python standard library. Only the root `README.md` may use emoji.

By contributing, you agree that your work is licensed under the [MIT License](LICENSE).
