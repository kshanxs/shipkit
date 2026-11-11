# Entity entry template

Reference for the seedbed skill. Copy the blocks below into the data map (`[map] file` in
seedbed.toml, for example `docs/data_map.md`) for a new entity: one row in the storage table, and
one subsection for the entity. Replace every `<...>`; delete nothing. Write "-" for "none", and say
why when it is not obvious.

Read each fact from the code on the day you write it: the table from the models, the fields from
the schemas, the routes and status codes from the router, the permissions from the policy table.

## Row for the storage table

```markdown
| <Entity> | `<database_table>` | `<web_store_table>` (kept on the web device) or -; say if a change may wait offline | `<device_table>` (mobile) or - |
```

## Subsection for the entity

```markdown
### <Entity>

| | Owner | Admin | Member | Viewer | Guest | Platform operator |
|---|---|---|---|---|---|---|
| Create | <All / Own projects / -> | | | - | - | - |
| Read | | | | <Own workspace> | <Invited project> | <Audited support access / -> |
| Update | | | | - | - | - |
| Delete | | | | - | - | - |

<One line for any rule the table cannot say: "A paid invoice is never deleted".>

| Route | Query or body | Answers |
|-------|---------------|---------|
| `<METHOD> /api/v1/<path>` | <query parameters or body fields> | `<2xx>` <what comes back>; `<4xx>` <when> |

<Enum fields and their values: "`status` is one of `draft`, `open`, `paid`, `void`.">

**Offline and demo.** Web device: <kept, under which store, or not kept; which change may wait and
what happens if it is refused on arrival>. Demo: <as in any workspace, or what the seed leaves
out>. Mobile: <pulled for which role; whether the device may write it; or "Not kept">.
```

## Row for a role page (`docs/roles/<role>.md`, "Data and API Access")

```markdown
| [<Entity>](data_map.md#entity) | <What this role may do through the API> | <Pulled / pushed / "Not kept"> |
```

Add the row to every role that has any access. A role with none gets no row; the map's permission
table already shows "-".
