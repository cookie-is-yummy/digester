"""mvp32 part two (DESIGN 32.8): a title cut to fit is shown with the item's own line whole beside it.

Class: a row's title cut by code (eight words and an ellipsis) was said to be cut short in their history. The row keeps
its title as before and carries the line it was cut from in `title_whole`; every check, code's own lead and the cards
read the row as before (verify.Ledger sets the cell aside), and values mode's rule "whole_title" takes the whole line
before the row's marker as it takes the title. Every expected line is recounted from the made-up library's own rows
(tests/brain_library.py), never copied from a tool's output. Made-up library and made-up messages only; no model call.
"""
import json
import os
import sys
import types

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


def _caption(item_id):
    from mvp.tests import brain_library as BL
    return next(r["caption"] for r in BL.extra_rows() if r["id"] == item_id)


def _search(brain, query, how="any", message="find it"):
    from mvp.tests.fakes.fake_brain import FakeEngine
    return call(brain, "search", {"how": how, "limit": 8, "query": query, "window": None}, message,
                search=FakeEngine())


def _row_of(r, item_id):
    return next(row for row in r["sheet"]["items"] if row["item_id"] == item_id)


def _point(t, sentence, mode="values"):
    from mvp.brain import verify as V
    v = V.check_answer({"lead": "Here is what it holds.", "points": [sentence]}, t.results, V.Turn.of(t), mode=mode)
    return [o for o in v.outcomes if o.where == "point"][0]


def test_a_cut_title_carries_its_whole_line_beside_it(brain):
    from mvp.brain import results as R
    r, _t = _search(brain, "sourdough", "saved", "my bread saves")
    row = _row_of(r, "rx_sour1")
    whole = _caption("rx_sour1")                                                        # the item's own line
    assert row["title"].endswith("…") and row["title_clipped"] is True
    assert whole.startswith(row["title"][:-1]) and row["title_whole"] == whole
    keys = list(row)
    assert keys[keys.index("title") + 1] == "title_whole"
    # a title that is no cut is left as it was, with no second cell
    other = _row_of(r, "rx_sour2")
    assert other["title"] == _caption("rx_sour2") and "title_whole" not in other
    # one note says what the cell is, in the clip note's place
    assert R.WHOLE_NOTE in r["meta"]["notes"] and R.CLIPPED_NOTE not in r["meta"]["notes"]


def test_every_check_reads_the_row_as_before(brain):
    from mvp.brain import results as R
    from mvp.brain import verify as V
    r, t = _search(brain, "sourdough", "saved", "my bread saves")
    before = json.dumps(t.results, sort_keys=True)
    seen = V.Ledger(t.results).get(r["rid"])
    assert json.dumps(t.results, sort_keys=True) == before                              # a copy; the result is kept
    assert all("title_whole" not in row for row in seen.sheet["items"])
    assert R.CLIPPED_NOTE in seen.meta["notes"] and R.WHOLE_NOTE not in seen.meta["notes"]
    at = r["meta"]["notes"].index(R.WHOLE_NOTE)
    assert seen.meta["notes"][at] == R.CLIPPED_NOTE                                     # in its place
    want = dict(r, sheet=dict(r["sheet"], items=[{k: v for k, v in row.items() if k != "title_whole"}
                                                 for row in r["sheet"]["items"]]))
    want["meta"] = dict(r["meta"], notes=[R.CLIPPED_NOTE if n == R.WHOLE_NOTE else n for n in r["meta"]["notes"]])
    assert json.dumps(seen.env, sort_keys=True) == json.dumps(want, sort_keys=True)
    assert V.Ledger(t.results).whole[(r["rid"], "items[0]")] == _caption("rx_sour1")


