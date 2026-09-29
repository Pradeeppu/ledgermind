import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import (csr, safe, inr, esc, kpi, page_header, section, current_user,  # noqa: E402
                           TXN_LABEL, CSR_TONE, MI)
from ui.icons import svg  # noqa: E402

user, me = current_user()
ov = safe(csr.overview, label="overview")
if not ov:
    st.stop()
t = ov.get("totals", {})
page_header("CSR fund overview",
            f'{ov.get("foundation", "Foundation")} · where every donor rupee went, as of {ov.get("sim_date", "")}')

# ---------------------------------------------------------------- KPIs
c = st.columns(6)
kpi(c[0], "Received", inr(t.get("received")), f'from {len(ov.get("donors", []))} CSR donors', accent=True,
    icon="hand-heart")
kpi(c[1], "Disbursed", inr(t.get("disbursed")), f'credited to {t.get("students_funded", 0)} students',
    icon="check-circle", tone="good")
kpi(c[2], "In transit", inr(t.get("in_transit")), "sent, awaiting credit", icon="send")
kpi(c[3], "Failed or returned", inr(t.get("failed_returned")), "back with the foundation, to re-send",
    icon="undo", tone="crit")
kpi(c[4], "Left over", inr(t.get("left")), f'{inr(t.get("committed_pending"))} committed this cycle',
    icon="wallet", tone="warn")
kpi(c[5], "Utilisation", f'{t.get("utilisation_pct", 0):.1f}%', "disbursed + in transit / received",
    icon="pie-chart")
st.write("")

