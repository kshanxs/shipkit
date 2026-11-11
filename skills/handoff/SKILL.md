---
name: handoff
description: "The shared memory between agent sessions, kept in HANDOFF.md in the repository: at the start of a session, read Now, Next up, Waiting on the owner, Blocked, Rules and the newest Work log rows; at the end of any session that changed anything, add one Work log row (handoff.py log) and update Now, Next up, Waiting and Blocked in place. Works in any agent (Claude Code, Cursor, Codex, Trae); Notion or another tool is an optional adapter. If the file cannot be read it says so and carries on, and never invents handoff content. Use when a session starts or ends, after a usage limit or a switch of tool, and when the user says 'handoff', 'where did we leave off', 'what is next', 'log this' or 'work log'."
---

# Handoff

One file is the shared memory of every agent working on the project. A session reads it first and
updates it last, so the next session (after a usage limit, a new chat or another tool) starts where
this one stopped.

The file holds what is happening and what comes next. The repository holds what the code does:
when they disagree, the repository wins, and the Work log row says so. Decisions and open questions
about the product go to the open questions register (open-loops skill), not only here.

`$SK` is the skills folder this skill is installed in.

## Where

`HANDOFF.md` at the project root, or `[handoff] file` in `shipkit.toml`. Also there: `owner` (who
answers the Waiting items), `timezone` (an IANA name for log dates; default the machine's),
`statuses` and `areas` (the words a row may use).

```bash
H="python3 $SK/handoff/scripts/handoff.py"
$H init          # write HANDOFF.md from references/HANDOFF.template.md
$H show          # the sections and the newest 8 Work log rows (--log N for more)
$H log --entry "Billing retries" --agent Claude --area Dev \
   --changed "Payments retry twice on a timeout" --links "PR #12 (abc1234)" \
   --next "Add the refund webhook test" --status "In progress"
$H check         # sections present, log rows well formed
```

Using Notion (or another shared tool) instead of, or beside, the file: see
[references/notion-adapter.md](references/notion-adapter.md). The steps are the same; only where
they are written changes.

## If the handoff cannot be read

No file, no access, or a read that fails twice:

1. Tell the user in one line: "Handoff not read: <reason>."
2. Carry on with the task. Do not stop because of it.
3. Never fill the gap from memory, an older chat or a guess. Say nothing about what Now or Next up
   contain; you have not read them.
4. At the end, print the Work log row you would have added and the Now and Next changes, under the
   heading "Handoff not written", so the user or the next session can paste them.

## At session start

1. **Read the file** top to bottom: Now, Next up, Waiting on the owner, Blocked, Rules, Page map.
2. **Read the newest Work log rows** (5 to 10). Note which agent did what, and any row In progress
   or Blocked: that is often the place to resume.
3. **Open only the Page map entries the task touches.**
4. **Check the repository when the task is code** (`git fetch`, look at the branch): a log row may
   be older than the branch.
5. **Tell the user where things stand** in one or two lines: what is in progress, what the task
   touches, what waits on the owner.

## Rules (the file's Rules section wins if they differ)

Re-read the Rules section each session. The template starts with:

- Work is plan-only unless the owner says build.
- No deletions, merges or sends without an explicit yes in the owner's own words.
- Never invent numbers, prices, dates or facts; write Unknown.
- No secrets, tokens, passwords or personal data in the file.

## At session end

After every session that changed anything (code, docs, a decision, a pull request). A read-only
session with nothing to hand over needs no row. A session cut short (usage limit, error, the user
stops it) still gets a row with Status In progress and the exact next step, if you can still write.

### 1. One Work log row (`handoff.py log`)

| Field | What to write |
|---|---|
| Entry | A short name for the work: "Billing retries", not "Session 3" |
| Date | Now, with the time and zone (the script writes it) |
| Agent | The tool or person: Claude, Cursor, Codex, Trae, Manual |
| Area | From `areas`: Dev, Docs, Research, Ops, Launch, Other |
| What changed | One to three plain sentences: what is different now, not what you tried |
| Links | Every file, branch or pull request touched, with its commit SHA for code |
| Next step | The single next action, specific enough to start without reading the chat |
| Status | From `statuses`: Done, In progress, Blocked, Waiting on owner |

One row per session; a long session with two separate pieces of work may add two. Never edit or
delete another session's row.

### 2. Now, Next up, Waiting and Blocked

Read the file again first (another agent may have changed it). Then edit only the lines you have a
reason to touch:

- **Now** (Item, Owner, Status, Link): add work you leave in progress; remove a row when its work is
  done. When empty, keep the single row `Nothing in progress right now | - | - | -`.
- **Next up** (numbered): remove what is done, add what this session uncovered; your log row's Next
  step appears here.
- **Waiting on the owner:** each item a question or a yes only they can give, with the options.
  Remove one only when they answered in their own words, and record the answer in your log row.
- **Blocked:** what cannot move and why; remove it when unblocked.
- History belongs in the Work log, never in these sections.
- Change only items your session touched or finished.

### 3. Page map

If you created or moved a key document, add a row (Page, What it holds). Never delete or rename
another session's entry.

### 4. Tell the user

One line: the log row's Entry and Status, and the Next step.

## Using it in other tools

The skill sits in the repository, so every agent that opens it sees it: Claude Code loads it from
`.claude/skills` (or `/handoff`), Cursor and Codex from `.agents/skills` and `AGENTS.md`, Trae from
`.trae/skills`. Without the repository (a chat app), paste this file into the project's
instructions and give the agent the handoff file's contents.
