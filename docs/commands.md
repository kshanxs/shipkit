# Slash commands

Every command is `/<short> <what to do>`, for example `/harden the checkout endpoint against double
submit` or `/break full`. In agents without slash commands, write `@<short>` in the message.

| Build | Break & Test | Docs & Flow |
|---|---|---|
| `/api` `/be` stack-backend | `/harden` `/bth` harden | `/docs` `/ds` docsync |
| `/web` `/fe` stack-web | `/sweep` `/hunt` bug-sweep | `/fmap` `/features` feature-map |
| `/native` `/rn` `/mobile` stack-native | `/load` `/sim` load-sim | `/loops` `/oq` open-loops |
| `/cli` `/shell` stack-cli | `/perf` `/mon` perf-watch | `/handoff` handoff |
| `/wire` wire-api | `/triage` `/report` triage-report | `/skillfix` shipkit-feedback |
| `/seed` seedbed | `/ship` `/ready` ship-check | `/sb` `/route` switchboard |
| `/fanout` `/par` fanout | | `/profile` `/configure` profile |

| Kits |
|---|
| `/build` kit-build, `/break` `/bt` kit-break, `/flow` kit-flow, `/feature` kit-feature, `/shipkit` `/auto` autopilot |

The short names and trigger phrases live in `skills/switchboard/skills.toml`. After editing it, run
`python3 skills/switchboard/scripts/route.py --write`.
