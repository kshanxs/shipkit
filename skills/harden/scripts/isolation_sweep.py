#!/usr/bin/env python3
"""
isolation_sweep.py: every route that names a record, aimed at another tenant's records.
Standard library only (Python 3.11+). Works on any HTTP API that publishes an OpenAPI document.

    python3 isolation_sweep.py --config sweep.toml --dry-run      # the requests it would make
    python3 isolation_sweep.py --config sweep.toml                # reads
    python3 isolation_sweep.py --config sweep.toml --writes       # reads and writes (a scratch database only)

For each route under `prefix` whose path names a record (a parameter called `id` or ending in
`_id`/`Id`), it fills the path with tenant A's real record ids and:

  * GET: asks as A (the control: the record is real and readable), then as B with B's tenant header.
    B must not get a 2xx.
  * a write (with --writes): asks only as B, with a body built from the route's schema and A's ids
    in every id field. B must not get a 2xx.

A 2xx for B is printed as a CANDIDATE: read it; some routes are not about a tenant's records.
Exit status 1 when there is a candidate, 2 when the server cannot be reached (0 for --dry-run).
--base-url overrides base_url, and an OpenAPI URL on the same server. The target must be this
machine unless allow_hosts names a test server. Never production. The config (generic SaaS example, references/sweep.example.toml):

    openapi = "http://localhost:8000/openapi.json"   # or a file
    base_url = "http://localhost:8000"
    prefix = "/api/v1"
    skip = ["/api/v1/admin/*", "/api/v1/auth/*"]
    tenant_header = "X-Workspace-ID"
    [a]  tenant = "1"   headers = { Authorization = "Bearer ${TOKEN_A}" }
    [b]  tenant = "2"   headers = { Authorization = "Bearer ${TOKEN_B}" }
    [ids] project_id = "11"  task_id = "301"  id = "11"
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ID_PARAM = re.compile(r"\{([A-Za-z_]*?(?:^id|_id|Id|ID)|id)\}")
WRITES = ("post", "put", "patch", "delete")


class Unreachable(Exception):
    """The server at a URL did not answer: nothing is listening, or the name does not resolve."""

    def __init__(self, url: str, reason: object) -> None:
        super().__init__(f"cannot reach {url} ({reason})")
        self.url = url


def unreachable(error: BaseException) -> bool:
    """A connection failure, as opposed to an HTTP status (HTTPError is a URLError too)."""
    return isinstance(error, ConnectionError) or (isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError))


def expand(value: str) -> str:
    """${VAR} and $VAR from the environment, so tokens stay out of the config file."""
    return os.path.expandvars(value)


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"No sweep config at {path}; start from the harden skill's references/sweep.example.toml")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_openapi(source: str, base: Path) -> dict:
    if source.startswith(("http://", "https://")):
        host = urlsplit(source).hostname or ""
        if host not in LOCAL_HOSTS:
            raise SystemExit(f"the OpenAPI document must come from this machine or a file, not {host}")
        try:
            with urllib.request.urlopen(source, timeout=20) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, ConnectionError) as error:
            if unreachable(error):
                raise Unreachable(source, getattr(error, "reason", error)) from None
            raise
    path = Path(source) if Path(source).is_absolute() else base / source
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_ref(spec: dict, node: dict) -> dict:
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < 20:
        parts = node["$ref"].lstrip("#/").split("/")
        node = spec
        for part in parts:
            node = node.get(part, {})
        seen += 1
    return node if isinstance(node, dict) else {}


def sample(spec: dict, schema: dict, ids: dict[str, str], depth: int = 0) -> object:
    """A minimal valid-looking body: required fields only, A's ids in every id field."""
    schema = resolve_ref(spec, schema)
    for key in ("allOf", "anyOf", "oneOf"):
        if schema.get(key):
            return sample(spec, schema[key][0], ids, depth)
    kind = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if kind == "object" or "properties" in schema:
        if depth > 4:
            return {}
        props = schema.get("properties", {})
        required = schema.get("required", list(props)[:3])
        out = {}
        for name in required:
            if name in ids or name.endswith("_id"):
                out[name] = ids.get(name) or ids.get("id") or "1"
            elif name in props:
                out[name] = sample(spec, props[name], ids, depth + 1)
        return out
    if kind == "array":
        return [sample(spec, schema.get("items", {}), ids, depth + 1)]
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True
    if schema.get("format") == "date":
        return "2026-01-01"
    if schema.get("format") == "date-time":
        return "2026-01-01T09:00:00Z"
    if schema.get("format") == "email":
        return "sweep@example.test"
    return "sweep"


