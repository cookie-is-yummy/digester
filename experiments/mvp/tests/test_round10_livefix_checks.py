"""The check of the live fixes of 19 Nov (DESIGN.md section 17.L, "17.L check"): an independent checker tried to break
F1 to F11 with new everyday messages, near-variant traps, the connector menu, the Instagram class and the practice
merchant's nine flows, and fixed what broke. Offline: the fake model of test_mvp, the fake Google of slice Y, the
practice merchant in a headless browser where one can start (skipped and counted where not). Made-up names,
example.com addresses and made-up handles only."""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round10_browser import NEVER_SAID, _practice, chromium_left, own_words, truth_host  # noqa: E402
from mvp.tests.test_round10_livefix import (FELL, IG_HEAD, TZ_MOVE, _final_state, calls, needs_browser,  # noqa: E402
                                            nothing_written, op, said_n, tester)  # noqa: F401  (op, tester: fixtures)
from mvp.tests.test_round10_youtube import connect, show, tell, yt  # noqa: E402,F401  (yt is a fixture)
from mvp.tests.test_slice2 import H  # noqa: E402

LINK = "https://example.com/itm_a"


# =====================================================================================================================
# (1) "I'm in" with the fillers a person texts: never a time zone (the model moved "im in lol" to another zone)
# =====================================================================================================================
@pytest.mark.parametrize("text", ["im in lol", "k im in", "kk im in", "yeah im in now", "im in now haha",
                                  "ok so im logged in", "ya im signed in lol", "cool im in"])
def test_im_in_with_fillers_and_no_run_says_the_plain_line_and_never_moves_the_time_zone(op, text):
    from mvp import texts as T
    op["bot"].store.set_timezone(H, "America/Chicago")
    c0 = calls(op)
    assert said_n(op, text, TZ_MOVE) == [T.SIGNED_IN_NOTHING]
    assert calls(op) == c0 and op["bot"].store.person(H)["timezone"] == "America/Chicago"


@pytest.mark.parametrize("text", ["k im in", "im in lol"])
def test_im_in_with_fillers_at_the_last_step_card_says_the_card_again(op, monkeypatch, text):
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(1)})
    _final_state(op["bot"], op["clock"][0])
    out = said_n(op, text, TZ_MOVE)
    assert len(out) == 1 and out[0].startswith("This is the last step. Streamly's page says:"), out
    assert op["bot"].store.get_state(f"browserrun:{H}")["step"] == "final_shown"


@pytest.mark.parametrize("text", ["im in london now lol", "im in the mood for tacos", "k im in chicago",
                                  "im into baking lol", "im in for friday"])
def test_a_place_or_anything_more_still_reaches_the_interpreter(op, text):
    c0 = calls(op)
    said_n(op, text)
    assert calls(op) == c0 + 1


# =====================================================================================================================
# (2) The connector menu: texting words and Spanish by code; "connect to other apps" is never an app's name
# =====================================================================================================================
@pytest.mark.parametrize("text", ["wat apps can u connect with", "do u have integrations", "what stuff can u hook up to",
                                  "can u connect to other apps", "what connectors r there", "list ur integrations",
                                  "which apps do u work with lol", "what can u even connect to",
                                  "a que apps te puedes conectar", "que puedo conectar contigo",
                                  "qué integraciones tienes"])
def test_the_menu_in_texting_words_and_spanish_is_read_by_code(op, tester, text):
    from mvp import texts as T
    c0 = calls(tester)
    out = said_n(tester, text)[-1]
    assert out.startswith(T.MENU_HEAD) and calls(tester) == c0, out
    assert "Other Apps" not in out


@pytest.mark.parametrize("text", ["what apps r u connected to rn", "what r u connected to"])
def test_what_r_u_connected_to_is_the_connected_answer(op, text):
    c0 = calls(op)
    out = said_n(op, text)[-1]
    assert out.startswith("Here's where I can put things for you:") and calls(op) == c0, out


@pytest.mark.parametrize("text", ["connect to other apps", "connect with other stuff", "link something"])
def test_words_after_connect_that_name_no_app_never_become_one(op, text):
    out = "\n".join(said_n(op, text))
    assert not out.startswith("I can't connect to"), out


@pytest.mark.parametrize("text", ["what can you do", "what apps do you like", "what can you make with chicken",
                                  "can you connect me with a cook", "do you have any recipes"])
def test_near_variants_of_the_menu_are_never_the_menu(op, text):
    from mvp import texts as T
    assert not any(o.startswith(T.MENU_HEAD) for o in said_n(op, text))


