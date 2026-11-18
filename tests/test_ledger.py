"""验证凭证边界、链上判定和 SQLite 调用记录。"""

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier

from kite_agent_ledger.chain import Check, RpcUnavailable, verify
from kite_agent_ledger.model import NETWORK, TOKEN, TRANSFER_TOPIC, Intent, parse_reply
from kite_agent_ledger.store import Conflict, Ledger

PAYER = "0x" + "1" * 40
RECIPIENT = "0x" + "2" * 40
TX = "0x" + "a" * 64
BLOCK_HASH = "0x" + "b" * 64
INTENT = Intent("tool-1", "agent-run-1", "scrape-api", PAYER, RECIPIENT, "100")


def header(**overrides):
    fields = {"success": True, "transaction": TX, "network": NETWORK, "payer": PAYER}
    return base64.b64encode(json.dumps(fields | overrides).encode()).decode()


def transfer(amount=100, address=TOKEN):
    return {
        "address": address,
        "topics": [TRANSFER_TOPIC, "0x" + "0" * 24 + PAYER[2:], "0x" + "0" * 24 + RECIPIENT[2:]],
        "data": f"0x{amount:064x}",
        "logIndex": "0x2",
        "removed": False,
    }


def receipt(**overrides):
    return {
        "transactionHash": TX, "blockNumber": "0x11", "blockHash": BLOCK_HASH,
        "status": "0x1", "logs": [transfer()],
    } | overrides


class FakeRpc:
    def __init__(self, result, chain="0x940"):
        self.result = result
        self.chain = chain
        self.methods = []

    def call(self, method, params):
        self.methods.append((method, params))
        if method == "eth_chainId":
            return self.chain
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ReplyTests(unittest.TestCase):
    def test_valid_header_distinguishes_pending_and_rejected(self):
        self.assertEqual(parse_reply(INTENT, 200, header()).tx_hash, TX)
        pending = header(success=False, errorReason="settlement_pending")
        self.assertEqual(parse_reply(INTENT, 402, pending).payment_status, "reported_pending")
        denied = header(success=False, transaction="", errorReason="insufficient_funds")
        self.assertIsNone(parse_reply(INTENT, 402, denied).tx_hash)
        self.assertEqual(parse_reply(INTENT, 402, denied).payment_status, "reported_failure")

    def test_rejects_other_network_or_payer(self):
        self.assertEqual(parse_reply(INTENT, 200, header(network="eip155:2366")).payment_status, "wrong_network")
        self.assertEqual(parse_reply(INTENT, 200, header(payer=RECIPIENT)).payment_status, "wrong_payer")
        self.assertIsNone(parse_reply(INTENT, 200, header(payer=RECIPIENT)).tx_hash)

    def test_missing_and_malformed_evidence(self):
        cases = [
            "%%%!", "A" * 8193, header(success="true"), header(transaction=""),
            header(success=False, transaction="", errorReason="settlement_pending"),
            base64.b64encode(b'{"success":true,"success":false}').decode(),
        ]
        for value in cases:
            with self.subTest(value=value[:12]):
                self.assertEqual(parse_reply(INTENT, 200, value).payment_status, "invalid_payment_response")
        self.assertEqual(parse_reply(INTENT, None, None).payment_status, "no_http_response")
        self.assertEqual(parse_reply(INTENT, 504, None).payment_status, "no_payment_response")
        with self.assertRaises(ValueError):
            parse_reply(INTENT, None, header())

    def test_validates_amount_and_identifiers(self):
        for amount in ("0", "-100", "1.0", "0100", str(1 << 256), 100):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                replace(INTENT, amount=amount)
        with self.assertRaises(ValueError):
            replace(INTENT, service="https://example.test/path?token=secret")


class ChainTests(unittest.TestCase):
    def test_confirms_exact_transfer_and_checks_network(self):
        rpc = FakeRpc(receipt())
        self.assertEqual(verify(rpc, INTENT, TX), Check("confirmed", "exact_transfer", 17, 2, BLOCK_HASH))
        self.assertEqual(rpc.methods, [("eth_chainId", []), ("eth_getTransactionReceipt", [TX])])

    def test_disagreement_is_not_a_confirmation(self):
        cases = [
            (receipt(logs=[transfer(99)]), "mismatch", "wrong_amount"),
            (receipt(logs=[transfer(address=RECIPIENT)]), "mismatch", "expected_transfer_missing"),
            (receipt(logs=[transfer(), transfer(99)]), "mismatch", "ambiguous_transfer"),
            (receipt(logs=[transfer() | {"removed": True}]), "unknown", "invalid_rpc_evidence"),
            (receipt(status="0x0"), "reverted", "transaction_reverted"),
            (receipt(transactionHash=BLOCK_HASH), "unknown", "rpc_wrong_transaction"),
            (None, "unknown", "receipt_not_found"),
            (RpcUnavailable(), "unknown", "rpc_unavailable"),
        ]
        for evidence, status, reason in cases:
            with self.subTest(reason=reason):
                result = verify(FakeRpc(evidence), INTENT, TX)
                self.assertEqual((result.status, result.reason), (status, reason))
        rpc = FakeRpc(receipt(), chain="0x93e")
        self.assertEqual(verify(rpc, INTENT, TX).reason, "rpc_wrong_chain")
        self.assertEqual(len(rpc.methods), 1)


class LedgerTests(unittest.TestCase):
    def test_observations_are_idempotent_and_chain_checks_are_append_only(self):
        with closing(Ledger(":memory:")) as ledger:
            ledger.open_call(INTENT)
            ledger.open_call(INTENT)
            with self.assertRaises(Conflict):
                ledger.open_call(replace(INTENT, amount="101"))
            self.assertEqual(ledger.capture(INTENT.call_id, 504, None)["payment_status"], "no_payment_response")
            ledger.attach(INTENT.call_id, TX)
            self.assertEqual(ledger.capture(INTENT.call_id, 504, None)["tx_source"], "manual")
            with self.assertRaises(Conflict):
                ledger.capture(INTENT.call_id, 200, header())
            ledger.save_check(INTENT.call_id, TX, Check("confirmed", "exact_transfer", 17, 2, BLOCK_HASH))
            ledger.save_check(INTENT.call_id, TX, Check("unknown", "rpc_unavailable"))
            row, = ledger.report(INTENT.run_id)
            self.assertEqual((row["http_status"], row["chain_status"]), (504, "unknown"))
            self.assertEqual([x["status"] for x in ledger.history(INTENT.call_id)], ["confirmed", "unknown"])

    def test_transaction_cannot_be_claimed_by_two_concurrent_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder, "ledger.sqlite3"))
            with closing(Ledger(path)) as ledger:
                ledger.open_call(INTENT)
                ledger.open_call(replace(INTENT, call_id="tool-2"))
            ready = Barrier(2, timeout=5)

            def capture(call_id):
                with closing(Ledger(path)) as ledger:
                    ready.wait()
                    try:
                        ledger.capture(call_id, 200, header())
                        return True
                    except Conflict:
                        return False

            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(capture, ["tool-1", "tool-2"])), [False, True])
            with closing(Ledger(path)) as ledger:
                self.assertEqual(sum(row["observed_at"] is not None for row in ledger.report(INTENT.run_id)), 1)


if __name__ == "__main__":
    unittest.main()
