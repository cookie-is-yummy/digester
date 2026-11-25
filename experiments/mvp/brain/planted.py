"""The verifier's planted set (eval/brain_planted.json, SPEC 4.8): every planted false sentence must be dropped with
one of its expected reasons, and at least 97% of the true ones kept. No model call.

    python3 -m mvp.brain.planted [--show dropped_true|kept_false|all]    (from experiments/)

A case: {"id", "source" ("new" | "insight_v5"), "class", "ledger" (a key of "ledgers"), "form" (a give_answer form),
"target" ("lead", "lead:N", "point:N", "outside:N", "item:N"), "expect" ("kept" | "dropped"), "reasons" (any one of
them is the expected reason; empty: any reason), "turn" (optional: message, unlock)}.
"""
import argparse
import json
import os
from datetime import date

from . import verify as V

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(HERE, "eval", "brain_planted.json")


def load(path=PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def outcome(case, ledgers):
    """(kept: bool, reasons: [str], verdict)"""
    led = V.Ledger(ledgers[case["ledger"]])
    t = case.get("turn") or {}
    today = date.fromisoformat(t["today"]) if t.get("today") else None
    turn = V.Turn(message=t.get("message", ""), unlock=t.get("unlock"), today=today)
    v = V.check_answer(case["form"], led, turn)
    tgt = case.get("target") or "point:0"
    kind, _, n = tgt.partition(":")
    if kind == "lead":
        os_ = [o for o in v.outcomes if o.where == "lead"]
        if n:
            o = next((o for o in os_ if o.index == int(n)), None)
            return (bool(o and o.kept), list(o.reasons) if o else ["missing"], v)
        return (bool(os_) and all(o.kept for o in os_), sorted({r for o in os_ for r in o.reasons}), v)
    if kind == "point":
        o = next((o for o in v.outcomes if o.where == "point" and o.index == int(n or 0)), None)
        return (bool(o and o.kept), list(o.reasons) if o else ["missing"], v)
    if kind == "outside":
        e = v.outside[int(n or 0)] if len(v.outside) > int(n or 0) else None
        return (bool(e and e["kept"]), list(e["reasons"]) if e else ["missing"], v)
    if kind == "item":
        e = v.items[int(n or 0)] if len(v.items) > int(n or 0) else None
        ok = bool(e and e["kept"] and not e["reasons"])
        return (ok, list(e["reasons"]) if e else ["missing"], v)
    raise ValueError(tgt)


def score(data=None):
    data = data or load()
    led = data["ledgers"]
    out = {"false": 0, "false_dropped": 0, "false_dropped_expected": 0, "true": 0, "true_kept": 0, "rows": [],
           "by_source": {}}
    for c in data["cases"]:
        kept, reasons, _v = outcome(c, led)
        want = c["expect"]
        exp = c.get("reasons") or []
        row = {"id": c["id"], "source": c.get("source"), "class": c.get("class"), "expect": want,
               "kept": kept, "reasons": reasons}
        src = out["by_source"].setdefault(c.get("source") or "new", {"false": 0, "false_dropped": 0, "true": 0,
                                                                     "true_kept": 0})
        if want == "dropped":
            out["false"] += 1
            src["false"] += 1
            if not kept:
                out["false_dropped"] += 1
                src["false_dropped"] += 1
                hit = not exp or any(r in reasons for r in exp)
                out["false_dropped_expected"] += hit
                row["reason_ok"] = hit
        else:
            out["true"] += 1
            src["true"] += 1
            out["true_kept"] += kept
            src["true_kept"] += kept
        out["rows"].append(row)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="", choices=("", "dropped_true", "kept_false", "wrong_reason", "all"))
    a = ap.parse_args(argv)
    s = score()
    print(json.dumps({k: v for k, v in s.items() if k != "rows"}, indent=1))
    for r in s["rows"]:
        bad = (r["expect"] == "kept" and not r["kept"]) or (r["expect"] == "dropped" and r["kept"])
        wrong = r["expect"] == "dropped" and not r["kept"] and r.get("reason_ok") is False
        if a.show == "all" or (a.show == "dropped_true" and r["expect"] == "kept" and not r["kept"]) or \
                (a.show == "kept_false" and r["expect"] == "dropped" and r["kept"]) or \
                (a.show == "wrong_reason" and wrong):
            print(("!! " if bad or wrong else "   ") + json.dumps(r))


if __name__ == "__main__":
    main()
