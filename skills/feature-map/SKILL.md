---
name: feature-map
description: "Keeps the feature map (docs/feature_catalog.md): the one file listing every feature, the sub-features under it, its tier (Free, Pro, Enterprise or your own) and what is built, with counts by what is left; holds the pricing page's comparison table to it and generates a public catalog (TypeScript or JSON) for the roadmap and pricing pages. Use whenever a feature or sub-feature is added, finished, split, renamed, removed, moved between tiers or given one; after a change that alters what a feature does or how far it is built; and when the user asks 'what is built', 'what is left', 'how much is done', 'which tier is X in', 'list the features', 'update the roadmap' or 'update the pricing page'."
---

# Feature map

`docs/feature_catalog.md` answers three questions for every feature: **which tier is it in, what is
under it, and is it built?** The pricing page and the roadmap are copies of it for customers; this
skill keeps the three the same.

**Tiers and pricing apply only to priced plans.** When the project profile has no priced plans
(`project.py has plans` says no, or `[project] plans = "none"`), the map is grouped by area alone:
`tiers = []`, no "which tier", no pricing page, no comparison table; the sections below about tiers
and pricing do not apply. The map still answers what is under each feature and what is built. It works beside docsync (changelogs, specs, the tracker): on a code
change use docsync first, then this. `$SK` is the skills folder this skill is installed in.

Configured by `[feature_map]` in `shipkit.toml`: `catalog`, `tiers` (cheapest first; default
`["Free", "Pro", "Enterprise"]`, or none when `[project] plans = "none"`), `specs_dir`, and optionally `comparison` (the file holding the
pricing page's `export const COMPARISON = [...]`) and `catalog_out` (the generated catalog, `.ts` or
`.json`).

## What owns what

| Question | Owner |
|---|---|
| Which tier is a feature in; its sub-features; is each built? | The feature map |
| Price, seats, discounts, what each tier is for | The pricing document |
| Engineering status by module, and the code map | The tracker (docsync) |
| What customers are told | The pricing page, written by hand to follow the map, and the generated catalog |

The map's status is per thing a customer would name; the tracker's is per module. When they
disagree, read the code, then correct both.

## The workflow

### 1. Find the feature

```bash
F="python3 $SK/feature-map/scripts/feature_map.py"
$F --list                                   # everything
$F --list --plan Pro --status Planned
```

Names differ between a customer's list, the pricing page and the code. Match by what the feature
does, and keep the map's name.

### 2. Check the code, not the documents

A status is a claim about the code. Look for the route and the screen before writing one. A model
with no route, or a route no screen calls, is not Built.

### 3. Edit the map

Everything between `<!-- tree:start -->` and `<!-- tree:end -->` follows one grammar:

```markdown
## Pro: collaborate and automate
### Workflow
- **Usage alerts by email and chat** · Partly · [Notifications](features/notifications.md)
  - Email when a quota is near · Built
  - Chat integration · Planned
```

- A feature is `- **Name** · Status`, then optionally ` · ` and links or a note. A sub-feature is
  indented two spaces and not bold.
- Statuses: Built, Partly, Backend only, Frontend only, In progress, Next, Planned, Coming soon.
- Break a feature into sub-features when part of it works and part does not; that is what makes
  "Partly" readable. A feature's status follows from its sub-features: all Built is Built, none
  started is Planned (or Next, or Coming soon), anything else is Partly.
- Every sub-feature has a row in its spec's "Sub-features in the code" table (what it does, its
  routes, its screen), written from the code.
- One name, one place. A capability that spans two tiers is two features with two names.
- A move between tiers, a new feature or a removal gets a line in "Changes to this map".

Start a map from [references/feature_catalog.example.md](references/feature_catalog.example.md).

### 4. Place a new feature

If a sorting rule the owner agreed to gives a clear tier, put it there. Otherwise, the default for
anything new: under `## Plan to be decided`, with the date and a note for the decision. The tier is
the owner's to choose, and so is a price; never write one that is not in the pricing document. A
feature that costs money each time it is used (a message, a model call) needs an allowance or an
add-on: record it as an open question (open-loops skill).

### 5. Bring the website into line

If `comparison` is configured, the script holds the pricing page's comparison table to the map:
each row's label is the map's name for a feature or sub-feature, `'no'` before its tier and
included from it on, `COMING_SOON` (never `'yes'`) for anything not built, and never `COMING_SOON`
for something built. Plan cards are written by hand from the same facts: built groups first, what
is not built in a group marked as coming soon.

If `catalog_out` is configured, `--write` generates it from the tiers (names, areas, sub-features,
statuses; no notes, links or untiered features). Never edit it by hand. Customers are never shown a
feature as present when it is not; "Coming soon" is a promise, so only for a feature the owner has
put in a tier.

### 6. Check

```bash
$F --write                                         # refresh the counts table and the catalog, then check
python3 $SK/docsync/scripts/check_docs.py --changed
```

| Check | Fails when |
|---|---|
| `format`, `status` | A line is not a heading, feature or sub-feature; a status is not one of the words |
| `rollup` | A feature's status does not follow from its sub-features |
| `names` | Two features share a name |
| `specs` | A spec under `specs_dir` is not linked from the map |
| `counts` | The counts table is stale |
| `site` | A comparison row is not in the map, is in the wrong tier, offers what is not built, or hides what is |
| `catalog` | The generated catalog is not what the map holds |

### 7. Report

What moved in the map, the new counts, what changed on the website, and which decisions wait for the
owner.

## When the user pastes a feature list

1. Map each row to a feature by what it does; note rows that are one feature split several ways,
   and rows the map does not have.
2. Check each against the code, then answer built, needs work, not started, by tier.
3. Rows the map lacks go to "Plan to be decided" only if the user wants them tracked.
