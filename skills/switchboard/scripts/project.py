#!/usr/bin/env python3
"""The project profile: what kind of project this is, so every skill runs only what fits it.
Standard library only (Python 3.11+).

    project.py show   [--json]            the effective profile: shipkit.toml's [project] over what is detected
    project.py detect [--json]            what the repository shows, with evidence and how sure each value is
    project.py toml   [--preset saas]     a complete shipkit.toml for this repository (printed)
    project.py write  [--preset saas]     write it: a new shipkit.toml, or add only what an existing one lacks
    project.py has <trait> [<trait>...]   exit 0 when the profile has every trait (for scripts and agents)
    --root <dir>                          the project (default: SHIPKIT_ROOT, else the shipkit.toml or git root)

The [project] table

    kind     = "saas"            saas | self-hosted | app | cli | library | infra | container-app
    tenancy  = "multi-tenant"    none | single-user | multi-user | multi-tenant
    money    = "payments"        none | payments
    plans    = "tiers"           none | tiers        (priced plans: a pricing page, a feature map by tier)
    auth     = "accounts"        none | local | accounts
    surfaces = ["api", "web"]    any of: api, web, native, cli, shell, container, library
    offline  = false             the app keeps working without a network and syncs later

A value set in shipkit.toml always wins; a value left out is detected. Nothing undetected is
assumed: a project with no tenant code is not multi-tenant, one with no payment code takes no money.

Traits, the words skills, checklists and kits.toml use in `needs` / `requires`:

    multi-tenant   tenancy is multi-tenant           money        money is not none
    accounts       auth is accounts (sign-up)        plans        plans is tiers
    auth           auth is local or accounts         offline      offline is true
    server         an api, a web app or a container  hosted       kind is saas
    self-hosted    kind is self-hosted or container-app
    api, web, native, cli, shell, container, library   that surface is present
    saas, app, infra, container-app                    that kind (as is self-hosted)

A trait written `!money` means the profile does not have it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("saas", "self-hosted", "app", "cli", "library", "infra", "container-app")
VALUES = {
    "kind": KINDS,
    "tenancy": ("none", "single-user", "multi-user", "multi-tenant"),
    "money": ("none", "payments"),
    "plans": ("none", "tiers"),
    "auth": ("none", "local", "accounts"),
}
SURFACES = ("api", "web", "native", "cli", "shell", "container", "library")
PRUNE = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next", ".expo", "coverage", "target",
    ".turbo", ".cache", "vendor", ".claude", ".agents", ".trae", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}  # fmt: skip
CODE = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".rb", ".java", ".kt", ".cs", ".php", ".sql", ".prisma", ".vue", ".svelte"}
MAX_FILES = 20000
MAX_READ = 200_000  # bytes read from one file

# What the code says. Each pattern counts the files it appears in.
TENANT = re.compile(
    r"\b(tenant_?id|workspace_?id|organi[sz]ation_?id|org_?id|account_?id)\b|x-(tenant|workspace|org)(-id)?\b|\btenant\b",
    re.I,
)
MONEY_DEPS = re.compile(
    r"""["'\s](stripe|@stripe/[\w-]+|razorpay|paddle|@paddle/[\w-]+|lemonsqueezy|@lemonsqueezy/[\w-]+|braintree|"""
    r"""paypal[\w-]*|@paypal/[\w-]+|chargebee|recurly|mollie[\w-]*|adyen[\w-]*|square|polar-sdk|@polar-sh/[\w-]+|dj-stripe|"""
    r"""pay|cashier)["'\s=<>~^]""",
    re.I,
)
MONEY_CODE = re.compile(
    r"\b(payment_?intent|checkout_?session|invoices?|refunds?|subscriptions?|billing|razorpay|stripe)\b", re.I
)
PLANS_CODE = re.compile(r"\b(plan_?id|price_?id|pricing_?tier|subscription_?plan|PLANS|COMPARISON)\b")
ACCOUNT_DEPS = re.compile(
    r"""["'\s](next-auth|@auth/[\w-]+|@clerk/[\w-]+|auth0[\w-]*|@auth0/[\w-]+|@supabase/(auth|supabase)[\w-]*|"""
    r"""firebase|better-auth|lucia|passport[\w-]*|fastapi-users|django-allauth|authlib|python-jose|pyjwt|"""
    r"""jsonwebtoken|devise|@kinde-oss/[\w-]+|workos[\w-]*|@workos-inc/[\w-]+|supertokens[\w-]*)["'\s=<>~^]""",
    re.I,
)
SIGNUP = re.compile(r"\b(sign_?up|register|signup|create_?account|invite_?member|reset_?password)\b", re.I)
LOCAL_AUTH = re.compile(r"\b(password|api_?key|bearer|auth_?token|basic_?auth|session_?secret)\b", re.I)
OFFLINE = re.compile(r"\b(expo-sqlite|op-sqlite|watermelondb|dexie|outbox|powersync|electric-sql|rxdb|replicache)\b")
SERVER_DEPS = re.compile(
    r"""["'\s](fastapi|flask|django|starlette|litestar|aiohttp|tornado|sanic|express|fastify|koa|hono|"""
    r"""@nestjs/core|@hapi/hapi|elysia|next|nuxt|@remix-run/[\w-]+|@sveltejs/kit|actix-web|axum|rocket|warp|gin|echo|fiber)["'\s=<>~^\[]""",
    re.I,
)
WEB_DEPS = re.compile(r"""["'](vite|vite-plus|next|nuxt|@sveltejs/kit|@remix-run/react|astro|@angular/core|react-scripts)["']""")
NATIVE_DEPS = re.compile(r"""["'](expo|react-native)["']""")
SCRIPT_SERVER = re.compile(r"\b(uvicorn|gunicorn|hypercorn|flask run|manage\.py runserver|node .*server|listen\()")


