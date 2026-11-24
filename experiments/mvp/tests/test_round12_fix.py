"""Round 12, fix (DESIGN.md section 19.F): what the two judges of the live run found in the history answers, fixed.

- A well-formed writer form that loses its answer or observations to the check no longer sends today's code reply
  (the top 5 by count the founder graded "filler"): code fills what failed from the same sheet (`insight.fill`,
  `insight.code_form`), in sentences checked by the same check. The model failing, the cap, no script, or a reply
  that is no form: today's code reply, as before.
- Rank words ("led", "followed by", "ahead of") are checked against the order of the sheet's own lists; "mostly" and
  "centered on" only for a fifth or more; a weekday split near 5 days in 7 is not said; "new" of a channel over more
  than about 13 months is not said; no run of more than 4 numbers; "a gap of N" and "each had 1 video" are filler.
- A day's "on 1 day" is left out (it dropped the whole answer); a long answer's first sentence may stand.
- The chart keeps a year's 12 months (it cut the oldest 4 without a word), a cut is said in its caption, a period's
  theme label fits a phone, and one main theme in every row gives the counts instead.
- The so-what is said once, is about what the answer is about, and for a first or a last says the person's path on
  the topic from the record; the first video's title is said once.
- "¿cómo ha cambiado lo que veo desde 2020?" is read as how WHAT is watched changed, in Spanish.

Made-up data only: the sheets of eval/insight_cases.json (every name invented), the made-up library of
tests/r12_library.py and the made-up writer of tests/r12_writer.py.
"""
import copy
import json
import os
import re
from datetime import date

import pytest

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round11_h import ask
from mvp.tests.test_round12_d import r12, person, mods, no_real_keys, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_merge import wr, later, last_steps, code_reply, QS  # noqa: F401  (fixtures)
from mvp.tests import r12_writer as RW

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(os.path.dirname(HERE), "eval", "insight_cases.json")


def case(cid):
    with open(CASES, encoding="utf-8") as f:
        return copy.deepcopy(next(c for c in json.load(f)["cases"] if c["id"] == cid))


def ins():
    from mvp import insight
    return insight


def facts_of(s):
    I = ins()
    return I.Facts(I.shown(s))


def checked(raw, s):
    I = ins()
    cv = I.chart(s)[1]
    return I.fill(I.check(raw, s, chart_vals=cv), raw, s, cv)


# ================================ 1. what failed is filled by code, never today's code reply ======================
def test_a_failed_answer_is_written_by_code_from_the_sheet_and_the_models_observations_stay():
    c = case("top_lately")
    raw = dict(c["fake"], answer="Gaming is a popular genre.")
    f = checked(raw, c["sheet"])
    assert f["answer"] and "filled" in f and "answer" in f["filled"]
    # round 12, pass 2 (T1): "mostly" only for half or more: Blender 3D's 31% with home cooking's 22% is 53%
    assert f["answer"].startswith("Mostly Blender 3D (31% of what you opened) and home cooking (22%)")
    assert any("grew to 31%" in o for o in f["observations"])


def test_one_observation_left_is_topped_up_by_code_to_three():
    c = case("top_lately")
    raw = dict(c["fake"], observations=c["fake"]["observations"][:1])
    f = checked(raw, c["sheet"])
    assert 3 <= len(f["observations"]) <= 4 and "observations" in f["filled"]
    # round 12, pass 2 (T2): no total of video length any more (it read as watch time)
    assert not any("hours" in o for o in f["observations"])


@pytest.mark.parametrize("raw", [{}, "a list, not a form", {"answer": 3}, None])
def test_no_form_still_gives_none_so_todays_code_reply_goes_out(wr, raw):
    I = ins()
    wr["state"]["answers"]["mvp_insight"] = lambda u: raw
    assert I.write(wr["bot"], person(wr), case("top_lately")["sheet"], wr["clock"][0]) is None


