"""PROTOTYPE ONLY - every model call of the MVP goes through experiments/lib/ai.py (AGENTS.md rule 11).

The MVP's own calls go to MVP_HOME/ai_runs.jsonl, each row tagged with the person it served (a keyed hash of the
handle, person_ref), so the per-person daily
cap (rule 8) and the build cap (section 14) can be checked. Search calls made by a library's engine go to that
library's own ledger; they are counted too. No prompt text or item text is logged.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
from datetime import datetime

from . import config

# One fixed MVP ledger, whatever MVP_HOME is (test runs share the build cap). Set explicitly: a DIGESTER_DATA left
# over from demo work must not move the MVP's calls into a library's ledger.
LEDGER_HOME = os.path.abspath(os.environ.get("MVP_LEDGER_HOME", os.path.join(config.REPO, "data", "mvp")))
os.environ["DIGESTER_DATA"] = LEDGER_HOME
os.environ["DIGESTER_OPENAI_BUDGET_USD"] = str(config.TOTAL_CAP_USD)
os.environ["DIGESTER_ANTHROPIC_BUDGET_USD"] = str(config.CLAUDE_CAP_USD)   # section 20: Claude has its own cap
sys.path.insert(0, os.path.join(config.EXP, "lib"))
import ai  # noqa: E402

# ai.py reads DIGESTER_DATA once, when it is first imported. A process that imports this module again with another
# MVP_LEDGER_HOME (the tests do) must not keep writing to the first one (it was the real data/mvp ledger).
ai.DATA = LEDGER_HOME
ai.LEDGER = os.path.join(LEDGER_HOME, "ai_runs.jsonl")
ai.TIMEOUT = float(os.environ.get("MVP_MODEL_TIMEOUT", "60"))  # a person is waiting: fail in a minute, not five
_tl = threading.local()
# ai.py's own _log. A second import of this module (the tests drop and import every mvp module again, many times) finds
# the wrapper an earlier import set and takes the function under it, so the wrappers never chain (round 9 merge: about
# a thousand imports in one pytest process passed Python's recursion limit).
_orig_log = getattr(ai._log, "_mvp_orig", ai._log)


_key_lock = threading.Lock()


def _person_key():
    """A random key kept beside the ledger (never in git), made at the first use."""
    path = os.path.join(LEDGER_HOME, "person_key.txt")
    with _key_lock:
        if not os.path.exists(path):
            os.makedirs(LEDGER_HOME, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32))
        with open(path) as f:
            return f.read().strip().encode()


def person_ref(handle):
    """review fix PRIV-5: the ledger names a person by a keyed hash of their handle, never the phone number or email
    itself, so a deletion leaves no handle in the shared ledger. The same handle always gives the same ref (the daily
    cap counts by it)."""
    if not handle:
        return handle
    return "p-" + hmac.new(_person_key(), str(handle).encode(), hashlib.sha256).hexdigest()[:20]


def rows_naming(handle):
    """Ledger rows written before PRIV-5 that hold the handle itself (counted for the deletion list)."""
    return sum(1 for r in _rows(ai.LEDGER) if r.get("person") == handle)


_run_lock = threading.Lock()
_RUN = {"usd": 0.0}   # section 20: this process's spend, for MVP_RUN_MAX_USD (eval_models.py sets it per eval)


def _log(row):
    row = dict(row)
    if getattr(_tl, "person", None):
        row["person"] = person_ref(_tl.person)
    tag = os.environ.get("MVP_RUN_TAG")
    if tag:   # section 20: eval_models.py finds its own rows (cost, latency) by this tag; unset in the bot
        row["run"] = tag[:80]
    _tl.cost = getattr(_tl, "cost", 0.0) + (row.get("cost_usd") or 0.0)  # this thread's calls only
    with _run_lock:
        _RUN["usd"] += row.get("cost_usd") or 0.0
    _orig_log(row)


_log._mvp_orig = _orig_log
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
BUILD_PURPOSES = ("mvp_import",)


def _lib_rows(library):
    rows = _rows(os.path.join(library, "ai_runs.jsonl"))
    try:
        with open(os.path.join(library, "library.json"), encoding="utf-8") as f:
            mirrored = bool(json.load(f).get("mvp_import"))
    except (OSError, ValueError):
        mirrored = False
    # review fix X4: every purpose the library's engine logged counts (its q8 refine calls are "c88_refine"); only a
    # build already written to the MVP ledger is left out here
    return [r for r in rows if not (mirrored and r.get("purpose") in MIRRORED)]


def spent_today(handle, library):
    """Cost today (local server date) for one person: their MVP calls plus their library's search calls."""
    day = datetime.now().strftime("%Y-%m-%d")
    refs = {handle, person_ref(handle)}   # rows from before PRIV-5 name the handle itself
    # review fix X3: a library build has its own limits (refresh.py: its cost cap and builds a day), so its spend is
    # left out of the person's daily cap; it still counts toward the total
    mine = sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER) if r.get("person") in refs and _today(r, day)
               and r.get("purpose") not in BUILD_PURPOSES)
    lib = sum(r.get("cost_usd", 0) for r in _lib_rows(library) if _today(r, day))
    return mine + lib


