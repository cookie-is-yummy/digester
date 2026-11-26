"""The verifier's planted set (eval/brain_planted.json, SPEC 4.8): every planted false sentence must be dropped with
one of its expected reasons, and at least 97% of the true ones kept. No model call.

    python3 -m mvp.brain.planted [--show dropped_true|kept_false|all] [--check full|cells]    (from experiments/)

A case: {"id", "source" ("new" | "insight_v5"), "class", "ledger" (a key of "ledgers"), "form" (a give_answer form),
"target" ("lead", "lead:N", "point:N", "outside:N", "item:N"), "expect" ("kept" | "dropped" | "private_line": dropped,
or kept with code's private line), "reasons" (any one of them is the expected reason; empty: any reason), "turn"
(optional: message, unlock, today, names, sensitive_names)}. Source "audit_true" (the step 1 audit's true sentences) is
reported in by_source only, never in the bar's "true" counts. mvp20 fix: the verifier attack's cases (sources "attack"
and "attack_true") are reported in by_source only too; an attack point case carries "forms" (one per carrier lead).

mvp24: `--check cells` (or MVP_BRAIN_CHECK=cells) scores the cells-only checker (verify.CELLS) with each false case's
class from eval/brain_cells_classes.json: every CELL-class false case must be handled and every true one kept; the
FRAMING-class and POLICY-class cases are counted apart, by kind, and may go out. Under the private-row convention
(eval/brain_attack_cases.PRIVATE_ROW_CONVENTION) a case kept with the private line is not counted false. The exit code
is 1 when a cell-class case goes out or a true one is lost. `--check full` (the default) is today's line, unchanged.

mvp25: the cells line also scores the second attack (eval/brain_cells_attack2.json: an independent attacker's 131 false
and 46 true sentences on 8 saved held-out results; each runs as a point under its record's carrier lead and alone as a
lead). A false case that gets out either way is a KNOWN LEAK when the file lists it (by mode, with its family); the line
prints how many, and fails (exit 1) on a leak the file does not list. The cells rules were built on these cases, so a
count of 0 is IN SAMPLE: the line says so and never reads as "every cell-class case handled".
"""
import argparse
import json
import os
import re
from datetime import date

from . import verify as V

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(HERE, "eval", "brain_planted.json")
CLASSES_PATH = os.path.join(HERE, "eval", "brain_cells_classes.json")
ATTACK2_PATH = os.path.join(HERE, "eval", "brain_cells_attack2.json")