@dataclass
class Value:
    value: object
    sure: bool  # from a manifest or the config, not a guess from counting words
    evidence: list[str] = field(default_factory=list)
    source: str = "detected"  # detected | shipkit.toml


@dataclass
class Detected:
    root: Path
    values: dict[str, Value] = field(default_factory=dict)
    stack: dict[str, object] = field(default_factory=dict)  # api_dir, web_dirs, native_dir
    packages: list[str] = field(default_factory=list)
    docs_dir: str = "docs"
    code_roots: list[str] = field(default_factory=list)
    ports: dict[str, int] = field(default_factory=dict)
    files: int = 0


# ── the files ────────────────────────────────────────────────────────────────


def find_root(start: Path | None = None) -> Path:
    if os.environ.get("SHIPKIT_ROOT") and start is None:
        return Path(os.environ["SHIPKIT_ROOT"]).resolve()
    here = (start or Path.cwd()).resolve()
    for marker in ("shipkit.toml", ".git"):
        for folder in (here, *here.parents):
            if (folder / marker).exists():
                return folder
    return here


def list_files(root: Path) -> list[str]:
    """The project's files as posix paths from the root: git's list when it is a repository, else a walk."""
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True
    )
    if done.returncode == 0 and done.stdout.strip():
        out = [p for p in done.stdout.splitlines() if p and not any(part in PRUNE for part in p.split("/"))]
        return [p for p in out if (root / p).is_file()][:MAX_FILES]
    out = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in PRUNE)
        rel = Path(folder).relative_to(root)
        out += [(rel / n).as_posix() for n in sorted(names)]
        if len(out) >= MAX_FILES:
            break
    return out[:MAX_FILES]


def read(root: Path, rel: str) -> str:
    try:
        with open(root / rel, "rb") as fh:
            return fh.read(MAX_READ).decode("utf-8", "replace")
    except OSError:
        return ""


def parent(rel: str) -> str:
    p = Path(rel).parent.as_posix()
    return "" if p == "." else p


# ── detection ────────────────────────────────────────────────────────────────


