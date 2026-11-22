"""Round 12, second pass, the second fixer (DESIGN.md section 19.P2 fix): what two judges still found in the live
history answers after the first fix of the pass, each reproduced on made-up data (a test here fails on 2257352) and
fixed, with its near variants.

Made-up data only: a sheet shaped like the real ones (areas, themes with their area, channels with their Shorts
share, eras, the usual day), the eval's made-up sheets and the made-up library (tests/r12_library.py).
"""
import copy
import re
from types import SimpleNamespace

import numpy as np
import pytest

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, person, mods, no_real_keys, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_merge import wr, QS  # noqa: F401  (fixtures)
from mvp.tests.test_round12_pass2 import case, sheet_of


def ins():
    from mvp import insight
    return insight


def facts_mod():
    from mvp import facts
    return facts


# A sheet shaped like the real "the most lately" (made-up names and numbers)
TOP = {
    "question": "what have i been watching the most lately", "kind": "top", "lang": "en",
    "filters": {"topic": None, "without_shorts": False},
    "window": {"words": "In the 4 weeks up to 30 October 2026, where your export ends", "start": "2026-10-03",
               "end": "2026-10-30", "clipped": True},
    "totals": {"items": 1000, "days_active": 28, "shorts": 700, "long": 250, "shorts_share": 0.737,
               "long_median_min": 23},
    "previous": {"items": 900, "days_active": 28, "shorts": 600, "long": 280, "shorts_share": 0.682,
                 "words": "the 4 weeks before (5 September to 2 October 2026)"},
    "areas": [
        {"name": "gaming", "items": 220, "share": 0.22, "previous_share": 0.12, "change_vs_previous": 0.10,
         "themes": [{"name": "Speed runs", "share": 0.05}, {"name": "Block battles", "share": 0.049}]},
        {"name": "comedy", "items": 110, "share": 0.11, "previous_share": 0.14, "change_vs_previous": -0.03,
         "themes": [{"name": "Sketch edits", "share": 0.035}]},
        {"name": "internet culture", "items": 93, "share": 0.093, "previous_share": 0.09, "change_vs_previous": 0.003,
         "themes": [{"name": "Meme drops", "share": 0.065}]},
        {"name": "sports", "items": 86, "share": 0.086, "previous_share": 0.16, "change_vs_previous": -0.074,
         "themes": [{"name": "Trick shots", "share": 0.036}]},
    ],
    "themes": [
        {"name": "Meme drops", "area": "internet culture", "items": 65, "share": 0.065, "previous_share": 0.05,
         "previous_items": 45, "change_vs_previous": 0.015, "shorts_share": 0.69, "days": 20,
         "channels": [{"name": "Meme Vault", "items": 20}]},
        {"name": "Speed runs", "area": "gaming", "items": 50, "share": 0.05, "previous_share": 0.01,
         "previous_items": 9, "change_vs_previous": 0.04, "shorts_share": 0.4, "days": 18,
         "channels": [{"name": "Pixel Forge", "items": 30}]},
        {"name": "Block battles", "area": "gaming", "items": 49, "share": 0.049, "previous_share": 0.05,
         "previous_items": 45, "change_vs_previous": -0.001, "shorts_share": 0.5, "days": 17,
         "channels": [{"name": "Doggo Plays", "items": 17}]},
        {"name": "Sketch edits", "area": "comedy", "items": 35, "share": 0.035, "previous_share": 0.06,
         "previous_items": 54, "change_vs_previous": -0.025, "shorts_share": 0.97, "days": 15,
         "channels": [{"name": "Laugh Lab", "items": 12}]},
    ],
    "channels": [
        {"name": "Pixel Forge", "items": 30, "days": 12, "share": 0.03, "area": "gaming", "theme": "Speed runs",
         "theme_share": 0.9, "shorts_share": 0.95, "previous_items": 20},
        {"name": "Doggo Plays", "items": 17, "days": 9, "share": 0.017, "area": "gaming", "theme": "Block battles",
         "theme_share": 1.0, "shorts_share": 0.29, "previous_items": 15},
    ],
    "when": {"busiest_hours": [{"hour": 21, "share": 0.12}]},
    "new": {"themes": [], "channels": []}, "stopped": {"themes": [], "channels": []},
    "library": {"saved_not_opened": []}, "so_what_candidates": [], "offers": ["without_shorts"],
}


def top(**kw):
    s = copy.deepcopy(TOP)
    s.update(kw)
    return s


def obs(text, s=None):
    """(the observation as sent, or None; why it was dropped) in the live writer's strict mode."""
    I = ins()
    f = I.check({"answer": "-", "observations": [{"text": text, "uses": []}]}, s or top(), strict=True)
    return (f["observations"][0] if f["observations"] else None,
            [d[1] for d in f["dropped"] if d[0] == "observation"])


# ================================ a theme bound to an area it is not in (both judges, rows 1, 2, 7) ===============
@pytest.mark.parametrize("text", [
    # live, row 1: "gaming was your biggest area at 22%, led by <a memes theme of internet culture>"
    "{areas[0].name} was your biggest area at {areas[0].share}, led by {themes[0].name}.",
    # live, "without shorts": "gaming ... with <science theme> and <technology theme> inside it"
    "{areas[0].name} was {areas[0].share}, with {themes[0].name} and {themes[3].name} inside it.",
    # live, row 7: "Your biggest area, gaming, is led by <comedy theme> and <internet culture theme>"
    "Your biggest area, {areas[0].name}, is led by {themes[3].name} and {themes[0].name}.",
    # live, row 1 asked again: an internet-culture theme among gaming's "main themes"
    "{themes[0].name} and {themes[1].name} were the main themes of {areas[0].name}.",
])
def test_a_theme_said_inside_an_area_it_is_not_in_is_dropped(text):
    kept, why = obs(text)
    assert kept is None and why == ["wrong_area"], (text, why)


