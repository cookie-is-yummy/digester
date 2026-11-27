"""mvp30 tools: the read tools say what is true where a note, an error or a cell said more than the library holds, and
the cells a question needs are there to cite. Each test names a class of case; every expected value is recounted from
the made-up library's own rows (tests/brain_library.py, r12_library.py), never copied from a tool's output.

Made-up library and made-up messages only; no model call.
"""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.tests.test_brain_evaltools import (
    harness,  # noqa: F401  (harness is a fixture)
)
from mvp.tests.test_brain_tools import (  # noqa: F401
    NOW,
    brain,
    built,
    no_real_keys,
    person,
)
from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)

# (the fixtures drop every mvp module between tests, so each test imports the brain's modules itself)
SC = {"exclude": [], "how": "opened", "length": "any", "only": [], "platforms": [], "weekday": None}
ALL = {"preset": "all", "same_as": None, "words": None}


def _turn(e, message):
    from mvp.brain import tools as TL
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    return TL.Turn(e["bot"], person(e), NOW, message=message, search=FakeEngine(), learned=fake_learned)


def V_strip(marked):
    from mvp.brain import verify as V
    return V.strip_markers(marked)


def _rows():
    from mvp.tests import brain_library as BL
    return BL.rows()


# ================================================================ the auditor: an id with no open under a base of saves
def test_auditor_reads_a_year_over_a_base_that_holds_saved_only_items(harness):
    """A sentence naming one year, read over a result of base 'any' that holds an item saved and never opened: the
    auditor narrows by the item's own days (it raised KeyError on the saved-only id before), and the run goes on."""
    from mvp import eval_brain as EB
    from mvp.brain import tools as TL
    t = harness.turn("how come there are gaps", search=None, learned=None)
    args = {"by": "none", "compare": "none", "order": "most", "top": 5, "window": ALL, "scope": dict(SC, how="any")}
    env_ = TL.call(t, "breakdown", args, sent=True)
    periods = env_["sheet"].get("periods") or []
    k = next(n for n, p in enumerate(periods) if str(p.get("label")) == "2024")
    n24 = periods[k]["items"]
    saved_only = {r["id"] for r in _rows() if r["events"] and all(kk != "watch" for kk, _ in r["events"])}
    assert saved_only, "the made-up library holds saved-only items"
    tot = env_["sheet"]["totals"]["items"]
    marked = f"Across all your history you have {tot}[r1.totals.items] items, and 2024 holds the fewest: " \
             f"{n24}[r1.periods[{k}].items] videos."
    rec = {"lead_source": "model", "calls": [{"rid": "r1", "name": "breakdown", "args": args}], "answer": {"rid": "r1"},
           "verdicts": [{"outcomes": [{"where": "point", "kept": True, "text": marked, "rid": "r1",
                                       "sent": V_strip(marked)}]}]}
    _bad, checked, err = EB.guarded_audit(harness, t.results, t.unlock, rec, "how come there are gaps")
    assert err is None and checked > 0


# ================================================================ shared recount helpers (the made-up rows only)
from collections import Counter

from mvp.tests.test_brain_tools import (
    call,
    local,
    opened,
    visible_rows,
)


# the made-up library's own theme names, by its rows' theme key (tests/r12_library.NAMES)
THEME_KEY = {"Minecraft builds": "mc", "Watercolor painting": "wc", "Digital drawing": "dd", "Speedruns": "sr",
             "Calculus lessons": "ca", "Home cooking": "co", "Gaming clips": "cl", "Number puzzles": "np",
             "Dating advice": "da"}


def W(words=None, preset=None, same_as=None):
    return {"words": words, "preset": preset, "same_as": same_as}


def S(**kw):
    return dict(SC, **kw)


def chan(r):
    return r["channel"] if r["platform"] == "youtube" else "@" + r["handle"]


def kept(t, sentence, where="lead"):
    from mvp.brain import verify as V
    form = {"lead": sentence, "points": []} if where == "lead" else {"lead": "Here is what it holds.",
                                                                       "points": [sentence]}
    v = V.check_answer(form, t.results, V.Turn.of(t), mode="values")
    return all(o.kept for o in v.outcomes if o.where == where)


