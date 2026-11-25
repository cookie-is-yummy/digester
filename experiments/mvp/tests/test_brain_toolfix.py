"""The read tools' faults that the checkers of the thin live slice found (scratchpad mvp20: result.json judges and fix,
the attack's out/). Each fault is reproduced here on the made-up library of tests/brain_library.py, with a recount
from the library's own rows (test_brain_tools' helpers, which share nothing with facts.py). Offline: no model call, no
network. Every title, channel, handle and theme is made up."""
import json
import os
import sys
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures and the recount helpers)
    NOW, OCTOBER, B, GAMING, brain, built, call, local, no_real_keys, opened, person, turn, visible_rows)

ROWS = {r["id"]: r for r in B.rows()}
I02 = "my partner thinks i watched a lot of dating advice in 2024, did i?"   # held-out I02.0: unlocks relationships
PLAIN_2024 = "what did i watch in 2024"
Y2024 = (date(2024, 1, 1), date(2024, 12, 31))


def W(words):
    return {"words": words}


def ever_touched(pred):
    """Ids of visible rows (the sensitive one included) with any event, that `pred` keeps."""
    return {r["id"] for r in visible_rows(unlock_sensitive=True) if r["events"] and pred(r)}


# ================================================================ 1. an unlocked topic has its theme and area rows
@pytest.mark.parametrize("by", ["none", "theme", "area"])
def test_an_unlocked_topic_has_its_own_theme_and_area_rows(brain, by):
    env_, t = call(brain, "breakdown", {"by": by, "window": W("2024"), "compare": "none"}, I02)
    assert t.unlock == "relationships"
    s = env_["sheet"]
    da = opened(*Y2024, keys={"da"}, unlock_sensitive=True)
    total = opened(*Y2024, unlock_sensitive=True)
    assert s["totals"]["items"] == len(total) == 58                                            # recount
    th = {r["name"]: r for r in s["themes"]}
    ar = {r["name"]: r for r in s["areas"]}
    assert th["relationships"]["items"] == len(da) == 50 and ar["relationships"]["items"] == 50
    assert th["relationships"]["share"] == round(50 / 58, 4) and ar["relationships"]["share"] == round(50 / 58, 4)
    # ranked where its count puts it: 50 leads Home cooking's 8 (held-out I02.0 said Home cooking was the top theme)
    assert s["themes"][0]["name"] == "relationships" and s["areas"][0]["name"] == "relationships"
    assert sum(r["items"] for r in s["themes"]) == s["totals"]["items"]
    assert th["relationships"]["area"] == "relationships"
    assert env_["meta"]["rows_of"]["themes"] == len(s["themes"]) and env_["meta"]["rows_of"]["areas"] == len(s["areas"])
    assert env_["meta"]["hidden"]["sensitive"] == 0


def test_an_unlocked_topic_row_carries_the_window_before(brain):
    env_, _t = call(brain, "breakdown", {"by": "theme", "window": W("2024")}, I02)
    row = next(r for r in env_["sheet"]["themes"] if r["name"] == "relationships")
    before = opened(date(2023, 1, 1), date(2023, 12, 31), keys={"da"}, unlock_sensitive=True)
    assert row["previous_items"] == len(before)
    assert row["change_vs_previous"] == round((row["share"] - row["previous_share"]) * 100, 1)


def test_a_locked_turn_has_no_row_of_the_topic_and_is_as_before(brain):
    env_, t = call(brain, "breakdown", {"by": "theme", "window": W("2024")}, PLAIN_2024)
    assert t.unlock is None
    s = env_["sheet"]
    assert [(r["name"], r["items"]) for r in s["themes"]] == [("Home cooking", 8)]
    assert [(r["name"], r["items"]) for r in s["areas"]] == [("food and cooking", 8)]
    assert "relationships" not in json.dumps(env_) and "Heart Notes" not in json.dumps(env_)
    assert env_["meta"]["hidden"]["sensitive"] == 50 and env_["meta"]["hidden"]["rank_hidden_above"] is True


