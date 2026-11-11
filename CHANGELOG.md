# Changelog

All notable changes to shipkit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `isolation_sweep.py --base-url` points a sweep, and an OpenAPI URL on the same server, at another address (2026-11-11)

### Fixed

- On a fresh project, `check_seeds.py`, `open_loops.py`, `feature_map.py` and `changelog.py` (the docsync README example) say in one line that their inputs do not exist yet and exit 0, instead of failing (2026-11-11)
- `isolation_sweep.py` with no server running names the URL it could not reach and says to start the server or pass `--base-url`, with no traceback; exit 2 for a real run, 0 for `--dry-run`; the same goes for an OpenAPI URL that answers an HTTP error such as 401, which gets one line with the URL, the status and a hint about auth or `--base-url` instead of an `HTTPError` traceback (2026-11-11)
- ship-check no longer offers or accepts installed skill folders (`.claude/`, `.agents/`, `.trae/`, anything shipkit installed) as project evidence, and a repository with no commits, or a folder that is not a git checkout at all (a plain `npm create vite`), gets a "no commits yet" or "not a git checkout" line and a note from `check` instead of a missing-SHA failure (2026-11-11)
- install.sh reports how many skills each layout really got and lists the ones it skipped; `--dry-run` says "would install" and "would write" and never claims it wrote shipkit.toml or anything else (2026-11-11)

## [0.1.0] - 2026-11-11

### Added

- Seventeen skills in three groups: Build (stack-backend, stack-web, stack-native, wire-api, seedbed, fanout), Break & Test (harden, bug-sweep, load-sim, perf-watch, triage-report, ship-check) and Docs & Flow (docsync, feature-map, open-loops, handoff, switchboard) (2026-11-11)
- install.sh for Claude Code (.claude/skills and slash commands), Cursor and Codex (.agents/skills and AGENTS.md) and Trae (.trae/skills) (2026-11-11)
- shipkit.toml configuration with a generic SaaS example; scenario configs for seedbed and load-sim (2026-11-11)
