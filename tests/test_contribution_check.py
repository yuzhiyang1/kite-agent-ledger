"""确保贡献检查能区分链上证据、示例配置和本地敏感文件。"""

import unittest

from scripts.check_contribution import findings, forbidden_path


class ContributionCheckTests(unittest.TestCase):
    def test_blocks_secret_bearing_and_generated_paths(self):
        for path in (
            ".env", "nested/.env.local", "audit.sqlite3-journal", "dist/example.whl",
            "nested/key.pem", ".venv/Scripts/python.exe",
        ):
            with self.subTest(path=path):
                self.assertTrue(forbidden_path(path))
        self.assertFalse(forbidden_path(".env.example"))
        self.assertFalse(forbidden_path("docs/ARCHITECTURE.md"))

    def test_secret_findings_do_not_print_credentials(self):
        fake_secret = "gh" + "p_" + "a" * 36
        results = findings("notes.md", f"safe line\ntoken={fake_secret}".encode())
        self.assertEqual(results, ["notes.md:2: GitHub token"])
        self.assertIn("needs manual review", findings("blob", b"\xff")[0])

    def test_public_transaction_hash_is_allowed(self):
        public_hash = "0x" + "a" * 64
        self.assertEqual(findings("evidence.md", f"TX_HASH={public_hash}".encode()), [])
