"""Offline tests for slice 4 (DESIGN.md sections 2, 6, 7 and 11 "To-dos and acting on answers"): the actions a rule or
an answer can do besides a chat message (email, calendar link and .ics file, to-dos), the email code, acting on the
last answer now and later, the test page's To-dos and Outbox panels, and the contact card. Synthetic data only; no
network (SMTP is a fake object); the bot fixtures come from test_mvp.py and test_slice2.py."""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

UTC = timezone.utc
ASK_EMAIL = "What's your email address? I'll send a 6-digit code there to check it's yours, then email this to you."


def ask_with(do, **content):
    a = ask_pasta()
    a["spec"]["do"] = do
    a["spec"]["content"].update(content)
    return a


def outbox_rows(bot, kind=None):
    return [r for r in reversed(bot.store.outbox(H)) if kind is None or r["kind"] == kind]


def read_eml(path):
    with open(path, "rb") as f:
        return BytesParser(policy=policy.default).parsebytes(f.read())


def last_code(bot):
    row = [r for r in outbox_rows(bot, "email") if r["subject"].startswith("Your code")][-1]
    return re.search(r"\d{6}", row["subject"]).group(0)


def confirmed(env, addr="a@b.co"):
    env["bot"].store.set_email(H, addr, verified=True)


def interpret_calls(env):
    return sum(1 for c in env["calls"] if c == "mvp_interpret")


# ---------- the email address and its code ----------
def test_code_flow_right_code_wrong_code_expiry_new_code_and_a_new_address(env):
    bot, clock = env["bot"], env["clock"]
    msg = say(env, "my email is A@B.co", {"intent": "set_email", "email": "A@B.co"})
    assert msg == ("I saved a@b.co as your email address and sent a 6-digit code to it. Text me the code within 15 "
                   "minutes to confirm it's yours. Email isn't connected here, so the code email is in the bot's outbox "
                   "folder instead of your inbox.")
    assert bot.store.email_of(H) == ("a@b.co", False)
    code = last_code(bot)
    m = read_eml(outbox_rows(bot, "email")[-1]["path"])
    assert m["To"] == "a@b.co" and code in m.get_body(("plain",)).get_content()
    n = interpret_calls(env)
    wrong = "111111" if code != "111111" else "222222"
    assert say(env, wrong, {"intent": "chat"}) == "That's not the code. You have 4 tries left."
    assert say(env, f"the code is {code[:3]} {code[3:]}", {"intent": "chat"}) == "Thanks, a@b.co is confirmed."
    assert interpret_calls(env) == n                                       # codes never reach the model
    assert bot.store.email_of(H) == ("a@b.co", True) and bot.store.get_state(f"emailcode:{H}") is None
    # a new address: saved unconfirmed (the reply says so), and its code expires after 15 minutes
    msg = say(env, "use c@d.co instead", {"intent": "set_email", "email": "c@d.co"})
    assert msg.startswith("I changed your email address to c@d.co and sent a 6-digit code to it.")
    assert "Until then I won't email you." in msg and bot.store.email_of(H) == ("c@d.co", False)
    code = last_code(bot)
    clock[0] += timedelta(minutes=16)
    assert say(env, code, {"intent": "chat"}) == "That code has expired. Reply \"new code\" and I'll send another."
    assert say(env, "send me a new code", {"intent": "chat"}).startswith("I sent a new 6-digit code to c@d.co.")
    new = last_code(bot)
    assert say(env, new, {"intent": "chat"}) == "Thanks, c@d.co is confirmed."
    # five wrong tries cancel the code; the right one then does nothing until a new code is asked for
    say(env, "e@f.co", {"intent": "set_email", "email": "e@f.co"})
    code = last_code(bot)
    wrong = "333333" if code != "333333" else "444444"
    for left in (4, 3, 2, 1):
        assert say(env, wrong, {"intent": "chat"}) == f"That's not the code. You have {left} {'try' if left == 1 else 'tries'} left."
    assert say(env, wrong, {"intent": "chat"}).startswith("That's not it either, so I've cancelled that code.")
    assert say(env, code, {"intent": "chat"}).startswith("That code was cancelled")
    assert bot.store.email_of(H) == ("e@f.co", False)
    # six digits with no code open are an ordinary message for the interpreter
    bot.store.set_state(f"emailcode:{H}", None)
    n = interpret_calls(env)
    say(env, "123456", {"intent": "chat", "reply": "What is that number for?"})
    assert interpret_calls(env) == n + 1


