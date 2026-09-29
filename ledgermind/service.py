"""Service facade used by the UI (see docs/SERVICE_CONTRACT.md). Plain dicts in, plain dicts out."""
from __future__ import annotations

import logging
import re
import uuid

from . import agent, config, db
from .memory import get_memory

log = logging.getLogger("ledgermind.service")
_STATUS_OUTCOME = {"APPROVED": "APPROVE", "FLAGGED": "FLAG", "ESCALATED": "ESCALATE"}


def _public(inv: dict) -> dict:
    v = db.vendors().get(inv["vendor_id"], {})
    st = db.state(inv["id"]) or {}
    out = {k: val for k, val in inv.items() if not k.startswith("_")}
    out["vendor_name"] = v.get("name", inv["vendor_id"])
    out["status"] = st.get("status", "PENDING")
    return out


def status() -> dict:
    mem = get_memory()
    ok, msg = mem.health()
    return {"memory_backend": mem.backend, "bank_id": config.BANK_ID,
            "llm": "Hindsight reflect" if mem.backend == "hindsight" else "rules engine (offline)",
            "healthy": ok, "message": msg}


def list_invoices(status: str | None = None, vendor_id: str | None = None) -> list[dict]:
    states = db.all_states()
    vendors = db.vendors()
    rows = []
    for inv in db.invoices().values():
        st = states.get(inv["id"], {})
        row = {"id": inv["id"], "number": inv["number"], "vendor_id": inv["vendor_id"],
               "vendor_name": vendors.get(inv["vendor_id"], {}).get("name", inv["vendor_id"]), "date": inv["date"],
               "po_id": inv.get("po_id"), "total": inv["total"], "status": st.get("status", "PENDING"),
               "outcome": st.get("outcome"), "confidence": st.get("confidence")}
        if status and row["status"] != status:
            continue
        if vendor_id and row["vendor_id"] != vendor_id:
            continue
        rows.append(row)
    return sorted(rows, key=lambda r: (r["date"], r["id"]), reverse=True)


def get_invoice(invoice_id: str) -> dict:
    return _public(db.invoices()[invoice_id])


def decide(invoice_id: str, memory_on: bool = True) -> dict:
    d = agent.decide(invoice_id, memory_on=memory_on)
    return {k: v for k, v in d.items() if not k.startswith("_")}


def get_decision(invoice_id: str) -> dict | None:
    d = db.last_decision(invoice_id, memory_on=True)
    return {k: v for k, v in d.items() if not k.startswith("_")} if d else None


def submit_feedback(invoice_id: str, action: str, new_outcome: str | None = None, reason: str = "",
                    user: str = "Priya R.") -> dict:
    return agent.feedback(invoice_id, action, new_outcome, reason, user)


def list_vendors() -> list[dict]:
    counts: dict[str, int] = {}
    for inv in db.invoices().values():
        counts[inv["vendor_id"]] = counts.get(inv["vendor_id"], 0) + 1
    return [{"id": v["id"], "name": v["name"], "category": v["category"], "gstin": v["gstin"],
             "invoice_count": counts.get(v["id"], 0)} for v in db.vendors().values()]


def _vendor_mentioned(rule: dict, vendor: dict) -> bool:
    if rule.get("vendor_id") == vendor["id"] or agent.vendor_tag(vendor["id"]) in (rule.get("tags") or []):
        return True
    first = vendor["name"].split()[0].lower()
    return bool(re.search(rf"\b{re.escape(first)}\b", rule["text"].lower()))


def vendor_profile(vendor_id: str) -> dict:
    vendor = db.vendors()[vendor_id]
    states = db.all_states()
    invs = sorted((i for i in db.invoices().values() if i["vendor_id"] == vendor_id), key=lambda i: i["date"])
    facts: list[str] = []
    try:
        facts = [m["text"] for m in get_memory().recall(
            f"{vendor['name']} payment terms, bank account, contract prices, usual behaviour",
            tags=[agent.vendor_tag(vendor_id)], limit=6)]
    except Exception as e:
        log.warning("profile recall failed: %s", e)
    bank: dict[str, dict] = {}
    for i in invs:
        st = states.get(i["id"], {})
        if st.get("final_outcome") != "APPROVE":
            continue
        b = bank.setdefault(i["bank_account"], {"account": i["bank_account"], "first_seen": i["date"],
                                                "last_seen": i["date"], "count": 0})
        b["last_seen"], b["count"] = i["date"], b["count"] + 1
    return {
        "vendor": {k: vendor[k] for k in ("id", "name", "category", "gstin", "payment_terms", "contact_phone")},
        "facts": facts,
        "bank_history": list(bank.values()),
        "observations": [r for r in learned_rules() if _vendor_mentioned(r, vendor)],
        "timeline": [{"date": i["date"], "invoice_id": i["id"], "number": i["number"], "total": i["total"],
                      "outcome": states.get(i["id"], {}).get("final_outcome") or states.get(i["id"], {}).get("outcome"),
                      "status": states.get(i["id"], {}).get("status", "PENDING")} for i in invs],
    }


