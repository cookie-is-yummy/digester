"""Round 12, sixth pass (DESIGN.md section 19.P6): what a hand check of 18 live answers found that the automatic audit
passed, fixed by construction: code words the part of a sentence that can be false (the subject of a count from the
filters in force, the base of a share, both values of a change, the order of items), whoever wrote the sentence.

Each test is one item of the hand check (X1 to X18). Every test here fails on c073c24 (the build the check read).
Made-up data only: the made-up library (tests/r12_library.py), the made-up sheets of tests/test_round12_pass2_fix.py
and small sheets built here.
"""
import copy
import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, mods, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_merge import wr, ask  # noqa: F401  (fixtures)
from mvp.tests.test_round12_pass2 import sheet_of
from mvp.tests.test_round12_pass2_fix import top, obs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ins():
    from mvp import insight
    return insight


def gate(text, s, said=False):
    I = ins()
    return I.gate_sentence(text, s, I._gate_names(I.shown(s)), {"opened_said": said})


def _ts(iso):
    return int(datetime.fromisoformat(iso).timestamp())


# ================================ X1: a first or a last by the instant of its open ===============================
def test_x1_a_last_is_ordered_by_the_instant_of_the_open_not_by_the_id():
    """The hand check: "the last minecraft video" named the one opened at 00:04, not the one at 09:12 that day."""
    from mvp import facts as F
    idx = SimpleNamespace(pos={"v1": 0, "v2": 1}, it=np.array([0, 1]), day=np.array([1, 1]),
                          sec=np.array([_ts("2026-10-30T13:12:00+00:00"), _ts("2026-10-30T04:04:00+00:00")]),
                          zone=ZoneInfo("America/New_York"))
    items = [{"id": "v2", "at": "2026-10-30", "channel": "Early Pixel"},
             {"id": "v1", "at": "2026-10-30", "channel": "Late Brick"}]
    F._by_instant(items, idx, np.array([True, True]), None, "last")
    assert [it["id"] for it in items] == ["v1", "v2"]
    assert items[0]["at_time"] == "9:12 am" and items[1]["at_time"] == "12:04 am"


def test_x1_a_lasts_answer_is_codes_item_with_its_day_time_and_channel():
    """The hand check: "You last watched 30 October 2026, and it was <theme> from <channel>" (watched what?)."""
    I = ins()
    s = top(kind="last", filters={"topic": "minecraft", "without_shorts": False})
    s["window"] = {"words": "", "start": "2019-01-01", "end": "2026-10-30", "clipped": False}
    s["items"] = [{"id": "v1", "title": "A made-up build", "channel": "Late Brick", "at": "2026-10-30",
                   "at_time": "9:12 am", "theme": "Speed runs", "is_short": True},
                  {"id": "v2", "title": "Another made-up build", "channel": "Early Pixel", "at": "2026-10-30",
                   "at_time": "12:04 am", "theme": "Block battles", "is_short": True}]
    s["topics"] = [{"name": "minecraft", "items": 80}]
    raw = {"answer": "You last watched {items[0].at}, and it was {items[0].theme} from {items[0].channel}.",
           "observations": [{"text": "You last watched {items[0].at}, and it was {items[0].theme}.", "uses": []}]}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    assert f["answer"].startswith("The last minecraft video you opened was from Late Brick, on 30 October 2026 at "
                                  "9:12 am."), f["answer"]
    assert not any(re.search(r"\blast watched\b", o) for o in f["observations"]), f["observations"]


def test_x1_the_sheets_first_is_the_first_open_in_time(r12):
    s = sheet_of(r12, "when did i first start watching watercolor videos")
    ts = [it.get("at_time") for it in s["items"]]
    assert ts and all(isinstance(t, str) and re.fullmatch(r"\d{1,2}:\d\d [ap]m", t) for t in ts[:3]), ts


# ================================ X2: a share inside an area says its base in its own sentence ====================
def test_x2_an_inside_share_says_its_base_even_when_the_answer_said_it():
    """The hand check: "Inside gaming, <theme> led with 3%." read as 3% of gaming (it was of everything opened)."""
    out, why = gate("Inside gaming, Speed runs led with 5%.", top(), said=True)
    assert why is None and out == "Inside gaming, Speed runs led with 5% of what you opened.", out
    out, _ = gate("Gaming grew to 22%, with Speed runs at 5% and Block battles at 5%.", top(), said=True)
    assert "of what you opened" in out, out   # an area and its theme in one sentence: its base in that sentence
    I = ins()
    t = top()
    t["areas"][0] = dict(t["areas"][0], themes=[{"name": "Speed runs", "share": 0.05}])
    cf = I.code_form(t)
    one = [o["text"] for o in cf["observations"] if o["text"].startswith("Inside gaming,")]
    assert one and one[0].endswith("led with 5% of what you opened."), one


# ================================ X3: a Shorts share named by "share" before its number ===========================
def test_x3_a_shorts_share_in_lower_case_gets_its_capital_and_its_base():
    """The hand check: "Your shorts share dropped from 64% in 2023 to 33%" (no base; "shorts")."""
    out, why = gate("Your shorts share dropped from 68% in 2023 to 74%.", top(), said=True)
    assert why is None and out == "Your Shorts share dropped from 68% of your YouTube videos in 2023 to 74%.", out


