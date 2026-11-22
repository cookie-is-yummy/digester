"""Round 11 fix, A (DESIGN.md section 18.LA): the history answers after the live check of 19 Nov (findings R1, R3 to
R7, and the history side of R2 and R8).

Offline: the fake model of test_mvp (a test fails when it is called where it must not be), the planted made-up watch
history of tests/h_library.py (Thursday 19 November 2026, New York) and, for R3, made-up item vectors written beside
it. Every title, channel and handle is invented. The near variants after each finding must NOT be taken."""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round11_h import ask, hist, NO_MODEL, REFRESH  # noqa: E402,F401  (hist is a fixture)
from mvp.tests.test_slice2 import H  # noqa: E402
from mvp.tests.test_slice6 import AllPool  # noqa: E402
from mvp.tests import h_library  # noqa: E402

TODAY = date(2026, 11, 19)
FRIENDS = "Posts from friends are not counted."
RANGE = "Your Instagram history here runs from"


def history():
    from mvp import history as Hm
    return Hm


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    """Never a live call from these tests: the fakes set a dummy key where one is needed."""
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


# ================================ R1: a recall is a recall, never a pick ===========================================
# 30 made-up recall messages, written before the code (each with what its answer must hold)
RECALLS = [
    ("what was that video i watched about color grading", "Color grading a night scene"),
    ("whats that video where they make lentil soup", "Weeknight cooking: lentil soup"),
    ("which video did i watch about soldering", "Soldering a tiny radio"),
    ("find the video i watched on knife skills last month", "Knife skills for cooking fast"),
    ("i watched something about fingerstyle a while ago, what was it", "Fingerstyle warmups"),
    ("that grade lab video about night scenes", "Color grading a night scene"),
    ("what was that reel i saw about latte art", "Latte art in slow motion"),
    ("what was that video i watched about blender lighting", "Blender lighting basics"),
    ("do you remember that video i watched about strumming patterns?", "Strumming patterns"),
    ("what's the name of that video i watched about sourdough", "Nothing you watched or saved fits \"sourdough\""),
    ("find that video where they explain a multimeter", "A beginner multimeter guide"),
    ("what was that clip i saw about bread", "Sunday bread bake"),
    ("which vid did i watch about barre chords", "Barre chords, week"),
    ("remember the video i saw on geometry nodes", "Blender geometry nodes intro"),
    ("can you find the video i watched about render settings", "Blender render settings explained"),
    ("what was that tutorial i watched on sculpting", "Blender sculpting for beginners"),
    ("yo what was that video i watched about cast iron", "Cooking with cast iron"),
    ("what was that video i watched in september about pasta sauce", "Cooking pasta sauce part"),
    ("what was that video with the one pot rice", "Cooking rice in one pot"),
    ("i saw a video about camera tricks the other day, can you find it", "Blender camera tricks"),
    ("what was that youtube video i watched about guitar cables", "Hum-free guitar cables"),
    ("whats that video i watched abt chord shapes", "Chord shapes lesson"),
    ("help me find the video i watched about donuts", "Blender donut, the easy way"),
    ("what was the video i watched about soldering a radio?", "Soldering a tiny radio"),
    ("what was that reel i watched about a cat", "Funny cat reel"),
    ("ok what was that video i saw about lentils", "Weeknight cooking: lentil soup"),
    ("where's that video i watched about eggs", "Cooking eggs three ways"),
    ("find the video i watched about matching two cameras", "Color grading: matching two cameras"),
    ("which video did i watch about knitting", "Nothing you watched or saved fits \"knitting\""),
    ("what was that kettle & cast video about bread", "Sunday bread bake"),
]
# 30 traps: ordinary picks, rules, reminders, feedback, acting, chat, history questions and video asks
RECALL_TRAPS = [
    "find me a video about color grading", "send me a video about color grading every friday",
    "what should i watch tonight", "that video was great", "that video about cooking was too long",
    "remind me to watch that video tomorrow", "add that video to my list", "what did that video say about lighting",
    "which videos did i watch last week", "how many videos about blender have i watched",
    "what was the last blender video i watched", "what was the first video i watched",
    "ask the video what tool they use", "is that video still on youtube", "can you find a reel about latte art",
    "summarize that video", "who made that video", "why did you send me that video",
    "what's a good video about soldering", "every time i watch a video about guitar remind me to practice",
    "what was that song in the video", "find the recipe from that video", "i watched a video about cooking yesterday",
    "what video should i watch about color grading", "email me that video i watched about color grading",
    "the video i watched about bread was so good", "show me videos about knife skills",
    "what was that video you sent me about pasta", "delete that video i watched about soldering",
    "what's that video called", "what was that video about spreadsheet shortcuts",
]