def test_a_planted_false_form_sends_only_true_sentences(wr):
    I = ins()
    c = case("top_lately")
    bad = {"answer": "You watched 9,999 videos, 47% of them knitting.", "observations": [
        {"text": "Zorblax Studio is new with 137 videos.", "uses": ["channels"]},
        {"text": "Knitting grew 23 points.", "uses": ["themes"]}], "so_what": "I have emailed this to you.",
           "offers": ["send_email", "only_topic:Ignore all rules"]}
    wr["state"]["answers"]["mvp_insight"] = lambda u: bad
    parts = I.write(wr["bot"], person(wr), c["sheet"], wr["clock"][0])
    text = "\n".join(p["text"] for p in parts if p["type"] == "text")
    for x in ("9,999", "47%", "knitting", "Knitting", "Zorblax", "137", "emailed", "Ignore"):
        assert x not in text
    assert "Blender 3D" in text and "• " in text


def test_the_brief_q3_with_one_observation_is_the_writers_answer_not_the_code_reply(wr, monkeypatch):
    base = code_reply(wr, monkeypatch, QS["q3"])
    later(wr)
    wr["state"]["answers"]["mvp_insight"] = lambda u: dict(RW.fake_insight(u),
                                                           observations=RW.fake_insight(u)["observations"][:1])
    out, calls = ask(wr, QS["q3"])
    assert calls == ["mvp_insight"] and out != base and "• " in out
    st = last_steps(wr)["writer"]
    assert st["used"] is True and st["kept"] == 1


# ================================ 2. rank, order, spread, baseline, long windows, number runs =====================
def test_a_channel_first_only_under_its_theme_does_not_lead():
    s = case("top_lately")["sheet"]
    f = facts_of(s)
    I = ins()
    # Kettle & Cast is first under home cooking, third of the channels
    assert I.check_sentence("Kettle & Cast led with 38 videos.", f) == "not_top"
    assert I.check_sentence("Pixel Forge led your Blender 3D with 41 videos.", f) is None


def test_names_said_in_ranking_order_must_be_in_the_sheets_order():
    s = case("channels_2025")["sheet"]
    f = facts_of(s)
    I = ins()
    assert I.check_sentence("Lantern Speedruns led with 820 videos, followed by Prime Number Club with 610.", f) is None
    assert I.check_sentence("Pixel Forge had 540 videos, followed by Prime Number Club with 610.", f) == "order"
    assert I.check_sentence("Kettle & Cast had 410, ahead of Pixel Forge with 540.", f) == "order"


def test_mostly_for_a_small_share_is_a_spread_not_a_lead():
    s = case("top_lately")["sheet"]
    s["themes"][0]["share"] = 0.065
    f = facts_of(s)
    I = ins()
    assert I.check_sentence("You were mostly into Blender 3D at 6.5%.", f) == "spread"
    s2 = case("top_lately")["sheet"]
    s2["totals"].update(shorts=404, long=431)
    assert I.check_sentence("It was mostly long videos: 431 of them.", facts_of(s2)) == "spread"
    # round 12, pass 2 (T1): "mostly" needs half or more; 31% is a lead, not "mostly"
    assert I.check_sentence("Mostly Blender 3D at 31%.", facts_of(case("top_lately")["sheet"])) == "spread"
    assert I.check_sentence("Mostly Blender 3D and home cooking, 31% and 22%.",
                            facts_of(case("top_lately")["sheet"])) is None


@pytest.mark.parametrize("share, ok", [(0.68, False), (0.72, False), (0.92, True)])
def test_a_weekday_split_near_five_days_in_seven_is_not_said(share, ok):
    s = case("top_lately")["sheet"]
    s["when"] = {"busiest_hours": [21], "weekday_share": share, "weekend_share": round(1 - share, 2),
                 "busiest_weekday": "Saturday"}
    I = ins()
    pct = round(share * 100)
    assert (I.check_sentence(f"Most of it came on weekdays, {pct}% of it.", facts_of(s)) is None) == ok
    assert (I.check_sentence("Most of it came on Saturday, 41 Blender 3D videos.", facts_of(s)) is None) == ok