def test_a_new_connector_of_the_sign_in_kind_is_never_told_youtubes_google_steps(op, monkeypatch):
    """A registry entry of the "oauth" kind that is not set up: the plain state, never YouTube's Google steps."""
    from mvp import connectors as C
    new = dict(C.CONNECTORS)
    new["zorbcal"] = C.Connector(key="zorbcal", name="Zorbcal", module="zorbcal_missing",
                                 actions={"todo": "zorbcal.add"}, kind="oauth", where="in Zorbcal", needs_check=False)
    monkeypatch.setattr(C, "CONNECTORS", new)
    out = said_n(op, "what can i connect")[-1]
    line = next(x for x in out.split("\n") if x.startswith("• Zorbcal:"))
    assert line == "• Zorbcal: not set up on this bot yet.", line
    yt_line = next(x for x in out.split("\n") if x.startswith("• YouTube:"))
    assert "Google Cloud" in yt_line   # YouTube's own line keeps its steps for the operator


def test_a_new_connector_of_the_token_kind_shows_for_the_operator_and_in_the_testers_operator_line(op, monkeypatch):
    from mvp import config
    from mvp import connectors as C
    new = dict(C.CONNECTORS)
    new["zorbnote"] = C.Connector(key="zorbnote", name="Zorbnote", module="zorbnote_missing",
                                  actions={"todo": "zorbnote.add"}, kind="token", where="in Zorbnote", needs_check=False)
    monkeypatch.setattr(C, "CONNECTORS", new)
    out = said_n(op, "what can i connect")[-1]
    assert "• Zorbnote: not set up yet (say \"connect zorbnote\")." in out
    assert "• Zorbnote: not set up yet (say \"connect zorbnote\")." in said_n(op, "what are you connected to")[-1]
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    out = said_n(op, "what can i connect")[-1]
    assert "• Zorbnote" not in out and "Zorbnote" in out.split("\n")[-1]   # one line: only the person who runs me
    assert "Zorbnote" not in said_n(op, "connect notion")[-1]   # a tester's short form names what they can have


SECRETS = {"MVP_TICKTICK_TOKEN": "tt-made-up-secret-1234", "MVP_TODOIST_TOKEN": "td-made-up-secret-5678",
           "MVP_WEBHOOK_URL": "https://hooks.example.com/made-up?key=wh-made-up-secret-90",
           "MVP_MAILBOX_ADDRESS": "made.up.sender@example.com", "MVP_MAILBOX_APP_PASSWORD": "abcd efgh ijkl mnop",
           "MVP_YT_CLIENT_ID": "made-up-client-id.example.com", "MVP_YT_CLIENT_SECRET": "made-up-client-secret"}
SHOWN_NEVER = re.compile(r"made-up|made\.up|abcd efgh|hooks\.example|\?key=|wh-|tt-|td-|someone\.else")


@pytest.mark.parametrize("who", ["operator", "tester"])
def test_no_token_address_client_id_or_url_with_a_query_in_any_connector_answer(op, monkeypatch, who):
    from mvp import config
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    op["bot"].store.set_email(H, "made.up.person@example.com", verified=True)
    op["bot"].store.set_email("+15559999", "someone.else@example.com", verified=True)
    if who == "tester":
        monkeypatch.setattr(config, "OPERATOR", "+15559999")
    op["ch"].name = "web"
    for text in ("what can i connect", "what are you connected to", "connect my gmail", "connect notion",
                 "connect netflix", "connect my instagram", "connect youtube", "help", "what can u do",
                 "connect my webhook", "check my ticktick", "do u have integrations"):
        for out in said_n(op, text):
            assert not SHOWN_NEVER.search(out), (text, out)
            assert not re.search(r"https?://\S+\?\S+=", out), (text, out)


TESTER_NEVER = re.compile(r"README|Connections panel|MVP_|settings file|Google Cloud|chmod|app password|restart me|"
                          r"switch it on: the README", re.I)


@pytest.mark.parametrize("browser_on", [False, True])
def test_a_tester_is_never_told_to_do_what_only_the_operator_can(tester, monkeypatch, browser_on):
    if browser_on:
        monkeypatch.setenv("MVP_BROWSER", "vm")
        monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    tester["ch"].name = "web"
    for text in ("what can i connect", "what are you connected to", "connect my gmail", "connect outlook",
                 "connect notion", "connect youtube", "unsubscribe me from youtube channels i never watch",
                 "connect ticktick", "connect todoist", "connect my webhook", "connect my mac", "help",
                 "cancel my netflix", "connect netflix", "connect streamly", "can u connect to other apps"):
        for out in said_n(tester, text):
            assert not TESTER_NEVER.search(out), (text, out)
        tester["bot"].store.clear_pending(H)
        tester["bot"].store.set_state(f"cancelask:{H}", None)


