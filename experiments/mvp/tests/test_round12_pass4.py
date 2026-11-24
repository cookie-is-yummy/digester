"""Round 12, fourth pass (DESIGN.md section 19.P4): what the fourth reading of the live history answers still found
(V1 to V6), each reproduced on made-up data (every test here fails on dfdd68c), fixed, and guarded with near variants.

Made-up data only: the sheets shaped like the real ones of tests/test_round12_pass2_fix.py (TOP, DAY), the made-up
summer of tests/test_round12_pass3_fix.py, small sheets built here, and the made-up library (tests/r12_library.py).
"""
import copy

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, mods, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_pass2 import sheet_of
from mvp.tests.test_round12_pass2_fix import DAY, top
from mvp.tests.test_round12_pass3_fix import _summer


def ins():
    from mvp import insight
    return insight


def math_channels():
    """A channels answer filtered to a topic (live: "most watched channels in math"): 440 Shorts, 22% of its videos."""
    s = top(kind="channels", question="most watched channels in number puzzles",
            filters={"topic": "number puzzles", "without_shorts": False})
    s["totals"] = {"items": 1959, "days_active": 600, "shorts": 440, "long": 1516, "shorts_share": 0.225,
                   "long_median_min": 13}
    s["channels"] = [{"name": "Prime Number Club", "items": 110, "days": 84, "shorts_share": 0.04},
                     {"name": "Proof Lab", "items": 104, "days": 80, "shorts_share": 0.01},
                     {"name": "Chalk Theorem", "items": 98, "days": 70, "shorts_share": 0.02},
                     {"name": "Ruler Hacks", "items": 28, "days": 20, "shorts_share": 0.9}]
    return s


# ================================ V1: a filtered sheet's shares and counts with ITS base ========================
def test_v1_a_topic_channels_answers_shorts_share_is_of_the_topics_videos():
    I = ins()
    s = math_channels()
    assert I.scoped("The long videos were typically about 13 minutes, and 440 Shorts made up 22% of your YouTube "
                    "videos.", s) == ("The long videos were typically about 13 minutes, and 440 Shorts made up 22% of "
                                      "your number puzzles videos on YouTube.")
    # the writer's path, rendered by code ("of what you opened" said of a Shorts share becomes the YouTube videos),
    # ends with the topic's base as it is sent
    f = I.check({"answer": "-", "observations": [
        {"text": "{totals.shorts} Shorts made up {totals.shorts_share} of everything you opened.", "uses": []}]}, s,
        strict=True)
    assert I.scoped(f["observations"][0], s) == "440 Shorts made up 22% of your number puzzles videos on YouTube."


def test_v1_a_firsts_shorts_share_is_of_the_topics_videos_in_every_wording():
    I = ins()
    s = {"kind": "first", "lang": "en", "filters": {"topic": "blender"}}
    for t in ("31% of your YouTube videos watched was Shorts.", "31% of the YouTube videos were Shorts.",
              "Shorts were 31% of all your YouTube videos.", "Shorts were 31% of YouTube videos you opened."):
        out = I.scoped(t, s)
        assert "of your blender videos on YouTube" in out and "of your YouTube" not in out and \
            "of the YouTube" not in out, (t, out)


def test_v1_every_filter_says_its_own_base_and_an_unfiltered_sheet_is_as_it_was():
    I = ins()
    t = "Sketch edits made up 12% of what you opened, and Shorts were 70% of your YouTube videos."
    ch = top(filters={"channel": "Pixel Forge"})
    assert I.scoped(t, ch) == ("Sketch edits made up 12% of the videos you opened from Pixel Forge, and Shorts were 70% "
                               "of your videos from Pixel Forge.")
    ws = top(filters={"without_shorts": True})
    assert I.scoped("Sketch edits made up 12% of everything you opened.", ws) == \
        "Sketch edits made up 12% of your long videos."
    ar = top(filters={"topic": "gaming", "without_shorts": True})
    assert I.scoped("Speed runs made up 23% of what you watched.", ar) == "Speed runs made up 23% of your long gaming videos."
    assert I.scoped(t, top()) == t   # not filtered: the words as they were
    # a day filtered to a topic
    d = copy.deepcopy(DAY)
    d["filters"] = {"topic": "cats"}
    assert I.scoped("Shorts were 90% of the day's YouTube videos.", d) == \
        "Shorts were 90% of the day's cats videos on YouTube."


