"""CSR & scholarships service facade (see docs/CSR_SERVICE_CONTRACT.md). Plain dicts in, plain dicts out."""
from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from datetime import date

from ..memory import get_memory
from . import agent, store

PAYOUT_STATUS_ORDER = {"PENDING": 0, "ESCALATED": 1, "ON_HOLD": 2, "RELEASED": 3}


# ---------- helpers ----------
def _txn_views(memory_on: bool = True) -> list[dict]:
    today = store.sim_date()
    slas = agent.learned_slas(today)
    studs = store.students()
    out = []
    for t in store.txns():
        v = agent.txn_status(t, today, memory_on, slas)
        v["student_name"] = studs[t["student_id"]]["name"]
        v["note"] = t["reason"] if v["status"] in ("FAILED", "RETURNED") else (
            f"Past the {v['sla_days']}-day window for {t['bank']}" if v["status"] == "DELAYED" else (
                f"Within {t['bank']}'s usual {v['sla_days']}-day window" if v["status"] == "IN_TRANSIT" else ""))
        out.append(v)
    return out


def _allocations() -> list[dict]:
    """Map every transfer that moved money onto donor grants: same programme first (oldest grant first), then General."""
    today = store.sim_date().isoformat()
    grants = [dict(g, remaining=g["amount"]) for g in store.grants() if g["date"] <= today]
    studs = store.students()
    allocs = []
    for t in sorted(_txn_views(), key=lambda t: (t["sent_on"], t["id"])):
        if t["status"] in ("FAILED", "RETURNED"):
            continue
        prog = studs[t["student_id"]]["program"]
        need = t["amount"]
        for pool in (prog, "General"):
            for g in grants:
                if need <= 0:
                    break
                if g["program"] == pool and g["remaining"] > 0 and g["date"] <= t["sent_on"]:
                    take = min(need, g["remaining"])
                    g["remaining"] -= take
                    need -= take
                    allocs.append({"grant_id": g["id"], "donor_id": g["donor_id"], "program": prog, "pool": pool,
                                   "amount": take, "txn": t})
        if need > 0:
            allocs.append({"grant_id": None, "donor_id": None, "program": prog, "pool": "Unfunded", "amount": need, "txn": t})
    return allocs


def _row(p: dict, st: dict) -> dict:
    s = store.students()[p["student_id"]]
    c = store.cycles()[p["cycle"]]
    ps = st.get(p["id"], {})
    return {"id": p["id"], "student_id": s["id"], "student_name": s["name"], "course": s["course"], "college": s["college"],
            "cycle": c["id"], "cycle_label": c["label"], "amount": p["amount"], "bank": p["bank"], "account": p["account"],
            "accountant": s["accountant"], "status": ps.get("status", "PENDING"), "outcome": ps.get("outcome"),
            "confidence": ps.get("confidence")}


def _current_cycle() -> dict:
    return store.cycles()["C3"]


