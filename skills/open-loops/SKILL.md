---
name: open-loops
description: "Keeps the open questions register (docs/open_questions.md): every question waiting for the owner, a lawyer, an accountant or a fact, with what the code does today, what each answer would change, anchors into the code it rests on (checked when the code moves), and a list of its open questions written into every document it touches. Use at the start of any change (which questions does it touch?) and at the end (update them); whenever a brief, spec or build leaves something undecided; when the user answers, changes or drops a question, says 'open questions', 'what is pending', 'what do you need from me', 'what is undecided', or answers one by number (Q-012); and when the stop hook says a change touches an open question."
---

# Open loops

`docs/open_questions.md` (or `[open_loops] register` in `shipkit.toml`) is the one place that
answers **what is waiting for an answer, what happens until it comes, and what would change when it
does.** Every document a question touches carries a short list of its open questions, written from
the register by the script. Works beside docsync and feature-map (a question about a tier is still
asked here). `$SK` is the skills folder this skill is installed in.

## An entry

```markdown
### Q-012

**Who pays the card fee on a refund?**
Decision · Open · raised 2026-10-06 · checked 2026-10-16 · needed with Q-003

- **Context:** why the question exists: what raised it, and why it could not be settled there.
- **Today:** what the code does now, checked against the code.
- **If the customer:** what this answer changes: screens, rules, policies, documents.
- **If we do:** the same for the other answer.
- **Recommended:** the answer advised, with its reason, if there is one.
- **Where:** [Billing §3](features/billing.md#3-refunds) · [Terms](features/legal.md)
- **Code:** `apps/api/app/billing/`
- **Lines:**
  - `apps/api/app/billing/refunds.py:77` `amount = sum(`: the amount refunded is the charge
```

- **Kind.** Decision (the owner chooses), Confirmation (built one way where a brief was silent;
  waits for a yes or a change), Advice (a lawyer or an accountant), Fact (to look up or supply).
  Change the words in `[open_loops] kinds`.
- **Context** is for whoever comes back months later: what raised it, what the build had to choose,
  why the answer is not the builder's. Two or three sentences.
- **Today** says what the code does, not what a document claims.
- **Implications** are the point: one `If ...` line per real answer, or an `Until answered` line.
- **Where** links only documents whose words would change; each gets the question in its list.
- **Code** names the folders the answer would land in; a change there makes the stop hook ask you
  to look again.
- **Lines** are anchors, `` `path:line` `text` ``: the script moves a line number when the code
  moves, and fails when the text is gone (the code the question rests on changed).
- **checked** is the day Context, Today and Lines were last read against the code.
- A number is never reused; an entry is never deleted.

Start a register from [references/open_questions.example.md](references/open_questions.example.md).

## The workflow

```bash
O="python3 $SK/open-loops/scripts/open_loops.py"
$O --for apps/api/app/billing docs/features/billing.md   # 1. at the start: the questions this change touches
$O --show Q-012                                          #    one question, with the code under each anchor today
$O --list --status Open                                  #    what is open
$O --changed                                             # 4. what this change set touches, when the register did not change
$O --write                                               # 5. refresh the counts and every document's list, move anchors
```

1. **At the start**, see which questions the change touches. Do not build over an open question:
   build to `Today`, or ask the user if the change needs the answer.
2. **When something is left undecided**, add it under its area with the next free number, `Open`,
   today's date, its Context and its Lines (and `checked`). Tell the user in your reply: a question
   only in a reply or a commit message is lost.
3. **When the user answers**: `Answered YYYY-MM-DD` (or `Dropped`), an `- **Answer:**` line in their
   words or a faithful summary, the entry moved under `## Answered`. Then do what the answer says:
   the code, then the documents in its Where. A tier answer goes into the feature map; a policy
   answer through the policy check. Add a line to "Changes to this register".
4. **When a change touches a question without answering it**, update its Today line, its
   implications, its Lines and its `checked` date.
5. **Write the lists and check**: `--write`, then `check_docs.py --changed`. A document with no list
   gets one at its end under `## Open questions`; to place it inside a section instead, move the
   markers there and write the start marker `<!-- open-questions:start bare -->`. Never edit inside
   the markers.

| Check | Fails when |
|---|---|
| `format`, `ids`, `words` | A line is not an area, a question or a field; a number is not `Q-NNN` or is used twice; a kind or status is not a register word |
| `place` | An answered question is above `## Answered`, or an open one under it |
| `fields` | An open question lacks Context, Today, an implication or Where, or names Code without Lines; an answered one lacks Answer |
| `where`, `code` | A linked document or a named path does not exist |
| `lines` | An anchor names no file, or its text is not on its line (`--write` moves it when the text moved; gone means read it again) |
| `refs` | A document names a question number the register lacks |
| `lists`, `counts` | A document's list or the counts table is stale |

The script cannot tell whether a Today line is true or an implication complete; that is yours. What
it can tell is that the code an anchor points at is still there, so anchor the lines that carry the
rule.

## Report

Say which questions were added, answered or changed, by number and title, and list new ones the
user must answer. When the user asks what is open, answer from `--list --status Open`, grouped by
area, the blocking ones first.
