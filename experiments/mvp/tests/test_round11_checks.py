"""The independent check of round 11 (DESIGN.md section 18.X): "ask your watch history anything" after the merge.

Offline: the fake model of test_mvp (it fails a test when it is called where code should answer), the fake Gemini, and
the checker's own made-up watch history below (invented titles, channels, handles and 11-letter video ids). The person
is in New York; the clock is Thursday 19 November 2026 unless a test moves it. The YouTube record ends on Sunday
15 November 2026 in New York (16 November 03:30 UTC), Instagram's on 10 November 2026."""
import json
import os
import sys
from datetime import date, datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice6 import AllPool  # noqa: E402

TODAY = date(2026, 11, 19)
UTC = timezone.utc
NO_MODEL = {"intent": "chat", "reply": "MODEL WAS CALLED"}


# ================================ the checker's made-up library ===================================================
def _rows():
    yt, n = [], [0]

    def add(title, ch, events):
        n[0] += 1
        yt.append((f"y{n[0]:03d}", f"CHKvid{n[0]:05d}", title, ch, events))

    def w(*ats):
        return [("watch", a) for a in ats]
    add("Paper maps for city walks", "Pocket Atlas", w("2023-12-03T16:00:00+00:00"))
    add("Synth patch from scratch", "Tidal Synths", w("2024-02-29T15:00:00+00:00"))          # leap day
    add("Cooking lentils for the week", "Orbit Kitchen", w("2024-03-10T18:00:00+00:00"))
    add("Moss terrarium in a jar", "Moss Lab", w("2024-06-01T14:00:00+00:00"))
    add("Old trail maps explained", "Pocket Atlas", w("2024-09-15T14:00:00+00:00"))
    add("Cooking eggs on a camp stove", "Orbit Kitchen", w("2024-11-02T18:00:00+00:00"))
    for i in range(12):
        ch, title = [("Orbit Kitchen", "Cooking beans, part {}"), ("Tidal Synths", "Synth pads lesson {}"),
                     ("Byte Garage", "Fixing an old laptop {}")][i % 3]
        add(title.format(i + 1), ch, w(f"2025-{i + 1:02d}-12T19:00:00+00:00"))
    add("Cocina rápida: arroz con verduras", "Orbit Kitchen", w("2025-07-20T19:00:00+00:00"))
    for i, d in enumerate(["02", "08", "14", "20", "26"]):
        add(f"Grain sanding trick {i + 1}", "Grain & Grit", w(f"2026-09-{d}T17:00:00+00:00"))
    add("Late night synth jam", "Tidal Synths", w("2026-10-01T02:00:00+00:00"))            # 30 Sep, New York
    add("Cooking rice without a cooker", "Orbit Kitchen", w("2026-10-03T18:00:00+00:00"))
    add("Synth filter basics", "Tidal Synths", w("2026-10-05T18:00:00+00:00"))
    add("Synth envelope explained", "Tidal Synths", w("2026-10-09T18:00:00+00:00"))
    add("Reading contour lines on maps", "Pocket Atlas", w("2026-10-12T18:00:00+00:00"))
    add("Cooking pasta for one", "Orbit Kitchen", w("2026-10-15T18:00:00+00:00"))
    add("Moss wall build", "Moss Lab", w("2026-10-20T18:00:00+00:00"))
    add("Synth sequencer tips", "Tidal Synths", w("2026-10-02T18:00:00+00:00", "2026-10-25T18:00:00+00:00",
                                                  "2026-11-04T18:00:00+00:00"))
    add("Halloween synth sounds", "Tidal Synths", w("2026-11-01T03:00:00+00:00"))          # 31 Oct, New York
    add("Wood grain filler test", "Grain & Grit", w("2026-10-28T18:00:00+00:00"))
    add("Cooking soup in ten minutes", "Orbit Kitchen", w("2026-11-03T18:00:00+00:00"))
    add("Map folding the easy way", "Pocket Atlas", w("2026-11-07T18:00:00+00:00"))
    add("Synth chords for beginners", "Tidal Synths", w("2026-11-09T18:00:00+00:00"))
    add("Laptop fan cleaning", "Byte Garage", w("2026-11-10T18:00:00+00:00"))
    add("Moss care in winter", "Moss Lab", w("2026-11-14T18:00:00+00:00") + [("like", "2026-11-10T18:10:00+00:00")])
    add("Sunday cooking prep", "Orbit Kitchen", w("2026-11-16T03:30:00+00:00"))            # 15 Nov, New York
    add("Synth knob sounds ASMR", "Tidal Synths", [("like", "2026-10-18T18:00:00+00:00")])  # liked, never watched
    ig = [("i001", "Cooking hack with a lid", "orbit.kitchen", "none", [("save", "2026-10-06T12:00:00+00:00")]),
          ("i002", "Tiny moss bowl", "moss.lab", "none", [("like", "2026-10-11T12:00:00+00:00")]),
          ("i003", "Synth desk tour", "tidal.synths", "none", [("watch", "2026-11-02T12:00:00+00:00")]),
          ("i004", "Map art reel", "pocket.atlas", "none", [("watch", "2026-11-05T12:00:00+00:00"),
                                                             ("like", "2026-11-05T12:01:00+00:00")]),
          ("i005", "Cooking noodles fast", "orbit.kitchen", "none", [("watch", "2026-11-10T12:00:00+00:00")]),
          ("i_f1", "Cooking party at my place", "bestie", "mutual", [("watch", "2026-11-08T12:00:00+00:00"),
                                                                     ("save", "2026-11-08T12:00:00+00:00")]),
          ("i_f2", "Synth night with friends", "bandmate", "mutual", [("like", "2026-10-20T12:00:00+00:00")])]
    return yt, ig