def load(path=PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def outcome(case, ledgers, mode=None):
    """(kept: bool, reasons: [str], verdict). A case with "forms" (the attack's point cases: one form per true carrier
    lead) counts as kept when ANY of its forms keeps the target, so a false point must be dropped under every carrier.
    `mode`: the checker's mode (None: verify.check_answer's own default)."""
    if case.get("forms"):
        best = None
        for f in case["forms"]:
            r = outcome(dict(case, form=f, forms=None), ledgers, mode)
            if best is None or (r[0] and not best[0]):
                best = r
        return best
    led = V.Ledger(ledgers[case["ledger"]])
    t = case.get("turn") or {}
    today = date.fromisoformat(t["today"]) if t.get("today") else None
    turn = V.Turn(message=t.get("message", ""), unlock=t.get("unlock"), today=today, names=list(t.get("names") or []),
                  sensitive_names=list(t.get("sensitive_names") or []))
    v = V.check_answer(case["form"], led, turn, mode=mode)
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
        if want == "private_line":
            # false said bare, true with code's line "Leaving out topics you keep private.": handled when dropped, or
            # when kept with the line asked for (the audit's F46, F46b; SPEC 4.3 step 13 as widened at step 1's close)
            kept = kept and not _v.private_line
            want = "dropped"
        exp = c.get("reasons") or []
        row = {"id": c["id"], "source": c.get("source"), "class": c.get("class"), "expect": want,
               "kept": kept, "reasons": reasons}
        src = out["by_source"].setdefault(c.get("source") or "new", {"false": 0, "false_dropped": 0, "true": 0,
                                                                     "true_kept": 0})
        if c.get("source") in ("audit_true", "attack_true"):
            # the audits' own true sentences: scored apart (the 97% bar is the planted set's true twins)
            src["true"] += 1
            src["true_kept"] += kept
            out["rows"].append(row)
            continue
        if c.get("source") == "attack":
            # mvp20 fix: the verifier attack's false sentences, scored apart from the builder's own cases (the bar's
            # "false" line stays the builder's and the step 1 audit's)
            src["false"] += 1
            src["false_dropped"] += not kept
            row["expect"] = "dropped"
            out["rows"].append(row)
            continue
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


def classes(path=CLASSES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["planted"]


def _kind(case):
    c = re.sub(r"\s*\(the audit expected.*", "", case.get("class") or "")
    c = re.sub(r"^planted: ", "", c)
    return c.split(":")[0].strip() if case.get("source") == "attack" else c


def score_cells(data=None, mode="cells"):
    """The cells-mode line: each false case handled or out, by class; the true ones kept (DESIGN 24)."""
    from ..eval import brain_attack_cases as ATK
    data = data or load()
    cls = classes()
    conv = {"attack_" + x for x in getattr(ATK, "PRIVATE_ROW_CONVENTION", ())}
    out = {"check": V.check_mode(mode).name, "off_codes": sorted(V.check_mode(mode).off), "true": 0, "true_kept": 0,
           "true_lost": [], "cell_out": [], "by_source": {}}
    cases = {}
    for c in data["cases"]:
        kept, _reasons, v = outcome(c, data["ledgers"], mode)
        src = c.get("source") or "new"
        if c["expect"] == "kept":
            b = out["by_source"].setdefault(src, {"true": 0, "true_kept": 0})
            b["true"] += 1
            b["true_kept"] += kept
            if src not in ("audit_true", "attack_true"):
                out["true"] += 1
                out["true_kept"] += kept
                if not kept:
                    out["true_lost"].append(c["id"])
            continue
        base = re.sub(r"_[LP]$", "", c["id"]) if src == "attack" else c["id"]
        line_ok = bool(v.private_line) and (c["expect"] == "private_line" or c["id"] in conv or base in conv)
        handled = (not kept) or line_ok
        e = cases.setdefault(base, {"src": src, "class": cls[c["id"]]["class"], "handled": True, "line": False,
                                    "kind": _kind(c)})
        e["handled"] = e["handled"] and handled
        e["line"] = e["line"] or (kept and line_ok)
    for cid, e in sorted(cases.items()):
        b = out["by_source"].setdefault(e["src"], {})
        k = b.setdefault(e["class"], {"false": 0, "handled": 0, "kept_under_private_line": 0, "out": 0, "out_by_kind": {}})
        k["false"] += 1
        k["handled"] += e["handled"]
        k["kept_under_private_line"] += e["line"]
        if not e["handled"]:
            k["out"] += 1
            k["out_by_kind"][e["kind"]] = k["out_by_kind"].get(e["kind"], 0) + 1
            if e["class"] == "cell":
                out["cell_out"].append(cid)
    a2 = score_attack2(mode)
    out["attack2"] = a2
    out["known_leaks"] = len(a2["known_leaks"])
    out["ok"] = not out["cell_out"] and out["true_kept"] == out["true"] and not a2["new_leaks"]
    out["summary"] = (f"cells mode: planted cell-class cases out {len(out['cell_out'])}, true kept "
                      f"{out['true_kept']} of {out['true']}; second attack: "
                      f"{a2['false'] - len(a2['out'])} of {a2['false']} false handled, "
                      f"{len(a2['known_leaks'])} known leaks"
                      + (f" ({', '.join(f'{k} {v}' for k, v in sorted(a2['known_leaks'].items()))})"
                         if a2["known_leaks"] else "")
                      + (f", {len(a2['new_leaks'])} NEW leaks {a2['new_leaks']}" if a2["new_leaks"] else "")
                      + f", true kept {a2['true_kept']} of {a2['true']}. The cells rules were built on these sets: "
                        "every figure is in sample, and an empty leak list is not a closed checker.")
    return out


def load_attack2(path=ATTACK2_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def attack2_outcome(case, data, mode=None):
    """(point kept, lead kept) of one second-attack case: the sentence as a point under its record's carrier lead, and
    alone as a lead."""
    led = V.Ledger(data["ledgers"][case["record"]])
    t = data["turns"][case["record"]]
    turn = V.Turn(message=t["message"], unlock=t["unlock"], screen=t["screen"],
                  today=date.fromisoformat(t["today"]) if t.get("today") else None, names=list(t["names"]),
                  sensitive_names=list(t["sensitive_names"]))
    vp = V.check_answer({"lead": data["carriers"][case["record"]], "points": [case["text"]]}, led, turn, mode=mode)
    op = next(o for o in vp.outcomes if o.where == "point")
    vl = V.check_answer({"lead": case["text"], "points": []}, led, turn, mode=mode)
    ol = [o for o in vl.outcomes if o.where == "lead"]
    return bool(op.kept), bool(ol) and all(o.kept for o in ol)


def score_attack2(mode=None, data=None):
    """The second attack in one mode: the false cases out (point or lead kept), against the file's known leaks of that
    mode; the true ones kept both ways."""
    data = data or load_attack2()
    name = V.check_mode(mode).name
    known = dict((data.get("known_leaks") or {}).get(name) or {})
    out = {"mode": name, "false": 0, "out": [], "out_by_family": {}, "true": 0, "true_kept": 0, "true_lost": [],
           "known_leaks": known, "new_leaks": [], "in_sample": True}
    for c in data["cases"]:
        p, lk = attack2_outcome(c, data, mode)
        if c["truth"] == "F":
            out["false"] += 1
            if p or lk:
                out["out"].append(c["id"])
                out["out_by_family"][c["family"]] = out["out_by_family"].get(c["family"], 0) + 1
                if c["id"] not in known:
                    out["new_leaks"].append(c["id"])
        else:
            out["true"] += 1
            if p and lk:
                out["true_kept"] += 1
            else:
                out["true_lost"].append(c["id"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="", choices=("", "dropped_true", "kept_false", "wrong_reason", "all"))
    ap.add_argument("--check", default=None, choices=V.CHECK_MODES,
                    help="the checker's mode (default: MVP_BRAIN_CHECK, else full)")
    a = ap.parse_args(argv)
    if V.check_mode(a.check).name == "cells":
        s = score_cells(mode="cells")
        print(json.dumps(s, indent=1))
        return 0 if s["ok"] else 1
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
    raise SystemExit(main())
