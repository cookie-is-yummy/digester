"""Round 12, third pass, the second fixer (DESIGN.md section 19.P3 fix): what two judges still found in the live
history answers after a0e0010, each reproduced on made-up data (every test here fails on a0e0010), fixed, and guarded
with its near variants.

Made-up data only: the sheets shaped like the real ones of tests/test_round12_pass2_fix.py (TOP, DAY), small sheets
built here, and the made-up library (tests/r12_library.py).
"""
import copy
import re

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, mods, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_pass2 import sheet_of
from mvp.tests.test_round12_pass2_fix import TOP, DAY, top


def ins():
    from mvp import insight
    return insight


def lately():
    """TOP with its so-what candidates as the sheet has them (the move: gaming 12% to 22%, sports 16% to 9%)."""
    F = mods()[1]
    s = top()
    s["so_what_candidates"] = F._so_what_candidates(s, "top", None)
    return s


RAW = {"answer": "{areas[0].name} led with {areas[0].share}, then {areas[1].name} ({areas[1].share}).",
       "observations": [{"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                        {"text": "{areas[1].name} was {areas[1].share}.", "uses": []}]}


def written(s, raw=None):
    I = ins()
    raw = copy.deepcopy(raw or RAW)
    return I.fill(I.check(raw, s, strict=True), raw, s)


# ================================ row 1: lead with the change; one fall once; a so-what to act on ===============
def test_row1_the_leaders_move_leads_and_the_so_what_is_what_fell_with_its_follow_up():
    f = written(lately())
    assert f["answer"].startswith("Gaming nearly doubled to 22% of what you opened, from 12% in the 4 weeks before"), f
    assert f["so_what"].startswith("Worth noticing: sports fell from 16% to 9% against the 4 weeks before")
    assert 'Say "only sports"' in f["so_what"]
    assert not any("gaming grew" in o.lower() for o in f["observations"])


def test_row1_asked_again_the_lead_stays_and_says_both_sides_and_no_bullet_says_them_again():
    # judge A (thread row 74): the second answer re-said the lead in a bullet
    s = lately()
    s["moving_lead"] = s["so_what_candidates"][0]
    s["so_what_candidates"] = []                  # the so-what was said on the answer before
    raw = copy.deepcopy(RAW)
    raw["observations"].append({"text": "{areas[0].name} grew by {areas[0].change_vs_previous} from {previous.words}, "
                                        "while {areas[3].name} fell by {areas[3].change_vs_previous}.", "uses": []})
    f = written(s, raw)
    assert f["answer"].startswith("Gaming nearly doubled to 22%") and "sports fell from 16% to 9%" in f["answer"], f
    assert not f["so_what"]
    assert not any("grew" in o or "fell" in o for o in f["observations"]), f["observations"]


def test_row1_a_themes_fall_inside_an_area_whose_fall_is_said_goes():
    I = ins()
    s = lately()
    s["themes"].append({"name": "Trick shots", "area": "sports", "items": 36, "share": 0.036, "previous_share": 0.06,
                        "previous_items": 54, "change_vs_previous": -0.024, "days": 10})
    f = {"answer": "Gaming led.", "so_what": "Worth noticing: sports fell from 16% to 9% against the 4 weeks before.",
         "observations": ["Trick shots fell from 6% to 4% against the 4 weeks before.", "Meme drops came on 20 days.",
                          "Speed runs came on 18 days."], "dropped": []}
    out = I._last_reads(f, s, I.Facts(I.shown(s)))
    assert out["observations"] == ["Meme drops came on 20 days.", "Speed runs came on 18 days."]
    # near variant: the same theme moving the other way, or an area not said to move, stands
    f2 = dict(f, observations=["Trick shots grew from 4% to 6%.", "Meme drops came on 20 days.",
                               "Speed runs came on 18 days."], dropped=[])
    assert len(I._last_reads(f2, s, I.Facts(I.shown(s)))["observations"]) == 3


def test_row1_and_row8_a_spans_dates_are_said_once():
    I = ins()
    s = lately()
    form = {"answer": "Gaming led.", "observations": [
        "Sports fell from 16% to 9% against the 4 weeks before (5 September to 2 October 2026).",
        "Comedy fell from 14% to 11% against the 4 weeks before (5 September to 2 October 2026)."],
        "so_what": "Worth noticing: gaming grew against the 4 weeks before (5 September to 2 October 2026).",
        "offers": []}
    text = I.layout(form, s)[0]["text"]
    assert text.count("(5 September to 2 October 2026)") == 1 and text.count("the 4 weeks before") == 3


def test_a_move_whose_two_values_read_the_same_goes():
    I = ins()
    assert I._flat_move("Gaming fell from 17% in the 90 days before to 17%, while sports rose from 6% to 10%.")
    assert not I._flat_move("Gaming fell from 21% to 16%.")


# ================================ "the last 3 months": the last 90 days the record holds ======================
def test_the_last_3_months_is_the_last_90_days_the_record_holds(r12):
    s = sheet_of(r12, "what have i been into the last 3 months")
    w = s["window"]
    from datetime import date
    a, b = date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
    assert (b - a).days == 89 and w["words"].startswith("the last 90 days up to"), w
    assert "90 days before" in (s.get("previous") or {}).get("words", ""), s.get("previous")


def test_a_base_goes_after_the_changes_last_value_never_after_a_question():
    # judge A: "...; what would you like to lean into next? against the 67 days before (...)"
    I = ins()
    s = top()
    t, why = I.render("{areas[3].name} fell from {areas[3].previous_share} to {areas[3].share}; what would you like "
                      "to lean into next?", s, I.Facts(I.shown(s)), strict=True)
    assert why is None and t.startswith("sports fell from 16% to 9% against the 4 weeks before"), t
    assert t.endswith("what would you like to lean into next?")


# ================================ Shorts said once (row 6, "into lately") ======================================
def test_a_count_of_shorts_is_the_same_fact_as_codes_shorts_share():
    I = ins()
    for t in ("9 of 10 videos were Shorts, while one channel was long.", "867 of your 1,437 videos were Shorts.",
              "Your watching was mostly Shorts at 82%."):
        assert I._SHORTS_SUBJ.search(I._norm(t)), t
    s = copy.deepcopy(DAY)
    s["window"] = dict(s["window"], words="On Saturday 12 September 2026")
    raw = {"answer": "{totals.items} videos.", "observations": [
        {"text": "{totals.shorts} of {totals.items} videos were Shorts.", "uses": []},
        {"text": "{channels[0].name} gave {channels[0].items} of them.", "uses": []}]}
    f = written(s, raw)
    assert sum("Shorts" in o for o in f["observations"]) == 1, f["observations"]


# ================================ row 6: a day in counts, never against the export's cut-off ================
def test_row6_the_exports_last_day_is_not_set_against_a_usual_day_and_its_leader_is_a_count():
    I = ins()
    s = copy.deepcopy(DAY)   # "the last day of your export"
    f = I.check(I.code_form(s), s)
    assert f["answer"] == "10 videos; Meme drops led with 3 of them.", f["answer"]
    assert not any("usual day peaks" in o or "as on a usual day" in o for o in f["observations"])
    assert any(o.endswith("on a usual day of the months before.") for o in f["observations"])


def test_row6_a_whole_day_says_what_a_usual_day_is_and_came_next_is_filler():
    I = ins()
    s = copy.deepcopy(DAY)
    s["window"] = dict(s["window"], words="On Saturday 12 September 2026")
    f = I.check(I.code_form(s), s)
    assert f["answer"].startswith("10 videos, fewer than on a usual day of the three months before (32); Meme drops "
                                  "led with 3 of them."), f["answer"]
    assert not any("came next" in o for o in f["observations"])
    raw = {"answer": "{totals.items} videos.", "observations": [
        {"text": "{themes[1].name} came next ({themes[1].share}).", "uses": []},
        {"text": "{channels[0].name} gave {channels[0].items} of them.", "uses": []},
        {"text": "{themes[0].name} had {themes[0].items}.", "uses": []}]}
    assert not any("came next" in o for o in written(s, raw)["observations"])


# ================================ a change between two closed years; row 7's turn ==============================
def _two_years():
    return {"question": "how did my watching change from 2023 to 2025", "kind": "changed", "lang": "en",
            "filters": {"topic": None, "without_shorts": False},
            "window": {"words": "From 1 January 2023 to 31 December 2025", "start": "2023-01-01",
                       "end": "2025-12-31", "clipped": False},
            "totals": {"items": 6000, "days_active": 1000, "shorts": 3000, "long": 2500},
            "periods": [{"label": str(y), "items": 2000, "areas": [{"name": "gaming", "share": g}],
                         "shorts_share": 0.6} for y, g in ((2023, 0.14), (2024, 0.19), (2025, 0.18))],
            "eras": [{"from": "2023", "to": "2025", "area": "gaming", "share": 0.17}],
            "areas_change": {"from": "2023", "to": "2025",
                             "left": [{"name": "comedy", "from_share": 0.13, "to_share": 0.09, "change": -4.0}],
                             "arrived": [{"name": "gaming", "from_share": 0.14, "to_share": 0.18, "change": 4.0}],
                             "shorts": {"from": "2023", "from_share": 0.70, "to": "2025", "to_share": 0.58}},
            "themes": [], "areas": [], "channels": [], "offers": ["without_shorts"]}


def test_a_change_between_two_closed_years_whose_leader_grew_says_it_once():
    # judge A: "gaming has led every year since 2023; around it, gaming rose from 14% in 2023 to 18% in 2025"
    a = ins().code_form(_two_years())["answer"]
    assert a == "Gaming led every year and grew, from 14% in 2023 to 18% in 2025, while comedy fell from 13% to 9%.", a
    assert "since" not in a and "around it" not in a


def _arc(lang="en"):
    from mvp.tests.test_round12_pass3 import _changed
    s = _changed()
    s["lang"] = lang
    for p, sh in zip(s["periods"], (0.04, 0.14, 0.22, 0.70, 0.35, 0.58, 0.81)):
        p["shorts_share"] = sh
    return s


def test_row7_the_turn_year_is_tied_to_the_move_to_shorts():
    a = ins().code_form(_arc())["answer"]
    assert "then down to 30% in 2023, the year you moved to Shorts, and 16% in 2026" in a, a


def test_row7_in_spanish_is_the_same_answer_and_the_same_chart():
    # judge A (thread row 70): the Spanish answer led with Shorts and charted the Shorts share
    I = ins()
    a = I.code_form(_arc("es"))["answer"]
    assert a.startswith("Gaming lideró cada año, pero su peso cambió: 22% en 2020") and "2023" in a, a
    assert I.chart(_arc("es"))[0].startswith("La parte de gaming en cada año:")


# ================================ row 8: a season that moved to Shorts leads with it ===========================
def _summer():
    s = top()
    s["question"] = "what was i into in the summer of 2023"
    s["window"] = {"words": "the summer of 2023 (1 June to 31 August 2023)", "start": "2023-06-01",
                   "end": "2023-08-31", "clipped": False}
    s["totals"] = dict(s["totals"], shorts_share=0.82)
    s["previous"] = dict(s["previous"], shorts_share=0.29, words="the spring before (1 March to 31 May 2023)")
    s["areas"][0] = dict(s["areas"][0], share=0.10, previous_share=0.33, change_vs_previous=-0.23)
    s["areas"][1] = dict(s["areas"][1], share=0.14, previous_share=0.08, change_vs_previous=0.06)
    s["areas"] = sorted(s["areas"], key=lambda a: -a["share"])
    s["distinct"] = {"rest_words": "the rest of 2023", "themes": [
        {"name": "Sketch edits", "share": 0.056, "rest_share": 0.035}, {"name": "Meme drops", "share": 0.038,
                                                                        "rest_share": 0.021}]}
    s["so_what_candidates"] = [{"key": "shorts_shift:up", "kind": "shorts_shift", "direction": "up", "share": 0.82,
                                "previous_share": 0.29}]
    return s


def test_row8_the_move_to_shorts_and_what_fell_lead_and_the_so_what_does_not_say_them_again():
    s = _summer()
    cf = ins().code_form(s)
    assert cf["answer"].startswith("you moved to Shorts: 82% of your YouTube videos, from 29% in the spring before, "
                                   "while gaming fell from 33% to 10%"), cf["answer"]
    f = written(s)
    assert f["answer"].lower() == cf["answer"].lower() and not (f["so_what"] or "").startswith("Shorts")


def test_row8_weak_differences_are_said_as_small():
    # round 12, pass 4 (V2, changed on purpose): "Little else set the summer apart ..." is filler; when nothing ran
    # at twice its share of the rest of the year, nothing is said about it
    obs = [o["text"] for o in ins().code_form(_summer())["observations"]]
    assert not any("set the summer apart" in o for o in obs), obs


# ================================ row 4: what the split is of, the part of the year, whose Shorts ==============
def test_row4_the_split_says_what_it_is_of_and_a_writers_split_with_no_base_is_replaced():
    I = ins()
    tot = {"items": 300, "shorts": 90, "long": 201, "long_median_min": 11, "by_platform": {"youtube": 291}}
    assert I._split_line(tot) == "Of the 291 on YouTube, 201 were long videos, typically about 11 minutes, and 90 Shorts."
    s = {"kind": "first", "lang": "en", "totals": tot, "filters": {"topic": "blender"}}
    assert I._split_no_base("90 Shorts and 201 long videos show a mixed format.", s)
    assert not I._split_no_base("Of the 291 on YouTube, 201 were long and 90 Shorts.", s)


def test_row4_the_path_names_its_subject_and_the_part_of_the_year():
    I = ins()
    c = {"kind": "path", "how": "faded", "last_label": "2026", "last_items": 12, "peak_label": "2023",
         "peak_items": 131}
    s = {"window": {"end": "2026-10-30"}, "filters": {"topic": "blender"}}
    # round 12, pass 6 (X15, on purpose): the arc as something to notice, when it peaked and what it is now
    assert I.so_what_text(c, s, topic="blender") == ("You were deepest into blender in 2023 (131 videos); in 2026 up to "
                                                     "30 October it was 12.")


def test_row4_a_topics_shorts_share_is_of_its_own_videos():
    # judge B: "31% of your YouTube videos watched was Shorts" was the share of the blender videos
    s = {"kind": "first", "lang": "en", "filters": {"topic": "blender"}}
    assert ins().scoped("31% of your YouTube videos watched were Shorts.", s) == \
        "31% of your blender videos on YouTube were Shorts."


# ================================ row 5: a chart that says more than the answer ================================
def test_row5_the_comparisons_chart_sets_each_side_against_the_span_before():
    I = ins()
    s = {"kind": "compare_topics", "lang": "en", "window": {"start": "2026-01-01"},
         "previous": {"words": "the same part of 2025 (1 January to 30 October 2025)"},
         "topics": [{"name": "gaming", "items": 3455, "previous_items": 3093},
                    {"name": "art", "items": 375, "previous_items": 221}]}
    text, _ = I.chart(s)
    assert text.splitlines()[0] == "Videos opened, by topic, against the same part of 2025:"
    assert [ln.split(" ", 1)[1] for ln in text.splitlines()[1:]] == ["3,455 gaming 2026", "3,093 gaming 2025",
                                                                     "375 art 2026", "221 art 2025"]
    # near variant: a count's chart by topic is as before
    c = {"kind": "count", "lang": "en", "topics": [{"name": "x", "items": 5}, {"name": "y", "items": 3}], "periods": []}
    assert I.chart(c)[0].startswith("Videos opened, by topic:")
    assert re.match(r"^\S+ 5 x$", I.chart(c)[0].splitlines()[1])


# ================================ row 3: a count as counted ====================================================
def test_row3_no_about_on_a_count_and_what_it_counts_once():
    s = {"kind": "count", "lang": "en", "filters": {"topic": "block games"},
         "topics": [{"name": "block games", "items": 1094, "matched_by": "themes and words"}]}
    out = ins().scoped("This year you opened about 1,094 block games videos, mostly builds.", s, answer=True)
    # round 12, pass 4 (V6, changed on purpose): what it counts, in words ("by their titles and themes" read as a guess)
    assert out == "This year you opened 1,094 videos whose title or theme is about block games, mostly builds."


# ================================ row 2: channels ==============================================================
def _channels():
    return {"question": "which channels did i watch the most in 2025", "kind": "channels", "lang": "en",
            "filters": {"topic": None, "without_shorts": True},
            "window": {"words": "2025", "start": "2025-01-01", "end": "2025-12-31", "clipped": False},
            "totals": {"items": 900, "days_active": 300},
            "channels": [{"name": "Orbit Notes", "items": 125, "days": 92, "theme": "Space talks", "area": "science"},
                         {"name": "Pixel Forge", "items": 105, "days": 97, "theme": "Speed runs", "area": "gaming"},
                         {"name": "Meme Vault", "items": 93, "days": 60, "theme": "Meme drops",
                          "area": "internet culture"}],
            "themes": [{"name": "Space talks", "area": "science", "items": 130, "share": 0.14},
                       {"name": "Speed runs", "area": "gaming", "items": 120, "share": 0.13}],
            "areas": [], "so_what_candidates": [], "offers": []}


def test_row2_the_lead_is_in_words_and_the_chart_carries_the_counts():
    I = ins()
    s = _channels()
    cf = I.code_form(s)
    assert cf["answer"] == "Orbit Notes led, ahead of Pixel Forge and Meme Vault."
    assert I.check(cf, s)["answer"] == cf["answer"]
    assert I.chart(s)[0].splitlines()[1].endswith("125 Orbit Notes")


def test_row2_a_bullet_that_says_the_leader_led_again_goes():
    I = ins()
    s = _channels()
    f = {"answer": "Orbit Notes led, ahead of Pixel Forge and Meme Vault.", "so_what": None, "dropped": [],
         "observations": ["Orbit Notes was the top channel, tied to Space talks.", "Pixel Forge came on 97 days.",
                          "Meme Vault came on 60 days."]}
    assert I._last_reads(f, s, I.Facts(I.shown(s)))["observations"] == ["Pixel Forge came on 97 days.",
                                                                        "Meme Vault came on 60 days."]


def test_row2_a_change_from_a_count_and_a_move_with_one_value_go():
    I = ins()
    s = _channels()
    f = {"answer": "Orbit Notes led.", "so_what": None, "dropped": [], "observations": [
        "Speed runs jumped from 35 in 2024 to 341.", "Gaming slipped from 22% in 2024.",
        "Pixel Forge came on 97 days.", "Meme Vault came on 60 days."]}
    assert I._last_reads(f, s, I.Facts(I.shown(s)))["observations"] == ["Pixel Forge came on 97 days.",
                                                                        "Meme Vault came on 60 days."]


def test_row2_both_filters_are_said_on_a_chained_follow_up():
    from mvp import history as Hm
    q = Hm.read("which channels did i watch the most in 2025", TODAY).model_copy(update={"without_shorts": True})
    assert Hm._taken_words("only_topic:gaming", q, {}) == "Only gaming, without Shorts:"
    assert Hm._taken_words("only_topic:gaming", q.model_copy(update={"without_shorts": False}), {}) == "Only gaming:"


def test_a_saved_so_what_with_no_offer_gets_codes_words():
    # live, math: "You saved 11 <a theme>."
    I = ins()
    s = _channels()
    s["so_what_candidates"] = [{"key": "saved:Space talks", "kind": "saved", "theme": "Space talks", "n": 11}]
    s["library"] = {"saved_not_opened": [{"theme": "Space talks", "n": 11}]}
    raw = {"answer": "{channels[0].name} led, ahead of {channels[1].name}.",
           "observations": [{"text": "{channels[1].name} came on {channels[1].days} days.", "uses": []},
                            {"text": "{channels[2].name} came on {channels[2].days} days.", "uses": []}],
           "so_what": {"pick": "saved:Space talks", "text": "You saved {so_what_candidates[0].n} "
                                                             "{so_what_candidates[0].theme}."}}
    f = written(s, raw)
    assert f["so_what"] == "You saved 11 Space talks videos you never opened. Want them as a list?", f


# ================================ row 7: a 3% top theme is filler ==============================================
def test_row7_a_biggest_theme_of_a_few_percent_is_filler():
    I = ins()
    s = _channels()
    f = {"answer": "Orbit Notes led.", "so_what": None, "dropped": [], "observations": [
        "The biggest theme now is Space talks at 3%, and its channels are Orbit Notes and Pixel Forge.",
        "Pixel Forge came on 97 days.", "Meme Vault came on 60 days."]}
    assert len(I._last_reads(copy.deepcopy(f), s, I.Facts(I.shown(s)))["observations"]) == 2
    f["observations"][0] = "The biggest theme now is Space talks at 14%."
    assert len(I._last_reads(copy.deepcopy(f), s, I.Facts(I.shown(s)))["observations"]) == 3



# ================================ the live reading of this fix: half a repeat, the usual day said twice =========
def test_live_a_bullet_whose_moves_the_answer_half_says_goes():
    # live, row 8: "comedy rose by 6 points and gaming fell by 23 points" under "while gaming fell from 33% to 10%"
    I = ins()
    s = _summer()
    f = I.Facts(I.shown(s))
    x = "Compared with the spring before, comedy rose by 6 points and gaming fell by 23 points."
    assert I._nested_move(x, ["You moved to Shorts, while gaming fell from 33% to 10%."], s, f)
    assert not I._nested_move(x, ["You moved to Shorts."], s, f)


def test_live_a_days_bullet_that_says_the_usual_day_again_goes():
    # live, 12 September: "2pm was the busiest hour, and 39 is your usual day's median" under the answer that says 39
    I = ins()
    s = copy.deepcopy(DAY)
    s["window"] = dict(s["window"], words="On Saturday 12 September 2026")
    f = {"answer": "10 videos, fewer than on a usual day of the three months before (32).", "so_what": None,
         "dropped": [], "observations": ["2pm was the busiest hour, and 32 is your usual day's median.",
                                         "Pixel Forge gave 2 of them.", "Block battles had 1."]}
    assert I._last_reads(f, s, I.Facts(I.shown(s)))["observations"] == ["Pixel Forge gave 2 of them.",
                                                                        "Block battles had 1."]
