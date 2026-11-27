"""mvp31 (DESIGN 31.9): seams of values mode, each closed by a class of case (rules VALUES_RULES_R31, in the default).
Every rule here refuses more, or rewords a refusal; none lets through a sentence the mvp30 default refused.

1. Lengths (rule "length_unit"). A length is cited with its marker right after the figure and the unit after it
   ("25[r1.items[0].minutes] minutes"), the form the check binds. The unit word written between the figure and a
   minute cell's marker is refused with a reword that gives that form. A hedge of direction on a length is held
   strictly; a length is never time spent nor the bound of a comparison. A bare length stays refused, its reword in
   the same form.
2. Days (rule "days_unit"). "N days[cell]" on a cell of days is bound to it and checked; a day cell's figure is never
   a count of things.
3. Paths (rule "cite_hint", and the tools' texts). Every path a result's own texts name is in that result, and every
   one in its sheet is reached by a marker and verifies as written; meta is read, never cited. The reword for a
   bracket that is no marker names cells by path (a meta copy's twin in the sheet, a group's own cells), never by the
   value written before it, and only cells the turn holds.
4. Empty brackets (rule "paren_tidy"). A bracket that held only markers leaves no "()" in the sentence sent; every
   other bracket, a title's own included, stays as written.

Made-up library and made-up messages only; every expected value is read from the made-up rows or from the result
under test, never copied from a saved answer; no model call.
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.tests.test_brain_tools import (  # noqa: E402,F401
    NOW,
    brain,
    built,
    no_real_keys,
    person,
    visible_rows,
)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)

SC = {"exclude": [], "how": "opened", "length": "any", "only": [], "platforms": [], "weekday": None}
ALL = {"preset": "all", "same_as": None, "words": None}
MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
       "December"]


def W(words=None, preset=None):
    return {"words": words, "preset": preset, "same_as": None}


def _turn(e, message, calls, keep=None):
    from mvp.brain import tools as TL
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    t = TL.Turn(e["bot"], person(e), NOW, message=message, search=FakeEngine(), learned=fake_learned)
    for name, args in calls:
        got = TL.call(t, name, args)
        if keep is not None:
            keep.append(got)
    return t


def _check(t, text, mode=None, where="point", results=None):
    from mvp.brain import verify as V
    form = {"lead": text, "points": []} if where == "lead" else {"lead": "Here is what it holds.", "points": [text]}
    v = V.check_answer(form, results if results is not None else t.results, V.Turn.of(t), mode=mode or V.VALUES)
    o = [o for o in v.outcomes if o.where == where][0]
    return o, V.repair_message(V.Verdict(outcomes=v.outcomes, repair=True)) or ""


def _old():
    from mvp.brain import verify as V
    return V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30)


def _day(iso):
    y, m, d = (int(x) for x in str(iso)[:10].split("-"))
    return f"{d} {MON[m - 1]} {y}"


def _leaves(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _leaves(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _leaves(v, f"{p}[{i}]")
    else:
        yield p, o


def _bare(p):
    return re.sub(r"\[\d+\]", "", p)


def _minute_cells(t):
    from mvp.brain import verify as V
    return [(rid, p, v) for rid, env_ in t.results.items() for p, v in _leaves(env_.get("sheet") or {})
            if isinstance(v, (int, float)) and not isinstance(v, bool) and V._v_minute_key(p.rsplit(".", 1)[-1])]


# ================================================================ 1. lengths
def test_a_length_takes_its_marker_after_the_figure_and_the_unit_word_before_the_marker_is_reworded(brain):
    from mvp import insight as I
    from mvp.brain import verify as V
    assert V.VALUES_RULES_R31 <= V.VALUES.rules
    assert V.VALUES_RULES_R31 == {"length_unit", "days_unit", "cite_hint", "paren_tidy"}
    t = _turn(brain, "my longest videos and my usual week", [
        ("items", {"limit": 3, "offset": 0, "order": "longest", "window": W(preset="all"), "scope": SC}),
        ("breakdown", {"by": "none", "compare": "previous", "order": "most", "top": 5, "window": W("in October"),
                       "scope": SC})])
    # every numeric cell the tools emit whose key holds minutes, found by the kind test, never a length total
    cells = _minute_cells(t)
    keys = {p.rsplit(".", 1)[-1] for _r, p, _v in cells}
    assert {"minutes", "longest_minutes", "shortest_minutes", "long_median_min"} <= keys
    assert not keys & set(I.LENGTH_KEYS)
    lengths = {x["length"] / 60 for x in visible_rows() if x["length"]}
    for rid, p, v in cells:
        if p.endswith("minutes"):
            assert any(abs(n - v) < 0.06 for n in lengths), (p, v)                    # a length of the made-up rows
        fig = f"{v:g}"
        twin = f"That one runs {fig}[{rid}.{p}] minutes."
        for m_ in (V.VALUES, _old()):   # the form the check binds, kept as it was
            o, _r = _check(t, twin, m_)
            assert o.kept, (twin, o.reasons)
        if p.endswith("long_median_min"):
            o, _r = _check(t, f"That one runs {fig} minutes[{rid}.{p}].")
            assert o.kept   # the sheet's median read "N minutes[...]" before and still does
            continue
        for said in (f"{fig} minutes", f"{fig} min", f"about {fig} minutes"):
            o, rep = _check(t, f"That one runs {said}[{rid}.{p}].")
            assert o.reasons == ["wrong_measure"], (said, p, o.reasons)
            assert f"{fig}[{rid}.{p}] minutes" in rep, rep                     # the reword gives the bound form
            o, _r = _check(t, f"That one runs {said}[{rid}.{p}].", _old())
            # refused before as well; "N min[...]" was never bound before (its figure was found in any cell)
            assert not o.kept or " min[" in f"{said}["
    row = t.results["r1"]["sheet"]["items"][0]
    fig = f"{row['minutes']:g}"
    o, rep = _check(t, f"{row['title']}[r1.items[0]] is a {fig}-minute[r1.items[0].minutes] video.")
    assert o.reasons == ["wrong_measure"] and f"{fig}[r1.items[0].minutes] minutes" in rep
    o, _r = _check(t, f"{row['title']}[r1.items[0]] runs {fig}[r1.items[0].minutes] minutes.")
    assert o.kept and o.sent == f"{row['title']} runs {fig} minutes."
    longest = t.results["r1"]["sheet"]["lengths"]["longest_minutes"]
    o, _r = _check(t, f"Your longest video runs {longest + 1:g}[r1.lengths.longest_minutes] minutes.")
    assert o.reasons == ["wrong_value"]
    o, _r = _check(t, f"Your longest video runs {longest:g} videos[r1.lengths.longest_minutes].")
    assert o.reasons == ["wrong_measure"]   # a count noun before a minute cell's marker


def test_a_hedge_of_direction_on_a_length_is_held_strictly(brain):
    t = _turn(brain, "my longest videos", [
        ("items", {"limit": 3, "offset": 0, "order": "longest", "window": W(preset="all"), "scope": SC})])
    n = t.results["r1"]["sheet"]["lengths"]["longest_minutes"]
    for s in (f"Most of these run under {n:g}[r1.lengths.longest_minutes] minutes.",
              f"Some of these run over {n:g}[r1.lengths.longest_minutes] minutes.",
              f"The longest runs just over {n:g}[r1.lengths.longest_minutes] minutes."):
        o, _r = _check(t, s)
        assert o.reasons == ["wrong_value"], (s, o.reasons)
        o, _r = _check(t, s, _old())
        assert o.kept   # the leniency of before: a hedge allowed the figure itself
    for s in (f"The longest runs about {n:g}[r1.lengths.longest_minutes] minutes.",
              f"The longest runs just over {n - 1:g}[r1.lengths.longest_minutes] minutes.",
              f"The longest runs under {n + 1:g}[r1.lengths.longest_minutes] minutes."):
        o, _r = _check(t, s)
        assert o.kept, (s, o.reasons)


def test_a_length_is_never_time_spent_nor_a_bound(brain):
    from mvp.brain import verify as V
    t = _turn(brain, "my longest videos", [
        ("items", {"limit": 3, "offset": 0, "order": "longest", "window": W(preset="all"), "scope": SC})])
    row = t.results["r1"]["sheet"]["items"][0]
    fig, title = f"{row['minutes']:g}", row["title"]
    spent = [f"You watched {title}[r1.items[0]] for {fig} minutes[r1.items[0].minutes].",
             f"You watched {title}[r1.items[0]] for {fig}[r1.items[0].minutes] minutes.",
             f"You watched it for {fig} minutes[r1.items[0].minutes].",
             f"Last week you watched it for {fig}[r1.items[0].minutes] minutes.",
             f"You spent {fig} minutes[r1.lengths.longest_minutes] on art.",
             f"You sat through {fig}[r1.lengths.longest_minutes] minutes of drawing."]
    for s in spent:
        o, rep = _check(t, s)
        assert "watch_time" in o.reasons, (s, o.reasons)
        assert "never time they spent" in rep
    o, _r = _check(t, f"You opened 2 videos longer than {fig}[r1.items[0].minutes] minutes.")
    assert "length_bound" in o.reasons
    for s in (f"{title}[r1.items[0]] runs {fig}[r1.items[0].minutes] minutes.",
              f"The longest video you opened runs {fig}[r1.lengths.longest_minutes] minutes.",
              f"You opened {title}[r1.items[0]], which runs {fig}[r1.items[0].minutes] minutes."):
        o, _r = _check(t, s)
        assert o.kept, (s, o.reasons)
    assert sorted(V.VALUES_REFUSE_R31) == ["length_bound"] and V.VALUES_REFUSE_DEFAULT["length_bound"]


def test_a_bare_length_stays_refused_and_its_reword_gives_the_bound_form(brain):
    t = _turn(brain, "my longest videos", [
        ("items", {"limit": 3, "offset": 0, "order": "longest", "window": W(preset="all"), "scope": SC})])
    fig = f"{t.results['r1']['sheet']['lengths']['longest_minutes']:g}"
    o, rep = _check(t, f"Your longest video runs {fig} minutes.")
    assert o.reasons == ["unfound_number"]
    m = re.search(r"as (" + re.escape(fig) + r"\[(r1\.[^\]]+)\] minutes)", rep)
    assert m and m.group(2) == "r1.lengths.longest_minutes", rep
    assert "[i]" in rep or "items[" not in rep   # a row's cell is named by its pattern, never one row by its value
    o, _r = _check(t, f"Your longest video runs {m.group(1)}.")
    assert o.kept
    o, rep = _check(t, f"You opened {fig} drawing videos.")
    assert o.reasons == ["unfound_number"] and "length" not in rep
    o, rep = _check(t, f"You watched it for {fig} minutes.")
    assert o.reasons == ["unfound_number"] and "never time they spent" in rep


# ================================================================ 2. days
def test_days_are_bound_to_a_day_cell_and_a_day_cell_is_never_a_count_of_things(brain):
    t = _turn(brain, "what I opened this October against before", [
        ("breakdown", {"by": "none", "compare": "previous", "order": "most", "top": 5, "window": W("in October"),
                       "scope": SC})])
    sh = t.results["r1"]["sheet"]
    d, da = sh["window"]["days"], sh["totals"]["days_active"]
    o, _r = _check(t, f"October here covers {d} days[r1.window.days].")
    assert o.kept
    o, rep = _check(t, f"October here covers {d + 1} days[r1.window.days].")
    assert o.reasons == ["wrong_value"] and f"r1.window.days = {d}" in rep
    o, _r = _check(t, f"October here covers {d + 1} days[r1.window.days].", _old())
    assert o.kept   # before: the figure was found in any cell and never compared to the one cited
    for s in (f"You opened {d}[r1.window.days] videos in October.", f"You opened {d} videos[r1.window.days] in October.",
              f"You opened {da}[r1.totals.days_active] items."):
        o, rep = _check(t, s)
        assert o.reasons == ["wrong_measure"] and "number of days" in rep, (s, o.reasons)
    for s in (f"You were active on {da} days[r1.totals.days_active].", f"You were active on {da}[r1.totals.days_active] days.",
              f"October has {d}[r1.window.days] days."):
        o, _r = _check(t, s)
        assert o.kept, (s, o.reasons)
    # a hedged figure stays unbound, as before: nothing is kept now that the mvp30 default refused
    med = sh["totals"]["long_median_min"]
    for s in (f"October here covers about {d + 3} days[r1.window.days].", f"October here covers over {d - 2} days[r1.window.days].",
              f"October here covers nearly {d + 2} days[r1.window.days].", f"You were active on about {da + 40} days[r1.totals.days_active].",
              f"Long ones ran about {med - 1:g} min[r1.totals.long_median_min] at the median.",
              f"Long ones were about {med - 1:g}-minute[r1.totals.long_median_min] videos at the median."):
        o, _r = _check(t, s)
        if o.kept:
            assert _check(t, s, _old())[0].kept, s


# ================================================================ 3. the reword names cells by path
def _named(rep):
    return re.findall(r"\b(r\d+\.[A-Za-z_]+(?:\[\d+\])?(?:\.[A-Za-z_]+(?:\[\d+\])?)*)", rep)


def _is_cell(t, path):
    from mvp.brain import verify as V
    rid, rest = path.split(".", 1)
    r = t.results.get(rid)
    try:
        v = V._resolve((r or {}).get("sheet") or {}, rest)
    except (KeyError, IndexError, TypeError):
        return False
    return not isinstance(v, (dict, list)) and v is not None


def test_a_bracket_that_is_no_marker_gets_a_reword_that_names_cells_by_path_never_by_value(brain):
    from mvp.brain import verify as V
    t = _turn(brain, "everything I opened", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                                            "window": ALL, "scope": SC})])
    d = t.results["r1"]["meta"]["window_dates"]
    tot = t.results["r1"]["sheet"]["totals"]
    # a meta copy: never cited, in this mode or before; the reword names its twin in the sheet (same key, same value)
    for br, said, twin in (("[r1.window_dates.start]", _day(d["start"]), "r1.window.start"),
                           ("[r1.meta.window_dates.end]", _day(d["end"]), "r1.window.end"),
                           ("[r1.window_dates.days]", f"{d['days']:,} days", "r1.window.days")):
        s = f"Your history: {said}{br}."
        for m_ in (V.VALUES, _old()):
            o, _r = _check(t, s, m_)
            assert o.reasons == ["bad_ref"], (s, o.reasons)
        o, rep = _check(t, s)
        assert twin in rep and "meta" in rep, rep
        o, _r = _check(t, s.replace(br, f"[{twin}]"))
        assert o.kept, s
    # never by the value written: a figure some other cell holds is not pointed at
    o, rep = _check(t, f"You opened {tot['days_active']}[r1.meta] videos.")
    assert o.reasons[0] == "bad_ref" and "days_active" not in rep
    # a group with many cells of the kind written names none of them
    o, rep = _check(t, f"You opened {tot['items']}[r1.totals] videos.")
    assert o.reasons == ["bad_ref"] and not [p for p in _named(rep) if p.startswith("r1.totals.")], rep
    # a group with few: its own cells of the kind written, by path; a wrong value there is still refused
    t2 = _turn(brain, "anything in 2019", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                                          "window": W("2019"), "scope": SC})])
    hs = t2.results["r1"]["sheet"]["cannot_see"]["history_starts"]
    o, rep = _check(t2, f"Nothing: the record begins on {_day(hs)}[r1.cannot_see].")
    assert o.reasons == ["bad_ref"] and "r1.cannot_see.history_starts" in rep and "r1.cannot_see.asked" not in rep
    o, _r = _check(t2, f"Nothing: the record begins on {_day(hs)}[r1.cannot_see.history_starts].")
    assert o.kept
    o, _r = _check(t2, "Yes, there are videos from 2019[r1.cannot_see] in it.")
    assert not o.kept
    # every path any reword names is a cell of the turn; the private count is never named
    for tt, brs in ((t, ("[r1.meta]", "[r1.nothing_here]", "[r1.window]", "[r1.meta.hidden.sensitive]",
                         "[r1.hidden]", "[r9.totals.items]")),
                    (t2, ("[r1.meta]", "[r1.cannot_see]", "[r1.totals.items]"))):
        for br in brs:
            for said in ("12", "5 January 2021", "some"):
                o, rep = _check(tt, f"It holds {said}{br}.")
                assert "bad_ref" in o.reasons, (br, o.reasons)
                assert all(_is_cell(tt, p) for p in _named(rep) if p != br[1:-1]), (br, rep)
                assert "hidden" not in rep.replace(br[1:-1], "")
    # full and cells keep their own reword text; the mvp30 default its own
    for m_ in (V.FULL, V.CELLS):
        o, rep = _check(t2, f"Nothing: the record begins on {_day(hs)}[r1.meta].", m_)
        assert "bad_ref" in o.reasons and "cite one cell of" not in rep
    o, rep = _check(t2, f"Nothing: the record begins on {_day(hs)}[r1.meta].", _old())
    assert "a bracket that is not a marker of this turn's results" in rep


def test_a_meta_copy_held_by_two_sheet_cells_names_both_and_picks_neither(brain):
    t = _turn(brain, "this October against the month before", [
        ("breakdown", {"by": "none", "compare": "previous", "order": "most", "top": 5, "window": W("in October"),
                       "scope": SC})])
    meta, sh = t.results["r1"]["meta"], t.results["r1"]["sheet"]
    b = meta["window_dates_before"]["days"]
    holders = [p for p, v in _leaves(sh) if p.rsplit(".", 1)[-1] == "days" and "[" not in p and v == b]
    o, rep = _check(t, f"The month before covers {b} days[r1.window_dates_before.days].")
    assert o.reasons == ["bad_ref"]
    assert all(f"r1.{p}" in rep for p in holders), (holders, rep)


# ================================================================ 3b. every path the texts name, per result
_DOT = re.compile(r"(?<![\w.\[/])(?:r\d+\.)?([a-z_]+(?:\[\d+\])?(?:\.[a-z_]+(?:\[\d+\])?)+)(?![\w(])")
_TICK = re.compile(r"`([a-z_][a-z_0-9]*(?:\.[a-z_]+)*)`")
_SNAKE = re.compile(r"(?<![\w.\[`/'-])([a-z]+(?:_[a-z]+)+)(?![\w(\[`'])")
PROSE = ("notes", "note", "error", "next", "holds", "holds_not")

# the battery: one call of each read tool and of each shape a note speaks of, and calls that fail (made-up messages)
BATTERY = [
    ("my themes in October", [("breakdown", {"by": "theme", "compare": "previous", "order": "most", "top": 25,
                                             "window": W("in October"), "scope": SC})]),
    ("my channels ever", [("breakdown", {"by": "channel", "compare": "none", "order": "most", "top": 25,
                                         "window": ALL, "scope": SC})]),
    ("areas lately", [("breakdown", {"by": "area", "compare": "previous", "order": "most", "top": 5,
                                     "window": W(preset="lately"), "scope": SC})]),
    ("everything in October", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                              "window": W("in October"), "scope": SC})]),
    ("all I did in October", [("breakdown", {"by": "channel", "compare": "none", "order": "most", "top": 5,
                                             "window": W("in October"), "scope": dict(SC, how="any")})]),
    ("instagram themes", [("breakdown", {"by": "theme", "compare": "none", "order": "most", "top": 5,
                                         "window": ALL, "scope": dict(SC, platforms=["instagram"])})]),
    ("anything in 2019", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                         "window": W("2019"), "scope": SC})]),
    ("instagram in September 2026", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                                    "window": W("September 2026"),
                                                    "scope": dict(SC, platforms=["instagram"])})]),
    ("instagram items in September 2026", [("items", {"limit": 5, "offset": 0, "order": "newest",
                                                      "window": W("September 2026"),
                                                      "scope": dict(SC, platforms=["instagram"])})]),
    ("months this year", [("timeline", {"unit": "month", "window": W("this year"), "scope": SC})]),
    ("every month", [("timeline", {"unit": "month", "window": ALL, "scope": SC})]),
    ("by year", [("timeline", {"unit": "year", "window": ALL, "scope": SC})]),
    ("what changed in October", [("changes", {"against": "previous", "level": "theme", "window": W("in October"),
                                              "scope": SC})]),
    ("new channels in October", [("changes", {"against": "previous", "level": "channel", "window": W("in October"),
                                              "scope": SC})]),
    ("October 2026 against September 2026", [("compare", {"a": W("October 2026"), "b": W("September 2026"),
                                                          "by": "theme", "scope": SC})]),
    ("my first gaming video", [("first_last", {"which": "first", "subject": "Gaming Daily"})]),
    ("my first knitting video", [("first_last", {"which": "first", "subject": "knitting"})]),
    ("knitting ever", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": ALL,
                                      "scope": dict(SC, only=["knitting"])})]),
    ("my longest videos", [("items", {"limit": 5, "offset": 0, "order": "longest", "window": ALL, "scope": SC})]),
    ("gaming I opened most", [("items", {"limit": 5, "offset": 0, "order": "most_opened", "window": ALL,
                                         "scope": dict(SC, only=["Gaming Daily"])})]),
    ("what I saved", [("items", {"limit": 5, "offset": 0, "order": "newest", "window": ALL,
                                 "scope": dict(SC, how="saved")})]),
    ("on 20 October 2026", [("items", {"limit": 5, "offset": 0, "order": "newest", "window": W("on 20 October 2026"),
                                       "scope": SC})]),
    ("find these", [("find", {"names": ["calculus", "Gaming Daily", "Bread days", "knitting"], "kinds": []})]),
    ("my sourdough saves", [("search", {"query": "sourdough", "how": "saved", "limit": 5, "window": ALL})]),
    ("notes from my sourdough saves", [("learned", {"topic": "sourdough", "scope": SC})]),
    ("notes from a channel I saved", [("learned", {"topic": "Bread days", "scope": SC})]),
    ("two channels in October", [("breakdown", {"by": "channel", "compare": "previous", "order": "most", "top": 5,
                                                "window": W("in October"),
                                                "scope": dict(SC, only=["Gaming Daily", "Clip Factory"])})]),
    ("castle videos", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": ALL,
                                      "scope": dict(SC, only=["castle"])})]),
    ("gaming channels", [("breakdown", {"by": "channel", "compare": "none", "order": "most", "top": 5, "window": ALL,
                                        "scope": dict(SC, only=["gaming"])})]),
    ("what areas changed in October", [("changes", {"against": "previous", "level": "area", "window": W("in October"),
                                                    "scope": SC})]),
    ("how my areas moved over the years", [("changes", {"against": "previous", "level": "area", "window": ALL,
                                                        "scope": SC})]),
    ("what stopped in 2024", [("changes", {"against": "previous", "level": "channel", "window": W("in 2024"),
                                           "scope": SC})]),
    ("what about early November", [("breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                                  "window": W("early November"), "scope": SC})]),
    ("a call with a wrong argument", [("breakdown", {"by": "weekday", "compare": "none", "order": "most", "top": 5,
                                                     "window": ALL, "scope": SC}),
                                      ("items", {"limit": 500, "order": "sideways", "window": ALL, "scope": SC})]),
]
# named words that are no cell, each by its reason
FLAGS = {"title_clipped": "a flag: code reads it and says the clip is the result's; no sentence writes true or false"}
PRIVATE = {"meta.hidden.sensitive": "the count of private items left out: code writes the private line, never a "
                                    "sentence"}


def _sentence(key, v, mpath):
    """A sentence that says the value as a person writes it, the marker in its bound form, or None for a flag."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        return f"It holds {_day(v) if re.match(r'^\d{4}-\d\d-\d\d', v) else v}[{mpath}]."
    if key.endswith("share") or key in ("faded_from", "faded_to", "grew_from", "grew_to"):
        return f"It holds {round(v * 100)}%[{mpath}]."
    if key in ("change_pts", "change_vs_previous"):
        pts = v * 100 if abs(v) <= 1 and key == "change_vs_previous" else v
        return f"It holds {'up' if pts >= 0 else 'down'} {abs(round(pts))} points[{mpath}]."
    if key == "hour":
        return f"It holds {int(v) % 12 or 12}{'am' if int(v) < 12 else 'pm'}[{mpath}]."
    if key == "minutes" or key.endswith("_minutes") or key.endswith("_min"):
        return f"It holds {v:g}[{mpath}] minutes."
    return f"It holds {v:g}[{mpath}]." if isinstance(v, float) else f"It holds {v}[{mpath}]."


