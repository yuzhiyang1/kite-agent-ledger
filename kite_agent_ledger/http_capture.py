"""从外部 HTTP 客户端的响应头中提取账本需要的两个字段。"""

import re

MAX_HEADER_DUMP = 64 * 1024
STATUS_LINE = re.compile(rb"HTTP/(?:1\.[01]|2(?:\.0)?|3(?:\.0)?) ([1-5][0-9]{2})(?: [^\x00-\x1f\x7f]*)?")
FIELD_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


def parse_http_headers(raw: bytes) -> tuple[int, str | None]:
    """读最后一段完整响应头，代理 CONNECT、临时响应及前序 402 保持独立。"""
    data = raw.replace(b"\r\n", b"\n")
    if len(raw) > MAX_HEADER_DUMP or b"\r" in data or not data.endswith(b"\n\n"):
        raise ValueError("expected a complete HTTP response header dump within 64 KiB")
    status = 0
    payments = []
    for block in data[:-2].split(b"\n\n"):
        start, *lines = block.split(b"\n")
        match = STATUS_LINE.fullmatch(start)
        if match is None:
            raise ValueError("expected HTTP status line in response header dump")
        status = int(match.group(1))
        payments = []
        for line in lines:
            name, delimiter, value = line.partition(b":")
            if not delimiter or FIELD_NAME.fullmatch(name) is None:
                raise ValueError("invalid response header field")
            if name.lower() == b"payment-response":
                payments.append(value.strip(b" \t"))
    if status < 200 or start.lower().endswith(b" connection established"):
        raise ValueError("HTTP response header dump is missing the final response")
    if len(payments) > 1:
        raise ValueError("final response includes multiple PAYMENT-RESPONSE headers")
    try:
        return status, payments[0].decode("ascii") if payments else None
    except UnicodeError as exc:
        raise ValueError("PAYMENT-RESPONSE must contain ASCII text") from exc
