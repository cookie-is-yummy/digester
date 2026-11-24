"""Round 12, fifth pass (DESIGN.md section 19.A): what the independent recount (eval_claims.py, the auditor) found on
the history answers, made structural: every percent with its base, worded by code; Shorts shares of all the YouTube
videos; a filtered sheet's moves, channels and Shorts said of their own set; "peaked" computed over every span it is
said of; a topic's row under the sheet's other filters; a first or a last of the sheet's own scope; an area's two-word
name read whole; a season not begun; the window's end said once; the trace with each sent sentence's paths.

Every test here fails on af7befb (the build the auditor read). Made-up data only: the made-up library
(tests/r12_library.py), the sheets of tests/test_round12_pass2_fix.py and small sheets built here.
"""
import copy
import re
from datetime import date

from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, mods, TODAY  # noqa: F401  (fixtures)
from mvp.tests.test_round12_pass2 import sheet_of
from mvp.tests.test_round12_pass2_fix import top


def ins():
    from mvp import insight
    return insight


def _pcts(text):
    return re.findall(r"\d+(?:\.\d)?%", text or "")


# ================================ 1. every percent with its base ==================================================
def test_a_filtered_channels_answers_moves_say_their_base_after_the_first_number():
    """The audit: "X grew from 10% to 15% against 2023" in a gaming answer (shares of the gaming videos, no base)."""
    I = ins()
    s = top(kind="channels", filters={"topic": "gaming"})
    s["themes"] = [dict(t, share=v) for t, v in zip(s["themes"], (0.15, 0.14, 0.11, 0.1))]
    raw = {"answer": "", "observations": []}
    f = I.fill(I.check(raw, s, strict=True), raw, s)
    moves = [o for o in f["observations"] if re.search(r"\b(?:grew|fell) ", o)]
    assert moves, f["observations"]
    for o in moves:
        assert re.search(r"\b(?:grew|fell) to \d+% of your gaming videos, from \d+% in ", o), o


def test_a_percent_with_no_base_gets_the_sheets_own_base_whoever_wrote_it():
    I = ins()
    s = top(filters={"topic": "gaming"})
    names = I._gate_names(I.shown(s))
    out, why = I.gate_sentence("Speed runs led with 23%, then Block battles (11%).", s, names, {})
    assert why is None and out == "Speed runs led with 23% of your gaming videos, then Block battles (11%).", out
    # a Shorts share and a record's share in one sentence: each kind its own base
    out, _ = I.gate_sentence("Shorts were 68%, while Speed runs fell to 9%.", s, names, {})
    assert out == ("Shorts were 68% of your gaming videos on YouTube, while Speed runs fell to 9% of your gaming "
                   "videos."), out
    # a run of numbers takes the base after its last one ("at 11% and 5%")
    out, _ = I.gate_sentence("Speed runs and Block battles peaked then, at 11% and 5%.", s, names, {})
    assert out.endswith("at 11% and 5% of your gaming videos."), out


def test_an_unfiltered_answer_says_of_what_you_opened_once_and_shorts_every_time():
    I = ins()
    s = top()
    names = I._gate_names(I.shown(s))
    st = {}
    a, _ = I.gate_sentence("Speed runs led with 23%, then Block battles (11%).", s, names, st)
    b, _ = I.gate_sentence("Meme drops grew from 3% to 7% against the 4 weeks before.", s, names, st)
    c, _ = I.gate_sentence("Shorts were 68%; the long ones were typically about 12 minutes.", s, names, st)
    assert a == "Speed runs led with 23% of what you opened, then Block battles (11%)." and st["opened_said"]
    assert b == "Meme drops grew from 3% to 7% against the 4 weeks before.", b   # said once in the answer
    assert c.startswith("Shorts were 68% of your YouTube videos;"), c
    # a Shorts share that is none of the spans' own (a theme's, or a number the sheet does not hold) is not said
    # "of your YouTube videos": its number, its clause or its sentence goes
    d, why = I.gate_sentence("Shorts were 79% of your YouTube videos.", s, names, st)
    assert d is None and why == "own_shorts_share"
    e, _ = I.gate_sentence("Behind Speed runs (5% of what you opened): Pixel Forge; 15% of it was Shorts.", s, names, st)
    assert e == "Behind Speed runs (5%): Pixel Forge.", e   # (said once: the answer said it above)
    f, _ = I.gate_sentence("Inside gaming: Speed runs (5% of everything you opened) and Meme drops (7%).", s, names, st)
    assert "(5% of everything you opened)" in f   # "Inside <area>:" keeps it (else it reads as of the area)


