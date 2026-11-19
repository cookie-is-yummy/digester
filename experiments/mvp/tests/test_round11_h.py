"""Round 11, slice H (DESIGN.md section 18.H): "ask your watch history anything", answered by code (history.py).

A planted, made-up watch history (tests/h_library.py), a fake clock (Thursday 19 November 2026, New York) and a fake
model that fails the test when it is called: every history question here is read and answered by code. The near
variants at the end must NOT be taken: picks, rules, to-dos, emails, the 159 rule texts and the 123 phrasings."""
import json
import os
import sys
from datetime import date, datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402
from mvp.tests.test_slice6 import AllPool  # noqa: E402
from mvp.tests import h_library  # noqa: E402

TODAY = date(2026, 11, 19)
NO_MODEL = {"intent": "chat", "reply": "MODEL WAS CALLED"}
ENDS = "your YouTube export on 30 October 2026, so I can't see after that."
REFRESH = "For newer history, send me a new export (ask \"how do I send you a new export?\" for the steps)."


@pytest.fixture()
def hist(env, tmp_path):
    lib = h_library.write(tmp_path / "hlib")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = AllPool(str(lib))
    bot.max_per_minute = None
    env["clock"][0] = datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc)
    env["lib"] = lib
    return env


def ask(e, text, form=None):
    """The person sends `text`; returns every message the bot sent for it, joined, and whether the model was asked."""
    n0, c0 = len(e["ch"].outbox), len(e["calls"])
    say(e, text, form or NO_MODEL)
    out = "\n".join(str(t) for _, _, t in e["ch"].outbox[n0:])
    return out, e["calls"][c0:]



# ================================ the founder's cases (the brief's H1 to H4 and H8) ===============================
def test_h1_the_most_this_month_honours_the_window_says_where_the_export_ends_and_ranks_channels(hist):
    out, calls = ask(hist, "what have i been watching the most this month")
    assert calls == []
    assert out.startswith("I can't see this month (1 to 19 November 2026): your Instagram export ends on 15 October "
                          "2026 and " + ENDS + " " + REFRESH)
    assert "The latest I can see:\nIn October 2026 you watched 17 videos (16 on YouTube, 1 on Instagram). Most from:\n" \
           "1. Pixel Forge: 6\n2. Kettle & Cast: 4\n3. Chord Garden: 3\n4. Grade Lab: 2\n5. Loose Wires: 1\n" \
           "(6 channels in all.)" in out
    assert "kept" not in out and "\"watching\"" not in out and "\"most\"" not in out and "this month\"" not in out


def test_h2_last_week_is_past_the_export_so_it_says_so_and_shows_the_last_week_it_can_see(hist):
    out, calls = ask(hist, "what did i watch last week")
    assert calls == []
    assert out.startswith("I can't see the week of 9 to 15 November 2026: your Instagram export ends on 15 October "
                          "2026 and " + ENDS)
    assert REFRESH in out
    assert "In the last 7 days (24 to 30 October 2026) you watched 4 videos. The latest 4:\n" \
           "1. Blender camera tricks by Pixel Forge (30 Oct) https://www.youtube.com/watch?v=vy005" in out


def test_h3_which_channels_gives_a_ranking_with_counts_over_all_the_history(hist):
    out, calls = ask(hist, "which channels do i watch the most")
    assert calls == []
    assert out.startswith("In all your history I can see, you watched 44 videos (42 on YouTube, 2 on Instagram). "
                          "Most from:\n1. Kettle & Cast: 18\n2. Chord Garden: 11\n3. Pixel Forge: 8\n")
    assert "your YouTube history from 5 January 2024 to 30 October 2026." in out and REFRESH in out


def test_h4_how_many_about_a_topic_says_watched_never_kept(hist):
    out, calls = ask(hist, "how many videos about blender have i watched")
    assert calls == []
    assert out.startswith("In all your history I can see, you watched 9 videos that mention \"blender\" "
                          "(of 44 you watched in all).")
    assert "kept" not in out


