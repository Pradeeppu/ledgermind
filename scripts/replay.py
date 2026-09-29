"""Seed memory and replay April -> mid-September invoices with a simulated AP clerk.

For each historical invoice, in date order:
  1. LedgerMind decides (memory ON).
  2. If it did not auto-approve, the "clerk" gives feedback using the invoice's hidden ground truth
     (accept when the agent was right, override with a reason when it was wrong).
  3. The outcome is retained in memory, so later invoices benefit.

Invoices dated on/after --live-from stay PENDING for the live demo.

Run:  python scripts/replay.py --reset            (fast: rules + recall, retains everything to memory)
      python scripts/replay.py --reset --reflect  (also calls Hindsight reflect per invoice; slower)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledgermind import agent, config, db, service  # noqa: E402
from ledgermind.memory import get_memory  # noqa: E402

CLERKS = ["Priya R.", "Priya R.", "Rakesh M."]


def seed_master_data(mem) -> None:
    items = []
    for v in db.vendors().values():
        items.append({
            "content": (f"{v['name']} (vendor ID {v['id']}, GSTIN {v['gstin']}, category {v['category']}) has payment "
                        f"terms {v['payment_terms']} in the vendor master. Its registered bank account ends "
                        f"{v['bank_account'][-4:]} ({v['bank_account']}). Verified contact phone on file: {v['contact_phone']}."),
            "tags": [agent.vendor_tag(v["id"]), "kind:master"], "metadata": {"fact_type": "world", "vendor_id": v["id"]},
            "timestamp": "2026-04-01T09:00:00", "context": "Vendor master data", "document_id": f"master-{v['id']}",
        })
    for p in db.pos().values():
        if p["vendor_id"] == "V02":
            items.append({"content": f"Apex Steel Industries contract price for MS round rod 12mm is Rs.512 per rod "
                                     f"(Q1 FY27 rate contract), with a 3% tolerance band.",
                          "tags": [agent.vendor_tag("V02"), "kind:master"], "metadata": {"fact_type": "world"},
                          "timestamp": "2026-04-01T09:00:00", "context": "Contract", "document_id": "contract-V02"})
            break
    items.append({"content": ("Acme AP policy: when a vendor asks to change bank details, never pay until the change is "
                              "verified by phone using the number already on file, never the number on the invoice or email."),
                  "tags": ["kind:policy"], "metadata": {"fact_type": "world"}, "timestamp": "2026-04-01T09:00:00",
                  "context": "AP policy", "document_id": "policy-bank-change"})
    mem.retain_batch(items)
    print(f"seeded {len(items)} master-data memories")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="clear decisions/feedback (and local memory) first")
    ap.add_argument("--reflect", action="store_true", help="call Hindsight reflect for every historical invoice")
    ap.add_argument("--live-from", default="2026-09-15")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose-csr", action="store_true", help="print every scholarship payout decision")
    args = ap.parse_args()

    mem = get_memory()
    ok, msg = mem.health()
    print(f"memory backend: {mem.backend} - {msg}")
    if not ok:
        sys.exit(1)
    if args.reset:
        db.reset()
        if mem.backend == "local":
            mem.items = []
            mem._save()
        else:  # start the Hindsight bank from scratch so earlier runs don't leak into this one
            try:
                mem.hs.delete_bank(mem.bank)
            except Exception as e:
                print(f"(bank delete skipped: {e})")
            mem._ready = False
            mem.ensure_bank()
    seed_master_data(mem)

    invs = sorted((i for i in db.invoices().values() if i["date"] < args.live_from), key=lambda i: (i["date"], i["id"]))
    if args.limit:
        invs = invs[:args.limit]
    wrong_auto = overrides = 0
    t0 = time.time()
    for n, inv in enumerate(invs, 1):
        d = agent.decide(inv["id"], memory_on=True, use_reflect=args.reflect)
        truth = inv["_truth"]
        clerk = CLERKS[n % len(CLERKS)]
        if d["outcome"] == "APPROVE":
            if truth["outcome"] != "APPROVE":
                wrong_auto += 1
                agent.feedback(inv["id"], "override", truth["outcome"], "Caught after payment run: " + truth["note"],
                               user=clerk, wait=False)
        elif d["outcome"] == truth["outcome"]:
            agent.feedback(inv["id"], "accept", reason=truth["note"], user=clerk, wait=False)
        else:
            overrides += 1
            agent.feedback(inv["id"], "override", truth["outcome"], truth["note"], user=clerk, wait=False)
        print(f"[{n:3}/{len(invs)}] {inv['date']} {inv['number']:10} {d['outcome']:8} truth={truth['outcome']:8} "
              f"{','.join(f['code'] for f in d['risk_flags']) or '-'}")
    print(f"\nreplayed {len(invs)} invoices in {time.time() - t0:.0f}s; overrides={overrides}; wrong auto-approvals={wrong_auto}")

    from ledgermind.csr import replay as csr_replay
    t1 = time.time()
    cs = csr_replay.run(mem, verbose=args.verbose_csr)
    print(f"replayed {cs['payouts']} scholarship payouts in {time.time() - t1:.0f}s; auto-released={cs['auto']} "
          f"accountant-handled={cs['human']} wrong auto-releases={cs['wrong_auto']}")
    for w in service.learning_curve():
        print(f"{w['week']} {w['from']}..{w['to']} n={w['invoices']:3} human={w['intervention_rate']:.0%} "
              f"exceptions={w['exceptions_caught']} protected=Rs.{w['value_protected']:,.0f}")


if __name__ == "__main__":
    main()