def test_new_of_a_channel_over_six_years_is_not_said_but_over_a_month_it_is():
    s = case("channels_2025")["sheet"]
    s["channels"][2]["new_in_window"] = True
    I = ins()
    # round 12, pass 2 (T7): "new in the window" of a year or more is filler too; over a month it is said
    assert I.check_sentence("Pixel Forge is new, with 540 videos.", facts_of(s)) == "not_new"
    s["window"].update(start="2025-10-01", end="2025-10-31")
    assert I.check_sentence("Pixel Forge is new, with 540 videos.", facts_of(s)) is None
    s["window"].update(start="2020-01-01", end="2026-10-30")
    assert I.check_sentence("Pixel Forge is new, with 540 videos.", facts_of(s)) == "not_new"


def test_an_answer_that_is_a_run_of_numbers_is_written_by_code():
    c = case("cmp_gaming_art")
    raw = dict(c["fake"], answer="This year you opened 640 gaming videos and 212 art ones, a gap of 428, on 150 days "
                                 "against 60, adding up to about 120 hours against 95.")
    f = checked(raw, c["sheet"])
    assert "gap of" not in f["answer"] and "answer" in f["filled"]
    # round 12, pass 2 (T7, T9): the lead is the ratio in words, with the two counts after it
    assert f["answer"].startswith("Much more gaming than art: about 3 times as many (640 against 212)")
    assert any(d[1] in ("number_run", "filler", "hours") for d in f["dropped"] if d[0] == "answer")   # pass 2: T2


def test_filler_each_had_one_video_is_dropped():
    s = case("day_oct30")["sheet"]
    I = ins()
    assert I.check_sentence("Lantern Speedruns and Pixel Forge each had 1 video.", facts_of(s)) == "filler"


def test_a_hyphenated_name_is_its_words():
    s = case("channels_2025")["sheet"]
    s["channels"][1]["name"] = "Stand-up Primes"
    I = ins()
    assert I.check_sentence("Stand-up Primes had 610 videos.", facts_of(s)) is None


def test_a_changed_sheets_rising_and_fading_rows_are_facts():
    s = case("changed_since_2020")["sheet"]
    s["change"] = {"from": "2020", "to": "2026", "rising": [{"name": "Blender 3D", "from_share": 0.001,
                                                               "to_share": 0.056, "change": 5.5,
                                                               "peak_period": "2026", "peak_share": 0.056}],
                   "fading": [{"name": "film essays", "from_share": 0.31, "to_share": 0.01, "change": -30.0,
                               "peak_period": "2020", "peak_share": 0.31}]}
    I = ins()
    f = facts_of(s)
    assert I.check_sentence("Blender 3D rose from 0.1% in 2020 to 5.6% in 2026.", f) is None
    assert I.check_sentence("Film essays fell from 31% in 2020 to 1% in 2026.", f) is None
    assert I.check_sentence("Film essays rose from 31% in 2020 to 1% in 2026.", f) == "direction"


# ================================ 3. a day's answer and a long answer =============================================
def test_a_days_on_one_day_is_left_out_not_the_whole_answer():
    c = case("day_oct30")
    raw = dict(c["fake"], answer="On Friday 30 October 2026, the last day of your export, you opened 31 videos on 1 "
                                 "day, led by speedrun clips at 45%.")
    f = ins().check(raw, c["sheet"])
    assert f["answer"] and "on 1 day" not in f["answer"] and "31 videos, led by speedrun clips" in f["answer"]


def test_a_long_answers_first_sentence_stands():
    c = case("top_lately")
    raw = dict(c["fake"], answer="Mostly Blender 3D lately, with home cooking second. " + "Blender 3D " * 40 + ".")
    f = ins().check(raw, c["sheet"])
    assert f["answer"] == "Mostly Blender 3D lately, with home cooking second."