def _args():
    """Every dotted path and every allowed word of the read tools' arguments ("window.same_as", "most_opened"): named
    in the texts as what to pass, never a cell."""
    from pydantic import BaseModel
    from mvp.brain import tools as TL
    out = set()

    def walk(model, prefix):
        for name, f in model.model_fields.items():
            p = f"{prefix}.{name}" if prefix else name
            out.update({p, name})
            ann = f.annotation
            for a in (ann, *getattr(ann, "__args__", ())):
                if isinstance(a, type) and issubclass(a, BaseModel):
                    walk(a, p)
                for lit in getattr(a, "__args__", ()) if getattr(a, "__origin__", None) is not None else ():
                    if isinstance(lit, str):
                        out.add(lit)
            for lit in getattr(ann, "__args__", ()):
                if isinstance(lit, str):
                    out.add(lit)
    from mvp.brain import loop as LP
    from mvp.brain import verify as V
    models = [t.params for t in TL.REGISTRY.values()] + [V.AnswerForm]   # the read tools' and give_answer's fields
    for m in models:
        if isinstance(m, type) and issubclass(m, BaseModel):
            walk(m, "")
            out.update(re.findall(r'"enum":\s*\[([^\]]*)\]', json.dumps(m.model_json_schema())))
    out.update({LP.GIVE_ANSWER, *re.findall(r"[a-z_]+", V.CALC.pattern.split("(?P<op>")[1].split(")")[0])})
    words = set()
    for x in out:
        words.update(re.findall(r'"([a-z_]+)"', x) if '"' in x else [x])
    return words