def test_v1_the_chart_caption_and_the_so_what_say_the_base_too():
    I = ins()
    s = top(kind="channels", filters={"topic": "number puzzles"})
    form = {"answer": "Pixel Forge led.", "observations": ["Pixel Forge came on 12 days.", "Doggo Plays came on 9."],
            "so_what": "Shorts went up to 74% of your YouTube videos, from 68%.", "offers": []}
    text = I.layout(form, s)[0]["text"]
    assert "Number puzzles videos opened, by channel:" in text, text
    assert "74% of your number puzzles videos on YouTube" in text and "of your YouTube videos" not in text
    t2 = top(filters={"topic": "gaming"})
    form2 = dict(form, answer="Speed runs led.", so_what=None)
    assert "Share of your gaming videos, by area:" in I.layout(form2, t2)[0]["text"] or \
        "Share of your gaming videos, by theme:" in I.layout(form2, t2)[0]["text"]


# ================================ V2: asked what he was INTO, the lead says what he was into =====================
def into_summer():
    s = _summer()
    s["distinct"] = {"rest_words": "the rest of 2023", "themes": [
        {"name": "Sketch edits", "share": 0.056, "rest_share": 0.035}]}   # under twice its share: nothing to say
    s["into"] = {"peaked": [{"name": "Meme drops", "area": "internet culture", "share": 0.065, "items": 65,
                             "peak_share": 0.065, "next_share": 0.05, "spans": 25}], "new": []}
    return s


