"""PROTOTYPE ONLY - score the interpreter on a rule evaluation file (DESIGN.md section 10, evalset/README.md).

    python3 -m mvp.eval_rules mvp/evalset/rules_dev_timing.jsonl [--limit N] [--ids t-dev-001,t-dev-007] [--out F]

Builds the situation each case names (the contexts in evalset/README.md), calls the real interpreter (no cache), and
compares its validated, completed form with the expected partial form by the README's matching rules. Prints one line
per failed case (the case texts are invented, so they may be printed) and a total; writes counts to a JSON file
(default: MVP_HOME/eval_rules/<file name>.json).
"""
import argparse
import json
import os
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

TZ = "America/New_York"
NOW = datetime(2026, 11, 12, 19, 7, tzinfo=timezone.utc)          # Thursday 12 Nov 2026, 14:07 in New York
LATE = datetime(2026, 11, 13, 2, 40, tzinfo=timezone.utc)         # Thursday 12 Nov 2026, 21:40 in New York
PERSON = {"handle": "eval-rules", "timezone": TZ}
PROFILE = [
    "Interests: cooking (level: comfortable home cook), Blender (beginner), home workouts (beginner), drawing and "
    "watercolor (beginner).",
    "Direction, in their words: \"get good enough at Blender to finish a small scene each week\".",
    "Preferences: none given.",
]


def _lib_spec(when, goal, searches):
    return {"when": when, "content": {"source": "library", "goal": goal, "searches": searches, "count": 1},
            "do": [{"action": "message.send"}]}


PASTA = {"id": 1, "status": "active", "created_at": "2026-11-01T13:00:00+00:00",
         "last_run_at": "2026-11-07T00:00:00+00:00", "next_run_at": "2026-11-14T00:00:00+00:00",
         "spec": _lib_spec({"type": "schedule", "days": ["FRI"], "times": ["19:00"], "every_weeks": 1},
                           "a pasta recipe for Friday dinner", ["pasta recipe", "easy pasta dinner"])}
WORKOUT = {"id": 2, "status": "active", "created_at": "2026-11-03T13:00:00+00:00", "last_run_at": None,
           "next_run_at": "2026-11-13T13:00:00+00:00",
           "spec": _lib_spec({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI"], "times": ["08:00"],
                              "every_weeks": 1}, "a short home workout", ["short home workout", "quick workout"])}
TODOS = [{"id": 1, "text": "buy basil", "list": "todo"}, {"id": 2, "text": "call the landlord", "list": "todo"},
         {"id": 3, "text": "book dentist appointment", "list": "todo"}]


def context(name):
    """(now, kwargs for interpret) for one context name of evalset/README.md."""
    c = {"rules": [], "pending": None, "last": None, "todos": [], "last_write": None, "about": PROFILE}
    now = NOW
    if name == "late_evening":
        now = LATE
    elif name == "one_rule":
        c["rules"] = [PASTA]
    elif name == "two_rules":
        c["rules"] = [PASTA, WORKOUT]
    elif name == "after_ask":
        c["last"] = {"goal": "quick chicken and rice dinners", "items": ["e1", "e2", "e3"], "rule_id": None,
                     "at": "2026-11-12T19:02:00+00:00", "request": "quick chicken and rice dinner ideas"}
    elif name == "after_rule_send":
        c["rules"] = [PASTA]
        c["last"] = {"goal": "a pasta recipe for Friday dinner", "items": ["e4"], "rule_id": 1,
                     "at": "2026-11-07T00:00:00+00:00"}
    elif name == "preview_open":
        c["pending"] = {"kind": "confirm_rule", "payload": {
            "text": "send me a pasta recipe every friday at 7pm",
            "spec": _lib_spec({"type": "schedule", "days": ["FRI"], "times": ["19:00"], "every_weeks": 1},
                              "a pasta recipe", ["pasta recipe", "easy pasta dinner"])}}
    elif name == "has_todos":
        c["todos"] = TODOS
    elif name == "after_write":
        c["todos"] = TODOS + [{"id": 4, "text": "pick up dry cleaning", "list": "todo"}]
        c["last_write"] = {"ago": "2 minutes ago", "say": "added to-do 4, \"pick up dry cleaning\", to the list \"todo\""}
    elif name == "clarify_open":
        c["pending"] = {"kind": "clarify", "payload": {
            "text": "every sunday send me a study tip until the end of the semester",
            "question": "When does your semester end?", "intent": "new_rule",
            "draft": _lib_spec({"type": "schedule", "days": ["SUN"], "times": ["09:00"], "every_weeks": 1},
                               "a study tip", ["study tips", "how to study"])}}
    elif name != "none":
        raise SystemExit(f"unknown context {name!r}")
    return now, c


