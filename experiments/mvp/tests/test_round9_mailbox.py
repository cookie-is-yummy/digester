"""Offline tests for round 9, slice A, W4 (the operator's own mailbox sends a draft after "send", over SMTP only,
with a two-minute hold) and A5 (a real draft in the operator's Drafts folder, over IMAP with a fixed allow-list).
DESIGN.md section 16.A; amendment A-013 (Proposed).

The approval rule is the heart of these tests: nothing leaves without "send" on the exact version last shown; any
change voids that yes; one send per yes; a placeholder blocks it; a post's text can never supply a recipient; and no
reply says "sent" before the mail server accepted it. Synthetic data only (example.com addresses, a made-up app
password); a fake SMTP server and a fake IMAP server record every command; no network, no model call."""
import json
import os
import socket
import sys
from datetime import timedelta
from email import message_from_bytes, policy

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round9_drafts import CHAT, HEAD, NEW, _bad_post, card, draft_row, link_of, one_pick  # noqa: E402
from mvp.tests.test_slice2 import H, lemon_pick, say  # noqa: E402

PASSWORD = "fake-app-pass-1234"
ME = "me@example.com"


class FakeMailSMTP:
    """smtplib.SMTP_SSL / smtplib.SMTP stand-in: records each command, accepts everything unless told to fail at
    one step ("connect", "login", "rcpt", "data_before", "data_after")."""
    made = []
    fail = None

    def __init__(self, host, port, timeout=None, context=None, **kw):
        self.host, self.port, self.calls, self.messages = host, port, [], []
        FakeMailSMTP.made.append(self)
        if FakeMailSMTP.fail == "connect":
            raise socket.timeout("timed out")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def ehlo(self, name=""):
        self.calls.append("ehlo")
        return 250, b"ok"

    def login(self, user, password):
        self.calls.append(("login", user, password == PASSWORD))
        if FakeMailSMTP.fail == "login":
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    def mail(self, sender, options=()):
        self.calls.append(("mail", sender))
        return 250, b"ok"

    def rcpt(self, to, options=()):
        self.calls.append(("rcpt", to))
        if FakeMailSMTP.fail == "rcpt":
            return 550, b"5.1.1 no such user"
        return 250, b"ok"

    def putcmd(self, cmd, args=""):
        self.calls.append(cmd)
        self._next = "354"

    def send(self, data):
        self.calls.append("message")
        body = data[:-len(b".\r\n")] if data.endswith(b"\r\n.\r\n") else data
        self.messages.append(body.replace(b"\r\n..", b"\r\n."))
        self._next = "250"

    def getreply(self):
        if self._next == "354":
            if FakeMailSMTP.fail == "data_before":
                raise socket.timeout("timed out")
            return 354, b"go ahead"
        if FakeMailSMTP.fail == "data_after":
            raise socket.timeout("timed out")
        return 250, b"2.0.0 OK queued"

    def rset(self):
        self.calls.append("rset")

    def quit(self):
        self.calls.append("quit")

    def close(self):
        self.calls.append("close")


@pytest.fixture()
def op(env, monkeypatch):
    """The operator, with their own mailbox in the environment (a made-up app password), and no model writing."""
    from mvp import config
    from mvp.actions import mailbox
    monkeypatch.setattr(config, "DRAFT_MODEL", False)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", ME)
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_PORT", "465")
    monkeypatch.delenv("MVP_SMTP_HOST", raising=False)
    monkeypatch.setattr(mailbox.smtplib, "SMTP_SSL", FakeMailSMTP)
    monkeypatch.setattr(mailbox.smtplib, "SMTP", FakeMailSMTP)
    FakeMailSMTP.made, FakeMailSMTP.fail = [], None
    return env


def sends():
    return [m for s in FakeMailSMTP.made for m in s.messages]


def draft(e, text="email maria@example.com that the kitchen sink is broken"):
    say(e, text, CHAT)
    return draft_row(e)


def tick_at(e, minutes):
    e["clock"][0] += timedelta(minutes=minutes)
    return e["bot"].tick()


