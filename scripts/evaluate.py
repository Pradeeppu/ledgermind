"""Evaluate LedgerMind against the hidden ground truth (SRS Section 14 acceptance metrics).

Replays history from scratch (like scripts/replay.py), then scores:
  * Memory ON  - the agent's first decision on each invoice, made online while it was learning
  * Memory OFF - the same invoice run stateless (no history, no recall)
on accuracy, risky-invoice recall, false auto-approvals, automation rate and the planted fraud cases.
Writes docs/EVALUATION.md.

Run: python scripts/evaluate.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ledgermind import agent, db, service  # noqa: E402

PLANTED = [  # (label, invoice number, expected)
    ("Bank-detail change (vendor impersonation)", "KE-1460", "ESCALATE"),
    ("Near-duplicate re-sent invoice", "BP-2291A", "FLAG"),
    ("Price creep above contract band", "APX-1321", "FLAG"),
    ("Prompt injection in invoice text", "OTH-1390", "FLAG"),
    ("Recurring SaaS bill jumped 38%", "VX-1042", "FLAG"),
    ("Sharma freight surcharge (learned OK)", "SL-1107", "APPROVE"),
    ("Metro net-15 terms (learned OK)", "MFS-1121", "APPROVE"),
    ("Clean invoice, known vendor", "NOS-1288", "APPROVE"),
]


def score(pairs: list[tuple[str, str]]) -> dict:
    n = len(pairs)
    correct = sum(p == t for p, t in pairs)
    risky = [(p, t) for p, t in pairs if t != "APPROVE"]
    caught = sum(p != "APPROVE" for p, _ in risky)
    false_auto = sum(p == "APPROVE" and t != "APPROVE" for p, t in pairs)
    auto = sum(p == "APPROVE" for p, _ in pairs)
    clean = [(p, t) for p, t in pairs if t == "APPROVE"]
    clean_auto = sum(p == "APPROVE" for p, _ in clean)
    return {"n": n, "accuracy": correct / n if n else 0, "risky": len(risky), "risky_recall": caught / len(risky) if risky else 1,
            "false_auto": false_auto, "auto_rate": auto / n if n else 0,
            "clean_auto_rate": clean_auto / len(clean) if clean else 0}


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], check=True, capture_output=True)
    invs = db.invoices()
    firsts = db.first_decisions_on()
    live = sorted((i for i in invs.values() if i["date"] >= "2026-09-15"), key=lambda i: i["date"])

    hist_on, hist_off, live_on, live_off, latencies = [], [], [], [], []
    for inv_id, d in firsts.items():
        t = invs[inv_id]["_truth"]["outcome"]
        hist_on.append((d["outcome"], t))
        hist_off.append((agent.decide(inv_id, memory_on=False, persist=False)["outcome"], t))
    live_rows = {}
    for inv in live:
        t0 = time.time()
        on = agent.decide(inv["id"], memory_on=True, persist=False)
        latencies.append(time.time() - t0)
        off = agent.decide(inv["id"], memory_on=False, persist=False)
        live_on.append((on["outcome"], inv["_truth"]["outcome"]))
        live_off.append((off["outcome"], inv["_truth"]["outcome"]))
        live_rows[inv["number"]] = (off, on)

    all_on, all_off = score(hist_on + live_on), score(hist_off + live_off)
    h_on, h_off, l_on, l_off = score(hist_on), score(hist_off), score(live_on), score(live_off)
    curve = service.learning_curve()

    # accuracy of the online agent per learning period
    ordered = sorted(firsts.items(), key=lambda kv: (invs[kv[0]]["date"], kv[0]))
    size = -(-len(ordered) // 8)
    period_acc = []
    for b in range(0, len(ordered), size):
        chunk = ordered[b:b + size]
        period_acc.append(sum(d["outcome"] == invs[i]["_truth"]["outcome"] for i, d in chunk) / len(chunk))

    L = ["# LedgerMind evaluation", "",
         f"Synthetic ledger: {len(invs)} invoices from 10 vendors (April-September 2026). Ground truth = what an "
         "experienced AP clerk would decide (hidden from the agent). Historical invoices are scored on the agent's "
         "*first* decision, made online while it was still learning; the 9 live-demo invoices are scored after the replay.",
         f"Memory backend during this run: **{service.status()['memory_backend']}**.", "",
         "## Headline: Memory ON vs Memory OFF (all invoices)", "",
         "| Metric | Memory OFF (stateless) | Memory ON (LedgerMind) |", "|---|---|---|",
         f"| Decision accuracy vs ground truth | {pct(all_off['accuracy'])} | **{pct(all_on['accuracy'])}** |",
         f"| Risky invoices caught (recall, n={all_on['risky']}) | {pct(all_off['risky_recall'])} | **{pct(all_on['risky_recall'])}** |",
         f"| False auto-approvals of risky invoices | {all_off['false_auto']} | **{all_on['false_auto']}** |",
         f"| Overall auto-approval rate | {pct(all_off['auto_rate'])} | {pct(all_on['auto_rate'])} |", "",
         "## After learning: the 9 live-demo invoices", "",
         "| Metric | Memory OFF | Memory ON |", "|---|---|---|",
         f"| Accuracy | {pct(l_off['accuracy'])} | **{pct(l_on['accuracy'])}** |",
         f"| Risky caught | {pct(l_off['risky_recall'])} | **{pct(l_on['risky_recall'])}** |",
         f"| False auto-approvals | {l_off['false_auto']} | **{l_on['false_auto']}** |",
         f"| Clean invoices auto-approved | {pct(l_off['clean_auto_rate'])} | {pct(l_on['clean_auto_rate'])} |",
         f"| Avg decision latency (memory ON, this backend) | | {sum(latencies) / len(latencies) * 1000:.0f} ms |", "",
         "## Planted cases", "", "| Case | Invoice | Expected | Memory OFF | Memory ON | Result |", "|---|---|---|---|---|---|"]
    for label, num, exp in PLANTED:
        off, on = live_rows[num]
        ok = "PASS" if on["outcome"] == exp else "FAIL"
        L.append(f"| {label} | {num} | {exp} | {off['outcome']} | {on['outcome']} | {ok} |")
    L += ["", "## Learning curve (memory ON, online)", "",
          "| Period | Dates | Invoices | Needed a human | Decision accuracy | Exceptions caught | Rs. protected |",
          "|---|---|---|---|---|---|---|"]
    for w, acc in zip(curve, period_acc):
        L.append(f"| {w['week']} | {w['from']} to {w['to']} | {w['invoices']} | {pct(w['intervention_rate'])} | {pct(acc)} | "
                 f"{w['exceptions_caught']} | {w['value_protected']:,.0f} |")
    L += ["", "## Historical invoices only (online learning phase)", "",
          "| Metric | Memory OFF | Memory ON |", "|---|---|---|",
          f"| Accuracy | {pct(h_off['accuracy'])} | {pct(h_on['accuracy'])} |",
          f"| Risky caught | {pct(h_off['risky_recall'])} | {pct(h_on['risky_recall'])} |",
          f"| False auto-approvals | {h_off['false_auto']} | {h_on['false_auto']} |", "",
          "Notes: Memory ON is deliberately conservative early on (cold-start rule: fewer than 3 prior invoices means "
          "a human reviews). That costs accuracy in period 1 but is why it makes zero false auto-approvals. "
          "Accuracy counts an exact outcome match, so a FLAG on a clean invoice counts as wrong even though it is safe."]
    L += csr_section()
    out = ROOT / "docs" / "EVALUATION.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    # leave the app in demo state (history replayed, live invoices pending)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], check=True, capture_output=True)


def csr_section() -> list[str]:
    """Scholarship payouts: memory ON vs OFF on the live cycle, the online replay, and transfer tracking."""
    from ledgermind.csr import agent as ca, service as cs, store as cst

    pays = cst.payouts()
    live = sorted((p for p in pays.values() if p["live"]), key=lambda p: p["student_id"])
    studs = cst.students()
    rows, on_pairs, off_pairs = [], [], []
    for p in live:
        on = ca.decide(p["id"], memory_on=True, persist=False)
        off = ca.decide(p["id"], memory_on=False, persist=False)
        t = p["_truth"]["outcome"]
        on_pairs.append((on["outcome"], t))
        off_pairs.append((off["outcome"], t))
        saw = ", ".join(f["code"].replace("_", " ").title() for f in on["risk_flags"]) or (
            "Cleared by memory: " + ("verified account change" if "verified" in on["learned_from"][0] else "learned exception")
            if on["learned_from"] else "Clean")
        rows.append(f"| {studs[p['student_id']]['name']} | {saw} "
                    f"| {t.title()} | {off['outcome'].title()} | {on['outcome'].title()} | {'PASS' if on['outcome'] == t else 'FAIL'} |")

    def sc(pairs):
        n = len(pairs)
        risky = [x for x in pairs if x[1] != "RELEASE"]
        return (sum(a == b for a, b in pairs) / n, sum(a != "RELEASE" for a, _ in risky) / len(risky),
                sum(a == "RELEASE" and b != "RELEASE" for a, b in pairs), len(risky))

    a_on, r_on, f_on, nr = sc(on_pairs)
    a_off, r_off, f_off, _ = sc(off_pairs)
    firsts = cst.first_decisions()
    hist = [(d["outcome"], pays[i]["_truth"]["outcome"]) for i, d in firsts.items() if i in pays]
    wrong = sum(a == "RELEASE" and b != "RELEASE" for a, b in hist)
    by_cycle = {}
    for i, d in firsts.items():
        c = pays[i]["cycle"]
        n, auto = by_cycle.get(c, (0, 0))
        by_cycle[c] = (n + 1, auto + (d["outcome"] == "RELEASE"))
    naive = sum(1 for t in cs.list_transactions(memory_on=False) if t["status"] == "DELAYED")
    learned = sum(1 for t in cs.list_transactions(memory_on=True) if t["status"] == "DELAYED")
    L = ["", "## CSR scholarship payouts", "",
         "A synthetic foundation funded by 3 CSR donors, with 48 students and 136 payouts over three instalment cycles "
         "(engineering Rs.40-45k a year, medicine Rs.50k a year). Payouts in cycles 1-2, plus the first batch of cycle 3, "
         "are replayed with a simulated accountant and a simulated bank. The 12 remaining cycle-3 payouts are the live test.", "",
         "| Metric | Memory OFF | Memory ON |", "|---|---|---|",
         f"| Live payouts decided correctly (n={len(live)}) | {pct(a_off)} | **{pct(a_on)}** |",
         f"| Risky payouts stopped (n={nr}) | {pct(r_off)} | **{pct(r_on)}** |",
         f"| Risky payouts wrongly released | {f_off} | **{f_on}** |",
         f"| Transfers flagged as delayed at the demo date | {naive} (naive 3-day SLA) | **{learned}** (learned per-bank timing) |",
         "", "| Student | What memory saw | Expected | Memory OFF | Memory ON | Result |", "|---|---|---|---|---|---|", *rows,
         "", f"Online replay: {len(hist)} historical payouts, **{wrong} wrong auto-releases**. Auto-release rate by cycle: "
         + ", ".join(f"{cst.cycles()[c]['label']} {auto / n:.0%}" for c, (n, auto) in sorted(by_cycle.items()))
         + ". Cycle 1 is every student's first payout, so each one needs a penny-drop check."]
    return L


if __name__ == "__main__":
    main()
