"""Round 9 adversarial checks of email and cancelling (DESIGN.md sections 16.A and 16.B, "Checks after the merge").

Each test here failed on the merged tree before its fix (and its near-variants show the fix is narrow). Synthetic data
only: made-up names, example.com addresses, a made-up app password; fake SMTP and IMAP servers; no model call except
the fake draft_v1 where a test names it."""
import json
import os
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round9_cancel import (STOPS, _backup, _restore, _three_rules, c, card_after, entry,  # noqa: E402,F401
                                          msg, routes_file, sent_since)
from mvp.tests.test_round9_drafts import CHAT, GOOD, card, d, draft_row, m, model  # noqa: E402,F401
from mvp.tests.test_round9_mailbox import (FakeIMAP, FakeMailSMTP, box, draft, op, sends,  # noqa: E402,F401
                                           tick_at)
from mvp.tests.test_slice2 import H, say  # noqa: E402

ME = "me@example.com"


def held(e):
    return e["bot"].store.get_state(f"sendhold:{H}")


# =====================================================================================================================
# 1. "send" only as the yes on the exact last version
# =====================================================================================================================
@pytest.mark.parametrize("text", ["send it?", "send?", "Send it??", "should I send it?", "can you send it?",
                                  "send it now?"])
def test_a_question_about_sending_is_never_the_yes(op, text):
    from mvp import texts as T
    draft(op)
    assert say(op, text, CHAT) == T.DRAFT_SEND_ASKED
    assert held(op) is None and draft_row(op)["status"] == "link_shown"
    tick_at(op, 5)
    assert sends() == []


@pytest.mark.parametrize("text", ["send", "send it", "Send it now!", "ok send it", "send it.", "yes, send it please"])
def test_the_send_words_still_send_once(op, text):
    draft(op)
    assert say(op, text, CHAT).startswith("Sending to maria@example.com at ")
    tick_at(op, 3)
    assert len(sends()) == 1


def test_send_it_question_while_held_says_when_and_changes_nothing(op):
    draft(op)
    say(op, "send", CHAT)
    hold = held(op)
    assert say(op, "send it?", CHAT) == "It's already waiting to go at 1:02 pm. Reply \"undo\" to stop it."
    assert held(op) == hold
    tick_at(op, 3)
    assert len(sends()) == 1


def test_send_it_question_on_the_link_route_never_says_sent(d):
    from mvp import texts as T
    say(d, "email maria@example.com that the kitchen sink is broken", CHAT)
    assert say(d, "send it?", CHAT) == T.DRAFT_SEND_LINK


def test_a_second_send_while_one_waits_never_drops_the_first(op):
    draft(op)
    say(op, "send", CHAT)
    hold = held(op)
    draft(op, "email sam@example.com that dinner is at 7")
    assert say(op, "send", CHAT) == ("Your email to maria@example.com is still waiting to go at 1:02 pm. Reply \"send\" "
                                     "again once it has gone, or \"undo\" to stop it.")
    assert held(op) == hold
    tick_at(op, 3)
    got = sends()
    assert len(got) == 1 and b"To: maria@example.com" in got[0]
    # the second card is still open and goes on its own "send"
    assert say(op, "send", CHAT).startswith("Sending to sam@example.com at ")
    tick_at(op, 3)
    assert len(sends()) == 2 and b"To: sam@example.com" in sends()[1]


def test_a_send_that_goes_leaves_a_newer_card_open(op):
    draft(op)
    say(op, "send", CHAT)
    draft(op, "email sam@example.com that dinner is at 7")
    tick_at(op, 3)
    assert len(sends()) == 1
    msg_ = say(op, "send", CHAT)
    assert "already sent" not in msg_ and msg_.startswith("Sending to sam@example.com at ")
    # with no newer card, "send" after it went still says so (the one send per yes)
    tick_at(op, 3)
    assert say(op, "send", CHAT).startswith("I already sent that one at ")


def _unknown(op):
    FakeMailSMTP.fail = "data_after"
    draft(op)
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert draft_row(op)["status"] == "unknown"
    FakeMailSMTP.fail = None


