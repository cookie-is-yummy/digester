"""The merge of round 11's fixes (DESIGN.md section 18.L): where fix A (history answers: the recall, the engine's fit,
the quiet footers) and fix B (summaries and asking videos) meet.

(a) fix B's offer after an Instagram post in view, or a history list of reels, reaches fix A's best_watched_video;
(b) fix A's recall puts its first video in view, so a question, "ask the video" and "ask them" (the recall's own list)
work on it; (c) a summary limited to what was watched reads fix A's record, and fix A's fit where the library has
vectors; (d) the hint on sending a new export is said once in a stretch, in summaries too; (e) the hook order (held by
test_round10_merge's HOOK_ORDER); (f) receipts, export and delete after asking several videos, and what leaves this
computer; (g) the help's one line for "ask them".

Offline: the fake model of test_mvp, the fake Gemini, fix B's made-up library (invented titles, channels, handles and
11-letter video ids). No test calls the network."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.fakes.fake_gemini import FakeGemini  # noqa: E402
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round11_fix_b import (CHAT, GOOD, LIB, fb, instagram_pick, on, seen, synth_meta,  # noqa: E402,F401
                                          video_asks, write_library)
from mvp.tests.test_round11_h import ask  # noqa: E402
from mvp.tests.test_slice2 import H  # noqa: E402

RECALL = "what was that video i watched about after effects"
REFRESH = "For newer history, send me a new export"


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    """Never a live call from these tests."""
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def urls(fake):
    return [FakeGemini.sent_url(r) for r in fake.requests]


# ================================ (a) the offer reaches fix A's best_watched_video ==================================
def test_a_an_instagram_post_in_view_offers_the_watched_youtube_video_fix_a_finds(fb, monkeypatch):
    on(monkeypatch)
    fake = FakeGemini(GOOD).install(monkeypatch)
    instagram_pick(fb)   # a saved post about motion design timing; the request said "motion design easing"
    out, calls = ask(fb, "ask the video what software they use")
    assert calls == [] and not fake.requests
    assert out.startswith("I can only ask YouTube videos.")
    # the request's words fit no watched title, so the post's own caption finds it (the merge's fallback)
    assert 'You also watched a YouTube video on this: "Motion design timing tips" ' \
           "https://www.youtube.com/watch?v=FAKEmot0004" in out
    out, calls = ask(fb, "ask that one")
    assert calls == [] and urls(fake) == ["https://www.youtube.com/watch?v=FAKEmot0004"]
    assert "what software they use" in FakeGemini.sent_text(fake.requests[0])


def test_a_the_request_words_come_first_when_they_fit_a_watched_title(fb, monkeypatch):
    on(monkeypatch)
    FakeGemini(GOOD).install(monkeypatch)
    instagram_pick(fb)
    fb["bot"].store.set_state(f"lastspec:{H}", {"text": "easing in after effects"})
    out, _ = ask(fb, "ask the video what software they use")
    assert 'You also watched a YouTube video on this: "Easing in After Effects, explained"' in out


def test_a_a_post_that_shares_nothing_with_a_watched_video_keeps_the_plain_line(fb, monkeypatch):
    on(monkeypatch)
    from mvp import videoask as V
    fake = FakeGemini(GOOD).install(monkeypatch)
    fb["bot"].store.set_last_answer(H, None, None, ["p3"], "color grading")   # the grading cheat sheet
    fb["bot"].store.set_state(f"lastspec:{H}", {"text": "color grading"})
    out, _ = ask(fb, "ask the video what scopes they use")
    assert out == V.NOT_YOUTUBE and not fake.requests


def test_a_a_history_list_of_reels_offers_the_latest_watched_youtube_video_on_its_topic(fb, monkeypatch):
    on(monkeypatch)
    from mvp import history
    fake = FakeGemini(GOOD).install(monkeypatch)
    st = fb["bot"].store
    run_id = st.add_run(handle=H, kind="history", at="2026-11-19T17:00:00+00:00", n_candidates=2, n_picks=2,
                        n_dropped=0, cost_usd=0, status="picked")
    st.set_last_answer(H, run_id, None, ["p2", "p1"], "history: last")
    st.set_state(history.STATE.format(h=H), {"run_id": run_id, "q": {"kind": "last", "topic": ["motion design"]},
                                             "at": "2026-11-19T17:00:00+00:00", "ids": ["p2", "p1"]})
    out, calls = ask(fb, "ask the video what tool do they use first")
    assert calls == [] and not fake.requests
    assert out.startswith("Those are Instagram posts, and I can only ask YouTube videos")
    # the latest watched (fix A's latest=True): "Motion design curves explained", 4 October at 18:00
    assert 'You also watched a YouTube video on this: "Motion design curves explained"' in out


def test_a_off_the_offer_is_never_made(fb, monkeypatch):
    from mvp import videoask as V
    instagram_pick(fb)
    it = fb["bot"].view(str(fb["lib"])).get("p1")
    assert V.offer_line(fb["bot"], fb["bot"].store.person(H), it, "q", fb["clock"][0]) == ""


# ================================ (b) the recall's videos in view ===================================================
def test_b_a_recall_then_ask_them_asks_the_recalls_own_videos_in_its_order(fb, monkeypatch):
    on(monkeypatch)
    seen(fb)
    fake = FakeGemini(GOOD).install(monkeypatch)
    out, calls = ask(fb, RECALL)
    assert calls == [] and out.startswith('You watched these about "after effects", best match first:')
    assert "You watched it on 1 October 2026." in out and "I recommend" not in out
    assert fb["bot"].store.last_answer(H)["items"] == ["y1"]   # the first is the pick in view
    out, calls = ask(fb, "ask them what easing they use")
    assert calls == [] and urls(fake) == ["https://www.youtube.com/watch?v=FAKEeas0001",
                                          "https://www.youtube.com/watch?v=FAKEeas0002",
                                          "https://www.youtube.com/watch?v=FAKEeas0003"]
    for n in (1, 2, 3):
        assert f"Video {n}, \"" in out
    assert [a["status"] for a in video_asks(fb)] == ["done"] * 3


def test_b_ask_them_with_no_question_after_a_recall_asks_about_its_topic(fb, monkeypatch):
    on(monkeypatch)
    seen(fb)
    fake = FakeGemini(GOOD).install(monkeypatch)
    ask(fb, RECALL)
    ask(fb, "ask them")
    assert len(fake.requests) == 3
    assert FakeGemini.sent_text(fake.requests[0]) == "Question: What does it say about after effects?"


def test_b_a_recall_then_ask_the_video_asks_the_first_one_only(fb, monkeypatch):
    on(monkeypatch)
    seen(fb)
    fake = FakeGemini(GOOD).install(monkeypatch)
    ask(fb, RECALL)
    out, calls = ask(fb, "ask the video what easing curve it uses")
    assert calls == [] and urls(fake) == ["https://www.youtube.com/watch?v=FAKEeas0001"]
    assert out.startswith('From the video (not checked against its text), "Easing in After Effects, explained":')


def test_b_a_recall_then_the_note_then_yes_asks_the_three(fb, monkeypatch):
    on(monkeypatch)
    fake = FakeGemini(GOOD).install(monkeypatch)
    ask(fb, RECALL)
    out, _ = ask(fb, "ask them what easing they use")
    assert out.startswith("Before I ask: asking these 3 videos sends their links") and not fake.requests
    out, calls = ask(fb, "yes")
    assert calls == [] and len(fake.requests) == 3


def test_b_a_recall_then_a_question_on_it_names_the_first_video(fb, monkeypatch):
    on(monkeypatch)
    ask(fb, RECALL)
    fb["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "none_reason": "The title says nothing about it."}
    out, calls = ask(fb, "what did that video say about the settings to use", {
        "intent": "follow_up", "pick_number": None, "question": "What did that video say about the settings to use?"})
    assert "Easing in After Effects, explained" in out and "text animation" not in out


def test_b_off_ask_them_after_a_recall_is_not_read(fb, monkeypatch):
    fake = FakeGemini(GOOD).install(monkeypatch)
    ask(fb, RECALL)
    out, calls = ask(fb, "ask them", CHAT)
    assert "mvp_interpret" in calls and not fake.requests


def test_b_a_recall_of_one_video_then_ask_them_asks_that_one(fb, monkeypatch):
    on(monkeypatch)
    seen(fb)
    fake = FakeGemini(GOOD).install(monkeypatch)
    out, _ = ask(fb, "what was that video i watched about easing")
    assert out.startswith('You watched this video about "easing":')
    ask(fb, "ask them what curve they use")
    assert urls(fake) == ["https://www.youtube.com/watch?v=FAKEeas0001"]


# ================================ (c) a summary limited to what was watched =========================================
def _vectors(lib, off_id):
    """Made-up 8-dimension vectors: the motion design items point one way, `off_id` another, the rest elsewhere."""
    import numpy as np
    rows = [json.loads(x) for x in open(lib / "corpus" / "items.jsonl")]
    rng = np.random.default_rng(11)
    ids, vecs = [], []
    for r in rows:
        v = rng.normal(0, 0.05, 8)
        if r["id"] == off_id:
            v[1] += 1.0
        elif "motion design" in r["caption"].lower():
            v[0] += 1.0
        else:
            v[2 + (len(r["id"]) % 5)] += 1.0
        ids.append(r["id"])
        vecs.append(v)
    d = lib / "corpus" / "emb" / "oai3l_1024"
    d.mkdir(parents=True)
    (d / "ids.json").write_text(json.dumps(ids))
    np.save(d / "emb.npy", np.asarray(vecs, dtype=np.float16))


MORE = [("y6", "youtube", "FAKEmot0006", "Motion design for app onboarding", "Pretend Motion Lab", "watch",
         "2026-10-05T15:00:00+00:00", "Animate one screen element at a time in motion design for onboarding."),
        ("y7", "youtube", "FAKEmot0007", "Motion design: arcs feel natural", "Invented Frames", "watch",
         "2026-10-05T16:00:00+00:00", "Move things along arcs, not straight lines, in motion design."),
        ("y8", "youtube", "FAKEtlk0008", "Late night chat: the host tries motion design", "Pretend Late Show",
         "watch", "2026-10-05T17:00:00+00:00", "The host tries motion design on air and the audience laughs.")]


@pytest.fixture()
def fitlib(fb, tmp_path, monkeypatch):
    from mvp.tests.test_round11_m import WordPool
    # fix B's writer and fake YouTube read the module's LIB (whatever name pytest imported it under)
    monkeypatch.setitem(write_library.__globals__, "LIB", LIB + MORE)
    lib = write_library(tmp_path / "fitlib")
    _vectors(lib, "y8")
    bot = fb["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.views.clear()
    bot.pool = WordPool(str(lib))
    fb["lib"] = lib
    return fb


def _summary_run(e):
    st = e["bot"].store
    run = st.one("SELECT steps FROM runs WHERE handle=? AND kind='synth' ORDER BY id DESC LIMIT 1", (H,))
    return json.loads(run["steps"] or "{}")


def test_c_watched_means_what_fix_as_record_counts_and_the_fit_leaves_out_what_only_mentions_it(fitlib):
    out, calls = ask(fitlib, "summarize what ive learned about motion design from what i watched", CHAT)
    assert "mvp_synth" in calls
    assert out.startswith("Here's what the videos you watched say about motion design:")
    assert "Late night chat" not in out and "Motion design tip: timing" not in out   # off the topic; a save
    assert _summary_run(fitlib).get("unfit") == 1


def test_c_without_the_watched_word_the_fit_is_not_used(fitlib):
    ask(fitlib, "summarize what ive learned about motion design", CHAT)
    assert "unfit" not in _summary_run(fitlib)


def test_c_the_limit_reads_the_record_not_the_items_own_list(fb, monkeypatch):
    """An item whose list of kinds says "watch" with no watch in the record is not a watch (the record is what a
    history answer counts too)."""
    from mvp import synth
    bot = fb["bot"]
    person = bot.store.person(H)
    view = bot.view(person["library"])
    it = view.get("p1")   # saved only
    monkeypatch.setattr(it, "kinds", list(it.kinds) + ["watch"])
    req = synth._limit(bot, person, {"topic": "motion design", "how": "watched", "these": False})
    assert "p1" not in req["only"] and {"y1", "y4", "p2"} <= req["only"]


# ================================ (d) the hint on a new export, once in a stretch ===================================
WINDOW = "summarize what i watched in october about motion design"


def test_d_a_summary_with_a_window_says_the_hint_once_and_where_the_export_ends_always(fb):
    out, _ = ask(fb, WINDOW, CHAT)
    assert "export on 4 October 2026, so I can't see after that." in out and REFRESH in out
    out, _ = ask(fb, WINDOW, CHAT)
    assert "export on 4 October 2026, so I can't see after that." in out and REFRESH not in out


def test_d_after_a_history_answer_said_it_the_summary_leaves_it_out(fb):
    out, _ = ask(fb, "what did i watch in october")
    assert REFRESH in out
    out, _ = ask(fb, WINDOW, CHAT)
    assert "so I can't see after that." in out and REFRESH not in out


def test_d_after_six_hours_it_is_said_again(fb):
    from datetime import timedelta
    ask(fb, WINDOW, CHAT)
    fb["clock"][0] += timedelta(hours=7)
    out, _ = ask(fb, WINDOW, CHAT)
    assert REFRESH in out


def test_d_a_window_wholly_after_the_record_always_says_how_to_refresh(fb):
    ask(fb, WINDOW, CHAT)
    out, calls = ask(fb, "what have i learned about motion design this month", CHAT)
    assert calls == [] and out.startswith("I can't see this month") and REFRESH in out


# ================================ (f) receipts, export, delete, what leaves this computer ===========================
def test_f_asking_three_videos_is_in_the_receipts_the_export_and_gone_after_delete(fb, monkeypatch):
    from mvp import export
    on(monkeypatch)
    seen(fb)
    FakeGemini(GOOD).install(monkeypatch)
    ask(fb, RECALL)
    ask(fb, "ask them what easing they use")
    out, _ = ask(fb, "what did you do for me", CHAT)
    assert "asked 3 YouTube videos a question for you, sending each link and your question to Google" in out
    st = fb["bot"].store
    got = export.round11_rows(st, H)
    assert [a["video_id"] for a in got["video_asks"]] == ["FAKEeas0001", "FAKEeas0002", "FAKEeas0003"]
    assert [v["video_id"] for v in got["video_answer"]["videos"]] == ["FAKEeas0001", "FAKEeas0002", "FAKEeas0003"]
    assert "easing they use" not in json.dumps(got["video_asks"])   # the question itself is never kept with an ask
    assert "notes_said" not in got or isinstance(got["notes_said"], dict)
    st.delete_person_data(H)
    for key in ("history", "histnotes", "videoask", "videoask_seen", "videomany_seen", "videoans", "videomany",
                "videoask_go", "consent_video"):
        assert st.get_state(f"{key}:{H}") is None, key
    assert export.round11_rows(st, H) == {}


def test_f_the_note_waiting_for_yes_and_the_summary_topic_are_in_the_export(fb, monkeypatch):
    from mvp import export
    on(monkeypatch)
    fb["state"]["answers"]["mvp_synth"] = synth_meta
    ask(fb, "summarize what ive learned about motion design from what i watched", CHAT)
    ask(fb, "ask them what easing they use")
    got = export.round11_rows(fb["bot"].store, H)
    assert got["ask_them_topic"]["topic"] == "motion design"
    assert got["video_ask_waiting_for_yes"]["videos"] >= 2


def test_f_what_leaves_this_computer_and_the_consent_name_several_videos_only_with_the_setting(fb, monkeypatch):
    from mvp import videoask as V
    assert "Gemini" not in V.leaves_text() and V.consent_note() == ""
    on(monkeypatch)
    assert "\"ask them\" sends up to 3 links, one at a time, each with your question" in V.leaves_text()
    assert "its link and your question go to Google (Gemini), up to 3 videos at once" in V.consent_note()


# ================================ (g) the help ====================================================================
def test_g_the_help_says_ask_them_in_one_line_only_with_the_setting(fb, monkeypatch):
    from mvp import texts as T
    out, _ = ask(fb, "help")
    assert T.HELP_ASK_THEM not in out and "ask them" not in out
    on(monkeypatch)
    out, _ = ask(fb, "help")
    assert out.count(T.HELP_ASK_THEM) == 1 and T.HELP_VIDEO_ASK in out
    assert out.index(T.HELP_VIDEO_ASK) < out.index(T.HELP_ASK_THEM)