# ---------- overview ----------
def overview() -> dict:
    today = store.sim_date().isoformat()
    grants = [g for g in store.grants() if g["date"] <= today]
    allocs = _allocations()
    txns = _txn_views()
    studs = store.students()
    donors = store.donors()

    d_rows = []
    for did, d in donors.items():
        rec = sum(g["amount"] for g in grants if g["donor_id"] == did)
        a = [x for x in allocs if x["donor_id"] == did]
        disb = sum(x["amount"] for x in a if x["txn"]["status"] == "CREDITED")
        transit = sum(x["amount"] for x in a if x["txn"]["status"] in ("IN_TRANSIT", "DELAYED"))
        d_rows.append({"id": did, "name": d["name"], "received": rec, "disbursed": disb, "in_transit": transit,
                       "left": rec - disb - transit, "students_funded": len({x["txn"]["student_id"] for x in a}),
                       "grants": sum(1 for g in grants if g["donor_id"] == did)})

    cyc = _current_cycle()
    st = store.states()
    cur = [p for p in store.payouts().values() if p["cycle"] == cyc["id"]]
    p_rows = []
    for prog in ("Engineering", "Medicine", "General"):
        rec = sum(g["amount"] for g in grants if g["program"] == prog)
        a = [x for x in allocs if x["pool"] == prog]
        disb = sum(x["amount"] for x in a if x["txn"]["status"] == "CREDITED")
        transit = sum(x["amount"] for x in a if x["txn"]["status"] in ("IN_TRANSIT", "DELAYED"))
        failed = sum(t["amount"] for t in txns if t["status"] in ("FAILED", "RETURNED")
                     and studs[t["student_id"]]["program"] == prog)
        need = sum(p["amount"] for p in cur if studs[p["student_id"]]["program"] == prog
                   and studs[p["student_id"]]["status"] == "active") if prog != "General" else 0
        p_rows.append({"program": prog, "received": rec, "disbursed": disb, "in_transit": transit, "failed_returned": failed,
                       "left": rec - disb - transit,
                       "students": len({x["txn"]["student_id"] for x in a}), "next_cycle_need": need})

    received = sum(g["amount"] for g in grants)
    disbursed = sum(x["amount"] for x in allocs if x["txn"]["status"] == "CREDITED")
    transit = sum(x["amount"] for x in allocs if x["txn"]["status"] in ("IN_TRANSIT", "DELAYED"))
    failed = sum(t["amount"] for t in txns if t["status"] in ("FAILED", "RETURNED"))
    counts = defaultdict(int)
    for p in cur:
        counts[st.get(p["id"], {}).get("status", "PENDING")] += 1

    flow = []
    for g in grants:
        flow.append({"source": donors[g["donor_id"]]["name"], "target": f"{g['program']} pool", "value": g["amount"]})
    for r in p_rows:
        for label, v in (("Credited to students", r["disbursed"]), ("In transit", r["in_transit"]), ("Unspent balance", r["left"])):
            if v > 0:
                flow.append({"source": f"{r['program']} pool", "target": label, "value": v})
    merged = defaultdict(float)
    for f in flow:
        merged[(f["source"], f["target"])] += f["value"]

    return {
        "sim_date": today, "foundation": store.foundation()["name"],
        "totals": {"received": received, "disbursed": disbursed, "in_transit": transit, "failed_returned": failed,
                   "left": received - disbursed - transit,
                   "committed_pending": sum(p["amount"] for p in cur if st.get(p["id"], {}).get("status", "PENDING") != "RELEASED"),
                   "utilisation_pct": round(disbursed / received * 100, 1) if received else 0,
                   "students_active": sum(1 for s in studs.values() if s["status"] == "active"),
                   "students_funded": len({x["txn"]["student_id"] for x in allocs})},
        "donors": d_rows, "programs": p_rows,
        "cycle": {"id": cyc["id"], "label": cyc["label"], "scheduled_on": cyc["scheduled_on"], "payouts": len(cur),
                  "released": counts["RELEASED"], "pending": counts["PENDING"], "on_hold": counts["ON_HOLD"],
                  "escalated": counts["ESCALATED"],
                  "amount_released": sum(p["amount"] for p in cur if st.get(p["id"], {}).get("status") == "RELEASED"),
                  "amount_pending": sum(p["amount"] for p in cur if st.get(p["id"], {}).get("status", "PENDING") != "RELEASED")},
        "flow": [{"source": s, "target": t, "value": v} for (s, t), v in merged.items()],
    }


def donor_trail(donor_id: str) -> dict:
    d = store.donors()[donor_id]
    today = store.sim_date().isoformat()
    studs = store.students()
    cyc = store.cycles()
    pays = store.payouts()
    a = [x for x in _allocations() if x["donor_id"] == donor_id]
    grants = [g for g in store.grants() if g["donor_id"] == donor_id and g["date"] <= today]
    rows = []
    for x in a:
        t, s = x["txn"], studs[x["txn"]["student_id"]]
        rows.append({"student_id": s["id"], "student_name": s["name"], "course": s["course"], "college": s["college"],
                     "cycle": cyc[pays[t["payout_id"]]["cycle"]]["label"], "amount": x["amount"], "sent_on": t["sent_on"],
                     "status": t["status"], "utr": t["utr"], "grant_id": x["grant_id"]})
    rec = sum(g["amount"] for g in grants)
    disb = sum(r["amount"] for r in rows if r["status"] == "CREDITED")
    transit = sum(r["amount"] for r in rows if r["status"] in ("IN_TRANSIT", "DELAYED"))
    return {"donor": {"id": d["id"], "name": d["name"], "contact": d["contact"]},
            "grants": [{"id": g["id"], "date": g["date"], "amount": g["amount"], "program": g["program"]} for g in grants],
            "allocations": sorted(rows, key=lambda r: (r["sent_on"], r["student_name"]), reverse=True),
            "summary": {"received": rec, "disbursed": disb, "in_transit": transit, "left": rec - disb - transit,
                        "students_funded": len({r["student_id"] for r in rows})}}


