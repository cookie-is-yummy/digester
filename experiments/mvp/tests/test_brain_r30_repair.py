"""mvp30 repair: the faults an independent attack found in the mvp30 round, each fixed by a class of case.

1. A length cell (an item's `minutes`, the `lengths` longest and shortest, the length totals) stands for no figure
   written with no marker, and a length cited in a sentence today's full check reads as watch time is refused (rule
   length_cells, in the values default). A length said of the video is kept.
2. A code lead after a timeout writes no sentence of a result whose scope no template says (it would go out with no
   scope line), and keeps the scope line of a lead whose scope no template says.
3. `last_watched`, `new.channels_first_opened` and `previous.channels` are counted in the call's own scope.
4. A learned read is of one topic and leaves no friend's post out; a search's friends count says a search never
   reads them.
5. An items result of a window before its scope's start carries the `cannot_see` cell its note names.

Every expected value is recounted from the made-up library's own rows; made-up messages only; no model call.
"""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.tests.test_brain_tools import (  # noqa: E402,F401
    brain,
    built,
    call,
    local,
    no_real_keys,
    person,
    visible_rows,
)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_r30_tools import THEME_KEY, S, W, chan  # noqa: E402


def _mode(rules):
    from mvp.brain import verify as V
    return V.values_mode(rules=rules)


def _point(t, text, mode=None):
    from mvp.brain import verify as V
    v = V.check_answer({"lead": "Here is what it holds.", "points": [text]}, t.results, V.Turn.of(t),
                       mode=mode or V.VALUES)
    return [o for o in v.outcomes if o.where == "point"][0]


# ================================================================ 1. a length is the video's, never a bare count
def test_a_length_cell_is_no_bare_figure_and_never_time_spent(brain):
    from mvp.brain import verify as V
    r, t = call(brain, "items", {"limit": 3, "offset": 0, "order": "longest", "window": W("in October"),
                                 "scope": S()}, "my longest videos in october")
    row = r["sheet"]["items"][0]
    mins = row["minutes"]
    octo = [x for x in visible_rows() if x["length"] and any(
        k == "watch" and date(2026, 10, 1) <= local(at) <= date(2026, 10, 30) for k, at in x["events"])]
    assert mins == max(x["length"] for x in octo) / 60                                                      # recount
    # no other cell of the turn holds the figure: a bare count equal to a length is not found by it
    assert "length_cells" in V.VALUES.rules
    bare = f"You opened {mins} videos about painting in October."
    assert _point(t, bare).reasons == ["unfound_number"]
    assert _point(t, bare, _mode(V.VALUES_RULES)).kept   # last round's mode found it in the length cell
    # a length cited as time they spent: refused (full's own watch-time reading); said of the video: kept
    spent = f"You spent {mins}[r1.items[0].minutes] minutes on {row['title']}[r1.items[0]]."
    assert "watch_time" in _point(t, spent).reasons
    runs = f"{row['title']}[r1.items[0]] runs {mins}[r1.items[0].minutes] minutes."
    assert _point(t, runs).kept
    # the tool says what the cell is
    from mvp.brain import tools as TL
    assert "never how long they watched it" in TL.REGISTRY["items"].description


# ================================================================ 2. a code lead never drops a scope it cannot say
def test_other_points_skip_a_result_whose_scope_no_template_says(brain):
    from mvp.brain import fallback as FB, tools as TL, verify as V
    _r, t = call(brain, "breakdown", {"by": "channel", "compare": "none", "order": "most", "top": 5,
                                      "window": W("in October"), "scope": S()}, "october channels and my dating videos")
    TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(preset="all"),
                             "scope": S(only=["Dating advice"])})
    TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W(preset="all"),
                             "scope": S(platforms=["instagram"])})
    led = V.Ledger(t.results)
    assert not FB.scope_said(led.get("r2")) and FB.scope_said(led.get("r3")) and FB.scope_said(led.get("r1"))
    pts, _priv = FB.other_points(led, {"rid": "r1", "lead": "x"}, V.Turn.of(t))
    assert len(pts) == 1 and "on Instagram only" in pts[0]
    da = sum(1 for x in visible_rows(True) if x["theme"] == "da" and any(k == "watch" for k, _ in x["events"]))
    assert not any(str(da) in p for p in pts)                                                              # recount
    # a lead whose own scope no template says keeps its scope line: no `mixed`
    led2 = V.Ledger({"r2": t.results["r2"]})
    out = FB.answer(led2, None, V.Turn.of(t), others=True)
    assert not out.get("mixed")


