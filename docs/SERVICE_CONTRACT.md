# LedgerMind service contract (UI <-> engine)

The UI only talks to `ledgermind/service.py`. All functions are synchronous and return plain
dicts/lists (JSON-serialisable). Money is INR as float. Dates are ISO strings `YYYY-MM-DD`.

## Enums
- outcome: `"APPROVE" | "FLAG" | "ESCALATE"`
- invoice status: `"PENDING" | "APPROVED" | "FLAGGED" | "ESCALATED"`
- memory_mode: `"on" | "off" | "unavailable"`
- risk severity: `"high" | "medium" | "low"`

## Functions

```python
status() -> {"memory_backend": "hindsight" | "local", "bank_id": str, "llm": str, "healthy": bool, "message": str}

list_invoices(status: str | None = None, vendor_id: str | None = None) -> list[InvoiceRow]
# InvoiceRow = {"id","number","vendor_id","vendor_name","date","po_id","total","status","outcome"(or None),"confidence"(or None)}

get_invoice(invoice_id) -> Invoice
# Invoice = {"id","number","vendor_id","vendor_name","date","po_id"(or None),
#            "lines":[{"item","qty","unit_price","amount"}], "subtotal","freight","tax","total",
#            "bank_account" (masked e.g. "****4417"), "payment_terms" (e.g. "net-45"), "notes" (str), "status"}

decide(invoice_id, memory_on: bool = True) -> Decision      # runs the agent (may take 2-10 s)
get_decision(invoice_id) -> Decision | None                 # last stored decision, memory ON
# Decision = {
#   "invoice_id", "outcome", "confidence" (0-1), "rationale" (<=120 words), "memory_mode",
#   "risk_flags": [{"code","severity","message","hard_rule": bool}],
#   "match": {"status": "MATCHED"|"VARIANCE"|"NO_PO",
#             "lines": [{"item","inv_qty","po_qty","grn_qty","inv_price","po_price","price_var_pct","qty_ok": bool,"price_ok": bool}],
#             "freight": {"invoice","expected","var_pct"}, "tax": {"invoice","expected","var_pct"},
#             "total": {"invoice","expected","var_pct"}},
#   "memories": [{"id","text","type": "world"|"experience"|"observation","date"}],
#   "learned_from": [str],        # e.g. "Learned from note by Priya R. on 2026-06-14"
#   "decided_at", "model", "latency_ms"
# }

submit_feedback(invoice_id, action: "accept"|"override"|"note", new_outcome: str | None = None,
                reason: str = "", user: str = "Priya R.") -> {"ok": bool, "retained": bool, "message": str}

list_vendors() -> list[{"id","name","category","gstin","invoice_count"}]

vendor_profile(vendor_id) -> {
  "vendor": {"id","name","category","gstin","payment_terms","contact_phone"},
  "facts": [str],                                    # recalled world facts
  "bank_history": [{"account","first_seen","last_seen","count"}],
  "observations": [LearnedRule],
  "timeline": [{"date","invoice_id","number","total","outcome","status"}]
}

learned_rules() -> list[LearnedRule]
# LearnedRule = {"id","text","vendor" (or None),"evidence_count","first_seen","last_seen","status": "active"|"confirmed"|"retired"}
set_rule_status(rule_id, status) -> {"ok": bool}

learning_curve() -> list[{"week": "W1".., "invoices", "auto_approved", "human_needed",
                          "intervention_rate" (0-1), "exceptions_caught", "value_protected"}]

ask(question: str) -> {"answer": str, "citations": [{"id","text","type","date"}]}

upload_invoices(invoices: list[dict]) -> list[str]   # returns new invoice ids
```
