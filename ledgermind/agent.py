"""The LedgerMind agent: match -> risk checks -> recall -> reflect -> decide -> retain -> learn.

Decision precedence (Section 11 of the SRS):
1. Hard rules (bank change, duplicates, high value, prompt injection, price creep, cold start) are
   evaluated in code first. The model cannot override them.
2. Soft exceptions (freight, tax, quantity, terms, recurring amount) can be cleared only when there is
   supporting evidence in memory: prior human approvals for the same vendor and exception, and
   Hindsight reflect agreeing with confidence >= AUTO_APPROVE_CONFIDENCE (FR-D5).
"""
from __future__ import annotations

import json
import logging
import time

from . import config, db, risk
from .match import three_way_match
from .memory import get_memory

log = logging.getLogger("ledgermind.agent")

ORDER = {"APPROVE": 0, "FLAG": 1, "ESCALATE": 2}
STATUS = {"APPROVE": "APPROVED", "FLAG": "FLAGGED", "ESCALATE": "ESCALATED"}
LEARNABLE = {"FREIGHT_OVERAGE", "TERMS_MISMATCH", "TAX_VARIANCE", "QTY_MISMATCH", "PRICE_VARIANCE",
             "RECURRING_AMOUNT_CHANGE", "NO_PO"}
CODE_LABEL = {
    "FREIGHT_OVERAGE": "freight/surcharge overage", "TERMS_MISMATCH": "payment-term mismatch",
    "TAX_VARIANCE": "tax variance", "QTY_MISMATCH": "quantity mismatch", "PRICE_VARIANCE": "price above PO",
    "RECURRING_AMOUNT_CHANGE": "change in recurring amount", "NO_PO": "non-PO invoice",
}

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["APPROVE", "FLAG", "ESCALATE"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "description": "Plain-language reason, max 120 words, citing past cases."},
    },
    "required": ["outcome", "confidence", "rationale"],
}


def vendor_tag(vendor_id: str) -> str:
    return f"vendor:{vendor_id}"


# ---------- history ("what the agent remembers about the ledger") ----------
def history(inv: dict) -> list[dict]:
    states = db.all_states()
    out = []
    for other in db.invoices().values():
        if other["vendor_id"] != inv["vendor_id"] or other["id"] == inv["id"] or other["date"] > inv["date"]:
            continue
        st = states.get(other["id"])
        if st and st.get("final_outcome"):
            out.append({**other, "final_outcome": st["final_outcome"]})
    return sorted(out, key=lambda h: h["date"])


def _encode_codes(flags: list[dict], match: dict) -> list[str]:
    codes = []
    for f in flags:
        if f["code"] == "FREIGHT_OVERAGE":
            codes.append(f"FREIGHT_OVERAGE:{match['freight']['var_pct']}")
        else:
            codes.append(f["code"])
    return codes


def _decode(code: str) -> tuple[str, float | None]:
    name, _, val = code.partition(":")
    return name, float(val) if val else None


def precedents(vendor_id: str, code: str, before_date: str, value: float | None = None) -> dict:
    """Human decisions on this vendor for this exception type, before the invoice date."""
    rows = [r for r in db.feedback_rows(vendor_id) if r["invoice_date"] < before_date]
    relevant = []
    for r in rows:
        for c in filter(None, (r["risk_codes"] or "").split(",")):
            name, v = _decode(c)
            if name == code:
                relevant.append({**r, "value": v})
    approvals = [r for r in relevant if r["final_outcome"] == "APPROVE"]
    rule_id = f"rule:{vendor_id}:{code}"
    retired = db.rule_statuses().get(rule_id) == "retired"
    max_ok = max((r["value"] for r in approvals if r["value"] is not None), default=None)
    covered = (len(approvals) >= 2 and relevant[-1]["final_outcome"] == "APPROVE" and not retired
               and (value is None or max_ok is None or value <= max_ok * 1.1))
    return {"code": code, "approvals": approvals, "relevant": relevant, "covered": covered, "rule_id": rule_id,
            "max_ok": max_ok}


