"""mvp36, second repair (DESIGN 35.6): one or more tests per fix of the round (brainwire.py, and the few lines of
handler.py, texts.py, videoask.py and channels/web.py it names). Made-up library (tests/brain_library.py), made-up
messages written for these tests, the fake provider and the fake interpreter only: no model call, no network, no money.

- X1: an `ask` of source `recent` is plain (tried); todos, note, items, trends and recap stay today's.
- X2: a follow-up declined for a search or "learned" call goes to today's follow-up, not code's line.
- X3: at H2 with intent `ask`, a result that counts nothing declines (today's search of saves answers).
- X4: a message made only of courtesy words is never tried at H2.
- X5: the caps through the handler; mixed ownership of the screen.
- X6: the second review's findings (A2-01 consent, A2-03 request log and draft, A2-04 / A2-06 claims and offers,
  A2-05 an import that fails, A2-07 a changed request, A2-10 what leaves this computer).
"""
import os
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mvp.tests.test_mvp import env  # noqa: E402,F401  (fixtures)
from mvp.tests.test_brain_tools import NOW, brain, built, no_real_keys  # noqa: E402,F401
from mvp.tests.test_slice2 import H  # noqa: E402
from mvp.tests.test_brain_r36_wire import (wired, send, good, ga, tu, P, OCT, OCT_Q, OPEN_Q,  # noqa: E402,F401
                                           requests_sent, dump, SC, twin, converse, OFF, ON, TRUE_LEAD, TRUE_POINT,
                                           NO_MODEL)


def ask(source="library", **content):
    c = dict({"source": source, "goal": "a look back at what i kept", "searches": ["kept lately"], "count": 2},
             **content)
    return {"intent": "ask", "spec": {"when": {"type": "now"}, "content": c}}


def today_picks(bot, monkeypatch, msg="(today's picks)"):
    monkeypatch.setattr(bot, "run", lambda *a, **k: (msg, None, None))


def pair(brain, tmp_path, monkeypatch, steps_off, steps_on, picks=True):
    """Two bots on their own stores: today's (switch off) and the wired one (switch on); the same steps."""
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "wired")
    if picks:
        for bot in (a, b):
            today_picks(bot, monkeypatch)
    t = converse(brain, a, cha, steps_off, monkeypatch, OFF)
    w = converse(brain, b, chb, steps_on, monkeypatch, ON)
    return a, b, t, w


# ================================================================ X1: `recent` is a plain ask
def test_x1_an_ask_of_source_recent_is_tried_and_sent(wired):
    _o, _c, d = send(wired, "what did i keep over the last few days?", good(), ask("recent", since_days=7))
    assert d["site"] == "H2" and d["intent"] == "ask" and d["decision"] == "sent", d


@pytest.mark.parametrize("source", ["trends", "todos", "recap"])
def test_x1_an_ask_of_another_source_is_never_tried_and_is_todays_byte_same(brain, tmp_path, monkeypatch, source):
    msg = "how have my saves been going lately?"
    a, b, t, w = pair(brain, tmp_path, monkeypatch, [(msg, ask(source), None)], [(msg, ask(source), good())],
                      picks=False)
    d = b._tl.brain_last
    assert d["decision"] == "not_eligible" and d["reason"] == "ask_does_more" and not b.brain_provider.sent
    assert t == w and dump(a.store) == dump(b.store)


@pytest.mark.parametrize("source,extra", [("note", {"text": "water the ferns"}), ("items", {"item_ids": ["x1"]})])
def test_x1_note_and_items_never_reach_the_chat_core_as_an_ask(wired, source, extra):
    from mvp import brainwire as W
    from mvp.schema import Interpretation
    if source == "items":   # the schema refuses item_ids from the interpreter (code sets them): built past it
        spec = Interpretation.model_validate(ask()).spec
        spec.content = spec.content.model_copy(update={"source": "items", "item_ids": ["x1"]})
    else:
        spec = Interpretation.model_validate(ask(source, **extra)).spec   # a form the schema takes
    assert spec.content.source == source and W.plain_ask(spec) is False


