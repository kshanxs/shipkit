# Seeding hundreds of tenants cheaply: clone one inside Postgres

Running the real seed 500 times takes hours. Running it once and copying the result inside the
database takes minutes. The technique, for a schema where every tenant-owned table carries a
tenant column (or hangs off one that does):

1. **Seed one template tenant fully**, through the real seed (every module, real rules).
2. **Find the tenant's tables** from the catalogue: every table with the tenant column, plus
   tables whose single-column foreign keys point into those (repeat until nothing is added). Leave
   out sign-in secrets, sessions, idempotency claims, queues and the platform's own tables.
3. **Order them parents first** (a depth-first walk of the foreign keys among the owned tables).
4. **Pick an id stride** larger than the biggest id in the database (the next power of ten), and
   refuse to go on if `stride x copies` passes the id column's range.
5. **Copy in batches**: for each owned table, one statement per batch of copies:

   ```sql
   INSERT INTO "tasks" ("id", "workspace_id", "project_id", "title", ...)
   SELECT src.id + k * :stride,
          :template + k * :stride,                                -- the tenant column
          CASE WHEN src.project_id IN (SELECT id FROM own_projects)
               THEN src.project_id + k * :stride ELSE src.project_id END,   -- a key into an owned table moves
          src.title, ...
   FROM "tasks" src CROSS JOIN generate_series(:first, :last) AS k
   WHERE src.id IN (SELECT id FROM own_tasks);
   ```

   where `own_<table>` is a temporary table of the template tenant's row ids.
6. **Make global unique text unique per copy** (emails, phone numbers, slugs, invoice numbers,
   codes): `left(col, 30) || '~' || k`, or a rule per column (`'u' || id || '@sim.test'`). Find
   them from the unique indexes none of whose columns moves with the copy.
7. **Clear values sealed under the template's keys** (encrypted columns, password hashes, second
   factor secrets): a copy cannot open them.
8. **Foreign-key cycles** (A points at B and B at A): insert the later key as NULL, then fill it
   with an `UPDATE ... FROM` once both tables are copied.
9. **Reset the sequences** (`setval(pg_get_serial_sequence(...), max(id))`) and `ANALYZE`.
10. **Keep the result as a template database** and create each run's database from it.

Guard it the same way as the driver: only a local database whose name says `sim` or `load`, only a
development setting. Give every member of the template an account first if the
seed only made a few: a real tenant has them all.

This is a pattern, not a script: the column rules (which columns are unique text, which are sealed)
are your schema's. Write the cloner in your stack, test it on three tenants, and keep it beside the
seed.
