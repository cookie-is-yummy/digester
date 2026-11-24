"""Round 12, third pass (DESIGN.md section 19.P3): what was still wrong with the history answers after the second
pass (U1 to U10), each reproduced on made-up data (a test here fails on a490cdd), fixed, and guarded with its near
variants.

Made-up data only: the sheet shaped like the real ones of tests/test_round12_pass2_fix.py (areas, themes with their
area, channels with their Shorts share), small sheets built here, the eval's made-up sheets and the made-up library
(tests/r12_library.py).
"""
import copy
import json
import os
import re

import pytest

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round11_h import ask
from mvp.tests.test_round12_d import r12, person, mods, no_real_keys, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_merge import wr, later, last_steps  # noqa: F401  (fixtures)
from mvp.tests.test_round12_pass2_fix import TOP, top, obs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ins():
    from mvp import insight
    return insight


def answer(text, s=None):
    """(the answer as kept, or None; why it was dropped), read in the live writer's strict mode."""
    I = ins()
    f = I.check({"answer": text, "observations": []}, s or top(), strict=True)
    return f["answer"], [d[1] for d in f["dropped"] if d[0] in ("answer", "answer_tail") and d[1] != "missing"]


def v5_direction_case():
    with open(os.path.join(HERE, "eval", "insight_cases.json"), encoding="utf-8") as f:
        d = json.load(f)
    c = next(x for x in d["v5"]["cases"] if x.get("as") == "answer")
    return c, d["v5"]["sheets"][c["case"]]


# ================================ U1: a direction needs a path whose values support it ===========================
_C, _S = v5_direction_case()


@pytest.mark.parametrize("text", [p["text"] for p in _C["plants"]])
def test_u1_a_false_direction_with_no_number_is_dropped(text):
    # live (pass 3): "shifted from one area to a broader mix with four areas rising, while Shorts became more of it"
    kept, why = answer(text, _S)
    assert kept is None, (text, why)


@pytest.mark.parametrize("text", _C["true"])
def test_u1_a_true_direction_stands(text):
    kept, why = answer(text, _S)
    assert kept and not why, (text, why)


def test_u1_the_planted_set_is_big_enough_and_all_of_it_has_no_number():
    assert len(_C["plants"]) >= 12 and len(_C["true"]) >= 6
    assert all(not re.search(r"\d", re.sub(r"\{[^}]*\}", " ", p["text"])) for p in _C["plants"])


@pytest.mark.parametrize("text,why", [
    ("{areas[0].name} rose while {areas[1].name} fell.", None),                       # both true
    ("{areas[1].name} rose while {areas[0].name} fell.", "direction"),                # both false
    ("Your watching shifted toward {areas[0].name}.", None),                          # gaming rose
    ("Your watching shifted toward {areas[3].name}.", "direction_unbound"),           # sports fell
    ("You watched less {areas[3].name} than {areas[0].name}.", None),
    ("You watched less {areas[0].name} than {areas[3].name}.", "direction"),
    ("{themes[0].name} peaked at {themes[0].share}.", "direction_unbound"),          # no peak path
])
def test_u1_near_variants_of_direction(text, why):
    kept, whys = answer(text)
    assert (kept is None) == (why is not None), (text, whys)
    if why:
        assert why in whys, whys


def test_u1_a_count_typed_in_words_is_a_number_typed_outside_a_path():
    kept, why = answer("{areas[0].name} led, with four areas rising.")
    assert kept is None and "free_number" in why


@pytest.mark.parametrize("text", ["how did my watching change from 2023 to 2025",
                                  "how did what i watch change between 2021 and 2024",
                                  "what did i watch in 2023 vs 2025", "what i watched in 2025 vs 2023",
                                  "compare what i watched in 2023 and 2025"])
def test_u1_a_change_between_two_years_about_what_is_read_as_changed(text):
    Hm = mods()[0]
    q = Hm.read(text, TODAY)
    assert q is not None and q.kind == "changed" and q.window.kind == "range", (text, q)
    assert q.window.start.month == 1 and q.window.end.month == 12 and q.window.start < q.window.end


@pytest.mark.parametrize("text,kind", [("how many videos did i watch in 2023 vs 2025", "compare"),
                                       ("did i watch more in 2023 or 2025", "compare"),
                                       ("how do i change my feed", None), ("how did my rules change", None)])
