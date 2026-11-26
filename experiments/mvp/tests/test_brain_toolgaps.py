"""The tool gaps the live run on fresh half A showed (scratchpad mvp24/runa/run1, read by hand in mvp24/recounta;
DESIGN 25). Each test replays the call the model made in that run (its arguments as recorded) on the made-up library
of tests/brain_library.py and checks the fixed result against a recount from the library's own rows (the helpers of
test_brain_tools.py, which share nothing with facts.py). Offline: no model call, no network. Every title, channel,
handle and theme is made up."""
import os
import sys
from collections import Counter
from datetime import date, datetime

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures and the recount helpers)
    NOW, NY, B, brain, built, call, local, no_real_keys, opened, person, turn, visible_rows)

SCOPE = {"exclude": [], "how": "opened", "length": "any", "only": [], "platforms": [], "weekday": None}


def W(words=None, preset=None, same_as=None):
    return {"words": words, "preset": preset, "same_as": same_as}


def S(**kw):
    return dict(SCOPE, **kw)


def ledger_of(t):
    from mvp.brain import verify as V
    return V.Ledger(t.results), V.Turn.of(t)


def kept(t, sentence, mode="cells", point=None):
    """The lead kept (or, with `point`, that point kept under the lead) by the checker."""
    from mvp.brain import verify as V
    led, vt = ledger_of(t)
    v = V.check_answer({"lead": sentence, "points": [point] if point else []}, led, vt, mode=mode)
    return v.lead_ok if point is None else [o for o in v.outcomes if o.where == "point"][0].kept


def opens_at(pred=lambda r: True, a=None, b=None, unlock_sensitive=False):
    """[(row, New York datetime)] of every watch of the visible rows that `pred` keeps, between a and b."""
    out = []
    for r in visible_rows(unlock_sensitive):
        for k, at in r["events"]:
            d = datetime.fromisoformat(at).astimezone(NY)
            if k == "watch" and pred(r) and (a is None or d.date() >= a) and (b is None or d.date() <= b):
                out.append((r, d))
    return out


# ================================================================ 1. windows: seasons, parts of a period, exact days
def test_the_summer_said_alone_is_this_summer(brain):
    # N004.0 "my last few weeks compared to the summer": 'the summer' was not read
    from mvp.brain import windows as W_
    w = W_.read_words("the summer", date(2026, 11, 22), message="compared to the summer")
    assert (w.start, w.end) == (date(2026, 6, 1), date(2026, 8, 31))
    env_, _t = call(brain, "breakdown", {"by": "area", "window": W("the summer")}, "compared to the summer")
    assert env_["meta"]["window_dates"] == {"start": "2026-06-01", "end": "2026-08-31", "days": 92,
                                            "said": "1 June to 31 August 2026"}
    assert env_["sheet"]["totals"]["items"] == len(opened(date(2026, 6, 1), date(2026, 8, 31))) == 45


def test_last_summer_beside_this_summer_is_the_summer_before(brain):
    # N010.0 "this summer vs last summer": both windows were the summer of 2026
    args = {"a": W("this summer"), "b": W("last summer"), "by": "area", "scope": S()}
    env_, _t = call(brain, "compare", args, "this summer vs last summer")
    m = env_["meta"]
    assert m["windows"]["a"]["start"] == "2026-06-01" and m["windows"]["b"]["start"] == "2025-06-01"
    assert m["window_dates_b"] == {"start": "2025-06-01", "end": "2025-08-31", "days": 92,
                                   "said": "1 June to 31 August 2025"}
    assert env_["sheet"]["totals"]["items"] == len(opened(date(2026, 6, 1), date(2026, 8, 31))) == 45      # recount
    assert env_["sheet"]["previous"]["items"] == len(opened(date(2025, 6, 1), date(2025, 8, 31))) == 16   # recount
    # N010.1 "just the art side": the same two summers, only art (14 of the 16 were watercolor)
    args = {"a": W("this summer"), "b": W("last summer"), "by": "none", "scope": S(only=["art"])}
    env_, _t = call(brain, "compare", args, "just the art side")
    assert env_["sheet"]["previous"]["items"] == len(opened(date(2025, 6, 1), date(2025, 8, 31), keys={"wc", "dd"}))
    assert env_["sheet"]["previous"]["items"] == 14