# =====================================================================================================================
# The approval rule (written before the code)
# =====================================================================================================================
def test_rule_send_on_the_exact_version_sends_once_after_the_hold(op):
    row = draft(op)
    c = card(op)
    assert c[2].startswith(f"Reply \"send\" to send it from {ME}. Or tap to send it yourself:\nmailto:")
    msg = say(op, "send", CHAT)
    assert msg == "Sending to maria@example.com at 1:02 pm. Reply \"undo\" before then to stop it."
    assert sends() == [] and draft_row(op)["status"] == "held"
    tick_at(op, 1)
    assert sends() == []
    tick_at(op, 1.5)
    got = sends()
    assert len(got) == 1
    m = message_from_bytes(got[0], policy=policy.default)
    assert m["From"] == ME and m["To"] == "maria@example.com" and m["Subject"] == row["subject"]
    assert m.get_content().replace("\r\n", "\n").rstrip("\n") == c[1]          # the body is the one shown, exactly
    assert last(op["ch"]) == ("Your mail server accepted the email to maria@example.com at 1:02 pm. I can't unsend "
                              "it.")
    r = draft_row(op)
    assert r["status"] == "sent" and r["sent_at"]
    s = FakeMailSMTP.made[-1]
    assert ("login", ME, True) in s.calls and ("rcpt", "maria@example.com") in s.calls


@pytest.mark.parametrize("change", ["say I'm home after 5", "subject: Sink", "to: jo@example.com", "don't sign it",
                                    "instead say the sink is fixed"])
def test_rule_any_change_voids_the_yes(op, change):
    draft(op)
    say(op, "send", CHAT)
    msg_lines = [t for _, _, t in op["ch"].outbox[-3:]]
    say(op, change, CHAT)
    c = card(op)
    assert c[0].startswith("That stopped the send I had waiting. Reply \"send\" to send this version.\n\n" + NEW)
    assert draft_row(op)["status"] == "link_shown" and op["bot"].store.get_state(f"sendhold:{H}") is None
    tick_at(op, 3)
    assert sends() == [] and msg_lines
    say(op, "send", CHAT)            # the new version needs its own "send"
    tick_at(op, 3)
    assert len(sends()) == 1
    m = message_from_bytes(sends()[0], policy=policy.default)
    assert m.get_content().replace("\r\n", "\n").rstrip("\n") == c[1]


def test_rule_a_token_for_an_old_version_is_refused_by_the_registry(op):
    from mvp.actions import Refused, make_yes_token, perform, text_hash
    from mvp.actions.base import Ctx
    from mvp.drafts import exact_text
    bot = op["bot"]
    row = draft(op)
    old = make_yes_token(row["id"], row["version"], row["text_hash"])
    say(op, "say I'm home after 5", CHAT)
    ctx = Ctx(bot=bot, person=bot.store.person(H), answer={}, picks=[], kind="draft", now=op["clock"][0])
    with pytest.raises(Refused):
        perform("mailbox.send", ctx, {"draft_id": row["id"]}, yes_token=old)
    with pytest.raises(Refused):
        perform("mailbox.send", ctx, {"draft_id": row["id"]}, yes_token=None)
    now = draft_row(op)
    good = make_yes_token(now["id"], now["version"], text_hash(exact_text(now["to_addr"], now["subject"], now["body"])))
    assert perform("mailbox.send", ctx, {"draft_id": row["id"]}, yes_token=good).status == "done"
    assert len(sends()) == 1


def test_rule_one_send_per_token(op):
    draft(op)
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert len(sends()) == 1
    assert say(op, "send", CHAT) == "I already sent that one at 1:03 pm."
    assert say(op, "send it now", CHAT) == "I already sent that one at 1:03 pm."
    tick_at(op, 3)
    assert len(sends()) == 1
    # a second tick, or a replayed hold, never sends it again
    from mvp.store import now_iso
    row = draft_row(op)
    op["bot"].store.set_state(f"sendhold:{H}", {"draft_id": row["id"], "version": row["version"], "token": "x",
                                                 "due_at": now_iso(op["clock"][0]), "at": now_iso(op["clock"][0])})
    tick_at(op, 1)
    assert len(sends()) == 1


