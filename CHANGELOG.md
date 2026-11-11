# Changelog

All notable changes to shipkit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- The project profile: a `[project]` table in shipkit.toml (kind, tenancy, money, plans, auth, surfaces, offline), and `switchboard/scripts/project.py` (show, detect, toml, write, has) that detects it from the repository with the evidence for each value, keeps whatever shipkit.toml sets, and never assumes what it cannot find (2026-11-12)
- profile skill (`/profile`, `/configure`): an agent fills in shipkit.toml from the project: detects the profile, the API, web and mobile folders, packages, code roots and ports, checks every guess against the code, asks only what the code cannot answer, and adds to an existing file without changing what is set (2026-11-12)
- kits.toml `needs`: a step whose traits the profile lacks is skipped with the reason; load-sim and perf-watch need a multi-tenant project. The autopilot prints the profile first and lists `/profile` while shipkit.toml has no `[project]` (2026-11-12)
- ship-check: `requires` on checklist groups and items, filtered by the profile, with what was left out named in the report; new items for self-hosted servers (cross-site requests, DNS rebinding, bind address, secrets on disk, data safety, upgrades), CLIs, libraries (releases and distribution) and machine-changing scripts (2026-11-12)
- bug-sweep and harden: local network checks for self-hosted servers (Origin or CSRF on every change, Host allow-list against DNS rebinding, what answers without a password); attack matrix section 9; areas for access control and the command line (2026-11-12)
- Kits: one command per group that runs its skills in order and only what fits the repository now (each step run, skip with the reason, or blocked with what is missing): kit-build (`/build`), kit-break (`/break`, tiers quick, full and launch), kit-flow (`/flow`, `/flow start`) and kit-feature (`/feature`: build, break, flow) (2026-11-11)
- The autopilot (`/shipkit`, `/auto`, or "run shipkit"): decides from what changed, new commits, schema changes, the registers that exist and whether the local stack answers which kits and skills to run now, runs them, and lists what is ready on request and what cannot run yet (2026-11-11)
- switchboard: `kit.py` (plan, auto, facts, members) and `kits.toml`; a named kit or the autopilot comes alone from the router (2026-11-11)
- install.sh: `--skills kit-break` (or any kit, or autopilot) also installs the skills it runs and the ones they hand work to (2026-11-11)
- `isolation_sweep.py --base-url` points a sweep, and an OpenAPI URL on the same server, at another address (2026-11-11)

### Changed

- kit-build: a Frame step first (the request, assumptions, success criteria as checks, the smallest change), test-first and surgical changes inside each step, and designing an unagreed feature with the user before code (2026-11-12)
- Kits and the autopilot: an evidence rule; a step is done only with a command run in this session and what it printed, otherwise it is not verified (2026-11-12)
- harden: fix the cause, one hypothesis at a time, and stop after three failed fixes for one flaw to report a design problem; bug-sweep: a suggested fix names the root cause and says when it is partial (2026-11-12)
- switchboard: how shipkit works beside general method packs (superpowers, karpathy-guidelines), and which skill decides where they overlap (2026-11-12)
- install.sh writes shipkit.toml from what the project is (`project.py write`) instead of copying the multi-tenant SaaS example into every project; the example is now opt-in with `--preset saas`, and the profile skill is installed with the switchboard (2026-11-12)
- Billing, tenant and pricing guidance applies only when the profile has it: bug-sweep areas and checks, harden's sections and attack matrix, stack-backend (access rules without tenants), stack-web, wire-api, load-sim, perf-watch, feature-map (no tiers without priced plans; `tiers` defaults to none when `[project] plans = "none"`), docsync and seedbed mark those parts with the trait they need (2026-11-12)
- kit.py takes the stack folders shipkit.toml leaves out from the repository instead of assuming `apps/api`, `apps/web` and `apps/mobile` (2026-11-12)
- README: badges, navigation and Mermaid diagrams (the three skill groups, a feature end to end, how skills hand off, how the switchboard routes, what install.sh writes, shipkit.toml), a note on installing once for every project, and what CI checks (2026-11-11)

### Fixed

- On a fresh project, `check_seeds.py`, `open_loops.py`, `feature_map.py` and `changelog.py` (the docsync README example) say in one line that their inputs do not exist yet and exit 0, instead of failing (2026-11-11)
- `isolation_sweep.py` with no server running names the URL it could not reach and says to start the server or pass `--base-url`, with no traceback; exit 2 for a real run, 0 for `--dry-run`; the same goes for an OpenAPI URL that answers an HTTP error such as 401, which gets one line with the URL, the status and a hint about auth or `--base-url` instead of an `HTTPError` traceback (2026-11-11)
- ship-check no longer offers or accepts installed skill folders (`.claude/`, `.agents/`, `.trae/`, anything shipkit installed) as project evidence, and a repository with no commits, or a folder that is not a git checkout at all (a plain `npm create vite`), gets a "no commits yet" or "not a git checkout" line and a note from `check` instead of a missing-SHA failure (2026-11-11)
- install.sh reports how many skills each layout really got and lists the ones it skipped; `--dry-run` says "would install" and "would write" and never claims it wrote shipkit.toml or anything else (2026-11-11)
- kit.py: the first uncommitted file lost its first letter (git's status output was stripped before parsing), and the installed skills, commands and shipkit.toml counted as the project's code changes, so the autopilot asked to /break a fresh install (2026-11-12)

## [0.1.0] - 2026-11-11

### Added

- Seventeen skills in three groups: Build (stack-backend, stack-web, stack-native, wire-api, seedbed, fanout), Break & Test (harden, bug-sweep, load-sim, perf-watch, triage-report, ship-check) and Docs & Flow (docsync, feature-map, open-loops, handoff, switchboard) (2026-11-11)
- install.sh for Claude Code (.claude/skills and slash commands), Cursor and Codex (.agents/skills and AGENTS.md) and Trae (.trae/skills) (2026-11-11)
- shipkit.toml configuration with a generic SaaS example; scenario configs for seedbed and load-sim (2026-11-11)