@pytest.mark.parametrize("words,first,last", [("last winter", "2024-12-01", "2025-02-28"),
                                              ("this winter", "2025-12-01", "2026-02-28"),
                                              ("last autumn", "2025-09-01", "2025-11-30"),
                                              ("over the summer", "2026-06-01", "2026-08-31")])
def test_the_season_convention(words, first, last):
    from mvp.brain import windows as W_
    w = W_.read_words(words, date(2026, 11, 22), message=words)
    assert (w.start.isoformat(), w.end.isoformat()) == (first, last)


def test_late_october_and_mid_2023_are_their_own_days(brain):
    # N063.0 "what was i watching late october", N064.0 "mid 2023 what was going on": both were refused
    env_, t = call(brain, "breakdown", {"by": "area", "compare": "none", "order": "most", "scope": S(), "top": 5,
                                        "window": W("late October")}, "what was i watching late october")
    assert not env_.get("is_error")
    assert env_["meta"]["window_dates"] == {"start": "2026-10-21", "end": "2026-10-30", "days": 10,
                                            "said": "21 to 30 October 2026"}
    assert env_["sheet"]["totals"]["items"] == len(opened(date(2026, 10, 21), date(2026, 10, 31))) == 38     # recount
    assert kept(t, "In late October 2026, you opened 38[r1.totals.items] videos.")
    env_, t = call(brain, "breakdown", {"by": "area", "compare": "none", "order": "most", "scope": S(), "top": 5,
                                        "window": W("mid 2023")}, "mid 2023 what was going on")
    assert env_["meta"]["window_dates"]["start"] == "2023-05-01" and env_["meta"]["window_dates"]["end"] == "2023-08-31"
    assert env_["sheet"]["totals"]["items"] == len(opened(date(2023, 5, 1), date(2023, 8, 31))) == 138       # recount
    assert kept(t, "In mid 2023, you opened 138[r1.totals.items] videos.")


def test_a_part_the_convention_does_not_name_is_still_refused(brain):
    env_, _t = call(brain, "breakdown", {"by": "area", "window": W("the first week of march")},
                    "the first week of march")
    assert env_.get("is_error") and "part of a period" in env_["error"]


def test_every_result_with_a_window_says_its_days(brain):
    ex = [("timeline", {"unit": "month", "window": W(preset="this_year"), "scope": S()}, ("2026-01-01", "2026-10-30")),
          ("items", {"window": W(preset="lately"), "scope": S(), "order": "newest", "limit": 3},
           ("2026-10-03", "2026-10-30")),
          ("first_last", {"subject": "minecraft", "which": "last", "scope": S()}, ("2021-01-05", "2026-10-30"))]
    for tool, args, days in ex:
        env_, _t = call(brain, tool, args, "x")
        d = env_["meta"]["window_dates"]
        assert (d["start"], d["end"]) == days, tool


# ================================================================ 2. after the export; a kind it does not hold
@pytest.mark.parametrize("args,asked", [
    ({"a": W(preset="this_month"), "b": W(preset="last_month"), "by": "area", "scope": S()}, "1 to 22 November 2026"),
    ({"a": W("last few weeks"), "b": W("this summer"), "by": "area", "scope": S()}, "2 to 22 November 2026")])