def write_library(path):
    yt, ig = _rows()
    (path / "corpus").mkdir(parents=True, exist_ok=True)
    with open(path / "corpus" / "items.jsonl", "w") as f, open(path / "corpus" / "interactions.jsonl", "w") as g:
        for iid, vid, title, ch, evs in yt:
            pd = {"owner_relation": "none", "video_id": vid, "owner_name": ch, "owner_handle": "", "duration_s": 480,
                  "media_kind": "video"}
            f.write(json.dumps({"id": iid, "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={vid}",
                                "caption": title, "interaction_kinds": sorted({k for k, _ in evs}),
                                "platform_data": pd}) + "\n")
            g.writelines(json.dumps({"item_id": iid, "kind": k, "at": at}) + "\n" for k, at in evs)
        for iid, cap, handle, rel, evs in ig:
            pd = {"owner_relation": rel, "owner_handle": handle, "media_kind": "reel"}
            f.write(json.dumps({"id": iid, "platform": "instagram", "source_url": f"https://www.instagram.com/reel/C{iid}X/",
                                "caption": cap, "interaction_kinds": sorted({k for k, _ in evs}),
                                "platform_data": pd}) + "\n")
            g.writelines(json.dumps({"item_id": iid, "kind": k, "at": at}) + "\n" for k, at in evs)
    return path


