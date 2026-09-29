"""Render the LedgerMind demo video end to end (voice-over + scripted screen recording + captions).

Pipeline:
  1. Reset the demo data (replay.py --reset) so the 9 September invoices are pending.
  2. Neural text-to-speech for each scene's narration (edge-tts).
  3. Playwright drives the running app scene by scene and records it, with a visible cursor and captions.
  4. ffmpeg trims each clip to its narration, joins everything with a title card and an end card.

Needs the app running:  python -m streamlit run app.py   (default http://localhost:8501)
Run:                     python scripts/make_video.py [--voice en-IN-NeerjaNeural] [--url http://localhost:8501]
Output:                  video/LedgerMind_demo.mp4
"""
from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BUILD = ROOT / "video" / "build"
OUT = ROOT / "video" / "LedgerMind_demo.mp4"
W, H = 1600, 900  # browser viewport; upscaled to 1080p at the end

import edge_tts  # noqa: E402
import imageio_ffmpeg  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# ------------------------------------------------------------------------------------------------ scenes
SCENES = [
    dict(id="01_hook", page="", caption="AP teams re-check the same exceptions every week. AI agents forget. LedgerMind remembers.",
         text="Every week, accounts payable teams re-check the same invoice exceptions. How each vendor behaves lives in "
              "one clerk's head, and a normal AI agent forgets everything between sessions. So companies pay duplicates, "
              "miss slow price creep, and pay fake bank accounts. This is LedgerMind. An accounts payable agent that remembers."),
    dict(id="02_run", page="", caption="Priya R. · AP Clerk · 9 pending September invoices",
         text="I'm Priya, an AP clerk at Acme Components. I have nine pending September invoices. "
              "I'll let the agent run on all of them."),
    dict(id="03_krishna", page="compare", caption="Memory OFF: Approve  →  Memory ON: Escalate · 18 paid invoices went to ****4417, this one asks for ****9032",
         text="Now the interesting part. Same invoice, same checks, memory off versus memory on. Krishna Electricals. "
              "Amount matches, PO matches. Without memory, the agent approves it. With memory, it escalates. "
              "It remembers eighteen paid invoices went to the account ending 4417. This one asks for 9032. "
              "It tells me to call the vendor back before paying."),
    dict(id="04_sharma", page="compare", caption="Flag  →  Approve · cites 6 prior approvals and Priya's own note",
         text="It works the other way too. Sharma Logistics adds a two point one percent fuel surcharge. Memory off flags it. "
              "Memory on approves it, and cites six earlier approvals and my own note. One false alarm gone."),
    dict(id="05_teach", page="decision", caption="Teaching live: override + reason → retained in memory",
         text="Now I'll teach it. Vertex IT billed fifty-eight thousand rupees. Usually it's forty-two thousand. "
              "The agent flags it, which is right. But I know why. I override to approve, and type the reason: "
              "annual licence true-up, approved by Rakesh. That reason goes straight into memory. "
              "Next time a Vertex bill jumps, it's part of the evidence."),
    dict(id="06_rules", page="learned", caption="Rules distilled from human decisions · evidence counts · managers confirm or retire",
         text="Repeated decisions turn into learned rules, like the one about Sharma's freight surcharge. "
              "Each rule shows how much evidence backs it, and a manager can confirm it or retire it."),
    dict(id="07_curve", page="dashboard", caption="Needs a human: 100% → 18% · 22/22 risky invoices caught · 0 false auto-approvals",
         text="Does it actually learn? We replayed six months of synthetic invoices. In the first period, a human checked "
              "every invoice. By the end, only eighteen percent. It caught all twenty-two planted risky invoices, with zero "
              "false auto-approvals. Overall accuracy is only a little better, seventy-eight versus seventy-five "
              "percent, because it's careful with new vendors. The win is safety."),
    dict(id="08_hindsight", page="settings", caption="Hindsight: retain → recall → reflect → observations · mission · directives · disposition",
         text="Under the hood, it's Hindsight. Every decision and correction is retained with vendor tags. Before each "
              "invoice, it recalls that vendor's history. Reflect makes the call, guided by a mission, directives "
              "and a skeptical disposition. Hard rules, like a changed bank account, run in code first. "
              "Memory can make a decision stricter, never looser."),
    dict(id="09_ask", page="ask", caption="Every answer cites the memories it used",
         text="I can also just ask. Has Krishna Electricals ever changed bank details? "
              "The answer comes back with the memories it used."),
    dict(id="10_close", page="", caption="LedgerMind · built on Hindsight by Vectorize",
         text="LedgerMind learns your vendors the way a senior clerk does, and never forgets. "
              "Less busywork, and fewer fake invoices paid. The code is on GitHub. Thanks for watching."),
]

