"""The live check of 19 Nov 2026 (DESIGN.md section 17.L): findings F1 to F11 reproduced with the fakes, fixed by code
reads and fixed texts, each with near variants that must not be taken. Offline: the fake model of test_mvp, the fake
Google of slice Y, the practice merchant in a headless browser where one can start (skipped and counted where not).
Made-up names, example.com addresses and made-up handles only."""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round10_browser import (FINAL, NEVER_SAID, OUTCOME, WHY_NO_BROWSER, _practice, chromium_left,  # noqa: E402,E501
                                            own_words, truth_host)
from mvp.tests.test_round10_errand import e, form  # noqa: E402,F401  (e is a fixture)
from mvp.tests.test_round10_youtube import actions, connect, show, tell, yt  # noqa: E402,F401  (yt is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402

UTC = timezone.utc
FELL = {"intent": "chat", "reply": "FELL"}
needs_browser = pytest.mark.skipif(WHY_NO_BROWSER is not None, reason=f"no browser can start here: {WHY_NO_BROWSER}")
IG_HEAD = "Instagram doesn't let any app"


def calls(e, purpose="mvp_interpret"):
    return e["calls"].count(purpose)


def said_n(e, text, answer=FELL):
    """The person sends `text`; every reply to it (a list)."""
    e["state"]["answers"]["mvp_interpret"] = answer if callable(answer) else (lambda u: answer)
    n = len(e["ch"].outbox)
    e["bot"].on_message(H, text)
    return [t for _, _, t in e["ch"].outbox[n:]]


@pytest.fixture()
def op(env, monkeypatch):
    """The env person as the operator; nothing outside set up."""
    from mvp import config
    for k in ("MVP_BROWSER", "MVP_BROWSER_DEMO", "MVP_BROWSER_FOR", "MVP_BROWSER_MERCHANTS", "MVP_YT_CLIENT_ID",
              "MVP_YT_CLIENT_SECRET", "MVP_TICKTICK_TOKEN", "MVP_TODOIST_TOKEN", "MVP_WEBHOOK_URL",
              "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_OPERATOR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(config, "OPERATOR", H)
    env["bot"].max_per_minute = None
    env["clock"][0] = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)
    return env


@pytest.fixture()
def tester(op, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    return op


# =====================================================================================================================
# F1. A bare "I'm in" never changes the time zone
# =====================================================================================================================
TZ_MOVE = {"intent": "set_timezone", "timezone": "America/New_York"}


@pytest.mark.parametrize("text", ["im in", "i'm in", "im in now", "ok im signed in", "logged in", "I'm in!",
                                  "i'm logged in", "signed in"])
def test_a_bare_im_in_with_no_run_says_one_plain_line_and_never_moves_the_time_zone(op, text):
    from mvp import texts as T
    op["bot"].store.set_timezone(H, "America/Chicago")
    c0 = calls(op)
    assert said_n(op, text, TZ_MOVE) == [T.SIGNED_IN_NOTHING]
    assert calls(op) == c0 and op["bot"].store.person(H)["timezone"] == "America/Chicago"


@pytest.mark.parametrize("text", ["i'm in chicago now", "im in the mood for pasta", "i'm in london until sunday",
                                  "im into baking now"])
def test_a_place_or_anything_more_after_im_in_still_reaches_the_interpreter(op, text):
    c0 = calls(op)
    said_n(op, text)
    assert calls(op) == c0 + 1


def _final_state(bot, now, step="final_shown"):
    bot.store.set_state(f"browserrun:{H}", {"step": step, "key": "streamly", "name": "Streamly", "run_id": 99,
                                            "cid": None, "at": now.isoformat(), "started": now.isoformat(),
                                            "yes_hash": "x" * 64, "final_name": "Finish Cancellation",
                                            "final_tag": "button", "final_quote": "Your membership ends on 1 Dec 2026."})


def test_im_in_at_the_last_step_card_says_the_last_step_again(op, monkeypatch):
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(1)})
    _final_state(op["bot"], op["clock"][0])
    c0 = calls(op)
    out = said_n(op, "im in", TZ_MOVE)
    assert out == ["This is the last step. Streamly's page says: \"Your membership ends on 1 Dec 2026.\" The button "
                   "says \"Finish Cancellation\". I haven't pressed it. Reply \"yes cancel streamly\" to press it, or "
                   "\"stop\"."]
    assert calls(op) == c0 and op["bot"].store.person(H)["timezone"] == "America/New_York"
    assert op["bot"].store.get_state(f"browserrun:{H}")["step"] == "final_shown"   # the card still waits