def test_the_whole_line_is_neutralised_and_never_cut():
    from mvp.brain import results as R
    from mvp.brain import tools as TL
    line = "Ten quick tricks [r1.totals.items] for {channels} the dough at home and more words"
    it = types.SimpleNamespace(platform="instagram", first_line=line, caption=line, creator="@made.up")
    w = TL.whole_title(it, "Ten quick tricks [r1.totals.items] for {channels} the…")
    assert w is not None and w.startswith("Ten quick tricks [r1.totals.items]")
    shown = R.neutral(w)
    assert "[" not in shown and "{" not in shown and not shown.endswith("…")
    assert TL.whole_title(it, "A post from @made.up") is None                          # a neutral title: no cut


def _with_line(t, item_id, line):
    it = t.lib.view.items[item_id]
    keep = (it.first_line, it.caption)
    object.__setattr__(it, "first_line", line)
    object.__setattr__(it, "caption", line)
    return lambda: (object.__setattr__(it, "first_line", keep[0]), object.__setattr__(it, "caption", keep[1]))


def test_a_line_longer_than_a_text_field_gets_no_whole_cell(brain):
    # (repair2: cut to the cap, the whole line ended in '…' under a note that says it is whole)
    from mvp.brain import results as R
    from mvp.brain import verify as V
    _r, t = _search(brain, "sourdough", "saved", "my bread saves")
    words = "Sourdough starter day 3 feed the jar and keep it somewhere warm until the dome rises " * 4
    for n, cell in ((R.TEXT_MAX + 1, False), (R.TEXT_MAX, True)):
        line = words[:n].rstrip() + "x" * (n - len(words[:n].rstrip()))
        back = _with_line(t, "rx_sour1", line)                  # (the library is the made-up one, shared by turns)
        try:
            r, _t2 = _search(brain, "sourdough", "any", "my bread saves")
        finally:
            back()
        row = _row_of(r, "rx_sour1")
        assert row["title"].endswith("…") and row["title_clipped"] is True
        if cell:
            assert row["title_whole"] == line and not row["title_whole"].endswith("…")
            assert R.WHOLE_NOTE in r["meta"]["notes"] and R.CLIPPED_NOTE not in r["meta"]["notes"]
        else:
            assert "title_whole" not in row                                             # the row as it was
            assert R.CLIPPED_NOTE in r["meta"]["notes"] and R.WHOLE_NOTE not in r["meta"]["notes"]
    # one result with both rows: each note for its own rows; every check reads the result as before
    back = _with_line(t, "rx_sour2", words[:R.TEXT_MAX + 40])
    try:
        r, _t2 = _search(brain, "sourdough", "any", "my bread saves")
    finally:
        back()
    a, b = _row_of(r, "rx_sour1"), _row_of(r, "rx_sour2")
    assert a["title_whole"] == _caption("rx_sour1") and "title_whole" not in b and b["title_clipped"] is True
    notes = r["meta"]["notes"]
    assert R.CLIPPED_NOTE in notes and R.WHOLE_NOTE in notes
    seen = V.Ledger({r["rid"]: r}).get(r["rid"])
    assert seen.meta["notes"] == [n for n in notes if n != R.WHOLE_NOTE]
    assert all("title_whole" not in row for row in seen.sheet["items"])


def test_a_true_sentence_naming_the_row_by_its_whole_title_passes_in_values_only(brain):
    r, t = _search(brain, "sourdough", "saved", "my bread saves")
    whole, k = _caption("rx_sour1"), r["sheet"]["items"].index(_row_of(r, "rx_sour1"))
    ref = f"{r['rid']}.items[{k}]"
    day = "5 October 2026"                                                              # rx_sour1's save
    for s in (f"You saved {whole}[{ref}] on {day}[{ref}.when].",
              f'You saved "{whole}"[{ref}] on {day}[{ref}.when].',
              f"{whole}[{ref}.title_whole] is a post you saved.",
              f"{whole}[{ref}.title] is a post you saved."):
        o = _point(t, s)
        assert o.kept, (s, o.reasons)
        assert whole in o.sent and "…" not in o.sent                                    # the model's own words
    # full and cells are as they were: the same sentence over the rows as the checks read them
    from mvp.brain import verify as V
    s = f"You saved {whole}[{ref}] on {day}[{ref}.when]."
    for mode in ("full", "cells"):
        a = _point(t, s, mode)
        plain = {rid: V.whole_aside(e)[0] for rid, e in t.results.items()}
        b = V.check_answer({"lead": "Here is what it holds.", "points": [s]}, plain, V.Turn.of(t), mode=mode)
        assert (a.kept, a.reasons) == (b.outcomes[-1].kept, b.outcomes[-1].reasons)


