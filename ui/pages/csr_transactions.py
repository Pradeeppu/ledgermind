import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import (csr, safe, inr, esc, kpi, page_header, section, txn_chip, current_user,  # noqa: E402
                           TXN_LABEL, CSR_TONE, MI)
from ui.icons import svg  # noqa: E402

user, me = current_user()
ov = safe(csr.overview, default={}, label="overview") or {}
page_header("Transaction tracker", "Every scholarship transfer, followed until the student's bank credits it")

# ---------------------------------------------------------------- clock + memory toggle
b1, b2, b3 = st.columns([1.1, 1.3, 2])
with b1:
    st.markdown(f'<div style="padding-top:.35rem"><span class="lm-simdate">{svg("calendar", 15)}Bank clock · '
                f'{esc(ov.get("sim_date", "—"))}</span></div>', unsafe_allow_html=True)
with b2:
    if st.button("Advance bank clock +1 day", icon=MI["clock"], width="stretch", key="csr_clock",
                 disabled=not me["can_decide"],
                 help="Simulate the next banking day so transfers move forward" if me["can_decide"] else
                 "Read-only role"):
        res = safe(csr.advance_bank_clock, 1, label="advance_bank_clock")
        if res:
            ups = res.get("updates") or []
            st.session_state["csr_clock_updates"] = res
            st.toast(f"Bank clock is now {res.get('sim_date')} · {len(ups)} transfer(s) changed status",
                     icon=MI["clock"])
            st.rerun()
with b3:
    memory_on = st.toggle("Use learned bank timings (memory)", value=True, key="csr_txn_memory",
                          help="On: each bank's learned credit window. Off: a naive 3-day SLA for every bank.")

last = st.session_state.get("csr_clock_updates")
if last:
    ups = last.get("updates") or []
    if ups:
        items = "".join(f'<div class="lm-flag" style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span><b>{esc(u.get("student_name"))}</b> <span class="lm-muted">{esc(u.get("txn_id"))}</span>'
                        f'</span><span>{txn_chip(u.get("from"))} {svg("arrow-right", 14)} {txn_chip(u.get("to"))}'
                        f'</span></div>' for u in ups)
        st.markdown(f'<div class="lm-card">{section("Moved on " + str(last.get("sim_date", "")), "history", len(ups))}'
                    f'{items}</div>', unsafe_allow_html=True)
    else:
        st.caption(f"Clock moved to {last.get('sim_date')}: no transfer changed status.")

txns = safe(csr.list_transactions, memory_on=memory_on, default=[], label="list_transactions") or []
if not txns:
    st.info("No transfers yet.")
    st.stop()
txns_on = txns if memory_on else (safe(csr.list_transactions, memory_on=True, default=[]) or [])

# ---------------------------------------------------------------- KPIs
cnt = {s: [t for t in txns if t["status"] == s] for s in TXN_LABEL}
c = st.columns(5)
kpi(c[0], "In transit", len(cnt["IN_TRANSIT"]), inr(sum(t["amount"] for t in cnt["IN_TRANSIT"])), accent=True,
    icon="send")
kpi(c[1], "Credited", len(cnt["CREDITED"]), inr(sum(t["amount"] for t in cnt["CREDITED"])), icon="check-circle",
    tone="good")
kpi(c[2], "Delayed", len(cnt["DELAYED"]), "past the bank's window, chase it", icon="clock", tone="warn")
kpi(c[3], "Failed", len(cnt["FAILED"]), inr(sum(t["amount"] for t in cnt["FAILED"])), icon="x-circle", tone="crit")
kpi(c[4], "Returned", len(cnt["RETURNED"]), inr(sum(t["amount"] for t in cnt["RETURNED"])), icon="undo", tone="crit")
st.write("")

# ---------------------------------------------------------------- false alarm callout
if not memory_on:
    on_delayed = {t["id"] for t in txns_on if t["status"] == "DELAYED"}
    false = [t for t in cnt["DELAYED"] if t["id"] not in on_delayed]
    if false:
        banks = sorted({t["bank"] for t in false})
        st.markdown(f'<div class="lm-callout warn">{svg("alert-triangle", 18)}<div><b>{len(false)} transfers would be '
                    f'falsely flagged as delayed</b> with a flat 3-day SLA ({esc(", ".join(banks))}). LedgerMind has '
                    'learned these banks take longer, so with memory on they stay in transit and nobody wastes a '
                    'call chasing them.</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="lm-callout">{svg("power-off", 18)}<div>Memory off: every bank gets the same 3-day '
                    'SLA. No extra false alarms right now.</div></div>', unsafe_allow_html=True)
