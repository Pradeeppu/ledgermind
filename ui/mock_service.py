"""Realistic in-memory mock of ledgermind.service (see docs/SERVICE_CONTRACT.md).

State lives at module level so it survives Streamlit reruns within one server process.
Demo story: Acme Components Pvt Ltd, AP clerk Priya R.
"""
from __future__ import annotations

import copy
import datetime as _dt
import random
import time
import uuid

BANK_ID = "acme-ap-demo"
TODAY = "2026-09-29"
GST = 0.18

# --------------------------------------------------------------------------- vendors
VENDORS = {
    "V-SHARMA": dict(name="Sharma Logistics", category="Freight & Logistics", gstin="27AAKCS4821M1Z5",
                     payment_terms="net-30", contact_phone="+91 98200 41177", bank=["****2281"]),
    "V-APEX": dict(name="Apex Steel", category="Raw Materials", gstin="24AADCA7734K1Z2",
                   payment_terms="net-45", contact_phone="+91 79 2658 1190", bank=["****7765"]),
    "V-BRIGHT": dict(name="BrightPack", category="Packaging", gstin="29AAHCB5510Q1Z9",
                     payment_terms="net-30", contact_phone="+91 80 4112 7788", bank=["****3310"]),
    "V-KRISHNA": dict(name="Krishna Electricals", category="Electrical Components", gstin="33AAFFK2291B1Z4",
                      payment_terms="net-45", contact_phone="+91 44 2815 6620", bank=["****4417", "****9032"]),
    "V-NOVA": dict(name="Nova Office Supplies", category="Office Supplies", gstin="27AAGCN8812D1Z1",
                   payment_terms="net-15", contact_phone="+91 22 6634 1020", bank=["****5521"]),
    "V-VERTEX": dict(name="Vertex IT Services", category="IT Services", gstin="36AAECV3345H1Z7",
                     payment_terms="net-30", contact_phone="+91 40 6789 2233", bank=["****8840"]),
    "V-GREEN": dict(name="GreenLeaf Chemicals", category="Chemicals", gstin="24AAJCG6612L1Z3",
                    payment_terms="net-45", contact_phone="+91 265 233 4410", bank=["****1197"]),
    "V-METRO": dict(name="Metro Facility Services", category="Facility Management", gstin="27AAMCM9021P1Z6",
                    payment_terms="net-30", contact_phone="+91 22 2493 5500", bank=["****6604"]),
    "V-ORION": dict(name="Orion Tools", category="Tools & Consumables", gstin="06AAPCO4478E1Z8",
                    payment_terms="net-30", contact_phone="+91 124 455 9012", bank=["****0438"]),
    "V-DELTA": dict(name="Delta Freight Carriers", category="Freight & Logistics", gstin="07AAKCD1180F1Z2",
                    payment_terms="net-15", contact_phone="+91 11 4055 3321", bank=["****7129"]),
}

_INVOICES: dict[str, dict] = {}
_POS: dict[str, dict] = {}
_DECISIONS: dict[str, dict] = {}
_MEMORIES: list[dict] = []
_RULES: list[dict] = []


def _mem(text, mtype, date, vendor=None, tags=()):
    m = dict(id=f"mem-{len(_MEMORIES) + 1:04d}", text=text, type=mtype, date=date,
             vendor=vendor, tags=set(tags))
    _MEMORIES.append(m)
    return m


def _add_invoice(inv_id, number, vendor_id, date, lines, freight=0.0, po=None, bank=None,
                 notes="", status="PENDING", outcome=None, confidence=None, scenario="clean",
                 po_freight=None, grn=None):
    """lines: list of (item, qty, unit_price). po: dict item->(qty, price) or None for NO_PO."""
    v = VENDORS[vendor_id]
    lns = [dict(item=i, qty=q, unit_price=float(p), amount=round(q * p, 2)) for i, q, p in lines]
    subtotal = round(sum(l["amount"] for l in lns), 2)
    tax = round((subtotal + freight) * GST, 2)
    po_id = None
    if po is not None:
        po_id = "PO-" + inv_id.split("-", 1)[1]
        _POS[po_id] = dict(lines=po, freight=freight if po_freight is None else po_freight,
                           grn=grn or {k: q for k, (q, _) in po.items()})
    _INVOICES[inv_id] = dict(
        id=inv_id, number=number, vendor_id=vendor_id, vendor_name=v["name"], date=date, po_id=po_id,
        lines=lns, subtotal=subtotal, freight=float(freight), tax=tax,
        total=round(subtotal + freight + tax, 2), bank_account=bank or v["bank"][0],
        payment_terms=v["payment_terms"], notes=notes, status=status,
        _outcome=outcome, _confidence=confidence, _scenario=scenario,
    )


