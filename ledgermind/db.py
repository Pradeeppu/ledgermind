"""Transactional store: reference data from data/*.json plus a SQLite file for decisions and feedback.

Knowledge (history, patterns, human judgement) lives in Hindsight; this module only keeps records.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from functools import lru_cache

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoice_state (
    invoice_id TEXT PRIMARY KEY, status TEXT NOT NULL, outcome TEXT, confidence REAL,
    final_outcome TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT, memory_mode TEXT, outcome TEXT,
    payload TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT, vendor_id TEXT, action TEXT,
    agent_outcome TEXT, final_outcome TEXT, reason TEXT, user TEXT, risk_codes TEXT,
    invoice_date TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS uploaded_invoices (id TEXT PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS rule_status (rule_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT);
"""


def _conn() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def execute(sql: str, args: tuple = ()) -> None:
    with _lock, _conn() as c:
        c.execute(sql, args)


def query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def reset() -> None:
    with _lock, _conn() as c:
        for t in ("invoice_state", "decisions", "feedback", "uploaded_invoices", "rule_status"):
            c.execute(f"DELETE FROM {t}")


# ---------- reference data ----------
@lru_cache(maxsize=None)
def _load(name: str) -> list[dict]:
    return json.loads((config.DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def vendors() -> dict[str, dict]:
    return {v["id"]: v for v in _load("vendors")}


def pos() -> dict[str, dict]:
    return {p["id"]: p for p in _load("pos")}


def grns_by_po() -> dict[str, dict]:
    return {g["po_id"]: g for g in _load("grns")}


def invoices() -> dict[str, dict]:
    out = {i["id"]: i for i in _load("invoices")}
    for r in query("SELECT payload FROM uploaded_invoices"):
        inv = json.loads(r["payload"])
        out[inv["id"]] = inv
    return out


def add_uploaded(inv: dict) -> None:
    execute("INSERT OR REPLACE INTO uploaded_invoices VALUES (?,?)", (inv["id"], json.dumps(inv)))


# ---------- state ----------
def state(invoice_id: str) -> dict | None:
    rows = query("SELECT * FROM invoice_state WHERE invoice_id=?", (invoice_id,))
    return rows[0] if rows else None


def all_states() -> dict[str, dict]:
    return {r["invoice_id"]: r for r in query("SELECT * FROM invoice_state")}


def set_state(invoice_id: str, status: str, outcome: str | None = None, confidence: float | None = None,
              final_outcome: str | None = None) -> None:
    cur = state(invoice_id) or {}
    execute("INSERT OR REPLACE INTO invoice_state VALUES (?,?,?,?,?,?)", (
        invoice_id, status,
        outcome if outcome is not None else cur.get("outcome"),
        confidence if confidence is not None else cur.get("confidence"),
        final_outcome if final_outcome is not None else cur.get("final_outcome"),
        now()))


def save_decision(decision: dict) -> None:
    execute("INSERT INTO decisions (invoice_id, memory_mode, outcome, payload, created_at) VALUES (?,?,?,?,?)",
            (decision["invoice_id"], decision["memory_mode"], decision["outcome"], json.dumps(decision), now()))


def last_decision(invoice_id: str, memory_on: bool = True) -> dict | None:
    modes = ("on", "unavailable") if memory_on else ("off",)
    rows = query(f"SELECT payload FROM decisions WHERE invoice_id=? AND memory_mode IN ({','.join('?' * len(modes))}) "
                 "ORDER BY id DESC LIMIT 1", (invoice_id, *modes))
    return json.loads(rows[0]["payload"]) if rows else None


def first_decisions_on() -> dict[str, dict]:
    """First memory-ON decision per invoice (what the agent did before any human touched it)."""
    out = {}
    for r in query("SELECT invoice_id, payload FROM decisions WHERE memory_mode IN ('on','unavailable') ORDER BY id"):
        out.setdefault(r["invoice_id"], json.loads(r["payload"]))
    return out


def add_feedback(**f) -> None:
    execute("INSERT INTO feedback (invoice_id, vendor_id, action, agent_outcome, final_outcome, reason, user, "
            "risk_codes, invoice_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f["invoice_id"], f["vendor_id"], f["action"], f["agent_outcome"], f["final_outcome"], f["reason"],
             f["user"], ",".join(f["risk_codes"]), f["invoice_date"], now()))


def feedback_rows(vendor_id: str | None = None) -> list[dict]:
    if vendor_id:
        return query("SELECT * FROM feedback WHERE vendor_id=? ORDER BY invoice_date, id", (vendor_id,))
    return query("SELECT * FROM feedback ORDER BY invoice_date, id")


def rule_statuses() -> dict[str, str]:
    return {r["rule_id"]: r["status"] for r in query("SELECT * FROM rule_status")}


def set_rule_status(rule_id: str, status: str) -> None:
    execute("INSERT OR REPLACE INTO rule_status VALUES (?,?,?)", (rule_id, status, now()))