# ================================ X4: a count under filters says every filter in force =============================
def test_x4_a_count_of_the_scope_names_every_filter_in_force():
    """The hand check: after "without shorts" and "only music": "You opened 431 long videos" (431 long MUSIC videos)."""
    s = top(filters={"topic": "music", "without_shorts": True})
    s["totals"] = dict(s["totals"], items=431, long=431, shorts=0)
    out, _ = gate("You opened 431 long videos, and noon was your busiest hour.", s)
    assert out.startswith("You opened 431 long music videos,"), out
    s2 = top(filters={"topic": "music", "without_shorts": False})
    s2["totals"] = dict(s2["totals"], items=500, shorts=320)
    out2, _ = gate("Of the 500 videos you opened, 320 were Shorts.", s2)
    assert "500 music videos" in out2 and "320 were Shorts" in out2, out2
    out3, _ = gate("You opened 500 videos whose title or theme is about music.", s2)
    assert out3 == "You opened 500 videos whose title or theme is about music.", out3   # the clause says it


# ================================ X5: a change is two values of one measure ======================================
def _moving():
    s = top()
    s["themes"][1].update(share=0.09, previous_share=0.03, previous_items=27, change_vs_previous=0.06)
    s["themes"][3].update(share=0.02, previous_share=0.07, previous_items=63, change_vs_previous=-0.05)
    return s


def test_x5_a_share_against_a_count_is_said_in_shares():
    """The hand check: "A theme climbed to 6% from 126 videos before"; "Another faded from 210" (no end value)."""
    kept, why = obs("{themes[1].name} climbed to {themes[1].share} from {themes[1].previous_items} videos before.",
                    _moving())
    assert kept and "videos" not in kept and re.search(r"climbed to 9% from 3%", kept), (kept, why)
    kept, why = obs("{themes[3].name} faded from {themes[3].previous_items}.", _moving())
    assert kept and re.search(r"faded from 7% to 2%", kept), (kept, why)


def test_x5_a_shorts_move_with_one_value_gets_the_other():
    kept, why = obs("Shorts rose from {previous.shorts_share}.")
    assert kept and kept.startswith("Shorts rose from 68% to 74%"), (kept, why)


# ================================ X6: without Shorts is the videos known to be long ==============================
def test_x6_without_shorts_counts_only_the_videos_known_to_be_long(r12):
    """The hand check: "22% of your long videos" was of every non-Short (8% of no known length): 24% of the long ones."""
    s = sheet_of(r12, "what did i watch the most in 2023 without shorts")
    t = s["totals"]
    assert t["items"] == t["long"], t   # 2 calculus videos of no known length are no longer counted as long ones
    assert s["filters"]["left_out"]["unknown_length"] == 2, s["filters"]["left_out"]


# ================================ X7: a day's Shorts share against a usual day on the same base ===================
def test_x7_the_usual_days_shorts_share_is_on_the_days_base(r12):
    """The hand check: 90% "of the day's YouTube videos" against a usual 78% of the known-length ones (77% same base)."""
    I = ins()
    s = sheet_of(r12, "what did i watch on october 30")
    us = s["usual"]
    assert "shorts_yt_share" in us and "day_shorts_yt_share" in us, us
    assert I.shown(s)["usual"]["shorts_share"] == us["shorts_yt_share"]


# ================================ X8: a count of saved videos says what it counts =================================
def test_x8_saved_and_never_opened_is_said_so():
    """The hand check: "You saved 5 <theme> videos" where 5 were the saved ones never opened (49 saved)."""
    s = top()
    s["library"] = {"saved_not_opened": [{"theme": "Speed runs", "n": 5}]}
    out, _ = gate("You saved 5 Speed runs videos; want to open them next?", s)
    assert out == "You saved and never opened 5 Speed runs videos; want to open them next?", out
    out, _ = gate("You saved 6 Block battles tutorials; want them?", dict(s, library={"saved_not_opened": [
        {"theme": "Block battles tutorials", "n": 6}]}))
    assert out.startswith("You saved and never opened 6 Block battles tutorials"), out


# ================================ X9: one fact once, in whatever words ===========================================
def test_x9_a_move_said_as_points_and_as_two_values_is_one_fact():
    I = ins()
    s = top()
    f = {"answer": "Mostly gaming.", "dropped": [], "observations": [
        "Compared with the weeks before, Speed runs rose by 4 points.",
        "Speed runs grew to 5%, from 1% in the 4 weeks before."]}
    out = I.p6_once(f, s)["observations"]
    assert out == ["Speed runs grew to 5%, from 1% in the 4 weeks before."], out


def test_x9_a_count_of_new_channels_and_a_named_new_channel_are_one_fact():
    I = ins()
    s = dict(top(), new_today={"channels": 2, "names": ["Doggo Plays"]})
    f = {"answer": "10 videos.", "dropped": [], "observations": [
        "Pixel Forge and Doggo Plays each gave one, while 2 channels were new that day.",
        "Doggo Plays was new that day, one of 2 channels you opened for the first time."]}
    out = I.p6_once(f, s)["observations"]
    assert out == ["Pixel Forge and Doggo Plays each gave one.",
                   "Doggo Plays was new that day, one of 2 channels you opened for the first time."], out