def test_codes_per_day_are_limited(env):
    from mvp import config
    for i in range(config.CODES_PER_DAY):
        say(env, f"x{i}@b.co", {"intent": "set_email", "email": f"x{i}@b.co"})
    assert say(env, "z@b.co", {"intent": "set_email", "email": "z@b.co"}) == \
        "I've sent enough codes for today. Please try again tomorrow."


# ---------- email.send ----------
def test_email_without_smtp_waits_for_the_address_then_goes_to_the_outbox(env):
    bot, ch = env["bot"], env["ch"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    msg = say(env, "pasta, and email it to me", ask_with(["message.send", "email.send"]))
    assert "I recommend Lemon garlic pasta" in msg and msg.endswith(ASK_EMAIL)   # the answer is never lost
    n = interpret_calls(env)
    msg = say(env, "a@b.co", {"intent": "chat"})                       # the address the bot just asked for
    assert msg.startswith("I saved a@b.co as your email address") and interpret_calls(env) == n
    ch.outbox_place = "in the Outbox panel"                            # the test page's wording
    msg = say(env, last_code(bot), {"intent": "chat"})
    assert msg == ("Thanks, a@b.co is confirmed.\nEmail isn't connected here, so I didn't send \"From your saves: a "
                   "pasta recipe\". The email is in the Outbox panel.")
    row = outbox_rows(bot, "email")[-1]
    assert row["via"] == "outbox" and row["path"].endswith(".eml") and os.path.isfile(row["path"])
    from mvp import config
    assert os.path.realpath(row["path"]).startswith(os.path.realpath(config.OUTBOX))
    m = read_eml(row["path"])
    plain, html = m.get_body(("plain",)).get_content(), m.get_body(("html",)).get_content()
    assert m["To"] == "a@b.co" and m["Subject"] == "From your saves: a pasta recipe"
    assert "I recommend Lemon garlic pasta by @chef" in plain and "https://example.com/itm_a" in plain
    assert '<a href="https://example.com/itm_a">Lemon garlic pasta</a> (Instagram)' in html
    assert "Ingredients (2):" in plain and "Not for you?" not in plain   # the checked answer, no chat footer
    logged = [(r["action"], r["status"]) for r in bot.store.q("SELECT action, status FROM action_log ORDER BY id")]
    assert logged[:2] == [("email.send", "waiting"), ("message.send", "done")] and ("email.send", "outbox") in logged
    assert bot.store.get_state(f"emailwait:{H}") is None
    # with a confirmed address, the next email goes out at once and the reply says where it is
    msg = say(env, "pasta again, email it", ask_with(["message.send", "email.send"]))
    assert msg.endswith("Email isn't connected here, so I didn't send it. The email is in the Outbox panel.")


class FakeSMTP:
    """A stand-in for smtplib.SMTP: records what the code does; never opens a socket."""
    made = []
    fail_login = False

    def __init__(self, host, port, timeout=None, **kw):
        self.host, self.port, self.calls, self.sent = host, port, [], []
        FakeSMTP.made.append(self)

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password == "app-pass"))
        if FakeSMTP.fail_login:
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, b"bad")

    def send_message(self, m):
        self.calls.append("send")
        self.sent.append(m)

    def quit(self):
        self.calls.append("quit")


