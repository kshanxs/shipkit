# load-sim

**Group:** Break & Test · **Commands:** `/load`, `/sim`

Simulates many tenants' real usage from a scenario config (`load-scenario.toml`): open-model Poisson traffic, profiles, idempotent changes sent twice, cross-tenant probes that must all be refused, thresholds that pass or fail the run, and a demand estimate. Standard-library driver plus a stub server that proves the harness before you aim it at your app.

## When to use it

Load or stress tests, "simulate 500 workspaces", finding where the API breaks.

## Example

In Claude Code:

```
/load run the peak profile at 50 requests a second against the local stack
```

In Cursor, Codex or Trae, name it in the message: `@load run the peak profile at 50 requests a second against the local stack`.

The scripts directly (paths shown for a `.claude/skills` install; use `.agents/skills` or `.trae/skills` for the others):

```bash
python3 .claude/skills/load-sim/scripts/sim.py init
python3 .claude/skills/load-sim/scripts/stub_server.py --port 8077 &
python3 .claude/skills/load-sim/scripts/sim.py run --profile peak --rps 20 --duration 10
```

The full instructions the agent follows are in [SKILL.md](SKILL.md).