# ================================ X10: no chart that says nothing ================================================
def test_x10_a_chart_whose_first_row_is_nine_tenths_or_whose_rows_round_to_zero_is_not_drawn():
    """The hand check: "Share of your long music videos, by area: 98% music, 0% gaming, 0% travel, ..."."""
    I = ins()
    s = top(filters={"topic": "music", "without_shorts": True})
    s["areas"] = [{"name": "music", "items": 425, "share": 0.977}] + [
        {"name": n, "items": 1, "share": 0.0023} for n in ("gaming", "travel", "comedy")]
    s["themes"] = [dict(s["themes"][0], name="Choir songs", area="music", items=215, share=0.5),
                   dict(s["themes"][1], name="Rap jokes", area="music", items=206, share=0.48)]
    ch, _ = I.chart(s, "areas")
    assert ch and "by theme" in ch.split("\n")[0] and " 0% " not in ch and "98%" not in ch, ch


# ================================ X11: a window after the export is answered over its latest stretch ==============
def test_x11_a_window_after_the_export_gets_the_insight_answer_with_one_clause(wr):
    """The hand check: "the last 10 days" asked after the export got a paragraph on what cannot be seen."""
    out, _ = ask(wr, "what did i watch the most in the last 10 days")
    assert out.startswith("In the last 10 days of your export (21 to 30 October 2026; nothing after 30 October 2026 "
                          "is in it)"), out
    assert "I can't see" not in out and "can not see" not in out, out


# ================================ X12: a rare word maps to no theme it is not about ===============================
def test_x12_a_rare_word_is_mapped_to_a_theme_only_when_its_titles_say_it():
    """The hand check: "origami" (6 videos by their words) was mapped to two unrelated themes (3,111 items)."""
    from mvp import themes as T
    items = {f"i{k}": SimpleNamespace(caption=("Fold a paper crane, origami" if k < 4 else f"Made-up song {k}"))
             for k in range(300)}
    view = SimpleNamespace(items=items, lib="made-up")
    rec = SimpleNamespace(events={i: [] for i in items})
    th = SimpleNamespace(themes={1: {"name": "Choir songs", "category": "music", "field": 0,
                                     "words": ["choir", "songs", "origami"]}},
                         fields={0: {"category": "music"}}, theme_id=lambda i: 1, shown=lambda t: "Choir songs")
    assert T.for_topic(view, rec, "origami", th) == []


def test_x12_a_handful_by_words_alone_is_codes_reply_with_no_writer_call(wr, monkeypatch):
    from mvp import facts, history as Hm
    base = facts.build

    def few(bot, person, q, now, text=None):
        s = base(bot, person, q, now, text=text)
        if isinstance(s, dict):
            s["filters"] = dict(s.get("filters") or {}, topic="origami", topic_themes=[])
            s["totals"] = dict(s.get("totals") or {}, items=6)
        return s
    monkeypatch.setattr(facts, "build", few)
    bot = wr["bot"]
    person = dict(bot.store.q("SELECT * FROM people")[0])
    q = Hm.read("how many origami videos have i watched", TODAY)
    parts, info, _sheet = Hm._write_now(bot, person, q, wr["clock"][0], False, "how many origami videos", [])
    assert parts is None and info.get("skipped") == "handful" and not info.get("called"), info


# ================================ X13: a chart rounds once, and a balance is its ratio ============================
def test_x13_a_chart_row_rounds_from_its_count_and_a_gap_is_never_said():
    """The hand check: 113 of 1,514 (7.46%) stored as 0.075 and drawn 8%; "the gap has narrowed" by the ratio."""
    I = ins()
    s = top()
    s["totals"] = dict(s["totals"], items=1514)
    s["areas"] = [dict(s["areas"][0], items=242, share=0.16), dict(s["areas"][1], items=113, share=0.075)]
    ch, _ = I.chart(s, "areas")
    assert "7% comedy" in ch and "8% comedy" not in ch, ch
    out, why = gate("The gap has narrowed since 2025.", top())
    assert out is None and why == "gap_words"
    from mvp import facts as F
    assert F._share(113, 1514) == 0.0746


# ================================ X14: a move under 3 points is not said ==========================================
def test_x14_a_move_under_three_points_is_filler_and_dropped():
    """Row 2: "gaming slipped by 1 point, while film and TV fell by 2 points"."""
    s = top()
    s["areas"][1] = dict(s["areas"][1], change_vs_previous=-0.02)
    kept, why = obs("{areas[1].name} slipped by {areas[1].change_vs_previous}.", s)
    assert kept is None and why == ["small_move"], (kept, why)
    s["themes"][1].update(share=0.05, previous_share=0.04)
    kept, why = obs("{themes[1].name} rose from {themes[1].previous_share} to {themes[1].share}.", s)
    assert kept is None and why == ["small_move"], (kept, why)


# ================================ X15: a first's so-what is its arc and the step to take =========================
def test_x15_a_firsts_so_what_is_the_arc_then_the_saved_videos_as_a_step():
    """Row 4: "suggest what I could learn with that information. Cuz 'so what?', you know?"."""
    I = ins()
    c = {"kind": "path", "how": "faded", "last_label": "2026", "last_items": 12, "peak_label": "2023",
         "peak_items": 131}
    s = {"window": {"end": "2026-10-30"}, "filters": {"topic": "blender"},
         "so_what_candidates": [c, {"kind": "saved", "theme": "Render tutorials", "n": 6}]}
    line = I._path_line(s, "blender")
    assert line == ("Your blender watching peaked at 131 in 2023; in 2026 up to 30 October it was 12. You saved and "
                    "never opened 6 Render tutorials: want them as a list, to pick it up again?"), line