def test_smtp_with_a_fake_server_and_the_fallback_when_it_fails(env, monkeypatch):
    bot = env["bot"]
    for k, v in {"MVP_SMTP_HOST": "smtp.example.invalid", "MVP_SMTP_PORT": "587", "MVP_SMTP_USER": "bot@example.invalid",
                 "MVP_SMTP_PASSWORD": "app-pass", "MVP_SMTP_FROM": "bot@example.invalid"}.items():
        monkeypatch.setenv(k, v)
    from mvp.actions import email as E
    monkeypatch.setattr(E.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.made, FakeSMTP.fail_login = [], False
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    msg = say(env, "pasta, email it", ask_with(["message.send", "email.send"]))
    assert msg.endswith("I emailed this to you at a@b.co.")
    s = FakeSMTP.made[-1]
    assert (s.host, s.port) == ("smtp.example.invalid", 587)
    assert s.calls == ["starttls", ("login", "bot@example.invalid", True), "send", "quit"]
    sent = s.sent[0]
    assert sent["To"] == "a@b.co" and "bot@example.invalid" in sent["From"]
    assert sent.get_body(("html",)) is not None and sent.get_body(("plain",)) is not None
    assert outbox_rows(bot, "email")[-1]["via"] == "smtp"
    # a revoked app password: the email is kept in the outbox and the reply says so
    FakeSMTP.fail_login = True
    msg = say(env, "pasta, email it", ask_with(["message.send", "email.send"]))
    assert msg.endswith("I couldn't send the email just now, so I put it in the bot's outbox folder instead.")
    assert outbox_rows(bot, "email")[-1]["via"] == "outbox"


def test_email_html_shows_a_youtube_thumbnail_by_url_with_a_youtube_label():
    from mvp.render import email_bodies
    parts = [{"type": "text", "text": "I recommend Donut by Synthetic Channel.\nSee https://example.com/x."},
             {"type": "link", "url": "https://www.youtube.com/watch?v=SYNvid00001", "title": "Donut <b>",
              "platform": "youtube", "video_id": "SYNvid00001"},
             {"type": "link", "url": "javascript:alert(1)", "title": "x", "platform": "instagram"}]
    text, html = email_bodies(parts, [("Add \"Donut\" to Google Calendar", "https://calendar.google.com/x?a=1&b=2")])
    assert '<img src="https://i.ytimg.com/vi/SYNvid00001/hqdefault.jpg"' in html and ">YouTube</span>" in html
    assert "Donut &lt;b&gt;" in html and "Donut <b>" not in html             # titles are escaped
    assert 'href="javascript' not in html                                  # only web links become links
    assert '<a href="https://example.com/x">https://example.com/x</a>.' in html
    assert "https://www.youtube.com/watch?v=SYNvid00001" in text and "Add \"Donut\" to Google Calendar: https://" in text


# ---------- calendar.add ----------
def cal_ctx(env, tz, picks=None, now=None, request=""):
    from mvp.actions.base import Ctx
    person = env["bot"].store.person(H)
    picks = picks if picks is not None else [{"item_id": "itm_a", "title": "Lemon garlic pasta",
                                              "url": "https://example.com/itm_a"}]
    return Ctx(bot=env["bot"], person=person, answer={"kind": "picks", "goal": "a pasta recipe", "parts": [],
                                                      "picks": picks},
               picks=picks, run_id=7, now=now or datetime(2026, 11, 12, 18, 0, tzinfo=UTC), tz=tz, request_text=request)


@pytest.mark.parametrize("tz,start_utc,end_utc", [
    ("America/Los_Angeles", "20261114T180000Z", "20261114T183000Z"),   # west of UTC (PST, -8)
    ("Asia/Tokyo", "20261114T010000Z", "20261114T013000Z"),            # east of UTC (+9)
    ("Europe/Berlin", "20261114T090000Z", "20261114T093000Z"),         # east of UTC (CET, +1)
])
def test_calendar_link_and_ics_fields_for_a_known_time_and_zone(env, tz, start_utc, end_utc):
    from urllib.parse import parse_qs, urlparse
    from mvp.actions import calendar as C
    from mvp.actions import CalendarParams
    ctx = cal_ctx(env, tz)
    out = C.run(ctx, CalendarParams(date="2026-11-14", time="10:00"))
    assert out.status == "done"
    url = out.link["url"]
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert url.startswith("https://calendar.google.com/calendar/render?action=TEMPLATE&")
    assert q["dates"] == "20261114T100000/20261114T103000" and q["ctz"] == tz   # wall time plus ctz, never Z
    assert q["text"] == "Lemon garlic pasta" and q["details"] == "From your saves: https://example.com/itm_a"
    day = "tomorrow" if tz == "Asia/Tokyo" else "on Saturday 14 November"   # in Tokyo it is already Friday the 13th
    assert out.line == f'To put "Lemon garlic pasta" on your calendar {day} at 10am, tap this link:'
    with open(out.ref, "rb") as f:
        raw = f.read()
    text = raw.decode()
    assert raw.endswith(b"\r\n") and b"\n" not in raw.replace(b"\r\n", b"")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert f"DTSTART:{start_utc}\r\n" in text and f"DTEND:{end_utc}\r\n" in text
    assert "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:" in text and "UID:r0-run7-itm_a@" in text
    assert "SUMMARY:Lemon garlic pasta\r\n" in text and "URL:https://example.com/itm_a\r\n" in text
    assert "DESCRIPTION:From your saves: https://example.com/itm_a" in text.replace("\r\n ", "")
    assert "RRULE" not in text and "VTIMEZONE" not in text                 # one event, UTC times
    assert out.attach == [("event.ics", out.ref, "text", "calendar")]


def test_calendar_defaults_all_day_past_days_long_titles_and_the_persons_own_title(env):
    from mvp.actions import calendar as C
    from mvp.actions import CalendarParams
    ctx = cal_ctx(env, "America/New_York")   # now: Thu 12 Nov, 1pm in New York
    out = C.run(ctx, CalendarParams(time="09:00"))                         # 9am has passed today: tomorrow
    assert "tomorrow at 9am" in out.line
    out = C.run(ctx, CalendarParams(time="18:30", duration_min=90))
    assert "today at 6:30pm" in out.line and "20261112T183000%2F20261112T200000" in out.link["url"]
    out = C.run(ctx, CalendarParams(date="2026-11-20"))                    # no time: all day
    assert out.line.endswith("on Friday 20 November (all day), tap this link:")
    text = open(out.ref).read()
    assert "DTSTART;VALUE=DATE:20261120" in text and "DTEND;VALUE=DATE:20261121" in text
    assert "dates=20261120%2F20261121" in out.link["url"] and "ctz" not in out.link["url"]
    assert C.run(ctx, CalendarParams(date="2026-11-10", time="10:00")).status == "skipped"   # a named day passed
    long = [{"item_id": "i", "title": "Pasta; garlic, lemon " + "très bon " * 12, "url": None}]
    out = C.run(cal_ctx(env, "UTC", picks=long), CalendarParams(time="20:00"))
    raw = open(out.ref, "rb").read()
    assert all(len(x) <= 75 for x in raw.split(b"\r\n")) and b"\r\n " in raw
    unfolded = raw.decode().replace("\r\n ", "")
    assert "SUMMARY:Pasta\\; garlic\\, lemon très bon" in unfolded and "URL:" not in unfolded
    # a title the person gave is used only when it is in their own words
    ctx = cal_ctx(env, "UTC", request="put it on my calendar as pasta night at 7")
    assert C.run(ctx, CalendarParams(time="19:00", title="Pasta night")).link["url"].count("text=Pasta%20night") == 1
    assert "text=Lemon%20garlic%20pasta" in C.run(ctx, CalendarParams(time="19:00", title="Gourmet feast")).link["url"]


def test_calendar_on_a_pick_puts_the_link_in_its_own_part_and_the_file_in_the_outbox(env):
    bot = env["bot"]
    env["ch"].link_previews = True
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    n = len(env["ch"].outbox)
    say(env, "add the first one to my calendar for Saturday at 10",
        {"intent": "act_on_last", "pick_number": 1, "actions": [{"action": "calendar.add",
                                                                 "params": {"date": "2026-11-14", "time": "10:00"}}]})
    sent = [t for _, _, t in env["ch"].outbox[n:]]
    assert sent[0] == 'To put "Lemon garlic pasta" on your calendar on Saturday 14 November at 10am, tap this link:'
    assert sent[1].startswith("https://calendar.google.com/calendar/render?action=TEMPLATE")   # alone in its message
    assert [r["kind"] for r in outbox_rows(bot)] == ["calendar"]
    log = bot.store.one("SELECT * FROM action_log WHERE action='calendar.add'")
    assert log["status"] == "done" and log["ref"].endswith(".ics")


# ---------- todo.add as an action ----------
def test_todo_add_both_forms_from_an_ask_and_from_a_rule_send(env):
    bot, clock = env["bot"], env["clock"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    msg = say(env, "a pasta recipe, put it on my grocery list",
              ask_with(["message.send", {"action": "todo.add", "params": {"list": "Grocery"}}]))
    assert "I recommend Lemon garlic pasta" in msg and msg.endswith('Added "Lemon garlic pasta" to your grocery list.')
    t = bot.store.todos(H)[0]
    assert (t["text"], t["url"], t["list"]) == ("Lemon garlic pasta", "https://example.com/itm_a", "grocery")
    # what: ingredients, on a rule's send: each checked ingredient line
    spec = pasta_spec(avoid=["cream"])
    spec["do"] = ["message.send", {"action": "todo.add", "params": {"what": "ingredients", "list": "shopping"}}]
    say(env, "pasta every friday, ingredients on my shopping list", {"intent": "new_rule", "spec": spec})
    assert "Each time I'll also put it on your list." in last(env["ch"])
    say(env, "yes", {"intent": "confirm"})
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "x",
                                                            "verdict": "clear", "lines": ["200g spaghetti", "2 lemons"]})
    bot.store.x("DELETE FROM deliveries")   # the preview's pick counts as sent: let the rule send it
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=UTC)
    assert bot.tick() == 1
    assert last(env["ch"]).endswith("Added 2 things to your shopping list: 200g spaghetti; 2 lemons.")
    assert [x["text"] for x in bot.store.todos(H) if x["list"] == "shopping"] == ["200g spaghetti", "2 lemons"]
    assert say(env, "undo", {"intent": "undo"}).startswith("Undone: I took those off your list")