# ---------- matching (evalset/README.md "Matching") ----------
SETS = {"days", "times", "month_days", "month_weeks", "except_dates", "kinds", "platforms", "extract", "do", "actions",
        "todo_number"}
STEM_LISTS = {"criteria", "avoid", "avoid_creators", "avoid_collections", "creators", "collections"}
STEM_SCALARS = {"lang", "list", "profile_note", "todo_text"}


def norm_when(w):
    """Rule 4: time X becomes times [X] when times is absent or empty; time is dropped."""
    if not isinstance(w, dict):
        return w
    w = dict(w)
    t = w.pop("time", None)
    if t is not None and not w.get("times"):
        w["times"] = [t]
    return w


def _name(a):
    return a.get("action") if isinstance(a, dict) else getattr(a, "action", a)


def _stem_hit(expected, got):
    return any(s and s in str(got).lower() for s in str(expected).lower().split("|"))


def cmp(key, e, g, path, diffs):
    if key == "when":
        e, g = norm_when(e), norm_when(g)
    if isinstance(e, dict):
        if not isinstance(g, dict):
            diffs.append(f"{path}: expected {json.dumps(e)}, got {json.dumps(g, default=str)}")
            return
        for k, ev in e.items():
            cmp(k, ev, g.get(k), f"{path}.{k}", diffs)
        return
    if isinstance(e, list):
        gl = g if isinstance(g, list) else ([] if g is None else [g])
        if not e:                                            # rule 8
            if gl:
                diffs.append(f"{path}: expected empty, got {json.dumps(gl, default=str)}")
            return
        if key in STEM_LISTS:                                # rule 7
            missing = [x for x in e if not any(_stem_hit(x, y) for y in gl)]
            if missing:
                diffs.append(f"{path}: expected entries like {missing}, got {json.dumps(gl, default=str)}")
            return
        if key in SETS:                                      # rule 5
            if key == "actions":
                gl = [_name(a) for a in gl]
            if set(map(json.dumps, e)) != set(map(json.dumps, gl)):
                diffs.append(f"{path}: expected {sorted(e, key=str)}, got {sorted(gl, key=str)}")
            return
        if e != gl:
            diffs.append(f"{path}: expected {e}, got {gl}")
        return
    if key in STEM_SCALARS:
        if g is None or not _stem_hit(e, g):
            diffs.append(f"{path}: expected like {e!r}, got {g!r}")
        return
    if e != g:
        diffs.append(f"{path}: expected {e!r}, got {g!r}")


def form_of(it):
    """What is compared: intent, spec.when, spec.content, the action names of spec.do, and the other fields. For
    clarify the half-built spec is used as returned (rule 2)."""
    if it.intent == "clarify":
        spec = it.draft or {}
    else:
        spec = it.spec.model_dump(exclude_none=True) if it.spec is not None else {}
    do = spec.get("do") or []
    do = [do] if isinstance(do, (str, dict)) else do
    return {"intent": it.intent, "when": spec.get("when"), "content": spec.get("content"),
            "do": [_name(a) for a in do], "fields": it.fields(), "it": it}


def match(exp, it, path=""):
    """The differences between one expect object and an Interpretation (empty: it matches)."""
    g = form_of(it)
    diffs = []
    if exp.get("intent") != g["intent"]:
        return [f"{path}intent: expected {exp.get('intent')}, got {g['intent']}"]
    for k in ("when", "content"):
        if k in exp:
            cmp(k, exp[k], g[k], path + k, diffs)
    if "do" in exp:                                          # rule 6: message.send is implied on both sides
        e, gd = set(exp["do"]) | {"message.send"}, set(g["do"]) | {"message.send"}
        if e != gd:
            diffs.append(f"{path}do: expected {sorted(e)}, got {sorted(gd)}")
    content = g["content"] or {}
    for k, ev in (exp.get("fields") or {}).items():
        p = f"{path}fields.{k}"
        if k == "also":
            if g["fields"].get("also") is None:
                diffs.append(f"{p}: expected a second interpretation, got none")
            else:
                diffs += match(ev, g["fields"]["also"], p + ".")
            continue
        got = g["fields"].get(k)
        if g["intent"] == "more" and k in ("avoid", "criteria", "outside") and not got:   # rule 9
            got = content.get(k)
        if k == "params":
            got = got or next((a.params for a in it.actions if a.action == "calendar.add"), {})
        cmp(k, ev, got, p, diffs)
    return diffs


