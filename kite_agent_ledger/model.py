"""校验本地记录和外部 x402 支付凭证。"""

import base64
import binascii
import json
import re
from dataclasses import dataclass

NETWORK = "eip155:2368"
CHAIN_ID = 2368
TOKEN = "0x38129cf4ce5e183eff248f42a7d345bb1b47621a"
RPC_URL = "https://rpc-testnet.gokite.ai/"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
MAX_UINT256 = (1 << 256) - 1


def safe_label(value: str, name: str) -> str:
    """仅接受短标识，避免把原始 URL、查询参数或请求内容写入账本。"""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ValueError(f"{name} must be a short ASCII identifier")
    return value


def hex_bytes(value: str, size: int, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"0x[0-9a-fA-F]{{{size * 2}}}", value):
        raise ValueError(f"{name} must contain {size} hex bytes")
    return value.lower()


def atomic_amount(value: str) -> str:
    """按整数比较 pieUSD 最小单位，避免小数换算或浮点误差。"""
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,77}", value):
        raise ValueError("amount must be a positive decimal integer in atomic units")
    if int(value) > MAX_UINT256:
        raise ValueError("amount exceeds uint256")
    return value


@dataclass(frozen=True)
class Intent:
    call_id: str
    run_id: str
    service: str
    payer: str
    recipient: str
    amount: str

    def __post_init__(self) -> None:
        for field in ("call_id", "run_id", "service"):
            safe_label(getattr(self, field), field)
        for field in ("payer", "recipient"):
            address = hex_bytes(getattr(self, field), 20, field)
            if int(address, 16) == 0:
                raise ValueError(f"{field} cannot be the zero address")
            object.__setattr__(self, field, address)
        if self.payer == self.recipient:
            raise ValueError("payer and recipient must be different")
        atomic_amount(self.amount)


@dataclass(frozen=True)
class Reply:
    http_status: int | None
    payment_status: str
    tx_hash: str | None = None


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """拒绝含重复键的证据，避免不同解析器选择不同字段值。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def parse_reply(
    intent: Intent, http_status: int | None, payment_response: str | None
) -> Reply:
    if http_status is None:
        if payment_response is not None:
            raise ValueError("a response header requires an HTTP status")
        return Reply(None, "no_http_response")
    if type(http_status) is not int or not 100 <= http_status <= 599:
        raise ValueError("invalid HTTP status")
    if payment_response is None:
        return Reply(http_status, "no_payment_response")

    try:
        if not isinstance(payment_response, str) or len(payment_response) > 8192:
            raise ValueError("invalid settlement header")
        decoded = base64.b64decode(payment_response, validate=True)
        payload = json.loads(decoded, object_pairs_hook=unique_object)
        if not isinstance(payload, dict) or type(payload.get("success")) is not bool:
            raise ValueError("invalid settlement response")
        if payload.get("network") != NETWORK:
            return Reply(http_status, "wrong_network")
        if "payer" in payload and hex_bytes(payload["payer"], 20, "receipt payer") != intent.payer:
            return Reply(http_status, "wrong_payer")
        transaction = payload.get("transaction")
        tx_hash = None if transaction == "" else hex_bytes(transaction, 32, "transaction")
        success = payload["success"]
        pending = payload.get("errorReason") == "settlement_pending"
        if (success or pending) and not tx_hash:
            raise ValueError("settlement response is missing a transaction")
        if success and pending:
            raise ValueError("settlement cannot be both successful and pending")
        status = "reported_success" if success else "reported_pending" if pending else "reported_failure"
        return Reply(http_status, status, tx_hash)
    except (ValueError, TypeError, binascii.Error, RecursionError):
        # 原始头和服务器返回的错误正文可能含敏感信息，账本只保存分类。
        return Reply(http_status, "invalid_payment_response")