@pytest.mark.parametrize("text,want", RECALLS)
def test_r1_thirty_recalls_are_answered_by_code_from_what_was_watched(hist, text, want):
    out, calls = ask(hist, text)
    assert calls == [], (text, out)
    assert want in out, (text, out)
    assert "recommend" not in out.lower() and "because" not in out.lower()


@pytest.mark.parametrize("text", RECALL_TRAPS)
def test_r1_thirty_traps_are_never_read_as_a_recall(text):
    assert history().read_recall(text, TODAY) is None, text


def test_r1_the_founders_case_gives_the_watched_videos_best_first_with_dates_and_cards(hist):
    out, calls = ask(hist, "what was that video i watched about color grading")
    assert calls == []
    assert out.startswith("You watched these that mention \"color grading\", best match first:\n"
                          "1. Color grading a night scene by Grade Lab. You watched it on 8 October 2026.\n"
                          "https://www.youtube.com/watch?v=vy013\n"
                          "2. Color grading: matching two cameras by Grade Lab. You watched it on 30 October 2026.\n"
                          "https://www.youtube.com/watch?v=vy014")
    st = hist["bot"].store
    kept = st.answer(st.last_answer(H)["run_id"])["parts"]
    assert [p["type"] for p in kept] == ["text", "text", "link", "text", "link"]   # each with its card
    # the first is the pick in view; "the second one" still reads the recall's own list
    assert st.last_answer(H)["items"] == ["y013"]
    out, calls = ask(hist, "the second one")
    assert calls == [] and "Color grading: matching two cameras" in out
    assert st.last_answer(H)["items"] == ["y014"]


def test_r1_youtube_comes_first_and_a_watched_reel_only_when_asked_or_nothing_on_youtube_fits(hist):
    # "blender speed sculpt" is a watched Instagram reel; "sculpting" a YouTube video: the video comes first
    out, _ = ask(hist, "what was that video i watched about sculpt")
    assert "Blender sculpting for beginners" in out and "speed sculpt reel" not in out
    out, _ = ask(hist, "what was that reel i watched about sculpt")
    assert out.startswith("You watched this reel that mentions \"sculpt\":\nBlender speed sculpt reel by @pixelforge.ig.")
    # a paper plane is only a watched reel: said so, then the reel
    out, _ = ask(hist, "what was that video i watched about paper planes")
    assert out.startswith("No YouTube video you watched fits \"paper planes\". You watched this reel that mentions")
    assert "Paper plane fold" in out


def test_r1_nothing_watched_fits_says_so_and_offers_the_saved_one(hist):
    out, calls = ask(hist, "what was that video i watched about desk setup")
    assert calls == []
    assert out.startswith("Nothing you watched fits \"desk setup\". You saved one about it: Studio desk setup by "
                          "@deskdaily (saved on 15 October 2026).")
    assert "https://www.instagram.com/reel/C" in out
    # a friend's post is never offered (it is not in the view)
    out, _ = ask(hist, "what was that video i watched about a blender cooking party")
    assert "party at mine" not in out