def test_send_after_an_unknown_send_never_says_it_was_sent(op):
    _unknown(op)
    assert say(op, "send", CHAT) == "I may or may not have sent it. Check your Sent folder before you ask me again."
    tick_at(op, 3)
    assert len(sends()) == 1   # (the fake took the bytes before it timed out) and nothing more


def test_undo_after_an_unknown_send_never_says_it_went(op):
    _unknown(op)
    assert say(op, "undo", CHAT) == ("I can't stop it now. I may or may not have sent the email to m***@example.com. "
                                     "Check your Sent folder before you ask me again.")


def test_undo_after_a_sent_one_still_says_where_it_went(op):
    draft(op)
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert say(op, "undo", CHAT).startswith("I can't unsend an email. It went to maria@example.com at ")


def test_show_during_the_hold_with_other_words_stops_the_send_and_says_so(op):
    draft(op)
    say(op, "send", CHAT)
    op["bot"].store.set_prefs(H, sign_as="Zed")   # the sign-off changed meanwhile: the words are not the ones said yes to
    n = len(op["ch"].outbox)
    say(op, "show it", CHAT)
    first = op["ch"].outbox[n][2]
    assert first.startswith("That stopped the send I had waiting. Reply \"send\" to send this version.")
    assert held(op) is None
    tick_at(op, 3)
    assert sends() == []
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert len(sends()) == 1 and b"Zed" in sends()[0]


def test_show_during_the_hold_with_the_same_words_keeps_it(op):
    draft(op)
    say(op, "send", CHAT)
    hold = held(op)
    say(op, "show it", CHAT)
    assert held(op) == hold
    tick_at(op, 3)
    assert len(sends()) == 1


# =====================================================================================================================
# 2. Words from a saved post never name who it goes to, a merchant route, or a phone number in the email
# =====================================================================================================================
def test_an_email_todo_from_a_post_never_names_the_recipient(d):
    d["bot"].store.add_todo(H, "Email Studio Owner about booking", item_id="itm_a", url="https://example.com/itm_a")
    say(d, "do 1 for me", CHAT)
    out = [x[2] for x in d["ch"].outbox[-2:]]
    assert out[0] == ("Who should it go to? Reply with their email address, or \"blank\" to pick them in your mail "
                      "app.")
    assert not any("Studio" in x for x in out)
    say(d, "sam@example.com", CHAT)
    say(d, "can I book a spot", CHAT)
    assert card(d)[1].startswith("Hi,\n\n")


def test_an_email_todo_the_person_typed_keeps_their_name(d):
    d["bot"].store.add_todo(H, "Email Sam about dinner")
    say(d, "do 1 for me", CHAT)
    assert d["ch"].outbox[-2][2].startswith("Who should it go to? Reply with Sam's email address")


def test_a_cancel_todo_from_a_post_asks_which_company(d):
    d["bot"].store.add_todo(H, "Cancel my Netflix subscription", item_id="itm_a", url="https://example.com/itm_a")
    say(d, "do 1 for me", CHAT)
    assert d["ch"].outbox[-2][2] == "Which company is it? Tell me the name and I'll find the way out."
    assert d["bot"].store.cancellations(H) == []
    say(d, "netflix", CHAT)   # the person names it: then the file's way out
    assert last(d["ch"]).startswith("Netflix cancels on its website.")


def test_a_cancel_todo_the_person_typed_keeps_its_merchant(d):
    d["bot"].store.add_todo(H, "Cancel my Netflix subscription")
    say(d, "do 1 for me", CHAT)
    assert d["ch"].outbox[-2][2].startswith("Netflix cancels on its website.")


