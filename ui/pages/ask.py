import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from ui.components import svc, safe, page_header, memories_html, MI  # noqa: E402

page_header("Ask LedgerMind", "Ask about any vendor or payment in plain English. Every answer cites its memories.")

SUGGESTED = ["Why did we pay Sharma extra freight in June?",
             "Has Krishna Electricals ever changed bank details?",
             "Which vendors show price creep?"]

hist = st.session_state.setdefault("chat", [])


def _render(msg):
    with st.chat_message(msg["role"], avatar=":material/person:" if msg["role"] == "user" else ":material/neurology:"):
        st.markdown(msg["content"])
        cits = msg.get("citations") or []
        if cits:
            with st.expander(f"{len(cits)} memories cited", icon=":material/database:"):
                st.markdown(memories_html(cits), unsafe_allow_html=True)


pending_q = None
if not hist:
    st.markdown('<div class="lm-muted" style="margin-bottom:.4rem">Try one of these:</div>', unsafe_allow_html=True)
cols = st.columns(len(SUGGESTED))
for col, q in zip(cols, SUGGESTED):
    if col.button(q, key=f"sq_{q}", width="stretch"):
        pending_q = q

for m in hist:
    _render(m)

typed = st.chat_input("Ask about a vendor, a payment, a pattern…")
question = typed or pending_q
if question:
    user_msg = {"role": "user", "content": question}
    hist.append(user_msg)
    _render(user_msg)
    with st.spinner("Recalling memories…"):
        res = safe(svc.ask, question, default=None)
    if res:
        bot = {"role": "assistant", "content": res.get("answer", ""), "citations": res.get("citations", [])}
    else:
        bot = {"role": "assistant", "content": "_Sorry — I couldn't reach the memory engine._", "citations": []}
    hist.append(bot)
    _render(bot)

if hist and st.button("Clear conversation", icon=MI["clear"]):
    st.session_state["chat"] = []
    st.rerun()
