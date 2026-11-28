"""mvp32 (DESIGN 32): faults that start in a tool result or in code, fixed where they start. Each test names a class
of case; every expected value is recounted from the made-up library's own rows (tests/brain_library.py,
r12_library.py), never copied from a tool's output. Made-up library and made-up messages only; no model call.

1. (taken back in the repair of this round: rows show today's display title, as before; DESIGN 32.)
2. The words of a scope's window say what each end is; the scope's start and the platform's start are named apart.
3. The private line follows what the results behind the answer that goes out left out.
4. A topic's name is cited on its own row (learned's `on_topic`), and the row's list is no figure.
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
    harness,
    local,
    no_real_keys,
    person,
    visible_rows,
)


def _values(t, form):
    from mvp.brain import verify as V
    return V.check_answer(form, t.results, V.Turn.of(t), mode="values")


def _point(t, sentence, lead="Here is what it holds."):
    v = _values(t, {"lead": lead, "points": [sentence]})
    return [o for o in v.outcomes if o.where == "point"][0]


def _lead(t, sentence):
    v = _values(t, {"lead": sentence, "points": []})
    return [o for o in v.outcomes if o.where == "lead"][0]


# ================================================================ 2. a span's words say what span it is
def _first(kinds, platform=None):
    return min(local(at) for x in visible_rows() if platform in (None, x["platform"]) for k, at in x["events"]
               if k in kinds)


def test_a_scope_window_over_all_history_says_what_each_end_is(brain):
    from mvp import history as Hm
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(how="saved")}, "everything i kept")
    w = r["sheet"]["window"]
    first_save = _first(("save", "playlist", "collection"))                                             # recount
    last_save = max(local(at) for x in visible_rows() for k, at in x["events"] if k in ("save", "playlist",
                                                                                         "collection"))
    assert w["start"] == first_save.isoformat() and w["end"] > last_save.isoformat()
    # mvp34 (DESIGN 33): the saves do not span the window, so its words say the days of the saves counted
    assert w["words"] == (f"all your history (the saves counted: {Hm.span_words(first_save, last_save)}; your export "
                          f"ends on {Hm.day_words(local('2026-10-30T12:00:00+00:00'))}; your first "
                          f"item of any kind: {Hm.day_words(_first(('watch', 'save', 'like')))})")
    assert "your saves:" not in w["words"] and r["meta"]["window_said"] == w["words"]
    # the meta copy of the window's days says the same words once, never the bare span of the window
    d = r["meta"]["window_dates"]
    assert d["said"] == w["words"][len("all your history ("):-1] and (d["start"], d["end"]) == (w["start"], w["end"])
    assert d["said"] != Hm.span_words(first_save, local("2026-10-30T12:00:00+00:00"))


def test_a_platform_scope_names_the_platforms_older_items_in_the_same_words(brain):
    from mvp import history as Hm
    r, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                    "window": W(preset="all"), "scope": S(platforms=["instagram"])},
                "my insta opens ever")
    w = r["sheet"]["window"]
    first_open, first_any = _first(("watch",), "instagram"), _first(("watch", "save", "like"), "instagram")
    assert first_any < first_open                                                                      # recount
    assert w["words"].startswith(f"all your history (from {Hm.day_words(first_open)}, the day of your first "
                                 "Instagram open, to ")
    assert w["words"].endswith(f"; your first Instagram item of any kind: {Hm.day_words(first_any)})")
    assert w["platform_starts"] == first_any.isoformat()
    # the words as the model would repeat them pass, with the count they frame
    said = w["words"][len("all your history ("):].split(",")[0]
    assert _lead(t, f"In all your history, {said}, you opened {r['sheet']['totals']['items']}[r1.totals.items] "
                    "Instagram items.").kept


def test_the_scope_start_and_the_platform_start_are_named_apart_in_one_note(brain):
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W("in 2023"), "scope": S(platforms=["instagram"])},
                 "insta in 2023")
    cs, w = r["sheet"]["cannot_see"], r["sheet"]["window"]
    assert cs["scope_starts"] == _first(("watch",), "instagram").isoformat()                         # recount
    assert w["platform_starts"] == _first(("watch", "save", "like"), "instagram").isoformat()
    note = next(x for x in r["meta"]["notes"] if "(cannot_see.scope_starts)" in x)
    assert "(window.platform_starts)" in note and note.index("scope_starts") < note.index("platform_starts")
    r2, _t2 = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                       "window": W("in October"), "scope": S(platforms=["instagram"])},
                   "insta in october")
    assert {"scope_starts", "platform_starts"} <= set(r2["sheet"]["window"])
    assert any(x.startswith("window.scope_starts:") and "window.platform_starts:" in x for x in r2["meta"]["notes"])


# ================================================================ 3. the private line behind the answer
def _private_month():
    """A month of the made-up library with private opens and one visible open."""
    from collections import Counter
    priv, vis = Counter(), Counter()
    for x in visible_rows(unlock_sensitive=True):
        for k, at in x["events"]:
            if k == "watch" and at.startswith("2024"):
                (priv if x["theme"] == "da" else vis)[at[:7]] += 1
    return max(m for m in vis if vis[m] == 1 and priv[m] > 0), priv


def _answer(t, form, also=None, mode="values"):
    from mvp.brain import answer as A
    from mvp.brain import verify as V
    v = V.check_answer(form, t.results, V.Turn.of(t), mode=mode)
    return A.build(V.Ledger(t.results), verdict=v, form=form, also=[v] + list(also or []), mode=mode), v


def test_the_line_shows_when_a_sent_sentence_cites_a_count_of_a_result_that_hid_private_rows(brain):
    from mvp.brain import tools as TL
    from mvp.brain import verify as V
    m, priv = _private_month()
    words = f"in {['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August'][int(m[5:]) - 1]} 2024"
    t = call(brain, "items", {"limit": 5, "offset": 0, "order": "newest", "window": W(words), "scope": S()},
             f"show me what i opened {words}")[1]
    TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(words),
                             "scope": S()})
    assert t.results["r1"]["meta"]["hidden"]["sensitive"] == t.results["r2"]["meta"]["hidden"]["sensitive"] == priv[m]
    lead = ("Of what you opened that month, 1[r2.totals.items] video shows: " + t.results["r1"]["sheet"]["items"][0]["title"]
            + "[r1.items[0]].")
    out, v = _answer(t, {"lead": lead, "points": []})
    assert [o.kept for o in v.outcomes] == [True] and not v.private_line   # the old rule: no line
    from mvp.brain import answer as A
    assert out["private_line"] and A.PRIVATE_LINE in out["text"]
    # the mvp31 rules (no "private_behind") build the line as before
    old = V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | V.VALUES_RULES_R31)
    assert not _answer(t, {"lead": lead, "points": []}, mode=old)[0]["private_line"]


def test_no_line_when_no_result_behind_the_answer_hid_private_rows(brain):
    from mvp.brain import tools as TL
    m, _priv = _private_month()
    words = f"in {['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August'][int(m[5:]) - 1]} 2024"
    t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(words),
                                  "scope": S()}, f"how much did i watch {words} and the cooking part of it")[1]
    TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(words),
                             "scope": S(only=["cooking"])})
    assert t.results["r1"]["meta"]["hidden"]["sensitive"] > 0 == t.results["r2"]["meta"]["hidden"]["sensitive"]
    sent = {"lead": f"In {words[3:]} you opened {t.results['r2']['sheet']['totals']['items']}[r2.totals.items] "
                    "cooking videos.", "points": []}
    not_sent = {"lead": f"In {words[3:]} you opened {t.results['r1']['sheet']['totals']['items']}[r1.totals.items] "
                        "videos.", "points": []}
    from mvp.brain import verify as V
    other = V.check_answer(not_sent, t.results, V.Turn.of(t), mode="values")
    assert other.private_line   # a form that was not sent, citing the result that hid private rows
    out, v = _answer(t, sent, also=[other])
    assert v.outcomes[0].kept and not out["private_line"]
    # a figure with no marker may be a count of any result: the line shows
    out2, v2 = _answer(t, {"lead": f"In {words[3:]} you opened 1 video.", "points": []})
    assert v2.outcomes[0].kept and out2["private_line"]


def _two_results(brain, first, message, **kw):
    """A turn of two results: `first` (a call of a result that hid no private row), then the items of a 2024 month
    that hid private rows, which no sentence below cites (`message` names the month where it says {words})."""
    from mvp.brain import tools as TL
    m, priv = _private_month()
    words = f"in {['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August'][int(m[5:]) - 1]} 2024"
    t = call(brain, *first, message.format(words=words), **kw)[1]
    TL.call(t, "items", {"limit": 5, "offset": 0, "order": "newest", "window": W(words), "scope": S()})
    assert t.results["r1"]["meta"]["hidden"]["sensitive"] == 0 and t.results["r2"]["meta"]["hidden"]["sensitive"] == \
        priv[m] > 0
    return t


def test_a_bare_figure_stands_only_on_the_results_that_hold_it(brain):
    """(repair: a figure written with no marker pooled every result of the turn, so the line went out when the only
    result that hid private rows held none of the sentence's figures)"""
    from mvp.brain import verify as V
    from mvp.tests.fakes.fake_brain import fake_learned
    t = _two_results(brain, ("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                           "window": W(preset="all"), "scope": S(only=["cooking"])}),
                     "how much cooking have i opened ever, and what did i open {words}")
    tot = t.results["r1"]["sheet"]["totals"]
    n, days = tot["items"], tot["days_active"]
    led = V.Ledger(t.results)
    # the figures are the cooking result's alone: the month's items (and what they hid) hold neither
    assert V._holders(led, [float(n)]) == V._holders(led, [float(days)]) == {"r1"}
    for lead in (f"In all your history you opened {n}[r1.totals.items] cooking videos, on {days} days.",
                 f"In all your history you opened {n} cooking videos.",
                 f"In all your history you opened {n}[r1.totals.items] cooking videos, on "
                 f"{days}[r1.totals.days_active] days."):
        out, v = _answer(t, {"lead": lead, "points": []})
        assert v.outcomes[0].kept and not out["private_line"], lead
    # a topic's row and a bare count only it holds: no line
    t2 = _two_results(brain, ("learned", {"topic": "calculus", "scope": S()}),
                      "what stuck from the maths lessons, and what did i open {words}", learned=fake_learned)
    k = t2.results["r1"]["sheet"]["on_topic"][0]["opened"]
    assert V._holders(V.Ledger(t2.results), [float(k)]) == {"r1"}
    out, v = _answer(t2, {"lead": f"You opened {k} items on Calculus lessons[r1.on_topic[0]].", "points": []})
    assert v.outcomes[0].kept and not out["private_line"]


def test_a_bare_figure_the_result_that_hid_private_rows_holds_shows_the_line(brain):
    from mvp.brain import verify as V
    t = _two_results(brain, ("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                           "window": W(preset="all"), "scope": S(only=["cooking"])}),
                     "how much cooking have i opened ever, and what did i open {words}")
    led = V.Ledger(t.results)
    n = t.results["r1"]["sheet"]["totals"]["items"]
    shown = len(t.results["r2"]["sheet"]["items"])
    assert "r2" in V._holders(led, [float(shown)])
    out, v = _answer(t, {"lead": f"In all your history you opened {n}[r1.totals.items] cooking videos; that month "
                                 f"shows {shown} video.", "points": []})
    assert v.outcomes[0].kept and out["private_line"]
    # a figure no single result holds, or a percent: every result of the turn is behind it
    assert V._holders(led, [987654.0]) == V._holders(led, [None]) == {"r1", "r2"}
    # the cited result that hid private rows: the line
    row = t.results["r2"]["sheet"]["items"][0]
    out, v = _answer(t, {"lead": f"That month you opened {row['title']}[r2.items[0]].", "points": []})
    assert v.outcomes[0].kept and out["private_line"]


def test_full_and_cells_build_the_line_as_before(brain):
    from mvp.brain import verify as V
    for mode in ("full", "cells"):
        assert not V.check_mode(mode).rule("private_behind")
    assert "private_behind" in V.VALUES.rules and V.VALUES_RULES_R32 == {"private_behind", "whole_title"}


# ================================================================ 4. a topic's name is cited on its row
def _learned(brain, message):
    from mvp.tests.fakes.fake_brain import fake_learned
    return call(brain, "learned", {"topic": "calculus", "scope": S()}, message, learned=fake_learned)


def test_a_topics_name_is_cited_on_its_own_row(brain):
    r, t = _learned(brain, "did i take anything in from the maths lessons")
    row = r["sheet"]["on_topic"]
    calc = [x for x in visible_rows() if x["theme"] == "ca"]
    n_open = sum(1 for x in calc if any(k == "watch" for k, _ in x["events"]))                          # recount
    assert row == [{"ref": "r1.on_topic[0]", "name": "Calculus lessons", "opened": n_open, "saved": 0}]
    for s in (f"Calculus lessons[r1.on_topic[0]] counts {n_open}[r1.on_topic[0].opened] videos you opened; you kept "
              "0[r1.on_topic[0].saved].",
              f"Calculus lessons[r1.on_topic[0]] holds {n_open}[r1.on_topic[0].opened] videos you opened."):
        assert _point(t, s).kept and _lead(t, s).kept, s


def test_a_topic_rows_false_twins_stay_refused_and_its_list_is_no_figure(brain):
    r, t = _learned(brain, "did i take anything in from the maths lessons")
    n = r["sheet"]["on_topic"][0]["opened"]
    assert not _point(t, f"Number puzzles[r1.on_topic[0]] counts {n}[r1.on_topic[0].opened] videos you opened.").kept
    assert _point(t, f"Calculus lessons[r1.on_topic[0]] counts {n + 1}[r1.on_topic[0].opened] videos you opened.").reasons \
        == ["wrong_value"]
    # the one-row list stands for no figure ("1") and takes no count marker, as the dict it was
    for s in ("You saved 1 calculus video.", "Calculus lessons[r1.on_topic[0]] is 1 of your topics."):
        assert _point(t, s).reasons == ["unfound_number"], s
    assert "bad_ref" in _point(t, "Calculus lessons[r1.on_topic[0]] is 1[r1.on_topic.count] topic.").reasons
