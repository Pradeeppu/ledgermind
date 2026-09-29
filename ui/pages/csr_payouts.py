import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import (csr, safe, inr, esc, kpi, page_header, section, memories_html, payout_card,  # noqa: E402
                           payout_status_chip, payout_label, current_user, read_only_notice, PAYOUT_META,
                           PAYOUT_SVG, PAYOUT_STATUS_LABEL, CSR_TONE, MI)
from ui.icons import svg  # noqa: E402


def _pick_row(sel, view, state_key, seen_key):
    """Apply a dataframe row selection only when it changes, so the picker below can still be used."""
    try:
        rows = list(sel.selection.rows)
    except Exception:  # noqa: BLE001
        rows = []
    if rows != st.session_state.get(seen_key):
        st.session_state[seen_key] = rows
        if rows and rows[0] < len(view):
            st.session_state[state_key] = view[rows[0]]["id"]


user, me = current_user()
ov = safe(csr.overview, default={}, label="overview") or {}
cyc = ov.get("cycle") or {}
cycle_id = cyc.get("id")
page_header("Scholarship payouts",
            f'{cyc.get("label", "Current cycle")} · scheduled {cyc.get("scheduled_on", "")} · '
            'the agent checks every payout against what it remembers about the student, the account and the bank')

rows = safe(csr.list_payouts, cycle=cycle_id, default=[], label="list_payouts") or []
if not rows:
    st.info("No payouts in this cycle yet.")
    st.stop()

# ---------------------------------------------------------------- KPIs
by = {s: [r for r in rows if r["status"] == s] for s in PAYOUT_STATUS_LABEL}
pending = by["PENDING"]
c = st.columns(5)
kpi(c[0], "Pending", len(pending), f'{inr(sum(r["amount"] for r in pending))} waiting', accent=True, icon="clock")
kpi(c[1], "Released", len(by["RELEASED"]), f'{inr(sum(r["amount"] for r in by["RELEASED"]))} sent',
    icon="check-circle", tone="good")
kpi(c[2], "On hold", len(by["ON_HOLD"]), "needs a fix before paying", icon="alert-triangle", tone="warn")
kpi(c[3], "Escalated", len(by["ESCALATED"]), "possible fraud or duplicate", icon="octagon-alert", tone="crit")
kpi(c[4], "Held back", inr(sum(r["amount"] for r in by["ON_HOLD"] + by["ESCALATED"])), "protected from a bad payout",
    icon="shield-check")
st.write("")

# ---------------------------------------------------------------- batch run
a1, a2 = st.columns([1, 2])
with a1:
    if st.button(f"Run agent on {len(pending)} pending", type="primary", icon=MI["run"],
                 disabled=not pending or not me["can_decide"], width="stretch", key="csr_run_all"):
        bar = st.progress(0.0, text="Starting…")
        res = {"RELEASE": 0, "HOLD": 0, "ESCALATE": 0}
        for i, r in enumerate(pending, 1):
            bar.progress((i - 1) / len(pending), text=f"Checking {r['student_name']} · {inr(r['amount'])}…")
            d = safe(csr.decide_payout, r["id"], memory_on=True, label=f"decide_payout({r['id']})")
            if d:
                res[d["outcome"]] = res.get(d["outcome"], 0) + 1
        bar.progress(1.0, text="Done")
        st.session_state["csr_last_batch"] = res
        st.rerun()
    if not me["can_decide"]:
        st.caption("Read-only role: you can review payouts but not run the agent.")
with a2:
    if st.session_state.get("csr_last_batch"):
        res = st.session_state["csr_last_batch"]
        st.success("  ·  ".join(f"{PAYOUT_META[k][0]} {PAYOUT_META[k][1]}: **{v}**" for k, v in res.items()
                                if k in PAYOUT_META))

st.divider()

# ---------------------------------------------------------------- filters + table
accts = sorted({r["accountant"] for r in rows})
if st.session_state.get("csr_open_accountant"):  # set by "Open their queue" on the workload page
    st.session_state["csr_acct_filter"] = st.session_state.pop("csr_open_accountant")
    st.session_state["csr_status_filter"] = "All"
f1, f2 = st.columns([1, 1])
status_opt = f1.selectbox("Status", ["All"] + list(PAYOUT_STATUS_LABEL),
                          format_func=lambda s: "All statuses" if s == "All" else PAYOUT_STATUS_LABEL[s],
                          key="csr_status_filter")
