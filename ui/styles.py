"""Single CSS block for LedgerMind. Call inject() once per run (app.py does)."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
/* set the font on containers only; icon spans keep their own Material Symbols font */
html, body, .stApp, .stMarkdown p, .stMarkdown li, label p, [data-testid="stWidgetLabel"] p,
input, textarea{font-family:'Inter',system-ui,sans-serif;}
:root{
  --lm-ink:#111827; --lm-ink-2:#4B5563; --lm-ink-3:#6B7280;
  --lm-surface:#FFFFFF; --lm-line:#E5E7EB;
  --lm-indigo:#3730A3; --lm-teal:#0F766E;
  --lm-good:#0ca30c; --lm-good-ink:#0B6B1F; --lm-good-bg:#E8F7EC;
  --lm-warn:#fab219; --lm-warn-ink:#8A5A00; --lm-warn-bg:#FFF6E0;
  --lm-crit:#d03b3b; --lm-crit-ink:#9B1C1C; --lm-crit-bg:#FDECEC;
  --lm-info-bg:#EEF0FF;
}
.block-container{padding-top:1.6rem; padding-bottom:3rem; max-width:1400px;}
h1,h2,h3{letter-spacing:-0.01em;}
.lm-title{font-size:1.65rem;font-weight:700;color:var(--lm-ink);margin:0 0 .15rem 0;}
.lm-sub{color:var(--lm-ink-3);margin:0 0 1.1rem 0;font-size:.95rem;}

.lm-card{background:var(--lm-surface);border:1px solid var(--lm-line);border-radius:14px;
  padding:1rem 1.15rem;box-shadow:0 1px 2px rgba(17,24,39,.04),0 4px 14px rgba(17,24,39,.05);margin-bottom:.8rem;}
.lm-card h4{margin:0 0 .5rem 0;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--lm-ink-3);}

.lm-kpi{background:var(--lm-surface);border:1px solid var(--lm-line);border-radius:14px;padding:.85rem 1rem;
  box-shadow:0 1px 2px rgba(17,24,39,.04),0 4px 14px rgba(17,24,39,.05);height:100%;}
.lm-kpi .lbl{font-size:.75rem;color:var(--lm-ink-3);text-transform:uppercase;letter-spacing:.06em;}
.lm-kpi .val{font-size:1.6rem;font-weight:700;color:var(--lm-ink);line-height:1.25;}
.lm-kpi .hint{font-size:.78rem;color:var(--lm-ink-2);}
.lm-kpi.accent{border-left:4px solid var(--lm-indigo);}

.lm-chip{display:inline-flex;align-items:center;gap:.3rem;padding:.12rem .6rem;border-radius:999px;
  font-size:.78rem;font-weight:600;border:1px solid transparent;white-space:nowrap;}
.lm-chip.APPROVE,.lm-chip.APPROVED{background:var(--lm-good-bg);color:var(--lm-good-ink);border-color:#BFE6C8;}
.lm-chip.FLAG,.lm-chip.FLAGGED{background:var(--lm-warn-bg);color:var(--lm-warn-ink);border-color:#F4D58A;}
.lm-chip.ESCALATE,.lm-chip.ESCALATED{background:var(--lm-crit-bg);color:var(--lm-crit-ink);border-color:#F2B8B8;}
.lm-chip.PENDING{background:#F1F5F9;color:#334155;border-color:#CBD5E1;}
.lm-chip.world{background:#E0F2FE;color:#075985;}
.lm-chip.experience{background:#EDE9FE;color:#4C1D95;}
.lm-chip.observation{background:#CCFBF1;color:#115E59;}
.lm-chip.hard{background:#111827;color:#fff;}
.lm-chip.high{background:var(--lm-crit-bg);color:var(--lm-crit-ink);}
.lm-chip.medium{background:var(--lm-warn-bg);color:var(--lm-warn-ink);}
.lm-chip.low{background:#F1F5F9;color:#334155;}
.lm-chip.active{background:var(--lm-info-bg);color:var(--lm-indigo);}
.lm-chip.confirmed{background:var(--lm-good-bg);color:var(--lm-good-ink);}
.lm-chip.retired{background:#F3F4F6;color:#6B7280;text-decoration:line-through;}

.lm-decision{border-radius:16px;padding:1.1rem 1.2rem;border:2px solid;margin-bottom:.8rem;
  box-shadow:0 6px 24px rgba(17,24,39,.08);background:var(--lm-surface);}
.lm-decision.APPROVE{border-color:var(--lm-good);background:linear-gradient(180deg,var(--lm-good-bg),#fff 70%);}
.lm-decision.FLAG{border-color:var(--lm-warn);background:linear-gradient(180deg,var(--lm-warn-bg),#fff 70%);}
.lm-decision.ESCALATE{border-color:var(--lm-crit);background:linear-gradient(180deg,var(--lm-crit-bg),#fff 70%);}
.lm-decision .badge{font-size:1.9rem;font-weight:800;letter-spacing:.02em;display:flex;align-items:center;gap:.5rem;}
.lm-decision.APPROVE .badge{color:var(--lm-good-ink);}
.lm-decision.FLAG .badge{color:var(--lm-warn-ink);}
.lm-decision.ESCALATE .badge{color:var(--lm-crit-ink);}
.lm-decision .mode{font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:var(--lm-ink-3);font-weight:600;}
.lm-decision .rat{color:var(--lm-ink);font-size:.97rem;line-height:1.5;margin:.6rem 0;}
.lm-meter{height:10px;border-radius:999px;background:#E5E7EB;overflow:hidden;margin:.25rem 0 .1rem 0;}
.lm-meter>span{display:block;height:100%;border-radius:999px;}
.lm-meter-lbl{font-size:.78rem;color:var(--lm-ink-2);display:flex;justify-content:space-between;}

.lm-flag{display:flex;gap:.5rem;align-items:flex-start;padding:.45rem .6rem;border-radius:10px;
  background:#F9FAFB;border:1px solid var(--lm-line);margin:.3rem 0;font-size:.88rem;}
.lm-learned{background:var(--lm-info-bg);border-left:4px solid var(--lm-indigo);border-radius:10px;
  padding:.45rem .7rem;margin:.3rem 0;font-size:.86rem;color:#312E81;}
.lm-mem{padding:.6rem .7rem;border:1px solid var(--lm-line);border-radius:12px;margin:.4rem 0;background:#fff;}
.lm-mem .meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:.25rem;
  font-size:.75rem;color:var(--lm-ink-3);}
.lm-mem .txt{font-size:.87rem;color:var(--lm-ink);line-height:1.4;}

.lm-verdict{border-radius:18px;padding:1.2rem 1.4rem;margin:.6rem 0 1rem 0;color:#fff;
  background:linear-gradient(120deg,#312E81 0%,#3730A3 45%,#0F766E 100%);box-shadow:0 10px 30px rgba(55,48,163,.25);}
.lm-verdict .big{font-size:1.45rem;font-weight:800;margin-bottom:.25rem;}
.lm-verdict .small{opacity:.92;font-size:.95rem;}
.lm-vs{font-size:.8rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:.25rem .7rem;
  border-radius:999px;display:inline-block;margin-bottom:.4rem;}
.lm-vs.off{background:#F3F4F6;color:#374151;}
.lm-vs.on{background:#3730A3;color:#fff;}

.lm-brand{font-size:1.35rem;font-weight:800;color:var(--lm-indigo);letter-spacing:-.01em;}
.lm-brand span{color:var(--lm-teal);}
.lm-tag{font-size:.75rem;color:var(--lm-ink-3);margin-top:-.2rem;}
.lm-status{display:inline-flex;gap:.35rem;align-items:center;padding:.2rem .6rem;border-radius:999px;
  font-size:.78rem;font-weight:600;}
.lm-status.ok{background:var(--lm-good-bg);color:var(--lm-good-ink);}
.lm-status.local{background:var(--lm-info-bg);color:var(--lm-indigo);}
.lm-status.mock{background:var(--lm-warn-bg);color:var(--lm-warn-ink);}
.lm-status.bad{background:var(--lm-crit-bg);color:var(--lm-crit-ink);}
.lm-muted{color:var(--lm-ink-3);font-size:.85rem;}
div[data-testid="stMetric"]{background:#fff;border:1px solid var(--lm-line);border-radius:14px;padding:.7rem .9rem;}

/* ---- icon system ---- */
.lm-ico{display:inline-block;vertical-align:-0.18em;flex:none;}
.lm-chip .lm-ico{margin-right:.05rem;}
.lm-chip + .lm-chip{margin-left:.3rem;}
.lm-card h4{display:flex;align-items:center;gap:.4rem;}
.lm-count{display:inline-block;min-width:1.35rem;padding:0 .4rem;border-radius:999px;background:#EEF0F6;
  color:var(--lm-ink-2);font-size:.7rem;font-weight:700;text-align:center;letter-spacing:0;}
.lm-sect{margin:.85rem 0 .3rem 0;font-size:.72rem;font-weight:700;color:var(--lm-ink-3);letter-spacing:.07em;
  text-transform:uppercase;display:flex;align-items:center;gap:.4rem;}
.lm-foot{margin-top:.8rem;padding-top:.55rem;border-top:1px dashed var(--lm-line);font-size:.75rem;
  color:var(--lm-ink-3);display:flex;align-items:center;gap:.35rem;}
.lm-decision .mode{display:flex;align-items:center;gap:.35rem;}
.lm-decision .badge .lm-ico{margin-top:1px;}

/* risk flags: severity rail on the left, title + badges on one line */
.lm-flag{display:block;border-left:3px solid #CBD5E1;}
.lm-flag.high{border-left-color:var(--lm-crit);}
.lm-flag.medium{border-left-color:var(--lm-warn);}
.lm-flag .head{display:flex;justify-content:space-between;align-items:center;gap:.5rem;margin-bottom:.15rem;}
.lm-flag .head b{font-size:.86rem;color:var(--lm-ink);}
.lm-flag .msg{font-size:.84rem;color:var(--lm-ink-2);line-height:1.45;}
.lm-flag .lm-chip{font-size:.7rem;padding:.05rem .45rem;}
.lm-empty-row{display:flex;align-items:center;gap:.4rem;color:var(--lm-good-ink);font-size:.86rem;
  background:var(--lm-good-bg);border-radius:10px;padding:.45rem .6rem;}
.lm-learned{display:flex;gap:.5rem;align-items:flex-start;}
.lm-learned .lm-ico{margin-top:.12rem;color:var(--lm-indigo);}

/* KPI icon tile */
.lm-kpi .lbl{display:flex;align-items:center;gap:.45rem;}
.lm-kpi .val.sm{font-size:1.12rem;padding:.3rem 0 .15rem 0;letter-spacing:.01em;}
.lm-kpi .ico{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:7px;
  background:var(--lm-info-bg);color:var(--lm-indigo);}
.lm-kpi .ico.good{background:var(--lm-good-bg);color:var(--lm-good-ink);}
.lm-kpi .ico.warn{background:var(--lm-warn-bg);color:var(--lm-warn-ink);}
.lm-kpi .ico.crit{background:var(--lm-crit-bg);color:var(--lm-crit-ink);}

/* status pill with a live dot instead of coloured emoji */
.lm-status i{width:8px;height:8px;border-radius:50%;background:currentColor;display:inline-block;}
.lm-status.ok i{box-shadow:0 0 0 3px rgba(12,163,12,.18);}

/* brand lockup + signed-in user */
.lm-lockup{display:flex;align-items:center;gap:.6rem;margin-bottom:.1rem;}
.lm-lockup .name{font-size:1.2rem;font-weight:800;color:var(--lm-ink);letter-spacing:-.02em;line-height:1;}
.lm-lockup .name span{color:var(--lm-teal);}
.lm-lockup .tag{font-size:.72rem;color:var(--lm-ink-3);margin-top:.2rem;}
.lm-user{display:flex;align-items:center;gap:.6rem;padding:.55rem .65rem;border:1px solid var(--lm-line);
  border-radius:12px;background:#fff;}
.lm-avatar{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-weight:700;font-size:.8rem;color:#fff;background:linear-gradient(135deg,#3730A3,#0F766E);flex:none;}
.lm-user .who{font-weight:600;font-size:.88rem;color:var(--lm-ink);line-height:1.2;}
.lm-user .role{font-size:.75rem;color:var(--lm-ink-3);}
.lm-empty{text-align:center;padding:2.2rem 1rem;}
.lm-empty .circle{width:52px;height:52px;border-radius:50%;margin:0 auto .7rem auto;display:flex;align-items:center;
  justify-content:center;background:var(--lm-info-bg);color:var(--lm-indigo);}
.lm-vs{display:inline-flex;align-items:center;gap:.4rem;}
.lm-verdict .big{display:flex;align-items:center;gap:.55rem;}
.lm-card h4 .lm-ico{margin-right:.4rem;}
.lm-kv{width:100%;font-size:.88rem;border-collapse:collapse;border:none !important;margin:0;}
.lm-kv tr, .lm-kv td{border:none !important;background:transparent !important;}
.lm-kv td{padding:.24rem .4rem .24rem 0;vertical-align:top;}
.lm-kv tr + tr td{border-top:1px solid #F1F2F6 !important;}
.lm-mem .txt{display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden;}
.lm-mem:hover .txt{-webkit-line-clamp:unset;}
.lm-kv td.k{color:var(--lm-ink-3);width:22%;}
.lm-note{display:flex;gap:.45rem;margin-top:.6rem;padding:.5rem .6rem;border-radius:10px;background:#F9FAFB;
  border:1px solid var(--lm-line);font-size:.84rem;color:var(--lm-ink-2);font-style:italic;}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
