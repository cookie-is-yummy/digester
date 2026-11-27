"""mvp32 part two (DESIGN 32.8): the scope line a person sees is short and true.

Class: a scope's window over all their history carries words that are right for the model (each end said for what it
is, and the platforms' older start), and code's own scope line printed them whole to the person. The line now says the
window's start, as what it is (and no start beside a filter beyond the platform: repair2); the model's words are not
changed, and every other window's line is as it was. Every
expected day is recounted from the made-up library's own rows (tests/brain_library.py). No model call.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mvp.tests.test_brain_r30_tools import (  # noqa: F401  (fixtures)
    S,
    W,
    brain,
    built,
    call,
    env,
    harness,
    local,
    no_real_keys,
    person,
    visible_rows,
)


def _first(kinds, platform=None):
    return min(local(at) for x in visible_rows() if platform in (None, x["platform"]) for k, at in x["events"]
               if k in kinds)


def _line(r):
    from mvp.brain import answer as A
    from mvp.brain import verify as V
    return A.scope_line(V.Ledger({r["rid"]: r}).get(r["rid"]))


def test_a_platform_scope_over_all_history_says_its_start_as_what_it_is(brain):
    from mvp import history as Hm
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(platforms=["instagram"])},
                 "my insta opens ever")
    first_open, first_any = _first(("watch",), "instagram"), _first(("watch", "save", "like"), "instagram")
    line = _line(r)
    assert f"all your history (from {Hm.day_words(first_open)}, your first Instagram open)" in line
    assert Hm.day_words(first_any) not in line and " to " not in line                    # no span of the rows
    # the model's words are the long ones, as before
    assert r["meta"]["window_said"].endswith(f"; your first Instagram item of any kind: {Hm.day_words(first_any)})")
    assert r["sheet"]["window"]["words"] == r["meta"]["window_said"]


def test_a_saves_scope_line_names_its_first_save(brain):
    from mvp import history as Hm
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(how="saved")}, "everything i kept")
    first_save = _first(("save", "playlist", "collection"))
    assert _line(r) == f"Counted: totals · what you saved · all your history (from {Hm.day_words(first_save)}, your " \
                       "first save)"


def test_every_other_window_keeps_its_line():
    from mvp.brain import answer as A
    from mvp.brain import tools as TL
    from datetime import date

    def line(said, filters=None):
        res = types.SimpleNamespace(meta={"window_said": said, "base": "of what you opened", "filters_said": filters},
                                    sheet={"kind": "totals"}, tool="breakdown")
        return A.scope_line(res)
    # the words tools.scope_span_words writes, for every kind and with no single platform, with and without the end
    for how, noun in (("watched", "open"), ("saved", "save"), ("liked", "like"), ("any", "item")):
        for plats, p in ((["youtube"], "YouTube "), (["youtube", "instagram"], "")):
            for end in (True, False):
                w = "all your history (" + TL.scope_span_words(plats, how, date(2026, 10, 3), date(2026, 10, 30), end,
                                                               date(2021, 1, 5)) + ")"
                assert line(w).endswith(f"all your history (from 3 October 2026, your first {p}{noun})"), w
    # windows of any other words: as they were
    for w, want in (("all your history (5 January 2021 to 30 October 2026, where your export ends)",
                     "all your history (5 January 2021 to 30 October 2026)"),
                    ("all your history (your Instagram opens: 12 to 15 October 2026)",
                     "all your history (your Instagram opens: 12 to 15 October 2026)"),
                    ("the last 4 weeks (3 to 30 October 2026, where your export ends)",
                     "the last 4 weeks (3 to 30 October 2026)"),
                    ("in October 2026", "in October 2026")):
        assert line(w).endswith(f" · what you opened · {want}"), w
    # a filter the line names is said once, as before
    w = "all your history (" + TL.scope_span_words(["instagram"], "watched", date(2026, 10, 12), date(2026, 10, 15),
                                                   True, date(2026, 10, 5)) + ")"
    assert line(w, "Instagram only").endswith("your first Instagram open) · Instagram only")


def test_beside_a_filter_beyond_the_platform_the_line_says_no_start():
    # (repair2: "from 3 October 2026, your first save · <a channel>" read as the first save of that channel's rows)
    from datetime import date

    from mvp.brain import answer as A
    from mvp.brain import tools as TL

    def line(said, filters=None, sheet_filters=None):
        res = types.SimpleNamespace(meta={"window_said": said, "base": "of what you saved", "filters_said": filters},
                                    sheet={"kind": "totals", "filters": sheet_filters or {}}, tool="breakdown")
        return A.scope_line(res)
    w = "all your history (" + TL.scope_span_words(["youtube", "instagram"], "saved", date(2026, 10, 3),
                                                   date(2026, 10, 30), True, date(2021, 1, 5)) + ")"
    for filters, tail in (("only food and cooking (area)", " · only food and cooking (area)"),
                          ("without food and cooking (area)", " · without food and cooking (area)"),
                          ("only Shorts and reels; Instagram only", " · only Shorts and reels · Instagram only"),
                          ("crumb.lab: @crumb.lab (channel)", " · crumb.lab: @crumb.lab (channel)")):
        got = line(w, filters)
        assert got.endswith(" · what you saved · all your history" + tail), got
        assert "October" not in got and "January" not in got
    got = line(w, None, {"without_shorts": True})
    assert got.endswith(" · what you saved · all your history · only videos known to be long"), got
    assert line(w, None, {"length": "short"}).endswith(" · all your history")
    # a platform alone keeps the start, said as what it is
    wi = "all your history (" + TL.scope_span_words(["instagram"], "saved", date(2026, 10, 5), date(2026, 10, 15),
                                                    True) + ")"
    assert line(wi, "Instagram only").endswith("all your history (from 5 October 2026, your first Instagram save) · "
                                               "Instagram only")
    # a window of other words beside a filter is as it was
    assert line("the last 4 weeks (3 to 30 October 2026, where your export ends)", "only food and cooking (area)") \
        .endswith(" · the last 4 weeks (3 to 30 October 2026) · only food and cooking (area)")


def test_a_first_save_of_a_channel_is_not_given_the_first_save_of_all(brain):
    from mvp import history as Hm
    r, _t = call(brain, "first_last", {"subject": "crumb.lab", "which": "first", "scope": S(how="saved")},
                 "the first crumb.lab post i kept")
    first_all = Hm.day_words(_first(("save", "playlist", "collection")))
    assert first_all in r["meta"]["window_said"]                                        # the model's words, as before
    line = _line(r)
    assert first_all not in line and " · all your history · " in line, line