# ================================================================ 2. find resolves an unlocked topic
def test_find_resolves_the_unlocked_topic_and_its_three_counts_agree(brain):
    env_, _t = call(brain, "find", {"names": ["dating advice", "dating"], "kinds": ["theme", "words", "channel"]},
                    I02)
    rows = env_["sheet"]["names"]
    assert [r["status"] for r in rows] == ["ok", "ok"]
    m = rows[0]["matches"][0]
    assert m["ref"] == "topic:relationships" and m["label"] == "relationships" and m["how"] == "private topic"
    da_ever = ever_touched(lambda r: r["theme"] == "da")
    assert m["items_all_time"] == len(da_ever) == 50                                            # recount
    assert rows[1]["matches"][0]["ref"] == "topic:relationships"   # the topic wins over the 33 titles with "dating"
    # the same topic as a scope, all time, and as the row of a breakdown: one number
    all_, _t = call(brain, "breakdown", {"by": "theme", "window": {"preset": "all"},
                                         "scope": {"only": ["dating advice"], "how": "any"}}, I02)
    assert all_["sheet"]["totals"]["items"] == 50
    assert all_["sheet"]["themes"][0]["items"] == 50 and all_["sheet"]["themes"][0]["name"] == "relationships"
    y, _t = call(brain, "breakdown", {"by": "none", "window": W("2024"), "scope": {"only": ["dating advice"]}}, I02)
    assert not y.get("error") and y["sheet"]["totals"]["items"] == 50
    # the typed ref the find gave is accepted by the other tools
    y2, _t = call(brain, "breakdown", {"by": "none", "window": W("2024"), "scope": {"only": ["topic:relationships"]}},
                  I02)
    assert y2["sheet"]["totals"]["items"] == 50
    # without it: everything else
    y3, _t = call(brain, "breakdown", {"by": "none", "window": W("2024"), "scope": {"exclude": ["dating advice"]}},
                  I02)
    assert y3["sheet"]["totals"]["items"] == 8


def test_a_locked_topic_is_still_no_match_with_no_options(brain):
    for name in ("dating advice", "topic:relationships", "relationships"):
        env_, _t = call(brain, "find", {"names": [name]}, PLAIN_2024)
        row = env_["sheet"]["names"][0]
        assert row["status"] == "no_match" and not row["matches"], name
        assert "relationships" not in json.dumps(row["options"]) and "Heart" not in json.dumps(row["options"])
    # another sensitive topic does not unlock this one
    env_, t = call(brain, "find", {"names": ["dating advice"]}, "my stock market videos")
    assert t.unlock == "money" and env_["sheet"]["names"][0]["status"] == "no_match"


# ================================================================ 3. a day's items are in the order said
@pytest.mark.parametrize("order", ["newest", "oldest", "most_opened"])
def test_the_items_of_a_day_come_in_the_order_meta_says(brain, order):
    env_, _t = call(brain, "items", {"window": W("on 30 October"), "order": order, "limit": 10},
                    "what did i watch on 30 October")
    got = [x["item_id"] for x in env_["sheet"]["items"]]
    day = date(2026, 10, 30)
    evs = sorted((at, i) for i in opened(day, day) for k, at in ROWS[i]["events"]
                 if k == "watch" and local(at) == day)
    oldest = [i for _at, i in evs]
    assert len(got) == len(oldest) == 4
    if order == "oldest":
        assert got == oldest
    elif order == "newest":
        assert got == oldest[::-1]
    else:   # most opened that day first; a tie keeps time order
        n = {i: sum(1 for _at, j in evs if j == i) for i in oldest}
        assert got == sorted(oldest, key=lambda i: -n[i])
    assert env_["meta"]["order"] == order


def test_the_offset_of_a_day_is_taken_after_its_order(brain):
    full, _t = call(brain, "items", {"window": W("on 30 October"), "order": "newest", "limit": 10},
                    "what did i watch on 30 October")
    page, _t = call(brain, "items", {"window": W("on 30 October"), "order": "newest", "limit": 2, "offset": 2},
                    "what did i watch on 30 October")
    assert [x["item_id"] for x in page["sheet"]["items"]] == [x["item_id"] for x in full["sheet"]["items"]][2:4]
    assert [x["ref"] for x in page["sheet"]["items"]] == ["r1.items[0]", "r1.items[1]"]


# ================================================================ 4. Instagram reels have a cell of their own
def _reel(r):
    return r["platform"] == "instagram" and (r.get("media") or "reel") in ("reel", "video")


def test_reels_are_counted_in_a_cell_beside_shorts(brain):
    env_, _t = call(brain, "breakdown", {"by": "area", "window": W("October"), "scope": {"exclude": ["gaming"]}},
                    "October without gaming")
    tot = env_["sheet"]["totals"]
    reels = opened(*OCTOBER, pred=lambda r: _reel(r) and r["theme"] not in GAMING)
    assert tot["reels"] == len(reels) == 4 and tot["shorts"] == 0                                # recount
    assert tot["by_platform"]["instagram"] == 4
    short, _t = call(brain, "breakdown", {"by": "area", "window": W("October"), "scope": {"length": "short"}},
                     "October only shorts")
    st = short["sheet"]["totals"]
    assert st["items"] == st["shorts"] + st["reels"] == 70                                       # the filter's own set
    long_, _t = call(brain, "breakdown", {"by": "area", "window": W("October"), "scope": {"length": "long"}},
                     "October only long videos")
    assert long_["sheet"]["totals"]["reels"] == 0
    assert "previous" not in long_["sheet"] or "reels" in long_["sheet"]["previous"]
    assert any("reels" in n and "Shorts" in n for n in env_["meta"]["notes"])


