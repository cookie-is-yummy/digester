"""mvp34 (DESIGN 33): the days of the rows counted, given by the tool. A window of all their history over a scope
starts on the scope's first row and ends where the export ends; no cell held the day of the last row counted, and a
sentence about the rows said the window's two ends as their span. Each test names a class of case; every expected
day is recounted from the made-up library's own rows (tests/brain_library.py, r12_library.py), never copied from a
tool's output. Made-up library and made-up messages only; no model call.

1. Every result that counts rows over a window gives the first and the last day of those rows, in its window.
2. A window of all their history whose rows do not span it says the rows' days, and where the export ends, apart.
3. The private topics and a friend's post never move those days.
4. The scope line a person sees says only the rows' days, and nothing beside a filter.
5. The reword of a cited meta.window_dates names the rows' cells, never the window's ends; a day of the rows said
   with no marker is not found through the new cells, and its reword names the cell.
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


def _days(kinds, keep=lambda r: True, a=None, b=None, rows=None):
    ds = [local(at) for x in (rows if rows is not None else visible_rows()) if keep(x) for k, at in x["events"]
          if k in kinds and (a is None or a <= local(at)) and (b is None or local(at) <= b)]
    return min(ds), max(ds)


def _values(t, form):
    from mvp.brain import verify as V
    return V.check_answer(form, t.results, V.Turn.of(t), mode="values")


def _point(t, sentence):
    v = _values(t, {"lead": "Here is what it holds.", "points": [sentence]})
    return [o for o in v.outcomes if o.where == "point"][0]


def _saves(brain, scope=None, tool="breakdown", message="count my kept things"):
    args = {"breakdown": {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(preset="all"),
                          "scope": scope or S(how="saved")},
            "items": {"window": W(preset="all"), "scope": scope or S(how="saved"), "order": "newest", "limit": 2},
            "timeline": {"unit": "month", "window": W(preset="all"), "scope": scope or S(how="saved")}}[tool]
    return call(brain, tool, args, message)


# ================================================================ 1. the rows' days, in the window
def test_a_saves_window_over_all_history_gives_the_days_of_the_saves_counted(brain):
    from mvp import history as Hm
    r, _t = _saves(brain)
    w = r["sheet"]["window"]
    first, last = _days(SAVE_KINDS)                                                                     # recount
    assert (w["first_counted"], w["last_counted"]) == (first.isoformat(), last.isoformat())
    # the window's own cells are as they were: its start is the first save, its end where the export ends
    assert (w["start"], w["end"]) == (first.isoformat(), EXPORT_END) and last.isoformat() < w["end"]
    assert w["days"] == (local(EXPORT_END + "T12:00:00+00:00") - first).days + 1
    # the words say the rows' days once, as that, and where the export ends, as that; no pair to the export's end
    assert w["words"] == (f"all your history (the saves counted: {Hm.span_words(first, last)}; your export ends on "
                          f"{Hm.day_words(local(EXPORT_END + 'T12:00:00+00:00'))}; your first item of any kind: "
                          f"{Hm.day_words(_days(('watch', 'save', 'like', 'playlist'))[0])})")
    assert "to 30 October 2026" not in w["words"] and r["meta"]["window_said"] == w["words"]
    d = r["meta"]["window_dates"]
    assert d["said"] == w["words"][len("all your history ("):-1] and (d["start"], d["end"]) == (w["start"], w["end"])
    assert "first_counted" not in d and any("window.first_counted" in n for n in r["meta"]["notes"])


def test_a_names_scope_gives_its_own_rows_days_not_the_scopes(brain):
    from mvp import history as Hm
    r, _t = _saves(brain, S(how="saved", only=["crumb.lab"]))
    w = r["sheet"]["window"]
    first, last = _days(SAVE_KINDS, lambda x: x.get("handle") == "crumb.lab")                           # recount
    assert (w["first_counted"], w["last_counted"]) == (first.isoformat(), last.isoformat())
    assert w["start"] == _days(SAVE_KINDS)[0].isoformat() < first.isoformat()   # the window starts on any first save
    assert f"the saves counted: {Hm.span_words(first, last)};" in w["words"]


def test_rows_that_span_the_window_keep_its_words(brain):
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S()}, "everything i opened")
    w = r["sheet"]["window"]
    first, last = _days(("watch",))                                                                     # recount
    assert (w["first_counted"], w["last_counted"]) == (w["start"], w["end"]) == (first.isoformat(), last.isoformat())
    assert w["words"] == "all your history (5 January 2021 to 30 October 2026, where your export ends)"


def test_an_asked_window_keeps_its_words_and_gets_the_rows_days(brain):
    import datetime as dt
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W("october 2026"), "scope": S(platforms=["instagram"])},
                 "my instagram opens in october 2026")
    w = r["sheet"]["window"]
    first, last = _days(("watch",), lambda x: x["platform"] == "instagram", dt.date(2026, 10, 1),
                        dt.date(2026, 10, 31))                                                          # recount
    assert (w["first_counted"], w["last_counted"]) == (first.isoformat(), last.isoformat())
    assert w["words"].startswith("October 2026") and "counted" not in w["words"]


def test_every_tool_with_a_window_gives_the_same_pair_in_its_window(brain):
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    msg = "october 2026 and september 2026"
    calls = [("timeline", {"unit": "month", "window": W(preset="all"), "scope": S(how="saved")}),
             ("changes", {"level": "theme", "window": W("october 2026"), "scope": S()}),
             ("compare", {"a": W("october 2026"), "b": W("september 2026"), "by": "none", "scope": S()}),
             ("first_last", {"subject": "watercolor", "which": "last", "scope": S()}),
             ("items", {"window": W(preset="all"), "scope": S(how="saved"), "order": "newest", "limit": 2})]
    for tool, args in calls:
        r, _t = call(brain, tool, args, msg)
        w = r["sheet"]["window"]
        assert w["first_counted"] <= w["last_counted"] and w["start"] <= w["first_counted"], tool
        assert w["last_counted"] <= w["end"], tool
    wc = _days(("watch",), lambda x: x["theme"] == "wc")                                                 # recount
    r, _t = call(brain, "first_last", {"subject": "watercolor", "which": "last", "scope": S()}, "watercolor")
    assert (r["sheet"]["window"]["first_counted"], r["sheet"]["window"]["last_counted"]) == \
        (wc[0].isoformat(), wc[1].isoformat())
    # search and learned count no window: no pair
    for tool, args in (("search", {"query": "sourdough", "how": "saved"}), ("learned", {"topic": "calculus"})):
        r, _t = call(brain, tool, args, "sourdough calculus", search=FakeEngine(), learned=fake_learned)
        assert "first_counted" not in str(r), tool


def test_no_row_counted_gives_no_pair(brain):
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W("2024"), "scope": S(how="saved")}, "what did i save in 2024")
    w = (r.get("sheet") or {}).get("window") or {}
    assert not any(x for x in visible_rows() for k, at in x["events"] if k in SAVE_KINDS
                   and local(at).year == 2024)                                                         # recount
    assert "first_counted" not in w and "last_counted" not in w


# ================================================================ 3. private rows and friends never move the days
def test_the_private_topic_moves_the_days_only_when_the_message_names_it(brain):
    import datetime as dt
    a, b = dt.date(2024, 2, 1), dt.date(2024, 8, 15)
    words = "between 1 february 2024 and 15 august 2024"
    args = {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(words), "scope": S()}
    shown = _days(("watch",), a=a, b=b)                                                                 # recount
    every = _days(("watch",), a=a, b=b, rows=visible_rows(unlock_sensitive=True))
    assert every[0] < shown[0] and shown[1] < every[1]   # the private rows are both ends of the window's opens
    r, _t = call(brain, "breakdown", args, f"what did i open {words}")
    w = r["sheet"]["window"]
    assert (w["first_counted"], w["last_counted"]) == (shown[0].isoformat(), shown[1].isoformat())
    r, _t = call(brain, "breakdown", args, f"my dating videos {words}")
    w = r["sheet"]["window"]
    assert (w["first_counted"], w["last_counted"]) == (every[0].isoformat(), every[1].isoformat())
    # a follow-up under a carried unlock: the topic stays out of a total not scoped to it, and out of its days
    r, _t = call(brain, "breakdown", args, f"and everything {words}", carried_unlock="dating")
    w = r["sheet"]["window"]
    assert (w["first_counted"], w["last_counted"]) == (shown[0].isoformat(), shown[1].isoformat())


def test_a_friends_post_is_never_a_day_of_the_rows(brain):
    import datetime as dt
    words = "between 6 october 2026 and 9 october 2026"
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(words), "scope": S(how="saved")}, f"what did i save {words}")
    w = r["sheet"]["window"]
    shown = _days(SAVE_KINDS, a=dt.date(2026, 10, 6), b=dt.date(2026, 10, 9))                          # recount
    friend = [local(at) for x in __import__("mvp.tests.brain_library", fromlist=["rows"]).rows() if x.get("friend")
              for _k, at in x["events"]]
    assert friend and shown[1] < friend[0] <= dt.date(2026, 10, 9)   # the friend's save is the window's last save
    assert (w["first_counted"], w["last_counted"]) == (shown[0].isoformat(), shown[1].isoformat())


# ================================================================ 4. the scope line a person sees
def test_the_scope_line_says_the_rows_days_and_nothing_beside_a_filter(brain):
    from mvp import history as Hm
    from mvp.brain import answer as A, verify as V
    first, last = _days(SAVE_KINDS)                                                                     # recount
    r, t = _saves(brain)
    line = A.scope_line(V.Ledger(t.results).get(r["rid"]))
    assert line.endswith(f"all your history (saves: {Hm.span_words(first, last)})"), line   # named as the rows' days
    assert "30 October" not in line and len(line) <= len("Counted: totals · what you saved · all your history "
                                                         "(from 3 October 2026, your first save)")
    r, t = _saves(brain, S(how="saved", only=["crumb.lab"]))
    line = A.scope_line(V.Ledger(t.results).get(r["rid"]))
    assert "all your history ·" in line and "October" not in line, line


# ================================================================ 5. the reword and the values check
def test_a_cited_meta_window_dates_is_reworded_to_the_rows_cells(brain):
    from mvp.brain import verify as V
    from mvp import history as Hm
    r, t = _saves(brain)
    first = Hm.day_words(_days(SAVE_KINDS)[0])                                                          # recount
    o = _point(t, f"Your kept things begin on {first}[r1.window_dates] and run to the export's end.")
    assert not o.kept and "bad_ref" in o.reasons
    d = " ".join(o.details)
    assert "r1.window.first_counted" in d and "r1.window.last_counted" in d
    assert "r1.window.start" not in d and "r1.window.end" not in d
    # within the 160 characters a reason keeps, with a two-digit rid and a long path
    sheet = {"window": {"start": "2026-10-03", "end": "2026-10-30", "first_counted": "2026-10-03",
                        "last_counted": "2026-10-10"}}
    s = V._v_rows_days_hint("[r12.meta.window_dates.start]", "r12", sheet, "window_dates.start", "date")
    assert s and len(s) <= 158 and "r12.window.last_counted" in s
    assert V._v_rows_days_hint("[r12.window_dates.days]", "r12", sheet, "window_dates.days", "number") is None


def test_the_rows_days_pass_on_their_markers_and_a_wrong_day_does_not(brain):
    from mvp import history as Hm
    r, t = _saves(brain)
    n = r["sheet"]["totals"]["items"]
    first, last = (Hm.day_words(x) for x in _days(SAVE_KINDS))                                          # recount
    ok = _point(t, f"You saved {n}[r1.totals.items] items, from {first}[r1.window.first_counted] to {last}"
                   "[r1.window.last_counted].")
    assert ok.kept, ok.reasons
    for bad in (f"You saved {n}[r1.totals.items] items, the last on 30 October 2026[r1.window.last_counted].",
                f"You saved {n}[r1.totals.items] items, the first on {last}[r1.window.first_counted]."):
        o = _point(t, bad)
        assert not o.kept and "wrong_value" in o.reasons, bad


def test_a_rows_day_with_no_marker_is_not_found_through_the_new_cells(brain):
    from mvp import history as Hm
    r, t = _saves(brain)
    n = r["sheet"]["totals"]["items"]
    last = Hm.day_words(_days(SAVE_KINDS)[1])                                                           # recount
    for s in (f"In all your history you saved {n}[r1.totals.items] items, the last on {last}.",
              f"In all your history you opened {n}[r1.totals.items] items, the last on {last}."):
        o = _point(t, s)
        assert not o.kept and o.reasons == ["unfound_date"], (s, o.reasons)
        assert "r1.window.last_counted" in " ".join(o.details)


def test_the_rows_span_with_no_marker_is_reworded_to_its_two_cells(brain):
    from mvp import history as Hm
    r, t = _saves(brain)
    first, last = _days(SAVE_KINDS)                                                                     # recount
    o = _point(t, f"You saved {r['sheet']['totals']['items']}[r1.totals.items] items, from "
                  f"{Hm.span_words(first, last)}.")
    assert not o.kept and o.reasons == ["unfound_date"]
    assert "from <day>[r1.window.first_counted] to <day>[r1.window.last_counted]" in " ".join(o.details)


def test_one_day_of_rows_and_a_day_two_results_hold_are_reworded_rightly(brain):
    from mvp import history as Hm
    from mvp.brain import tools as TL, verify as V
    from mvp.tests.test_brain_tools import turn
    one = [x for x in visible_rows() if x.get("handle") == "noodle.nights"]
    day = _days(SAVE_KINDS, rows=one)                                                                   # recount
    assert day[0] == day[1]
    t = turn(brain, "count my noodle things")
    r = TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(preset="all"),
                                 "scope": S(how="saved", only=["noodle.nights"])})
    w = r["sheet"]["window"]
    assert w["first_counted"] == w["last_counted"] == day[0].isoformat()
    assert f"the saves counted: {Hm.day_words(day[0])};" in w["words"]
    o = _point(t, f"You kept 1[r1.totals.items] noodle post, on {Hm.day_words(day[0])}.")
    assert o.reasons == ["unfound_date"] and "cite r1.window.last_counted right after the day" in " ".join(o.details)
    # the same day held by the rows of two results: no cell is picked for the model
    TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(preset="all"),
                             "scope": S(how="saved")})
    o = _point(t, f"You kept 1[r1.totals.items] noodle post, on {Hm.day_words(day[0])}.")
    d = " ".join(o.details)
    assert o.reasons == ["unfound_date"] and "first_counted" not in d and "last_counted" not in d
    assert "no result of this turn holds" not in d


def test_the_model_is_never_sent_the_words_kept_for_the_checks(brain):
    from mvp.brain import loop as L, results as R
    r, _t = _saves(brain)
    assert R.BASE_WINDOW in r and r[R.BASE_WINDOW]["words"] != r["sheet"]["window"]["words"]
    sent = L.present(r)
    assert R.BASE_WINDOW not in sent and r[R.BASE_WINDOW]["words"] not in sent


def test_one_marker_after_a_span_of_the_rows_is_reworded_to_two(brain):
    from mvp import history as Hm
    r, t = _saves(brain)
    first, last = _days(SAVE_KINDS)                                                                     # recount
    o = _point(t, f"You saved {r['sheet']['totals']['items']}[r1.totals.items] items, between "
                  f"{Hm.span_words(first, last)}[r1.window.first_counted].")
    assert not o.kept and "wrong_value" in o.reasons
    assert "from <day>[r1.window.first_counted] to <day>[r1.window.last_counted]" in " ".join(o.details)
