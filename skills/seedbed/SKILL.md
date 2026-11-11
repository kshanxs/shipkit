---
name: seedbed
description: "The seed-data protocol: every new or changed feature ships seed data that a fresh database, a demo and the tests all show; the seed is idempotent, dated relative to today and uses made-up people; a scenario config (seedbed.toml) names the modules and scenarios a seed run may ask for, the personas, the client-side stores and the data map, and check_seeds.py holds the code to it. Use when adding or changing a feature, model, schema, route shape, permission or persona; when touching seed scripts, fixtures or mocks; when a demo shows empty or broken data; and when the user says 'seed', 'demo data', 'fixtures', 'mock data' or 'personas'."
---

# Seedbed

A feature is not finished when its screen works against a developer's own database. It is
finished when a fresh database, the demo and the data map all show it. This skill keeps that
true. It adds to the docsync contract; it does not replace it.

`$SK` below is the skills folder this skill is installed in (`.claude/skills`, `.agents/skills`
or `.trae/skills`).

## The scenario config

`seedbed.toml` at the project root (or the path in `[seedbed] config` of `shipkit.toml`) says what
the seed can make. Start from the generic SaaS example:

```bash
python3 $SK/seedbed/scripts/check_seeds.py --init     # copies references/seedbed.example.toml
```

| Table | Says |
|---|---|
| `[catalogue]` | The modules a seed run may ask for, and the scenarios staged on top (each with the module it needs) |
| `[seed]` | The seed files, and the patterns that show which module or scenario the code fills (`wants("tasks")`, `def scenario_trial_ending(`) |
| `[personas]` | The people a demo or a test signs in as, the login pattern (`@demo.test`), the ones that must exist |
| `[map]` | The data map document, and the client-side stores whose tables it must name (Dexie on the web, SQLite on the phone) |
| `[roles]` | One page per role, each with a data-access section |
| `[changed]` | The files whose change usually means the seed must change (schemas, models) |
| `[[tests]]` | The commands that hold the seed together |

[references/example_seed.py](references/example_seed.py) is a runnable seed for the example
(SQLite, standard library): copy the pattern into your ORM.

## For every feature that is added or changes shape, in the same piece of work

### 1. The seed (always)

- Realistic rows for the feature: enough to fill its list, the opposite of its empty state, and
  each status the screen distinguishes (a draft and a published post; a paid, an open and an
  overdue invoice).
- **Idempotent.** Look each row up by a natural key before making it. Never rely on a clean
  database. A second run adds nothing.
- Dates relative to today, so the demo always looks current.
- Data with rules behind it (anything a service validates) is made by calling the service or the
  API as a persona, so it is what the app itself would produce.
- People are made up, on the reserved `.test` domain. Never copy a real person.
- If logins changed, regenerate any generated credentials document; never edit it by hand.

### 2. The catalogue

| The change | What to do |
|---|---|
| A new screen over data the seed already makes | Nothing |
| New rows for an existing module | Seed them inside that module's part of the seed |
| A new area that is a module of its own | Add it to `[catalogue] modules` and seed it under its marker |
| A situation worth staging for a demo or a test | A scenario function, and its name in `[catalogue.scenarios]` with the module it needs |

The tenant itself (its people, its settings) is always seeded, so every persona can sign in and
every picker has something in it.

### 3. Mocks (when the front end has a mock layer)

The mock answers in the same shape as the contract (generated types), with a test that checks every
mock answer against it. A new mock collection is also named in the data map.

## Schema parity

The API's schemas are the contract; the web types and the device schema follow them.

| Rule | API | Web | Mobile (device database) |
|---|---|---|---|
| Field names | `snake_case` | The same, never renamed | Column the same; TypeScript key its camelCase form |
| Nullability | `X \| None` | `X \| null` | Nullable column |
| Enums | The enum's strings | A union of exactly those strings, declared once | The same union |
| Dates | `YYYY-MM-DD`, ISO 8601 | Strings as sent | Text, or integer `timestamp_ms` |
| Money | Decimal | Decimal strings | Text |

## The data map

One home per entity ([references/entity_entry_template.md](references/entity_entry_template.md)):
its storage (the table; whether a client keeps a copy), who may create, read, update and delete it
(read from the code and the policy table, never from memory), its routes with the status codes the
router really answers, and whether it is available offline.

## Validate

```bash
python3 $SK/seedbed/scripts/check_seeds.py              # static: catalogue, personas, map, roles. Exit 1 on error
python3 $SK/seedbed/scripts/check_seeds.py --run        # and the [[tests]] commands
python3 $SK/seedbed/scripts/check_seeds.py --changed    # and warn when a schema changed without its seed
```

Then, against real services, on a **scratch** database: seed from empty, seed again (nothing may be
added), seed each module and scenario you touched alone, and open the feature's screen as each
persona that may use it.

**Never run a seed's flush, clean or reset against a developer's own database without asking.**
It deletes data the seed does not recreate. Check where a seed is pointed before running it.

## Done when

- [ ] The seed makes the feature's data, and a second run changes nothing
- [ ] A new module or scenario is in the catalogue, and `check_seeds.py` prints `0 errors`
- [ ] The feature's screen shows the data for each persona allowed to see it
- [ ] Field names, nullability and enums are the same in the API, the web types and the device schema
- [ ] The entity's entry in the data map and each role page are current
- [ ] The docsync contract is met