OVERLAY_JS = r"""
(draft) => {
  if (document.getElementById('lm-cap')) return;
  const st = document.createElement('style');
  st.textContent = `
    #lm-cap{position:fixed;left:50%;top:18px;transform:translateX(-50%);max-width:1180px;z-index:99999;
      background:rgba(17,24,39,.88);color:#fff;font:600 21px/1.35 Inter,Segoe UI,sans-serif;padding:14px 24px;
      border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.25);text-align:center;transition:opacity .35s;opacity:0}
    #lm-cap b{color:#5EEAD4}
    #lm-cur{position:fixed;left:800px;top:450px;z-index:100000;width:26px;height:26px;pointer-events:none;
      transition:left .7s cubic-bezier(.4,0,.2,1),top .7s cubic-bezier(.4,0,.2,1)}
    #lm-cur.click::after{content:'';position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;
      border:3px solid #3730A3;animation:lmping .45s ease-out}
    @keyframes lmping{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
    #lm-draft{position:fixed;bottom:16px;right:18px;z-index:99999;background:#FFF6E0;color:#8A5A00;border:1px solid #F4D58A;
      font:600 13px Inter,Segoe UI,sans-serif;padding:6px 12px;border-radius:999px}`;
  document.head.appendChild(st);
  const cap = document.createElement('div'); cap.id = 'lm-cap'; document.body.appendChild(cap);
  const cur = document.createElement('div'); cur.id = 'lm-cur';
  cur.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l16 9.5-7 1.6-3.6 6.9z" fill="#111827" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  document.body.appendChild(cur);
  if (draft) { const d = document.createElement('div'); d.id = 'lm-draft'; d.textContent = draft; document.body.appendChild(d); }
}
"""