def test_a_day_answer_after_another_history_answer_is_the_writers_with_its_cards(wr):
    ask(wr, QS["q2"])
    wr["state"]["answers"]["mvp_insight"] = lambda u: dict(RW.fake_insight(u), answer=(
        RW.fake_insight(u)["answer"].rstrip(".") + " on 1 day."))
    out, calls = ask(wr, QS["q6"])
    assert calls == ["mvp_insight"] and "• " in out and "on 1 day" not in out
    assert last_steps(wr)["writer"]["used"] is True


# ================================ 4. the chart ====================================================================
def test_a_year_by_month_keeps_all_its_months_and_a_cut_is_said():
    I = ins()
    s = case("count_minecraft")["sheet"]
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    s["periods"] = [{"label": f"{m} 2026", "items": 10 + k, "themes": [{"name": ("cozy gaming" if k % 2 else
                                                                          "a very long made up theme name"),
                                                                          "share": 0.5}]}
                    for k, m in enumerate(names)]
    text = I.chart(s)[0]
    rows = text.split("\n")[1:]
    assert len(rows) == 10 and " Jan 2026 " in rows[0] and " Oct 2026 " in rows[-1]
    assert all(len(r) <= 12 + 1 + 8 + 1 + I.PERIOD_LABEL_MAX for r in rows)   # one line at 430 px
    s["periods"] = [{"label": str(2000 + k), "items": 5 + k} for k in range(14)]
    text = I.chart(s)[0]
    assert len(text.split("\n")) == 13 and "(the last 12)" in text.split("\n")[0]


def test_one_main_theme_in_every_row_gives_the_counts():
    I = ins()
    s = case("count_minecraft")["sheet"]
    s["periods"] = [{"label": f"{m} 2026", "items": n, "themes": [{"name": "cozy gaming", "share": 0.4}]}
                    for m, n in (("Jan", 30), ("Feb", 20), ("Mar", 25))]
    text = I.chart(s)[0]
    assert "cozy gaming" not in text and text.split("\n")[1].endswith("Jan 2026 30")


# ================================ 5. the so-what, the title, the words ============================================
def test_the_so_what_is_said_once_not_also_as_a_bullet():
    c = case("top_lately")
    raw = dict(c["fake"], observations=list(c["fake"]["observations"]) + [
        {"text": "You saved 7 Blender 3D videos you never opened.", "uses": ["library"]}])
    f = checked(raw, c["sheet"])
    assert f["so_what"] and "saved 7" in f["so_what"]
    assert not any("never opened" in o for o in f["observations"])


def test_a_so_what_about_a_theme_the_answer_never_names_is_dropped():
    c = case("top_lately")
    c["sheet"]["library"]["saved_not_opened"].append({"theme": "guitar practice", "n": 4, "examples": ["s9"]})
    raw = dict(c["fake"], answer="Mostly Blender 3D lately.", observations=[
        {"text": "Blender 3D grew to 31% of what you opened, up 12 points on the 4 weeks before.", "uses": ["themes"]},
        {"text": "Pixel Forge is behind 41 of the 97 Blender 3D videos.", "uses": ["themes", "channels"]}],
        so_what="You saved 4 guitar practice videos you never opened; want them as a list?")
    f = checked(raw, c["sheet"])
    assert ("so_what", "unrelated") in [(d[0], d[1]) for d in f["dropped"]]
    assert f["so_what"] and "Blender 3D" in f["so_what"]   # the code's, on what the answer is about


