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

# ---- CSR & scholarships engine (docs/CSR_SERVICE_CONTRACT.md), selected independently of the AP engine
CSR_USING_MOCK = True
CSR_FALLBACK_REASON = ""

if os.environ.get("LEDGERMIND_MOCK", "").strip() in ("1", "true", "yes"):
    from ui import csr_mock as csr  # noqa: E402
    CSR_FALLBACK_REASON = "forced by LEDGERMIND_MOCK=1"
else:
    try:
        from ledgermind.csr import service as csr  # type: ignore  # noqa: E402

        if not callable(getattr(csr, "decide_payout", None)):
            raise AttributeError("ledgermind.csr.service has no decide_payout()")
        CSR_USING_MOCK = False
    except Exception as exc:  # ImportError, AttributeError, or engine init errors
        from ui import csr_mock as csr  # noqa: E402
        CSR_FALLBACK_REASON = f"{type(exc).__name__}: {exc}"

__all__ = ["svc", "USING_MOCK", "FALLBACK_REASON", "csr", "CSR_USING_MOCK", "CSR_FALLBACK_REASON"]
