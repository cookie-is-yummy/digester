"""SPEC 4.8 source 1 and the step-1 proof (DECISIONS "Build order changes"): the insight_v5 sentences of
eval/insight_cases.json (slotted, `{themes[0].share}`), turned by code into the brain's marker form
(`31%[r1.themes[0].share]`, `Blender 3D[r1.themes[0]]`) over the same sheet wrapped in the result envelope of SPEC 2.3,
then read by brain/verify.check_answer one sentence at a time and compared with what insight's own eval
(eval_insight.v5_scores) says of the same sentence.

    python3 eval/convert_insight_cases.py [--json OUT]    (from experiments/mvp; no model call, made-up sheets only)

The labels do not carry over one to one: in the "sent" and "gated" blocks insight keeps a true sentence after code
rewrote it (its base, its second value: the `good` words), and a planted one counts as caught when it goes out
without its false words. The brain's verifier never adds words, so a sentence that is true only after a rewrite is
read here as what it is when typed: incomplete or false, to be dropped. Each sentence is put in one of four classes:
  true_as_typed   insight keeps it and its `good` words (if any) are already in the plain fill
  true_rewritten  insight keeps it only with words code adds (expected dropped by the verifier)
  planted         a planted false sentence (expected dropped)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp import insight as I  # noqa: E402
from mvp import eval_insight as E  # noqa: E402
from mvp.brain import verify as V  # noqa: E402
from mvp.tests.brain_envelope import envelope, tool_of  # noqa: E402

CASES = os.path.join(HERE, "insight_cases.json")
PHRASE_PATHS = ("window.words", "previous.words")


def load():
    with open(CASES, encoding="utf-8") as f:
        d = json.load(f)
    cases = {c["id"]: c for c in d["cases"]}
    extra = (d.get("v5") or {}).get("sheets") or {}
    return d, cases, extra


def to_markers(text, sheet, rid="r1"):
    """A slotted v5 sentence in marker form over `sheet` (the envelope's shown sheet): a row's name slot becomes a row
    marker, another name or phrase slot the typed words (window and base-period words carry no marker), a number
    slot insight's own formatting of the value followed by its value marker. None when a slot does not resolve."""
    out, last = [], 0
    for m in I.SLOT.finditer(text):
        path = re.sub(r"\s+", "", m.group(1))
        segs = I._path_segs(path)
        try:
            v = I._resolve(sheet, segs)
        except KeyError:
            return None
        key = segs[-1][0] if segs[-1][1] is None else None
        out.append(text[last:m.start()])
        last = m.end()
        if path in PHRASE_PATHS or (key in I.PHRASE_KEYS):
            out.append(I._fmt_value(key or "words", v) or str(v))
            continue
        if isinstance(v, str):
            owner = I._path_str(segs[:-1]) if segs[-1][1] is None and len(segs) > 1 else path
            try:
                rec = I._resolve(sheet, I._path_segs(owner))
            except KeyError:
                rec = None
            if isinstance(rec, dict) and key == I._record_name_key(rec):
                out.append(f"{v}[{rid}.{owner}]")
            elif key in I.DATE_KEYS:
                out.append(f"{I._fmt_value(key, v)}[{rid}.{path}]")
            else:
                out.append(f"{v}[{rid}.{path}]")
            continue
        t = I._fmt_value(key or "", v)
        if key == "long_median_min" and re.match(r"^\s*min", text[m.end():]):
            t = str(int(v))   # "{totals.long_median_min} minutes": the unit is typed after the slot
        if t is None:
            out.append(f"{v}[{rid}.{path}]")
            continue
        p = path
        if key == "change_vs_previous" and re.match(r"^(?:areas|top_areas)\[", path):
            p = path.rsplit(".", 1)[0] + ".change_pts"
        out.append(f"{t}[{rid}.{p}]")
    out.append(text[last:])
    return "".join(out)


def window_lead(env):
    w = (env["meta"].get("window_said") or "").strip().rstrip(",")
    return (w[:1].upper() + w[1:] + ", here is what I counted.") if w else "Here is what I counted."


def insight_kept(x, s, t, good=None, bad=None):
    """eval_insight.v5_scores's own reading of one sentence (its `kept`), on the raw sheet."""
    as_answer, as_sent, gated = x.get("as") == "answer", x.get("as") in ("sent", "gated"), x.get("as") == "gated"
    if as_sent:
        f = I.check({"answer": "-", "observations": [{"text": t, "uses": []}]}, s, strict=True)
        out_ = I.scoped(f["observations"][0], s) if f["observations"] else None
        if out_ is not None and gated:
            out_, _w = I.gate_sentence(out_, s, I._gate_names(I.shown(s)), {"opened_said": True})
        if out_ is None:
            return False, None
        if bad and re.search(bad, out_):
            return True, out_
        return (not bad and (not good or good in out_)), out_
    if as_answer:
        a = I.check({"answer": t, "observations": []}, s, strict=True)["answer"]
        return bool(a), a
    o = I.check({"answer": "-", "observations": [{"text": t, "uses": []}]}, s, strict=True)["observations"]
    return bool(o), (o[0] if o else None)


def rows():
    """One row per v5 sentence: its case, class, slotted and marked forms, insight's verdict, the verifier's."""
    d, cases, extra = load()
    out = []
    for n, x in enumerate((d.get("v5") or {}).get("cases") or []):
        s = extra[x["case"]] if x["case"] in extra else cases[x["case"]]["sheet"]
        env = envelope("r1", tool_of(s), s)
        sheet = env["sheet"]
        items = [(t, True) for t in x["true"]] + [(p, False) for p in x["plants"]]
        for t, is_true in items:
            text = t["text"] if isinstance(t, dict) else t
            good = t.get("good") if isinstance(t, dict) else None
            bad = t.get("bad") if isinstance(t, dict) else None
            marked = to_markers(text, sheet)
            ins_kept, ins_out = insight_kept(x, s, text, good=good, bad=None if is_true else bad)
            if not is_true:
                ins_caught = not ins_kept
            fill = V._plain_fill(text, V._strip_added(sheet))
            if is_true:
                cls = "true_as_typed" if (not good or (fill and good in fill)) else "true_rewritten"
            else:
                cls = "planted"
            row = {"block": n, "case": x["case"], "as": x.get("as"), "class": cls, "why": None if is_true else
                   t.get("why"), "slotted": text, "marked": marked, "good": good, "bad": bad,
                   "insight": "kept" if (is_true and ins_kept) else ("caught" if (not is_true and ins_caught)
                                                                     else ("dropped" if is_true else "missed"))}
            if marked is None:  # (never in this set)
                row.update(verify="unconvertible", reasons=[])
                out.append(row)
                continue
            lead = window_lead(env)
            if x.get("as") == "answer":
                # the sentence is the lead (insight read it as the answer); the lead's window rule is the brain's own
                # (4.3 step 2), counted apart: window_lead() is not prepended, since a lower-case first word would
                # make the two one sentence
                form = {"lead": marked, "points": []}
                where = "lead"
            else:
                form = {"lead": lead, "points": [marked]}
                where = "point"
            v = V.check_answer(form, [env], V.Turn())
            o = [o for o in v.outcomes if o.where == where][-1]
            reasons = list(o.reasons)
            window_only = where == "lead" and reasons == ["window_missing"]
            if where == "lead" and "window_missing" in reasons:
                reasons.remove("window_missing")
            lead0 = next(o for o in v.outcomes if o.where == "lead")
            # insight's step alone on the same sentence (run even when a marker step failed): does insight's own
            # check catch the plant, one sentence at a time?
            probe = V.check_sentence(marked, V.Ledger([env]), V.Turn(), where, 0, probe=True)
            row["insight_step"] = probe.insight
            row.update(verify="dropped" if reasons else "kept", reasons=reasons, layer=o.layer if reasons else None,
                       details=list(o.details), lead_window_missing=window_only,
                       lead_ok=lead0.kept if where == "point" else None)
            if is_true and ins_out:
                # what today's sent path makes of it (layout: scoped, then the gate), against the plain fill
                prod = ins_out
                if x.get("as") not in ("sent", "gated"):
                    prod = I.scoped(prod, s)
                    prod, _w = I.gate_sentence(prod, s, I._gate_names(I.shown(s)), {"opened_said": True})
                # (insight's house style, `tidy` and `_unit_before`, is wording, not truth: applied to both sides)
                fill_t = I._unit_before(I.tidy(fill or ""), s)
                ins, only = V._inserted(V._norm_cmp(fill_t), V._norm_cmp(prod or ""))
                bw_ = " ".join(re.findall(r"[\w%'’]+", str(I._base_of(V._strip_added(sheet)) or "@@").lower()))
                row["insight_added"] = [w for w in ins if w not in ("against " + bw_, "in " + bw_)]
                if row["insight_added"]:
                    row["class"] = "true_rewritten"
            out.append(row)
    return out


def summary(rs):
    s = {"sentences": len(rs)}
    for cls in ("true_as_typed", "true_rewritten", "planted"):
        xs = [r for r in rs if r["class"] == cls]
        s[cls] = {"n": len(xs), "kept": sum(r["verify"] == "kept" for r in xs),
                  "dropped": sum(r["verify"] == "dropped" for r in xs),
                  "unconvertible": sum(r["verify"] == "unconvertible" for r in xs),
                  "insight_agrees": sum((r["verify"] == "kept") == (r["insight"] == "kept") for r in xs
                                        if r["verify"] != "unconvertible")}
    layers = {}
    for r in rs:
        if r["verify"] == "dropped":
            k = (r["class"], r.get("layer"))
            layers[f"{k[0]}:{k[1]}"] = layers.get(f"{k[0]}:{k[1]}", 0) + 1
    s["drop_layer"] = layers
    s["lead_failed"] = sum(1 for r in rs if r.get("lead_ok") is False)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--show", default="", help="print the rows of one class (true_as_typed, true_rewritten, planted)")
    a = ap.parse_args(argv)
    rs = rows()
    print(json.dumps(summary(rs), indent=1))
    print("insight's own eval:", json.dumps({k: v for k, v in E.v5_scores().items() if k != "by_why"}))
    if a.show:
        for r in rs:
            if r["class"] == a.show:
                print(f"- [{r['verify']}] {r['reasons']} ({r.get('layer')}) [{r['insight']}] {r['why'] or ''}\n"
                      f"    {r['marked']}\n    {r.get('details')}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(rs, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
