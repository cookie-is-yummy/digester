"""Offline tests for round 9, W9 (DESIGN.md section 16.F): "what did you do for me" - an honest list, from the rows the
bot keeps, of what it did and what it only prepared, newest first, with what is still waiting and what can still be
undone. Synthetic data only (example.com addresses, made-up names), a fake clock, a fake SMTP server; no model call
(every message here is sent with a fake interpreter that fails the test if it is called)."""
import json
import os
import re
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402

CHAT = {"intent": "chat", "reply": "OK."}


def boom(u):
    raise AssertionError("the model was called")


def ask(e, text):
    """A message the code must answer by itself (the fake interpreter fails the test if it is reached)."""
    n = len(e["calls"])
    out = say(e, text, boom)
    assert len(e["calls"]) == n
    return out


@pytest.fixture()
def r(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "DRAFT_MODEL", False, raising=False)
    for k in ("MVP_SMTP_HOST", "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_OPERATOR"):
        monkeypatch.delenv(k, raising=False)
    return env


def at(e, minutes_ago=0, days_ago=0):
    return e["clock"][0] - timedelta(minutes=minutes_ago, days=days_ago)


def fill(e):
    """A store with a row of every kind, at known times (the clock is 12 Nov 2026, New York)."""
    from mvp.store import now_iso
    s = e["bot"].store
    for d in (3, 2, 1):
        s.log_action(H, None, None, "email.send", "done", at=at(e, minutes_ago=60, days_ago=d))
    s.log_action(H, None, None, "email.send", "link", at=at(e, days_ago=2))
    s.log_action(H, None, None, "email.send", "failed", at=at(e, days_ago=2))     # never counted
    s.log_action(H, None, None, "calendar.add", "done", at=at(e, days_ago=4))
    s.log_action(H, None, None, "calendar.add", "done", at=at(e, days_ago=4))
    s.log_action(H, None, None, "mailbox.draft", "done", at=at(e, days_ago=1))
    s.log_action(H, None, None, "email.send", "done", at=at(e, days_ago=9))       # older than 7 days
    sent = s.add_draft(H, "email", "mailbox", "maria@example.com", "Maria", "Sink", {}, at=at(e, days_ago=1))
    s.update_draft(sent, status="sent", version=1, done_at=now_iso(at(e, days_ago=1)))
    link = s.add_draft(H, "email", "link", "sam@example.com", None, "Hello", {"to_word": "landlord"},
                       at=at(e, minutes_ago=30))
    s.update_draft(link, status="link_shown", version=1,
                   shown_at=now_iso(at(e, minutes_ago=30)))
    said = s.add_draft(H, "email", "link", "jo@example.org", "Jo", "Hi", {}, at=at(e, days_ago=3))
    s.update_draft(said, status="person_sent", version=1,
                   done_at=now_iso(at(e, days_ago=3)))
    gone = s.add_draft(H, "email", "link", "x@example.net", None, "No", {}, at=at(e, days_ago=2))
    s.update_draft(gone, status="cancelled", version=1)
    for i in range(3):
        s.add_todo(H, f"thing {i}", at=at(e, days_ago=5))
    pid = [s.add_placement(H, "mac", "mac.reminder", f"R-{i}", at=at(e, days_ago=2)) for i in range(6)]
    s.remove_placements(pid[:1], at=at(e, days_ago=2))
    s.add_placement(H, "mac", "mac.list", "L-1", at=at(e, days_ago=2))   # a list the bot made: not counted
    c1 = s.add_cancellation(H, "netflix", "web", "prepared", at=at(e, days_ago=6))
    s.update_cancellation(c1, at=at(e, days_ago=6), status="person_says_done")
    s.add_cancellation(H, None, "notice", "notice_drafted", at=at(e, days_ago=5))


def test_nothing_done_says_so_with_no_model_call(r):
    assert ask(r, "what did you do for me") == "I haven't done anything for you in the last 7 days."
    assert ask(r, "what did you do today") == "I haven't done anything for you today."
    assert ask(r, "what's still waiting") == "Nothing is waiting for you."