def utilisation_report_csv(donor_id: str | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Donor", "Grant", "Student ID", "Student", "Course", "College", "Cycle", "Amount (INR)", "Sent on",
                "Transfer status", "UTR"])
    for did, d in store.donors().items():
        if donor_id and did != donor_id:
            continue
        for r in donor_trail(did)["allocations"]:
            w.writerow([d["name"], r["grant_id"], r["student_id"], r["student_name"], r["course"], r["college"], r["cycle"],
                        f"{r['amount']:.0f}", r["sent_on"], r["status"], r["utr"]])
    return buf.getvalue()


# ---------- payouts ----------
def list_payouts(status: str | None = None, accountant: str | None = None, cycle: str | None = None) -> list[dict]:
    st = store.states()
    cycle = cycle or _current_cycle()["id"]
    rows = [_row(p, st) for p in store.payouts().values() if cycle == "all" or p["cycle"] == cycle]
    rows = [r for r in rows if (not status or r["status"] == status) and (not accountant or r["accountant"] == accountant)]
    return sorted(rows, key=lambda r: (PAYOUT_STATUS_ORDER.get(r["status"], 9), r["student_name"]))


def get_payout(payout_id: str) -> dict:
    p = store.payouts()[payout_id]
    row = _row(p, store.states())
    ay = store.cycles()[p["cycle"]]["academic_year"]
    paid = sum(h["amount"] for h in agent.student_history(p["student_id"])
               if h["id"] != payout_id and h["final_outcome"] == "RELEASE" and store.cycles()[h["cycle"]]["academic_year"] == ay)
    return {**row, "year": p["year"], "annual_entitlement": p["annual_entitlement"], "paid_this_year": paid,
            "ifsc": p["ifsc"], "account_holder": p["holder"], "request_note": p.get("request_note", ""),
            "scheduled_on": p["scheduled_on"]}


def _public(d: dict | None) -> dict | None:
    return {k: v for k, v in d.items() if not k.startswith("_")} if d else None


def decide_payout(payout_id: str, memory_on: bool = True) -> dict:
    st = store.states().get(payout_id, {})
    persist = not (memory_on and st.get("status") == "RELEASED")  # never re-release money already sent
    return _public(agent.decide(payout_id, memory_on=memory_on, persist=persist))


def get_payout_decision(payout_id: str) -> dict | None:
    return _public(store.last_decision(payout_id))


def payout_feedback(payout_id: str, action: str, new_outcome: str | None = None, reason: str = "",
                    user: str = "Meera K.") -> dict:
    return agent.feedback(payout_id, action, new_outcome, reason, user)


# ---------- transactions ----------
def list_transactions(status: str | None = None, bank: str | None = None, memory_on: bool = True) -> list[dict]:
    rows = []
    for t in _txn_views(memory_on):
        if (status and t["status"] != status) or (bank and t["bank"] != bank):
            continue
        rows.append({k: t[k] for k in ("id", "payout_id", "student_id", "student_name", "amount", "bank", "account", "utr",
                                       "sent_on", "expected_by", "credited_on", "status", "days_in_transit", "sla_days", "note")})
    order = {"DELAYED": 0, "FAILED": 1, "RETURNED": 2, "IN_TRANSIT": 3, "CREDITED": 4}
    return sorted(rows, key=lambda r: (order.get(r["status"], 9), r["sent_on"]), reverse=False)


