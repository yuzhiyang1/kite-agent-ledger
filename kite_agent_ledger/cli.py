"""命令行入口，标准输出使用 JSON 方便 Agent 或流水线消费。"""

import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing

from .chain import Check, KiteRpc, verify
from .http_capture import MAX_HEADER_DUMP, parse_http_headers
from .model import NETWORK, RPC_URL, TOKEN, Intent, unique_object
from .store import Conflict, Ledger


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Audit agent HTTP payments on Kite Testnet")
    cli.add_argument("--db", default=os.getenv("KITE_LEDGER_DB", "kite-ledger.sqlite3"))
    commands = cli.add_subparsers(dest="command", required=True)

    open_call = commands.add_parser("open", help="record the expected payment before calling the API")
    for field in ("run-id", "call-id", "service", "payer", "recipient", "amount"):
        open_call.add_argument(f"--{field}", required=True)

    capture = commands.add_parser("capture", help="read HTTP status and PAYMENT-RESPONSE from stdin")
    capture.add_argument("call_id")
    capture.add_argument("--http-headers", action="store_true", help="read a raw HTTP response header dump instead of JSON")

    attach = commands.add_parser("attach", help="attach a separately obtained transaction hash")
    attach.add_argument("call_id")
    attach.add_argument("tx_hash")

    reconcile = commands.add_parser("reconcile", help="verify the attached transaction on Kite Testnet")
    reconcile.add_argument("call_id")
    reconcile.add_argument("--rpc-url", default=os.getenv("KITE_LEDGER_RPC_URL", RPC_URL))

    report = commands.add_parser("report", help="report all calls for one agent run")
    report.add_argument("run_id")

    history = commands.add_parser("history", help="show all reconciliation observations for a call")
    history.add_argument("call_id")
    return cli


def read_capture() -> dict:
    body = sys.stdin.buffer.read(16385)
    if len(body) > 16384:
        raise ValueError("capture JSON exceeds 16 KiB")
    try:
        payload = json.loads(body, object_pairs_hook=unique_object)
    except (ValueError, RecursionError) as exc:
        raise ValueError("capture must contain a valid JSON object") from exc
    if not isinstance(payload, dict) or set(payload) != {"http_status", "payment_response"}:
        raise ValueError("capture fields must be http_status and payment_response")
    return payload


def execute(args: argparse.Namespace, ledger: Ledger) -> tuple[object, int]:
    if args.command == "open":
        return ledger.open_call(Intent(
            args.call_id, args.run_id, args.service, args.payer, args.recipient, args.amount,
        )), 0
    if args.command == "capture":
        if args.http_headers:
            status, payment_response = parse_http_headers(sys.stdin.buffer.read(MAX_HEADER_DUMP + 1))
            return ledger.capture(args.call_id, status, payment_response), 0
        return ledger.capture(args.call_id, **read_capture()), 0
    if args.command == "attach":
        return ledger.attach(args.call_id, args.tx_hash), 0
    if args.command == "history":
        return {"call_id": args.call_id, "checks": ledger.history(args.call_id)}, 0
    if args.command == "report":
        return {"network": NETWORK, "asset": TOKEN, "run_id": args.run_id, "calls": ledger.report(args.run_id)}, 0

    call = ledger.get_call(args.call_id)
    tx_hash = call["tx_hash"]
    if tx_hash is None:
        check = Check("unknown", "no_transaction_hash")
    else:
        check = verify(KiteRpc(args.rpc_url), ledger.intent(call), tx_hash)
    return ledger.save_check(args.call_id, tx_hash, check), 0 if check.status == "confirmed" else 3


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        with closing(Ledger(args.db)) as ledger:
            result, code = execute(args, ledger)
    except Conflict as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 4
    except (sqlite3.Error, OSError):
        print(json.dumps({"error": "local storage or input unavailable"}), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