def test_h8_first_gives_the_date_and_the_items_with_their_cards_never_a_recommendation(hist):
    out, calls = ask(hist, "when did i first start watching cooking videos")
    assert calls == []
    assert out.startswith("The first video you watched that mentions \"cooking\" was on 10 February 2024:\n"
                          "1. Cooking rice the easy way by Kettle & Cast (10 Feb 2024)\n"
                          "2. Cooking eggs three ways by Kettle & Cast (2 Mar 2024)\n"
                          "3. Cooking with cast iron by Kettle & Cast (9 Mar 2024)\n(14 in all.)\n"
                          "https://www.youtube.com/watch?v=vy_firstcook\nhttps://www.youtube.com/watch?v=vy036\n"
                          "https://www.youtube.com/watch?v=vy037\nYour Instagram history here runs from")
    assert "your YouTube history from 5 January 2024 to 30 October 2026." in out
    assert "recommend" not in out.lower()
    st = hist["bot"].store
    kept = st.answer(st.last_answer(H)["run_id"])["parts"]   # on a channel with previews, each link is a card
    assert [p["type"] for p in kept] == ["text", "link", "link", "link", "text"]
    assert [p["url"] for p in kept if p["type"] == "link"] == [
        "https://www.youtube.com/watch?v=vy_firstcook", "https://www.youtube.com/watch?v=vy036",
        "https://www.youtube.com/watch?v=vy037"]