def test_every_kind_is_counted_newest_first_and_honestly(r):
    fill(r)
    msg = ask(r, "what have you done for me")
    lines = msg.split("\n")
    assert lines[0] == "In the last 7 days I:"
    body = [x[2:] for x in lines[1:] if x.startswith("• ")]
    assert body == [
        "prepared the email to your landlord (today; a link you open in your mail app; I can't see whether you sent "
        "it)",
        "sent the email to Maria yesterday at 1pm, after your \"send\" (the mail server took it)",
        "saved 1 draft in your Drafts folder (nothing was sent)",
        "emailed you 3 times (last yesterday)",
        "gave you 1 link that opens an email to yourself (last on Tuesday; I can't see whether you sent it)",
        "added 6 reminders on your Mac, and removed 1 again",
        "wrote the email to Jo, and you told me you sent it (on Monday)",
        "gave you 2 calendar links (I can't see whether you added them)",
        "added 3 things to your lists here",
        "helped with 2 cancellations (you said 1 is done, 1 still open)",
    ]
    # the old row (9 days ago), the failed send, the dropped draft and the list the bot made are not in it
    assert "4 times" not in msg and "example.net" not in msg and "7 reminders" not in msg
    # no merchant, no address in the list
    assert "netflix" not in msg.lower() and "@" not in msg


def test_newest_first_order(r):
    fill(r)
    body = [x for x in ask(r, "what did you do for me").split("\n") if x.startswith("• ")]
    assert body[0].startswith("• prepared the email to your landlord")
    assert body[-1].startswith("• helped with 2 cancellations")


def test_a_link_draft_never_says_you_sent_or_sent(r):
    s = r["bot"].store
    d = s.add_draft(H, "email", "link", "sam@example.com", "Sam", "Hello", {}, at=at(r, 5))
    s.update_draft(d, status="link_shown", version=1)
    msg = ask(r, "what did you do for me")
    line = next(x for x in msg.split("\n") if "Sam" in x)
    assert "I can't see whether you sent it" in line
    assert not re.search(r"\byou sent\b|\byou added\b|\bmail server\b|^• sent\b", line.replace("whether you sent it", ""))
    assert ask(r, "did you send the email to Sam") == (
        "I didn't send it: I wrote the email to Sam and gave you a link to send it from your mail app. I can't see "
        "whether you sent it. Tell me \"sent\" if you did.")


def test_a_draft_never_shown_is_not_counted_as_prepared(r):
    s = r["bot"].store
    s.add_draft(H, "email", "link", None, "Sam", "Hello", {}, at=at(r, 5))   # still asking "who should it go to?"
    assert ask(r, "what did you do for me") == "I haven't done anything for you in the last 7 days."
    assert ask(r, "did you send the email to sam") == (
        "No. I started the email to Sam, but it isn't finished. Say \"show the draft\" to see it.")


def test_did_you_send_to_someone_never_written_for(r):
    assert ask(r, "did you send the email to Maria?") == (
        "I haven't written an email to Maria for you. To start one, say \"email Maria that ...\".")


def test_a_cancellation_says_no_merchant_and_never_cancelled(r):
    s = r["bot"].store
    c = s.add_cancellation(H, "spotify", "web", "prepared", at=at(r, 10))
    s.update_cancellation(c, at=at(r, 10), status="person_sent")
    msg = ask(r, "what did you do for me")
    assert "helped with 1 cancellation (you sent 1 notice)" in msg
    assert "spotify" not in msg.lower() and not re.search(r"cancell?ed|canceled", msg)


def test_today_counts_only_today(r):
    fill(r)
    msg = ask(r, "what did you do today")
    assert msg.split("\n")[0] == "Today I:"
    assert [x for x in msg.split("\n") if x.startswith("• ")] == [
        "• prepared the email to your landlord (today; a link you open in your mail app; I can't see whether you sent "
        "it)"]


def test_undo_is_offered_while_the_last_write_can_be_undone(r):
    say(r, "add milk to my list", {"intent": "todo_add", "todo_text": "milk"})
    msg = ask(r, "what did you do for me")
    assert msg.endswith("You can still undo the last thing (added to-do \"milk\" to the list \"todo\"): say \"undo\" "
                        "within 10 minutes.")
    r["clock"][0] += timedelta(minutes=11)
    assert "undo" not in ask(r, "what did you do for me")


def test_the_agent_phrasings_still_give_the_agent_log_and_a_count_line_is_added(r):
    s = r["bot"].store
    assert say(r, "what did my agent ask", CHAT) == "Your agent hasn't asked me for anything in the last 7 days."
    s.log_action(H, None, None, "mcp.search", "done", at=at(r, 60))
    s.log_action(H, None, None, "mcp.search", "done", at=at(r, 50))
    assert say(r, "what did my agent ask", CHAT).startswith("What your agent asked me for, by day:")
    assert ask(r, "what did you do for me").endswith(
        "Your agent asked me for things 2 times. Say \"what did my agent ask\" to see them.")