def log_spend(person, purpose, cost_usd, **extra):
    """A cost made outside this process (a library build), written to the MVP ledger with the person it served."""
    ai._log({"provider": "openai", "purpose": purpose, "prompt_version": None, "cost_usd": round(cost_usd, 6),
             **extra, "person": person_ref(person)})


def started_at():
    """When the MVP's spending began, in the ledgers' own format (local time, no zone, as ai.py writes it)."""
    path = os.path.join(LEDGER_HOME, "started_at.txt")
    if not os.path.exists(path):
        os.makedirs(LEDGER_HOME, exist_ok=True)
        with open(path, "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    return open(path).read().strip()


CLAUDE = "anthropic"   # the ledger's provider name for Claude rows (section 20)


def spent_total(libraries):
    """Build-and-test spend on OpenAI and Gemini: the MVP ledger plus the libraries' search calls since the MVP
    started. Section 20: Claude rows (provider "anthropic") have their own cap (spent_claude) and are not counted here."""
    since = started_at()
    total = sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER) if r.get("provider") != CLAUDE)
    for lib in set(libraries):
        total += sum(r.get("cost_usd", 0) for r in _lib_rows(lib) if str(r.get("at", "")) >= since
                     and r.get("provider") != CLAUDE)
    return total


def spent_claude():
    """Section 20: Claude spend, from the MVP ledger's rows whose provider is "anthropic" (config.CLAUDE_CAP_USD)."""
    return sum(r.get("cost_usd", 0) for r in _rows(ai.LEDGER) if r.get("provider") == CLAUDE)


def cap_reached(libraries):
    """The one place the total caps are read (section 20). "total": the OpenAI+Gemini spend is within the margin of
    config.TOTAL_CAP_USD; "claude": a Claude model is set and its spend is within the margin of config.CLAUDE_CAP_USD.
    None: room left. The per-person daily cap is spent_today's (it counts every provider)."""
    if spent_total(libraries) + config.TOTAL_CAP_MARGIN_USD >= config.TOTAL_CAP_USD:
        return "total"
    if config.claude_models() and spent_claude() + config.TOTAL_CAP_MARGIN_USD >= config.CLAUDE_CAP_USD:
        return "claude"
    return None


# ---------- section 20: the knobs a Claude call takes ----------
EFFORT = {"none": "low", "minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh",
          "max": "max"}   # an OpenAI reasoning_effort, said as Claude's output_config.effort
FALLBACK_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5")   # Haiku 5.5 has no server-side fallback