def test_act_on_last_todo_and_the_todo_intent_share_one_implementation(env, monkeypatch):
    from mvp.actions import todo as todo_action
    seen = []
    real = todo_action.add
    monkeypatch.setattr(todo_action, "add", lambda *a, **k: (seen.append(a[3]), real(*a, **k))[1])
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    say(env, "add it to my list", {"intent": "act_on_last", "actions": ["todo.add"], "pick_number": 1})
    say(env, "add its ingredients to my list", {"intent": "todo_add", "pick_number": 1, "what": "ingredients"})
    assert seen == ["pick", "ingredients"]


# ---------- a spec's do, as the executor runs it ----------
def test_a_rule_whose_do_is_email_only_sends_one_line_here_and_never_twice(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    ch.outbox_place = "in the Outbox panel"   # the test page: the person can open the outbox (see the probe tests below)
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    spec = pasta_spec(avoid=["cream"])
    spec["do"] = ["email.send"]
    msg = say(env, "email me a pasta recipe every friday at 7pm", {"intent": "new_rule", "spec": spec})
    assert "I'll email it to you instead of sending it here." in msg and "Reply YES to start" in msg
    msg = say(env, "yes", {"intent": "confirm"})
    assert msg.startswith("Got it: every Friday at 7pm") and "I'll email it to you instead of sending it here." in msg
    bot.store.x("DELETE FROM deliveries")
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=UTC)
    assert bot.tick() == 1
    assert last(ch) == ('For "a pasta recipe": Email isn\'t connected here, so I didn\'t send it. The email is in the '
                        "Outbox panel.")
    assert "I recommend" not in last(ch)
    m = read_eml(outbox_rows(bot, "email")[-1]["path"])
    assert "I recommend Lemon garlic pasta" in m.get_body(("plain",)).get_content()
    # the next send's message fails once: on the retry the email is not sent again
    real = ch.send
    fails = [1]

    def flaky(handle, text):
        if fails:
            fails.pop()
            raise ConnectionError("down")
        return real(handle, text)
    ch.send = flaky
    clock[0] = datetime(2026, 11, 21, 0, 1, tzinfo=UTC)
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta night!", "why": "x", "verdict": "clear"})
    n = len(outbox_rows(bot, "email"))
    assert bot.tick() == 0
    assert len(outbox_rows(bot, "email")) == n + 1
    clock[0] += timedelta(minutes=16)
    assert bot.tick() == 1
    assert len(outbox_rows(bot, "email")) == n + 1                         # once per slot
    assert last(ch).startswith('For "a pasta recipe": Email isn\'t connected here')