@pytest.mark.parametrize("text", ["what have you done for me", "what did you do for me", "What did you do for me?",
                                  "what did you send today", "show my activity", "what did you do this week",
                                  "what's still waiting", "so what have you done for me lately", "my receipts",
                                  "what have you sent"])
def test_each_phrasing_is_read_by_code(r, text):
    out = ask(r, text)
    assert out.startswith(("I haven't done", "Nothing is waiting"))


@pytest.mark.parametrize("text", ["what did you do with my pasta recipe", "what did you send me yesterday about pasta",
                                  "show my rules", "what did my agent ask", "what can you do for me",
                                  "what should I do today", "what did you find", "did you get my message",
                                  "what's waiting at the store"])
def test_near_variants_are_not_taken(r, text):
    from mvp.receipts import DID_SEND, RECEIPTS
    assert not RECEIPTS.match(text) and not DID_SEND.match(text), text


def test_a_mailbox_send_is_waiting_then_sent_and_only_then_says_sent(env, monkeypatch):
    from mvp.tests.test_round9_mailbox import FakeMailSMTP, op as _op  # noqa: F401
    from mvp import config
    from mvp.actions import mailbox
    monkeypatch.setattr(config, "DRAFT_MODEL", False)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "me@example.com")
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", "fake-app-pass-0000")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_PORT", "465")
    monkeypatch.delenv("MVP_SMTP_HOST", raising=False)
    monkeypatch.setattr(mailbox.smtplib, "SMTP_SSL", FakeMailSMTP)
    FakeMailSMTP.made, FakeMailSMTP.fail = [], None
    say(env, "email maria@example.com that the kitchen sink is broken", CHAT)
    assert "(today; not sent)" in ask(env, "what did you do for me")   # (round 9 checks) "not sent", plainly
    assert ask(env, "did you send the email to maria").startswith("No. I wrote the email to someone at example.com")
    say(env, "send", CHAT)
    msg = ask(env, "what's still waiting")
    assert msg.startswith("Waiting for you:\n• the email to someone at example.com goes at 1:02pm.")
    assert ask(env, "did you send the email to maria") == (
        "Not yet. The email to someone at example.com is waiting to go out. Say \"undo\" to stop it.")
    env["clock"][0] += timedelta(minutes=3)
    env["bot"].tick()
    msg = ask(env, "what did you do for me")
    assert "• sent the email to someone at example.com from me@example.com today at 1:03pm, after your \"send\" (the " \
           "mail server took it)" in msg
    assert ask(env, "did you send the email to maria").startswith(
        "Yes. I sent the email to someone at example.com from me@example.com today at 1:03pm")


def test_a_failed_server_send_never_says_sent(env, monkeypatch):
    from mvp.tests.test_round9_mailbox import FakeMailSMTP
    from mvp import config
    from mvp.actions import mailbox
    monkeypatch.setattr(config, "DRAFT_MODEL", False)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "me@example.com")
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", "fake-app-pass-0000")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_PORT", "465")
    monkeypatch.setattr(mailbox.smtplib, "SMTP_SSL", FakeMailSMTP)
    FakeMailSMTP.made, FakeMailSMTP.fail = [], "data_after"
    say(env, "email maria@example.com that the kitchen sink is broken", CHAT)
    say(env, "send", CHAT)
    env["clock"][0] += timedelta(minutes=3)
    env["bot"].tick()
    msg = ask(env, "what did you do for me")
    assert "can't tell whether it went" in msg and "mail server took it" not in msg
    assert not re.search(r"^• sent\b", msg, re.M)


def test_a_deleted_person_gets_nothing(r):
    fill(r)
    say(r, "delete my data", {"intent": "delete_data"})
    say(r, "YES", CHAT)
    s = r["bot"].store
    for t in ("drafts", "cancellations", "placements", "todos"):
        assert s.one(f"SELECT COUNT(*) AS n FROM {t} WHERE handle=?", (H,))["n"] == 0, t
    assert s.one("SELECT COUNT(*) AS n FROM action_log WHERE handle=?", (H,))["n"] == 0
    from mvp.texts import UNKNOWN
    assert say(r, "what did you do for me", boom) == UNKNOWN


def test_the_text_of_receipts_never_claims_an_outcome_it_cannot_see(r):
    fill(r)
    msg = ask(r, "what did you do for me")
    assert not re.search(r"\b(?:delivered|booked|bought|applied|cancell?ed|canceled|in your Sent folder)\b", msg)
    assert json.dumps(msg)
