import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from ui.components import (csr, safe, inr, esc, kpi, page_header, section, chip, current_user,  # noqa: E402
                           PAYOUT_STATUS_LABEL, TXN_LABEL, CSR_TONE)
from ui.icons import svg  # noqa: E402

page_header("Scholars", "What LedgerMind remembers about each student: accounts, payouts and transfers")
user, me = current_user()

students = safe(csr.list_students, default=[], label="list_students") or []
if not students:
    st.info("No students yet.")
    st.stop()
STATUS_TXT = {"ACTIVE": "Active", "DROPPED_OUT": "Dropped out", "DISCONTINUED": "Discontinued",
              "GRADUATED": "Graduated", "PAUSED": "Paused"}


def _st_label(s):  # engines may send "ACTIVE" or "active"
    s = (s or "").upper()
    return STATUS_TXT.get(s, s.replace("_", " ").title())


ids = [s["id"] for s in students]
cur = st.session_state.get("csr_student")
if cur not in ids:
    cur = ids[0]
s_row = st.selectbox("Student", students, index=ids.index(cur), key="csr_student_pick",
                     format_func=lambda s: f'{s["name"]} · {s["course"]} · {s["college"]} · {_st_label(s["status"])}')
st.session_state["csr_student"] = s_row["id"]

prof = safe(csr.student_profile, s_row["id"], label="student_profile")
if not prof:
    st.stop()
s = dict(prof.get("student", {}))
s["status"] = (s.get("status") or "").upper()
accounts = prof.get("accounts") or []
payouts = prof.get("payouts") or []

# ---------------------------------------------------------------- header card + KPIs
st.markdown(
    f'<div class="lm-card"><div style="display:flex;justify-content:space-between;align-items:center;gap:.6rem">'
    f'<div class="lm-person" style="margin:0"><div class="lm-avatar">'
    f'{esc("".join(w[0] for w in s.get("name", "?").split()[:2]).upper())}</div>'
    f'<div><div class="name">{esc(s.get("name"))}</div><div class="role">{esc(s.get("course"))} · year '
    f'{esc(s.get("year"))} · {esc(s.get("college"))}</div></div></div>'
    f'{chip(_st_label(s.get("status")), s.get("status", ""), "check-circle" if s.get("status") == "ACTIVE" else "x-circle")}'
    f'</div><div class="lm-muted" style="margin-top:.5rem">{svg("map-pin", 13)} {esc(s.get("region", "—"))} · '
    f'{svg("phone", 13)} {esc(s.get("phone", "—"))} · {svg("user", 13)} Accountant {esc(s.get("accountant", "—"))}'
    f'</div></div>', unsafe_allow_html=True)

credited = [p for p in payouts if p.get("txn_status") == "CREDITED"]
bad_accts = [a for a in accounts if a.get("state") in ("failed", "unverified")]
c = st.columns(4)
kpi(c[0], "Annual entitlement", inr(s.get("annual_entitlement")), "two instalments a year", accent=True,
    icon="graduation-cap")
kpi(c[1], "Received so far", inr(sum(p["amount"] for p in credited)), f"{len(credited)} credited payouts",
    icon="check-circle", tone="good")
kpi(c[2], "Accounts on file", len(accounts), f"{len(bad_accts)} need attention" if bad_accts else "all verified",
    icon="landmark", tone="crit" if bad_accts else "good")
kpi(c[3], "Remembered facts", len(prof.get("facts") or []), f'{len(prof.get("observations") or [])} observations',
    icon="database")
st.write("")

# ---------------------------------------------------------------- accounts + payouts
left, right = st.columns([1.35, 1], gap="large")
with left:
    st.markdown("**Account history**")
    if not accounts:
        st.caption("No bank accounts on file.")
    else:
        STATE_TXT = {"verified": "Verified", "failed": "Failed", "new": "New", "unverified": "Unverified"}
        adf = pd.DataFrame([{"State": STATE_TXT.get(a.get("state"), a.get("state")), "Bank": a["bank"],
                             "Account": a["account"], "IFSC": a.get("ifsc") or "—", "Holder": a.get("holder") or "—",
                             "Payouts": a.get("payouts", 0), "First used": a.get("first_used") or "—",
                             "Last used": a.get("last_used") or "—"} for a in accounts])
        name = s.get("name")

        def _hl(r):
            if r["State"] in ("Failed", "Unverified"):
                return ["background-color:#FDECEC;color:#9B1C1C"] * len(r)
            if r["State"] == "New":
                return ["background-color:#FFF6E0;color:#8A5A00"] * len(r)
            return [""] * len(r)

        st.dataframe(adf.style.apply(_hl, axis=1), hide_index=True, width="stretch")
        if len(accounts) > 1:
            st.markdown(f'<div class="lm-callout crit">{svg("alert-triangle", 18)}<div><b>The bank account changed.</b> '
                        f'{esc(name)} has {len(accounts)} accounts on file. Payouts to a changed account need a '
                        'call-back or penny-drop before release.</div></div>', unsafe_allow_html=True)
        for a in accounts:
            if a.get("state") == "failed":
                st.markdown(f'<div class="lm-callout crit">{svg("x-circle", 18)}<div><b>{esc(a["bank"])} '
                            f'{esc(a["account"])} failed.</b> The last transfer to it bounced. Ask the student for a '
                            'working account.</div></div>', unsafe_allow_html=True)
            if a.get("holder") and a["holder"] != name:
                st.markdown(f'<div class="lm-callout">{svg("user", 18)}<div>{esc(a["bank"])} {esc(a["account"])} is '
                            f'held by <b>{esc(a["holder"])}</b>, not the student.</div></div>', unsafe_allow_html=True)

    st.markdown("**Payout history**")
    if not payouts:
        st.caption("No payouts yet.")
    else:
        pdf = pd.DataFrame([{"Cycle": p["cycle_label"], "Amount": inr(p["amount"]),
                             "Payout": PAYOUT_STATUS_LABEL.get(p["status"], p["status"]),
                             "Transfer": TXN_LABEL.get(p.get("txn_status"), "Not sent"),
                             "Sent": p.get("sent_on") or "—", "Credited": p.get("credited_on") or "—",
                             "ID": p["payout_id"]} for p in payouts])
        st.dataframe(pdf.style.map(lambda v: f"color:{CSR_TONE[v]};font-weight:600" if v in CSR_TONE else "",
                                   subset=["Payout", "Transfer"]), hide_index=True, width="stretch")

with right:
    facts = prof.get("facts") or []
    st.markdown(f'<div class="lm-card">{section("Remembered facts", "book-open", len(facts))}'
                + ('<ul class="lm-facts">' + "".join(f"<li>{esc(f)}</li>" for f in facts) + "</ul>" if facts else
                   '<div class="lm-muted">Nothing remembered yet.</div>') + '</div>', unsafe_allow_html=True)
    obs = prof.get("observations") or []
    items = "".join(
        f'<div class="lm-mem"><div class="meta">{chip(o.get("status", "active").title(), o.get("status", "active"), "layers")}'
        f'<span>{esc(o.get("evidence_count", 0))} times · {esc(o.get("first_seen", ""))} to '
        f'{esc(o.get("last_seen", ""))}</span></div><div class="txt">{esc(o.get("text"))}</div></div>' for o in obs)
    st.markdown(f'<div class="lm-card">{section("Observations", "layers", len(obs))}'
                + (items or '<div class="lm-muted">No patterns observed for this student yet.</div>') + '</div>',
                unsafe_allow_html=True)