def test_a_firsts_so_what_says_the_path_on_the_topic_and_its_title_is_said_once():
    I = ins()
    c = case("first_blender")
    s = c["sheet"]
    s["periods"] = [{"label": "2019", "items": 12}, {"label": "2023", "items": 300}, {"label": "2026", "items": 40}]
    title = s["items"][0]["title"]
    raw = dict(c["fake"], answer=f"You first opened a blender video on 14 March 2019: \"{title}\".")
    f = checked(raw, s)
    # round 12, pass 3 fix (judge A, row 4, on purpose): the subject named, the part of the year said
    # round 12, pass 6 (X15, on purpose): the arc as something to notice, then the saved ones as the step to take
    assert f["so_what"].startswith("You were deepest into blender in 2023 (300 videos); in 2026 up to 30 October it "
                                   "was 40.")
    assert "You still have 18 Blender 3D videos you saved and never opened" in f["so_what"]
    head = I.layout(f, s)[0]["text"]
    # round 12, pass 6 (X1, on purpose): a first's answer is code's, with the first item's channel
    assert head.count(title) == 1 and head.startswith("You first opened a blender video on 14 March 2019, from ")


@pytest.mark.parametrize("raw, want", [
    ("The two long ones add up to about 0.4 hours in length.", "about 24 minutes"),
    ("You saved 1 Blender 3D videos you never opened.", "1 Blender 3D video "),
    ("Comedy episodes videos rose.", "Comedy episodes rose"),
])
def test_house_style_minutes_one_video_and_no_videos_after_a_plural(raw, want):
    assert want in ins().tidy(raw)


# ================================ 6. what the sheet holds and Spanish =============================================
def test_a_channels_sheets_saved_things_are_on_its_top_channels_themes(wr):
    Hm, F, _L, _T = mods()
    q = Hm.read(QS["q2"], TODAY)
    s = F.build(wr["bot"], person(wr), q, wr["clock"][0], text=QS["q2"])
    ch_themes = {c.get("theme") for c in s["channels"][:3]}
    assert all(x["theme"] in ch_themes for x in s["library"]["saved_not_opened"])


@pytest.mark.parametrize("text, window", [("¿cómo ha cambiado lo que veo desde 2020?", "since"),
                                          ("¿cómo han cambiado mis gustos este año?", "year")])
def test_spanish_how_what_i_watch_changed_is_read_as_changed(text, window):
    from mvp import history as Hm
    q = Hm.read(text, date(2026, 11, 22))
    assert q.kind == "changed" and q.lang == "es" and q.window.kind == window


@pytest.mark.parametrize("text", ["como ha cambiado el precio", "¿qué ha cambiado en mi plan?",
                                  "lo que veo es muy bueno"])
def test_spanish_change_words_alone_are_no_history_question(text):
    from mvp import history as Hm
    q = Hm.read(text, date(2026, 11, 22))
    assert q is None or q.kind != "changed"


def test_the_code_form_reads_every_kind_of_the_brief_on_the_made_up_library(wr):
    I = ins()
    Hm, F, _L, _T = mods()
    for key, text in QS.items():
        q = Hm.read(text, TODAY)
        s = F.build(wr["bot"], person(wr), q, wr["clock"][0], text=text)
        s["lang"] = q.lang
        cf = I.check(I.code_form(s), s, chart_vals=I.chart(s)[1])
        assert cf["answer"], (key, cf["dropped"])
        assert not re.search(r"\b20\d\d: \d", cf["answer"])


# ================================ 7. after the live reading: the answer names what was asked =====================
def test_a_channels_answer_that_names_no_channel_and_count_is_written_by_code():
    c = case("channels_2025")
    raw = dict(c["fake"], answer="In 2025 you opened 9,654 videos, led by speedrun clips at 20%.")
    f = checked(raw, c["sheet"])
    # round 12, pass 3 fix (judge A, row 2, on purpose): the lead in words, the chart carries the counts
    assert f["answer"].startswith("Lantern Speedruns led, ahead of Prime Number Club and")
    raw = dict(c["fake"], answer="In 2025 Lantern Speedruns and Prime Number Club were your top channels.")
    assert ins().check(raw, c["sheet"])["dropped"][0][:2] == ("answer", "shape")