def test_the_reels_cell_agrees_with_the_length_words_of_the_items(brain):
    env_, _t = call(brain, "first_last", {"subject": "watercolor", "which": "last"}, "my last watercolor video")
    tot = env_["sheet"]["totals"]
    reels = ever_touched(lambda r: _reel(r) and r["theme"] == "wc" and any(k == "watch" for k, _a in r["events"]))
    assert tot["reels"] == len(reels) == 4
    ig = [x for x in env_["sheet"]["items"] if x["platform"] == "instagram"]
    assert ig and all(x["length"] == "short" for x in ig)


# ================================================================ 5. a compare of windows of unequal days says so
def test_a_compare_cut_at_the_export_end_says_both_windows_days(brain):
    env_, _t = call(brain, "compare", {"a": W("this autumn"), "b": W("last autumn")}, "this autumn against last autumn")
    m = env_["meta"]
    assert m["windows"] == {"a": {"start": "2026-09-01", "end": "2026-10-30", "days": 60},
                            "b": {"start": "2025-09-01", "end": "2025-11-30", "days": 91}}
    assert m["same_days"] is False
    note = next(n for n in m["notes"] if "days" in n and "60" in n)
    assert "91" in note and "30 October 2026" in note and "30 November 2025" in note
    # the other way round, the cut is on b
    rev, _t = call(brain, "compare", {"a": W("last autumn"), "b": W("this autumn")}, "last autumn against this autumn")
    assert rev["meta"]["windows"]["a"]["days"] == 91 and rev["meta"]["windows"]["b"]["days"] == 60
    assert rev["meta"]["same_days"] is False


def test_a_compare_of_equal_windows_has_no_days_note(brain):
    env_, _t = call(brain, "compare", {"a": W("2023"), "b": W("2022")}, "2023 against 2022")
    m = env_["meta"]
    assert m["windows"]["a"]["days"] == m["windows"]["b"]["days"] == 365 and m["same_days"] is True
    assert not any("days" in n and "365" in n for n in m["notes"])


# ================================================================ 6. a no-match result has a cell a sentence can cite
def test_a_name_with_no_match_carries_how_many_items_hold_its_words(brain):
    env_, _t = call(brain, "find", {"names": ["knitting", "soup"]}, "did i watch anything about knitting or soup")
    k, s = env_["sheet"]["names"]
    assert k["status"] == s["status"] == "no_match"
    assert k["searched"] == "knitting" and k["items_with_words"] == 0
    soup = ever_touched(lambda r: "soup" in r["caption"].lower())
    assert s["searched"] == "soup" and s["items_with_words"] == len(soup) == 1                   # recount
    assert k["row"] == "r1.names[0]"
    # the count leaves the private topics out, and never says how many (a constant asks for the private line)
    assert env_["meta"]["hidden"] == {"sensitive": 1, "friends": 0, "rank_hidden_above": True}


def test_a_words_count_never_says_whether_a_private_title_holds_the_words(brain):
    # "Heart Notes" is a private channel on a locked turn: its count is of what they may see (0), with the same
    # constant as any other words count, so a name cannot be probed for private items by the cell or by the meta
    hid, _t = call(brain, "find", {"names": ["Heart Notes"]}, PLAIN_2024)
    open_, _t = call(brain, "find", {"names": ["knitting"]}, PLAIN_2024)
    h, o = hid["sheet"]["names"][0], open_["sheet"]["names"][0]
    assert h["status"] == o["status"] == "no_match" and h["items_with_words"] == o["items_with_words"] == 0
    assert hid["meta"]["hidden"] == open_["meta"]["hidden"] and not h["options"]


def test_a_counting_tool_given_no_match_carries_the_same_cell(brain):
    env_, _t = call(brain, "breakdown", {"by": "none", "window": {"preset": "all"}, "scope": {"only": ["knitting"]}},
                    "did i watch anything about knitting")
    assert env_["error"] == "no_match" and env_["searched"] == "knitting" and env_["items_with_words"] == 0