def transaction_timeline(txn_id: str) -> list[dict]:
    t = next(x for x in _txn_views() if x["id"] == txn_id)
    today = store.sim_date().isoformat()
    ev = [{"date": t["sent_on"], "event": "Released", "detail": f"Approved by {t['released_by']}"},
          {"date": t["sent_on"], "event": "Sent to bank", "detail": f"NEFT to {t['account']} at {t['bank']} · {t['utr']}"}]
    if t["status"] == "DELAYED":
        ev.append({"date": store.add_days(t["expected_by"], 1), "event": "Delayed",
                   "detail": f"No credit confirmation after {t['sla_days']} days (this bank's learned window). Chase the bank."})
    if t["status"] == "CREDITED":
        if t["credit_days"] > t["sla_days"]:
            ev.append({"date": store.add_days(t["expected_by"], 1), "event": "Delayed",
                       "detail": f"Past the {t['sla_days']}-day window: {t['reason'] or 'bank-side delay'}"})
        ev.append({"date": t["credited_on"], "event": "Credited",
                   "detail": f"Rs.{t['amount']:,.0f} credited after {t['credit_days']} day(s)"})
    elif t["status"] in ("FAILED", "RETURNED"):
        ev.append({"date": t["closed_on"], "event": t["status"].title(), "detail": t["reason"] + ". Funds returned to the pool."})
    else:
        ev.append({"date": today, "event": "Awaiting confirmation", "detail": f"Day {t['days_in_transit']} in transit; this bank's usual window is {t['sla_days']} days"})
    return ev


def advance_bank_clock(days: int = 1) -> dict:
    return agent.advance(days)


def bank_insights() -> list[dict]:
    return agent.bank_stats()


# ---------- students & team ----------
def list_students() -> list[dict]:
    return [{"id": s["id"], "name": s["name"], "course": s["course"], "college": s["college"],
             "year": s["year_2025"] + 1, "status": s["status"], "accountant": s["accountant"]}
            for s in store.students().values()]


def student_profile(student_id: str) -> dict:
    s = store.students()[student_id]
    hist = agent.student_history(student_id)
    st = store.states()
    tx = {t["payout_id"]: t for t in _txn_views()}
    accounts: dict[str, dict] = {}
    for p in sorted((p for p in store.payouts().values() if p["student_id"] == student_id), key=lambda p: p["scheduled_on"]):
        a = accounts.setdefault(p["account"], {"account": p["account"], "bank": p["bank"], "ifsc": p["ifsc"],
                                               "holder": p["holder"], "first_used": p["scheduled_on"], "last_used": None,
                                               "payouts": 0, "state": "unverified", "_last": None})
        t = tx.get(p["id"])
        if t:
            a["payouts"] += 1
            a["last_used"] = p["scheduled_on"]
            a["_last"] = t["status"]
    for a in accounts.values():
        last = a.pop("_last")
        if last in ("FAILED", "RETURNED"):
            a["state"] = "failed"
        elif a["payouts"] or agent.verified(student_id, a["account"]):
            a["state"] = "verified"
        elif len(accounts) > 1:
            a["state"] = "new"
    facts = []
    try:
        facts = [m["text"] for m in get_memory().recall(
            f"{s['name']} scholarship, bank account, transfers, verification", tags=[agent.stag(student_id)], limit=6)]
    except Exception:  # noqa: BLE001
        pass
    obs = []
    for code in agent.LEARNABLE:
        prior = [r for r in store.feedback_rows(student_id) if code in (r["risk_codes"] or "").split(",")
                 and r["final_outcome"] == "RELEASE"]
        if prior:
            obs.append({"id": f"csr:{student_id}:{code}", "text": f"{s['name']}: {code.replace('_', ' ').lower()} is accepted "
                        f"by the accountants ({prior[-1]['reason'][:90]})", "evidence_count": len(prior),
                        "first_seen": prior[0]["on_date"], "last_seen": prior[-1]["on_date"], "status": "active"})
    for v in store.verifications(student_id):
        obs.append({"id": f"ver:{v['id']}", "text": f"Account {v['account']} at {v['bank']} verified by {v['user']}: {v['reason']}",
                    "evidence_count": 1, "first_seen": v["on_date"], "last_seen": v["on_date"], "status": "confirmed"})
    return {
        "student": {"id": s["id"], "name": s["name"], "course": s["course"], "college": s["college"],
                    "year": s["year_2025"] + 1, "status": s["status"],
                    "annual_entitlement": max((p["annual_entitlement"] for p in store.payouts().values()
                                               if p["student_id"] == student_id), default=0),
                    "accountant": s["accountant"], "region": s["region"], "phone": s["phone"]},
        "facts": facts,
        "accounts": list(accounts.values()),
        "payouts": [{"payout_id": p["id"], "cycle_label": store.cycles()[p["cycle"]]["label"], "amount": p["amount"],
                     "status": st.get(p["id"], {}).get("status", "PENDING"),
                     "txn_status": tx[p["id"]]["status"] if p["id"] in tx else None,
                     "sent_on": tx[p["id"]]["sent_on"] if p["id"] in tx else None,
                     "credited_on": tx[p["id"]]["credited_on"] if p["id"] in tx else None}
                    for p in sorted((p for p in store.payouts().values() if p["student_id"] == student_id),
                                    key=lambda p: p["scheduled_on"])],
        "observations": obs,
        "_history_count": len(hist),
    }


