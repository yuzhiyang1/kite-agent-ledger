"""覆盖真实 HTTP 客户端的响应头格式与输入边界。"""

import unittest

from kite_agent_ledger.http_capture import MAX_HEADER_DUMP, parse_http_headers


class HttpCaptureTests(unittest.TestCase):
    def test_accepts_crlf_and_lf_with_proxy_and_interim_responses(self):
        raw = (
            b"HTTP/1.1 200 Connection established\r\n\r\n"
            b"HTTP/1.1 103 Early Hints\r\nLink: </style.css>\r\n\r\n"
            b"HTTP/2 402\r\nPAYMENT-RESPONSE: stale\r\n\r\n"
            b"HTTP/2 200\r\npayment-response:\t dGVzdA== \t\r\n\r\n"
        )
        self.assertEqual(parse_http_headers(raw), (200, "dGVzdA=="))
        self.assertEqual(parse_http_headers(raw.replace(b"\r\n", b"\n")), (200, "dGVzdA=="))

    def test_final_response_without_header_does_not_reuse_stale_receipt(self):
        raw = b"HTTP/2 402\r\nPAYMENT-RESPONSE: stale\r\n\r\nHTTP/3 503\r\nRetry-After: 1\r\n\r\n"
        self.assertEqual(parse_http_headers(raw), (503, None))

    def test_rejects_ambiguous_or_incomplete_header_dumps(self):
        cases = [
            b"HTTP/2 200\nPAYMENT-RESPONSE: x\npayment-response: y\n\n",
            b"HTTP/2 200\nPAYMENT-RESPONSE: x\n",
            b"HTTP/2 200\nPAYMENT-RESPONSE: \xff\n\n",
            b"HTTP/2 200\nPAYMENT-RESPONSE : x\n\n",
            b"HTTP/2 200\n\nnot a response body\n\n",
            b"HTTP/1.1 100 Continue\n\n",
            b"HTTP/1.1 200 Connection established\n\n",
            b"HTTP/1.1 200 OK\nX-Data: " + b"x" * MAX_HEADER_DUMP + b"\n\n",
        ]
        for value in cases:
            with self.subTest(raw=value[:30]), self.assertRaises(ValueError):
                parse_http_headers(value)