@pytest.mark.parametrize("text", ["done", "ready", "continue"])
def test_at_the_last_step_card_other_go_on_words_keep_their_old_path(op, monkeypatch, text):
    """F1 reads the sign-in words only; "done", "ready", "continue" at the card go the way they went before."""
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(1)})
    _final_state(op["bot"], op["clock"][0])
    outs = said_n(op, text)
    assert not any(o.startswith("This is the last step.") for o in outs), outs
    assert op["bot"].store.get_state(f"browserrun:{H}")["step"] == "final_shown"


def test_im_in_after_a_hand_back_or_at_the_reminder_question_is_never_the_model(op, monkeypatch):
    from mvp import browser
    from mvp import texts as T
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(1)})
    _final_state(op["bot"], op["clock"][0], step="handed_back")
    c0 = calls(op)
    assert said_n(op, "im in", TZ_MOVE) == ["The browser is yours for now. Say \"stop\" to close it."]
    st = {"step": "reminder", "key": "streamly", "name": "Streamly", "cid": None, "at": op["clock"][0].isoformat(),
          "started": op["clock"][0].isoformat(), "offer_at": (op["clock"][0] + timedelta(days=8)).isoformat()}
    op["bot"].store.set_state(f"browserrun:{H}", st)
    assert said_n(op, "ok im signed in", TZ_MOVE) == [T.SIGNED_IN_NOTHING]
    assert op["bot"].store.get_state(f"browserrun:{H}")["step"] == "reminder"   # the question is still open
    assert calls(op) == c0


def test_im_in_while_a_youtube_code_waits_asks_google_instead(yt):
    tell(yt, "connect youtube")
    yt["g"].approve()
    assert tell(yt, "i'm signed in").startswith("YouTube is connected.")


# =====================================================================================================================
# F2. "what did you do for me" after the browser pressed the last button: what happened there, in the page's words
# =====================================================================================================================
QUOTE = "Your membership has been cancelled. You can watch until 1 Dec 2026."


def _pressed_run(op, status="page_says_cancelled", quote=QUOTE, final="Finish Cancellation"):
    st, now = op["bot"].store, op["clock"][0]
    cid = st.add_cancellation(H, "streamly", "web", status, at=now)
    rid = st.add_browser_run(H, "streamly", cid, "operator", at=now)
    st.update_browser_run(rid, final_name=final)
    st.end_browser_run(rid, status, at=now + timedelta(minutes=2), outcome_quote=quote)
    return cid


def test_the_receipts_say_what_the_browser_pressed_and_quote_the_page(op, monkeypatch):
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    _pressed_run(op)
    out = said_n(op, "what did you do for me")[-1]
    assert ("• pressed \"Finish Cancellation\" on Streamly's cancel page (a practice site) today at 9:02am, after your "
            f"\"yes cancel streamly\". The page then said: \"{QUOTE}\"") in out, out
    assert "helped with" not in out and "still open" not in out
    assert not NEVER_SAID.search(own_words(out)), out   # never the bot's own claim that it ended
    assert browser.route("streamly")["practice"]