def fork(e, bot, tmp_path, name):
    """A second bot on a copy of `bot`'s store as it is now (the same library, clock and person)."""
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    from mvp.tests.test_slice6 import AllPool
    ch = ConsoleChannel(printer=None)
    other = Bot(ch, store=Store(str(tmp_path / f"{name}.sqlite")), pool=AllPool(str(e["lib"])),
                clock=lambda: e["clock"][0])
    bot.store.db.commit()
    bot.store.db.backup(other.store.db)
    other.max_per_minute = None
    return other, ch


def setenv(monkeypatch, d):
    for k, v in d.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def on_and_off(e, tmp_path, monkeypatch, text, script, form, name="off", prep=None):
    """The same message, now, through the wired bot (switch on) and through a copy of its store with the switch off
    (`prep(bot)` readies the copy as the wired bot was). -> (reply on, reply off, decision on, the two dumps after)."""
    off, cho = fork(e, e["bot"], tmp_path, name)
    if prep is not None:
        prep(off)
    setenv(monkeypatch, ON)
    out_on, _c, d = send(e, text, script, form)
    setenv(monkeypatch, OFF)
    out_off, _c2, _d2 = send(e, text, None, form, bot=off, ch=cho)
    setenv(monkeypatch, ON)
    return out_on, out_off, d, nochan(dump(e["bot"].store)), nochan(dump(off.store))


def nochan(d):
    """A dump with the channel's own message numbers left out (a copied store's channel counts from 1 again)."""
    return dict(d, sent=[dict(r, channel_ref=None) for r in d.get("sent") or []])


# ================================================================ X4: courtesy messages are never tried at H2
COURTEOUS = ["thanks!", "lol ok", "hi there", "ok", "thank you so much", "good morning", "Thanks a lot bot :)",
             "hehe nice, cheers", "cool cool", "hahaha", "no worries, see ya"]
ASKING = ["ok and in 2024?", "thanks, and last month?", "cool, what about gaming", "only the long ones", "by month?",
          "ok which channel?", "thanks! how many in march?", "hi, what did i watch most", "cool so what changed?",
          "nice. and the top one?"]


@pytest.mark.parametrize("s", COURTEOUS)
def test_x4_a_message_made_only_of_courtesy_words_matches(s):
    from mvp import brainwire as W
    assert W.courtesy(s)


@pytest.mark.parametrize("s", ASKING)
def test_x4_a_question_or_a_follow_up_never_matches(s):
    from mvp import brainwire as W
    assert not W.courtesy(s)


def test_x4_the_form_is_linear_on_long_laughter():
    import time
    from mvp import brainwire as W
    t = time.perf_counter()
    for s in ("ha" * 400 + " x", "haha" * 300 + "? x", "ok " * 500 + "and?", "hehe" * 300 + "z"):
        assert not W.courtesy(s)
    assert W.courtesy("haha" * 300 + "!")
    assert time.perf_counter() - t < 1.0


@pytest.mark.parametrize("msg,form", [
    ("thanks!", {"intent": "chat", "reply": "Any time."}),
    ("lol ok", {"intent": "chat", "reply": "Ha."}),
    ("ok", {"intent": "confirm"}),
    ("cool thanks", {"intent": "confirm"}),
], ids=["chat_thanks", "chat_lol", "confirm_ok", "confirm_cool"])
def test_x4_courtesy_as_chat_or_confirm_is_not_tried_and_is_todays_byte_same(brain, tmp_path, monkeypatch, msg, form):
    a, b, t, w = pair(brain, tmp_path, monkeypatch, [(msg, form, None)], [(msg, form, good())])
    d = b._tl.brain_last
    assert d["site"] == "H2" and d["decision"] == "not_eligible" and d["reason"] == "courtesy", d
    assert not b.brain_provider.sent and t == w and all(t) and dump(a.store) == dump(b.store)


@pytest.mark.parametrize("text,kind", [("thanks so much!", "up"), ("not for me", "down"), ("that was helpful", "up"),
                                       ("more of that kind please", "more")])