# ================================================================ titles: an episode number is part of the title
def test_numbered_episodes_keep_their_own_titles(brain):
    """Videos whose captions differ only by an episode tag ("... #60") showed one title, so twenty different videos
    read as one title; each row now shows its own caption's title, tag kept, and no two of them collide."""
    r, _t = call(brain, "items", {"limit": 10, "offset": 0, "order": "newest", "window": W(preset="all"),
                                  "scope": S(only=["gaming"])}, "my gaming clips")
    caps = {x["id"]: x["caption"] for x in visible_rows()}
    rows = r["sheet"]["items"]
    assert rows and all(row["title"] == caps[row["item_id"]] for row in rows)
    assert all("other_items_same_title" not in row and "same_title" not in row for row in rows)


def test_a_shared_title_counts_the_other_items_only(brain, monkeypatch):
    """Where items do share a title, the row counts the OTHER items with it (the row itself left out), under a name
    that says so, and the values check keeps the true count and refuses the count that includes the row."""
    import re

    from mvp import history as Hm
    from mvp.brain import tools as TL
    monkeypatch.setattr(TL, "item_title", lambda it: Hm._title(it))   # titles without their episode tag
    r, t = call(brain, "items", {"limit": 5, "offset": 0, "order": "newest", "window": W(preset="all"),
                                 "scope": S(only=["gaming"])}, "my gaming clips")
    k = next(n for n, x in enumerate(r["sheet"]["items"]) if "other_items_same_title" in x)
    row = r["sheet"]["items"][k]
    stem = re.sub(r"\s*#\d+$", "", next(x["caption"] for x in visible_rows() if x["id"] == row["item_id"]))
    n = sum(1 for x in visible_rows() if re.sub(r"\s*#\d+$", "", x["caption"]) == stem
            and any(k == "watch" for k, _ in x["events"]))                                               # recount
    assert row["other_items_same_title"] == n - 1 and n > 2
    assert any("OTHER items" in x for x in r["meta"]["notes"])
    good = f'"{row["title"]}"[r1.items[{k}]] shares its title with {n - 1}[r1.items[{k}].other_items_same_title] ' \
           'other videos.'
    bad = f'"{row["title"]}"[r1.items[{k}]] shares its title with {n}[r1.items[{k}].other_items_same_title] other ' \
          'videos.'
    assert kept(t, good) and not kept(t, bad)


# ================================================================ an order by times opened over a tie
def test_an_all_opened_once_tie_is_said_as_the_fact_with_a_cell(brain):
    r, t = call(brain, "items", {"limit": 5, "offset": 0, "order": "most_opened", "window": W(preset="all"),
                                 "scope": S(only=["calculus"])}, "the maths ones i went back to")
    calc = [x for x in visible_rows() if x["theme"] == "ca"]
    again = sum(1 for x in calc if sum(1 for k, _ in x["events"] if k == "watch") > 1)                    # recount
    assert r["sheet"]["opened_more_than_once"] == again == 0
    assert any("nothing here was opened again" in x for x in r["meta"]["notes"])
    assert not any("no ranking" in x for x in r["meta"]["notes"])
    assert kept(t, "None of these was opened more than once: 0[r1.opened_more_than_once] repeats.")


# ================================================================ lengths: minutes, and an order by length
def test_item_rows_carry_their_minutes_and_an_order_by_length_reads_every_item(brain):
    r, t = call(brain, "items", {"limit": 5, "offset": 0, "order": "longest", "window": W(preset="all"),
                                 "scope": S(only=["calculus"])}, "the lengthiest maths lessons")
    calc = [x for x in visible_rows() if x["theme"] == "ca" and any(k == "watch" for k, _ in x["events"])]
    known = [x for x in calc if x["length"]]
    lens = r["sheet"]["lengths"]
    assert (lens["known"], lens["unknown"]) == (len(known), len(calc) - len(known)) == (83, 2)            # recount
    assert lens["longest_minutes"] == lens["shortest_minutes"] == max(x["length"] for x in known) / 60 == 10
    by_id = {x["id"]: x for x in calc}
    assert all(row["minutes"] == by_id[row["item_id"]]["length"] / 60 for row in r["sheet"]["items"])
    assert any("none is longer than another" in x for x in r["meta"]["notes"])
    assert kept(t, "Every calculus video you opened with a known length runs 10[r1.lengths.longest_minutes] minutes.")
    # a window of mixed lengths: longest first, by the rows' own lengths
    r2, _t = call(brain, "items", {"limit": 3, "offset": 0, "order": "longest", "window": W("in October"),
                                   "scope": S()}, "my longest videos in october")
    octo = opened(date(2026, 10, 1), date(2026, 10, 30))
    top = max(x["length"] for x in visible_rows() if x["id"] in octo and x["length"])                      # recount
    assert r2["sheet"]["items"][0]["minutes"] == top / 60 == 25


