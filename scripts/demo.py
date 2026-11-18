"""可复现的离线超时演示和已公开的 Kite 测试网历史转账回查。"""

import argparse
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path

from kite_agent_ledger.chain import Check, KiteRpc, verify
from kite_agent_ledger.model import RPC_URL, Intent
from kite_agent_ledger.store import Ledger

HISTORICAL_TX = "0x51ba634e11cfa21a015e0e8f18d0aac341083e2f67acc491653a12be02a68544"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="query Kite Testnet for a historical transfer")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder, closing(Ledger(str(Path(folder, "demo.sqlite3")))) as ledger:
        timeout = Intent(
            "simulated-timeout", "demo", "simulated-service", "0x" + "1" * 40, "0x" + "2" * 40, "100",
        )
        ledger.open_call(timeout)
        ledger.capture(timeout.call_id, None, None)
        ledger.save_check(timeout.call_id, None, Check("unknown", "no_transaction_hash"))
        output = {"simulated_timeout": ledger.report(timeout.run_id)[0]}
        status = 0

        if args.live:
            # 行为记录是合成的，交易与链上返回是真实公开数据。
            historical = Intent(
                "historical-transfer", "live-readonly", "public-transfer",
                "0x14433179e3450a5a4d5a7e0a6e81627e4e6421a8",
                "0x13a95beb284f1c18de85e4a238366f3c4d9721f9",
                "97900000000000000",
            )
            ledger.open_call(historical)
            ledger.capture(historical.call_id, None, None)
            ledger.attach(historical.call_id, HISTORICAL_TX)
            outcome = verify(KiteRpc(os.getenv("KITE_LEDGER_RPC_URL", RPC_URL)), historical, HISTORICAL_TX)
            ledger.save_check(historical.call_id, HISTORICAL_TX, outcome)
            output["live_historical_transfer"] = ledger.report(historical.run_id)[0]
            status = 0 if outcome.status == "confirmed" else 3
        print(json.dumps(output, indent=2))
        return status


if __name__ == "__main__":
    raise SystemExit(main())