def _prose(o, out, key=None):
    if isinstance(o, dict):
        for k, v in o.items():
            _prose(v, out, k)
    elif isinstance(o, list):
        for v in o:
            _prose(v, out, key)
    elif isinstance(o, str) and key in PROSE:
        out.append(o)


def _names(text):
    out = set()
    for rx in (_DOT, _TICK, _SNAKE):
        out.update(m.group(1) for m in rx.finditer(text))
    return out


def _nodes(o, p=""):
    """Every path of a tree with its value, the lists and groups as well as the cells."""
    if p:
        yield p, o
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _nodes(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _nodes(v, f"{p}[{i}]")


def _hits(tree, nb):
    return [(p, v) for p, v in _nodes(tree) if _bare(p) == nb or _bare(p).endswith("." + nb) or
            _bare(p).startswith(nb + ".") or ("." + nb + ".") in _bare(p)]


def test_every_path_a_results_own_texts_name_is_in_that_result_and_its_cells_verify_as_written(brain, monkeypatch):
    """The texts are read as they are emitted, result by result (notes, errors, next steps), plus the tools'
    descriptions and the two new prompt files; a name is matched against the result whose text names it."""
    from mvp import history as Hm
    from mvp.brain import tools as TL
    from mvp.brain import verify as V
    runs = []
    for m, calls in BATTERY:
        got = []
        runs.append((_turn(brain, m, calls, keep=got), got))
    monkeypatch.setattr(TL, "item_title", lambda it: Hm._title(it))   # rows that share a title
    got = []
    runs.append((_turn(brain, "my gaming clips", [("items", {"limit": 5, "offset": 0, "order": "newest", "window": ALL,
                                                             "scope": dict(SC, only=["gaming"])})], keep=got), got))
    args = _args()
    # the words of an envelope itself (its keys, an error's code), named in the texts as what a result carries
    # (the keys every result or every failed call carries; a key only a name with no match carries is its data)
    args |= {k for _t, envs in runs for e in envs if e.get("sheet") or e.get("is_error") for k in e}
    args |= {e["error"] for _t, envs in runs for e in envs if re.fullmatch(r"[a-z_]+", str(e.get("error")))}
    every = {p for t, _g in runs for env_ in t.results.values() for part in ("sheet", "meta")
             for p, _v in _nodes(env_.get(part) or {})}
    keys = {seg for p in every for seg in re.split(r"[.\[\]]+", _bare(p)) if seg}
    absent, unreached, walked = [], [], set()
    for t, envs in runs:
        for env_ in envs:
            texts = []
            _prose(env_, texts)
            res = t.results.get(env_.get("rid")) if env_.get("rid") else None
            sheet = (res or {}).get("sheet") or {}
            meta = env_.get("meta") or {}
            for text in texts:
                if re.fullmatch(r"[a-z_]+", text):
                    continue   # a code (an error's status), no prose
                for name in _names(text):
                    nb = _bare(name)
                    if name in PRIVATE or nb in FLAGS:
                        continue
                    if nb.startswith("meta."):
                        if not _hits(meta, nb[5:]):
                            absent.append((env_.get("tool"), name, text[:90]))
                        continue
                    hits = _hits(sheet, nb)
                    if hits:
                        ok = False
                        for p, v in hits:
                            if isinstance(v, dict):
                                continue   # a group: its cells are hits of their own
                            if isinstance(v, list):
                                s = f"It holds {len(v)}[{env_['rid']}.{p}.count]."
                            else:
                                s = _sentence(re.split(r"[.\[\]]+", _bare(p))[-1], v, f"{env_['rid']}.{p}")
                            if s is None:
                                ok = True
                                break
                            o, _r = _check(t, s)
                            if o.kept:
                                ok = True
                                break
                        (walked.add(nb) if ok else unreached.append((env_.get("tool"), name, hits[0][0])))
                    elif _hits(meta, nb) or nb in args or nb.split(".")[-1] in args:
                        continue   # meta, read and never cited; or an argument the text tells them to pass
                    else:
                        absent.append((env_.get("tool"), name, text[:90]))
    assert not absent, "\n".join(map(str, sorted(set(absent))))
    assert not unreached, "\n".join(map(str, sorted(set(unreached))))
    assert len(walked) >= 40, sorted(walked)
    assert {"cannot_see", "cannot_see.outside_scope_items", "first_watched"} <= walked, sorted(walked)
    # the tools' descriptions and the two new prompt files name only cells some result holds, or arguments
    glob = [t.description for t in TL.REGISTRY.values()]
    glob += [open(os.path.join(MVP, "prompts", p)).read() for p in ("brain_v3d.md", "brain_v4d.md")]
    loose = sorted({_bare(n) for g in glob for n in _names(g) if _bare(n).split(".")[0] not in keys and
                    _bare(n).removeprefix("meta.").split(".")[0] not in keys and _bare(n) not in args and
                    _bare(n).split(".")[-1] not in args and _bare(n) not in FLAGS and _bare(n) != "meta"})
    assert not loose, " ".join(loose)
    # and a name of theirs that some result's sheet holds is reached by a marker there, as written
    gnames = {_bare(n) for g in glob for n in _names(g)} - set(FLAGS) - {_bare(p) for p in PRIVATE}
    unreached_g, walked_g = [], set()
    for nb in sorted(gnames):
        if nb.startswith("meta.") or nb in args:
            continue
        tried = False
        for t, envs in runs:
            for env_ in envs:
                res = t.results.get(env_.get("rid")) if env_.get("rid") else None
                for p, v in _hits((res or {}).get("sheet") or {}, nb):
                    if isinstance(v, dict):
                        continue
                    tried = True
                    sen = f"It holds {len(v)}[{env_['rid']}.{p}.count]." if isinstance(v, list) else \
                        _sentence(re.split(r"[.\[\]]+", _bare(p))[-1], v, f"{env_['rid']}.{p}")
                    if sen is None or _check(t, sen)[0].kept:
                        walked_g.add(nb)
                        break
                else:
                    continue
                break
            else:
                continue
            break
        else:
            if tried:
                unreached_g.append(nb)
    assert not unreached_g, unreached_g
    assert {"areas.previous_share", "change_pts", "totals.items"} <= walked_g, sorted(walked_g)
    # the private count stays out of reach on purpose
    t = runs[1][0]
    n = t.results["r1"]["meta"]["hidden"]["sensitive"]
    o, _r = _check(t, f"It holds {n}[r1.meta.hidden.sensitive].")
    assert o.reasons == ["bad_ref"]
    # verify's own reword texts, turn by turn: every path they name is a cell of that turn
    for t, _envs in runs:
        rid = next(iter(t.results), "r1")
        for br in (f"[{rid}.meta]", f"[{rid}.nothing_here]", f"[{rid}.window_dates]", f"[{rid}.totals.items]"):
            for said in ("12", "5 January 2021"):
                o, rep = _check(t, f"It holds {said}{br}.")
                bad = [p for p in _named(rep) if not _is_cell(t, p) and p != br[1:-1]]
                assert not bad, (t.message, br, rep)
    assert V.VALUES_RULES_R31 <= V.VALUES.rules


def test_a_name_that_matched_nothing_names_no_cell_it_does_not_have(brain):
    got = []
    t = _turn(brain, "my first knitting video", [("first_last", {"which": "first", "subject": "knitting"})], keep=got)
    env_ = got[0]
    assert env_.get("error") == "no_match" and "items_with_words" in env_ and not env_.get("sheet")
    texts = []
    _prose(env_, texts)
    assert texts and not any("items_with_words" in x or "searched" in x for x in texts), texts
    n = env_["items_with_words"]
    o, rep = _check(t, f"{n} of your items[{env_['rid']}.items_with_words] hold that word.")
    assert o.reasons[0] == "bad_ref" and "not a result with numbers" in rep
    o, _r = _check(t, "No channel or theme goes by that name.")
    assert o.kept


# ================================================================ 4. a marker alone in brackets
def test_only_a_bracket_that_held_markers_alone_is_dropped_from_the_sentence_sent(brain):
    from mvp.brain import answer as AN
    from mvp.brain import verify as V
    t = _turn(brain, "my videos by year and my newest", [
        ("timeline", {"unit": "year", "window": ALL, "scope": SC}),
        ("items", {"limit": 3, "offset": 0, "order": "newest", "window": ALL, "scope": SC})])
    periods = t.results["r1"]["sheet"]["periods"]
    k = max(range(len(periods)), key=lambda n: periods[n]["items"])
    lab, n = periods[k]["label"], periods[k]["items"]
    for s, want in ((f"The busiest year was {lab} ([r1.periods[{k}]]).", f"The busiest year was {lab}."),
                    (f"The busiest year was {lab} ( [r1.periods[{k}]] ), by far.", f"The busiest year was {lab}, by far."),
                    (f"The busiest year was {lab} (([r1.periods[{k}]])).", f"The busiest year was {lab}."),
                    (f"The busiest year was {lab} ([r1.periods[{k}]]; [r1.periods[{k}]]).", f"The busiest year was {lab}."),
                    (f"In {lab} ([r1.periods[{k}]]) you opened {n}[r1.periods[{k}].items] videos.",
                     f"In {lab} you opened {n} videos.")):
        for where in ("point", "lead"):
            o, _r = _check(t, s, where=where)
            assert o.kept and o.sent == want, (s, o.sent)
        o, _r = _check(t, s, _old())
        assert o.kept and "(" in o.sent   # last round's mode sent the empty brackets
    # brackets the model wrote with words, or empty with no marker, stay as written, as before
    for s in (f"The busiest year was {lab} (see [r1.periods[{k}]]).",
              f"The busiest year was {lab} [r1.periods[{k}]] (the () is mine).",
              f"The busiest year was {lab} [r1.periods[{k}]] (, )."):
        o, _r = _check(t, s)
        o2, _r = _check(t, s, _old())
        assert o.kept and o.sent == o2.sent, (s, o.sent, o2.sent)
    # a title's own brackets are data: never touched
    res = copy.deepcopy(t.results)
    row = res["r2"]["sheet"]["items"][0]
    row["title"] = "Tiny loops() explained"   # a made-up title holding "()"
    s = f"You opened Tiny loops() explained[r2.items[0]] on {_day(row['when'])}[r2.items[0].when]."
    o, _r = _check(t, s, results=res)
    assert o.kept and o.sent == f"You opened Tiny loops() explained on {_day(row['when'])}.", o.sent
    form = {"lead": f"The busiest year was {lab} ([r1.periods[{k}]]).", "points": []}
    v = V.check_answer(form, t.results, V.Turn.of(t), mode=V.VALUES)
    assert "()" not in AN.build(V.Ledger(t.results), v, form=form, mode="values")["text"]
