"""The merge of round 11 (DESIGN.md section 18): where slices H (history questions), M (summaries across many items)
and Q (asking a YouTube video itself, MVP_VIDEO_ASK=1) meet, and the framing ("ask your watch history anything" leads
the help, "what can you do" and the setup's suggestions).

Offline: the fake model of test_mvp, the fake Gemini, made-up libraries only (invented titles, channels, video ids)."""
import json
import os
import re
import sys
from datetime import date, datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.fakes.fake_gemini import FakeGemini  # noqa: E402
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round11_h import ask, hist  # noqa: E402,F401  (hist is a fixture)
from mvp.tests.test_slice2 import H  # noqa: E402
from mvp.tests.test_slice6 import AllPool  # noqa: E402

TODAY = date(2026, 11, 19)
UTC = timezone.utc
CHAT = {"intent": "chat", "reply": "MODEL WAS CALLED"}
GOOD = {"answered": True, "points": [{"at": "01:05", "says": "Set the white balance by hand before you start."},
                                     {"at": "03:10", "says": "Keep the shutter at twice the frame rate."}]}
# (id, platform, an 11-letter made-up video id, title, channel or handle, the day it was watched or saved)
LIB = [("v1", "youtube", "FAKEvidAAA1", "Lens filters for night video, made simple", "Pretend Lens Co",
        "2026-10-02T15:00:00+00:00"),
       ("v2", "youtube", "FAKEvidAAA2", "Lens filters for bright daylight video", "Pretend Lens Co",
        "2026-10-02T18:00:00+00:00"),
       ("v3", "youtube", "FAKEvidAAA3", "A slow walk in an invented forest", "Made Up Trails",
        "2026-10-09T18:00:00+00:00"),
       ("p1", "instagram", None, "Lens filters cheat sheet for phone video", "notarealshooter",
        "2026-10-05T12:00:00+00:00")]


def write_library(path):
    (path / "corpus").mkdir(parents=True)
    with open(path / "corpus" / "items.jsonl", "w") as f, open(path / "corpus" / "interactions.jsonl", "w") as g:
        for iid, plat, vid, title, who, at in LIB:
            kind = "watch" if plat == "youtube" else "save"
            pd = {"owner_relation": "none"}
            if plat == "youtube":
                pd.update(owner_name=who, video_id=vid, duration_s=420, media_kind="video")
                url = f"https://www.youtube.com/watch?v={vid}"
            else:
                pd.update(owner_handle=who, media_kind="reel")
                url = f"https://www.instagram.com/reel/C{iid}FAKE/"
            f.write(json.dumps({"id": iid, "platform": plat, "source_url": url, "caption": title,
                                "interaction_kinds": [kind], "platform_data": pd}) + "\n")
            g.write(json.dumps({"item_id": iid, "kind": kind, "at": at}) + "\n")
    return path


@pytest.fixture()
def lib(env, tmp_path, monkeypatch):
    path = write_library(tmp_path / "mlib")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(path), H))
    bot.views.clear()
    bot.pool = AllPool(str(path))
    bot.max_per_minute = None
    env["state"]["answers"]["mvp_profile_guess"] = lambda u: {"topics": []}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"key_points": []}
    for k in ("MVP_VIDEO_ASK", "MVP_VIDEO_ASK_MAX_MIN", "MVP_VIDEO_ASK_PER_DAY", "MVP_VIDEO_ASK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-not-a-key")
    env["clock"][0] = datetime(2026, 11, 19, 17, 0, tzinfo=UTC)
    return env


def on(monkeypatch):
    monkeypatch.setenv("MVP_VIDEO_ASK", "1")


# ================================ (a) one hook order ===============================================================
def test_the_history_read_comes_before_asking_a_video_and_both_before_the_summary_and_the_model():
    src = open(os.path.join(os.path.dirname(HERE), "handler.py"), encoding="utf-8").read()
    body = src[src.index("    def answer_normally("):]
    body = body[:body.index("\n    def ", 10)]
    at = [body.index(n) for n in ("done, ref = self.integration_reads(person, text, now)",
                                  "ref = history.history_reads(self, person, text, now)",
                                  "ref = videoask.reads(self, person, text, now)",
                                  "it, paid = self.code_reads(person, text, self._answer_seen(handle))",
                                  "over = self._over_cap(person)",
                                  "ref = synth_reads(self, person, text, now)",
                                  "it, _ = interpret(")]
    assert at == sorted(at)


@pytest.mark.parametrize("text", ["ask the video", "ask the video what white balance it uses", "ask video 2 about iso",
                                  "what leaves this computer"])
