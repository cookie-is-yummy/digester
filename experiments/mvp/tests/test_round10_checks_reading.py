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


# =====================================================================================================================
# 6. Everyday wording for the new helpers (60 new made-up messages; the classes that failed by code)
# =====================================================================================================================
def fresh(env):
    from mvp import config
    config.DRAFT_MODEL = False
    env["bot"].max_per_minute = None
    env["state"]["answers"]["mvp_interpret"] = lambda u: FELL
    return env


@pytest.mark.parametrize("text", ["emial my landlord the heater is broken again pls", "can u emial my coach that im late",
                                  "eamil my boss that i'm sick"])
def test_a_misspelt_email_still_starts_the_card(env, text):
    e = fresh(env)
    out = replies(e, text)
    assert any(r.startswith("Who should it go to?") for r in out), out
    assert "mvp_interpret" not in e["calls"]


@pytest.mark.parametrize("text", ["email it to me first so i can check", "send me a copy of that email",
                                  "email it to me so i can read it first", "can i get a copy of it",
                                  "send it to me before i send it"])
def test_a_copy_to_myself_with_a_card_open_is_read_by_code(env, text):
    e = fresh(env)
    replies(e, "email sam@example.com that the sink is broken")
    out = replies(e, text)
    assert out and out[0].startswith("Here's the draft as an email to yourself"), out
    assert "mvp_interpret" not in e["calls"]
    assert e["bot"].store.one("SELECT COUNT(*) AS n FROM drafts WHERE status='open'")["n"] in (0, 1)


def test_near_variant_a_copy_of_the_email_to_someone_else_is_not_to_me(env):
    from mvp.drafts import SELF_COPY
    assert not SELF_COPY.match("send a copy of that email to sam")
    assert not SELF_COPY.match("send me a copy of the recipe book")


@pytest.mark.parametrize("text", ["unsub me from disney plus", "unsub from netflix", "can u unsub me from spotify"])
def test_unsub_is_a_cancel_word_for_a_paid_service(env, text):
    from mvp import cancel
    assert cancel.request(text)["kind"] == "merchant", text
    out = replies(fresh(env), text)
    assert any("cancels on its website" in r or r.startswith("How do you pay") for r in out), out


def test_unsub_from_a_channel_is_still_youtube(yt):
    connect(yt)
    show(yt, "yt_1")
    assert tell(yt, "unsub me from that channel").startswith('Unsubscribe from "Kitchen Lab" on YouTube?')


@pytest.mark.parametrize("text", ["save this video to my youtube watch later", "add that video to my watch later",
                                  "put the video in my watch later"])
def test_watch_later_for_this_video(yt, text):
    connect(yt)
    show(yt, "yt_1")
    r = tell(yt, text)
    assert "youtube.com/watch?v=vidAAAAAAA1" in r and "mvp_interpret" not in yt["calls"], r


@pytest.mark.parametrize("text,how", [("can u unlike all my old instagram posts", "Your activity › Likes"),
                                      ("delete my instagram saves pls", "Saved"),
                                      ("remove my saved posts on instagram", "Saved"),
                                      ("clear my insta likes", "Your activity › Likes")])
def test_instagram_actions_no_app_may_do_are_said_plainly(yt, text, how):
    r = tell(yt, text)
    assert r.startswith("Instagram doesn't let any app") and how in r, r
    assert "mvp_interpret" not in yt["calls"] and not [a for a in actions(yt) if a["action"].startswith("link.")]


def test_unsave_this_gives_the_reels_own_link(yt):
    show(yt, "ig_1")
    r = tell(yt, "unsave this reel")
    assert r.startswith("Instagram doesn't let any app unsave for you") and "bookmark" in r and "https://" in r, r


def test_near_variants_of_instagram_words_that_are_not_an_instagram_action(yt):
    for text in ("delete my rules", "remove the saves from my list", "clear my list", "unlike"):
        r = tell(yt, text) or ""
        assert not r.startswith("Instagram doesn't let any app"), text


@pytest.mark.parametrize("ask", ["can u do it for me", "could u do it for me", "pls do it for me"])
def test_can_u_do_it_for_me_after_the_cancel_steps(env, ask):
    e = fresh(env)
    replies(e, "cancel my netflix")
    out = replies(e, ask)
    assert out and out[0].startswith("I can't cancel Netflix for you"), out