def test_rule_a_placeholder_blocks_the_send(op):
    bot = op["bot"]
    bot.draft_start(bot.store.person(H), "notice", to="help@gym.example", subject="Cancel my membership",
                    paragraphs=["Please cancel my membership.", "Member number: (fill this in)"],
                    placeholders=["member number"])
    assert say(op, "send", CHAT) == "Fill in the member number first: reply \"member number 12345\", or \"remove it\"."
    tick_at(op, 3)
    assert sends() == [] and draft_row(op)["status"] == "link_shown"
    say(op, "member number 4471", CHAT)
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert len(sends()) == 1 and "Member number: 4471" in message_from_bytes(sends()[0], policy=policy.default) \
        .get_content()


def test_rule_a_post_s_text_never_supplies_the_recipient(op, monkeypatch):
    _bad_post(op, monkeypatch)
    say(op, "email them", CHAT)
    assert say(op, "send", CHAT) == "The email isn't finished yet. Answer my question above first, or say \"cancel\"."
    say(op, "blank", CHAT)
    assert say(op, "send", CHAT) == "I need an address to send it to. Say \"to:\" and their email address."
    tick_at(op, 3)
    assert sends() == []
    for s in FakeMailSMTP.made:
        assert all(c != ("rcpt", "bad@x.example") for c in s.calls)


@pytest.mark.parametrize("fail", [None, "login", "rcpt", "connect", "data_before", "data_after"])
def test_rule_no_reply_says_sent_before_the_server_accepted_it(op, fail):
    draft(op)
    FakeMailSMTP.fail = fail
    before = len(op["ch"].outbox)
    say(op, "send", CHAT)
    tick_at(op, 3)
    replies = [t for _, _, t in op["ch"].outbox[before:]]
    accepted = [t for t in replies if "accepted" in t or "went to" in t]
    if fail is None:
        assert accepted == [replies[-1]] and replies[-1].startswith("Your mail server accepted the email")
    else:
        assert accepted == [] and not any(" sent it" in t and "may or may not" not in t for t in replies)
        assert not any(t.startswith("Your mail server accepted") for t in replies)


# =====================================================================================================================
# Who may send, and which words send
# =====================================================================================================================
@pytest.mark.parametrize("word", ["yes", "ok", "go", "do it", "👍", "sure", "looks good"])
def test_only_the_send_words_send(op, word):
    draft(op)
    say(op, word, CHAT)
    tick_at(op, 3)
    assert sends() == [] and draft_row(op)["status"] == "link_shown"


def test_a_tapback_and_a_model_confirm_form_never_send(op):
    draft(op)
    ref = op["ch"].outbox[-1][0]
    op["bot"].on_message(H, "", tapback="up", tapback_ref=ref)
    say(op, "alright fire it off then", {"intent": "confirm"})
    tick_at(op, 3)
    assert sends() == [] and draft_row(op)["status"] == "link_shown"


@pytest.mark.parametrize("word", ["send", "send it", "send it now", "send now", "yes send it", "ok send it",
                                  "go ahead and send it", "send the email"])
def test_each_send_word_holds_then_sends(op, word):
    draft(op)
    assert say(op, word, CHAT).startswith("Sending to maria@example.com at ")
    tick_at(op, 3)
    assert len(sends()) == 1