# ================================================================ learned: an empty result says what the library holds
def test_an_empty_learned_result_counts_the_topic_opened_and_saved(brain):
    r, t = call(brain, "learned", {"topic": "calculus", "scope": S()}, "anything i picked up on maths",
                learned=__import__("mvp.tests.fakes.fake_brain", fromlist=["fake_learned"]).fake_learned)
    sh = r["sheet"]
    calc = [x for x in visible_rows() if x["theme"] == "ca"]
    n_open = sum(1 for x in calc if any(k == "watch" for k, _ in x["events"]))                             # recount
    n_save = sum(1 for x in calc if any(k in ("save", "playlist", "collection") for k, _ in x["events"]))
    assert sh["points"] == [] and sh["reads"] == "saved" and r["meta"]["base"] == "of what you saved"
    assert sh["on_topic"] == {"name": "Calculus lessons", "opened": n_open, "saved": n_save} and n_open == 85
    assert kept(t, "You opened 85[r1.on_topic.opened] calculus videos and saved 0[r1.on_topic.saved].")


# ================================================================ a scope's start is not the start of their history
def test_a_platform_scope_says_what_starts_there_and_what_lies_outside_it(brain):
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                     "window": W(preset="all"), "scope": S(platforms=["instagram"])},
                "what's my instagram history")
    ig_open = min(local(at) for x in visible_rows() if x["platform"] == "instagram" for k, at in x["events"]
                  if k == "watch")                                                                          # recount
    assert r["sheet"]["window"]["words"].startswith("all your history (your Instagram opens: ")
    assert ig_open == date(2026, 10, 12)
    r2, _t2 = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                       "window": W("2022"), "scope": S(platforms=["instagram"])},
                  "insta stuff from 2022")
    cs = r2["sheet"]["cannot_see"]
    first = min(local(at) for x in visible_rows() for k, at in x["events"])
    in22 = {x["id"] for x in visible_rows() for k, at in x["events"] if local(at).year == 2022}
    assert (cs["scope_starts"], cs["record_starts"]) == (ig_open.isoformat(), first.isoformat())
    assert cs["outside_scope_items"] == len(in22) == 108 and "history_starts" not in cs
    first_ig = min(local(at) for x in visible_rows() if x["platform"] == "instagram" for k, at in x["events"])
    assert r["sheet"]["window"]["platform_starts"] == first_ig.isoformat() < ig_open.isoformat()           # recount
    assert any("as a whole starts on 5 January 2021" in x for x in r2["meta"]["notes"])
    assert not any(x.startswith("Your history starts on 12 October") for x in r2["meta"]["notes"])


# ================================================================ friends' posts: never shown, counted apart
def test_the_friends_note_says_they_are_counted_apart(brain):
    from mvp.brain import tools as TL
    r, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                      "window": W("in October"), "scope": S(how="saved")},
                 "my october saves, the friends ones too")
    fr = [x for x in B_rows() if x.get("friend") and any(k == "save" and local(at).month == 10
                                                         for k, at in x["events"])]                       # recount
    assert r["sheet"]["left_out"]["friends"] == len(fr) == 1
    assert TL.FRIENDS_LINE in r["meta"]["notes"] and TL.FRIENDS_LEFT_NOTE in r["meta"]["notes"]
    assert "not counted" not in TL.FRIENDS_LINE


def B_rows():
    from mvp.tests import brain_library as BL
    return BL.rows()


