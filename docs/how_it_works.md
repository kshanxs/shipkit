# How the skills work

Each skill is a folder with a `SKILL.md` (the instructions the agent follows), a short `README.md`,
and, where it helps, standard-library Python scripts, references and tests.

- **The agent reads `SKILL.md`.** Claude Code loads skills from `.claude/skills/` (by description or
  by slash command); Cursor and Codex read `.agents/skills/` through `AGENTS.md`; Trae reads
  `.trae/skills/`. The instructions are written to be followed literally: what to read first, what
  to change, what to run, and when it is done.
- **Scripts do the mechanical parts.** Plain Python 3.11+ with no dependencies, so they run with
  `python3` or `uv run python` in any project. Each reads its paths from `shipkit.toml` and skips
  checks whose files do not exist.
- **Skills hand work to each other.** stack-backend ends in docsync; harden's attack log lives in
  docsync and its matrix feeds bug-sweep, load-sim and triage-report; fanout reserves numbers from
  open-loops and docsync and lands through docsync's checks.
- **The switchboard routes.** `@docs` or `/docs` names a skill; otherwise trigger phrases and file
  paths in `skills/switchboard/skills.toml` pick up to four, and the hook suggests them on each
  message.

## The three groups

```mermaid
flowchart LR
    subgraph build["Build"]
        direction TB
        be["stack-backend"]
        web["stack-web"]
        rn["stack-native"]
        cli["stack-cli"]
        wire["wire-api"]
        seed["seedbed"]
        fan["fanout"]
    end
    subgraph test["Break and Test"]
        direction TB
        harden["harden"]
        sweep["bug-sweep"]
        load["load-sim"]
        perf["perf-watch"]
        triage["triage-report"]
        ship["ship-check"]
    end
    subgraph flow["Docs and Flow"]
        direction TB
        docs["docsync"]
        fmap["feature-map"]
        loops["open-loops"]
        hand["handoff"]
        sb["switchboard"]
        prof["profile"]
        feedback["shipkit-feedback"]
    end
    build --> test --> flow
    flow -. "next session" .-> build
```

## A feature, end to end

```mermaid
flowchart TB
    subgraph plan["1. Start and build"]
        direction LR
        start(["a feature"]) --> handoffr["handoff<br/>read where we left off"]
        handoffr --> loops1["open-loops<br/>which questions it touches"]
        loops1 --> buildc{"one agent<br/>or several?"}
        buildc -- one --> stack["stack-backend<br/>stack-web, stack-native<br/>stack-cli"]
        buildc -- several --> fanout["fanout<br/>worktrees, owned paths"]
        fanout --> stack
    end
    subgraph prove["2. Prove and record"]
        direction LR
        wire["wire-api<br/>screen to endpoint"] --> seed["seedbed<br/>demo and test data"]
        seed --> harden["harden<br/>test first, then break it"]
        harden --> docs["docsync<br/>changelog, spec, tracker"]
        docs --> fmap["feature-map<br/>what is built"]
        fmap --> handoffw(["handoff<br/>log the session"])
    end
    plan --> prove
```

## How the skills hand off

```mermaid
flowchart LR
    be["stack-backend"] --> docs["docsync"]
    web["stack-web"] --> docs
    rn["stack-native"] --> docs
    cli["stack-cli"] --> docs
    wire["wire-api"] -- "tracker status" --> docs
    harden["harden"] -- "attack log" --> docs
    harden -- "test matrix" --> sweep["bug-sweep"]
    harden -- "test matrix" --> load["load-sim"]
    harden -- "matrix coverage" --> triage["triage-report"]
    load --> perf["perf-watch"]
    perf -- "stats.md" --> triage
    sweep --> triage
    fan["fanout"] -- "reserves numbers" --> loops["open-loops"]
    fan -- "reserves numbers,<br/>lands with its checks" --> docs
    docs <--> fmap["feature-map"]
    ship["ship-check"] -. "reads" .-> docs
```

## How the switchboard routes a message

```mermaid
sequenceDiagram
    autonumber
    actor You
    participant Hook as switchboard hook<br/>(UserPromptSubmit)
    participant Route as route.py + skills.toml
    participant Agent
    You->>Hook: "/harden the checkout endpoint against double submit"
    Hook->>Route: names, slash commands, trigger phrases, file paths
    Route-->>Hook: up to four skills: harden, stack-backend, docsync
    Hook-->>Agent: suggested skills for this message
    Agent->>Agent: load each SKILL.md and follow it literally
    Agent-->>You: change, tests, docs updated
```