def _seed():
    rnd = random.Random(7)
    # ---------------- history (decided) ----------------
    weeks = [(_dt.date(2026, 8, 3) + _dt.timedelta(weeks=w)) for w in range(8)]
    months = ["2026-04-28", "2026-05-27", "2026-06-26", "2026-07-28", "2026-08-27"]
    n = 100
    for k, d in enumerate(months):  # Vertex monthly retainer
        n += 1
        _add_invoice(f"INV-{n}", f"VIT/26/{k + 4:02d}", "V-VERTEX", d,
                     [("Managed IT support retainer", 1, 42000)], po={"Managed IT support retainer": (1, 42000)},
                     status="APPROVED", outcome="APPROVE", confidence=0.95)
    apex_prices = [512, 512, 520, 526, 531, 536]
    for k, p in enumerate(apex_prices):  # Apex price creep
        n += 1
        d = (_dt.date(2026, 3, 16) + _dt.timedelta(days=30 * k)).isoformat()
        _add_invoice(f"INV-{n}", f"AS-{4410 + k}", "V-APEX", d, [("MS round rod 12mm (per 100kg)", 40, p)],
                     po={"MS round rod 12mm (per 100kg)": (40, 512)},
                     status="APPROVED" if p < 531 else "FLAGGED", outcome="APPROVE" if p < 531 else "FLAG",
                     confidence=0.9 if p < 531 else 0.72)
    for k in range(7):  # Sharma freight routinely ~2% over
        n += 1
        d = (_dt.date(2026, 4, 6) + _dt.timedelta(days=21 * k)).isoformat()
        base_fr = 18000
        over = round(base_fr * (1 + rnd.uniform(0.015, 0.024)))
        _add_invoice(f"INV-{n}", f"SL/{2026}/{310 + k}", "V-SHARMA", d,
                     [("FTL Pune → Chennai", 2, 38500)], freight=over, po={"FTL Pune → Chennai": (2, 38500)},
                     po_freight=base_fr, status="FLAGGED" if k < 2 else "APPROVED",
                     outcome="FLAG" if k < 2 else "APPROVE", confidence=0.6 if k < 2 else 0.91)
    _add_invoice("INV-150", "BP-2291", "V-BRIGHT", "2026-09-02",
                 [("5-ply corrugated carton 450x300", 2500, 38), ("Stretch wrap roll 23 micron", 60, 410)],
                 po={"5-ply corrugated carton 450x300": (2500, 38), "Stretch wrap roll 23 micron": (60, 410)},
                 status="APPROVED", outcome="APPROVE", confidence=0.94)
    for k in range(4):
        n += 1
        d = (_dt.date(2026, 5, 11) + _dt.timedelta(days=28 * k)).isoformat()
        _add_invoice(f"INV-{n}", f"KE/{880 + k}", "V-KRISHNA", d,
                     [("MCB 32A DP", 120, 485), ("FR PVC cable 2.5 sq mm (90m)", 30, 2150)],
                     po={"MCB 32A DP": (120, 485), "FR PVC cable 2.5 sq mm (90m)": (30, 2150)},
                     bank="****4417", status="APPROVED", outcome="APPROVE", confidence=0.93)
    for vid, item, qty, price in [("V-NOVA", "A4 copier paper 75gsm (ream)", 200, 265),
                                  ("V-GREEN", "Isopropyl alcohol 99% (200L drum)", 4, 21800),
                                  ("V-METRO", "Housekeeping services – monthly", 1, 96000),
                                  ("V-ORION", "Carbide end mill 10mm", 50, 1840)]:
        for k in range(3):
            n += 1
            d = (_dt.date(2026, 6, 8) + _dt.timedelta(days=26 * k + rnd.randint(0, 5))).isoformat()
            fr = 1200 if vid == "V-GREEN" else 0
            _add_invoice(f"INV-{n}", f"{vid[2:5]}-{7000 + n}", vid, d, [(item, qty, price)], freight=fr,
                         po={item: (qty, price)}, po_freight=0 if vid == "V-GREEN" else None,
                         status="APPROVED", outcome="APPROVE", confidence=0.9 + rnd.random() * 0.08)

    # ---------------- pending demo invoices ----------------
    _add_invoice("INV-201", "SL/2026/318", "V-SHARMA", "2026-09-24", [("FTL Pune → Chennai", 2, 38500)],
                 freight=18380, po={"FTL Pune → Chennai": (2, 38500)}, po_freight=18000,
                 notes="Fuel surcharge applied as per diesel index.", scenario="sharma")
    _add_invoice("INV-202", "AS-4416", "V-APEX", "2026-09-25", [("MS round rod 12mm (per 100kg)", 40, 540)],
                 po={"MS round rod 12mm (per 100kg)": (40, 512)}, notes="Revised price as per market.",
                 scenario="apex")
    _add_invoice("INV-203", "BP-2291A", "V-BRIGHT", "2026-09-26",
                 [("5-ply corrugated carton 450x300", 2500, 38), ("Stretch wrap roll 23 micron", 60, 410)],
                 po={"5-ply corrugated carton 450x300": (2500, 38), "Stretch wrap roll 23 micron": (60, 410)},
                 notes="Re-issued invoice.", scenario="bright_dup")
    _add_invoice("INV-204", "KE/884", "V-KRISHNA", "2026-09-26",
                 [("MCB 32A DP", 120, 485), ("FR PVC cable 2.5 sq mm (90m)", 30, 2150)],
                 po={"MCB 32A DP": (120, 485), "FR PVC cable 2.5 sq mm (90m)": (30, 2150)},
                 bank="****9032", notes="Please note our new bank details for remittance.",
                 scenario="krishna")
    _add_invoice("INV-205", "NOS-2026-0931", "V-NOVA", "2026-09-27",
                 [("A4 copier paper 75gsm (ream)", 200, 265), ("Whiteboard marker (box of 10)", 12, 320)],
                 po={"A4 copier paper 75gsm (ream)": (200, 265), "Whiteboard marker (box of 10)": (12, 320)},
                 scenario="clean")
    _add_invoice("INV-206", "VIT/26/09", "V-VERTEX", "2026-09-27",
                 [("Managed IT support retainer", 1, 42000), ("Additional on-site support (32 hrs)", 1, 16000)],
                 scenario="vertex")
    _add_invoice("INV-207", "GLC/0977", "V-GREEN", "2026-09-28", [("Isopropyl alcohol 99% (200L drum)", 4, 21800)],
                 freight=1200, po={"Isopropyl alcohol 99% (200L drum)": (4, 21800)}, po_freight=0,
                 notes="Hazmat handling surcharge.", scenario="green")
    _add_invoice("INV-208", "MFS-SEP-26", "V-METRO", "2026-09-28", [("Housekeeping services – monthly", 1, 96000)],
                 po={"Housekeeping services – monthly": (1, 96000)}, scenario="clean")
    _add_invoice("INV-209", "OT-7788", "V-ORION", "2026-09-28", [("Carbide end mill 10mm", 50, 1840)],
                 po={"Carbide end mill 10mm": (50, 1840)}, grn={"Carbide end mill 10mm": 40},
                 notes="Balance 10 pcs dispatched separately.", scenario="orion")
    _add_invoice("INV-210", "DFC/001", "V-DELTA", "2026-09-29", [("LTL Delhi → Pune", 1, 27500)],
                 freight=0, scenario="delta")

    # ---------------- memory bank ----------------
    _mem("Sharma Logistics freight routinely runs 1.5–2.5% above PO because of the diesel-index fuel surcharge "
         "clause in the 2026 rate contract.", "world", "2026-05-20", "V-SHARMA", ["freight"])
    _mem("Priya R. approved SL/2026/312 with +2.1% freight: 'Fuel surcharge is contractual, approve up to 2.5%'.",
         "experience", "2026-06-14", "V-SHARMA", ["freight"])
    _mem("Pattern: 5 of the last 5 Sharma invoices had freight +1.6% to +2.4% over PO; all approved by a human.",
         "observation", "2026-08-30", "V-SHARMA", ["freight"])
    _mem("Apex Steel MS rod price has risen 512 → 520 → 526 → 531 → 536 over six months against a fixed PO "
         "price of ₹512.", "observation", "2026-08-15", "V-APEX", ["price"])
    _mem("Procurement (Rahul M.) note: Apex rate contract fixes ₹512/100kg until Dec 2026; any increase needs "
         "a signed amendment.", "world", "2026-07-02", "V-APEX", ["price"])
    _mem("Priya R. flagged AS-4414 (₹531): 'Price creep – ask procurement to renegotiate'.", "experience",
         "2026-07-18", "V-APEX", ["price"])
    _mem("BrightPack invoice BP-2291 for ₹1,41,128 was paid on 2026-09-10 (UTR ending 5512).", "experience",
         "2026-09-10", "V-BRIGHT", ["duplicate"])
    _mem("BrightPack has previously re-issued invoices with an 'A' suffix after courier loss (BP-1877A in 2025) – "
         "these were duplicates of already-paid invoices.", "observation", "2026-03-04", "V-BRIGHT", ["duplicate"])
    _mem("Krishna Electricals has been paid to account ****4417 (HDFC, Chennai) on all 14 invoices since 2024.",
         "world", "2026-08-20", "V-KRISHNA", ["bank"])
    _mem("Company policy: any vendor bank-detail change must be verified by phone call-back to the number on the "
         "vendor master before payment.", "world", "2026-01-05", None, ["bank", "policy"])
    _mem("Finance alert: two Chennai suppliers reported email-compromise attempts requesting bank changes in Sep 2026.",
         "experience", "2026-09-12", None, ["bank"])
    _mem("Vertex IT retainer is ₹42,000 every month; no variation in the last 6 invoices.", "observation",
         "2026-08-28", "V-VERTEX", ["baseline"])
    _mem("Vertex IT contract: additional on-site support billable at ₹500/hr only with IT-head pre-approval.",
         "world", "2026-04-01", "V-VERTEX", ["baseline"])
    _mem("GreenLeaf charges a fixed ₹1,200 hazmat handling surcharge per drum consignment; approved by Priya R. "
         "three times.", "observation", "2026-08-05", "V-GREEN", ["freight"])
    _mem("Orion Tools ships partial quantities; Priya R.: 'pay on GRN quantity, balance on next GRN'.",
         "experience", "2026-07-22", "V-ORION", ["grn"])
    _mem("Nova Office Supplies invoices have matched PO and GRN exactly on 9 of 9 occasions.", "observation",
         "2026-08-18", "V-NOVA", ["clean"])
    _mem("Metro Facility monthly housekeeping invoice is fixed at ₹96,000 per contract MFS-2026.", "world",
         "2026-04-01", "V-METRO", ["clean"])
    _mem("Delta Freight Carriers onboarded on 2026-09-22; vendor master KYC completed, no PO issued yet.", "world",
         "2026-09-22", "V-DELTA", ["new"])

    rules = [
        ("Sharma Logistics freight overage up to 2.5% is contractual fuel surcharge – approve.", "V-SHARMA", 7,
         "2026-05-20", "2026-09-14", "confirmed"),
        ("Apex Steel unit price creeping above ₹512 PO rate – flag and route to procurement.", "V-APEX", 4,
         "2026-06-18", "2026-09-01", "active"),
        ("BrightPack 'A'-suffix invoice numbers are likely duplicates of paid invoices.", "V-BRIGHT", 2,
         "2025-11-03", "2026-09-10", "active"),
        ("Any bank-account change requires call-back verification before payment (hard rule).", None, 3,
         "2026-01-05", "2026-09-12", "confirmed"),
        ("Vertex IT monthly baseline is ₹42,000; extras need IT-head approval.", "V-VERTEX", 6,
         "2026-04-28", "2026-08-28", "active"),
        ("GreenLeaf ₹1,200 hazmat surcharge is expected on every drum consignment.", "V-GREEN", 3,
         "2026-06-10", "2026-08-05", "active"),
        ("Orion Tools: pay on GRN quantity when shipment is partial.", "V-ORION", 2, "2026-06-30",
         "2026-07-22", "active"),
        ("Metro Facility quarterly deep-clean invoices can be auto-approved.", "V-METRO", 1, "2026-04-02",
         "2026-04-02", "retired"),
    ]
    for i, (text, v, ev, fs, ls, st) in enumerate(rules, 1):
        _RULES.append(dict(id=f"rule-{i:02d}", text=text, vendor=VENDORS[v]["name"] if v else None,
                           evidence_count=ev, first_seen=fs, last_seen=ls, status=st, _vendor_id=v))