def routes(spec: dict, prefix: str, skip: list[str]) -> list[tuple[str, str, dict]]:
    """(method, path, operation) for every route under prefix whose path names a record."""
    found = []
    for path, item in sorted(spec.get("paths", {}).items()):
        if not path.startswith(prefix) or any(fnmatch.fnmatch(path, pattern) for pattern in skip):
            continue
        if not ID_PARAM.search(path):
            continue
        for method, operation in item.items():
            if method.lower() in ("get", *WRITES) and isinstance(operation, dict):
                found.append((method.lower(), path, operation))
    return found


def fill_path(path: str, ids: dict[str, str]) -> tuple[str, list[str]]:
    missing = []

    def value(match: re.Match) -> str:
        name = match.group(1)
        if name in ids:
            return str(ids[name])
        missing.append(name)
        return "1"

    return re.sub(r"\{([^}]+)\}", value, path), missing


def send(method: str, url: str, headers: dict, body: object | None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method.upper(), headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(300).decode(errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(300).decode(errors="replace")
    except (urllib.error.URLError, ConnectionError) as error:
        if unreachable(error):
            raise Unreachable(url, getattr(error, "reason", error)) from None
        return 0, type(error).__name__
    except Exception as error:
        return 0, type(error).__name__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Every record route, aimed at another tenant's records.")
    parser.add_argument("--config", default="sweep.toml")
    parser.add_argument("--writes", action="store_true", help="also try every write as B (a scratch database only)")
    parser.add_argument("--only", help="only routes whose path matches this regular expression")
    parser.add_argument("--dry-run", action="store_true", help="print the requests; send nothing")
    parser.add_argument("--base-url", help="the server to sweep, in place of base_url in the config")
    args = parser.parse_args(argv)
    try:
        return sweep(args)
    except Unreachable as error:
        print(f"isolation_sweep: {error}. Start the server, or pass --base-url to point at where it runs.")
        return 0 if args.dry_run else 2


def sweep(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    base_url = cfg.get("base_url", "http://localhost:8000").rstrip("/")
    openapi = cfg.get("openapi", f"{base_url}/openapi.json")
    if args.base_url:
        if openapi.startswith(base_url + "/"):
            openapi = args.base_url.rstrip("/") + openapi[len(base_url) :]
        base_url = args.base_url.rstrip("/")
    host = urlsplit(base_url).hostname or ""
    if host not in LOCAL_HOSTS | set(cfg.get("allow_hosts", [])):
        raise SystemExit(f"{host} is not this machine; add it to allow_hosts only for a test server, never production")
    spec = load_openapi(openapi, config_path.parent)
    ids = {k: str(v) for k, v in cfg.get("ids", {}).items()}
    header = cfg.get("tenant_header", "")
    sides = {}
    for side in ("a", "b"):
        table = cfg.get(side, {})
        headers = {k: expand(str(v)) for k, v in table.get("headers", {}).items()}
        if header and table.get("tenant"):
            headers[header] = str(table["tenant"])
        sides[side] = headers

    plan = routes(spec, cfg.get("prefix", ""), cfg.get("skip", []))
    if args.only:
        plan = [r for r in plan if re.search(args.only, r[1])]
    tried = candidates = controls_failed = skipped = 0
    for method, path, operation in plan:
        if method in WRITES and not args.writes:
            continue
        url_path, missing = fill_path(path, ids)
        if missing:
            skipped += 1
            print(f"skip   {method.upper():6} {path}: no id for {', '.join(missing)} under [ids]")
            continue
        body = None
        if method in WRITES and method != "delete":
            content = operation.get("requestBody", {}).get("content", {}).get("application/json", {})
            body = sample(spec, content.get("schema", {}), ids) if content else {}
        url = base_url + url_path
        if args.dry_run:
            print(f"plan   {method.upper():6} {url_path}" + (f"  body {json.dumps(body)}" if body is not None else ""))
            tried += 1
            continue
        if method == "get":
            control, _ = send(method, url, sides["a"], None)
            if not 200 <= control < 300:
                controls_failed += 1
                print(f"ctrl   GET    {url_path}: A got {control}; fix the id under [ids] or A's token, or the route is not A's")
                continue
        status, text = send(method, url, sides["b"], body)
        tried += 1
        if 200 <= status < 300:
            candidates += 1
            print(f"CANDIDATE {method.upper():6} {url_path}: B got {status}: {text[:160]}")
        else:
            print(f"held   {method.upper():6} {url_path}: B got {status}")
    verb = "planned" if args.dry_run else "tried"
    print(f"\n{len(plan)} record routes; {tried} {verb}, {skipped} skipped (no id), {controls_failed} controls failed, {candidates} candidates")
    return 1 if candidates else 0


if __name__ == "__main__":
    sys.exit(main())
