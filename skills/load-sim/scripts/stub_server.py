#!/usr/bin/env python3
"""A stand-in API for proving the load harness before pointing it at a real app. Standard library only.

    python3 stub_server.py --port 8077            # serves until stopped
    python3 sim.py run --scenario load-scenario.toml --profile peak --rps 20 --duration 10

It answers the generic SaaS scenario (references/scenario.example.toml) the way a well-behaved
multi-tenant API should, so a run against it shows what a clean result looks like:

  * a request whose `Authorization: Bearer sim-<tenant>-<role>` names another tenant than its
    `X-Workspace-ID` header gets 403; a record of another tenant in the path gets 404;
  * a change with an `Idempotency-Key` seen before is answered again with `Idempotency-Replayed: true`;
  * --fail-rate makes that share of requests answer 500, and --delay-ms adds latency, to see a
    threshold fail on purpose.

Nothing here is used by any product. It listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYS: dict[str, tuple[int, bytes]] = {}
LOCK = threading.Lock()


def make_handler(fail_rate: float, delay_ms: float, tenant_header: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # quiet
            return

        def answer(self, status: int, payload: dict, extra: dict | None = None) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def handle_any(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            if delay_ms:
                time.sleep(delay_ms / 1000 * random.uniform(0.5, 1.5))
            if self.path == "/health":
                return self.answer(200, {"status": "ok"})
            if fail_rate and random.random() < fail_rate:
                return self.answer(500, {"code": "STUB_FAILURE"})
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            found = re.fullmatch(r"sim-([^-]+)-([a-z_]+)", token)
            if not found:
                return self.answer(401, {"code": "NOT_SIGNED_IN"})
            own, role = found.groups()
            header = self.headers.get(tenant_header)
            if header and header != own:
                return self.answer(403, {"code": "NOT_A_MEMBER"})
            path_tenant = re.search(r"/workspaces/([^/]+)/", self.path)
            if path_tenant and path_tenant.group(1) != own:
                return self.answer(404, {"code": "NOT_FOUND"})
            if role == "viewer" and self.command != "GET":
                return self.answer(403, {"code": "FORBIDDEN"})
            key = self.headers.get("Idempotency-Key")
            if key and self.command != "GET":
                scoped = f"{own}:{role}:{key}"
                with LOCK:
                    if scoped in KEYS:
                        status, kept = KEYS[scoped]
                        return self.answer(status, json.loads(kept), {"Idempotency-Replayed": "true"})
                    payload = {"id": random.randint(1, 10**9), "ok": True}
                    KEYS[scoped] = (201, json.dumps(payload).encode())
                return self.answer(201, payload)
            return self.answer(200 if self.command == "GET" else 201, {"ok": True, "tenant": own, "bytes": len(body)})

        do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = handle_any

    return Handler


def serve(port: int, fail_rate: float = 0.0, delay_ms: float = 0.0, tenant_header: str = "X-Workspace-ID") -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(fail_rate, delay_ms, tenant_header))
    server.daemon_threads = True
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8077)
    parser.add_argument("--fail-rate", type=float, default=0.0)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    parser.add_argument("--tenant-header", default="X-Workspace-ID")
    args = parser.parse_args()
    server = serve(args.port, args.fail_rate, args.delay_ms, args.tenant_header)
    print(f"stub API on http://127.0.0.1:{args.port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
