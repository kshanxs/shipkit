"""sim.py against stub_server.py: the plan, a short real run, the thresholds, the guards and the demand estimate."""

from __future__ import annotations

import contextlib
import io
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import sim  # noqa: E402
import stub_server  # noqa: E402

EXAMPLE = SKILL / "references" / "scenario.example.toml"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Harness(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.port = free_port()
        self.scenario = self.dir / "load-scenario.toml"
        text = EXAMPLE.read_text().replace("http://localhost:8077", f"http://127.0.0.1:{self.port}")
        self.scenario.write_text(text)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = sim.main(list(argv))
            except SystemExit as stop:
                code = stop.code if isinstance(stop.code, int) else 2
                out.write(str(stop.code))
        return code, out.getvalue()

    @contextlib.contextmanager
    def stub(self, **options):
        server = stub_server.serve(self.port, **options)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()

    def run_sim(self, profile: str, *extra: str) -> tuple[int, str, Path]:
        out = self.dir / f"out-{profile}"
        code, text = self.cli("run", "--scenario", str(self.scenario), "--profile", profile, "--rps", "60", "--duration", "1.5", "--out", str(out), *extra)
        return code, text, out


class Plan(Harness):
    def test_plan_names_calls_and_sends_nothing(self) -> None:
        code, out = self.cli("plan", "--scenario", str(self.scenario), "--profile", "peak", "--count", "12", "--verbose")
        self.assertEqual(code, 0, out)
        self.assertIn("12 calls planned", out)
        self.assertIn("/api/v1/workspaces/", out)
        self.assertNotIn("{tenant}", out)
        self.assertIn("<redacted>", out)

    def test_a_profile_naming_an_unknown_request_is_refused(self) -> None:
        self.scenario.write_text(self.scenario.read_text().replace('"admin.members" = 0.5', '"admin.gone" = 0.5'))
        code, out = self.cli("plan", "--scenario", str(self.scenario), "--profile", "peak")
        self.assertNotEqual(code, 0)
        self.assertIn("admin.gone", out)


class Run(Harness):
    def test_a_clean_run_passes_its_thresholds_and_writes_its_files(self) -> None:
        with self.stub():
            code, out, folder = self.run_sim("peak")
        self.assertEqual(code, 0, out)
        summary = (folder / "summary.md").read_text()
        self.assertIn("| Threshold | Measured | Result |", summary)
        self.assertNotIn("FAIL", summary)
        self.assertIn("member.create_task.replay", summary)
        rows = (folder / "requests.csv").read_text().splitlines()
        self.assertGreater(len(rows), 10)
        self.assertNotIn("NOT-REPLAYED", "\n".join(rows))

    def test_the_abuse_mix_counts_leaks_and_a_safe_api_has_none(self) -> None:
        with self.stub():
            code, out, folder = self.run_sim("abuse")
        self.assertEqual(code, 0, out)
        self.assertIn("0 cross-tenant requests answered 2xx", (folder / "summary.md").read_text())

    def test_a_failing_server_fails_the_error_threshold(self) -> None:
        with self.stub(fail_rate=0.5):
            code, out, folder = self.run_sim("mixed")
        self.assertEqual(code, 1)
        self.assertIn("| error_rate <= 0.01 |", (folder / "summary.md").read_text())
        self.assertIn("FAIL", (folder / "summary.md").read_text())

    def test_a_remote_host_is_refused(self) -> None:
        self.scenario.write_text(self.scenario.read_text().replace(f"http://127.0.0.1:{self.port}", "https://api.example.com"))
        code, out, _ = self.run_sim("peak")
        self.assertNotEqual(code, 0)
        self.assertIn("is not this machine", out)


class Demand(Harness):
    def test_demand_multiplies_out_the_population(self) -> None:
        code, out = self.cli("demand", "--scenario", str(self.scenario), "--tenants", "500")
        self.assertEqual(code, 0, out)
        self.assertIn("Estimated demand for 500 tenants", out)
        self.assertIn("plan for", out)

    def test_init_writes_the_example_once(self) -> None:
        target = self.dir / "new.toml"
        self.assertEqual(self.cli("init", "--scenario", str(target))[0], 0)
        self.assertEqual(target.read_text(), EXAMPLE.read_text())
        self.assertIn("nothing written", self.cli("init", "--scenario", str(target))[1])


class Placeholders(unittest.TestCase):
    def test_fill_replaces_every_placeholder(self) -> None:
        import random

        filled = sim.fill({"a": "/t/{tenant}/{rand:1-1}/{n}", "b": ["{other_tenant}"]}, {"tenant": "7", "other_tenant": "9", "n": "3"}, random.Random(1))
        self.assertEqual(filled, {"a": "/t/7/1/3", "b": ["9"]})

    def test_uuid7_carries_its_time(self) -> None:
        value = sim.uuid7(1_700_000_000.0)
        self.assertEqual(value[14], "7")
        self.assertEqual(int(value.replace("-", "")[:12], 16), 1_700_000_000_000)


if __name__ == "__main__":
    unittest.main()
