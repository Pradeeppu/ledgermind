"""First-boot setup for hosted deployments (Render, etc.).

Hosted free tiers wipe the local disk on every deploy or restart, so the SQLite state and local memory
disappear. If no decisions exist yet, replay the history once so the app opens in demo state:
April to mid-September processed, the nine September invoices pending.

Run: python scripts/bootstrap.py   (safe to run on every start; it does nothing when data is present)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ledgermind import db  # noqa: E402


def main() -> None:
    if db.query("SELECT COUNT(*) AS n FROM decisions")[0]["n"]:
        print("bootstrap: data present, nothing to do")
        return
    print("bootstrap: empty database, seeding demo data...")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "replay.py"), "--reset"], check=True)


if __name__ == "__main__":
    main()