def learned_rules() -> list[dict]:
    rules = agent.derived_rules()
    statuses = db.rule_statuses()
    try:
        for o in get_memory().observations():
            rules.append({"id": o["id"], "text": o["text"], "vendor": None, "evidence_count": o["evidence_count"],
                          "first_seen": o["first_seen"], "last_seen": o["last_seen"],
                          "status": statuses.get(o["id"], "active"), "source": "hindsight", "tags": o["tags"]})
    except Exception as e:
        log.warning("observations failed: %s", e)
    return rules


def set_rule_status(rule_id: str, status: str) -> dict:
    if status not in ("active", "confirmed", "retired"):
        return {"ok": False}
    db.set_rule_status(rule_id, status)
    rule = next((r for r in learned_rules() if r["id"] == rule_id), None)
    if rule:
        verb = {"confirmed": "confirmed", "retired": "retired (no longer valid)", "active": "re-activated"}[status]
        try:
            tags = [agent.vendor_tag(rule["vendor_id"])] if rule.get("vendor_id") else (rule.get("tags") or [])
            get_memory().retain(f"AP Manager {verb} the learned rule: \"{rule['text']}\" on {db.now()[:10]}.",
                                tags=tags + ["kind:rule-review"], context="AP manager rule review",
                                metadata={"fact_type": "experience"})
        except Exception as e:
            log.warning("rule review retain failed: %s", e)
    return {"ok": True}


def learning_curve(buckets: int = 8) -> list[dict]:
    firsts = db.first_decisions_on()
    invs = db.invoices()
    decided = sorted((invs[i] for i in firsts if i in invs and invs[i]["date"] < config.DEMO_LIVE_FROM),
                     key=lambda i: (i["date"], i["id"]))  # the replayed history only; live demo invoices excluded
    if not decided:
        return []
    size = max(1, -(-len(decided) // buckets))
    out = []
    for b in range(0, len(decided), size):
        chunk = decided[b:b + size]
        auto = exc = 0
        protected = 0.0
        for inv in chunk:
            d = firsts[inv["id"]]
            if d["outcome"] == "APPROVE":
                auto += 1
            real = [f for f in d["risk_flags"] if f["code"] != "COLD_START"]
            if d["outcome"] != "APPROVE" and real:
                exc += 1
                protected += sum(f.get("at_risk", 0) for f in real)
        out.append({"week": f"W{len(out) + 1}", "from": chunk[0]["date"], "to": chunk[-1]["date"],
                    "invoices": len(chunk), "auto_approved": auto, "human_needed": len(chunk) - auto,
                    "intervention_rate": round((len(chunk) - auto) / len(chunk), 3),
                    "exceptions_caught": exc, "value_protected": round(protected, 2)})
    return out


def ask(question: str) -> dict:
    mem = get_memory()
    try:
        if mem.backend == "hindsight":
            r = mem.hs.reflect(mem.bank, question, budget="mid", include_facts=True)
            cites = []
            if r.based_on and r.based_on.memories:
                cites = [{"id": m.id, "text": m.text, "type": m.type or "world",
                          "date": str(m.occurred_start or m.mentioned_at or "")[:10]} for m in r.based_on.memories[:8]]
            return {"answer": r.text, "citations": cites}
        hits = mem.recall(question, limit=6)
        if not hits:
            return {"answer": "I don't have any memories that match that question yet.", "citations": []}
        return {"answer": "Here is what I remember that is relevant:\n\n" + "\n".join(f"- {h['text']}" for h in hits),
                "citations": [{k: h[k] for k in ("id", "text", "type", "date")} for h in hits]}
    except Exception as e:
        return {"answer": f"Memory is unavailable right now ({e}).", "citations": []}


def upload_invoices(invoices: list[dict]) -> list[str]:
    ids = []
    vendors = db.vendors()
    by_name = {v["name"].lower(): v["id"] for v in vendors.values()}
    by_gstin = {v["gstin"]: v["id"] for v in vendors.values()}
    for raw in invoices:
        vid = raw.get("vendor_id") or by_gstin.get(raw.get("gstin", "")) or by_name.get(str(raw.get("vendor_name", "")).lower())
        if not vid:
            continue
        lines = [{"item": l["item"], "qty": float(l["qty"]), "unit_price": float(l["unit_price"]),
                  "amount": round(float(l["qty"]) * float(l["unit_price"]), 2)} for l in raw.get("lines", [])]
        subtotal = round(sum(l["amount"] for l in lines), 2)
        freight, tax = float(raw.get("freight", 0)), float(raw.get("tax", round(subtotal * 0.18, 2)))
        acct = str(raw.get("bank_account", vendors[vid]["bank_account"]))
        inv = {"id": raw.get("id") or f"UP-{uuid.uuid4().hex[:6].upper()}", "number": raw.get("number", "UNKNOWN"),
               "vendor_id": vid, "date": raw.get("date", db.now()[:10]), "po_id": raw.get("po_id"), "lines": lines,
               "subtotal": subtotal, "freight": freight, "tax": tax,
               "total": float(raw.get("total", subtotal + freight + tax)),
               "bank_account": acct if acct.startswith("****") else f"****{acct[-4:]}",
               "payment_terms": raw.get("payment_terms", vendors[vid]["payment_terms"]), "notes": raw.get("notes", "")}
        db.add_uploaded(inv)
        ids.append(inv["id"])
    return ids
