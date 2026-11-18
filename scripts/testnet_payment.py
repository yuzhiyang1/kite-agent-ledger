"""用临时钱包向官方测试接口支付 0.1 pieUSD，并通过账本核验链上结果。"""

import argparse
import base64
import json
import secrets
import subprocess
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from uuid import uuid4

from kite_agent_ledger.chain import Check, KiteRpc, NoRedirect, verify
from kite_agent_ledger.model import NETWORK, RPC_URL, TOKEN, Intent, unique_object
from kite_agent_ledger.store import Ledger

MERCHANT = "https://passport.dev.gokite.ai/x402/test"
BACKEND = "https://passport.dev.gokite.ai"
RECIPIENT = "0x677a3c93e717ccaa73f19de98c1d715a1768c56e"
AMOUNT = "100000000000000000"


def payment_terms(challenge: dict) -> dict:
    """在创建钱包和签名前固定测试网、代币、收款方及单次付款金额。"""
    if not isinstance(challenge, dict):
        raise ValueError("Payment challenge must be a JSON object")
    accepts = challenge.get("accepts")
    if challenge.get("x402Version") != 2 or not isinstance(accepts, list) or len(accepts) != 1:
        raise ValueError("Expected one x402 v2 testnet payment option")
    terms = accepts[0]
    if not isinstance(terms, dict) or (
        terms.get("scheme") != "exact"
        or terms.get("network") != NETWORK
        or str(terms.get("asset")).lower() != TOKEN
        or str(terms.get("payTo")).lower() != RECIPIENT
        or terms.get("amount") != AMOUNT
        or terms.get("extra") != {"name": "pieUSD", "version": "1"}
    ):
        raise ValueError("Quote differs from the pinned 0.1 pieUSD testnet payment")
    return terms


def kpass(executable: str, *args: str) -> dict:
    completed = subprocess.run(
        [executable, *args, "--base-url", BACKEND, "--output", "json", "--no-interactive"],
        capture_output=True, text=True, timeout=30,
    )
    try:
        response = json.loads(completed.stdout, object_pairs_hook=unique_object)
    except ValueError as exc:
        raise ValueError("Kite CLI did not return one JSON result") from exc
    if completed.returncode != 0 or not isinstance(response, dict) or response.get("status") != "success":
        raise ValueError("Kite CLI command failed; check dev login and sandbox state")
    return response


def run(executable: str, db: str) -> dict:
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    rpc = KiteRpc(RPC_URL)
    if int(rpc.call("eth_chainId", []), 16) != 2368:
        raise ValueError("RPC is not Kite Testnet")
    mode = kpass(executable, "sandbox", "status")
    if mode.get("sandbox") is not True or mode.get("mode") != "sandbox":
        raise ValueError("Kite CLI must be in sandbox mode")
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(MERCHANT, method="GET"), timeout=15):
            raise ValueError("Expected an x402 payment challenge")
    except HTTPError as response:
        if response.code != 402:
            raise ValueError("Official test endpoint did not return 402") from response
        raw = response.headers.get("PAYMENT-REQUIRED", "")
        if len(raw) > 16384:
            raise ValueError("Payment challenge exceeds the input limit")
        challenge = json.loads(base64.b64decode(raw, validate=True), object_pairs_hook=unique_object)
    terms = payment_terms(challenge)

    # 私钥仅驻留在此进程的内存中，付款凭证和日志只保存公开元数据。
    account = Account.create()
    funding = kpass(executable, "faucet", "drop", "--recipient", account.address, "--token", "pieUSD")
    if funding.get("chain_id") != 2368:
        raise ValueError("Faucet reported a different chain")

    def balance() -> int:
        result = rpc.call("eth_call", [{
            "to": TOKEN, "data": "0x70a08231" + "0" * 24 + account.address[2:].lower(),
        }, "latest"])
        return int(result, 16)

    before = balance()
    if before < int(AMOUNT):
        raise ValueError("Faucet transfer has not funded the test wallet")
    authorization = {
        "from": account.address, "to": terms["payTo"], "value": AMOUNT,
        "validAfter": "0", "validBefore": str(int(time.time()) + 60),
        "nonce": "0x" + secrets.token_hex(32),
    }
    domain = {"name": "pieUSD", "version": "1", "chainId": 2368, "verifyingContract": TOKEN}
    types = {"TransferWithAuthorization": [
        {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
    ]}
    message = {
        name: int(value) if name in {"value", "validAfter", "validBefore"} else value
        for name, value in authorization.items()
    }
    signable = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    chain_domain = rpc.call("eth_call", [{"to": TOKEN, "data": "0x3644e515"}, "latest"])
    if "0x" + signable.header.hex() != chain_domain.lower():
        raise ValueError("EIP-712 domain differs from the testnet token contract")
    payload = {
        "x402Version": 2, "resource": challenge.get("resource"), "accepted": terms,
        "payload": {
            "authorization": authorization,
            "signature": "0x" + bytes(account.sign_message(signable).signature).hex(),
        },
    }
    payment_header = base64.b64encode(json.dumps(payload).encode()).decode()
    intent = Intent(
        "paid-" + uuid4().hex, "testnet-validation", "kite-official-test",
        account.address, RECIPIENT, AMOUNT,
    )
    with closing(Ledger(db)) as ledger:
        ledger.open_call(intent)
        response = None
        try:
            response = opener.open(Request(
                MERCHANT, headers={"PAYMENT-SIGNATURE": payment_header}, method="GET",
            ), timeout=90)
        except HTTPError as failed:
            response = failed
        except (OSError, URLError):
            pass
        status, payment_response = None, None
        if response is not None:
            status = response.status
            payment_response = response.headers.get("PAYMENT-RESPONSE")
            response.close()
        call = ledger.capture(intent.call_id, status, payment_response)
        check = verify(rpc, intent, call["tx_hash"]) if call["tx_hash"] else Check("unknown", "no_transaction_hash")
        ledger.save_check(intent.call_id, call["tx_hash"], check)
        return {
            "call": call, "checks": ledger.history(intent.call_id),
            "balance_before_atomic": str(before), "balance_after_atomic": str(balance()),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kpass", default="kpass", help="official Kite CLI executable")
    parser.add_argument("--db", default="kite-testnet-validation.sqlite3")
    args = parser.parse_args()
    result = run(args.kpass, args.db)
    print(json.dumps(result, indent=2))
    check = result["checks"][-1]
    deducted = int(result["balance_before_atomic"]) - int(result["balance_after_atomic"])
    return 0 if check["status"] == "confirmed" and result["call"]["http_status"] == 200 and deducted == int(AMOUNT) else 3


if __name__ == "__main__":
    raise SystemExit(main())