def test_a2_02_a_feedback_while_the_chat_core_owns_the_screen_is_never_tried_and_is_todays_byte_same(
        wired, tmp_path, monkeypatch, text, kind):
    """(A2-02) Today's `_feedback` writes on every feedback (its rows, `lastwrite`), so the chat core never takes one:
    the reply and every table equal a switch-off copy's, and the provider is not asked."""
    send(wired, OCT_Q, good())
    from mvp import brainwire as W
    assert W.owns_screen(wired["bot"], H, wired["clock"][0])
    wired["clock"][0] += timedelta(minutes=1)
    on, off, d, da, db = on_and_off(wired, tmp_path, monkeypatch, text, good(), {"intent": "feedback", "feedback": kind})
    assert d is None and not wired["bot"].brain_provider.sent   # the provider of this message was never asked
    assert on == off and on and da == db


def test_x4_a_follow_up_with_a_courtesy_word_in_it_is_still_tried(wired):
    send(wired, OCT_Q, good())
    wired["clock"][0] += timedelta(minutes=1)
    _o, _c, d = send(wired, "thanks, and last month?", good(), {"intent": "follow_up", "question": "and last month?"})
    assert d["site"] == "H2" and d["decision"] == "sent", d


# ================================================================ X3: at H2 `ask`, a result that counts nothing declines
Y19 = {"words": "in 2019", "preset": None, "same_as": None}   # before the made-up history starts: the sheet counts 0
Q19 = "top channels i watched in 2019?"   # today's parse takes it (H1)


def zero_items():
    return [[tu("items", {"limit": 3, "order": "newest", "window": Y19, "scope": SC})],
            [ga("Nothing shows up from 2019 in what you opened.")]]


def test_x3_counts_nothing_reads_both_forms():
    from mvp import brainwire as W

    def rec(name, sheet, **env):
        return {"calls": [{"name": name, "result": dict({"rid": "r1", "tool": name, "sheet": sheet}, **env)}]}
    assert W._counts_nothing(rec("breakdown", {"totals": {"items": 0}}))
    assert W._counts_nothing(rec("items", {"items": [], "totals": {"items": 3}}))
    assert not W._counts_nothing(rec("breakdown", {"totals": {"items": 4}}))
    assert not W._counts_nothing(rec("items", {"items": [{"ref": "x"}]}))
    assert not W._counts_nothing(rec("breakdown", {"totals": {"items": 0}}, is_error=True))
    assert not W._counts_nothing(rec("find", {"names": []}, error="no_match"))
    assert not W._counts_nothing(rec("timeline", {"rows": []}))


def test_x3_the_zero_result_is_seen_through_the_handler(wired):
    from mvp import brainwire as W
    _o, _c, d = send(wired, Q19, zero_items())   # H1: sent, the record kept in the decision
    assert d["site"] == "H1" and d["decision"] == "sent", d
    assert W._counts_nothing(d["rec"]) and W.decide(d["rec"], d["turn"], "H2", "ask") == "empty"
    wired["clock"][0] += timedelta(hours=7)
    _o, _c, d = send(wired, OCT_Q, good())
    assert d["decision"] == "sent" and not W._counts_nothing(d["rec"])


def test_x3_an_ask_whose_result_counts_nothing_declines_and_is_todays_byte_same(brain, tmp_path, monkeypatch):
    msg = "anything good i opened in 2019?"
    a, b, t, w = pair(brain, tmp_path, monkeypatch, [(msg, ask(), None)], [(msg, ask(), zero_items())])
    d = b._tl.brain_last
    assert d["site"] == "H2" and d["intent"] == "ask" and d["decision"] == "declined" and d["reason"] == "empty", d
    assert t == w == ["(today's picks)"]
    assert dump(a.store) == dump(b.store)


def test_x3_h1_and_the_other_intents_still_send_a_zero(wired):
    _o, _c, d = send(wired, Q19, zero_items())
    assert d["site"] == "H1" and d["decision"] == "sent"
    wired["clock"][0] += timedelta(minutes=1)
    _o, _c, d = send(wired, "and in 2019?", zero_items(), {"intent": "follow_up", "question": "and in 2019?"})
    assert d["site"] == "H2" and d["intent"] == "follow_up" and d["decision"] == "sent", d
    wired["clock"][0] += timedelta(hours=7)
    _o, _c, d = send(wired, "how much stuff did i open in 2019, roughly", zero_items(), {"intent": "library_stats"})
    assert d["site"] == "H2" and d["intent"] == "library_stats" and d["decision"] == "sent", d