def test_asking_a_video_is_never_a_history_question(text):
    from mvp import history
    assert history.read(text, TODAY) is None


def test_ask_the_video_with_no_video_in_view_says_so_and_calls_nothing(lib, monkeypatch):
    on(monkeypatch)
    fake = FakeGemini(GOOD).install(monkeypatch)
    out, calls = ask(lib, "ask the video what white balance it uses")
    assert out.startswith("I haven't shown you a YouTube video to ask yet.") and calls == [] and not fake.requests


# ================================ (b) a window inside a summary ====================================================
@pytest.mark.parametrize("text,kind", [("summarize what i watched last month about lens filters", "month"),
                                       ("what have i learned about lens filters in october", "month"),
                                       ("summarize what i learned about blender this month", "month"),
                                       ("what did i learn about running last week", "week"),
                                       ("what have i learned about sleep lately", "lately")])
def test_a_summary_reads_one_window_with_slice_hs_words_and_keeps_only_the_topic(text, kind):
    from mvp import synth
    got = synth.read(text, TODAY)
    assert got is not None and got["window"].kind == kind, text
    assert not re.search(r"\b(?:month|week|october|lately|last|this)\b", got["topic"]), got
    assert synth.read(text) is None   # without today (slice M's own read), as before


@pytest.mark.parametrize("text", ["send me a summary of what i learned about blender every week",
                                  "every sunday summarize what i learned about sourdough",
                                  "remind me what i learned about blender tomorrow",
                                  "how many videos about blender have i watched", "what did i watch last week",
                                  "when did i first start watching cooking videos",
                                  "what do these say last month",
                                  "summarize what i learned about blender in october and every friday"])
def test_a_window_never_lets_in_a_rule_a_reminder_or_a_history_question(text):
    from mvp import synth
    assert synth.read(text, TODAY) is None, text


def test_a_summary_with_a_window_reads_only_what_was_watched_then_and_says_the_window_and_the_export_end(lib):
    seen = []

    def synth_fake(user):
        seen.append(user)
        return {"points": [], "about": []}
    lib["state"]["answers"]["mvp_synth"] = synth_fake
    lib["state"]["answers"]["mvp_extract"] = lambda u: {"key_points": ["Lens filters for night video made simple"]}
    out, calls = ask(lib, "summarize what i watched in october about lens filters", CHAT)
    assert "mvp_interpret" not in calls
    # round 11 fix, B (S3): the plain line names the window (was "about lens filters in what you watched in October 2026")
    assert "of the 2 videos you watched in October 2026 about lens filters" in out
    assert "Pretend Lens Co" in out and "cheat sheet" not in out   # watched only: the saved post is left out
    assert "Your YouTube export ends on 9 October 2026, so I can't see after that." in out
    assert "how do I send you a new export?" in out


def test_a_window_outside_the_record_is_said_plainly_with_no_model_call(lib):
    out, calls = ask(lib, "what have i learned about lens filters this month", CHAT)
    assert calls == []
    assert out.startswith("I can't see this month (1 to 19 November 2026): your Instagram export ends on 5 October "
                          "2026 and your YouTube export on 9 October 2026, so I can't see after that.")
    out, calls = ask(lib, "what did i learn about lens filters in 2019", CHAT)
    assert calls == [] and out.startswith("I can't see 2019: your ")


# ================================ (c) the summary's video offer ====================================================
def _summary(e, monkeypatch=None):
    e["state"]["answers"]["mvp_extract"] = lambda u: {"key_points": [
        re.search(r"<item>(?:Title: )?(.*?)(?:\n|</item>)", u, re.S).group(1).strip()]}

    def synth_fake(user):
        blocks = re.findall(r"(?m)^(\d+)\. <item>Title: .*?\nPoints from its own text:\n- (.*?)\n", user, re.S)
        return {"points": [{"text": b, "sources": [{"n": int(n), "quote": b}]} for n, b in blocks],
                "about": [int(n) for n, _ in blocks]}
    e["state"]["answers"]["mvp_synth"] = synth_fake
    return ask(e, "summarize what i've learned about lens filters", CHAT)


