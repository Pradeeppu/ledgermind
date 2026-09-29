import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import (svc, safe, inr, esc, page_header, decision_card, memories_html, section,  # noqa: E402
                           status_chip, invoice_label, current_user, read_only_notice, OUTCOME_META, MI)
from ui.icons import svg  # noqa: E402

page_header("Review invoice", "Three-way match, the agent's recommendation, and the memories behind it")
user, me = current_user()

rows = safe(svc.list_invoices, default=[]) or []
if not rows:
    st.info("No invoices yet.")
    st.stop()
ids = [r["id"] for r in rows]
sel_id = st.session_state.get("selected_invoice")
if sel_id not in ids:
    pend = [r["id"] for r in rows if r["status"] == "PENDING"]
    sel_id = pend[0] if pend else ids[0]

top1, top2 = st.columns([4, 1.3])
row = top1.selectbox("Invoice", rows, index=ids.index(sel_id), format_func=invoice_label,
                     label_visibility="collapsed")
st.session_state["selected_invoice"] = row["id"]
inv_id = row["id"]

inv = safe(svc.get_invoice, inv_id)
if not inv:
    st.stop()
decision = safe(svc.get_decision, inv_id)

with top2:
    if st.button("Run again" if decision else "Run agent", icon=MI["rerun"] if decision else MI["run"],
                 type="primary", width="stretch", disabled=not me["can_decide"]):
        with st.spinner("Recalling this vendor's history and deciding…"):
            decision = safe(svc.decide, inv_id, memory_on=True)
        if decision:
            icon, label, _ = OUTCOME_META.get(decision["outcome"], (MI["memory"], decision["outcome"], ""))
            st.toast(f"{label} · {decision['confidence'] * 100:.0f}% confidence", icon=icon)
            st.rerun()

left, centre, right = st.columns([1.25, 1.35, 1], gap="medium")

# ---------------------------------------------------------------- left: invoice + match
with left:
    st.markdown(
        f'<div class="lm-card">{section("Invoice", "file-text")}'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div style="font-size:1.2rem;font-weight:700">{esc(inv["number"])}</div>{status_chip(inv["status"])}</div>'
        f'<div style="margin:.2rem 0 .6rem 0"><b>{esc(inv["vendor_name"])}</b> '
        f'<span class="lm-muted">· {esc(inv["vendor_id"])}</span></div>'
        f'<table class="lm-kv">'
        f'<tr><td class="k">Date</td><td>{esc(inv["date"])}</td>'
        f'<td class="k">PO</td><td>{esc(inv.get("po_id") or "None")}</td></tr>'
        f'<tr><td class="k">Bank a/c</td><td><b>{esc(inv.get("bank_account"))}</b></td>'
        f'<td class="k">Terms</td><td>{esc(inv.get("payment_terms"))}</td></tr>'
        f'<tr><td class="k">Subtotal</td><td>{inr(inv["subtotal"])}</td>'
        f'<td class="k">Freight</td><td>{inr(inv["freight"])}</td></tr>'
        f'<tr><td class="k">GST</td><td>{inr(inv["tax"])}</td>'
        f'<td class="k">Total</td><td><b>{inr(inv["total"])}</b></td></tr></table>'
        + (f'<div class="lm-note">{svg("message", 15)}<span>“{esc(inv["notes"])}”</span></div>' if inv.get("notes") else "")
        + '</div>', unsafe_allow_html=True)

    st.markdown("**Line items**")
    st.dataframe(pd.DataFrame([{"Item": l["item"], "Qty": l["qty"], "Unit price": inr(l["unit_price"], 2),
                                "Amount": inr(l["amount"])} for l in inv["lines"]]),
                 hide_index=True, width="stretch")

    st.markdown("**Three-way match** · invoice, PO and goods receipt")
    match = (decision or {}).get("match")
    if not match:
        st.caption("Run the agent to compute the match.")
    elif match.get("status") == "NO_PO":
        st.warning("No purchase order on this invoice, so a three-way match isn't possible. "
                   "The agent compares it with the vendor's recurring pattern instead.", icon=":material/description:")
    else:
        if match["status"] == "MATCHED":
            st.caption(":green[:material/check_circle:] **Matched** within tolerance")
        else:
            st.caption(":orange[:material/warning:] **Variance found**, see highlighted rows")
        mdf = pd.DataFrame([{
            "Item": l["item"], "Inv qty": l["inv_qty"], "PO qty": l["po_qty"], "GRN qty": l["grn_qty"],
            "Inv ₹": l["inv_price"], "PO ₹": l["po_price"], "Var %": l["price_var_pct"],
            "Qty": "OK" if l["qty_ok"] else "Mismatch", "Price": "OK" if l["price_ok"] else "Mismatch",
        } for l in match.get("lines", [])])

        def _hl(r):
            bad = "Mismatch" in (r["Qty"], r["Price"])
            return ["background-color:#FFF6E0;color:#8A5A00" if bad else "" for _ in r]

        if not mdf.empty:
            st.dataframe(mdf.style.apply(_hl, axis=1).format({"Inv ₹": "{:,.2f}", "PO ₹": "{:,.2f}",
                                                              "Var %": "{:+.1f}%"}),
                         hide_index=True, width="stretch")
        tot = []
        for k in ("freight", "tax", "total"):
            x = match.get(k) or {}
            vp = x.get("var_pct")
            tot.append({"Component": k.title(), "Invoice": inr(x.get("invoice")), "Expected": inr(x.get("expected")),
                        "Var %": "—" if vp is None else f"{vp:+.1f}%",
                        "Check": "—" if vp is None else ("OK" if abs(vp) <= 0.5 else "Variance")})
        tdf = pd.DataFrame(tot)
        st.dataframe(tdf.style.apply(lambda r: ["background-color:#FFF6E0;color:#8A5A00" if r["Check"] == "Variance"
                                                else "" for _ in r], axis=1), hide_index=True, width="stretch")