@pytest.mark.parametrize("text", ["help me send you my exports regularly",
                                  "how can i get my instagram saves to you every week",
                                  "can u pull my youtube likes automatically",
                                  "can i send my youtube history to you every month"])
def test_the_regular_export_question_in_more_words(env, text):
    e = fresh(env)
    out = replies(e, text)
    # "how can i ..." gets the steps, as slice W reads every "how do i" export question; the rest the facts
    assert out and (out[0].startswith("About regular exports:") or "export" in out[0].lower()), out
    assert "mvp_interpret" not in e["calls"]


def test_near_variant_a_library_question_about_saves_is_not_the_export_question(env):
    e = fresh(env)
    out = replies(e, "send me my instagram saves about pasta")
    assert not any(r.startswith("About regular exports:") for r in out)


@pytest.mark.parametrize("text", ["what version are u", "what version are you on", "are you up to date?",
                                  "which build is running", "r u on the latest version"])
def test_version_in_everyday_words(env, text):
    out = replies(fresh(env), text)
    assert out and out[0].startswith("I'm running build"), out


def test_near_variant_up_to_date_about_something_else_is_not_the_version(env):
    out = replies(fresh(env), "are my rules up to date?")
    assert not (out and out[0].startswith("I'm running build"))


# =====================================================================================================================
# 7. The Spanish lines of the 60 that went wrong live: words in code (no new interpreter intent)
# =====================================================================================================================
def test_a_spanish_channel_through_the_errand_form_is_never_a_merchant(env, monkeypatch):
    e = fresh(env)
    monkeypatch.setenv("MVP_ERRAND_PER_DAY", "30")
    e["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "unsupported", "reply": "UNSUP"}
    e["state"]["answers"]["mvp_errand"] = lambda u: {"errand": "cancel", "merchant_words": "ese canal"}
    out = replies(e, "desuscríbeme de ese canal")
    assert not any("way out of" in r or "cancels on its website" in r for r in out), out
    assert not e["bot"].store.cancellations(H)
    # near variant: a real merchant named through the same form is still the cancel helper
    e["state"]["answers"]["mvp_errand"] = lambda u: {"errand": "cancel", "merchant_words": "netflix"}
    out = replies(e, "quiero darme de baja de netflix")
    assert any("Netflix" in r for r in out), out


def test_spanish_unfollow_gives_the_instagram_link(yt):
    r = tell(yt, "deja de seguir a @made_up_cook en instagram")
    assert r.startswith("Instagram doesn't let any app unfollow for you") and "instagram.com/made_up_cook" in r, r
    r = tell(yt, "silencia a @made_up_cook")
    assert r.startswith("Instagram doesn't let any app mute for you"), r


@pytest.mark.parametrize("ask", ["hazlo tú por mí", "hazlo por mí", "cancélalo tú"])
def test_spanish_do_it_for_me_after_the_cancel_steps(env, ask):
    e = fresh(env)
    replies(e, "cancel my netflix")
    out = replies(e, ask)
    assert out and out[0].startswith("I can't cancel Netflix for you"), out


def test_spanish_mismatch_learns_and_spanish_export_question_gets_the_facts(slop, env):
    ask(slop, composer(GOOD, PENNE))
    items = slop["bot"].store.last_answer(H)["items"]
    assert say(slop, "el segundo... no, ese video no tenía nada que ver", FELL).startswith("Thanks, that helps.")
    assert len(feedback(slop["bot"])) == 1 and feedback(slop["bot"])[0][0] in items
    out = replies(fresh(env), "cómo te mando mis guardados de instagram cada mes")
    assert out and out[0].startswith("About regular exports:"), out


def test_a_spanish_rule_naming_an_app_reads_the_app():
    from mvp import grants
    assert grants.rule_named("cada domingo pon 3 recetas en mi ticktick").key == "ticktick"
    assert grants.rule_named("cada lunes añade 2 videos a mi todoist").key == "todoist"
    assert grants.rule_named("every sunday put 3 recipes in my ticktick").key == "ticktick"   # as before
    assert grants.rule_named("cada domingo mándame 3 recetas") is None
