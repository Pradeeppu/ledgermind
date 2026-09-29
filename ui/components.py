"""Reusable UI building blocks for LedgerMind pages.

Icon conventions:
  * HTML we render ourselves -> ui.icons.svg(...) (one stroke icon set, consistent weight)
  * Native Streamlit widgets -> Material Symbols shortcodes (MI dict below)
  * Selectboxes and table cells -> plain text only (neither renders icons)
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui.backend import svc, USING_MOCK, FALLBACK_REASON  # noqa: E402,F401
from ui.icons import svg  # noqa: E402

# outcome -> (material icon, label, colour); icon and label always travel together (never colour alone)
OUTCOME_META = {
    "APPROVE": (":material/check_circle:", "Approve", "#0ca30c"),
    "FLAG": (":material/warning:", "Flag", "#fab219"),
    "ESCALATE": (":material/gpp_bad:", "Escalate", "#d03b3b"),
}
OUTCOME_SVG = {"APPROVE": "check-circle", "FLAG": "alert-triangle", "ESCALATE": "octagon-alert"}
STATUS_LABEL = {"PENDING": "Pending", "APPROVED": "Approved", "FLAGGED": "Flagged", "ESCALATED": "Escalated"}
STATUS_SVG = {"PENDING": "clock", "APPROVED": "check-circle", "FLAGGED": "alert-triangle", "ESCALATED": "octagon-alert"}
STATUS_TO_OUTCOME = {"APPROVED": "APPROVE", "FLAGGED": "FLAG", "ESCALATED": "ESCALATE"}
MEM_META = {"world": ("book-open", "Fact"), "experience": ("history", "Experience"), "observation": ("layers", "Observation")}

MI = {  # Material Symbols used by native widgets
    "run": ":material/play_arrow:", "rerun": ":material/refresh:", "open": ":material/arrow_forward:",
    "accept": ":material/check:", "override": ":material/edit:", "note": ":material/sticky_note_2:",
    "upload": ":material/upload_file:", "memory": ":material/neurology:", "error": ":material/error:",
    "confirm": ":material/verified:", "retire": ":material/archive:", "restore": ":material/unarchive:",
    "clear": ":material/delete_sweep:", "compare": ":material/compare_arrows:", "bank": ":material/account_balance:",
    "lock": ":material/lock:", "save": ":material/save:", "reset": ":material/restart_alt:",
}

USERS = {
    "Priya R.": {"role": "AP Clerk", "can_decide": True, "can_manage": False},
    "Rakesh M.": {"role": "AP Manager", "can_decide": True, "can_manage": True},
    "Anita D.": {"role": "Internal Auditor", "can_decide": False, "can_manage": False},
}


def current_user() -> tuple[str, dict]:
    name = st.session_state.get("user", "Priya R.")
    return name, USERS.get(name, USERS["Priya R."])


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def safe(fn, *args, default=None, label: str | None = None, **kwargs):
    """Call an engine function; show a friendly error instead of crashing."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        name = label or getattr(fn, "__name__", "engine call")
        st.error(f"**{name}** failed: {type(exc).__name__}: {exc}", icon=MI["error"])
        return default


