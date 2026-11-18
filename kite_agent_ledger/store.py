"""SQLite 账本。一次调用只允许一条 HTTP 观察和一个交易哈希。"""

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict

from .chain import Check
from .model import Intent, hex_bytes, parse_reply, safe_label

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    service TEXT NOT NULL,
    payer TEXT NOT NULL,
    recipient TEXT NOT NULL,
    amount TEXT NOT NULL,
    opened_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    observed_at TEXT,
    http_status INTEGER,
    payment_status TEXT,
    response_tx_hash TEXT,
    tx_hash TEXT UNIQUE,
    tx_source TEXT
);
CREATE INDEX IF NOT EXISTS calls_by_run ON calls (run_id, opened_at, call_id);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES calls(call_id),
    tx_hash TEXT,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    block INTEGER,
    log_index INTEGER,
    block_hash TEXT,
    checked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS checks_by_call ON checks (call_id, id);
"""

INTENT_FIELDS = ("call_id", "run_id", "service", "payer", "recipient", "amount")


class Conflict(ValueError):
    """同一个调用或交易已登记为不同的证据。"""


class Ledger:
    def __init__(self, path: str) -> None:
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.executescript(SCHEMA)
        except sqlite3.Error:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def write(self):
        """先取得写锁再比较旧值，两个进程不会各自接受互相冲突的记录。"""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def open_call(self, intent: Intent) -> dict:
        fields = asdict(intent)
        with self.write():
            self.db.execute(
                """INSERT INTO calls (call_id, run_id, service, payer, recipient, amount)
                   VALUES (:call_id, :run_id, :service, :payer, :recipient, :amount)
                   ON CONFLICT(call_id) DO NOTHING""",
                fields,
            )
            call = self.get_call(intent.call_id)
            if self.intent(call) != intent:
                raise Conflict("call ID already has a different intent")
            return call

    @staticmethod
    def intent(call: dict) -> Intent:
        return Intent(**{field: call[field] for field in INTENT_FIELDS})

    def get_call(self, call_id: str) -> dict:
        safe_label(call_id, "call_id")
        row = self.db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
        if row is None:
            raise ValueError("unknown call ID")
        return dict(row)

    def capture(self, call_id: str, http_status: int | None, payment_response: str | None) -> dict:
        with self.write():
            call = self.get_call(call_id)
            reply = parse_reply(self.intent(call), http_status, payment_response)
            if call["observed_at"] is not None:
                recorded = (call["http_status"], call["payment_status"], call["response_tx_hash"])
                if recorded != (reply.http_status, reply.payment_status, reply.tx_hash):
                    raise Conflict("call already has a different HTTP observation")
                return call
            try:
                self.db.execute(
                    """UPDATE calls
                       SET observed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                           http_status = ?, payment_status = ?, response_tx_hash = ?,
                           tx_hash = ?, tx_source = ?
                       WHERE call_id = ?""",
                    (
                        reply.http_status, reply.payment_status, reply.tx_hash, reply.tx_hash,
                        "payment_response" if reply.tx_hash else None, call_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("transaction is already attached to a different call") from exc
            return self.get_call(call_id)

    def attach(self, call_id: str, tx_hash: str) -> dict:
        tx_hash = hex_bytes(tx_hash, 32, "transaction")
        with self.write():
            call = self.get_call(call_id)
            if call["observed_at"] is None:
                raise ValueError("record the HTTP observation before attaching a transaction")
            if call["tx_hash"] == tx_hash:
                return call
            if call["tx_hash"]:
                raise Conflict("call already has a different transaction")
            try:
                self.db.execute(
                    "UPDATE calls SET tx_hash = ?, tx_source = 'manual' WHERE call_id = ?",
                    (tx_hash, call_id),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("transaction is already attached to a different call") from exc
            return self.get_call(call_id)

    def save_check(self, call_id: str, tx_hash: str | None, check: Check) -> dict:
        with self.write():
            call = self.get_call(call_id)
            if call["tx_hash"] != tx_hash:
                raise Conflict("transaction changed while checking chain evidence")
            cursor = self.db.execute(
                """INSERT INTO checks (call_id, tx_hash, status, reason, block, log_index, block_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (call_id, tx_hash, check.status, check.reason, check.block, check.log_index, check.block_hash),
            )
            return dict(self.db.execute("SELECT * FROM checks WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def history(self, call_id: str) -> list[dict]:
        self.get_call(call_id)
        checks = self.db.execute("SELECT * FROM checks WHERE call_id = ? ORDER BY id", (call_id,))
        return [dict(check) for check in checks]

    def report(self, run_id: str) -> list[dict]:
        safe_label(run_id, "run_id")
        rows = self.db.execute(
            """SELECT c.*, k.status AS chain_status, k.reason AS chain_reason,
                      k.block, k.log_index, k.block_hash, k.checked_at
               FROM calls c
               LEFT JOIN checks k ON k.id = (
                   SELECT MAX(id) FROM checks WHERE call_id = c.call_id AND tx_hash IS c.tx_hash
               )
               WHERE c.run_id = ?
               ORDER BY c.opened_at, c.call_id""",
            (run_id,),
        )
        return [dict(row) for row in rows]
