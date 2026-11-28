# Changelog

All notable changes to shipkit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- shipkit-feedback: rules for every report (shipkit's own skills only, generic, useful elsewhere, checked before posting), and `feedback.py check [--file]` for issue and pull request text written by hand; drafts and checks refuse names of skills from other packs installed beside shipkit, and `--skill` must be a shipkit skill. A fix for a report follows the same rules: only its generic, shipkit part reaches the current skills, and the added lines and PR body are checked before the commit. Placeholder emails on `example.com`, `.org` and `.net` pass the checker, as URLs there already did. The field report form and CONTRIBUTING.md say the same (2026-11-28)
- stack-cli: an explicit `Environment=PATH=` replaces systemd's default, so keep the sbin and bin folders after the extras, from one shared value; scripts a service, cron or ssh runs look in the sbin folders before saying a tool is missing; a minimal-`PATH` test case and a root-prefix override for scripts that read `/sys` or fixed tool paths (2026-11-27)
- docs/: install, configuration, kits and the autopilot, how the skills work (with the hand-off and routing diagrams), slash commands, self-improvement and development, moved out of the root README, which now keeps the pitch, a quick start, the skill and kit tables and a docs index (2026-11-26)
- stack-cli: a "Running unattended" reference (`references/unattended.md`) for timers that must keep a next run (`OnCalendar=` with `Persistent=true`), ssh connection reuse and backoff on resets, and checking new DNS names against the authoritative server instead of a caching resolver (2026-11-26)
- docsync: `naming_exempt = [...]` in `[docsync]`, paths (or a folder) the naming rule skips, for owner- or tool-mandated names such as `docs/BRIEF.md`; the rule stays on for every other document (2026-11-26)
- fanout: `fanout.py leftovers [--hours N] [--json]`, a read-only report of what finished or abandoned runs left behind: `fanout-*` containers whose plan is missing, whose task landed or that are older than N hours (with their Redis key count), and worktrees and branches of landed, abandoned or planless tasks, each with the exact command to clean it up (2026-11-25)
- Public contribution paths: issue forms for bugs, field reports and features, a pull request template, CONTRIBUTING.md and SECURITY.md (2026-11-22)
- `install.sh --global`: one user-wide install for Claude Code and Codex, with opt-in hooks, a dry run and an uninstall; `doctor.py` reports what this machine lacks, on any Python, with clean `--json`; shipkit-feedback now ships here and finds its repository from the checkout, so forks work (2026-11-21)
- stack-cli skill (`/cli`, `/shell`) and a build step for CLIs, scripts, infrastructure and libraries; harden gains tooling attacks for projects with no API (2026-11-21)
- shipkit-feedback: automatic learnings. Agents save generic drafts locally; `feedback.py` refuses secrets, personal details and project names, removes duplicates, limits filing to three issues a day, and posts only for a user who opted in; a workflow labels each report `needs-review` (2026-11-22)
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

- stack-web: a global reduced-motion rule makes infinite animations flicker; stop looping animations under reduced motion instead (2026-11-26)
- stack-backend: an embedded SQLite section for Node (`node:sqlite`): one module for the database, pragmas and file mode, migrations with a backup first, `db check`, hot copies, a WAL restore drill, index parity with an existing search, and test state folders set before import (2026-11-26)
- stack-web: check contrast once per theme, and status text against its own tint (2026-11-25)
- stack-web: how to run a headless browser check on a Linux server with missing shared libraries, and two measuring pitfalls (2026-11-25)
- stack-cli: what to get right when an installer sets up services: PATH in user units, lingering, proxies that make every request local, self-rewriting configs, pop-on-read queues and tested rollbacks (2026-11-25)
- open-loops and docsync: a new question, bug or attack number is one above the highest on any local or remote branch, in any other worktree's uncommitted copy and in fanout plans, not just on the current branch (`open_loops.py --next-id`, `attacks.py next`, and `attacks.py add` without `--id`); before recording an answer, check that no other branch or worktree has answered the question differently (2026-11-25)
- stack-backend: renaming a stored value that an HMAC or signature covers keeps old records verifying with a `SEALED_AS` alias instead of re-sealing in the migration; a test run that crosses midnight is re-run, and checked on the base branch, before its failures are blamed on the change (2026-11-25)
- docsync: the root README.md may use emoji; every other document still may not (2026-11-21)
- harden: a section for changes that rewrite users' files or delete items: an approved read-only corpus dry run, targets resolved right before deleting, intrinsic duplicate identity, reference checks for binary formats and a staged first run (2026-11-22)
- The public-repository test no longer embeds a private name; `SHIPKIT_PRIVATE_TERMS` points it at your own list of terms kept outside the repository (2026-11-21)
- harden step 6: a test that still passes with its guard removed may miss the guard, or the guard may be dead or covered by another; find which and fix it, and run new timing tests several times for ties (2026-11-16)
- harden: overlapping scheduled jobs that call a provider, claim-then-send, reconciliation over offset-paged listings, and holding a race at the faked provider (2026-11-22)
- kit-build: a Frame step first (the request, assumptions, success criteria as checks, the smallest change), test-first and surgical changes inside each step, and designing an unagreed feature with the user before code (2026-11-12)
- harden: the race gate in the concurrency recipes yields what it held, and the example asserts every request met at the gate; new advice on a gate that never engaged and on a lock taken before the gated read (it makes the gate time out). The test matrix notes that every backticked span under "Covered by" is checked as a test, so codes go in plain text (2026-11-16)
- bug-sweep and harden: cross-site checks prefer `Sec-Fetch-Site`, try JSON sent as `text/plain`, and test a reverse proxy that rewrites `Host` (2026-11-22)
- Kits and the autopilot: an evidence rule; a step is done only with a command run in this session and what it printed, otherwise it is not verified (2026-11-12)
- harden: fix the cause, one hypothesis at a time, and stop after three failed fixes for one flaw to report a design problem; bug-sweep: a suggested fix names the root cause and says when it is partial (2026-11-12)
- stack-backend and fanout: every test and scratch database uses one name function within Postgres's 63 characters, keeping the worker suffix (2026-11-22)
- switchboard: how shipkit works beside general method packs (superpowers, karpathy-guidelines), and which skill decides where they overlap (2026-11-12)
- install.sh writes shipkit.toml from what the project is (`project.py write`) instead of copying the multi-tenant SaaS example into every project; the example is now opt-in with `--preset saas`, and the profile skill is installed with the switchboard (2026-11-12)
- stack-backend: a nullable JSON or JSONB column set to `None` can store JSON `null`, which `IS NOT NULL` lets through (2026-11-22)
- Billing, tenant and pricing guidance applies only when the profile has it: bug-sweep areas and checks, harden's sections and attack matrix, stack-backend (access rules without tenants), stack-web, wire-api, load-sim, perf-watch, feature-map (no tiers without priced plans; `tiers` defaults to none when `[project] plans = "none"`), docsync and seedbed mark those parts with the trait they need (2026-11-12)
- kit.py takes the stack folders shipkit.toml leaves out from the repository instead of assuming `apps/api`, `apps/web` and `apps/mobile` (2026-11-12)
- stack-web: nested vertical scroll areas on touch screens, where `overscroll-contain` belongs, and how to check it with touch emulation (2026-11-22)
- README: badges, navigation and Mermaid diagrams (the three skill groups, a feature end to end, how skills hand off, how the switchboard routes, what install.sh writes, shipkit.toml), a note on installing once for every project, and what CI checks (2026-11-11)

### Fixed

- stack-web: long unbroken outside text (paths, emails, errors) in flex and grid children gets `min-width: 0` and `overflow-wrap: anywhere`, with a per-box spill check and a stress pass; seedbed: one long unbroken value per outside-text field in seeds and mocks; bug-sweep lists the spill (field report #60, 2026-11-28)
- stack-web and stack-native: focus effects never depend on callback props (`useEffectEvent` or a ref), with a browser check on a polling page (field report #59, 2026-11-28)
- fanout and stack-web: a `node_modules` linked into a worktree makes Vite answer 403 for assets; install instead, or allow the real path (field report #58, 2026-11-28)
- stack-backend (Node): no synchronous subprocess or file read on a request path; slow outside state is refreshed in the background with a TTL, and the main read endpoint is timed. stack-web: buttons show a returned promise as pending (never `void`), tap feedback, and phone widths of 360 and 390 px with every page reachable (field report #57, 2026-11-28)
- stack-cli: a wrapper that forwards to a system-changing command must pass `--dry-run` and `--print` to the child, fail closed when it cannot, and be tested with a stub child before its first real call; tools a live service runs are developed in a worktree (field report #55, 2026-11-28)
- stack-cli: stub commands and fixtures print with `printf '%s\n'`, never `echo` (dash expands its escapes); heredocs holding `$` or backslashes quote their delimiter (field report #52, 2026-11-28)
- harden: host-based tests send the `Host` header with `node:http` or `curl`, never Node's `fetch`, which ignores it; assert the server saw the intended identity first (field report #53, 2026-11-28)
- handoff: `log --help` lists the allowed `--status` and `--area` words, and a wrong one fails at the parser; work open in a pull request is Waiting on owner (field report #54, 2026-11-28)
- stack-cli: warns that under `set -e` a false test inside an assignment's command substitution ends the script silently (2026-11-25)
- doctor.py finds tools in `~/.local/bin` when a non-login shell leaves it off PATH (2026-11-21)
- profile: Tauri and Electron apps get a `desktop` surface and `kind = app` instead of being called self-hosted servers; a real server in the repository still counts, and bug-sweep has a desktop area (2026-11-22)
- kit.py and the autopilot read the project they are run from; with skills linked from a shared shipkit checkout they analyzed the shipkit repository instead (2026-11-21)
- On a fresh project, `check_seeds.py`, `open_loops.py`, `feature_map.py` and `changelog.py` (the docsync README example) say in one line that their inputs do not exist yet and exit 0, instead of failing (2026-11-11)
- fanout: `land` refuses a branch that adds `node_modules` or `.venv`, including a symlink that a trailing-slash `.gitignore` pattern misses; stack-web warns that `npx vp` can fetch the wrong package (2026-11-22)
- `isolation_sweep.py` with no server running names the URL it could not reach and says to start the server or pass `--base-url`, with no traceback; exit 2 for a real run, 0 for `--dry-run`; the same goes for an OpenAPI URL that answers an HTTP error such as 401, which gets one line with the URL, the status and a hint about auth or `--base-url` instead of an `HTTPError` traceback (2026-11-11)
- ship-check no longer offers or accepts installed skill folders (`.claude/`, `.agents/`, `.trae/`, anything shipkit installed) as project evidence, and a repository with no commits, or a folder that is not a git checkout at all (a plain `npm create vite`), gets a "no commits yet" or "not a git checkout" line and a note from `check` instead of a missing-SHA failure (2026-11-11)
- fanout reserves attack-log numbers beside migrations, questions and bugs, and `attacks.py add --id` uses a reserved number, so branches from one base no longer take the same `ATK-NNN` (2026-11-22)
- install.sh reports how many skills each layout really got and lists the ones it skipped; `--dry-run` says "would install" and "would write" and never claims it wrote shipkit.toml or anything else (2026-11-11)
- kit.py: the first uncommitted file lost its first letter (git's status output was stripped before parsing), and the installed skills, commands and shipkit.toml counted as the project's code changes, so the autopilot asked to /break a fresh install (2026-11-12)

## [0.1.0] - 2026-11-11

### Added

- Seventeen skills in three groups: Build (stack-backend, stack-web, stack-native, wire-api, seedbed, fanout), Break & Test (harden, bug-sweep, load-sim, perf-watch, triage-report, ship-check) and Docs & Flow (docsync, feature-map, open-loops, handoff, switchboard) (2026-11-11)
- install.sh for Claude Code (.claude/skills and slash commands), Cursor and Codex (.agents/skills and AGENTS.md) and Trae (.trae/skills) (2026-11-11)
- shipkit.toml configuration with a generic SaaS example; scenario configs for seedbed and load-sim (2026-11-11)