def _learned_from(p: dict) -> list[str]:
    notes = []
    for r in reversed(p["approvals"]):
        if r["reason"]:
            notes.append(f"Learned from note by {r['user']} on {r['invoice_date']}: \"{r['reason'][:140]}\"")
        if len(notes) == 1:
            break
    if len(p["approvals"]) > 1:
        notes.append(f"{len(p['approvals'])} prior {CODE_LABEL.get(p['code'], p['code'])} cases approved by the AP team")
    return notes


# ---------- decide ----------
def _summary(inv: dict, vendor: dict, match: dict, flags: list[dict]) -> str:
    lines = "; ".join(f"{l['item']} x{l['qty']} @ Rs.{l['unit_price']:,.2f}" for l in inv["lines"])
    fl = "\n".join(f"- [{f['code']}] {f['message']}" for f in flags) or "- none"
    return (f"Invoice {inv['number']} from {vendor['name']} dated {inv['date']}, PO {inv.get('po_id') or 'none'}, "
            f"total Rs.{inv['total']:,.2f} (freight Rs.{inv['freight']:,.2f}, tax Rs.{inv['tax']:,.2f}), "
            f"bank account {inv['bank_account']}, terms {inv['payment_terms']}. Lines: {lines}.\n"
            f"Three-way match: {match['status']}.\nRisk checks:\n{fl}")