def score_case(case, it):
    """(passed, the differences against `expect`)."""
    diffs = match(case["expect"], it)
    if not diffs:
        return True, []
    for alt in case.get("accept_also") or []:
        if not match(alt, it):
            return True, []
    return False, diffs


# ---------- running ----------
_seen = threading.local()


def _recording(chat):
    """Wraps llm.chat_json so each case keeps the raw forms the model returned (for --debug)."""
    def wrapped(*a, **kw):
        out, cost = chat(*a, **kw)
        getattr(_seen, "raws", []).append(out)
        return out, cost
    return wrapped


def run_case(case):
    from mvp.interpret import interpret
    now, c = context(case["ctx"])
    t0 = time.time()
    _seen.raws = []
    try:
        it, cost = interpret(case["text"], PERSON, c["rules"], c["pending"], c["last"], now, todos=c["todos"],
                             last_write=c["last_write"], about=c["about"])
    except Exception as e:  # noqa: BLE001
        return {"id": case["id"], "ok": False, "diffs": [f"error: {type(e).__name__}: {str(e)[:120]}"], "cost": 0.0,
                "seconds": round(time.time() - t0, 2)}
    ok, diffs = score_case(case, it)
    return {"id": case["id"], "ok": ok, "diffs": diffs, "cost": cost, "seconds": round(time.time() - t0, 2),
            "got": it.intent, "raws": list(_seen.raws)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", default=None, help="comma-separated case ids to run")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--debug", default=None, help="write the raw forms of failed cases to this JSON file")
    a = ap.parse_args(argv)
    from mvp import config, llm
    llm.chat_json = _recording(llm.chat_json)
    cases = [json.loads(line) for line in open(a.file, encoding="utf-8") if line.strip()]
    if a.ids:
        want = set(a.ids.split(","))
        cases = [c for c in cases if c["id"] in want]
    if a.limit:
        cases = cases[:a.limit]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        results = list(pool.map(run_case, cases))
    by_intent = defaultdict(lambda: [0, 0])
    for case, r in zip(cases, results, strict=True):
        by_intent[case["expect"]["intent"]][1] += 1
        by_intent[case["expect"]["intent"]][0] += r["ok"]
        if not r["ok"]:
            print(f"FAIL {r['id']}: " + "; ".join(r["diffs"]))
    passed = sum(r["ok"] for r in results)
    cost = sum(r["cost"] for r in results)
    name = os.path.splitext(os.path.basename(a.file))[0]
    summary = {"file": os.path.basename(a.file), "prompt_version": config.PROMPT_INTERPRET, "model": config.MODEL,
               "cases": len(results), "passed": passed, "score": round(passed / len(results), 3) if results else None,
               "by_intent": {k: {"passed": v[0], "cases": v[1]} for k, v in sorted(by_intent.items())},
               "failed": [r["id"] for r in results if not r["ok"]], "cost_usd": round(cost, 4),
               "cost_per_case_usd": round(cost / len(results), 5) if results else None,
               "seconds": round(time.time() - t0, 1), "at": datetime.now().isoformat(timespec="seconds")}
    out = a.out or os.path.join(config.HOME, "eval_rules", f"{name}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(summary, f, indent=1)
    if a.debug:
        with open(a.debug, "w") as f:
            json.dump([{k: r.get(k) for k in ("id", "diffs", "raws")} for r in results if not r["ok"]], f, indent=1)
    print(f"TOTAL {name}: {passed}/{len(results)} passed ({summary['score']}), cost ${cost:.4f}, written to {out}")
    return summary


if __name__ == "__main__":
    main()
