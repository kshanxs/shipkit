# Template: a new feature specification

Copy the block below to `docs/features/<feature>.md` (lowercase
`snake_case`). Fill what is known today and leave out a section that does not
apply. A short honest page on day one is better than none: the page grows
with the code.

```markdown
# <Feature Name>

> **Status (YYYY-MM-DD): In progress.** Tier: to be decided. Every row is in the [tracker](../feature_status.md).

One or two sentences: what it does and who uses it.

Code: `apps/api/app/<module>/`, `apps/web/src/features/<feature>/`.
Tests: `apps/api/tests/test_<module>.py`. Migration: `NNN_<name>`.

## 1. What it does

The behaviour as the code has it today: the rules, states and workflows.
Mark anything not built yet as planned, with the date.

## 2. Who can do what

Roles and permissions, as the code enforces them.

## 3. Data

This feature's tables and the columns that matter. Link to the schema
document for shared tables.

## 4. API

The routes, by purpose, with the status codes the router really answers.

## 5. Sub-features

| Sub-feature | Status | Since | Notes |
|-------------|--------|-------|-------|
| <name> | Built | YYYY-MM-DD | |
| <name> | Planned | | |

## 6. Policies and other documents this touches

Result of the policy check: which policy sections were checked, what
changed, what waits for the owner.

## 7. Open questions

One line each, linked to the open questions register (open-loops skill).

## 8. Related

Links to related features and role pages.
```

Status words for the first line: Built, Partly built, Backend only, Frontend
only, In progress, Next, Planned, Coming soon. "Tier: to be decided" stays
until the owner assigns a tier; the feature sits in the feature map's queue
(`docs/feature_catalog.md`, "Plan to be decided") until then.

## Adding to an existing spec instead

When the change is a sub-feature of something already documented, do not
create a new file. Add a section to the existing spec with its own dated
status line:

```markdown
## <Sub-feature>

> **Status (YYYY-MM-DD): Backend only.** <what works>. Tier: to be decided ([queue](../feature_catalog.md#plan-to-be-decided)).
```