# ================================================================ the size cut keeps the periods asked for
def test_a_timeline_keeps_every_period_and_names_what_it_cut(brain):
    r, _t = call(brain, "timeline", {"unit": "year", "window": W(preset="all"), "scope": S()},
                 "a thing i stuck with across the years")
    ps = r["sheet"]["periods"]
    years = sorted({local(at).year for x in visible_rows() for k, at in x["events"] if k == "watch"})       # recount
    assert [p["label"] for p in ps] == [str(y) for y in years]
    assert all(p.get("themes") for p in ps)   # each period keeps its themes
    every = r["sheet"]["in_top_of_every_period"]["themes"]
    for nm in every:
        key = {"Home cooking": "co"}.get(nm)
        assert key and all(any(x["theme"] == key and local(at).year == y for x in visible_rows()
                               for k, at in x["events"] if k == "watch") for y in years)                 # recount
    assert "Home cooking" in every
    assert all(not c.startswith("periods:") for c in r["meta"].get("cut") or [])
    m, _t = call(brain, "timeline", {"unit": "month", "window": W(preset="all"), "scope": S()}, "month by month")
    months = {(local(at).year, local(at).month) for x in visible_rows() for k, at in x["events"] if k == "watch"}
    (y0, m0), (y1, m1) = min(months), max(months)
    assert len(m["sheet"]["periods"]) == (y1 - y0) * 12 + (m1 - m0) + 1 == 70                             # recount
    assert m["meta"]["complete"] is True and m["meta"]["cut"]


def test_a_period_holding_private_items_is_never_marked_sparse(brain):
    """A period under the sparse floor that holds private items left out is not all they did in it: it is not marked
    sparse. A period under the floor with no private item still is."""
    from mvp.brain import tools as TL
    from mvp.tests.test_brain_tools import SENSITIVE_KEYS
    r, _t = call(brain, "timeline", {"unit": "year", "window": W(preset="all"), "scope": S()}, "each year")
    shown = Counter(local(at).year for x in visible_rows() for k, at in x["events"] if k == "watch")      # recount
    shown = {y: len({x["id"] for x in visible_rows() for k, at in x["events"] if k == "watch" and local(at).year == y})
             for y in shown}
    private = {y: len({x["id"] for x in B_rows() if x["theme"] in SENSITIVE_KEYS and not x.get("friend")
                       for k, at in x["events"] if k == "watch" and local(at).year == y}) for y in shown}
    for p in r["sheet"]["periods"]:
        y = int(p["label"])
        assert p["items"] == shown[y]
        assert p["sparse"] is (shown[y] < 50 and private[y] == 0), y
    thin = [y for y in shown if shown[y] < 50]
    assert thin == [2024] and private[2024] == 50                                                          # recount
    assert TL.SPARSE_NOTE.format(n=50) in r["meta"]["notes"]
    m, _t = call(brain, "timeline", {"unit": "month", "window": W(preset="all"), "scope": S()}, "month by month")
    for p in m["sheet"]["periods"]:
        ids = {x["id"] for x in B_rows() if x["theme"] in SENSITIVE_KEYS and not x.get("friend")
               for k, at in x["events"] if k == "watch" and local(at).strftime("%b %Y") == p["label"]}
        if p["items"] < 50:
            assert p["sparse"] is (not ids), p["label"]


def test_a_scoped_result_counts_the_names_of_its_scope(brain):
    r, t = call(brain, "breakdown", {"by": "area", "compare": "none", "order": "most", "top": 8,
                                     "window": W(preset="all"), "scope": S(only=["gaming", "cooking", "calculus"])},
                "gaming cooking and calculus")
    assert r["sheet"]["filters"]["names_in_scope"] == 3
    assert kept(t, "Across these three[r1.filters.names_in_scope] names you opened "
                   f"{r['sheet']['totals']['items']}[r1.totals.items] videos.")
    u, _t = call(brain, "breakdown", {"by": "area", "compare": "none", "order": "most", "top": 8,
                                      "window": W(preset="all"), "scope": S()}, "everything")
    assert "names_in_scope" not in u["sheet"]["filters"]


# ================================================================ a longer name that holds the word asked
def test_a_word_that_is_an_area_names_the_channels_and_themes_holding_it(brain):
    r, _t = call(brain, "find", {"names": ["gaming"], "kinds": []}, "the gaming daily channel")
    also = {x["label"] for x in r["sheet"]["names"][0]["also"]}
    holding = {chan(x) for x in visible_rows() if "gaming" in chan(x).lower()}                          # recount
    assert holding == {"Gaming Daily"} and holding <= also and "Gaming clips" in also
    b, _t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                      "window": W(preset="all"), "scope": S(only=["gaming"])}, "gaming daily")
    assert "Gaming Daily" in {x["label"] for x in b["meta"]["also"]["gaming"]}


