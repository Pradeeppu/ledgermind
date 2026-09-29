"""Selects the engine: real `ledgermind.service` if importable, else the UI mock.

Set env LEDGERMIND_MOCK=1 to force the mock.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

USING_MOCK = True
FALLBACK_REASON = ""

if os.environ.get("LEDGERMIND_MOCK", "").strip() in ("1", "true", "yes"):
    from ui import mock_service as svc  # noqa: E402
    FALLBACK_REASON = "forced by LEDGERMIND_MOCK=1"
else:
    try:
        from ledgermind import service as svc  # type: ignore  # noqa: E402

        if not callable(getattr(svc, "decide", None)):
            raise AttributeError("ledgermind.service has no decide()")
        USING_MOCK = False
    except Exception as exc:  # ImportError, AttributeError, or engine init errors
        from ui import mock_service as svc  # noqa: E402
        FALLBACK_REASON = f"{type(exc).__name__}: {exc}"

__all__ = ["svc", "USING_MOCK", "FALLBACK_REASON"]