def test_a_failed_action_is_said_and_never_loses_the_answer(env, monkeypatch):
    from mvp.actions import calendar as C
    bot = env["bot"]

    def broken(ctx, params):
        raise OSError("disk full")
    monkeypatch.setattr(C, "run", broken)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    msg = say(env, "pasta and put it on my calendar at 7",
              ask_with(["message.send", {"action": "calendar.add", "params": {"time": "19:00"}},
                        {"action": "todo.add"}]))
    assert "I recommend Lemon garlic pasta" in msg
    assert msg.endswith('Added "Lemon garlic pasta" to your list.\nI couldn\'t make the calendar entry this time, sorry.')
    rows = bot.store.q("SELECT action, status, detail FROM action_log ORDER BY id")
    assert [(r["action"], r["status"]) for r in rows] == [("todo.add", "done"), ("calendar.add", "failed"),
                                                          ("message.send", "done")]
    assert json.loads(rows[1]["detail"])["error"] == "OSError"


def test_a_preview_does_nothing_but_show(env):
    bot = env["bot"]
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    spec = pasta_spec(avoid=["cream"])
    spec["do"] = ["message.send", "email.send", "todo.add"]
    msg = say(env, "pasta every friday, email it and add it to my list", {"intent": "new_rule", "spec": spec})
    assert "Each time I'll also put it on your list and email it to you." in msg
    assert outbox_rows(bot) == [] and bot.store.todos(H) == [] and bot.store.q("SELECT * FROM action_log") == []