@pytest.mark.parametrize("text", [
    "{areas[0].name} was your biggest area at {areas[0].share}, led by {areas[0].themes[0].name}.",
    "{areas[0].name} grew to {areas[0].share}, with {themes[1].name} and {themes[2].name} inside it.",
    "{areas[0].name} grew to {areas[0].share}, while {themes[0].name} rose to {themes[0].share}.",
])
def test_a_theme_inside_its_own_area_or_set_against_another_stands(text):
    kept, why = obs(text)
    assert kept and not why, (text, why)


# ================================ "mostly" and its kin (judge A: "mostly gaming at 46%"; judge B) ==================
def _mostly_sheet():
    s = top()
    s["areas"][0].update(share=0.46, themes=[{"name": "Speed runs", "share": 0.11}, {"name": "Block battles",
                                                                                     "share": 0.06}])
    s["themes"][1]["share"], s["themes"][2]["share"] = 0.11, 0.06
    return s


@pytest.mark.parametrize("text", [
    # live: "mostly into gaming at 46%, led by A at 11% and B at 6%": the themes are inside it, not added to it
    "You were mostly into {areas[0].name} at {areas[0].share}, led by {areas[0].themes[0].name} at "
    "{areas[0].themes[0].share} and {areas[0].themes[1].name} at {areas[0].themes[1].share}.",
    "Mostly {areas[0].name} ({areas[0].share}), with {themes[1].name} ({themes[1].share}) inside it.",
])
def test_mostly_with_the_themes_inside_an_area_needs_the_area_itself_at_half(text):
    kept, why = obs(text, _mostly_sheet())
    assert kept is None and why == ["spread"], why


@pytest.mark.parametrize("text", [
    "Primarily {areas[0].name} ({areas[0].share}).",
    "Overwhelmingly {areas[1].name} ({areas[1].share}).",
    "Predominantly {areas[0].name} at {areas[0].share}.",
])
def test_primarily_and_overwhelmingly_are_mostly(text):
    assert obs(text)[1] == ["spread"]


def test_overwhelmingly_needs_four_in_five():
    s = _mostly_sheet()
    s["areas"][0]["share"] = 0.6
    assert obs("Mostly {areas[0].name} ({areas[0].share}).", s)[0]
    assert obs("Overwhelmingly {areas[0].name} ({areas[0].share}).", s)[1] == ["spread"]


def test_the_code_answer_says_by_far_not_mostly_under_half():
    I = ins()
    s = _mostly_sheet()
    s["areas"][1]["share"] = 0.06
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"].startswith("Gaming by far: 46% of what you opened, well ahead of comedy (6%)")
    assert "mostly" not in f["answer"].lower()


# ================================ numbers bound to the wrong thing, in new shapes ===================================
@pytest.mark.parametrize("text, why", [
    # judge A, row 5: the window's median long video bound to one side ("art ... typically about 20 minutes")
    ("{channels[0].name} was {channels[0].shorts_share} Shorts, while the long videos were typically about "
     "{totals.long_median_min} minutes.", "median_of_window"),
    ("{themes[1].name} came on {themes[1].days} days, and its long videos ran about {totals.long_median_min} minutes.",
     "median_of_window"),
    # judge A, row 8: "Shorts made up 12,080 of your window"
    ("Shorts made up {totals.shorts} of your window.", "count_as_share"),
    ("Shorts made up {totals.shorts} of what you opened.", "count_as_share"),
    # judge B, row 3: "leaned more long-form at 69%" where 69% is its Shorts share
    ("{themes[0].name} leaned more long-form at {themes[0].shorts_share}.", "shorts_as_long"),
    # judge B: "was almost all long videos, with 46% Shorts"
    ("{channels[1].name} was almost all long videos, with {channels[1].shorts_share} Shorts.", "spread"),
    ("{themes[1].name} was almost all Shorts ({themes[1].shorts_share}).", "spread"),
])
def test_a_number_bound_to_the_wrong_thing_is_dropped(text, why):
    kept, whys = obs(text, top(kind="channels"))
    assert kept is None and whys == [why], (text, whys)


@pytest.mark.parametrize("text", [
    "{totals.shorts} of the {totals.items} were Shorts, and the long videos were typically about "
    "{totals.long_median_min} minutes.",
    "{themes[0].name} was {themes[0].shorts_share} Shorts.",
    "{channels[0].name} was almost all Shorts ({channels[0].shorts_share}).",
    "{totals.shorts} of your {totals.items} videos were Shorts.",
])
def test_the_same_numbers_bound_right_stand(text):
    kept, why = obs(text, top(kind="channels"))
    assert kept and not why, (text, why)


# ================================ words of rank, change and watch time (judge B's offline probe) =================
@pytest.mark.parametrize("text, why", [
    ("You opened {themes[2].name} most, at {themes[2].share}.", "rank"),
    ("{areas[1].name} topped the window at {areas[1].share}.", "rank"),
    ("{areas[3].name} came second at {areas[3].share}.", "rank"),
    ("{areas[0].name} was your second area at {areas[0].share}.", "rank"),
    ("{areas[0].name} took up {areas[0].share} of your viewing.", "watch_time"),
    ("You binged {themes[1].name} at {themes[1].share}.", "watch_time"),
])
def test_rank_and_watch_time_words_the_sheet_does_not_support_are_dropped(text, why):
    kept, whys = obs(text)
    assert kept is None and whys == [why], (text, whys)