def detect(root: Path) -> Detected:
    root = root.resolve()
    d = Detected(root=root)
    files = list_files(root)
    d.files = len(files)
    names = {Path(f).name for f in files}
    manifests = [f for f in files if Path(f).name in ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "Gemfile")]
    manifest_text = {m: read(root, m) for m in manifests}
    deps_all = "\n".join(manifest_text.values())

    # surfaces and where each lives
    api_dirs, web_dirs, native_dirs, cli_ev, lib_ev = [], [], [], [], []
    for m, text in manifest_text.items():
        folder = parent(m)
        name = Path(m).name
        if NATIVE_DEPS.search(text) and name == "package.json":
            native_dirs.append(folder)
            continue
        if WEB_DEPS.search(text) and name == "package.json" and not SERVER_DEPS.search(text.replace('"next"', "")):
            web_dirs.append(folder)
        elif SERVER_DEPS.search(text):
            (web_dirs if re.search(r"""["'](next|nuxt|@sveltejs/kit|@remix-run/[\w-]+)["']""", text) else api_dirs).append(folder)
        if name == "pyproject.toml" and re.search(r"^\[project\.scripts\]|^\[tool\.poetry\.scripts\]", text, re.M):
            cli_ev.append(m)
        if name == "package.json" and re.search(r'"bin"\s*:', text):
            cli_ev.append(m)
        if name == "Cargo.toml" and (re.search(r"^\[\[bin\]\]", text, re.M) or f"{folder + '/' if folder else ''}src/main.rs" in files):
            cli_ev.append(m)
        if name == "Cargo.toml" and (re.search(r"^\[lib\]", text, re.M) or f"{folder + '/' if folder else ''}src/lib.rs" in files):
            lib_ev.append(m)
        if name == "pyproject.toml" and not SERVER_DEPS.search(text) and m not in cli_ev and re.search(r"^\[project\]", text, re.M):
            lib_ev.append(m)
        if name == "package.json" and re.search(r'"(exports|main|module)"\s*:', text) and folder not in web_dirs + api_dirs + native_dirs:
            if not re.search(r'"private"\s*:\s*true', text):
                lib_ev.append(m)
    for f in files:
        if Path(f).name.startswith("vite.config.") and parent(f) not in web_dirs:
            web_dirs.append(parent(f))
        if Path(f).name in ("app.json", "app.config.ts", "app.config.js") and '"expo"' in read(root, f) and parent(f) not in native_dirs:
            native_dirs.append(parent(f))
    if not cli_ev:
        cli_ev = [f for f in files if Path(f).name in ("cli.py", "__main__.py", "main.go") or f.startswith("cmd/")][:3]
    if not cli_ev:  # scripts meant to be run: bin/ or scripts/ with a main guard
        cli_ev = [f for f in files if f.split("/")[0] in ("bin", "scripts") and f.endswith(".py") and "__main__" in read(root, f)][:3]
    for f in files:  # a Python package with an entry point and a server dependency in requirements is an API
        if Path(f).name in ("main.py", "app.py", "server.py") and not api_dirs and SERVER_DEPS.search(" " + read(root, f)[:4000] + " "):
            api_dirs.append(parent(f))
    shell = [f for f in files if f.endswith((".sh", ".bash")) or (Path(f).suffix == "" and read(root, f)[:40].startswith("#!/") and "sh" in read(root, f)[:40])]
    container = [f for f in files if Path(f).name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "umbrel-app.yml", "Containerfile")]
    infra = [f for f in files if f.endswith((".tf", ".tfvars")) or "ansible" in f or f.endswith(("playbook.yml", "inventory.ini")) or Path(f).name == "fleet.json"]

    def uniq(xs: list[str]) -> list[str]:
        return list(dict.fromkeys(xs))

    api_dirs, web_dirs, native_dirs = uniq(api_dirs), uniq(web_dirs), uniq(native_dirs)
    surfaces = []
    if api_dirs:
        surfaces.append("api")
    if web_dirs:
        surfaces.append("web")
    if native_dirs:
        surfaces.append("native")
    if cli_ev:
        surfaces.append("cli")
    code_files = [f for f in files if Path(f).suffix.lower() in CODE]
    if shell and (len(shell) >= 2 or len(shell) * 3 >= max(1, len(code_files))):
        surfaces.append("shell")
    if container:
        surfaces.append("container")
    if lib_ev and not (api_dirs or web_dirs or native_dirs):
        surfaces.append("library")
    d.values["surfaces"] = Value(surfaces, True, (api_dirs + web_dirs + native_dirs + cli_ev + shell[:2] + container[:2] + lib_ev)[:6])
    d.stack = {"api_dir": api_dirs[0] if api_dirs else "", "web_dirs": web_dirs, "native_dir": native_dirs[0] if native_dirs else ""}

    # what the code says: count files that mention each thing
    def hits(pattern: re.Pattern, pool: list[str], limit: int = 3000) -> list[str]:
        return [f for f in pool[:limit] if pattern.search(read(root, f))]

    tenant_files = [f for f in hits(TENANT, code_files) if "/test" not in f and not f.startswith("test")]
    money_deps = [m for m, t in manifest_text.items() if MONEY_DEPS.search(t)]
    money_dirs = sorted({f.split("/billing/")[0] + "/billing/" for f in files if "/billing/" in f or f.startswith("billing/")} | {f.split("/payments/")[0] + "/payments/" for f in files if "/payments/" in f or f.startswith("payments/")})
    money_files = [f for f in hits(MONEY_CODE, code_files) if "/test" not in f]
    pricing_files = [f for f in files if re.search(r"(^|/)(pricing|plans)[\w.-]*\.(tsx?|jsx?|vue|svelte|md|mdx|astro|html)$", f, re.I)]
    plans_code = hits(PLANS_CODE, code_files)
    account_deps = [m for m, t in manifest_text.items() if ACCOUNT_DEPS.search(t)]
    signup_files = [f for f in hits(SIGNUP, code_files) if "/test" not in f]
    local_auth = hits(LOCAL_AUTH, [f for f in code_files if any(f.startswith(a + "/") or a == "" for a in api_dirs)] or code_files)
    offline_ev = [f for f in manifests + code_files if OFFLINE.search(read(root, f))][:3]
    server = bool(api_dirs or web_dirs or any(SCRIPT_SERVER.search(read(root, f)) for f in container[:3]))

    # tenancy, money, plans and accounts belong to something that serves people: without an API, a web
    # app or a container, code that merely talks about them (a tool, a library) does not make them so.
    if not server:
        tenant_files, money_dirs, money_files, pricing_files, plans_code, signup_files = [], [], [], [], [], []

    # tenancy
    if len(tenant_files) >= 3:
        d.values["tenancy"] = Value("multi-tenant", len(tenant_files) >= 8, tenant_files[:3])
    elif (account_deps and server) or len(signup_files) >= 2:
        d.values["tenancy"] = Value("multi-user", bool(account_deps), (account_deps + signup_files)[:3])
    elif server or surfaces:
        d.values["tenancy"] = Value("single-user" if server else "none", False, [])
    else:
        d.values["tenancy"] = Value("none", False, [])

    # money
    if money_deps and server:
        d.values["money"] = Value("payments", True, (money_deps + money_dirs)[:3])
    elif money_dirs or len(money_files) >= 5:
        d.values["money"] = Value("payments", False, (money_dirs + money_files)[:3])
    else:
        d.values["money"] = Value("none", not money_files, money_files[:3])

    # plans
    catalog = root / "docs" / "feature_catalog.md"
    if pricing_files or (catalog.exists() and re.search(r"^## (Free|Pro|Enterprise|Team|Business)\b", catalog.read_text(errors="replace"), re.M)):
        d.values["plans"] = Value("tiers", bool(pricing_files), pricing_files[:3] or ["docs/feature_catalog.md"])
    elif d.values["money"].value == "payments" and len(plans_code) >= 2:
        d.values["plans"] = Value("tiers", False, plans_code[:3])
    else:
        d.values["plans"] = Value("none", d.values["money"].value == "none", [])

    # auth
    if (account_deps and server) or (len(signup_files) >= 2 and d.values["tenancy"].value in ("multi-user", "multi-tenant")):
        d.values["auth"] = Value("accounts", bool(account_deps), (account_deps + signup_files)[:3])
    elif local_auth and server:
        d.values["auth"] = Value("local", False, local_auth[:3])
    else:
        d.values["auth"] = Value("none", False, [])

    if not (server or native_dirs):
        offline_ev = []
    d.values["offline"] = Value(bool(offline_ev), bool(offline_ev), offline_ev)

    # kind
    t, m = d.values["tenancy"].value, d.values["money"].value
    if t == "multi-tenant" or (m == "payments" and d.values["auth"].value == "accounts"):
        kind, sure = "saas", t == "multi-tenant" and d.values["tenancy"].sure
    elif "umbrel-app.yml" in names or (container and not (api_dirs or web_dirs or cli_ev) and not lib_ev):
        kind, sure = "container-app", "umbrel-app.yml" in names
    elif server and container:
        kind, sure = "self-hosted", False
    elif server:
        kind, sure = ("app" if t == "multi-user" else "self-hosted"), False
    elif "native" in surfaces:
        kind, sure = "app", True
    elif infra or ("shell" in surfaces and not code_files):
        kind, sure = "infra", bool(infra)
    elif cli_ev:
        kind, sure = "cli", True
    elif lib_ev:
        kind, sure = "library", True
    else:
        kind, sure = "app", False
    d.values["kind"] = Value(kind, sure, [])

    # docs, packages, code roots, ports
    d.docs_dir = "docs" if (root / "docs").is_dir() else ("doc" if (root / "doc").is_dir() else "docs")
    pkgs = sorted({f.split("/")[0] + "/*" for f in manifests if f.count("/") == 2 and f.split("/")[0] in ("apps", "packages", "services", "libs", "crates")})
    if not pkgs:
        pkgs = sorted({parent(f) for f in files if Path(f).name == "CHANGELOG.md" and parent(f)})
    d.packages = pkgs
    roots = []
    for folder in api_dirs:
        for sub in ("app", "src", Path(folder).name.replace("-", "_")):
            if (root / folder / sub).is_dir():
                roots.append(f"{folder}/{sub}".lstrip("/"))
                break
        else:
            roots.append(folder or ".")
    for folder in web_dirs + native_dirs:
        roots.append(f"{folder}/src".lstrip("/") if (root / folder / "src").is_dir() else (folder or "."))
    d.code_roots = uniq(roots)
    d.ports = detect_ports(root, files, api_dirs, web_dirs)
    return d


