import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import csr, safe, inr, esc, kpi, page_header, current_user, goto_page, MI  # noqa: E402
from ui.icons import svg  # noqa: E402

page_header("Accountant workload", "Who has what on their desk this cycle, and which transfers they need to chase")
user, me = current_user()

team = safe(csr.team_workload, default=[], label="team_workload") or []
if not team:
    st.info("No accountants yet.")
    st.stop()

c = st.columns(4)
kpi(c[0], "Waiting for a decision", sum(t["pending"] for t in team), inr(sum(t["amount_pending"] for t in team))
    + " not yet released", accent=True, icon="clock")
kpi(c[1], "On hold", sum(t["on_hold"] for t in team), "needs a fix", icon="alert-triangle", tone="warn")
kpi(c[2], "Escalated", sum(t["escalated"] for t in team), "needs a senior look", icon="octagon-alert", tone="crit")
kpi(c[3], "Transfers to chase", sum(t["failed_to_chase"] + t["delayed_to_chase"] for t in team),
    "failed or delayed", icon="send", tone="crit")
st.write("")

cols = st.columns(len(team))
for col, t in zip(cols, team):
    initials = "".join(w[0] for w in t["accountant"].replace(".", "").split())[:2].upper()
    chase = t["failed_to_chase"] + t["delayed_to_chase"]
    col.markdown(
        f'<div class="lm-card{" sel" if t["accountant"] == user else ""}"><div class="lm-person">'
        f'<div class="lm-avatar">{esc(initials)}</div><div><div class="name">{esc(t["accountant"])}'
        + (' <span class="lm-muted">(you)</span>' if t["accountant"] == user else "")
        + f'</div><div class="role">{esc(t.get("focus", ""))}</div></div></div>'
        f'<div class="lm-mini"><div>Pending<b>{esc(t["pending"])}</b></div>'
        f'<div>{svg("alert-triangle", 12)} On hold<b class="warn">{esc(t["on_hold"])}</b></div>'
        f'<div>{svg("octagon-alert", 12)} Escalated<b class="crit">{esc(t["escalated"])}</b></div>'
        f'<div>{svg("check-circle", 12)} Released<b class="good">{esc(t.get("released", 0))}</b></div>'
        f'<div>Amount pending<b>{esc(inr(t["amount_pending"]))}</b></div>'
        f'<div>Avg turnaround<b>{esc(t.get("avg_turnaround_days", "—"))} days</b></div>'
        f'<div>{svg("x-circle", 12)} Failed to chase<b class="{"crit" if t["failed_to_chase"] else ""}">'
        f'{esc(t["failed_to_chase"])}</b></div>'
        f'<div>{svg("clock", 12)} Delayed to chase<b class="{"warn" if t["delayed_to_chase"] else ""}">'
        f'{esc(t["delayed_to_chase"])}</b></div></div>'
        + (f'<div class="lm-callout crit" style="margin:.7rem 0 0 0">{svg("send", 16)}<div>{chase} transfer(s) '
           'to follow up with the bank.</div></div>' if chase else "")
        + '</div>', unsafe_allow_html=True)
    if col.button("Open their queue", key=f"csr_q_{t['accountant']}", icon=MI["queue"], width="stretch"):
        goto_page("ui/pages/csr_payouts.py", csr_open_accountant=t["accountant"], csr_payout=None)

st.markdown("**Workload by accountant** · current cycle")
SERIES = [("pending", "Pending", "#64748B"), ("on_hold", "On hold", "#fab219"), ("escalated", "Escalated", "#d03b3b"),
          ("released", "Released", "#0ca30c")]
fig = go.Figure()
names = [t["accountant"] for t in team]
for k, lbl, colr in SERIES:
    fig.add_bar(x=names, y=[t.get(k, 0) for t in team], name=lbl, marker_color=colr, text=[t.get(k, 0) for t in team],
                textposition="outside", textfont=dict(color="#4B5563", size=11),
                hovertemplate="%{x} · " + lbl + ": %{y}<extra></extra>")
fig.update_traces(marker_line_color="#fff", marker_line_width=2, cliponaxis=False)
fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08, height=320, margin=dict(l=10, r=10, t=30, b=10),
                  plot_bgcolor="#fff", paper_bgcolor="#fff", legend=dict(orientation="h", y=1.15, x=0),
                  yaxis=dict(gridcolor="#EEF0F4", title="Payouts", dtick=1), xaxis=dict(showgrid=False),
                  font=dict(family="Inter, system-ui, sans-serif", color="#111827"))
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with st.expander("Table view"):
    st.dataframe(pd.DataFrame([{"Accountant": t["accountant"], "Focus": t.get("focus", ""), "Pending": t["pending"],
                                "On hold": t["on_hold"], "Escalated": t["escalated"], "Released": t.get("released", 0),
                                "Amount pending": inr(t["amount_pending"]),
                                "Avg turnaround (days)": t.get("avg_turnaround_days"),
                                "Failed to chase": t["failed_to_chase"], "Delayed to chase": t["delayed_to_chase"]}
                               for t in team]), hide_index=True, width="stretch")
