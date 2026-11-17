"""Offline tests for round 9, W10 (DESIGN.md section 16.F): "do 2 for me" hands a to-do to the helper that fits - an
email to-do to the draft card (drafts.from_todo), a cancel to-do to the cancel helper (cancel.from_todo), a to-do that
came from a pick to the apply or book menu - and says plainly when none fits. A to-do is ticked off only when the
outcome is real (the person's "sent", the mail server taking it, "I cancelled it"). Synthetic data only; no model call
in any message the code must answer (the fake interpreter fails the test if it is reached)."""
import os
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

CHAT = {"intent": "chat", "reply": "OK."}
TICK = 'Tick it off once it\'s done: "done {n}".'


def boom(u):
    raise AssertionError("the model was called")


def ask(e, text):
    n = len(e["calls"])
    out = say(e, text, boom)
    assert len(e["calls"]) == n, text
    return out


def outs(e, k):
    return [t for _, _, t in e["ch"].outbox[-k:]]


@pytest.fixture()
def d(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "DRAFT_MODEL", False, raising=False)
    for k in ("MVP_SMTP_HOST", "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_OPERATOR"):
        monkeypatch.delenv(k, raising=False)
    return env


def todos(e, *texts, item_id=None):
    s = e["bot"].store
    return [s.add_todo(H, t, item_id=item_id, at=e["clock"][0]) for t in texts]


def show_list(e):
    return say(e, "my list", {"intent": "todo_list"})


def open_texts(e):
    return [t["text"] for t in e["bot"].store.todos(H)]


# ---------- the request reader ----------
@pytest.mark.parametrize("text,number,words", [
    ("do it for me", None, None), ("can you do number 2", 2, None), ("do 3 for me", 3, None),
    ("do the first one", 1, None), ("help me with 2", 2, None), ("handle the landlord one", None, "landlord"),
    ("take care of the first one", 1, None), ("Can you please do to-do 4 for me?", 4, None),
    ("help me with the second one please", 2, None), ("do #2 for me", 2, None), ("take care of it", None, None)])
def test_the_phrasings_are_read(text, number, words):
    from mvp.todos import doit_request
    r = doit_request(text)
    assert r is not None and r["number"] == number and r["words"] == words, text


@pytest.mark.parametrize("text", ["do it", "do 2", "Do it!", "do the dishes", "help me with my homework",
                                  "take care of yourself", "do you have pasta recipes", "do it again",
                                  "help me with something", "handle it later", "do the last one", "2", "yes"])
def test_near_variants_are_not_read(text):
    from mvp.todos import doit_request
    assert doit_request(text) is None, text


# ---------- each row of the verdict's table ----------
def test_an_email_to_do_starts_the_draft_and_is_ticked_only_on_sent(d):
    todos(d, "Email landlord about the sink")
    show_list(d)
    ask(d, "do 1 for me")
    got = outs(d, 2)
    assert got[0] == "Who should it go to? Reply with your landlord's email address, or \"blank\" to pick them in your mail app."
    assert got[1] == TICK.format(n=1)
    ask(d, "landlord@example.com")
    assert open_texts(d) == ["Email landlord about the sink"]   # a card with a link is not an outcome
    assert "mailto:" in last(d["ch"])
    msg = ask(d, "sent")
    assert msg.endswith('I ticked "Email landlord about the sink" off your list.')
    assert open_texts(d) == []


def test_a_dropped_email_draft_leaves_the_to_do_open(d):
    todos(d, "Email the dentist about Friday")
    show_list(d)
    ask(d, "take care of the first one")
    ask(d, "dentist@example.com")
    ask(d, "cancel")
    assert open_texts(d) == ["Email the dentist about Friday"]


def test_a_cancel_to_do_goes_to_the_cancel_helper_and_is_ticked_on_i_cancelled_it(d):
    todos(d, "Buy milk", "Cancel netflix")
    show_list(d)
    ask(d, "do 2 for me")
    got = outs(d, 2)
    assert got[0].startswith("Netflix cancels on its website. I can't do it for you, because I never sign in as you.")
    assert got[1] == TICK.format(n=2)
    assert open_texts(d) == ["Buy milk", "Cancel netflix"]
    msg = ask(d, "I cancelled netflix")
    assert msg == 'Good, thanks for telling me. I ticked "Cancel netflix" off your list.'
    assert open_texts(d) == ["Buy milk"]


def test_a_cancel_said_done_before_the_hand_off_does_not_tick(d):
    say(d, "cancel my netflix", boom)                  # an older cancel, not from the list
    todos(d, "Cancel netflix")
    show_list(d)
    d["bot"].store.set_state(f"doit:{H}", None)
    assert ask(d, "I cancelled netflix") == "Good, thanks for telling me."
    assert open_texts(d) == ["Cancel netflix"]