def test_r1_a_window_and_a_channel_narrow_it_and_a_window_past_the_export_says_where_it_ends(hist):
    out, _ = ask(hist, "find the video i watched about pasta sauce in september")
    assert "Cooking pasta sauce part" in out and "in September 2026" in out
    out, _ = ask(hist, "find the video i watched about pasta sauce in october")
    assert out.startswith("Nothing you watched in October 2026 or saved fits \"pasta sauce\".")
    assert "your YouTube export on 30 October 2026, so I can't see after that." in out
    out, _ = ask(hist, "that chord garden video about chords")
    assert "from Chord Garden" in out and "Kettle" not in out
    # a "channel" the library doesn't have is not a recall: the interpreter reads it
    out, calls = ask(hist, "that pretend studio video about chords", NO_MODEL)
    assert calls == ["mvp_interpret"]


def test_r1_the_engines_ranking_orders_the_videos_that_hold_the_words(hist):
    class Ranked(AllPool):
        def search(self, lib, q, depth=300):
            self.queries.append(q)
            ids = list(self.ids)
            ids.remove("y014")
            return {"ids": ["y014"] + ids, "mode": "normal", "cost_usd": 0.0}
    hist["bot"].pool = Ranked(str(hist["lib"]))
    out, _ = ask(hist, "what was that video i watched about color grading")
    assert out.index("matching two cameras") < out.index("a night scene")
    assert hist["bot"].pool.queries == ["color grading"]


def test_r1_over_the_cap_the_engine_is_not_asked_and_the_words_still_answer(hist, monkeypatch):
    bot = hist["bot"]
    monkeypatch.setattr(type(bot), "_over_cap", lambda self, person: "daily")
    out, calls = ask(hist, "what was that video i watched about soldering")
    assert calls == [] and "Soldering a tiny radio" in out and bot.pool.queries == []


def test_r1_the_first_is_in_view_for_a_question_and_for_ask_the_video(hist, tmp_path, monkeypatch):
    # two made-up videos with 11-letter video ids (the ones "ask the video" can send)
    lib = h_library.write(tmp_path / "asklib", extra_rows=[
        {"id": "ygradeaaa1", "platform": "youtube", "caption": "Grading log footage on a cheap monitor",
         "channel": "Pretend Grade Lab", "events": [("watch", "2026-10-20T15:00:00+00:00")]},
        {"id": "ygradeaaa2", "platform": "youtube", "caption": "A cheap monitor for grading, one year later",
         "channel": "Pretend Grade Lab", "events": [("watch", "2026-10-21T15:00:00+00:00")]}])
    hist["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    hist["bot"].views.clear()
    hist["bot"].pool = AllPool(str(lib))
    monkeypatch.setenv("MVP_VIDEO_ASK", "1")
    out, _ = ask(hist, "what was that video i watched about grading on a cheap monitor")
    assert out.startswith("You watched these that mention \"grading cheap monitor\", best match first:\n1. Grading log "
                          "footage on a cheap monitor")
    hist["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "intro": ""}
    out, calls = ask(hist, "what did that video say about the settings to use", {
        "intent": "follow_up", "pick_number": None, "question": "What did that video say about the settings to use?"})
    assert "Grading log footage on a cheap monitor" in out and "one year later" not in out
    assert 'say "ask the video"' in out
    from mvp.tests.fakes.fake_gemini import FakeGemini
    fake = FakeGemini({"answered": True, "points": [{"at": "01:05", "says": "Shoot flat and grade by hand."}]})
    fake.install(monkeypatch)   # never the network
    out, calls = ask(hist, "ask the video")
    assert calls == [] and out.startswith("From the video (not checked against its text)")
    assert FakeGemini.sent_url(fake.requests[0]) == "https://www.youtube.com/watch?v=vygradeaaa1"


def test_r1_a_recall_is_kept_as_an_answer_so_email_it_to_me_and_reactions_work(hist):
    ask(hist, "what was that video i watched about soldering")
    st = hist["bot"].store
    last = st.last_answer(H)
    snap = st.answer(last["run_id"])
    assert snap["picks"][0]["item_id"] == "y015" and last["goal"] == "history: recall"
    run = st.one("SELECT kind, steps FROM runs WHERE id=?", (last["run_id"],))
    steps = json.loads(run["steps"])["history"]
    assert run["kind"] == "history" and steps["kind"] == "recall"
    assert "soldering" not in run["steps"]   # the run keeps the form's shape, never the words


def test_r1_near_variants_stay_where_they_were(hist):
    hist["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "intro": ""}
    for text, form in [
            ("find me a video about color grading", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
                "goal": "a video about color grading", "searches": ["color grading"], "count": 1}}}),
            ("send me a video about color grading every friday", NO_MODEL),
            ("that video was great", NO_MODEL),
            ("what should i watch tonight", NO_MODEL),
            ("ok thanks", NO_MODEL)]:
        out, calls = ask(hist, text, form)
        assert calls[:1] == ["mvp_interpret"], (text, out)
        assert "You watched these" not in out and "You watched this" not in out
    # history questions stay history answers
    out, calls = ask(hist, "what was the last blender video i watched")
    assert calls == [] and out.startswith("The last video you watched that mentions \"blender\"")
    out, calls = ask(hist, "which videos did i watch last week")
    assert calls == [] and out.startswith("I can't see the week of")


