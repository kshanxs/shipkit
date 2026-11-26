# Developing shipkit

```bash
uv run pytest                                           # every skill's tests, the installer and the layout rules
python3 skills/switchboard/scripts/route.py --check     # skills.toml and the shipped commands in step
python3 skills/switchboard/scripts/route.py --write     # after editing skills.toml
```

CI runs both on Python 3.11 and 3.13 for every push and pull request. The layout tests hold the repo
to its own rules: every skill has frontmatter, a README, a router entry and commands; the root README
lists every skill; and no home paths, key-shaped strings or private terms appear in a public file.
Set `SHIPKIT_PRIVATE_TERMS` to a file of your own terms to check for those too.

Only the root `README.md` may use emoji; every other document may not. Log each change under
`## [Unreleased]` in [CHANGELOG.md](../CHANGELOG.md). See [CONTRIBUTING.md](../CONTRIBUTING.md) for
issues and pull requests.
