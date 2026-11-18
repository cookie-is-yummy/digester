"""Offline tests for the adversarial check of round 10 on reading and answers (checker 2 of the verdict's section 5.2;
DESIGN.md section 17, "The check of reading and answers"). Each test here failed before the fix it guards.

- What the person says about a reel: every everyday way of saying "slop" asks first; the pick named in the mismatch's
  own clause is the one learned, never one the same message calls fine; a complaint about what was asked is asked about
  before anything is learned (captionmark.fit_reads).
- YouTube and the cancel helper: "i want to unsubscribe from that channel" is the person's YouTube, never a merchant
  called "Channel" (ytreads._PLEASE, cancel.CHANNEL_NAME).
- Two asks in one message reach both helpers, whichever comes first (Bot._another_ask, ytreads.is_ask).

Fakes only (the fake model of test_mvp, the fake Google of slice Y); made-up names, example.com addresses; no model
call, no network. None of these messages comes from the held-out phrasing set.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round10_slop import slop, ask, composer  # noqa: E402,F401
from mvp.tests.test_round10_youtube import yt, tell, show, connect, actions  # noqa: E402,F401

FELL = {"intent": "chat", "reply": "FELL"}
STRONG = ("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")
GOOD = ("busy nights", "clear", "Creamy chicken alfredo")
PENNE = ("Penne", "clear", "Creamy Penne")
ASKED = 'Was it that the video didn\'t match what its caption said? Reply "yes" or "no".'


def feedback(bot):
    return [(r["item_id"], r["kind"]) for r in bot.store.caption_feedback(H)]


# =====================================================================================================================
# 1. "slop" in everyday words asks first (attack 44); it never learns by itself
# =====================================================================================================================
@pytest.mark.parametrize("msg", ["that's ai slop", "ai slop", "slop lol", "thats slop tbh", "these are slop",
                                 "that reel is slop", "that was slop", "the first one is slop", "lol that's slop",
                                 "ugh slop", "that's such slop", "total ai slop", "this is ai slop", "the 2nd one is slop"])
def test_everyday_slop_asks_the_one_question_and_learns_nothing(slop, msg):
    ask(slop, composer(STRONG, GOOD))
    n = len(slop["calls"])
    assert say(slop, msg, FELL) == ASKED, msg
    assert slop["calls"][n:] == [] and feedback(slop["bot"]) == []


@pytest.mark.parametrize("msg", ["that is not slop", "not slop", "so sloppy", "sloppy joes recipe", "slop?"])
def test_near_variants_that_are_not_slop_are_left_alone(slop, msg):
    ask(slop, composer(STRONG, GOOD))
    assert say(slop, msg, FELL) != ASKED and feedback(slop["bot"]) == []


def test_the_question_after_the_first_one_is_slop_is_about_the_first_pick(slop):
    ask(slop, composer(GOOD, PENNE))
    first = slop["bot"].store.last_answer(H)["items"][0]
    assert say(slop, "the first one is slop", FELL) == ASKED
    assert say(slop, "yes", FELL).startswith("Thanks, that helps.")
    assert feedback(slop["bot"]) == [(first, "mismatch")]


# =====================================================================================================================
# 2. The pick a mismatch is about: the one named in its own clause (attack 44, near variants)
# =====================================================================================================================
@pytest.mark.parametrize("msg", ["the first one was fine, the second one had nothing to do with it",
                                 "the first one was fine but the second reel had nothing to do with it",
                                 "the 1st one was ok and the 2nd video doesn't match",
                                 "the second one had nothing to do with it, the first one was fine"])
def test_a_mismatch_lands_on_the_pick_its_clause_names_never_on_the_one_called_fine(slop, msg):
    ask(slop, composer(GOOD, PENNE))
    items = slop["bot"].store.last_answer(H)["items"]
    assert say(slop, msg, FELL).startswith("Thanks, that helps.")
    assert feedback(slop["bot"]) == [(items[1], "mismatch")], msg


def test_with_two_picks_the_unnamed_one_is_the_other_one_and_with_three_nothing_is_guessed(slop):
    ask(slop, composer(GOOD, PENNE))
    items = slop["bot"].store.last_answer(H)["items"]
    say(slop, "the first one was fine but the reel had nothing to do with it", FELL)
    assert feedback(slop["bot"]) == [(items[1], "mismatch")]
    slop["bot"].store.x("DELETE FROM caption_feedback")
    ask(slop, composer(GOOD, PENNE, STRONG))
    assert len(slop["bot"].store.last_answer(H)["items"]) == 3
    say(slop, "the first one was fine but the reel had nothing to do with it", FELL)
    assert feedback(slop["bot"]) == []


def test_a_plain_mismatch_still_learns_as_before(slop):
    ask(slop, composer(GOOD, PENNE))
    items = slop["bot"].store.last_answer(H)["items"]
    say(slop, "the second video doesn't match", FELL)
    assert feedback(slop["bot"]) == [(items[1], "mismatch")]


# =====================================================================================================================
# 3. A complaint about what was asked is about the answer, not the caption: asked first (W-6)
# =====================================================================================================================
@pytest.mark.parametrize("msg", ["the video doesn't match what i asked for", "you sent the wrong video, i wanted soup",
                                 "the reel was unrelated to my question", "that video had nothing to do with my request"])
def test_a_complaint_about_the_request_asks_before_it_learns(slop, msg):
    ask(slop, composer(GOOD, PENNE))
    assert say(slop, msg, FELL) == ASKED, msg
    assert feedback(slop["bot"]) == []


def test_a_mismatch_that_names_the_caption_still_learns(slop):
    ask(slop, composer(GOOD, PENNE))
    say(slop, "the video doesn't match the caption, not what i asked for", FELL)
    assert len(feedback(slop["bot"])) == 1


# =====================================================================================================================
# 4. "i want to unsubscribe from that channel" is the person's YouTube (attack 38, near variants)
# =====================================================================================================================
@pytest.mark.parametrize("text", ["i want to unsubscribe from that channel", "i'd like to unsubscribe from this channel",
                                  "i wanna unsub from that channel", "help me unsubscribe from that youtuber",
                                  "i need to unsubscribe from kitchen lab"])
def test_what_one_wants_before_the_verb_still_reaches_youtube(yt, text):
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, text) == ('Unsubscribe from "Kitchen Lab" on YouTube? Reply "yes" to unsubscribe, or "no" to keep '
                              'it.'), text
    assert not actions(yt, "cancel.help")


def test_not_connected_it_says_how_and_never_names_a_merchant_called_channel(yt):
    show(yt, "yt_1")
    r = tell(yt, "i want to unsubscribe from that channel")
    assert r.startswith("I can do that on YouTube once you connect it") and "Channel" not in r
    from mvp import cancel
    for text in ("i want to unsubscribe from that channel", "unsubscribe from the youtuber", "unsubscribe from this page"):
        assert cancel.request(text) is None, text
    assert cancel.request("unsubscribe me from my brightbox subscription")["kind"] == "unknown"   # near variant


def test_a_paid_service_after_i_want_to_is_still_the_cancel_helper(yt):
    connect(yt)
    show(yt, "yt_1")
    tell(yt, "i want to unsubscribe from netflix")
    assert [r["status"] for r in actions(yt, "cancel.help")] == ["done"]


# =====================================================================================================================
# 5. Two asks in one message reach both helpers, in either order
# =====================================================================================================================
def replies(e, text):
    n = len(e["ch"].outbox)
    e["bot"].on_message(H, text)
    return [t for _, _, t in e["ch"].outbox[n:]]


@pytest.mark.parametrize("text", ["unsubscribe from that channel and cancel netflix",
                                  "cancel netflix and unsubscribe me from that channel",
                                  "unsubscribe from kitchen lab and also cancel my netflix"])
def test_a_channel_and_a_cancel_in_one_message_reach_both(yt, text):
    connect(yt)
    show(yt, "yt_1")
    out = replies(yt, text)
    assert any(r.startswith('Unsubscribe from "Kitchen Lab" on YouTube?') for r in out), out
    assert any(r.startswith("Netflix cancels on its website.") for r in out), out
    assert not any("can't find a channel" in r for r in out)


def test_an_email_then_a_cancel_is_a_card_without_the_cancel_and_the_cancel_steps(env):
    from mvp import config
    config.DRAFT_MODEL = False
    env["bot"].max_per_minute = None
    env["state"]["answers"]["mvp_interpret"] = lambda u: FELL
    out = replies(env, "email maria@example.com that the sink is broken and cancel my netflix")
    card = "\n".join(out)
    assert "Subject: The sink is broken" in card and "The sink is broken." in card
    assert "cancel my netflix" not in card.lower().replace("netflix cancels", "")
    assert any(r.startswith("Netflix cancels on its website.") for r in out)
    assert "mvp_interpret" not in env["calls"]


@pytest.mark.parametrize("text", ["email sam@example.com that i will cancel my netflix",
                                  "email my landlord that the sink is broken and send someone to fix it",
                                  "email sam@example.com that i cancelled netflix and hulu"])
def test_one_email_whose_words_name_a_cancel_stays_one_card(env, text):
    from mvp import config
    config.DRAFT_MODEL = False
    env["bot"].max_per_minute = None
    env["state"]["answers"]["mvp_interpret"] = lambda u: FELL
    out = replies(env, text)
    assert not any("cancels on its website" in r or r.startswith("How do you pay") for r in out), out
    assert env["bot"].store.one("SELECT COUNT(*) AS n FROM drafts")["n"] == 1