# ================================ R2, R8: the best-fitting YouTube video watched ===================================
def _person(e):
    return e["bot"].store.person(H)


def test_r2_best_watched_video_for_a_topic_or_for_an_instagram_post_in_view(hist):
    Hm = history()
    bot = hist["bot"]
    p = _person(hist)
    assert Hm.best_watched_video(bot, p, topic="color grading").id in ("y013", "y014")
    assert Hm.best_watched_video(bot, p, topic="color grading", latest=True).id == "y014"
    assert Hm.best_watched_video(bot, p, topic="latte art") is None          # only a liked reel
    assert Hm.best_watched_video(bot, p, topic="knitting") is None
    view = bot.view(p["library"])
    post = next(it for it in view.items.values() if it.caption == "Blender shortcut cheat sheet")
    got = Hm.best_watched_video(bot, p, item=post)
    assert got is not None and got.platform == "youtube" and "Blender" in got.caption
    cat = next(it for it in view.items.values() if it.caption == "Funny cat reel")
    assert Hm.best_watched_video(bot, p, item=cat) is None
    # never a friend's post, never an Instagram item, never the item itself
    assert Hm.best_watched_video(bot, p, topic="party") is None


def test_r8_the_latest_blender_video_after_a_history_answer_of_reels(hist):
    Hm = history()
    ask(hist, "what was the last blender video i watched")
    bot = hist["bot"]
    now = hist["clock"][0]
    assert Hm.history_topic(bot, H, now) == "blender"
    got = Hm.best_watched_video(bot, _person(hist), topic=Hm.history_topic(bot, H, now), latest=True)
    assert got.id == "y005"   # "Blender camera tricks", 30 October: the latest YouTube one
    hist["clock"][0] = now + timedelta(hours=7)
    assert Hm.history_topic(bot, H, hist["clock"][0]) is None


# ================================ R3: the topic's items fit it by the library's own vectors ========================
def _write_vectors(lib, talk_id):
    """Made-up 8-dimension vectors: every item whose title says "cooking" points one way, except the talk-show clip,
    which points another way; everything else is spread out."""
    import numpy as np
    rows = [json.loads(x) for x in open(lib / "corpus" / "items.jsonl")]
    rng = np.random.default_rng(7)
    ids, vecs = [], []
    for r in rows:
        v = rng.normal(0, 0.05, 8)
        if r["id"] == talk_id:
            v[1] += 1.0
        elif "cook" in r["caption"].lower():
            v[0] += 1.0
        else:
            v[2 + (len(r["id"]) % 5)] += 1.0
        ids.append(r["id"])
        vecs.append(v)
    d = lib / "corpus" / "emb" / "oai3l_1024"
    d.mkdir(parents=True)
    (d / "ids.json").write_text(json.dumps(ids))
    np.save(d / "emb.npy", np.asarray(vecs, dtype=np.float16))


