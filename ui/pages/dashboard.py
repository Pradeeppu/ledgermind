import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import svc, safe, inr, page_header, kpi  # noqa: E402

page_header("Learning curve", "The agent needs the team less every period, without letting risk through")

curve = safe(svc.learning_curve, default=[]) or []
if not curve:
    st.info("No learning data yet.")
    st.stop()
df = pd.DataFrame(curve)
first, last = curve[0], curve[-1]

c = st.columns(4)
kpi(c[0], "Needs a human", f'{last["intervention_rate"] * 100:.0f}%',
    f'down from {first["intervention_rate"] * 100:.0f}% in {first["week"]}', accent=True, icon="trending-up")
kpi(c[1], "Invoices processed", int(df["invoices"].sum()), f'{len(curve)} periods, Apr to Sep', icon="file-text")
kpi(c[2], "Exceptions caught", int(df["exceptions_caught"].sum()), "duplicates, bank changes, price creep",
    icon="alert-triangle", tone="warn")
kpi(c[3], "Value protected", inr(df["value_protected"].sum()), "held before payment", icon="shield-check", tone="good")
st.write("")

INDIGO, ORANGE, INK2, GRID = "#2a78d6", "#eb6834", "#52514e", "#EEF0F4"

left, right = st.columns([1.3, 1], gap="large")
with left:
    st.markdown("**Share of invoices that needed a human**")
    fig = go.Figure(go.Scatter(
        x=df["week"], y=df["intervention_rate"] * 100, mode="lines+markers", name="Intervention rate",
        line=dict(color="#3730A3", width=2.5, shape="spline"), marker=dict(size=9, color="#3730A3",
                                                                           line=dict(color="#fff", width=2)),
        fill="tozeroy", fillcolor="rgba(55,48,163,0.08)",
        hovertemplate="%{x}: %{y:.0f}% needed a human<extra></extra>"))
    for pt, pos in ((first, "top right"), (last, "top left")):
        fig.add_annotation(x=pt["week"], y=pt["intervention_rate"] * 100, text=f'<b>{pt["intervention_rate"] * 100:.0f}%</b>',
                           showarrow=True, arrowhead=0, ax=28 if pos == "top right" else -28, ay=-30,
                           font=dict(size=15, color="#111827"), bgcolor="#fff", bordercolor="#3730A3",
                           borderwidth=1, borderpad=4)
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      showlegend=False, yaxis=dict(ticksuffix="%", range=[0, 108], gridcolor=GRID, title=None),
                      xaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with right:
    st.markdown("**Auto-approved vs needed a human**")
    fig2 = go.Figure()
    fig2.add_bar(x=df["week"], y=df["auto_approved"], name="Auto-approved", marker_color=INDIGO,
                 hovertemplate="%{x}: %{y} auto<extra></extra>")
    fig2.add_bar(x=df["week"], y=df["human_needed"], name="Needed a human", marker_color=ORANGE,
                 hovertemplate="%{x}: %{y} human<extra></extra>")
    fig2.update_layout(barmode="stack", bargap=0.35, height=340, margin=dict(l=10, r=10, t=20, b=10),
                       plot_bgcolor="#fff", paper_bgcolor="#fff", legend=dict(orientation="h", y=1.1, x=0),
                       yaxis=dict(gridcolor=GRID, title="Invoices"), xaxis=dict(showgrid=False))
    fig2.update_traces(marker_line_color="#fff", marker_line_width=2)
    st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})

with st.expander("Table view"):
    st.dataframe(pd.DataFrame([{"Week": r["week"], "Invoices": r["invoices"], "Auto": r["auto_approved"],
                                "Human": r["human_needed"], "Intervention": f'{r["intervention_rate"] * 100:.0f}%',
                                "Exceptions caught": r["exceptions_caught"],
                                "Value protected": inr(r["value_protected"])} for r in curve]),
                 hide_index=True, width="stretch")