# ---------------------------------------------------------------- Sankey
flow = ov.get("flow") or []
programs = ov.get("programs") or []
left, right = st.columns([1.55, 1], gap="large")
with left:
    st.markdown("**Where the CSR money went**")
    st.caption("Donor, then programme, then what happened to the money. Hover a band for the amount.")
    if not flow:
        st.info("No fund flow yet.")
    else:
        nodes = []
        for f in flow:
            for n in (f["source"], f["target"]):
                if n not in nodes:
                    nodes.append(n)
        donor_names = {d["name"] for d in ov.get("donors", [])}
        prog_names = {p["program"] for p in programs}
        OUT_COL = {"credited": "#0ca30c", "transit": "#3730A3", "fail": "#d03b3b", "return": "#d03b3b"}

        # engine may label programme nodes "Engineering" or "Engineering pool"; match on the programme name
        def is_prog(n):
            return n in prog_names or any(n.lower().startswith(pn.lower()) for pn in prog_names) or "pool" in n.lower()

        def node_col(n):
            if n in donor_names:
                return "#312E81"
            if is_prog(n):
                return "#0F766E"
            low = n.lower()
            return next((v for k, v in OUT_COL.items() if k in low), "#94A3B8")

        def rgba(hexc, a):
            h = hexc.lstrip("#")
            return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"

        idx = {n: i for i, n in enumerate(nodes)}
        # links take the colour of their destination outcome, or of the programme for donor -> programme bands
        link_cols = [rgba(node_col(f["target"]), 0.28) for f in flow]
        fig = go.Figure(go.Sankey(
            arrangement="snap", valueformat=",.0f", valuesuffix=" INR",
            node=dict(label=nodes, pad=18, thickness=16, color=[node_col(n) for n in nodes],
                      line=dict(color="#fff", width=2),
                      hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>"),
            link=dict(source=[idx[f["source"]] for f in flow], target=[idx[f["target"]] for f in flow],
                      value=[f["value"] for f in flow], color=link_cols,
                      hovertemplate="%{source.label} to %{target.label}: ₹%{value:,.0f}<extra></extra>")))
        fig.update_layout(height=400, margin=dict(l=4, r=4, t=8, b=8), paper_bgcolor="#fff",
                          font=dict(family="Inter, system-ui, sans-serif", size=12, color="#111827"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# ---------------------------------------------------------------- programmes
with right:
    st.markdown("**Programmes**")
    SEG = [("disbursed", "Credited", "#0ca30c"), ("in_transit", "In transit", "#3730A3"),
           ("failed_returned", "Failed or returned", "#d03b3b")]
    st.markdown('<div class="lm-legend">' + "".join(f'<span><i style="background:{col}"></i>{esc(lbl)}</span>'
                                                    for _, lbl, col in SEG)
                + '<span><i style="background:#EEF0F4;border:1px solid #CBD5E1"></i>Not yet spent</span></div>',
                unsafe_allow_html=True)
    short = []
    html_rows = []
    for p in programs:
        rec = p.get("received") or 0
        segs = "".join(f'<span style="width:{(p.get(k) or 0) / rec * 100:.2f}%;background:{col}" '
                       f'title="{esc(lbl)}: {esc(inr(p.get(k)))}"></span>' for k, lbl, col in SEG if rec and p.get(k))
        html_rows.append(
            f'<div class="lm-prog"><div class="top"><b>{esc(p["program"])}</b>'
            f'<span>{esc(p.get("students", 0))} students · {esc(inr(rec))} received</span></div>'
            f'<div class="lm-stack" role="img" aria-label="{esc(p["program"])} utilisation">{segs}</div>'
            f'<div class="top" style="margin-top:.25rem"><span>Left {esc(inr(p.get("left")))}</span>'
            f'<span>Next cycle needs {esc(inr(p.get("next_cycle_need")))}</span></div></div>')
        if (p.get("left") or 0) < (p.get("next_cycle_need") or 0):
            short.append(p)
    st.markdown(f'<div class="lm-card">{"".join(html_rows)}</div>', unsafe_allow_html=True)
    for p in short:
        gap = (p.get("next_cycle_need") or 0) - (p.get("left") or 0)
        st.markdown(f'<div class="lm-callout warn">{svg("alert-triangle", 18)}<div><b>{esc(p["program"])} is '
                    f'{esc(inr(gap))} short for the next cycle.</b> {esc(inr(p.get("left")))} left against '
                    f'{esc(inr(p.get("next_cycle_need")))} needed for pending and next-instalment payouts. '
                    'Ask its donors for a top-up before the next cycle.</div></div>', unsafe_allow_html=True)
    if programs and not short:
        st.markdown(f'<div class="lm-callout good">{svg("check-circle", 18)}<div>Every programme has enough left '
                    'for the next cycle.</div></div>', unsafe_allow_html=True)

cyc = ov.get("cycle") or {}
if cyc:
    st.markdown(f'<div class="lm-callout">{svg("calendar", 18)}<div><b>{esc(cyc.get("label"))}</b> scheduled '
                f'{esc(cyc.get("scheduled_on"))}: {esc(cyc.get("released", 0))} of {esc(cyc.get("payouts", 0))} '
                f'payouts released ({esc(inr(cyc.get("amount_released")))}), {esc(cyc.get("pending", 0))} pending, '
                f'{esc(cyc.get("on_hold", 0))} on hold, {esc(cyc.get("escalated", 0))} escalated '
                f'({esc(inr(cyc.get("amount_pending")))} not yet released).</div></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- donors
st.divider()
st.markdown("#### Donors")
donors = ov.get("donors") or []
if not donors:
    st.info("No donors yet.")
    st.stop()
locked = me.get("donor")
if locked:
    mine = [d for d in donors if d["name"] == locked]
    if mine:
        st.caption(f"Donor view: you can see {locked}'s trail only.")
        donors_shown = mine
    else:
        donors_shown = donors
else:
    donors_shown = donors
ids = [d["id"] for d in donors_shown]
sel = st.session_state.get("csr_donor")
if sel not in ids:
    sel = ids[0]

cols = st.columns(max(3, len(donors_shown)))
for col, d in zip(cols, donors_shown):
    rec = d.get("received") or 0
    used = ((d.get("disbursed") or 0) + (d.get("in_transit") or 0)) / rec * 100 if rec else 0
    col.markdown(
        f'<div class="lm-card{" sel" if d["id"] == sel else ""}"><div class="lm-person">'
        f'<span class="lm-kpi" style="padding:.4rem;box-shadow:none;height:auto">{svg("building", 20)}</span>'
        f'<div><div class="name">{esc(d["name"])}</div><div class="role">{esc(d.get("grants", 0))} grants · '
        f'{esc(d.get("students_funded", 0))} students funded</div></div></div>'
        f'<div class="lm-mini"><div>Received<b>{esc(inr(rec))}</b></div>'
        f'<div>Disbursed<b class="good">{esc(inr(d.get("disbursed")))}</b></div>'
        f'<div>In transit<b>{esc(inr(d.get("in_transit")))}</b></div>'
        f'<div>Left<b>{esc(inr(d.get("left")))}</b></div></div>'
        f'<div class="lm-meter-lbl" style="margin-top:.6rem"><span>Utilised</span><b>{used:.0f}%</b></div>'
        f'<div class="lm-meter"><span style="width:{min(used, 100):.0f}%;background:#3730A3"></span></div></div>',
        unsafe_allow_html=True)
    if col.button("Show trail" if d["id"] != sel else "Showing trail", key=f"donor_{d['id']}", width="stretch",
                  icon=":material/route:", type="primary" if d["id"] == sel else "secondary"):
        st.session_state["csr_donor"] = d["id"]
        st.rerun()

trail = safe(csr.donor_trail, sel, label="donor_trail")
if not trail:
    st.stop()
dn = trail.get("donor", {})
summ = trail.get("summary", {})
st.markdown(f'<div class="lm-card">{section("Donor trail · " + dn.get("name", ""), "route")}'
            f'<div class="lm-muted">{esc(dn.get("contact", ""))}</div></div>', unsafe_allow_html=True)
g1, g2 = st.columns([1, 2], gap="large")
with g1:
    st.markdown("**Grants received**")
    grants = trail.get("grants") or []
    if grants:
        st.dataframe(pd.DataFrame([{"Grant": g["id"], "Date": g["date"], "Programme": g["program"],
                                    "Amount": inr(g["amount"])} for g in grants]), hide_index=True, width="stretch")
    else:
        st.caption("No grants recorded.")
    st.markdown(
        f'<div class="lm-card"><div class="lm-mini"><div>Received<b>{esc(inr(summ.get("received")))}</b></div>'
        f'<div>Disbursed<b class="good">{esc(inr(summ.get("disbursed")))}</b></div>'
        f'<div>In transit<b>{esc(inr(summ.get("in_transit")))}</b></div>'
        f'<div>Left<b>{esc(inr(summ.get("left")))}</b></div></div></div>', unsafe_allow_html=True)
    csv_text = safe(csr.utilisation_report_csv, sel, default="", label="utilisation_report_csv") or ""
    st.download_button("Download utilisation report (CSV)", data=csv_text.encode("utf-8"),
                       file_name=f"utilisation_{sel}.csv", mime="text/csv", icon=MI["download"], width="stretch",
                       disabled=not csv_text, key="dl_util")
with g2:
    allocs = trail.get("allocations") or []
    st.markdown(f"**Students funded** · {len({a['student_id'] for a in allocs})} students, {len(allocs)} payouts")
    if not allocs:
        st.caption("No payouts from this donor yet.")
    else:
        adf = pd.DataFrame([{"Status": TXN_LABEL.get(a.get("status"), a.get("status") or "—"),
                             "Student": a["student_name"], "Course": a["course"], "College": a["college"],
                             "Cycle": a["cycle"], "Amount": inr(a["amount"]), "Sent": a.get("sent_on") or "—",
                             "UTR": a.get("utr") or "—"} for a in reversed(allocs)])
        st.dataframe(adf.style.map(lambda v: f"color:{CSR_TONE[v]};font-weight:600" if v in CSR_TONE else "",
                                   subset=["Status"]),
                     hide_index=True, width="stretch", height=min(38 * len(adf) + 40, 420))
if not me.get("can_decide"):
    st.caption(f"{user} has read-only access. Payout decisions are made by foundation accountants.")
