"""CSR module storage: reference data from data/csr/*.json and state tables in the shared SQLite file."""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache

from .. import config, db

DATA = config.DATA_DIR / "csr"

SCHEMA = """
CREATE TABLE IF NOT EXISTS csr_payout_state (payout_id TEXT PRIMARY KEY, status TEXT, outcome TEXT, confidence REAL,
    final_outcome TEXT, released_on TEXT, released_by TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS csr_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, payout_id TEXT, memory_mode TEXT,
    outcome TEXT, payload TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS csr_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, payout_id TEXT, student_id TEXT, action TEXT,
    agent_outcome TEXT, final_outcome TEXT, reason TEXT, user TEXT, risk_codes TEXT, on_date TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS csr_verifications (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, account TEXT, bank TEXT,
    user TEXT, reason TEXT, on_date TEXT);
CREATE TABLE IF NOT EXISTS csr_txns (id TEXT PRIMARY KEY, payout_id TEXT, student_id TEXT, amount REAL, bank TEXT,
    account TEXT, utr TEXT, sent_on TEXT, credit_days INTEGER, result TEXT, reason TEXT, released_by TEXT);
CREATE TABLE IF NOT EXISTS csr_settings (key TEXT PRIMARY KEY, value TEXT);
"""
TABLES = ("csr_payout_state", "csr_decisions", "csr_feedback", "csr_verifications", "csr_txns", "csr_settings")


def init() -> None:
    with db._lock, db._conn() as c:  # noqa: SLF001 - share the app's single SQLite file
        c.executescript(SCHEMA)


def reset() -> None:
    init()
    for t in TABLES:
        db.execute(f"DELETE FROM {t}")


# ---------- reference data ----------
@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def foundation() -> dict:
    return _load("foundation")


def donors() -> dict[str, dict]:
    return {d["id"]: d for d in _load("donors")}


def grants() -> list[dict]:
    return sorted(_load("grants"), key=lambda g: g["date"])


def cycles() -> dict[str, dict]:
    return {c["id"]: c for c in _load("cycles")}


def students() -> dict[str, dict]:
    return {s["id"]: s for s in _load("students")}


def payouts() -> dict[str, dict]:
    return {p["id"]: p for p in _load("payouts")}


def seed_verifications() -> list[dict]:
    return _load("verifications")


# ---------- simulated bank clock ----------
def sim_date() -> date:
    init()
    rows = db.query("SELECT value FROM csr_settings WHERE key='sim_date'")
    return date.fromisoformat(rows[0]["value"] if rows else foundation()["sim_start"])


def set_sim_date(d: date) -> None:
    init()
    db.execute("INSERT OR REPLACE INTO csr_settings VALUES ('sim_date', ?)", (d.isoformat(),))


def days_between(a: str, b: date) -> int:
    return (b - date.fromisoformat(a)).days


def add_days(a: str, n: int) -> str:
    return (date.fromisoformat(a) + timedelta(days=n)).isoformat()


# ---------- state ----------
def states() -> dict[str, dict]:
    init()
    return {r["payout_id"]: r for r in db.query("SELECT * FROM csr_payout_state")}


def set_state(payout_id: str, status: str, outcome: str | None = None, confidence: float | None = None,
              final_outcome: str | None = None, released_on: str | None = None, released_by: str | None = None) -> None:
    cur = states().get(payout_id, {})
    db.execute("INSERT OR REPLACE INTO csr_payout_state VALUES (?,?,?,?,?,?,?,?)", (
        payout_id, status, outcome if outcome is not None else cur.get("outcome"),
        confidence if confidence is not None else cur.get("confidence"),
        final_outcome if final_outcome is not None else cur.get("final_outcome"),
        released_on if released_on is not None else cur.get("released_on"),
        released_by if released_by is not None else cur.get("released_by"), db.now()))


def save_decision(d: dict) -> None:
    init()
    db.execute("INSERT INTO csr_decisions (payout_id, memory_mode, outcome, payload, created_at) VALUES (?,?,?,?,?)",
               (d["payout_id"], d["memory_mode"], d["outcome"], json.dumps(d), db.now()))


def last_decision(payout_id: str, memory_on: bool = True) -> dict | None:
    init()
    modes = ("on", "unavailable") if memory_on else ("off",)
    rows = db.query(f"SELECT payload FROM csr_decisions WHERE payout_id=? AND memory_mode IN ({','.join('?' * len(modes))}) "
                    "ORDER BY id DESC LIMIT 1", (payout_id, *modes))
    return json.loads(rows[0]["payload"]) if rows else None


def first_decisions() -> dict[str, dict]:
    init()
    out: dict[str, dict] = {}
    for r in db.query("SELECT payout_id, payload FROM csr_decisions WHERE memory_mode IN ('on','unavailable') ORDER BY id"):
        out.setdefault(r["payout_id"], json.loads(r["payload"]))
    return out


def add_feedback(**f) -> None:
    init()
    db.execute("INSERT INTO csr_feedback (payout_id, student_id, action, agent_outcome, final_outcome, reason, user, "
               "risk_codes, on_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (f["payout_id"], f["student_id"], f["action"], f["agent_outcome"], f["final_outcome"], f["reason"],
                f["user"], ",".join(f["risk_codes"]), f["on_date"], db.now()))


def feedback_rows(student_id: str | None = None) -> list[dict]:
    init()
    if student_id:
        return db.query("SELECT * FROM csr_feedback WHERE student_id=? ORDER BY on_date, id", (student_id,))
    return db.query("SELECT * FROM csr_feedback ORDER BY on_date, id")


def add_verification(student_id: str, account: str, bank: str, user: str, reason: str, on_date: str) -> None:
    init()
    db.execute("INSERT INTO csr_verifications (student_id, account, bank, user, reason, on_date) VALUES (?,?,?,?,?,?)",
               (student_id, account, bank, user, reason, on_date))


def verifications(student_id: str | None = None) -> list[dict]:
    init()
    if student_id:
        return db.query("SELECT * FROM csr_verifications WHERE student_id=? ORDER BY on_date, id", (student_id,))
    return db.query("SELECT * FROM csr_verifications ORDER BY on_date, id")


def add_txn(t: dict) -> None:
    init()
    db.execute("INSERT OR REPLACE INTO csr_txns VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (t["id"], t["payout_id"], t["student_id"], t["amount"], t["bank"], t["account"], t["utr"], t["sent_on"],
                t["credit_days"], t["result"], t["reason"], t["released_by"]))


def txns() -> list[dict]:
    init()
    return db.query("SELECT * FROM csr_txns ORDER BY sent_on, id")