def test_a_non_operator_gets_the_link_card_only(op, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", "+15559999999")
    draft(op)
    assert card(op)[2].startswith("Tap to open it in your mail app, check it, and press Send there:")
    assert say(op, "send", CHAT) == "I can't send from your address. Tap the link above and press Send in your mail app."
    tick_at(op, 3)
    assert sends() == [] and FakeMailSMTP.made == []


def test_mailbox_send_cannot_be_named_by_a_model_form_or_a_rule():
    from mvp.actions import REGISTRY, validate_action
    from mvp.schema import RuleSpec
    d = REGISTRY["mailbox.send"]
    assert (d.outside, d.undo, d.confirm, d.max_per_day, d.in_rules, d.who, d.from_model, d.connector, d.fallback) == \
        (True, "hold", "send_word", 5, False, "operator", False, "mailbox", "email.draft_link")
    with pytest.raises(ValueError):
        validate_action("mailbox.send", {"draft_id": 1})
    with pytest.raises(ValueError):
        validate_action("mailbox.send", {"draft_id": 1}, by="code", where="rule")
    with pytest.raises(Exception):
        RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "x y", "searches": ["a"]},
                                 "do": [{"action": "mailbox.send", "params": {"draft_id": 1}}]})


def test_a_non_operator_cannot_run_it_through_the_registry_even_with_a_token(op, monkeypatch):
    from mvp import config
    from mvp.actions import Refused, make_yes_token, perform
    from mvp.actions.base import Ctx
    row = draft(op)
    monkeypatch.setattr(config, "OPERATOR", None)
    bot = op["bot"]
    ctx = Ctx(bot=bot, person=bot.store.person(H), answer={}, picks=[], kind="draft", now=op["clock"][0])
    with pytest.raises(Refused):
        perform("mailbox.send", ctx, {"draft_id": row["id"]},
                yes_token=make_yes_token(row["id"], row["version"], row["text_hash"]))
    assert sends() == []


def test_outlook_is_refused_at_the_start(op, monkeypatch):
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "me@outlook.com")
    monkeypatch.delenv("MVP_MAILBOX_SMTP_HOST")
    draft(op)
    assert card(op)[2].startswith("Tap to open it in your mail app")
    assert say(op, "send", CHAT) == ("Outlook.com doesn't allow app passwords any more, so I can't send from it. Tap "
                                     "the link to send it yourself.")
    assert FakeMailSMTP.made == []


def test_the_default_hosts_by_domain(monkeypatch):
    from mvp.actions import mailbox
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", PASSWORD)
    monkeypatch.delenv("MVP_MAILBOX_SMTP_HOST", raising=False)
    monkeypatch.delenv("MVP_MAILBOX_SMTP_PORT", raising=False)
    for addr, want in (("a@gmail.com", ("smtp.gmail.com", 465)), ("a@icloud.com", ("smtp.mail.me.com", 587)),
                       ("a@me.com", ("smtp.mail.me.com", 587)), ("a@fastmail.com", ("smtp.fastmail.com", 465))):
        monkeypatch.setenv("MVP_MAILBOX_ADDRESS", addr)
        s = mailbox.settings()
        assert (s["host"], s["port"]) == want
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "a@unknown.example")
    assert mailbox.settings() is None
    monkeypatch.delenv("MVP_MAILBOX_APP_PASSWORD")
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "a@gmail.com")
    assert mailbox.settings() is None


def test_port_587_uses_starttls(op, monkeypatch):
    monkeypatch.setenv("MVP_MAILBOX_SMTP_PORT", "587")
    draft(op)
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert FakeMailSMTP.made[-1].calls[:2] == ["starttls", ("login", ME, True)] or \
        "starttls" in FakeMailSMTP.made[-1].calls


# =====================================================================================================================
# The hold, undo, a late hold, a restart
# =====================================================================================================================
def test_undo_in_the_hold_stops_it_and_after_says_it_went(op):
    draft(op)
    say(op, "send", CHAT)
    op["clock"][0] += timedelta(seconds=119)
    assert say(op, "undo", CHAT) == "Stopped. Nothing was sent. Reply \"send\" when you're ready."
    tick_at(op, 3)
    assert sends() == [] and draft_row(op)["status"] == "link_shown"
    say(op, "send", CHAT)
    tick_at(op, 2.02)
    assert len(sends()) == 1
    op["clock"][0] += timedelta(seconds=30)
    assert say(op, "undo", CHAT) == "I can't unsend an email. It went to maria@example.com at 1:07 pm."