def test_a_locked_private_name_has_no_count(brain):
    env_, _t = call(brain, "find", {"names": ["dating advice"]}, PLAIN_2024)
    row = env_["sheet"]["names"][0]
    assert row["status"] == "no_match" and "items_with_words" not in row
    u, _t = call(brain, "breakdown", {"by": "none", "window": W("2024"), "scope": {"only": ["dating"]}}, PLAIN_2024)
    assert u["error"] == "no_match" and "items_with_words" not in u


# ================================================================ 7. an Instagram channel: its handle apart, its name
def test_an_instagram_channel_row_keeps_its_handle_as_its_own_field(brain):
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W("in October")}, "which channels in October")
    rows = {r["name"]: r for r in env_["sheet"]["channels"]}
    ig = rows["@wetpaper.ig"]   # the made-up library has no display name for it: the handle stays its name
    assert ig["handle"] == "wetpaper.ig" and ig["items"] == 4
    assert "handle" not in rows["Clip Factory"]   # a YouTube channel has no handle of its own here


def _with_display(brain, monkeypatch, name):
    from mvp.brain import tools as TL
    t = TL.Turn(brain["bot"], person(brain), NOW, message="which channels in October")
    for it in t.lib.view.items.values():
        if it.creator == "@wetpaper.ig":
            monkeypatch.setattr(it, "display", name)
    return t


def test_an_instagram_channel_with_a_display_name_is_named_by_it(brain, monkeypatch):
    from mvp.brain import tools as TL
    t = _with_display(brain, monkeypatch, "Wet Paper Studio")
    env_ = TL.call(t, "breakdown", {"by": "channel", "window": W("in October")})
    row = next(r for r in env_["sheet"]["channels"] if r.get("handle") == "wetpaper.ig")
    assert row["name"] == "Wet Paper Studio" and row["items"] == 4
    f = TL.call(t, "find", {"names": ["Wet Paper Studio", "@wetpaper.ig"]})
    refs = [r["matches"][0]["ref"] for r in f["sheet"]["names"]]
    assert refs[0] == refs[1] and refs[0].startswith("channel:")
    assert f["sheet"]["names"][0]["matches"][0]["label"] == "Wet Paper Studio"


def test_a_display_name_that_is_another_channels_name_is_not_used(brain, monkeypatch):
    from mvp.brain import tools as TL
    t = _with_display(brain, monkeypatch, "Wet Paper")   # the YouTube channel's name
    env_ = TL.call(t, "breakdown", {"by": "channel", "window": W("in October")})
    names = [r["name"] for r in env_["sheet"]["channels"]]
    assert names.count("Wet Paper") == 1 and "@wetpaper.ig" in names


# ================================================================ 8. friends are counted in the result's own window
@pytest.mark.parametrize("words,how,scope,want", [
    ("2024", "opened", {}, 0),               # the friend's post is a save of 9 October 2026
    ("October", "opened", {}, 0),
    ("October", "saved", {}, 1),
    ("October", "any", {}, 1),
    ("September", "saved", {}, 0),
    ("October", "saved", {"platforms": ["youtube"]}, 0),
    ("October", "saved", {"only": ["cooking"]}, 0),   # a friend's post is never placed in a theme or a channel
])
def test_friends_left_out_are_counted_in_the_results_window_and_base(brain, words, how, scope, want):
    env_, _t = call(brain, "breakdown", {"by": "channel", "window": W(words), "scope": dict(scope, how=how)},
                    f"what did i {how} in {words}")
    friend = [r for r in B.rows() if r.get("friend")]
    assert len(friend) == 1 and friend[0]["events"] == [("save", "2026-10-09T15:00:00+00:00")]
    assert env_["meta"]["hidden"]["friends"] == want


# ================================================================ 9. a long timeline is whole or says it is cut
def test_a_month_timeline_of_all_history_keeps_every_month_or_says_it_is_cut(brain):
    env_, _t = call(brain, "timeline", {"unit": "month", "window": {"preset": "all"}}, "by month")
    periods = env_["sheet"]["periods"]
    months = (2026 - 2021) * 12 + 10   # January 2021 to October 2026
    assert env_["meta"]["rows_of"]["periods"] == months
    if len(periods) < months:
        assert env_["meta"]["complete"] is False and env_["meta"]["truncated"] is True
    else:
        assert env_["meta"]["complete"] is True
    # the newest months are never the ones cut: October 2026 is in it
    assert periods[-1]["label"] == "Oct 2026"
    assert periods[-1]["items"] == len(opened(date(2026, 10, 1), date(2026, 10, 31)))