# ================================================================ X2, A2-07: a declined follow-up that is today's
SEARCH_KNIT = [[tu("search", {"query": "knitting"})], [ga("Here is what that shows.")]]
FU_KNIT = {"intent": "follow_up", "question": "did i keep any knitting stuff in october?"}
MSG_KNIT = "and did i keep any knitting stuff in october?"
KEPT_REQ = {"spec": {"when": {"type": "now"}, "content": {"source": "library", "goal": "soup videos",
                                                           "searches": ["soup"], "count": 1}},
            "rule_id": None, "text": "find me a soup video", "shown": [], "clear_shown": 0}
FU_CHANGE = {"intent": "follow_up", "question": "a quicker one, no lentils", "avoid": ["lentils"]}
MSG_CHANGE = "a quicker one, no lentils"


def stub_run(bot, monkeypatch, msg="(today's follow-up: a search of the saves)"):
    monkeypatch.setattr(bot, "run", lambda *a, **k: (msg, None, 1))


def _own_itemless_screen(wired, monkeypatch, msg="(today's follow-up: a search of the saves)"):
    stub_run(wired["bot"], monkeypatch, msg)
    send(wired, OCT_Q, good())   # the chat core's answer, no item on screen
    from mvp import brainwire as W
    assert W.owns_screen(wired["bot"], H, wired["clock"][0]) and not wired["bot"].store.last_answer(H)["items"]
    wired["clock"][0] += timedelta(minutes=1)


def test_x2_a_follow_up_declined_for_a_search_goes_to_todays_follow_up_byte_same(wired, tmp_path, monkeypatch):
    from mvp import brainwire as W
    _own_itemless_screen(wired, monkeypatch)
    on, off, d, da, db = on_and_off(wired, tmp_path, monkeypatch, MSG_KNIT, SEARCH_KNIT, FU_KNIT,
                                    prep=lambda b: stub_run(b, monkeypatch))
    assert d["decision"] == "declined" and d["reason"] == "search_or_learned", d
    assert on != W.FOLLOW_DECLINED and on == off and on
    assert len(wired["bot"].brain_provider.sent) == 1   # the stop: one request only
    assert da == db


@pytest.mark.parametrize("script", [None, "plain"], ids=["provider", "plain"])
def test_x2_other_decline_reasons_keep_codes_line(wired, monkeypatch, script):
    from mvp import brainwire as W
    _own_itemless_screen(wired, monkeypatch)
    sc = [P().ProviderError("made-up failure")] if script is None else [[{"type": "text", "text": "hm"}],
                                                                        [{"type": "text", "text": "hm"}]]
    out, _c, d = send(wired, "and the month after?", sc, {"intent": "follow_up", "question": "the month after?"})
    assert d["decision"] == "declined" and d["reason"] in ("provider", "plain"), d
    assert out == W.FOLLOW_DECLINED


def test_a2_07_a_declined_follow_up_that_changes_a_kept_request_runs_todays_changed_request(wired, tmp_path,
                                                                                         monkeypatch):
    from mvp import brainwire as W
    _own_itemless_screen(wired, monkeypatch, "(today's changed request: new picks)")
    wired["bot"].store.set_state(f"lastspec:{H}", KEPT_REQ)
    seen = []
    real = wired["bot"]._changed_request
    monkeypatch.setattr(wired["bot"], "_changed_request", lambda *a, **k: seen.append(1) or real(*a, **k))
    on, off, d, da, db = on_and_off(wired, tmp_path, monkeypatch, MSG_CHANGE, [P().ProviderError("x")], FU_CHANGE,
                                    prep=lambda b: stub_run(b, monkeypatch, "(today's changed request: new picks)"))
    assert d["decision"] == "declined" and d["reason"] == "provider", d
    assert seen == [1] and on != W.FOLLOW_DECLINED and on == off and on and da == db


