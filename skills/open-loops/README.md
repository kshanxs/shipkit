# open-loops

**Group:** Docs & Flow · **Commands:** `/loops`, `/oq`

Keeps the open questions register: each question waiting for an answer with what the code does today, what each answer would change, and anchors into the code that are checked (and moved) when the code moves; writes each question into the documents it touches; reminds the agent when a change touches one.

## When to use it

Something left undecided, an answer from the owner, "what do you need from me?".

## Example

In Claude Code:

```
/loops what is still open about billing?
```

In Cursor, Codex or Trae, name it in the message: `@loops what is still open about billing?`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/open-loops/scripts/open_loops.py --for apps/api/app/billing
python3 .claude/skills/open-loops/scripts/open_loops.py --write
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