def detect_ports(root: Path, files: list[str], api_dirs: list[str], web_dirs: list[str]) -> dict[str, int]:
    ports: dict[str, int] = {}
    for f in files:
        name = Path(f).name
        if name.startswith("vite.config.") and "WEB_PORT" not in ports:
            found = re.search(r"\bport\s*:\s*(\d{2,5})", read(root, f))
            if found:
                ports["WEB_PORT"] = int(found.group(1))
        if name in (".env.example", ".env.sample", "docker-compose.yml", "compose.yml", "Dockerfile", "Makefile", "package.json", "pyproject.toml") and "API_PORT" not in ports:
            text = read(root, f)
            found = re.search(r"\b(?:API_)?PORT\s*[=:]\s*\"?(\d{2,5})", text) or re.search(r"--port[ =](\d{2,5})", text)
            if found and api_dirs:
                ports["API_PORT"] = int(found.group(1))
    if api_dirs:
        ports.setdefault("API_PORT", 8000)
    if web_dirs:
        ports.setdefault("WEB_PORT", 5173)
    return ports


# ── the effective profile ────────────────────────────────────────────────────


def config(root: Path) -> dict:
    path = root / "shipkit.toml"
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}


@dataclass
class Profile:
    root: Path
    values: dict[str, Value]
    configured: bool  # shipkit.toml has a [project] table

    def get(self, key: str) -> object:
        return self.values[key].value

    @property
    def traits(self) -> set[str]:
        v = {k: x.value for k, x in self.values.items()}
        surfaces = set(v["surfaces"])
        out = set(surfaces) | {str(v["kind"])}
        if v["tenancy"] == "multi-tenant":
            out.add("multi-tenant")
        if v["money"] != "none":
            out.add("money")
        if v["plans"] == "tiers":
            out.add("plans")
        if v["auth"] == "accounts":
            out |= {"accounts", "auth"}
        elif v["auth"] == "local":
            out.add("auth")
        if v["offline"]:
            out.add("offline")
        if surfaces & {"api", "web", "container"} or v["kind"] in ("saas", "self-hosted", "container-app"):
            out.add("server")
        if v["kind"] == "saas":
            out.add("hosted")
        if v["kind"] in ("self-hosted", "container-app"):
            out.add("self-hosted")
        return out

    def has(self, *needs: str) -> bool:
        traits = self.traits
        return all((n[1:] not in traits) if n.startswith("!") else (n in traits) for n in needs)

    def missing(self, *needs: str) -> list[str]:
        traits = self.traits
        return [n for n in needs if ((n[1:] in traits) if n.startswith("!") else (n not in traits))]

    def line(self) -> str:
        v = {k: x.value for k, x in self.values.items()}
        bits = [str(v["kind"]), str(v["tenancy"]), "money" if v["money"] != "none" else "no money",
                "priced plans" if v["plans"] == "tiers" else "no plans", f"auth {v['auth']}",
                "surfaces " + (", ".join(v["surfaces"]) or "none")]  # fmt: skip
        if v["offline"]:
            bits.append("offline")
        return " · ".join(bits) + ("" if self.configured else "  (detected; `project.py write` records it)")


