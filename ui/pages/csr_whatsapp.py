import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from ui.components import safe, esc, inr, page_header, kpi, current_user, MI  # noqa: E402
from ui.icons import svg  # noqa: E402

try:
    from ui.backend import csr  # noqa: E402
except Exception:  # noqa: BLE001
    from ledgermind.csr import service as csr  # noqa: E402

page_header("WhatsApp alerts", "Students hear about every payout, and confirm bank changes from their registered number")
user, me = current_user()

st.markdown("""<style>
.wa-phone{border:1px solid var(--lm-line);border-radius:22px;overflow:hidden;background:#fff;box-shadow:0 10px 30px rgba(17,24,39,.08)}
.wa-head{display:flex;align-items:center;gap:.7rem;padding:.8rem 1rem;background:#075E54;color:#fff}
.wa-head .av{width:38px;height:38px;border-radius:50%;background:#25D366;display:flex;align-items:center;justify-content:center;font-weight:700}
.wa-head .nm{font-weight:700;line-height:1.1}.wa-head .ph{font-size:.78rem;opacity:.85}
.wa-body{background:#ECE5DD;padding:1rem .9rem;height:430px;overflow-y:auto;display:flex;flex-direction:column;gap:.45rem}
.wa-day{align-self:center;background:#E1F2FB;color:#44545c;font-size:.72rem;padding:.15rem .6rem;border-radius:8px;margin:.3rem 0}
.wa-b{max-width:82%;padding:.45rem .65rem .3rem .65rem;border-radius:10px;font-size:.88rem;line-height:1.4;color:#111;
  box-shadow:0 1px 1px rgba(0,0,0,.08)}
.wa-b.out{align-self:flex-end;background:#DCF8C6;border-top-right-radius:2px}
.wa-b.in{align-self:flex-start;background:#fff;border-top-left-radius:2px}
.wa-b .meta{display:flex;justify-content:flex-end;gap:.35rem;font-size:.68rem;color:#667;margin-top:.15rem}
.wa-b.q{border-left:3px solid #d97706}
.wa-thread{display:flex;gap:.6rem;align-items:flex-start;padding:.55rem .6rem;border-radius:12px;border:1px solid var(--lm-line);
  background:#fff;margin-bottom:.4rem}
.wa-thread.wait{border-color:#F4D58A;background:#FFFBEB}
.wa-thread .t{font-weight:600;font-size:.88rem}.wa-thread .s{font-size:.78rem;color:var(--lm-ink-3);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.wa-mode{display:flex;gap:.5rem;align-items:center;padding:.55rem .8rem;border-radius:12px;font-size:.86rem;margin-bottom:.8rem}
.wa-mode.sim{background:#EEF0FF;color:#3730A3}.wa-mode.live{background:#E8F7EC;color:#0B6B1F}
</style>""", unsafe_allow_html=True)

mode = safe(csr.whatsapp_mode, default={"mode": "simulated", "sender": "Shiksha Setu Foundation"}) or {}
if mode.get("mode") == "live":
    st.markdown(f'<div class="wa-mode live">{svg("send", 16)}<span><b>Live:</b> messages are sent through the WhatsApp '
                f'Business Cloud API' + (f' to the test number {esc(mode["test_recipient"])}' if mode.get("test_recipient") else "")
                + '.</span></div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="wa-mode sim">{svg("message", 16)}<span><b>Simulated:</b> messages are shown here and not sent '
                '(demo numbers are fictional). Set <code>WHATSAPP_LIVE=1</code> with a Cloud API token to send for real.'
                '</span></div>', unsafe_allow_html=True)

threads = safe(csr.whatsapp_threads, default=[]) or []
if not threads:
    st.info("No conversations yet. Run the agent on this cycle's payouts to send the first alerts.")
    st.stop()

allmsgs_out = sum(t["count"] for t in threads)
waiting = [t for t in threads if t["awaiting_reply"]]
c = st.columns(4)
kpi(c[0], "Conversations", len(threads), "one per student", accent=True, icon="message")
kpi(c[1], "Messages", allmsgs_out, "alerts, questions and replies", icon="send")
kpi(c[2], "Awaiting a reply", len(waiting), "verification questions open", icon="clock", tone="warn" if waiting else "")
kpi(c[3], "Registered numbers only", "100%", "questions never go to a new number", icon="shield-check", tone="good")
st.write("")