def test_a_page_that_did_not_say_it_ended_is_said_so_and_a_run_stopped_before_the_press_is_still_open(op,
                                                                                                    monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    _pressed_run(op, status="page_unclear", quote="")
    out = said_n(op, "what did you do for me")[-1]
    assert "on Streamly's cancel page (a practice site)" in out and "The page didn't say it had ended" in out
    # near variant: a run handed back before the last button pressed nothing: the old count, no "pressed"
    op["bot"].store.x("DELETE FROM browser_runs")
    op["bot"].store.x("DELETE FROM cancellations")
    st, now = op["bot"].store, op["clock"][0]
    cid = st.add_cancellation(H, "streamly", "web", "handed_back", at=now)
    st.end_browser_run(st.add_browser_run(H, "streamly", cid, "operator", at=now), "handed_back", at=now)
    out = said_n(op, "what did you do for me")[-1]
    assert "pressed" not in out and "helped with 1 cancellation (1 still open)" in out


def test_with_the_demo_off_a_practice_run_is_still_named_and_never_said_to_have_ended(op):
    _pressed_run(op)
    out = said_n(op, "what did you do for me")[-1]
    assert "on Streamly's cancel page" in out and QUOTE in out and not NEVER_SAID.search(own_words(out))


@pytest.fixture()
def cvx(op, monkeypatch):
    """The operator with the browser on and the practice merchant (flow 1) in a headless stand-in."""
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "streamly")
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(1)})
    monkeypatch.setattr(browser, "make_host", lambda m: truth_host())
    yield op
    browser.close_all(op["bot"])
    assert chromium_left() == []


@needs_browser
def test_the_whole_run_im_in_at_the_last_step_then_the_receipt_in_the_pages_words(cvx):
    from mvp import browser
    for text in ("cancel my streamly", "do it for me", "allow streamly"):
        said_n(cvx, text)
    assert said_n(cvx, "I'm in") == ["Thanks. Going to the cancel page."]
    assert browser.wait(cvx["bot"], H, timeout=60) and last(cvx["ch"]) == FINAL
    c0 = calls(cvx)
    assert said_n(cvx, "im in", TZ_MOVE) == [FINAL]   # F1: the last step again, never a time zone
    assert said_n(cvx, "yes cancel streamly") == [OUTCOME]
    out = said_n(cvx, "what did you do for me")[-1]
    assert "pressed \"Finish Cancellation\" on Streamly's cancel page" in out and \
        "The page then said: \"Your membership has been cancelled. You can watch until 1 Dec 2026.\"" in out
    assert calls(cvx) == c0 and cvx["bot"].store.person(H)["timezone"] == "America/New_York"


# =====================================================================================================================
# F3. With the browser on but not for this merchant: the true reason (browser off: today's words, byte-equal)
# =====================================================================================================================
SWITCH_OP = ("Netflix cancels on its website. I can't do it for you yet: the browser is on, but Netflix isn't switched "
             "on for it, because I've never tried its cancel path on the real site. You can switch it on: the README's "
             "round 10 settings name the setting. Here's where it is:")


@pytest.mark.parametrize("mode", ["operator", "vm"])
def test_browser_on_netflix_not_switched_on_says_why_and_how_for_the_operator(op, monkeypatch, mode):
    monkeypatch.setenv("MVP_BROWSER", mode)
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    out = said_n(op, "can u cancel my netflix for me")[-1]
    assert out.startswith(SWITCH_OP + "\n1. "), out
    assert "never sign in as you" not in out and out.endswith("Tell me when, like \"friday\".")   # the steps, the offer
    out = said_n(op, "do it for me")[-1]
    assert out == ("I can't cancel Netflix for you yet: the browser is on, but Netflix isn't switched on for it, "
                   "because I've never tried its cancel path on the real site. You can switch it on: the README's "
                   "round 10 settings name the setting. The steps above are how to do it yourself. Want a reminder to "
                   "check it went through? Tell me when, like \"friday\".")
    assert said_n(op, "friday")[-1].startswith("OK. On Friday")   # the reminder question stayed open