# ---------- act_on_last in full ----------
def test_act_on_last_later_sends_the_pick_as_it_was_at_the_time_named(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    msg = say(env, "remind me of the first one at 8", {
        "intent": "act_on_last", "pick_number": 1, "actions": [{}],
        "when": {"type": "once", "date": "2026-11-12", "times": ["20:00"]}})
    assert msg == 'OK. Today at 8pm I\'ll send it to you here: "Lemon garlic pasta". Reply "stop 1" to cancel.'
    r = bot.store.rules(H)[0]
    assert r["spec"]["content"] == {"source": "items", "item_ids": ["itm_a"], "goal": "Lemon garlic pasta",
                                    "count": 1, "order": "best", "outside": "none", "exclude_sent": True, "style": "full"}
    assert say(env, "undo", {"intent": "undo"}).startswith("Undone: I stopped the rule")
    say(env, "remind me of the first one at 8", {
        "intent": "act_on_last", "pick_number": 1, "actions": ["message.send"],
        "when": {"type": "once", "date": "2026-11-12", "times": ["20:00"]}})
    calls = len(env["calls"])
    clock[0] = datetime(2026, 11, 13, 1, 0, 30, tzinfo=UTC)               # 8pm in New York
    assert bot.tick() == 1
    assert len(env["calls"]) == calls                                     # no search, no model call
    sent = last(ch)
    assert sent.startswith("Here's what you asked me to send you:\nLemon garlic pasta by @chef.")
    assert "https://example.com/itm_a" in sent and "Ingredients (2):" in sent and "• 2 lemons" in sent
    assert bot.store.last_answer(H)["items"] == ["itm_a"]                 # "add it to my list" works on it next


def test_act_on_last_email_tomorrow_asks_for_the_address_and_sends_once_confirmed(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    msg = say(env, "email me this tomorrow morning", {"intent": "act_on_last", "actions": ["email.send"],
                                                      "when": {"type": "once", "date": "2026-11-13", "times": ["08:00"]}})
    assert msg.startswith('OK. Tomorrow at 8am I\'ll email it to you: "Lemon garlic pasta". Reply "stop 1" to cancel.')
    assert msg.endswith("What's your email address? I'll send a 6-digit code there to check it's yours. Until then I "
                        "can't email these.")
    say(env, "a@b.co", {"intent": "chat"})
    say(env, last_code(bot), {"intent": "chat"})
    clock[0] = datetime(2026, 11, 13, 13, 0, 30, tzinfo=UTC)
    assert bot.tick() == 1
    # on a channel with no Outbox panel the person cannot open the outbox, so the pick comes here too, with the line
    assert last(ch).startswith("Here's what you asked me to send you:\nLemon garlic pasta by @chef.")
    assert last(ch).endswith("Email isn't connected here, so I didn't send it. The email is in the bot's outbox folder.")
    m = read_eml(outbox_rows(bot, "email")[-1]["path"])
    assert m["Subject"] == "From your saves: Lemon garlic pasta" and "Lemon garlic pasta by @chef" in \
        m.get_body(("plain",)).get_content()


def test_act_on_last_now_with_a_pick_number_and_a_rules_latest_send(env):
    bot = env["bot"]
    confirmed(env)
    two = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "Fits.", "verdict": "clear",
                         "lines": ["200g spaghetti", "2 lemons"]},
                        {"n": 2, "title": "Pasta night", "why": "Fits.", "verdict": "clear"})
    env["state"]["answers"]["mvp_compose"] = two
    spec = pasta_spec({"type": "now"}, avoid=["cream"])
    spec["content"]["count"] = 2
    say(env, "two pasta ideas", {"intent": "ask", "spec": spec})
    msg = say(env, "email me the second one", {"intent": "act_on_last", "actions": ["email.send"], "pick_number": 2})
    assert msg == "Email isn't connected here, so I didn't send it. The email is in the bot's outbox folder."
    m = read_eml(outbox_rows(bot, "email")[-1]["path"])
    body = m.get_body(("plain",)).get_content()
    assert m["Subject"] == "Pasta night" and body.startswith("Pasta night by @chef.") and "Lemon" not in body
    assert say(env, "email me the 5th", {"intent": "act_on_last", "actions": ["email.send"], "pick_number": 5}) == \
        "My last message had 2 picks. Which one?"
    msg = say(env, "send me the second one again", {"intent": "act_on_last", "actions": ["message.send"],
                                                    "pick_number": 2})
    assert msg.startswith("Pasta night by @chef.")


