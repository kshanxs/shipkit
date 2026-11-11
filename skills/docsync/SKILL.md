---
name: docsync
description: "The documentation contract for any repository: every code change is logged in its package's changelog, every feature has a spec, a tracker row and a place in the feature map, bugs and attacks have registers that agree with the changelogs, releases are cut from the changelogs, and check_docs.py enforces what a machine can (links, headings, fences, emoji, naming, retired terms, status lines, the code map, Unreleased format, the bug register, the attack log, what must change together). Runs as a script, a Claude Code stop hook and git hooks. Use at the start and end of any code change; when a markdown file, changelog or spec is created, renamed or edited; when a bug is found, filed or fixed; when a release is cut; and when the user says 'document this', 'update the docs', 'changelog', 'release', 'bug', 'what did we build', 'what is the status' or 'sync docs'."
---

# Docsync

Three promises:

1. **Nothing changes silently.** Every code change is in its package's changelog the day it is made.
2. **Nothing exists undocumented.** Every feature has a spec, a tracker row and a place in the
   feature map (under a tier, or in the queue of features waiting for one).
3. **Nothing is promised that is not true.** Pricing pages, policies and every status say what the
   code does today.

`check_docs.py` enforces what a machine can check. Paths and rules come from the `[docsync]` table
of `shipkit.toml` ([references/config.md](references/config.md)); a check whose files are absent is
skipped, so a small project gets only the checks it can use. `$SK` is the skills folder this skill
is installed in.

```bash
D="python3 $SK/docsync/scripts"
$D/check_docs.py --changed            # this change set: documents, plus what must change together. Exit 1 on error
$D/check_docs.py --changed --base main
$D/check_docs.py --changed --staged   # what a commit would contain (the pre-commit hook)
$D/check_docs.py --strict             # warnings fail too; --map prints who links to what
$D/changelog.py add api fixed "An invoice was charged twice" --doc docs/features/billing.md
$D/changelog.py release 0.3.0         # Unreleased becomes [0.3.0] - today, in every log with entries
$D/attacks.py add|run|report|check    # the attack log (harden skill)
```

## The workflow

### Before changing code

1. Read the feature's tracker row (`docs/feature_status.md`) and its spec (the tracker's code map
   names the document for every module).
2. Read the top of the package's `CHANGELOG.md`.
3. If the documents disagree with the code you are about to change, the code is right: correct the
   document as part of this change.
4. Work that takes more than one sitting: set the feature to **In progress** in the tracker, naming
   the branch.

### After changing code, every time

5. **Changelog.** One line under `## [Unreleased]` in each changed package's `CHANGELOG.md`, with
   `changelog.py add`. A bug fix counts. Two packages, two entries.
6. **The spec**, so it describes the new behaviour, and its status line.
7. **The tracker** row (status, note) and the summary counts.
8. **The policy check**, if the project has one: when a change touches personal data, a new outside
   service or what customers are promised, draft the policy wording and list it for the owner.
9. **What changes together** (below).
10. **Product-level logs:** the root `CHANGELOG.md` for what a customer would notice; a dated entry
    in `docs/bugs_fixed_and_improvements.md` when the reasoning matters later.
11. **Run the checks** and fix what they report: `check_docs.py --changed`.
12. **Report** what changed, what was documented, what the policy check found, and what waits for a
    person. Do not commit unless asked.

### A new feature

Steps 5 to 12, and first: a spec from
[references/feature_spec_template.md](references/feature_spec_template.md) at
`docs/features/<feature>.md` (a sub-feature gets a section with its own dated status line); a
tracker row and a code map row; a line in the feature map (feature-map skill). **Do not choose its
tier**: put it in the queue of features waiting for one, with the date and a note for the decision.
It is not on a pricing page or a plan card until it is built and has a tier.

### A bug fix

1. Find or file its row in the bug register (`docs/testing/bug_report.md`): the next free `BUG-NNN`,
   a severity (Critical, High, Medium, Low), where, what is wrong, what closes it.
2. Write the test that fails because of the bug; watch it fail. If none can be written, say why.
3. Fix the cause; look for the same mistake elsewhere. Run the tests.
4. Record it: a `Fixed` line naming the bug (`Security` when it let someone see or do what they
   should not), the row moved to Closed with the date, the fix and the test; for Critical or High, a
   history entry with the cause, why it was not caught and what stops it returning; and, when an
   attack found it, its attack log row (`attacks.py add ... --fixed BUG-NNN`).

## Where each record lives

| Question | Answered by |
|---|---|
| What changed in this package, and when? | `<package>/CHANGELOG.md` |
| What changed that a customer would notice? | `CHANGELOG.md` |
| Why was it changed; what was the bug? | `docs/bugs_fixed_and_improvements.md` |
| What waits for an answer? | `docs/open_questions.md` (open-loops skill) |
| Which bugs are open, and what closed the others? | `docs/testing/bug_report.md` |
| What has been attacked on purpose, and what held? | `docs/testing/attack_log.md` (harden skill) |
| What is built, in progress, next, planned? | `docs/feature_status.md`, with the code map |
| How does a feature behave? | `docs/features/<feature>.md` |
| Which tier is it in? | `docs/feature_catalog.md` (feature-map skill) |
| What was decided, and why? | `docs/architecture/decisions.md` |

Every subject has one home; other documents link to it and do not copy its tables. Rename any of
these paths in `[docsync]`.

