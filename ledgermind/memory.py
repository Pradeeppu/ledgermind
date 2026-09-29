"""Memory layer. Hindsight is the long-term memory of the agent (retain / recall / reflect / observations).

`LocalMemory` is a tiny keyword store used only when HINDSIGHT_URL is not configured, so the app can
run offline during development. The UI shows which backend is active.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime

from . import config

log = logging.getLogger("ledgermind.memory")


def _date(v) -> str | None:
    if not v:
        return None
    return str(v)[:10]


class HindsightMemory:
    backend = "hindsight"

    def __init__(self) -> None:
        from hindsight_client import Hindsight

        self.hs = Hindsight(base_url=config.HINDSIGHT_URL, api_key=config.HINDSIGHT_API_KEY, timeout=120.0)
        self.bank = config.BANK_ID
        self._ready = False

    # ---- setup ----
    def ensure_bank(self) -> None:
        if self._ready:
            return
        try:
            self.hs.get_bank_config(self.bank)
        except Exception:
            self.hs.create_bank(
                self.bank, name="LedgerMind AP memory (Acme Components)", mission=config.MISSION,
                reflect_mission=config.MISSION,
                retain_mission=("Extract facts about vendors, invoices, amounts, bank accounts (masked), payment terms, "
                                "exceptions, and how the AP team resolved them, including who decided and why."),
                observations_mission=("Consolidate recurring vendor behaviour and the AP team's decisions into rules such as "
                                      "'Vendor X freight surcharge up to 3% is routinely approved'."),
                disposition_skepticism=config.DISPOSITION["skepticism"],
                disposition_literalism=config.DISPOSITION["literalism"],
                disposition_empathy=config.DISPOSITION["empathy"],
                enable_observations=True)
            for name, content in config.DIRECTIVES:
                try:
                    self.hs.create_directive(self.bank, name=name, content=content, priority=10)
                except Exception as e:  # directive may already exist
                    log.warning("directive %s: %s", name, e)
        self._ready = True

    def health(self) -> tuple[bool, str]:
        try:
            self.hs.get_version()
            self.ensure_bank()
            return True, f"Hindsight connected (bank {self.bank})"
        except Exception as e:
            return False, f"Hindsight unreachable: {e}"

    # ---- core operations ----
    def retain(self, text: str, *, tags: list[str], metadata: dict | None = None, timestamp: str | None = None,
               document_id: str | None = None, context: str | None = None, wait: bool = True) -> None:
        self.ensure_bank()
        ts = datetime.fromisoformat(timestamp) if timestamp else None
        md = {k: str(v) for k, v in (metadata or {}).items()}
        for attempt in range(3):  # NFR-R3: retry with back-off
            try:
                self.hs.retain(self.bank, text, timestamp=ts, context=context, document_id=document_id,
                               metadata=md, tags=tags, retain_async=not wait)
                return
            except Exception as e:
                log.warning("retain failed (attempt %s): %s", attempt + 1, e)
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("Hindsight retain failed after retries")

    def retain_batch(self, items: list[dict]) -> None:
        """items: [{content, tags, metadata, timestamp, context, document_id}]"""
        self.ensure_bank()
        payload = []
        for it in items:
            p = {"content": it["content"], "tags": it.get("tags", []),
                 "metadata": {k: str(v) for k, v in (it.get("metadata") or {}).items()}}
            if it.get("timestamp"):
                p["timestamp"] = it["timestamp"]
            if it.get("context"):
                p["context"] = it["context"]
            if it.get("document_id"):
                p["document_id"] = it["document_id"]
            payload.append(p)
        self.hs.retain_batch(self.bank, payload, retain_async=True)

    def recall(self, query: str, tags: list[str] | None = None, types: list[str] | None = None,
               limit: int = 8, budget: str = "mid") -> list[dict]:
        self.ensure_bank()
        r = self.hs.recall(self.bank, query, types=types, tags=tags, tags_match="any" if tags else "any",
                           budget=budget, max_tokens=3000)
        return [{"id": m.id, "text": m.text, "type": m.type or "world",
                 "date": _date(m.occurred_start or m.mentioned_at), "tags": m.tags or []}
                for m in (r.results or [])[:limit]]

    def reflect(self, query: str, context: str, schema: dict, tags: list[str] | None = None) -> dict:
        self.ensure_bank()
        r = self.hs.reflect(self.bank, query, context=context, response_schema=schema, tags=tags, budget="mid",
                            include_facts=True, apply_all_directives=True)
        mems = []
        if r.based_on and r.based_on.memories:
            mems = [{"id": m.id, "text": m.text, "type": m.type or "world",
                     "date": _date(m.occurred_start or m.mentioned_at)} for m in r.based_on.memories]
        return {"text": r.text, "structured": r.structured_output, "error": r.structured_output_error,
                "memories": mems}

    def observations(self, limit: int = 200) -> list[dict]:
        self.ensure_bank()
        r = self.hs.list_memories(self.bank, type="observation", limit=limit)
        out = []
        for m in r.items or []:
            out.append({"id": m.id, "text": m.text, "evidence_count": m.proof_count or len(m.source_memory_ids or []) or 1,
                        "first_seen": _date(m.occurred_start or m.mentioned_at),
                        "last_seen": _date(m.occurred_end or m.updated_at or m.mentioned_at),
                        "tags": m.tags or []})
        return out


class LocalMemory:
    """Offline fallback: a JSON-file store with keyword recall. No reflect (the agent uses its rule engine)."""

    backend = "local"

    def __init__(self) -> None:
        self.path = config.DATA_DIR / "local_memory.json"
        self._lock = threading.Lock()
        self._mtime = None
        self.items: list[dict] = []
        self._refresh()

    def _refresh(self) -> None:
        """Reload if another process (e.g. scripts/replay.py) rewrote the file, so we never serve or save stale data."""
        mtime = self.path.stat().st_mtime if self.path.exists() else None
        if mtime != self._mtime:
            self.items = json.loads(self.path.read_text(encoding="utf-8")) if mtime else []
            self._mtime = mtime

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
        self._mtime = self.path.stat().st_mtime

    def health(self) -> tuple[bool, str]:
        return True, "Local dev memory (set HINDSIGHT_URL to use Hindsight)"

    def ensure_bank(self) -> None:
        pass

    def retain(self, text: str, *, tags: list[str], metadata: dict | None = None, timestamp: str | None = None,
               document_id: str | None = None, context: str | None = None, wait: bool = True) -> None:
        with self._lock:
            self._refresh()
            self.items.append({"id": uuid.uuid4().hex[:12], "text": text, "tags": tags, "metadata": metadata or {},
                               "type": (metadata or {}).get("fact_type", "experience"), "date": (timestamp or "")[:10]})
            self._save()

    def retain_batch(self, items: list[dict]) -> None:
        with self._lock:
            self._refresh()
            for it in items:
                md = it.get("metadata") or {}
                self.items.append({"id": uuid.uuid4().hex[:12], "text": it["content"], "tags": it.get("tags", []),
                                   "metadata": md, "type": md.get("fact_type", "world"),
                                   "date": str(it.get("timestamp") or "")[:10]})
            self._save()

    def recall(self, query: str, tags: list[str] | None = None, types: list[str] | None = None,
               limit: int = 8, budget: str = "mid") -> list[dict]:
        with self._lock:
            self._refresh()
        words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
        scored = []
        for it in self.items:
            if tags and not set(tags) & set(it["tags"]):
                continue
            if types and it["type"] not in types:
                continue
            score = len(words & set(re.findall(r"[a-z0-9]+", it["text"].lower())))
            if score:
                scored.append((score, it["date"], it))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [{"id": it["id"], "text": it["text"], "type": it["type"], "date": it["date"], "tags": it["tags"]}
                for _, _, it in scored[:limit]]

    def reflect(self, query: str, context: str, schema: dict, tags: list[str] | None = None) -> dict:
        raise NotImplementedError("LocalMemory has no reflect")

    def observations(self, limit: int = 200) -> list[dict]:
        return []


_local = None
_thread = threading.local()


def get_memory():
    """One Hindsight client per thread (its sync API runs an asyncio loop per thread; Streamlit uses many threads)."""
    global _local
    if config.hindsight_enabled():
        if getattr(_thread, "memory", None) is None:
            _thread.memory = HindsightMemory()
        return _thread.memory
    if _local is None:
        _local = LocalMemory()
    return _local
