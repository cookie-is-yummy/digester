"""PROTOTYPE ONLY - every model call of the MVP goes through experiments/lib/ai.py (AGENTS.md rule 11).

The MVP's own calls go to MVP_HOME/ai_runs.jsonl, each row tagged with the person it served, so the per-person daily
cap (rule 8) and the build cap (section 14) can be checked. Search calls made by a library's engine go to that
library's own ledger; they are counted too. No prompt text or item text is logged.
"""
import json
import os
import sys
import threading
from datetime import datetime

from . import config

# One fixed MVP ledger, whatever MVP_HOME is (test runs share the build cap). Set explicitly: a DIGESTER_DATA left
# over from demo work must not move the MVP's calls into a library's ledger.
LEDGER_HOME = os.path.abspath(os.environ.get("MVP_LEDGER_HOME", os.path.join(config.REPO, "data", "mvp")))
os.environ["DIGESTER_DATA"] = LEDGER_HOME
os.environ["DIGESTER_OPENAI_BUDGET_USD"] = str(config.TOTAL_CAP_USD)
sys.path.insert(0, os.path.join(config.EXP, "lib"))
import ai  # noqa: E402

# ai.py reads DIGESTER_DATA once, when it is first imported. A process that imports this module again with another
# MVP_LEDGER_HOME (the tests do) must not keep writing to the first one (it was the real data/mvp ledger).
ai.DATA = LEDGER_HOME
ai.LEDGER = os.path.join(LEDGER_HOME, "ai_runs.jsonl")
ai.TIMEOUT = float(os.environ.get("MVP_MODEL_TIMEOUT", "60"))  # a person is waiting: fail in a minute, not five
_tl = threading.local()
_orig_log = ai._log


def _log(row):
    row = dict(row)
    if getattr(_tl, "person", None):
        row["person"] = _tl.person
    _tl.cost = getattr(_tl, "cost", 0.0) + (row.get("cost_usd") or 0.0)  # this thread's calls only
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


# A library built by an import (refresh.py) records its build in its own ledger; that spend is also written to the
# MVP ledger (log_spend), so those rows are counted once, from the MVP ledger.
MIRRORED = ("demo_item_vectors_3l", "demo_key_check")


def _lib_rows(library):
    rows = _rows(os.path.join(library, "ai_runs.jsonl"))
    try:
        with open(os.path.join(library, "library.json"), encoding="utf-8") as f:
            mirrored = bool(json.load(f).get("mvp_import"))
    except (OSError, ValueError):
        mirrored = False
    return [r for r in rows if str(r.get("purpose", "")).startswith("demo_")
            and not (mirrored and r.get("purpose") in MIRRORED)]


def spent_today(handle, library):
    """Cost today (local server date) for one person: their MVP calls plus their library's search calls."""
    day = datetime.now().strftime("%Y-%m-%d")
    mine = sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER) if r.get("person") == handle and _today(r, day))
    lib = sum(r.get("cost_usd", 0) for r in _lib_rows(library) if _today(r, day))
    return mine + lib


def log_spend(person, purpose, cost_usd, **extra):
    """A cost made outside this process (a library build), written to the MVP ledger with the person it served."""
    ai._log({"provider": "openai", "purpose": purpose, "prompt_version": None, "cost_usd": round(cost_usd, 6),
             **extra, "person": person})


def started_at():
    """When the MVP's spending began, in the ledgers' own format (local time, no zone, as ai.py writes it)."""
    path = os.path.join(LEDGER_HOME, "started_at.txt")
    if not os.path.exists(path):
        os.makedirs(LEDGER_HOME, exist_ok=True)
        with open(path, "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    return open(path).read().strip()


def spent_total(libraries):
    """Build-and-test spend: the MVP ledger plus the libraries' search calls since the MVP started."""
    since = started_at()
    total = sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER))
    for lib in set(libraries):
        total += sum(r.get("cost_usd", 0) for r in _lib_rows(lib) if str(r.get("at", "")) >= since)
    return total


def chat_json(system, user, purpose, prompt_version, person=None, max_tokens=1200, temperature=None, seed=None):
    """One JSON call. Returns (parsed, cost_usd). temperature and seed are sent only when given."""
    _tl.person, _tl.cost = person, 0.0
    extra = {k: v for k, v in (("temperature", temperature), ("seed", seed)) if v is not None}
    try:
        out, _ = ai.openai_chat_json(config.MODEL, system, user, max_tokens=max_tokens, purpose=purpose,
                                     prompt_version=prompt_version, **extra)
        return out, _tl.cost
    finally:
        _tl.person = None