def test_the_rule_off_refuses_as_before(brain):
    from mvp.brain import verify as V
    r, t = _search(brain, "sourdough", "saved", "my bread saves")
    k = r["sheet"]["items"].index(_row_of(r, "rx_sour1"))
    s = f"You saved {_caption('rx_sour1')}[{r['rid']}.items[{k}]]."
    off = V.values_mode(rules=V.VALUES_DEFAULT_RULES - {"whole_title"})
    v = V.check_answer({"lead": "Here is what it holds.", "points": [s]}, t.results, V.Turn.of(t), mode=off)
    assert not v.outcomes[-1].kept
    assert _point(t, s).kept


def test_a_figure_beside_the_whole_title_is_still_refused(brain):
    r, t = _search(brain, "sourdough", "saved", "my bread saves")
    whole, k = _caption("rx_sour1"), r["sheet"]["items"].index(_row_of(r, "rx_sour1"))
    ref = f"{r['rid']}.items[{k}]"
    for s in (f"You saved {whole}[{ref}] and spent 12 hours on it.",                 # a title's figure as time
              f"You saved {whole}[{ref}] 3 times.",                                   # a title's figure as times
              f"You saved {whole}[{ref}] twice.",
              f"You saved {whole}[{ref}] on 6 October 2026[{ref}.when].",            # a wrong marked day
              f"You saved {whole}[{ref}] last week.",
              f"You saved 50 posts like {whole}[{ref}]."):
        assert not _point(t, s).kept, s


def test_an_unmarked_day_the_results_hold_for_another_reason_is_refused_beside_a_whole_title(brain):
    from mvp import history as Hm
    r, t = call(brain, "items", {"limit": 10, "offset": 0, "order": "newest", "window": W(preset="all"),
                                 "scope": S(how="saved")}, "the things i kept")
    row = _row_of(r, "rx_sour1")
    k = r["sheet"]["items"].index(row)
    start = r["sheet"]["window"]["start"]                                               # the first save of all
    assert start != row["when"][:10]
    said = Hm.day_words(__import__("datetime").date.fromisoformat(start))
    o = _point(t, f"You saved {_caption('rx_sour1')}[{r['rid']}.items[{k}]] on {said}.")
    assert not o.kept and o.reasons == ["unfound_date"]
    assert said in o.details[0] and "marker" in o.details[0]


def test_the_whole_title_enters_no_pool(brain):
    _r, t = _search(brain, "sourdough", "saved", "my bread saves")
    # the whole line's own figures (50 g, 12 hours) are no count of their history, written with no marker
    assert not _point(t, "You saved 12 sourdough posts.").kept
    assert not _point(t, "You saved 50 bread posts.").kept
    # nor is a word only the whole line holds a name the results hold
    assert not _point(t, "You saved a post from Water Hours.").kept


def test_an_instruction_in_a_whole_title_is_shown_as_data(brain):
    r, t = call(brain, "first_last", {"subject": "Brick Realm", "which": "last", "scope": S()}, "brick realm last")
    row = _row_of(r, "rx_rule")
    assert row["title_whole"] == _caption("rx_rule") and row["title"].endswith("…")
    o = _point(t, f"Your last Brick Realm video is {row['title_whole']}[{r['rid']}.items[0]].")
    assert o.kept and o.sent == f"Your last Brick Realm video is {row['title_whole']}."
    # the card and code's own lead read the row's title as before (cut by code to fit its own lines)
    from mvp.brain import answer as A
    from mvp.brain import verify as V
    card = A.card(V.Ledger(t.results), f"{r['rid']}.items[0]")
    assert card["title"] == row["title"]