def test_a_tester_who_may_have_the_browser_hears_that_the_person_running_it_can_switch_it_on(tester, monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_FOR", "all")
    out = said_n(tester, "cancel my spotify")[-1]
    assert out.startswith("Spotify cancels on its website. I can't do it for you yet: the browser is on, but Spotify "
                          "isn't switched on for it") and "The person who runs me can switch it on." in out
    assert "README" not in out


def test_a_merchant_with_no_browser_path_is_said_plainly(op, monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "operator")
    out = said_n(op, "cancel my peacock")[-1]
    assert out.startswith("Peacock cancels on its website. I can't do it for you: I only press buttons on sites whose "
                          "cancel path I've checked, and Peacock's isn't one of them yet. Here's where it is:"), out


def test_browser_off_the_old_words_byte_equal(op):
    from mvp import texts as T
    out = said_n(op, "cancel my netflix")[-1]
    assert out.startswith("Netflix cancels on its website. I can't do it for you, because I never sign in as you. "
                          "Here's where it is:\n1. ")
    assert said_n(op, "do it for me")[-1] == T.cancel_doit_cant("Netflix")


def test_a_tester_the_browser_is_not_for_keeps_the_old_words(tester, monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "netflix")
    out = said_n(tester, "cancel my netflix")[-1]
    assert out.startswith("Netflix cancels on its website. I can't do it for you, because I never sign in as you.")


# =====================================================================================================================
# F4 to F6. Actions on Instagram asked of the bot: one plain line, the pick's own link; nothing written or learned
# =====================================================================================================================
LINK = "https://example.com/itm_a"   # the made-up Instagram pick's own link (test_mvp's library)


def nothing_written(e):
    st = e["bot"].store
    return (st.todos(H) == [] and st.q("SELECT * FROM feedback WHERE handle=?", (H,)) == []
            and st.caption_feedback(H) == [])


@pytest.mark.parametrize("text,tap", [
    ("like that reel for me", "tap the heart"), ("can you like it on instagram", "tap the heart"),
    ("heart that post for me", "tap the heart"), ("comment nice on that reel", "tap the speech bubble"),
    ("could you comment \"so good\" on it", "tap the speech bubble"),
    ("leave a comment on that reel", "tap the speech bubble"), ("comment on that reel for me", "tap the speech bubble"),
    ("would you like it for me", "tap the heart"),
    ("share that to my story", "Add to story"), ("repost that reel", "tap the repost arrows"),
    ("send that reel to @made_up_friend", "tap the paper plane"),
    ("save that reel to my instagram collection called dinners", "hold the bookmark and pick \"dinners\""),
])
def test_an_instagram_action_on_the_pick_gets_the_plain_line_and_its_own_link(op, text, tap):
    show(op, "itm_a")
    c0 = calls(op)
    out = said_n(op, text, {"intent": "feedback", "feedback": "up"})[0]
    assert out.startswith(IG_HEAD) and "and I won't sign in as you." in out and tap in out and LINK in out, out
    assert calls(op) == c0 and nothing_written(op)


@pytest.mark.parametrize("text,word", [
    ("dm that creator", "Message"), ("follow that creator", "Follow"), ("block that account", "⋯ › Block"),
    ("follow @made_up_cook on instagram", "Follow"), ("please restrict them on insta", "⋯ › Restrict"),
])
def test_an_action_on_an_account_gets_the_accounts_own_profile_link(op, text, word):
    show(op, "itm_a")
    out = said_n(op, text)[0]
    hd = "made_up_cook" if "@made_up_cook" in text else "chef"
    assert out.startswith(IG_HEAD) and f"Tap to open @{hd}, then {word}: https://www.instagram.com/{hd}/" in out, out
    assert nothing_written(op)


@pytest.mark.parametrize("text,how", [
    ("remove a follower", "tap Followers, then Remove"), ("post this on my instagram", "tap + at the bottom"),
    ("delete my post on instagram", "⋯ › Delete"), ("like that reel for me", "open the post and tap the heart"),
])
def test_with_no_pick_in_view_the_line_says_how_to_do_it_in_the_app(op, text, how):
    out = said_n(op, text)[0]
    assert out.startswith(IG_HEAD) and how in out and nothing_written(op), out


def test_two_instagram_picks_and_that_reel_asks_which(op):
    show(op, "itm_a", "itm_b")
    out = said_n(op, "like that reel for me")[0]
    assert out.endswith("Which post? Say its number, or open it and do it yourself.")
    out = said_n(op, "like the second one for me")[0]
    assert "https://example.com/itm_b" in out


@pytest.mark.parametrize("text", ["i like that one", "liked it", "love that reel", "like that reel",
                                  "find me a reel i'd like", "comment on my draft", "follow up with my landlord",
                                  "save that for later", "share that with me by email", "i love this post",
                                  "follow that recipe", "post a reminder for me at 6pm",
                                  # a question about the post, never a request to tap (checked before the commit)
                                  "can you comment on that", "comment on this", "comment on that reel",
                                  "would you like it"])
def test_near_variants_are_never_the_instagram_line(op, text):
    show(op, "itm_a")
    outs = said_n(op, text)
    assert not any(o.startswith(IG_HEAD) for o in outs), (text, outs)


def test_feedback_words_and_the_thumb_still_learn(op):
    show(op, "itm_a")
    assert said_n(op, "👍") == ["Noted 👍"]
    assert op["bot"].store.q("SELECT kind FROM feedback WHERE handle=?", (H,)) == [{"kind": "up"}]


def test_a_youtube_pick_with_no_instagram_word_is_not_this_read(op):
    show(op, "itm_e")   # the library's YouTube video
    outs = said_n(op, "like that video for me")
    assert not any(o.startswith(IG_HEAD) for o in outs)


def test_the_instagram_read_comes_before_the_feedback_shopping_and_to_do_helpers(e):
    """F5 as it went live: the interpreter refused, the errand form said "buy" and the recipe's ingredients went on the
    shopping list. Now the Instagram read answers before both; and the form's buy without a buy word is refused."""
    show(e, "itm_a")
    e["bot"].store.set_last_answer(H, None, None, ["itm_a"], "test")
    form(e, {"errand": "post_act", "act": "buy", "target_words": "that reel"})
    out = said_n(e, "comment nice on that reel", {"intent": "unsupported"})
    assert out[0].startswith(IG_HEAD) and LINK in out[0] and "shopping list" not in "\n".join(out)
    assert calls(e, "mvp_errand") == 0 and nothing_written(e)


def test_the_errand_form_never_uses_an_act_the_message_does_not_say(e):
    from mvp.errand import built
    bot, person, now = e["bot"], e["bot"].store.person(H), e["clock"][0]
    f = {"errand": "post_act", "act": "buy", "target_words": "that reel"}
    assert built(bot, person, f, "comment nice on that reel", "answer 1", now) is None
    assert built(bot, person, f, "do that thing with that reel", "answer 1", now) is None
    # near variants: the act's own word, English or Spanish, is still used
    assert built(bot, person, dict(f, target_words="that one"), "buy that one", "answer 1", now) is not None
    f2 = {"errand": "post_act", "act": "book", "target_words": "ese restaurante"}
    assert built(bot, person, f2, "resérvame en ese restaurante", "answer 1", now) is not None


def test_save_to_a_collection_offers_my_own_list_and_yes_keeps_it_there(op):
    show(op, "itm_a")
    out = said_n(op, "save that reel to my instagram collection called dinners")[0]
    assert out.endswith("\nI can keep it on my own list called \"Dinners\" here instead: reply \"yes\".")
    assert nothing_written(op)
    said_n(op, "yes")
    rows = op["bot"].store.todos(H)
    assert [(r["list"], r["text"].startswith("Lemon garlic pasta")) for r in rows] == [("dinners", True)], rows


def test_after_the_collection_offer_another_message_adds_nothing(op):
    show(op, "itm_a")
    said_n(op, "save that reel to my instagram collection called dinners")
    said_n(op, "thanks")
    said_n(op, "yes")
    assert op["bot"].store.todos(H) == []


def test_a_youtube_pick_and_youtube_connected_also_offers_the_playlist(yt):
    connect(yt)
    show(yt, "yt_1")
    out = tell(yt, "save that video to my instagram collection called dinners")
    assert out.startswith(IG_HEAD) and "add it to my dinners playlist" in out
    assert not actions(yt, "youtube.playlist_add")


# =====================================================================================================================
# F7, F8. The connector menu, built from the registry; "connect <anything>" read by code
# =====================================================================================================================
MENU_WORDS = ["what can i connect you to", "what can I connect", "what connectors do you have",
              "which apps do you work with", "what apps can you use", "connect", "integrations",
              "what can you hook up to", "what can you connect to", "What integrations do you have?"]


@pytest.mark.parametrize("text", MENU_WORDS)
def test_every_menu_wording_gets_the_menu_by_code(op, text):
    from mvp import texts as T
    c0 = calls(op)
    out = said_n(op, text)[-1]
    assert out.startswith(T.MENU_HEAD) and calls(op) == c0, out


def test_the_operators_menu_names_every_connector_its_state_and_the_words(op, monkeypatch):
    from mvp import connectors as C
    monkeypatch.setenv("MVP_TICKTICK_TOKEN", "made-up-token-value-123")
    out = said_n(op, "what can i connect you to")[-1]
    for con in C.CONNECTORS.values():
        assert f"• {con.name[:1].upper() + con.name[1:]}:" in out, con.key
    assert "• TickTick: connected." in out and "• Todoist: not set up yet (say \"connect todoist\")." in out
    assert "(say \"connect my webhook\")" in out and "connect youtube" in out
    assert "Browser for cancelling: off (the README's round 10 settings say how to turn it on)." in out
    assert "• Instagram: no app may act on a personal account" in out and "Email to you:" in out
    assert "made-up-token-value-123" not in out and "Only the person who runs me" not in out


def test_a_tester_sees_what_they_can_connect_and_one_line_for_the_rest(tester):
    out = said_n(tester, "what can i connect you to")[-1]
    assert "• YouTube: not set up on this bot yet." in out and "Google Cloud" not in out
    assert out.endswith("Only the person who runs me can set up Reminders and Calendar on the Mac, TickTick, Todoist, "
                        "a webhook and sending email from a mailbox.")
    assert "• TickTick:" not in out and "README" not in out
    assert "Browser for cancelling: off on this bot" in out


def test_a_connector_added_to_the_registry_is_named_by_the_menu(op, tester, monkeypatch):
    """The menu is built from connectors.CONNECTORS, never from a hand-kept list."""
    from mvp import config
    from mvp import connectors as C
    new = dict(C.CONNECTORS)
    new["zorbnote"] = C.Connector(key="zorbnote", name="Zorbnote", module="zorbnote_missing",
                                  actions={"todo": "zorbnote.add"}, kind="token", where="in Zorbnote",
                                  needs_check=False)
    monkeypatch.setattr(C, "CONNECTORS", new)
    out = said_n(tester, "what can i connect")[-1]
    assert "Zorbnote" in out
    monkeypatch.setattr(config, "OPERATOR", H)
    out = said_n(tester, "what can i connect")[-1]
    assert "• Zorbnote: not set up yet (say \"connect zorbnote\")." in out
    # the short form after "I can't connect to X yet" comes from the same registry
    assert "Zorbnote" in said_n(tester, "connect notion")[-1]


def test_the_short_form_after_an_app_with_no_connector_is_true_to_this_person(op, tester, monkeypatch):
    """F8: "I can't connect to X yet", then the menu's short form: what this person can have here, names only."""
    from mvp import config
    from mvp import connectors as C
    out = said_n(tester, "connect notion")[-1]
    assert out == "I can't connect to Notion yet. I can reach email and a calendar link; say \"what can I connect\" for how."
    assert said_n(tester, "can you hook up my google calendar")[-1].startswith(
        "I can't connect to Google Calendar yet. I can reach email and a calendar link;")
    monkeypatch.setenv("MVP_YT_CLIENT_ID", "made-up-client.example.com")
    monkeypatch.setenv("MVP_YT_CLIENT_SECRET", "made-up-client-secret")
    assert "a calendar link and YouTube;" in said_n(tester, "connect notion")[-1]
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setenv("MVP_BROWSER", "operator")
    out = said_n(tester, "connect notion")[-1]
    for key, con in C.CONNECTORS.items():
        assert ({"mac": "Reminders and Calendar on the Mac", "webhook": "a webhook"}.get(key, con.name)) in out, key
    assert "a browser for cancelling;" in out and "made-up" not in out


def test_the_menu_never_shows_an_address_or_a_value(op, monkeypatch):
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "made.up.sender@example.com")
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("MVP_SMTP_HOST", "smtp.example.com")
    op["bot"].store.set_email(H, "made.up.person@example.com", verified=True)
    out = said_n(op, "what can i connect")[-1]
    from mvp import texts as T
    assert out.startswith(T.MENU_HEAD) and "• Email to you: on." in out
    assert "example.com" not in out and "abcd" not in out