def profile(root: Path | None = None, cfg: dict | None = None, detected: Detected | None = None) -> Profile:
    root = (root or find_root()).resolve()
    cfg = config(root) if cfg is None else cfg
    table = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    keys = ("kind", "tenancy", "money", "plans", "auth", "surfaces", "offline")
    values: dict[str, Value] = {}
    need = [k for k in keys if k not in table]
    if need:
        detected = detected or detect(root)
    for k in keys:
        if k in table:
            values[k] = Value(table[k], True, [], "shipkit.toml")
        else:
            values[k] = detected.values[k]  # type: ignore[union-attr]
    return Profile(root, values, bool(table))


def problems(cfg: dict) -> list[str]:
    out = []
    table = cfg.get("project", {})
    for key, allowed in VALUES.items():
        if key in table and table[key] not in allowed:
            out.append(f"[project] {key} = {table[key]!r} is not one of {', '.join(allowed)}")
    for s in table.get("surfaces", []):
        if s not in SURFACES:
            out.append(f"[project] surfaces: {s!r} is not one of {', '.join(SURFACES)}")
    if "offline" in table and not isinstance(table["offline"], bool):
        out.append("[project] offline is true or false")
    return out


# ── the shipkit.toml it writes ───────────────────────────────────────────────


def q(s: object) -> str:
    return json.dumps(s)


