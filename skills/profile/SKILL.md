---
name: profile
description: "Fills in shipkit.toml for the project it is in: detects what kind of project it is (SaaS, self-hosted app, CLI, library, infrastructure scripts, container app), whether it has tenants, takes money, sells priced plans, has accounts or works offline, and where its API, web and mobile code, docs, packages and ports are; checks every guess against the code; asks only what the code cannot answer; and writes the [project] profile every other skill uses to run only what fits. Use when shipkit is installed in a project, when shipkit.toml is missing, has no [project] or no longer matches the code, when the autopilot lists /profile, when a skill talks about billing, tenants or pricing the project does not have, and when the user says 'set up shipkit', 'configure shipkit', 'fill the toml', 'profile', 'what kind of project is this' or 'shipkit.toml'."
---

# Profile: fill in shipkit.toml from the project

Every shipkit skill reads `shipkit.toml`. Its `[project]` table says what kind of project this is,
and the skills hold themselves to it: a project that takes no money gets no billing checks, one
with no tenants gets no tenant-isolation sweep or many-tenant load test, one with no priced plans
gets no pricing page checks. This skill fills that file in so the user does not have to.
`$SK` is the skills folder this skill is installed in.

```bash
P="python3 $SK/switchboard/scripts/project.py"
$P show        # the effective profile: what shipkit.toml sets, and what is detected for the rest
$P detect      # what the repository alone shows, with the evidence for each value
$P toml        # a complete shipkit.toml for this repository (printed, nothing written)
$P write       # write it: a new shipkit.toml, or add only the tables and keys an existing one lacks
$P has money   # exit 0 when the profile has every trait named (multi-tenant, money, plans, self-hosted, ...)
```

## 1. Detect

Run `$P detect`, then `$P toml`. Each `[project]` line ends with how it was found:

| Note | Meaning | What you do |
|---|---|---|
| `detected: <paths>` | a manifest or many files show it | keep it unless the paths are clearly wrong |
| `guess, check it: <paths>` | counted from words in the code | open the paths and confirm or correct it |
| `guess, check it` (no paths) | nothing was found either way | decide from the README and the code, or ask |
| `set` | already in shipkit.toml | keep it; never overwrite what the user set |

## 2. Check every guess against the code

Read what the evidence points at, plus the README and the main entry points. Decide each value:

| Key | Values | How to decide |
|---|---|---|
| `kind` | saas, self-hosted, app, cli, library, infra, container-app | **saas**: you run it for many customers. **self-hosted**: users run their own copy (a server on their machine, NAS or home server). **container-app**: packaging of an app for an app store or compose (no code of its own). **app**: a client app (mobile, desktop, single-user web) that is neither. **cli** / **library**: installed and run or imported. **infra**: scripts and config that set up machines |
| `tenancy` | none, single-user, multi-user, multi-tenant | **multi-tenant**: records belong to an organisation, workspace or team and one must never see another's. **multi-user**: many accounts, no separate organisations. **single-user**: one person or household per install. **none**: no users at all (a library, a script) |
| `money` | none, payments | **payments**: it charges, invoices, refunds or records fees. A word like "invoice" in a list of features is not payments; code that moves or records money is |
| `plans` | none, tiers | **tiers**: customers buy priced plans (Free, Pro, ...) and features are sold by plan |
| `auth` | none, local, accounts | **accounts**: sign-up, sign-in, invites, password reset. **local**: one password, token or API key guards the app |
| `surfaces` | api, web, native, cli, shell, container, library | every part that exists: a server API, a web front end, a mobile app, a command line, shell scripts, a Dockerfile or compose file, an importable package |
| `offline` | true, false | **true** only when the app keeps working with no network and syncs later (a local database and an outbox). A cache or an install-to-home-screen web app is not offline |

Then the rest of the file:

- `[stack]`: the API, web and mobile folders. `""` or `[]` when there is none, so no skill looks
  for `apps/api` in a project that does not have it.
- `[docsync]`: `packages` (each with its own CHANGELOG.md; `[]` for one package), `code_roots`
  (where the source lives), `docs_dir`.
- `[feature_map] tiers`: the real plan names, cheapest first, only when `plans = "tiers"`;
  otherwise `[]`.
- `[fanout] ports`: the ports the dev servers really use (read the dev scripts and configs).
- `[handoff] timezone` and `[triage] timezone`: the owner's time zone when the repository shows it.

## 3. Ask only what is left

When the code cannot decide a value (a payments folder that may be dead code; a server that may be
hosted for others or only self-hosted), ask the user, one question at a time, leading with your
recommended answer and the evidence, so one word settles it. Never ask about a value the code
decides. Never invent a plan name, price or port.

## 4. Write and verify

1. With no shipkit.toml: `$P write`, then edit the lines your checks corrected. With one: `$P write`
   adds only missing tables and keys; edit corrected values by hand, and never change a value the
   user set without asking.
2. Remove the `guess, check it` notes from the lines you confirmed, so the next reader knows they
   were checked.
3. `$P show` must exit 0 (every value one of the allowed words) and print the profile you decided.
4. `python3 $SK/switchboard/scripts/kit.py auto` must no longer list `/profile`, and its plans must
   skip what the project does not have.
5. Tell the user the profile in one line and which values you corrected from the detection.

## When to run it again

When the project changes kind: it starts taking payments, adds organisations, ships a mobile app,
moves its code. Run `$P detect` and compare it with `[project]`; propose each change, and change
nothing the user set without asking.

## Rules

- shipkit.toml is the user's file: add, never overwrite a value they set.
- Undetected is absent, not assumed: no tenant code means not multi-tenant, no payment code means
  no money. Never fall back to "a SaaS with billing".
- A trait a skill needs and the profile lacks means the skill skips that part and says so. If a
  skill still talks about something the project does not have, fix the profile or report it with
  `shipkit-feedback`.