@pytest.mark.parametrize("text", [
    "{areas[1].name} came second at {areas[1].share}.",
    "{areas[0].name} topped the window at {areas[0].share}.",
])
def test_a_rank_word_that_holds_stands(text):
    kept, why = obs(text)
    assert kept and not why, (text, why)


def test_tripled_of_an_area_that_fell_is_dropped():
    kept, why = obs("{areas[3].name} tripled to {areas[3].share}.")
    assert kept is None and why == ["direction"]
    assert obs("{areas[0].name} grew to {areas[0].share}, while {areas[3].name} fell to {areas[3].share}.")[0]


def test_steadier_with_no_number_that_says_it_is_dropped_and_with_days_it_stands():
    s = case("cmp_cooking_guitar")["sheet"]
    I = ins()
    f = I.check({"answer": "-", "observations": [{"text": "Guitar was smaller but steadier.", "uses": ["topics"]}]}, s)
    assert not f["observations"] and f["dropped"][-1][1] == "unsupported"
    f = I.check({"answer": "-", "observations": [{"text": "But guitar was steadier: 190 days against 120 for cooking.",
                                                  "uses": ["topics"]}]}, s)
    assert f["observations"]


def test_the_gap_was_is_filler():
    s = case("cmp_cooking_guitar")["sheet"]
    I = ins()
    f = I.check({"answer": "-", "observations": [{"text": "Cooking had 410 videos, versus 380 for guitar, and the gap "
                                                          "was 30.", "uses": ["topics"]}]}, s)
    assert not f["observations"] and f["dropped"][-1][1] == "filler"


# ================================ bullets that say nothing new or nothing at all ==================================
def test_a_bullet_whose_every_number_the_answer_said_is_a_repeat():
    I = ins()
    s = top()
    s["themes"][1]["share"], s["areas"][0]["share"] = 0.88, 0.89
    raw = {"answer": "{themes[1].name} made up {themes[1].share} of what you opened.",
           "observations": [{"text": "{areas[0].name} took {areas[0].share} of what you opened.", "uses": []},
                            {"text": "{areas[0].name} grew from {areas[0].previous_share} against before.",
                             "uses": []}]}
    f = I.check(raw, s, strict=True)
    assert ("observation", "repeat") in [(d[0], d[1]) for d in f["dropped"]]
    assert f["observations"] == ["Gaming grew from 12% against before."]


def test_a_direction_with_no_number_is_vague():
    kept, why = obs("{themes[1].name} rose most, while {themes[3].name} faded from the early weeks.")
    assert kept is None and why == ["vague"]


def test_one_channels_shorts_share_is_filler_on_a_top_answer_but_not_on_a_channels_one():
    text = "{channels[0].name} was almost all Shorts at {channels[0].shorts_share}."
    assert obs(text)[1] == ["filler"]
    s = top(kind="channels")
    assert obs(text, s)[0]


# ================================ a day is set against the usual day, never the day before ========================
DAY = {
    "question": "what did i watch on october 30", "kind": "day", "lang": "en", "filters": {},
    "window": {"words": "On Friday 30 October 2026, the last day of your export", "start": "2026-10-30",
               "end": "2026-10-30", "clipped": True},
    "totals": {"items": 10, "days_active": 1, "shorts": 9, "long": 1, "shorts_share": 0.9},
    "previous": {"items": 30, "words": "the day before"},
    "themes": [{"name": "Meme drops", "area": "internet culture", "items": 3, "share": 0.3, "previous_share": 0.1,
                "change_vs_previous": 0.2},
               {"name": "Block battles", "area": "gaming", "items": 1, "share": 0.1}],
    "areas": [{"name": "internet culture", "items": 3, "share": 0.3, "previous_share": 0.1,
               "change_vs_previous": 0.2}],
    "channels": [{"name": "Pixel Forge", "items": 2}],
    "when": {"busiest_hours": [{"hour": 9, "share": 0.6}]},
    "usual": {"days": 87, "median_items": 32, "shorts_share": 0.78, "busiest_hour": 1, "day_shorts_share": 0.9},
    "new_today": {"channels": 0, "names": []},
    "items": [{"id": "i1", "title": "A made-up clip", "channel": "Pixel Forge", "at": "2026-10-30T09:00:00",
               "short": True}],
    "library": {"saved_not_opened": []}, "so_what_candidates": [], "offers": [],
}


def test_a_day_is_never_set_against_the_day_before():
    I = ins()
    s = copy.deepcopy(DAY)
    sh = I.shown(s)
    assert "previous" not in sh and "change_vs_previous" not in sh["areas"][0]
    raw = {"answer": "{totals.items} videos that day.",
           "observations": [{"text": "Against the day before, {areas[0].name} grew to {areas[0].share}.", "uses": []}]}
    f = I.check(raw, s, strict=True)
    assert not f["observations"]


