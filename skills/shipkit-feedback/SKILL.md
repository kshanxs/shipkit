---
name: shipkit-feedback
description: "Turn a lesson from real project work into a shipkit improvement, as a separate pull request or issue on the shipkit repository the user runs, a fork included. Writes the lesson in generic terms, with no project names, private paths or secrets, and never mixes it into the project's commits. Use when the user says 'improve shipkit', 'update the skill', 'shipkit feedback' or 'field report', or when their instructions ask for this after coding tasks."
---

# shipkit-feedback

Shipkit and the project you worked in are **two separate repositories**. Project changes stay in the
project. A shipkit change goes through its own branch and pull request, after the project task is
done. Publish nothing unless the user asked for it or their standing instructions say to.
`$SK` is the skills folder this skill is installed in.

## 1. Decide

- Did a skill say something wrong, outdated or incomplete?
- Did you repeat a generic mistake, or work out a technique a skill should teach?
- Is there no skill for a kind of work that will come up again?

If none, say `Shipkit: nothing to improve` and stop. Otherwise write the lesson in **generic** terms:
no project or client names, private paths, hostnames, secrets or business details. Project-specific
values belong in that project's `shipkit.toml`.

## 2. Find the shipkit repository

```bash
S="$(git -C "$(cd "$SK/shipkit-feedback" && pwd -P)" rev-parse --show-toplevel 2>/dev/null || true)"
[ -f "$S/install.sh" ] && [ -f "$S/skills/switchboard/kits.toml" ] || S=""
[ -z "$S" ] || R="$(cd "$S" && gh repo view --json nameWithOwner --jq .nameWithOwner)"
```

If `S` is empty, shipkit was installed as a copy. Use `[feedback] repo` from the project's
`shipkit.toml`, else `kshanxs/shipkit`, and file an issue (step 4b).

## 3. Check what is already open

```bash
gh pr list -R "$R" --state open
gh issue list -R "$R" --state open --search "<the skill and the gap>"
```

Add to an open PR or issue on the same point instead of opening a duplicate.

## 4a. Small, clear fix: pull request

A checkout that skills link to is live: never edit, branch or check out in it. Use a worktree.

```bash
slug=<short-kebab-name>
W="${SHIPKIT_WORKTREES:-$HOME/.cache/shipkit/worktrees}/$slug"
git -C "$S" fetch --quiet origin
git -C "$S" worktree add "$W" -b "improve/$slug" origin/main
cd "$W"
```

1. Change the skill's `SKILL.md`, and its scripts, references and tests where they apply.
2. Changed triggers, names or commands: edit `skills/switchboard/skills.toml`, then run
   `python3 skills/switchboard/scripts/route.py --write`.
3. Add a dated line under `## [Unreleased]` in `CHANGELOG.md`.
4. Run `uv run pytest` and `python3 skills/switchboard/scripts/route.py --check`.
5. Commit, push and open the PR with **Field report**, **Lesson**, **Change** and **Checks run**.
   Without write access to `R`, `gh pr create` offers to use your fork.
6. Do not merge unless the user says so. After the merge, run `git -C "$S" worktree remove "$W"`.

## 4b. Bigger or unclear: issue

```bash
gh issue create -R "$R" --title "<skill>: <the gap>" --body "<field report, lesson, proposed change>"
```

Add `--label field-report` when the repository has that label.

## 5. Report

End your reply with `Shipkit: PR <url>`, `Shipkit: issue <url>` or `Shipkit: nothing to improve`.