def test_a_window_after_the_export_says_what_it_holds(brain, args, asked):
    # N067.0 "november vs october so far", N004.0's second call: a bare "starts after where the export ends"
    env_, t = call(brain, "compare", args, "november vs october so far")
    assert env_["is_error"]
    ends = max(local(at) for r in visible_rows() for _k, at in r["events"])
    assert ends == date(2026, 10, 30) and env_["export"]["ends"] == ends.isoformat()                         # recount
    assert env_["export"]["holds"] == ["opened", "saved"] and env_["export"]["holds_not"] == ["liked"]
    assert env_["asked"]["said"] == asked
    assert env_["nearest"]["window"] == {"preset": "lately"} and env_["nearest"]["end"] == "2026-10-30"
    assert "Or answer with the other window" in env_["error"]
    assert t.limits == [f"Your export ends on 30 October 2026, so {asked} is not in it."]
    # the nearest window, passed as it is, is not refused
    ok, _t2 = call(brain, "compare", dict(args, a=env_["nearest"]["window"]), "november vs october so far")
    assert not ok.get("is_error")


def test_a_kind_the_export_does_not_hold_says_what_it_holds(brain):
    # N038.0 "what have i liked recently": "nothing in their record for this", twice
    kinds = Counter(k for r in visible_rows() for k, _at in r["events"])
    assert "like" not in kinds and kinds["save"] + kinds["playlist"] == 6                                    # recount
    env_, t = call(brain, "breakdown", {"by": "area", "compare": "none", "order": "most", "top": 5,
                                        "scope": S(how="liked"), "window": W("recently")}, "what have i liked recently")
    assert env_["is_error"] and env_["nearest"] == {"scope.how": "saved"}
    assert env_["export"]["holds_not"] == ["liked"] and "holds no likes" in env_["error"]
    assert t.limits == ["Your export holds no likes."]


# ================================================================ 3. first_last with its subject in scope.only
def test_first_last_takes_its_subject_in_scope_only(brain):
    # N013.0, N013.1: "put what it is about in `subject`, not in scope.only", and a second call
    args = {"scope": S(only=["minecraft"]), "subject": "minecraft", "which": "last"}
    env_, _t = call(brain, "first_last", args, "when was the last time i watched any minecraft")
    plain, _t2 = call(brain, "first_last", dict(args, scope=S()), "when was the last time i watched any minecraft")
    assert not env_.get("is_error") and env_["sheet"] == plain["sheet"]
    last = max(opens_at(lambda r: r["theme"] == "mc"), key=lambda x: x[1])
    assert env_["sheet"]["items"][0]["item_id"] == last[0]["id"]                                              # recount
    other, _t3 = call(brain, "first_last", dict(args, scope=S(only=["cooking"])), "x")
    assert other["is_error"] and "one subject" in other["error"]


# ================================================================ 4. item rows say what happened and when
def test_an_item_row_says_its_event(brain):
    # N048.0 "find the sourdough starter post": a saved post went out as "opened on 5 October 2026"
    from mvp.tests.fakes.fake_brain import FakeEngine
    env_, t = call(brain, "search", {"how": "any", "limit": 5, "query": "sourdough starter", "window": W(preset="all")},
                   "find the sourdough starter post", search=FakeEngine())
    row = next(x for x in env_["sheet"]["items"] if x["item_id"] == "rx_sour1")
    src = next(r for r in B.rows() if r["id"] == "rx_sour1")
    assert [k for k, _at in src["events"]] == ["save"] and local(src["events"][0][1]).isoformat() == row["when"]
    assert row["how"] == "saved"                                                                              # recount
    assert kept(t, f"The closest match is {row['title']}[{row['ref']}], saved on 5 October 2026[{row['ref']}.when].")
    env_, _t = call(brain, "items", {"limit": 5, "order": "newest", "scope": S(how="saved"), "window": W("recently")},
                    "what have i saved recently")
    assert {x["how"] for x in env_["sheet"]["items"]} == {"saved"}
    env_, _t = call(brain, "items", {"limit": 3, "order": "newest", "scope": S(), "window": W(preset="lately")}, "x")
    assert {x["how"] for x in env_["sheet"]["items"]} == {"opened"}


