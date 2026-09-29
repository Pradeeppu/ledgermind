import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui.components import svc, safe, esc, page_header, section, current_user, USING_MOCK, MI  # noqa: E402
from ui.icons import svg  # noqa: E402

page_header("Settings", "Memory bank, decision thresholds and demo data")
user, me = current_user()

try:
    from ledgermind import config as cfg
except Exception:  # mock mode or engine not importable
    cfg = None

info = safe(svc.status, default={}) or {}
if not me["can_manage"]:
    st.info(f"You're signed in as {user} ({me['role']}). Settings are read-only; switch to an AP Manager to edit them.",
            icon=MI["lock"])

tab_mem, tab_rules, tab_demo = st.tabs([":material/database: Memory bank", ":material/tune: Thresholds",
                                         ":material/restart_alt: Demo data"])

# ---------------------------------------------------------------- memory bank
with tab_mem:
    c1, c2 = st.columns([1.2, 1], gap="large")
    with c1:
        backend = "Hindsight Cloud" if info.get("memory_backend") == "hindsight" else "Local memory (offline)"
        st.markdown(
            f'<div class="lm-card">{section("Connection", "database")}<table class="lm-kv">'
            f'<tr><td class="k">Backend</td><td><b>{esc(backend)}</b></td></tr>'
            f'<tr><td class="k">Bank ID</td><td><code>{esc(info.get("bank_id", "—"))}</code></td></tr>'
            f'<tr><td class="k">Reasoning</td><td>{esc(info.get("llm", "—"))}</td></tr>'
            f'<tr><td class="k">Status</td><td>{esc(info.get("message", "—"))}</td></tr></table></div>',
            unsafe_allow_html=True)
        if cfg:
            st.markdown(f'<div class="lm-card">{section("Mission", "bookmark")}'
                        f'<div style="font-size:.92rem;line-height:1.5">{esc(cfg.MISSION)}</div></div>',
                        unsafe_allow_html=True)
        if info.get("memory_backend") != "hindsight":
            st.caption("To use Hindsight, set `HINDSIGHT_URL` and `HINDSIGHT_API_KEY` in `.env` and restart the app.")
    with c2:
        if cfg:
            rows = "".join(f'<div class="lm-flag high"><div class="head"><b>{esc(n.replace("-", " ").title())}</b>'
                           f'<span class="lm-chip hard">{svg("lock", 12)}Directive</span></div>'
                           f'<div class="msg">{esc(t)}</div></div>' for n, t in cfg.DIRECTIVES)
            st.markdown(f'<div class="lm-card">{section("Directives (hard rules)", "shield-check", len(cfg.DIRECTIVES))}'
                        f'{rows}</div>', unsafe_allow_html=True)
            d = cfg.DISPOSITION
            bars = "".join(
                f'<div class="lm-meter-lbl"><span>{esc(k.title())}</span><b>{v} / 5</b></div>'
                f'<div class="lm-meter" style="margin-bottom:.55rem"><span style="width:{v * 20}%;background:#3730A3"></span></div>'
                for k, v in d.items())
            st.markdown(f'<div class="lm-card">{section("Disposition", "user")}{bars}'
                        '<div class="lm-muted">High skepticism: when evidence is thin, it escalates rather than '
                        'approves.</div></div>', unsafe_allow_html=True)
        else:
            st.caption("Bank configuration is shown when the real engine is running.")

# ---------------------------------------------------------------- thresholds
with tab_rules:
    if not cfg:
        st.caption("Thresholds are available when the real engine is running.")
    else:
        st.caption("These change how the agent decides from the next invoice onwards. Changes last until the app "
                   "restarts; put them in `.env` to keep them.")
        with st.form("thresholds"):
            a, b = st.columns(2)
            conf = a.slider("Auto-approve only at or above this confidence", 0.5, 0.99,
                            float(cfg.AUTO_APPROVE_CONFIDENCE), 0.01, disabled=not me["can_manage"])
            band = b.slider("Price-creep band (% over first-seen price)", 1.0, 10.0,
                            float(cfg.PRICE_CREEP_BAND_PCT), 0.5, disabled=not me["can_manage"])
            hv = a.number_input("High-value limit (₹), always needs a human", 50_000, 10_000_000,
                                int(cfg.HIGH_VALUE_LIMIT), 50_000, disabled=not me["can_manage"])
            cold = b.number_input("Cold start: invoices a vendor needs before auto-approval", 0, 10,
                                  int(cfg.COLD_START_MIN_INVOICES), 1, disabled=not me["can_manage"])
            if st.form_submit_button("Save thresholds", icon=MI["save"], type="primary",
                                     disabled=not me["can_manage"]):
                cfg.AUTO_APPROVE_CONFIDENCE, cfg.PRICE_CREEP_BAND_PCT = conf, band
                cfg.HIGH_VALUE_LIMIT, cfg.COLD_START_MIN_INVOICES = float(hv), int(cold)
                st.toast("Thresholds saved. They apply from the next decision.", icon=MI["save"])

# ---------------------------------------------------------------- demo data
with tab_demo:
    st.markdown("Rebuild the demo from scratch. This clears every decision and note, re-seeds vendor master data "
                "into memory, and replays April to mid-September with a simulated AP clerk. The nine September "
                "invoices are left pending for the live walkthrough.")
    if USING_MOCK:
        st.caption("Not available on mock data.")
    else:
        sure = st.checkbox("I understand this clears all decisions and feedback", disabled=not me["can_manage"])
        if st.button("Reset demo data", icon=MI["reset"], disabled=not (sure and me["can_manage"])):
            with st.spinner("Replaying six months of invoices…"):
                r = subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"],
                                   capture_output=True, text=True, cwd=str(ROOT))
            if r.returncode == 0:
                for k in ("selected_invoice", "compare_result", "compare_invoice", "last_batch", "chat"):
                    st.session_state.pop(k, None)
                st.success("Demo data rebuilt. " + (r.stdout.strip().splitlines() or [""])[-9], icon=MI["reset"])
            else:
                st.error(f"Replay failed:\n\n```\n{r.stderr[-1500:]}\n```")