def test_a_run_of_shares_after_an_areas_name_goes_next_to_its_own_names():
    """Live: "A and B were the biggest gaming themes, with 5% and 5%" (of everything opened, read as of gaming)."""
    I = ins()
    s = top()
    names = I._gate_names(I.shown(s))
    out, _ = I.gate_sentence("Speed runs and Block battles were the biggest gaming themes, with 5% and 5%.", s, names,
                             {"opened_said": True})
    assert out == "Speed runs (5% of everything you opened) and Block battles (5%) were the biggest gaming themes.", out


def test_a_change_over_the_years_says_each_value_with_its_year():
    """Live: "Shorts rose from 4% to 70% between 2020 and 2026" (read as the whole span's share)."""
    I = ins()
    s = top(kind="changed")
    s.pop("previous", None)   # a change has no span before: its two years
    s["window"] = dict(s["window"], start="2020-01-01", end="2026-10-30")
    s["periods"] = [{"label": "2020", "items": 900, "themes": [], "shorts_share": 0.04},
                    {"label": "2026", "items": 950, "themes": [], "shorts_share": 0.7}]
    s["areas_change"] = {"from": "2020", "to": "2026", "left": [], "arrived": [],
                         "shorts": {"from": "2020", "from_share": 0.04, "to": "2026", "to_share": 0.7}}
    f = I.check({"answer": "-", "observations": [{"text": "Shorts rose from {areas_change.shorts.from_share} to "
                                                          "{areas_change.shorts.to_share}.", "uses": []}]}, s,
                strict=True)
    o = f["observations"][0] if f["observations"] else ""
    assert "4% in 2020 to 70% in 2026" in o and "between" not in o, (o, f["dropped"])
    g, _ = I.gate_sentence(o, s, I._gate_names(I.shown(s)), {})
    assert g == "Shorts rose from 4% of your YouTube videos in 2020 to 70% in 2026.", g


def test_a_shorts_share_in_an_answer_without_shorts_is_not_sent():
    I = ins()
    s = top(filters={"without_shorts": True})
    out, why = I.gate_sentence("Shorts were 40% of it.", s, I._gate_names(I.shown(s)), {})
    assert out is None and why == "shorts_left_out"


# ================================ 2. Shorts of all the YouTube videos ===============================================
def test_a_shorts_share_said_of_your_youtube_videos_is_of_all_of_them(r12):
    """The audit, (d): "79% of your YouTube videos" was of the ones with a known length (77% of all of them)."""
    I = ins()
    s = sheet_of(r12, "what have i been watching the most lately")
    t = s["totals"]
    assert t["shorts_yt_share"] == round(t["shorts"] / t["by_platform"]["youtube"], 3)
    assert I.shown(s, model=True)["totals"]["shorts_share"] == t["shorts_share"]   # the model reads it as built
    assert "shorts_yt_share" not in I.user_message(s)
    assert I.shown(s)["totals"]["shorts_share"] == t["shorts_yt_share"]           # code says it as said
    # with a video of no known length, the two differ, and code's own line says the share of all of them
    s2 = top()
    s2["totals"] = dict(s2["totals"], shorts=70, long=20, shorts_share=0.778, shorts_yt_share=0.7,
                        by_platform={"youtube": 100, "instagram": 0})
    f = I.code_form(s2)
    said = " ".join([f.get("answer") or ""] + [o["text"] for o in f["observations"]])
    assert "70% of your YouTube videos" in said and "78%" not in said, said


def test_a_topics_shorts_shift_is_of_its_videos_on_youtube():
    I = ins()
    c = {"kind": "shorts_shift", "direction": "up", "share": 0.6, "previous_share": 0.3, "topic": "block games"}
    assert I.so_what_text(c, {"previous": {"words": "the 4 weeks before"}}).startswith(
        "Shorts went up to 60% of your block games videos on YouTube, from 30%")