def test_a2_07_with_no_kept_request_the_line_stays(wired, monkeypatch):
    from mvp import brainwire as W
    _own_itemless_screen(wired, monkeypatch)
    out, _c, d = send(wired, MSG_CHANGE, [P().ProviderError("x")], FU_CHANGE)
    assert d["decision"] == "declined" and out == W.FOLLOW_DECLINED


# ================================================================ A2-04, A2-06: claim forms and offers
CLAIMS_FIX2 = [
    "You'll now get one of these every Tuesday.", "You will soon receive a digest.", "That's been emailed to you.",
    "It's been saved.", "Noted, thanks!", "Noted.", "I'll have them added by Monday.", "I'll have it forwarded to you.",
    "They were saved to your notes.", "This was put on your calendar.", "I'll set an alarm for that.", "On it.",
    "Emailing these over now.", "I've queued a recap for Friday.", "I lined up a list for you.", "Recaps: on.",
    "Reminders switched on.", "Your calendar now has the three of them.", "Those are now in your list.",
    "The digest will go out on Sundays.", "Your list is on its way.", "I'll circle back next week.",
    "I'll get these over to you tonight.", "I've set it all up.", "I`ve emailed them.", "Ive added it.",
    "It's sent.", "It's set for Monday.", "From now on in May, you get one a week.",
    "I'll jot that down.", "I'll note it.", "They're now saved to your to-do list.", "The rule got created.",
    "You're all set for Monday.", "It was e-mailed to you earlier.", "I've arranged a weekly list.",
    # offers of a thing the chat core cannot do (A2-06)
    "Want me to text you these?", "Would you like me to add these to your list?", "Should I schedule this for Monday?",
    "Shall I remind you on Friday?", "I could email you a copy.", "Do you want me to save this?",
    "Can I send you the rest?",
]
TRUE_FIX2 = [
    "Want me to split that by week?", "Should I leave out Shorts?", "Would you like the top 10 instead?",
    "I'll start from March.", "We'll start in 2024.", "I'll keep to Instagram here.",
    "I can add Shorts to the count if you want.", "It was sent to you by a friend twice.",
    "I can remember only what the export holds.", "Your inbox of saves holds 12 posts.",
    "Two were added to Bread days in October.", "You've sent 3 of them to friends.",
    "Pan Theory goes out of your top 5 after June.", "Should I count only what you opened?",
    "It's the channel you opened most.", "That's 12 more than September.", "They're mostly cooking videos.",
    "You noticed Gaming Daily in October.", "Saving was highest on Sundays.",
]


@pytest.mark.parametrize("s", CLAIMS_FIX2)
def test_a2_04_each_new_claim_or_offer_form_is_caught(s):
    from mvp import brainwire as W
    assert W.claims({"lead": s, "points": []}, names=[]) == [s]
    assert W.claims({"lead": "You opened 3 videos.", "points": [s]}, names=[]) == [s]


@pytest.mark.parametrize("s", TRUE_FIX2)
def test_a2_04_true_sentences_still_pass(s):
    from mvp import brainwire as W
    assert W.claims({"lead": s, "points": []}, names=["clip factory", "pan theory", "bread days", "gaming daily"]) == []


@pytest.mark.parametrize("s", ["You'll now get these every Tuesday.", "That's been emailed to you.", "Noted!",
                               "Should I add these to your list?"])
def test_a2_04_a_claim_or_an_offer_never_goes_out_end_to_end(wired, s):
    out, _c, d = send(wired, OCT_Q, [[tu("breakdown", OCT)], [ga(TRUE_LEAD, [TRUE_POINT, s])]])
    assert s not in out
    if s.endswith("?"):   # the values check drops a question point (no figure): it never goes out either way
        assert d["decision"] == "sent" or d["reason"] == "claimed_action", d
    else:
        assert d["decision"] == "declined" and d["reason"] == "claimed_action", d


# ================================================================ A2-03: the request log and code's draft card
def _requests(bot):
    return [(r["handle"], r["text"], r["intent"]) for r in bot.store.q("SELECT handle, text, intent FROM requests")]


