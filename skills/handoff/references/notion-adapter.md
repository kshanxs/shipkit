# The handoff in Notion (an optional adapter)

The handoff skill writes `HANDOFF.md` by default. A team that already lives in Notion can keep the
same handoff there instead, through a Notion MCP server or connector. The steps of the skill do not
change; only where each part is written does.

## Set up once

1. A page, for example "Agent Handoff", with these sections as headings: Now (a table: Item, Owner,
   Status, Link), Next up (a numbered list), Waiting on <owner>, Blocked, Rules, Page map (a table:
   Page, What it holds).
2. An inline database on that page, "Work log", with these properties:

| Property | Type | Holds |
|---|---|---|
| Entry | title | A short name for the work |
| Date | date (with time) | When, in the team's time zone |
| Agent | select | Claude, Cursor, Codex, Trae, Manual (add options on purpose, not from a session) |
| Area | multi-select | Dev, Docs, Research, Ops, Launch, Other |
| What changed | text | One to three sentences |
| Links | text | Files, branches, pull requests, with commit SHAs |
| Next step | text | The single next action |
| Status | select | Done, In progress, Blocked, Waiting on owner |

3. Record where they are in the project, not in the skill: `shipkit.toml`

```toml
[handoff]
adapter = "notion"
notion_page = "<the Agent Handoff page's URL or id>"
notion_work_log = "<the Work log database's id or data source>"
```

Keep the ids in that config file (the repository may be public: ids are not secrets, but they are
not anyone else's business either; put them in a gitignored `shipkit.local.toml` if you prefer).

## How the steps map

| Skill step | In Notion |
|---|---|
| Read the file | Fetch the handoff page; query the Work log for the newest 5 to 10 rows by Date |
| `handoff.py log` | Create one row in the Work log with the fields above |
| Update Now, Next up, Waiting, Blocked | Fetch the page again, then make small targeted edits to those blocks; never rewrite the page |
| Cannot be reached | Same rule as the file: say "Handoff not read: <reason>", carry on, never invent, print the row at the end under "Handoff not written" |

Read the database's schema before the first write of a session, and follow what it says now if a
write is refused (properties get renamed). The file and Notion should not both be live: pick one
per project, and say which in the project's `AGENTS.md`.