# ================================ 3. a channel under a topic =========================================================
def test_a_channels_theme_share_under_a_topic_is_not_said_as_of_all_its_videos():
    """The audit, (b): "A and B are both about T (100% and 99% of their videos)": of their math videos only."""
    I = ins()
    s = top(kind="channels", filters={"topic": "gaming"})
    s["channels"] = [dict(c, theme="Speed runs", theme_share=0.99) for c in s["channels"][:2]] + s["channels"][2:]
    f = I.code_form(I.shown(s) | {"filters": s["filters"]})
    said = " ".join(o["text"] for o in f["observations"])
    assert "of their videos" not in said and "of its videos" not in said, said
    assert "In gaming, " in said and "are both about Speed runs." in said, said


def test_a_clip_channels_shorts_share_under_a_topic_is_not_a_number():
    I = ins()
    s = top(kind="channels", filters={"topic": "gaming"})
    s["channels"] = [dict(s["channels"][0], shorts_share=0.95), dict(s["channels"][1], shorts_share=0.02, days=40)] + \
        s["channels"][2:]
    f = I.code_form(s)
    line = next((o["text"] for o in f["observations"] if "clip channel" in o["text"]), "")
    assert line and not _pcts(line.split(";")[0]) and "Shorts)" not in line, line
    # unfiltered, the number stays (of all its videos then)
    s0 = top(kind="channels")
    s0["channels"] = [dict(s0["channels"][0], shorts_share=0.95), dict(s0["channels"][1], shorts_share=0.02, days=40)]\
        + s0["channels"][2:]
    line0 = next((o["text"] for o in I.code_form(s0)["observations"] if "clip channel" in o["text"]), "")
    assert "(95% Shorts)" in line0, line0


# ================================ 4. a peak over every span of its length ===========================================
def test_a_peak_is_not_said_when_a_span_a_month_earlier_held_more():
    """The audit, (a): "peaked then, at 5%, more than in any other three months": the three months starting one month
    earlier held 5.4%. Calendar seasons alone said it peaked."""
    import numpy as np
    from types import SimpleNamespace as NS
    F = mods()[1]
    months = [(2024, m) for m in range(1, 13)] + [(2025, m) for m in range(1, 13)]
    day, it, theme = [], [], []
    k = 0
    for y, m in months:
        # theme 1: 3% a month, 9% in May 2025, 8% in June to August 2025 (the window), 3% after
        share = {(2025, 5): 0.12, (2025, 6): 0.08, (2025, 7): 0.08, (2025, 8): 0.06}.get((y, m), 0.03)
        for j in range(100):
            day.append(date(y, m, 1 + j % 28).toordinal())
            it.append(k)
            theme.append(1 if j < share * 100 else 2)
            k += 1
    idx = NS(day=np.array(day), it=np.array(it))
    facts = NS(theme=np.array(theme))
    so, eo = date(2025, 6, 1).toordinal(), date(2025, 8, 31).toordinal()
    rows = [{"name": "Peak theme", "theme_id": 1, "share": 0.073, "items": 22},
            {"name": "Flat theme", "theme_id": 2, "share": 0.927, "items": 278}]
    out = F._peaks_new(idx, facts, None, np.ones(len(day), bool), so, eo, rows)
    assert out["peaked"] == [], out   # May to July held 9.3%, more than the summer's 7.3%
    # without the high May, the summer is the highest of every 3-month span: a peak
    theme2 = [2 if (date.fromordinal(d).month == 5 and date.fromordinal(d).year == 2025 and t == 1 and
                    (i % 100) >= 3) else t for i, (d, t) in enumerate(zip(day, theme))]
    out2 = F._peaks_new(idx, NS(theme=np.array(theme2)), None, np.ones(len(day), bool), so, eo, rows)
    assert [p["name"] for p in out2["peaked"]] == ["Peak theme"] and out2["peaked"][0]["span_months"] == 3, out2


def test_the_span_said_is_the_span_computed():
    I = ins()
    for (a, b), want in ((("2025-06-01", "2025-08-31"), "three months"), (("2025-01-01", "2025-12-31"), "year"),
                         (("2026-10-03", "2026-10-30"), "four weeks"), (("2026-09-01", "2026-10-30"), "two months")):
        assert I._span_noun({"window": {"start": a, "end": b}}) == want, (a, b)


# ================================ 5. a topic's row and a first, of the sheet's own scope ============================
def test_a_without_shorts_follow_ups_topic_row_leaves_the_shorts_out(r12):
    """The audit: a "without Shorts" follow-up's topic row kept its Shorts (8,005 against 1,875 in its totals)."""
    s = sheet_of(r12, "most watched channels in gaming without shorts")
    tp = s["topics"][0]
    assert s["filters"]["without_shorts"] and tp["shorts"] == 0, tp
    assert tp["items"] == s["totals"]["items"], (tp["items"], s["totals"]["items"])