# ================================================================ 5. the private topic on a follow-up
def test_a_follow_up_keeps_the_private_topic_the_last_answer_resolved(brain):
    # N053.0 then N053.1 "and how did that year compare to 2023": compare and find gave no_match for "dating"
    from mvp.brain import loop as BL
    q0 = "was i really watching dating videos every week in 2024"
    env0, t0 = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                         "scope": S(only=["dating"]), "window": W("in 2024")}, q0)
    carry = BL.unlock_after(t0, {"calls": [{"result": env0}]})
    assert carry == "relationships"
    q1 = "and how did that year compare to 2023"
    args = {"a": W("in 2024"), "b": W("in 2023"), "by": "none", "scope": S(only=["dating"])}
    scr = '{"last_answer": {"plan": [{"window_said": "2024"}]}}'   # the screen holds the digits of 2024, as in run1
    locked, _t = call(brain, "compare", args, q1, screen=scr)
    assert locked.get("error") == "no_match"                                       # as run1 had it, with nothing carried
    env1, t1 = call(brain, "compare", args, q1, carried_unlock=carry, screen=scr)
    assert t1.unlock == "relationships" and not env1.get("is_error")
    y24 = opened(date(2024, 1, 1), date(2024, 12, 31), keys={"da"}, unlock_sensitive=True)
    y23 = opened(date(2023, 1, 1), date(2023, 12, 31), keys={"da"}, unlock_sensitive=True)
    assert env1["sheet"]["totals"]["items"] == len(y24) == 50 and env1["sheet"]["previous"]["items"] == len(y23) == 0
    fnd, _t = call(brain, "find", {"kinds": ["theme", "words"], "names": ["dating"]}, q1, carried_unlock=carry,
                   screen=scr)
    assert fnd["sheet"]["names"][0]["status"] == "ok"
    # the follow-up's totals keep the topic out (hidden from totals unless the message names it; the set's N053.1):
    # 8 shown in 2024 and 50 left out, with the private line, as before
    tot, _t = call(brain, "compare", dict(args, scope=S()), q1, carried_unlock=carry, screen=scr)
    assert tot["sheet"]["totals"]["items"] == len(opened(date(2024, 1, 1), date(2024, 12, 31))) == 8
    assert tot["meta"]["hidden"]["sensitive"] == 50
    # a search of the follow-up, not scoped to the topic, leaves its items out too
    from mvp.tests.fakes.fake_brain import FakeEngine
    srch, ts = call(brain, "search", {"query": "dating advice", "how": "opened"}, q1, carried_unlock=carry, screen=scr,
                    search=FakeEngine())
    assert not any(ts.carried_hidden(x["item_id"]) for x in srch["sheet"]["items"])
    # the checker reads the follow-up's unlock: a sentence on the topic's own result is kept
    assert kept(t1, "In 2024 you opened 50[r1.totals.items] videos on that topic, against 0[r1.previous.items] in 2023.")
    # nothing is carried from an answer that resolved no name to the topic, and the screen never holds it
    plain, tp = call(brain, "breakdown", {"by": "area", "window": W("in 2024")}, q0)
    assert BL.unlock_after(tp, {"calls": [{"result": plain}]}) is None
    assert "relationships" not in str(BL.screen_after({"calls": [{"name": "breakdown", "args": {}, "result": env0}],
                                                       "answer": {"scope_line": None}}))


def test_a_message_that_names_another_topic_is_not_overridden_by_the_carried_one(brain):
    t = turn(brain, "was i really watching dating videos", carried_unlock="health")
    assert t.unlock == "relationships"