def test_a2_03_an_unsupported_answer_the_chat_core_sends_keeps_todays_request_row(brain, tmp_path, monkeypatch):
    msg = "what was my october like, channel wise"
    form = {"intent": "unsupported", "reply": "I can't do that."}
    a, b, t, w = pair(brain, tmp_path, monkeypatch, [(msg, form, None)], [(msg, form, good())])
    assert b._tl.brain_last["decision"] == "sent" and b._tl.brain_last["intent"] == "unsupported"
    assert _requests(a) == _requests(b) == [(H, msg, "unsupported")]


# ================================================================ A2-01: "+anthropic" only for the text that named it
def _new_person(bot):
    bot.store.set_consent(H, None)
    return bot


def test_a2_01_shown_the_older_text_then_switched_on_an_agreement_gets_the_new_text_and_stores_nothing(
        brain, tmp_path, monkeypatch):
    b, ch = twin(brain, tmp_path, "p")
    _new_person(b)
    setenv(monkeypatch, OFF)
    out1, _c, _d = send(brain, "hi there", None, NO_MODEL, bot=b, ch=ch)
    assert "Anthropic" not in out1 and "training" in out1
    setenv(monkeypatch, ON)
    brain["clock"][0] += timedelta(minutes=2)
    out2, _c, _d = send(brain, "I agree", None, NO_MODEL, bot=b, ch=ch)
    assert b.store.person(H)["consent_version"] is None
    assert "Anthropic" in out2 and "training" not in out2
    brain["clock"][0] += timedelta(minutes=2)
    send(brain, "I agree", None, NO_MODEL, bot=b, ch=ch)
    assert b.store.person(H)["consent_version"] == "mvp-consent-v1+anthropic"


def test_a2_01_shown_the_new_text_an_agreement_stores_the_anthropic_version(brain, tmp_path, monkeypatch):
    b, ch = twin(brain, tmp_path, "p")
    _new_person(b)
    setenv(monkeypatch, ON)
    out1, _c, _d = send(brain, "hi there", None, NO_MODEL, bot=b, ch=ch)
    assert "Anthropic" in out1 and "training" not in out1
    brain["clock"][0] += timedelta(minutes=2)
    send(brain, "I agree", None, NO_MODEL, bot=b, ch=ch)
    assert b.store.person(H)["consent_version"] == "mvp-consent-v1+anthropic"


def test_a2_01_shown_the_new_text_then_the_older_one_an_agreement_after_switching_on_gets_the_new_text(
        brain, tmp_path, monkeypatch):
    b, ch = twin(brain, tmp_path, "p")
    _new_person(b)
    setenv(monkeypatch, ON)
    send(brain, "hi there", None, NO_MODEL, bot=b, ch=ch)            # the new text
    setenv(monkeypatch, OFF)
    brain["clock"][0] += timedelta(hours=25)
    out, _c, _d = send(brain, "what is this?", None, NO_MODEL, bot=b, ch=ch)   # the older text, a day on
    assert "Anthropic" not in out
    setenv(monkeypatch, ON)
    brain["clock"][0] += timedelta(minutes=2)
    send(brain, "ok I agree", None, NO_MODEL, bot=b, ch=ch)
    assert b.store.person(H)["consent_version"] is None


def test_a2_01_with_the_switch_off_the_consent_flow_is_todays_byte_same(brain, tmp_path, monkeypatch):
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "other")
    for bot in (a, b):
        _new_person(bot)
    steps = [("hi there", NO_MODEL, None), ("what is this?", NO_MODEL, None), ("I agree", NO_MODEL, None)]
    t = converse(brain, a, cha, steps, monkeypatch, OFF)
    w = converse(brain, b, chb, steps, monkeypatch, {"MVP_BRAIN": "1", "MVP_BRAIN_PEOPLE": "+15559990000"})
    assert t == w and dump(a.store) == dump(b.store)
    assert a.store.person(H)["consent_version"] == "mvp-consent-v1"
    assert not [k for (k,) in b.store.db.execute("SELECT key FROM state") if k.startswith("consent_brain:")]