def test_the_summary_offers_to_ask_a_video_only_with_the_setting_and_names_the_videos_by_number(lib, monkeypatch):
    out, _ = _summary(lib)
    assert "ask the video" not in out and "ask video" not in out
    on(monkeypatch)
    out, _ = _summary(lib)
    # round 11 fix, B (S1, V1): the YouTube sources by the numbers shown, and "ask them" (was 'say "ask video N" and
    # your question (2 is "<title>", ...)')
    m = re.search(r'say "ask them" and your question, and I\'ll ask videos (.*?); for one, "ask video (\d)"\.', out)
    assert m, out
    shown = lib["bot"].store.last_answer(H)["items"]
    for n in re.findall(r"\d", m.group(1)):
        it = lib["bot"].view(lib["bot"].store.person(H)["library"]).get(shown[int(n) - 1])
        assert it.platform == "youtube"
        assert f"{n}. \"{it.caption}" in out


def test_ask_video_n_after_a_summary_asks_that_video(lib, monkeypatch):
    on(monkeypatch)
    fake = FakeGemini(GOOD).install(monkeypatch)
    out, _ = _summary(lib)
    n = re.search(r'(?m)^(\d)\. "Lens filters for night', out).group(1)   # round 11 fix, B (S1): the numbered list
    out, _ = ask(lib, f"ask video {n} what white balance it uses")
    assert out.startswith("Before I ask:")   # the first time: what leaves this computer
    out, calls = ask(lib, "ask the video")
    assert fake.requests and "FAKEvidAAA1" in json.dumps(fake.requests[-1])
    assert out.startswith('From the video (not checked against its text), "Lens filters for night video')
    assert "watch?v=FAKEvidAAA1&t=65s" in out and "mvp_interpret" not in calls


def test_no_offer_when_no_youtube_video_is_shown(lib, monkeypatch):
    from mvp import synth

    class It:
        def __init__(self, platform):
            self.platform, self.url, self.video_id = platform, "https://www.instagram.com/reel/CxFAKE/", None
    on(monkeypatch)
    assert synth._video_offer([It("instagram")]) == ""
    monkeypatch.setenv("MVP_VIDEO_ASK", "0")
    assert synth._video_offer([It("youtube")]) == ""


# ================================ (d) a history answer puts a video pick in view ===================================
def test_a_history_list_then_the_second_one_then_a_question_its_title_cannot_answer_offers_the_video(lib, monkeypatch):
    on(monkeypatch)
    fake = FakeGemini(GOOD).install(monkeypatch)
    out, calls = ask(lib, "what did i watch on october 2")
    assert calls == [] and "Lens filters for night video" in out and "Lens filters for bright" in out
    out, calls = ask(lib, "the second one")
    assert calls == []
    second = lib["bot"].store.last_answer(H)["items"]
    assert len(second) == 1   # the one shown is the pick in view
    out, calls = ask(lib, "what does it say about white balance", {"intent": "follow_up", "pick_number": None,
                                                                     "question": "What does it say about white balance?"})
    assert "I only have the title of" in out or "I can't tell that from what" in out
    assert 'say "ask the video"' in out
    out, _ = ask(lib, "ask the video")
    assert fake.requests and out.startswith("From the video (not checked against its text)")
    # the history follow-ups still read the history answer's own list
    out, calls = ask(lib, "the first one")
    assert calls == [] and "watch?v=" in out


def test_with_the_setting_off_the_honest_line_stays_and_nothing_is_offered(lib, monkeypatch):
    fake = FakeGemini(GOOD).install(monkeypatch)
    ask(lib, "what did i watch on october 2")
    ask(lib, "the first one")
    out, _ = ask(lib, "what does it say about white balance", {"intent": "follow_up", "pick_number": None,
                                                                "question": "What does it say about white balance?"})
    assert "ask the video" not in out and "Gemini" not in out and not fake.requests


def test_what_do_these_say_after_a_history_answer_sums_up_its_items_on_its_topic(lib):
    ask(lib, "what did i watch about lens filters in october")
    lib["state"]["answers"]["mvp_synth"] = lambda u: {"points": [], "about": []}
    out, calls = ask(lib, "what do these say", CHAT)
    assert "mvp_interpret" not in calls and "about lens filters" in out and "history:" not in out