def test_h5_that_video_about_stays_a_search_for_the_one_video(hist):
    hist["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "intro": ""}
    out, calls = ask(hist, "what was that video i watched about color grading", {"intent": "ask", "spec": {
        "when": {"type": "now"}, "content": {"goal": "a video about color grading", "searches": ["color grading"],
                                             "count": 1}}})
    assert calls[:1] == ["mvp_interpret"]


# ================================ what is counted ==================================================================
def test_a_watch_is_dated_in_the_persons_time_zone(hist):
    out, _ = ask(hist, "what did i watch on october 30")
    # 31 October 02:30 UTC is 30 October 22:30 in New York
    assert out.startswith("On Friday 30 October 2026 you watched 3 videos:\n")
    assert "Color grading: matching two cameras by Grade Lab (30 Oct)" in out
    out, _ = ask(hist, "show me what i watched on halloween")
    assert out.startswith("I can't see Saturday 31 October 2026: ")


def test_a_video_watched_again_counts_in_each_month_and_once_in_each(hist):
    sep, _ = ask(hist, "how many videos did i watch in sept 2026")
    oct_, _ = ask(hist, "how many youtube videos did i watch in october")
    assert sep.startswith("In September 2026 you watched 10 videos.")
    assert oct_.startswith("In October 2026 you watched 16 videos.")
    out, _ = ask(hist, "whats my most rewatched video")
    assert "1. Blender render settings explained by Pixel Forge: 3 times, last on 20 Oct " \
           "https://www.youtube.com/watch?v=vy_rewatch" in out


def test_friends_posts_are_never_counted_not_even_their_watches(hist):
    out, _ = ask(hist, "how many posts did i save last month", {"intent": "library_stats", "stats": {"kinds": ["save"]}})
    assert out.startswith("In October 2026 you saved 4 posts and videos.")   # the friend's save is the fifth
    assert "Posts from friends are not counted." in out
    out, _ = ask(hist, "how many videos did i watch in october")
    assert out.startswith("In October 2026 you watched 17 videos (16 on YouTube, 1 on Instagram).")


def test_likes_are_liked_and_saves_are_saved(hist):
    out, _ = ask(hist, "how many things did i like last month")
    assert out.startswith("In October 2026 you liked 3 posts and videos (2 on Instagram, 1 on YouTube).")
    out, _ = ask(hist, "how many posts did i save in october", {"intent": "library_stats", "stats": {"kinds": ["save"]}})
    assert out.startswith("In October 2026 you saved 4 posts and videos.")
    assert "(Saved counts saves, collections, posts you sent yourself and playlists.)" in out
    # saves stay where they were without the interpreter's form: the recent answer and the library count (rule eval
    # t-dev-014 and t-dev-049)
    from mvp import history
    assert history.read("what did i save this week", TODAY) is None
    assert history.read("how many recipes have i saved total", TODAY) is None
    out, calls = ask(hist, "how many recipes have i saved total", {"intent": "library_stats", "stats": {}})
    assert calls == ["mvp_interpret"] and out.startswith("You've kept ")


@pytest.mark.parametrize("text,head", [
    ("how many videos did i watch in 2025", "In 2025 you watched 11 videos."),
    ("how many videos have i watched in the last 30 days",
     "In the last 30 days (21 October to 19 November 2026) you watched 5 videos."),
    ("what have i watched since october 20", "Since 20 October 2026 you watched 6 videos. The latest 5:"),
    ("how many guitar videos did i watch this year",
     "This year (1 January to 19 November 2026) you watched 0 videos that mention \"guitar\" (of 27 you watched "
     "then)."),
    ("what was i watching in march 2024", "In March 2024 you watched 2 videos. The latest 2:"),
    ("my most watched channels in 2026", "In 2026 you watched 27 videos (25 on YouTube, 2 on Instagram). Most from:"),
    ("what have i been watching lately", "In the 4 weeks up to 30 October 2026 (where your export ends), you watched "
                                         "16 videos. The latest 5:"),
    ("how many vidoes did i wacth this week", "I can't see this week (16 to 19 November 2026): "),
    ("how many hours of youtube have i watched", "I count videos, not hours or minutes. In all your history I can "
                                                 "see, you watched 42 videos."),
])
def test_the_window_is_always_said_back(hist, text, head):
    out, calls = ask(hist, text)
    assert calls == [] and out.startswith(head), out


def test_a_window_inside_the_record_does_not_say_where_it_ends_and_one_that_touches_it_does(hist):
    out, _ = ask(hist, "how many videos did i watch in 2025")
    assert "export ends" not in out and "runs from" not in out
    out, _ = ask(hist, "how many videos did i watch in october")
    assert ENDS in out and REFRESH in out


def test_big_numbers_are_written_with_separators():
    from mvp import history
    assert history.num(108997) == "108,997" and history.num(108997, "es") == "108.997" and history.num(44) == "44"


def test_the_refresh_words_are_read_as_the_export_steps(hist):
    from mvp.refresh import export_kind
    assert export_kind("how do I send you a new export?") == "how"


def test_timeline_compare_and_channel_questions(hist):
    out, _ = ask(hist, "how has my blender watching changed over time")
    assert out.startswith("Videos you watched that mention \"blender\", by year:\n2024: 0, 2025: 1, 2026: 8 (up to "
                          "30 Oct 2026).\nThe last months, by month: May 2026: 0, Jun 2026: 0, Jul 2026: 0, Aug 2026: 0, "
                          "Sep 2026: 2, Oct 2026: 7 (up to 30 Oct 2026).\n9 in all.")
    out, _ = ask(hist, "how many blender videos did i watch each month this year")
    assert out.startswith("Videos you watched that mention \"blender\", by month, this year (1 January to 19 November "
                          "2026):\nJan 2026: 0,")
    out, _ = ask(hist, "how much youtube did i watch last month compared to the month before")
    assert out.startswith("In October 2026 you watched 16 videos, and in September 2026, 10: 6 more in October 2026.")
    out, _ = ask(hist, "how many videos from kettle & cast have i watched")
    assert out.startswith("In all your history I can see, you watched 18 videos from Kettle & Cast (of 44 you watched "
                          "in all).")
    out, _ = ask(hist, "when did i start watching chord garden")
    assert out.startswith("The first video you watched from Chord Garden was on 1 May 2024:")
    out, _ = ask(hist, "which channel do i watch most for cooking")
    assert "you watched 14 videos that mention \"cooking\". Most from:\n1. Kettle & Cast: 14" in out


def test_a_topic_that_is_also_a_channel_name_stays_a_topic_unless_the_message_says_from(hist, tmp_path):
    lib = h_library.write(tmp_path / "hlib2", extra_rows=[
        {"id": "y_chan", "platform": "youtube", "caption": "Studio tour", "channel": "Blender",
         "events": [("watch", "2026-10-10T12:00:00+00:00")]}])
    hist["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    out, _ = ask(hist, "how many videos about blender have i watched")
    assert "that mention \"blender\"" in out
    out, _ = ask(hist, "how many videos from blender have i watched")
    assert "1 video from Blender" in out


def test_spanish_questions_get_spanish_answers(hist):
    out, calls = ask(hist, "que vi ayer")
    assert calls == [] and out.startswith("No veo miércoles 18 de noviembre de 2026: ")
    assert "El viernes 30 de octubre de 2026 viste 3 videos:" in out
    out, _ = ask(hist, "cuántos videos vi el mes pasado")
    assert out.startswith("En octubre de 2026 viste 17 videos (16 en YouTube, 1 en Instagram).")
    out, _ = ask(hist, "¿qué canales veo más?")
    assert out.startswith("En todo tu historial, viste 44 videos") and "1. Kettle & Cast: 18" in out


# ================================ follow-ups =======================================================================
def test_follow_ups_change_the_window_the_platform_and_the_topic_and_list_them(hist):
    ask(hist, "which channels do i watch the most")
    out, calls = ask(hist, "and last month?")
    assert calls == [] and out.startswith("In October 2026 you watched 17 videos")
    out, _ = ask(hist, "what about youtube")
    assert out.startswith("In October 2026 you watched 16 videos. Most from:")
    out, _ = ask(hist, "the first one")   # after a ranking: that channel's videos
    assert out.startswith("In October 2026 you watched 6 videos from Pixel Forge. The latest 5:")
    out, _ = ask(hist, "more")
    assert out.startswith("The next 1:\n6. Blender donut, the easy way by Pixel Forge (1 Oct)")
    ask(hist, "how many videos did i watch in october")
    out, _ = ask(hist, "show me them")
    assert out.startswith("In October 2026 you watched 17 videos. The latest 5:")
    out, calls = ask(hist, "the second one")
    assert calls == [] and out == "Sunday bread bake by Kettle & Cast\nhttps://www.youtube.com/watch?v=vy009"
    ask(hist, "how many videos did i watch in october")
    out, _ = ask(hist, "what about guitar")
    assert out.startswith("In October 2026 you watched 0 videos that mention \"guitar\" (of 17 you watched then).")
    out, _ = ask(hist, "and in 2025?")
    assert out.startswith("In 2025 you watched 0 videos that mention \"guitar\" (of 11 you watched then).")
    out, _ = ask(hist, "what about cooking")
    assert out.startswith("In 2025 you watched 6 videos that mention \"cooking\" (of 11 you watched then).")
    out, _ = ask(hist, "show me them")
    assert out.startswith("In 2025 you watched 6 videos that mention \"cooking\". The latest 5:\n"
                          "1. Cooking for one, episode 6 by Kettle & Cast (14 Jul 2025)")


def test_a_follow_up_word_after_an_ordinary_answer_is_not_read_as_history(hist):
    hist["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(hist, "pasta, no cream", ask_pasta())
    out, calls = ask(hist, "and last month?")
    assert calls == ["mvp_interpret"]
    ask(hist, "how many videos did i watch in october")
    hist["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(hist, "pasta, no cream", ask_pasta())   # a newer answer ends the history follow-ups
    out, calls = ask(hist, "show me them")
    assert calls == ["mvp_interpret"]


def test_the_follow_ups_end_after_six_hours(hist):
    from datetime import timedelta
    ask(hist, "which channels do i watch the most")
    hist["clock"][0] += timedelta(hours=7)
    out, calls = ask(hist, "and last month?")
    assert calls == ["mvp_interpret"]


def test_a_history_answer_is_kept_as_the_last_answer_with_its_items(hist):
    ask(hist, "what did i watch on october 30")
    last = hist["bot"].store.last_answer(H)
    assert last["items"] == ["y005", "y009", "y014"]
    assert hist["bot"].store.answer(last["run_id"])["kind"] == "history"
    run = hist["bot"].store.one("SELECT * FROM runs WHERE id=?", (last["run_id"],))
    steps = json.loads(run["steps"])["history"]
    assert run["kind"] == "history" and run["cost_usd"] == 0.0 and steps["kind"] == "on_day"
    assert "topic" not in steps   # the person's words are not kept in the run, only how many


# ================================ after the interpreter ============================================================
def test_a_library_stats_form_with_a_history_shape_gets_the_history_answer(hist, monkeypatch):
    from mvp import history
    monkeypatch.setattr(history, "read", lambda text, today, loose=False: None if not loose else
                        history.HistoryQuery(kind="count", window=history._win("month", date(2026, 10, 1),
                                                                                  date(2026, 10, 31))))
    out, calls = ask(hist, "videos october count", {"intent": "library_stats", "stats": {"words": ["october"]}})
    assert calls == ["mvp_interpret"] and out.startswith("In October 2026 you watched 17 videos")


def test_the_old_count_keeps_its_answer_and_loses_the_questions_own_words(hist):
    out, _ = ask(hist, "how many cooking things do i have", {"intent": "library_stats",
                                                             "stats": {"words": ["cooking", "most", "this month"]}})
    assert out.startswith("You've kept ") and "mention \"cooking\"." in out
    assert "\"most\"" not in out and "this month" not in out


def test_a_rule_made_of_a_history_question_is_said_plainly_with_todays_answer(hist):
    rule = {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON"], "time": "09:00"},
                                           "content": {"goal": "top channels", "searches": ["top channels"]}}}
    out, calls = ask(hist, "send me my top channels every month", rule)
    assert calls == ["mvp_interpret"]
    assert out.startswith("I can answer that now, but I can't send your history on a schedule yet, so I didn't set "
                          "up a rule. Here it is for now:\n\nIn all your history I can see, you watched 44 videos")
    assert hist["bot"].store.rules(H) == [] and hist["bot"].store.pending(H) is None
    out, _ = ask(hist, "every sunday tell me which channels i watched the most", rule)
    assert out.startswith("I can answer that now")


def test_a_rule_that_is_not_a_history_question_stays_a_rule(hist):
    hist["state"]["answers"]["mvp_compose"] = lemon_pick()
    rule = {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["FRI"], "time": "18:00"},
                                           "content": {"goal": "a pasta recipe", "searches": ["pasta recipe"]}}}
    for text in ("every friday send me a pasta recipe", "text me the top 5 videos i saved this month every friday",
                 "every friday send me the most popular recipe from my saves",
                 "remind me to watch more cooking videos every weekend"):
        hist["bot"].store.clear_pending(H)
        out, _ = ask(hist, text, rule)
        assert "can't send your history" not in out, text


# ================================ what is never taken ==============================================================
TRAPS = [json.loads(x) for x in """
{"text": "what should i watch tonight"}
{"text": "send me my top channels every month"}
{"text": "what was that video i watched about color grading"}
{"text": "what did that video say about the settings to use"}
{"text": "summarize what ive learned about motion design from what i watched"}
{"text": "remind me to watch the blender video tomorrow"}
{"text": "email sam that i watched the game last week"}
{"text": "add the last video i watched to my list"}
{"text": "find me a cooking video i watched that uses lentils"}
{"text": "every friday send me the most popular recipe from my saves"}
{"text": "what's the most useful blender tutorial i saved"}
{"text": "show me a guitar lesson i watched"}
{"text": "recommend a channel like the ones i watch"}
{"text": "what are some youtube channels for learning blender"}
{"text": "remind me in october to renew my passport"}
{"text": "add watch the new season to my list"}
{"text": "every month send me a recipe i saved"}
{"text": "what have i been into lately"}
{"text": "how many rules do i have"}
{"text": "did my export come in"}
{"text": "email me the last video i watched"}
{"text": "unsubscribe me from the channels i don't watch anymore"}
{"text": "what's a good movie to watch this weekend"}
{"text": "give me something new to watch from my saves"}
{"text": "last month i watched a video about sourdough, find it"}
{"text": "pause my rules for a month"}
{"text": "what did you do for me last week"}
{"text": "every sunday tell me which channels i watched the most"}
{"text": "put the first video i watched in my calendar"}
{"text": "i watched way too much youtube this month lol"}
{"text": "show me videos from october about cooking"}
{"text": "what's the best channel for color grading"}
{"text": "my rules"}
{"text": "stop sending me the monthly recap"}
{"text": "how do i export my watch history"}
{"text": "who can see what i watch"}
{"text": "what did the blender video i watched say about render settings"}
{"text": "remind me to watch more cooking videos every weekend"}
{"text": "text me the top 5 videos i saved this month every friday"}
{"text": "qué debería ver esta noche"}
{"text": "i saved a reel last week about knife skills"}
{"text": "what are the most popular videos on youtube right now"}
{"text": "when did i save the lasagna recipe, can you send it"}
{"text": "show me the blender videos i saved"}
{"text": "what was the first thing you told me"}
{"text": "how many to-dos do i have this week"}
{"text": "which of my saves should i watch first"}
{"text": "delete everything i watched last month"}
{"text": "add my top channels to my calendar"}
{"text": "something i watched last month about lentils, the soup one"}
""".strip().splitlines()]


def test_the_traps_are_never_read_as_history_questions():
    from mvp import history
    taken = [t["text"] for t in TRAPS if history.read(t["text"], TODAY) is not None]
    assert taken == []


def test_the_traps_never_reach_the_history_answer_through_the_bot(hist):
    from mvp import history
    seen = []
    real = history.send_answer

    def spy(*a, **kw):
        seen.append(a[2])
        return real(*a, **kw)
    history.send_answer = spy
    try:
        for t in TRAPS:
            if "every" in t["text"] and "channels i watched" in t["text"] or t["text"].startswith("send me my top"):
                continue   # a rule made of a history question: the plain line (tested above)
            hist["bot"].store.clear_pending(H)
            say(hist, t["text"], NO_MODEL)
    finally:
        history.send_answer = real
    assert seen == []


QUESTIONS = """what have i been watching the most this month|what did i watch last week|which channels do i watch the most
how many videos about blender have i watched|when did i first start watching cooking videos|what did i watch yesterday
how many videos did i watch in october|top channels last month|who do i watch the most on youtube
what was the last cooking video i watched|how has my blender watching changed over time|what did i watch on october 30
how many youtube videos have i watched in 2025|my most watched channels in 2026|whats the first video i ever watched
how many guitar videos did i watch this year|what did i watch last friday|how many videos did i like on youtube
how many reels have i liked on instagram this year|which channel do i watch most for cooking
did i watch more in october or september|how much youtube did i watch last month compared to the month before
videos watched per month this year|when was the last time i watched something about color grading
how many videos have i watched in the last 30 days|what have i watched since october 20
how many vidoes did i wacth this week|wich chanels do i watch the most|top 10 youtubers i watched this year
when did i first watch something about guitar|what was i watching in march 2024|how many videos have i watched in total
how many blender videos did i watch each month this year|show me what i watched on halloween
what channels did i watch in september|how many cooking videos have i watched since 2025|whats my most rewatched video
what videos have i watched more than once|how many things did i like last month|what did i like in october
how many hours of youtube have i watched|first blender video i watched|the last thing i watched
what did i watch on youtube the past 2 weeks|how much did i watch in 2024 vs 2025|my watch history for october
how many videos from kettle & cast have i watched|when did i start watching chord garden
how many videos did i watch on october 30|what have i been watching lately|what topics do i watch the most
since when have i been watching guitar stuff|how many videos did i watch in sept 2026
which youtube channels did i watch the most last year|how many blender videos have i watched by year
¿qué canales veo más?|cuantos videos de cocina he visto este año|que vi ayer|cuándo empecé a ver videos de guitarra
cuántos videos vi el mes pasado""".replace("\n", "|").split("|")


def test_sixty_history_questions_are_answered_by_code_with_no_model_call(hist):
    assert len(QUESTIONS) == 60
    for q in QUESTIONS:
        out, calls = ask(hist, q)
        assert calls == [] and out and "MODEL WAS CALLED" not in out, q


def test_no_rule_text_or_rule_phrasing_is_taken_by_slice_h(env, monkeypatch):
    """The 159 rule-eval texts (with and without an answer kept) and the 123 rule phrasings of the earlier test files
    are answered by neither history read (hook 8h, nor the read after the interpreter's chat form)."""
    from mvp import history
    from mvp.tests.test_round9_merge import eval_texts, rule_phrasings
    taken = []
    for name in ("history_reads", "after_interpret"):
        real = getattr(history, name)

        def w(*a, _real=real, _name=name, **kw):
            out = _real(*a, **kw)
            if out is not None:
                taken.append((_name, a[2] if _name == "history_reads" else a[3]))
            return out
        monkeypatch.setattr(history, name, w)
    env["bot"].max_per_minute = None
    texts = eval_texts()
    phr = rule_phrasings()
    assert len(texts) == 159 and len(phr) == 123
    for after_answer in (False, True):
        for t in texts + phr:
            if after_answer:
                env["state"]["answers"]["mvp_compose"] = lemon_pick()
                say(env, "pasta, no cream", ask_pasta())
            env["bot"].store.clear_pending(H)
            say(env, t, {"intent": "chat", "reply": "OK."})
    assert taken == []
    for t in texts:   # read directly too (the bot's earlier hooks answer some of them first)
        assert history.read(t, TODAY) is None, t


def test_hook_8h_sits_after_integration_reads_and_before_the_code_reads_and_the_model():
    src = open(os.path.join(os.path.dirname(HERE), "handler.py"), encoding="utf-8").read()
    body = src[src.index("    def answer_normally("):]
    body = body[:body.index("\n    def ", 10)]
    a = body.index("done, ref = self.integration_reads(person, text, now)")
    b = body.index("ref = history.history_reads(self, person, text, now)")
    c = body.index("it, paid = self.code_reads(person, text, self._answer_seen(handle))")
    d = body.index("it, _ = interpret(")
    e = body.index("ref = history.after_interpret(self, person, it, text, now)")
    f = body.index("screened = self.screen_guard(person, it, text, now)")
    assert a < b < c < d < f < e


def test_history_names_no_action_and_calls_no_model():
    src = open(os.path.join(os.path.dirname(HERE), "history.py"), encoding="utf-8").read()
    for word in ("chat_json", "llm.", "executor", "registry", "email.send", "calendar.add"):
        assert word not in src, word