def test_cancel_in_the_hold_stops_it(op):
    draft(op)
    say(op, "send", CHAT)
    assert say(op, "cancel", CHAT).startswith("OK, I've dropped it. Nothing was sent.")
    tick_at(op, 3)
    assert sends() == []


def test_send_again_while_held_says_when(op):
    draft(op)
    say(op, "send", CHAT)
    assert say(op, "send", CHAT) == "It's already waiting to go at 1:02 pm. Reply \"undo\" to stop it."


def test_a_hold_more_than_15_minutes_late_is_not_sent(op):
    draft(op, "email my landlord Maria at maria@example.com that the sink is broken")
    say(op, "send", CHAT)
    tick_at(op, 18)
    assert sends() == []
    assert last(op["ch"]) == ("I didn't send your email to Maria at 1:02 pm because I was offline. Reply \"send\" to "
                              "send it now.")
    assert draft_row(op)["status"] == "link_shown"
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert len(sends()) == 1


def test_a_send_cut_off_by_a_restart_is_never_sent_again(op):
    bot = op["bot"]
    row = draft(op)
    bot.store.update_draft(row["id"], status="sending", sent_at="2026-11-12T18:00:00+00:00")
    bot.store.set_state(f"sendhold:{H}", None)
    tick_at(op, 3)
    assert sends() == []
    assert last(op["ch"]) == ("I may or may not have sent the email to m***@example.com before I restarted. Check "
                              "your Sent folder before you ask me again.")
    assert draft_row(op)["status"] == "unknown"
    tick_at(op, 3)
    assert sends() == []


def test_the_30_minute_freshness_shows_it_again(op):
    draft(op)
    op["clock"][0] += timedelta(minutes=31)
    msg = say(op, "send", CHAT)
    assert msg == "That draft is from 1:00 pm. Reply \"send\" if it's still right."
    assert texts_of(op, 4)[0].startswith(HEAD)
    assert draft_row(op)["status"] == "link_shown"
    assert say(op, "send", CHAT).startswith("Sending to maria@example.com at ")


def texts_of(e, n):
    return [t for _, _, t in e["ch"].outbox[-n:]]


# =====================================================================================================================
# Errors and the daily cap
# =====================================================================================================================
@pytest.mark.parametrize("fail,line,status", [
    ("login", "Your mailbox refused my sign-in, so nothing was sent. Tap the link to send it yourself.", "failed"),
    ("rcpt", "The address was refused, so nothing was sent. Check it and say \"to: <address>\".", "failed"),
    ("connect", "I couldn't reach your mailbox, so nothing was sent.", "failed"),
    ("data_before", "I couldn't reach your mailbox, so nothing was sent.", "failed"),
    ("data_after", "I may or may not have sent it. Check your Sent folder before you ask me again.", "unknown"),
])
def test_the_four_error_lines(op, fail, line, status):
    draft(op)
    FakeMailSMTP.fail = fail
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert last(op["ch"]) == line and draft_row(op)["status"] == status
    log = op["bot"].store.q("SELECT status FROM action_log WHERE action='mailbox.send'")
    assert [r["status"] for r in log] == [status]


def test_a_failed_send_can_be_tried_again_with_a_new_send(op):
    draft(op)
    FakeMailSMTP.fail = "connect"
    say(op, "send", CHAT)
    tick_at(op, 3)
    FakeMailSMTP.fail = None
    say(op, "show the draft", CHAT)
    say(op, "send", CHAT)
    tick_at(op, 3)
    assert len(sends()) == 1


def test_the_sixth_send_in_a_day_is_the_person_s_own(op):
    op["bot"].max_per_minute = None
    for i in range(5):
        draft(op, f"email sam{i}@example.com that the party is at {i}")
        say(op, "send", CHAT)
        tick_at(op, 3)
    assert len(sends()) == 5
    draft(op, "email sam9@example.com that the party is at 9")
    msg = say(op, "send", CHAT)
    assert msg.startswith("I've sent 5 emails for you today, which is my limit. Tap to send this one yourself:\n"
                          "mailto:sam9@example.com?")
    tick_at(op, 3)
    assert len(sends()) == 5