# ================================ X16: a list of more than 3 as compact rows, nothing named hidden ================
def test_x16_a_day_of_more_than_three_is_compact_rows_with_their_times():
    I = ins()
    s = top(kind="day")
    s["window"] = {"words": "Friday 30 October 2026", "start": "2026-10-30", "end": "2026-10-30"}
    s["items"] = [{"id": f"v{k}", "title": f"Made-up {k}", "channel": f"Chan {k}", "at": "2026-10-30",
                   "at_time": f"{k}:00 pm", "length_s": 30, "is_short": True} for k in range(1, 6)]
    cards = [{"type": "link", "url": f"https://www.youtube.com/watch?v=vid{k}x", "title": f"Made-up {k}",
              "platform": "youtube", "video_id": f"vid{k}x", "item": s["items"][k - 1]} for k in range(1, 6)]
    form = {"answer": "5 videos.", "observations": ["Mostly Shorts.", "Chan 1 came first."], "offers": [],
            "so_what": None, "dropped": []}
    parts = I.layout(form, s, cards)
    links = [p for p in parts if p.get("type") == "link"]
    assert len(links) == 5 and all(p.get("compact") for p in links)
    assert links[0]["caption"] == "1. Chan 1 · 1:00 pm · 30 s · Short", links[0]["caption"]
    page = open(os.path.join(HERE, "channels", "web_page.html"), encoding="utf-8").read()
    assert "card row1" in page and "l.compact" in page


def test_x16_every_channel_the_overview_names_has_its_card():
    I = ins()
    s = {"kind": "day", "items": [{"id": f"v{k}", "channel": f"Chan {k}"} for k in range(1, 14)]}
    I._named_first(s, "Chan 12 and Chan 2 led the day.")
    shown_ = [it["channel"] for it in s["items"][:I.SHOW["items"]]]
    assert "Chan 12" in shown_ and "Chan 2" in shown_ and len(s["items"]) == 13, shown_


def test_x16_the_usual_day_comes_first(r12):
    I = ins()
    s = sheet_of(r12, "what did i watch on october 30")
    form = {"answer": "4 videos.", "observations": ["The busiest hour was 10am.",
                                                    "Shorts were 25% of the day's YouTube videos, against none on "
                                                    "a usual day."], "offers": [], "so_what": None, "dropped": []}
    text = I.layout(form, s)[0]["text"]
    assert text.index("usual day") < text.index("busiest hour"), text


# ================================ X17: a past season against the year around it ==================================
def test_x17_a_seasons_shorts_move_is_its_own_bullet_and_what_was_new_is_said():
    """Row 8: compared only with the spring; "... while gaming fell from 33% to 10%" hung off the Shorts sentence."""
    from mvp.tests.test_round12_pass4 import into_summer
    I = ins()
    s = into_summer()
    s["new"] = {"themes": [], "channels": [{"name": "Kite Lab", "items": 40, "theme": "Speed runs", "since_items": 2},
                                           {"name": "Moss Den", "items": 30, "theme": "Meme drops",
                                            "since_items": 9}]}
    texts = [o["text"] for o in I.code_form(s)["observations"]]
    assert "You moved to Shorts: 82% of your YouTube videos, from 29% in the spring before." in texts, texts
    assert any(t.startswith("New that summer, by videos opened: Kite Lab (40) and Moss Den (30); since then you opened "
                            "2 more of the first and 9 more of the second") for t in texts), texts


def test_x17_what_he_did_then_and_not_since_is_a_so_what_with_a_step():
    from mvp import facts as F
    out = {"kind": "top", "themes": [], "new": {"channels": [{"name": "Kite Lab", "items": 40, "theme": "Speed runs",
                                                              "since_items": 2}]}}
    q = SimpleNamespace(window=SimpleNamespace(label="summer"), season="the summer of 2023")
    c = [x for x in F._so_what_candidates(out, "top", q) if x["kind"] == "then_not_since"]
    assert c and c[0]["channel"] == "Kite Lab" and c[0]["since"] == 2, c
    t = ins().so_what_text(c[0], {})
    assert t == ("Kite Lab was a thing of that time: you opened 40 of their videos then and 2 since. Say \"only Speed "
                 "runs\" to see all the Speed runs you opened then."), t


# ================================ X18: two base phrases at most, one for the answer's own base =====================
def test_x18_one_phrase_for_the_answers_own_base():
    I = ins()
    s = top()
    form = {"answer": "In the 4 weeks up to 30 October 2026, gaming led with 22% of what you opened.",
            "observations": ["Inside gaming: Speed runs (5% of everything you opened) and Block battles (5%).",
                             "Meme drops made up 7% of all you watched."], "offers": [], "so_what": None,
            "dropped": []}
    text = I.layout(copy.deepcopy(form), s)[0]["text"]
    assert "of everything" not in text and "of all you watched" not in text, text
    assert text.count("of what you opened") >= 2, text


# ================================ X19: a day's new channels counted over all the day's channels ===================
def test_x19_new_channels_of_a_day_are_counted_over_every_channel_of_the_day(r12, monkeypatch):
    """The auditor: a day of 26 channels said "2 channels were new that day" where 5 were (it counted the sheet's
    top list only). Here the top list is cut to the channels that are not new: the count still sees the new one."""
    from mvp import facts as F
    orig = F._channel_rows

    def cut(*a, **k):
        return [c for c in orig(*a, **k) if c["name"] != "Clip Factory"]
    monkeypatch.setattr(F, "_channel_rows", cut)
    s = sheet_of(r12, "what did i watch on october 1")
    assert all(c["name"] != "Clip Factory" for c in s["channels"]), s["channels"]
    assert s["new_today"] == {"channels": 1, "names": ["Clip Factory"]}, s["new_today"]