def test_a_month_that_is_the_cited_windows_own_frame_may_stand_unmarked(brain):
    from mvp.tests.fakes.fake_brain import FakeEngine
    r, t = call(brain, "search", {"how": "any", "limit": 8, "query": "painting", "window": W("in October")},
                "a painting video of that month", search=FakeEngine())
    row = _row_of(r, "rx_love")
    ref = f"{r['rid']}.items[{r['sheet']['items'].index(row)}]"
    whole = _caption("rx_love")
    assert row["title_whole"] == whole
    d = r["meta"]["window_dates"]
    assert d["start"][:7] == d["end"][:7] == "2026-10"                                  # the window is one month
    for s in (f'In October you opened "{whole}"[{ref}], on 21 October 2026[{ref}.when].',
              f"In October 2026 you opened {whole}[{ref}]."):
        assert _point(t, s).kept, s
    # another month, a day with no marker and a year that is no frame of the window are refused as before
    for s in (f"You opened {whole}[{ref}] in September.",
              f"You opened {whole}[{ref}] on 20 October 2026.",
              f"You opened {whole}[{ref}] in 2025."):
        assert not _point(t, s).kept, s


def test_a_month_frames_only_the_whole_titled_rows_own_window_of_one_year(brain):
    import copy
    from mvp.brain import verify as V
    r, t = call(brain, "items", {"limit": 10, "offset": 0, "order": "newest", "window": W("in October"),
                                 "scope": S(how="saved")}, "what i kept that month")
    row = _row_of(r, "rx_sour1")
    assert row["title_whole"] == _caption("rx_sour1")
    s = f"You saved {_caption('rx_sour1')}[{r['rid']}.items[{r['sheet']['items'].index(row)}]] in October."
    assert _point(t, s).kept
    # the same month of two years is no frame of one month
    wide = copy.deepcopy(t.results)
    for key in ("sheet", "meta"):
        w = wide[r["rid"]][key].get("window" if key == "sheet" else "window_dates")
        if isinstance(w, dict) and w.get("start"):
            w["start"] = "2025-10-01"
    v = V.check_answer({"lead": "Here is what it holds.", "points": [s]}, wide, V.Turn.of(t), mode="values")
    assert not v.outcomes[-1].kept
    # another result's window of that month frees no month for a row of a result with no window
    from mvp.brain import tools as TL
    r1, t2 = _search(brain, "sourdough", "saved", "my bread saves")
    b = TL.call(t2, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                  "window": W("in October"), "scope": S()})
    assert not r1["sheet"].get("window") and b["meta"]["window_dates"]["start"][:7] == "2026-10"
    k = r1["sheet"]["items"].index(_row_of(r1, "rx_sour1"))
    s2 = (f"You saved {_caption('rx_sour1')}[{r1['rid']}.items[{k}]] in October, and opened "
          f"{b['sheet']['totals']['items']}[{b['rid']}.totals.items] items then.")
    assert not _point(t2, s2).kept