else:
    real = cnt["DELAYED"]
    if real:
        st.markdown(f'<div class="lm-callout crit">{svg("clock", 18)}<div><b>{len(real)} transfer(s) really are '
                    'late</b>: past the window LedgerMind learned for that bank. Chase them with the bank.</div></div>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- filters + table
f1, f2 = st.columns(2)
status_opt = f1.selectbox("Status", ["All"] + list(TXN_LABEL),
                          format_func=lambda s: "All statuses" if s == "All" else TXN_LABEL[s], key="csr_txn_status")
banks = sorted({t["bank"] for t in txns})
bank_opt = f2.selectbox("Bank", ["All"] + banks, format_func=lambda b: "All banks" if b == "All" else b,
                        key="csr_txn_bank")
view = [t for t in txns if (status_opt == "All" or t["status"] == status_opt)
        and (bank_opt == "All" or t["bank"] == bank_opt)]
order = {"DELAYED": 0, "FAILED": 1, "IN_TRANSIT": 2, "RETURNED": 3, "CREDITED": 4}
view.sort(key=lambda t: (order.get(t["status"], 9), t["sent_on"]), reverse=False)
if not view:
    st.info("No transfers match these filters.")
    st.stop()

df = pd.DataFrame([{
    "Status": TXN_LABEL.get(t["status"], t["status"]), "Student": t["student_name"], "Amount": inr(t["amount"]),
    "Bank": t["bank"], "Account": t["account"], "UTR": t["utr"], "Sent": t["sent_on"],
    "Expected by": t["expected_by"], "Credited": t.get("credited_on") or "—", "Days": t["days_in_transit"],
    "SLA": t["sla_days"], "Note": t.get("note") or "",
} for t in view])
st.caption(f"{len(view)} transfers · select a row to see its timeline")
sel = st.dataframe(df.style.map(lambda v: f"color:{CSR_TONE[v]};font-weight:600" if v in CSR_TONE else "",
                                subset=["Status"]),
                   hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                   height=min(38 * len(view) + 40, 440), key="csr_txn_table")
try:
    _rows = list(sel.selection.rows)
except Exception:  # noqa: BLE001
    _rows = []
if _rows != st.session_state.get("csr_txn_tsel"):  # apply a table selection only when it changes
    st.session_state["csr_txn_tsel"] = _rows
    if _rows and _rows[0] < len(view):
        st.session_state["csr_txn"] = view[_rows[0]]["id"]
ids = [t["id"] for t in view]
by_id = {t["id"]: t for t in view}
if st.session_state.get("csr_txn") not in ids:
    st.session_state["csr_txn"] = ids[0]
st.session_state["csr_txn_pick"] = st.session_state["csr_txn"]

# ---------------------------------------------------------------- timeline + bank insights
left, right = st.columns([1, 1.5], gap="large")
with left:
    tid = st.selectbox("Transfer", ids, key="csr_txn_pick",
                       format_func=lambda i: f'{by_id[i]["student_name"]} · {inr(by_id[i]["amount"])} · '
                                             f'{by_id[i]["bank"]} · {TXN_LABEL.get(by_id[i]["status"], by_id[i]["status"])}',
                       on_change=lambda: st.session_state.update(csr_txn=st.session_state["csr_txn_pick"]))
    t = by_id[tid]
    events = safe(csr.transaction_timeline, t["id"], default=[], label="transaction_timeline") or []

    def _tone(ev):
        e = (ev.get("event") or "").lower()
        if "credited" in e:
            return "good", "check-circle"
        if "fail" in e or "return" in e or "money back" in e:
            return "crit", "x-circle" if "fail" in e else "undo"
        if "delay" in e:
            return "warn", "clock"
        if "await" in e or "sent" in e or "transit" in e:
            return "info", "send"
        return "", "circle-dot"

    evs = []
    for ev in events:
        tone, ico = _tone(ev)
        evs.append(f'<div class="ev"><span class="dot {tone}">{svg(ico, 12)}</span>'
                   f'<div class="when">{esc(ev.get("date"))}</div><div class="what">{esc(ev.get("event"))}</div>'
                   f'<div class="det">{esc(ev.get("detail"))}</div></div>')
    st.markdown(f'<div class="lm-card">{section("Timeline · " + t["utr"], "route")}'
                f'<div style="margin-bottom:.6rem">{txn_chip(t["status"])} <span class="lm-muted">'
                f'{esc(t["bank"])} {esc(t["account"])} · day {esc(t["days_in_transit"])} of a '
                f'{esc(t["sla_days"])}-day window</span></div>'
                f'<div class="lm-tl">{"".join(evs) or "<div class=lm-muted>No events.</div>"}</div></div>',
                unsafe_allow_html=True)
with right:
    st.markdown("**Bank insights** · what LedgerMind has learned about each bank")
    ins = safe(csr.bank_insights, default=[], label="bank_insights") or []
    if ins:
        idf = pd.DataFrame([{
            "Bank": b["bank"], "Transfers": b["transfers"], "Credited": b["credited"], "Failed": b["failed"],
            "Median days": b.get("median_days"), "P90 days": b.get("p90_days"),
            "Learned SLA": b.get("learned_sla_days"), "Naive SLA": b.get("naive_sla_days"),
            "False alarms avoided": b.get("false_delay_alarms_avoided"), "Note": b.get("note") or "",
        } for b in ins])

        def _hl(r):
            slow = (r["Learned SLA"] or 0) > (r["Naive SLA"] or 0)
            return ["background-color:#EEF0FF;color:#312E81" if slow and k in ("Learned SLA", "False alarms avoided")
                    else "" for k in r.index]

        st.dataframe(idf.style.apply(_hl, axis=1).format({"Median days": "{:.1f}", "P90 days": "{:.1f}"},
                                                         na_rep="—"),
                     hide_index=True, width="stretch")
        avoided = sum(b.get("false_delay_alarms_avoided") or 0 for b in ins)
        if avoided:
            st.caption(f"Learned timings have avoided {avoided} false delay alarm(s) so far. Highlighted banks are "
                       "slower than the naive 3-day SLA.")
    else:
        st.caption("No bank history yet.")