CARD_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>html,body{margin:0;height:100%;font-family:Inter,Segoe UI,sans-serif}
body{display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#1E1B4B 0%,#3730A3 45%,#0F766E 100%);color:#fff}
.w{text-align:center}.t{font-size:88px;font-weight:800;letter-spacing:-2px;margin:26px 0 8px}.t span{color:#5EEAD4}
.s{font-size:30px;opacity:.92}.f{margin-top:44px;font-size:20px;opacity:.75}</style></head>
<body><div class="w">{logo}<div class="t">Ledger<span>Mind</span></div><div class="s">{sub}</div><div class="f">{foot}</div></div></body></html>"""


# ------------------------------------------------------------------------------------------------ helpers
def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    return r.stderr


def duration(path: Path) -> float:
    err = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


async def tts(text: str, path: Path, voice: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(str(path))


class Director:
    """Wraps a Playwright page with a visible cursor, captions and human-paced actions."""

    def __init__(self, page, draft: str | None):
        self.p, self.draft = page, draft

    def overlay(self):
        self.p.evaluate(OVERLAY_JS, self.draft)

    def caption(self, text: str):
        self.p.evaluate("t => { const c = document.getElementById('lm-cap'); c.textContent = t; c.style.opacity = t ? 1 : 0; }", text)

    def move(self, locator, dx: float = 0.5, dy: float = 0.5, pause: float = 0.8):
        box = locator.bounding_box()
        if not box:
            return
        x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
        self.p.evaluate("([x,y]) => { const c = document.getElementById('lm-cur'); c.style.left = x+'px'; c.style.top = y+'px'; }", [x, y])
        self.p.mouse.move(x, y)
        time.sleep(pause)

    def click(self, locator, pause: float = 0.5):
        locator.scroll_into_view_if_needed()
        self.move(locator)
        self.p.evaluate("() => { const c = document.getElementById('lm-cur'); c.classList.remove('click'); void c.offsetWidth; c.classList.add('click'); }")
        locator.click()
        time.sleep(pause)

    def scroll(self, dy: int, steps: int = 30, total: float = 3.0):
        for _ in range(steps):
            self.p.mouse.wheel(0, dy / steps)
            time.sleep(total / steps)

    def wait_text(self, text: str, timeout: float = 60):
        self.p.get_by_text(text).first.wait_for(timeout=timeout * 1000)


# ------------------------------------------------------------------------------------------------ scene actions
def act(d: Director, sid: str, budget: float):
    p = d.p
    if sid == "01_hook":
        time.sleep(2.0)
        d.move(p.get_by_text("Pending", exact=True).first, pause=1.2)
        d.move(p.get_by_text("Held from payment").first, pause=1.2)
        d.scroll(420, total=3.5)
        time.sleep(1.5)
        d.scroll(-420, total=2.0)
        d.move(p.locator(".lm-status").first, pause=1.5)
    elif sid == "02_run":
        time.sleep(1.0)
        d.click(p.get_by_role("button", name=re.compile(r"Run agent on \d+ pending")))
        d.wait_text("Approve:")
        d.move(p.get_by_text("Approve:").first, pause=1.5)
    elif sid in ("03_krishna", "04_sharma"):
        pick = "Bank change" if sid == "03_krishna" else "Freight surcharge"
        time.sleep(0.8)
        d.click(p.get_by_role("button", name=pick))
        time.sleep(1.2)
        d.click(p.get_by_role("button", name="Run both"))
        d.wait_text("Memory caught" if sid == "03_krishna" else "Memory removed")
        time.sleep(1.0)
        long = sid == "03_krishna"
        d.move(p.locator(".lm-verdict").first, pause=2.0 if long else 1.2)
        cards = p.locator(".lm-decision")
        d.move(cards.nth(0), dy=0.25, pause=2.5 if long else 1.2)
        d.move(cards.nth(1), dy=0.25, pause=2.5 if long else 1.2)
        d.move(p.locator(".lm-decision.%s .rat" % ("ESCALATE" if long else "APPROVE")).first, pause=2.5 if long else 1.2)
        if long:
            d.scroll(380, total=2.5)
    elif sid == "05_teach":
        time.sleep(0.8)
        sb = p.locator('[data-testid="stMain"] [data-testid="stSelectbox"]').first
        d.click(sb)
        p.keyboard.type("VX-1042", delay=60)
        time.sleep(0.6)
        p.keyboard.press("Enter")
        p.locator(".lm-card").filter(has_text="VX-1042").first.wait_for(timeout=60000)
        time.sleep(1.5)
        d.move(p.locator(".lm-decision").first, dy=0.2, pause=2.0)
        d.scroll(700, total=2.0)
        d.click(p.get_by_role("tab").filter(has_text="Override"))
        d.click(p.locator('[data-testid="stRadio"] label').filter(has_text="Approve").first)
        box = p.get_by_placeholder(re.compile("Fuel surcharge is contractual"))
        d.click(box)
        box.press_sequentially("Annual licence true-up, approved by Rakesh", delay=45)
        time.sleep(0.6)
        d.click(p.get_by_role("button", name="Save override"))
        d.wait_text("Saved to memory")
        d.move(p.get_by_text("Saved to memory").first, pause=2.0)
    elif sid == "06_rules":
        time.sleep(1.2)
        cards = p.locator(".lm-kpi")
        d.move(cards.nth(0), pause=1.5)
        d.move(p.get_by_text(re.compile("Sharma Logistics Pvt Ltd: freight")).first, pause=2.5)
        d.move(p.get_by_text(re.compile(r"\d+ cases")).first, pause=1.5)
        d.move(p.get_by_role("button", name="Confirm").first, pause=1.2)
        d.move(p.get_by_role("button", name="Retire").first, pause=1.2)
    elif sid == "07_curve":
        time.sleep(1.0)
        d.move(p.locator(".lm-kpi").nth(0), pause=2.5)
        chart = p.locator('[data-testid="stPlotlyChart"]').first
        d.move(chart, dx=0.08, dy=0.12, pause=3.0)
        d.move(chart, dx=0.95, dy=0.8, pause=3.0)
        d.move(p.locator(".lm-kpi").nth(2), pause=2.5)
        d.move(p.locator(".lm-kpi").nth(3), pause=2.5)
    elif sid == "08_hindsight":
        time.sleep(1.0)
        d.move(p.get_by_text("Mission", exact=True).first, pause=2.5)
        d.move(p.get_by_text("Bank Change", exact=True).first, pause=3.0)
        d.scroll(420, total=2.5)
        d.move(p.get_by_text("Skepticism").first, pause=2.5)
    elif sid == "09_ask":
        time.sleep(0.8)
        d.click(p.get_by_role("button", name="Has Krishna Electricals ever changed bank details?"))
        d.wait_text("memories cited", timeout=90)
        time.sleep(0.8)
        d.click(p.get_by_text(re.compile(r"\d+ memories cited")).first)
        time.sleep(1.0)
        d.scroll(300, total=1.5)
    elif sid == "10_close":
        time.sleep(1.5)
        d.move(p.get_by_role("link", name="Invoice queue"), pause=1.5)
        d.move(p.locator(".lm-status").first, pause=2.0)


def ready_selector(page_name: str) -> str:
    return {"": "Invoice queue", "compare": "Quick picks", "decision": "Review invoice", "learned": "Learned rules",
            "dashboard": "Learning curve", "settings": "Settings", "ask": "Ask LedgerMind"}[page_name]


# ------------------------------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--voice", default="en-IN-NeerjaNeural")
    ap.add_argument("--rate", default="+14%")
    ap.add_argument("--no-reset", action="store_true")
    ap.add_argument("--only", nargs="*", help="render only these scene ids (for re-takes)")
    args = ap.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)

    from ledgermind import service
    backend = service.status()["memory_backend"]
    draft = None if backend == "hindsight" else "Draft · recorded on local memory backend"
    print(f"memory backend: {backend}")
    if not args.no_reset:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], check=True, capture_output=True)
        print("demo data reset (9 pending)")

    scenes = [s for s in SCENES if not args.only or s["id"] in args.only]
    for s in scenes:  # 1. voice-over
        a = BUILD / f"{s['id']}.mp3"
        asyncio.run(tts(s["text"], a, args.voice, args.rate))
        s["audio"], s["dur"] = a, duration(a)
        print(f"tts {s['id']}: {s['dur']:.1f}s")

    from ui.icons import logo
    clips = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        def card(name: str, sub: str, foot: str, secs: float) -> Path:
            ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(BUILD / "raw"),
                                      record_video_size={"width": W, "height": H})
            pg = ctx.new_page()
            t0 = time.monotonic()
            pg.set_content(CARD_HTML.replace("{logo}", logo(132)).replace("{sub}", sub).replace("{foot}", foot))
            pg.wait_for_timeout(700)
            ready = time.monotonic() - t0
            time.sleep(secs)
            ctx.close()
            raw = Path(pg.video.path())
            out = BUILD / f"{name}.mp4"
            run([FFMPEG, "-y", "-ss", f"{ready:.2f}", "-i", str(raw), "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                 "-t", f"{secs:.2f}", "-vf", "scale=1920:1080:flags=lanczos,fps=30,fade=in:0:12", "-c:v", "libx264", "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)])
            return out

        if not args.only:
            clips.append(card("00_title", "The accounts payable agent that remembers every vendor",
                              "Built on Hindsight by Vectorize · Hindsight Hackathon", 3.5))

        for s in scenes:  # 2. screen recording
            ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(BUILD / "raw"),
                                      record_video_size={"width": W, "height": H})
            pg = ctx.new_page()
            t0 = time.monotonic()
            pg.goto(f"{args.url}/{s['page']}", wait_until="networkidle")
            pg.get_by_text(ready_selector(s["page"]), exact=True).first.wait_for(timeout=60000)
            pg.wait_for_timeout(1800)  # fonts, icons, charts settle
            d = Director(pg, draft)
            d.overlay()
            d.caption(s["caption"])
            ready = time.monotonic() - t0
            act(d, s["id"], s["dur"])
            remaining = s["dur"] + 0.9 - (time.monotonic() - t0 - ready)
            if remaining > 0:
                time.sleep(remaining)
            length = time.monotonic() - t0 - ready
            ctx.close()
            raw = Path(pg.video.path())
            out = BUILD / f"{s['id']}.mp4"
            run([FFMPEG, "-y", "-ss", f"{ready:.2f}", "-i", str(raw), "-i", str(s["audio"]), "-t", f"{length:.2f}",
                 "-vf", "scale=1920:1080:flags=lanczos,fps=30", "-af", "apad,aresample=24000", "-ac", "1",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)])
            clips.append(out)
            print(f"scene {s['id']}: {length:.1f}s")

        if not args.only:
            clips.append(card("99_end", "Remembers every vendor. Learns from every correction.",
                              "Code on GitHub (link in the description) · All data is synthetic", 5.0))
        browser.close()

    if args.only:
        print("re-rendered:", ", ".join(c.name for c in clips), "(run without --only to rebuild the full video)")
        return
    lst = BUILD / "concat.txt"  # 3. join
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", "30", "-preset", "veryfast", "-c:a", "aac", "-ar", "24000", "-movflags", "+faststart", str(OUT)])
    print(f"\nvideo: {OUT}  ({duration(OUT):.0f}s)")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], capture_output=True)
    print("demo data reset again, so the app is ready for a live demo")


if __name__ == "__main__":
    main()