# ---------- the test page ----------
def test_the_test_pages_todos_and_outbox_panels_and_start_over(env):
    from mvp.channels.web import WebChannel
    bot = env["bot"]
    web = WebChannel(port=0, host="127.0.0.1")
    try:
        web.attach(bot)
        bot.channel = web
        env["state"]["answers"]["mvp_compose"] = lemon_pick()
        env["state"]["answers"]["mvp_interpret"] = lambda u: ask_with(
            ["message.send", "email.send", {"action": "calendar.add", "params": {"time": "19:00"}},
             {"action": "todo.add", "params": {"list": "dinner"}}])
        confirmed(env)
        bot.on_message(H, "pasta, email it, calendar at 7 and add it to my dinner list")
        texts = [m["text"] for m in web.threads[H]]
        assert any("The email is in the Outbox panel." in t for t in texts)
        base = f"http://127.0.0.1:{web.port}"
        from urllib.parse import quote
        h = quote(H)   # "+" in a query is a space

        def get(path, token=web.token):
            req = urllib.request.Request(base + path, headers={"X-Test-Token": token})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        st = get(f"/api/state?as={h}")
        assert st["todos"] == [{"list": "dinner", "open": [{"text": "Lemon garlic pasta",
                                                            "url": "https://example.com/itm_a", "number": 1,
                                                            "due": None, "overdue": False}], "done": []}]
        kinds = [(o["kind"], o["via"]) for o in st["outbox"]]
        assert kinds == [("email", "outbox"), ("calendar", "file")]           # newest first
        mail = get(f"/api/outbox?as={h}&id={st['outbox'][0]['id']}")
        assert mail["to"] == "a@b.co" and "I recommend Lemon garlic pasta" in mail["text"]
        assert mail["attachments"] == ["event.ics"] and "Add \"Lemon garlic pasta\" to Google Calendar" in mail["text"]
        assert "<a href=" in mail["html"]
        cal = get(f"/api/outbox?as={h}&id={st['outbox'][1]['id']}")
        assert cal["text"].startswith("BEGIN:VCALENDAR")
        with pytest.raises(urllib.error.HTTPError) as e:
            get(f"/api/outbox?as={h}&id={st['outbox'][0]['id']}", token="wrong")
        assert e.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as e:
            get(f"/api/outbox?as=someone-else&id={st['outbox'][0]['id']}")   # another person's outbox: not found
        assert e.value.code == 404
        bot.store.update_todo(bot.store.todos(H)[0]["id"], done_at="2026-11-12T19:00:00+00:00")
        assert get(f"/api/state?as={h}")["todos"][0]["done"] == [{"text": "Lemon garlic pasta",
                                                                  "url": "https://example.com/itm_a"}]
        paths = [r["path"] for r in bot.store.outbox(H)]
        web._control({"op": "start_over", "handle": H})
        st = get(f"/api/state?as={h}")
        assert st["todos"] == [] and st["outbox"] == [] and not any(os.path.exists(p) for p in paths)
        assert bot.store.email_of(H) == (None, False) and bot.store.q("SELECT * FROM action_log") == []
        assert not bot.store.q("SELECT key FROM state WHERE key LIKE 'email%'")
        page = open(os.path.join(os.path.dirname(HERE), "channels", "web_page.html")).read()
        assert 'id="todos"' in page and 'id="outbox"' in page and "/api/outbox" in page and 'sandbox' in page
    finally:
        web.close()


# ---------- stores, registry, contact card ----------
def test_an_old_store_gains_the_slice_4_tables_and_columns_and_old_specs_validate(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT "
                     "NOT NULL, consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT);"
                     "INSERT INTO people(handle,library,timezone) VALUES('+1','/x','UTC');")
    db.commit()
    db.close()
    from mvp.store import Store
    s = Store(str(path))
    assert s.email_of("+1") == (None, False)
    s.set_email("+1", "a@b.co", verified=True)
    assert s.email_of("+1") == ("a@b.co", True)
    s.put_answer(1, "+1", None, "g", "picks", [{"type": "text", "text": "x"}], [])
    assert s.answer(1)["parts"] == [{"type": "text", "text": "x"}]
    s.log_action("+1", 1, None, "email.send", "outbox", ref="/p")
    s.add_outbox("+1", "email", "s", None, "outbox")
    assert s.actions_of_run(1) == [{"action": "email.send", "status": "outbox", "ref": "/p"}]
    from mvp.schema import RuleSpec
    old = {"when": {"type": "schedule", "days": ["FRI"], "time": "19:00"},
           "content": {"goal": "a pasta recipe", "searches": ["pasta"], "extract": "ingredients"},
           "do": [{"action": "todo.add", "params": {"list": "shopping"}}, "email.send"]}
    spec = RuleSpec.model_validate(old)
    assert spec.stored()["do"] == [{"action": "todo.add", "params": {"list": "shopping"}}, {"action": "email.send"}]


