"""WhatsApp channel for scholarship payouts: student alerts, bank-change verification, and replies that feed memory.

Default mode is SIMULATED: messages are stored in an outbox and shown in the app, and nothing leaves the machine
(the demo's phone numbers are fictional). Live mode sends through the WhatsApp Business Cloud API when all of
these are set:
    WHATSAPP_LIVE=1, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID
    WHATSAPP_TEST_RECIPIENT  (strongly recommended: every message goes to this one number, e.g. your own phone)
The Cloud API only delivers free-form text inside a 24-hour window opened by the recipient messaging the
business number first; outside it you need an approved template.

Anti-fraud rule: verification questions go to the student's REGISTERED phone number from the scholar master,
never to a number supplied with the change request.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

from .. import db
from . import store

log = logging.getLogger("ledgermind.whatsapp")
SENDER = "Shiksha Setu Foundation"

SCHEMA = """
CREATE TABLE IF NOT EXISTS csr_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, direction TEXT,
    phone TEXT, body TEXT, kind TEXT, payout_id TEXT, txn_id TEXT, status TEXT, on_date TEXT, meta TEXT);
"""


def init() -> None:
    with db._lock, db._conn() as c:  # noqa: SLF001
        c.executescript(SCHEMA)


def reset() -> None:
    init()
    db.execute("DELETE FROM csr_messages")


def mode() -> dict:
    live = (os.getenv("WHATSAPP_LIVE") == "1" and os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"))
    test = os.getenv("WHATSAPP_TEST_RECIPIENT", "").strip()
    return {"mode": "live" if live else "simulated", "sender": SENDER,
            "test_recipient": ("••••" + test[-4:]) if test else None}


def _first(name: str) -> str:
    return name.split()[0]


def _send_live(phone: str, body: str) -> str:
    to = os.getenv("WHATSAPP_TEST_RECIPIENT", "").strip() or phone
    to = re.sub(r"\D", "", to)
    url = f"https://graph.facebook.com/v20.0/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    req = urllib.request.Request(url, method="POST", data=json.dumps(
        {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}).encode(),
        headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 - fixed Meta Graph URL
        return "sent" if r.status < 300 else f"error {r.status}"


def send(student_id: str, kind: str, body: str, payout_id: str | None = None, txn_id: str | None = None,
         meta: dict | None = None) -> dict:
    init()
    s = store.students()[student_id]
    status = "simulated"
    if mode()["mode"] == "live":
        try:
            status = _send_live(s["phone"], body)
        except Exception as e:  # noqa: BLE001
            log.warning("WhatsApp send failed: %s", e)
            status = "failed"
    db.execute("INSERT INTO csr_messages (student_id, direction, phone, body, kind, payout_id, txn_id, status, on_date, meta) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)", (student_id, "out", s["phone"], body, kind, payout_id, txn_id, status,
                                                store.sim_date().isoformat(), json.dumps(meta or {})))
    return {"status": status}


def messages(student_id: str | None = None) -> list[dict]:
    init()
    if student_id:
        return db.query("SELECT * FROM csr_messages WHERE student_id=? ORDER BY id", (student_id,))
    return db.query("SELECT * FROM csr_messages ORDER BY id")


def pending_question(student_id: str) -> dict | None:
    """The latest verification question that hasn't been answered yet."""
    rows = messages(student_id)
    released = {pid for pid, st in store.states().items() if st.get("status") == "RELEASED"}
    for m in reversed(rows):
        if m["direction"] == "in":
            return None
        if m["kind"] in ("verify_change", "verify_first"):
            return None if m["payout_id"] in released else m
    return None


# ---------- templates (called from the agent) ----------
def on_release(p: dict, s: dict, utr: str) -> None:
    send(s["id"], "released", f"Hi {_first(s['name'])}, your {SENDER} scholarship of Rs.{p['amount']:,.0f} "
         f"({store.cycles()[p['cycle']]['label']}) has been sent to your account {p['account']} at {p['bank']}. "
         f"Reference {utr}. We'll message you when it's credited.", payout_id=p["id"])


def on_transfer(t: dict, s: dict, status: str) -> None:
    first = _first(s["name"])
    if status == "CREDITED":
        body = f"Good news {first}: Rs.{t['amount']:,.0f} has been credited to your account {t['account']} (ref {t['utr']})."
    elif status == "DELAYED":
        body = (f"Hi {first}, your scholarship transfer (ref {t['utr']}) is taking longer than usual at {t['bank']}. "
                "Our accountant is following up with the bank. No action is needed from you.")
    else:
        body = (f"Hi {first}, the scholarship transfer to {t['account']} could not be completed: {t['reason']}. "
                "Please reply with your updated bank details (account number, IFSC and a passbook photo). "
                "We will verify them by calling your registered number before sending again.")
    send(s["id"], status.lower(), body, payout_id=t["payout_id"], txn_id=t["id"])