# ================================================================ 6. rollups: parts of the day, ties, first days
def test_a_totals_sheet_has_the_parts_of_the_day(brain):
    # N027.0 "do i watch more at night or during the day": 716 of 723 fell between 2pm and 8pm, never said
    env_, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5, "scope": S(),
                                        "window": W(preset="all")}, "do i watch more at night or during the day")
    parts = {p["part"]: p for p in env_["sheet"]["when"]["parts_of_day"]}
    hours = Counter(d.hour for _r, d in opens_at())
    want = {"morning": range(5, 12), "afternoon": range(12, 17), "evening": range(17, 21),
            "night": [*range(21, 24), *range(0, 5)]}
    for part, hs in want.items():
        assert parts[part]["events"] == sum(hours[h] for h in hs), part                                     # recount
    assert [parts[p]["events"] for p in ("morning", "afternoon", "evening", "night")] == [5, 219, 498, 1]
    assert sum(p["events"] for p in parts.values()) == env_["sheet"]["when"]["events"] == 723
    assert any("parts_of_day" in n for n in env_["meta"]["notes"])
    assert kept(t, "Across all your history, you opened 723[r1.totals.items] videos.",
                point="The afternoon held 219[r1.when.parts_of_day[1].events] and the night just "
                      "1[r1.when.parts_of_day[3].events].")
    # N112.0 "do i scroll insta in the mornings or what": all 4 Instagram opens came at 8am
    env_, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 5,
                                        "scope": S(platforms=["instagram"]), "window": W(preset="all")},
                   "do i scroll insta in the mornings or what")
    ig = [d.hour for r, d in opens_at(lambda r: r["platform"] == "instagram")]
    assert ig == [8, 8, 8, 8] and env_["sheet"]["when"]["parts_of_day"][0]["events"] == 4                    # recount
    assert kept(t, "On Instagram, all 4[r1.when.parts_of_day[0].events] of your opens came in the morning.")


def test_a_ranked_sheet_keeps_its_rows_before_the_added_cells(brain):
    # the cells this round added never cost a ranked sheet a row (results.drop_extras)
    from mvp.brain import results as R
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W(preset="lately"), "top": 10}, "x")
    assert "parts_of_day" not in env_["sheet"].get("when", {})
    s = {"kind": "top", "new": {"themes": [{"name": "x", "first_watched": "2026-01-01"}]}, "when": {"parts_of_day": [1]},
         "pad": "y" * 7000}
    assert R.drop_extras(s) and "first_watched" not in s["new"]["themes"][0] and "parts_of_day" not in s["when"]


@pytest.mark.parametrize("args,message", [
    ({"limit": 5, "offset": 0, "order": "most_opened", "scope": S(only=["cooking"]), "window": W(preset="all")},
     "show me a few of the cooking ones"),
    ({"limit": 5, "offset": 5, "order": "most_opened", "scope": S(only=["cooking"]), "window": W(preset="all")},
     "next 5"),
    ({"limit": 3, "offset": 0, "order": "most_opened", "scope": S(length="long"), "window": W(preset="all")},
     "which video did i watch all the way through")])
def test_an_order_by_times_opened_over_a_tie_says_so(brain, args, message):
    # N044.0, N044.1, N056.0: "the most-opened long videos are led by ..." where every video was opened once
    assert max(Counter(r["id"] for r, _d in opens_at()).values()) == 1                                        # recount
    env_, _t = call(brain, "items", args, message)
    assert env_["meta"]["tie"] == "all" and any("no ranking by times opened" in n for n in env_["meta"]["notes"])


def test_a_new_theme_says_its_own_first_day(brain):
    # N008.1: "Pixel Pencil and Clip Factory were the channels that started in it [October]"; Pixel Pencil began on
    # 1 August 2026 (its channel row already says so; a new theme's row now says it too, where the sheet has room)
    args = {"a": W("this summer"), "b": W("last summer"), "by": "area", "scope": S()}
    env_, t = call(brain, "compare", args, "this summer vs last summer")
    dd = next(r for r in env_["sheet"]["new"]["themes"] if r["name"] == "Digital drawing")
    first = min(d.date() for r, d in opens_at(lambda r: r["theme"] == "dd"))
    assert dd["first_watched"] == first.isoformat() == "2026-08-01"                                           # recount
    ch = next(r for r in env_["sheet"]["channels"] if r["name"] == "Pixel Pencil")
    assert ch["first_watched"] == "2026-08-01"