def inr(x, decimals: int = 0) -> str:
    if x is None:
        return "—"
    neg = x < 0
    x = abs(float(x))
    whole = int(x)
    frac = f"{x - whole:.{decimals}f}"[1:] if decimals else ""
    t = str(whole)
    if len(t) > 3:
        head, tail = t[:-3], t[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        t = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + t + frac


def page_header(title: str, subtitle: str = ""):
    st.markdown(f'<div class="lm-title">{esc(title)}</div>'
                + (f'<div class="lm-sub">{esc(subtitle)}</div>' if subtitle else ""), unsafe_allow_html=True)


def section(title: str, icon: str | None = None, count: int | None = None) -> str:
    """Small uppercase card heading with an optional icon."""
    n = f' <span class="lm-count">{count}</span>' if count is not None else ""
    return f'<h4>{svg(icon, 14) if icon else ""}{esc(title)}{n}</h4>'


def chip(text: str, cls: str = "", icon: str | None = None) -> str:
    return f'<span class="lm-chip {esc(cls)}">{svg(icon, 13) if icon else ""}{esc(text)}</span>'


def outcome_chip(outcome: str | None) -> str:
    if not outcome:
        return chip("Pending", "PENDING", "clock")
    return chip(OUTCOME_META.get(outcome, ("", outcome, ""))[1], outcome, OUTCOME_SVG.get(outcome))


def status_chip(status: str) -> str:
    return chip(STATUS_LABEL.get(status, status), status, STATUS_SVG.get(status))


def kpi(col, label: str, value, hint: str = "", accent: bool = False, icon: str | None = None, tone: str = ""):
    ico = f'<span class="ico {esc(tone)}">{svg(icon, 16)}</span>' if icon else ""
    size = " sm" if len(str(value)) > 11 else ""
    col.markdown(f'<div class="lm-kpi{" accent" if accent else ""}"><div class="lbl">{ico}{esc(label)}</div>'
                 f'<div class="val{size}">{esc(value)}</div><div class="hint">{esc(hint)}</div></div>',
                 unsafe_allow_html=True)


def confidence_meter(conf: float | None, color: str) -> str:
    c = max(0.0, min(1.0, float(conf or 0)))
    lvl = "High" if c >= 0.85 else "Medium" if c >= 0.65 else "Low"
    return (f'<div class="lm-meter-lbl"><span>Confidence · {lvl}</span><b>{c * 100:.0f}%</b></div>'
            f'<div class="lm-meter" role="img" aria-label="confidence {c * 100:.0f} percent">'
            f'<span style="width:{c * 100:.0f}%;background:{color}"></span></div>')


def _code_label(code: str) -> str:
    return (code or "").replace("_", " ").title()


def flags_html(flags: list[dict]) -> str:
    if not flags:
        return f'<div class="lm-empty-row">{svg("shield-check", 15)}No risk flags raised.</div>'
    out = []
    for f in flags:
        sev = f.get("severity", "low")
        badges = chip(sev.title(), sev)
        if f.get("hard_rule"):
            badges += chip("Hard rule", "hard", "lock")
        out.append(f'<div class="lm-flag {esc(sev)}"><div class="head"><b>{esc(_code_label(f.get("code")))}</b>'
                   f'<span>{badges}</span></div><div class="msg">{esc(f.get("message"))}</div></div>')
    return "".join(out)


def decision_card(d: dict, show_mode: bool = True, compact: bool = False):
    """Decision card: colour + icon + text label (never colour alone)."""
    outcome = d.get("outcome", "FLAG")
    _, label, color = OUTCOME_META.get(outcome, ("", outcome, "#6B7280"))
    mode = d.get("memory_mode", "on")
    mode_txt = {"on": "Memory on", "off": "Memory off", "unavailable": "Memory unavailable"}.get(mode, mode)
    learned = "".join(f'<div class="lm-learned">{svg("lightbulb", 15)}<span>{esc(x)}</span></div>'
                      for x in d.get("learned_from") or [])
    flags = d.get("risk_flags") or []
    body = (f'<div class="lm-decision {esc(outcome)}">'
            + (f'<div class="mode">{svg("database" if mode == "on" else "power-off", 13)}{esc(mode_txt)} · agent recommendation</div>'
               if show_mode else "")
            + f'<div class="badge">{svg(OUTCOME_SVG.get(outcome, "circle-dot"), 30, 2.2)}<span>{esc(label)}</span></div>'
            + confidence_meter(d.get("confidence"), color)
            + f'<div class="rat">{esc(d.get("rationale", ""))}</div>'
            + f'<div class="lm-sect">Risk checks <span class="lm-count">{len(flags)}</span></div>' + flags_html(flags)
            + (('<div class="lm-sect">Learned from</div>' + learned) if learned else "")
            + (f'<div class="lm-foot">{svg("cpu", 13)}{esc(d.get("model", "—"))} · {esc(d.get("latency_ms", "—"))} ms · '
               f'{esc(d.get("decided_at", ""))}</div>' if not compact else "")
            + '</div>')
    st.markdown(body, unsafe_allow_html=True)


def memories_html(mems: list[dict]) -> str:
    if not mems:
        return '<div class="lm-muted">No memories were recalled for this decision.</div>'
    out = []
    for m in mems:
        t = m.get("type", "world")
        ico, lbl = MEM_META.get(t, ("circle-dot", t.title()))
        out.append(f'<div class="lm-mem"><div class="meta">{chip(lbl, t, ico)}'
                   f'<span>{esc(m.get("date", "") or "")}</span></div><div class="txt">{esc(m.get("text", ""))}</div></div>')
    return "".join(out)


def status_badge_html(st_info: dict | None) -> str:
    if USING_MOCK:
        return '<span class="lm-status mock"><i></i>Demo data (mock engine)</span>'
    if not st_info or not st_info.get("healthy", False):
        return '<span class="lm-status bad"><i></i>Memory unreachable</span>'
    if st_info.get("memory_backend") == "hindsight":
        return '<span class="lm-status ok"><i></i>Hindsight connected</span>'
    return '<span class="lm-status local"><i></i>Local memory (offline)</span>'


def goto_decision(invoice_id: str):
    st.session_state["selected_invoice"] = invoice_id
    try:
        st.switch_page("ui/pages/decision.py")
    except Exception:  # page run standalone (tests) – just remember selection
        st.rerun()


def invoice_label(row: dict) -> str:
    return f'{row["number"]} · {row["vendor_name"]} · {inr(row["total"])} · {STATUS_LABEL.get(row["status"], row["status"])}'


def read_only_notice():
    name, u = current_user()
    st.info(f"Signed in as {name} ({u['role']}). This role is read-only, so decisions can't be changed here.",
            icon=MI["lock"])