def test_a_first_is_the_first_of_the_sheets_own_topic_and_its_day_is_the_first_open(r12):
    """The audit: "You first opened a gaming video on 5 April 2020" where the topic's own themes hold one from 2019;
    the date came from the word match, and an item's "at" was its last open."""
    I = ins()
    s = sheet_of(r12, "when did i first start watching gaming videos")
    tp = s["topics"][0]
    assert s["items"] and s["items"][0]["at"] == tp["first_watched"], (s["items"][0]["at"], tp["first_watched"])
    ats = [it["at"] for it in s["items"]]
    assert ats == sorted(ats), ats
    f = I.code_form(s)
    assert f["answer"].startswith("You first opened a gaming video on " +
                                  I._day_words(date.fromisoformat(tp["first_watched"])))
    s2 = dict(s, filters=dict(s["filters"], topic="art"), items=s["items"][:1])
    assert I.code_form(s2)["answer"].startswith("You first opened an art video on ")


def test_a_cards_caption_says_no_length_over_three_hours():
    I = ins()
    assert I.item_caption(1, {"channel": "Long Stream", "at": "2020-03-29", "length_s": 3236700}) == \
        "1. Long Stream · 29 Mar"
    assert I.item_caption(2, {"channel": "Short Talk", "at": "2020-03-29", "length_s": 600}, year=2020).endswith(
        "10 min")


# ================================ 6. the reads =======================================================================
def test_an_areas_two_word_name_is_one_topic():
    """The audit: "most watched channels in <two-word area>" was read as its first word (22 answers)."""
    Hm = mods()[0]
    for t, want in (("most watched channels in art and design", ["art and design"]),
                    ("how many film and tv videos did i watch this year", ["film and tv"]),
                    ("when did i first start watching food and cooking videos", ["food and cooking"]),
                    ("did i watch more music or more film and tv videos in 2025", ["music", "film and tv"]),
                    ("did i watch more art and design or more science videos in 2026", ["art and design", "science"])):
        q = Hm.read(t, TODAY)
        assert q is not None and q.topic == want, (t, q and q.topic)
    assert Hm.read("did i watch more music or more film and tv videos in 2025", TODAY).kind == "compare_topics"
    q = Hm.read("how many cats and dogs videos did i watch", TODAY)   # two words that are no area: as before
    assert q.topic == ["cats", "dogs"]


def test_a_season_not_begun_is_that_season_never_a_topic():
    """The audit: "into in the winter of <this year>", asked in November, read "winter" as a topic over the year."""
    Hm = mods()[0]
    q = Hm.read("what was i into in the winter of 2026", TODAY)
    assert q.topic == [] and q.window.start == date(2026, 12, 1) and q.window.end == date(2027, 2, 28), q
    q = Hm.read("what was i into in the summer of 2023", TODAY)   # a past season as before
    assert q.window.start == date(2023, 6, 1) and q.window.end == date(2023, 8, 31)


def test_a_range_past_the_export_says_its_end_once(r12):
    """The audit: "From 1 January 2024 to 24 November 2026 up to 30 October 2026, where your export ends"."""
    s = sheet_of(r12, "how did my watching change from 2024 to 2026")
    w = s["window"]["words"]
    assert w.count(" to ") == 1 and "up to" not in w and w.endswith("30 October 2026, where your export ends"), w


# ================================ 7. the trace keeps each sentence's paths ==========================================
def test_each_sent_sentence_has_the_paths_it_rests_on():
    I = ins()
    s = top()
    s["totals"] = dict(s["totals"], shorts_share=0.79, shorts=790, long=210)
    text = ("Gaming led with 22% of what you opened, then comedy (11%).\n\n"
            "• Shorts were 79% of your YouTube videos.\n\nShare of what you opened, by area:\n██████░░ 22% gaming")
    paths = I.sentence_paths(text, s)
    assert len(paths) == 2, paths   # the chart's caption and bars are code's drawing, not sentences
    assert paths[0] == ["areas[0].share", "areas[1].share"] and "totals.shorts_share" in paths[1], paths
    blob = repr(paths)
    assert "gaming" not in blob and "comedy" not in blob   # paths only, no words