# ================================================================ when: each weekday; channels: their last day
def test_the_events_of_each_weekday_and_a_channels_last_day(brain):
    r, t = call(brain, "breakdown", {"by": "channel", "compare": "none", "order": "most", "top": 25,
                                     "window": W(preset="all"), "scope": S()}, "channels i stopped going to")
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    c = Counter(local(at).weekday() for x in visible_rows() for k, at in x["events"] if k == "watch")  # recount
    assert r["sheet"]["when"]["events_by_weekday"] == {days[k]: c.get(k, 0) for k in range(7)}
    last = {}
    for x in visible_rows():
        for k, at in x["events"]:
            if k == "watch":
                last[chan(x)] = max(last.get(chan(x), date.min), local(at))
    for row in r["sheet"]["channels"]:
        nm = "@" + row["handle"] if row.get("handle") else row["name"]
        assert row["last_watched"] == last[nm].isoformat(), nm                                           # recount
    th, _t = call(brain, "breakdown", {"by": "theme", "compare": "none", "order": "most", "top": 25,
                                       "window": W(preset="all"), "scope": S()}, "themes i quit")
    lastk = {}
    for x in visible_rows():
        for k, at in x["events"]:
            if k == "watch":
                lastk[x["theme"]] = max(lastk.get(x["theme"], date.min), local(at))
    for row in th["sheet"]["themes"]:
        assert row["last_watched"] == lastk[THEME_KEY[row["name"]]].isoformat(), row["name"]             # recount
    fp = next(row for row in r["sheet"]["channels"] if row["name"] == "Frame Perfect")
    assert fp["last_watched"].startswith("2023")
    sun = c.get(6, 0)
    assert kept(t, f"You opened {sun}[r1.when.events_by_weekday.Sunday] videos on Sundays.")
    assert not kept(t, f"You opened {sun + 1}[r1.when.events_by_weekday.Sunday] videos on Sundays.")


# ================================================================ the cells of a change, said as what they count
def test_new_channels_all_counted_and_the_window_before_has_its_own_count(brain):
    r, _t = call(brain, "changes", {"against": "previous", "level": "channel", "window": W("this fall"),
                                    "scope": S()}, "channels that are new to me this autumn")
    sh = r["sheet"]
    a, b = date.fromisoformat(sh["window"]["start"]), date.fromisoformat(sh["window"]["end"])
    assert sh["window"]["days"] == (b - a).days + 1                                                       # recount
    first = {}
    for x in visible_rows():
        for k, at in x["events"]:
            if k == "watch":
                first[chan(x)] = min(first.get(chan(x), date.max), local(at))
    assert sh["new"]["channels_first_opened"] == sum(1 for d in first.values() if a <= d <= b)          # recount
    wb = r["meta"]["window_dates_before"]
    pa, pb = date.fromisoformat(wb["start"]), date.fromisoformat(wb["end"])
    before = {chan(x) for x in visible_rows() for k, at in x["events"] if k == "watch" and pa <= local(at) <= pb}
    assert sh["previous"]["channels"] == len(before)                                                     # recount
    assert sh["previous"].get("days", (pb - pa).days + 1) == (pb - pa).days + 1


def test_a_new_theme_begun_before_the_window_is_listed_apart(brain):
    r, _t = call(brain, "breakdown", {"by": "theme", "window": W("this autumn")}, "this autumn")
    new = r["sheet"]["new"]
    start = date.fromisoformat(r["sheet"]["window"]["start"])
    for row in new.get("themes_begun_before") or []:
        assert date.fromisoformat(row["first_watched"]) < start
    for row in new.get("themes") or []:
        assert date.fromisoformat(row["first_watched"]) >= start
    assert any(row["name"] == "Home cooking" for row in new["themes_begun_before"])
    co = next(row for row in new["themes_begun_before"] if row["name"] == "Home cooking")
    first_co = min(local(at) for x in visible_rows() if x["theme"] == "co" for k, at in x["events"] if k == "watch")
    end = date.fromisoformat(r["sheet"]["window"]["end"])
    assert co["first_watched"] == first_co.isoformat() < start.isoformat()                                # recount
    assert co["items"] == len(opened(start, end, keys={"co"}))                                            # recount