def test_connect_netflix_with_the_browser_on_for_streamly_only_says_the_truth(op, monkeypatch):
    monkeypatch.setenv("MVP_BROWSER", "vm")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    op["ch"].name = "web"
    out = said_n(op, "connect netflix")[-1]
    assert out == "There's nothing to connect for Netflix. Say \"cancel my netflix\" when you want out, and I'll help."
    out = said_n(op, "connect streamly")[-1]
    assert out.startswith("There's nothing to connect for Streamly.") and "practice site" in out


def test_the_help_names_only_sites_the_browser_can_do_and_says_the_practice_one(op, monkeypatch):
    """A key in MVP_BROWSER_MERCHANTS with no checked path (or no merchant at all) is never named as one it can do."""
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_DEMO", "1")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "peacock,zorbflix")
    out = said_n(op, "help")[-1]
    assert "Cancelling for you: I can do it in a browser on Streamly (a practice site); say \"cancel my streamly\"." \
        in out, out
    assert "peacock" not in out.lower() and "zorbflix" not in out.lower()
    monkeypatch.delenv("MVP_BROWSER_DEMO")
    assert "Cancelling for you" not in said_n(op, "help")[-1]   # nothing it can do: no line at all
    menu = said_n(op, "what can i connect")[-1]
    assert "Say \"cancel my peacock\"" not in menu and "Say \"cancel my zorbflix\"" not in menu