left, right = st.columns([1, 1.5], gap="large")
with left:
    only_wait = st.toggle("Only conversations awaiting a reply", value=bool(waiting))
    view = waiting if only_wait and waiting else threads
    ids = [t["student_id"] for t in view]
    sel = st.session_state.get("wa_student")
    if sel not in ids:
        sel = ids[0]
    pick = st.radio("Conversation", ids, index=ids.index(sel), label_visibility="collapsed",
                    format_func=lambda i: next(f"{t['student_name']}{'  ·  awaiting reply' if t['awaiting_reply'] else ''}"
                                               for t in view if t["student_id"] == i))
    st.session_state["wa_student"] = pick
    for t in view[:6]:
        st.markdown(f'<div class="wa-thread{" wait" if t["awaiting_reply"] else ""}">{svg("user", 18)}<div>'
                    f'<div class="t">{esc(t["student_name"])} <span class="lm-muted">· {esc(t["last_date"])}</span></div>'
                    f'<div class="s">{esc(t["last_message"])}</div></div></div>', unsafe_allow_html=True)

with right:
    t = next(x for x in threads if x["student_id"] == pick)
    msgs = safe(csr.whatsapp_messages, pick, default=[]) or []
    initials = "".join(w[0] for w in t["student_name"].split())[:2]
    body, day = [], None
    for m in msgs[-40:]:
        if m["date"] != day:
            day = m["date"]
            body.append(f'<div class="wa-day">{esc(day)}</div>')
        q = " q" if m["kind"] in ("verify_change", "verify_first", "need_details") else ""
        tick = "" if m["direction"] == "in" else (" · simulated" if m["status"] == "simulated" else f" · {esc(m['status'])}")
        who = "Student" if m["direction"] == "in" else "Foundation"
        body.append(f'<div class="wa-b {m["direction"]}{q}">{esc(m["body"])}<div class="meta">{who}{tick}</div></div>')
    st.markdown(f'<div class="wa-phone"><div class="wa-head"><div class="av">{esc(initials)}</div><div>'
                f'<div class="nm">{esc(t["student_name"])}</div><div class="ph">Registered number {esc(t["phone"])}</div></div></div>'
                f'<div class="wa-body">{"".join(body)}</div></div>', unsafe_allow_html=True)

    st.markdown("**Reply as the student** (demo)")
    if t["awaiting_reply"]:
        st.caption("A verification question is open. A YES verifies the account; a NO blocks the payout as fraud.")
    b1, b2, b3 = st.columns([1, 1, 2])
    reply = None
    if b1.button("YES", icon=":material/check:", width="stretch", key=f"wa_yes_{pick}", disabled=not t["awaiting_reply"]):
        reply = "Yes, I made this request" if t["question_kind"] == "verify_change" else "Yes, I received Rs.1"
    if b2.button("NO", icon=":material/block:", width="stretch", key=f"wa_no_{pick}", disabled=not t["awaiting_reply"]):
        reply = "NO, I did not request this change"
    with b3.form(f"wa_form_{pick}", clear_on_submit=True, border=False):
        txt = st.text_input("Message", placeholder="Type a reply…", label_visibility="collapsed")
        if st.form_submit_button("Send", icon=":material/send:"):
            reply = txt.strip() or None
    if reply:
        res = safe(csr.whatsapp_reply, pick, reply)
        if res and res.get("ok"):
            st.toast(res["message"], icon=":material/chat:")
            st.session_state["wa_last"] = res
            st.rerun()
    last = st.session_state.pop("wa_last", None)
    if last:
        icon = {"verified": MI["confirm"], "fraud_blocked": ":material/gpp_bad:"}.get(last["action"], MI["note"])
        (st.success if last["action"] == "verified" else st.error if last["action"] == "fraud_blocked" else st.info)(
            last["message"], icon=icon)
