"""PROTOTYPE ONLY - every model call of the MVP goes through experiments/lib/ai.py (AGENTS.md rule 11).

The MVP's own calls go to MVP_HOME/ai_runs.jsonl, each row tagged with the person it served, so the per-person daily
cap (rule 8) and the build cap (section 14) can be checked. Search calls made by a library's engine go to that
library's own ledger; they are counted too. No prompt text or item text is logged.
"""
import json
import os
import sys
import threading
from datetime import datetime, timezone

from . import config

os.environ.setdefault("DIGESTER_DATA", config.HOME)
os.environ.setdefault("DIGESTER_OPENAI_BUDGET_USD", str(config.TOTAL_CAP_USD))
sys.path.insert(0, os.path.join(config.EXP, "lib"))
import ai  # noqa: E402

_tl = threading.local()
_orig_log = ai._log


def _log(row):
    row = dict(row)
    if getattr(_tl, "person", None):
        row["person"] = _tl.person
    _orig_log(row)


ai._log = _log


class Budget(Exception):
    pass


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _today(row, day):
    return str(row.get("at", "")).startswith(day)


def spent_today(handle, library):
    """Cost today (local server date) for one person: their MVP calls plus their library's search calls."""
    day = datetime.now().strftime("%Y-%m-%d")
    mine = sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER) if r.get("person") == handle and _today(r, day))
    lib = sum(r.get("cost_usd", 0) for r in _rows(os.path.join(library, "ai_runs.jsonl"))
              if _today(r, day) and str(r.get("purpose", "")).startswith("demo_"))
    return mine + lib


def spent_total(libraries, since):
    """Build-and-test spend since the MVP started: the MVP ledger plus the libraries' search calls since then."""
    total = sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER))
    for lib in set(libraries):
        total += sum(r.get("cost_usd", 0) for r in _rows(os.path.join(lib, "ai_runs.jsonl"))
                     if str(r.get("at", "")) >= since and str(r.get("purpose", "")).startswith("demo_"))
    return total


def library_spent(library):
    return sum(r.get("cost_usd", 0) for r in _rows(os.path.join(library, "ai_runs.jsonl")))


def chat_json(system, user, purpose, prompt_version, person=None, max_tokens=1200):
    """One JSON call. Returns (parsed, cost_usd)."""
    _tl.person = person
    try:
        before = os.path.getsize(ai.LEDGER) if os.path.exists(ai.LEDGER) else 0
        out, _ = ai.openai_chat_json(config.MODEL, system, user, max_tokens=max_tokens, purpose=purpose,
                                     prompt_version=prompt_version)
        cost = 0.0
        with open(ai.LEDGER) as f:
            f.seek(before)
            for line in f:
                if line.strip():
                    cost += json.loads(line).get("cost_usd", 0)
        return out, cost
    finally:
        _tl.person = None


def now_utc():
    return datetime.now(timezone.utc)