TALK = {"id": "y_talk", "platform": "youtube", "caption": "Late night chat: the host's cooking disaster",
        "channel": "Pretend Late Show", "events": [("watch", "2024-01-20T03:00:00+00:00")]}


@pytest.fixture()
def fitlib(hist, tmp_path):
    lib = h_library.write(tmp_path / "fitlib", extra_rows=[TALK])
    _write_vectors(lib, "y_talk")
    bot = hist["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.views.clear()
    bot.pool = AllPool(str(lib))
    return hist


def test_r3_without_vectors_the_talk_show_clip_comes_first(hist, tmp_path):
    lib = h_library.write(tmp_path / "plain", extra_rows=[TALK])
    hist["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    hist["bot"].views.clear()
    out, _ = ask(hist, "when did i first start watching cooking videos")
    assert out.startswith("The first video you watched that mentions \"cooking\" was on 19 January 2024:\n"
                          "1. Late night chat: the host's cooking disaster")


def test_r3_with_the_librarys_vectors_the_items_shown_fit_the_topic_and_say_about(fitlib):
    out, calls = ask(fitlib, "when did i first start watching cooking videos")
    assert calls == []
    assert out.startswith("The first video you watched about \"cooking\" was on 10 February 2024:\n"
                          "1. Cooking rice the easy way by Kettle & Cast (10 Feb 2024)")
    assert "Late night chat" not in out
    assert "in all. 1 more mentions \"cooking\" but doesn't seem to be about it, so I left it out.)" in out
    # the count stays a word count, said "mention"
    out, _ = ask(fitlib, "how many cooking videos have i watched")
    assert "15 videos that mention \"cooking\"" in out
    # a list and a last answer fit too
    out, _ = ask(fitlib, "what cooking videos did i watch in january 2024")
    assert "Late night chat" not in out and "about \"cooking\"" in out
    out, _ = ask(fitlib, "what was the last cooking video i watched")
    assert out.startswith("The last video you watched about \"cooking\"")


def test_r3_a_topic_with_few_matches_or_a_channel_keeps_the_word_match(fitlib):
    out, _ = ask(fitlib, "when did i first watch videos about soldering")   # one match: the fit can't tell
    assert "that mentions \"soldering\"" in out
    out, _ = ask(fitlib, "when did i start watching kettle & cast")
    assert out.startswith("The first video you watched from Kettle & Cast")


def test_r3_the_fit_reads_the_int8_store_of_a_demo_library_too(hist, tmp_path):
    import numpy as np
    lib = h_library.write(tmp_path / "q8lib", extra_rows=[TALK])
    _write_vectors(lib, "y_talk")
    d = lib / "corpus" / "emb"
    v = np.load(d / "oai3l_1024" / "emb.npy").astype(np.float32)
    s = np.abs(v).max(0) / 127 + 1e-9
    (d / "oai3l_1024_q8").mkdir()
    (d / "oai3l_1024_q8" / "ids.json").write_text((d / "oai3l_1024" / "ids.json").read_text())
    np.save(d / "oai3l_1024_q8" / "q8.npy", np.round(v / s).astype(np.int8))
    np.save(d / "oai3l_1024_q8" / "scale.npy", s.astype(np.float32))
    import shutil
    shutil.rmtree(d / "oai3l_1024")
    hist["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    hist["bot"].views.clear()
    out, _ = ask(hist, "when did i first start watching cooking videos")
    assert "about \"cooking\"" in out and "Late night chat" not in out


def test_r3_holds_gives_the_same_answer_as_contains_word():
    from mvp.retrieve import contains_word
    Hm = history()
    texts = ["Strawberries and cream", "Tomatoes three ways", "Cheesy bread", "Peanut butter", "Ten minutes",
             "Boil an egg", "#blender_tutorial", "Blender3D", "Icecream at home", "Dishes done", "Ｂｌｅｎｄｅｒ tips",
             "Color grading: two cameras", "Speedrunning", "Creamy pasta", "After Effects"]
    words = ["berry", "berries", "tomato", "cheese", "nut", "minute", "oil", "egg", "blender", "cream", "dish",
             "color grading", "running", "after effects", "ice cream"]
    for t in texts:
        for w in words:
            assert Hm.holds(t, w) == contains_word(t, w), (t, w)


def test_r3_after_effects_is_one_topic():
    q = history().read("when did i first start watching after effects videos", TODAY)
    assert q.topic == ["after effects"]


# ================================ R4: the friends line and the range, once in a stretch ============================
def test_r4_the_friends_line_and_the_range_are_said_once_in_six_hours(hist):
    out, _ = ask(hist, "which channels do i watch the most")
    # round 12, W (R-H): the friends line only when asked about friends; no hint on an all-time answer
    assert FRIENDS not in out and RANGE in out and REFRESH not in out
    out, _ = ask(hist, "how many videos about blender have i watched")
    assert FRIENDS not in out and RANGE not in out and REFRESH not in out
    out, _ = ask(hist, "how many videos did i watch in 2025")
    assert FRIENDS not in out
    # a window that reaches the export's end always says so
    out, _ = ask(hist, "how many videos did i watch in october")
    # round 11 fix pass 2 (P5b): the end always, the hint on a new export once in 6 hours (it came with the range)
    # round 12, W (R-H): the end in the window's words; the hint here, the first answer about after the export
    assert "where your YouTube export ends" in out and REFRESH in out
    out, _ = ask(hist, "what did i watch last week")
    assert out.startswith("I can't see the week of 9 to 15 November 2026:")
    # an all-time "last" still says where the record ends (it changes the answer)
    out, _ = ask(hist, "what was the last cooking video i watched")
    assert "your YouTube export on 30 October 2026, so I can't see after that." in out and RANGE not in out
    # after six hours, once again
    hist["clock"][0] = hist["clock"][0] + timedelta(hours=6, minutes=1)
    out, _ = ask(hist, "which channels do i watch the most")
    assert FRIENDS not in out and RANGE in out


def test_r4_spanish_too(hist):
    out, _ = ask(hist, "cuantos videos vi en 2025")
    assert "No cuento las publicaciones de tus amigos." not in out   # round 12, W (R-H): only when asked
    out, _ = ask(hist, "cuantos videos vi en 2024")
    assert "No cuento las publicaciones de tus amigos." not in out


def test_r4_the_notes_are_the_persons_state_and_go_with_delete_my_data(hist):
    ask(hist, "which channels do i watch the most")
    st = hist["bot"].store
    assert set(st.get_state(f"histnotes:{H}")) == {"range"}   # round 12, W (R-H): no friends line, no hint here
    st.delete_all(H) if hasattr(st, "delete_all") else None
    if hasattr(st, "delete_all"):
        assert st.get_state(f"histnotes:{H}") is None


# ================================ R5: "more in X or Y" answers first =============================================
@pytest.mark.parametrize("text,head", [
    ("did i watch more in 2024 or 2025", "More in 2025: 11 videos, against 6 in 2024 (5 more)."),
    ("did i watch more in 2025 or 2024", "More in 2025: 11 videos, against 6 in 2024 (5 more)."),
    ("did i watch less in 2025 or 2024", "Fewer in 2024: 6 videos, against 11 in 2025 (5 fewer)."),
    ("did i watch more cooking in 2025 or 2024",
     "More in 2025: 6 videos that mention \"cooking\", against 3 in 2024 (3 more)."),
    ("did i watch more in october or september",
     "More in October 2026 (up to 30 October, where your YouTube export ends; your Instagram export ends on 15 "
     "October 2026): 17 videos, against 10 in September 2026 (7 more)."),   # round 12, W (R-H)
    ("vi mas videos en 2024 o 2025?", "Más en 2025: 11 videos, frente a 6 en 2024 (5 más)."),
    ("cuantos videos vi en 2024 comparado con 2025", "Más en 2025: 11 videos, frente a 6 en 2024 (5 más)."),
])
def test_r5_the_comparison_leads_with_the_answer(hist, text, head):
    out, calls = ask(hist, text)
    assert calls == [] and out.startswith(head), out


def test_r5_the_same_count_says_the_same(hist):
    out, _ = ask(hist, "did i watch more in march 2025 or july 2025")
    assert out.startswith("In March 2025 you watched 2 videos, and in July 2025, 2: the same.")


# ================================ R6: the timeline starts where the counts do =====================================
def test_r6_no_leading_zero_years(hist, tmp_path):
    # a video watched in 2019 starts the record years before the first video about pottery
    lib = h_library.write(tmp_path / "early", extra_rows=[
        {"id": "y_old", "platform": "youtube", "caption": "An old unboxing", "channel": "Loose Wires",
         "events": [("watch", "2019-06-01T12:00:00+00:00")]},
        {"id": "y_pot1", "platform": "youtube", "caption": "Pottery wheel basics", "channel": "Clay Days",
         "events": [("watch", "2023-03-01T12:00:00+00:00")]},
        {"id": "y_pot2", "platform": "youtube", "caption": "Pottery glazes", "channel": "Clay Days",
         "events": [("watch", "2025-05-01T12:00:00+00:00")]}])
    hist["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    hist["bot"].views.clear()
    out, calls = ask(hist, "how has my pottery watching changed over the years")
    assert calls == []
    assert out.startswith("Videos you watched that mention \"pottery\", by year:\n2023: 1, 2024: 0, 2025: 1, 2026: 0 "
                          "(up to 30 Oct 2026). None before 2023.")
    assert "2019: 0" not in out and "2020: 0" not in out
    # all of it, by year: starts at 2019, where the first watch is (no "none before")
    out, _ = ask(hist, "how many videos did i watch each year")
    assert out.startswith("Videos you watched, by year:\n2019: 1, 2020: 0,") and "None before" not in out


# ================================ R7: accounts and channels =======================================================
def test_r7_accounts_and_channels_when_instagram_is_in_the_count(hist):
    out, _ = ask(hist, "which channels do i watch the most")
    assert "(7 accounts and channels in all.)" in out
    out, _ = ask(hist, "which youtube channels do i watch the most")
    assert "(5 channels in all.)" not in out or "accounts" not in out
    out, _ = ask(hist, "how many accounts did i like on instagram")
    assert "you liked posts from 3 accounts." in out
    out, _ = ask(hist, "how many channels have i watched")
    assert "from 7 accounts and channels." in out
    out, _ = ask(hist, "how many youtube channels have i watched")
    assert "from 5 channels." in out


def test_r7_the_word_by_platform():
    Hm = history()

    class It:
        def __init__(self, p):
            self.platform, self.creator = p, "x"

    class V:
        items = {"a": It("youtube"), "b": It("instagram")}
    assert Hm.who_word(V, ["a"], 3) == "channels" and Hm.who_word(V, ["b"], 3) == "accounts"
    assert Hm.who_word(V, ["a", "b"], 3) == "accounts and channels" and Hm.who_word(V, ["b"], 1) == "account"
    assert Hm.who_word(V, ["a", "b"], 3, "es") == "cuentas y canales"


# ================================ the guards: the rule texts and the phrasings ====================================
def test_no_rule_text_or_rule_phrasing_is_read_as_a_recall(env):
    """The 159 rule-eval texts and the 123 rule phrasings (the bot's own run of them through hook 8h, recall inside,
    is test_round11_h.py's test_no_rule_text_or_rule_phrasing_is_taken_by_slice_h)."""
    from mvp.tests.test_round9_merge import eval_texts, rule_phrasings
    Hm = history()
    texts, phr = eval_texts(), rule_phrasings()
    assert len(texts) == 159 and len(phr) == 123
    assert [t for t in texts + phr if Hm.read_recall(t, TODAY) is not None] == []