def arr(xs: list) -> str:
    return "[" + ", ".join(q(x) for x in xs) + "]"


def note(v: Value) -> str:
    if v.source == "shipkit.toml":
        return "set"
    if v.source == "preset":
        return "the saas preset"
    ev = f": {', '.join(v.evidence[:3])}" if v.evidence else ""
    return ("detected" if v.sure else "guess, check it") + ev


def draft(root: Path, preset: str = "") -> dict[str, list[str]]:
    """The tables of a shipkit.toml for this repository: {table name: its lines, header included}."""
    d = detect(root)
    p = profile(root, cfg={}, detected=d)
    if preset == "saas":
        p.values.update({
            "kind": Value("saas", True, [], "preset"), "tenancy": Value("multi-tenant", True, [], "preset"),
            "money": Value("payments", True, [], "preset"), "plans": Value("tiers", True, [], "preset"),
            "auth": Value("accounts", True, [], "preset"),
        })  # fmt: skip
    v = p.values
    t: dict[str, list[str]] = {}
    t["project"] = [
        "# What kind of project this is. Skills, checklists and kits run only the parts that fit it.",
        "# Each value is detected (sure), a guess to check, or set by hand. See `project.py --help`.",
        "[project]",
        f"kind = {q(v['kind'].value):<22} # {'|'.join(KINDS)} ({note(v['kind'])})",
        f"tenancy = {q(v['tenancy'].value):<19} # none|single-user|multi-user|multi-tenant ({note(v['tenancy'])})",
        f"money = {q(v['money'].value):<21} # none|payments ({note(v['money'])})",
        f"plans = {q(v['plans'].value):<21} # none|tiers: priced plans ({note(v['plans'])})",
        f"auth = {q(v['auth'].value):<22} # none|local|accounts ({note(v['auth'])})",
        f"surfaces = {arr(v['surfaces'].value):<18} # api, web, native, cli, shell, container, library",
        f"offline = {str(v['offline'].value).lower():<19} # works offline and syncs later",
    ]
    t["stack"] = [
        "# Where the code is, so the stack skills look in the right place (\"\" or [] when there is none).",
        "[stack]",
        f"api_dir = {q(d.stack['api_dir'])}",
        f"web_dirs = {arr(d.stack['web_dirs'])}",
        f"native_dir = {q(d.stack['native_dir'])}",
    ]
    t["docsync"] = [
        "# docsync: the documentation contract.",
        "[docsync]",
        f"docs_dir = {q(d.docs_dir)}",
        f"packages = {arr(d.packages)}{'':<10} # each keeps its own CHANGELOG.md; [] for a one-package repo",
        f'tracker = "{d.docs_dir}/feature_status.md"',
        f'features_dir = "{d.docs_dir}/features"',
        f"code_roots = {arr(d.code_roots)}",
        f'bug_register = "{d.docs_dir}/testing/bug_report.md"',
        f'attack_log = "{d.docs_dir}/testing/attack_log.md"',
        'naming = "snake"                   # snake | kebab | lower | any',
    ]
    if "plans" in p.traits:
        t["docsync"] += [
            f'plan_sources = ["{d.docs_dir}/feature_catalog.md"]',
            "pairs = []                         # e.g. [[\"apps/web/src/pricing.ts\", \"docs/pricing.md\"]]",
        ]
    if "multi-tenant" in p.traits or "money" in p.traits or "api" in p.traits:
        t["harden"] = ["[harden]", f'matrix = "{d.docs_dir}/testing/test_matrix.md"', f'axes = "{d.docs_dir}/testing/axes.toml"']
    t["open_loops"] = ["[open_loops]", f'register = "{d.docs_dir}/open_questions.md"']
    fm = ["# feature-map: the map of features" + (" and the priced plans (tiers, cheapest first)." if "plans" in p.traits else "; no priced plans, so no tiers."),
          "[feature_map]", f'catalog = "{d.docs_dir}/feature_catalog.md"']  # fmt: skip
    fm.append('tiers = ["Free", "Pro", "Enterprise"]   # your plan names' if "plans" in p.traits else "tiers = []")
    t["feature_map"] = fm
    if len(p.values["surfaces"].value) > 1 or d.ports:
        ports = ", ".join(f"{k} = {n}" for k, n in d.ports.items())
        t["fanout"] = ["[fanout]", "max_parallel = 3"] + ([f"ports = {{ {ports} }}"] if ports else [])
    if "api" in p.traits or "native" in p.traits:
        t["seedbed"] = ["[seedbed]", 'config = "seedbed.toml"']
    t["ship_check"] = ["# ship-check: its checklist keeps only the items this profile needs (`requires`).", "[ship_check]", 'checklist = "ship-check.toml"']
    t["handoff"] = ["[handoff]", 'file = "HANDOFF.md"', 'owner = "the owner"', 'timezone = "UTC"']
    t["triage"] = ["[triage]", 'repo_url = ""                       # default: the origin remote', 'timezone = "UTC"']
    return t