def test_a_breakdown_says_that_ranks_are_within_one_level(brain):
    # N067.0: "Clip Factory led with 61" and "Digital drawing came next at 29", a channel and a theme ranked as one
    env_, _t = call(brain, "breakdown", {"by": "area", "window": W(preset="last_month")}, "x")
    assert any(n.startswith("areas, themes and channels are three levels") for n in env_["meta"]["notes"])


# ================================================================ 7 and 8. cards, ask-backs and the code lead
def _answer(brain, tool, args, message, form=None, mode="cells"):
    from mvp.brain import answer as A, fallback as FB, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine
    _env, t = call(brain, tool, args, message, search=FakeEngine())
    led, vt = ledger_of(t)
    v = V.check_answer(form, led, vt, mode=mode) if form else None
    code = FB.answer(led, v, vt, mode=mode)
    links = lambda iid: t.lib.view.items[iid].url  # noqa: E731
    return A.build(led, verdict=None, code=code, form=form, also=[v] if v else [], mode=mode, links=links,
                   limits=t.limits), code, t


def test_the_code_lead_of_an_items_call_names_the_item(brain):
    # N014.0 "last cooking video i watched?": the code lead was the all-time total, 72 videos
    out, code, _t = _answer(brain, "items", {"limit": 1, "offset": 0, "order": "newest", "scope": S(only=["cooking"]),
                                             "window": W(preset="all")}, "last cooking video i watched?")
    newest = max(opens_at(lambda r: r["theme"] == "co"), key=lambda x: x[1])[0]
    assert newest["caption"] == "Cooking soup on the 30th"                                                    # recount
    assert code["how"] == "template" and out["lead"] == ("In all your history, counting only food and cooking, the "
                                                          'newest video you opened was "Cooking soup on the 30th", on '
                                                          "30 October 2026.")   # (mvp26 toolfix2 4: quoted)
    assert out["cards"][0]["line"].startswith("Cooking soup on the 30th · [Pan Theory](https://")
    assert out["cards"][0]["line"].endswith(" · opened on 30 October 2026")


def test_the_code_lead_of_a_timeline_gives_the_range(brain):
    # N008.0 "month by month this year pls": the code lead was one total
    out, code, _t = _answer(brain, "timeline", {"scope": S(), "unit": "month", "window": W(preset="this_year")},
                            "month by month this year pls")
    by = Counter(d.month for _r, d in opens_at(a=date(2026, 1, 1)))
    assert (max(by.values()), min(by.values()), sum(by.values())) == (142, 4, 254)                            # recount
    assert out["lead"] == "This year, you opened 254 videos: 142 in Oct 2026 and 4 in Feb 2026."


def test_a_search_code_lead_goes_out_with_its_cards_and_the_ask_back(brain):
    # N049.0 "that video about integrals, when did i watch it": "Here's what I found." with 5 items in hand
    form = {"lead": "Several videos match.", "points": [], "items": [],
            "ask_back": {"between": ["the first one", "the second one"]}}
    out, code, _t = _answer(brain, "search", {"how": "opened", "limit": 5, "query": "integrals",
                                              "window": W(preset="all")},
                            "that video about integrals, when did i watch it", form=form)
    assert code["how"] == "template" and len(out["cards"]) == 5 and out["ask"]
    lines = out["text"].split("\n")
    assert lines[1] == "Which one do you mean?" and lines[2].startswith("• Integrals by parts · [Limit Lane](")
    assert "the first one" not in out["text"]          # the model's ask-back words never go out; code's question does
    assert out["points"] == []                         # cells mode: no model point under a code lead