_seed()


# --------------------------------------------------------------------------- helpers
def _pct(a, b):
    return round((a - b) / b * 100, 2) if b else (0.0 if not a else 100.0)


def _match(inv):
    po = _POS.get(inv["po_id"]) if inv["po_id"] else None
    if not po:
        return dict(status="NO_PO", lines=[],
                    freight=dict(invoice=inv["freight"], expected=None, var_pct=None),
                    tax=dict(invoice=inv["tax"], expected=round((inv["subtotal"] + inv["freight"]) * GST, 2),
                             var_pct=0.0),
                    total=dict(invoice=inv["total"], expected=None, var_pct=None))
    rows, ok = [], True
    exp_sub = 0.0
    for l in inv["lines"]:
        pq, pp = po["lines"].get(l["item"], (0, 0))
        gq = po["grn"].get(l["item"], 0)
        pv = _pct(l["unit_price"], pp)
        qty_ok = l["qty"] <= min(pq, gq)
        price_ok = abs(pv) <= 0.5
        ok = ok and qty_ok and price_ok
        exp_sub += min(pq, gq, l["qty"]) * pp
        rows.append(dict(item=l["item"], inv_qty=l["qty"], po_qty=pq, grn_qty=gq, inv_price=l["unit_price"],
                         po_price=pp, price_var_pct=pv, qty_ok=qty_ok, price_ok=price_ok))
    ef = po["freight"]
    fv = _pct(inv["freight"], ef)
    ok = ok and abs(fv) <= 0.5
    etax = round((exp_sub + ef) * GST, 2)
    etot = round(exp_sub + ef + etax, 2)
    return dict(status="MATCHED" if ok else "VARIANCE", lines=rows,
                freight=dict(invoice=inv["freight"], expected=ef, var_pct=fv),
                tax=dict(invoice=inv["tax"], expected=etax, var_pct=_pct(inv["tax"], etax)),
                total=dict(invoice=inv["total"], expected=etot, var_pct=_pct(inv["total"], etot)))