# ================================ X20: a first's items of one day in the order of their instants ==================
def test_x20_a_firsts_items_of_one_day_are_in_the_order_they_were_opened():
    """The auditor: a first answer's cards of 18 May were opened at 07:36, 10:23 and 07:28 (in that order on the
    page); the 07:28 one comes first."""
    from mvp import facts as F
    idx = SimpleNamespace(pos={"a": 0, "b": 1, "c": 2}, it=np.array([0, 1, 2, 1]), day=np.array([1, 1, 1, 2]),
                          sec=np.array([_ts("2020-05-18T11:36:00+00:00"), _ts("2020-05-18T14:23:00+00:00"),
                                        _ts("2020-05-18T11:28:00+00:00"), _ts("2020-05-19T11:00:00+00:00")]),
                          zone=ZoneInfo("America/New_York"))
    items = [{"id": "a", "at": "2020-05-18"}, {"id": "b", "at": "2020-05-18"}, {"id": "c", "at": "2020-05-18"}]
    F._by_instant(items, idx, np.array([True, True, True, True]), None, "first")
    assert [it["id"] for it in items] == ["c", "a", "b"], items
    assert [it["at_time"] for it in items] == ["7:28 am", "7:36 am", "10:23 am"], items


# ================================ X5 (the auditor's replays): no change without its values, each with its span =====
def test_x5_a_side_clause_with_a_change_and_no_number_goes():
    """The auditor, on the replayed live forms: "Gaming fell to 30% ..., from 49% in 2022, while comedy and music
    grew." (no values for comedy and music)."""
    out, why = gate("Gaming grew to 22%, from 12% in the 4 weeks before, while comedy and sports fell.", top(),
                    said=True)
    assert why is None and out == "Gaming grew to 22%, from 12% in the 4 weeks before.", out
    out, _ = gate("Gaming grew to 22%, while sports fell to 9%.", top(), said=True)
    assert "while sports fell to 9%" in out, out   # a side clause with its number stays


def test_x5_a_change_from_the_year_before_says_that_year_on_its_own_value():
    """The auditor: "<theme> fell from 11% to 8% in 2021" in an answer about 2022 (8% was 2022's, 11% was 2021's)."""
    s = top()
    s["window"] = {"words": "In 2022", "start": "2022-01-01", "end": "2022-12-31", "clipped": False}
    s["previous"] = dict(s["previous"], words="in 2021")
    out, _ = gate("Speed runs fell from 11% to 8% in 2021.", s, said=True)
    assert out == "Speed runs fell from 11% in 2021 to 8%.", out


# ================================ X9 (the auditor's replays): the so-what's move is not a bullet too ===============
def test_x9_a_move_the_so_what_says_is_not_also_a_bullet():
    I = ins()
    f = {"answer": "In the 4 weeks up to 30 October 2026, you were into gaming, comedy and internet culture.",
         "dropped": [], "observations": [
             "Inside gaming: Speed runs and Block battles.",
             "Gaming grew from 12% to 22% against the 4 weeks before (5 September to 2 October 2026)."],
         "so_what": "Worth noticing: gaming grew from 12% to 22% against the 4 weeks before, while sports fell from "
                    "16% to 9%. Say \"only sports\" to see what you still open of it."}
    out = I.p6_once(f, top())["observations"]
    assert out == ["Inside gaming: Speed runs and Block battles."], out


# ================================ X4 (the auditor's replays): a channel's rise says the filters of its count ========
def test_x4_a_channels_rise_under_without_shorts_counts_long_videos():
    """The auditor: "<channel> is new at the top: 12 videos now" after "without shorts" (12 long videos)."""
    I = ins()
    c = {"kind": "channel_rise", "channel": "Kite Lab", "items": 12, "previous_items": 0}
    s = top(filters={"topic": None, "without_shorts": True})
    t = I.so_what_text(c, s)
    assert t.startswith("Kite Lab is new at the top: 12 long videos now, against 0"), t
    assert I.so_what_text(c, top()).startswith("Kite Lab is new at the top: 12 videos now"), t


def test_x4_a_count_said_with_its_days_names_every_filter_in_force():
    """The auditor, on the made-up writer's follow-ups: after "without shorts": "You opened 225 videos on 27 different
    days." (225 long videos). A noun followed by "on <a number>" is still the count's subject."""
    s = top(filters={"topic": None, "without_shorts": True})
    s["totals"] = dict(s["totals"], items=225, long=225, shorts=0, days_active=27)
    out, _ = gate("You opened 225 videos on 27 different days.", s)
    assert out == "You opened 225 long videos on 27 different days.", out
    out2, _ = gate("You opened 225 videos on YouTube.", s)
    assert out2.startswith("You opened 225 long videos"), out2


