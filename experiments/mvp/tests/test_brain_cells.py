"""mvp24 (DESIGN.md section 24): the pinned cells-only checker mode of brain/verify.py.

"cells" checks the cells only (numbers, names, dates, calculations, what each number is bound to), the policy lines
and the marker grammar; every framing rule is off at the source. "full" (the default) is today's checker. The mode is
chosen by an argument or by MVP_BRAIN_CHECK. Made-up library and planted ledgers only; no model call.
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
    return hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest()


# ================================================================ the pin
# The codes OFF in cells mode, the codes ON, the loosenings, the framing-listed rule kept on, the doubtful codes'
# decisions and the frozen class of every planted false case. Changing any of them is a decision: DESIGN 24.2.
# mvp25 (DESIGN 24.4): re-hashed after short_word and platform_all went out, the cells rules (CELLS_RULES) and the
# loosenings of the true sentences went in, limits was split by emitter, and three cell codes were added
PIN_OFF = "f0f4c667b93d46d3f9c5b4e9ecbce76bce8ff27b8bbbfe92d44216be6a013247"
PIN_ON = "b2ad95ff2e68c5ee9b5338ce31d37233213d4456092f70d07be69c03a574dca4"   # mvp26: re-hashed when insight's "percent" was classed as a cell code (DESIGN 26)
PIN_LOOSE = "392cd40c5853a13662fe4543b2763535f2f8f23002b299851158871ca43a95b3"
PIN_KEPT = "22d78bacbfac1875b7de193d0ecf3a841a596fc0569e58bf01d1268aafc6d97b"
PIN_DOUBT = "e54e1711163ba4ce40c59fb36d884885ff9bb127963f77bdcb16340f335b8c1f"
PIN_RULES = "80a1156ae8277c17562fc0b875d741c7b28ee3421b21ac128aed001a7eddfe82"
PIN_WALK = "70d347a7301e345eafd828956a9e29ed84eb2f0a5b772c9f7ae845ec0f55a884"
PIN_CLASSES = "34bdceae77eb6ae451e1a640c9ae1d9ba46f0278b82a918e16ec30e9441760b1"
ON_CODES = [
    "about_not_cited", "bad_marker", "bad_path", "bad_ref", "bad_value", "bound", "bound_to_other", "calc",
    "channel_not_in_theme", "count_as_share", "count_of_videos", "date", "direction@calc", "direction@from_to",
    "direction@insight", "direction@sign", "empty", "filler", "fraction", "free_number", "garbled", "generic_claim",
    "insight_error", "item_field", "language", "length_cell", "link", "made_up_difference", "marker",
    "median_of_window", "month", "name", "not_item", "number", "number_word", "other_name", "other_period", "outcome",
    "outside_in_history", "percent", "point_text", "psych", "quote", "ratio", "second_person", "sensitive", "share_of_name",
    "shorts_as_long", "source", "too_long", "too_many", "two_results", "typed_name", "uncited_claim@nomarker",
    "uncited_name", "uncited_number", "unknown_name", "unnamed_owner", "watch_time", "weak_fit", "weekday", "word",
    "wrong_area", "wrong_group", "wrong_measure", "wrong_name", "wrong_value"]
CELLS_RULES = ["date_owner", "free_date", "insight_walk", "item_fields", "length_cell", "pairs_crossed",
               "period_bind", "period_named", "weekday_typed"]
CELLS_LOOSE = {"title_quote", "item_channel", "own_fields", "hour_word", "handle", "month_alone", "label_in_date",
               "quoted_title"}


def _known():
    return V.CELL_CODES | V.POLICY_CODES | V.FRAMING_CODES | set(V.DOUBT_CODES)


def test_the_codes_on_and_off_in_cells_mode_are_pinned():
    on = sorted(c for c in _known() if not V.CELLS.is_off(c))
    assert on == ON_CODES
    assert _h(on) == PIN_ON
    assert _h(sorted(V.CELLS.off)) == PIN_OFF
    assert _h(sorted(V.CELLS.loose)) == PIN_LOOSE
    assert _h(sorted(V.FRAMING_KEPT)) == PIN_KEPT
    assert _h(V.DOUBT_CODES) == PIN_DOUBT
    assert sorted(V.CELLS_RULES) == CELLS_RULES and _h(sorted(V.CELLS_RULES)) == PIN_RULES
    assert _h(sorted(V.WALK_ACCEPT)) == PIN_WALK
    assert not V.FULL.rules and V.CELLS.rules == V.CELLS_RULES
    with open(os.path.join(MVP, "eval", "brain_cells_classes.json"), "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == PIN_CLASSES


def test_the_code_lists_are_disjoint_and_every_framing_code_but_the_kept_one_is_off():
    assert not (V.CELL_CODES & V.POLICY_CODES) and not (V.CELL_CODES & V.FRAMING_CODES)
    assert not (V.POLICY_CODES & V.FRAMING_CODES)
    for c in V.FRAMING_CODES - set(V.FRAMING_KEPT):
        assert V.CELLS.is_off(c), c
    for c in V.CELL_CODES | V.POLICY_CODES:
        assert not V.CELLS.is_off(c), c
    assert set(V.FRAMING_KEPT) == {"weekday"} and V.CELLS.loose == CELLS_LOOSE
    assert not ({"short_word", "platform_all"} & V.CELLS.loose)   # mvp25: out (DESIGN 24.4)
    assert all(V.CELLS.is_off("limits", e) for e in ("words", "self", "insight"))
    assert not V.FULL.off and not V.FULL.loose and not V.FULL.cells


# ================================================================ choosing the mode
def test_the_mode_comes_from_the_argument_then_the_environment_then_full(monkeypatch):
    monkeypatch.delenv(V.CHECK_ENV, raising=False)
    assert V.check_mode() is V.FULL and V.check_mode("cells") is V.CELLS and V.check_mode(" Full ") is V.FULL
    monkeypatch.setenv(V.CHECK_ENV, "cells")
    assert V.check_mode() is V.CELLS and V.check_mode("full") is V.FULL
    monkeypatch.setenv(V.CHECK_ENV, "loose")
    with pytest.raises(ValueError):
        V.check_mode()
    with pytest.raises(ValueError):
        V.check_mode("framing")


# ================================================================ the planted lines
def _cases():
    return {c["id"]: c for c in P.load()["cases"]}


def _turn(c):
    t = c.get("turn") or {}
    return V.Turn(message=t.get("message", ""), unlock=t.get("unlock"),
                  today=date.fromisoformat(t["today"]) if t.get("today") else None, names=list(t.get("names") or []),
                  sensitive_names=list(t.get("sensitive_names") or []))


def test_full_mode_keeps_todays_planted_line(monkeypatch):
    monkeypatch.delenv(V.CHECK_ENV, raising=False)
    s = P.score()
    assert (s["false"], s["false_dropped"], s["false_dropped_expected"], s["true"], s["true_kept"]) == \
        (332, 332, 332, 78, 78)
    b = s["by_source"]
    assert (b["attack"]["false"], b["attack"]["false_dropped"]) == (169, 169)
    assert b["attack_true"]["true_kept"] == 41 and b["audit_true"]["true_kept"] == 49


def test_the_cells_planted_line_counts_the_known_leaks_and_says_it_is_in_sample():
    s = P.score_cells(mode="cells")
    assert s["ok"] and s["cell_out"] == [] and (s["true"], s["true_kept"]) == (78, 78)
    got = {src: {k: (x["false"], x["handled"], x["kept_under_private_line"], x["out"])
                 for k, x in b.items() if isinstance(x, dict)} for src, b in s["by_source"].items()}
    # mvp25: the cells rules also drop framing-class cases they bind (a period name on another window's cell, ...)
    assert got["new"] == {"cell": (42, 42, 0, 0), "policy": (14, 12, 0, 2), "framing": (36, 16, 0, 20)}
    assert got["audit"] == {"cell": (54, 54, 0, 0), "policy": (14, 13, 0, 1), "framing": (69, 19, 2, 50)}
    assert got["insight_v5"] == {"cell": (19, 19, 0, 0), "policy": (1, 1, 0, 0), "framing": (83, 23, 0, 60)}
    # the attack counted by case (a case placed both as a lead and as a point is one case)
    assert got["attack"] == {"cell": (30, 30, 0, 0), "policy": (11, 11, 0, 0), "framing": (125, 33, 8, 92)}
    assert s["by_source"]["attack_true"]["true_kept"] == 54 and s["by_source"]["audit_true"]["true_kept"] == 58
    # the second attack: the count of known leaks is printed, and the line never reads as "every case handled"
    a2 = s["attack2"]
    assert s["known_leaks"] == len(KNOWN_LEAKS["cells"]) and a2["known_leaks"] == KNOWN_LEAKS["cells"]
    assert a2["new_leaks"] == [] and a2["in_sample"] and (a2["false"], a2["true"]) == (131, 46)
    assert f"{len(KNOWN_LEAKS['cells'])} known leaks" in s["summary"] and "in sample" in s["summary"]
    assert "every cell-class case handled" not in s["summary"]


def test_the_planted_command_takes_the_mode_and_fails_on_a_cell_class_case(monkeypatch, capsys):
    assert P.main(["--check", "cells"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["check"] == "cells" and out["ok"] and "known leaks" in out["summary"]
    real = P.classes()
    monkeypatch.setattr(P, "classes", lambda path=None: dict(real, attack_A01={"class": "cell"}))
    assert P.main(["--check", "cells"]) == 1   # attack_A01 (a framing case cells mode lets out) read as cell
    assert json.loads(capsys.readouterr().out)["cell_out"] == ["attack_A01"]


def test_no_code_that_is_off_reaches_a_cells_mode_outcome():
    data = P.load()
    seen = set()
    for c in data["cases"]:
        for f in c.get("forms") or [c["form"]]:
            v = V.check_answer(f, V.Ledger(data["ledgers"][c["ledger"]]), _turn(c), mode="cells")
            for o in v.outcomes:
                seen |= set(o.reasons)
                assert not any(V.CELLS.is_off(r) for r in o.reasons), (c["id"], o.reasons)
            for it in v.items:
                assert not any(V.CELLS.is_off(r) for r in it["reasons"]), (c["id"], it["reasons"])
    unknown = {r.split(":")[0] for r in seen} - {k.split("@")[0] for k in _known()}
    assert not unknown, unknown


def test_every_code_full_mode_gives_on_the_planted_set_has_a_class():
    data = P.load()
    seen = set()
    for c in data["cases"]:
        for f in c.get("forms") or [c["form"]]:
            v = V.check_answer(f, V.Ledger(data["ledgers"][c["ledger"]]), _turn(c), mode="full")
            seen |= {r.split(":")[0] for o in v.outcomes for r in o.reasons}
    assert not seen - {k.split("@")[0] for k in _known()}, seen - {k.split("@")[0] for k in _known()}


# ================================================================ what cells mode does, sentence by sentence
def _point(cid, sentence, mode):
    c = _cases()[cid]
    f0 = (c.get("forms") or [c["form"]])[0]
    data = P.load()
    v = V.check_answer({"lead": f0.get("lead") or "", "points": [sentence]}, V.Ledger(data["ledgers"][c["ledger"]]),
                       _turn(c), mode=mode)
    o = [o for o in v.outcomes if o.where == "point"][0]
    return o.kept, o.reasons


def test_c1_a_change_of_one_row_now_against_another_row_before_is_a_cell_fault():
    # the attack's V05, the one cell-class sentence the record table showed getting out of cells only ("C1")
    bad = ("Gaming[r1.areas[0]] rose 29 points[=points(r1.areas[0].share, r1.areas[2].previous_share)] on last "
           "autumn, more than food and cooking[r1.areas[2]].")
    assert _point("attack_V05", bad, "cells") == (False, ["calc"])
    assert not _point("attack_V05", bad, "full")[0]
    twin = "Gaming[r1.areas[0]] rose 42 points[=points(r1.areas[0].share, r1.areas[0].previous_share)] on last autumn."
    assert _point("attack_V05", twin, "cells") == (True, [])


def test_a_row_said_now_in_one_measure_and_before_in_another_is_refused():
    bad = ("Speed runs[r1.themes[1]] climbed to 9%[r1.themes[1].share] from 27[r1.themes[1].previous_items] videos "
           "before.")
    assert _point("v5_112", bad, "cells") == (False, ["wrong_measure"])
    twin = "Speed runs[r1.themes[1]] climbed to 9%[r1.themes[1].share] from 3%[r1.themes[1].previous_share]."
    assert _point("v5_112", twin, "cells") == (True, [])
    # the window's own totals and previous cells may be said apart
    apart = "You opened 1000[r1.totals.items] videos; Shorts were 68%[r1.previous.shorts_share] of them before."
    assert _point("v5_112", apart, "cells")[0]


def test_the_windows_median_said_of_a_row_is_refused_whatever_insight_says_first():
    bad = ("Speed runs[r1.themes[1]] led on 18[r1.themes[1].days] days, and its long videos ran about "
           "23[r1.totals.long_median_min] minutes.")
    assert _point("v5_054", bad, "cells") == (False, ["median_of_window"])
    assert _point("v5_054", "Your long videos ran about 23[r1.totals.long_median_min] minutes.", "cells") == (True, [])


def test_now_in_the_from_slot_a_typed_sign_and_a_wrong_weekday_of_a_date_stay_refused():
    swapped = ("Clip Factory[r1.channels[0]] went from 13[r1.channels[0].items] videos the week before to "
               "14[r1.channels[0].previous_items] in the last 7 days.")
    assert _point("attack_X02", swapped, "cells") == (False, ["direction"])
    right = ("Clip Factory[r1.channels[0]] went from 14[r1.channels[0].previous_items] videos the week before to "
             "13[r1.channels[0].items] in the last 7 days.")
    assert _point("attack_X02", right, "cells") == (True, [])
    assert not _point("f_sign", _cases()["f_sign"]["form"]["points"][0], "cells")[0]
    sunday = ("Your first Clip Factory video was Funniest gaming fail[r1.items[0]], on 1 October 2026[r1.items[0].when], "
              "a Sunday.")
    assert _point("attack_Q01", sunday, "cells") == (False, ["weekday"])


def test_a_framing_fault_goes_out_in_cells_mode_and_not_in_full():
    s = "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of your long videos."
    assert _point("attack_A01", s, "full") == (False, ["length_word"])
    assert _point("attack_A01", s, "cells") == (True, [])


def test_a_title_in_quotes_stands_before_an_items_marker_and_a_short_no_longer_does():
    quoted = 'Your first Clip Factory video was "Funniest gaming fail"[r1.items[0]].'
    assert not _point("attack_Q01", quoted, "full")[0] and _point("attack_Q01", quoted, "cells") == (True, [])
    # mvp25: short_word is out of cells mode (it let a short go out under another channel's name: attack2 e12, l07)
    short = "You opened a short[r1.items[0]] on 1 October 2026[r1.items[0].when]."
    assert not _point("attack_Q01", short, "full")[0] and not _point("attack_Q01", short, "cells")[0]


# compound probes: a binding fault with a framing word added. Insight stops at its first reason, so a framing reason
# that is off could hide its binding reason; p16 and p19 were the two holes that showed (DESIGN 24.3). mvp25: the
# cells rule insight_walk walks past the reason that is off, and both are closed (hole False)
PROBES = [
    ("f_under_other_name", "Pan Theory[r1.channels[1]] led with 56[r1.channels[0].items] videos.", False),
    ("f_under_other_name", "Mostly Pan Theory[r1.channels[1]], with 56[r1.channels[0].items] videos.", False),
    ("audit_F03", "Gaming clips[r1.themes[0]] led, at 51%[r1.areas[0].share] of what you opened.", False),
    ("audit_F83c", "In 2022, your biggest year, you opened 134[r1.periods[0].items] videos.", False),
    ("audit_F84", "Lately, in October 2026, you opened 44[r1.periods[8].items] videos.", False),
    ("v5_016", "Prime Number Club[r1.channels[1]] came on 140[r1.channels[0].days] days, the most of any channel.",
     False),
    ("v5_054", "Lately Speed runs[r1.themes[1]] was your top theme; its long videos ran about "
               "23[r1.totals.long_median_min] minutes.", False),
    ("v5_056", "Meme drops[r1.themes[0]] led and leaned long-form at 69%[r1.themes[0].shorts_share].", False),
    ("attack_P03", "Pan Theory[r1.channels[1]] and Pixel Pencil[r1.channels[2]] together led, at "
                   "43%[r1.channels[0].share] of what you opened.", False),
    # the two former holes (p16, p19), closed by insight_walk: wrong_area and shorts_as_long reached past 'mostly'
    ("v5_051", "gaming[r1.areas[0]] led at 22%[r1.areas[0].share], mostly Meme drops[r1.themes[0]].", False),
    ("v5_056", "Meme drops[r1.themes[0]] was mostly long-form at 69%[r1.themes[0].shorts_share].", False),
]


@pytest.mark.parametrize("cid,sentence,hole", PROBES)
def test_compound_probes_of_a_binding_fault(cid, sentence, hole):
    assert not _point(cid, sentence, "full")[0]
    assert _point(cid, sentence, "cells")[0] is hole


# ================================================================ the skeptic's and the record checker's cases
def _extra():
    with open(os.path.join(MVP, "eval", "brain_cells_extra.json"), encoding="utf-8") as f:
        return json.load(f)


def _extra_kept(e, ledgers, mode):
    t = dict(e["turn"])
    t["today"] = date.fromisoformat(t["today"]) if t.get("today") else None
    v = V.check_answer(e["form"], ledgers[e["ledger"]], V.Turn(**t), mode=mode)
    os_ = [o for o in v.outcomes if o.where == "lead"] if e["where"] == "L" else \
        [o for o in v.outcomes if (o.where, o.index) == ("point", 0)]
    return bool(os_) and all(o.kept for o in os_)


def test_the_skeptics_and_the_record_checkers_cell_class_cases():
    d = _extra()
    for e in d["cases"]:
        assert _extra_kept(e, d["ledgers"], "full") is e["kept_full"], e["id"]
        assert _extra_kept(e, d["ledgers"], "cells") is e["kept_cells"], e["id"]
        if e["class"] == "cell" and e["id"] != "K37":
            assert not e["kept_cells"], e["id"]
    k37 = next(e for e in d["cases"] if e["id"] == "K37")
    # the one cell-class case of the four sets cells mode does not handle (arguable: a length scope), and full mode
    # does not handle it either: "Your Shorts ran 10[r1.totals.long_median_min] minutes at the median"
    assert k37["kept_cells"] and k37["kept_full"] and k37["arguable"] == "framing"
    cells = {e["id"] for e in d["cases"] if e["class"] == "cell"}
    assert cells == {"K03", "K30", "K37", "K39", "K45", "K46", "N24", "N25", "N33"}


# ================================================================ the answer: a code lead carries no model point
def _code_lead_case(harness):
    from mvp.brain import verify as V_
    rec, _p, t = run(harness, [[bd()], [ga(FALSE_LEAD, [TRUE_POINT])], [ga(FALSE_LEAD, [TRUE_POINT])]], check="cells")
    return rec, t, V_


def test_in_cells_mode_a_code_lead_goes_out_with_no_point_of_the_models(harness):
    rec, t, _v = _code_lead_case(harness)
    assert rec["check"] == "cells" and rec["lead_source"] == "code"
    want = FB.code_lead(t.results, turn=V.Turn.of(t))
    assert rec["answer"]["lead"] == want["lead"] and rec["answer"]["points"] == []
    assert rec["sentences"]["kept_sent"] == 0 and no_marker(rec["answer"]["text"])
    assert all(v["outcomes"] is not None for v in rec["verdicts"])
    # full mode, the same script: the point that passed rides on the code lead, as today
    rec2, _p, _t = run(harness, [[bd()], [ga(FALSE_LEAD, [TRUE_POINT])], [ga(FALSE_LEAD, [TRUE_POINT])]], check="full")
    assert rec2["check"] == "full" and rec2["answer"]["points"] == ["Pan Theory came next with 32 videos."]


def test_the_turn_reads_the_environment_once_and_writes_its_mode(harness, monkeypatch):
    monkeypatch.setenv(V.CHECK_ENV, "cells")
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]])
    assert rec["check"] == "cells" and rec["lead_source"] == "model"
    monkeypatch.delenv(V.CHECK_ENV)
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]])
    assert rec["check"] == "full"


def test_answer_build_and_fallback_answer_drop_the_models_points_in_cells_mode(harness):
    rec, t, _v = _code_lead_case(harness)
    led = V.Ledger(t.results)
    vt = V.Turn.of(t)
    v1 = V.check_answer({"lead": FALSE_LEAD, "points": [TRUE_POINT]}, led, vt, mode="cells")
    assert not v1.lead_ok and [o.kept for o in v1.outcomes if o.where == "point"] == [True]
    assert FB.answer(led, v1, vt, mode="cells")["points"] == []
    assert FB.answer(led, v1, vt, mode="full")["points"] == ["Pan Theory came next with 32 videos."]
    code = dict(FB.code_lead(led, v1, vt), points=["Pan Theory came next with 32 videos."])
    assert A.build(led, code=code, mode="cells")["points"] == []
    assert A.build(led, code=code, mode="full")["points"] == ["Pan Theory came next with 32 videos."]


def test_codes_own_template_lead_is_checked_with_every_rule(harness, monkeypatch):
    rec, t, _v = _code_lead_case(harness)
    seen = []
    real = V.check_answer

    def spy(form, ledger, turn=None, mode=None):
        seen.append(mode)
        return real(form, ledger, turn, mode=mode)
    monkeypatch.setattr(V, "check_answer", spy)
    monkeypatch.setattr(FB, "_from_code_form", lambda res: None)   # the template path (code_form has no check)
    lead = FB.code_lead(t.results, turn=V.Turn.of(t))
    assert lead["how"] == "template" and seen and set(seen) == {"full"}


# ================================================================ the eval: the mode in every record and summary
def test_the_eval_summary_says_the_mode(harness):
    from mvp import eval_brain as E
    recs = []
    for check in ("cells", "cells"):
        rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]], check=check)
        rec.update(id="X", n=len(recs), key=f"X.{len(recs)}", g2={"verdict": "understood"},
                   audit={"findings": [], "checked": 0}, reading_errors=[], reading_window_failed=[],
                   dropped=E.dropped_of(rec))
        recs.append(rec)
    assert E.summarize(recs, {"check": "cells"})["check"] == "cells"
    assert E.summarize(recs)["check"] == "cells"
    recs[1]["check"] = "full"
    assert E.summarize(recs)["check"] == ["cells", "full"]


# ================================================================ mvp25: the second attack (brain_cells_attack2.json)
# An independent attacker's 131 false and 46 true new sentences on 8 saved held-out results (mvp24 pincheck), frozen
# as they were. Each runs as a point under its record's true carrier lead and alone as a lead. A false case that gets
# out either way is a KNOWN LEAK, listed by id with its family. IN SAMPLE: the cells rules of DESIGN 24.4 were built on
# these cases (at the attacker's run, 4064f3e, 24 got out in cells mode: a19 f08 f16 f21 f22 c09 c10 e09 e12 e13 g05
# h01 h02 h03 m02 l07 w01 p02 p04 p05 p06 p07 n05 n09).
KNOWN_LEAKS = {"cells": {},
               "full": {"a19": "measure", "e09": "wrong_row", "e13": "measure", "w01": "date", "p02": "wrong_row"}}
TRUE_LOST = {"cells": {"a25", "k07", "e04", "l01", "l06", "q01", "q08"},
             "full": {"a01", "a07", "a15", "a22", "a25", "a29", "d01", "d05", "d08", "f01", "f07", "f10", "f13",
                      "k01", "k07", "k08", "c01", "c11", "b01", "b08", "e01", "e04", "e10", "e14", "g01", "g06",
                      "l01", "l06", "t03", "t04", "t05", "t06", "t07", "t09", "t10", "q01", "q05", "q08"}}
MVP24_CELLS_OUT = {"a19", "f08", "f16", "f21", "f22", "c09", "c10", "e09", "e12", "e13", "g05", "h01", "h02", "h03",
                   "m02", "l07", "w01", "p02", "p04", "p05", "p06", "p07", "n05", "n09"}


def _a2():
    return P.load_attack2()


def test_the_second_attack_is_frozen_whole_and_made_up():
    d = _a2()
    assert len(d["cases"]) == 177 and sum(c["truth"] == "F" for c in d["cases"]) == 131
    assert {c["id"] for c in d["cases"] if c["truth"] == "F" and
            (c["mvp24_cells"]["point_kept"] or c["mvp24_cells"]["lead_kept"])} == MVP24_CELLS_OUT
    assert d["known_leaks"] == KNOWN_LEAKS
    blob = json.dumps(d)
    assert "http" not in blob and "@example" not in blob and "/home/" not in blob


@pytest.mark.parametrize("mode", ["cells", "full"])
def test_every_second_attack_case_is_pinned_case_by_case(mode, monkeypatch):
    monkeypatch.delenv(V.CHECK_ENV, raising=False)
    d = _a2()
    for c in d["cases"]:
        p, lk = P.attack2_outcome(c, d, mode)
        if c["truth"] == "F":
            assert (p or lk) is (c["id"] in KNOWN_LEAKS[mode]), (mode, c["id"], c["family"], p, lk)
        else:
            assert (p and lk) is (c["id"] not in TRUE_LOST[mode]), (mode, c["id"], p, lk)


def test_the_carrier_leads_of_the_second_attack_stay_kept_in_cells_mode():
    d = _a2()
    for key, lead in d["carriers"].items():
        t = d["turns"][key]
        turn = V.Turn(message=t["message"], unlock=t["unlock"], screen=t["screen"],
                      today=date.fromisoformat(t["today"]), names=t["names"], sensitive_names=t["sensitive_names"])
        assert V.check_answer({"lead": lead, "points": []}, d["ledgers"][key], turn, mode="cells").lead_ok, key


def _a2_kept(rec, sentence, mode="cells"):
    d = _a2()
    case = {"record": rec, "text": sentence}
    return P.attack2_outcome(case, d, mode)


def _without(kind, name):
    cm = V.CELLS
    if kind == "rule":
        return V.CheckMode("cells-" + name, off=cm.off, loose=cm.loose, cells=True, rules=cm.rules - {name})
    return V.CheckMode("cells-" + name, off=cm.off, loose=cm.loose - {name}, cells=True, rules=cm.rules)


# each cells rule is what closes its family: with the rule off, that family's case gets out again
# (f08, p07, m02, n05 are closed by both period rules; period_bind alone closes the planted f_prev_in_now, below)
RULE_CASES = [
    ("period_named", "f21"), ("period_named", "p05"), ("period_named", "f22"), ("free_date", "g05"),
    ("free_date", "c10"), ("weekday_typed", "w01"), ("item_fields", "h03"), ("item_fields", "e09"),
    ("item_fields", "e13"), ("length_cell", "a19"), ("length_cell", "p06"), ("length_cell", "n09"),
    ("pairs_crossed", "p02")]


@pytest.mark.parametrize("rule,cid", RULE_CASES)
def test_each_cells_rule_closes_its_family_and_is_switchable(rule, cid):
    d = _a2()
    c = next(x for x in d["cases"] if x["id"] == cid)
    assert P.attack2_outcome(c, d, "cells") == (False, False)
    assert any(P.attack2_outcome(c, d, _without("rule", rule)))


def test_period_bind_alone_holds_a_cell_of_the_window_before_said_with_the_windows_words():
    data = P.load()
    for cid in ("f_prev_in_now", "audit_F82", "attack_E02"):
        c = next(x for x in data["cases"] if x["id"] == cid)
        assert not P.outcome(c, data["ledgers"], "cells")[0], cid
        assert P.outcome(c, data["ledgers"], _without("rule", "period_bind"))[0], cid


def test_insight_walk_closes_the_two_masking_holes_and_counts_only_binding_and_name_reasons():
    (c16, s16, _h), (c19, s19, _h2) = PROBES[-2:]
    assert _point(c16, s16, "cells") == (False, ["wrong_area"])
    assert _point(c16, s16, _without("rule", "insight_walk")) == (True, [])
    # p19 ("mostly long-form at 69%[...shorts_share]") is held twice: insight's shorts_as_long, reached by the walk,
    # and the rule length_cell
    assert _point(c19, s19, "cells") == (False, ["length_cell", "shorts_as_long"])
    assert _point(c19, s19, _without("rule", "insight_walk")) == (False, ["length_cell"])
    assert "date" not in V.WALK_ACCEPT and "percent" not in V.WALK_ACCEPT and "wrong_area" in V.WALK_ACCEPT
    from mvp import insight as I
    assert I._go("spread", frozenset()) and not I._go("spread", frozenset({"spread"})) and I._go("x", {"spread"})


def test_date_owner_holds_a_date_beside_another_rows_handle_now_that_the_handle_is_no_link():
    d = _a2()
    c = next(x for x in d["cases"] if x["id"] == "b09")
    assert P.attack2_outcome(c, d, "cells") == (False, False)
    assert any(P.attack2_outcome(c, d, _without("rule", "date_owner")))


# false twins: a sibling of a closed case in another shape (written after the rules; five of them got out at first and
# were closed: a yearless day, a month after 'starting', 'every one a Short', 'N Shorts', another item's quoted title)
FALSE_TWINS = [
    ("C09.0", "Gaming clutch moment[r1.items[4]] was opened on 30 October."),
    ("C09.0", "Gaming clutch moment[r1.items[4]] was opened on 30 October 2026."),
    ("C08.0", "Frame Perfect[r1.channels[0]] made all 90[r1.totals.items] of them, starting in April."),
    ("C08.0", "Frame Perfect[r1.channels[0]] made all 90[r1.totals.items] of them, from April 2022."),
    ("A01.3", "Pan Theory[r1.channels[1]] made 32[r1.channels[1].items] videos, every one a Short."),
    ("A01.3", "Pan Theory[r1.channels[1]] made 32[r1.channels[1].items] Shorts."),
    ("A01.3", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of those cooking videos, ahead of Pan "
              "Theory[r1.channels[1]]."),
    ("F11.0", "September had 36[r2.periods[7].items] videos."),
    ("F11.0", "In 2024 you opened 254[r2.totals.items] videos."),
    ("B07.0", 'You first opened "Watercolor trees easy" on 10 January 2025[r1.items[0].when].'),
    ("B07.0", "Watercolor trees easy[r1.items[1]] came on 10 January 2025[r1.items[0].when]."),
    ("B07.0", "You first opened a watercolor video on 10 January 2025[r1.items[0].when], late at night."),
    ("D07.0", "Digital drawing on the 30th[r1.items[0]] came first, and Cooking soup on the 30th[r1.items[3]] came "
              "from Pixel Pencil."),
    ("D07.0", "Cooking soup on the 30th[r1.items[3]] was opened on 30 October 2026[r1.items[3].when], from Pixel "
              "Pencil."),
    ("D07.0", "On Saturday 30 October 2026, you opened 4[r1.totals.items] videos."),
]
TRUE_TWINS = [
    ("C08.0", "Frame Perfect[r1.channels[0]] made all 90[r1.totals.items] of them, starting in March."),
    ("B07.0", "You first opened a watercolor video on 10 January 2025[r1.items[0].when], in late January."),
    ("B07.0", "You first opened a watercolor video on 10 January 2025[r1.items[0].when], in the afternoon."),
    ("B07.0", 'You first opened "Watercolor wet on wet" on 10 January 2025[r1.items[0].when].'),
    ("F11.0", "August had 36[r2.periods[7].items] videos."),
    ("F11.0", "In August 2026 you opened 36[r2.periods[7].items] videos."),
    ("A01.3", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] Shorts."),
    ("A01.3", "Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] of those gaming videos."),
    ("A01.3", "Pan Theory[r1.channels[1]] made 32[r1.channels[1].items] long videos."),
    ("A01.3", "You opened 142[r1.totals.items] videos in October, 72[r1.totals.long] of them long."),
    ("D07.0", "Cooking soup on the 30th[r1.items[3]] came from Pan Theory."),
    ("D07.0", "Cooking soup on the 30th[r1.items[3]] was opened late, and Digital drawing on the 30th[r1.items[0]] "
              "came from Pixel Pencil."),
    ("D07.0", "On Friday 30 October 2026, you opened 4[r1.totals.items] videos."),
    ("K03.0", "Watercolor painting[r3.themes[2]] went from 45[r3.themes[2].previous_items] videos in the same part of "
              "2025 to 41[r3.themes[2].items] this year."),
]


@pytest.mark.parametrize("rec,sentence", FALSE_TWINS)
def test_false_twins_are_dropped_in_cells_mode(rec, sentence):
    assert _a2_kept(rec, sentence) == (False, False)


@pytest.mark.parametrize("rec,sentence", TRUE_TWINS)
def test_true_twins_are_kept_in_cells_mode(rec, sentence):
    assert _a2_kept(rec, sentence) == (True, True)


# the loosenings of DESIGN 24.4 step 5, each bringing back a true sentence the marker bookkeeping dropped
LOOSE_CASES = [
    ("own_fields", "D07.0", "Cooking soup on the 30th[r1.items[3]] came from Pan Theory."),
    ("handle", "A01.3", "Watercolor painting[r1.themes[4]] came to 5[r1.themes[4].items] videos, "
                        "4[r1.themes[4].channels[0].items] of them from @wetpaper.ig[r1.themes[4].channels[0]]."),
    ("month_alone", "F11.0", "August had 36[r2.periods[7].items] videos."),
]


@pytest.mark.parametrize("loose,rec,sentence", LOOSE_CASES)
def test_each_loosening_brings_back_its_true_sentence(loose, rec, sentence):
    assert _a2_kept(rec, sentence) == (True, True)
    assert not all(_a2_kept(rec, sentence, _without("loose", loose)))


def test_hour_word_and_a_window_end_inside_a_date():
    led = {"r1": {"rid": "r1", "tool": "breakdown", "meta": {"window_said": "all your history"}, "sheet": {
        "kind": "when", "window": {"words": "all your history", "start": "2021-01-05", "end": "2026-10-30"},
        "totals": {"items": 723},
        "when": {"busiest_hours": [{"hour": 16, "share": 0.25}, {"hour": 18, "share": 0.25}]}}}}
    s = "Hour 18[r1.when.busiest_hours[1].hour] came next at 25%[r1.when.busiest_hours[1].share]."
    o = V.check_sentence(s, V.Ledger(led), V.Turn(), mode="cells")
    assert "unknown_name" not in o.reasons and "watch_time" not in o.reasons
    o2 = V.check_sentence(s, V.Ledger(led), V.Turn(), mode=_without("loose", "hour_word"))
    assert "unknown_name" in o2.reasons