def decide(invoice_id: str, memory_on: bool = True, use_reflect: bool = True, persist: bool = True) -> dict:
    t0 = time.time()
    inv = db.invoices()[invoice_id]
    vendor = db.vendors()[inv["vendor_id"]]
    po = db.pos().get(inv.get("po_id") or "")
    grn = db.grns_by_po().get(inv.get("po_id") or "")
    mem = get_memory()
    memory_mode = "on" if memory_on else "off"
    hist = history(inv) if memory_on else []
    match = three_way_match(inv, po, grn)
    flags = risk.check(inv, vendor, match, hist, memory_on=memory_on)
    hard = [f for f in flags if f["hard_rule"]]
    soft = [f for f in flags if not f["hard_rule"]]
    memories: list[dict] = []
    learned: list[str] = []
    model = "rules"

    if not memory_on:
        if hard:
            outcome = max((f["forces"] for f in hard), key=ORDER.get)
            rationale = " ".join(f["message"] for f in hard)
            conf = 0.9
        elif soft:
            outcome, conf = "FLAG", 0.6
            rationale = ("Amount or terms do not match the purchase order. Please review: "
                         + "; ".join(CODE_LABEL.get(f["code"], f["code"]) for f in soft) + ".")
        else:
            outcome, conf = "APPROVE", 0.8
            rationale = "Invoice, PO and GRN match. No history available, so this is a rules-only check."
    else:
        # recall vendor memory (FR-M2)
        try:
            topics = ", ".join(CODE_LABEL.get(f["code"], f["code"]) for f in flags) or "normal invoices"
            memories = mem.recall(f"{vendor['name']} invoices: {topics}; bank account; how the AP team resolved "
                                  f"past exceptions", tags=[vendor_tag(vendor["id"])], limit=6)
        except Exception as e:
            log.warning("recall failed: %s", e)
            memory_mode = "unavailable"

        precs = {f["code"]: precedents(vendor["id"], f["code"], inv["date"],
                                       match["freight"]["var_pct"] if f["code"] == "FREIGHT_OVERAGE" else None)
                 for f in soft}
        for p in precs.values():
            if p["covered"]:
                learned += _learned_from(p)
        all_covered = all(p["covered"] and p["code"] in LEARNABLE for p in precs.values())

        if hard:
            outcome = max((f["forces"] for f in hard), key=ORDER.get)
            conf = 0.95 if outcome == "ESCALATE" else 0.85
            rationale = " ".join(f["message"] for f in hard)
        elif not soft:
            outcome, conf = "APPROVE", 0.93
            rationale = (f"Perfect three-way match. {vendor['name']} has {len(hist)} prior processed invoices with the "
                         f"same bank account {inv['bank_account']} and no open exceptions.")
        elif all_covered:
            outcome, conf = "APPROVE", 0.9
            parts = []
            for f in soft:
                p = precs[f["code"]]
                limit = f" (up to {p['max_ok']:.1f}%)" if p["max_ok"] is not None else ""
                parts.append(f"{f['message']} This matches an approved pattern{limit}: "
                             f"{len(p['approvals'])} prior approvals by the AP team.")
            rationale = " ".join(parts) + " Auto-approved."
        else:
            outcome, conf = "FLAG", 0.7
            rationale = " ".join(f["message"] for f in soft) + " No approved precedent for this vendor yet; needs review."

        # Hindsight reflect (FR-M4): the model can confirm or veto an approval, never loosen a hard rule.
        if use_reflect and memory_mode == "on" and mem.backend == "hindsight" and not hard:
            try:
                ctx = (_summary(inv, vendor, match, flags) + "\n\nPrecedent check from the ledger:\n" +
                       ("\n".join(f"- {c}: {len(p['approvals'])} prior approvals, covered={p['covered']}"
                                  for c, p in precs.items()) or "- no soft exceptions"))
                r = mem.reflect(
                    f"Should LedgerMind APPROVE, FLAG or ESCALATE invoice {inv['number']} from {vendor['name']}? "
                    "Use this vendor's history and the AP team's past decisions. Cite the specific past cases.",
                    context=ctx, schema=DECISION_SCHEMA, tags=[vendor_tag(vendor["id"])])
                s = r["structured"] or {}
                if isinstance(s, str):
                    s = json.loads(s)
                model = "hindsight-reflect"
                memories = (r["memories"] or []) + [m for m in memories if m["id"] not in {x["id"] for x in r["memories"]}]
                r_out, r_conf = s.get("outcome"), float(s.get("confidence", 0))
                if r_out in ORDER:
                    if r_out == "APPROVE" and outcome == "APPROVE" and r_conf >= config.AUTO_APPROVE_CONFIDENCE:
                        conf, rationale = max(conf, r_conf), s.get("rationale") or rationale
                    elif ORDER[r_out] > ORDER[outcome]:
                        outcome, conf, rationale = r_out, r_conf, s.get("rationale") or rationale
                    elif outcome != "APPROVE":
                        rationale = s.get("rationale") or rationale
            except Exception as e:
                log.warning("reflect failed, keeping rule decision: %s", e)
                model = "rules (reflect failed)"

        if memory_mode == "unavailable" and outcome == "APPROVE":  # NFR-R1: never auto-approve blind
            outcome, conf = "FLAG", 0.5
            rationale = "Memory unavailable: rules-only check passed, but auto-approval is disabled. " + rationale

    words = rationale.split()
    if len(words) > 120:
        rationale = " ".join(words[:120]) + "..."

    decision = {
        "invoice_id": invoice_id, "outcome": outcome, "confidence": round(conf, 2), "rationale": rationale,
        "memory_mode": memory_mode, "risk_flags": [{k: f[k] for k in ("code", "severity", "message", "hard_rule", "at_risk")} for f in flags],
        "match": match, "memories": [{k: m.get(k) for k in ("id", "text", "type", "date")} for m in memories[:8]],
        "learned_from": learned[:3], "decided_at": db.now(), "model": model,
        "latency_ms": int((time.time() - t0) * 1000), "_codes": _encode_codes(flags, match),
    }
    if persist:
        db.save_decision(decision)
        if memory_on:
            final = "APPROVE" if outcome == "APPROVE" else None
            db.set_state(invoice_id, STATUS[outcome], outcome, decision["confidence"], final)
            if final:
                retain_outcome(inv, vendor, decision, actor="LedgerMind (auto-approved)", final="APPROVE",
                               action="auto", reason="")
    return decision


