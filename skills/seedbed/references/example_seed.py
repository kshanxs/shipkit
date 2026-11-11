#!/usr/bin/env python3
"""An example seed for the generic SaaS app in seedbed.example.toml. Standard library only.

It shows the rules the seedbed skill asks of any seed, in about a hundred lines:

  * idempotent: every row is looked up by a natural key before it is made, so a second run adds nothing;
  * relative dates: due dates and trial ends are counted from today, so the demo always looks current;
  * made-up people on the reserved `.test` domain;
  * modules a run may ask for (`wants("tasks")`), and scenarios staged on top (`scenario_<name>`).

    python3 example_seed.py --db /tmp/demo.sqlite                 # every module
    python3 example_seed.py --db /tmp/demo.sqlite --modules projects,tasks --scenarios busy_monday
    python3 example_seed.py --check                               # seed twice in memory; exit 1 if the second run added rows

Copy it into your project as a starting point (scripts/seed.py in the example config) and replace
the tables with yours, or use it only as the pattern for a seed in your own ORM.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, timedelta

MODULES = ("projects", "tasks", "comments", "billing")
PERSONAS = (("owner", "Olive Owner"), ("admin", "Adam Admin"), ("member", "Mona Member"), ("viewer", "Vic Viewer"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, plan TEXT NOT NULL, trial_ends TEXT);
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members (workspace_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL, PRIMARY KEY (workspace_id, user_id));
CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, key TEXT NOT NULL, name TEXT NOT NULL, UNIQUE (workspace_id, key));
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, ref TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, due TEXT, assignee_id INTEGER, UNIQUE (project_id, ref));
CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, author_id INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE (task_id, author_id, body));
CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, number TEXT UNIQUE NOT NULL, amount_cents INTEGER NOT NULL, status TEXT NOT NULL);
"""


def upsert(db: sqlite3.Connection, table: str, key: dict, values: dict | None = None) -> int:
    """The row's id, looked up by its natural key and made only when it is not there."""
    where = " AND ".join(f"{k} = ?" for k in key)
    row = db.execute(f"SELECT rowid FROM {table} WHERE {where}", tuple(key.values())).fetchone()
    if row:
        return row[0]
    data = {**key, **(values or {})}
    cursor = db.execute(f"INSERT INTO {table} ({', '.join(data)}) VALUES ({', '.join('?' for _ in data)})", tuple(data.values()))
    return cursor.lastrowid


def seed(db: sqlite3.Connection, modules: set[str], scenarios: list[str], today: date | None = None) -> None:
    today = today or date.today()

    def wants(module: str) -> bool:
        return module in modules

    db.executescript(SCHEMA)
    # The workspace and its people are always seeded, so every persona can sign in.
    ws = upsert(db, "workspaces", {"slug": "acme"}, {"name": "Acme Demo", "plan": "pro", "trial_ends": None})
    people = {}
    for role, name in PERSONAS:
        people[role] = upsert(db, "users", {"email": f"{role}@demo.test"}, {"name": name})
        upsert(db, "members", {"workspace_id": ws, "user_id": people[role]}, {"role": role})
    project = None
    if wants("projects"):
        project = upsert(db, "projects", {"workspace_id": ws, "key": "WEB"}, {"name": "Website relaunch"})
        upsert(db, "projects", {"workspace_id": ws, "key": "OPS"}, {"name": "Operations"})
    if wants("tasks") and project:
        # One task in each status the board distinguishes, dated from today.
        for ref, title, status, days in (("WEB-1", "Draft the brief", "done", -5), ("WEB-2", "Design review", "in_progress", 1), ("WEB-3", "Launch checklist", "todo", 7)):
            upsert(db, "tasks", {"project_id": project, "ref": ref}, {"title": title, "status": status, "due": (today + timedelta(days=days)).isoformat(), "assignee_id": people["member"]})
    if wants("comments") and project:
        task = db.execute("SELECT id FROM tasks WHERE ref = 'WEB-2'").fetchone()
        if task:
            upsert(db, "comments", {"task_id": task[0], "author_id": people["admin"], "body": "Looks good; two small fixes."})
    if wants("billing"):
        upsert(db, "invoices", {"number": "INV-0001"}, {"workspace_id": ws, "amount_cents": 4900, "status": "paid"})
        upsert(db, "invoices", {"number": "INV-0002"}, {"workspace_id": ws, "amount_cents": 4900, "status": "open"})
    for name in scenarios:
        print(RUNNERS[name](db, ws, people, today))
    db.commit()


def scenario_trial_ending(db: sqlite3.Connection, ws: int, people: dict, today: date) -> str:
    db.execute("UPDATE workspaces SET plan = 'trial', trial_ends = ? WHERE id = ?", ((today + timedelta(days=2)).isoformat(), ws))
    return "trial_ending: the workspace's trial ends in two days"


def scenario_busy_monday(db: sqlite3.Connection, ws: int, people: dict, today: date) -> str:
    project = upsert(db, "projects", {"workspace_id": ws, "key": "WEB"}, {"name": "Website relaunch"})
    for n in range(1, 6):
        upsert(db, "tasks", {"project_id": project, "ref": f"WEB-B{n}"}, {"title": f"Overdue item {n}", "status": "todo", "due": (today - timedelta(days=n)).isoformat(), "assignee_id": people["member"]})
    return "busy_monday: five overdue tasks for the member"


def scenario_fresh_signup(db: sqlite3.Connection, ws: int, people: dict, today: date) -> str:
    upsert(db, "workspaces", {"slug": "fresh"}, {"name": "Fresh Signup", "plan": "free", "trial_ends": None})
    return "fresh_signup: an empty second workspace"


RUNNERS = {"trial_ending": scenario_trial_ending, "busy_monday": scenario_busy_monday, "fresh_signup": scenario_fresh_signup}


def counts(db: sqlite3.Connection) -> dict[str, int]:
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the example SaaS database.")
    parser.add_argument("--db", default=":memory:")
    parser.add_argument("--modules", default=",".join(MODULES))
    parser.add_argument("--scenarios", default="")
    parser.add_argument("--check", action="store_true", help="seed twice; exit 1 if the second run added rows")
    args = parser.parse_args(argv)
    modules = {m for m in args.modules.split(",") if m}
    unknown = modules - set(MODULES) | {s for s in args.scenarios.split(",") if s} - set(RUNNERS)
    if unknown:
        print(f"unknown module or scenario: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    scenarios = [s for s in args.scenarios.split(",") if s]
    db = sqlite3.connect(args.db)
    seed(db, modules, scenarios)
    first = counts(db)
    if args.check:
        seed(db, modules, scenarios)
        second = counts(db)
        grew = {t: (first[t], second[t]) for t in first if second[t] != first[t]}
        print(f"first run: {sum(first.values())} rows; second run added {sum(second.values()) - sum(first.values())}")
        return 1 if grew else 0
    print(", ".join(f"{t} {n}" for t, n in first.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
