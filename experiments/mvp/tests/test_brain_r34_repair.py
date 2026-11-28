"""mvp34 repair (DESIGN 33.5): two faults of the round's fix, each fixed where it starts. Every expected day is
recounted from the made-up library's own rows (tests/brain_library.py), never copied from a tool's output. Made-up
library and made-up messages only; no model call.

1. A weekday's window over all their history ("on Mondays, over all your history (...)") kept the window's two ends
   as its words, the class the round fixes: its words, its said days and the scope line now say the rows' days.
2. A quoted day was found in the window's words that say the rows' days: those words are kept out of the text a
   quote is looked up in, as they are out of code's strings, so a quoted day stands only where it stood before.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mvp.tests.test_brain_r30_tools import (  # noqa: E402,F401  (fixtures)
    S,
    W,
    brain,
    built,
    call,
    env,
    local,
    no_real_keys,
    person,
    visible_rows,
)

SAVE_KINDS = ("save", "playlist", "collection")
EXPORT_END = "2026-10-30"   # where the made-up YouTube export ends (brain_library's clock), the later of the two


def _event_days(kinds, weekday=None):
    return sorted(local(at) for x in visible_rows() for k, at in x["events"]
                  if k in kinds and (weekday is None or local(at).weekday() == weekday))


def _monday_saves(brain):
    return call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(how="saved", weekday=0)},
                "what did i keep on mondays")


def _point(t, sentence):
    from mvp.brain import verify as V
    v = V.check_answer({"lead": "Here is what it holds.", "points": [sentence]}, t.results, V.Turn.of(t),
                       mode="values")
    return [o for o in v.outcomes if o.where == "point"][0]


# ================================================================ 1. a weekday's window over all their history
def test_a_weekday_window_over_all_history_says_the_rows_days_not_the_windows_ends(brain):
    from mvp import history as Hm
    r, _t = _monday_saves(brain)
    w = r["sheet"]["window"]
    days = _event_days(SAVE_KINDS, weekday=0)                                                           # recount
    first, last = days[0], days[-1]
    assert (w["first_counted"], w["last_counted"]) == (first.isoformat(), last.isoformat())
    # the window's own cells are as they were: it starts on the first save of any day, it ends where the export ends
    assert w["start"] == _event_days(SAVE_KINDS)[0].isoformat() < first.isoformat() and w["end"] == EXPORT_END
    end_words = Hm.day_words(local(EXPORT_END + "T12:00:00+00:00"))
    assert w["words"].startswith("on Mondays, over all your history (the saves counted: "
                                 f"{Hm.span_words(first, last)}; your export ends on {end_words}")
    # no pair from the window's start to its end, in any of the words the model reads
    pair = Hm.span_words(_event_days(SAVE_KINDS)[0], local(EXPORT_END + "T12:00:00+00:00"))
    d = r["meta"]["window_dates"]
    for words in (w["words"], r["meta"]["window_said"], d["said"]):
        assert pair not in words and "where your export ends" not in words, words
    assert r["meta"]["window_said"] == w["words"]
    assert d["said"] == w["words"][len("on Mondays, over all your history ("):-1]
    # no day b99bcea's weekday words did not hold: not the first item of any kind (window.platform_starts holds it)
    assert "of any kind" not in w["words"] and w.get("platform_starts")


def test_a_weekday_window_keeps_its_old_words_for_the_full_and_cells_checks(brain):
    from mvp import history as Hm
    from mvp.brain import verify as V
    r, t = _monday_saves(brain)
    base = V.rows_aside(V.Ledger(t.results).get(r["rid"]).env)
    pair = Hm.span_words(_event_days(SAVE_KINDS)[0], local(EXPORT_END + "T12:00:00+00:00"))            # recount
    assert base["sheet"]["window"]["words"] == f"on Mondays, over all your history ({pair}, where your export ends)"
    assert base["meta"]["window_said"] == base["sheet"]["window"]["words"]
    assert base["meta"]["window_dates"]["said"] == pair   # the bare days, as before the round
    assert "first_counted" not in base["sheet"]["window"]


def test_the_scope_line_of_a_weekday_window_says_no_day_that_is_not_the_rows(brain):
    from mvp.brain import answer as A, verify as V
    r, t = _monday_saves(brain)
    res = V.Ledger(t.results).get(r["rid"])
    line = A.scope_line(res)
    assert line.endswith("on Mondays, over all your history"), line
    assert "October" not in line and "January" not in line
    # never longer than the line of the words as they were
    old = A.scope_line(V.Ledger([V.rows_aside(res.env)]).get(r["rid"]))
    assert len(line) <= len(old) and "30 October 2026" in old


def test_a_weekday_over_an_asked_window_keeps_its_words(brain):
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W("october 2026"), "scope": S(how="saved", weekday=0)},
                 "what did i keep on mondays in october 2026")
    w = r["sheet"]["window"]
    # an asked window: its words are the tool's, as before (only all their history is reworded)
    assert w["words"].startswith("on Mondays, over ") and "counted:" not in w["words"]


# ================================================================ 2. a quoted day of the rows' words
def test_a_quoted_day_of_the_rows_words_is_not_found(brain):
    from mvp import history as Hm
    r, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(how="saved")}, "count my kept things")
    days = _event_days(SAVE_KINDS)                                                                      # recount
    last = Hm.day_words(days[-1])
    assert days[-1].isoformat() < EXPORT_END and last in r["sheet"]["window"]["words"]
    for s in (f'Your first kept thing is dated "{last}".',
              f'Your kept things run "{Hm.span_words(days[0], days[-1])}".'):
        o = _point(t, s)
        assert not o.kept and "unfound_name" in o.reasons, (s, o.reasons)
    # the same day on its own cell still passes
    o = _point(t, f"Your last kept thing is from {last}[r1.window.last_counted].")
    assert o.kept, o.reasons


def test_the_text_a_quote_is_looked_up_in_holds_no_rows_days(brain):
    from mvp import history as Hm
    from mvp.brain import verify as V
    r, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(how="saved")}, "count my kept things")
    pool = V._Pool(V.Ledger(t.results), "count my kept things")
    days = _event_days(SAVE_KINDS)                                                                      # recount
    assert Hm.day_words(days[-1]).lower() not in pool.text
    assert days[-1].isoformat() not in pool.text and days[-1].isoformat() in pool.rows_days
    assert "your export ends on" in pool.text   # the rest of the words is still text