# ---------------------------------------------------------------- centre: decision
with centre:
    if decision:
        decision_card(decision)
    else:
        st.markdown(f'<div class="lm-card lm-empty"><div class="circle">{svg("cpu", 24)}</div><b>No recommendation yet</b><br>'
                    '<span class="lm-muted">Run the agent to recall this vendor\'s history and get a '
                    'recommendation.</span></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- right: memories
with right:
    mems = (decision or {}).get("memories") or []
    st.markdown(f'<div class="lm-card">{section("Memories used", "database", len(mems))}{memories_html(mems)}</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- feedback
st.divider()
st.markdown("#### Your decision")
st.caption("Whatever you choose is retained in memory. It's how LedgerMind learns this vendor.")
if not decision:
    st.caption("Run the agent first, then accept, override or annotate its recommendation.")
elif not me["can_decide"]:
    read_only_notice()
else:
    t_acc, t_ovr, t_note = st.tabs([f"{MI['accept']} Accept", f"{MI['override']} Override", f"{MI['note']} Add note"])
    rec = OUTCOME_META[decision["outcome"]][1].lower()
    with t_acc:
        st.write(f"Accept the recommendation to **{rec}** {inv['number']}.")
        acc_note = st.text_input("Comment (optional)", key=f"acc_{inv_id}")
        if st.button("Accept", type="primary", icon=MI["accept"], key=f"accb_{inv_id}"):
            res = safe(svc.submit_feedback, inv_id, "accept", reason=acc_note, user=user)
            if res:
                if res.get("ok"):
                    st.toast(res["message"], icon=MI["memory"])
                else:
                    st.warning(res.get("message"))
    with t_ovr:
        opts = [o for o in ("APPROVE", "FLAG", "ESCALATE") if o != decision["outcome"]]
        c1, c2 = st.columns([1, 2])
        new_o = c1.radio("Change to", opts, format_func=lambda o: f"{OUTCOME_META[o][0]} {OUTCOME_META[o][1]}",
                         key=f"ovo_{inv_id}")
        reason = c2.text_area("Reason (required; the agent learns from this)", key=f"ovr_{inv_id}",
                              placeholder="e.g. Fuel surcharge is contractual, approve up to 2.5%")
        if st.button("Save override", type="primary", icon=MI["save"], key=f"ovb_{inv_id}"):
            if not reason.strip():
                st.error("Add a reason. It becomes the memory the agent learns from.")
            else:
                res = safe(svc.submit_feedback, inv_id, "override", new_outcome=new_o, reason=reason, user=user)
                if res:
                    if res.get("ok"):
                        st.toast(res["message"], icon=MI["memory"])
                        if res.get("retained"):
                            st.success("Saved to memory.", icon=MI["memory"])
                    else:
                        st.warning(res.get("message"))
    with t_note:
        note = st.text_area("Note for the agent", key=f"note_{inv_id}",
                            placeholder="e.g. Krishna called back and the new account was verified by Rakesh on 30-Sep")
        if st.button("Save note", icon=MI["save"], key=f"noteb_{inv_id}"):
            if not note.strip():
                st.error("The note is empty.")
            else:
                res = safe(svc.submit_feedback, inv_id, "note", reason=note, user=user)
                if res:
                    if res.get("ok"):
                        st.toast(res["message"], icon=MI["note"])
                    else:
                        st.warning(res.get("message"))