def test_the_registry_runs_each_action_through_its_own_module():
    from mvp.actions import REGISTRY, ordered, validate_action
    import importlib
    for name, d in REGISTRY.items():
        mod = importlib.import_module(f"mvp.actions.{d.module}")
        assert callable(mod.run), name
    assert [a.action for a in ordered([type("A", (), {"action": n}) for n in REGISTRY][::-1])] == \
        ["todo.add", "calendar.add", "email.send", "message.send"]
    assert validate_action("todo.add", {"what": "ingredients"}) == ("todo.add", {"what": "ingredients"})
    with pytest.raises(Exception):
        validate_action("todo.add", {"what": "steps"})


def test_contact_card(tmp_path):
    from mvp.contact_card import main, make_vcf
    card = make_vcf("Digest bot", "+1 (555) 010-0000")
    assert card == ("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Digest bot\r\nN:;Digest bot;;;\r\nORG:Digest bot\r\n"
                    "TEL;TYPE=CELL,VOICE:+15550100000\r\nEND:VCARD\r\n")
    with pytest.raises(ValueError):
        make_vcf("Digest bot", "call me")
    with pytest.raises(ValueError):
        make_vcf("", "+15550100000")
    out = tmp_path / "bot.vcf"
    main(["--out", str(out), "--name", "Bot, the", "--number", "+15550100000"])
    assert open(out, newline="").read().startswith("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Bot\\, the\r\n")


def test_a_one_time_search_that_points_at_a_pick_is_act_on_last(env):
    """Found live: "remind me of the second one tonight at 8" came back as new_rule with a library search."""
    from mvp.interpret import later_on_last, settle
    now = datetime(2026, 11, 12, 22, 0, tzinfo=UTC)
    form = {"intent": "new_rule", "spec": {"when": {"type": "once", "date": "2026-11-12", "time": "20:00"},
                                           "content": {"goal": "the second recipe", "searches": ["second recipe"]}}}
    last3 = {"items": ["a", "b", "c"]}
    it = later_on_last(settle(form, "remind me of the second one tonight at 8", [], now, "America/New_York"),
                       "remind me of the second one tonight at 8", last3)
    assert (it.intent, it.pick_number, [a.action for a in it.actions]) == ("act_on_last", 2, ["message.send"])
    assert (it.when.date, it.when.times) == ("2026-11-12", ["20:00"])
    it = later_on_last(settle(form, "send me that tonight at 8", [], now, "America/New_York"), "send me that tonight at 8",
                       last3)
    assert it.intent == "act_on_last" and it.pick_number is None
    note = {"intent": "new_rule", "spec": {"when": {"type": "once", "date": "2026-11-12", "time": "20:00"},
                                           "content": {"source": "note", "text": "the second one"}}}
    it = later_on_last(settle(note, "remind me of the second one tonight at 8", [], now, "America/New_York"),
                       "remind me of the second one tonight at 8", last3)   # also found live: a note "the second one"
    assert (it.intent, it.pick_number) == ("act_on_last", 2)
    plain = dict(note, spec=dict(note["spec"], content={"source": "note", "text": "call mum"}))
    assert later_on_last(settle(plain, "remind me to call mum at 8", [], now, "America/New_York"),
                         "remind me to call mum at 8", last3).intent == "new_rule"
    for text, last_ in [("remind me of the fifth one tonight", last3), ("tonight at 8 send me a pasta recipe", last3),
                        ("remind me of the second one tonight at 8", None)]:
        assert later_on_last(settle(form, text, [], now, "America/New_York"), text, last_).intent == "new_rule"
    # through the bot: the pick is sent as it was, at the time named
    bot, clock = env["bot"], env["clock"]
    two = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "Fits.", "verdict": "clear",
                         "lines": ["200g spaghetti", "2 lemons"]},
                        {"n": 2, "title": "Pasta night", "why": "Fits.", "verdict": "clear"})
    env["state"]["answers"]["mvp_compose"] = two
    spec = pasta_spec({"type": "now"}, avoid=["cream"])
    spec["content"]["count"] = 2
    say(env, "two pasta ideas", {"intent": "ask", "spec": spec})
    msg = say(env, "remind me of the second one tonight at 8", form)
    assert msg == 'OK. Today at 8pm I\'ll send it to you here: "Pasta night". Reply "stop 1" to cancel.'
    clock[0] = datetime(2026, 11, 13, 1, 0, 30, tzinfo=UTC)
    assert bot.tick() == 1 and last(env["ch"]).startswith("Here's what you asked me to send you:\nPasta night by @chef.")