def test_v2_the_into_lead_names_the_areas_and_what_peaked_then_and_the_shorts_move_is_a_bullet():
    I = ins()
    s = into_summer()
    cf = I.code_form(s)
    assert cf["answer"] == ("you were into comedy (14% of what you opened) and gaming (10%); your Meme drops watching "
                            "peaked then, at 6%, more than in any other three months."), cf["answer"]
    texts = [o["text"] for o in cf["observations"]]
    # round 12, pass 6 (X17, on purpose): the move to Shorts is one bullet with its own base and nothing hung off it;
    # what ran above its share of the rest of the year is said with both shares
    assert "You moved to Shorts: 82% of your YouTube videos, from 29% in the spring before." in texts, texts
    assert not any("while gaming fell" in t for t in texts), texts
    assert any("set the summer apart" in t for t in texts), texts
    raw = {"answer": "{areas[0].name} led with {areas[0].share}.",
           "observations": [{"text": "Your long videos were typically about {totals.long_median_min} minutes, and "
                                     "{when.busiest_hours[0].hour} was your busiest hour.", "uses": []},
                            {"text": "{themes[1].name} came on {themes[1].days} days.", "uses": []},
                            {"text": "{areas[2].name} was {areas[2].share}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["answer"].startswith("You were into comedy (14% of what you opened)"), f["answer"]
    assert not any("busiest hour" in o or "typically about" in o for o in f["observations"]), f["observations"]
    assert not (f["so_what"] or "").startswith("Shorts")   # the move to Shorts is said once, as a bullet


def test_v2_a_year_that_one_area_led_by_far_and_the_window_with_nothing_that_peaked():
    I = ins()
    s = top(question="what was i watching back in 2021")
    s["window"] = {"words": "2021", "start": "2021-01-01", "end": "2021-12-31", "clipped": False}
    s["areas"][0] = dict(s["areas"][0], share=0.46)
    s["into"] = {"peaked": [{"name": "Speed runs", "share": 0.05, "items": 50}], "new": []}
    assert I._into_lead(I._rows_named(s["areas"], ("name", "share")), s["into"], s) == (
        "you were into gaming by far the most: 46% of what you opened, well ahead of comedy (11%); your Speed runs "
        "watching peaked then, at 5%, more than in any other year.")
    s["into"] = {"peaked": [], "new": []}
    assert I._into_lead(I._rows_named(s["areas"], ("name", "share")), s["into"], s).endswith("well ahead of comedy (11%).")


def test_v2_the_sheet_reads_into_questions_and_not_the_most(r12):
    F = mods()[1]
    for t in ("what was i into in the summer of 2023", "what was i watching back in 2021",
              "what have i been into the last 3 months", "what have i been into lately"):
        assert F.into_question(t), t
    for t in ("what have i been watching the most lately", "what did i watch the most in 2021",
              "which channels did i watch the most in 2025"):
        assert not F.into_question(t), t
    s = sheet_of(r12, "what have i been into the last 3 months")
    assert isinstance(s.get("into"), dict) and set(s["into"]) == {"peaked", "new"}, s.get("into")
    assert "into" not in ins().shown(s)   # code's lead says them; the writer is not shown them
    assert "into" not in sheet_of(r12, "what have i been watching the most lately")


def test_v2_a_peak_is_higher_than_every_other_span_of_its_length():
    import numpy as np
    from types import SimpleNamespace as NS
    F = mods()[1]
    # 4 calendar months (round 12, pass 5: the spans are whole months, sliding by one); theme 1 is 30% of the last
    # month, 10% of the others; theme 2 is flat
    from datetime import date
    starts = [date(2025, m, 1).toordinal() for m in (1, 2, 3, 4)]
    day, it, theme = [], [], []
    k = 0
    for span in range(4):
        for j in range(120):
            day.append(starts[span] + j % 28)
            it.append(k)
            theme.append(1 if (span == 3 and j < 36) or (span < 3 and j < 12) else 2)
            k += 1
    idx = NS(day=np.array(day), it=np.array(it))
    facts = NS(theme=np.array(theme))
    rows = [{"name": "Peak theme", "theme_id": 1, "share": 0.3, "items": 36},
            {"name": "Flat theme", "theme_id": 2, "share": 0.7, "items": 84}]
    out = F._peaks_new(idx, facts, None, np.ones(len(day), bool), starts[3], date(2025, 4, 30).toordinal(), rows)
    assert [p["name"] for p in out["peaked"]] == ["Peak theme"] and out["peaked"][0]["next_share"] == 0.1, out


# ================================ V3: one fact once, also in other words =========================================
def test_v3_a_count_of_shorts_under_codes_shorts_line_goes_whatever_its_order():
    I = ins()
    s = copy.deepcopy(DAY)
    facts = I.Facts(I.shown(s))
    must = "Shorts were 90% of the day's YouTube videos, against about 78% on a usual day of the months before."
    form = {"answer": "10 videos; Meme drops led with 3 of them.", "so_what": None, "dropped": [],
            "observations": ["9 of the 10 were Shorts.", "Pixel Forge gave 4 of them.", must], "_must": [must]}
    out = I._pass4(form, s, facts)
    assert out["observations"] == ["Pixel Forge gave 4 of them.", must], out["observations"]


def test_v3_a_bullet_naming_the_leads_two_themes_again_with_their_shares_goes_and_a_move_stays():
    I = ins()
    s = top()
    facts = I.Facts(I.shown(s))
    form = {"answer": "Mostly Meme drops and Speed runs lately.", "so_what": None, "dropped": [],
            "observations": ["Meme drops (7%) and Speed runs (5%) were your biggest themes.",
                             "Speed runs grew from 1% to 5% against the 4 weeks before.",
                             "Pixel Forge came on 12 days."]}
    out = I._pass4(form, s, facts)
    assert out["observations"] == ["Speed runs grew from 1% to 5% against the 4 weeks before.",
                                   "Pixel Forge came on 12 days."], out["observations"]
    # a move the answer does not say is no repeat of its two numbers (live, row 8: "comedy grew from 9% to 14%")
    assert I._obs_more("Comedy grew from 9% to 14% against the spring before.", "You were into comedy (14%) and "
                       "gaming (10%).", s, None, facts) != "repeat"


# ================================ V4: a so-what is a step code can take ==========================================
def test_v4_a_notice_with_no_step_is_a_bullet_and_a_fall_gets_its_follow_up():
    I = ins()
    s = top()
    facts = I.Facts(I.shown(s))
    form = {"answer": "Gaming led with 22%.", "dropped": [], "observations": ["Pixel Forge came on 12 days.",
                                                                              "Doggo Plays came on 9 days."],
            "so_what": "Shorts went up to 74% of your YouTube videos, from 68% in the 4 weeks before.",
            "so_what_id": "shorts_shift:up", "so_what_kind": "shorts_shift"}
    out = I._pass4(copy.deepcopy(form), s, facts)
    assert out["so_what"] is None and out["so_what_id"] is None
    assert out["observations"][-1].startswith("Shorts went up to 74%")
    f2 = dict(copy.deepcopy(form), so_what="The learning side gave way: sports fell from 16% to 9%.",
              so_what_kind="learning_faded", so_what_faded="sports")
    assert I._pass4(f2, s, facts)["so_what"].endswith('Say "only sports" to see what you still open of it.')
    s3 = top(library={"saved_not_opened": [{"theme": "Speed runs", "n": 5, "examples": ["x"]}]})
    f3 = dict(copy.deepcopy(form), so_what="You saved 5 Speed runs videos to revisit.", so_what_kind="path")
    assert I._pass4(f3, s3, I.Facts(I.shown(s3)))["so_what"].endswith("to revisit. Want them as a list?")


# ================================ V5: offers that fit ============================================================
def test_v5_no_only_theme_of_a_handful_and_no_offer_that_repeats_a_first():
    I = ins()
    d = copy.deepcopy(DAY)
    d["offers"] = ["without_shorts", "only_topic:Meme drops"]
    d["themes"] = [{"name": "Meme drops", "items": 3, "share": 0.3}]
    assert I.offers_fit(d, None, "10 videos; Meme drops led with 3 of them.") == ["without_shorts"]
    d["themes"] = [{"name": "Meme drops", "items": 12, "share": 0.3}]
    assert I.offers_fit(d, None, "Meme drops led with 12 of them.") == ["without_shorts", "only_topic:Meme drops"]
    f = {"kind": "first", "lang": "en", "offers": ["by_month", "show_videos", "without_shorts"]}
    assert I.offers_fit(f, None, "You first opened a blender video on 14 March 2019.") == ["without_shorts"]


# ================================ V6: small wording ==============================================================
def test_v6_a_word_of_the_next_place_is_said_of_the_record_right_after():
    I = ins()
    s = math_channels()
    facts = I.Facts(I.shown(s))
    bad = I.render("{channels[0].name} came on {channels[0].days} days, while {channels[2].name} was close behind at "
                   "{channels[2].items}.", s, facts, strict=True)
    assert bad == (None, "rank"), bad
    ok = I.render("{channels[0].name} came on {channels[0].days} days, while {channels[1].name} was close behind at "
                  "{channels[1].items}.", s, facts, strict=True)
    assert ok[1] is None and ok[0].endswith("Proof Lab was close behind at 104."), ok
    assert I.render("{channels[2].name} came next with {channels[2].items}.", s, facts, strict=True)[1] == "rank"
    assert I.render("{channels[1].name} came next with {channels[1].items}.", s, facts, strict=True)[1] is None


def test_v6_a_theme_led_by_its_channels_says_its_share_with_grammar_for_plural_names():
    I = ins()
    s = top()
    facts = I.Facts(I.shown(s))
    form = {"answer": "Gaming led with 22%.", "so_what": None, "dropped": [],
            "observations": ["Sketch edits was driven by Laugh Lab and Pixel Forge, with 97% of those videos as Shorts.",
                             "Meme drops was led by Meme Vault; 69% of it was Shorts.", "Doggo Plays came on 9 days."]}
    out = I._pass4(form, s, facts)["observations"]
    assert out[0] == ("Behind Sketch edits (4% of what you opened): Laugh Lab and Pixel Forge, with 97% of those "
                      "videos as Shorts."), out
    assert out[1] == "Behind Meme drops (6% of what you opened): Meme Vault; 69% of it was Shorts.", out


def test_v6_a_count_code_counted_says_what_it_counts():
    I = ins()
    s = {"kind": "count", "lang": "en", "filters": {"topic": "minecraft"},
         "topics": [{"name": "minecraft", "items": 1094, "matched_by": "themes and words"}]}
    assert I.scoped("This year you opened about 1,094 minecraft videos, mostly memes.", s, answer=True) == \
        "This year you opened 1,094 videos whose title or theme is about minecraft, mostly memes."
    assert I.scoped("You opened 1,094 videos.", s, answer=True) == \
        "You opened 1,094 videos whose title or theme is about minecraft."


# ================================ the live reading of this pass (made-up stand-ins) =============================
def test_live_one_fall_said_twice_in_two_bullets_and_a_bullet_the_so_what_says_go():
    I = ins()
    s = _summer()
    facts = I.Facts(I.shown(s))
    must = "You moved to Shorts: 82% of your YouTube videos, from 29% in the spring before, while gaming fell from 33% to 10%."
    form = {"answer": "You were into comedy (14% of what you opened) and gaming (10%).", "so_what": None, "dropped": [],
            "observations": ["Against the spring before, comedy rose by 6 points while gaming fell by 23 points.",
                             "Inside comedy: Sketch edits (4% of everything you opened).", must], "_must": [must]}
    assert I._pass4(form, s, facts)["observations"] == ["Inside comedy: Sketch edits (4% of everything you opened).",
                                                        must]
    t = top()
    form2 = {"answer": "You were into gaming (22% of what you opened) and comedy (11%).", "dropped": [],
             "so_what": "Worth noticing: gaming grew from 12% to 22% against the 4 weeks before, while sports fell from 16% "
                        "to 9%.", "so_what_kind": "moving", "so_what_faded": "sports",
             "observations": ["Gaming grew from 12% to 22% against the 4 weeks before.", "Pixel Forge came on 12 days.",
                              "Doggo Plays came on 9 days."]}
    out = I._pass4(form2, t, I.Facts(I.shown(t)))
    assert out["observations"] == ["Pixel Forge came on 12 days.", "Doggo Plays came on 9 days."], out["observations"]
    assert out["so_what"].endswith('Say "only sports" to see what you still open of it.')


def test_live_a_themes_share_the_answer_says_is_not_added_to_its_channels_bullet():
    I = ins()
    s = top()
    form = {"answer": "You were into gaming by far the most; Meme drops peaked then, at 6%.", "so_what": None,
            "dropped": [], "observations": ["Meme drops was led by Meme Vault.", "Pixel Forge came on 12 days."]}
    assert I._pass4(form, s, I.Facts(I.shown(s)))["observations"][0] == "Behind Meme drops: Meme Vault."
    # live, 2021: "<A> and <B> peaked then, at 11% and 5%" (the share not right after its name)
    form = dict(form, dropped=[], answer="You were into gaming; Meme drops and Speed runs peaked then, at 6% and 5%.",
                observations=["Meme drops was led by Meme Vault.", "Pixel Forge came on 12 days."])
    assert I._pass4(form, s, I.Facts(I.shown(s)))["observations"][0] == "Behind Meme drops: Meme Vault."