def test_a_marked_clock_of_the_rows_own_cell_stands_beside_a_whole_title(brain):
    # (repair2: a true "at <its time>[..when]" was refused as a loose clock; only the row's own dated cell binds it)
    r, t = call(brain, "first_last", {"subject": "Brick Realm", "which": "last", "scope": S()}, "brick realm last")
    row, other = r["sheet"]["items"][0], r["sheet"]["items"][1]
    assert row["item_id"] == "rx_rule" and row["title_whole"] == _caption("rx_rule")
    clock, other_clock = row["when"].split(" ", 1)[1], other["when"].split(" ", 1)[1]   # "2:00 pm"
    assert clock != other_clock
    ref, w = f"{r['rid']}.items[0]", row["title_whole"]
    for s in (f"You opened {w}[{ref}] at {clock}[{ref}.when].",
              f"You opened {w}[{ref}] at {clock.replace(':00', '')}[{ref}.when].",
              f'Your last Brick Realm video was "{w}"[{ref}], at {clock}[{ref}.when].'):
        o = _point(t, s)
        assert o.kept, (s, o.reasons)
    wrong = "3:00 pm" if clock != "3:00 pm" else "4:00 pm"
    for s in (f"You opened {w}[{ref}] at {wrong}[{ref}.when].",                        # a wrong clock
              f"You opened {w}[{ref}] at {other_clock}[{ref}.when].",                  # another row's clock
              f"You opened {w}[{ref}] at {other_clock}[{r['rid']}.items[1].when].",    # another row's cell
              f"You opened {w}[{ref}] at {clock}.",                                    # no marker
              f"You opened {w}[{ref}] at {clock}[{ref}.channel].",                     # a cell that is no date
              f"You opened {w}[{ref}] at 7 pm[{ref}.when].",                           # the title's own figure
              f"You opened {w}[{ref}] between 1:00 pm and {clock}[{ref}.when]."):
        assert not _point(t, s).kept, s


def test_the_reword_of_a_titles_own_figures_names_them_all_and_the_forms_that_pass(brain):
    """Part three: the reword text only. A sentence that says figures of a cut row's whole line with no marker is
    refused as before; its reword names every such figure at once and the row by its path, never a word of the
    title."""
    from mvp.brain import verify as V
    r, t = _search(brain, "sourdough", "saved", "my bread saves")
    whole = _caption("rx_sour1")
    assert "50 g" in whole and "12 hours" in whole                                      # the made-up line's figures
    o = _point(t, "Its title says to feed 50 g flour and 50 g water, then wait 12 hours.")
    assert not o.kept and o.reasons == ["unfound_number"]
    hint = o.notes["unfound_number"]
    assert hint.startswith("'50', '12' are only in an item's title") and f"[{r['rid']}.items[0]]" in hint
    assert "`title_whole`" in hint and len(hint) <= 160
    low = hint.lower()
    assert not any(w in low for w in ("sourdough", "starter", "flour", "water", "hours"))  # no word of the title
    v = V.check_answer({"lead": "Its title says to feed 50 g flour, then wait 12 hours.", "points": []}, t.results,
                       V.Turn.of(t), mode="values")
    assert "'50', '12' are only in an item's title" in V.repair_message(v)
    # the form the reword names passes, and so does the sentence without the figures
    assert _point(t, f"Its title is {whole}[{r['rid']}.items[0]].").kept
    assert _point(t, "Its title gives the feeding step for a starter.").kept
    # one figure: said in the singular
    one = _point(t, "It is about day 3 of a starter.")
    assert not one.kept and one.notes["unfound_number"].startswith("'3' is only in an item's title")


def test_the_reword_is_as_before_when_a_figure_is_in_no_whole_line(brain):
    from mvp.brain import verify as V
    r, t = _search(brain, "sourdough", "saved", "my bread saves")
    old = "has no marker and no result of this turn holds it"
    a = _point(t, "You saved 61 posts about bread.")                                    # no title holds 61
    assert not a.kept and old in a.notes["unfound_number"]
    b = _point(t, "Its title says to feed 50 g flour, and you saved 61 like it.")       # one of the two is no title's
    assert not b.kept and old in b.notes["unfound_number"]
    # with the rule off, and in full and cells, the text is as it was
    off = V.values_mode(rules=(V.VALUES.rules - {"whole_title"}))
    c = [o for o in V.check_answer({"lead": "Here is what it holds.", "points": ["It is about day 3 of a starter."]},
                                   t.results, V.Turn.of(t), mode=off).outcomes if o.where == "point"][0]
    assert not c.kept and old in c.notes["unfound_number"]
    for m in ("full", "cells"):
        assert "only in an item's title" not in json.dumps(_point(t, "It is about day 3 of a starter.", m).notes)