# =====================================================================================================================
# What the code can and cannot do, and the secret
# =====================================================================================================================
def test_mailbox_send_never_imports_imaplib():
    import ast
    path = os.path.join(os.path.dirname(HERE), "actions", "mailbox.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("imap" in (x or "").lower() for x in names)
    assert "imaplib" not in open(path, encoding="utf-8").read()


def test_the_app_password_is_nowhere_after_a_full_run(op, capsys):
    draft(op)
    say(op, "send", CHAT)
    tick_at(op, 3)
    FakeMailSMTP.fail = "login"
    draft(op, "email jo@example.com that the party is at 8")
    say(op, "send", CHAT)
    tick_at(op, 3)
    out = capsys.readouterr()
    assert PASSWORD not in out.out and PASSWORD not in out.err
    bot = op["bot"]
    with open(bot.store.path, "rb") as f:
        assert PASSWORD.encode() not in f.read()
    for root, _, files in os.walk(os.environ["MVP_HOME"]):
        for name in files:
            with open(os.path.join(root, name), "rb") as f:
                assert PASSWORD.encode() not in f.read(), name
    assert not any(PASSWORD in t for _, _, t in op["ch"].outbox)


def test_the_hold_minutes_come_from_the_environment(op, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "SEND_HOLD_MIN", 5)
    draft(op)
    assert say(op, "send", CHAT) == "Sending to maria@example.com at 1:05 pm. Reply \"undo\" before then to stop it."
    tick_at(op, 3)
    assert sends() == []
    tick_at(op, 3)
    assert len(sends()) == 1


def test_a_sent_draft_s_log_holds_the_domain_never_the_address(op):
    draft(op)
    say(op, "send", CHAT)
    tick_at(op, 3)
    rows = op["bot"].store.q("SELECT detail FROM action_log WHERE action='mailbox.send'")
    det = json.loads(rows[0]["detail"])
    assert det["recipient_domain"] == "example.com" and "maria" not in json.dumps(det)


# =====================================================================================================================
# A5: mailbox.draft, a real draft in the Drafts folder (IMAP with a fixed allow-list)
# =====================================================================================================================
ALLOWED = {"LOGIN", "LIST", "APPEND", "SELECT", "UID STORE", "UID EXPUNGE", "LOGOUT"}


class FakeIMAP:
    """imaplib.IMAP4_SSL stand-in: records every command; any command outside ALLOWED fails the test."""
    made = []
    uidplus = True
    fail = None
    folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"',
               b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.host, self.port, self.commands, self.appended, self.selected = host, port, [], [], None
        FakeIMAP.made.append(self)
        if FakeIMAP.fail == "connect":
            raise OSError("unreachable")

    def _cmd(self, name, *args):
        assert name in ALLOWED, name
        self.commands.append((name, *args))

    def login(self, user, password):
        self._cmd("LOGIN", user, password == PASSWORD)
        if FakeIMAP.fail == "login":
            import imaplib
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"ok"]

    def list(self, directory='""', pattern="*"):
        self._cmd("LIST")
        return "OK", list(FakeIMAP.folders)

    def append(self, mailbox, flags, date_time, message):
        self._cmd("APPEND", mailbox, flags)
        if FakeIMAP.fail == "append":
            return "NO", [b"quota"]
        self.appended.append(message)
        return "OK", [b"[APPENDUID 1 4242] (Success)" if FakeIMAP.uidplus else b"(Success)"]

    def select(self, mailbox="INBOX", readonly=False):
        self._cmd("SELECT", mailbox)
        self.selected = mailbox
        return "OK", [b"1"]

    def uid(self, command, *args):
        self._cmd("UID " + command.upper(), *args)
        return "OK", [b"done"]

    def logout(self):
        self._cmd("LOGOUT")
        return "BYE", [b""]

    def __getattr__(self, name):   # fetch, search, examine, store, expunge ...: never allowed
        raise AssertionError(f"IMAP command not allowed: {name}")


