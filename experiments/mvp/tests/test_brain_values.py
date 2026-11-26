"""mvp26 (DESIGN.md section 26): the checker's third mode, "values".

A check refuses a sentence only on values, with no reading of words: a marker whose cell does not hold the value
written beside it, a marker whose path does not exist, a calc whose arithmetic does not give the written value, and a
number, date, clock time or name written with no marker that no result of the turn holds (nor the message). The
privacy and safety refusals keep their power. Every code of today's full and cells checks is a flag that refuses
nothing. Full and cells mode are unchanged (pinned by digest). Made-up library and frozen ledgers only; no model call.
"""
import hashlib
import json
import os
import sys
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.brain import answer as A  # noqa: E402
from mvp.brain import fallback as FB  # noqa: E402
from mvp.brain import planted as P  # noqa: E402
from mvp.brain import verify as V  # noqa: E402
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys, person  # noqa: E402,F401  (fixtures)
from mvp.tests.test_brain_slice import (  # noqa: E402,F401  (fixture and helpers)
    FALSE_LEAD, TRUE_LEAD, TRUE_POINT, bd, ga, harness, no_marker, run)


def _h(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


# ================================================================ the pin
# Changing any of these is a decision (DESIGN 26.2): the refuse list, the safety codes kept, the number-word variant,
# the keys whose strings never hold a figure, a date or a time.
REFUSE = ["bad_ref", "calc", "empty", "garbled", "language", "link", "not_item", "outcome", "psych", "row_name",
          "sensitive", "unfound_date", "unfound_name", "unfound_number", "unfound_time", "watch_time", "wrong_measure",
          "wrong_name", "wrong_value"]
# (mvp27, DESIGN 29.1: "row_name" added, a title or name before a row marker that the row does not hold)
PIN_REFUSE = "6faec7f8052e3f86c27dd9321f823df1cacccb06a0dd75b1aeaf5962d5b9b7f4"
SAFETY = ["sensitive", "psych", "outcome", "language", "link", "watch_time"]
THIRD_PARTY = ["caption", "channel", "description", "handle", "name", "snippet", "text", "title", "why_matched"]


def test_the_refuse_list_is_pinned_and_hashed():
    assert sorted(V.VALUES_REFUSE) == REFUSE
    assert _h(sorted(V.VALUES_REFUSE)) == _h(REFUSE)
    assert _h(V.VALUES_REFUSE) == PIN_REFUSE, _h(V.VALUES_REFUSE)
    assert list(V.VALUES_SAFETY) == SAFETY and set(SAFETY) <= set(V.VALUES_REFUSE)
    assert sorted(V._V_THIRD_PARTY) == THIRD_PARTY
    assert V.VALUES_NUMBER_WORDS == "refuse" and V.VALUES.rule("nw_refuse")
    # the values codes are their own; the cells pin (test_brain_cells) is not moved by them
    assert not (V.VALUES_CODES - set(V.VALUES_REFUSE))
    assert "percent" in V.CELL_CODES   # mvp26: insight's percent, classed


# ================================================================ choosing the mode
def test_the_mode_comes_from_the_argument_or_the_environment(monkeypatch):
    monkeypatch.delenv(V.CHECK_ENV, raising=False)
    assert "values" in V.CHECK_MODES and V.check_mode("values") is V.VALUES and V.check_mode(" Values ") is V.VALUES
    assert V.check_mode() is V.FULL
    monkeypatch.setenv(V.CHECK_ENV, "values")
    assert V.check_mode() is V.VALUES and V.check_mode("cells") is V.CELLS
    # a code lead under values mode carries no model point, as in cells mode
    assert V.VALUES.cells and V.VALUES.rule("values") and not V.CELLS.rule("values") and not V.FULL.rule("values")
    assert V.values_mode("flag").rule("values") and not V.values_mode("flag").rule("nw_refuse")


# ================================================================ the frozen second attack's ledgers
A2 = json.load(open(os.path.join(MVP, "eval", "brain_cells_attack2.json"), encoding="utf-8"))


def _turn(rec):
    t = A2["turns"][rec]
    return V.Turn(message=t["message"], unlock=t["unlock"], screen=t["screen"],
                  today=date.fromisoformat(t["today"]) if t["today"] else None, names=list(t["names"]),
                  sensitive_names=list(t["sensitive_names"]))


def _point(text, rec="A01.3", mode="values"):
    v = V.check_answer({"lead": A2["carriers"][rec], "points": [text]}, A2["ledgers"][rec], _turn(rec), mode=mode)
    assert v.lead_ok, v.lead[0].reasons
    return next(o for o in v.outcomes if o.where == "point")


MADE_UP = [   # (sentence on A01.3: October 2026, channels Clip Factory 61, Pan Theory 32, Pixel Pencil 29; code)
    ("Clip Factory[r1.channels[0]] made 62[r1.channels[0].items] videos.", "wrong_value"),
    ("Clip Factory[r1.channels[0]] made 44%[r1.channels[0].share] of what you opened.", "wrong_value"),
    ("Clip Factory[r1.channels[0]] made 61%[r1.channels[0].items] of what you opened.", "wrong_measure"),
    ("Clip Factory[r1.channels[0]] made 61[r1.channels[9].items] videos.", "bad_ref"),
    ("Clip Factory[r1.channels[0]] had 30 more[=diff(r1.channels[0].items, r1.channels[1].items)] videos than Pan "
     "Theory[r1.channels[1]].", "calc"),
    ("Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos and 777 Shorts.", "unfound_number"),
    ("Bananarama Studio made 61[r1.channels[0].items] of your videos.", "unfound_name"),
    ("Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos, the first on 3 March 2019.", "unfound_date"),
    ("Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos, three times Pan Theory[r1.channels[1]].",
     "unfound_number"),
    ("Clip Factory[r1.channels[0]] made half[r1.channels[0].share] of what you opened.", "wrong_value"),
    ("Anime clips[r1.themes[0]] came to 61[r1.channels[0].items] videos.", "unfound_name"),
]
TRUE_TWINS = [
    "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.",
    "Clip Factory[r1.channels[0]] made 43%[r1.channels[0].share] of what you opened.",
    "Clip Factory[r1.channels[0]] had 29 more[=diff(r1.channels[0].items, r1.channels[1].items)] videos than Pan "
    "Theory[r1.channels[1]].",
    "Clip Factory[r1.channels[0]] made 61 videos in October 2026.",
    "Pan Theory came next with 32[r1.channels[1].items] videos.",
]


@pytest.mark.parametrize("text,code", MADE_UP)
def test_a_made_up_value_is_refused(text, code):
    o = _point(text)
    assert not o.kept and code in o.reasons, (o.reasons, o.details)
    assert set(o.reasons) <= set(V.VALUES_REFUSE)


@pytest.mark.parametrize("text", TRUE_TWINS)
def test_its_true_twin_is_kept(text):
    o = _point(text)
    assert o.kept, (o.reasons, o.details)


def test_the_number_word_variant_decides_unmarked_ratio_and_fraction_words():
    ratio = "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos, three times Pan Theory[r1.channels[1]]."
    half = "Clip Factory[r1.channels[0]] made half[r1.channels[0].share] of what you opened."
    for text in (ratio, half):
        assert not _point(text).kept
        assert _point(text, mode=V.values_mode("flag")).kept


def test_a_real_value_misattached_still_gets_out_by_design():
    # 32 is Pan Theory's count, real, said of Pixel Pencil; a rank over the wrong row: framing and binding by words
    o = _point("Pixel Pencil came next with 32[r1.channels[1].items] videos.")
    assert o.kept and {f["code"] for f in o.flags if f["mode"] == "cells"}   # cells refuses it; values flags it


def test_flags_never_refuse_and_carry_todays_codes():
    n = flagged = 0
    for c in A2["cases"]:
        rec = c["record"]
        for form in ({"lead": A2["carriers"][rec], "points": [c["text"]]}, {"lead": c["text"], "points": []}):
            v = V.check_answer(form, A2["ledgers"][rec], _turn(rec), mode="values")
            vc = V.check_answer(form, A2["ledgers"][rec], _turn(rec), mode="cells")
            vf = V.check_answer(form, A2["ledgers"][rec], _turn(rec), mode="full")
            for o in v.outcomes:
                n += 1
                assert set(o.reasons) <= set(V.VALUES_REFUSE)
                assert o.kept == (not o.reasons)
                for name, other in (("cells", vc), ("full", vf)):
                    x = next(x for x in other.outcomes if (x.where, x.index) == (o.where, o.index))
                    assert [f["code"] for f in o.flags if f["mode"] == name] == x.reasons
                flagged += bool(o.flags)
            assert v.repair == ((not v.lead_ok) or 2 * sum(not o.kept for o in v.outcomes) > len(v.outcomes))
    assert n and flagged


def test_a_title_number_is_never_found():
    data = P.load()
    case = next(c for c in data["cases"] if c["id"] == "f_forged_title2")
    kept, reasons, _v = P.outcome(case, data["ledgers"], "values")
    assert not kept and "unfound_number" in reasons


# ================================================================ privacy and safety keep their power
@pytest.mark.parametrize("cid,code", [("f_psych", "psych"), ("f_outcome", "outcome"), ("f_sensitive", "sensitive"),
                                      ("f_second_topic", "sensitive"), ("attack_T01", "psych"),
                                      ("attack_T02", "psych"), ("attack_T03", "psych"), ("audit_F64", "language"),
                                      ("audit_F43", "sensitive"), ("o_you", "second_person")])
def test_the_safety_refusals_hold(cid, code):
    data = P.load()
    case = next(c for c in data["cases"] if c["id"] == cid)
    kept, reasons, _v = P.outcome(case, data["ledgers"], "values")
    assert not kept and code in reasons, reasons


def test_the_planted_values_line():
    s = P.score_values()
    assert s["ok"] and s["true_kept"] == s["true"] == 78 and not s["safety_out"]
    assert s["by_source"]["audit_true"]["true_kept"] == 60 and s["by_source"]["attack_true"]["true_kept"] == 60


# ================================================================ full and cells unchanged (digests of every verdict)
def _vdump(v):
    out = {k: getattr(v, k) for k in ("items", "outside", "chart", "form_error", "private_line", "repair", "version",
                                      "check")}
    out["outcomes"] = [{k: getattr(o, k) for k in ("where", "index", "text", "sent", "reasons", "details", "cells",
                                                   "rid", "hidden_rank", "layer", "insight", "notes")}
                       for o in v.outcomes]
    assert all(not o.flags for o in v.outcomes)
    return out


def _digest(mode):
    data = P.load()
    h = hashlib.sha256()
    for c in data["cases"]:
        led = V.Ledger(data["ledgers"][c["ledger"]])
        t = c.get("turn") or {}
        turn = V.Turn(message=t.get("message", ""), unlock=t.get("unlock"),
                      today=date.fromisoformat(t["today"]) if t.get("today") else None,
                      names=list(t.get("names") or []), sensitive_names=list(t.get("sensitive_names") or []))
        for f in (c.get("forms") or [c["form"]]):
            h.update(repr(_vdump(V.check_answer(f, led, turn, mode=mode))).encode())
    for c in A2["cases"]:
        rec = c["record"]
        for form in ({"lead": A2["carriers"][rec], "points": [c["text"]]}, {"lead": c["text"], "points": []}):
            h.update(repr(_vdump(V.check_answer(form, A2["ledgers"][rec], _turn(rec), mode=mode))).encode())
    return h.hexdigest()


# computed on this tree after the scratchpad differential (mvp26/values/diff26.py) showed 0 of 9910 verdicts differ
# from the tip's verify.py (d7ba2ef) in full and cells mode
# from the tip's verify.py (d7ba2ef) as well; the same digests
DIGEST = {"full": "b88106bd224e571edc5baac9dfea2e7443a83b9fff33e252aa28976fd76e7cf1",
          "cells": "f641b49754d32778fdc2ec99cd66e463434a6124ee7b172704471be2ab69f7d6"}


@pytest.mark.parametrize("mode", ["full", "cells"])
def test_full_and_cells_are_unchanged(mode, monkeypatch):
    monkeypatch.delenv(V.CHECK_ENV, raising=False)
    assert _digest(mode) == DIGEST[mode]


# ================================================================ the loop, the code lead, the eval record
def test_the_turn_writes_the_mode_and_the_flags(harness):
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]], check="values")
    assert rec["check"] == "values" and rec["lead_source"] == "model"
    assert isinstance(rec["flags"], list) and all({"form", "where", "index", "code", "mode"} <= set(f)
                                                  for f in rec["flags"])
    assert all("flags" in o for o in rec["verdicts"][0]["outcomes"])
    rec2, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]], check="cells")
    assert "flags" not in rec2 and all("flags" not in o for o in rec2["verdicts"][0]["outcomes"])


