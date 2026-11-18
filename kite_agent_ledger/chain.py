"""通过 Kite 测试网 RPC 只读验证 pieUSD Transfer 事件。"""

import json
import re
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .model import CHAIN_ID, TOKEN, TRANSFER_TOPIC, Intent, hex_bytes, unique_object


class NoRedirect(HTTPRedirectHandler):
    """RPC 配置中的目标固定，拒绝跳到另一个站点。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RpcUnavailable(Exception):
    """RPC 暂时不可用或返回了无法核验的数据。"""


class KiteRpc:
    def __init__(self, url: str) -> None:
        endpoint = urlsplit(url)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.fragment
        ):
            raise ValueError("RPC endpoint must be an HTTPS URL without embedded credentials")
        self.url = url
        self.opener = build_opener(NoRedirect())

    def call(self, method: str, params: list[str]) -> object:
        query = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        request = Request(
            self.url, json.dumps(query).encode(), {"Content-Type": "application/json"}
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError("oversized RPC response")
            message = json.loads(body, object_pairs_hook=unique_object)
            if (
                not isinstance(message, dict)
                or message.get("jsonrpc") != "2.0"
                or type(message.get("id")) is not int
                or message["id"] != 1
                or "error" in message
            ):
                raise ValueError("invalid RPC response")
            return message["result"]
        except (OSError, URLError, HTTPException, ValueError, KeyError, RecursionError) as exc:
            # 上游错误和 URL 可能含访问凭据，外部只得到稳定的错误类别。
            raise RpcUnavailable("Kite RPC request failed") from exc


@dataclass(frozen=True)
class Check:
    status: str
    reason: str
    block: int | None = None
    log_index: int | None = None
    block_hash: str | None = None


def quantity(value: object) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})", value):
        raise ValueError("invalid RPC quantity")
    return int(value, 16)


def verify(rpc: KiteRpc, intent: Intent, tx_hash: str) -> Check:
    """核验交易成功且恰有一条匹配转账，区分证据缺失与链上不匹配。"""
    try:
        if quantity(rpc.call("eth_chainId", [])) != CHAIN_ID:
            return Check("unknown", "rpc_wrong_chain")
        receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            return Check("unknown", "receipt_not_found")
        if not isinstance(receipt, dict):
            raise ValueError("receipt must be a JSON object")
        if hex_bytes(receipt.get("transactionHash"), 32, "receipt transaction") != tx_hash:
            return Check("unknown", "rpc_wrong_transaction")
        block = quantity(receipt.get("blockNumber"))
        if block > (1 << 53) - 1:
            raise ValueError("block number exceeds report range")
        block_hash = hex_bytes(receipt.get("blockHash"), 32, "block hash")
        status = quantity(receipt.get("status"))
        if status == 0:
            return Check("reverted", "transaction_reverted", block, block_hash=block_hash)
        if status != 1 or not isinstance(receipt.get("logs"), list):
            raise ValueError("invalid receipt status or logs")

        transfers = matching_transfers(receipt["logs"], intent)
        if not transfers:
            return Check("mismatch", "expected_transfer_missing", block, block_hash=block_hash)
        if len(transfers) > 1:
            return Check("mismatch", "ambiguous_transfer", block, block_hash=block_hash)
        index, amount = transfers[0]
        if amount != int(intent.amount):
            return Check("mismatch", "wrong_amount", block, block_hash=block_hash)
        return Check("confirmed", "exact_transfer", block, index, block_hash)
    except RpcUnavailable:
        return Check("unknown", "rpc_unavailable")
    except (ValueError, TypeError):
        return Check("unknown", "invalid_rpc_evidence")


def matching_transfers(logs: list, intent: Intent) -> list[tuple[int, int]]:
    transfers = []
    payer = "0x" + "0" * 24 + intent.payer[2:]
    recipient = "0x" + "0" * 24 + intent.recipient[2:]
    for log in logs:
        if not isinstance(log, dict):
            raise ValueError("log must be a JSON object")
        if hex_bytes(log.get("address"), 20, "log address") != TOKEN:
            continue
        topics = log.get("topics")
        if not isinstance(topics, list):
            raise ValueError("invalid log topics")
        if not topics or hex_bytes(topics[0], 32, "event topic") != TRANSFER_TOPIC:
            continue
        if len(topics) != 3 or log.get("removed", False) is not False:
            raise ValueError("malformed or removed Transfer event")
        parties = [hex_bytes(topic, 32, "indexed address") for topic in topics[1:]]
        amount = int(hex_bytes(log.get("data"), 32, "transfer amount"), 16)
        if parties == [payer, recipient]:
            index = quantity(log.get("logIndex"))
            if index > (1 << 31) - 1:
                raise ValueError("log index exceeds report range")
            transfers.append((index, amount))
    return transfers