def render(tables: dict[str, list[str]]) -> str:
    head = "# shipkit.toml: one config for every shipkit skill, written from this repository by project.py.\n# Check the lines marked \"guess\", then delete these notes as you like.\n"
    return head + "\n" + "\n\n".join("\n".join(lines) for lines in tables.values()) + "\n"


def merge(existing: str, tables: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Add to an existing shipkit.toml only the tables and keys it lacks; never change a value it has."""
    have = tomllib.loads(existing)
    lines = existing.rstrip("\n").split("\n")
    added: list[str] = []
    for name, body in tables.items():
        if name not in have:
            lines += ["", *body]
            added.append(f"[{name}]")
            continue
        missing = [ln for ln in body if re.match(r"^[a-z_]+ = ", ln) and ln.split(" = ")[0] not in have[name]]
        if not missing:
            continue
        at = next((i for i, ln in enumerate(lines) if ln.strip() == f"[{name}]"), None)
        if at is None:
            continue  # an inline or dotted table: leave it to the person
        end = at + 1
        while end < len(lines) and not lines[end].lstrip().startswith("["):
            end += 1
        while end > at + 1 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = missing
        added += [f"[{name}] {ln.split(' = ')[0]}" for ln in missing]
    return "\n".join(lines) + "\n", added


# ── command line ─────────────────────────────────────────────────────────────


def show(p: Profile, as_json: bool) -> str:
    if as_json:
        return json.dumps({
            "root": str(p.root), "configured": p.configured, "traits": sorted(p.traits),
            "values": {k: {"value": v.value, "sure": v.sure, "source": v.source, "evidence": v.evidence} for k, v in p.values.items()},
        }, indent=2)  # fmt: skip
    out = [f"Profile: {p.line()}", ""]
    for k, v in p.values.items():
        val = ", ".join(v.value) if isinstance(v.value, list) else str(v.value).lower() if isinstance(v.value, bool) else str(v.value)
        out.append(f"  {k:<9} {val or '-':<24} {note(v)}")
    out += ["", "Traits: " + ", ".join(sorted(p.traits))]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    def opt(name: str, default: str = "") -> str:
        if name in argv:
            i = argv.index(name)
            value = argv[i + 1] if i + 1 < len(argv) else default
            del argv[i : i + 2]
            return value
        return default

    root_arg = opt("--root")
    preset = opt("--preset")
    if preset not in ("", "saas"):
        raise SystemExit("project.py: --preset is saas (or leave it out to detect everything)")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    root = Path(root_arg).resolve() if root_arg else find_root()
    cmd = argv[0]
    if cmd == "show":
        cfg = config(root)
        for problem in problems(cfg):
            print(problem, file=sys.stderr)
        print(show(profile(root, cfg), as_json))
        return 1 if problems(cfg) else 0
    if cmd == "detect":
        print(show(profile(root, cfg={}), as_json))
        return 0
    if cmd == "has":
        if len(argv) < 2:
            raise SystemExit("project.py has <trait> [<trait> ...]")
        p = profile(root)
        missing = p.missing(*argv[1:])
        if missing:
            print(f"no: the profile lacks {', '.join(missing)} ({p.line()})")
            return 1
        print("yes")
        return 0
    if cmd in ("toml", "write"):
        tables = draft(root, preset)
        path = root / "shipkit.toml"
        if cmd == "toml":
            print(render(tables), end="")
            return 0
        if not path.exists():
            path.write_text(render(tables), encoding="utf-8")
            print(f"wrote {path}")
            print(f"Profile: {profile(root).line()}")
            guesses = [ln.split(" =")[0] for ln in tables["project"] if "guess, check it" in ln]
            if guesses:
                print(f"check these guesses in [project]: {', '.join(guesses)}")
            return 0
        try:
            text, added = merge(path.read_text(encoding="utf-8"), tables)
        except tomllib.TOMLDecodeError as e:
            print(f"{path} does not parse ({e}); nothing written")
            return 1
        if added:
            path.write_text(text, encoding="utf-8")
            print(f"{path}: added {', '.join(added)}; nothing that was set changed")
        else:
            print(f"{path} already has every table and key; nothing written")
        return 0
    raise SystemExit(f"project.py: unknown command {cmd!r}; see --help")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