def test_a_refused_lead_is_reworded_once_then_the_code_lead_goes_out_with_no_model_point(harness):
    rec, _p, t = run(harness, [[bd()], [ga(FALSE_LEAD, [TRUE_POINT])], [ga(FALSE_LEAD, [TRUE_POINT])]],
                     check="values")
    assert rec["check"] == "values" and rec["lead_source"] == "code" and rec["repair_message"]
    assert rec["answer"]["points"] == [] and no_marker(rec["answer"]["text"])
    led, vt = V.Ledger(t.results), V.Turn.of(t)
    v1 = V.check_answer({"lead": FALSE_LEAD, "points": [TRUE_POINT]}, led, vt, mode="values")
    assert not v1.lead_ok and v1.repair and [o.kept for o in v1.outcomes if o.where == "point"] == [True]
    assert FB.answer(led, v1, vt, mode="values")["points"] == []
    code = dict(FB.code_lead(led, v1, vt), points=["Pan Theory came next with 32 videos."])
    assert A.build(led, code=code, mode="values")["points"] == []


def test_a_refused_point_alone_is_dropped_and_asks_for_no_reword(harness):
    bad_point = "Pan Theory[r1.channels[1]] came next with 33[r1.channels[1].items] videos."
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT, bad_point])]], check="values")
    assert rec["lead_source"] == "model" and not rec["repair_message"]
    assert rec["answer"]["points"] == ["Pan Theory came next with 32 videos."]


def test_the_eval_summary_counts_the_flags(harness):
    from mvp import eval_brain as E
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]], check="values")
    rec.update(id="X", n=0, key="X.0", g2={"verdict": "understood"}, audit={"findings": [], "checked": 0},
               reading_errors=[], reading_window_failed=[], dropped=E.dropped_of(rec))
    rec["flags"] = rec["flags"] or [{"form": 0, "where": "lead", "index": 0, "code": "tie", "mode": "full"}]
    s = E.summarize([rec], {"check": "values"})
    assert s["check"] == "values" and s["flag_codes"]
    rec2, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]], check="cells")
    rec2.update(id="X", n=1, key="X.1", g2={"verdict": "understood"}, audit={"findings": [], "checked": 0},
                reading_errors=[], reading_window_failed=[], dropped=E.dropped_of(rec2))
    assert "flag_codes" not in E.summarize([rec2], {"check": "cells"})
