"""Scholarship payout agent: check -> recall -> (reflect) -> decide -> release -> track -> learn.

What memory adds over a stateless payout run (memory OFF can only see the payout and the student's master record):
  * bank-account baseline per student (catches unverified changes, and recognises verified ones)
  * accounts shared between students (a middleman / fraud signal)
  * the last transfer's result (don't resend to a closed account)
  * payouts already released this cycle (duplicates)
  * learned exceptions (e.g. an account held by a parent, approved by the accountant before)
  * each bank's normal crediting time (so slow banks aren't flagged as delayed every time)
"""
from __future__ import annotations

import json
import logging
import math
import statistics
import time
import zlib
from datetime import date

from .. import config, db
from ..memory import get_memory
from . import store, whatsapp

log = logging.getLogger("ledgermind.csr")

ORDER = {"RELEASE": 0, "HOLD": 1, "ESCALATE": 2}
STATUS = {"RELEASE": "RELEASED", "HOLD": "ON_HOLD", "ESCALATE": "ESCALATED"}
NAIVE_SLA = 3
LEARNABLE = {"NAME_MISMATCH"}
URGENT = ("urgent", "immediately", "asap", "today itself", "fees due")

SCHEMA = {
    "type": "object",
    "properties": {"outcome": {"type": "string", "enum": ["RELEASE", "HOLD", "ESCALATE"]},
                   "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                   "rationale": {"type": "string"}},
    "required": ["outcome", "confidence", "rationale"],
}


def stag(student_id: str) -> str:
    return f"student:{student_id}"


def btag(bank: str) -> str:
    return "bank:" + bank.lower().replace(" ", "-")


def _flag(code, severity, message, forces=None, at_risk=0.0):
    return {"code": code, "severity": severity, "message": message, "hard_rule": forces is not None, "forces": forces,
            "at_risk": round(max(at_risk, 0.0), 2)}


# ---------- memory of the ledger ----------
def txn_status(t: dict, today: date, memory_on: bool = True, slas: dict | None = None) -> dict:
    elapsed = store.days_between(t["sent_on"], today)
    sla = (slas or {}).get(t["bank"], NAIVE_SLA) if memory_on else NAIVE_SLA
    done = elapsed >= t["credit_days"]
    status = t["result"] if done else ("DELAYED" if elapsed > sla else "IN_TRANSIT")
    return {**t, "status": status, "sla_days": sla, "expected_by": store.add_days(t["sent_on"], sla),
            "credited_on": store.add_days(t["sent_on"], t["credit_days"]) if done and t["result"] == "CREDITED" else None,
            "closed_on": store.add_days(t["sent_on"], t["credit_days"]) if done else None,
            "days_in_transit": min(elapsed, t["credit_days"]) if done else elapsed}


def learned_slas(today: date | None = None) -> dict[str, int]:
    """Per bank: the p90 of observed crediting days (only transfers already credited), plus one day of slack."""
    today = today or store.sim_date()
    days: dict[str, list[int]] = {}
    for t in store.txns():
        if t["result"] == "CREDITED" and store.days_between(t["sent_on"], today) >= t["credit_days"]:
            days.setdefault(t["bank"], []).append(t["credit_days"])
    out = {}
    for bank, ds in days.items():
        if len(ds) >= 3:
            ds = sorted(ds)
            p90 = ds[min(len(ds) - 1, math.ceil(0.9 * len(ds)) - 1)]
            out[bank] = max(NAIVE_SLA, p90 + 1)
    return out


def student_history(student_id: str, before: str | None = None) -> list[dict]:
    """Processed payouts of a student (with final outcome and the resulting transfer, as of the bank clock)."""
    today = store.sim_date()
    st = store.states()
    tx = {t["payout_id"]: t for t in store.txns()}
    out = []
    for p in store.payouts().values():
        if p["student_id"] != student_id or (before and p["scheduled_on"] > before):
            continue
        s = st.get(p["id"])
        if s and s.get("final_outcome"):
            t = tx.get(p["id"])
            out.append({**p, "final_outcome": s["final_outcome"], "txn": txn_status(t, today) if t else None})
    return sorted(out, key=lambda h: h["scheduled_on"])


def account_baseline(hist: list[dict]) -> dict[str, dict]:
    """Accounts that actually received money for this student."""
    base: dict[str, dict] = {}
    for h in hist:
        t = h.get("txn")
        if t and t["status"] == "CREDITED":
            b = base.setdefault(h["account"], {"account": h["account"], "bank": h["bank"], "first": h["scheduled_on"], "count": 0})
            b["count"] += 1
            b["last"] = h["scheduled_on"]
    return base


def verified(student_id: str, account: str) -> dict | None:
    rows = [v for v in store.verifications(student_id) if v["account"] == account]
    return rows[-1] if rows else None


def shared_with(p: dict) -> list[dict]:
    """Other students whose money went to this account."""
    studs = store.students()
    out = {}
    for t in store.txns():
        if t["account"] == p["account"] and t["bank"] == p["bank"] and t["student_id"] != p["student_id"]:
            out[t["student_id"]] = studs[t["student_id"]]
    return list(out.values())


# ---------- checks ----------
def check(p: dict, student: dict, memory_on: bool) -> tuple[list[dict], list[str]]:
    flags, learned = [], []
    note = (p.get("request_note") or "").lower()
    ay = store.cycles()[p["cycle"]]["academic_year"]

    # static checks: a stateless run sees these too (master data only)
    if student.get("status") != "active":
        flags.append(_flag("INELIGIBLE", "high", f"Student status is '{student['status']}'. "
                           f"{student.get('status_note', '')} Payments must stop.".strip(), "HOLD", p["amount"]))
    if p["amount"] > p["annual_entitlement"] / 2:
        flags.append(_flag("OVER_ENTITLEMENT", "high",
                           f"Instalment Rs.{p['amount']:,.0f} is above the per-instalment entitlement of "
                           f"Rs.{p['annual_entitlement'] / 2:,.0f} (annual Rs.{p['annual_entitlement']:,.0f}).", "HOLD",
                           p["amount"] - p["annual_entitlement"] / 2))
    if p["holder"].strip().lower() != student["name"].strip().lower():
        flags.append(_flag("NAME_MISMATCH", "medium",
                           f"Account holder '{p['holder']}' is not the student '{student['name']}'."))

    if not memory_on:
        return flags, learned

    hist = [h for h in student_history(p["student_id"]) if h["id"] != p["id"]]
    same_cycle = [h for h in hist if h["cycle"] == p["cycle"] and h["final_outcome"] == "RELEASE"]
    if same_cycle:
        h = same_cycle[0]
        flags.append(_flag("DUPLICATE_PAYOUT", "high",
                           f"{student['name']} was already paid Rs.{h['amount']:,.0f} for {store.cycles()[p['cycle']]['label']} "
                           f"(payout {h['id']} on {h['scheduled_on']}). This would pay twice.", "ESCALATE", p["amount"]))
    paid_year = sum(h["amount"] for h in hist if store.cycles()[h["cycle"]]["academic_year"] == ay and h["final_outcome"] == "RELEASE")
    if paid_year + p["amount"] > p["annual_entitlement"] and not same_cycle and p["amount"] <= p["annual_entitlement"] / 2:
        flags.append(_flag("YEAR_CAP", "high", f"Already paid Rs.{paid_year:,.0f} this academic year; this payout would exceed "
                           f"the annual Rs.{p['annual_entitlement']:,.0f}.", "HOLD", paid_year + p["amount"] - p["annual_entitlement"]))

    denied = [r for r in store.feedback_rows(p["student_id"]) if r["payout_id"] == p["id"]
              and (r["reason"] or "").startswith("FRAUD ALERT")]
    if denied:
        flags.append(_flag("FRAUD_CONFIRMED", "high", f"{student['name']} replied NO on WhatsApp ({denied[-1]['on_date']}) from "
                           f"the registered number: they did not request {p['account']}. Keep blocked and investigate.",
                           "ESCALATE", p["amount"]))
    base = account_baseline(hist)
    v = verified(p["student_id"], p["account"])
    others = shared_with(p)
    if others:
        names = ", ".join(f"{o['name']} ({o['id']})" for o in others)
        flags.append(_flag("SHARED_ACCOUNT", "high",
                           f"Account {p['account']} at {p['bank']} already received scholarship money for {names}. "
                           "One account for two students is a middleman signal.", "ESCALATE", p["amount"]))
    if base and p["account"] not in base:
        old = max(base.values(), key=lambda b: b["count"])
        if v:
            learned.append(f"New account {p['account']} was verified by {v['user']} on {v['on_date']}: \"{v['reason']}\"")
        else:
            urgency = " The request uses urgency language, a common pressure tactic." if any(u in note for u in URGENT) else ""
            flags.append(_flag("BANK_CHANGE", "high",
                               f"{old['count']} earlier payouts were credited to {old['account']} ({old['bank']}); this one asks "
                               f"for {p['account']} ({p['bank']}), which nobody has verified.{urgency} Call the student on "
                               f"{student['phone']} (the number on file) before paying.", "ESCALATE", p["amount"]))
    last_to_acct = [h for h in hist if h["account"] == p["account"] and h.get("txn")]
    failed_last = last_to_acct and last_to_acct[-1]["txn"]["status"] in ("FAILED", "RETURNED")
    if failed_last and (not v or v["on_date"] < last_to_acct[-1]["txn"]["closed_on"]):  # only a newer check counts
        t = last_to_acct[-1]["txn"]
        flags.append(_flag("PREVIOUS_FAILURE", "high",
                           f"The last transfer to {p['account']} ({t['utr']}, {last_to_acct[-1]['scheduled_on']}) was "
                           f"{t['status'].lower()}: {t['reason']}. Get updated bank details before sending again.", "HOLD"))
    if not hist and not v:
        flags.append(_flag("FIRST_PAYOUT", "medium",
                           f"First payout to {student['name']}. Verify {p['account']} with a Rs.1 penny-drop test before "
                           "releasing.", "HOLD"))
    elif not hist and v:
        learned.append(f"Account {p['account']} verified by {v['user']} on {v['on_date']}: \"{v['reason']}\"")

    # learned exception: the same soft issue approved by an accountant at least twice before
    for f in [f for f in flags if f["code"] in LEARNABLE]:
        prior = [r for r in store.feedback_rows(p["student_id"]) if f["code"] in (r["risk_codes"] or "").split(",")
                 and r["final_outcome"] == "RELEASE" and r["payout_id"] != p["id"]]
        if len(prior) >= 2:
            f["cleared"] = True
            r = prior[-1]
            learned.append(f"Learned from {r['user']} on {r['on_date']}: \"{r['reason'][:140]}\"")
            learned.append(f"{len(prior)} earlier payouts with this {f['code'].replace('_', ' ').lower()} were released")
    return flags, learned


# ---------- decide ----------
def decide(payout_id: str, memory_on: bool = True, use_reflect: bool = True, persist: bool = True) -> dict:
    t0 = time.time()
    p = store.payouts()[payout_id]
    student = store.students()[p["student_id"]]
    mem = get_memory()
    mode = "on" if memory_on else "off"
    flags, learned = check(p, student, memory_on)
    open_flags = [f for f in flags if not f.get("cleared")]
    hard = [f for f in open_flags if f["hard_rule"]]
    soft = [f for f in open_flags if not f["hard_rule"]]
    memories: list[dict] = []
    model = "rules"

    if memory_on:
        try:
            memories = mem.recall(f"{student['name']} scholarship payouts, bank account {p['account']} {p['bank']}, "
                                  "verification, failed transfers, accountant notes",
                                  tags=[stag(p["student_id"])], limit=6)
        except Exception as e:  # noqa: BLE001
            log.warning("recall failed: %s", e)
            mode = "unavailable"

    if hard:
        outcome = max((f["forces"] for f in hard), key=ORDER.get)
        conf = 0.95 if outcome == "ESCALATE" else 0.9
        rationale = " ".join(f["message"] for f in hard)
    elif soft:
        outcome, conf = "HOLD", 0.7
        rationale = " ".join(f["message"] for f in soft) + (" No earlier approval on record." if memory_on else " Needs review.")
    else:
        outcome = "RELEASE"
        if memory_on:
            conf = 0.92
            hist = student_history(p["student_id"])
            ok = sum(1 for h in hist if h.get("txn") and h["txn"]["status"] == "CREDITED" and h["account"] == p["account"])
            rationale = (f"Rs.{p['amount']:,.0f} is within the {p['annual_entitlement'] / 2:,.0f} instalment entitlement. "
                         + (f"{ok} earlier payouts were credited to {p['account']} ({p['bank']}). " if ok else "")
                         + ("Cleared using what the accountants taught me. " if learned else "")
                         + "Releasing to the bank.")
        else:
            conf = 0.8
            rationale = "Amount is within entitlement and the student is active. No history available: rules-only check."

    if memory_on and use_reflect and mode == "on" and mem.backend == "hindsight" and not hard:
        try:
            ctx = (f"Payout {p['id']} of Rs.{p['amount']:,.0f} to {student['name']} ({student['course']}, "
                   f"{student['college']}) for {store.cycles()[p['cycle']]['label']}, account {p['account']} at {p['bank']} "
                   f"(holder {p['holder']}). Request note: {p.get('request_note') or 'none'}.\nChecks:\n"
                   + ("\n".join(f"- [{f['code']}] {f['message']}" for f in flags) or "- none"))
            r = mem.reflect(f"Should the foundation RELEASE, HOLD or ESCALATE scholarship payout {p['id']} for "
                            f"{student['name']}? Use this student's payout history and the accountants' past decisions.",
                            context=ctx, schema=SCHEMA, tags=[stag(p["student_id"])])
            s = r["structured"] or {}
            if isinstance(s, str):
                s = json.loads(s)
            model = "hindsight-reflect"
            memories = (r["memories"] or []) + [m for m in memories if m["id"] not in {x["id"] for x in r["memories"]}]
            ro, rc = s.get("outcome"), float(s.get("confidence", 0))
            if ro in ORDER and ORDER[ro] > ORDER[outcome]:  # reflect can only make it stricter
                outcome, conf, rationale = ro, rc, s.get("rationale") or rationale
            elif ro == outcome == "RELEASE" and rc >= config.AUTO_APPROVE_CONFIDENCE:
                conf, rationale = max(conf, rc), s.get("rationale") or rationale
        except Exception as e:  # noqa: BLE001
            log.warning("reflect failed: %s", e)
            model = "rules (reflect failed)"

    if mode == "unavailable" and outcome == "RELEASE":
        outcome, conf = "HOLD", 0.5
        rationale = "Memory unavailable, so auto-release is disabled. " + rationale

    d = {"payout_id": payout_id, "outcome": outcome, "confidence": round(conf, 2), "rationale": rationale,
         "memory_mode": mode, "risk_flags": [{k: f[k] for k in ("code", "severity", "message", "hard_rule", "at_risk")}
                                             for f in open_flags],
         "memories": [{k: m.get(k) for k in ("id", "text", "type", "date")} for m in memories[:8]],
         "learned_from": learned[:3], "decided_at": db.now(), "model": model,
         "latency_ms": int((time.time() - t0) * 1000), "_codes": [f["code"] for f in flags]}
    if persist:
        store.save_decision(d)
        if memory_on:
            if outcome == "RELEASE":
                release(p, student, d, by="LedgerMind (auto-release)")
            else:
                store.set_state(payout_id, STATUS[outcome], outcome, d["confidence"])
                whatsapp.on_hold(p, student, [f["code"] for f in open_flags])
    return d


# ---------- release, transfers and learning ----------
def release(p: dict, student: dict, d: dict, by: str, reason: str = "") -> None:
    today = store.sim_date().isoformat()
    store.set_state(p["id"], "RELEASED", d["outcome"], d["confidence"], "RELEASE", today, by)
    truth = p["_txn"]
    utr = f"UTR{p['id'][1:]}{zlib.crc32(p['account'].encode()) % 90000 + 10000}"
    store.add_txn({"id": f"T{p['id'][1:]}", "payout_id": p["id"], "student_id": p["student_id"], "amount": p["amount"],
                   "bank": p["bank"], "account": p["account"], "utr": utr, "sent_on": today,
                   "credit_days": truth["days"], "result": truth["result"], "reason": truth.get("reason", ""),
                   "released_by": by})
    whatsapp.on_release(p, student, utr)
    why = "; ".join(f["message"].rstrip(". ") for f in d.get("risk_flags", [])) or "all checks passed"
    txt = (f"On {today} {by} released scholarship payout {p['id']} of Rs.{p['amount']:,.0f} to {student['name']} "
           f"({student['id']}, {store.cycles()[p['cycle']]['label']}) into account {p['account']} at {p['bank']} "
           f"(holder {p['holder']}). Checks: {why}." + (f" Reason: {reason.rstrip('.')}." if reason else ""))
    _retain(txt, [stag(p["student_id"]), btag(p["bank"]), "kind:payout"], today)


def _retain(text: str, tags: list[str], on_date: str) -> bool:
    try:
        get_memory().retain(text, tags=tags, metadata={"fact_type": "experience"}, timestamp=on_date,
                            context="Scholarship payout", wait=False)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("retain failed: %s", e)
        return False


def feedback(payout_id: str, action: str, new_outcome: str | None = None, reason: str = "",
             user: str = "Meera K.") -> dict:
    p = store.payouts()[payout_id]
    student = store.students()[p["student_id"]]
    today = store.sim_date().isoformat()
    if action == "verify_account":
        store.add_verification(p["student_id"], p["account"], p["bank"], user, reason.strip() or "Verified", today)
        ok = _retain(f"On {today} {user} verified {student['name']}'s bank account {p['account']} at {p['bank']} "
                     f"(holder {p['holder']}): {reason.strip() or 'verified'}.",
                     [stag(p["student_id"]), btag(p["bank"]), "kind:verification"], today)
        return {"ok": True, "retained": ok, "message": f"Account {p['account']} marked verified for {student['name']}. "
                                                        "Run the agent again to re-check the payout."}
    if action not in ("accept", "override", "note"):
        return {"ok": False, "retained": False, "message": f"Unknown action {action}"}
    if action == "override" and (not new_outcome or not reason.strip()):
        return {"ok": False, "retained": False, "message": "An override needs a new outcome and a reason."}
    d = store.last_decision(payout_id)
    if not d:
        return {"ok": False, "retained": False, "message": "Run the agent on this payout first."}
    st = store.states().get(payout_id, {})
    if st.get("status") == "RELEASED" and action == "override":
        return {"ok": False, "retained": False, "message": "Already released to the bank; it can't be overridden."}
    final = new_outcome if action == "override" else d["outcome"]
    store.add_feedback(payout_id=payout_id, student_id=p["student_id"], action=action, agent_outcome=d["outcome"],
                       final_outcome=final, reason=reason.strip(), user=user, risk_codes=d.get("_codes", []), on_date=today)
    if final == "RELEASE" and st.get("status") != "RELEASED":
        release(p, student, d, by=user, reason=reason)
        ok = True
    else:
        if st.get("status") != "RELEASED":
            store.set_state(payout_id, STATUS[final], final_outcome=final)
        verb = {"accept": "accepted the recommendation to", "override": "changed the decision to", "note": "noted on"}[action]
        ok = _retain(f"On {today} {user} {verb} {final.lower()} payout {payout_id} for {student['name']} "
                     f"({store.cycles()[p['cycle']]['label']}, {p['account']} at {p['bank']}). "
                     f"Reason: {reason.strip().rstrip('.') or 'none given'}.",
                     [stag(p["student_id"]), "kind:feedback"], today)
    return {"ok": True, "retained": ok,
            "message": f"Saved. {'Released to the bank' if final == 'RELEASE' else 'Kept ' + final.lower()} and retained in memory."}


def advance(days: int = 1) -> dict:
    """Move the simulated bank clock and record every transfer that changed state."""
    before_date = store.sim_date()
    slas = learned_slas(before_date)
    before = {t["id"]: txn_status(t, before_date, True, slas) for t in store.txns()}
    new_date = date.fromordinal(before_date.toordinal() + days)
    store.set_sim_date(new_date)
    slas2 = learned_slas(new_date)
    studs = store.students()
    updates = []
    for t in store.txns():
        a, b = before[t["id"]]["status"], txn_status(t, new_date, True, slas2)["status"]
        if a != b:
            updates.append({"txn_id": t["id"], "student_name": studs[t["student_id"]]["name"], "from": a, "to": b})
            if b in ("CREDITED", "FAILED", "RETURNED"):
                retain_txn_outcome(t)
            whatsapp.on_transfer(t, studs[t["student_id"]], b)
    return {"sim_date": new_date.isoformat(), "updates": updates}


def retain_txn_outcome(t: dict) -> None:
    s = store.students()[t["student_id"]]
    end = store.add_days(t["sent_on"], t["credit_days"])
    if t["result"] == "CREDITED":
        txt = (f"Transfer {t['utr']} of Rs.{t['amount']:,.0f} to {s['name']}'s account {t['account']} at {t['bank']} "
               f"was credited on {end}, {t['credit_days']} day(s) after it was sent on {t['sent_on']}.")
    else:
        txt = (f"Transfer {t['utr']} of Rs.{t['amount']:,.0f} to {s['name']}'s account {t['account']} at {t['bank']} "
               f"was {t['result'].lower()} on {end}: {t['reason']}.")
    _retain(txt, [stag(t["student_id"]), btag(t["bank"]), "kind:transfer"], end)


def bank_stats(today: date | None = None) -> list[dict]:
    today = today or store.sim_date()
    slas = learned_slas(today)
    rows: dict[str, dict] = {}
    for t in store.txns():
        st = txn_status(t, today, True, slas)
        r = rows.setdefault(t["bank"], {"bank": t["bank"], "transfers": 0, "credited": 0, "failed": 0, "_days": [],
                                        "false_delay_alarms_avoided": 0})
        r["transfers"] += 1
        if st["status"] == "CREDITED":
            r["credited"] += 1
            r["_days"].append(t["credit_days"])
        if st["status"] in ("FAILED", "RETURNED"):
            r["failed"] += 1
        naive = txn_status(t, today, False)["status"]
        if naive == "DELAYED" and st["status"] == "IN_TRANSIT":
            r["false_delay_alarms_avoided"] += 1
    out = []
    for r in rows.values():
        ds = sorted(r.pop("_days"))
        med = statistics.median(ds) if ds else None
        p90 = ds[min(len(ds) - 1, math.ceil(0.9 * len(ds)) - 1)] if ds else None
        sla = slas.get(r["bank"], NAIVE_SLA)
        note = (f"Usually credits in about {med:g} days; not delayed until day {sla + 1}." if med and sla > NAIVE_SLA
                else "Credits within the standard 3-day window." if med else "Not enough history yet.")
        out.append({**r, "median_days": med, "p90_days": p90, "learned_sla_days": sla, "naive_sla_days": NAIVE_SLA,
                    "note": note})
    return sorted(out, key=lambda r: -r["transfers"])
