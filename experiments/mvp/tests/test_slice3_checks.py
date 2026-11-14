"""Checker tests for slice 3: what the checks found and fixed. A failed details call or an odd YouTube response never
fails the answer; wrong shapes from the model are read as nothing; nothing is said to be "in the video" when the post's
text holds a list; number words and digits back each other; a description that arrives later is read even after the
title alone gave nothing twice; a pick with a must-have "no" is never shown; lengths are not rounded across a limit.
Synthetic data only."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (a fixture)
from mvp.tests.test_slice3 import add_items, compose_once, yt_item  # noqa: E402

PICK = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"}], "intro": "Found one."}


def test_a_failed_details_call_still_sends_the_answer_and_claims_nothing(env):
    def boom(u):
        raise TimeoutError("model slow")
    env["state"]["answers"]["mvp_extract"] = boom
    msg = compose_once(env, PICK, extract=["ingredients"])
    assert "I recommend Lemon garlic pasta" in msg and "in the video" not in msg
    assert env["bot"].store.one("SELECT COUNT(*) n FROM facts")["n"] == 0      # nothing cached from a failed call


def test_an_odd_youtube_response_works_as_before(env, monkeypatch):
    from mvp import ytinfo
    add_items(env, [yt_item()])
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda ids, key, timeout=None: ["not", "a", "dict"])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_y", "itm_a"], "mode": "normal", "cost_usd": 0}
    assert "I recommend " in compose_once(env, PICK)
    assert env["bot"].yt.errors == 1


def test_wrong_shapes_from_the_composer_are_read_as_nothing(env):
    for raw in ([], {"picks": {"n": 2}}, {"picks": "2"}):
        assert compose_once(env, raw).startswith("I didn't find a good match")
    odd = {"picks": [{"n": "2", "verdict": None, "title": None, "criteria": "yes", "facts": "2 lemons",
                      "because": ["x"]}]}
    msg = compose_once(env, odd)
    assert "The closest I have is" in msg or "I recommend" in msg


def test_a_details_line_given_as_a_string_is_read(env):
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": "200g spaghetti", "steps": []}
    assert "Ingredients (1):\n• 200g spaghetti" in compose_once(env, PICK, extract=["ingredients"])


def test_in_the_video_is_never_said_when_the_post_holds_a_list(env):
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": [], "steps": []}
    msg = compose_once(env, PICK, extract=["ingredients"])             # itm_a's caption has an ingredients list
    assert "in the video" not in msg
    msg = compose_once(env, {"picks": [{"n": 3, "verdict": "clear", "title": "Pasta night"}]}, extract=["ingredients"])
    assert "The recipe is in the video, not written in the post." in msg   # no list in that caption


def test_number_words_and_digits_back_each_other():
    from mvp.compose import numbers_backed
    assert numbers_backed("it needs two lemons", "2 lemons")
    assert numbers_backed("it needs 4 cloves", "four cloves of garlic")
    assert not numbers_backed("it needs three lemons", "2 lemons")
    assert numbers_backed("it is one of the easiest", "easy pasta")      # "one of", "this one": not a quantity
    assert numbers_backed("this one is quick", "quick pasta")
    assert not numbers_backed("it needs only one pot", "a big pot of pasta")
    assert numbers_backed("it needs only one pot", "all in 1 pot")
    assert numbers_backed("it is a one-pot dinner", "One-pot pasta")


def test_a_description_that_arrives_later_is_read_after_empty_title_attempts(env):
    from mvp.extract import details
    add_items(env, [yt_item(title="A very long beginner Blender donut tutorial title, part one of three")])
    bot = env["bot"]
    view = bot.view(str(env["lib"]))
    it = view.get("itm_y")
    env["state"]["answers"]["mvp_extract"] = lambda u: {"steps": []}
    details(it, ["steps"], view.lib, store=bot.store)
    details(it, ["steps"], view.lib, store=bot.store)                # the title alone, twice: cached as empty
    assert details(it, ["steps"], view.lib, store=bot.store)[1]["calls"] == 0
    extra = {"itm_y": {"description": "Steps:\n1. Add a torus\n2. Sculpt the icing\n3. Render it", "duration_s": 600}}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"steps": ["Add a torus", "Sculpt the icing", "Render it"]}
    facts, info = details(it, ["steps"], view.lib, store=bot.store, extra=extra)
    assert facts["steps"] == ["Add a torus", "Sculpt the icing", "Render it"] and info["calls"] >= 1


def test_a_must_have_no_is_never_shown_even_as_the_closest(env):
    raw = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta", "criteria": [{"answer": "no"}]}],
           "none_reason": "none of these ends with a finished dish"}
    n = env["calls"].count("mvp_compose")
    msg = compose_once(env, raw, criteria=["ends with a finished dish"])
    # fix pass, finding 26: a pick whose only "no" is the finished-result must-have is still shown, plainly as the
    # closest, when nothing else is even close (a "no" on any other must-have is never shown: test_slice3.py)
    assert msg.startswith("None of what I found is a whole recipe you can cook, so the closest I have is Lemon garlic "
                          "pasta")
    assert env["calls"].count("mvp_compose") == n + 2      # asked once more for the closest among the others


def test_when_every_pick_fails_a_must_have_the_closest_of_the_others_is_offered(env):
    seen = []
    answers = iter([{"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta",
                                "criteria": [{"answer": "no"}]}]},
                    {"picks": [{"n": 3, "verdict": "close", "title": "Pasta night", "criteria": [{"answer": "unknown"}]}]}])
    msg = compose_once(env, lambda u: (seen.append(u), next(answers))[1], criteria=["ends with a finished dish"])
    assert "candidates 2 fail a must-have" in seen[1]
    assert msg.startswith("I couldn't confirm any of these is a whole recipe you can cook, but the closest I have is "
                          "Pasta night")
    assert "the closest I have is Pasta night" in msg and "Lemon garlic" not in msg


def test_a_web_card_is_only_made_for_a_web_link():
    from mvp.channels.web import WebChannel
    ch = WebChannel(serve=False)
    ch.send_link("+1", {"url": "javascript:alert(1)", "title": "x", "platform": "instagram"})
    assert ch.threads["+1"][-1]["link"] is None


def test_a_length_is_not_rounded_across_a_limit():
    from mvp.ytinfo import minutes_text
    assert minutes_text(9 * 60 + 40) == "9 minutes 40 seconds"
    assert minutes_text(10 * 60) == "10 minutes" and minutes_text(61) == "1 minute 1 second"
    assert minutes_text(3600 + 5 * 60 + 59) == "1 hour 5 minutes" and minutes_text(30) == "under a minute"