def _mems(vendor_id, tags=None, extra_global=False, limit=5):
    out = []
    for m in _MEMORIES:
        if (m["vendor"] == vendor_id and (not tags or m["tags"] & set(tags))) or \
                (extra_global and m["vendor"] is None and tags and m["tags"] & set(tags)):
            out.append(dict(id=m["id"], text=m["text"], type=m["type"], date=m["date"]))
    return sorted(out, key=lambda x: x["date"], reverse=True)[:limit]


def _flag(code, sev, msg, hard=False):
    return dict(code=code, severity=sev, message=msg, hard_rule=hard)


def _inr(x):
    s = f"{x:,.0f}"
    # Indian grouping
    x = int(round(x))
    t = str(abs(x))
    if len(t) > 3:
        head, tail = t[:-3], t[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    else:
        s = t
    return "₹" + s


def _decide_logic(inv, m, memory_on):
    sc = inv["_scenario"]
    v = inv["vendor_id"]
    fv = m["freight"]["var_pct"]
    if not memory_on:
        # generic, rule-of-thumb agent with no vendor history
        if sc == "sharma":
            return "FLAG", 0.58, (f"Freight of {_inr(inv['freight'])} exceeds the PO amount by {fv:.1f}%. "
                                 "Amount exceeds PO; manual review required."), \
                [_flag("FREIGHT_VARIANCE", "medium", f"Freight {fv:+.1f}% vs PO")], []
        if sc == "apex":
            return "FLAG", 0.61, "Unit price differs from PO price. Amount exceeds PO; please review.", \
                [_flag("PRICE_VARIANCE", "medium", "Unit price +5.5% vs PO")], []
        if sc == "bright_dup":
            return "APPROVE", 0.88, "Invoice lines, quantities and prices match the PO and GRN. Approve for payment.", [], []
        if sc == "krishna":
            return "APPROVE", 0.91, "Three-way match is clean: quantities and prices agree with PO and GRN. Approve.", [], []
        if sc == "vertex":
            return "FLAG", 0.55, "No purchase order referenced. Cannot perform three-way match; manual review needed.", \
                [_flag("NO_PO", "medium", "No PO on invoice")], []
        if sc == "green":
            return "FLAG", 0.57, "Freight charged but PO has no freight. Amount exceeds PO.", \
                [_flag("FREIGHT_VARIANCE", "medium", "Unexpected freight ₹1,200")], []
        if sc == "orion":
            return "FLAG", 0.6, "Invoiced quantity exceeds received quantity. Review required.", \
                [_flag("QTY_EXCEEDS_GRN", "medium", "Invoiced 50, received 40")], []
        if sc == "delta":
            return "FLAG", 0.5, "No purchase order referenced. Manual review required.", \
                [_flag("NO_PO", "medium", "No PO on invoice")], []
        return "APPROVE", 0.9, "Invoice matches PO and GRN within tolerance. Approve for payment.", [], []

    # ---------------- memory ON ----------------
    if sc == "sharma":
        return "APPROVE", 0.93, (
            f"Freight is {fv:+.1f}% over PO, inside the 2.5% fuel-surcharge band that Priya R. approved on "
            "2026-06-14 and that has been accepted on every Sharma invoice since. Line items match PO and GRN. "
            "Approve."), [_flag("FREIGHT_VARIANCE", "low", f"Freight {fv:+.1f}% vs PO – within learned 2.5% band")], \
            ["Learned from note by Priya R. on 2026-06-14", "Learned from 5 prior approved Sharma invoices"]
    if sc == "apex":
        return "FLAG", 0.9, (
            "₹540 is the 5th consecutive increase (512 → 540, +5.5%) against a rate contract fixed at ₹512 until "
            "Dec 2026. No signed amendment on file. Flag and route to procurement for renegotiation; excess "
            f"exposure {_inr(40 * 28 * 1.18)}."), \
            [_flag("PRICE_CREEP", "high", "Unit price +5.5% vs contract; 5th rise in 6 months"),
             _flag("NO_AMENDMENT", "medium", "Price change without signed contract amendment")], \
            ["Learned from price trend across 6 Apex invoices", "Learned from note by Priya R. on 2026-07-18"]
    if sc == "bright_dup":
        return "FLAG", 0.96, (
            "BP-2291A is identical in lines and amount to BP-2291, already paid on 2026-09-10. BrightPack has "
            "re-issued 'A'-suffix duplicates before (BP-1877A). Hold payment; confirm with vendor."), \
            [_flag("DUPLICATE_INVOICE", "high", "Same lines & total as paid invoice BP-2291", True)], \
            ["Learned from payment record of BP-2291 on 2026-09-10", "Learned from BP-1877A duplicate in 2025"]
    if sc == "krishna":
        return "ESCALATE", 0.97, (
            "Remittance account changed from ****4417 (used on all 14 prior invoices) to ****9032, requested "
            "inside the invoice note. Policy requires phone call-back to the vendor-master number before payment; "
            "matches the Sep 2026 email-compromise pattern. Escalate to finance controller."), \
            [_flag("BANK_ACCOUNT_CHANGED", "high", "Bank ****4417 → ****9032", True),
             _flag("CHANGE_VIA_INVOICE", "medium", "Bank change requested in invoice notes, not via vendor master")], \
            ["Learned from 14 payments to ****4417", "Learned from finance alert on 2026-09-12"]
    if sc == "vertex":
        return "FLAG", 0.89, (
            "Total ₹58,000 (+GST) is 38% above the ₹42,000 monthly baseline seen on the last 6 invoices. The "
            "₹16,000 on-site support line needs IT-head pre-approval per contract. Flag for approval evidence."), \
            [_flag("ABOVE_BASELINE", "medium", "+38% vs 6-month baseline ₹42,000"),
             _flag("NO_PO", "low", "Retainer invoices are billed without PO")], \
            ["Learned from 6-month Vertex billing baseline"]
    if sc == "green":
        return "APPROVE", 0.9, (
            "₹1,200 freight is GreenLeaf's standard hazmat handling surcharge, approved three times by Priya R. "
            "Drum quantity and price match PO and GRN. Approve."), \
            [_flag("FREIGHT_VARIANCE", "low", "Hazmat surcharge ₹1,200 – expected")], \
            ["Learned from 3 approved GreenLeaf invoices"]
    if sc == "orion":
        return "FLAG", 0.86, (
            "Only 40 of 50 end mills received. Following the learned practice for Orion, approve payment for the "
            f"GRN quantity ({_inr(40 * 1840 * 1.18)}) and hold the balance until the next GRN."), \
            [_flag("QTY_EXCEEDS_GRN", "medium", "Invoiced 50, received 40 – partial pay")], \
            ["Learned from note by Priya R. on 2026-07-22"]
    if sc == "delta":
        return "FLAG", 0.74, (
            "First invoice from Delta Freight (onboarded 2026-09-22) and no PO exists. No behavioural history yet, "
            "so the agent cannot vouch for it. Request a PO from logistics before approval."), \
            [_flag("NEW_VENDOR", "medium", "No invoice history"), _flag("NO_PO", "medium", "No PO on invoice")], []
    return "APPROVE", 0.95, (
        f"Clean three-way match. {inv['vendor_name']} has matched PO and GRN on every prior invoice; bank account "
        "and terms unchanged. Approve for payment."), [], [f"Learned from {inv['vendor_name']} invoice history"]


_TAGS = dict(sharma=["freight"], apex=["price"], bright_dup=["duplicate"], krishna=["bank"],
             vertex=["baseline"], green=["freight"], orion=["grn"], delta=["new"], clean=None)


def _row(inv):
    d = _DECISIONS.get(inv["id"])
    return dict(id=inv["id"], number=inv["number"], vendor_id=inv["vendor_id"], vendor_name=inv["vendor_name"],
                date=inv["date"], po_id=inv["po_id"], total=inv["total"], status=inv["status"],
                outcome=d["outcome"] if d else inv["_outcome"], confidence=d["confidence"] if d else inv["_confidence"])


def _public(inv):
    return {k: copy.deepcopy(v) for k, v in inv.items() if not k.startswith("_")}


def _get(invoice_id):
    if invoice_id not in _INVOICES:
        raise KeyError(f"Unknown invoice {invoice_id}")
    return _INVOICES[invoice_id]


# --------------------------------------------------------------------------- contract
def status():
    return dict(memory_backend="local", bank_id=BANK_ID, llm="mock-llm", healthy=True,
                message="Mock service (UI demo data) – engine not connected")


def list_invoices(status=None, vendor_id=None):
    rows = [_row(i) for i in _INVOICES.values()
            if (not status or i["status"] == status) and (not vendor_id or i["vendor_id"] == vendor_id)]
    return sorted(rows, key=lambda r: (r["status"] != "PENDING", r["date"]), reverse=False)


def get_invoice(invoice_id):
    return _public(_get(invoice_id))


def decide(invoice_id, memory_on=True):
    inv = _get(invoice_id)
    t0 = time.time()
    time.sleep(0.35)
    m = _match(inv)
    outcome, conf, rationale, flags, learned = _decide_logic(inv, m, memory_on)
    tags = _TAGS.get(inv["_scenario"])
    mems = _mems(inv["vendor_id"], tags, extra_global=True) if memory_on else []
    if memory_on and not mems:
        mems = _mems(inv["vendor_id"])
    d = dict(invoice_id=invoice_id, outcome=outcome, confidence=round(conf, 2), rationale=rationale,
             memory_mode="on" if memory_on else "off", risk_flags=flags, match=m, memories=mems,
             learned_from=learned if memory_on else [],
             decided_at=_dt.datetime.now().isoformat(timespec="seconds"),
             model="mock-llm", latency_ms=int((time.time() - t0) * 1000))
    if memory_on:
        _DECISIONS[invoice_id] = d
        if inv["status"] == "PENDING" and outcome == "APPROVE" and conf >= 0.85:
            inv["status"] = "APPROVED"
        elif inv["status"] == "PENDING" and outcome == "FLAG":
            inv["status"] = "FLAGGED"
        elif inv["status"] == "PENDING" and outcome == "ESCALATE":
            inv["status"] = "ESCALATED"
    return copy.deepcopy(d)


def get_decision(invoice_id):
    _get(invoice_id)
    d = _DECISIONS.get(invoice_id)
    return copy.deepcopy(d) if d else None


_STATUS_FOR = {"APPROVE": "APPROVED", "FLAG": "FLAGGED", "ESCALATE": "ESCALATED"}


def submit_feedback(invoice_id, action, new_outcome=None, reason="", user="Priya R."):
    inv = _get(invoice_id)
    d = _DECISIONS.get(invoice_id)
    if action == "accept":
        if not d:
            return dict(ok=False, retained=False, message="Run the agent before accepting a decision.")
        inv["status"] = _STATUS_FOR[d["outcome"]]
        _mem(f"{user} accepted agent decision {d['outcome']} on {inv['number']} ({inv['vendor_name']})."
             + (f" Note: {reason}" if reason else ""), "experience", TODAY, inv["vendor_id"])
        return dict(ok=True, retained=True, message=f"Decision accepted and retained to memory bank '{BANK_ID}'.")
    if action == "override":
        if new_outcome not in _STATUS_FOR:
            return dict(ok=False, retained=False, message="new_outcome must be APPROVE, FLAG or ESCALATE.")
        if not reason.strip():
            return dict(ok=False, retained=False, message="A reason is required to override.")
        old = d["outcome"] if d else "—"
        inv["status"] = _STATUS_FOR[new_outcome]
        if d:
            d["outcome"] = new_outcome
        _mem(f"{user} overrode {old} → {new_outcome} on {inv['number']} ({inv['vendor_name']}): '{reason}'.",
             "experience", TODAY, inv["vendor_id"])
        return dict(ok=True, retained=True,
                    message=f"Override recorded ({old} → {new_outcome}). The agent will remember why.")
    if action == "note":
        if not reason.strip():
            return dict(ok=False, retained=False, message="Note is empty.")
        _mem(f"Note by {user} on {inv['number']}: {reason}", "experience", TODAY, inv["vendor_id"])
        return dict(ok=True, retained=True, message="Note retained to memory.")
    return dict(ok=False, retained=False, message=f"Unknown action '{action}'.")


def list_vendors():
    out = []
    for vid, v in VENDORS.items():
        out.append(dict(id=vid, name=v["name"], category=v["category"], gstin=v["gstin"],
                        invoice_count=sum(1 for i in _INVOICES.values() if i["vendor_id"] == vid)))
    return out


def vendor_profile(vendor_id):
    if vendor_id not in VENDORS:
        raise KeyError(f"Unknown vendor {vendor_id}")
    v = VENDORS[vendor_id]
    invs = sorted([i for i in _INVOICES.values() if i["vendor_id"] == vendor_id], key=lambda i: i["date"])
    bank = {}
    for i in invs:
        b = bank.setdefault(i["bank_account"], dict(account=i["bank_account"], first_seen=i["date"],
                                                   last_seen=i["date"], count=0))
        b["last_seen"] = i["date"]
        b["count"] += 1
    facts = [m["text"] for m in _MEMORIES if m["vendor"] == vendor_id and m["type"] == "world"]
    facts.insert(0, f"GSTIN {v['gstin']} · {v['category']} · terms {v['payment_terms']}")
    obs = [{k: val for k, val in r.items() if not k.startswith("_")} for r in _RULES if r["_vendor_id"] == vendor_id]
    for m in _MEMORIES:
        if m["vendor"] == vendor_id and m["type"] == "observation":
            obs.append(dict(id=m["id"], text=m["text"], vendor=v["name"], evidence_count=1,
                            first_seen=m["date"], last_seen=m["date"], status="active"))
    timeline = [dict(date=i["date"], invoice_id=i["id"], number=i["number"], total=i["total"],
                     outcome=_row(i)["outcome"], status=i["status"]) for i in invs]
    return dict(vendor=dict(id=vendor_id, name=v["name"], category=v["category"], gstin=v["gstin"],
                            payment_terms=v["payment_terms"], contact_phone=v["contact_phone"]),
                facts=facts, bank_history=list(bank.values()), observations=obs, timeline=timeline)


def learned_rules():
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in _RULES]