def test_an_answer_that_is_a_run_of_names_is_written_by_code():
    c = case("day_oct30")
    s = c["sheet"]
    s["themes"] += [{"name": n, "share": 0.02} for n in ("cozy gaming", "chess openings", "film essays",
                                                          "math explainers")]
    raw = dict(c["fake"], answer="On Friday 30 October 2026 you opened 31 videos: speedrun clips, Blender 3D, home "
                                 "cooking, cozy gaming, chess openings, film essays and math explainers.")
    f = checked(raw, s)
    assert ("answer", "name_run") in [(d[0], d[1]) for d in f["dropped"]] and "answer" in f["filled"]
    # round 12, pass 2 (T10): the day's own words (no usual day in this made-up sheet)
    assert f["answer"].startswith("31 videos, 18 of them Shorts; speedrun clips (45%) led, then Blender 3D (26%)")


def test_a_saved_bullet_about_another_theme_goes_and_its_so_what_too():
    c = case("top_lately")
    c["sheet"]["library"]["saved_not_opened"].append({"theme": "guitar practice", "n": 4, "examples": ["s9"]})
    raw = dict(c["fake"], observations=list(c["fake"]["observations"][:2]) + [
        {"text": "Guitar practice had 4 saved videos you never opened.", "uses": ["library"]}],
        so_what="You saved 4 guitar practice videos you never opened; want them as a list?")
    f = checked(raw, c["sheet"])
    assert not any("guitar" in o.lower() for o in f["observations"])
    assert "guitar" not in (f["so_what"] or "").lower()


@pytest.mark.parametrize("text", ["Gaming had 640 and art 212, so the lead there is only 428.",
                                  "You opened 640 gaming videos, a lead of 428 over art."])
def test_a_lead_said_as_a_bare_difference_is_filler(text):
    s = case("cmp_gaming_art")["sheet"]
    assert ins().check_sentence(text, facts_of(s)) == "filler"


def test_busiest_hours_are_no_length_so_the_length_is_still_said():
    c = case("top_lately")
    raw = dict(c["fake"], observations=[
        {"text": "Blender 3D grew to 31% of what you opened, up 12 points on the 4 weeks before.", "uses": ["themes"]},
        {"text": "Your busiest hours are after 9pm.", "uses": ["when"]}])
    f = checked(raw, c["sheet"])
    # round 12, pass 2 (T2): no total of video length; Shorts against long videos instead
    assert not any("add up" in o or "adds up" in o for o in f["observations"]) and len(f["observations"]) >= 3


def test_an_unfinished_observation_and_a_run_of_years_are_dropped():
    c = case("changed_since_2020")
    s = c["sheet"]
    I = ins()
    raw = dict(c["fake"], observations=list(c["fake"]["observations"]) + [
        {"text": "Blender 3D and film essays add up to 4,?", "uses": ["periods"]},
        {"text": "Blender 3D was there in 2020, 2021, 2022, 2023, 2024 and 2026.", "uses": ["periods"]}])
    f = I.check(raw, s)
    whys = {(d[2] or "")[:20]: d[1] for d in f["dropped"] if d[0] == "observation"}
    assert whys["Blender 3D and film "] == "unfinished" and whys["Blender 3D was there"] == "number_run"


def test_a_so_what_that_adds_a_theme_the_answer_never_named_is_the_codes_on_the_named_one():
    c = case("top_lately")
    c["sheet"]["library"]["saved_not_opened"].append({"theme": "guitar practice", "n": 4, "examples": ["s9"]})
    raw = dict(c["fake"], so_what="You saved 7 Blender 3D videos and 4 guitar practice videos you never opened; want "
                                  "them as a list?")
    f = checked(raw, c["sheet"])
    assert f["so_what"] == "You saved 7 Blender 3D videos you never opened. Want them as a list?"
