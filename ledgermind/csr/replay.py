"""Replay the scholarship history with a simulated accountant and a simulated bank.

For each processed payout, in date order: move the bank clock to the payout date, let the agent decide, and if it
didn't release, have the "accountant" act on the hidden ground truth (verify the account, override with a reason,
or accept the hold). Transfers then play out on the bank clock, and their outcomes are retained in memory.
Payouts marked `live` stay PENDING for the demo. The bank clock ends at the foundation's `sim_start` date.
"""
from __future__ import annotations

from datetime import date

from . import agent, store, whatsapp


def seed_master(mem) -> int:
    items = []
    for s in store.students().values():
        items.append({"content": (f"Scholar {s['name']} ({s['id']}) studies {s['course']} at {s['college']} "
                                  f"({s['program']} programme, handled by accountant {s['accountant']}). Registered bank "
                                  f"account ****{s['account']} at {s['bank']}, IFSC {s['ifsc']}, holder {s['holder']}. "
                                  f"Verified phone on file: {s['phone']}."),
                      "tags": [agent.stag(s["id"]), agent.btag(s["bank"]), "kind:csr-master"],
                      "metadata": {"fact_type": "world"}, "timestamp": "2025-07-01T09:00:00",
                      "context": "Scholar master data", "document_id": f"scholar-{s['id']}"})
    items.append({"content": ("Shiksha Setu Foundation payout policy: never pay into a changed bank account until it is "
                              "verified by calling the student on the registered number or by a Rs.1 penny-drop test; "
                              "never pay two students into one account; stop payments to discontinued students."),
                  "tags": ["kind:csr-policy"], "metadata": {"fact_type": "world"}, "timestamp": "2025-07-01T09:00:00",
                  "context": "Payout policy", "document_id": "csr-policy"})
    mem.retain_batch(items)
    return len(items)


def run(mem, verbose: bool = False) -> dict:
    store.reset()
    whatsapp.reset()
    n_master = seed_master(mem)
    seeds = sorted(store.seed_verifications(), key=lambda v: v["date"])
    pays = sorted((p for p in store.payouts().values() if not p["live"]), key=lambda p: (p["scheduled_on"], p["id"]))
    retained: set[str] = set()
    stats = {"payouts": 0, "auto": 0, "human": 0, "wrong_auto": 0}

    def settle(upto: date) -> None:  # retain transfer outcomes that happened by this date
        for t in store.txns():
            end = date.fromisoformat(store.add_days(t["sent_on"], t["credit_days"]))
            if end <= upto and t["id"] not in retained:
                agent.retain_txn_outcome(t)
                whatsapp.on_transfer(t, store.students()[t["student_id"]], t["result"])
                retained.add(t["id"])

    for p in pays:
        day = date.fromisoformat(p["scheduled_on"])
        while seeds and seeds[0]["date"] <= p["scheduled_on"]:
            v = seeds.pop(0)
            store.set_sim_date(date.fromisoformat(v["date"]))
            agent.feedback(next(x["id"] for x in store.payouts().values() if x["student_id"] == v["student_id"] and x["live"]),
                           "verify_account", reason=v["reason"], user=v["user"])
        store.set_sim_date(day)
        settle(day)
        d = agent.decide(p["id"], memory_on=True, use_reflect=False)
        truth = p["_truth"]
        s = store.students()[p["student_id"]]
        user = s["accountant"]
        stats["payouts"] += 1
        if d["outcome"] == "RELEASE":
            stats["auto"] += 1
            if truth["outcome"] != "RELEASE":
                stats["wrong_auto"] += 1
        else:
            stats["human"] += 1
            store.set_sim_date(date.fromordinal(day.toordinal() + (2 if truth.get("verify") else 1)))  # a human takes time
            if truth["outcome"] == "RELEASE":
                if truth.get("verify"):
                    if whatsapp.pending_question(p["student_id"]):  # the student answers the welcome message
                        whatsapp.receive(p["student_id"], "Yes, I received Rs.1. Thank you!")
                    else:
                        agent.feedback(p["id"], "verify_account", reason="Rs.1 penny-drop test succeeded; name matches passbook",
                                       user=user)
                agent.feedback(p["id"], "override", "RELEASE", truth["note"], user=user)
            elif truth["outcome"] == d["outcome"]:
                agent.feedback(p["id"], "accept", reason=truth["note"], user=user)
            else:
                agent.feedback(p["id"], "override", truth["outcome"], truth["note"], user=user)
        if verbose:
            print(f"  {p['scheduled_on']} {p['id']} {s['name']:18} {d['outcome']:8} truth={truth['outcome']:8} "
                  f"{','.join(f['code'] for f in d['risk_flags']) or '-'}")

    start = date.fromisoformat(store.foundation()["sim_start"])
    for v in seeds:  # verifications dated after the last processed payout
        store.set_sim_date(date.fromisoformat(v["date"]))
        agent.feedback(next(x["id"] for x in store.payouts().values() if x["student_id"] == v["student_id"] and x["live"]),
                       "verify_account", reason=v["reason"], user=v["user"])
    store.set_sim_date(start)
    settle(start)
    slas = agent.learned_slas(start)
    for t in store.txns():  # tell students whose transfer is already running late
        if agent.txn_status(t, start, True, slas)["status"] == "DELAYED":
            whatsapp.on_transfer(t, store.students()[t["student_id"]], "DELAYED")
    stats["master"] = n_master
    return stats
