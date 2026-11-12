"""Checker tests for slice 4 (outputs): each one guards a gap the checker found by probing the builder's code with the
fakes. Synthetic data only; no network (SMTP is a fake object)."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402
from mvp.tests.test_slice4 import FakeSMTP, ask_with, confirmed, last_code, outbox_rows, read_eml  # noqa: E402

UTC = timezone.utc
ONLY_YOU = "I can only email you, at your own address. Say \"email it to me\" and I'll send it to you, so you can forward it."


# ---------- the address ----------
def test_an_address_must_be_one_plain_address_written_by_the_person(env):
    bot = env["bot"]
    # the model filled an address the person never wrote: no code is sent anywhere, the bot asks
    msg = say(env, "use my email please", {"intent": "set_email", "email": "made.up@x.co"})
    assert msg == "What's your email address? Type it out and I'll send a 6-digit code there to check it's yours."
    assert outbox_rows(bot) == [] and bot.store.email_of(H) == (None, False)
    # "x,y@b.co" would put two people in the To header: not taken as an address
    say(env, "x,y@b.co", {"intent": "chat", "reply": "Hm?"})
    assert outbox_rows(bot) == [] and bot.store.email_of(H) == (None, False)
    from mvp.schema import Interpretation
    with pytest.raises(Exception):
        Interpretation.model_validate({"intent": "set_email", "email": "x,y@b.co"})
    assert Interpretation.model_validate({"intent": "set_email", "email": "First.Last+tag@mail.example.co.uk"}).email \
        == "first.last+tag@mail.example.co.uk"
    # the address the bot just asked for is taken in code
    assert say(env, "a@b.co", {"intent": "chat"}).startswith("I saved a@b.co as your email address")


def test_sending_to_someone_else_is_offered_to_the_person_instead(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    assert say(env, "email this to my mom at mom@x.co", {"intent": "set_email", "email": "mom@x.co"}) == ONLY_YOU
    assert say(env, "email it to my friend", {"intent": "act_on_last", "actions": ["email.send"]}) == ONLY_YOU
    assert say(env, "forward that to my boss", {"intent": "unsupported", "reply": "I can't do that."}) == ONLY_YOU
    assert bot.store.email_of(H) == (None, False) and outbox_rows(bot) == []
    # their own words about their own address still work
    assert say(env, "my work email is me@work.co", {"intent": "set_email", "email": "me@work.co"}).startswith(
        "I saved me@work.co")


# ---------- the code ----------
def test_new_code_is_only_a_message_about_the_code_and_works_after_expiry(env):
    bot, clock = env["bot"], env["clock"]
    say(env, "my email is a@b.co", {"intent": "set_email", "email": "a@b.co"})
    n = len(outbox_rows(bot, "email"))
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    msg = say(env, "find me new videos about code reviews", ask_pasta())   # a request, not "new code"
    assert "I recommend Lemon garlic pasta" in msg and len(outbox_rows(bot, "email")) == n
    from mvp.outputs import NEW_CODE
    for t in ("new code", "send me a new code", "another code please", "I didn't get the code", "resend the code",
              "send the code again"):
        assert NEW_CODE.match(t), t
    for t in ("new code tutorials", "send me new code examples", "find me another coding video"):
        assert not NEW_CODE.match(t), t
    # a day later the code has run out: an email that needs the address says so, and "new code" sends another
    clock[0] += timedelta(days=2)
    msg = say(env, "pasta, email it", ask_with(["message.send", "email.send"]))
    assert msg.endswith("Your email isn't confirmed yet, and the code I sent to a@b.co has run out. Reply \"new code\" "
                        "and I'll send another, then email it.")
    assert say(env, "new code", {"intent": "chat"}).startswith("I sent a new 6-digit code to a@b.co.")
    msg = say(env, last_code(bot), {"intent": "chat"})
    assert msg.startswith("Thanks, a@b.co is confirmed.\n") and "From your saves: a pasta recipe" in msg
    # an unconfirmed address with no code state at all (e.g. cleared): "new code" still sends one
    bot.store.set_email(H, "c@d.co")
    bot.store.set_state(f"emailcode:{H}", None)
    assert say(env, "new code", {"intent": "chat"}).startswith("I sent a new 6-digit code to c@d.co.")


def test_a_code_sent_by_smtp_is_not_kept_in_a_file(env, monkeypatch):
    bot = env["bot"]
    for k, v in {"MVP_SMTP_HOST": "smtp.example.invalid", "MVP_SMTP_PORT": "587", "MVP_SMTP_USER": "bot@example.invalid",
                 "MVP_SMTP_PASSWORD": "app-pass", "MVP_SMTP_FROM": "bot@example.invalid"}.items():
        monkeypatch.setenv(k, v)
    from mvp.actions import email as E
    monkeypatch.setattr(E.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.made, FakeSMTP.fail_login = [], False
    msg = say(env, "my email is a@b.co", {"intent": "set_email", "email": "a@b.co"})
    assert msg == ("I saved a@b.co as your email address and sent a 6-digit code to it. Text me the code within 15 "
                   "minutes to confirm it's yours.")
    sent = FakeSMTP.made[-1].sent[0]
    code = sent["Subject"].split()[-1]
    assert code.isdigit() and len(code) == 6
    rows = outbox_rows(bot, "email")
    assert [(r["subject"], r["path"], r["via"]) for r in rows] == [("Your code (sent)", None, "smtp")]
    assert not [f for _, _, fs in os.walk(os.path.join(os.environ["MVP_HOME"], "outbox")) for f in fs]
    log = bot.store.one("SELECT ref FROM action_log WHERE action='email.code'")
    assert log["ref"] is None
    assert say(env, code, {"intent": "chat"}) == "Thanks, a@b.co is confirmed."


# ---------- acting on the last answer ----------
def test_acting_with_nothing_sent_yet_and_on_a_reminder(env):
    bot, clock = env["bot"], env["clock"]
    assert say(env, "email me that", {"intent": "act_on_last", "actions": ["email.send"]}) == \
        "I haven't sent you anything yet. Ask me for something first."
    assert say(env, "add it to my list", {"intent": "act_on_last", "actions": ["todo.add"]}) == \
        "I haven't sent you anything to add yet. Ask me for something first."
    # after a reminder, "email me that" emails the reminder (not an older answer)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    say(env, "remind me to call mum at 2pm", {"intent": "new_rule", "spec": {
        "when": {"type": "once", "date": "2026-11-12", "time": "14:00"}, "content": {"source": "note", "text": "call mum"}}})
    clock[0] = datetime(2026, 11, 12, 19, 0, 30, tzinfo=UTC)
    assert bot.tick() == 1 and last(env["ch"]) == "Reminder: call mum"
    confirmed(env)
    msg = say(env, "email me that", {"intent": "act_on_last", "actions": ["email.send"]})
    assert msg == "Email isn't connected here, so I didn't send it. The email is in the bot's outbox folder."
    m = read_eml(outbox_rows(bot, "email")[-1]["path"])
    assert m["Subject"] == "Reminder: call mum" and "Reminder: call mum" in m.get_body(("plain",)).get_content()
    assert "Lemon" not in m.get_body(("plain",)).get_content()


def test_each_action_runs_once_even_when_named_twice(env):
    bot = env["bot"]
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    msg = say(env, "email it and add it to my list", {"intent": "act_on_last",
                                                      "actions": ["email.send", "email.send", "todo.add"]})
    assert msg.count("Email isn't connected here") == 1 and len(outbox_rows(bot, "email")) == 1
    assert len(bot.store.todos(H)) == 1


# ---------- the answer is never lost ----------
def test_an_email_only_rule_without_an_address_still_brings_the_answer_here(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    ch.outbox_place = "in the Outbox panel"
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    spec = pasta_spec(avoid=["cream"])
    spec["do"] = ["email.send"]
    say(env, "email me a pasta recipe every friday at 7pm", {"intent": "new_rule", "spec": spec})
    say(env, "yes", {"intent": "confirm"})
    bot.store.x("DELETE FROM deliveries")
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=UTC)
    assert bot.tick() == 1
    sent = last(ch)
    assert "I recommend Lemon garlic pasta" in sent                       # the answer, not only "what's your email?"
    assert "What's your email address? I'll send a 6-digit code there" in sent


def test_an_email_the_person_cannot_open_or_that_failed_keeps_the_answer_here(env, monkeypatch):
    ch = env["ch"]
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    # a channel with no Outbox panel (Messages) and no SMTP: the person cannot open the outbox
    msg = say(env, "email me a pasta recipe", ask_with(["email.send"]))
    assert "I recommend Lemon garlic pasta" in msg and msg.endswith(
        "Email isn't connected here, so I didn't send it. The email is in the bot's outbox folder.")
    # on the test page the Outbox panel is where it is: one line
    ch.outbox_place = "in the Outbox panel"
    msg = say(env, "email me a pasta recipe", ask_with(["email.send"]))
    assert msg == ('For "a pasta recipe": Email isn\'t connected here, so I didn\'t send it. The email is in the Outbox '
                   "panel.")
    # a failed email: the answer and the line
    from mvp.actions import email as E

    def broken(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(E, "send", broken)
    msg = say(env, "email me a pasta recipe", ask_with(["email.send"]))
    assert "I recommend Lemon garlic pasta" in msg and msg.endswith("I couldn't email this, sorry. Ask me again in a bit.")


def test_a_title_with_a_line_break_never_breaks_the_email_header(env):
    from mvp.actions import email as E
    via, path, err = E.send(env["bot"], H, "a@b.co", "Pasta\r\nBcc: evil@x.co", "body")
    m = read_eml(path)
    assert m["Subject"] == "Pasta Bcc: evil@x.co" and m["Bcc"] is None and m["To"] == "a@b.co"


# ---------- calendar on a timed send ----------
def test_a_reminder_with_a_calendar_entry_at_its_own_time_is_today(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    say(env, "remind me to call mum at 2pm and put it on my calendar", {"intent": "new_rule", "spec": {
        "when": {"type": "once", "date": "2026-11-12", "time": "14:00"}, "content": {"source": "note", "text": "call mum"},
        "do": ["message.send", {"action": "calendar.add", "params": {"time": "14:00"}}]}})
    clock[0] = datetime(2026, 11, 12, 19, 0, 30, tzinfo=UTC)               # 30 seconds after 2pm in New York
    assert bot.tick() == 1
    assert 'To put "call mum" on your calendar today at 2pm, tap this link:' in last(ch)
    assert "dates=20261112T140000%2F20261112T143000" in last(ch)
    ics = open(outbox_rows(bot, "calendar")[-1]["path"]).read()
    assert "DTSTART:20261112T190000Z" in ics


# ---------- "remind me of the second one" read in code ----------
@pytest.mark.parametrize("text,source,intent,n", [
    ("remind me of the second one tonight at 8", "library", "act_on_last", 2),
    ("remind me of the second one tonight at 8", "note", "act_on_last", 2),
    ("send me #3 tomorrow at 9", "library", "act_on_last", 3),
    ("email me these tonight at 8", "library", "act_on_last", None),
    ("send me that again tomorrow", "library", "act_on_last", None),
    ("send me this weekend's best pasta tomorrow at 9", "library", "new_rule", None),
    ("remind me to watch the last video of the series at 8", "note", "new_rule", None),
    ("send me the first recipe I ever saved tomorrow at 9", "library", "new_rule", None),
    ("send me the second one from my baking collection at 9", "library", "new_rule", None),
])
def test_only_a_pointer_at_the_last_answer_becomes_act_on_last(env, text, source, intent, n):
    from mvp.interpret import later_on_last, settle
    now = datetime(2026, 11, 12, 22, 0, tzinfo=UTC)
    content = {"goal": "pasta ideas", "searches": ["pasta"]} if source == "library" else \
        {"source": "note", "text": "the second one" if "second" in text else "watch the last video of the series"}
    form = {"intent": "new_rule", "spec": {"when": {"type": "once", "date": "2026-11-13", "time": "20:00"},
                                           "content": content}}
    it = later_on_last(settle(form, text, [], now, "America/New_York"), text, {"items": ["a", "b", "c"]})
    assert (it.intent, it.pick_number if it.intent == "act_on_last" else None) == (intent, n)


# ---------- the test page ----------
def test_the_outbox_reader_lists_a_code_email_that_was_not_kept(env):
    from mvp.channels.web import WebChannel
    bot = env["bot"]
    web = WebChannel(port=0, host="127.0.0.1")
    try:
        web.attach(bot)
        oid = bot.store.add_outbox(H, "email", "Your code (sent)", None, "smtp")
        got = web.outbox_item(H, oid)
        assert got["text"] == "This email was sent. Its code is not kept here." and got["html"] is None
        assert web.outbox_item("someone-else", oid) is None
    finally:
        web.close()


def test_an_unasked_to_do_is_dropped_but_the_email_asked_for_stays(env):
    """'email it' read as email plus a to-do: the to-do was not asked for and goes; the email still happens."""
    bot = env["bot"]
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    msg = say(env, "email it", {"intent": "act_on_last", "actions": ["email.send", "todo.add"]})
    assert msg == "Email isn't connected here, so I didn't send it. The email is in the bot's outbox folder."
    assert bot.store.todos(H) == [] and len(outbox_rows(bot, "email")) == 1
