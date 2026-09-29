# CSR & scholarships: service contract (UI <-> engine)

Module: `ledgermind/csr/service.py` (import as `from ledgermind.csr import service as csr`).

**Scenario.** CSR donors (corporate CSR budgets) fund a scholarship foundation. The foundation pays each student
an annual scholarship in two instalments a year: engineering ₹40,000–45,000 a year, medicine ₹50,000 a year.
Accountants release the payouts by bank transfer. LedgerMind remembers every student (bank-account baseline,
payout and transfer history) and every bank (how fast it normally credits), decides each payout, and tracks each
transfer until it's credited.

All data is fictional: "Shiksha Setu Foundation", the donors and the students.

All functions are synchronous and return plain JSON-serialisable dicts and lists. Money is INR as a float.
Dates are `YYYY-MM-DD` strings. The engine runs on a simulated "bank clock" date (`sim_date`) so transfers
can move forward during a demo.

## Enums
- payout outcome: `"RELEASE" | "HOLD" | "ESCALATE"`, shown to users as Release / Hold / Escalate
- payout status: `"PENDING" | "RELEASED" | "ON_HOLD" | "ESCALATED"`
- transaction status: `"IN_TRANSIT" | "CREDITED" | "DELAYED" | "FAILED" | "RETURNED"`
- risk severity: `"high" | "medium" | "low"`; risk flags use the same shape as the AP module:
  `{"code","severity","message","hard_rule": bool, "at_risk": float}`

## Functions

```python
overview() -> {
  "sim_date": str, "foundation": str,
  "totals": {"received","disbursed","in_transit","failed_returned","left","committed_pending","utilisation_pct",
             "students_active","students_funded"},
  "donors": [{"id","name","received","disbursed","in_transit","left","students_funded","grants": int}],
  "programs": [{"program": "Engineering"|"Medicine"|"General","received","disbursed","in_transit","failed_returned",
                "left","students","next_cycle_need"}],
  "cycle": {"id","label","scheduled_on","payouts","released","pending","on_hold","escalated","amount_released","amount_pending"},
  "flow": [{"source","target","value"}]          # donor -> program -> outcome, for a Sankey chart
}

donor_trail(donor_id) -> {
  "donor": {"id","name","contact"},
  "grants": [{"id","date","amount","program"}],
  "allocations": [{"student_id","student_name","course","college","cycle","amount","sent_on","status","utr"}],
  "summary": {"received","disbursed","in_transit","left","students_funded"}
}
utilisation_report_csv(donor_id: str | None = None) -> str     # CSV text for st.download_button

list_payouts(status=None, accountant=None, cycle=None) -> list[PayoutRow]
# PayoutRow = {"id","student_id","student_name","course","college","cycle","cycle_label","amount","bank","account",
#              "accountant","status","outcome"(or None),"confidence"(or None)}
get_payout(payout_id) -> Payout
# Payout = PayoutRow + {"year","annual_entitlement","paid_this_year","ifsc","account_holder","request_note","scheduled_on"}
decide_payout(payout_id, memory_on: bool = True) -> PayoutDecision
get_payout_decision(payout_id) -> PayoutDecision | None
# PayoutDecision = {"payout_id","outcome","confidence","rationale","memory_mode","risk_flags":[...],
#                   "memories":[{"id","text","type","date"}],"learned_from":[str],"decided_at","model","latency_ms"}
payout_feedback(payout_id, action: "accept"|"override"|"note"|"verify_account", new_outcome=None,
                reason: str = "", user: str = "Meera K.") -> {"ok","retained","message"}
# "verify_account" = the accountant confirmed the student's current bank account (penny-drop test or a call-back).
# The account becomes that student's verified baseline, so future payouts to it can release.

list_transactions(status=None, bank=None, memory_on: bool = True) -> list[Txn]
# Txn = {"id","payout_id","student_id","student_name","amount","bank","account","utr","sent_on","expected_by",
#        "credited_on"(or None),"status","days_in_transit","sla_days","note"}
# memory_on=False uses a naive 3-day SLA for every bank; memory_on=True uses each bank's learned SLA.
transaction_timeline(txn_id) -> list[{"date","event","detail"}]
advance_bank_clock(days: int = 1) -> {"sim_date", "updates": [{"txn_id","student_name","from","to"}]}
bank_insights() -> list[{"bank","transfers","credited","failed","median_days","p90_days","learned_sla_days","naive_sla_days",
                         "false_delay_alarms_avoided","note"}]

list_students() -> list[{"id","name","course","college","year","status","accountant"}]
student_profile(student_id) -> {
  "student": {"id","name","course","college","year","status","annual_entitlement","accountant","region","phone"},
  "facts": [str],                                          # recalled from memory
  "accounts": [{"account","bank","ifsc","holder","first_used","last_used","payouts","state": "verified"|"failed"|"new"|"unverified"}],
  "payouts": [{"payout_id","cycle_label","amount","status","txn_status","sent_on","credited_on"}],
  "observations": [{"id","text","evidence_count","first_seen","last_seen","status"}]
}

team_workload() -> list[{"accountant","focus","pending","on_hold","escalated","released","amount_pending",
                         "avg_turnaround_days","failed_to_chase","delayed_to_chase"}]
```
