# Configuration

One file, `shipkit.toml`, at the project root. The installer writes it from what the project is
(`project.py write`), and `/profile` checks every guess against the code. See
[every table, as the multi-tenant SaaS preset](../shipkit.example.toml).

## The project profile

The `[project]` table is the profile every skill runs by. A value set there wins; a value left out
is detected; nothing undetected is assumed.

| Key | Values |
|---|---|
| `kind` | `saas`, `self-hosted`, `app`, `cli`, `library`, `infra`, `container-app` |
| `tenancy` | `none`, `single-user`, `multi-user`, `multi-tenant` |
| `money` | `none`, `payments` |
| `plans` | `none`, `tiers` (priced plans) |
| `auth` | `none`, `local`, `accounts` |
| `surfaces` | any of `api`, `web`, `native`, `desktop`, `cli`, `shell`, `container`, `library` |
| `offline` | `true`, `false` |

So a self-hosted tool never gets billing checks, a library never gets a many-tenant load test, and a
multi-tenant SaaS with payments gets all of it. Kit steps (`needs` in kits.toml), ship-check items
(`requires`) and skill sections marked **[money]**, **[multi-tenant]**, **[plans]** or
**[self-hosted]** apply only when the profile has the trait.

```bash
python3 <skills>/switchboard/scripts/project.py show        # print the profile
python3 <skills>/switchboard/scripts/project.py has money   # yes or no
```

## Other tables and files

```mermaid
flowchart LR
    toml["shipkit.toml"] --> proj["[project]<br/>kind, tenancy, money, plans"]
    toml --> stack["[stack]<br/>api, web and native dirs"]
    toml --> docsync["[docsync]<br/>docs, packages, registers"]
    toml --> hardent["[harden]<br/>matrix and axes"]
    toml --> loopst["[open_loops]<br/>register"]
    toml --> more["one table per skill<br/>missing table = defaults"]
    seedt["seedbed.toml"] --> seedbed["seedbed"]
    loadt["load-scenario.toml"] --> loadsim["load-sim"]
    shipt["ship-check.toml"] --> shipc["ship-check"]
```

Three skills take their own files: `seedbed.toml` (seed modules, scenarios, personas),
`load-scenario.toml` (traffic) and an optional `ship-check.toml` (the checklist). The first two have
an `init` command that writes the generic example.
