"""Build the demo video from a recorded narration (e.g. a WhatsApp voice note) instead of text-to-speech.

Steps:
  1. Clean the narration (high-pass, noise reduction, loudness normalisation).
  2. Keep only the planned sentence ranges per scene, shorten long pauses, and speed up slightly (pitch kept).
  3. Record each scene in the running app, timed to its narration, with cursor and captions (see make_video.py).
  4. Join everything with a title card and an end card, encoded at 1080p.

Run (app must be running on http://localhost:8501):
  python scripts/make_video_narrated.py "../WhatsApp Audio 2026-09-29 at 9.02.02 PM.mpeg"
Output: video/LedgerMind_demo_narrated.mp4
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import make_video as mv  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = mv.ROOT
BUILD = ROOT / "video" / "build_narrated"
OUT = ROOT / "video" / "LedgerMind_demo_narrated.mp4"
FF = mv.FFMPEG
VW, VH = 1600, 900  # recorded at this size, upscaled to 1080p (Playwright video ignores device_scale_factor)

# Sentence ranges (seconds in the original recording) kept for each scene, taken from its transcript.
# Cut: "Now comes the interesting part", the Vertex follow-up, the learned-rules section, "And that's the
# important point", the Ask LedgerMind section, "Less repetitive work...", and the repeated closing phrase.
PLAN = [
    ("01_hook", [(0.0, 30.9)], "AP teams re-check the same exceptions every week. AI agents forget. LedgerMind remembers."),
    ("02_run", [(30.9, 42.9)], "Priya R. · AP Clerk · 9 pending September invoices"),
    ("03_krishna", [(44.9, 95.9)],
     "Memory OFF: Approve  →  Memory ON: Escalate · 18 paid invoices went to ****4417, this one asks for ****9032"),
    ("04_sharma", [(95.9, 121.9)], "Flag  →  Approve · cites 6 prior approvals and Priya's own note"),
    ("05_teach", [(121.9, 151.9)], "Teaching live: override + reason → retained in memory"),
    ("07_curve", [(184.9, 218.9), (220.9, 225.9)],
     "Needs a human: 100% → 18% · 22/22 risky invoices caught · 0 false auto-approvals"),
    ("08_hindsight", [(225.9, 260.9)],
     "Hindsight: retain → recall → reflect → observations · mission · directives · disposition"),
    ("10_close", [(276.7, 285.4), (294.84, 300.8)], "LedgerMind · built on Hindsight by Vectorize"),
]


def silences(path: Path) -> list[tuple[float, float]]:
    err = subprocess.run([FF, "-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.3", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    return list(zip(starts, ends))


def snap(t: float, sil: list[tuple[float, float]], win: float = 0.9) -> float:
    """Move a cut point into the nearest pause so no word is clipped."""
    best = None
    for a, b in sil:
        mid = (a + b) / 2
        if a - win <= t <= b + win and (best is None or abs(mid - t) < abs(best - t)):
            best = mid
    return best if best is not None else t


def pieces(ranges, sil, max_pause: float = 0.4) -> list[tuple[float, float]]:
    """Split each kept range around long pauses, keeping max_pause of silence."""
    out = []
    for a, b in ranges:
        a, b = snap(a, sil), snap(b, sil)
        cur = a
        for s, e in sil:
            if s > cur and e < b and (e - s) > max_pause:
                keep = max_pause / 2
                out.append((cur, s + keep))
                cur = e - keep
        out.append((cur, b))
    return [(x, y) for x, y in out if y - x > 0.05]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--target", type=float, default=205.0, help="target total length in seconds (max 210)")
    ap.add_argument("--max-speed", type=float, default=1.2)
    args = ap.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    src = Path(args.audio).resolve()

    # 1. clean the whole narration once
    clean = BUILD / "clean.wav"
    mv.run([FF, "-y", "-i", str(src), "-ac", "1", "-ar", "48000", "-af",
            "highpass=f=80,lowpass=f=12000,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11", str(clean)])
    sil = silences(clean)

    # 2. plan the cuts and pick a speed that fits the target
    plan = [(sid, pieces(r, sil), cap) for sid, r, cap in PLAN]
    speech = sum(y - x for _, ps, _ in plan for x, y in ps)
    cards = 2.5 + 4.0
    speed = min(args.max_speed, max(1.0, speech / (args.target - cards - 0.3 * len(plan))))
    print(f"speech kept {speech:.1f}s of {mv.duration(src):.1f}s; speed x{speed:.2f} -> ~{speech / speed + cards:.0f}s total")

    scenes = []
    for sid, ps, cap in plan:
        out = BUILD / f"{sid}.wav"
        fc = "".join(f"[0:a]atrim={x:.3f}:{y:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={y - x - 0.03:.3f}:d=0.03[p{i}];"
                     for i, (x, y) in enumerate(ps))
        fc += "".join(f"[p{i}]" for i in range(len(ps))) + f"concat=n={len(ps)}:v=0:a=1,atempo={speed:.4f}[out]"
        mv.run([FF, "-y", "-i", str(clean), "-filter_complex", fc, "-map", "[out]", str(out)])
        scenes.append({"id": sid, "audio": out, "dur": mv.duration(out), "caption": cap,
                       "page": next(s["page"] for s in mv.SCENES if s["id"] == sid)})
        print(f"  {sid}: {scenes[-1]['dur']:.1f}s")

    # 3. reset demo data, then record
    from ledgermind import service
    draft = None if service.status()["memory_backend"] == "hindsight" else "Draft · recorded on local memory backend"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], check=True, capture_output=True)
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "30"]
    clips = []
    from ui.icons import logo
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        def ctx():
            return browser.new_context(viewport={"width": VW, "height": VH}, record_video_dir=str(BUILD / "raw"),
                                   record_video_size={"width": VW, "height": VH})

        def card(name, sub, foot, secs):
            c = ctx()
            pg = c.new_page()
            t0 = time.monotonic()
            pg.set_content(mv.CARD_HTML.replace("{logo}", logo(132)).replace("{sub}", sub).replace("{foot}", foot))
            pg.wait_for_timeout(800)
            ready = time.monotonic() - t0
            time.sleep(secs)
            c.close()
            o = BUILD / f"{name}.mp4"
            mv.run([FF, "-y", "-ss", f"{ready:.2f}", "-i", pg.video.path(), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", f"{secs:.2f}", "-vf", "scale=1920:1080:flags=lanczos,fade=in:0:10", *enc, "-c:a", "aac", "-b:a", "160k",
                    "-shortest", str(o)])
            return o

        clips.append(card("00_title", "The accounts payable agent that remembers every vendor",
                          "Built on Hindsight by Vectorize · Hindsight Hackathon", 2.5))
        for s in scenes:
            c = ctx()
            pg = c.new_page()
            t0 = time.monotonic()
            pg.goto(f"{args.url}/{s['page']}", wait_until="networkidle")
            pg.get_by_text(mv.ready_selector(s["page"]), exact=True).first.wait_for(timeout=60000)
            pg.wait_for_timeout(1800)
            pg.set_default_timeout(8000)  # a missed hover must not stall the take
            d = mv.Director(pg, draft)
            d.overlay()
            d.caption(s["caption"])
            ready = time.monotonic() - t0
            try:
                mv.act(d, s["id"], s["dur"])
            except Exception as e:  # noqa: BLE001 - a missed hover shouldn't ruin the take
                print(f"  (scene {s['id']}: action skipped: {str(e).splitlines()[0][:120]})")
            left = s["dur"] + 0.3 - (time.monotonic() - t0 - ready)
            if left > 0:
                time.sleep(left)
            length = time.monotonic() - t0 - ready
            c.close()
            o = BUILD / f"{s['id']}.mp4"
            mv.run([FF, "-y", "-ss", f"{ready:.2f}", "-i", pg.video.path(), "-i", str(s["audio"]), "-t", f"{length:.2f}",
                    "-vf", "scale=1920:1080:flags=lanczos,unsharp=5:5:0.6", "-af", "apad", *enc, "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                    str(o)])
            clips.append(o)
            print(f"  recorded {s['id']}: {length:.1f}s (voice {s['dur']:.1f}s)")
        clips.append(card("99_end", "Remembers every vendor. Learns from every correction.",
                          "github.com/Pradeeppu/ledgermind · All data is synthetic", 4.0))
        browser.close()

    lst = BUILD / "concat.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    mv.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), *enc, "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart", str(OUT)])
    print(f"\nvideo: {OUT} ({mv.duration(OUT):.0f}s)")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], capture_output=True)


if __name__ == "__main__":
    main()
