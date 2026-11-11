# Shapes: a feature spec, a role page, a schema block

Reference for the docsync skill. Which document links to which is not kept by hand; print it:

```bash
python3 <skills>/docsync/scripts/check_docs.py --map
```

If the project keeps a schema document (`docs/architecture/database.md`), give it one section per
area and list, at the top of each, the feature specs whose tables it holds. A change to a table goes
in the spec and in that section together.

## Shape of a feature spec

`docs/features/<feature>.md`, in this order. Leave out a section that does not apply rather than
writing "N/A".

1. Title, the dated status line, a one-line summary.
2. Overview: purpose and principles.
3. Behaviour: rules, states, workflows. Mark each part built or planned, with the date.
4. Role access and permissions.
5. Data: this feature's tables only, linking to the schema document.
6. API endpoints.
7. Sub-features in the code: a table of sub-feature, what it does, its routes and its screen
   (the feature-map skill reads it).
8. Related features.

Tier availability is one sentence with a link to the feature map, never a copied table.

## Shape of a role page

`docs/roles/<role>.md` has a "Data and API Access" section: the role's slice of the data map (see
the seedbed skill), one row per entity the role works with. The map is the home of each entity's
storage, routes and status codes; the role page links to it and does not copy them. It ends with a
Related Documentation table (features, other roles, pricing).

## Schema blocks

The same table is written the same way in the spec and in the schema document:

```sql
-- Brief comment
CREATE TABLE table_name (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id BIGINT NOT NULL REFERENCES workspaces(id),
  -- columns
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON table_name (workspace_id, column);
```

Every code fence is closed, and line breaks are real line breaks, never a typed `\n`.