def test_u1_how_much_between_two_years_stays_a_count_and_other_changes_are_not_history(text, kind):
    Hm = mods()[0]
    q = Hm.read(text, TODAY)
    assert (q.kind if q else None) == kind, (text, q)


def test_u1_a_change_from_one_year_to_another_is_told_with_areas_not_a_timeline_of_counts(wr):
    out, _ = ask(wr, "how did my watching change from 2023 to 2025")
    assert not re.search(r"\b20\d\d: [\d,]+, 20\d\d: [\d,]+", out), out
    assert "led" in out and "The main area each year" in out


# ================================ U2: "what have i been into lately" is a history question ======================
@pytest.mark.parametrize("text,wk", [("what have i been into lately", "lately"),
                                     ("what have i been into the last 3 months", "days"),
                                     ("what have i been into the past 3 months", "days"),
                                     ("what am i into lately", "lately"), ("what am i into these days", "lately"),
                                     ("what am i into right now", "lately"), ("what i've been into lately", "lately")])
def test_u2_into_with_a_window_is_the_top_kind(text, wk):
    Hm = mods()[0]
    q = Hm.read(text, TODAY)
    assert q is not None and q.kind == "top" and q.window.kind == wk and not q.topic, (text, q)


@pytest.mark.parametrize("text", ["what have i been saving lately", "what am i into", "what have i been into",
                                  "what am i into saving", "i have been into gaming lately"])
def test_u2_saves_and_a_bare_into_are_not(text):
    Hm = mods()[0]
    q = Hm.read(text, TODAY)
    assert q is None or q.kind != "top", (text, q)


def test_u2_the_bot_answers_into_lately_from_the_watch_history_not_the_trends(wr):
    out, _ = ask(wr, "what have i been into lately")
    assert out.startswith("In the 4 weeks up to 30 October 2026"), out
    assert "rising or fading" not in out
    later(wr)
    out, _ = ask(wr, "what have i been into the last 3 months")
    assert out.startswith("In the last 90 days up to 30 October 2026"), out


def test_u2_saving_lately_still_goes_where_it_went(wr):
    out, _ = ask(wr, "what have i been saving lately")
    assert not out.startswith("In the 4 weeks"), out


# ================================ U3: without Shorts, nothing about Shorts; the chart at the answer's level ======
def _wo():
    s = top()
    s["filters"] = {"topic": None, "without_shorts": True, "left_out": {"shorts": 700, "reels": 0}}
    return s


@pytest.mark.parametrize("text", ["{channels[0].name} is almost all Shorts.",
                                  "{areas[0].name} led at {areas[0].share}, with Shorts behind it.",
                                  "{channels[1].name} leaned on Shorts, with {channels[1].items} videos."])
def test_u3_a_without_shorts_answer_says_nothing_about_shorts(text):
    kept, why = obs(text, _wo())
    assert kept is None and why == ["shorts_left_out"], why


def test_u3_saying_the_shorts_were_left_out_stands():
    kept, why = obs("Without Shorts, {areas[0].name} led at {areas[0].share}.", _wo())
    assert kept and not why, why