def test_the_menu_after_delete_my_data_shows_nothing_of_before(yt):
    """YouTube connected, then "delete my data": the person is gone (people.json does not bring them back), so there is
    no menu, no state and no sign-in left to show."""
    from mvp import texts as T
    from mvp import tokens
    connect(yt)
    assert "• YouTube: connected." in tell(yt, "what can i connect")
    yt["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    tell(yt, "delete my data")
    tell(yt, "YES")
    assert yt["bot"].store.person(H) is None and not tokens.exists(H, "youtube")
    out = tell(yt, "what can i connect")
    assert out is None or not out.startswith(T.MENU_HEAD), out
    yt["bot"].load_people()   # a deleted person is not set up again from the file
    assert yt["bot"].store.person(H) is None
    assert yt["bot"].store.q("SELECT * FROM connections WHERE handle=?", (H,)) == []


# =====================================================================================================================
# (3) The Instagram class: Spanish asks by code; a caption's own "like and follow" is never the person asking
# =====================================================================================================================
@pytest.mark.parametrize("text,tap", [
    ("dale like a ese reel por mi", "tap the heart"), ("dale like a ese reel", "tap the heart"),
    ("ponle un corazon a esa foto", "tap the heart"), ("comenta que rico en ese reel", "tap the speech bubble"),
    ("deja un comentario en ese reel", "tap the speech bubble"), ("comparte ese reel en mi historia", "Add to story"),
    ("guarda ese reel en mi coleccion de instagram llamada cenas", "hold the bookmark and pick \"cenas\""),
])
def test_spanish_instagram_asks_get_the_plain_line_and_the_picks_link(op, text, tap):
    show(op, "itm_a")
    c0 = calls(op)
    out = said_n(op, text, {"intent": "feedback", "feedback": "up"})[0]
    assert out.startswith(IG_HEAD) and tap in out and LINK in out, out
    assert calls(op) == c0 and nothing_written(op)


@pytest.mark.parametrize("text,word", [("sigue a esa cuenta", "Follow"), ("mandale un mensaje a ese creador", "Message")])
def test_spanish_asks_about_an_account_get_its_profile(op, text, word):
    show(op, "itm_a")
    out = said_n(op, text)[0]
    assert out.startswith(IG_HEAD) and f"then {word}: https://www.instagram.com/chef/" in out, out


@pytest.mark.parametrize("text", ["me gusta ese", "me encanta", "me gusta ese reel", "comenta", "dale",
                                  "sigue asi", "guardalo para despues", "comparte eso conmigo por email",
                                  "que opinas de ese reel"])
def test_spanish_near_variants_are_never_the_instagram_line(op, text):
    show(op, "itm_a")
    c0 = calls(op)
    outs = said_n(op, text)
    assert not any(o.startswith(IG_HEAD) for o in outs), (text, outs)
    assert calls(op) == c0 + 1


def _caption_item(e):
    """A made-up reel whose caption asks the viewer to like, follow, comment and share."""
    import json
    with open(e["lib"] / "corpus" / "items.jsonl", "a") as f:
        f.write(json.dumps({"id": "itm_cta", "platform": "instagram", "source_url": "https://example.com/itm_cta",
                            "caption": "Garlic noodles in 10 min\nLike and follow for more!\nComment RECIPE and I'll "
                                       "DM you\nShare this to your story\nSave it to your collection",
                            "interaction_kinds": ["save"],
                            "platform_data": {"owner_handle": "made_up_noodles", "owner_relation": "following"}}) + "\n")
    with open(e["lib"] / "corpus" / "interactions.jsonl", "a") as f:
        f.write(json.dumps({"item_id": "itm_cta", "kind": "save", "at": "2026-03-01T10:00:00+00:00"}) + "\n")
    e["bot"].views.clear()   # the view is read again with the new item


@pytest.mark.parametrize("text", ["👍", "thanks", "more like this", "i liked that one", "love it", "ok", "nice",
                                  "like and follow for more", "comment RECIPE", "follow for more"])
def test_a_caption_that_says_like_and_follow_never_makes_the_bot_answer_as_if_asked(op, text):
    _caption_item(op)
    show(op, "itm_cta")
    outs = said_n(op, text)
    assert not any(o.startswith(IG_HEAD) for o in outs), (text, outs)
    st = op["bot"].store
    assert st.todos(H) == [] and st.caption_feedback(H) == []


@pytest.mark.parametrize("text", ["i liked that one", "love it", "liked it", "love that reel"])
def test_feedback_words_still_reach_the_interpreter_and_learn(op, text):
    show(op, "itm_a")
    c0 = calls(op)
    outs = said_n(op, text, {"intent": "feedback", "feedback": "up"})
    assert calls(op) == c0 + 1 and not any(o.startswith(IG_HEAD) for o in outs)
    assert op["bot"].store.q("SELECT kind FROM feedback WHERE handle=?", (H,)) == [{"kind": "up"}]


@pytest.mark.parametrize("text", ["save this", "save it", "save that for later", "save this to my list"])
def test_save_with_no_instagram_word_keeps_its_old_path(op, text):
    show(op, "itm_a")
    outs = said_n(op, text)
    assert not any(o.startswith(IG_HEAD) for o in outs), (text, outs)


@pytest.mark.parametrize("text", ["every friday send me reels i would like", "every friday at 6pm send me reels to like",
                                  "cada viernes mandame reels que me gusten"])
def test_a_rule_text_with_like_is_still_a_rule_for_the_interpreter(op, text):
    show(op, "itm_a")
    c0 = calls(op)
    outs = said_n(op, text)
    assert calls(op) == c0 + 1 and not any(o.startswith(IG_HEAD) for o in outs)


# =====================================================================================================================
# (4) The practice merchant's nine flows end to end, and the receipts line (F2) for each outcome
# =====================================================================================================================
@pytest.fixture()
def flowbot(op, monkeypatch):
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setenv("MVP_BROWSER_MERCHANTS", "streamly")
    monkeypatch.setattr(browser, "make_host", lambda m: truth_host())
    yield op
    browser.close_all(op["bot"])
    assert chromium_left() == []


def _run_flow(e, monkeypatch, flow, ending):
    from mvp import browser
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(flow, practice=True)})
    for t in ("cancel my streamly", "do it for me", "allow streamly", "I'm in"):
        said_n(e, t)
    assert browser.wait(e["bot"], H, timeout=60)
    st = e["bot"].store.get_state(f"browserrun:{H}") or {}
    if st.get("step") == "final_shown":
        said_n(e, "yes cancel streamly" if ending == "yes" else "stop")
    elif st.get("step") in ("wall", "handed_back"):
        said_n(e, "I'm in" if ending == "yes" else "stop")
        browser.wait(e["bot"], H, timeout=60)
    return said_n(e, "what did you do for me")[-1]


PRESSED = {1: "Finish Cancellation", 2: "Finish Cancellation", 3: "Finish Cancellation", 4: "Confirm cancellation",
           7: "No thanks, finish cancelling", 8: "Finish Cancellation"}