# ================================ (e) receipts, export, delete =====================================================
def test_a_video_asked_is_in_the_receipts_the_export_and_gone_after_delete(lib, monkeypatch):
    from mvp import export
    on(monkeypatch)
    FakeGemini(GOOD).install(monkeypatch)
    ask(lib, "what did i watch on october 2")
    ask(lib, "the first one")
    ask(lib, "what does it say about white balance", {"intent": "follow_up", "pick_number": None,
                                                      "question": "What does it say about white balance?"})
    ask(lib, "ask the video")
    ask(lib, "ask the video")
    out, _ = ask(lib, "what did you do for me")
    assert "asked 1 YouTube video a question for you, sending its link and your question to Google" in out
    st = lib["bot"].store
    got = export.round11_rows(st, H)
    assert got["video_asks"][0]["video_id"] == "FAKEvidAAA1" and got["video_asks"][0]["status"] == "done"
    assert [p["at"] for p in got["video_answer"]["points"]] == [65, 190]
    assert "white balance" not in json.dumps(got["video_asks"])   # the question itself is never kept
    st.delete_person_data(H)
    for key in ("history", "videoask", "videoask_seen", "videoans"):
        assert st.get_state(f"{key}:{H}") is None, key
    assert export.round11_rows(st, H) == {}


def test_the_history_follow_up_form_is_in_the_export(lib):
    from mvp import export
    ask(lib, "which channels did i watch the most in october")
    got = export.round11_rows(lib["bot"].store, H)
    assert got["history_follow_up"]["form"]["kind"] == "top_channels" and "video_asks" not in got


# ================================ (f) and the framing: help, "what can you do", the setup ===========================
def test_the_help_leads_with_asking_the_watch_history_from_the_persons_own_counts(lib):
    out, calls = ask(lib, "help")
    assert calls == []
    assert out.startswith("Ask your watch history anything. I can see 3 videos you watched on YouTube, up to 9 "
                          "October 2026. Try:\n\"which channels did I watch the most in October?\"\n")
    from mvp import texts as T
    assert T.HELP in out and "Apps: \"what can I connect\"" in out and "I'm running build" in out
    assert "ask the video" not in out
    out2, _ = ask(lib, "what can you do")
    assert out2 == out


def test_the_help_examples_use_a_profile_topic_the_record_holds_and_are_all_taken_by_code(lib, monkeypatch):
    from mvp import history, synth
    from mvp import profile as P
    st = lib["bot"].store
    prof = P.get(st, H)
    prof["interests"] = [{"topic": "made up knitting", "status": "confirmed"},
                         {"topic": "lens filters", "status": "confirmed"}]
    monkeypatch.setattr(P, "get", lambda store, h: prof)
    line, qs = history.examples(lib["bot"], st.person(H), lib["clock"][0])
    assert qs == ["which channels did I watch the most in October?",
                  "when did I first watch videos about lens filters?",
                  "summarize what I've learned about lens filters"]
    assert all(history.read(q, TODAY) is not None or synth.read(q) is not None for q in qs)


def test_the_help_names_asking_a_video_only_with_the_setting(lib, monkeypatch):
    on(monkeypatch)
    out, _ = ask(lib, "help")
    assert "Videos: after I show you a YouTube video, \"ask the video\" and your question asks the video itself " \
           "(its link and your question go to Google)." in out


def test_an_empty_history_keeps_the_help_as_it_was(env):
    from mvp import config
    from mvp import texts as T
    from mvp.places import help_args
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", ("/nonexistent/made-up-library", H))
    bot.views.clear()
    assert bot._help_text(H) == T.help_full(config.BUILD, **help_args(bot, H))


def test_the_connector_menu_says_nothing_of_asking_a_video(lib, monkeypatch):
    on(monkeypatch)
    out, _ = ask(lib, "what can i connect")
    assert "Gemini" not in out and "ask the video" not in out


# ================================ the checks that stay true =========================================================
def test_no_rule_text_or_rule_phrasing_is_taken_by_the_window_read_or_by_asking_a_video(env, monkeypatch):
    from mvp import synth, videoask
    from mvp.tests.test_round9_merge import eval_texts, rule_phrasings
    texts, phr = eval_texts(), rule_phrasings()
    assert len(texts) == 159 and len(phr) == 123
    assert [t for t in texts + phr if synth.read(t, TODAY) is not None] == []
    assert [t for t in texts + phr if videoask.read_ask(t) is not None or videoask.LEAVES.match(t)] == []


def test_the_setups_last_message_leads_its_suggestions_with_asking_the_watch_history(lib):
    bot = lib["bot"]
    lib["state"]["answers"]["mvp_first_requests"] = lambda u: {"requests": []}
    n = len(lib["ch"].outbox)
    bot._onboard_final(bot.store.person(H), lib["clock"][0])
    out = "\n".join(str(m[2]) for m in lib["ch"].outbox[n:])
    block = out.index("Ask your watch history anything. I can see 3 videos you watched on YouTube, up to 9 October 2026.")
    assert block < out.index("Anything I should know to pick better")
    assert "\"which channels did I watch the most in October?\"" in out