# ================================ X9 (the live run of pass 6, row 7): a record named only deep in the sheet ==========
def test_x9_a_move_of_an_area_named_only_in_the_periods_is_said_once():
    """Live, row 7: "Woodwork fell from 11% in 2020 to 2% in 2026." as a bullet, then the so-what "The learning side
    gave way: woodwork fell from 11% in 2020 to 2% in 2026." The area was named only in the sheet's periods, so the
    repeat check did not know it."""
    I = ins()
    s = {"kind": "changed", "lang": "en", "filters": {"topic": None, "without_shorts": False},
         "themes": [{"name": "Kite repairs", "area": "crafts", "share": 0.06}],
         "periods": [{"label": "2020", "areas": [{"name": "woodwork", "share": 0.11}]},
                     {"label": "2026", "areas": [{"name": "woodwork", "share": 0.02}]}],
         "areas_change": {"left": [{"name": "woodwork", "from": 0.11, "to": 0.02}]}}
    f = {"answer": "Since 2020, crafts took more of it.", "dropped": [],
         "observations": ["Kite repairs rose from 0.1% in 2020 to 6% in 2026.",
                          "Woodwork fell from 11% in 2020 to 2% in 2026."],
         "so_what": "The learning side gave way: woodwork fell from 11% in 2020 to 2% in 2026. Say \"only woodwork\" "
                    "to see what you still open of it."}
    out = I.p6_once(f, s)["observations"]
    assert out == ["Kite repairs rose from 0.1% in 2020 to 6% in 2026."], out


# =====================================================================================================================
# The second round of the pass: what an independent hand check of the merged build found (30 live answers, made-up
# here). Each test fails on ed32261 (the build the check read) and on c073c24.
# =====================================================================================================================
def _run(raw, s):
    I = ins()
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    return I.layout(f, s)[0]["text"]


def _count_sheet(**kw):
    s = top(kind="count", filters={"topic": "kites", "without_shorts": False}, **kw)
    s["totals"] = dict(s["totals"], items=1094)
    s["previous"] = dict(s["previous"], items=808, words="the same part of 2025 (1 January to 30 October 2025)")
    s["topics"] = [{"name": "kites", "items": 1094, "days": 200, "matched_by": "themes and words"}]
    return s


# ---- R2-1: a change's subject is worded by code, never left to "That" (b3, n06.3)
def test_r2_a_change_of_the_count_names_its_subject_and_both_values():
    """b3: after "<theme> led with 373 videos", "That is up from 808 in the same part of 2025": 808 was the topic's
    count (1,094 now); read in place, "That" is the theme's 373."""
    I = ins()
    lines = [o["text"] for o in I.code_form(_count_sheet())["observations"]]
    assert not any(re.match(r"^(?:That|This|It)\b", t) for t in lines), lines
    one = [t for t in lines if "808" in t]
    assert one and "kites videos" in one[0].lower() and "1,094" in one[0], one
    raw = {"answer": "x", "observations": [
        {"text": "{themes[1].name} led with {themes[1].items} videos.", "uses": []},
        {"text": "That is up from {previous.items} in {previous.words}.", "uses": []}]}
    text = _run(raw, _count_sheet())
    assert "That is" not in text and "That's" not in text, text


def test_r2_a_pronoun_led_change_is_reworded_or_goes():
    s = _count_sheet()
    out, _ = gate("That is up from 808 in the same part of 2025.", s, said=True)
    assert out is None or (not out.startswith("That") and "1,094" in out and "kites videos" in out), out
    out, _ = gate("It fell from 9% to 5% against the 4 weeks before.", top(), said=True)
    assert out is None, out


# ---- R2-2: saved and never opened counts every platform, and says what it counts (b2, b4)
def test_r2_saved_and_never_opened_counts_instagram_saves_too():
    """b4: "You saved and never opened 6 <theme>": 6 was the YouTube ones; by hand 371 (290 reels, 75 posts, 6
    YouTube videos)."""
    from mvp import facts as F
    ids = ["y1", "y2", "r1", "r2", "p1", "w1"]
    plat = np.array([0, 0, 1, 1, 1, 0], dtype=np.int8)
    kinds = ["playlist", "save", "watch"]
    #          y1 saved   y2 saved+watched   r1 saved   r2 saved   p1 saved   w1 watched
    it = np.array([0, 1, 1, 2, 3, 4, 5])
    kind = np.array([0, 0, 2, 1, 1, 1, 2])
    idx = SimpleNamespace(ids=ids, it=it, day=np.arange(7), platform=plat, kinds=kinds,
                          kind_mask=lambda ks: np.isin(kind, [n for n, k in enumerate(kinds) if k in ks]))
    facts = SimpleNamespace(theme=np.array([7, 7, 7, 7, 7, 7]))
    th = SimpleNamespace(shown=lambda t: "Kite repairs")
    media = {"y1": "video", "y2": "video", "r1": "reel", "r2": "reel", "p1": "post", "w1": "video"}
    view = SimpleNamespace(items={i: SimpleNamespace(media=m, platform="youtube" if i[0] in "yw" else "instagram")
                                  for i, m in media.items()})
    rows = F._saved_not_opened(view, idx, facts, th, [7])
    assert rows and rows[0]["n"] == 4 and rows[0]["youtube"] == 1 and rows[0]["noun"] == "posts and videos", rows
    I = ins()
    t = I.so_what_text({"kind": "saved", "theme": "Kite repairs", "n": 4, "noun": "posts and videos"}, top())
    assert t.startswith("You saved and never opened 4 Kite repairs posts and videos"), t


def test_r2_a_saved_count_in_the_writers_words_gets_the_rows_noun():
    s = top()
    s["library"] = {"saved_not_opened": [{"theme": "Speed runs", "n": 26, "noun": "posts and videos"}]}
    out, _ = gate("You saved 26 Speed runs videos; want to open them next?", s, said=True)
    assert out and "never opened 26 Speed runs posts and videos" in out, out


