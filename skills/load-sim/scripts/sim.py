#!/usr/bin/env python3
"""
Simulate many tenants' real usage against a local or test server, driven by a scenario config.
Standard library only (Python 3.11+).

    python3 sim.py plan    --scenario load-scenario.toml --profile peak --count 10   # what would be sent; no network
    python3 sim.py run     --scenario load-scenario.toml --profile peak --rps 50 --duration 60
    python3 sim.py demand  --scenario load-scenario.toml --tenants 500               # the busiest hour, estimated
    python3 sim.py init                                                               # write load-scenario.toml (generic SaaS)

The scenario (references/scenario.example.toml, the generic SaaS example) names the target, how a
request is signed, the tenants, the people per tenant, every request kind, the profiles (relative
weights of request kinds) and the thresholds. Nothing about the product is in this script.

Why it is cheap:
  * An open model: requests arrive at a rate (Poisson, --rps), each picked as a person of a tenant
    doing a thing; thousands of people cost nothing until one acts.
  * One address per tenant (X-Forwarded-For), so a tenant behind one router trips the rate limit
    the way a real office does: if normal use trips it, that is a finding.
  * Tokens come from the environment or a file the user made locally; the script never signs in.

Safety: the target must be this machine unless --allow-host (or [target] allow_hosts) names a
test server. Never production. Results go to --out (default ./sim-out/<time>-<profile>/):
requests.csv, one row a request, and summary.md, per request kind slowest p95 first, with the
thresholds PASS or FAIL. Exit status 1 when a threshold fails.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import os
import random
import secrets
import shutil
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

SKILL = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


# ── scenario ─────────────────────────────────────────────────────────────────


@dataclass
class Kind:
    name: str
    method: str
    path: str
    role: str = ""
    body: object = None
    headers: dict = field(default_factory=dict)
    idempotent: bool = False
    replay: float = 0.0
    cross_tenant: str = ""  # "header": another tenant's header; "path": its ids in the path ({other_tenant})
    expect: str = "2xx"


@dataclass
class Scenario:
    path: Path
    data: dict
    kinds: dict[str, Kind]

    @property
    def target(self) -> dict:
        return self.data.get("target", {})

    @property
    def tenants(self) -> dict:
        return self.data.get("tenants", {})

    @property
    def profiles(self) -> dict[str, dict[str, float]]:
        return self.data.get("profiles", {})


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"No scenario at {path}. Start one: sim.py init (writes the generic SaaS example)")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    kinds: dict[str, Kind] = {}
    for item in data.get("requests", []):
        kind = Kind(
            name=item["name"],
            method=item.get("method", "GET").upper(),
            path=item["path"],
            role=item.get("role", item["name"].split(".")[0]),
            body=item.get("body"),
            headers=dict(item.get("headers", {})),
            idempotent=bool(item.get("idempotency", False)),
            replay=float(item.get("replay", 0.0)),
            cross_tenant=str(item.get("cross_tenant", "") or ""),
            expect=item.get("expect", "2xx"),
        )
        kinds[kind.name] = kind
    problems = []
    for profile, weights in data.get("profiles", {}).items():
        for name in weights:
            if name not in kinds:
                problems.append(f"profile `{profile}` names `{name}`, which is not a [[requests]] entry")
    if problems:
        raise SystemExit("scenario errors:\n  " + "\n  ".join(problems))
    return Scenario(path, data, kinds)


def tenant_ids(scenario: Scenario, count: int | None) -> list[str]:
    """The tenants that take part: `ids` from the config (a list, or "first..last"), the first `count` of them."""
    raw = scenario.tenants.get("ids", f"1..{scenario.tenants.get('count', 3)}")
    if isinstance(raw, str) and ".." in raw:
        first, last = (int(x) for x in raw.split(".."))
        ids = [str(i) for i in range(first, last + 1)]
    else:
        ids = [str(i) for i in raw]
    return ids[: count or len(ids)]


def uuid7(at: float | None = None) -> str:
    ms = int((at if at is not None else time.time()) * 1000)
    value = (ms << 80) | (7 << 76) | (secrets.randbits(12) << 64) | (0b10 << 62) | secrets.randbits(62)
    return str(uuid.UUID(int=value))


def fill(template: object, values: dict[str, str], rng: random.Random) -> object:
    """Fill {tenant}, {other_tenant}, {n}, {uuid}, {rand:a-b} and any [tenants.vars] name in strings, lists and dicts."""
    if isinstance(template, str):
        out = template
        while "{rand:" in out:
            start = out.index("{rand:")
            end = out.index("}", start)
            low, high = (int(x) for x in out[start + 6 : end].split("-"))
            out = out[:start] + str(rng.randint(low, high)) + out[end + 1 :]
        for key, value in values.items():
            out = out.replace("{" + key + "}", value)
        return out.replace("{uuid}", str(uuid.UUID(int=rng.getrandbits(128))))
    if isinstance(template, list):
        return [fill(item, values, rng) for item in template]
    if isinstance(template, dict):
        return {key: fill(value, values, rng) for key, value in template.items()}
    return template


# ── signing ──────────────────────────────────────────────────────────────────


class Signer:
    """Headers that sign a request as a role of a tenant. Tokens are made by the user beforehand."""

    def __init__(self, scenario: Scenario) -> None:
        self.auth = scenario.data.get("auth", {})
        self.mode = self.auth.get("mode", "none")
        self.tokens: dict = {}
        if self.mode == "tokens_file":
            file = Path(os.path.expandvars(self.auth.get("file", "tokens.json")))
            if not file.is_absolute():
                file = scenario.path.parent / file
            if not file.is_file():
                raise SystemExit(f"auth mode tokens_file: {file} does not exist (a JSON object: tenant -> role -> token)")
            self.tokens = json.loads(file.read_text(encoding="utf-8"))

    def headers(self, tenant: str, role: str) -> dict[str, str]:
        header = self.auth.get("header", "Authorization")
        prefix = self.auth.get("prefix", "Bearer ")
        if self.mode == "none":
            return {}
        if self.mode == "env":
            # SIM_TOKEN_<ROLE> when set, else SIM_TOKEN (the variable names are configurable).
            base = self.auth.get("env", "SIM_TOKEN")
            token = os.environ.get(f"{base}_{role.upper()}") or os.environ.get(base)
            if not token:
                raise SystemExit(f"auth mode env: set {base} or {base}_{role.upper()} to a token minted on the test stack")
            return {header: prefix + token}
        if self.mode == "tokens_file":
            token = self.tokens.get(tenant, {}).get(role) or self.tokens.get("*", {}).get(role)
            return {header: prefix + token} if token else {}
        if self.mode == "template":
            # A header the stub or a test server accepts, e.g. "Bearer sim-{tenant}-{role}".
            return {header: self.auth.get("template", "Bearer sim-{tenant}-{role}").replace("{tenant}", tenant).replace("{role}", role)}
        raise SystemExit(f"unknown auth mode {self.mode!r}: use none, env, tokens_file or template")


# ── calls ────────────────────────────────────────────────────────────────────


@dataclass
class Call:
    kind: Kind
    tenant: str
    method: str
    url: str
    headers: dict
    body: bytes | None
    replay: bool = False


def make_call(scenario: Scenario, signer: Signer, kind: Kind, tenant: str, tenants: list[str], n: int, rng: random.Random) -> Call:
    others = [t for t in tenants if t != tenant] or [tenant]
    other = rng.choice(others)
    values = {"tenant": tenant, "other_tenant": other, "n": str(n)}
    for name, template in scenario.tenants.get("vars", {}).items():
        values[name] = str(fill(template, values, rng))
    path = str(fill(kind.path, values, rng))
    base = scenario.target.get("base_url", "http://localhost:8000").rstrip("/")
    headers = {"Accept": "application/json", **scenario.target.get("headers", {})}
    headers.update(signer.headers(tenant, kind.role))
    tenant_header = scenario.tenants.get("header")
    if tenant_header:
        # A cross-tenant request carries the other tenant's header: the request a leak test makes.
        headers[tenant_header] = other if kind.cross_tenant == "header" else tenant
    if scenario.tenants.get("forwarded_for", True):
        index = tenants.index(tenant) if tenant in tenants else 0
        headers["X-Forwarded-For"] = f"10.{index // 250 % 250}.{index % 250}.1"
    headers.update({k: str(fill(v, values, rng)) for k, v in kind.headers.items()})
    body = None
    if kind.body is not None:
        body = json.dumps(fill(kind.body, values, rng)).encode()
        headers.setdefault("Content-Type", "application/json")
    if kind.idempotent:
        headers[scenario.data.get("idempotency", {}).get("header", "Idempotency-Key")] = uuid7()
    return Call(kind, tenant, kind.method, base + path, headers, body, replay=kind.replay > 0 and rng.random() < kind.replay)


def check_target(scenario: Scenario, allow: list[str]) -> None:
    host = urlsplit(scenario.target.get("base_url", "http://localhost:8000")).hostname or ""
    allowed = LOCAL_HOSTS | set(scenario.target.get("allow_hosts", [])) | set(allow)
    if host not in allowed:
        raise SystemExit(f"{host} is not this machine; add it to [target] allow_hosts or --allow-host only for a test server, never production")


@dataclass
class Result:
    t: float
    name: str
    status: int
    ms: float
    tenant: str
    code: str = ""
    waited: float = 0.0


def send(call: Call, timeout: float) -> tuple[int, float, dict, str]:
    started = time.perf_counter()
    request = urllib.request.Request(call.url, data=call.body, headers=call.headers, method=call.method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode(errors="replace")
            return response.status, (time.perf_counter() - started) * 1000, dict(response.headers), body
    except urllib.error.HTTPError as error:
        body = error.read(4096).decode(errors="replace")
        return error.code, (time.perf_counter() - started) * 1000, dict(error.headers or {}), body
    except Exception as error:  # a dropped connection is a result too
        return 0, (time.perf_counter() - started) * 1000, {}, type(error).__name__


def error_code(body: str) -> str:
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return ""
    if isinstance(data, dict):
        value = data.get("code") or data.get("error") or (data.get("detail") if isinstance(data.get("detail"), str) else "")
        return str(value or "")[:40]
    return ""


class Driver:
    def __init__(self, scenario: Scenario, args: argparse.Namespace) -> None:
        self.scenario = scenario
        self.args = args
        self.signer = Signer(scenario)
        self.rng = random.Random(args.seed)
        self.tenants = tenant_ids(scenario, args.tenants)
        self.results: list[Result] = []
        self.lock = threading.Lock()
        self.started = 0.0
        self.backlog = 0
        replay = scenario.data.get("idempotency", {})
        self.replay_header = replay.get("replayed_header", "Idempotency-Replayed")

    def calls(self, count: int) -> list[Call]:
        weights = self.scenario.profiles[self.args.profile]
        names, w = list(weights), list(weights.values())
        return [
            make_call(self.scenario, self.signer, self.scenario.kinds[self.rng.choices(names, w)[0]], self.rng.choice(self.tenants), self.tenants, n, self.rng)
            for n in range(1, count + 1)
        ]

    def one(self, call: Call, arrived: float) -> None:
        waited = (time.perf_counter() - arrived) * 1000
        status, ms, headers, body = send(call, self.args.timeout)
        code = error_code(body) if status >= 400 or status == 0 else ""
        rows = [Result(time.perf_counter() - self.started, call.kind.name, status, ms, call.tenant, code if status else body, waited)]
        if call.replay and 200 <= status < 300:
            again, ms2, headers2, _ = send(call, self.args.timeout)
            replayed = str(headers2.get(self.replay_header, "")).lower() == "true"
            rows.append(Result(time.perf_counter() - self.started, call.kind.name + ".replay", again, ms2, call.tenant, "replayed" if replayed else "NOT-REPLAYED"))
        with self.lock:
            self.results += rows

    def run(self) -> float:
        weights = self.scenario.profiles[self.args.profile]
        names, w = list(weights), list(weights.values())
        self.started = time.perf_counter()
        deadline = self.started + self.args.duration
        next_at = self.started
        n = 0
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.args.concurrency)
        futures: set[concurrent.futures.Future] = set()
        while True:
            now = time.perf_counter()
            if now >= deadline:
                break
            if now < next_at:
                time.sleep(min(next_at - now, 0.02))
                continue
            next_at += self.rng.expovariate(self.args.rps)  # Poisson arrivals at --rps
            n += 1
            if n > self.args.max_requests:
                break
            kind = self.scenario.kinds[self.rng.choices(names, w)[0]]
            call = make_call(self.scenario, self.signer, kind, self.rng.choice(self.tenants), self.tenants, n, self.rng)
            future = pool.submit(self.one, call, time.perf_counter())
            futures.add(future)
            future.add_done_callback(futures.discard)
        done, pending = concurrent.futures.wait(set(futures), timeout=self.args.timeout + 5)
        self.backlog = len(pending)
        pool.shutdown(wait=False, cancel_futures=True)
        return time.perf_counter() - self.started


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(p * len(values)) - 1))]


def judged(scenario: Scenario, results: list[Result]) -> list[tuple[str, str, bool]]:
    """(threshold, measured, passed) for each threshold in the scenario."""
    limits = scenario.data.get("thresholds", {})
    plain = [r for r in results if not r.name.endswith(".replay")]
    total = len(plain) or 1
    errors = sum(1 for r in plain if r.status == 0 or r.status >= 500)
    leaks = [r for r in plain if scenario.kinds[r.name].expect == "4xx" and 200 <= r.status < 300]
    not_replayed = [r for r in results if r.code == "NOT-REPLAYED"]
    normal = [r.ms for r in plain if scenario.kinds[r.name].expect != "4xx"]
    measured = {
        "error_rate": (errors / total, f"{100 * errors / total:.2f}% 5xx or no answer"),
        "p95_ms": (pct(normal, 0.95), f"p95 {pct(normal, 0.95):.0f} ms"),
        "p99_ms": (pct(normal, 0.99), f"p99 {pct(normal, 0.99):.0f} ms"),
        "abuse_2xx": (len(leaks), f"{len(leaks)} cross-tenant requests answered 2xx"),
        "not_replayed": (len(not_replayed), f"{len(not_replayed)} changes sent twice with one key and not replayed"),
    }
    out = []
    for name, limit in limits.items():
        if name in measured:
            value, text = measured[name]
            out.append((f"{name} <= {limit}", text, value <= limit))
    return out


def summarise(scenario: Scenario, args: argparse.Namespace, results: list[Result], wall: float, backlog: int) -> str:
    by: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        by[r.name].append(r)
    total = len(results)
    errors = sum(1 for r in results if r.status == 0 or r.status >= 500)
    lines = [
        f"# Simulation: {args.profile}, {len(tenant_ids(scenario, args.tenants))} tenants",
        "",
        f"- Target: {scenario.target.get('base_url', 'http://localhost:8000')}; asked {args.rps} requests/s for {args.duration} s with at most {args.concurrency} in flight",
        f"- Sent {total:,} in {wall:.0f} s ({total / max(wall, 1e-9):.1f}/s achieved); still waiting when the run ended: {backlog:,}",
        f"- 5xx or no answer: {errors:,} ({100 * errors / max(total, 1):.2f}%)",
        f"- As a person feels it (queue + answer): p50 {pct([r.ms + r.waited for r in results], 0.5):.0f} ms, p95 {pct([r.ms + r.waited for r in results], 0.95):.0f} ms",
        f"- The server's answer alone: p50 {pct([r.ms for r in results], 0.5):.0f} ms, p95 {pct([r.ms for r in results], 0.95):.0f} ms, p99 {pct([r.ms for r in results], 0.99):.0f} ms",
        "",
        "| Request | Count | p50 ms | p95 ms | p99 ms | Max ms | 5xx % | Statuses (codes) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, rs in sorted(by.items(), key=lambda kv: -pct([r.ms for r in kv[1]], 0.95)):
        ms = [r.ms for r in rs]
        statuses = Counter(f"{r.status}{'/' + r.code if r.code else ''}" for r in rs)
        err = sum(1 for r in rs if r.status == 0 or r.status >= 500)
        lines.append(
            f"| {name} | {len(rs):,} | {pct(ms, 0.5):.0f} | {pct(ms, 0.95):.0f} | {pct(ms, 0.99):.0f} | {max(ms):.0f}"
            f" | {100 * err / len(rs):.1f} | {', '.join(f'{k} x{v}' for k, v in statuses.most_common(4))} |"
        )
    verdicts = judged(scenario, results)
    if verdicts:
        lines += ["", "## Thresholds", "", "| Threshold | Measured | Result |", "|---|---|---|"]
        lines += [f"| {name} | {text} | {'PASS' if ok else 'FAIL'} |" for name, text, ok in verdicts]
    return "\n".join(lines) + "\n"


# ── commands ─────────────────────────────────────────────────────────────────


def cmd_plan(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    if args.profile not in scenario.profiles:
        raise SystemExit(f"no profile {args.profile!r}; profiles: {', '.join(scenario.profiles)}")
    driver = Driver(scenario, args)
    for call in driver.calls(args.count):
        shown = {k: ("<redacted>" if k.lower() in ("authorization", "cookie") else v) for k, v in call.headers.items()}
        print(f"{call.kind.name:28} {call.method:6} {call.url}  tenant={call.tenant}{'  (sent twice)' if call.replay else ''}")
        if args.verbose:
            print(f"    headers {json.dumps(shown)}")
            if call.body:
                print(f"    body    {call.body.decode()}")
    print(f"\n{args.count} calls planned from profile {args.profile!r} over {len(driver.tenants)} tenants; nothing was sent")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    if args.profile not in scenario.profiles:
        raise SystemExit(f"no profile {args.profile!r}; profiles: {', '.join(scenario.profiles)}")
    check_target(scenario, args.allow_host)
    driver = Driver(scenario, args)
    out = Path(args.out or f"sim-out/{datetime.now():%Y%m%d-%H%M%S}-{args.profile}")
    out.mkdir(parents=True, exist_ok=True)
    print(f"{len(driver.tenants)} tenants, profile {args.profile}, {args.rps}/s for {args.duration} s against {scenario.target.get('base_url')}")
    wall = driver.run()
    with (out / "requests.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t", "request", "status", "ms", "queued_ms", "tenant", "code"])
        for r in sorted(driver.results, key=lambda r: r.t):
            writer.writerow([f"{r.t:.3f}", r.name, r.status, f"{r.ms:.1f}", f"{r.waited:.1f}", r.tenant, r.code])
    summary = summarise(scenario, args, driver.results, wall, driver.backlog)
    (out / "summary.md").write_text(summary)
    print(summary)
    print(f"written to {out}")
    return 0 if all(ok for _, _, ok in judged(scenario, driver.results)) else 1


def cmd_demand(args: argparse.Namespace) -> int:
    """What N real tenants would ask of the API in their busiest hour, to compare with what a run achieved."""
    scenario = load_scenario(args.scenario)
    people = scenario.data.get("population", {})
    peak = scenario.data.get("peak", {})
    per_hour = peak.get("requests_per_hour", {})
    active = peak.get("active_share", {})
    tenants = args.tenants or len(tenant_ids(scenario, None))
    if not people or not per_hour:
        raise SystemExit("demand needs [population] (people per tenant by role) and [peak] requests_per_hour in the scenario")
    print(f"Estimated demand for {tenants} tenants in the busiest hour ({peak.get('label', 'the peak hour')}):\n")
    total = 0.0
    for role, count in people.items():
        n = count * tenants * float(active.get(role, 1.0))
        rps = n * float(per_hour.get(role, 0)) / 3600
        total += rps
        print(f"  {role:10} {n:>10,.0f} active x {per_hour.get(role, 0):>4} requests/h = {rps:8.1f} requests/s")
    burst = float(peak.get("burst_factor", 2.0))
    print(f"\n  average {total:.1f} requests/s; plan for {math.ceil(total * burst)}/s ({burst:g}x for bursts) at the scenario's p95 threshold")
    print("  This is an estimate from the scenario's numbers, not a measurement; a run shows what the machine achieved.")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.scenario)
    if target.exists():
        print(f"{target} exists; nothing written")
        return 0
    shutil.copy(SKILL / "references" / "scenario.example.toml", target)
    print(f"wrote {target}: the generic SaaS example; edit the target, auth, tenants, requests and profiles")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate many tenants' usage against a local or test server.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--scenario", default="load-scenario.toml")
    p = sub.add_parser("plan", parents=[common], help="print the calls a run would make; no network")
    p.add_argument("--profile", default="mixed")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--tenants", type=int)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_plan, timeout=10)
    p = sub.add_parser("run", parents=[common], help="drive traffic at the target")
    p.add_argument("--profile", default="mixed")
    p.add_argument("--tenants", type=int, help="how many of the scenario's tenants take part")
    p.add_argument("--rps", type=float, default=20, help="requests per second asked (Poisson arrivals)")
    p.add_argument("--duration", type=float, default=30, help="seconds")
    p.add_argument("--concurrency", type=int, default=50, help="most requests in flight at once")
    p.add_argument("--max-requests", type=int, default=100_000, help="a hard cap, so a run is always bounded")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--allow-host", action="append", default=[])
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("demand", parents=[common], help="estimate the requests per second N tenants need")
    p.add_argument("--tenants", type=int)
    p.set_defaults(func=cmd_demand)
    p = sub.add_parser("init", parents=[common], help="write the generic SaaS scenario to --scenario")
    p.set_defaults(func=cmd_init)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
