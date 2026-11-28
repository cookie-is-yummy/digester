"""Round 11, fix pass 2 (DESIGN.md section 18, part "18.L2"): the orchestrator's second live check of 25a1189 found P1
to P6; each is reproduced here on a made-up library, with near variants that must NOT be taken.

Offline: the fake model of test_mvp, the fake Gemini (tests/fakes/fake_gemini.py), a made-up watch history (a person
in New York; the clock Friday 20 November 2026; YouTube ends Thursday 12 November 2026, Instagram 3 November 2026) with
made-up item vectors beside it and made-up YouTube descriptions. Every title, channel, handle and id is invented."""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.fakes.fake_gemini import FakeGemini  # noqa: E402
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round11_fix_checks import WordPool, fake_extract, fake_synth  # noqa: E402
from mvp.tests.test_round11_h import ask  # noqa: E402
from mvp.tests.test_slice2 import H  # noqa: E402

UTC = timezone.utc
TODAY = date(2026, 11, 20)
CHAT = {"intent": "chat", "reply": "MODEL WAS CALLED"}
REFRESH = "For newer history, send me a new export"
GOOD = {"answered": True, "points": [{"at": "01:05", "says": "start with the bevel tool on the edges."},
                                     {"at": "03:10", "says": "set the segments to 3 for a rounder edge."}]}


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    """Never a live call from these tests: the fakes set a dummy key where one is needed."""
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY", "MVP_VIDEO_ASK", "MVP_VIDEO_ASK_MAX_MIN",
              "MVP_VIDEO_ASK_PER_DAY", "MVP_VIDEO_ASK_MODEL"):
        monkeypatch.delenv(k, raising=False)


# ================================ the made-up library ===============================================================
def _w(*ats):
    return [("watch", a + "T18:00:00+00:00") for a in ats]


def rows():
    """(id, platform, title or caption, channel or handle, relation, events, YouTube description, direction)."""
    out = []

    def yt(iid, title, ch, evs, desc=None, d=7):
        out.append((iid, "youtube", title, ch, "none", evs, desc, d))

    def ig(iid, cap, handle, evs, rel="none", d=7):
        out.append((iid, "instagram", cap, handle, rel, evs, None, d))
    # blender: two titled videos and, latest, one with no title of its own (only tags); two watched reels
    yt("b1", "Blender donut, part one", "Mesh Yard", _w("2026-09-01"), "Model the donut with a torus.", d=0)
    yt("b2", "Blender bevel modifier basics", "Mesh Yard", _w("2026-10-01"), "Bevel the edges, 3 segments.", d=0)
    yt("b3", "#blender #3d", "Mesh Yard", _w("2026-11-10"), d=0)
    ig("r1", "blender tip: bevel modifier in ten seconds", "meshyard.ig", _w("2026-10-30"), d=0)
    ig("r2", "blender shortcut reel: frame selected", "meshyard.ig", _w("2026-11-01"), d=0)
    # color grading: 4 watched videos about it, and 9 saved posts that hold the words but point elsewhere (P6)
    for k, (t, at) in enumerate([("Color grading skin tones in Resolve", "2026-03-14"),
                                 ("Color grading a night street", "2026-06-02"),
                                 ("Color grading with nodes, step by step", "2026-08-20"),
                                 ("Color grading for phone footage", "2026-10-05")]):
        yt(f"c{k}", t, "Lumen Lab", _w(at), "Lift the shadows before saturation.", d=1)
    for k in range(9):
        ig(f"s{k}", f"Color grading preset pack {k + 1}: link in bio", f"presetshop{k}",
           [("save", f"2026-0{1 + k % 9}-10T12:00:00+00:00")], d=2)
    # cooking: 7 watched videos about it, and one clip whose title says "cooked" as slang (P5c)
    for k, (t, at) in enumerate([("Cooking rice on the stove", "2026-10-02"), ("Cooking lentils for the week",
                                                                              "2026-10-06"),
                                 ("Cooking an omelette slowly", "2026-10-09"), ("Cooking ramen broth", "2026-10-13"),
                                 ("Cooking with cast iron", "2026-10-16"), ("Cooking chickpeas from dry", "2026-10-20"),
                                 ("Cooking a weeknight curry", "2026-10-23")]):
        yt(f"k{k}", t, "Pan Theory", _w(at), "Simmer it gently and season at the end. Salt the water well.", d=3)
    yt("kx", "Bro is cooked after leg day", "Gym Laughs", _w("2026-10-27"),
       "He is so cooked after this set. Leg day never ends.", d=6)
    # squash and stretch: watched reels only (P5a)
    ig("m1", "Squash and stretch reel\nSquash the ball on impact so it reads as soft.\nStretch it on the fall.",
       "bouncebox", _w("2026-10-25"), d=4)
    ig("m2", "Squash and stretch tip\nKeep the volume the same when you squash and stretch.\nExaggerate it at "
       "speed.", "bouncebox", _w("2026-10-26"), d=4)
    # a month apart for the comparisons
    yt("t1", "Trail run at dawn", "Trail Notes", _w("2026-09-05", "2026-09-06"), d=5)
    yt("t2", "Trail run in the rain", "Trail Notes", _w("2026-10-05"), d=5)
    ig("f1", "Cooking night at mine", "my.pal", _w("2026-10-10"), rel="mutual", d=3)   # a friend's: never counted
    ig("p3", "Trail sunrise reel", "trail.notes", _w("2026-11-03"), d=5)                # where Instagram ends
    yt("e1", "Synth arpeggios explained", "Tape Hiss", _w("2026-11-12"), d=5)         # where YouTube ends
    return out