def test_the_menu_with_the_browser_on_and_youtube_set_up(op, monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    monkeypatch.setenv("MVP_YT_CLIENT_ID", "made-up-client.example.com")
    monkeypatch.setenv("MVP_YT_CLIENT_SECRET", "made-up-client-secret")
    out = said_n(op, "what can i connect")[-1]
    assert "• Browser for cancelling: on, on my side (you watch it on the test page), for you only. Sites: streamly " \
           "(a practice site). Say \"cancel my streamly\"." in out
    assert "• YouTube: not connected yet (say \"connect youtube\")." in out
    assert "made-up-client" not in out


def test_what_are_you_connected_to_also_names_what_isnt_connected_yet(op):
    out = said_n(op, "what are you connected to")[-1]
    assert out.startswith("Here's where I can put things for you:")
    assert "\nNot connected yet:\n• TickTick: not set up yet (say \"connect ticktick\")." in out
    assert "connect youtube" in out


@pytest.mark.parametrize("text,start", [
    ("connect netflix", "There's nothing to connect for Netflix. Say \"cancel my netflix\" when you want out"),
    ("connect spotify", "There's nothing to connect for Spotify. Say \"cancel my spotify\""),
    ("connect my instagram", "Instagram doesn't let any app connect to a personal account, so there's nothing to "
                             "connect"),
    ("connect my gmail", "I don't sign in to Gmail, but email works"),
    ("connect my email", "I don't sign in to your email, but email works"),
    ("hook up my outlook", "I don't sign in to Outlook, but email works"),
    ("connect notion", "I can't connect to Notion yet. I can reach email, a calendar link, "),
    ("connect zorblax", "I can't connect to Zorblax yet. I can reach email, a calendar link, "),
    ("can you link my brightbox account", "I can't connect to Brightbox yet."),
])
def test_connect_anything_is_read_by_code(op, text, start):
    c0 = calls(op)
    out = said_n(op, text)[-1]
    assert out.startswith(start) and calls(op) == c0, out


def test_connect_my_gmail_for_the_operator_says_where_the_mailbox_goes(op, tester):
    from mvp import config
    out = said_n(tester, "connect my gmail")[-1]
    assert "app password" not in out and out.endswith("a draft you send from your mail app.")
    config.OPERATOR = H
    op["ch"].name = "web"
    out = said_n(op, "connect my gmail")[-1]
    assert out.endswith("add your address and its app password in the Connections panel beside this chat.")


def test_connect_instagram_says_how_the_export_reaches_the_bot_and_that_works_by_code(op):
    out = said_n(op, "connect my instagram")[-1]
    assert "https://accountscenter.instagram.com/info_and_permissions/dyi" in out and "how do i send you my instagram export" in out
    c0 = calls(op)
    assert "Accounts Center" in said_n(op, "how do i send you my instagram export")[-1] and calls(op) == c0


@pytest.mark.parametrize("text", ["connect four strategy videos", "connect with people who cook", "connect the dots",
                                  "connect four", "how do i connect with my friends more"])
def test_words_after_connect_that_are_not_an_app_go_the_usual_way(op, text):
    c0 = calls(op)
    out = said_n(op, text)[-1]
    assert calls(op) == c0 + 1 and not out.startswith("I can't connect to"), out


# =====================================================================================================================
# F9. Two or more things to cancel in one message: never one dropped silently
# =====================================================================================================================
def test_two_things_to_cancel_the_first_is_handled_and_the_second_is_said_with_its_words(op):
    out = said_n(op, "can you cancel my spotify and my gym membership")
    assert out[0].startswith("Spotify cancels on its website.")
    assert out[1] == ("You also asked to cancel your gym membership. When this one is done, say \"cancel my gym "
                      "membership\".")
    assert said_n(op, "cancel my gym membership")[-1].startswith("Which gym")


def test_three_things_are_all_said_and_the_first_in_the_message_goes_first(op):
    out = said_n(op, "cancel my hulu, netflix and my brightbox subscription")
    assert out[0].startswith("How do you pay for Hulu") or "Hulu" in out[0].split("\n")[0], out[0]
    assert out[-1] == ("You also asked to cancel Netflix and Brightbox. One at a time: when this one is done, say "
                       "\"cancel my netflix\", then \"cancel my brightbox\".")


def test_no_second_model_call_and_one_thing_is_as_before(op):
    c0 = len(op["calls"])
    said_n(op, "cancel netflix and spotify please")
    assert len(op["calls"]) == c0
    for text in ("cancel my netflix", "cancel my netflix and tell me when it ends"):
        outs = said_n(op, text)
        assert not any("You also asked" in o for o in outs), (text, outs)


# =====================================================================================================================
# F10. YouTube with no Google client: the person who runs the bot is told how; a tester gets the plain line
# =====================================================================================================================
@pytest.mark.parametrize("text", ["connect youtube", "unsubscribe me from youtube channels i never watch"])
def test_the_page_operator_is_told_how_to_set_youtube_up(op, text):
    from mvp import texts as T
    op["ch"].name = "web"
    out = said_n(op, text)[-1]
    assert out.startswith("YouTube isn't set up on this bot yet. In a Google Cloud project, make an OAuth client of the "
                          "type \"TVs and Limited Input devices\", put its client id and secret in the Connections panel "
                          "beside this chat, then say \"connect youtube\".") and T.YT_FEED in out, out


@pytest.mark.parametrize("text", ["connect youtube", "unsubscribe me from youtube channels i never watch"])
def test_a_tester_gets_the_plain_youtube_line(tester, text):
    from mvp import texts as T
    tester["ch"].name = "web"
    assert said_n(tester, text)[-1] == T.YT_NOT_SET_UP


# =====================================================================================================================
# F11. The help says the apps, truthful to this run's switches (at most two new lines)
# =====================================================================================================================
@pytest.mark.parametrize("text", ["help", "what can you do for me", "what can you do?", "What can u do"])
def test_the_help_has_one_apps_line_and_no_browser_line_when_it_is_off(op, text):
    from mvp import config
    from mvp import texts as T
    c0 = calls(op)
    out = said_n(op, text)[-1]
    assert out == T.HELP + "\nApps: \"what can I connect\" shows what I can reach here and how to connect each.\n" + \
        T.build_line(config.BUILD)
    assert calls(op) == c0 and "browser" not in out.lower() and "connect youtube" not in out


def test_the_help_with_the_browser_on_and_youtube_set_up_is_two_lines_longer_at_most(op, monkeypatch):
    from mvp import config
    from mvp import texts as T
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "netflix")
    monkeypatch.setenv("MVP_YT_CLIENT_ID", "made-up-client.example.com")
    monkeypatch.setenv("MVP_YT_CLIENT_SECRET", "made-up-client-secret")
    out = said_n(op, "help")[-1]
    old = T.HELP + "\n" + T.build_line(config.BUILD)
    assert len(out.split("\n")) - len(old.split("\n")) == 2
    assert "; YouTube: \"connect youtube\"." in out and \
        "Cancelling for you: I can do it in a browser on netflix; say \"cancel my netflix\"." in out