# ---- R2-3: channels set behind themes they are not in (c06)
def test_r2_channels_said_behind_themes_they_are_not_in_are_dropped():
    """c06: "<A> and <B> were the biggest themes, with <ch1> and <ch2> behind them" (topics[0].top_themes with
    topics[0].channels): both channels were 95% a third theme."""
    kept, why = obs("{themes[0].name} and {themes[1].name} were the biggest themes, with {channels[0].name} and "
                    "{channels[1].name} behind them.")
    assert kept is None and why, (kept, why)   # Doggo Plays is Block battles
    kept, why = obs("{themes[1].name} and {themes[2].name} were there too, with {channels[0].name} and "
                    "{channels[1].name} behind them.")
    assert kept, why   # each channel is its theme's


def test_r2_a_topics_channels_carry_their_theme(r12):
    s = sheet_of(r12, "how many minecraft videos did i watch in 2021")
    ch = [c for t in s.get("topics") or [] for c in t.get("channels") or []]
    assert ch and all(c.get("theme") for c in ch), ch


# ---- R2-4: a record's own Shorts share is never said of the scope (n05b)
def test_r2_a_channels_own_shorts_share_never_gets_the_scopes_base():
    """n05b: "... and 0% of your science videos shows <ch> was almost all long videos" (0% was the channel's Shorts
    share; the channel is 3.6% of the science videos)."""
    for f_ in ({"topic": "gaming", "without_shorts": False}, {"topic": None, "without_shorts": False}):
        s = top(kind="last", filters=f_)
        s["channels"][1]["shorts_share"] = 0.0
        s["items"] = [{"id": "v1", "title": "A made-up run", "channel": "Pixel Forge", "at": "2026-10-30",
                       "theme": "Speed runs"}]
        s["topics"] = [{"name": f_["topic"] or "gaming", "items": 300}]
        raw = {"answer": "x", "observations": [{"text": "{channels[0].name} and {channels[1].name} were the biggest "
                                                        "channels, and {channels[1].shorts_share} shows "
                                                        "{channels[1].name} was almost all long videos.", "uses": []}]}
        text = _run(raw, s)
        assert not re.search(r"\b0% (?:of|shows)\b", text), text


# ---- R2-5: no rank word on a tie (n03)
def test_r2_a_tie_is_never_said_as_a_lead():
    """n03: "In 2025, for music, <ch1> led, ahead of <ch2>": both had 11 long music videos."""
    I = ins()
    t = top(kind="channels")
    t["channels"][1]["items"] = 30
    t["channels"].append({"name": "Laugh Lab", "items": 12, "days": 5, "area": "comedy", "theme": "Sketch edits",
                          "shorts_share": 0.97})
    ans = I.code_form(t)["answer"]
    assert "Pixel Forge led" not in ans and "tied" in ans, ans
    kept, why = obs("{channels[0].name} led, ahead of {channels[1].name}.", t)
    assert kept is None, (kept, why)


# ---- R2-6: "N more" counts new videos, not videos opened again (b8)
def test_r2_since_a_season_counts_new_videos_apart_from_reopened_ones():
    """b8: "since then you opened ... 12 more of the second": 9 of the 12 were opened in the summer too (3 new)."""
    from mvp import facts as F
    # channel 0: in the season (days 1..3) videos 0,1,2; after it (day 10..12) videos 1, 2 (again) and 3 (new)
    idx = SimpleNamespace(it=np.array([0, 1, 2, 1, 2, 3]), day=np.array([1, 2, 3, 10, 11, 12]),
                          creator=np.array([0, 0, 0, 0]))
    ev = np.ones(6, bool)
    opened, new = F._since_counts(idx, ev, 3, 0)
    assert (opened, new) == (3, 1), (opened, new)
    I = ins()
    from mvp.tests.test_round12_pass4 import into_summer
    s = into_summer()
    s["new"] = {"themes": [], "channels": [{"name": "Kite Lab", "items": 40, "theme": "Speed runs", "since_items": 12,
                                            "since_new": 3},
                                           {"name": "Moss Den", "items": 30, "theme": "Meme drops",
                                            "since_items": 9, "since_new": 9}]}
    texts = [o["text"] for o in I.code_form(s)["observations"]]
    one = [t for t in texts if "Kite Lab (40)" in t]
    assert one and "3 more of the first" in one[0] and "12 more" not in one[0], one


# ---- R2-7: under "without Shorts" every count of videos is of long videos (c03, n03, n06.1, n06.3)
def test_r2_without_shorts_every_count_of_videos_says_long():
    w = top(filters={"topic": None, "without_shorts": True})
    cases = {"Pixel Forge and Doggo Plays came next, with 15 and 9 videos.": "with 15 and 9 long videos",
             "Speed runs led with 130 videos, ahead of Block battles.": "130 long videos",
             "Behind Speed runs: Pixel Forge (14 videos) and Doggo Plays (9).": "(14 long videos)"}
    for text, want in cases.items():
        out, _ = gate(text, w, said=True)
        assert out and want in out, out
    out, _ = gate("Speed runs led with 130 videos, ahead of Block battles.", top(), said=True)
    assert "130 videos" in out, out   # with Shorts: as it was