def vid(iid):
    return "FAKE" + iid.upper().ljust(7, "x")[:7]


def url(iid):
    r = next(x for x in rows() if x[0] == iid)
    return f"https://www.youtube.com/watch?v={vid(iid)}" if r[1] == "youtube" else f"https://www.instagram.com/reel/C{iid}FAKEX/"


def write_library(path, vectors=True):
    import numpy as np
    (path / "corpus").mkdir(parents=True, exist_ok=True)
    rs = rows()
    with open(path / "corpus" / "items.jsonl", "w") as f, open(path / "corpus" / "interactions.jsonl", "w") as g:
        for iid, plat, cap, who, rel, evs, _, _ in rs:
            pd = {"owner_relation": rel}
            if plat == "youtube":
                pd.update(owner_name=who, video_id=vid(iid), owner_handle="", duration_s=480, media_kind="video")
            else:
                pd.update(owner_handle=who, media_kind="reel")
            f.write(json.dumps({"id": iid, "platform": plat, "source_url": url(iid), "caption": cap,
                                "interaction_kinds": sorted({k for k, _ in evs}), "platform_data": pd}) + "\n")
            for k, at in evs:
                g.write(json.dumps({"item_id": iid, "kind": k, "at": at}) + "\n")
    if vectors:
        rng = np.random.default_rng(11)
        ids, vecs = [], []
        for iid, *_, d in rs:
            v = rng.normal(0, 0.05, 8)
            v[d] += 1.0
            ids.append(iid)
            vecs.append(v)
        d = path / "corpus" / "emb" / "oai3l_1024"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ids.json").write_text(json.dumps(ids))
        np.save(d / "emb.npy", np.asarray(vecs, dtype=np.float16))
    return path


def fake_videos(ids, key, timeout=None):
    desc = {vid(r[0]): r[6] for r in rows() if r[1] == "youtube" and r[6]}
    return {"items": [{"id": v, "snippet": {"description": desc.get(v, ""), "publishedAt": "2026-01-02T00:00:00Z"},
                       "contentDetails": {"duration": "PT8M"}} for v in ids]}


@pytest.fixture()
def f2(env, tmp_path, monkeypatch):
    from mvp import ytinfo
    lib = write_library(tmp_path / "f2lib")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.views.clear()
    bot.pool = WordPool(str(lib))
    bot.max_per_minute = None
    monkeypatch.setenv("MVP_F2_TEST_KEY", "fake-key")
    bot.yt = ytinfo.YouTubeInfo(bot.store, fetch=fake_videos, key_env="MVP_F2_TEST_KEY")
    env["state"]["answers"]["mvp_profile_guess"] = lambda u: {"topics": []}
    env["state"]["answers"]["mvp_extract"] = fake_extract
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "intro": ""}
    env["state"]["answers"]["mvp_synth"] = fake_synth
    env["clock"][0] = datetime(2026, 11, 20, 17, 0, tzinfo=UTC)
    env["lib"] = lib
    return env


