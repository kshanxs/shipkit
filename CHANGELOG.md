# Changelog

All notable changes to shipkit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Kits: one command per group that runs its skills in order and only what fits the repository now (each step run, skip with the reason, or blocked with what is missing): kit-build (`/build`), kit-break (`/break`, tiers quick, full and launch), kit-flow (`/flow`, `/flow start`) and kit-feature (`/feature`: build, break, flow) (2026-11-11)
- The autopilot (`/shipkit`, `/auto`, or "run shipkit"): decides from what changed, new commits, schema changes, the registers that exist and whether the local stack answers which kits and skills to run now, runs them, and lists what is ready on request and what cannot run yet (2026-11-11)
- switchboard: `kit.py` (plan, auto, facts, members) and `kits.toml`; a named kit or the autopilot comes alone from the router (2026-11-11)
- install.sh: `--skills kit-break` (or any kit, or autopilot) also installs the skills it runs and the ones they hand work to (2026-11-11)

### Changed

- README: badges, navigation and Mermaid diagrams (the three skill groups, a feature end to end, how skills hand off, how the switchboard routes, what install.sh writes, shipkit.toml), a note on installing once for every project, and what CI checks (2026-11-11)

## [0.1.0] - 2026-11-11

### Added

- Seventeen skills in three groups: Build (stack-backend, stack-web, stack-native, wire-api, seedbed, fanout), Break & Test (harden, bug-sweep, load-sim, perf-watch, triage-report, ship-check) and Docs & Flow (docsync, feature-map, open-loops, handoff, switchboard) (2026-11-11)
- install.sh for Claude Code (.claude/skills and slash commands), Cursor and Codex (.agents/skills and AGENTS.md) and Trae (.trae/skills) (2026-11-11)
- shipkit.toml configuration with a generic SaaS example; scenario configs for seedbed and load-sim (2026-11-11)
