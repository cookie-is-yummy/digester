"""Round 12, D (DESIGN.md section 19.D): lengths, themes, the fact sheet and the history questions that were misread.

Offline: the fake model of test_mvp (a test fails when it is called where it must not be), a fake videos.list, a fake
naming call, and the made-up library of tests/r12_library.py (known themes; Sunday 22 November 2026, New York). Every
title, channel and handle is invented. The expected numbers are counted here from the library's own rows, by code that
shares nothing with the bot's."""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round11_h import ask, NO_MODEL  # noqa: E402,F401
from mvp.tests.test_slice2 import H  # noqa: E402
from mvp.tests.test_slice6 import AllPool  # noqa: E402
from mvp.tests import r12_library as R  # noqa: E402

NY = ZoneInfo("America/New_York")
TODAY = date(2026, 11, 22)
GAMING, ART, MATH = {"mc", "sr", "cl"}, {"wc", "dd"}, {"ca", "np"}


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def mods():
    from mvp import facts, history, lengths, themes
    return history, facts, lengths, themes


@pytest.fixture()
def r12(env, tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_DERIVED_HOME", str(tmp_path / "derived"))
    lib = R.write(tmp_path / "r12lib")
    Hm, F, L, T = mods()
    L.run(str(lib), key="made-up-key", fetch=R.fake_videos_list(), now=datetime(2026, 11, 22, tzinfo=timezone.utc),
          log=lambda s: None)
    calls = []
    T.build(str(lib), chat=R.fake_namer(calls), log=lambda s: None)
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = AllPool(str(lib))
    bot.max_per_minute = None
    env["clock"][0] = datetime(2026, 11, 22, 17, 0, tzinfo=timezone.utc)
    env["lib"] = lib
    env["name_calls"] = calls
    return env


def person(e):
    return {"handle": H, "library": str(e["lib"]), "timezone": "America/New_York"}


def sheet(e, text):
    Hm, F, _L, _T = mods()
    q = Hm.read(text, TODAY)
    assert q is not None, text
    return F.build(e["bot"], person(e), q, e["clock"][0], text=text)


# ---------------------------------------------------------------- an independent count over the made-up rows
def local(at):
    return datetime.fromisoformat(at).astimezone(NY).date()


def watched(a, b, keys=None, platform=None):
    return {r["id"] for r in R.rows() for k, at in r["events"]
            if k == "watch" and (a is None or a <= local(at)) and (b is None or local(at) <= b)
            and (keys is None or r["theme"] in keys) and (platform is None or r["platform"] == platform)}


def row_of(iid):
    return next(r for r in R.rows() if r["id"] == iid)


def is_clip(iid):
    r = row_of(iid)
    return r["theme"] == "cl"


# ================================================================ (1) lengths
def test_lengths_are_fetched_fifty_a_call_kept_with_their_version_and_resumable(r12, tmp_path):
    _Hm, _F, L, _T = mods()
    path = os.path.join(L.folder(), "lengths.jsonl")
    rows = [json.loads(x) for x in open(path)]
    vids = L.watched_video_ids(str(r12["lib"]))
    assert len(rows) == len(vids) and {r["video_id"] for r in rows} == set(vids)
    assert all(r["version"] == "lengths-v1" and r["refresh_by"] > r["fetched_at"] for r in rows)
    deleted = [r for r in rows if r["length_s"] is None]
    assert len(deleted) == 2                      # the two calculus videos the fake API does not return
    assert "made-up-key" not in open(path).read()
    runs = [json.loads(x) for x in open(os.path.join(L.folder(), "runs.jsonl"))]
    assert runs[-1]["processed"] == len(vids) and runs[-1]["no_answer"] == 2
    assert runs[-1]["calls"] == -(-len(vids) // 50) and "items_per_s" in runs[-1] and "wall_s" in runs[-1]
    # a second run asks for nothing: every row is still fresh
    fetch = R.fake_videos_list()
    again = L.run(str(r12["lib"]), key="k", fetch=fetch, now=datetime(2026, 11, 23, tzinfo=timezone.utc),
                  log=lambda s: None)
    assert again["asked"] == 0 and fetch.calls == []
    # 31 days later every row is past its refresh_by: asked again, and not used until then
    later = datetime(2026, 12, 24, tzinfo=timezone.utc)
    assert L.load(now=later) == {}
    again = L.run(str(r12["lib"]), key="k", fetch=fetch, now=later, log=lambda s: None)
    assert again["asked"] == len(vids)


def test_a_run_with_no_key_and_no_fake_is_refused(r12, monkeypatch):
    _Hm, _F, L, _T = mods()
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        L.run(str(r12["lib"]), log=lambda s: None)


@pytest.mark.parametrize("length,title,published,short", [
    (30, "A clip", "2020-01-01", True), (61, "A clip", "2019-05-01", True), (62, "A clip", "2024-01-01", False),
    (120, "A clip", "2025-01-01", True), (180, "A clip", "2024-10-15", True), (181, "A clip", "2025-01-01", False),
    (120, "Trick shot #shorts", None, True), (120, "Trick shot", None, False), (200, "A #shorts mark", "2025-01-01", False),
    (None, "A clip", None, None), (0, "A clip", None, None)])
def test_the_short_rule(length, title, published, short):
    from mvp import lengths as L
    assert L.is_short(length, title, published) is short


def test_a_video_with_no_answer_has_no_length(r12):
    _Hm, _F, L, _T = mods()
    from mvp.libview import LibraryView
    v = LibraryView(str(r12["lib"]))
    gone = [i for i in v.items if row_of(i)["length"] is None and v.items[i].platform == "youtube"]
    assert len(gone) == 2 and all(L.length_of(v.items[i]) == (None, None) for i in gone)
    assert L.length_of(v.items["rcl001"])[1] is True and L.length_of(v.items["rmc001"]) == (600, False)


# ================================================================ (2) themes
def test_items_land_in_the_right_theme_and_names_come_one_call_per_field(r12):
    _Hm, _F, _L, T = mods()
    th = T.load(str(r12["lib"]))
    rows = R.rows()
    by_name = {}
    for r in rows:
        if r["theme"] == "da":
            continue
        by_name.setdefault(th.shown(th.theme_id(r["id"])), []).append(r["theme"])
    # every shown theme holds one made-up theme only, and every made-up theme is under one name
    assert all(len(set(v)) == 1 for v in by_name.values()), {k: set(v) for k, v in by_name.items()}
    names_of = {}
    for k, v in by_name.items():
        names_of.setdefault(v[0], set()).add(k)
    assert all(len(v) == 1 for v in names_of.values()) and len(names_of) == 8
    assert len(r12["name_calls"]) == len(th.fields) < 10      # one call per field, never one per item


def test_a_sensitive_theme_has_no_name_and_its_items_fall_under_no_theme(r12):
    _Hm, _F, _L, T = mods()
    th = T.load(str(r12["lib"]))
    da = [r["id"] for r in R.rows() if r["theme"] == "da"]
    assert all(th.shown(th.theme_id(i)) is None for i in da)
    meta = json.dumps(th.meta)
    assert "Dating advice" not in meta and "dating" not in meta.lower().replace("relationships", "")
    s = sheet(r12, "how have my interests changed")
    assert "dating" not in json.dumps(s).lower()


def test_the_build_records_its_version_the_embedding_model_and_its_numbers(r12):
    _Hm, _F, _L, T = mods()
    meta = json.load(open(os.path.join(T.folder(str(r12["lib"])), "build.json")))
    assert meta["version"] == "themes-v2" and meta["prompt_version"] == "theme_name_v2"
    assert meta["embedding_store"] == "oai3l_1024" and meta["embedding_model"].startswith("text-embedding-3-large")
    assert meta["items_clustered"] > 700 and meta["wall_s"] >= 0 and "items_per_s" in meta


def test_an_item_added_later_gets_the_nearest_theme_by_code_and_a_new_version_is_not_read(r12, tmp_path):
    _Hm, _F, _L, T = mods()
    lib = r12["lib"]
    extra = [{"id": "rnew1", "platform": "youtube", "caption": "Watercolor clouds", "channel": "Wet Paper",
              "theme": "wc", "length": 600, "published": "2020-01-01", "events": [("watch", "2026-10-29T12:00:00+00:00")]}]
    R.write(lib, extra_rows=extra)
    th = T.load(str(lib))
    assert th.shown(th.theme_id("rnew1")) == "Watercolor painting"
    meta_path = os.path.join(T.folder(str(lib)), "build.json")
    meta = json.load(open(meta_path))
    meta["version"] = "themes-v0"
    json.dump(meta, open(meta_path, "w"))
    assert T.load(str(lib)) is None


@pytest.mark.parametrize("topic,expect", [
    ("gaming", {"Minecraft builds", "Speedruns", "Gaming clips"}), ("games", {"Minecraft builds", "Speedruns",
                                                                               "Gaming clips"}),
    ("art", {"Watercolor painting", "Digital drawing"}), ("drawing", {"Watercolor painting", "Digital drawing"}),
    ("math", {"Calculus lessons", "Number puzzles"}), ("minecraft", {"Minecraft builds"}),
    ("calculus", {"Calculus lessons"}), ("cooking", {"Home cooking"}), ("dating", set()), ("knitting", set())])
def test_a_topic_maps_to_themes_by_code(r12, topic, expect):
    Hm, _F, _L, T = mods()
    from mvp.libview import LibraryView
    v = LibraryView(str(r12["lib"]))
    rec = Hm.record(v, "America/New_York")
    th = T.load(v.lib)
    assert {th.shown(t) for t in T.for_topic(v, rec, topic, th)} == expect


# ================================================================ (3) the fact sheet of the brief's questions
def test_q1_lately_judges_by_items_length_themes_and_says_where_the_export_ends(r12):
    s = sheet(r12, "what have i been watching the most lately")
    a, b = date(2026, 10, 3), date(2026, 10, 30)
    ids = watched(a, b)
    assert s["kind"] == "top" and s["window"]["words"] == "the 4 weeks up to 30 October 2026, where your export ends"
    assert s["window"]["clipped"] is True and s["totals"]["items"] == len(ids)
    yt = [i for i in ids if row_of(i)["platform"] == "youtube"]
    secs = sum(row_of(i)["length"] or 0 for i in yt)
    assert s["totals"]["length_hours"] == round(secs / 3600, 1)
    assert s["totals"]["shorts"] == sum(1 for i in yt if is_clip(i))
    assert s["totals"]["long"] == sum(1 for i in yt if not is_clip(i) and row_of(i)["length"])
    assert s["previous"]["items"] == len(watched(a - timedelta(days=28), a - timedelta(days=1)))
    assert s["previous"]["words"] == "the 4 weeks before (5 September to 2 October 2026)"
    names = [t["name"] for t in s["themes"]]
    assert names[0] == "Gaming clips" and "Digital drawing" in names
    clips = next(t for t in s["themes"] if t["name"] == "Gaming clips")
    assert clips["items"] == len([i for i in ids if is_clip(i)]) and clips["shorts_share"] == 1.0
    assert clips["channels"][0]["name"] == "Clip Factory" and len(clips["examples"]) == 3
    assert "Gaming clips" in [t["name"] for t in s["new"]["themes"]]   # none in the 4 weeks before
    assert "without_shorts" in s["offers"] and "only_topic:Gaming clips" in s["offers"]
    w = s["when"]
    assert abs(w["weekday_share"] + w["weekend_share"] - 1) < 0.01 and len(w["busiest_hours"]) == 3


def test_q2_channels_in_a_year_with_the_year_before_and_the_without_shorts_offer(r12):
    s = sheet(r12, "which channels did i watch the most in 2025")
    ids = watched(date(2025, 1, 1), date(2025, 12, 31))
    assert s["kind"] == "channels" and s["totals"]["items"] == len(ids)
    assert s["previous"]["words"] == "2024" and s["previous"]["items"] == len(watched(date(2024, 1, 1),
                                                                                       date(2024, 12, 31)))
    top = s["channels"][0]
    assert top["name"] == "Wet Paper" and top["items"] == len(watched(date(2025, 1, 1), date(2025, 12, 31), {"wc"}))
    assert top["theme"] == "Watercolor painting" and top["first_watched"] == "2025-01-10" and top["new_in_window"]


def test_q2_without_shorts_leaves_the_shorts_out_and_says_how_many(r12):
    s = sheet(r12, "which channels did i watch the most this year without shorts")
    ids = watched(date(2026, 1, 1), date(2026, 10, 30))
    clips = {i for i in ids if is_clip(i)}
    ig = {i for i in ids if row_of(i)["platform"] == "instagram"}
    assert s["filters"]["without_shorts"] is True and s["filters"]["left_out"] == {"shorts": len(clips),
                                                                                  "reels": len(ig)}
    assert s["totals"]["shorts"] == 0 and s["totals"]["items"] == len(ids - clips - ig)
    assert "Clip Factory" not in [c["name"] for c in s["channels"]] and "without_shorts" not in s["offers"]


def test_q2_most_watched_channels_in_a_topic(r12):
    s = sheet(r12, "most watched channels in math")
    assert s["kind"] == "channels" and s["filters"]["topic"] == "math"
    assert set(s["filters"]["topic_themes"]) == {"Calculus lessons", "Number puzzles"}
    assert [c["name"] for c in s["channels"]] == ["Limit Lane", "Odd Prime"]
    assert s["totals"]["items"] == len(watched(None, None, MATH))


def test_q3_a_count_gives_more_than_was_asked(r12):
    s = sheet(r12, "how many minecraft videos did i watch this year")
    ids = watched(date(2026, 1, 1), date(2026, 10, 30), {"mc"})
    assert s["kind"] == "count" and s["topics"][0]["items"] == len(ids) == s["totals"]["items"]
    assert s["window_totals"]["items"] == len(watched(date(2026, 1, 1), date(2026, 10, 30)))
    assert s["previous"]["words"] == "the same part of 2025 (1 January to 30 October 2025)"
    assert s["topics"][0]["first_watched"] == "2021-01-05" and s["topics"][0]["themes"] == ["Minecraft builds"]


def test_q4_first_gives_the_items_the_year_by_year_and_what_is_saved_on_it(r12):
    s = sheet(r12, "when did i first start watching watercolor videos")
    assert s["kind"] == "first" and [x["at"] for x in s["items"]][:1] == ["2025-01-10"]
    assert all(x["theme"] == "Watercolor painting" for x in s["items"])
    assert [p["label"] for p in s["periods"]] == ["2025", "2026"]
    saved = s["library"]["saved_not_opened"]
    assert saved and saved[0]["theme"] == "Watercolor painting" and saved[0]["n"] == 3


def test_q5_more_gaming_or_more_art_this_year_compares_the_two_topics(r12):
    s = sheet(r12, "did i watch more gaming or more art videos this year")
    a, b = date(2026, 1, 1), date(2026, 10, 30)
    assert s["kind"] == "compare_topics" and [t["name"] for t in s["topics"]] == ["gaming", "art"]
    g, ar = s["topics"]
    assert g["items"] == len(watched(a, b, GAMING)) and ar["items"] == len(watched(a, b, ART))
    assert set(g["themes"]) == {"Minecraft builds", "Speedruns", "Gaming clips"}
    assert g["shorts"] == len([i for i in watched(a, b, GAMING) if is_clip(i)])
    assert ar["length_hours"] > g["length_hours"]   # fewer art videos, but longer ones


def test_q6_a_day_keeps_its_list_and_gains_the_overview(r12):
    s = sheet(r12, "what did i watch on october 30")
    d = date(2026, 10, 30)
    ids = watched(d, d)
    assert s["kind"] == "day" and s["window"]["words"] == "Friday 30 October 2026, the last day of your export"
    assert s["totals"]["items"] == len(ids) and {x["id"] for x in s["items"]} == ids
    assert s["totals"]["shorts"] == 1 and s["previous"]["words"] == "the day before (29 October 2026)"
    assert {t["name"] for t in s["themes"]} >= {"Digital drawing", "Gaming clips", "Home cooking"}
    assert s["new"] == {"themes": [], "channels": []}   # a day is too short to call anything new


def test_q7_how_what_i_watch_changed_gives_themes_per_year_and_what_rose_and_faded(r12):
    s = sheet(r12, "how has what i watch changed since 2020")
    assert s["kind"] == "changed" and [p["label"] for p in s["periods"]] == [str(y) for y in range(2021, 2027)]
    p21 = s["periods"][0]
    assert p21["items"] == len(watched(date(2021, 1, 1), date(2021, 12, 31)))
    assert p21["themes"][0]["name"] == "Minecraft builds"
    ch = s["change"]
    assert ch["from"] == "2021" and ch["to"] == "2026"
    assert {r["name"] for r in ch["rising"]} >= {"Digital drawing", "Gaming clips"}
    assert {r["name"] for r in ch["fading"]} >= {"Minecraft builds", "Speedruns"}
    mc = next(r for r in ch["fading"] if r["name"] == "Minecraft builds")
    assert mc["peak_period"] == "2021"


def test_q8_the_summer_of_2023_is_read_and_answered_with_its_themes(r12):
    s = sheet(r12, "what was i into in the summer of 2023")
    assert s["kind"] == "top" and s["window"]["words"] == "the summer of 2023 (1 June to 31 August 2023)"
    ids = watched(date(2023, 6, 1), date(2023, 8, 31))
    assert s["totals"]["items"] == len(ids)
    assert [t["name"] for t in s["themes"][:2]] == ["Calculus lessons", "Number puzzles"]
    assert s["previous"]["words"] == "the spring before (1 March to 31 May 2023)"


def test_the_sheet_is_fast_and_carries_its_versions(r12):
    t0 = time.monotonic()
    s = sheet(r12, "how has what i watch changed since 2020")
    assert time.monotonic() - t0 < 1.5
    assert s["versions"]["themes"] == "themes-v2" and s["versions"]["lengths"] == "lengths-v1"
    assert s["versions"]["themes_embedding"].startswith("text-embedding-3-large")


def test_with_no_themes_or_lengths_the_sheet_still_stands(env, tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_DERIVED_HOME", str(tmp_path / "nothing"))
    from mvp.tests import h_library
    lib = h_library.write(tmp_path / "hlib")
    Hm, F, _L, _T = mods()
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    q = Hm.read("what have i been watching the most lately", date(2026, 11, 19))
    s = F.build(env["bot"], {"handle": H, "library": str(lib), "timezone": "America/New_York"}, q,
                datetime(2026, 11, 19, 17, tzinfo=timezone.utc))
    # no lengths file: the corpus's own duration_s (600 seconds each here) is the length
    assert s["totals"]["items"] == 16 and s["themes"] == [] and s["totals"]["length_hours"] == 2.5
    assert s["channels"][0]["name"] == "Pixel Forge"


def test_a_person_with_no_library_gets_no_sheet(r12):
    _Hm, F, _L, _T = mods()
    Hm = mods()[0]
    q = Hm.read("what have i been watching the most lately", TODAY)
    assert F.build(r12["bot"], {"handle": H, "library": "/nowhere/at/all"}, q, r12["clock"][0]) is None


# ================================================================ (4) the reads
READS = [
    ("did i watch more gaming or more art videos this year", "compare_topics"),
    ("did i watch more gaming or art this year?", "compare_topics"),
    ("which did i watch more, gaming or art", "compare_topics"),
    ("have i watched more cooking than math videos", "compare_topics"),
    ("did i watch less gaming than art in 2025", "compare_topics"),
    ("how has what i watch changed since 2020", "changed"),
    ("how have my interests changed", "changed"),
    ("how has my taste changed over the years", "changed"),
    ("how have my youtube habits changed since 2022?", "changed"),
    ("how has what i've been watching changed", "changed"),
    ("what was i into in the summer of 2023", "top"),
    ("what was i into last summer", "top"),
    ("what was i watching back in 2021", "top"),
    ("what was i obsessed with in 2022", "top"),
    ("what was i into in spring 2024?", "top"),
    ("which channels did i watch the most in 2025 without shorts", "top_channels"),
    ("which channels did i watch the most in 2025, no shorts", "top_channels"),
    ("my top channels this year excluding shorts", "top_channels"),
    ("which channels did i watch most in 2025 only long videos", "top_channels"),
    ("most watched channels in math", "top_channels"),
    ("my most watched channels in gaming", "top_channels"),
    ("what did i watch on october 30", "on_day"),
    ("what have i been watching the most lately", "top_channels"),
]


@pytest.mark.parametrize("text,kind", READS)
def test_the_questions_that_were_misread_are_read_by_code(text, kind):
    from mvp import history as Hm
    q = Hm.read(text, TODAY)
    assert q is not None and q.kind == kind, (text, q)
    if "short" in text or "long videos" in text:
        assert q.without_shorts and not q.topic
    if "back in" in text:
        assert q.topic == [] and q.window.start == date(2021, 1, 1)
    if "summer of 2023" in text:
        assert (q.window.start, q.window.end, q.window.label) == (date(2023, 6, 1), date(2023, 8, 31),
                                                                  "the summer of 2023")
    if "last summer" in text:
        assert q.window.start == date(2026, 6, 1)
    if kind == "compare_topics":
        assert len(q.topic) == 2
    if kind == "changed":
        assert q.topic == []
    if "in math" in text:
        assert q.topic == ["math"]


TRAPS = [
    "should i watch more gaming or art", "send me gaming or art videos every day", "find me gaming or art videos",
    "recommend something, gaming or art", "i want to watch more art than gaming", "how do i change my interests",
    "my interests have changed, find me new stuff", "can you change what i watch", "how has blender changed since 2020",
    "what changed in the new update", "how has the weather changed", "i was into minecraft in 2021",
    "what was i thinking", "what am i doing tomorrow", "find me cooking videos without shorts",
    "recommend long videos only", "send me videos without shorts every morning", "no shorts please, find me a recipe",
    "remind me to watch more art", "add more gaming videos to my list", "what's the best channel in math",
    "what are the most watched channels in the world", "summarize what i learned about art",
    "what did that video say about gaming", "that video about art was too long", "thanks!",
    "what's the weather like in the summer", "is it better to watch art or gaming", "gaming or art?",
    "tell me a joke", "what can you do", "how have you changed", "what do you think of my taste",
    "delete my history from 2021", "follow that art channel for me", "remind me in the summer of 2027",
    "email me my top channels", "what should i watch tonight, art or gaming", "make me a playlist of art videos",
    "i watched way too much gaming lol", "what have i been into lately", "what am i into", "what was i into",
]


@pytest.mark.parametrize("text", TRAPS)
def test_the_traps_are_not_read_as_new_history_kinds(text):
    from mvp import history as Hm
    q = Hm.read(text, TODAY)
    assert q is None or q.kind not in ("compare_topics", "changed", "top") and not q.without_shorts, (text, q)


# ================================================================ (5) the follow-ups the offers name
def test_without_shorts_only_a_topic_show_the_videos_by_month_and_by_theme_follow_a_history_answer(r12):
    out, calls = ask(r12, "which channels did i watch the most this year")
    assert calls == [] and "Clip Factory" in out
    out, calls = ask(r12, "without shorts")
    assert calls == [] and "Clip Factory" not in out and "Pixel Pencil" in out
    out, calls = ask(r12, "only art")
    assert calls == [] and "Limit Lane" not in out
    out, calls = ask(r12, "by month")
    assert calls == [] and "Sep 2026" in out
    out, calls = ask(r12, "show the videos")
    assert calls == [] and "youtube.com/watch" in out


def test_by_theme_after_a_ranking_is_the_top_answer(r12):
    Hm = mods()[0]
    out, _ = ask(r12, "which channels did i watch the most in 2025")
    out, calls = ask(r12, "by theme")
    st = r12["bot"].store.get_state(Hm.STATE.format(h=H))
    assert calls == [] and st["q"]["kind"] == "top"


@pytest.mark.parametrize("text", ["just kidding", "only if you want", "no thanks", "ok thanks", "only the first one",
                                  "just checking", "only you", "by the way", "by tomorrow", "only 5", "just do it",
                                  "no shorts in my rules please, remind me tomorrow"])
def test_the_follow_up_traps_are_not_taken(text):
    from mvp import history as Hm
    q = Hm.HistoryQuery(kind="top_channels", window=Hm.Window(kind="year", start=date(2025, 1, 1),
                                                                end=date(2025, 12, 31)))
    assert Hm.follow_r12(q, Hm.normal(text), known=lambda x: True) is None


def test_without_shorts_after_an_ordinary_answer_is_not_a_history_follow_up(r12):
    from mvp import history as Hm
    st = r12["bot"].store.get_state(Hm.STATE.format(h=H))
    assert st is None
    q = Hm.read("without shorts", TODAY)
    assert q is None


# ================================================================ (6) today's code answers for the new kinds
def test_the_new_kinds_get_a_code_answer_with_no_model_call(r12):
    out, calls = ask(r12, "did i watch more gaming or more art videos this year")
    a, b = date(2026, 1, 1), date(2026, 10, 30)
    g, ar = len(watched(a, b, GAMING)), len(watched(a, b, ART))
    assert calls == []
    hi, lo = ("gaming", "art") if g > ar else ("art", "gaming")
    assert f'you watched more videos about "{hi}" than about "{lo}": {max(g, ar)} against {min(g, ar)}.' in out
    out, calls = ask(r12, "how has what i watch changed since 2020")
    assert calls == [] and "what you watch moved towards" in out and "2021: Minecraft builds" in out
    out, calls = ask(r12, "what was i into in the summer of 2023")
    assert calls == [] and out.startswith("In the summer of 2023 (1 June to 31 August 2023) you watched")


def test_a_thin_first_year_is_not_the_start_of_a_change(r12):
    """Three stray videos in 2019 would make "100% to 0%" of their theme: the change starts at the first year with
    enough items, and the thin years are named."""
    extra = [{"id": f"rold{k}", "platform": "youtube", "caption": f"Speedrun of old {k}", "channel": "Frame Perfect",
              "theme": "sr", "length": 600, "published": "2019-01-01",
              "events": [("watch", f"2019-0{k + 1}-10T12:00:00+00:00")]} for k in range(3)]
    R.write(r12["lib"], extra_rows=extra)
    s = sheet(r12, "how have my interests changed")
    assert s["periods"][0]["label"] == "2019" and s["periods"][0]["sparse"] is True
    assert s["change"]["from"] == "2021" and s["change"]["sparse_before"] == ["2019", "2020"]


def test_the_history_form_keeps_its_old_shape_for_the_old_kinds():
    from mvp import history as Hm
    q = Hm.read("what did i watch last week", TODAY)
    assert q.kind == "list" and q.without_shorts is False and q.window.label is None
