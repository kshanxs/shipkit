"""isolation_sweep.py against a tiny API with one leaky route: the plan, the candidates, the guards."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import isolation_sweep  # noqa: E402

OPENAPI = {
    "openapi": "3.1.0",
    "paths": {
        "/api/v1/projects/{project_id}": {"get": {}, "patch": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ProjectIn"}}}}}},
        "/api/v1/projects/{project_id}/tasks/{task_id}": {"get": {}},
        "/api/v1/invoices/{invoice_id}": {"get": {}},
        "/api/v1/admin/workspaces/{workspace_id}": {"get": {}},
        "/api/v1/me": {"get": {}},
    },
    "components": {"schemas": {"ProjectIn": {"type": "object", "required": ["name", "owner_id"], "properties": {"name": {"type": "string"}, "owner_id": {"type": "integer"}}}}},
}


class Api(BaseHTTPRequestHandler):
    """Tenant 1 owns everything. Invoices forget to check the tenant: the leak to find."""

    def log_message(self, *args) -> None:
        return

    def reply(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        tenant = self.headers.get("X-Workspace-ID")
        leaky = self.path.startswith("/api/v1/invoices/")
        status = 200 if (tenant == "1" or leaky or self.path == "/openapi.json") else 404
        body = json.dumps(OPENAPI if self.path == "/openapi.json" else {"ok": status == 200}).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_PATCH = reply


class SignedOut(BaseHTTPRequestHandler):
    """Every request, /openapi.json included, needs a login this sweep does not send."""

    def log_message(self, *args) -> None:
        return

    def do_GET(self) -> None:
        body = b'{"code": "NOT_SIGNED_IN"}'
        self.send_response(401)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Sweep(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.port = free_port()
        (self.dir / "openapi.json").write_text(json.dumps(OPENAPI))
        self.config = self.dir / "sweep.toml"
        self.config.write_text(
            f'openapi = "openapi.json"\nbase_url = "http://127.0.0.1:{self.port}"\nprefix = "/api/v1"\n'
            'skip = ["/api/v1/admin/*"]\ntenant_header = "X-Workspace-ID"\n'
            '[a]\ntenant = "1"\nheaders = { Authorization = "Bearer ${SWEEP_TEST_TOKEN}" }\n'
            '[b]\ntenant = "2"\n[ids]\nproject_id = "11"\ntask_id = "301"\ninvoice_id = "77"\n'
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = isolation_sweep.main(["--config", str(self.config), *argv])
            except SystemExit as stop:
                code, _ = 2, out.write(str(stop.code))
        return code, out.getvalue()

    @contextlib.contextmanager
    def api(self, handler: type[BaseHTTPRequestHandler] = Api):
        server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield
        finally:
            server.shutdown()
            server.server_close()

    def test_dry_run_lists_record_routes_only_and_skips_what_it_is_told(self) -> None:
        code, out = self.cli("--dry-run", "--writes")
        self.assertEqual(code, 0, out)
        self.assertIn("plan   GET    /api/v1/projects/11", out)
        self.assertIn('plan   PATCH  /api/v1/projects/11  body {"name": "sweep", "owner_id": "1"}', out)
        self.assertNotIn("/admin/", out)
        self.assertNotIn("/api/v1/me", out)

    def test_finds_the_leaky_route_and_holds_the_rest(self) -> None:
        with self.api():
            code, out = self.cli()
        self.assertEqual(code, 1, out)
        self.assertIn("CANDIDATE GET    /api/v1/invoices/77", out)
        self.assertIn("held   GET    /api/v1/projects/11: B got 404", out)
        self.assertIn("1 candidates", out)

    def test_a_route_without_an_id_is_skipped_with_the_reason(self) -> None:
        self.config.write_text(self.config.read_text().replace('task_id = "301"\n', ""))
        code, out = self.cli("--dry-run")
        self.assertIn("no id for task_id", out)

    def test_no_server_is_a_clear_message_not_a_traceback(self) -> None:
        url = f"http://127.0.0.1:{self.port}"
        self.config.write_text(self.config.read_text().replace('openapi = "openapi.json"', f'openapi = "{url}/openapi.json"'))
        code, out = self.cli("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"cannot reach {url}/openapi.json", out)
        self.assertIn("Start the server, or pass --base-url", out)
        self.assertNotIn("Traceback", out)
        code, out = self.cli()
        self.assertEqual(code, 2, out)
        self.assertIn(f"cannot reach {url}/openapi.json", out)

    def test_an_openapi_url_that_answers_401_is_one_clear_line_never_exit_1(self) -> None:
        url = f"http://127.0.0.1:{self.port}/openapi.json"
        self.config.write_text(self.config.read_text().replace('openapi = "openapi.json"', f'openapi = "{url}"'))
        with self.api(SignedOut):
            dry_code, dry = self.cli("--dry-run")
            real_code, real = self.cli()
        self.assertEqual(dry_code, 0, dry)
        self.assertEqual(real_code, 2, real)
        for out in (dry, real):
            self.assertEqual(len(out.strip().splitlines()), 1, out)
            self.assertIn(f"{url} answered HTTP 401", out)
            self.assertIn("needs a login", out)
            self.assertIn("--base-url", out)
            self.assertNotIn("Traceback", out)
            self.assertNotIn("HTTPError", out)

    def test_no_server_on_a_real_run_with_a_file_spec_stops_at_the_first_request(self) -> None:
        code, out = self.cli()
        self.assertEqual(code, 2, out)
        self.assertIn(f"cannot reach http://127.0.0.1:{self.port}/api/v1/", out)
        self.assertIn("pass --base-url", out)
        self.assertNotIn("ctrl", out)

    def test_base_url_points_the_sweep_and_the_openapi_url_at_another_port(self) -> None:
        down = free_port()
        self.config.write_text(
            self.config.read_text()
            .replace(f"127.0.0.1:{self.port}", f"127.0.0.1:{down}")
            .replace('openapi = "openapi.json"', f'openapi = "http://127.0.0.1:{down}/openapi.json"')
        )
        with self.api():
            code, out = self.cli("--base-url", f"http://127.0.0.1:{self.port}")
        self.assertIn("1 candidates", out)
        self.assertEqual(code, 1, out)

    def test_a_remote_target_is_refused(self) -> None:
        self.config.write_text(self.config.read_text().replace(f"http://127.0.0.1:{self.port}", "https://api.example.com"))
        code, out = self.cli("--dry-run")
        self.assertNotEqual(code, 0)
        self.assertIn("is not this machine", out)


if __name__ == "__main__":
    unittest.main()
