# shipkit-feedback

**Group:** Docs & Flow · **Commands:** `/skillfix`

Turns a lesson from real project work into a shipkit pull request or issue, on the repository you run (a fork works too). The lesson is written in generic terms and stays out of the project's commits.

## When to use it

When a skill was wrong, missing or outdated, or you worked out something a skill should teach.

## Automatic learnings

An agent can save a lesson as a local draft at the end of a session. Drafts are checked for secrets, personal details and project names, and nothing is posted until you opt in:

```bash
python3 <skills>/shipkit-feedback/scripts/feedback.py consent on    # file drafts for this user
python3 <skills>/shipkit-feedback/scripts/feedback.py consent off   # keep them local
python3 <skills>/shipkit-feedback/scripts/feedback.py list          # see what is waiting
```

Filed reports are limited to three a day, skip duplicates, and arrive labelled `needs-review` for the maintainer. A project's `shipkit.toml` cannot turn filing on or change where reports go. Forks can use `consent on --repo OWNER/NAME`.

## Example

In Claude Code:

```
/skillfix the backend skill missed JSON null in nullable columns
```

In Cursor, Codex or Trae, name it in the message: `@skillfix the backend skill missed JSON null in nullable columns`.