def claude_knobs(model, reasoning_effort=None):
    """(thinking, effort, fallbacks) for one Claude call from the settings (config.CLAUDE_*) and the caller's
    reasoning_effort (which wins over MVP_CLAUDE_EFFORT)."""
    eff = reasoning_effort if reasoning_effort else (config.CLAUDE_EFFORT or None)
    eff = EFFORT.get(str(eff).strip().lower()) if eff else None
    mode = "adaptive" if config.CLAUDE_THINKING == "adaptive" else "off"
    thinking, eff = ai.claude_thinking(model, mode, eff)
    return thinking, eff, bool(config.CLAUDE_FALLBACKS and model in FALLBACK_MODELS)


def _run_room(system, user, max_tokens, model):
    """MVP_RUN_MAX_USD (set by eval_models.py for one eval): refuse a call whose worst case would pass it."""
    cap = os.environ.get("MVP_RUN_MAX_USD")
    if not cap:
        return
    est = estimate_usd(system, user, max_tokens, model)
    with _run_lock:
        spent = _RUN["usd"]
    if spent + est > float(cap):
        mark = os.environ.get("MVP_RUN_STOP_FILE")   # eval_models.py: the evaluation says "ceiling reached"
        if mark:
            with open(mark, "a", encoding="utf-8") as f:
                f.write("refused\n")
        raise RuntimeError(f"budget stop (run): spent ${spent:.3f} + est ${est:.3f} > ${float(cap):.2f}")


def chat_json(system, user, purpose, prompt_version, person=None, max_tokens=1200, temperature=None, seed=None,
              model=None, reasoning_effort=None, schema=None):
    """One JSON call. Returns (parsed, cost_usd). temperature and seed are sent only when given. Round 9, slice U:
    `model` names another priced model for one call (a measurement; config.MODEL otherwise), with its
    `reasoning_effort` when given. Section 20: a model id starting with "claude-" goes to Anthropic (ai.py,
    anthropic_chat_json), which takes no temperature or seed (both are left out and named in the ledger row);
    `schema` (a JSON schema) is used there as structured output; the OpenAI path ignores it."""
    _tl.person, _tl.cost = person, 0.0
    model = model or config.MODEL
    claude = config.is_claude(model)
    try:
        _run_room(system, user, max_tokens, model)
        if claude:
            thinking, effort, fallbacks = claude_knobs(model, reasoning_effort)
            dropped = [k for k, v in (("temperature", temperature), ("seed", seed)) if v is not None]
            out, _ = ai.anthropic_chat_json(model, system, user, max_tokens=max_tokens, purpose=purpose,
                                            prompt_version=prompt_version, schema=schema, thinking=thinking,
                                            effort=effort, fallbacks=fallbacks, dropped=dropped)
            return out, _tl.cost
        extra = {k: v for k, v in (("temperature", temperature), ("seed", seed), ("reasoning_effort", reasoning_effort))
                 if v is not None}
        out, _ = ai.openai_chat_json(model, system, user, max_tokens=max_tokens, purpose=purpose,
                                     prompt_version=prompt_version, **extra)
        return out, _tl.cost
    except Exception as e:
        if _cut_after_send(e) and not _tl.cost:
            # review fix X4: we stopped waiting, but the request was sent and the server may finish and bill it. A
            # worst-case estimate is written, so both caps see it (ai.py logs only after a reply has come back)
            _log({"provider": CLAUDE if claude else "openai", "model": model, "purpose": purpose,
                  "prompt_version": prompt_version,
                  "n": 1, "in_tokens": int((len(system) + len(user)) / 3.5), "out_tokens": max_tokens,
                  "cost_usd": estimate_usd(system, user, max_tokens, model), "estimated": True,
                  "error": type(e).__name__})
        raise
    finally:
        _tl.person = None


def budget_stop(e):
    """review fix X6: True for ai.py's refusal of a call that would pass the total budget (nothing was sent)."""
    return isinstance(e, RuntimeError) and str(e).startswith("budget stop")


def estimate_usd(system, user, max_tokens, model=None):
    """The worst case of one call, as ai.py's guard works it out."""
    p = ai.prices().get(model or config.MODEL) or {}
    return round((len(system) + len(user)) / 3.5 / 1e6 * p.get("input_per_m", 0)
                 + max_tokens / 1e6 * p.get("output_per_m", 0), 6)


