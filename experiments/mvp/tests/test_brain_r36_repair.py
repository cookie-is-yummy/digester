"""mvp36 repair (DESIGN 35.9): one or more tests per finding the review of the wired chat core raised (brainwire.py).
Made-up library (tests/brain_library.py), made-up messages written for these tests, the fake provider and the fake
interpreter only: no model call, no network, no money.

- F01, F05: an `ask` that does more than answer (a to-do, an email, a calendar entry, a time, new finds from YouTube)
  is never tried: today's _dispatch runs with its spec.
- F02: a message that carries a lasting fact for the profile (profile_note, or a level the text states) is never
  tried at H2: today's merge runs.
- F03: the claim forms: adverbs inside the forms, "we", more verbs, the short forms with no subject.
- F06: a clarify that carries a rule draft is today's (the pending question keeps the half-made rule).
- F08: a declined follow-up of the chat core's own answer that showed no item gets code's own line, not today's
  search of the saves against an answer it cannot read.
- F09: a failure in the reads before the turn (eligibility, who owns the screen) declines to today's bot.
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
                                           requests_sent, dump, SC)

LIB_CONTENT = {"source": "library", "goal": "two cooking videos from october", "searches": ["cooking october"],
               "count": 2}


def ask(do=None, **content):
    spec = {"when": {"type": "now"}, "content": dict(LIB_CONTENT, **content)}
    if do is not None:
        spec["do"] = do
    return {"intent": "ask", "spec": spec}


def spy(bot, monkeypatch, name):
    seen = []
    real = getattr(bot, name)

    def wrap(*a, **k):
        seen.append((a, k))
        return real(*a, **k)
    monkeypatch.setattr(bot, name, wrap)
    return seen


def today_picks(bot, monkeypatch):
    monkeypatch.setattr(bot, "run", lambda *a, **k: ("(today's picks)", None, None))


ITEMS_OCT = {"limit": 2, "order": "newest", "window": {"words": "in October", "preset": None, "same_as": None},
             "scope": SC}


def items_answer():
    return [[tu("items", ITEMS_OCT)], [ga("Here are your newest from October.", items=[{"ref": "r1.items[0]"},
                                                                                       {"ref": "r1.items[1]"}])]]


# ================================================================ F01, F05: an ask that does more is today's
@pytest.mark.parametrize("do", [
    ["message.send", {"action": "todo.add"}], ["message.send", {"action": "email.send"}],
    ["message.send", {"action": "calendar.add"}], [{"action": "email.send"}], [{"action": "todo.add"}],
], ids=["reply_and_todo", "reply_and_email", "reply_and_calendar", "email_only", "todo_only"])
def test_f01_an_ask_that_carries_an_action_is_never_tried_and_todays_dispatch_runs_with_it(wired, monkeypatch, do):
    bot = wired["bot"]
    today_picks(bot, monkeypatch)
    disp = spy(bot, monkeypatch, "_dispatch")
    form = ask(do)
    _o, calls, d = send(wired, "pick two cooking videos from my october and keep them for me", items_answer(), form)
    assert d["site"] == "H2" and d["decision"] == "not_eligible" and d["reason"] == "ask_does_more", d
    assert requests_sent(bot) == 0 and calls[:1] == ["mvp_interpret"]
    got = [[a.action for a in x[0][1].spec.do] for x in disp]
    from mvp.schema import Interpretation
    assert got == [[a.action for a in Interpretation.model_validate(form).spec.do]]


@pytest.mark.parametrize("form,msg", [
    (ask(["message.send", {"action": "todo.add"}]), "pick two cooking videos from my october for my to-do list"),
    ({"intent": "chat", "reply": "Good to know.", "profile_note": "learning to make pasta by hand"},
     "I'm learning to make pasta by hand btw, anything about october worth a look?"),
    ({"intent": "clarify", "question": "What time on Saturday?", "draft": {
        "when": {"type": "schedule", "days": ["SAT"], "time": "10:00"},
        "content": {"goal": "a bread recap", "searches": ["bread"], "count": 1}}},
     "every saturday tell me what bread stuff i opened"),
], ids=["ask_with_todo", "profile_note", "clarify_with_draft"])
def test_f01_f02_f06_not_tried_gives_todays_replies_and_store_byte_same(brain, tmp_path, monkeypatch, form, msg):
    from mvp.tests.test_brain_r36_wire import twin, converse, OFF, ON
    a, cha = twin(brain, tmp_path, "today")
    b, chb = twin(brain, tmp_path, "wired")
    for bot in (a, b):
        today_picks(bot, monkeypatch)
    today = converse(brain, a, cha, [(msg, form, None)], monkeypatch, OFF)
    w = converse(brain, b, chb, [(msg, form, good())], monkeypatch, ON)
    assert b._tl.brain_last["decision"] == "not_eligible" and not b.brain_provider.sent
    assert today == w and all(today) and dump(a.store) == dump(b.store)


@pytest.mark.parametrize("outside,msg", [("only", "find me some new bread videos on youtube"),
                                         ("some", "bread videos from my saves, plus new ones")])
def test_f05_an_ask_for_new_finds_from_outside_the_library_is_never_tried(wired, monkeypatch, outside, msg):
    """(Today's guards set `outside` back to "none" when the message asks for nothing new: the messages say "new".)"""
    bot = wired["bot"]
    today_picks(bot, monkeypatch)
    disp = spy(bot, monkeypatch, "_dispatch")
    _o, _c, d = send(wired, msg, good(), ask(outside=outside))
    assert d["decision"] == "not_eligible" and d["reason"] == "ask_does_more" and requests_sent(bot) == 0
    assert len(disp) == 1 and disp[0][0][1].spec.content.outside == outside


def test_f01_plain_ask_reads_every_part_of_the_spec():
    from mvp import brainwire as W
    from mvp.schema import Interpretation

    def spec(**kw):
        f = ask()
        for k, v in kw.items():
            if k == "when":
                f["spec"]["when"] = v
            else:
                f["spec"]["content"][k] = v
        return Interpretation.model_validate(f).spec

    assert W.plain_ask(spec()) is True
    assert W.plain_ask(None) is False
    assert W.plain_ask(spec(when={"type": "once", "in_minutes": 60})) is False
    assert W.plain_ask(spec(source="recent", since_days=7)) is True   # fix2 (X1): `recent` is plain too
    for src in ("todos", "note", "items", "trends", "recap"):   # (built past the schema's own per-source checks)
        s = spec()
        s.content = s.content.model_copy(update={"source": src})
        assert W.plain_ask(s) is False, src
    assert W.plain_ask(spec(outside="only")) is False
    s = spec()
    from mvp.schema import RulePlace
    s.place = RulePlace(connector="todoist", kind="todo")
    assert W.plain_ask(s) is False


def test_f01_a_plain_ask_is_still_tried_and_sent(wired):
    _o, _c, d = send(wired, OPEN_Q, good(), ask())
    assert d["site"] == "H2" and d["intent"] == "ask" and d["decision"] == "sent", d


# ================================================================ F02: a profile write is today's
def test_f02_a_profile_note_said_with_a_question_is_never_tried_and_todays_merge_runs(wired, monkeypatch):
    bot = wired["bot"]
    merged = spy(bot, monkeypatch, "_merge_note")
    form = {"intent": "chat", "reply": "Good to know.", "profile_note": "learning to make pasta by hand"}
    _o, _c, d = send(wired, "I'm learning to make pasta by hand btw, anything about october worth a look?", good(),
                     form)
    assert d["decision"] == "not_eligible" and d["reason"] == "profile_note" and requests_sent(bot) == 0
    assert len(merged) == 1 and "learning to make pasta by hand" in bot.store.profile_notes(H)


def test_f02_a_level_stated_in_the_text_is_never_tried_and_todays_merge_runs(wired, monkeypatch):
    bot = wired["bot"]
    merged = spy(bot, monkeypatch, "_merge_note")
    from mvp import profile as PR
    msg = "I'm a beginner at watercolor, anything about october worth a look?"
    assert PR.level_stated(msg) is not None
    _o, _c, d = send(wired, msg, good(), {"intent": "chat", "reply": "ok"})
    assert d["decision"] == "not_eligible" and d["reason"] == "profile_note" and requests_sent(bot) == 0
    assert len(merged) == 1


def test_f02_a_profile_note_on_a_follow_up_of_the_chat_cores_answer_is_todays_too(wired, monkeypatch):
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    wired["clock"][0] += timedelta(minutes=1)
    merged = spy(bot, monkeypatch, "_merge_note")
    form = {"intent": "follow_up", "question": "and pan theory?", "profile_note": "plays the cello"}
    _o, _c, d = send(wired, "I play the cello by the way, and pan theory?", good(), form)
    assert d["decision"] == "not_eligible" and d["reason"] == "profile_note" and len(merged) == 1


def test_f02_no_note_and_no_level_is_tried(wired):
    _o, _c, d = send(wired, OPEN_Q, good(), {"intent": "chat", "reply": "ok"})
    assert d["decision"] == "sent"


# ================================================================ F06: a clarify with a rule draft is today's
def test_f06_a_clarify_that_carries_a_rule_draft_is_never_tried_and_the_pending_question_is_kept(wired):
    bot = wired["bot"]
    form = {"intent": "clarify", "question": "What time on Saturday?", "draft": {
        "when": {"type": "schedule", "days": ["SAT"], "time": "10:00"},
        "content": {"goal": "a bread recap", "searches": ["bread"], "count": 1}}}
    _o, _c, d = send(wired, "every saturday tell me what bread stuff i opened", good(), form)
    assert d["decision"] == "not_eligible" and d["reason"] == "clarify_draft" and requests_sent(bot) == 0
    assert (bot.store.pending(H) or {}).get("kind") == "clarify"


def test_f06_every_clarify_carries_a_draft_so_none_is_tried(wired):
    """The schema refuses a clarify with no draft; through the handler such a form is read as `unsupported` (its
    guard), which is tried. So in effect no clarify reaches the chat core."""
    from mvp.schema import Interpretation
    with pytest.raises(Exception):
        Interpretation.model_validate({"intent": "clarify", "question": "Which month?"})
    _o, _c, d = send(wired, OPEN_Q, good(), {"intent": "clarify", "question": "Which month?"})
    assert d["site"] == "H2" and d["intent"] == "unsupported" and d["decision"] == "sent", d


# ================================================================ F08: a declined follow-up of the chat core's answer
def test_f08_a_declined_follow_up_after_an_answer_with_no_item_gets_codes_line_and_the_screen_stays(wired):
    from mvp import brainwire as W
    bot = wired["bot"]
    fu = {"intent": "follow_up", "question": "and the month after that"}
    send(wired, OCT_Q, good())
    st1 = bot.store.get_state(f"brain:{H}")
    last1 = bot.store.last_answer(H)
    runs1 = len(bot.store.q("SELECT id FROM runs"))
    wired["clock"][0] += timedelta(minutes=1)
    out, _c, d = send(wired, "and the month after?", [P().ProviderError("x")], fu)
    assert d["decision"] == "declined" and d["reason"] == "provider"
    assert out == W.FOLLOW_DECLINED and "nothing in your library" not in out
    assert bot.store.get_state(f"brain:{H}") == st1 and bot.store.last_answer(H) == last1
    assert len(bot.store.q("SELECT id FROM runs")) == runs1
    wired["clock"][0] += timedelta(minutes=1)
    _o, _c, d3 = send(wired, "and the one before?", good(), fu)   # the chat core's answer still owns the screen
    assert d3["decision"] == "sent" and d3["rec"]["screen"]["last_answer"]["minutes_ago"] == 2


def test_f08_with_items_on_screen_todays_follow_up_still_reads_them(wired, monkeypatch):
    from mvp import brainwire as W
    bot = wired["bot"]
    send(wired, OCT_Q, items_answer())
    assert bot.store.last_answer(H)["items"]
    wired["clock"][0] += timedelta(minutes=1)
    monkeypatch.setattr(bot, "run", lambda *a, **k: ("(today's follow-up of the picks)", None, 1))
    out, _c, d = send(wired, "is the first one long?", [P().ProviderError("x")],
                      {"intent": "follow_up", "question": "is the first one long?"})
    assert d["decision"] == "declined" and out != W.FOLLOW_DECLINED and out


def test_f08_a_feedback_and_a_follow_up_not_eligible_stay_todays(wired, monkeypatch):
    from mvp import brainwire as W
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    wired["clock"][0] += timedelta(minutes=1)
    out, _c, d = send(wired, "that was great", [P().ProviderError("x")], {"intent": "feedback", "feedback": "up"})
    assert d is None and out and out != W.FOLLOW_DECLINED   # (A2-02) a feedback is never tried: today's takes it
    wired["clock"][0] += timedelta(minutes=1)
    monkeypatch.setattr(W, "not_eligible", lambda *a, **k: "claude_cap")
    out, _c, d = send(wired, "and the month after?", None, {"intent": "follow_up", "question": "the month after"})
    assert d["decision"] == "not_eligible" and out != W.FOLLOW_DECLINED


# ================================================================ F09: failures before the turn decline
def test_f09_a_state_time_with_no_zone_is_not_fresh_and_nothing_escapes(wired):
    from mvp import brainwire as W
    bot = wired["bot"]
    send(wired, OCT_Q, good())
    st = bot.store.get_state(f"brain:{H}")
    bot.store.set_state(f"brain:{H}", dict(st, at=st["at"][:19]))
    wired["clock"][0] += timedelta(minutes=1)
    assert W.fresh_state(bot, H, wired["clock"][0]) is None
    out, _c, _d = send(wired, "and pan theory?", good(), {"intent": "follow_up", "question": "and pan theory?"})
    assert out   # today's bot answered; no exception left on_message


def test_f09_an_exception_in_the_eligibility_reads_declines_to_today(wired, monkeypatch):
    from mvp import brainwire as W
    bot = wired["bot"]

    def boom(*a, **k):
        raise RuntimeError("made-up failure")
    monkeypatch.setattr(W, "not_eligible", boom)
    out, _c, d = send(wired, OCT_Q, good())
    assert d["decision"] == "not_eligible" and d["reason"] == "raised:RuntimeError" and "Clip Factory" in out
    monkeypatch.setattr(W, "h2_refusal", boom)
    wired["clock"][0] += timedelta(minutes=1)
    out, _c, d = send(wired, OPEN_Q, good(), {"intent": "chat", "reply": "Happy to help."})
    assert d["site"] == "H2" and d["reason"] == "raised:RuntimeError" and "Happy to help." in out
    assert requests_sent(bot) == 0


# ================================================================ F03: the claim forms
CLAIMS_NEW = [
    "I've also set up a monthly email of these.", "I've just saved those for you.", "I have now added it to your list.",
    "I set it up for Saturdays.", "I've gone ahead and booked that.", "We'll send you a list each Friday.",
    "We will email you these on Mondays.", "I'll make sure you get one each week.", "I'll text you that list later.",
    "I'll ping you when new ones show up.", "I'll let you know when more come in.", "I'll remember that you like baking.",
    "I'll put it on your calendar for Friday.", "I'm sending it over now.", "We're adding these to your list.",
    "Reminder set for Thursday.", "Expect them in your inbox tonight.", "I'll be emailing you the summary.",
    "I will definitely send it on Saturday.", "Your weekly recap starts on Monday.", "You'll be getting one every week.",
    "Scheduled for 8am every Saturday.", "Added to your to-do list.", "I've turned it on for you.",
    "I'll create a rule for that.", "Sent!", "Done.", "I can send you these each week.", "I can set that up for you.",
    "I'll notify you when it changes.", "A reminder has been set for Friday.", "It has been scheduled for Monday.",
]
TRUE_NEW = [
    "You saved 9 videos in October.", "You'll see Pan Theory near the top.", "You kept coming back to Clip Factory.",
    "From September on, you opened fewer videos.", "Every Saturday in October you watched Pan Theory.",
    "I'll start with September.", "I'm going to keep it short: Pan Theory led.", "You added 4 posts to Bread days.",
    "You set up nothing new in October.", "Pan Theory has sent you 32 videos this year.",
    "You started watching Gaming Daily in October.", "Saved posts in October: 5.", "I can't see after 30 October.",
    "I can see 61 videos from Clip Factory.", "We can see you watched more in October.",
    "Most of what you saved was baking.", "Your busiest month was October.",
]


@pytest.mark.parametrize("s", CLAIMS_NEW)
def test_f03_each_new_claim_form_is_caught(s):
    from mvp import brainwire as W
    assert W.claims({"lead": s, "points": []}, names=[]) == [s]
    assert W.claims({"lead": "You opened 3 videos.", "points": [s]}, names=[]) == [s]


@pytest.mark.parametrize("s", TRUE_NEW)
def test_f03_true_sentences_still_pass(s):
    from mvp import brainwire as W
    assert W.claims({"lead": s, "points": []}, names=["clip factory", "pan theory", "bread days",
                                                       "gaming daily"]) == []


def test_f03_a_missed_claim_form_no_longer_goes_out_end_to_end(wired):
    from mvp.tests.test_brain_r36_wire import TRUE_LEAD, TRUE_POINT
    for s in ("I've also set up a monthly email of these.", "We'll send you a list each Friday."):
        out, _c, d = send(wired, OCT_Q, [[tu("breakdown", OCT)], [ga(TRUE_LEAD, [TRUE_POINT, s])]])
        assert d["decision"] == "declined" and d["reason"] == "claimed_action" and s not in out
        wired["clock"][0] += timedelta(hours=7)
