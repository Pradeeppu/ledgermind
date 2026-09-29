"""LedgerMind – AI Accounts Payable agent with Hindsight memory.

Run:  python -m streamlit run app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="LedgerMind · Accounts Payable", page_icon=str(ROOT / "ui" / "assets" / "favicon-64.png"),
                   layout="wide", initial_sidebar_state="expanded")

from ui import styles  # noqa: E402
from ui.components import (svc, USING_MOCK, FALLBACK_REASON, USERS, status_badge_html, esc,  # noqa: E402
                           CSR_USING_MOCK, CSR_FALLBACK_REASON)

styles.inject()

P = "ui/pages/"
pages = {
    "Work": [
        st.Page(P + "queue.py", title="Invoice queue", icon=":material/inbox:", default=True),
        st.Page(P + "decision.py", title="Review invoice", icon=":material/fact_check:"),
        st.Page(P + "compare.py", title="Memory on vs off", icon=":material/compare_arrows:"),
    ],
    "CSR & scholarships": [
        st.Page(P + "csr_overview.py", title="CSR fund overview", icon=":material/volunteer_activism:"),
        st.Page(P + "csr_payouts.py", title="Scholarship payouts", icon=":material/payments:"),
        st.Page(P + "csr_transactions.py", title="Transaction tracker", icon=":material/swap_horiz:"),
        st.Page(P + "csr_students.py", title="Scholars", icon=":material/school:"),
        st.Page(P + "csr_team.py", title="Accountant workload", icon=":material/groups:"),
        st.Page(P + "csr_whatsapp.py", title="WhatsApp alerts", icon=":material/chat:"),
    ],
    "Memory": [
        st.Page(P + "vendor.py", title="Vendors", icon=":material/storefront:"),
        st.Page(P + "learned.py", title="Learned rules", icon=":material/rule:"),
        st.Page(P + "ask.py", title="Ask LedgerMind", icon=":material/forum:"),
    ],
    "Reports": [
        st.Page(P + "dashboard.py", title="Learning curve", icon=":material/monitoring:"),
        st.Page(P + "settings.py", title="Settings", icon=":material/tune:"),
    ],
}
nav = st.navigation(pages)
st.logo(str(ROOT / "ui" / "assets" / "logo.svg"), icon_image=str(ROOT / "ui" / "assets" / "logo-mark.svg"),
        size="large")

with st.sidebar:
    names = list(USERS)
    user = st.selectbox("Signed in as", names, index=names.index(st.session_state.get("user", names[0])),
                        format_func=lambda n: f"{n} · {USERS[n]['role']}", key="user_select")
    st.session_state["user"] = user
    initials = "".join(p[0] for p in user.replace(".", "").split())[:2].upper()
    st.markdown(f'<div class="lm-user"><div class="lm-avatar">{esc(initials)}</div><div>'
                f'<div class="who">{esc(user)}</div><div class="role">{esc(USERS[user]["role"])} · {esc(USERS[user].get("org", "Acme Components"))}</div>'
                '</div></div>', unsafe_allow_html=True)

    st.divider()
    try:
        info = svc.status()
    except Exception as exc:  # noqa: BLE001
        info = {"healthy": False, "message": str(exc), "bank_id": "—", "llm": "—"}
    st.markdown(status_badge_html(info), unsafe_allow_html=True)
    st.caption(f"Bank `{info.get('bank_id', '—')}` · reasoning: {info.get('llm', '—')}")
    if USING_MOCK and FALLBACK_REASON:
        st.caption(f"Engine fallback: {FALLBACK_REASON}")
    st.caption("CSR engine: " + ("demo data (mock)" if CSR_USING_MOCK else "connected"))
    if CSR_USING_MOCK and CSR_FALLBACK_REASON and not CSR_FALLBACK_REASON.startswith("forced"):
        st.caption(f"CSR fallback: {CSR_FALLBACK_REASON}")

nav.run()
