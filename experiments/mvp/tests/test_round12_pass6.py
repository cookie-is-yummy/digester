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
                 "runs\" to see the rest of Speed runs you opened then."), t


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