def on_hold(p: dict, s: dict, codes: list[str]) -> None:
    """Send at most one question per payout, and only to the registered number."""
    if any(m["payout_id"] == p["id"] and m["kind"].startswith("verify") for m in messages(s["id"])):
        return
    first = _first(s["name"])
    if "BANK_CHANGE" in codes or "SHARED_ACCOUNT" in codes:
        send(s["id"], "verify_change",
             f"Hi {first}, we received a request to pay your scholarship into a NEW account {p['account']} at {p['bank']}. "
             "Did you make this request? Reply YES or NO. We never ask for OTPs or passwords.",
             payout_id=p["id"], meta={"account": p["account"], "bank": p["bank"]})
    elif "FIRST_PAYOUT" in codes:
        send(s["id"], "verify_first",
             f"Welcome to {SENDER}, {first}! Before your first scholarship payment we will send Rs.1 to account "
             f"{p['account']} at {p['bank']}. Reply YES once you see it in your account.",
             payout_id=p["id"], meta={"account": p["account"], "bank": p["bank"]})
    elif "PREVIOUS_FAILURE" in codes:
        send(s["id"], "need_details",
             f"Hi {first}, your last scholarship transfer to {p['account']} bounced, so this instalment is on hold. "
             "Please reply with your updated bank details and a passbook photo.", payout_id=p["id"])


def receive(student_id: str, text: str) -> dict:
    """Record a student's reply. YES / NO to a pending verification question changes the payout's evidence."""
    from . import agent  # local import: agent imports this module

    init()
    s = store.students()[student_id]
    today = store.sim_date().isoformat()
    q = pending_question(student_id)
    db.execute("INSERT INTO csr_messages (student_id, direction, phone, body, kind, payout_id, txn_id, status, on_date, meta) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)", (student_id, "in", s["phone"], text, "reply", q["payout_id"] if q else None,
                                                None, "received", today, "{}"))
    answer = text.strip().lower()
    if not q:
        agent._retain(f"On {today} {s['name']} wrote on WhatsApp from the registered number: \"{text.strip()[:200]}\"",
                      [agent.stag(student_id), "kind:whatsapp"], today)
        return {"ok": True, "action": "stored", "message": "Reply saved to the student's conversation and memory."}
    meta = json.loads(q["meta"] or "{}")
    if answer.startswith("yes") or answer in ("y", "haan", "ha", "ok done", "received"):
        how = ("confirmed on WhatsApp from the registered number that they requested the new account"
               if q["kind"] == "verify_change" else "confirmed on WhatsApp that the Rs.1 test credit arrived")
        agent.feedback(q["payout_id"], "verify_account", reason=f"Student {how}", user="WhatsApp · student reply")
        send(student_id, "ack", f"Thank you {_first(s['name'])}. Your account is verified and your scholarship will be "
                                f"processed shortly.", payout_id=q["payout_id"])
        return {"ok": True, "action": "verified", "message": f"Verified {meta.get('account', '')} from the student's reply. "
                                                             "Run the agent on the payout to release it."}
    if answer.startswith("no") or "not me" in answer:
        agent.feedback(q["payout_id"], "note", reason=(f"FRAUD ALERT: the student replied NO on WhatsApp. They did NOT "
                                                        f"request account {meta.get('account', '')}. Keep blocked and investigate."),
                       user="WhatsApp · student reply")
        agent._retain(f"On {today} {s['name']} said on WhatsApp (registered number) that they did NOT request the bank "
                      f"change to {meta.get('account', '')} at {meta.get('bank', '')}. Treat that account as fraudulent.",
                      [agent.stag(student_id), "kind:whatsapp", "kind:fraud"], today)
        send(student_id, "ack", f"Thank you {_first(s['name'])}. We have blocked that change. Your scholarship stays with your "
                                "existing account, and our team will call you.", payout_id=q["payout_id"])
        return {"ok": True, "action": "fraud_blocked", "message": "Student denied the change. Payout stays blocked; "
                                                                  "fraud attempt retained in memory."}
    return {"ok": True, "action": "stored", "message": "Reply saved. It wasn't a YES or NO, so nothing changed."}
