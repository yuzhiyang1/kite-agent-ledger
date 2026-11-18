"""验证 CLI 的进程边界、标准输入和退出状态。"""

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_command_ingests_http_response_and_only_retains_audit_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder, "ledger.sqlite3"))
            prefix = [sys.executable, "-m", "kite_agent_ledger.cli", "--db", db]
            payer = "0x" + "1" * 40
            tx_hash = "0x" + "a" * 64
            subprocess.run(
                [*prefix, "open", "--run-id", "run-1", "--call-id", "call-1", "--service", "fixture-api",
                 "--payer", payer, "--recipient", "0x" + "2" * 40, "--amount", "100"],
                capture_output=True, timeout=15, check=True,
            )
            response = base64.b64encode(json.dumps({
                "success": True, "network": "eip155:2368", "payer": payer, "transaction": tx_hash,
            }).encode())
            raw = b"HTTP/2 200\r\nSet-Cookie: audit-cookie-marker\r\nPAYMENT-RESPONSE: " + response + b"\r\n\r\n"
            captured = subprocess.run(
                [*prefix, "capture", "call-1", "--http-headers"],
                input=raw, capture_output=True, timeout=15, check=True,
            )
            row = json.loads(captured.stdout)
            self.assertEqual((row["http_status"], row["tx_hash"], row["tx_source"]), (200, tx_hash, "payment_response"))
            self.assertNotIn(b"audit-cookie-marker", Path(db).read_bytes())
            self.assertNotIn(response, Path(db).read_bytes())

    def test_timeout_remains_unknown_and_report_is_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder, "ledger.sqlite3"))

            def run(*args, data=None):
                return subprocess.run(
                    [sys.executable, "-m", "kite_agent_ledger.cli", "--db", db, *args],
                    input=data, text=True, capture_output=True, timeout=15, check=False,
                )

            opened = run(
                "open", "--run-id", "run-1", "--call-id", "call-1", "--service", "fixture-api",
                "--payer", "0x" + "1" * 40, "--recipient", "0x" + "2" * 40, "--amount", "100",
            )
            self.assertEqual(opened.returncode, 0, opened.stderr)
            capture = run("capture", "call-1", data='{"http_status":null,"payment_response":null}')
            self.assertEqual(capture.returncode, 0, capture.stderr)
            reconcile = run("reconcile", "call-1")
            self.assertEqual(reconcile.returncode, 3, reconcile.stderr)
            self.assertEqual(json.loads(reconcile.stdout)["reason"], "no_transaction_hash")
            result = run("report", "run-1")
            self.assertEqual(result.returncode, 0, result.stderr)
            row, = json.loads(result.stdout)["calls"]
            self.assertEqual(row["payment_status"], "no_http_response")
            self.assertEqual(row["chain_status"], "unknown")
            self.assertIsNone(row["tx_hash"])

    def test_unrecognized_capture_input_cannot_enter_the_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-m", "kite_agent_ledger.cli", "--db", str(Path(folder, "invalid.db")),
                 "capture", "call-1"],
                input='{"http_status":200,"payment_response":null,"body":"sensitive"}',
                capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("sensitive", result.stderr)
