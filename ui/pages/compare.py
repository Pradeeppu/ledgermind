import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from ui.components import (svc, safe, inr, esc, page_header, decision_card, memories_html, section,  # noqa: E402
                           invoice_label, OUTCOME_META, OUTCOME_SVG, goto_decision, MI)
from ui.icons import svg  # noqa: E402

page_header("Memory on vs off", "Same invoice, same checks. The only difference is what the agent remembers.")

rows = safe(svc.list_invoices, default=[]) or []
if not rows:
    st.info("No invoices yet.")
    st.stop()

# hero picks: the demo story invoices
HERO = [("Krishna Electricals", "Bank change", ":material/account_balance:"),
        ("BrightPack", "Duplicate", ":material/content_copy:"),
        ("Sharma Logistics", "Freight surcharge", ":material/local_shipping:"),
        ("Vertex IT", "Bill spike", ":material/trending_up:"),
        ("Apex Steel", "Price creep", ":material/show_chart:")]
ids = [r["id"] for r in rows]
cur = st.session_state.get("compare_invoice") or st.session_state.get("selected_invoice")
if cur not in ids:
    kr = [r["id"] for r in rows if "Krishna" in r["vendor_name"] and r["date"] >= "2026-09-01"]
    cur = kr[0] if kr else ids[0]

st.caption("Quick picks")
qcols = st.columns(len(HERO))
for col, (vname, tag, ico) in zip(qcols, HERO):
    cand = sorted([r for r in rows if vname.lower() in r["vendor_name"].lower()], key=lambda r: r["date"])
    if cand and col.button(tag, key=f"hero_{vname}", icon=ico, width="stretch", help=f"{cand[-1]['number']} · {vname}"):
        st.session_state["compare_invoice"] = cand[-1]["id"]
        st.session_state.pop("compare_result", None)
        st.rerun()

p1, p2 = st.columns([4, 1.3])
row = p1.selectbox("Invoice", rows, index=ids.index(cur), format_func=invoice_label, label_visibility="collapsed")
if row["id"] != st.session_state.get("compare_invoice"):
    st.session_state["compare_invoice"] = row["id"]
run = p2.button("Run both", type="primary", icon=MI["compare"], width="stretch")

res = st.session_state.get("compare_result")
if run:
    with st.spinner("Running the agent twice: once with no history, once with Hindsight memory…"):
        off = safe(svc.decide, row["id"], memory_on=False, label="decide(memory_on=False)")
        on = safe(svc.decide, row["id"], memory_on=True, label="decide(memory_on=True)")
    if off and on:
        res = {"invoice_id": row["id"], "off": off, "on": on}
        st.session_state["compare_result"] = res

if not res or res.get("invoice_id") != row["id"]:
    st.markdown(f'<div class="lm-card lm-empty"><div class="circle">{svg("compare", 24)}</div>'
                '<b>Pick an invoice and press Run both.</b><br>'
                '<span class="lm-muted">Start with Krishna Electricals: a bank-account swap that looks perfectly '
                'clean if you have no history.</span></div>', unsafe_allow_html=True)
    st.stop()

off, on = res["off"], res["on"]
total = row["total"]
o_off, o_on = off["outcome"], on["outcome"]
l_off, l_on = OUTCOME_META[o_off][1], OUTCOME_META[o_on][1]

# ---------------------------------------------------------------- verdict banner
risk_rank = {"APPROVE": 0, "FLAG": 1, "ESCALATE": 2}
if o_off != o_on:
    if risk_rank[o_on] > risk_rank[o_off]:
        big = f"Memory caught what a stateless agent missed: {l_off} → {l_on}"
        small = (f"Without memory, {inr(total)} would have gone out the door. "
                 f"LedgerMind recalled {len(on.get('memories', []))} memories and stopped it.")
    else:
        big = f"Memory removed a false alarm: {l_off} → {l_on}"
        small = (f"A stateless agent would have sent this to a human. LedgerMind remembered the vendor's pattern "
                 f"and cleared {inr(total)} with {on['confidence'] * 100:.0f}% confidence. No clerk time spent.")
else:
    dc = (on["confidence"] - off["confidence"]) * 100
    big = f"Same verdict ({l_on}), but now it can say why"
    small = (f"Confidence {off['confidence'] * 100:.0f}% → {on['confidence'] * 100:.0f}% ({dc:+.0f} pts), "
             f"with {len(on.get('memories', []))} memories cited instead of a generic rule.")
st.markdown(f'<div class="lm-verdict"><div class="big">{svg(OUTCOME_SVG[o_on], 26, 2.2)}{esc(big)}</div>'
            f'<div class="small">{esc(small)}</div></div>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------- side by side
c_off, c_on = st.columns(2, gap="large")
with c_off:
    st.markdown(f'<span class="lm-vs off">{svg("power-off", 14)}Memory off · no history</span>', unsafe_allow_html=True)
    decision_card(off, show_mode=False, compact=True)
    st.markdown(f'<div class="lm-card">{section("Memories used", "database", 0)}<div class="lm-muted">Starts from '
                'zero every time: no vendor history, no past decisions by the AP team.</div></div>', unsafe_allow_html=True)
with c_on:
    st.markdown(f'<span class="lm-vs on">{svg("database", 14)}Memory on · Hindsight</span>', unsafe_allow_html=True)
    decision_card(on, show_mode=False, compact=True)
    st.markdown(f'<div class="lm-card">{section("Memories used", "database", len(on.get("memories", [])))}'
                f'{memories_html(on.get("memories", []))}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- diff
st.markdown("#### What memory changed")
new_flags = {f["code"] for f in on.get("risk_flags", [])} - {f["code"] for f in off.get("risk_flags", [])}
gone_flags = {f["code"] for f in off.get("risk_flags", [])} - {f["code"] for f in on.get("risk_flags", [])}
m1, m2, m3, m4 = st.columns(4)
m1.metric("Outcome", l_on, delta="changed" if o_on != o_off else "unchanged",
          delta_color="normal" if o_on != o_off else "off")
m2.metric("Confidence", f"{on['confidence'] * 100:.0f}%", delta=f"{(on['confidence'] - off['confidence']) * 100:+.0f} pts")
def _names(codes):
    return ", ".join(c.replace("_", " ").title() for c in sorted(codes)) or None


m3.metric("Risks surfaced", len(new_flags), delta=_names(new_flags), delta_color="off")
m4.metric("False alarms cleared", len(gone_flags), delta=_names(gone_flags), delta_color="off")
if st.button("Open in review", icon=MI["open"]):
    goto_decision(row["id"])