def team_workload() -> list[dict]:
    studs = store.students()
    st = store.states()
    cyc = _current_cycle()["id"]
    txns = _txn_views()
    later_release = defaultdict(list)
    for t in txns:
        later_release[t["student_id"]].append(t)
    focus = {}
    for s in studs.values():
        focus[s["accountant"]] = s["region"]
    out = []
    for acc, region in sorted(focus.items()):
        mine = [p for p in store.payouts().values() if studs[p["student_id"]]["accountant"] == acc]
        cur = [p for p in mine if p["cycle"] == cyc]
        cnt = defaultdict(int)
        for p in cur:
            cnt[st.get(p["id"], {}).get("status", "PENDING")] += 1
        turn = [store.days_between(p["scheduled_on"], date.fromisoformat(st[p["id"]]["released_on"]))
                for p in mine if st.get(p["id"], {}).get("released_on")]
        my_tx = [t for t in txns if studs[t["student_id"]]["accountant"] == acc]
        failed = [t for t in my_tx if t["status"] in ("FAILED", "RETURNED")
                  and not any(o["sent_on"] > t["sent_on"] and o["status"] != "FAILED" for o in later_release[t["student_id"]])]
        out.append({"accountant": acc, "focus": region, "pending": cnt["PENDING"], "on_hold": cnt["ON_HOLD"],
                    "escalated": cnt["ESCALATED"], "released": cnt["RELEASED"],
                    "amount_pending": sum(p["amount"] for p in cur if st.get(p["id"], {}).get("status", "PENDING") != "RELEASED"),
                    "avg_turnaround_days": round(statistics.mean(turn), 1) if turn else None,
                    "failed_to_chase": len(failed), "delayed_to_chase": sum(1 for t in my_tx if t["status"] == "DELAYED")})
    return out


# ---------- WhatsApp ----------
def whatsapp_mode() -> dict:
    from . import whatsapp
    return whatsapp.mode()


def whatsapp_threads() -> list[dict]:
    """One row per student conversation, newest activity first; `awaiting_reply` marks open verification questions."""
    from . import whatsapp
    studs = store.students()
    threads: dict[str, dict] = {}
    for m in whatsapp.messages():
        t = threads.setdefault(m["student_id"], {"student_id": m["student_id"], "student_name": studs[m["student_id"]]["name"],
                                                 "phone": m["phone"], "count": 0})
        t.update(count=t["count"] + 1, last_message=m["body"], last_date=m["on_date"], last_kind=m["kind"], _id=m["id"])
    for sid, t in threads.items():
        q = whatsapp.pending_question(sid)
        t["awaiting_reply"] = bool(q)
        t["question_kind"] = q["kind"] if q else None
    rows = sorted(threads.values(), key=lambda t: (not t["awaiting_reply"], -t.pop("_id")))
    return rows


def whatsapp_messages(student_id: str) -> list[dict]:
    from . import whatsapp
    return [{"id": m["id"], "direction": m["direction"], "body": m["body"], "kind": m["kind"], "status": m["status"],
             "date": m["on_date"], "payout_id": m["payout_id"], "phone": m["phone"]} for m in whatsapp.messages(student_id)]


def whatsapp_reply(student_id: str, text: str) -> dict:
    """Simulate (or record) a student's reply from their registered number."""
    from . import whatsapp
    return whatsapp.receive(student_id, text)