@needs_browser
@pytest.mark.parametrize("flow", list(range(1, 10)))
def test_each_flow_with_the_yes_the_receipt_lists_only_what_was_pressed(flowbot, monkeypatch, flow):
    out = _run_flow(flowbot, monkeypatch, flow, "yes")
    runs = flowbot["bot"].store.browser_runs_of(H)
    assert len(runs) == 1
    if flow in PRESSED:   # pressed after the yes, and the page said cancelled: its own words
        assert runs[0]["status"] == "page_says_cancelled"
        assert (f"• pressed \"{PRESSED[flow]}\" on Streamly's cancel page (a practice site) today at 9am, after your "
                "\"yes cancel streamly\". The page then said: \"Your membership has been cancelled. You can watch until "
                "1 Dec 2026.\"") in out, out
        assert "helped with" not in out
    else:   # a sign-in wall (5), a check (6), a typed reason (9): handed back, nothing final pressed
        assert runs[0]["status"] in ("handed_back", "stopped") and not runs[0]["outcome_quote"]
        assert "pressed" not in out and "helped with 1 cancellation (1 still open)" in out, out
    assert not NEVER_SAID.search(own_words(out)), out


@needs_browser
@pytest.mark.parametrize("flow", [1, 4, 7])
def test_stopped_by_the_person_at_the_last_step_lists_nothing_as_pressed(flowbot, monkeypatch, flow):
    out = _run_flow(flowbot, monkeypatch, flow, "stop")
    assert flowbot["bot"].store.browser_runs_of(H)[0]["status"] == "stopped"
    assert "pressed" not in out and "The page" not in out and "helped with 1 cancellation (1 still open)" in out, out


def test_an_offer_accepted_page_after_the_press_says_the_plan_goes_on(op):
    from datetime import timedelta
    st, now = op["bot"].store, op["clock"][0]
    cid = st.add_cancellation(H, "streamly", "web", "offer_taken", at=now)
    rid = st.add_browser_run(H, "streamly", cid, "operator", at=now)
    st.update_browser_run(rid, final_name="Finish Cancellation")
    st.end_browser_run(rid, "offer_taken", at=now + timedelta(minutes=2))
    out = said_n(op, "what did you do for me")[-1]
    assert "pressed \"Finish Cancellation\" on Streamly's cancel page" in out and "your plan goes on" in out, out
    assert "helped with" not in out and not NEVER_SAID.search(own_words(out))


# =====================================================================================================================
# (5) The help in texting words and Spanish
# =====================================================================================================================
@pytest.mark.parametrize("text", ["what do u do", "wat can u do", "what can u even do", "que puedes hacer",
                                  "qué puedes hacer"])
def test_the_help_in_texting_words_and_spanish_is_read_by_code(op, text):
    c0 = calls(op)
    out = said_n(op, text)[-1]
    assert out.startswith("I find things in what you've saved") and "\nApps: " in out and calls(op) == c0, out


# =====================================================================================================================
# (6) Read live in this check: "allow streamly" again while its run is open; the outbox on the test page
# =====================================================================================================================
@pytest.mark.parametrize("step,tail", [
    ("opened", "The browser is open on Streamly. Sign in there yourself if it asks, then say \"I'm in\"."),
    ("wall", "I'm waiting for you in the browser. Say \"I'm in\" when you're done, or \"stop\"."),
    ("final_shown", "I'm waiting on the last step. Reply \"yes cancel streamly\" to press it, or \"stop\"."),
    ("handed_back", "The browser is yours for now. Say \"stop\" to close it.")])
def test_allow_again_while_the_run_is_open_says_it_is_allowed_and_where_the_run_is(op, monkeypatch, step, tail):
    """Live: the site was already allowed, so "do it for me" opened the browser; "allow streamly" then went to the
    model, which said "That's not something I can do"."""
    from mvp import browser
    monkeypatch.setenv("MVP_BROWSER", "operator")
    monkeypatch.setattr(browser, "EXTRA", {"streamly": _practice(1)})
    _final_state(op["bot"], op["clock"][0], step=step)
    c0 = calls(op)
    assert said_n(op, "allow streamly") == [f"You've already allowed Streamly. {tail}"]
    assert calls(op) == c0 and op["bot"].store.get_state(f"browserrun:{H}")["step"] == step
    assert said_n(op, "allow netflix") != [f"You've already allowed Streamly. {tail}"]   # another site: not this line


def test_the_menu_on_the_test_page_says_the_outbox_panel(op):
    out = said_n(op, "what can i connect")[-1]
    assert "• Email to you: not connected here, so emails wait in my outbox." in out
    op["ch"].name = "web"
    out = said_n(op, "what can i connect")[-1]
    assert "• Email to you: not connected here, so emails wait in the Outbox panel." in out