def test_a2_01_the_test_pages_start_over_counts_as_shown(brain):
    from mvp import texts as T
    st = brain["bot"].store
    assert T.brain_text_shown(st, H) is False
    T.mark_brain_shown(st, H, "2026-11-22T17:00:00+00:00")
    assert T.brain_text_shown(st, H) is True               # no consent_shown kept: the start-over's showing
    st.set_state(f"consent_shown:{H}", "2026-11-23T17:00:00+00:00")
    assert T.brain_text_shown(st, H) is False              # shown again since, not the text that names Anthropic


# ================================================================ A2-05: the wiring fails to import
def test_a2_05_an_import_that_fails_gives_todays_reply_at_h1_and_h2(brain, tmp_path, monkeypatch):
    import mvp
    steps = [(OCT_Q, NO_MODEL, None), (OPEN_Q, {"intent": "chat", "reply": "Happy to help."}, None)]
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "broken")
    t = converse(brain, a, cha, steps, monkeypatch, OFF)
    monkeypatch.delattr(mvp, "brainwire", raising=False)
    monkeypatch.setitem(sys.modules, "mvp.brainwire", None)   # "import of mvp.brainwire halted"
    w = converse(brain, b, chb, steps, monkeypatch, ON)
    assert t == w and all(t) and "Happy to help." in w[1]
    da, db = dump(a.store), dump(b.store)
    assert {k: v for k, v in da.items() if k != "trace"} == {k: v for k, v in db.items() if k != "trace"}


# ================================================================ A2-10, A2-09: what leaves, and the export
@pytest.mark.parametrize("version,named", [("mvp-consent-v1", False), ("mvp-consent-v1+anthropic", True)])
def test_a2_10_what_leaves_names_the_chat_core_only_once_the_consent_named_anthropic(wired, version, named):
    bot = wired["bot"]
    bot.store.set_consent(H, version)
    bot.store.set_state(f"onboard:{H}", {"step": "done", "at": "2026-11-22T17:00:00+00:00"})
    out, _c, _d = send(wired, "what leaves this computer")
    assert ("rows I read from your watch history" in out) is named
    assert "training" not in out.lower()   # the founder's decision 6, for a person the switch names


def test_a2_09_the_export_lists_the_chat_cores_state_by_shape_only(wired):
    import json
    from mvp import export as X
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    st = bot.store.get_state(f"brain:{H}")
    bot.store.set_state(f"brain:{H}", dict(st, carry="dating"))
    got = X.round11_rows(bot.store, H)["chat_core_screen"]
    assert got == {"run_id": st["run_id"], "since": st["at"], "topic_carried": True}
    assert "dating" not in json.dumps(X.round11_rows(bot.store, H))


# ================================================================ X5a: the caps, through the handler
@pytest.mark.parametrize("cap", ["day", "total"])
@pytest.mark.parametrize("site", ["H1", "H2"])
def test_x5a_over_a_cap_the_switch_on_gives_todays_replies_and_store_and_no_request(brain, tmp_path, monkeypatch,
                                                                                    cap, site):
    from mvp import llm
    if cap == "day":
        monkeypatch.setattr(llm, "spent_today", lambda h, l: 999.0)
    else:
        monkeypatch.setattr(llm, "spent_total", lambda libs: 999.0)
    text, form = (OCT_Q, NO_MODEL) if site == "H1" else (OPEN_Q, {"intent": "chat", "reply": "Happy to help."})
    steps = [(text, form, None), ("and which week had the most?", form, None)]
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "wired")
    t = converse(brain, a, cha, steps, monkeypatch, OFF)
    w = converse(brain, b, chb, [(x, f, good()) for x, f, _ in steps], monkeypatch, ON)
    assert t == w and t[0] and dump(a.store) == dump(b.store)   # (today's limit notice is said once a day)
    assert not b.brain_provider.sent
    d = b._tl.brain_last
    assert d is None or d["decision"] == "not_eligible", d