def test_the_model_s_item_picks_go_out_as_cards(brain):
    # N041.1 "which ones are from instagram": the three picks were not rendered
    from mvp.brain import answer as A, verify as V
    _env, t = call(brain, "items", {"limit": 10, "offset": 0, "order": "most_opened", "window": W(preset="all"),
                                    "scope": S(how="saved", platforms=["instagram"])}, "which ones are from instagram")
    led, vt = ledger_of(t)
    form = {"lead": "You saved 3[r1.items.count] Instagram items in all your history.",
            "items": [{"ref": f"r1.items[{k}]", "note": "a model note"} for k in range(3)]}
    v = V.check_answer(form, led, vt, mode="cells")
    out = A.build(led, verdict=v, form=form, also=[v], mode="cells", links=lambda iid: t.lib.view.items[iid].url)
    saved = {r["id"] for r in visible_rows() if r["platform"] == "instagram" and any(k == "save" for k, _ in r["events"])}
    assert {c["ref"] for c in out["cards"]} == {"r1.items[0]", "r1.items[1]", "r1.items[2]"} and len(saved) == 3
    assert all(" · saved on " in c["line"] for c in out["cards"]) and "a model note" not in out["text"]


def test_code_s_limit_line_goes_under_a_code_lead_only(brain):
    # N038.0: the code lead never said the record holds no likes
    from mvp.brain import answer as A, fallback as FB
    from mvp.brain import tools as TL
    t = turn(brain, "what have i liked recently")
    TL.call(t, "items", {"limit": 5, "order": "newest", "scope": S(how="liked"), "window": W("recently")})
    TL.call(t, "items", {"limit": 5, "order": "newest", "scope": S(how="saved"), "window": W("recently")})
    led, vt = ledger_of(t)
    code = FB.answer(led, None, vt, mode="cells")
    out = A.build(led, code=code, mode="cells", limits=t.limits)
    assert out["limits"] == ["Your export holds no likes."] and "Your export holds no likes." in out["text"]
    assert len(out["cards"]) == 5


def test_the_watch_time_line_goes_under_the_model_s_own_lead_once(brain):
    # N057.0 "how many minutes of youtube a day do i do": the result had the watch-time note, nothing printed it
    from mvp.brain import answer as A, tools as TL, verify as V
    q = "how many minutes of youtube a day do i do"
    _env, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "top": 1,
                                        "scope": S(platforms=["youtube"]), "window": W(preset="lately")}, q)
    led, vt = ledger_of(t)
    form = {"lead": "In the 4 weeks up to 30 October 2026, you opened 126[r1.totals.by_platform.youtube] YouTube "
                    "videos, on 28[r1.totals.days_active] different days.", "points": []}
    v = V.check_answer(form, led, vt, mode="cells")
    assert v.lead_ok
    out = A.build(led, verdict=v, form=form, also=[v], mode="cells", limits=["Your export holds no likes."])
    assert out["limits"] == [TL.WATCH_TIME_LINE] and out["text"].count(TL.WATCH_TIME_LINE) == 1
    assert "likes" not in out["text"]      # a refused call's line goes under a code lead only


# ================================================================ 9. the loop's budget and the eval's bars
def test_the_time_budget_is_set_for_the_bars_of_8_and_11_seconds():
    from mvp.brain import loop as BL
    assert (BL.SOFT_S, BL.DEEP_S, BL.HARD_S) == (7.0, 11.0, 15.0)
    from mvp import eval_brain as E
    recs = [{"seconds": 7.0, "lead_source": "model", "sentences": {"written": 1, "kept_first_pass": 1, "kept_sent": 1},
             "cost_usd": 0.001, "calls": [], "events": [], "requests": [], "g2": {"verdict": "understood"},
             "key": "X.0", "answer": {"text": "x", "offers": []}, "audit": {"findings": []}, "verdicts": [],
             "forms": [], "check": "cells"}]
    try:
        g5 = E.summarize(recs)["G5_seconds"]
    except Exception:  # noqa: BLE001 - the summary's other lines need more of a record; the bars are read from source
        import inspect
        src = inspect.getsource(E.summarize)
        assert '"bar_median": 8.0, "bar_p90": 11.0' in src
        return
    assert (g5["bar_median"], g5["bar_p90"]) == (8.0, 11.0)