def test_u3_no_shorts_so_what_without_shorts():
    I = ins()
    c = {"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.8, "previous_share": 0.5}
    assert not I._so_what_fits(c, _wo()) and I._so_what_fits(c, top())


def _thin_areas():
    s = top()
    for a, sh in zip(s["areas"], (0.12, 0.09, 0.08, 0.05)):
        a["share"] = sh   # 34% of the window: too little for the chart by area
    return s


def test_u3_the_chart_follows_the_level_the_answer_names():
    I = ins()
    s = _thin_areas()
    assert I.chart(s)[0].startswith("Share of what you opened, by theme:")
    assert I.chart(s, I.answer_level("Mostly gaming (12%) and comedy (9%).", s))[0].startswith(
        "Share of what you opened, by area:")
    assert I.chart(s, I.answer_level("Meme drops led with 7%.", s))[0].startswith("Share of what you opened, by theme:")


def test_u3_codes_lead_is_by_theme_when_the_areas_are_not_drawn():
    I = ins()
    s = _thin_areas()
    assert I.code_form(s)["answer"].startswith("A wide mix: Meme drops")
    assert I.code_form(top())["answer"].startswith("gaming")


# ================================ U4: one fact once; list answers as captioned cards ============================
def test_u4_a_bullet_that_rests_on_the_answers_paths_is_a_repeat():
    I = ins()
    raw = {"answer": "{areas[0].name} led with {areas[0].share}, then {areas[1].name} ({areas[1].share}).",
           "observations": [{"text": "{areas[0].name} led with {areas[0].share}, ahead of {areas[1].name} at "
                                     "{areas[1].share}.", "uses": []},
                            {"text": "{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share} against "
                                     "{previous.words}.", "uses": []}]}
    f = I.check(raw, top(), strict=True)
    assert ("observation", "repeat") in [(d[0], d[1]) for d in f["dropped"]]
    assert len(f["observations"]) == 1 and "fell from 16% to 9%" in f["observations"][0]


def test_u4_two_bullets_on_the_same_paths_keep_the_first():
    I = ins()
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "observations": [{"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                            {"text": "You opened {themes[1].name} on {themes[1].days} different days.", "uses": []}]}
    f = I.check(raw, top(), strict=True)
    assert len(f["observations"]) == 1 and f["observations"][0].startswith("Speed runs came on 18 days")


def test_u4_the_windows_shorts_are_said_once_when_the_so_what_says_them():
    I = ins()
    s = top()
    s["areas"][3]["change_vs_previous"] = -0.01   # no "what is changing" so-what: the Shorts one stands
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.5}]
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "observations": [{"text": "Shorts were {totals.shorts_share} of your YouTube videos.", "uses": []},
                            {"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                            {"text": "{areas[1].name} was {areas[1].share}.", "uses": []}],
           "so_what": {"pick": "shorts_shift:up", "text": None}}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    said = [x for x in f["observations"] if re.search(r"\bShorts were\b", x)]
    # round 12, pass 4 (V4, changed on purpose): the Shorts shift has no step code can take, so it is a bullet, not a
    # so-what; the window's Shorts are still said once
    assert not f["so_what"] and not said, (f["so_what"], f["observations"])
    assert sum("Shorts" in x for x in f["observations"]) == 1, f["observations"]


def test_u4_a_day_is_the_overview_then_cards_with_one_caption_line_and_never_a_list_twice(wr):
    out, _ = ask(wr, "what did i watch on october 30")
    assert "on the 30th by Pixel Pencil (30 Oct" not in out   # the numbered text list of the same items is gone
    assert "1. Pixel Pencil · 25 min\nhttps://www.youtube.com/watch?v=vrday1" in out, out
    assert out.count("vrday1") == 1


def test_u4_the_cards_caption_reaches_a_channel_that_draws_cards():
    from mvp.channels.web import WebChannel
    ch = WebChannel.__new__(WebChannel)
    got = {}
    ch.send = lambda handle, text, link=None: got.update(link=link) or "ref"
    WebChannel.send_link(ch, "h", {"type": "link", "url": "https://www.youtube.com/watch?v=abc123", "title": "T",
                                   "platform": "youtube", "video_id": "abc123", "caption": "1. Pixel Pencil · 25 min"})
    assert got["link"]["caption"] == "1. Pixel Pencil · 25 min"
    page = open(os.path.join(HERE, "channels", "web_page.html"), encoding="utf-8").read()
    assert "[l.caption].concat([l.channel, l.length])" in page


def test_u4_and_n_more_comes_after_the_cards(wr):
    from mvp import insight as I
    old = I.SHOW["items"]
    I.SHOW["items"] = 2
    try:
        out, _ = ask(wr, "what did i watch on october 30")
    finally:
        I.SHOW["items"] = old
    assert out.index("vrday2") < out.index("And 2 more"), out


# ================================ U5: the so-what is about the question's subject ================================
def test_u5_the_most_lately_says_what_is_changing():
    F = mods()[1]
    keys = [c["key"] for c in F._so_what_candidates(top(), "top", None)]
    assert keys[0] == "moving:gaming"
    I = ins()
    s = top()
    s["so_what_candidates"] = F._so_what_candidates(s, "top", None)
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "observations": [{"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                            {"text": "{areas[1].name} was {areas[1].share}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    # round 12, pass 3 fix (judge A, row 1, on purpose): what grew leads the answer; the so-what is what fell, with the
    # follow-up that shows it
    assert f["answer"].startswith("Gaming nearly doubled to 22% of what you opened, from 12% in the 4 weeks before"), f
    assert f["so_what"].startswith("Worth noticing: sports fell from 16% to 9% against the 4 weeks before"), f
    assert 'Say "only sports"' in f["so_what"] and f["so_what_id"] == "moving:gaming"


def test_u5_no_moving_so_what_for_a_season_or_a_long_window():
    F = mods()[1]
    s = top()
    s["window"] = dict(s["window"], start="2025-01-01", end="2026-10-30")
    assert "moving" not in [c["kind"] for c in F._so_what_candidates(s, "top", None)]


def _cmp_sheet():
    from mvp.tests.test_round12_pass2 import case
    s = case("cmp_gaming_art")["sheet"]
    s["topics"][0]["top_themes"] = [{"name": "Speed runs", "items": 300}, {"name": "Block battles", "items": 200}]
    s["topics"][1]["top_themes"] = [{"name": "Paint basics", "items": 120}, {"name": "Ink sketching", "items": 60}]
    s["so_what_candidates"] = [{"key": "saved:Hermit episodes", "kind": "saved", "theme": "Hermit episodes", "n": 3}]
    s["library"] = {"saved_not_opened": [{"theme": "Hermit episodes", "n": 3}]}
    return s


def test_u5_a_comparison_offers_no_saved_series_from_outside_either_side():
    # live, row 5: three unopened saved episodes of an entertainment series under gaming against art
    I = ins()
    s = _cmp_sheet()
    raw = {"answer": "x", "observations": [], "so_what": {"pick": "saved:Hermit episodes", "text": "You saved "
                                                                                                    "{so_what_candidates[0].n} {so_what_candidates[0].theme} videos you never opened."}}
    f = I.fill(I.check(raw, s), raw, s)
    assert not f["so_what"], f["so_what"]


def test_u5_a_comparison_keeps_a_saved_one_inside_a_side():
    I = ins()
    s = _cmp_sheet()
    inner = next(t["name"] for tp in s["topics"] for t in tp.get("top_themes") or [])
    s["so_what_candidates"] = [{"key": "saved:" + inner, "kind": "saved", "theme": inner, "n": 4}]
    s["library"] = {"saved_not_opened": [{"theme": inner, "n": 4}]}
    raw = {"answer": "x", "observations": []}
    f = I.fill(I.check(raw, s), raw, s)
    assert f["so_what"] and inner in f["so_what"], (inner, f["so_what"], f["dropped"])


def test_u5_a_channels_answer_says_no_so_what_about_the_windows_shorts():
    I = ins()
    s = top(kind="channels")
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.5}]
    raw = {"answer": "{channels[0].name} led with {channels[0].items} videos.", "observations": [],
           "so_what": {"pick": "shorts_shift:up", "text": "Shorts went up to {so_what_candidates[0].share}."}}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert not f["so_what"], f["so_what"]


# ================================ U6: offers name only what the answer showed ===================================
def test_u6_an_offer_of_a_theme_the_answer_never_showed_is_not_made():
    I = ins()
    s = top(offers=["without_shorts", "only_topic:gaming", "only_topic:comedy", "only_topic:Meme drops",
                    "only_topic:Speed runs", "show_videos"])
    got = I.offers_fit(s, ["only_topic:Meme drops", "only_topic:gaming"], "gaming led with 22%, then comedy (11%).")
    assert got == ["only_topic:gaming"]
    got = I.offers_fit(s, [], "gaming led with 22%, then comedy (11%).")
    assert got == ["without_shorts", "only_topic:gaming"]


def test_u6_no_by_month_under_a_chart_by_month():
    I = ins()
    s = top(offers=["by_month", "show_videos"])
    assert I.offers_fit(s, ["by_month"], "x", "Videos opened per month:\n...") == ["show_videos"]
    assert I.offers_fit(s, ["by_month"], "x", "Share of what you opened, by area:") == ["by_month"]


def test_u6_a_top_sheet_offers_its_areas_first():
    F = mods()[1]
    from mvp import history as Hm
    q = Hm.read("what have i been watching the most lately", TODAY)
    out = {"totals": {"shorts": 3}, "areas": [{"name": "gaming"}, {"name": "comedy"}],
           "themes": [{"name": "Speed runs"}], "window": {"start": "2026-10-03", "end": "2026-10-30"}}
    assert F._offers(q, "top", out)[:4] == ["without_shorts", "only_topic:gaming", "only_topic:comedy",
                                            "only_topic:Speed runs"]


def test_u6_only_an_area_offered_is_taken(wr):
    out, _ = ask(wr, "what have i been watching the most lately")
    m = re.search(r"Want it (?:without Shorts or )?only ([a-z ]+)\?", out)
    assert m, out
    out2, _ = ask(wr, "only " + m.group(1))
    assert out2.startswith("Only " + m.group(1) + ":"), out2


# ================================ U7: every change with its direction, values and base ==========================
def test_u7_one_point_is_one_point():
    I = ins()
    assert I._fmt_value("change_vs_previous", 0.012) == "1 point"
    assert I._fmt_value("change_vs_previous", 0.12) == "12 points"


def test_u7_a_change_with_no_base_gets_the_sheets_own_base():
    kept, why = obs("{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share}.")
    assert kept == "Sports fell from 16% to 9% against the 4 weeks before (5 September to 2 October 2026).", kept


def test_u7_a_change_with_no_direction_is_dropped():
    kept, why = obs("{areas[1].name} moved {areas[1].change_vs_previous} from {previous.words}.")
    assert kept is None and why in (["no_direction"], ["direction_unbound"]), why


def test_u7_a_change_from_a_count_is_dropped():
    kept, why = obs("{areas[1].name} was down {areas[1].change_vs_previous} from {previous.items}.")
    assert kept is None, why


def test_u7_codes_falls_say_their_base_too():
    I = ins()
    o = [x["text"] for x in I.code_form(top())["observations"]]
    falls = [x for x in o if " fell from " in x]
    assert falls and all("against the 4 weeks before" in x for x in falls), o


# ================================ U8: what the answer is about (rows 7, 8, 2) ===================================
def _changed():
    per = []
    for y, g, c in ((2020, 0.22, 0.05), (2021, 0.36, 0.05), (2022, 0.48, 0.06), (2023, 0.30, 0.08),
                    (2024, 0.25, 0.09), (2025, 0.20, 0.10), (2026, 0.16, 0.11)):
        per.append({"label": str(y), "items": 1000, "areas": [{"name": "gaming", "share": g},
                                                             {"name": "comedy", "share": c}],
                    "shorts_share": 0.04 + (y - 2020) * 0.12})
    return {"question": "how has what i watch changed since 2020", "kind": "changed", "lang": "en",
            "filters": {"topic": None, "without_shorts": False},
            "window": {"words": "Since 1 January 2020 up to 30 October 2026, where your export ends",
                       "start": "2020-01-01", "end": "2026-10-30", "clipped": True},
            "totals": {"items": 7000, "days_active": 2000, "shorts": 3000, "long": 3000}, "periods": per,
            "eras": [{"from": "2020", "to": "2026", "area": "gaming", "share": 0.28}],
            "areas_change": {"from": "2020", "to": "2026", "left": [{"name": "gaming", "from_share": 0.22,
                                                                     "to_share": 0.16, "change": -6.0}],
                             "arrived": [{"name": "comedy", "from_share": 0.05, "to_share": 0.11, "change": 6.0}],
                             "shorts": {"from": "2020", "from_share": 0.04, "to": "2026", "to_share": 0.76}},
            "themes": [], "areas": [], "channels": [], "offers": ["without_shorts"]}


def test_u8_row7_one_area_every_year_says_how_its_weight_moved_and_what_took_its_place():
    I = ins()
    a = I.code_form(_changed())["answer"]
    # round 12, pass 3 fix (judge A, row 7, on purpose): the year of the turn is said
    assert a == ("Gaming led every year, but its weight moved: 22% in 2020, up to 48% in 2022, then down to 30% in "
                 "2023, and 16% in 2026; comedy took more of it."), a
    assert I.chart(_changed())[0].startswith("The share of gaming in each year:")
    assert any("Shorts went from 4%" in x["text"] for x in I.code_form(_changed())["observations"])


def test_u8_row7_a_steady_leader_keeps_the_shorts_answer():
    I = ins()
    s = _changed()
    for p in s["periods"]:
        p["areas"][0]["share"] = 0.30
    assert "how you watch changed" in I.code_form(s)["answer"]
    assert I.chart(s)[0].startswith("Shorts' share")


def test_u8_row8_a_season_says_what_set_it_apart_from_the_rest_of_its_year():
    I = ins()
    s = top(window={"words": "the summer of 2023 (1 June to 31 August 2023)", "start": "2023-06-01",
                    "end": "2023-08-31", "clipped": False},
            distinct={"rest_words": "the rest of 2023", "themes": [
                {"name": "Meme drops", "share": 0.07, "rest_share": 0.03, "items": 65},
                {"name": "Speed runs", "share": 0.05, "rest_share": 0.02, "items": 50}]})
    o = [x for x in I.code_form(s)["observations"] if x["text"].startswith("What set")]
    assert o and o[0]["must"] and o[0]["text"] == ("What set the summer apart from the rest of 2023: Meme drops (7%, "
                                                   "against 3%) and Speed runs (5%, against 2%).")
    assert I.check_sentence(o[0]["text"], I.Facts(I.shown(s))) is None


def test_u8_row8_the_distinct_themes_of_a_season_on_the_made_up_library(wr):
    Hm, F = mods()[0], mods()[1]
    q = Hm.read("what was i into in the summer of 2023", TODAY)
    s = F.build(wr["bot"], person(wr), q, wr["clock"][0], text="x")
    d = s.get("distinct")
    assert isinstance(d, dict)
    for t in (d or {}).get("themes") or []:
        assert t["share"] >= 1.5 * t["rest_share"] and t["share"] >= 0.02


def test_u8_row2_the_ranking_says_which_channels_he_grazes_and_which_he_follows():
    I = ins()
    s = top(kind="channels", channels=[
        {"name": "Clip Barn", "items": 130, "days": 40, "shorts_share": 0.95, "area": "gaming"},
        {"name": "Deep Space Weekly", "items": 120, "days": 92, "shorts_share": 0.0, "area": "science"},
        {"name": "Edit Hive", "items": 110, "days": 30, "shorts_share": 1.0, "area": "film and TV"},
        {"name": "Map Runner", "items": 100, "days": 97, "shorts_share": 0.02, "area": "gaming"}])
    o = [x for x in I.code_form(s)["observations"] if "grazed" in x["text"]]
    assert o and o[0]["must"] and o[0]["text"] == (
        "Clip Barn and Edit Hive are clip channels you grazed (95% and 100% Shorts); Deep Space Weekly and Map Runner "
        "are long-form channels you kept coming back to (on 92 and 97 days).")


# ================================ U9: one measure in lead and chart; whose Shorts ===============================
def test_u9_month_bars_that_add_up_to_more_than_the_count_say_what_they_count():
    I = ins()
    s = {"kind": "count", "lang": "en", "topics": [{"name": "minecraft", "items": 20}], "totals": {"items": 20},
         "periods": [{"label": "Sep 2026", "items": 14}, {"label": "Oct 2026", "items": 9}]}
    assert I.chart(s)[0].startswith("Videos opened per month (a video opened in two months counts in both):")
    s["periods"][1]["items"] = 6
    assert I.chart(s)[0].startswith("Videos opened per month:")


def test_u9_a_share_of_them_says_whose():
    I = ins()
    s = {"kind": "count", "lang": "en", "filters": {"topic": "minecraft"}, "topics": [{"name": "minecraft"}]}
    # round 12, pass 5: a Shorts share is of the YouTube videos, so under a topic "of your <topic> videos on YouTube"
    assert I.scoped("61% of them were Shorts.", s) == "61% of your minecraft videos on YouTube were Shorts."


# ================================ U10: the daily cap in the trace ===============================================
def test_u10_a_cap_reached_is_in_the_run_and_the_trace(wr, monkeypatch, capsys):
    monkeypatch.setattr(type(wr["bot"]), "_over_cap", lambda self, p: "daily")
    out, calls = ask(wr, "which channels did i watch the most in 2025")
    assert calls == []
    assert last_steps(wr)["writer"]["error"] == "daily cap reached"
    row = wr["bot"].store.q("SELECT error FROM runs ORDER BY id DESC LIMIT 1")[0]
    assert row["error"] == "daily cap reached"


def test_u10_the_readme_says_how_to_raise_the_cap_for_testing():
    text = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    part = text.split("Before you test history answers", 1)[1][:3000]
    assert "MVP_DAILY_CAP_USD" in part and "daily cap reached" in part


def test_u10_the_trace_prints_a_runs_error():
    src = open(os.path.join(HERE, "trace.py"), encoding="utf-8").read()
    assert "r.error AS run_error" in src and "run_error" in src


# ================================ the guards that must stay =====================================================
def test_guard_the_old_planted_sets_are_all_still_caught():
    from mvp import eval_insight as E
    rows = E.run("fake", E.load())
    s = E.summary(rows, "fake")
    assert s["caught"] == s["planted"] and s["true_kept"] == s["true_obs"]
    assert s["caught_v5"] == s["planted_v5"] and s["kept_v5"] == s["true_v5"]


def test_guard_a_top_sheet_copy_is_untouched_by_the_checks():
    I = ins()
    s = top()
    before = copy.deepcopy(s)
    I.fill(I.check({"answer": "{areas[0].name} led.", "observations": []}, s, strict=True),
           {"answer": "{areas[0].name} led.", "observations": []}, s)
    assert s == before and TOP["areas"][0]["share"] == 0.22


# ================================ what my own live reading found (the real library; made-up data here) ==========
def test_live_a_so_what_about_saved_clips_under_the_pick_of_the_shorts_shift_is_said_as_the_shift():
    # live, row 8: "You might want to save the <clips theme> you left unopened: 6 are waiting." went out under the pick
    # of the Shorts shift (its saved clips are no candidate)
    I = ins()
    s = top()
    s["areas"][3]["change_vs_previous"] = -0.01   # no "what is changing" so-what
    s["library"] = {"saved_not_opened": [{"theme": "Sketch edits", "n": 6}]}
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.5}]
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "observations": [{"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                            {"text": "{areas[1].name} was {areas[1].share}.", "uses": []}],
           "so_what": {"pick": "shorts_shift:up", "text": "You might want to save the "
                                                          "{library.saved_not_opened[0].theme} you left unopened: "
                                                          "{library.saved_not_opened[0].n} are waiting."}}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert ("so_what", "not_its_candidate") in [(d[0], d[1]) for d in f["dropped"]]
    # round 12, pass 4 (V4, changed on purpose): the shift is said in code's words, as a bullet (it has no step)
    assert not f["so_what"] and any(x.startswith("Shorts went up to 74%") for x in f["observations"]), f


def test_live_a_bullet_that_names_the_same_two_names_twice_is_filler():
    # live, row 6: "2 channels were new that day: A and B; A and B were also first watched that day."
    kept, why = obs("{new.channels[0]} and {new.channels[1]} were new, with {channels[0].days} days; "
                    "{new.channels[0]} and {new.channels[1]} were also first opened then.",
                    top(new={"themes": [], "channels": ["Pixel Forge", "Doggo Plays"]}))
    assert kept is None and why == ["filler"], why
    kept, why = obs("{channels[0].name} came on {channels[0].days} days and {channels[1].name} on "
                    "{channels[1].days}.")
    assert kept and not why


def test_live_a_bullet_with_the_so_whats_two_shares_goes_however_it_says_shorts():
    # live, row 3: "minecraft rose from 20% shorts to 61%, and <theme> gained 20 points ..." above the so-what
    # "Shorts went up to 61% of your minecraft videos, from 20% ..."
    I = ins()
    s = top()
    s["areas"][3]["change_vs_previous"] = -0.01
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.737,
                                "previous_share": 0.682}]
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "observations": [{"text": "Your videos rose from {previous.shorts_share} shorts to {totals.shorts_share} "
                                     "against {previous.words}.", "uses": []},
                            {"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                            {"text": "{areas[1].name} was {areas[1].share}.", "uses": []}],
           "so_what": {"pick": "shorts_shift:up", "text": None}}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    # round 12, pass 4 (V4, changed on purpose): the shift is a bullet (no step), said once, in code's words
    both = [x for x in f["observations"] if "74%" in x and "68%" in x]
    assert not f["so_what"] and len(both) == 1 and both[0].startswith("Shorts went up"), f["observations"]


def test_live_a_change_over_the_years_says_its_two_years():
    # live, row 7: "Gaming faded from 22% to 16%, while internet culture rose from 4% to 9%." (no years)
    I = ins()
    s = _changed()
    f = I.check({"answer": "-", "observations": [{"text": "{areas_change.left[0].name} faded from "
                                                          "{areas_change.left[0].from_share} to "
                                                          "{areas_change.left[0].to_share}, while "
                                                          "{areas_change.arrived[0].name} rose.", "uses": []}]},
                s, strict=True)
    assert f["observations"] == ["Gaming faded from 22% to 16% between 2020 and 2026, while comedy rose."], f