# ================================================================ X5b: mixed ownership of the screen
def test_x5b_i_after_todays_answer_then_a_chat_core_answer_the_follow_up_is_the_chat_cores(wired, monkeypatch):
    from mvp import brainwire as W, history as Hm
    bot = wired["bot"]
    with monkeypatch.context() as m:   # (never monkeypatch.undo(): it would undo the fixtures' fakes too)
        m.setattr(W, "not_eligible", lambda *a, **k: "made_up")   # today's history answer first
        out1, _c, d1 = send(wired, OCT_Q)
    assert d1["decision"] == "not_eligible" and "Clip Factory" in out1
    assert Hm._fresh_state(bot, H, wired["clock"][0]) is not None
    from mvp import llm
    assert llm.chat_json.__name__ == "fake_chat"
    wired["clock"][0] += timedelta(minutes=1)
    _o, c2, d2 = send(wired, OPEN_Q, good(), {"intent": "chat", "reply": "ok"})   # the chat core's answer
    assert c2[:1] == ["mvp_interpret"]
    assert d2["decision"] == "sent" and W.owns_screen(bot, H, wired["clock"][0])
    assert Hm._fresh_state(bot, H, wired["clock"][0]) is None   # one run id: today's history state is not fresh
    wired["clock"][0] += timedelta(minutes=1)
    _o, c3, d3 = send(wired, "and last month?", good(), {"intent": "follow_up", "question": "and last month?"})
    assert c3[:1] == ["mvp_interpret"]
    assert d3["site"] == "H2" and d3["intent"] == "follow_up" and d3["decision"] == "sent", d3


def test_x5b_ii_a_chat_core_answer_then_todays_answer_after_a_decline_the_follow_up_is_todays(wired):
    from mvp import brainwire as W, history as Hm
    bot = wired["bot"]
    send(wired, OPEN_Q, good(), {"intent": "chat", "reply": "ok"})
    assert W.owns_screen(bot, H, wired["clock"][0])
    wired["clock"][0] += timedelta(minutes=1)
    out, _c, d = send(wired, OCT_Q, [P().ProviderError("made-up failure")])   # declined: today's history answers
    assert d["site"] == "H1" and d["decision"] == "declined" and "Clip Factory" in out
    assert not W.owns_screen(bot, H, wired["clock"][0])
    assert Hm._fresh_state(bot, H, wired["clock"][0]) is not None
    wired["clock"][0] += timedelta(minutes=1)
    out, _c, d = send(wired, "and the month before?", None, {"intent": "follow_up", "question": "the month before?"})
    assert out and not bot.brain_provider.sent   # today's follow-up read took it; the chat core was never asked
    assert d is None or d["decision"] != "sent"


def test_a2_07_its_cost_a_history_follow_up_shaped_as_a_refinement_runs_the_kept_request(wired, tmp_path,
                                                                                      monkeypatch):
    """(Reported, not wanted: today's REFINE reads "and in september?" as a change of the kept pick request, so with
    one kept, a declined history follow-up of that shape gets today's changed request, as with the switch off.)"""
    from mvp import brainwire as W
    _own_itemless_screen(wired, monkeypatch, "(today's changed request: new picks)")
    wired["bot"].store.set_state(f"lastspec:{H}", KEPT_REQ)
    fu = {"intent": "follow_up", "question": "and in september?"}
    on, off, d, da, db = on_and_off(wired, tmp_path, monkeypatch, "and in september?", [P().ProviderError("x")], fu,
                                    prep=lambda b: stub_run(b, monkeypatch, "(today's changed request: new picks)"))
    assert d["decision"] == "declined" and on != W.FOLLOW_DECLINED and on == off and da == db


def test_a2_09_the_written_export_holds_the_chat_cores_state_by_shape(wired):
    import json
    from mvp import export as X
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    st = bot.store.get_state(f"brain:{H}")
    bot.store.set_state(f"brain:{H}", dict(st, carry="dating"))
    got = X.export(bot, bot.store.person(H), wired["clock"][0])
    path = dict(got["files"])["history_and_videos.json"]
    text = open(path, encoding="utf-8").read()
    assert json.loads(text)["chat_core_screen"]["topic_carried"] is True and "dating" not in text