def test_under_base_any_opens_saves_and_likes_are_apart(brain):
    r, _t = call(brain, "breakdown", {"by": "channel", "compare": "none", "order": "most", "top": 25,
                                      "window": W("this year"), "scope": S(how="any")}, "wet paper this year")
    row = next(x for x in r["sheet"]["channels"] if x["name"] == "Wet Paper")
    wp = [x for x in visible_rows() if x.get("channel") == "Wet Paper"]
    y = 2026
    o = sum(1 for x in wp if any(k == "watch" and local(at).year == y for k, at in x["events"]))         # recount
    s = sum(1 for x in wp if any(k in ("save", "playlist") and local(at).year == y for k, at in x["events"]))
    assert (row["opened"], row["saved"], row["liked"]) == (o, s, 0) and row["items"] == o + s and s == 3
    t2, _t = call(brain, "breakdown", {"by": "theme", "compare": "none", "order": "most", "top": 25,
                                       "window": W("this year"), "scope": S(how="any")}, "painting this year")
    trow = next(x for x in t2["sheet"]["themes"] if x["name"] == "Watercolor painting")
    wcr = [x for x in visible_rows() if x["theme"] == "wc"]
    to = sum(1 for x in wcr if any(k == "watch" and local(at).year == y for k, at in x["events"]))        # recount
    ts = sum(1 for x in wcr if any(k in ("save", "playlist") and local(at).year == y for k, at in x["events"]))
    tl = sum(1 for x in wcr if any(k == "like" and local(at).year == y for k, at in x["events"]))
    if "opened" in trow:
        assert (trow["opened"], trow["saved"], trow["liked"]) == (to, ts, tl)
    assert "opened" in trow


def test_a_compare_says_the_days_of_both_windows(brain):
    r, _t = call(brain, "compare", {"a": W("this summer"), "b": W("last summer"), "by": "area", "scope": S()},
                 "summer against summer")
    ws = r["sheet"]["windows"]
    for side, (a0, b0) in (("a", (date(2026, 6, 1), date(2026, 8, 31))), ("b", (date(2025, 6, 1), date(2025, 8, 31)))):
        assert (ws[side]["start"], ws[side]["end"]) == (a0.isoformat(), b0.isoformat())
        assert ws[side]["days"] == (b0 - a0).days + 1 == 92                                               # recount


def test_a_share_that_is_all_of_a_scope_by_construction_is_left_out(brain):
    r, _t = call(brain, "breakdown", {"by": "area", "compare": "none", "order": "most", "top": 5,
                                      "window": W(preset="lately"), "scope": S(only=["minecraft"])}, "minecraft lately")
    assert r["sheet"]["areas"] and all("share" not in a for a in r["sheet"]["areas"] if a.get("items"))
    assert any("by construction" in x for x in r["meta"]["notes"])
    assert r["sheet"]["library"]["counted_over"] == "all your history"


def test_a_title_clipped_by_code_says_so(brain):
    from mvp.tests.fakes.fake_brain import FakeEngine
    r, _t = call(brain, "search", {"how": "saved", "limit": 5, "query": "sourdough", "window": None},
                 "my sourdough saves", search=FakeEngine())
    for row in r["sheet"]["items"]:
        assert row.get("title_clipped", False) is row["title"].endswith("…")
    assert any(row.get("title_clipped") for row in r["sheet"]["items"])
    assert any("is whole in their history" in x for x in r["meta"]["notes"])


# ================================================================ the schema, and the eval's outside-the-record turns
def test_breakdown_order_stays_required_and_says_what_it_does_by_none(brain):
    from mvp.brain import tools as TL
    s = TL.schema("breakdown")
    assert "order" in s["required"] and "by 'none'" in s["properties"]["order"]["description"]
    bad = TL.sent_problems("breakdown", {"by": "none", "compare": "none", "top": 5, "window": W(preset="all"),
                                         "scope": S()})
    assert [p["path"] for p in bad] == ["order"]


def test_a_window_wholly_before_the_record_says_so_in_its_limit_cell(harness):
    from mvp.brain import tools as TL
    t = harness.turn("my 2019 videos")
    env_ = TL.call(t, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "window": W("2019"),
                                     "scope": S()}, sent=True)
    assert env_["sheet"]["cannot_see"]["reason"] == "before"
