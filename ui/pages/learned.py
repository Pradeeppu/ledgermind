import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from ui.components import svc, safe, esc, page_header, chip, kpi, current_user, MI  # noqa: E402
from ui.icons import svg  # noqa: E402

page_header("Learned rules", "Patterns LedgerMind has distilled from your team's decisions. Managers stay in control.")
_, me = current_user()
if not me["can_manage"]:
    st.caption(":material/lock: Only an AP Manager can confirm or retire rules. Switch user in the sidebar.")

rules = safe(svc.learned_rules, default=[]) or []
c = st.columns(4)
kpi(c[0], "Learned rules", len(rules), "ledger patterns + Hindsight observations", accent=True, icon="layers")
kpi(c[1], "Confirmed", sum(r["status"] == "confirmed" for r in rules), "verified by a manager", icon="shield-check", tone="good")
kpi(c[2], "Active", sum(r["status"] == "active" for r in rules), "in use, not yet confirmed", icon="circle-dot")
kpi(c[3], "Evidence", sum(int(r.get("evidence_count") or 0) for r in rules), "decisions behind them", icon="history")
st.write("")

f1, f2 = st.columns([2, 1])
show = f1.segmented_control("Show", ["All", "active", "confirmed", "retired"], default="All",
                            format_func=lambda s: s.title())
q = f2.text_input("Search", placeholder="vendor or keyword", label_visibility="collapsed")
view = [r for r in rules if (show in (None, "All") or r["status"] == show)
        and (not q or q.lower() in (r["text"] + " " + (r.get("vendor") or "")).lower())]
if not view:
    st.info("No rules match.")

STATUS_LABEL = {"active": ("Active", "circle-dot"), "confirmed": ("Confirmed", "shield-check"),
                "retired": ("Retired", "x-circle")}
SOURCE = {"hindsight": "Hindsight observation", "ledger": "From AP decisions"}
cols = st.columns(2, gap="medium")
for i, r in enumerate(view):
    with cols[i % 2]:
        with st.container(border=True):
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem">'
                f'<span class="lm-muted">{svg("building", 14)} {esc(r.get("vendor") or "All vendors")}</span>'
                f'<span>{chip(SOURCE.get(r.get("source"), "Learned"), "world")}'
                f'{chip(STATUS_LABEL.get(r["status"], (r["status"], None))[0], r["status"], STATUS_LABEL.get(r["status"], ("", None))[1])}'
                f'</span></div>'
                f'<div style="font-size:1rem;font-weight:600;line-height:1.4;margin-bottom:.4rem">{esc(r["text"])}</div>'
                f'<div class="lm-muted">{svg("history", 14)} <b>{esc(r.get("evidence_count", 0))}</b> {"case" if r.get("evidence_count") == 1 else "cases"} · first seen '
                f'{esc(r.get("first_seen", "—"))} · last seen {esc(r.get("last_seen", "—"))}</div>',
                unsafe_allow_html=True)
            b1, b2, _ = st.columns([1, 1, 1.5])
            if b1.button("Confirm", icon=MI["confirm"], key=f"c_{r['id']}",
                         disabled=r["status"] == "confirmed" or not me["can_manage"], width="stretch"):
                if (safe(svc.set_rule_status, r["id"], "confirmed") or {}).get("ok"):
                    st.toast("Rule confirmed. The agent will lean on it more.", icon=MI["confirm"])
                    st.rerun()
            if r["status"] == "retired":
                if b2.button("Restore", icon=MI["restore"], key=f"r_{r['id']}", disabled=not me["can_manage"],
                             width="stretch"):
                    if (safe(svc.set_rule_status, r["id"], "active") or {}).get("ok"):
                        st.rerun()
            elif b2.button("Retire", icon=MI["retire"], key=f"r_{r['id']}", disabled=not me["can_manage"],
                           width="stretch"):
                if (safe(svc.set_rule_status, r["id"], "retired") or {}).get("ok"):
                    st.toast("Rule retired. It won't influence decisions any more.", icon=MI["retire"])
                    st.rerun()