def _cut_after_send(e):
    """A time-out or a dropped connection: the request may have reached the server. Not a refusal before sending (the
    budget guard, a refused connection) and not an HTTP error answer (that came back, unbilled)."""
    import http.client
    import socket
    import urllib.error
    if isinstance(e, ai.ClaudeConnection):   # section 20: the SDK's own errors, as ai.py turns them
        return e.maybe_sent
    if isinstance(e, (ai.ClaudeHTTPError, ai.MissingKey, ai.ClaudeStop)):
        return False
    if isinstance(e, urllib.error.HTTPError):
        return False
    if isinstance(e, urllib.error.URLError):
        e = e.reason if isinstance(e.reason, BaseException) else None
        if e is None:
            return False
    if isinstance(e, ConnectionRefusedError):
        return False
    return isinstance(e, (TimeoutError, socket.timeout, ConnectionResetError, ConnectionAbortedError,
                          http.client.RemoteDisconnected, http.client.IncompleteRead))


# ---------- section 20: `python3 -m mvp.llm smoke [model]` and `python3 -m mvp.llm path-test` ----------
SMOKE_SYSTEM = "You fill in a small form. Answer with the form as JSON."
SMOKE_USER = ('Form: {"sum": <the number>, "sky": "<one word>"}. Fill it in: "sum" is 2 + 3; "sky" is the colour of '
              'a clear sky at noon.')


def smoke(models=None, out=print):
    """One tiny form call per Claude model (the configured ones, or `models`), through chat_json (so the ledger and
    the caps see it). Prints model, seconds, tokens and cost per call; never the key. Returns 0 when every call came
    back with the form filled, else 1; 2 when there is nothing to run or no key."""
    import time
    models = list(models or config.claude_models())
    if not models:
        out("No Claude model is set (MVP_MODEL, MVP_JUDGE_MODEL or MVP_ERRAND_MODEL). Name one: "
            "python3 -m mvp.llm smoke claude-haiku-5-5")
        return 2
    bad = [m for m in models if not config.is_claude(m)]
    if bad:
        out(f"Not a Claude model: {', '.join(bad)}")
        return 2
    try:
        name, _ = ai.anthropic_key()
    except ai.MissingKey as e:
        out(str(e))
        return 2
    out(f"key: from {name} (value not shown); base URL {ai.ANTHROPIC_URL}; ledger {ai.LEDGER}")
    rc = 0
    for m in models:
        n0 = len(_rows(ai.LEDGER))
        t0 = time.time()
        try:
            got, cost = chat_json(SMOKE_SYSTEM, SMOKE_USER, "mvp_smoke", "smoke_v1", max_tokens=300, model=m)
            rows = _rows(ai.LEDGER)[n0:]
            r = rows[-1] if rows else {}
            ok = isinstance(got, dict) and str(got.get("sum")).strip() == "5" and bool(got.get("sky"))
            out(f"{m}: {'ok' if ok else 'FORM WRONG'} {time.time() - t0:.2f} s, in {r.get('in_tokens')} out "
                f"{r.get('out_tokens')} tokens, ${cost:.6f}"
                + (f", served by {r['served_model']}" if r.get("served_model") else ""))
            rc |= 0 if ok else 1
        except Exception as e:  # noqa: BLE001 - our errors never hold the key or the reply's text
            out(f"{m}: FAILED {time.time() - t0:.2f} s: {type(e).__name__}: {e}")
            rc = 1
    return rc


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["smoke"]:
        return smoke(argv[1:] or None)
    if argv[:1] == ["path-test"]:
        r = ai.anthropic_path_test(*(argv[1:2] or []))
        print(json.dumps(r))
        return 0 if r["ok"] else 1
    print("usage: python3 -m mvp.llm smoke [model ...] | python3 -m mvp.llm path-test")
    return 2


if __name__ == "__main__":
    sys.exit(main())