@pytest.fixture()
def box(op, monkeypatch):
    from mvp.actions import mailbox_imap
    monkeypatch.setenv("MVP_MAILBOX_IMAP_HOST", "imap.example.invalid")
    monkeypatch.setattr(mailbox_imap.imaplib, "IMAP4_SSL", FakeIMAP)
    FakeIMAP.made, FakeIMAP.uidplus, FakeIMAP.fail = [], True, None
    return op


def appended():
    return [m for c in FakeIMAP.made for m in c.appended]


def commands():
    return [c for x in FakeIMAP.made for c in x.commands]


def test_a5_save_it_as_a_draft_puts_the_shown_card_in_drafts_and_keeps_the_card(box):
    draft(box)
    c = card(box)
    msg = say(box, "save it as a draft", CHAT)
    assert msg == ("I saved it in your Drafts folder (maria@example.com is filled in). Nothing has been sent. Reply "
                   "\"undo\" within 10 minutes to take it out again.")
    got = appended()
    assert len(got) == 1
    m = message_from_bytes(got[0], policy=policy.default)
    assert m["To"] == "maria@example.com" and m["From"] == ME
    assert m.get_content().replace("\r\n", "\n").rstrip("\n") == c[1]
    assert [x[0] for x in commands()] == ["LOGIN", "LIST", "APPEND", "LOGOUT"]
    assert commands()[2][1:] == ('"[Gmail]/Drafts"', "(\\Draft)")
    assert sends() == [] and draft_row(box)["status"] == "link_shown"
    assert say(box, "send", CHAT).startswith("Sending to maria@example.com at ")   # the card is still open


@pytest.mark.parametrize("text", ["put this in my email", "save it as a draft", "draft it in my gmail",
                                  "put it in my drafts"])
def test_a5_with_no_card_the_answer_goes_to_drafts_addressed_to_them(box, text):
    one_pick(box)
    msg = say(box, text, CHAT)
    assert msg.startswith(f"I saved it in your Drafts folder ({ME} is filled in). Nothing has been sent.")
    m = message_from_bytes(appended()[0], policy=policy.default)
    body = m.get_content()
    assert m["To"] == ME and "Lemon garlic pasta" in body and "Sent by" not in body


def test_a5_put_the_second_one_in_my_drafts(box):
    box["state"]["answers"]["mvp_compose"] = compose_picks(
        {"n": 1, "title": "Lemon garlic pasta", "why": "Fits.", "verdict": "clear"},
        {"n": 2, "title": "Pasta night", "why": "Fits.", "verdict": "clear"})
    from mvp.tests.test_slice2 import ask_pasta
    form = ask_pasta()
    form["spec"]["content"]["count"] = 2
    say(box, "pasta", form)
    say(box, "put the second one in my drafts", CHAT)
    m = message_from_bytes(appended()[0], policy=policy.default)
    assert m["Subject"] == "Pasta night" and "Lemon garlic" not in m.get_content()


def test_a5_undo_deletes_only_that_uid_in_that_folder(box):
    draft(box)
    say(box, "save it as a draft", CHAT)
    assert say(box, "undo", CHAT) == "Undone: I deleted the draft from your Drafts folder."
    last_conn = FakeIMAP.made[-1].commands
    assert last_conn == [("LOGIN", ME, True), ("SELECT", '"[Gmail]/Drafts"'),
                         ("UID STORE", "4242", "+FLAGS", "(\\Deleted)"), ("UID EXPUNGE", "4242"), ("LOGOUT",)]
    assert all(c[1] == '"[Gmail]/Drafts"' for c in commands() if c[0] == "SELECT")


def test_a5_without_uidplus_the_reply_says_it_cannot_be_undone(box):
    FakeIMAP.uidplus = False
    draft(box)
    assert say(box, "save it as a draft", CHAT).endswith(
        "I can't take it out again from here, so delete it in Drafts if you change your mind.")
    assert say(box, "undo", CHAT) == "I can't take back a draft in your Drafts folder, so I left everything else as it was."
    assert not any(c[0].startswith("UID") for c in commands())