def set_rule_status(rule_id, status):
    for r in _RULES:
        if r["id"] == rule_id and status in ("active", "confirmed", "retired"):
            r["status"] = status
            return dict(ok=True)
    return dict(ok=False)


def learning_curve():
    rates = [0.62, 0.55, 0.46, 0.38, 0.29, 0.21, 0.15, 0.11]
    vols = [38, 41, 44, 40, 46, 49, 47, 52]
    caught = [1, 2, 2, 3, 3, 4, 4, 5]
    protected = [18500, 42000, 36800, 141128, 97000, 188400, 121500, 257300]
    out = []
    for w, (r, n, c, p) in enumerate(zip(rates, vols, caught, protected), 1):
        human = round(n * r)
        out.append(dict(week=f"W{w}", invoices=n, auto_approved=n - human, human_needed=human,
                        intervention_rate=r, exceptions_caught=c, value_protected=float(p)))
    return out


def _cite(*ids):
    return [dict(id=m["id"], text=m["text"], type=m["type"], date=m["date"]) for m in _MEMORIES if m["id"] in ids]


def ask(question):
    q = question.lower()
    time.sleep(0.3)

    def by(vendor, tags=None):
        return [dict(id=m["id"], text=m["text"], type=m["type"], date=m["date"]) for m in _MEMORIES
                if m["vendor"] == vendor and (not tags or m["tags"] & set(tags))]

    if "sharma" in q or "freight" in q:
        return dict(answer=("Sharma Logistics' rate contract includes a diesel-index fuel surcharge, so freight "
                            "typically lands 1.5–2.5% above the PO. In June, Priya R. approved SL/2026/312 at +2.1% "
                            "with the note 'Fuel surcharge is contractual, approve up to 2.5%'. Since then the agent "
                            "auto-approves Sharma freight inside that band."), citations=by("V-SHARMA"))
    if "krishna" in q or "bank" in q:
        return dict(answer=("Yes. Krishna Electricals was paid to ****4417 on every invoice since 2024. Invoice KE/884 "
                            "(2026-09-26) asks for remittance to a new account ****9032 via the invoice note. The "
                            "agent escalated it: policy requires call-back verification, and finance flagged similar "
                            "email-compromise attempts in September."),
                    citations=by("V-KRISHNA") + [c for c in by(None, ["bank"])])
    if "creep" in q or "price" in q or "apex" in q:
        return dict(answer=("Apex Steel is the clear case: MS rod went 512 → 520 → 526 → 531 → 536 → 540 per 100 kg "
                            "(+5.5%) against a contract fixed at ₹512 until December. Vertex IT's latest bill is also "
                            "38% above its ₹42,000 baseline, though that is scope, not unit price."),
                    citations=by("V-APEX") + by("V-VERTEX", ["baseline"])[:1])
    if "duplicate" in q or "brightpack" in q:
        return dict(answer="BP-2291A duplicates BP-2291, which was paid on 2026-09-10. The agent flagged it.",
                    citations=by("V-BRIGHT"))
    return dict(answer=("I searched the memory bank but found nothing specific. Try asking about a vendor by name, "
                        "bank changes, freight or price trends."), citations=[])


def upload_invoices(invoices):
    ids = []
    name_to_id = {v["name"].lower(): k for k, v in VENDORS.items()}
    for raw in invoices:
        vid = raw.get("vendor_id") or name_to_id.get(str(raw.get("vendor_name", "")).lower())
        if vid not in VENDORS:
            vid = "V-DELTA"
        new_id = f"INV-U{uuid.uuid4().hex[:5].upper()}"
        lines = raw.get("lines") or [dict(item=raw.get("item", "Uploaded item"), qty=raw.get("qty", 1),
                                          unit_price=raw.get("unit_price", raw.get("total", 0)))]
        _add_invoice(new_id, str(raw.get("number", new_id)), vid, str(raw.get("date", TODAY)),
                     [(l["item"], float(l.get("qty", 1)), float(l.get("unit_price", 0))) for l in lines],
                     freight=float(raw.get("freight", 0) or 0), bank=raw.get("bank_account"),
                     notes=str(raw.get("notes", "")), scenario="upload")
        ids.append(new_id)
    return ids