def role(monkeypatch, who):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", H if who == "operator" else "+15559999")


def on(monkeypatch, answer=GOOD):
    monkeypatch.setenv("MVP_VIDEO_ASK", "1")
    return FakeGemini(answer).install(monkeypatch)


def seen(e):
    e["bot"].store.set_state(f"videoask_seen:{H}", "2026-11-20T16:00:00+00:00")


def notes(e):
    got = []
    orig = e["bot"].note

    def note(**kw):
        if kw.get("intent"):
            got.append(kw["intent"])
        return orig(**kw)
    e["bot"].note = note
    return got


def last_run(e):
    r = e["bot"].store.q("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    if not r:
        return None
    r = dict(r[0])
    if r["kind"] == "history":
        return "history:" + str((json.loads(r.get("steps") or "{}").get("history") or {}).get("kind"))
    return r["kind"]


def step(e, text, form=CHAT):
    e["clock"][0] += timedelta(seconds=30)
    return ask(e, text, form)


# ================================ P1: a video's answer answers the question, or says it doesn't cover it ============
def test_p1_the_prompt_is_v2_and_says_what_a_point_is():
    from mvp import videoask as V
    assert V.PROMPT_VERSION == "video_ask_v2"
    p = V.prompt()
    assert "thing asked" in p and "does not answer a question about easing" in p
    assert "names, values, steps, settings" in p and "up to 5 points" in p
    assert V.prompt("video_ask_v1") != p   # v1 is kept as it was measured


@pytest.mark.parametrize("q,thing", [
    ("What does it say about easing in after effects?", "easing"),
    ("what does it say about the settings to use", "the settings to use"),
    ("how do i froth milk for a latte?", "how to froth milk for a latte"),
    ("how do you get the tire off my rim", "how to get the tire off your rim"),
    ("about masks", "masks"),
    ("what tool do they use first", None),
    ("which lens", None),
])
def test_p1_the_thing_asked_is_read_by_code(q, thing):
    from mvp import videoask as V
    assert V.asked_thing(q) == thing
    assert V.not_covered(q) == f"doesn't seem to cover {thing or 'that'}."


def test_p1_a_video_that_does_not_cover_it_says_so_naming_the_thing_and_shows_no_point(f2, monkeypatch):
    fake = on(monkeypatch, {"answered": False, "points": [{"at": "01:00", "says": "Set the feather to 20 px."}]})
    seen(f2)
    step(f2, "what was that video i watched about blender bevel")
    out, calls = step(f2, "ask the video what does it say about easing in after effects")
    assert calls == [] and len(fake.requests) == 1
    assert 'This video, "Blender bevel modifier basics", doesn\'t seem to cover easing.' in out
    assert "feather" not in out and "watch?v=FAKEB2xxxxx" in out
    assert "From the video (not checked" not in out


def test_p1_ask_them_a_video_that_does_not_cover_it_gets_one_plain_line(f2, monkeypatch):
    def answer(req):
        return GOOD if vid("b1") in FakeGemini.sent_url(req) else {"answered": False, "points": []}
    fake = on(monkeypatch, answer)
    seen(f2)
    f2["bot"].store.set_state(f"videomany_seen:{H}", "2026-11-20T16:00:00+00:00")
    step(f2, "what blender videos did i watch this year")
    out, _ = step(f2, "ask them what does it say about easing")
    assert len(fake.requests) == 2
    assert re.search(r'Video \d, "Blender bevel modifier basics": doesn\'t seem to cover easing\.', out), out
    assert "• Start with the bevel tool on the edges." in out


@pytest.mark.parametrize("says", [
    "The presenter introduces the tutorial on bevels.",
    "This video covers the bevel modifier.",
    "In this tutorial, the host goes over the basics of bevels.",
    "The video is sponsored by a render farm with a discount code.",
    "Leave a comment below with your render.",
    "Blender bevel modifier basics",        # its title said again
])
def test_p1_a_point_that_only_says_what_the_video_is_is_left_out(says):
    from mvp import videoask as V
    kept, dropped = V.check_points({"answered": True, "points": [{"at": "00:30", "says": says},
                                                                {"at": "01:00", "says": "Set segments to 3."}]},
                                   480, None, title="Blender bevel modifier basics")
    assert [x for _, x in kept] == ["Set segments to 3."] and dropped["about_video"] == 1


@pytest.mark.parametrize("says", [
    "The presenter sets the bevel width to 0.02 m.",
    "Press Ctrl+B to bevel the selected edges.",
    "The video shows the segments at 3 for a rounder edge.",
    "Bevel modifier: set the limit method to Angle.",
    "Add a bevel modifier, then set segments to 3.",
    "Easy Ease is F9.",
])
def test_p1_a_concrete_point_is_kept(says):
    from mvp import videoask as V
    kept, dropped = V.check_points({"answered": True, "points": [{"at": "00:30", "says": says}]}, 480, None,
                                   title="Blender bevel modifier basics")
    assert len(kept) == 1 and dropped["about_video"] == 0


def test_p1_only_points_about_the_video_say_it_does_not_cover_it(f2, monkeypatch):
    fake = on(monkeypatch, {"answered": True, "points": [{"at": "00:05", "says": "The presenter introduces the video."}]})
    seen(f2)
    step(f2, "what was that video i watched about blender bevel")
    out, _ = step(f2, "ask the video how do i bevel")
    assert len(fake.requests) == 1 and "doesn't seem to cover how to bevel." in out and "introduces" not in out


def test_p1_the_request_holds_the_link_and_the_question_only_and_the_ledger_names_v2(f2, monkeypatch):
    from mvp import videoask as V
    got = {}

    def call(mdl, request, est_tokens, person, version=None):
        got["req"] = request
        return GOOD, 0.004, ""
    monkeypatch.setenv("MVP_VIDEO_ASK", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-key")
    monkeypatch.setattr(V, "call_model", call)
    seen(f2)
    step(f2, "what was that video i watched about blender bevel")
    step(f2, "ask the video what segments does it use")
    parts = got["req"]["contents"][0]["parts"]
    assert parts[0]["file_data"]["file_uri"] == "https://www.youtube.com/watch?v=" + vid("b2")
    assert parts[1]["text"] == "Question: what segments does it use"
    assert "Blender bevel" not in json.dumps(got["req"])   # no title, channel or description
    assert got["req"]["system_instruction"]["parts"][0]["text"] == V.prompt("video_ask_v2")


def test_p1_the_email_of_a_video_that_does_not_cover_it_keeps_no_question(f2, monkeypatch):
    on(monkeypatch, {"answered": False, "points": []})
    seen(f2)
    step(f2, "what was that video i watched about blender bevel")
    step(f2, "ask the video what does it say about easing")
    va = f2["bot"].store.get_state(f"videoans:{H}")
    assert "easing" not in json.dumps(va)
    from mvp import videoask as V
    got = V.answer_in_view(f2["bot"], H)
    assert "doesn't seem to cover what you asked" in got["parts"][0]["text"]


# ================================ P2: never a video with no title; the question already typed is kept =============
def test_p2_the_offer_skips_a_video_with_no_title_and_keeps_the_question(f2, monkeypatch):
    fake = on(monkeypatch)
    seen(f2)
    out, _ = step(f2, "what was the last blender reel i watched")
    assert last_run(f2) == "history:last"
    out, calls = step(f2, "ask the video what tool do they use first")
    assert calls == [] and not fake.requests
    assert "A video from" not in out and "#blender" not in out
    assert 'You also watched a YouTube video on this: "Blender bevel modifier basics"' in out
    assert 'Say "ask that one" and I\'ll ask it: "what tool do they use first?"' in out
    out, calls = step(f2, "ask that one")
    assert calls == [] and len(fake.requests) == 1
    assert FakeGemini.sent_url(fake.requests[0]) == url("b2")
    assert FakeGemini.sent_text(fake.requests[0]) == "Question: what tool do they use first"


def test_p2_no_titled_video_left_gives_the_plain_line(f2, monkeypatch):
    from mvp import history, videoask as V
    on(monkeypatch)
    seen(f2)
    step(f2, "what was the last blender reel i watched")
    real = history.best_watched_video

    def only_untitled(bot, person, topic=None, item=None, latest=False, exclude=()):
        return None if "b3" in exclude else bot.view(person["library"]).get("b3")
    monkeypatch.setattr(history, "best_watched_video", only_untitled)
    out, _ = step(f2, "ask the video what tool do they use first")
    assert out.startswith(V.ALL_INSTAGRAM) or out.startswith(V.NOT_YOUTUBE)
    assert "You also watched" not in out and "A video from" not in out
    monkeypatch.setattr(history, "best_watched_video", real)


def test_p2_without_a_question_the_offer_asks_for_one():
    from mvp import videoask as V
    assert "and your question" in V.ALSO and not V.asks_something("") and not V.asks_something("lol")
    assert V.asks_something("what lens is it") and V.asks_something("is it any good?")


def test_p2_ask_them_skips_a_video_with_no_title(f2, monkeypatch):
    fake = on(monkeypatch)
    seen(f2)
    f2["bot"].store.set_state(f"videomany_seen:{H}", "2026-11-20T16:00:00+00:00")
    out, _ = step(f2, "what blender videos did i watch this year")
    out, _ = step(f2, "ask them what tool do they use")
    assert url("b3") not in [FakeGemini.sent_url(r) for r in fake.requests]
    assert {FakeGemini.sent_url(r) for r in fake.requests} == {url("b1"), url("b2")}


def test_p2_a_summary_never_offers_a_source_with_no_title():
    from mvp import synth

    class It:
        def __init__(self, i, plat, cap):
            self.id, self.platform, self.caption, self.first_line, self.creator = i, plat, cap, cap, "Mesh Yard"
            self.media, self.url, self.video_id = "video", "", vid(i)
    os.environ["MVP_VIDEO_ASK"] = "1"
    try:
        out = synth._video_offer([It("b1", "youtube", "Blender donut, part one"), It("b3", "youtube", "#blender #3d")])
    finally:
        del os.environ["MVP_VIDEO_ASK"]
    assert "video 1" in out and "video 2" not in out and "ask them" not in out


# ================================ P3: "ask the video" after a recall asks about its topic; "ask them" with nothing =
def test_p3_ask_the_video_after_a_recall_asks_about_the_recalls_topic_and_says_so(f2, monkeypatch):
    fake = on(monkeypatch)
    seen(f2)
    step(f2, "what was that video i watched about color grading")
    out, calls = step(f2, "ask the video")
    assert calls == [] and len(fake.requests) == 1
    assert out.startswith("I'll ask it about color grading.\n")
    assert FakeGemini.sent_text(fake.requests[0]) == "Question: What does it say about color grading?"


def test_p3_ask_them_after_a_recall_says_the_topic_too(f2, monkeypatch):
    fake = on(monkeypatch)
    seen(f2)
    f2["bot"].store.set_state(f"videomany_seen:{H}", "2026-11-20T16:00:00+00:00")
    step(f2, "what was that video i watched about color grading")
    out, _ = step(f2, "ask them")
    assert out.startswith("I'll ask them about color grading.") and len(fake.requests) >= 2
    assert all(FakeGemini.sent_text(r) == "Question: What does it say about color grading?" for r in fake.requests)


def test_p3_the_first_time_the_note_says_the_topic_and_yes_asks_it(f2, monkeypatch):
    fake = on(monkeypatch)
    step(f2, "what was that video i watched about color grading")
    out, _ = step(f2, "ask the video")
    assert out.startswith("I'll ask it about color grading. Before I ask:") and not fake.requests
    out, _ = step(f2, "yes")
    assert len(fake.requests) == 1 and "color grading" in FakeGemini.sent_text(fake.requests[0])


def test_p3_ask_the_video_after_a_pick_with_no_topic_still_asks_what_to_ask(f2, monkeypatch):
    from mvp import videoask as V
    fake = on(monkeypatch)
    seen(f2)
    f2["bot"].store.set_last_answer(H, None, None, ["b1"], "a blender video")
    out, _ = step(f2, "ask the video")
    assert out == V.ASK_WHAT and not fake.requests


@pytest.mark.parametrize("text", ["ask them", "ask those videos", "ask them what lens they use", "ask all 3",
                                  "ask the top 3 what they recommend"])
def test_p3_ask_them_with_nothing_shown_is_one_plain_line_by_code(f2, monkeypatch, text):
    from mvp import videoask as V
    fake = on(monkeypatch)
    out, calls = step(f2, text)
    assert calls == [] and not fake.requests and out == V.NOTHING_SHOWN


@pytest.mark.parametrize("who", ["tester", "operator"])
@pytest.mark.parametrize("text", ["ask them", "ask the video", "ask that one", "ask them what lens they use"])
def test_p3_with_the_setting_off_nothing_about_asking_videos_is_read(f2, monkeypatch, who, text):
    role(monkeypatch, who)
    step(f2, "what was that video i watched about color grading")
    got = notes(f2)
    out, calls = step(f2, text)
    assert "mvp_interpret" in calls and "video_ask" not in got


# near variants of P2 and P3 that are not "ask" reads at all
P3_TRAPS = ["ask them for a refund", "ask my mom what she thinks", "can you ask them to send it", "ask about my rules",
            "ask me later", "find me a video about blender bevel", "remind me to ask the video tomorrow",
            "that video was so good", "every friday send me a blender video", "lol ask them"]


@pytest.mark.parametrize("text", P3_TRAPS)
def test_p3_near_variants_are_not_asks(f2, monkeypatch, text):
    on(monkeypatch)
    got = notes(f2)
    step(f2, "what was that video i watched about color grading")
    out, calls = step(f2, text)
    assert got.count("video_ask") == 0, (text, got)


# ================================ P4: the shapes that still fell to the model, read by code =======================
P4_READ = [
    (["remind me what that video i watched about cooking rice was"], "history:recall"),
    (["can you remind me what that video i watched about ramen broth was"], "history:recall"),
    (["remind me what that reel i saw about squash and stretch was called"], "history:recall"),
    (["whens the first time i watched something about color grading"], "history:first"),
    (["when's the first time i watched cooking videos"], "history:first"),
    (["more videos in october or september?"], "history:compare"),
    (["more videos in october or september"], "history:compare"),
    (["fewer reels this month than last month"], "history:compare"),
    (["vi mas videos en octubre o en septiembre"], "history:compare"),
    (["vi mas videos en 2025 o en 2026"], "history:compare"),
    # round 12, fix (judge: the Spanish of the brief's 7 got the old run of counts): how WHAT is watched changed
    (["como ha cambiado lo que veo"], "history:changed"),
    (["como ha cambiado lo que veo de cocina con el tiempo"], "history:changed"),
    (["sum up what my watch history says about color grading"], "synth"),
    (["summarize what my saves say about color grading"], "synth"),
    (["what does my watch history say about cooking"], "synth"),
]


@pytest.mark.parametrize("who", ["tester", "operator"])
@pytest.mark.parametrize("msgs,want", P4_READ, ids=[f"p4_{k:02d}" for k in range(len(P4_READ))])
def test_p4_the_shapes_are_read_by_code(f2, monkeypatch, msgs, want, who):
    role(monkeypatch, who)
    got = notes(f2)
    out, calls = None, None
    for m in msgs:
        out, calls = step(f2, m)
    assert "mvp_interpret" not in calls, out
    if want == "synth":
        assert got[-1] == "synth", out
    else:
        assert last_run(f2) == want, out


def test_p4_the_remind_me_recall_answers_like_the_recall(f2):
    out, _ = step(f2, "remind me what that video i watched about cooking rice was")
    assert out.startswith("You watched this video about \"cooking rice\":") or "Cooking rice on the stove" in out
    assert "remind" not in out.lower() and "I'll" not in out


def test_p4_whens_never_becomes_the_topic(f2):
    out, _ = step(f2, "whens the first time i watched something about color grading")
    assert "when's" not in out and "whens" not in out and "14 March 2026" in out


def test_p4_the_bare_comparison_answers_first(f2):
    out, _ = step(f2, "more videos in october or september?")
    assert out.startswith("More in October 2026:"), out


def test_p4_the_spanish_comparison_and_timeline_answer_in_spanish(f2):
    out, _ = step(f2, "vi mas videos en octubre o en septiembre")
    assert out.startswith("Más en octubre de 2026") or out.startswith("Más en octubre"), out
    out, _ = step(f2, "como ha cambiado lo que veo de cocina con el tiempo")
    assert "cocina" in out and "como" not in out.split("\n")[0].lower().split("cocina")[0][-12:]


@pytest.mark.parametrize("first", ["ask the video what segments does it use", "ask them what tool do they use"])
@pytest.mark.parametrize("text", ["can you email me that", "email me that", "email me this please"])
def test_p4_email_me_that_after_a_video_answer_emails_the_answer(f2, monkeypatch, first, text):
    on(monkeypatch)
    seen(f2)
    f2["bot"].store.set_state(f"videomany_seen:{H}", "2026-11-20T16:00:00+00:00")
    step(f2, "what blender videos did i watch this year" if "them" in first else
         "what was that video i watched about blender bevel")
    step(f2, first)
    got = notes(f2)
    out, calls = step(f2, text)
    assert "mvp_interpret" not in calls and got and got[-1] == "act_on_last", (out, got)
    assert "email" in out.lower()


def test_p4_email_me_that_after_a_summary_is_read_by_code(f2, monkeypatch):
    step(f2, "summarize what ive learned about squash and stretch from what i watched")
    got = notes(f2)
    out, calls = step(f2, "can you email me that")
    assert "mvp_interpret" not in calls and got[-1] == "act_on_last", out


@pytest.mark.parametrize("text", ["can you email me that", "email me that"])
def test_p4_email_me_that_after_a_pick_stays_the_interpreters(f2, text):
    f2["bot"].store.set_last_answer(H, None, None, ["b1"], "a blender video")
    out, calls = step(f2, text)
    assert "mvp_interpret" in calls


P4_TRAPS = [
    "remind me to watch the ramen video tomorrow at 7", "remind me what that video i watched about ramen was tomorrow",
    "remind me what that video i watched about ramen was every friday", "remind me about the cooking video later",
    "remind me what that video was", "more videos like this", "more videos about cooking please",
    "more videos in this style or that one", "more cooking please", "less cooking please",
    "i watched more in 2024 than 2025", "vi un video de cocina", "como estas", "como hago pan",
    "sum up my day", "sum up what you did for me", "summarize what my rules say about email",
    "send me a cooking video every friday at 6pm", "find me a video about color grading", "ok thanks",
    "email me that tomorrow", "email my brother that", "that video was so good",
]


@pytest.mark.parametrize("text", P4_TRAPS)
def test_p4_near_variants_are_not_taken(text):
    from mvp import history, synth
    assert history.read_recall(text, TODAY) is None, text
    q = history.read(text, TODAY)
    assert q is None or q.kind not in ("compare", "timeline", "first"), (text, q)
    assert synth.read(text, TODAY) is None, text


@pytest.mark.parametrize("text", ["remind me to watch the ramen video tomorrow at 7", "more videos like this",
                                  "email me that tomorrow", "every friday send me a cooking video", "lol"])
def test_p4_near_variants_after_a_history_answer_reach_the_model(f2, text):
    step(f2, "what was that video i watched about cooking rice")
    got = notes(f2)
    out, calls = step(f2, text)
    assert "mvp_interpret" in calls, (text, out)
    assert not {"history", "synth", "video_ask", "act_on_last"} & set(got), (text, got)


# ================================ P5: wording ======================================================================
def test_p5a_a_watched_summary_of_reels_says_reels_in_the_lead_and_the_last_line(f2):
    out, _ = step(f2, "summarize what ive learned about squash and stretch from what i watched")
    assert out.startswith("Here's what the reels you watched say about squash and stretch:"), out
    assert "From 2 reels." in out and "posts" not in out and "the videos you watched" not in out


def test_p5a_the_words_for_videos_and_reels():
    from mvp import synth, texts

    class It:
        def __init__(self, plat, media="reel"):
            self.platform, self.media, self.kinds, self.dates = plat, media, ["watch"], {}
    yt, ig, photo = It("youtube", "video"), It("instagram"), It("instagram", "image")
    assert synth.lead_words("watched", [yt, yt]) == "the videos you watched"
    assert synth.lead_words("watched", [ig, photo]) == "the reels you watched"
    assert synth.lead_words("watched", [yt, ig]) == "the videos and reels you watched"
    assert synth.lead_words("any", [yt, ig]) == "the videos and reels you watched"
    assert synth.lead_words("saved", [ig]) == "the posts you saved"
    assert texts.synth_counts([ig, photo], reels=True) == "2 reels"
    assert texts.synth_counts([yt, ig], reels=True) == "1 video and 1 reel"
    assert texts.synth_counts([ig], reels=False) == "1 post"


def test_p5b_the_new_export_hint_once_in_6_hours_and_the_end_every_time(f2):
    outs = [step(f2, m)[0] for m in ("what did i watch last week", "how many videos did i watch this month",
                                     "what did i watch in november", "how many reels did i watch in november")]
    ends = "Your Instagram export ends on 3 November 2026 and your YouTube export on 12 November 2026"
    assert all(REFRESH not in o for o in outs), outs   # round 12, pass 2 (T6): no hint on an answer that has one
    assert all(ends.lower() in o.lower() or "instagram export ends on 3 november 2026" in o.lower()
               or "up to 3 november, where your instagram export ends" in o.lower() for o in outs), outs   # R-H
    out, _ = step(f2, "what did i watch this week")   # wholly after the record: round 12, W (R-H): the hint once
    # round 12, pass 2 (T6): the one history answer that says the hint (its whole window is after the record)
    assert out.startswith("I can't see this week") and REFRESH in out
    f2["clock"][0] += timedelta(hours=7)
    out, _ = step(f2, "what did i watch last week")
    assert REFRESH not in out


def test_p5b_a_summary_after_a_history_answer_leaves_the_hint_out_and_the_other_way(f2):
    out1, _ = step(f2, "what did i watch last week")
    out2, _ = step(f2, "summarize what i watched this month about blender")
    # round 12, pass 2 (T6): the history answer no longer says the hint; it is still noted, so the summary's reply
    # is as it was
    assert REFRESH not in out1 and REFRESH not in out2


def test_p5c_a_slang_form_of_the_topic_word_is_not_in_a_summary(f2):
    out, _ = step(f2, "summarize what i watched last month about cooking")
    assert "Bro is cooked" not in out and url("kx") not in out
    run = f2["bot"].store.q("SELECT steps FROM runs WHERE kind='synth' ORDER BY id DESC LIMIT 1")[0]
    assert json.loads(run["steps"]).get("other_form_unfit") == 1


def test_p5c_without_vectors_other_forms_count_as_before(env, tmp_path, monkeypatch):
    from mvp import ytinfo
    lib = write_library(tmp_path / "novec", vectors=False)
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.views.clear()
    bot.pool = WordPool(str(lib))
    bot.max_per_minute = None
    monkeypatch.setenv("MVP_F2_TEST_KEY", "fake-key")
    bot.yt = ytinfo.YouTubeInfo(bot.store, fetch=fake_videos, key_env="MVP_F2_TEST_KEY")
    env["state"]["answers"]["mvp_extract"] = fake_extract
    env["state"]["answers"]["mvp_synth"] = fake_synth
    env["clock"][0] = datetime(2026, 11, 20, 17, 0, tzinfo=UTC)
    out, _ = step(env, "summarize what i watched last month about cooking")
    run = bot.store.q("SELECT steps FROM runs WHERE kind='synth' ORDER BY id DESC LIMIT 1")[0]
    assert "other_form_unfit" not in json.loads(run["steps"])


def test_p5c_the_word_forms_of_the_history_answers():
    from mvp import history
    assert history.holds("Cooking rice", "cooking") and not history.holds("Bro is cooked", "cooking")


# ================================ P6: few watched items: all shown, "mention" =====================================
def test_p6_a_recall_with_few_watched_videos_shows_them_all_and_says_mention(f2):
    out, _ = step(f2, "what was that video i watched about color grading")
    assert out.startswith('You watched these that mention "color grading", best match first:'), out
    assert all(url(f"c{k}") in out for k in range(3)) and "Nothing you watched" not in out


def test_p6_a_first_answer_with_few_watched_videos_shows_them_all(f2):
    out, _ = step(f2, "when did i first watch color grading videos")
    assert out.startswith('The first video you watched that mentions "color grading" was on 14 March 2026:'), out
    assert "(4 in all.)" in out and "left them out" not in out


def test_p6_with_six_or_more_watched_the_fit_is_used_and_says_about(f2):
    out, _ = step(f2, "what was the last cooking video i watched")
    assert out.startswith('The last video you watched about "cooking" was on 23 October 2026:'), out
    out, _ = step(f2, "what was that video i watched about cooking")
    assert out.startswith('You watched these about "cooking", best match first:'), out


def test_p6_the_threshold_is_six():
    from mvp import history
    assert history.FIT_WATCHED_MIN == 6 == history.FIT_MIN
