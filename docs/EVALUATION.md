# LedgerMind evaluation

Synthetic ledger: 145 invoices from 10 vendors (April-September 2026). Ground truth = what an experienced AP clerk would decide (hidden from the agent). Historical invoices are scored on the agent's *first* decision, made online while it was still learning; the 9 live-demo invoices are scored after the replay.
Memory backend during this run: **local**.

## Headline: Memory ON vs Memory OFF (all invoices)

| Metric | Memory OFF (stateless) | Memory ON (LedgerMind) |
|---|---|---|
| Decision accuracy vs ground truth | 75.2% | **77.9%** |
| Risky invoices caught (recall, n=22) | 50.0% | **100.0%** |
| False auto-approvals of risky invoices | 11 | **0** |
| Overall auto-approval rate | 75.2% | 62.8% |

## After learning: the 9 live-demo invoices

| Metric | Memory OFF | Memory ON |
|---|---|---|
| Accuracy | 44.4% | **100.0%** |
| Risky caught | 40.0% | **100.0%** |
| False auto-approvals | 3 | **0** |
| Clean invoices auto-approved | 50.0% | 100.0% |
| Avg decision latency (memory ON, this backend) | | 8 ms |

## Planted cases

| Case | Invoice | Expected | Memory OFF | Memory ON | Result |
|---|---|---|---|---|---|
| Bank-detail change (vendor impersonation) | KE-1460 | ESCALATE | APPROVE | ESCALATE | PASS |
| Near-duplicate re-sent invoice | BP-2291A | FLAG | APPROVE | FLAG | PASS |
| Price creep above contract band | APX-1321 | FLAG | APPROVE | FLAG | PASS |
| Prompt injection in invoice text | OTH-1390 | FLAG | FLAG | FLAG | PASS |
| Recurring SaaS bill jumped 38% | VX-1042 | FLAG | FLAG | FLAG | PASS |
| Sharma freight surcharge (learned OK) | SL-1107 | APPROVE | FLAG | APPROVE | PASS |
| Metro net-15 terms (learned OK) | MFS-1121 | APPROVE | FLAG | APPROVE | PASS |
| Clean invoice, known vendor | NOS-1288 | APPROVE | APPROVE | APPROVE | PASS |

## Learning curve (memory ON, online)

| Period | Dates | Invoices | Needed a human | Decision accuracy | Exceptions caught | Rs. protected |
|---|---|---|---|---|---|---|
| W1 | 2026-04-01 to 2026-04-20 | 17 | 100.0% | 5.9% | 5 | 24,000 |
| W2 | 2026-04-21 to 2026-05-12 | 17 | 52.9% | 52.9% | 3 | 24,000 |
| W3 | 2026-05-12 to 2026-06-03 | 17 | 23.5% | 88.2% | 4 | 24,570 |
| W4 | 2026-06-03 to 2026-06-22 | 17 | 23.5% | 82.4% | 3 | 24,000 |
| W5 | 2026-06-23 to 2026-07-13 | 17 | 23.5% | 94.1% | 3 | 43,800 |
| W6 | 2026-07-13 to 2026-08-01 | 17 | 29.4% | 88.2% | 3 | 38,400 |
| W7 | 2026-08-03 to 2026-08-23 | 17 | 17.6% | 100.0% | 3 | 50,400 |
| W8 | 2026-08-23 to 2026-09-10 | 17 | 17.6% | 100.0% | 3 | 54,800 |

## Historical invoices only (online learning phase)

| Metric | Memory OFF | Memory ON |
|---|---|---|
| Accuracy | 77.2% | 76.5% |
| Risky caught | 52.9% | 100.0% |
| False auto-approvals | 8 | 0 |

Notes: Memory ON is deliberately conservative early on (cold-start rule: fewer than 3 prior invoices means a human reviews). That costs accuracy in period 1 but is why it makes zero false auto-approvals. Accuracy counts an exact outcome match, so a FLAG on a clean invoice counts as wrong even though it is safe.

## CSR scholarship payouts

A synthetic foundation funded by 3 CSR donors, with 48 students and 136 payouts over three instalment cycles (engineering Rs.40-45k a year, medicine Rs.50k a year). Payouts in cycles 1-2, plus the first batch of cycle 3, are replayed with a simulated accountant and a simulated bank. The 12 remaining cycle-3 payouts are the live test.

| Metric | Memory OFF | Memory ON |
|---|---|---|
| Live payouts decided correctly (n=12) | 50.0% | **100.0%** |
| Risky payouts stopped (n=7) | 28.6% | **100.0%** |
| Risky payouts wrongly released | 5 | **0** |
| Transfers flagged as delayed at the demo date | 4 (naive 3-day SLA) | **1** (learned per-bank timing) |

| Student | What memory saw | Expected | Memory OFF | Memory ON | Result |
|---|---|---|---|---|---|
| Rahul Yadav | Clean | Release | Release | Release | PASS |
| Sneha Verma | Previous Failure | Hold | Release | Hold | PASS |
| Pooja Shetty | Bank Change | Escalate | Release | Escalate | PASS |
| Lakshmi Menon | Clean | Release | Release | Release | PASS |
| Suresh Joshi | Clean | Release | Hold | Release | PASS |
| Aditya Gowda | Over Entitlement | Hold | Hold | Hold | PASS |
| Nandini Hegde | Duplicate Payout | Escalate | Release | Escalate | PASS |
| Ayesha Verma | Clean | Release | Release | Release | PASS |
| Madhuri Hegde | Shared Account, Bank Change | Escalate | Release | Escalate | PASS |
| Pradeep Nair | Clean | Release | Release | Release | PASS |
| Imran Rao | Ineligible | Hold | Hold | Hold | PASS |
| Kiran Sharma | First Payout | Hold | Release | Hold | PASS |

Online replay: 124 historical payouts, **0 wrong auto-releases**. Auto-release rate by cycle: 2025-26 · Instalment 1 0%, 2025-26 · Instalment 2 89%, 2026-27 · Instalment 1 95%. Cycle 1 is every student's first payout, so each one needs a penny-drop check.