# ================================================================ 3. the three cells are of the call's scope
def test_last_watched_and_the_channel_counts_are_of_the_calls_scope(brain):
    r, _t = call(brain, "breakdown", {"by": "theme", "compare": "none", "order": "most", "top": 25,
                                      "window": W(preset="all"), "scope": S(platforms=["instagram"])},
                 "my instagram themes")
    last = {}
    for x in visible_rows():
        if x["platform"] != "instagram":
            continue
        for k, at in x["events"]:
            if k == "watch":
                last[x["theme"]] = max(last.get(x["theme"], date.min), local(at))
    rows = [row for row in r["sheet"]["themes"] if "last_watched" in row]
    assert rows
    for row in rows:
        assert row["last_watched"] == last[THEME_KEY[row["name"]]].isoformat(), row["name"]                # recount
    # one channel's scope: the channels first opened in the window are that channel's only
    r2, _t = call(brain, "changes", {"against": "previous", "level": "channel", "window": W("in October"),
                                     "scope": S(only=["Gaming Daily"])}, "gaming daily in october")
    sh = r2["sheet"]
    a, b = date.fromisoformat(sh["window"]["start"]), date.fromisoformat(sh["window"]["end"])
    first, inw = {}, set()
    for x in visible_rows():
        for k, at in x["events"]:
            if k == "watch":
                first[chan(x)] = min(first.get(chan(x), date.max), local(at))
                if chan(x) == "Gaming Daily" and a <= local(at) <= b:
                    inw.add(chan(x))
    want = sum(1 for c, d in first.items() if a <= d <= b and c in inw)                                    # recount
    assert sh["new"]["channels_first_opened"] == want == 1
    wb = r2["meta"]["window_dates_before"]
    pa, pb = date.fromisoformat(wb["start"]), date.fromisoformat(wb["end"])
    before = {chan(x) for x in visible_rows() for k, at in x["events"]
              if k == "watch" and chan(x) == "Gaming Daily" and pa <= local(at) <= pb}
    assert sh["previous"]["channels"] == len(before)                                                      # recount


# ================================================================ 4. friends' posts: of no topic, never searched
def test_a_learned_read_leaves_no_friends_post_out_and_a_search_says_it_never_reads_them(brain):
    from mvp.brain import tools as TL
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    r, _t = call(brain, "learned", {"topic": "calculus", "scope": S()}, "what did i pick up on maths",
                 learned=fake_learned)
    assert r["meta"]["hidden"]["friends"] == 0 and "left_out" not in r["sheet"]
    assert TL.FRIENDS_LEFT_NOTE not in r["meta"]["notes"]
    s, _t = call(brain, "search", {"query": "watercolor", "how": "saved", "limit": 5, "window": W(preset="all")},
                 "my watercolor saves", search=FakeEngine())
    fr = [x for x in __import__("mvp.tests.brain_library", fromlist=["rows"]).rows()
          if x.get("friend") and any(k == "save" for k, _ in x["events"])]                                 # recount
    assert fr, "the made-up library holds a friend's saved post"
    assert s["sheet"]["left_out"]["friends"] == len(fr)
    assert TL.FRIENDS_SEARCH_NOTE in s["meta"]["notes"] and TL.FRIENDS_LEFT_NOTE not in s["meta"]["notes"]


# ================================================================ 5. an items result carries the cell its note names
def test_an_items_window_before_its_scope_carries_the_cannot_see_cell(brain):
    r, t = call(brain, "items", {"limit": 5, "offset": 0, "order": "newest", "window": W("2024"),
                                 "scope": S(platforms=["instagram"])}, "instagram things from 2024")
    cs = r["sheet"]["cannot_see"]
    in24 = {x["id"] for x in visible_rows() for k, at in x["events"] if local(at).year == 2024}             # recount
    assert cs["reason"] == "before" and cs["outside_scope_items"] == len(in24)
    assert any("cannot_see.outside_scope_items" in n for n in r["meta"]["notes"])
    assert _point(t, f"This window holds {len(in24)}[r1.cannot_see.outside_scope_items] items outside Instagram.").kept
