#!/usr/bin/env python3
"""
adversarial_runner.py - Lightweight Adversarial & Concurrency Test Runner

Runs automated adversarial input fuzzing and concurrent race condition attacks
against HTTP endpoints using Python standard library (zero external dependencies).

Only against this machine (localhost, 127.0.0.1) unless --allow-host names the host: the test
server, say. Never production. Pass the sign-in and the tenant with --header:
    --header "Authorization: Bearer <token>" --header "X-Workspace-ID: 1"
Mint tokens on your local or test stack; never paste production credentials.

Usage:
    python3 adversarial_runner.py --url http://localhost:8000/api/v1/health
    python3 adversarial_runner.py --url http://localhost:8000/api/v1/projects --method POST --payload '{"name": "Launch"}' --fuzz
    python3 adversarial_runner.py --url http://localhost:8000/api/v1/invites --method POST --concurrency 20 --requests 100
"""

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

STANDARD_FUZZ_VECTORS = [
    ("Empty String", ""),
    ("Whitespace Only", "     "),
    ("Extreme Long String (100k)", "A" * 100_000),
    ("Null Byte Injection", "test\x00malicious"),
    ("Special Metacharacters", "<script>alert(1)</script>' OR '1'='1"),
    ("Negative Integer", -1),
    ("Extreme Large Integer (64-bit max)", 9223372036854775807),
    ("Zero Value", 0),
    ("Deeply Nested Dict", {"l1": {"l2": {"l3": {"l4": "deep"}}}}),
]


def send_request(url: str, method: str, headers: dict, data: bytes | None) -> tuple[int, float, str]:
    start = time.perf_counter()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = (time.perf_counter() - start) * 1000
            return resp.status, elapsed, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return e.code, elapsed, e.read().decode(errors="replace")
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return 0, elapsed, str(e)


def run_fuzz_battery(url: str, method: str, headers: dict, base_payload: dict):
    print(f"\n[*] Starting Input Fuzzing Battery against {method} {url}...")
    failures = 0
    passes = 0

    if not base_payload:
        print("[!] No base payload provided for fuzzing. Testing raw body vectors...")
        for name, vector in STANDARD_FUZZ_VECTORS:
            body = json.dumps(vector).encode("utf-8")
            status, latency, _resp = send_request(url, method, headers, body)
            # A 500 status code indicates uncaught crash / failure
            if status >= 500:
                print(f"  FAIL Vector '{name}' caused HTTP {status} (Uncaught Server Error) in {latency:.1f}ms")
                failures += 1
            else:
                print(f"  pass Vector '{name}' safely handled with HTTP {status} in {latency:.1f}ms")
                passes += 1
        return failures

    for field in list(base_payload.keys()):
        print(f"\n--- Fuzzing field: '{field}' ---")
        for name, vector in STANDARD_FUZZ_VECTORS:
            mutated = dict(base_payload)
            mutated[field] = vector
            body = json.dumps(mutated).encode("utf-8")
            status, latency, _resp = send_request(url, method, headers, body)

            if status >= 500:
                print(f"  FAIL Field '{field}' with '{name}' caused HTTP {status} in {latency:.1f}ms")
                failures += 1
            else:
                print(f"  pass Field '{field}' with '{name}' returned HTTP {status} ({latency:.1f}ms)")
                passes += 1

    print(f"\n[+] Fuzzing Complete: {passes} handled safely, {failures} uncaught server errors (5xx).")
    return failures


def run_concurrency_load(url: str, method: str, headers: dict, data: bytes | None, concurrency: int, total: int):
    print("\n[*] Starting Concurrency & Race Condition Test:")
    print(f"    Target: {method} {url}")
    print(f"    Total Requests: {total} | Concurrent Workers: {concurrency}")

    latencies = []
    status_counts = {}

    def worker(_):
        status, elapsed, _ = send_request(url, method, headers, data)
        return status, elapsed

    start_all = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker, i) for i in range(total)]
        for f in concurrent.futures.as_completed(futures):
            status, elapsed = f.result()
            latencies.append(elapsed)
            status_counts[status] = status_counts.get(status, 0) + 1

    total_time = time.perf_counter() - start_all
    latencies.sort()

    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    rps = total / total_time if total_time > 0 else 0

    print("\n--- Results Summary ---")
    print(f"Total Time:      {total_time:.2f}s ({rps:.1f} req/s)")
    print(f"Status Codes:    {status_counts}")
    print(f"Latency p50:     {p50:.2f}ms")
    print(f"Latency p95:     {p95:.2f}ms")
    print(f"Latency p99:     {p99:.2f}ms")
    print(f"Max Latency:     {max(latencies):.2f}ms")

    server_errors = sum(count for status, count in status_counts.items() if status >= 500 or status == 0)
    if server_errors > 0:
        print(f"ALERT: {server_errors} requests resulted in 5xx server errors or connection drops!")
        return 1
    else:
        print("CLEAN: 0 server errors detected under concurrency.")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Adversarial & Concurrency Test Runner")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--method", default="GET", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    parser.add_argument("--payload", default="", help="JSON string payload")
    parser.add_argument("--header", action="append", default=[], help="Header in 'Key: Value' format")
    parser.add_argument("--fuzz", action="store_true", help="Run input fuzzing battery")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent worker count")
    parser.add_argument("--requests", type=int, default=1, help="Total requests for concurrency test")

    parser.add_argument("--allow-host", action="append", default=[], help="A host other than this machine to allow")
    parser.add_argument("--max-requests", type=int, default=2000, help="Refuse a run larger than this")

    args = parser.parse_args()

    host = urlsplit(args.url).hostname or ""
    if host not in LOCAL_HOSTS | set(args.allow_host):
        print(f"[!] {host} is not this machine. Add --allow-host {host} if it is a server you may test (never production).")
        sys.exit(2)
    if args.requests > args.max_requests:
        print(f"[!] {args.requests} requests is more than --max-requests ({args.max_requests}); raise it on purpose.")
        sys.exit(2)

    headers = {"Content-Type": "application/json"}
    for h in args.header:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    base_payload = None
    data = None
    if args.payload:
        try:
            base_payload = json.loads(args.payload)
            data = args.payload.encode("utf-8")
        except json.JSONDecodeError:
            print("[!] Error: --payload must be valid JSON")
            sys.exit(1)

    exit_code = 0
    if args.fuzz:
        fuzz_failures = run_fuzz_battery(args.url, args.method, headers, base_payload or {})
        if fuzz_failures > 0:
            exit_code = 1

    if args.requests > 1 or args.concurrency > 1:
        load_failures = run_concurrency_load(args.url, args.method, headers, data, args.concurrency, args.requests)
        if load_failures > 0:
            exit_code = 1

    if not args.fuzz and args.requests == 1 and args.concurrency == 1:
        # Single probe
        status, latency, body = send_request(args.url, args.method, headers, data)
        print(f"HTTP {status} ({latency:.1f}ms):\n{body[:500]}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