def test_a5_no_drafts_flag_uses_the_usual_name(box):
    FakeIMAP.folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Drafts"']
    try:
        draft(box)
        say(box, "save it as a draft", CHAT)
        assert commands()[2][1] == '"Drafts"'
    finally:
        FakeIMAP.folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"',
                            b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']


@pytest.mark.parametrize("fail,line", [
    ("login", "I couldn't save it to your Drafts folder: your mailbox refused my sign-in."),
    ("connect", "I couldn't save it to your Drafts folder: I couldn't reach your mailbox."),
    ("append", "I couldn't save it to your Drafts folder: your mailbox said no."),
])
def test_a5_a_failure_says_what_failed_then_the_link(box, fail, line):
    FakeIMAP.fail = fail
    draft(box)
    assert say(box, "save it as a draft", CHAT) == line + " Tap the link above to open it in your mail app instead."
    one_pick(box)
    say(box, "cancel", CHAT)
    msg = say(box, "put this in my email", CHAT)
    assert msg.startswith(line + "\nHere it is as an email to yourself.") and "mailto:" in msg


def test_a5_never_reads_the_mailbox(box):
    draft(box)
    say(box, "save it as a draft", CHAT)
    say(box, "undo", CHAT)
    one_pick(box)
    say(box, "put this in my email", CHAT)
    names = {c[0] for c in commands()}
    assert names <= ALLOWED and not names & {"FETCH", "SEARCH", "EXAMINE", "UID FETCH", "UID SEARCH"}
    assert all(c[1] != '"INBOX"' and c[1] != "INBOX" for c in commands() if c[0] == "SELECT")
    import ast
    path = os.path.join(os.path.dirname(HERE), "actions", "mailbox_imap.py")
    src = open(path, encoding="utf-8").read()
    calls = {n.func.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "conn"}
    assert calls <= {"login", "list", "append", "select", "uid", "logout"}


def test_a5_a_non_operator_keeps_the_old_way(box, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", None)
    draft(box)
    assert say(box, "save it as a draft", CHAT) == (
        "I can't save to your Drafts folder. Tap the link above: it opens the email in your mail app, where you can "
        "save it as a draft.")
    say(box, "cancel", CHAT)
    one_pick(box)
    say(box, "put this in my email", {"intent": "act_on_last", "actions": ["email.send"]})
    assert FakeIMAP.made == []


def test_a5_mailbox_draft_cannot_be_named_by_a_model_or_a_rule():
    from mvp.actions import REGISTRY, validate_action
    d = REGISTRY["mailbox.draft"]
    assert (d.outside, d.undo, d.confirm, d.max_per_day, d.in_rules, d.who, d.from_model) == \
        (True, "delete", "never", 20, False, "operator", False)
    with pytest.raises(ValueError):
        validate_action("mailbox.draft", {})


def test_a5_the_21st_draft_in_a_day_falls_back_with_the_cap_line(box):
    box["bot"].max_per_minute = None
    one_pick(box)
    for _ in range(20):
        assert say(box, "put this in my email", CHAT).startswith("I saved it in your Drafts folder")
    msg = say(box, "put this in my email", CHAT)
    assert msg.startswith("I've reached my limit of 20 drafts a day for you.") and "mailto:" in msg
    assert len(appended()) == 20


def test_a5_the_password_is_in_no_log_and_the_log_has_no_address(box, capsys):
    FakeIMAP.fail = "login"
    draft(box)
    say(box, "save it as a draft", CHAT)
    FakeIMAP.fail = None
    say(box, "save it as a draft", CHAT)
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err
    blob = json.dumps(box["bot"].store.q("SELECT * FROM action_log"))
    assert PASSWORD not in blob and "maria@" not in blob
    with open(box["bot"].store.path, "rb") as f:
        assert PASSWORD.encode() not in f.read()