def test_a_book_to_do_from_a_pick_opens_the_book_menu(d):
    todos(d, "Book a table at Lemon garlic pasta", item_id="itm_a")
    show_list(d)
    ask(d, "help me with 1")
    head = [t for t in outs(d, 4) if t.startswith("I can't book")]
    assert head and "Find it in Google Maps: https://www.google.com/maps/search/?api=1&query=" in head[0]
    assert last(d["ch"]) == TICK.format(n=1)
    assert open_texts(d) == ["Book a table at Lemon garlic pasta"]


def test_an_apply_to_do_from_a_pick_opens_the_apply_path(d):
    todos(d, "Apply to the Lemon garlic pasta class", item_id="itm_a")
    show_list(d)
    ask(d, "do the first one")
    got = outs(d, 2)
    assert got[0].startswith("I can't fill in or send the application myself.")
    assert got[1] == TICK.format(n=1)


def test_buy_call_and_anything_else_say_plainly_and_offer_a_reminder(d):
    todos(d, "Buy gochujang", "Call the dentist", "Renew passport")
    show_list(d)
    assert ask(d, "do 1 for me") == ('I can\'t buy things for you. It\'s on your list; tick it off with "done 1" when '
                                     'you have it. Want a reminder? Tell me when.')
    assert ask(d, "do 2 for me") == 'I can\'t make calls. Want a reminder? Tell me when, like "tomorrow at 10am".'
    msg = ask(d, "tomorrow at 10am")
    assert msg == 'OK. I\'ll remind you about "Call the dentist" tomorrow at 10am.'
    t = d["bot"].store.todos(H)[1]
    assert t["due_at"] and t["text"] == "Call the dentist"
    assert ask(d, "do 3 for me") == 'I can\'t do "Renew passport" for you. I can remind you if you tell me when, like "friday".'
    # any other message ends the offer: the next "friday" is not a reminder for it
    say(d, "thanks", CHAT)
    say(d, "friday", CHAT)
    assert d["bot"].store.todos(H)[2]["due_at"] is None
    assert len(open_texts(d)) == 3                       # nothing ticked off by any of these


def test_it_with_no_to_do_in_view_asks_which(d):
    assert ask(d, "do it for me") == 'Which one? Say "do 2 for me" ("my list" shows the numbers).'
    todos(d, "Renew passport", "Buy milk")
    assert ask(d, "take care of it") == 'Which one? Say "do 2 for me" ("my list" shows the numbers).'


def test_it_means_the_to_do_just_added(d):
    say(d, "add renew passport to my list", {"intent": "todo_add", "todo_text": "renew passport"})
    assert ask(d, "do it for me") == 'I can\'t do "renew passport" for you. I can remind you if you tell me when, like "friday".'


def test_a_number_past_the_list(d):
    from mvp import texts as T
    assert ask(d, "do 2 for me") == T.NO_TODOS
    todos(d, "Renew passport")
    show_list(d)
    assert ask(d, "do 4 for me") == T.todo_numbers_unknown(1)


def test_a_number_right_after_an_answer_is_not_taken(d):
    todos(d, "Renew passport")
    show_list(d)
    d["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(d, "pasta, no cream", ask_pasta())               # a newer answer: "2" may be a pick now
    assert d["bot"].do_it(d["bot"].store.person(H), "do 2 for me", d["clock"][0]) is None
    # "to-do 1" says which list it means
    assert d["bot"].do_it(d["bot"].store.person(H), "do to-do 1 for me", d["clock"][0]) is not None


def test_nothing_is_taken_while_a_rule_preview_waits(d):
    """A bare "do it" is a yes to the preview (T.YES, as today); "do it for me" is not read by W10 while one waits."""
    from mvp.texts import YES
    assert YES.match("do it")
    todos(d, "Renew passport")
    d["bot"].store.set_pending(H, "confirm_rule", {"spec": {}}, at=d["clock"][0])
    person = d["bot"].store.person(H)
    for text in ("do it for me", "do 1 for me", "handle the passport one"):
        assert d["bot"].do_it(person, text, d["clock"][0]) is None, text
    d["bot"].store.clear_pending(H)
    assert d["bot"].do_it(person, "do 1 for me", d["clock"][0]) is not None


def test_words_pick_the_to_do_by_name(d):
    todos(d, "Email landlord about the sink", "Call the dentist")
    ask(d, "handle the landlord one")
    assert outs(d, 2)[0].startswith("Who should it go to?")
    person = d["bot"].store.person(H)
    assert d["bot"].do_it(person, "handle the pizza one", d["clock"][0]) is None   # no such to-do: the usual path


def test_the_to_do_tick_line_never_claims_an_outcome(d):
    import re
    todos(d, "Cancel netflix", "Book a table at Lemon garlic pasta", "Email landlord about the sink")
    show_list(d)
    for n in (1, 2, 3):
        ask(d, f"do {n} for me")
    sent = " ".join(t for _, _, t in d["ch"].outbox)
    assert not re.search(r"\b(?:cancell?ed|canceled|booked|sent it|emailed them)\b", sent.replace("I cancelled", ""))
