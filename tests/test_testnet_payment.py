"""锁定真实付款工具的测试网和金额约束，测试自身不发起网络请求。"""

import unittest

from scripts.testnet_payment import AMOUNT, NETWORK, RECIPIENT, TOKEN, payment_terms


class TestnetPaymentTests(unittest.TestCase):
    def quote(self, **changes):
        terms = {
            "scheme": "exact", "network": NETWORK, "asset": TOKEN, "amount": AMOUNT,
            "payTo": RECIPIENT, "extra": {"name": "pieUSD", "version": "1"},
        } | changes
        return {"x402Version": 2, "accepts": [terms]}

    def test_accepts_the_expected_official_testnet_quote(self):
        self.assertEqual(payment_terms(self.quote())["amount"], AMOUNT)

    def test_refuses_changed_network_token_recipient_amount_and_domain(self):
        changes = [
            {"network": "eip155:2366"}, {"asset": "0x" + "1" * 40},
            {"payTo": "0x" + "2" * 40}, {"amount": str(int(AMOUNT) + 1)},
            {"extra": {"name": "pieUSD", "version": "2"}}, {"scheme": "upto"},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                payment_terms(self.quote(**change))

    def test_refuses_ambiguous_or_missing_payment_options(self):
        with self.assertRaises(ValueError):
            payment_terms([])
        for options in ([], [None], self.quote()["accepts"] * 2):
            with self.subTest(options=options), self.assertRaises(ValueError):
                payment_terms({"x402Version": 2, "accepts": options})