## Status words

| Word | Means |
|---|---|
| Built | Works end to end |
| Partly built | Some of it works; say which part |
| Backend only / Frontend only | One side exists |
| In progress | Being built now; name the branch |
| Next | Not built; to be built next |
| Planned | Not built; no date |
| Coming soon | Not built; deliberately later. The only not-built status shown to customers |

A status line sits under the title of every spec: `> **Status (YYYY-MM-DD): Built.** <note>`, the
date being the day it was last checked against the code. Change the words in `[docsync] statuses`.

## Changelogs

Keep a Changelog sections under `## [Unreleased]`: Added, Changed, Deprecated, Removed, Fixed,
Security. One line per change: what changed for the person using it, the date, a link to the
document that describes it.

```markdown
### Fixed

- A late fee was charged twice when a payment and the nightly job ran together (2026-10-07) — [Billing](../../docs/features/billing.md)
```

The entry is written by whoever made the change, never generated from commit messages. Add, never
rewrite; one heading per type (`changelog.py tidy` joins repeats without changing an entry).
Commit messages are Conventional Commits (`type(scope): summary`); the `commit-msg` hook checks
them. A release (`changelog.py release 0.3.0`) is chosen by the owner; the script prints the
`git tag` command and does not tag.

## What changes together

| When this changes | Update |
|---|---|
| New feature | Its spec, the tracker (row, code map, counts), the feature map's queue, the features index |
| Feature shipped, changed or fixed | The changelog, the spec and its status line, the tracker, the feature map line (and the pricing page if a status crossed built / not built) |
| A feature gets a tier | The feature map, the spec, the tracker, the pricing page, the policy check |
| Price | The pricing document, the pricing page, the policies, any mock plans |
| Table or column | A migration, the spec's data section, the seed and the data map (seedbed) |
| Route | The spec's API section, generated types (wire-api) |
| Role or permission | The role pages and the data map, the spec's permissions section |
| A new outside service, or data sent somewhere new | The policy check, the infrastructure document |
| An attack made on purpose | The attack log (`attacks.py add`), whatever the result; a flaw goes through the bug fix steps |
| A document's name or place | [references/structure.md](references/structure.md) |
| A skill added or renamed | The switchboard's `skills.toml`, then `route.py --write` and `--check` |

## Writing rules

1. Say what is true today; check every claim against the code.
2. Add to a document; do not rewrite what others wrote unless it is wrong, and then say so in the
   history. Never delete a log entry or a tracker row; change its status.
3. Link, do not copy. Relative links between repository files, with a heading anchor where a
   section is meant.
4. Dates are absolute (`2026-10-06`), never "recently".
5. Never invent a fact: a price, a tier, a company detail, a legal claim, a metric. A missing fact
   becomes an open question. No document claims legal compliance.
6. Policy wording is drafted, then reviewed by the owner.
7. No emoji (ticks, crosses, warning signs, coloured dots): write Yes, No, Done, Warning.
8. Generated blocks are never edited by hand.

## Checks

| Check | Fails when |
|---|---|
| `links` | A relative link or image points at a missing file or heading |
| `fences`, `escapes` | A code fence is not closed; a table or SQL line holds a literal `\n` |
| `emoji` | A document uses an emoji, a tick or cross, or a coloured dot |
| `naming`, `scratch` | A file under `docs/` breaks the naming rule (`snake`, `kebab`, `lower` or `any`); a `TODO.md` sits in a package |
| `stale` | A retired name, price or path from `[[docsync.stale]]` is used outside the logs and its allowed files |
| `coverage` | A folder under `code_roots` is missing from the tracker's code map |
| `status` | A spec has no dated status line |
| `plan` | A spec is linked from none of `plan_sources` |
| `unreleased` | A changelog's Unreleased section is malformed |
| `bugs` | The bug register repeats an id, an open bug has no severity, or a fixed bug is still open |
| `attacks` | The attack log is malformed, names a missing test, or disagrees with the register |
| `changelog` (with --changed) | A package's code changed and its changelog did not |
| `policy` (with --changed) | A policy page changed and its stamp file did not |
| `pairs`, `docs`, `spec`, `tests`, `attacks` (warnings) | One file of a pair changed alone; code changed and no doc did; a module changed and its spec did not; a fix was logged and no test changed; a race test changed and the attack log did not |
| `orphans`, `index`, `matrix` (warnings) | A document nothing links to; a docs folder missing from the index; the test matrix names something that does not exist |

The checks see files, not meaning: steps 6 to 9 are still yours.

## Enforcement

| Where | When | Set up by |
|---|---|---|
| Claude Code stop hook | An agent tries to finish | `install.sh --hooks` adds `scripts/stop_hook.py` to `.claude/settings.json`. It blocks once with the errors, then lets the session end |
| Git pre-commit hook | Every commit | `git config core.hooksPath <skills>/docsync/hooks` (or copy `hooks/pre-commit` into your hooks folder) |
| Git commit-msg hook | Every commit | The same folder: refuses a first line that is not a Conventional Commit |
| CI | Every pull request | A job that runs `check_docs.py --changed --base origin/main` |

If the stop hook's errors come from a change that is not yours, leave it alone and say so; the
second stop goes through. `git commit --no-verify` is for a deliberate exception, said in the
message. Do not weaken a check to get past it: change the rule in config (or the script, with a
test), and record why.
