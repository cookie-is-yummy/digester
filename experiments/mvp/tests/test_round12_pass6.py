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
    assert out == "You have 5 Speed runs videos you saved and never opened; want to open them next?", out
    out, _ = gate("You saved 6 Block battles tutorials; want them?", dict(s, library={"saved_not_opened": [
        {"theme": "Block battles tutorials", "n": 6}]}))
    assert out.startswith("You have 6 Block battles tutorials you saved and never opened"), out


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
    assert line == ("You were deepest into blender in 2023 (131 videos); in 2026 up to 30 October it was 12. You "
                    "still have 6 Render tutorials you saved and never opened: want them as a list, to pick it up "
                    "again?"), line


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
    assert any(t.startswith("New that summer: Kite Lab (40 videos, 2 since) and Moss Den (30 videos, 9 since)")
               for t in texts), texts


def test_x17_what_he_did_then_and_not_since_is_a_so_what_with_a_step():
    from mvp import facts as F
    out = {"kind": "top", "themes": [], "new": {"channels": [{"name": "Kite Lab", "items": 40, "theme": "Speed runs",
                                                              "since_items": 2}]}}
    q = SimpleNamespace(window=SimpleNamespace(label="summer"), season="the summer of 2023")
    c = [x for x in F._so_what_candidates(out, "top", q) if x["kind"] == "then_not_since"]
    assert c and c[0]["channel"] == "Kite Lab" and c[0]["since"] == 2, c
    t = ins().so_what_text(c[0], {})
    assert t == ("Kite Lab was a thing of that time: 40 videos then, 2 since. Say \"only Speed runs\" to see the rest "
                 "of Speed runs you opened then."), t


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
