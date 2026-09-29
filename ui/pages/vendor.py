import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import svc, safe, inr, esc, page_header, chip, kpi, goto_decision, section, MI  # noqa: E402

page_header("Vendors", "Everything LedgerMind remembers about a supplier")

vendors = safe(svc.list_vendors, default=[]) or []
if not vendors:
    st.info("No vendors.")
    st.stop()
vids = [v["id"] for v in vendors]
default = st.session_state.get("vendor_id")
if default not in vids:
    kr = [v["id"] for v in vendors if "Krishna" in v["name"]]
    default = kr[0] if kr else vids[0]
v = st.selectbox("Vendor", vendors, index=vids.index(default),
                 format_func=lambda x: f'{x["name"]} · {x["category"]} · {x["invoice_count"]} invoices')
st.session_state["vendor_id"] = v["id"]

prof = safe(svc.vendor_profile, v["id"])
if not prof:
    st.stop()
vend = prof["vendor"]
bank = prof.get("bank_history") or []
tl = prof.get("timeline") or []

c = st.columns(4)
kpi(c[0], "GSTIN", vend.get("gstin", "—"), vend.get("category", ""), accent=True, icon="building")
kpi(c[1], "Payment terms", vend.get("payment_terms", "—"), f'Call-back: {vend.get("contact_phone", "—")}', icon="file-text")
kpi(c[2], "Invoices seen", len(tl), f'{inr(sum(t["total"] for t in tl))} billed', icon="history")
kpi(c[3], "Bank accounts", len(bank), "Changed, verify before paying" if len(bank) > 1 else "Stable, one account on record",
    icon="landmark", tone="crit" if len(bank) > 1 else "good")
st.write("")

if len(bank) > 1:
    st.error(f"**Bank account changed.** This vendor has been paid to {len(bank)} different accounts. Policy: call back "
             "on the phone number in the vendor master before paying a new account.", icon=MI["bank"])

left, right = st.columns([1.1, 1], gap="large")
with left:
    st.markdown(f'<div class="lm-card">{section("What memory knows", "book-open")}'
                + "".join(f'<div class="lm-mem"><div class="txt">{esc(f)}</div></div>' for f in prof.get("facts", []))
                + "</div>", unsafe_allow_html=True)
    st.markdown("**Bank-account history**")
    if bank:
        bdf = pd.DataFrame([{"Account": b["account"], "First seen": b["first_seen"], "Last seen": b["last_seen"],
                             "Invoices": b["count"]} for b in bank])
        latest = max(bank, key=lambda b: b["first_seen"])["account"] if len(bank) > 1 else None
        st.dataframe(bdf.style.apply(lambda r: ["background-color:#FDECEC;color:#9B1C1C;font-weight:600"
                                                if r["Account"] == latest else "" for _ in r], axis=1),
                     hide_index=True, width="stretch")
        if latest:
            st.caption(f"{latest} is new and highlighted in red.")
    else:
        st.caption("No payments recorded.")
with right:
    obs = prof.get("observations") or []
    html = "".join(
        f'<div class="lm-mem"><div class="meta">{chip(o.get("status", "active").title(), o.get("status", "active"), "layers")}'
        f'<span>{o.get("evidence_count", 1)} cases · last {esc(o.get("last_seen", ""))}</span></div>'
        f'<div class="txt">{esc(o["text"])}</div></div>' for o in obs) or '<div class="lm-muted">Nothing learned yet.</div>'
    st.markdown(f'<div class="lm-card">{section("Learned about this vendor", "layers", len(obs))}{html}</div>',
                unsafe_allow_html=True)

st.markdown("#### Invoice timeline")
if tl:
    colors = {"APPROVE": "#0ca30c", "FLAG": "#eda100", "ESCALATE": "#d03b3b", None: "#94A3B8"}
    symbols = {"APPROVE": "circle", "FLAG": "diamond", "ESCALATE": "x", None: "circle-open"}
    labels = {"APPROVE": "Approved", "FLAG": "Flagged", "ESCALATE": "Escalated", None: "Pending"}
    df = pd.DataFrame(tl).sort_values("date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["total"], mode="lines", line=dict(color="#CBD5E1", width=2),
                             hoverinfo="skip", showlegend=False))
    for oc in ["APPROVE", "FLAG", "ESCALATE", None]:
        sub = df[df["outcome"].isna()] if oc is None else df[df["outcome"] == oc]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["total"], mode="markers", name=labels[oc],
            marker=dict(size=12, color=colors[oc], symbol=symbols[oc], line=dict(color="#fff", width=2)),
            customdata=sub[["number", "status"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>₹%{y:,.0f}<br>%{customdata[1]}<extra></extra>"))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      legend=dict(orientation="h", y=1.12, x=0), hovermode="closest",
                      yaxis=dict(title="Invoice total (₹)", gridcolor="#EEF0F4", tickprefix="₹", separatethousands=True),
                      xaxis=dict(gridcolor="#F5F6F8"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with st.expander("Table view"):
        st.dataframe(pd.DataFrame([{"Date": t["date"], "Invoice": t["number"], "Total": inr(t["total"]),
                                    "Outcome": t.get("outcome") or "—", "Status": t["status"]} for t in tl]),
                     hide_index=True, width="stretch")
        pick = st.selectbox("Open invoice", tl, format_func=lambda t: f'{t["number"]} · {t["date"]}')
        if st.button("Open in review", icon=MI["open"]):
            goto_decision(pick["invoice_id"])
else:
    st.caption("No invoices yet.")