# ---------- learning ----------
def retain_outcome(inv: dict, vendor: dict, decision: dict, *, actor: str, final: str, action: str, reason: str,
                   wait: bool = False) -> bool:
    flags = decision.get("risk_flags", [])
    fl = "; ".join(f["message"].rstrip(". ") for f in flags) or "clean three-way match"
    reason = (reason or "").strip().rstrip(".")
    if action == "auto":
        text = (f"On {inv['date']} LedgerMind auto-approved invoice {inv['number']} from {vendor['name']} for "
                f"Rs.{inv['total']:,.0f} (PO {inv.get('po_id') or 'none'}, bank account {inv['bank_account']}). Checks: {fl}.")
    else:
        verb = {"accept": "accepted", "override": "overrode it to", "note": "added a note to"}[action]
        tail = f" {final}" if action == "override" else ""
        text = (f"On {inv['date']} {actor} of the AP team reviewed invoice {inv['number']} from {vendor['name']} for "
                f"Rs.{inv['total']:,.0f} (PO {inv.get('po_id') or 'none'}, bank account {inv['bank_account']}, terms "
                f"{inv['payment_terms']}). LedgerMind recommended {decision['outcome']} because: {fl}. {actor} "
                f"{verb}{tail if action == 'override' else ' the recommendation'}. Final outcome: {final}. "
                f"Reason: {reason or 'none given'}.")
    try:
        get_memory().retain(text, tags=[vendor_tag(vendor["id"]), f"invoice:{inv['id']}", f"kind:{'decision' if action == 'auto' else 'feedback'}"],
                            metadata={"vendor_id": vendor["id"], "invoice_id": inv["id"], "final_outcome": final,
                                      "fact_type": "experience"},
                            timestamp=inv["date"], document_id=f"outcome-{inv['id']}",
                            context="AP invoice decision" if action == "auto" else "AP team feedback", wait=wait)
        return True
    except Exception as e:
        log.warning("retain failed: %s", e)
        return False


def feedback(invoice_id: str, action: str, new_outcome: str | None = None, reason: str = "",
             user: str = "Priya R.", wait: bool = True) -> dict:
    if action not in ("accept", "override", "note"):
        return {"ok": False, "retained": False, "message": f"Unknown action {action}"}
    if action == "override" and (not new_outcome or not reason.strip()):
        return {"ok": False, "retained": False, "message": "An override needs a new outcome and a reason (FR-F2)."}
    d = db.last_decision(invoice_id, memory_on=True)
    if not d:
        return {"ok": False, "retained": False, "message": "Run the agent on this invoice first."}
    inv = db.invoices()[invoice_id]
    vendor = db.vendors()[inv["vendor_id"]]
    final = new_outcome if action == "override" else d["outcome"]
    db.add_feedback(invoice_id=invoice_id, vendor_id=vendor["id"], action=action, agent_outcome=d["outcome"],
                    final_outcome=final, reason=reason.strip(), user=user, risk_codes=d.get("_codes", []),
                    invoice_date=inv["date"])
    db.set_state(invoice_id, STATUS[final], final_outcome=final)
    ok = retain_outcome(inv, vendor, d, actor=user, final=final, action=action, reason=reason, wait=wait)
    return {"ok": True, "retained": ok,
            "message": f"Saved. {'Retained in memory' if ok else 'Memory write queued/failed'}; "
                       f"future {vendor['name']} invoices will use this."}


def derived_rules() -> list[dict]:
    """Vendor rules consolidated from AP-team decisions (shown alongside Hindsight observations)."""
    vendors = db.vendors()
    statuses = db.rule_statuses()
    groups: dict[tuple, list[dict]] = {}
    for r in db.feedback_rows():
        for c in filter(None, (r["risk_codes"] or "").split(",")):
            name, v = _decode(c)
            if name in LEARNABLE:
                groups.setdefault((r["vendor_id"], name), []).append({**r, "value": v})
    rules = []
    for (vid, code), rows in groups.items():
        approvals = [r for r in rows if r["final_outcome"] == "APPROVE"]
        held = len(rows) - len(approvals)
        vname = vendors[vid]["name"]
        label = CODE_LABEL.get(code, code)
        if len(approvals) >= 2 and rows[-1]["final_outcome"] == "APPROVE":
            vals = [r["value"] for r in approvals if r["value"] is not None]
            limit = f" up to {max(vals):.1f}% of PO value" if vals else ""
            text = f"{vname}: {label}{limit} is routinely approved by the AP team."
        elif held >= 1:
            text = f"{vname}: {label} is held for review; the AP team has not accepted it."
        else:
            continue
        rid = f"rule:{vid}:{code}"
        rules.append({"id": rid, "text": text, "vendor": vname, "vendor_id": vid, "evidence_count": len(rows),
                      "first_seen": rows[0]["invoice_date"], "last_seen": rows[-1]["invoice_date"],
                      "status": statuses.get(rid, "active"), "source": "ledger"})
    return sorted(rules, key=lambda r: -r["evidence_count"])
