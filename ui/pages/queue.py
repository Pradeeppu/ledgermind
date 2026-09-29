import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import csv  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import (svc, safe, inr, kpi, page_header, goto_decision, STATUS_LABEL,  # noqa: E402
                           OUTCOME_META, invoice_label, current_user, MI)

page_header("Invoice queue", "Acme Components Pvt Ltd · accounts payable inbox")
_, me = current_user()

rows = safe(svc.list_invoices, default=[]) or []
vendors = safe(svc.list_vendors, default=[]) or []

# ---------------------------------------------------------------- KPIs
pending = [r for r in rows if r["status"] == "PENDING"]
decided = [r for r in rows if r["status"] != "PENDING"]
approved = [r for r in decided if r["status"] == "APPROVED"]
flagged = [r for r in rows if r["status"] == "FLAGGED"]
escalated = [r for r in rows if r["status"] == "ESCALATED"]
protected = sum(r["total"] for r in flagged + escalated)
c = st.columns(5)
kpi(c[0], "Pending", len(pending), "waiting for the agent", accent=True, icon="clock")
kpi(c[1], "Auto-approved", f"{(len(approved) / len(decided) * 100) if decided else 0:.0f}%",
    f"{len(approved)} of {len(decided)} decided", icon="check-circle", tone="good")
kpi(c[2], "Flagged", len(flagged), "needs a human look", icon="alert-triangle", tone="warn")
kpi(c[3], "Escalated", len(escalated), "manager review", icon="octagon-alert", tone="crit")
kpi(c[4], "Held from payment", inr(protected), "flagged + escalated value", icon="shield-check")
st.write("")

# ---------------------------------------------------------------- actions
a1, a2 = st.columns([1, 2])
with a1:
    st.markdown("##### Review pending invoices")
    if st.button(f"Run agent on {len(pending)} pending", type="primary", icon=MI["run"],
                 disabled=not pending or not me["can_decide"], width="stretch"):
        bar = st.progress(0.0, text="Starting…")
        results = {"APPROVE": 0, "FLAG": 0, "ESCALATE": 0}
        for i, r in enumerate(pending, 1):
            bar.progress((i - 1) / len(pending), text=f"Deciding {r['number']} · {r['vendor_name']}…")
            d = safe(svc.decide, r["id"], memory_on=True, label=f"decide({r['number']})")
            if d:
                results[d["outcome"]] = results.get(d["outcome"], 0) + 1
        bar.progress(1.0, text="Done")
        st.session_state["last_batch"] = results
        st.rerun()
    if st.session_state.get("last_batch"):
        res = st.session_state["last_batch"]
        st.success("  ·  ".join(f"{OUTCOME_META[k][0]} {OUTCOME_META[k][1]}: **{v}**" for k, v in res.items()
                                if k in OUTCOME_META))
with a2:
    with st.expander("Import invoices (JSON or CSV)", icon=MI["upload"]):
        st.caption("JSON: a list of invoice objects (vendor_id or vendor_name, number, date, lines[{item,qty,"
                   "unit_price}], freight, bank_account, notes). CSV: one line item per row with the same columns.")
        up = st.file_uploader("Invoice file", type=["json", "csv"], label_visibility="collapsed")
        if up is not None and st.button("Import", key="import_btn"):
            try:
                raw = up.getvalue().decode("utf-8-sig")
                if up.name.lower().endswith(".json"):
                    data = json.loads(raw)
                    data = data if isinstance(data, list) else data.get("invoices", [data])
                else:
                    grouped: dict = {}
                    for rec in csv.DictReader(io.StringIO(raw)):
                        key = rec.get("number") or f"row{len(grouped)}"
                        inv = grouped.setdefault(key, {k: v for k, v in rec.items()
                                                       if k not in ("item", "qty", "unit_price")} | {"lines": []})
                        if rec.get("item"):
                            inv["lines"].append({"item": rec["item"], "qty": float(rec.get("qty") or 1),
                                                 "unit_price": float(rec.get("unit_price") or 0)})
                    data = list(grouped.values())
                ids = safe(svc.upload_invoices, data, default=[])
                if ids:
                    st.toast(f"Imported {len(ids)} invoice(s)", icon=MI["upload"])
                    st.success(f"Imported: {', '.join(ids)}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not parse file — {exc}")

st.divider()

# ---------------------------------------------------------------- filters + table
f1, f2, f3 = st.columns([1.2, 1.6, 1])
status_opt = f1.selectbox("Status", ["All", "PENDING", "APPROVED", "FLAGGED", "ESCALATED"],
                          format_func=lambda s: "All statuses" if s == "All" else STATUS_LABEL[s])
vmap = {v["id"]: v["name"] for v in vendors}
vendor_opt = f2.selectbox("Vendor", ["All"] + list(vmap), format_func=lambda v: "All vendors" if v == "All" else vmap[v])
sort_opt = f3.selectbox("Sort", ["Pending first", "Newest", "Largest amount"])

view = [r for r in rows if (status_opt == "All" or r["status"] == status_opt)
        and (vendor_opt == "All" or r["vendor_id"] == vendor_opt)]
if sort_opt == "Newest":
    view.sort(key=lambda r: r["date"], reverse=True)
elif sort_opt == "Largest amount":
    view.sort(key=lambda r: r["total"], reverse=True)
else:
    view.sort(key=lambda r: (r["status"] != "PENDING", r["date"]), reverse=False)
    view = [r for r in view if r["status"] == "PENDING"] + sorted(
        [r for r in view if r["status"] != "PENDING"], key=lambda r: r["date"], reverse=True)

if not view:
    st.info("No invoices match these filters.")
    st.stop()

df = pd.DataFrame([{
    "Status": STATUS_LABEL.get(r["status"], r["status"]),
    "Invoice": r["number"],
    "Vendor": r["vendor_name"],
    "Date": r["date"],
    "PO": r["po_id"] or "No PO",
    "Total": inr(r["total"]),
    "Agent": OUTCOME_META[r["outcome"]][1] if r.get("outcome") in OUTCOME_META else "—",
    "Confidence": r["confidence"] if r.get("confidence") is not None else None,
} for r in view])

st.caption(f"{len(view)} invoices · select a row, then open it")
TONE = {"Approved": "#0B6B1F", "Approve": "#0B6B1F", "Flagged": "#8A5A00", "Flag": "#8A5A00",
        "Escalated": "#9B1C1C", "Escalate": "#9B1C1C", "Pending": "#334155"}
styled = df.style.map(lambda v: f"color:{TONE[v]};font-weight:600" if v in TONE else "", subset=["Status", "Agent"])
sel = st.dataframe(
    styled, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
    height=min(38 * len(view) + 40, 520), key="queue_table",
    column_config={
        "Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
        "Status": st.column_config.TextColumn(width="small"),
    },
)
picked = None
try:
    idx = sel.selection.rows
    if idx:
        picked = view[idx[0]]
except Exception:  # noqa: BLE001
    picked = None

o1, o2 = st.columns([3, 1])
choice = o1.selectbox("Open invoice", view, index=view.index(picked) if picked in view else 0,
                      format_func=invoice_label, label_visibility="collapsed")
if o2.button("Review invoice", type="primary", icon=MI["open"], width="stretch"):
    goto_decision(choice["id"])
