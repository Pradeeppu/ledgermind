"""Deterministic risk checks (FR-R1..R4, BR-1..BR-9).

A flag with `forces` set is a hard rule: it is evaluated in code and the LLM can never override it.
Soft flags (forces=None) are the ones the agent may clear using learned vendor behaviour.

`history` is the vendor's previously processed invoices (the agent's memory of the ledger). With
memory OFF it is empty, so history-based checks (bank baseline, duplicates, price creep, cold start)
cannot run -- exactly what a stateless system would miss.
"""
from __future__ import annotations

import re
import statistics
from datetime import date

from . import config

INJECTION = re.compile(
    r"(ignore (all |any )?(previous |prior |above )?(rules|instructions|checks))|(approve (this|the) invoice (immediately|now|without))"
    r"|(system prompt)|(you are now)|(disregard (the|all) )", re.I)
SUFFIX = re.compile(r"^(.*?)(?:[-/ ]?(?:A|B|R|REV|DUP|\d))$", re.I)


def _flag(code, severity, message, forces=None, at_risk=0.0):
    return {"code": code, "severity": severity, "message": message, "hard_rule": forces is not None, "forces": forces,
            "at_risk": round(max(at_risk, 0.0), 2)}


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def check(inv: dict, vendor: dict, match: dict, history: list[dict], memory_on: bool = True) -> list[dict]:
    flags: list[dict] = []
    text = f"{inv.get('notes', '')} " + " ".join(l["item"] for l in inv["lines"])

    # ---- hard rules evaluated before the LLM ----
    if INJECTION.search(text):
        flags.append(_flag("PROMPT_INJECTION", "high",
                           "Invoice text contains instructions aimed at the approval system; treated as untrusted and flagged.", "FLAG"))
    if inv["total"] > config.HIGH_VALUE_LIMIT:
        flags.append(_flag("HIGH_VALUE", "medium",
                           f"Total Rs.{inv['total']:,.0f} is above the Rs.{config.HIGH_VALUE_LIMIT:,.0f} limit; a human must approve.", "FLAG"))

    if memory_on:
        paid = [h for h in history if h.get("final_outcome") == "APPROVE"]
        accounts: dict[str, list[dict]] = {}
        for h in paid:
            accounts.setdefault(h["bank_account"], []).append(h)
        if accounts and inv["bank_account"] not in accounts:
            main_acct, used = max(accounts.items(), key=lambda kv: len(kv[1]))
            first = min(u["date"] for u in used)
            flags.append(_flag("BANK_CHANGE", "high",
                               f"{len(used)} paid invoices since {first} went to account {main_acct}; this invoice asks for "
                               f"{inv['bank_account']}. Verify by phone using {vendor.get('contact_phone', 'the number on file')} "
                               "(never the number on the invoice).", "ESCALATE", inv["total"]))

        for h in history:
            if h["id"] == inv["id"]:
                continue
            if h["number"].strip().upper() == inv["number"].strip().upper():
                flags.append(_flag("EXACT_DUPLICATE", "high", f"Invoice number {inv['number']} was already processed on {h['date']}.", "ESCALATE", inv["total"]))
                break
            base = SUFFIX.match(inv["number"])
            suffixed = bool(base) and base.group(1).upper() == h["number"].upper()
            same_po = inv.get("po_id") and inv.get("po_id") == h.get("po_id")
            same_amt = abs(inv["total"] - h["total"]) <= 0.01 * max(h["total"], 1)
            if (suffixed or same_po or (same_amt and _days(inv["date"], h["date"]) <= 3)) and _days(inv["date"], h["date"]) <= 30:
                why = "suffixed invoice number" if suffixed else ("same PO" if same_po else "same amount within days")
                flags.append(_flag("NEAR_DUPLICATE", "high",
                                   f"Likely duplicate of {h['number']} ({why}; Rs.{h['total']:,.0f} on {h['date']}, "
                                   f"{_days(inv['date'], h['date'])} days earlier).", "FLAG", inv["total"]))
                break

        for l in inv["lines"]:
            seen = sorted((h["date"], hl["unit_price"]) for h in history for hl in h["lines"] if hl["item"] == l["item"])
            if seen:
                first_date, first_price = seen[0]
                rise = (l["unit_price"] - first_price) / first_price * 100 if first_price else 0
                if rise > config.PRICE_CREEP_BAND_PCT:
                    flags.append(_flag("PRICE_CREEP", "medium",
                                       f"{l['item']}: unit price Rs.{l['unit_price']:,.0f} is {rise:.1f}% above the first-seen "
                                       f"Rs.{first_price:,.0f} ({first_date}), over the {config.PRICE_CREEP_BAND_PCT:.0f}% band "
                                       f"across {len(seen) + 1} invoices. Notify procurement.", "FLAG",
                                       (l["unit_price"] - first_price) * l["qty"]))

        if len(history) < config.COLD_START_MIN_INVOICES:
            flags.append(_flag("COLD_START", "low",
                               f"Only {len(history)} prior invoice(s) from this vendor; not enough history to auto-approve.", "FLAG"))

        if match["status"] == "NO_PO" and history:
            amounts = [h["total"] for h in history if not h.get("po_id")]
            if amounts:
                med = statistics.median(amounts)
                if abs(inv["total"] - med) > 0.05 * med:
                    flags.append(_flag("RECURRING_AMOUNT_CHANGE", "medium",
                                       f"Recurring non-PO bill is usually Rs.{med:,.0f}; this one is Rs.{inv['total']:,.0f} "
                                       f"({(inv['total'] - med) / med * 100:+.0f}%).", at_risk=inv["total"] - med))

    # ---- soft, match-based checks (a stateless system sees these too) ----
    if match["status"] == "NO_PO" and not (memory_on and history):
        flags.append(_flag("NO_PO", "medium", "Invoice has no purchase order and no recurring pattern to compare with."))
    if match["status"] != "NO_PO":
        for l in match["lines"]:
            if not l["qty_ok"]:
                flags.append(_flag("QTY_MISMATCH", "medium",
                                   f"{l['item']}: invoiced {l['inv_qty']}, PO {l['po_qty']}, received (GRN) {l['grn_qty']}.",
                                   at_risk=(l["inv_qty"] - min(l["po_qty"], l["grn_qty"] if l["grn_qty"] is not None else l["po_qty"])) * l["inv_price"]))
            if not l["price_ok"]:
                flags.append(_flag("PRICE_VARIANCE", "medium",
                                   f"{l['item']}: invoice price Rs.{l['inv_price']:,.2f} vs PO Rs.{l['po_price']:,.2f} ({l['price_var_pct']:+.1f}%)."))
        f = match["freight"]
        if f["var_pct"] and f["var_pct"] > config.TOLERANCE_PCT:
            flags.append(_flag("FREIGHT_OVERAGE", "medium",
                               f"Freight/surcharge Rs.{f['invoice']:,.0f} vs Rs.{f['expected']:,.0f} on PO ({f['var_pct']:.1f}% of PO value)."))
        t = match["tax"]
        if t["var_pct"] and abs(t["var_pct"]) > config.TOLERANCE_PCT:
            flags.append(_flag("TAX_VARIANCE", "medium",
                               f"Tax Rs.{t['invoice']:,.0f} vs expected Rs.{t['expected']:,.0f} ({t['var_pct']:+.1f}%). Check GST rate per item.",
                               at_risk=t["invoice"] - t["expected"]))
    if inv.get("payment_terms") and vendor.get("payment_terms") and inv["payment_terms"] != vendor["payment_terms"]:
        flags.append(_flag("TERMS_MISMATCH", "low",
                           f"Invoice terms {inv['payment_terms']} differ from vendor master {vendor['payment_terms']}."))
    return flags