def _post(e, monkeypatch, title):
    lib = e["lib"]
    with open(lib / "corpus" / "items.jsonl", "a") as f:
        f.write(json.dumps({"id": "itm_x", "platform": "instagram", "source_url": "https://example.com/itm_x",
                            "caption": "Pottery workshop Saturday, call 555-123-4567 to book",
                            "interaction_kinds": ["save"],
                            "platform_data": {"owner_handle": "studio", "owner_relation": "following"}}) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "a") as f:
        f.write(json.dumps({"item_id": "itm_x", "kind": "save", "at": "2026-03-01T10:00:00+00:00"}) + "\n")
    monkeypatch.setattr(e["bot"].pool, "search", lambda lib, q, depth=300: {"ids": ["itm_x"], "mode": "normal",
                                                                             "cost_usd": 0.0})
    e["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": title, "why": "Fits.", "verdict": "clear"})
    say(e, "pottery", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a pottery class", "searches": ["pottery workshop"], "count": 1}}})


def test_a_phone_number_in_a_post_title_never_goes_in_the_email(d, monkeypatch):
    _post(d, monkeypatch, "Pottery workshop Saturday, call 555-123-4567")
    say(d, "email it to sam@example.com", CHAT)
    c = card(d)
    assert "555-123-4567" not in "\n".join(c)
    assert c[1] == "Hi,\n\nA post from @studio by @studio\nhttps://example.com/itm_x\n\nThanks,\nT"


def test_a_post_title_with_no_phone_number_is_kept(d, monkeypatch):
    _post(d, monkeypatch, "Pottery workshop Saturday")
    say(d, "email it to sam@example.com", CHAT)
    assert card(d)[1].startswith("Hi,\n\nPottery workshop Saturday by @studio\n")


# =====================================================================================================================
# 3. The model's words: no day, number or "already done" the person did not say
# =====================================================================================================================
SRC = ["email maria@example.com that the kitchen sink is broken", "", "T"]


@pytest.mark.parametrize("added,why", [
    ("I can come by on monday.", "monday"), ("Tomorrow works for me.", "tomorrow"),
    ("I can pay fifty dollars.", "fifty"), ("I already took care of the deposit.", "already"),
    ("Tonight is fine.", "tonight"), ("See you next week.", "next week"), ("Could you come on friday?", "friday"),
    ("It's been broken for three days.", "three"), ("Lo arreglo el viernes.", "viernes"),
])
def test_grounded_refuses_a_day_a_number_or_a_claim_the_person_never_said(added, why):
    from mvp.drafts import grounded
    probs = grounded(dict(GOOD, body="The kitchen sink is broken. " + added), SRC, name="")
    assert any(why in p for p in probs), probs


@pytest.mark.parametrize("brief,added", [
    ("email maria@example.com that the kitchen sink is broken and I can come by on monday", "I can come by on monday."),
    ("email maria@example.com that the kitchen sink is broken and tomorrow works for me", "Tomorrow works for me."),
    ("email maria@example.com that the kitchen sink is broken, I can pay fifty dollars", "I can pay fifty dollars."),
    ("email maria@example.com that the kitchen sink is broken, I already paid the deposit", "I already paid the deposit."),
    ("email maria@example.com that the kitchen sink has been broken for three days", "It's been broken for three days."),
])
def test_grounded_takes_the_same_words_when_the_person_said_them(brief, added):
    from mvp.drafts import grounded
    assert grounded(dict(GOOD, body="The kitchen sink is broken. " + added), [brief, "", "T"], name="") == []


def test_grounded_takes_a_translation_of_the_same_day_and_number():
    """The live eval's Spanish rewrite (d-dev-10) fell back to code on the first run of these checks: "sábado" is
    "Saturday" in the person's words. A translation counts; a different day does not."""
    from mvp.drafts import grounded
    src = ["email my neighbor that the party is on Saturday at 8", "neighbor", "",
           "Hi,\n\nThe party is on Saturday at 8. I hope you can come.\n\nThanks,", "in Spanish"]
    form = {"subject": "La fiesta del sábado", "greeting": "Hola,", "closing": "Gracias,",
            "body": "La fiesta es el sábado a las ocho. Espero que puedas venir."}
    assert grounded(form, src, name="") == []
    assert grounded(dict(form, body="La fiesta es el viernes a las ocho."), src, name="") == [
        "the day or time \"viernes\" is not in their message"]
    assert grounded(dict(form, body="La fiesta es el sábado a las nueve."), src, name="") == [
        "the number \"nueve\" is not in their message"]


def test_grounded_takes_the_eval_s_kind_of_draft():
    from mvp.drafts import grounded
    assert grounded(GOOD, SRC, name="") == []
    assert grounded(dict(GOOD, body="Could you take a look when you have a moment? Thanks for your help."), SRC,
                    name="") == []


def test_a_rewrite_that_adds_a_day_is_not_shown(m):
    model(m, GOOD, dict(GOOD, body="The kitchen sink is broken, sorry to bother you! I can come by on monday."))
    say(m, "email maria@example.com that the kitchen sink is broken", CHAT)
    say(m, "make it friendlier", CHAT)
    # (round 9 live fix pass, finding 105: the model was asked, so the reply says it couldn't without adding things)
    assert last(m["ch"]).startswith("I couldn't make it friendlier without adding things you didn't say, so the email "
                                    "is the same as before.")
    assert "monday" not in card(m)[1]


# =====================================================================================================================
# 4. The cancel helper's questions never swallow a command about rules
# =====================================================================================================================
OPEN = {"which": ["cancel my subscription"], "gym": ["how do I get out of my gym membership"],
        "member_name": ["how do I get out of my gym membership", "Planet Fitness"]}


def _run(e, text, form):
    bot = e["bot"]
    n = len(e["ch"].outbox)
    if form is None:
        e["state"]["answers"].pop("mvp_interpret", None)
        bot.on_message(H, text)
    else:
        say(e, text, form)
    return sent_since(e, n), [(r["id"], r["status"], r["paused_until"]) for r in
                              bot.store.rules(H, statuses=("active", "paused", "stopped", "done"))]


@pytest.mark.parametrize("opener", list(OPEN))
@pytest.mark.parametrize("text,form", STOPS)
def test_a_rule_stop_after_a_cancel_question_goes_as_with_nothing_open(c, opener, text, form):
    from mvp import config
    config.DRAFT_MODEL = False
    bot = c["bot"]
    _three_rules(c)
    snap = _backup(bot)
    base = _run(c, text, form)
    _restore(bot, snap)
    for t in OPEN[opener]:
        c["state"]["answers"].pop("mvp_interpret", None)
        bot.on_message(H, t)
    got = _run(c, text, form)
    assert got == base
    assert not bot.store.q("SELECT id FROM drafts WHERE handle=?", (H,))


@pytest.mark.parametrize("opener,answer,reply", [
    ("which", "Brightbox", "I don't have a checked way out of Brightbox yet."),
    ("which", "spotify", "Spotify cancels on its website."),
    ("gym", "Planet Fitness", "What name is the membership under? I only use it for the notice."),
    ("gym", "Iron Temple", "What name is the membership under? I only use it for the notice."),
    ("member_name", "Alex Rivera", "Here's a cancellation notice you can send to Planet Fitness."),
    ("member_name", "Will Smith", "Here's a cancellation notice you can send to Planet Fitness."),
    ("member_name", "Mark Done", "Here's a cancellation notice you can send to Planet Fitness."),
])
def test_names_typed_back_are_still_answers(c, opener, answer, reply):
    from mvp import config
    config.DRAFT_MODEL = False
    for t in OPEN[opener]:
        msg(c, t)
    n = len(c["ch"].outbox)
    msg(c, answer)
    assert sent_since(c, n)[0].startswith(reply)


# =====================================================================================================================
# 5. The notice's address: only from a page read in the last 60 days
# =====================================================================================================================
@pytest.mark.parametrize("checked,shown", [("2026-11-17", True), ("2026-09-19", True), ("2026-09-18", False),
                                           ("2026-08-01", False)])
def test_a_notice_address_is_only_given_while_its_check_is_fresh(c, tmp_path, monkeypatch, checked, shown):
    routes_file(tmp_path, monkeypatch, [entry("fitco", "Fitco", route="notice", notice_email="cancel@fitco.example",
                                              checked=checked)])
    msg(c, "cancel my fitco membership")
    out = card_after(c, "Alex Rivera")
    assert ("To: cancel@fitco.example\n" in out) is shown
    assert shown or "To: (type their email address" in out


# =====================================================================================================================
# 6. The IMAP fake catches a forbidden command even when the code would swallow its error
# =====================================================================================================================
def test_the_imap_fake_records_a_forbidden_command_hidden_by_a_try(box, monkeypatch):
    from mvp.actions import mailbox_imap
    real = mailbox_imap.delete_draft

    def sneaky(s, folder, uid):
        conn = mailbox_imap._connect(s)
        try:
            conn.uid("FETCH", uid, "(RFC822)")
        except Exception:  # noqa: BLE001 - the mutation this test is about
            pass
        try:
            conn.fetch("1", "(RFC822)")
        except Exception:  # noqa: BLE001
            pass
        mailbox_imap._bye(conn)
        return real(s, folder, uid)
    monkeypatch.setattr(mailbox_imap, "delete_draft", sneaky)
    draft(box)
    say(box, "save it as a draft", CHAT)
    say(box, "undo", CHAT)
    assert FakeIMAP.forbidden == ["UID FETCH", "FETCH"]
    FakeIMAP.forbidden = []   # (the fixture fails any other test that leaves one here)


# =====================================================================================================================
# 7. "What did you do for me" after a notice: who sent it is said as it happened
# =====================================================================================================================
from mvp.tests.test_round9_cancel import opc  # noqa: E402,F401


def _cancel_line(e):
    say(e, "what did you do for me", CHAT)
    return next(x for x in last(e["ch"]).split("\n") if "helped with" in x)


def test_a_notice_the_mailbox_sent_is_never_you_sent_in_the_receipts(opc):
    msg(opc, "cancel my fitco membership")
    card_after(opc, "Alex Rivera")
    msg(opc, "remove it")
    msg(opc, "send")
    opc["clock"][0] += timedelta(minutes=3)
    opc["bot"].tick()
    assert len(opc["sends"]()) == 1
    line = _cancel_line(opc)
    assert "you sent" not in line and "I sent 1 notice after your \"send\"" in line


def test_a_notice_the_person_sent_from_the_link_is_you_sent(c):
    from mvp import config
    config.DRAFT_MODEL = False
    msg(c, "cancel my planet fitness membership")
    msg(c, "Alex Rivera")
    msg(c, "remove it")
    msg(c, "sent")
    line = _cancel_line(c)
    assert "you sent 1 notice" in line and "I sent" not in line


# =====================================================================================================================
# 8. Held in the adversarial pass (kept as regression tests)
# =====================================================================================================================
from mvp.tests.test_mvp import pasta_spec  # noqa: E402
from mvp.tests.test_round9_cancel import EVERY_DAY  # noqa: E402


@pytest.mark.parametrize("words,stop", [("check netflix for new shows", "stop the netflix one"),
                                        ("cancel the spotify family plan", "stop the spotify reminder"),
                                        ("pay the gym", "pause the gym one")])
def test_a_rule_named_by_a_merchant_word_is_stopped_not_cancelled(c, words, stop):
    say(c, "every day at 7 remind me to " + words, {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": EVERY_DAY, "time": "07:00"}, "content": {"source": "note", "text": words}}})
    say(c, stop, {"intent": stop.split()[0], "rule_number": 1})
    assert [r["status"] for r in c["bot"].store.rules(H, statuses=("active", "paused", "stopped"))] != ["active"]
    assert c["bot"].store.cancellations(H) == []


def test_a_list_named_after_a_merchant_is_not_a_cancel(c):
    c["bot"].store.add_todo(H, "Stranger Things", list_name="netflix")
    say(c, "cancel my netflix list", {"intent": "chat", "reply": "ok"})
    assert c["bot"].store.cancellations(H) == []


@pytest.mark.parametrize("text", ["cancel my netflix at https://evil.example/cancel",
                                  "cancel my netflix, the link is evil.example/cancel"])
def test_a_link_the_person_types_is_never_the_way_out(c, text):
    out = msg(c, text)
    assert "evil.example" not in out and "https://www.netflix.com/cancelplan" in out


def test_a_link_in_a_todo_is_never_the_way_out(c):
    c["bot"].store.add_todo(H, "Cancel netflix https://evil.example/cancel")
    msg(c, "do 1 for me")
    assert not any("evil.example" in x[2] for x in c["ch"].outbox[-3:])


def test_cancel_that_after_a_rule_preview_drops_the_preview(c):
    say(c, "every friday send me a pasta recipe", {"intent": "new_rule", "spec": pasta_spec()})
    msg(c, "cancel that")
    assert c["bot"].store.pending(H) is None and c["bot"].store.cancellations(H) == []