if st.session_state.get("csr_acct_filter") not in ["All"] + accts:
    st.session_state["csr_acct_filter"] = "All"
acct_opt = f2.selectbox("Accountant", ["All"] + accts, format_func=lambda a: "All accountants" if a == "All" else a,
                        key="csr_acct_filter")
view = [r for r in rows if (status_opt == "All" or r["status"] == status_opt)
        and (acct_opt == "All" or r["accountant"] == acct_opt)]
view.sort(key=lambda r: (r["status"] != "PENDING", r["status"], r["student_name"]))
if not view:
    st.info("No payouts match these filters.")
    st.stop()

df = pd.DataFrame([{
    "Status": PAYOUT_STATUS_LABEL.get(r["status"], r["status"]),
    "Student": r["student_name"], "Course": r["course"], "Amount": inr(r["amount"]),
    "Bank": r["bank"], "Account": r["account"], "Accountant": r["accountant"],
    "Agent": PAYOUT_META[r["outcome"]][1] if r.get("outcome") in PAYOUT_META else "—",
    "Confidence": r.get("confidence"),
} for r in view])
st.caption(f"{len(view)} payouts · select a row to review it")
sel = st.dataframe(
    df.style.map(lambda v: f"color:{CSR_TONE[v]};font-weight:600" if v in CSR_TONE else "", subset=["Status", "Agent"]),
    hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
    height=min(38 * len(view) + 40, 460), key="csr_payout_table",
    column_config={"Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
_pick_row(sel, view, "csr_payout", "csr_payout_tsel")
ids = [r["id"] for r in view]
by_id = {r["id"]: r for r in view}
if st.session_state.get("csr_payout") not in ids:
    st.session_state["csr_payout"] = ids[0]
st.session_state["csr_payout_pick"] = st.session_state["csr_payout"]
pid = st.selectbox("Payout", ids, format_func=lambda i: payout_label(by_id[i]), label_visibility="collapsed",
                   key="csr_payout_pick", on_change=lambda: st.session_state.update(
                       csr_payout=st.session_state["csr_payout_pick"]))
row = by_id[pid]

p = safe(csr.get_payout, pid, label="get_payout")
if not p:
    st.stop()
decision = safe(csr.get_payout_decision, pid, label="get_payout_decision")

# ---------------------------------------------------------------- review panel
st.markdown("#### Review payout")
h1, h2 = st.columns([4, 1.3])
h1.caption("The student and request, the agent's recommendation, and the memories behind it.")
with h2:
    if st.button("Run again" if decision else "Run agent", icon=MI["rerun"] if decision else MI["run"],
                 type="primary", width="stretch", disabled=not me["can_decide"], key="csr_run_one"):
        with st.spinner("Recalling this student's accounts, payouts and bank history…"):
            decision = safe(csr.decide_payout, pid, memory_on=True, label="decide_payout")
        if decision:
            icon, label, _ = PAYOUT_META.get(decision["outcome"], (MI["memory"], decision["outcome"], ""))
            st.toast(f"{label} · {decision['confidence'] * 100:.0f}% confidence", icon=icon)
            st.rerun()

left, centre, right = st.columns([1.2, 1.35, 1], gap="medium")
with left:
    ent = p.get("annual_entitlement") or 0
    paid = p.get("paid_this_year") or 0
    over = paid + p["amount"] > ent + 0.5 if ent else False
    st.markdown(
        f'<div class="lm-card">{section("Student and payout", "graduation-cap")}'
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:.5rem">'
        f'<div style="font-size:1.15rem;font-weight:700">{esc(p["student_name"])}</div>{payout_status_chip(p["status"])}</div>'
        f'<div class="lm-muted" style="margin:.15rem 0 .6rem 0">{esc(p["course"])} · {esc(p["college"])}</div>'
        f'<table class="lm-kv">'
        f'<tr><td class="k">Amount</td><td><b>{inr(p["amount"])}</b></td>'
        f'<td class="k">Cycle</td><td>{esc(p["cycle_label"])}</td></tr>'
        f'<tr><td class="k">Entitlement</td><td>{inr(ent)} / year</td>'
        f'<td class="k">Paid {esc(p.get("year", ""))}</td><td>'
        + (f'<b style="color:var(--lm-crit-ink)">{inr(paid)}</b>' if over else inr(paid)) + '</td></tr>'
        f'<tr><td class="k">Bank</td><td>{esc(p["bank"])}</td><td class="k">IFSC</td><td>{esc(p.get("ifsc", "—"))}</td></tr>'
        f'<tr><td class="k">Account</td><td><b>{esc(p["account"])}</b></td>'
        f'<td class="k">Holder</td><td>{esc(p.get("account_holder", "—"))}</td></tr>'
        f'<tr><td class="k">Accountant</td><td>{esc(p["accountant"])}</td>'
        f'<td class="k">Scheduled</td><td>{esc(p.get("scheduled_on", "—"))}</td></tr></table>'
        + (f'<div class="lm-note">{svg("message", 15)}<span>“{esc(p["request_note"])}”</span></div>'
           if p.get("request_note") else "")
        + '</div>', unsafe_allow_html=True)
with centre:
    if decision:
        payout_card(decision)
    else:
        st.markdown(f'<div class="lm-card lm-empty"><div class="circle">{svg("cpu", 24)}</div><b>No recommendation yet</b>'
                    '<br><span class="lm-muted">Run the agent to check this payout against the student\'s accounts, '
                    'past transfers and this cycle.</span></div>', unsafe_allow_html=True)
with right:
    mems = (decision or {}).get("memories") or []
    st.markdown(f'<div class="lm-card">{section("Memories used", "database", len(mems))}{memories_html(mems)}</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- memory on vs off
with st.expander("Compare memory on / off", icon=MI["compare"], expanded=bool(st.session_state.get("csr_cmp"))):
    st.caption("Same payout, same checks. The only difference is what the agent remembers. "
               "If the agent hasn't run on it yet, the memory-on run is also recorded as its recommendation.")
    if st.button("Run both", icon=MI["compare"], key="csr_cmp_run", disabled=not me["can_decide"]):
        with st.spinner("Running the agent twice: once with no history, once with memory…"):
            off = safe(csr.decide_payout, pid, memory_on=False, label="decide_payout(memory_on=False)")
            # memory-on run for comparison only: reuse the stored decision if there is one so status isn't changed
            on = decision or safe(csr.decide_payout, pid, memory_on=True, label="decide_payout(memory_on=True)")
        if off and on:
            st.session_state["csr_cmp"] = {"id": pid, "off": off, "on": on}
            st.rerun()
    cmp = st.session_state.get("csr_cmp")
    if cmp and cmp.get("id") == pid:
        off, on = cmp["off"], cmp["on"]
        o_off, o_on = off["outcome"], on["outcome"]
        l_off, l_on = PAYOUT_META[o_off][1], PAYOUT_META[o_on][1]
        rank = {"RELEASE": 0, "HOLD": 1, "ESCALATE": 2}
        first = p["student_name"].split()[0]
        n_mem = len(on.get("memories", []))
        mem_txt = f"{n_mem} memor{'y' if n_mem == 1 else 'ies'}"
        if o_off != o_on and rank[o_on] > rank[o_off]:
            big = f"Memory caught what a stateless agent missed: {l_off} → {l_on}"
            small = (f"Without memory, {inr(p['amount'])} would have gone out for {first}. LedgerMind recalled "
                     f"{mem_txt} and stopped it.")
        elif o_off != o_on:
            big = f"Memory removed a false alarm: {l_off} → {l_on}"
            small = (f"A stateless agent would have held {first}'s scholarship. LedgerMind remembered why this is "
                     f"fine and released it with {on['confidence'] * 100:.0f}% confidence.")
        else:
            big = f"Same verdict ({l_on}), but now it can say why"
            small = (f"Confidence {off['confidence'] * 100:.0f}% → {on['confidence'] * 100:.0f}%, with "
                     f"{mem_txt} cited instead of the request alone.")
        st.markdown(f'<div class="lm-verdict"><div class="big">{svg(PAYOUT_SVG[o_on], 26, 2.2)}{esc(big)}</div>'
                    f'<div class="small">{esc(small)}</div></div>', unsafe_allow_html=True)
        c_off, c_on = st.columns(2, gap="large")
        with c_off:
            st.markdown(f'<span class="lm-vs off">{svg("power-off", 14)}Memory off · no history</span>',
                        unsafe_allow_html=True)
            payout_card(off, show_mode=False, compact=True)
        with c_on:
            st.markdown(f'<span class="lm-vs on">{svg("database", 14)}Memory on · Hindsight</span>',
                        unsafe_allow_html=True)
            payout_card(on, show_mode=False, compact=True)

# ---------------------------------------------------------------- feedback
st.divider()
st.markdown("#### Your decision")
st.caption("Whatever you choose is retained in memory. It's how LedgerMind learns each student and account.")


def _done(res, icon=MI["memory"]):
    if not res:
        return
    if res.get("ok"):
        st.toast(res.get("message", "Saved."), icon=icon)
        if res.get("retained"):
            st.success(res.get("message", "Saved to memory."), icon=MI["memory"])
    else:
        st.warning(res.get("message", "Not saved."))


if not me["can_decide"]:
    read_only_notice()
elif not decision:
    st.caption("Run the agent first, then accept, override, annotate or verify the account.")
else:
    t_acc, t_ovr, t_note, t_ver = st.tabs([f"{MI['accept']} Accept", f"{MI['override']} Override",
                                           f"{MI['note']} Add note", f"{MI['verify']} Verify account"])
    rec = PAYOUT_META[decision["outcome"]][1].lower()
    with t_acc:
        st.write(f"Accept the recommendation to **{rec}** {p['student_name']}'s {inr(p['amount'])}.")
        acc_note = st.text_input("Comment (optional)", key=f"csr_acc_{pid}")
        if st.button("Accept", type="primary", icon=MI["accept"], key=f"csr_accb_{pid}"):
            _done(safe(csr.payout_feedback, pid, "accept", reason=acc_note, user=user, label="payout_feedback"))
    with t_ovr:
        opts = [o for o in PAYOUT_META if o != decision["outcome"]]
        c1, c2 = st.columns([1, 2])
        new_o = c1.radio("Change to", opts, format_func=lambda o: f"{PAYOUT_META[o][0]} {PAYOUT_META[o][1]}",
                         key=f"csr_ovo_{pid}")
        reason = c2.text_area("Reason (required; the agent learns from this)", key=f"csr_ovr_{pid}",
                              placeholder="e.g. Committee approved the hostel top-up on 28-Sep, release the full amount")
        if st.button("Save override", type="primary", icon=MI["save"], key=f"csr_ovb_{pid}"):
            if not reason.strip():
                st.error("Add a reason. It becomes the memory the agent learns from.")
            else:
                _done(safe(csr.payout_feedback, pid, "override", new_outcome=new_o, reason=reason, user=user,
                           label="payout_feedback"))
    with t_note:
        note = st.text_area("Note for the agent", key=f"csr_note_{pid}",
                            placeholder="e.g. Student says the college will send a corrected renewal form")
        if st.button("Save note", icon=MI["save"], key=f"csr_noteb_{pid}"):
            if not note.strip():
                st.error("The note is empty.")
            else:
                _done(safe(csr.payout_feedback, pid, "note", reason=note, user=user, label="payout_feedback"),
                      icon=MI["note"])
    with t_ver:
        st.write(f"Confirm that **{p['bank']} {p['account']}** (holder {p.get('account_holder', '—')}) really belongs "
                 f"to {p['student_name']}. It becomes the student's verified account, so future payouts to it can "
                 "release.")
        v1, v2 = st.columns([1, 2])
        how = v1.radio("How was it verified?", ["Call-back to the number on file", "Penny-drop test"],
                       key=f"csr_vhow_{pid}")
        vnote = v2.text_input("Detail (optional)", key=f"csr_vnote_{pid}",
                              placeholder="e.g. Called +91 98220 41873, student confirmed the HDFC account")
        if st.button("Verify account", type="primary", icon=MI["verify"], key=f"csr_vb_{pid}"):
            res = safe(csr.payout_feedback, pid, "verify_account", reason=f"{how}. {vnote}".strip(), user=user,
                       label="payout_feedback")
            if res and res.get("ok"):
                st.toast(res.get("message", "Account verified."), icon=MI["verify"])
                if p["status"] != "RELEASED":
                    with st.spinner("Re-checking the payout with the verified account…"):
                        d2 = safe(csr.decide_payout, pid, memory_on=True, label="decide_payout")
                    if d2:
                        st.success(f"Account verified. The agent now recommends **{PAYOUT_META[d2['outcome']][1]}**.",
                                   icon=MI["verify"])
            else:
                _done(res)