def test_a_tester_the_browser_is_not_for_gets_no_browser_line(tester, monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "netflix")
    assert "Cancelling for you" not in said_n(tester, "help")[-1]


# =====================================================================================================================
# What worked on 19 Nov keeps working (the findings' "What worked" list, with the fakes)
# =====================================================================================================================
def test_what_worked_unfollow_on_instagram_and_the_ticktick_steps(op):
    show(op, "itm_a")
    out = said_n(op, "unfollow that creator on instagram")[-1]
    assert out.startswith("Instagram doesn't let any app unfollow for you, and I won't sign in as you. Tap to open "
                          "@chef, then Following › Unfollow: https://www.instagram.com/chef/")
    assert said_n(op, "connect ticktick")[-1].startswith("I can add tasks to your TickTick")


def test_the_new_reads_are_all_inside_hooks_the_round_9_rule_text_checks_wrap():
    """F1 sits in browser_reads, F4 to F6 in youtube_reads (5b), F7 and F8 in place_reads (8), F9 in cancel_reads
    (6), F2 in receipts_reads (8): each is a hook test_round9_merge wraps for the 159 rule texts and 123 phrasings."""
    src = open(os.path.join(os.path.dirname(HERE), "tests", "test_round9_merge.py"), encoding="utf-8").read()
    for hook in ("browser_reads", "youtube_reads", "place_reads", "cancel_reads", "receipts_reads"):
        assert hook in src, hook
    assert re.search(r"SIGNED_IN", open(os.path.join(os.path.dirname(HERE), "browser.py")).read())