# ---- R2-8: a weekday question is a history question (n02)
def test_r2_what_do_i_usually_watch_on_a_weekday_is_read_as_history(r12):
    """n02: "what do i usually watch on sundays": history.read returned None and the bot said nothing matched."""
    from mvp import history as H
    for t, wd in (("what do i usually watch on sundays", 6), ("what do i watch on fridays", 4),
                  ("what do i usually watch on a saturday", 5)):
        q = H.read(t, TODAY)
        assert q is not None and q.weekday == wd and q.window.kind == "all", (t, q)
    assert H.read("remind me on sundays to watch a cooking video", TODAY) is None
    s = sheet_of(r12, "what do i usually watch on sundays")
    assert s["filters"]["weekday"] == "Sundays" and s["totals"]["items"] > 0, s["filters"]
    assert "other days" in (s.get("previous") or {}).get("words", ""), s.get("previous")
    I = ins()
    assert I.bases(s)["opened"] == "what you opened on Sundays", I.bases(s)
    cf = I.code_form(s)
    form = {"answer": cf["answer"], "observations": [o["text"] for o in cf["observations"]], "offers": [],
            "so_what": None, "dropped": []}
    text = I.layout(form, s)[0]["text"]
    assert "Sundays" in text.split("\n")[0], text


# ---- R2-9: "the week of <date>" is a history window (n01)
def test_r2_the_week_of_a_date_is_a_window():
    from mvp import history as H
    q = H.read("what did i watch the week of march 9 2025", TODAY)
    assert q is not None and str(q.window.start) == "2025-03-09" and str(q.window.end) == "2025-03-15", q


# ---- R2-S4: a list said "by videos opened" is the top of its ranking, else "among" (b8)
def test_r2_a_ranked_list_with_a_gap_says_among():
    """b8: "New that summer, by videos opened: <A> (97) and <B> (60)" where a 68 was left out (sensitive)."""
    from mvp.tests.test_round12_pass4 import into_summer
    I = ins()
    s = into_summer()
    s["new"] = {"themes": [], "channels": [
        {"name": "Kite Lab", "items": 97, "theme": "Speed runs", "since_items": 20, "since_new": 20},
        {"name": "Dating Tips Daily", "items": 68, "theme": "Meme drops", "since_items": 34, "since_new": 30},
        {"name": "Moss Den", "items": 60, "theme": "Meme drops", "since_items": 12, "since_new": 3}]}
    texts = [o["text"] for o in I.code_form(s)["observations"]]
    one = [t for t in texts if "Kite Lab (97)" in t]
    assert one and "by videos opened" not in one[0] and one[0].startswith("Among the channels new that summer"), one


# ---- R2-S2, S5: a change with one value gets the other; the end value is never put in the base period (c05.1, c08)
def test_r2_a_change_to_one_value_says_where_it_came_from():
    """c05.1: "Film and TV rose to 8% of your long videos and science to 6%, both above 2023" (no 2023 values)."""
    s = top()
    kept, why = obs("{areas[0].name} rose to {areas[0].share} and {areas[2].name} to {areas[2].share}.", s)
    assert kept is None, kept   # internet culture moved under 3 points (or the other way): not said as a rise
    kept, why = obs("{areas[0].name} rose to {areas[0].share}.", s)
    assert kept and "from 12%" in kept, (kept, why)
    kept, why = obs("{areas[0].name} rose to {areas[0].share} and {areas[1].name} to {areas[1].share}.", s)
    assert kept is None and why == ["direction"], (kept, why)   # comedy fell


def test_r2_the_end_value_goes_after_the_base_period():
    """c08: "Gaming slipped from 50% to 47% in the summer before": 47% was the fall's own share."""
    s = top()
    s["previous"] = dict(s["previous"], words="the summer before (1 June to 31 August 2021)")
    kept, why = obs("{areas[3].name} slipped from {areas[3].previous_share} in {previous.words}.", s)
    assert kept == "Sports slipped from 16% in the summer before (1 June to 31 August 2021) to 9%.", (kept, why)


# ---- R2-S6: a move under 3 points is not said in Spanish either (n07)
def test_r2_a_small_move_in_points_goes_in_spanish_too():
    s = top(lang="es")
    s["areas"][0] = dict(s["areas"][0], change_vs_previous=1.68)
    kept, why = obs("{areas[0].name} aportó {areas[0].share}, subió {areas[0].change_vs_previous} puntos frente a "
                    "{previous.words}.", s)
    assert kept is None and why == ["small_move"], (kept, why)


# ---- R2-S3: one fact once (n06.1, n07)
def test_r2_one_records_channels_and_a_leads_share_said_once():
    I = ins()
    f = {"answer": "En 2022, lo que más viste fue gaming con 48% de todo.", "dropped": [],
         "observations": ["Gaming aportó 48%.", "Behind Speed runs (5% of your long videos): Pixel Forge, with Doggo "
                          "Plays following.", "Behind Speed runs: Pixel Forge (14 long videos) and Doggo Plays (9).",
                          "Gaming grew from 12% to 48%."], "so_what": None}
    out = I.p6_once(f, top())["observations"]
    assert out == ["Behind Speed runs: Pixel Forge (14 long videos) and Doggo Plays (9).",
                   "Gaming grew from 12% to 48%."], out


# ---- R2-S8: a first's arc is said after another first's (n05a)
def test_r2_a_firsts_arc_key_names_its_topic():
    from mvp import facts as F
    out = {"kind": "first", "filters": {"topic": "kites"}, "themes": [],
           "periods": [{"label": "2023", "items": 131}, {"label": "2026", "items": 12}]}
    c = [x for x in F._so_what_candidates(out, "first", None) if x["kind"] == "path"]
    assert c and c[0]["key"] == "path:faded:kites", c