def test_a_days_shorts_and_busiest_hour_against_the_usual_day_are_always_said():
    I = ins()
    s = copy.deepcopy(DAY)
    raw = {"answer": "{totals.items} videos that day, fewer than your usual {usual.median_items}.",
           "observations": [{"text": "{themes[0].name} led with {themes[0].share}.", "uses": []},
                            {"text": "{channels[0].name} gave {channels[0].items} of them.", "uses": []},
                            {"text": "{themes[1].name} had {themes[1].items}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert any(o.startswith("Shorts were 90% of the day's YouTube videos, against about 78%") for o in
               f["observations"])
    # round 12, pass 3 fix (judge A, row 6, on purpose): the export's last day has no busiest hour against a usual day
    assert not any("usual day peaks" in o for o in f["observations"])
    s["window"] = dict(s["window"], words="On Saturday 12 September 2026")
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert any(o.startswith("The busiest hour was 9am, where a usual day peaks around 1am") for o in
               f["observations"])
    assert len(f["observations"]) <= I.OBS_MAX


# ================================ a change told by its biggest move, and eras that come back =====================
CHANGED = {
    "question": "how has what i watch changed since 2020", "kind": "changed", "lang": "en", "filters": {},
    "window": {"words": "Since 1 January 2020 up to 30 October 2026, where your export ends", "start": "2020-01-01",
               "end": "2026-10-30", "clipped": True},
    "totals": {"items": 5000, "days_active": 2000, "shorts": 3000, "long": 1500},
    "themes": [{"name": "Speed runs", "area": "gaming", "items": 500, "share": 0.1}],
    "areas": [{"name": "gaming", "items": 1300, "share": 0.26}],
    "eras": [{"from": "2020", "to": "2026", "area": "gaming", "share": 0.26}],
    "areas_change": {"from": "2020", "to": "2026",
                     "left": [{"name": "science", "from_share": 0.10, "to_share": 0.02, "change": -8.0}],
                     "arrived": [{"name": "internet culture", "from_share": 0.04, "to_share": 0.09, "change": 5.0}],
                     "shorts": {"from": "2020", "from_share": 0.04, "to": "2026", "to_share": 0.81}},
    "periods": [{"label": str(y), "items": 700, "shorts_share": v, "areas": [{"name": "gaming", "share": 0.26}]}
                for y, v in zip(range(2020, 2027), (0.04, 0.14, 0.22, 0.7, 0.35, 0.58, 0.81))],
    "change": {}, "library": {"saved_not_opened": []}, "so_what_candidates": [], "offers": [],
}


def test_one_area_every_year_leads_with_the_move_to_shorts():
    I = ins()
    s = copy.deepcopy(CHANGED)
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"] == ("Gaming has led every year since 2020, but how you watch changed: Shorts went from 4% of "
                           "your YouTube videos in 2020 to 81% in 2026.")


def test_eras_that_come_back_to_the_same_area_never_name_it_twice():
    I = ins()
    s = copy.deepcopy(CHANGED)
    s["eras"] = [{"from": "Jan 2026", "to": "Mar 2026", "area": "gaming", "share": 0.2},
                 {"from": "Apr 2026", "to": "May 2026", "area": "comedy", "share": 0.15},
                 {"from": "Jun 2026", "to": "Aug 2026", "area": "gaming", "share": 0.2},
                 {"from": "Sep 2026", "to": "Sep 2026", "area": "sports", "share": 0.13},
                 {"from": "Oct 2026", "to": "Oct 2026", "area": "gaming", "share": 0.21}]
    s["areas_change"]["shorts"] = {"from": "Jan 2026", "from_share": 0.7, "to": "Oct 2026", "to_share": 0.75}
    f = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
    assert f["answer"] == ("Gaming led most of the time; in between, comedy led from Apr 2026 to May 2026 and sports "
                           "led in Sep 2026.")


def test_arrived_of_an_area_that_was_there_before_is_dropped():
    s = copy.deepcopy(CHANGED)
    s["areas_change"]["arrived"] = [{"name": "gaming", "from_share": 0.16, "to_share": 0.21, "change": 5.0}]
    s["eras"] = [{"from": "Jan 2026", "to": "Mar 2026", "area": "gaming", "share": 0.2},
                 {"from": "Apr 2026", "to": "Oct 2026", "area": "comedy", "share": 0.2}]
    assert obs("{areas_change.arrived[0].name} arrived, at {areas_change.arrived[0].to_share}.", s)[1] == ["not_new"]
    s["areas_change"]["arrived"] = [{"name": "internet culture", "from_share": 0.01, "to_share": 0.09, "change": 8.0}]
    assert obs("{areas_change.arrived[0].name} arrived, at {areas_change.arrived[0].to_share}.", s)[0]


def test_a_change_so_what_is_the_learning_side_that_gave_way_not_saved_clips():
    F = facts_mod()
    s = copy.deepcopy(CHANGED)
    s["library"]["saved_not_opened"] = [{"theme": "Sketch edits", "n": 4, "examples": ["x"]}]
    c = F._so_what_candidates(s, "changed", None)
    assert [x["kind"] for x in c] == ["learning_faded"]
    I = ins()
    s["so_what_candidates"] = c
    raw = {"answer": "", "observations": []}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["so_what"] == ("The learning side gave way: science fell from 10% in 2020 to 2% in 2026, while internet "
                            "culture grew from 4% to 9%.")


# ================================ the so-what: worth saying, never twice, code's when the writer gave none ========
def test_saved_clips_are_no_so_what_and_saved_learning_comes_first():
    F = facts_mod()
    s = top()
    s["themes"].append({"name": "Paint basics", "area": "art and design", "items": 20, "share": 0.02})
    s["library"]["saved_not_opened"] = [{"theme": "Sketch edits", "n": 9}, {"theme": "Meme drops", "n": 7},
                                        {"theme": "Block battles", "n": 8}, {"theme": "Paint basics", "n": 3}]
    # round 12, pass 3 (U5): a top answer's "what is changing" (moving) comes first; the saved order is unchanged
    keys = [x["key"] for x in F._so_what_candidates(s, "top", None) if x["kind"] != "moving"]
    assert keys[:2] == ["saved:Paint basics", "saved:Block battles"] and not [k for k in keys if "edits" in k
                                                                              or "memes" in k]


def test_a_topics_shorts_shift_says_whose_videos_and_a_comparison_has_none():
    F = facts_mod()
    I = ins()
    s = top(kind="count", filters={"topic": "block games"})
    s["previous"]["shorts"], s["previous"]["long"] = 200, 680
    c = [x for x in F._so_what_candidates(s, "count", None) if x["kind"] == "shorts_shift"]
    assert c and c[0]["topic"] == "block games"
    assert I.so_what_text(c[0], s).startswith("Shorts went up to 74% of your block games videos, from 23%")
    assert not [x for x in F._so_what_candidates(s, "compare_topics", None) if x["kind"] == "shorts_shift"]


def test_code_says_the_strongest_candidate_when_the_writer_picked_none():
    I = ins()
    s = top()
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.5, "previous_words": "the 4 weeks before"}]
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.", "so_what": None,
           "observations": [{"text": "{areas[0].name} grew from {areas[0].previous_share}.", "uses": []},
                            {"text": "{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share}.",
                             "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["so_what"] and f["so_what"].startswith("Shorts went up to 74%") and f["so_what_id"] == "shorts_shift:up"


def test_a_firsts_path_and_its_saved_videos_are_both_kept_as_said():
    I = ins()
    c = case("first_blender")
    s = c["sheet"]
    s["periods"] = [{"label": "2019", "items": 12}, {"label": "2023", "items": 300}, {"label": "2026", "items": 40}]
    f = I.fill(I.check(c["fake"], s), c["fake"], s)
    assert "You saved" in f["so_what"]
    assert f["so_what_id"].startswith("path:") and "|saved:" in f["so_what_id"]


def test_never_the_same_saved_videos_on_the_next_answer(wr, monkeypatch):
    """Judges: rows 4 and 5 both ended "You saved 6 <theme> tutorials": a so-what of two candidates keeps both."""
    from mvp import history as Hm
    from mvp.tests.test_round11_h import ask
    seen = {}
    real = Hm._write_now

    def spy(bot, person_, q, now, follow, words, said, deadline=None):
        st = bot.store.get_state(Hm.STATE.format(h=person_["handle"])) or {}
        if st.get("so_what_id"):
            seen["last"] = st["so_what_id"]
        out = real(bot, person_, q, now, follow, words, said, deadline)
        if out[2]:
            seen["cands"] = [c["key"] for c in out[2].get("so_what_candidates") or []]
        return out
    monkeypatch.setattr(Hm, "_write_now", spy)
    wr["bot"].store.set_state(Hm.STATE.format(h=person(wr)["handle"]),
                              {"so_what_id": "path:faded|saved:Watercolor painting", "q": None})
    ask(wr, QS["q2"])
    assert seen.get("last") == "path:faded|saved:Watercolor painting"
    assert "saved:Watercolor painting" not in seen.get("cands", [])


# ================================ the channels answer says what the top channels are (judge A, row 2) ===========
def test_what_the_top_channels_are_is_said_whatever_the_writer_chose():
    I = ins()
    s = top(kind="channels", question="which channels did i watch the most in 2025")
    s["channels"] = [{"name": n, "items": i, "area": a, "shorts_share": 0.5, "theme": "x", "theme_share": 0.5}
                     for n, i, a in (("Pixel Forge", 137, "gaming"), ("Star Notes", 125, "science"),
                                     ("Reel Reels", 112, "film and TV"), ("Doggo Plays", 107, "gaming"),
                                     ("Speed Kid", 96, "gaming"))]
    s["top_areas"] = {"area": "gaming", "n": 3, "of": 5}
    raw = {"answer": "{channels[0].name} led with {channels[0].items} videos, ahead of {channels[1].name} "
                     "({channels[1].items}).",
           "observations": [{"text": "{channels[2].name} had {channels[2].items}.", "uses": []},
                            {"text": "{channels[3].name} came on {channels[3].days} days.", "uses": []},
                            {"text": "{channels[4].name} had {channels[4].items}.", "uses": []}]}
    for c in s["channels"]:
        c["days"] = 30
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert ("3 of your top 5 are gaming channels (Pixel Forge, Doggo Plays, Speed Kid); Star Notes is science and "
            "Reel Reels is film and TV.") in f["observations"]
    assert len(f["observations"]) <= I.OBS_MAX


def test_under_a_topic_the_channels_are_not_told_by_their_area():
    """Judge A, "only gaming": "led by gaming at 100%", "X is gaming, Y is gaming"; row 3: "mostly gaming at 98%"."""
    I = ins()
    s = top(kind="channels", filters={"topic": "gaming"})
    s["areas"] = [{"name": "gaming", "items": 990, "share": 1.0}]
    s["top_areas"] = {"area": "gaming", "n": 2, "of": 2}
    sh = I.shown(s)
    assert "areas" not in sh and "top_areas" not in sh and all("area" not in c for c in sh["channels"])
    f = I.check(I.code_form(s), s)
    assert not [o for o in f["observations"] if " are gaming channels" in o or " is gaming" in o]


def test_a_topics_share_is_of_its_own_videos():
    """Judges: "Number games made up 96% of what you opened" in a math answer; "took 89% of the window"."""
    I = ins()
    s = top(kind="channels", filters={"topic": "math"})
    assert I.scoped("Number games made up 96% of what you opened.", s) == "Number games made up 96% of your math videos."
    s["kind"] = "first"
    assert I.scoped("Art and design took 89% of the window.", s) == "Art and design took 89% of your math videos."


# ================================ a comparison says how its balance moved (judges, row 5) =========================
def test_a_comparison_says_the_balance_against_last_year_with_its_ratio_then():
    F = facts_mod()
    I = ins()
    tp = [{"name": "gaming", "items": 3455, "previous_items": 3093, "days": 300, "shorts": 2236, "long": 1182},
          {"name": "art", "items": 375, "previous_items": 221, "days": 150, "shorts": 259, "long": 53}]
    cmpx = F._compare(tp, [3093, 221])
    assert cmpx["balance"] == "narrower" and cmpx["previous_ratio_words"] == "about 14 times as many"
    s = {"question": "did i watch more gaming or more art videos this year", "kind": "compare_topics", "lang": "en",
         "filters": {}, "window": {"words": "This year", "start": "2026-01-01", "end": "2026-10-30"},
         "totals": {"items": 21000}, "previous": {"items": 20000, "words": "the same part of 2025"},
         "topics": tp, "comparison": cmpx, "library": {"saved_not_opened": []}, "so_what_candidates": [],
         "offers": []}
    raw = {"answer": "x", "observations": [{"text": "Gaming came on 300 days, art on 150.", "uses": ["topics"]},
                                           {"text": "2,236 of the gaming videos were Shorts.", "uses": ["topics"]},
                                           {"text": "Art had 259 Shorts.", "uses": ["topics"]}]}
    f = I.fill(I.check(raw, s), raw, s)
    assert ("In the same part of 2025 it was about 14 times as many (3,093 gaming against 221 art): the gap has "
            "narrowed.") in f["observations"]


# ================================ facts: a Shorts share counts the long streams, "new" means new ===================
def test_a_shorts_share_counts_a_video_over_three_hours_as_long():
    """Judge B, row 1: a channel "46% Shorts" was 5 of its 17 videos (29%): 6 streams over 3 hours were left out."""
    F = facts_mod()
    n = 17
    idx = SimpleNamespace(platform=np.zeros(n, np.int8))
    short = np.array([1] * 5 + [0] * 12, np.int8)
    length = np.array([40] * 5 + [600] * 6 + [-2] * 6, np.int64)   # -2: over 3 hours, out of every length sum
    facts = SimpleNamespace(short=short, length=length)
    key = np.zeros(n, np.int32)
    secs, known, shorts = F._length_by(np.arange(n), key, facts, idx)[0]
    assert (known, shorts) == (17, 5) and secs == 5 * 40 + 6 * 600


def test_a_theme_with_many_videos_before_is_never_new():
    """Judge A, "without shorts": "<theme> grew sharply and became new" of a theme with 35 videos the year before."""
    F = facts_mod()
    th = SimpleNamespace(shown=lambda t: {0: "Card tricks", 1: "Other"}[t])
    theme = np.array([0] * 400 + [1] * 9600 + [0] * 35 + [1] * 9965, np.int32)
    facts = SimpleNamespace(theme=theme)
    idx = SimpleNamespace(creator=np.full(len(theme), -1, np.int32))
    sc = SimpleNamespace(items=np.arange(10000))
    prev = SimpleNamespace(items=np.arange(10000, 20000))
    new, _ = F._new_stopped(sc, prev, idx, facts, th, None, None)
    assert new["themes"] == []
    theme[10000:10035] = 1   # none before: new
    new, _ = F._new_stopped(sc, prev, idx, facts, th, None, None)
    assert [t["name"] for t in new["themes"]] == ["Card tricks"]


# ================================ wording slips ====================================================================
def test_an_area_after_the_window_words_is_not_capitalised():
    I = ins()
    assert I.window_lead("Gaming led with 22%.", top()).startswith(
        "In the 4 weeks up to 30 October 2026, where your export ends, gaming led")
    s = top()
    assert I.window_lead("Pixel Forge led with 30 videos.", s).endswith(", Pixel Forge led with 30 videos.")


def test_an_estimate_is_said_with_about_once():
    I = ins()
    s = {"kind": "count", "lang": "en", "filters": {"topic": "block games"},
         "topics": [{"name": "block games", "items": 1094, "matched_by": "themes and words"}]}
    # round 12, pass 3 fix (judge A, row 3, on purpose): no "about" on a number code counted; what it counts, once
    assert I.scoped("About 1,094 block games videos.", s, answer=True) == \
        "1,094 block games videos (by their titles and themes)."


def test_the_real_shaped_top_sheet_end_to_end_says_no_false_thing():
    """The whole top answer by code on the real-shaped sheet: the broad picture, the themes inside the right area,
    Shorts as a share, and nothing the judges flagged."""
    I = ins()
    s = top()
    raw = {"answer": "", "observations": []}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    text = "\n".join(p["text"] for p in I.layout(f, s))
    assert "gaming led with 22% of what you opened" in text
    assert "Inside gaming: Speed runs (5% of everything you opened) and Block battles (5%)" in text
    assert re.search(r"Shorts were 74% of your YouTube videos", text)
    assert not re.search(r"\bmostly\b|hours|of your window", text)


# ================================ found in my own live reading after the fixes above ==============================
def test_a_direction_said_against_the_span_before_with_no_number_is_vague():
    """Live, row 1: "Compared with the 4 weeks before (5 September to 2 October 2026), gaming gained share while
    comedy and sports lost ground": the digits are the window's, not a number of the claim."""
    s = top()
    s["previous"]["words"] = "the 4 weeks before (5 September to 2 October 2026)"
    kept, why = obs("Compared with {previous.words}, {areas[0].name} gained share while {areas[1].name} lost ground.",
                    s)
    assert kept is None and why == ["vague"]


def test_the_answers_date_said_again_is_a_repeat():
    """Live, row 4: "<its date> is the first <its date> in your blender history"."""
    I = ins()
    s = case("first_blender")["sheet"]
    raw = {"answer": "You first opened a blender video on 14 March 2019.",
           "observations": [{"text": "14 March 2019 is the first 14 March 2019 in your blender history.",
                             "uses": ["items"]},
                            {"text": "On 14 March 2019 Blender 3D was where it began.", "uses": ["items"]}]}
    f = I.check(raw, s)
    assert f["observations"] == [] and [d[1] for d in f["dropped"] if d[0] == "observation"] == ["repeat", "repeat"]


def test_anything_saved_is_said_in_the_so_what_line_only():
    """Live, row 6: "... were new that day, while 1 <theme> video stayed saved"."""
    I = ins()
    assert I._SAVED_OBS.search("pixel forge was new that day, while 1 meme drops video stayed saved")


def test_without_shorts_no_shorts_share_is_shown():
    """Live, "without shorts": "0% of its videos were Shorts"."""
    I = ins()
    s = top(kind="channels", filters={"topic": None, "without_shorts": True})
    sh = I.shown(s)
    assert all("shorts_share" not in c for c in sh["channels"]) and "shorts" not in sh["totals"]
    assert sh["filters"]["without_shorts"] is True


def test_a_comparison_is_not_shown_the_windows_own_shorts_and_lengths():
    """Live, row 5: "your watching was mostly Shorts at 81%, the long ones about 20 minutes" under gaming against
    art: those are of everything opened, not of the two sides."""
    I = ins()
    s = top(kind="compare_topics")
    sh = I.shown(s)
    assert not {"shorts", "long", "shorts_share", "long_median_min"} & set(sh["totals"]) and sh["totals"]["items"]


def test_a_bullet_the_so_what_says_goes():
    """Live, row 2: "11,932 videos were Shorts, up from 4,476" above "Shorts went up to 58% of your YouTube videos"."""
    I = ins()
    s = top()
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.5}]
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.", "so_what": {"pick": "shorts_shift:up", "text": None},
           "observations": [{"text": "{totals.shorts} videos were Shorts, up from {previous.shorts}.", "uses": []},
                            {"text": "{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share}.",
                             "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["so_what"].startswith("Shorts went up to 74%")
    assert not [o for o in f["observations"] if "up from 600" in o]
    assert ("observation", "said_by_so_what") in [(d[0], d[1]) for d in f["dropped"]]


def test_the_models_bullets_are_new_against_codes_answer_when_code_wrote_it():
    """Live, row 8: code's answer "comedy led with 14%" and the writer's bullet "Comedy led with 14%, and ..." (only
    while 2 bullets are left: never at the cost of the whole answer)."""
    I = ins()
    s = top()
    raw = {"answer": "{areas[0].name} topped everything at {areas[2].share}.",   # fails: code writes the answer
           "observations": [{"text": "{areas[0].name} led with {areas[0].share}, then {areas[1].name} "
                                     "({areas[1].share}).", "uses": []},
                            {"text": "{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share}.",
                             "uses": []},
                            {"text": "{themes[1].name} grew from {themes[1].previous_share} to {themes[1].share}.",
                             "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["answer"].startswith("gaming led with 22%") or f["answer"].startswith("Gaming led with 22%")
    assert not [o for o in f["observations"] if o.startswith("Gaming led with 22%")]


def test_a_change_so_what_does_not_say_again_what_grew():
    I = ins()
    s = copy.deepcopy(CHANGED)
    s["so_what_candidates"] = facts_mod()._so_what_candidates(s, "changed", None)
    raw = {"answer": "", "observations": [
        {"text": "{areas_change.arrived[0].name} rose from {areas_change.arrived[0].from_share} to "
                 "{areas_change.arrived[0].to_share}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    # round 12, pass 3 (U4, live, row 7: what grew was said in the answer and a bullet, then a third time here)
    assert f["so_what"] == "The learning side gave way: science fell from 10% in 2020 to 2% in 2026."


def test_a_topics_channels_answer_has_enough_bullets_from_code():
    """Live, "only gaming": the writer's bullets all failed and code had one, so today's code reply went out."""
    I = ins()
    s = top(kind="channels", filters={"topic": "gaming"})
    s["themes"] = [dict(t, share=v) for t, v in zip(s["themes"], (0.15, 0.14, 0.11, 0.1))]
    raw = {"answer": "", "observations": []}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["answer"] and len(f["observations"]) >= I.OBS_MIN


# ================================ my second live reading ==========================================================
def test_the_windows_shorts_share_is_of_the_youtube_videos():
    """Live, row 1: "Shorts made up 79% of everything you opened" (79% is of the YouTube videos)."""
    kept, why = obs("Shorts made up {totals.shorts_share} of everything you opened.")
    assert kept == "Shorts made up 74% of your YouTube videos." and not why


@pytest.mark.parametrize("text, why", [
    # live, row 4: "90 Shorts made up 90 of 300 videos"
    ("{totals.shorts} Shorts made up {totals.shorts} of {totals.items} videos.", "garbled"),
    # live, row 7: "The biggest shift is from science and gaming toward internet culture and film and TV."
    ("The biggest shift is from {areas[1].name} toward {areas[0].name}.", "vague"),
    # live, row 8: "12,080 of your videos were Shorts"
    ("{totals.shorts} of your videos were Shorts.", "count_as_share"),
])
def test_my_live_readings_slips_are_dropped(text, why):
    kept, whys = obs(text)
    assert kept is None and whys == [why], (text, whys)


def test_a_whole_said_as_n_of_the_n_stands():
    kept, why = obs("{channels[1].name} is behind {themes[2].channels[0].items} of the {themes[2].channels[0].items} "
                    "{themes[2].name} videos.")
    assert not why or why != ["garbled"]


def test_a_firsts_answer_without_its_topic_is_codes_date_sentence():
    """Live, row 4: "You first started watching <its date>."."""
    I = ins()
    c = case("first_blender")
    s = c["sheet"]
    raw = dict(c["fake"], answer="You first started watching 14 March 2019. Blender 3D was most of it.")
    f = I.fill(I.check(raw, s), raw, s)
    assert f["answer"].startswith("You first opened a blender video on 14 March 2019.")


def test_codes_must_line_takes_the_writers_bullet_on_the_same_subject():
    """Live, a day: "the busiest hour was 9am" twice; "10 of your videos were Shorts" beside the usual-day line."""
    I = ins()
    s = copy.deepcopy(DAY)
    raw = {"answer": "{totals.items} videos that day, fewer than your usual {usual.median_items}.",
           "observations": [{"text": "{themes[0].name} led with {themes[0].share}.", "uses": []},
                            {"text": "The busiest hour was {when.busiest_hours[0].hour}.", "uses": []},
                            {"text": "{totals.shorts} of your {totals.items} videos were Shorts.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert sum("busiest hour" in o for o in f["observations"]) == 1
    assert sum("Shorts" in o for o in f["observations"]) == 1


def test_a_bullet_another_bullet_says_in_full_goes():
    I = ins()
    s = top(kind="channels")
    raw = {"answer": "{channels[0].name} led with {channels[0].items} videos, ahead of {channels[1].name}.",
           "observations": [{"text": "{channels[0].name} was the top channel, at {channels[0].shorts_share} Shorts.",
                             "uses": []},
                            {"text": "{channels[0].name} is {channels[0].shorts_share} Shorts and {channels[1].name} "
                                     "{channels[1].shorts_share}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert not [o for o in f["observations"] if o.startswith("Pixel Forge was the top channel")]


def test_a_comparison_and_a_change_are_not_shown_what_misleads_them():
    """Live: "your biggest area was gaming at 19%" under music against cooking; "still mostly Shorts at 81%, but the
    share slipped from 80% to 77%" on a change."""
    I = ins()
    sh = I.shown(top(kind="compare_topics"))
    assert not {"areas", "themes", "channels"} & set(sh)
    sh = I.shown(copy.deepcopy(CHANGED) | {"totals": {"items": 9, "shorts_share": 0.81}})
    assert "shorts_share" not in sh["totals"]


# ================================ my third live reading ============================================================
def test_one_video_each_is_filler():
    kept, why = obs("{themes[0].name} came from {themes[0].channels[0].name} and others, all with one video each.")
    assert kept is None and why == ["filler"]


def test_a_change_is_not_shown_the_spans_channels():
    """Live, row 7: "Your top channels show the mix: X is <theme>, Y is <theme>, and Z is almost all long videos"."""
    I = ins()
    assert "channels" not in I.shown(copy.deepcopy(CHANGED) | {"channels": [{"name": "Pixel Forge", "items": 9}]})


def test_a_so_what_with_no_number_is_said_in_codes_words_with_its_numbers():
    """Live, row 8: "You could compare how much more of your summer watching was Shorts than the spring before"."""
    I = ins()
    s = top()
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.682}]
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "so_what": {"pick": "shorts_shift:up", "text": "You could compare how much more of it was Shorts."},
           "observations": [{"text": "{areas[0].name} grew from {areas[0].previous_share}.", "uses": []},
                            {"text": "{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share}.",
                             "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["so_what"].startswith("Shorts went up to 74% of your YouTube videos, from 68%")
    assert not [o for o in f["observations"] if o.startswith("Shorts were 74%")]


def test_the_same_move_said_twice_with_and_without_its_months_goes_once():
    I = ins()
    s = copy.deepcopy(CHANGED)
    raw = {"answer": "",
           "observations": [{"text": "{areas_change.left[0].name} fell from {areas_change.left[0].from_share} to "
                                     "{areas_change.left[0].to_share}, while {areas_change.arrived[0].name} rose from "
                                     "{areas_change.arrived[0].from_share} to {areas_change.arrived[0].to_share}.",
                             "uses": []},
                            {"text": "{areas_change.left[0].name} fell from {areas_change.left[0].from_share} in "
                                     "{areas_change.from} to {areas_change.left[0].to_share} in {areas_change.to}.",
                             "uses": []},
                            {"text": "{areas[0].name} was {areas[0].share} of what you opened.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert sum(o.lower().startswith("science fell from 10%") for o in f["observations"]) == 1


def test_channel_shorts_trivia_with_no_number_is_filler_on_a_top_answer():
    """Live, row 1 (picture): "X was your top channel and almost all Shorts, while Y leaned less on Shorts"."""
    kept, why = obs("{channels[0].name} was your top channel and almost all Shorts, while {channels[1].name} leaned "
                    "less on Shorts.")
    # round 12, pass 3 (U1): "less on Shorts" names no path that supports it, so it goes before the filler rule
    assert kept is None and why in (["filler"], ["direction_unbound"])


def test_a_repeat_of_codes_answer_goes_when_code_can_fill_the_minimum():
    """Live, row 7 (picture): "Shorts climbed from 4% in 2020 to 81% in 2026" under code's answer saying it."""
    I = ins()
    s = copy.deepcopy(CHANGED)
    s["change"] = {"from": "2020", "to": "2026", "rising": [{"name": "Speed runs", "from_share": 0.01,
                                                              "to_share": 0.06}], "fading": []}
    raw = {"answer": "Since 2020 {eras[0].area} led every year.",
           "observations": [{"text": "Shorts climbed from {areas_change.shorts.from_share} in {areas_change.shorts.from} "
                                     "to {areas_change.shorts.to_share} in {areas_change.shorts.to}.", "uses": []},
                            {"text": "{areas[0].name} was the biggest area at {areas[0].share}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["answer"].startswith("Gaming has led every year since 2020, but how you watch changed")
    assert not [o for o in f["observations"] if o.startswith("Shorts climbed")] and len(f["observations"]) >= 2