@pytest.fixture()
def chk(env, tmp_path, monkeypatch):
    lib = write_library(tmp_path / "chklib")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.views.clear()
    bot.pool = AllPool(str(lib))
    bot.max_per_minute = None
    env["state"]["answers"]["mvp_profile_guess"] = lambda u: {"topics": []}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"key_points": []}
    for k in ("MVP_VIDEO_ASK", "MVP_VIDEO_ASK_MAX_MIN", "MVP_VIDEO_ASK_PER_DAY", "MVP_VIDEO_ASK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    env["clock"][0] = datetime(2026, 11, 19, 17, 0, tzinfo=UTC)
    env["libpath"] = lib
    return env


def ask(e, text, form=None):
    n0, c0 = len(e["ch"].outbox), len(e["calls"])
    say(e, text, form or NO_MODEL)
    return "\n".join(str(t) for _, _, t in e["ch"].outbox[n0:]), e["calls"][c0:]


def at(e, iso):
    e["clock"][0] = datetime.fromisoformat(iso)


# ================================ 1. messages: windows the merge read wrong ========================================
def test_29_february_without_a_year_is_the_latest_leap_day_never_the_last_four_weeks(chk):
    out, calls = ask(chk, "what did i watch on feb 29")
    assert calls == [] and out.startswith("On Thursday 29 February 2024 you watched 1 video:\n"
                                          "1. Synth patch from scratch by Tidal Synths (29 Feb 2024)")


def test_this_yr_is_this_year_never_the_topic_yr(chk):
    out, calls = ask(chk, "wich chanels did i wacth the most this yr")
    assert calls == [] and out.startswith("This year (1 January to 19 November 2026) you watched 24 videos")
    assert '"yr"' not in out


def test_spanish_function_words_are_never_a_topic(chk):
    out, calls = ask(chk, "cual fue el primer video que vi")
    assert calls == [] and out.startswith("El primer video que viste fue el 3 de diciembre de 2023:")
    assert '"fue"' not in out


def test_spanish_the_last_n_days_is_that_window_never_all_time(chk):
    out, calls = ask(chk, "cuantos videos vi en los ultimos 7 dias")
    assert calls == [] and out.startswith("En los últimos 7 días (13 a 19 de noviembre de 2026) viste 2 videos.")


def test_did_i_watch_anything_on_a_day_lists_that_day(chk):
    out, calls = ask(chk, "did i watch anything on nov 10")
    assert calls == [] and out.startswith("On Tuesday 10 November 2026 you watched 2 videos:\n")


@pytest.mark.parametrize("clock,text,head", [
    ("2026-11-19T17:00:00+00:00", "what did i watch this past weekend",
     "On the weekend of 14 to 15 November 2026 you watched 2 videos."),
    ("2026-11-19T17:00:00+00:00", "what did i watch last weekend",
     "On the weekend of 14 to 15 November 2026 you watched 2 videos."),
    ("2026-11-15T17:00:00+00:00", "what did i watch last weekend",          # on a Sunday: the weekend before
     "On the weekend of 7 to 8 November 2026 you watched 1 video."),
    ("2026-11-19T17:00:00+00:00", "what did i watch 2 weeks ago",
     "In the week of 2 to 8 November 2026 you watched 5 videos."),
    ("2026-11-19T17:00:00+00:00", "what did i watch between oct 1 and oct 10",
     "From 1 to 10 October 2026 you watched 4 videos."),
    ("2026-11-19T17:00:00+00:00", "what did i watch 6 days ago", "On Friday 13 November 2026 you watched no videos."),
    ("2026-11-19T17:00:00+00:00", "what did i watch 3 days ago", "I can't see Monday 16 November 2026: "),
])
def test_weekends_ago_and_ranges_are_their_own_windows(chk, clock, text, head):
    at(chk, clock)
    out, calls = ask(chk, text)
    assert calls == [] and out.startswith(head), out


@pytest.mark.parametrize("text", ["how many videos did i watch in the first week of october",
                                  "how many videos do i watch a day",
                                  "what did i watch the week after halloween",
                                  "how many videos did i watch in my first year of college"])
def test_time_words_no_window_took_go_to_the_interpreter_never_another_window(chk, text):
    from mvp import history
    assert history.read(text, TODAY) is None
    _, calls = ask(chk, text)
    assert calls[:1] == ["mvp_interpret"]


def test_this_week_on_a_monday_past_the_export_says_the_one_day_it_shows(chk):
    at(chk, "2026-11-16T15:00:00+00:00")
    out, _ = ask(chk, "what did i watch this week")
    assert out.startswith("I can't see this week (16 November 2026): ")
    assert "The latest I can see:\nOn Sunday 15 November 2026 you watched 1 video." in out
    assert "last 1 days" not in out


def test_like_or_save_never_counts_a_watch(chk):
    out, calls = ask(chk, "how many cooking posts did i like or save")
    assert calls == []
    assert out.startswith('In all your history I can see, you liked or saved 1 post or video that mentions "cooking" '
                          '(of 5 you liked or saved in all).')
    assert "watched" not in out.split("\n")[0]


def test_where_likes_start_is_said_as_the_likes_never_the_history(chk):
    out, _ = ask(chk, "what did i like on youtube in october")
    assert "Your YouTube likes here start on 18 October 2026, so I can't see before that." in out
    assert "history here starts" not in out


def test_a_channel_counts_the_same_in_the_ranking_the_pick_and_the_count(chk):
    out, _ = ask(chk, "which channels do i watch the most")
    assert "1. Tidal Synths: 11\n2. Orbit Kitchen: 11\n" in out
    out, _ = ask(chk, "the first one")
    assert out.startswith("In all your history I can see, you watched 11 videos from Tidal Synths.")
    assert "@tidal.synths" not in out          # the Instagram account of the same name is another account
    out, _ = ask(chk, "how many videos from orbit kitchen have i watched")
    assert out.startswith("In all your history I can see, you watched 11 videos from Orbit Kitchen")


# ================================ 1. follow-ups ===================================================================
@pytest.mark.parametrize("text", ["ok thanks", "for real?", "lol", "nice", "just kidding", "that's wrong",
                                  "in the morning", "ok cool", "and?", "y tu?", "for dinner", "so what", "but why",
                                  "on it", "only the good ones", "just checking", "in a bit", "on my way", "ok wait",
                                  "and you?", "for sure", "and then?", "what about it", "so random", "lmao", "thanks!",
                                  "and the weather?", "for my sister"])
def test_chat_after_a_history_answer_is_never_a_new_topic(chk, text):
    ask(chk, "how many videos did i watch in october")
    out, calls = ask(chk, text)
    assert calls[:1] == ["mvp_interpret"], out


@pytest.mark.parametrize("text,head", [
    ("and the month before that?", "In September 2026 you watched 6 videos."),
    ("the ones i liked", "In October 2026 you liked 2 posts and videos (1 on YouTube, 1 on Instagram)."),
    ("last month?", "In October 2026 you watched 9 videos."),
    ("and cooking?", 'In October 2026 you watched 2 videos that mention "cooking"'),
    ("what about knitting", 'In October 2026 you watched 0 videos that mention "knitting"'),
    ("only on youtube", "In October 2026 you watched 9 videos."),
])
def test_real_follow_ups_still_work(chk, text, head):
    ask(chk, "how many videos did i watch in october")
    out, calls = ask(chk, text)
    assert calls == [] and out.startswith(head), out


# ================================ 1. the traps: never a history question ==========================================
TRAPS = ["what should i watch tonight", "remind me to watch the synth video tomorrow at 6",
         "every friday send me a cooking video", "email me the last video i watched", "cancel my netflix",
         "stop rule 2", "that was a great pick thanks", "this isn't what i asked for",
         "connect my youtube so you can see what i watch", "can you see my watch history?",
         "find that video about the synth patch i watched", "recommend something like the cooking videos i watched",
         "i watched way too much youtube this month lol", "what's the most popular cooking channel",
         "summarize this video", "summarize my week", "show me my rules", "pause all my rules for this month",
         "add the first one to my list", "what did you do for me this week", "who can see what i watch",
         "delete my watch history", "remind me in october to rewatch the synth tutorials",
         "next month remind me to cancel spotify", "the second one", "another one", "more like this",
         "what channel is this from", "is this channel any good", "how do i send you a new export?",
         "export my data", "unsubscribe me from that channel", "put this on my calendar for saturday",
         "what's on my to-do list", "i don't like cooking videos anymore", "stop sending me synth stuff",
         "every monday send me the most watched video of the week", "what month is it", "who is the best youtuber",
         "watch this later", "save this for later", "i want to start watching more cooking videos",
         "show me cooking videos", "give me a synth tutorial to watch", "summarize the second one",
         "how many rules do i have", "how many to-dos do i have", "how many recipes have i saved",
         "what did i save this week", "what did i save last month", "my youtube is connected right?",
         "remind me every sunday to clean my room", "text me at 9pm to watch the synth video",
         "what are you connected to", "most of these are mid tbh", "these were the worst picks this month",
         "ok thanks", "can you watch this video for me and tell me what it says",
         "send me the channels i watch most every month", "what was the name of the channel from that video"]


@pytest.mark.parametrize("text", TRAPS)
def test_the_checkers_60_traps_are_never_a_history_question(text):
    from mvp import history
    assert history.read(text, TODAY) is None
    assert len(TRAPS) == 60


# ================================ 2. numbers and window edges (counted by hand from the library above) ==========
@pytest.mark.parametrize("clock,text,head", [
    # the person's time zone: 1 Oct 02:00 UTC is 30 September in New York, 1 Nov 03:00 UTC is 31 October
    ("2026-11-19T17:00:00+00:00", "how many videos did i watch in september", "In September 2026 you watched 6 videos."),
    ("2026-11-19T17:00:00+00:00", "how many videos did i watch in october", "In October 2026 you watched 9 videos."),
    ("2026-11-19T17:00:00+00:00", "what did i watch on halloween",
     "On Saturday 31 October 2026 you watched 1 video:\n1. Halloween synth sounds"),
    ("2026-11-19T17:00:00+00:00", "what did i watch on oct 1", "On Thursday 1 October 2026 you watched no videos."),
    # "today" at 23:00 in New York is still 15 November, where UTC is on the 16th
    ("2026-11-16T04:00:00+00:00", "what did i watch today", "On Sunday 15 November 2026 you watched 1 video:"),
    # the month at 22:00 on 30 November in New York is November, not December
    ("2026-12-01T03:00:00+00:00", "how many videos did i watch this month", "This month (1 to 30 November 2026) you"),
    # "the last 7 days" counts today and the 6 days before it: 9 November is in, 8 November is not
    ("2026-11-15T20:00:00+00:00", "how many videos did i watch in the last 7 days",
     "In the last 7 days (9 to 15 November 2026) you watched 5 videos (4 on YouTube, 1 on Instagram)."),
    ("2026-11-19T17:00:00+00:00", "how many videos did i watch on feb 29 2024",
     "On Thursday 29 February 2024 you watched 1 video."),
    ("2026-11-19T17:00:00+00:00", "how many videos did i watch on christmas 2025",
     "On Thursday 25 December 2025 you watched 0 videos."),
    ("2026-11-19T17:00:00+00:00", "what did i watch in 2022",
     "I can't see 2022: your YouTube history here starts on 3 December 2023, so I can't see before that."),
    ("2026-11-19T17:00:00+00:00", "how many videos did i watch in 2025", "In 2025 you watched 13 videos."),
    ("2026-11-19T17:00:00+00:00", "which channels do i watch the most",
     "In all your history I can see, you watched 43 videos (40 on YouTube, 3 on Instagram). Most from:\n"
     "1. Tidal Synths: 11\n2. Orbit Kitchen: 11\n3. Grain & Grit: 6\n4. Byte Garage: 5\n5. Pocket Atlas: 4\n"
     "(9 channels in all.)"),
])
def test_numbers_and_window_edges_match_a_count_by_hand(chk, clock, text, head):
    at(chk, clock)
    out, calls = ask(chk, text)
    assert calls == [] and out.startswith(head), out


def test_a_holiday_with_a_year_is_that_years():
    from mvp import history
    q = history.read("how many videos did i watch on halloween 2025", TODAY)
    assert (q.window.kind, q.window.start, q.window.end) == ("day", date(2025, 10, 31), date(2025, 10, 31))


# ================================ 3. honesty ======================================================================
def test_a_window_that_reaches_one_platforms_export_end_says_that_one(chk):
    out, _ = ask(chk, "what did i watch between nov 1 and nov 12")
    assert out.startswith("From 1 to 12 November 2026 you watched 8 videos.")
    assert "Your Instagram export ends on 10 November 2026, so I can't see after that." in out
    assert "YouTube export" not in out          # YouTube's runs to the 15th, past the window


def test_friends_posts_are_never_counted_nor_shown(chk):
    out, _ = ask(chk, "how many videos have i liked")
    assert out.startswith("In all your history I can see, you liked 4 posts and videos (2 on YouTube, 2 on Instagram).")
    out, _ = ask(chk, "how many cooking videos have i watched")
    assert out.startswith('In all your history I can see, you watched 11 videos that mention "cooking"')
    out, _ = ask(chk, "what did i watch on nov 8")
    assert out.startswith("On Sunday 8 November 2026 you watched no videos.")
    assert "party" not in out.lower() and "bestie" not in out and "bandmate" not in out


def test_a_like_is_never_said_as_watched(chk):
    out, _ = ask(chk, "which videos did i like last month")
    first = out.split("\n")[0]
    assert first.startswith("In October 2026 you liked 2 posts and videos") and "watched" not in out
    out, _ = ask(chk, "when did i first like a video")
    assert out.startswith("The first post or video you liked was on 11 October 2026:") and "watched" not in out


@pytest.mark.parametrize("text,head", [
    ("have i ever watched anything about knitting",
     'In all your history I can see, you watched 0 videos that mention "knitting" (of 43 you watched in all).'),
    ("what did i watch about knitting last month", 'In October 2026 you watched no videos that mention "knitting".'),
    ("when did i first watch knitting videos", 'In all your history I can see, you watched no videos that mention '
                                               '"knitting".'),
])
def test_a_topic_with_no_match_says_so_and_lists_nothing(chk, text, head):
    out, calls = ask(chk, text)
    assert calls == [] and out.startswith(head), out
    assert "http" not in out
