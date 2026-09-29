"""Three-way match: Invoice <-> Purchase Order <-> Goods Receipt Note (FR-X1, FR-X2)."""
from __future__ import annotations

from . import config


def _pct(actual: float, expected: float, base: float | None = None) -> float:
    base = base if base is not None else expected
    if not base:
        return 0.0 if actual == expected else 100.0
    return round((actual - expected) / base * 100, 2)


def three_way_match(inv: dict, po: dict | None, grn: dict | None) -> dict:
    if po is None:
        return {"status": "NO_PO", "lines": [],
                "freight": {"invoice": inv["freight"], "expected": None, "var_pct": None},
                "tax": {"invoice": inv["tax"], "expected": None, "var_pct": None},
                "total": {"invoice": inv["total"], "expected": None, "var_pct": None}}

    po_lines = {l["item"]: l for l in po["lines"]}
    grn_qty = {l["item"]: l["qty"] for l in (grn or {}).get("lines", [])}
    tol = config.TOLERANCE_PCT
    lines = []
    for l in inv["lines"]:
        p = po_lines.get(l["item"])
        po_qty = p["qty"] if p else 0
        po_price = p["unit_price"] if p else 0
        g = grn_qty.get(l["item"], 0 if grn else None)
        price_var = _pct(l["unit_price"], po_price)
        lines.append({
            "item": l["item"], "inv_qty": l["qty"], "po_qty": po_qty, "grn_qty": g,
            "inv_price": l["unit_price"], "po_price": po_price, "price_var_pct": price_var,
            "qty_ok": bool(p) and l["qty"] <= po_qty and (g is None or l["qty"] <= g),
            "price_ok": bool(p) and abs(price_var) <= tol,
        })

    po_sub = sum(l["qty"] * l["unit_price"] for l in po["lines"])
    exp_freight = po.get("freight", 0.0)
    exp_tax = round(po_sub * po.get("tax_rate", 0.18), 2)
    exp_total = round(po_sub + exp_freight + exp_tax, 2)
    base = po_sub + exp_freight
    result = {
        "lines": lines,
        "freight": {"invoice": inv["freight"], "expected": exp_freight, "var_pct": _pct(inv["freight"], exp_freight, base)},
        "tax": {"invoice": inv["tax"], "expected": exp_tax, "var_pct": _pct(inv["tax"], exp_tax)},
        "total": {"invoice": inv["total"], "expected": exp_total, "var_pct": _pct(inv["total"], exp_total)},
    }
    clean = (all(l["qty_ok"] and l["price_ok"] for l in lines)
             and abs(result["freight"]["var_pct"]) <= tol and abs(result["tax"]["var_pct"]) <= tol
             and abs(result["total"]["var_pct"]) <= tol)
    result["status"] = "MATCHED" if clean else "VARIANCE"
    return result
