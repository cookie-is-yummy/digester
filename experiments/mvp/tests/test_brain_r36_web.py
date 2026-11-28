"""mvp36 (DESIGN 35.8): the wired chat core driven through the test page's channel (channels/web.py), the route a
tester takes: "Start over", the consent text that names Anthropic, "I agree", then a history question. Made-up
library, made-up messages, the fake provider and the fake interpreter only: no model call, no network, no money."""
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mvp.tests.test_mvp import env  # noqa: E402,F401  (fixtures)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys  # noqa: E402,F401
from mvp.tests.test_slice2 import H  # noqa: E402
from mvp.tests.test_brain_r36_wire import wired, good, P, OCT_Q, NO_MODEL  # noqa: E402,F401


def page(wired):
    from mvp.channels.web import WebChannel
    bot = wired["bot"]
    web = WebChannel(serve=False)
    web.attach(bot)
    bot.channel = web
    return bot, web


def say(wired, bot, web, text, script=None, form=NO_MODEL):
    bot.brain_provider = P().FakeProvider([list(s) for s in (script or [])])
    wired["state"]["answers"]["mvp_interpret"] = lambda u: form
    n = len(web.state(H)["messages"])
    bot.on_message(H, text)
    return [m["text"] for m in web.state(H)["messages"][n:]], getattr(bot._tl, "brain_last", None)


def test_start_over_on_the_test_page_shows_the_text_that_names_anthropic_and_an_agreement_stores_it(wired):
    from mvp import texts as T
    bot, web = page(wired)
    try:
        web._control({"op": "start_over", "handle": H, "with_welcome": True})
        s = web.state(H)
        first = s["messages"][0]["text"]
        assert s["agreed"] is False and "Anthropic" in first and "training" not in first
        assert T.brain_text_shown(bot.store, H)
        wired["clock"][0] += timedelta(minutes=1)
        out, d = say(wired, bot, web, "I agree")
        assert bot.store.person(H)["consent_version"] == "mvp-consent-v1+anthropic" and out
        assert d is None   # the chat core is not asked while the consent is given
    finally:
        web.close()


def test_start_over_with_the_switch_off_then_switched_on_an_agreement_gets_the_new_text_first(wired, monkeypatch):
    from mvp import texts as T
    bot, web = page(wired)
    try:
        monkeypatch.setenv("MVP_BRAIN", "0")
        web._control({"op": "start_over", "handle": H, "with_welcome": True})
        first = web.state(H)["messages"][0]["text"]
        assert "Anthropic" not in first and not T.brain_text_shown(bot.store, H)
        monkeypatch.setenv("MVP_BRAIN", "1")
        wired["clock"][0] += timedelta(minutes=1)
        out, _d = say(wired, bot, web, "I agree")
        assert bot.store.person(H)["consent_version"] is None
        assert "Anthropic" in "\n".join(out) and "training" not in "\n".join(out)
        wired["clock"][0] += timedelta(minutes=1)
        say(wired, bot, web, "I agree")
        assert bot.store.person(H)["consent_version"] == "mvp-consent-v1+anthropic"
    finally:
        web.close()


def test_a_history_question_on_the_test_page_is_answered_by_the_chat_core_and_the_page_shows_it(wired):
    bot, web = page(wired)
    try:
        out, d = say(wired, bot, web, OCT_Q, good())
        assert d["site"] == "H1" and d["decision"] == "sent", d
        assert "Clip Factory" in "\n".join(out) and "61" in "\n".join(out)
        s = web.state(H)   # the whole page state renders after a chat-core answer
        assert s["agreed"] is True and s["messages"]
        wired["clock"][0] += timedelta(minutes=1)
        out, d = say(wired, bot, web, "and pan theory?", good(), {"intent": "follow_up", "question": "and pan theory?"})
        assert d["site"] == "H2" and d["decision"] == "sent" and out, d
        web._control({"op": "start_over", "handle": H})   # the other button: the chat core's screen goes too
        assert bot.store.get_state(f"brain:{H}") is None
    finally:
        web.close()
