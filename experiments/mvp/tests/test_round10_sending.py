"""Offline tests for round 10, slice D (DESIGN.md section 17.D): sending and notices.

D1 the send route read again at "send" (a change shows the card again and takes no yes); D2 the notice's follow-up
(a check date offered, "yes" / a day / "no", the check reminder's two answers, the second notice); D3 the route file's
facts read on 17 Nov 2026; D4 the switch-on line; and the test page's Connections panel (the addendum, section 2).
Synthetic data only: made-up names, example.com addresses, made-up passwords. A fake SMTP server; no network, no
model call (the fake model fails a test that reaches it without an answer set)."""
import http.client
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round9_cancel import entry, routes_file  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

UTC = timezone.utc
ME = "me@example.com"
PASSWORD = "fake-app-pass-1234"
NEVER_SAID = re.compile(r"\b(?:cancell?ed|canceled|you're all set)\b", re.I)
QUOTED = re.compile(r'"[^"]*"')
CHAT = {"intent": "chat", "reply": "Sure."}
MAILBOX_ENV = ("MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_MAILBOX_SMTP_HOST", "MVP_MAILBOX_SMTP_PORT",
               "MVP_SMTP_HOST", "MVP_TOKEN_KEY", "MVP_TOKEN_KEY_AUTO", "MVP_OPERATOR")


# ---------------------------------------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def b(env, monkeypatch, tmp_path):
    """The env bot on Wednesday 18 November 2026, 9am in New York; no mailbox settings; a fake SMTP server ready; a
    route file with one gym whose own page gave its address."""
    from mvp import config
    from mvp.actions import mailbox
    from mvp.tests import test_round9_mailbox as M
    for k in MAILBOX_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(config, "DRAFT_MODEL", False)
    monkeypatch.setattr(mailbox.smtplib, "SMTP_SSL", M.FakeMailSMTP)
    monkeypatch.setattr(mailbox.smtplib, "SMTP", M.FakeMailSMTP)
    M.FakeMailSMTP.made, M.FakeMailSMTP.fail = [], None
    env["clock"][0] = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)
    env["bot"].max_per_minute = None
    env["sends"] = M.sends
    routes_file(tmp_path, monkeypatch, [entry("fitco", "Fitco", route="notice", notice_email="cancel@fitco.example")])
    return env


def operator(e, monkeypatch, mailbox=True):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", H)
    if mailbox:
        mailbox_on(monkeypatch)
    return e


def mailbox_on(monkeypatch):
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", ME)
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_PORT", "465")


def mailbox_off(monkeypatch):
    for k in ("MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


def msg(e, text):
    """The person sends `text`; no model answer is set, so any model call fails the test."""
    e["bot"].on_message(H, text)
    return last(e["ch"])


def replies(e, text):
    n = len(e["ch"].outbox)
    e["bot"].on_message(H, text)
    return [m[2] for m in e["ch"].outbox[n:]]


def tick(e, minutes):
    n = len(e["ch"].outbox)
    e["clock"][0] += timedelta(minutes=minutes)
    e["bot"].tick()
    return [m[2] for m in e["ch"].outbox[n:]]


def draft(e, text="email maria@example.com that the kitchen sink is broken"):
    say(e, text, CHAT)
    return e["bot"].store.one("SELECT * FROM drafts WHERE handle=? ORDER BY id DESC LIMIT 1", (H,))


def draft_row(e):
    return e["bot"].store.one("SELECT * FROM drafts WHERE handle=? ORDER BY id DESC LIMIT 1", (H,))


def no_model(e):
    assert not e["calls"], e["calls"]


def as_web(e):
    e["ch"].name = "web"   # the test page's channel name: what the page-only lines check
    return e


def notice_ready(e, name="fitco"):
    """'cancel my <gym> membership', the name, the member number: the notice card ready to send."""
    msg(e, f"cancel my {name} membership")
    msg(e, "Alex Rivera")
    return replies(e, "member number 4471")


# =====================================================================================================================
# D1: the send route, read when the card is made and again at "send"
# =====================================================================================================================
def test_d1_sending_switched_on_after_the_card_shows_the_card_again_and_takes_no_yes(b, monkeypatch):
    """The founder's path: a card made while sending was off, then the mailbox set (here sealed through the panel),
    then "send". The card is shown again with the route as it is now; that "send" is not the yes; the next one is."""
    from mvp import panel
    operator(b, monkeypatch, mailbox=False)
    d = draft(b)
    assert d["route"] == "link"
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    panel.save("MVP_MAILBOX_ADDRESS", ME)
    panel.save("MVP_MAILBOX_APP_PASSWORD", PASSWORD)
    out = replies(b, "send")
    assert out[-1] == ("Your mail connection changed, so here's the email again. Reply \"send\" if it's still "
                       "right.")
    assert out[0].startswith("Here's the email. Nothing has been sent.")
    assert out[2].startswith(f"Reply \"send\" to send it from {ME}.")
    assert draft_row(b)["status"] == "link_shown" and draft_row(b)["route"] == "mailbox"
    assert b["bot"].store.get_state(f"sendhold:{H}") is None
    assert tick(b, 5) == [] and b["sends"]() == []
    held = msg(b, "send")
    assert held.startswith("Sending to maria@example.com at ")
    tick(b, 3)
    (m,) = b["sends"]()
    assert message_from_bytes(m, policy=policy.default)["To"] == "maria@example.com"
    no_model(b)


def test_d1_sending_switched_off_after_the_card_shows_the_link_and_sends_nothing(b, monkeypatch):
    operator(b, monkeypatch)
    assert draft(b)["route"] == "mailbox"
    mailbox_off(monkeypatch)
    out = replies(b, "send")
    assert out[-1] == ("Your mail connection changed, so here's the email again. I can't send it from here now: tap "
                       "the link to send it yourself.")
    assert out[2].startswith("Tap to open it in your mail app, check it, and press Send there:\nmailto:maria")
    assert draft_row(b)["route"] == "link" and b["bot"].store.get_state(f"sendhold:{H}") is None
    tick(b, 5)
    assert b["sends"]() == []


def test_d1_sending_switched_off_during_the_hold_sends_nothing_and_says_so(b, monkeypatch):
    operator(b, monkeypatch)
    draft(b)
    assert msg(b, "send").startswith("Sending to maria@example.com")
    mailbox_off(monkeypatch)
    out = tick(b, 3)
    assert out[0].startswith("Your mail connection changed before it went, so nothing was sent.")
    assert "mailto:" in out[-1]
    assert b["sends"]() == [] and draft_row(b)["status"] == "link_shown"
    assert b["bot"].store.get_state(f"sendhold:{H}") is None


def test_d1_send_while_held_after_the_route_changed_stops_the_hold(b, monkeypatch):
    operator(b, monkeypatch)
    draft(b)
    msg(b, "send")
    mailbox_off(monkeypatch)
    assert msg(b, "send").startswith("Your mail connection changed")
    tick(b, 3)
    assert b["sends"]() == []


def test_d1_the_three_card_cases(b, monkeypatch):
    """Operator with the mailbox: "send"; tester: the tap-to-send link; a placeholder: no link and no "send"."""
    operator(b, monkeypatch)
    draft(b)
    assert last(b["ch"]).startswith(f"Reply \"send\" to send it from {ME}. Or tap to send it yourself:\nmailto:")
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    msg(b, "cancel")
    draft(b)
    assert last(b["ch"]).startswith("Tap to open it in your mail app, check it, and press Send there:\nmailto:")
    msg(b, "cancel")
    msg(b, "cancel my fitco membership")
    assert msg(b, "Alex Rivera") == "Fill in the member number first: reply \"member number 12345\", or \"remove it\"."


def test_d1_the_send_as_route_is_a_seam_only(b):
    from mvp import drafts
    bot = b["bot"]
    assert bot.SEND_ROUTES == ("send_as", "mailbox", "link")
    assert bot._send_route(H) in ("mailbox", "link")
    with pytest.raises(drafts.NotBuilt):
        bot._send_as({"handle": H}, {}, None)


# =====================================================================================================================
# D4: "can you send it for me"
# =====================================================================================================================
@pytest.mark.parametrize("text", ["can you send it for me", "can you send it for me?", "could you send the email for me",
                                  "can u send it", "can't you send it yourself?", "would you send it for me please"])
def test_d4_a_tester_asking_hears_the_link_line_and_nothing_is_sent(b, text):
    draft(b)
    assert msg(b, text) == "I can't send from your address yet. Tap the link above and press Send in your mail app."
    assert b["bot"].store.get_state(f"sendhold:{H}") is None and b["sends"]() == []
    no_model(b)


@pytest.mark.parametrize("text", ["send it for me", "please send it for me", "send it yourself"])
def test_d4_a_tester_saying_send_it_for_me_gets_the_link_line(b, text):
    draft(b)
    assert msg(b, text) == "I can't send from your address. Tap the link above and press Send in your mail app."
    tick(b, 5)
    assert b["sends"]() == []


@pytest.mark.parametrize("text", ["send", "can you send it for me", "send it for me", "send it?"])
def test_d4_the_operator_without_a_mailbox_hears_how_to_switch_sending_on(b, monkeypatch, text):
    operator(b, monkeypatch, mailbox=False)
    draft(b)
    assert msg(b, text) == ("To let me send from your own address, the person who runs me sets MVP_MAILBOX_ADDRESS "
                            "and an app password (never in this chat).")
    as_web(b)
    assert msg(b, text) == ("To let me send from your own address, add your email address and an app password in the "
                            "Connections panel on this page (never in this chat). Then say \"send\" again.")
    assert b["bot"].store.get_state(f"sendhold:{H}") is None


def test_d4_the_operator_with_a_mailbox_asking_is_not_the_yes_but_send_it_for_me_is(b, monkeypatch):
    operator(b, monkeypatch)
    draft(b)
    assert msg(b, "can you send it for me") == "Nothing has been sent yet. Reply \"send\" when you want it to go."
    assert b["bot"].store.get_state(f"sendhold:{H}") is None
    assert msg(b, "send it for me").startswith("Sending to maria@example.com at ")
    tick(b, 3)
    assert len(b["sends"]()) == 1


def test_d4_the_words_read(b):
    from mvp.drafts import SEND_ASK, SEND_FOR_ME
    for t in ["send it for me", "please send it for me", "ok send it for me", "send the notice for me",
              "send it from my email", "send it yourself!", "just send it for me now"]:
        assert SEND_FOR_ME.match(t), t
    for t in ["can you send it", "could you send it for me?", "can u send the email", "why can't you send it"]:
        assert SEND_ASK.match(t), t
    for t in ["send it to me", "send it to my mom", "don't send it for me", "send me recipes for dinner",
              "send it for me every friday", "can you send me a recipe", "send", "send it", "for me"]:
        assert not SEND_FOR_ME.match(t) and not SEND_ASK.match(t), t


def test_d4_an_outlook_operator_hears_outlook_not_the_switch_on_line(b, monkeypatch):
    operator(b, monkeypatch, mailbox=False)
    draft(b)
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "me@outlook.com")
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", PASSWORD)
    out = msg(b, "can you send it for me")
    assert "Outlook.com doesn't allow app passwords" in out


# =====================================================================================================================
# D2: the notice that cancels by email, and its follow-up
# =====================================================================================================================
def _notice_sent(e, monkeypatch):
    operator(e, monkeypatch)
    notice_ready(e)
    assert msg(e, "send").startswith("Sending to cancel@fitco.example at ")
    return tick(e, 3)


def test_d2_the_whole_notice_conversation_by_the_mailbox(b, monkeypatch):
    """Rows 1 to 20 of the design's conversation, with the operator's mailbox: the notice goes after "send" and the
    hold; the receipt names the gym and offers a check date; "yes" takes it; the reminder says how to answer; "they
    confirmed" ends it. The bot never says the membership is cancelled."""
    bot = b["bot"]
    said = []
    out = _notice_sent(b, monkeypatch)
    (m,) = b["sends"]()
    mail = message_from_bytes(m, policy=policy.default)
    assert mail["To"] == "cancel@fitco.example" and "Member number: 4471" in mail.get_content()
    assert out == ["Your mail server accepted your cancellation notice to Fitco (cancel@fitco.example) at 9:03 am. I "
                   "can't unsend it. That doesn't end it yet: it ends when they confirm in writing. Keep their reply. "
                   "Want a reminder on Wednesday 25 November to check they confirmed? Reply \"yes\", or give another "
                   "day."]
    said += out
    (row,) = bot.store.cancellations(H)
    assert row["status"] == "notice_sent"
    said.append(msg(b, "yes"))
    assert said[-1] == "OK. On Wednesday 25 November at 9am I'll remind you to check. Reply \"stop 1\" to drop it."
    (rule,) = bot.store.rules(H)
    assert bot.store.cancellations(H)[0]["check_rule_id"] == rule["id"]
    b["clock"][0] = datetime(2026, 11, 25, 14, 1, tzinfo=UTC)
    bot.tick()
    said.append(last(b["ch"]))
    assert said[-1].startswith("Reminder: Check that Fitco confirmed your cancellation (look for their email). If they did, say "
                               "\"they confirmed\". If not, I can write a second notice.")
    said.append(msg(b, "they confirmed"))
    assert said[-1] == "Good, thanks for telling me."
    assert bot.store.cancellations(H)[0]["status"] == "person_says_done"
    for s in said:
        assert not NEVER_SAID.search(QUOTED.sub("", s)), s
    no_model(b)


def test_d2_what_did_you_do_says_i_sent_the_notice(b, monkeypatch):
    _notice_sent(b, monkeypatch)
    msg(b, "no")
    out = msg(b, "what did you do for me")
    assert "I sent 1 notice after your \"send\"" in out and "you sent" not in out


@pytest.mark.parametrize("answer,want", [
    ("friday", "OK. On Friday 20 November at 9am I'll remind you to check."),
    ("monday at 10am", "OK. On Monday 23 November at 10am I'll remind you to check."),
    ("no", "OK, no reminder."),
    ("no thanks", "OK, no reminder."),
])
def test_d2_a_day_replaces_the_offered_date_and_no_sets_nothing(b, monkeypatch, answer, want):
    _notice_sent(b, monkeypatch)
    assert msg(b, answer).startswith(want)
    rules = b["bot"].store.rules(H)
    assert len(rules) == (0 if answer.startswith("no") else 1)
    no_model(b)


def test_d2_the_bot_never_sets_the_check_by_itself(b, monkeypatch):
    _notice_sent(b, monkeypatch)
    tick(b, 60 * 24 * 8)
    assert b["bot"].store.rules(H) == []


def test_d2_after_the_link_sent_is_person_sent_with_the_same_offer(b):
    bot = b["bot"]
    notice_ready(b)
    out = msg(b, "sent")
    assert out.startswith("Thanks. That doesn't end it yet: it ends when they confirm in writing. Keep their reply. "
                          "Want a reminder on Wednesday 25 November")
    assert bot.store.cancellations(H)[0]["status"] == "person_sent"
    assert msg(b, "yes").startswith("OK. On Wednesday 25 November at 9am I'll remind you to check.")
    assert b["sends"]() == []


def _to_the_check(e):
    assert msg(e, "yes").startswith("OK. On Wednesday 25 November")
    e["clock"][0] = datetime(2026, 11, 25, 14, 1, tzinfo=UTC)
    e["bot"].tick()
    assert last(e["ch"]).startswith("Reminder: Check that Fitco confirmed")


@pytest.mark.parametrize("answer", ["no", "they didn't", "not yet", "nope", "no they haven't", "nothing yet"])
def test_d2_no_after_the_check_offers_a_second_notice_and_yes_writes_it(b, monkeypatch, answer):
    bot = b["bot"]
    _notice_sent(b, monkeypatch)
    _to_the_check(b)
    assert msg(b, answer) == ("Want me to write a second notice? It says you asked on 18 November and asks them to "
                              "confirm within 7 days.")
    out = replies(b, "yes")
    assert out[0] == ("Here's a second notice you can send to Fitco. Nothing has been sent.\nTo: cancel@fitco.example\n"
                      "Subject: Second notice: cancel my membership")
    assert out[1] == ("Hello,\n\nI asked you to cancel my membership on 18 November and have not had a confirmation. "
                      "Please cancel my membership effective immediately, stop all future charges, and confirm the "
                      "cancellation in writing within 7 days.\n\nName on the membership: Alex Rivera\nMember number: "
                      "4471\n\nThank you,\nAlex Rivera")
    assert out[2].startswith(f"Reply \"send\" to send it from {ME}.")
    assert len(b["sends"]()) == 1   # nothing more went: the second notice waits for its own "send"
    assert msg(b, "send").startswith("Sending to cancel@fitco.example")
    out = tick(b, 3)
    assert len(b["sends"]()) == 2
    assert "Want a reminder on Wednesday 2 December" in out[0]
    assert [r["status"] for r in bot.store.cancellations(H)] == ["notice_sent", "notice_sent"]
    no_model(b)


def test_d2_no_to_the_second_notice_leaves_it(b, monkeypatch):
    _notice_sent(b, monkeypatch)
    _to_the_check(b)
    msg(b, "they didn't")
    assert msg(b, "no") == "OK, I've left it. If you want one later, say \"write a second notice\"."
    assert len(b["bot"].store.drafts_of(H)) == 1
    assert replies(b, "write a second notice")[0].startswith("Here's a second notice you can send to Fitco.")
    assert b["sends"]() and len(b["sends"]()) == 1   # written, not sent


def test_d2_no_is_read_only_right_after_the_check_reminder(b, monkeypatch):
    """A plain "no" is the reminder's answer only while that reminder is the bot's newest message (72 hours)."""
    bot = b["bot"]
    _notice_sent(b, monkeypatch)
    _to_the_check(b)
    person = bot.store.person(H)
    assert bot._cancel_after_check(person, "no", b["clock"][0] + timedelta(hours=73)) is None
    assert bot._cancel_after_check(person, "what's for dinner", b["clock"][0]) is None
    bot.send(H, "Something else.")
    assert bot._cancel_after_check(person, "no", b["clock"][0]) is None
    assert bot._cancel_after_check(person, "they didn't", b["clock"][0]) is None


def test_d2_they_confirmed_it_any_time_while_a_notice_is_open(b, monkeypatch):
    _notice_sent(b, monkeypatch)
    msg(b, "yes")
    assert msg(b, "they confirmed it") == "Good. I've stopped the check reminder."
    row = b["bot"].store.cancellations(H)[0]
    assert row["status"] == "person_says_done"
    assert b["bot"].store.rule(row["check_rule_id"])["status"] == "stopped"


def test_d2_the_second_notice_asks_the_name_again_when_the_words_are_cleared(b, monkeypatch):
    """After 7 days the first notice's words are cleared (as every draft's): the second notice asks the name again and
    leaves the member number to fill in. It never makes one up."""
    bot = b["bot"]
    _notice_sent(b, monkeypatch)
    _to_the_check(b)
    bot.store.clear_old_drafts(b["clock"][0] + timedelta(days=1))
    msg(b, "no")
    assert msg(b, "yes") == "What name is the membership under? I only use it for the notice."
    out = replies(b, "Alex Rivera")
    assert "Subject: Second notice: cancel my membership" in out[0] and "Member number: (fill this in)" in out[1]
    assert "To: (type their email address" not in out[0]   # the gym's read address still fills To
    no_model(b)


def test_d2_check_dates_by_the_route_file():
    from zoneinfo import ZoneInfo
    from mvp.cancel import check_date
    thu = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)
    tz = "America/New_York"
    assert check_date(thu, tz) == datetime(2026, 11, 26, 9, 0, tzinfo=ZoneInfo(tz))
    assert check_date(thu, tz, {"notice_days": 3}) == datetime(2026, 11, 22, 9, 0, tzinfo=ZoneInfo(tz))
    assert check_date(thu, tz, {"notice_days": 3, "notice_business_days": True}) == \
        datetime(2026, 11, 24, 9, 0, tzinfo=ZoneInfo(tz))


def test_d2_one_send_per_yes_and_send_again_after_it_went(b, monkeypatch):
    _notice_sent(b, monkeypatch)
    tick(b, 5)
    assert len(b["sends"]()) == 1
    assert msg(b, "send").startswith("I already sent that one at ")
    assert len(b["sends"]()) == 1


def test_d2_the_action_log_holds_no_address_subject_or_words(b, monkeypatch):
    _notice_sent(b, monkeypatch)
    msg(b, "yes")
    rows = sqlite3.connect(b["bot"].store.path).execute("SELECT action, status, ref, detail FROM action_log").fetchall()
    blob = json.dumps(rows).lower()
    for w in ("fitco", "4471", "alex", "rivera", "cancel my membership", ME, "maria"):
        assert w not in blob, w


def test_d2_new_lines_never_say_cancelled():
    from mvp import texts as T
    for s in [T.notice_offer("Wednesday 25 November"), T.notice_check_text("Fitco"), T.second_notice_offer("18 November"),
              T.SECOND_NOTICE_NO, T.notice_accepted("Fitco", "a@example.com", "9:03 am"), T.SEND_ROUTE_CHANGED,
              T.SEND_ROUTE_GONE, T.SEND_ROUTE_GONE_HELD, T.second_notice_head("Fitco")]:
        assert not NEVER_SAID.search(QUOTED.sub("", s)), s


# =====================================================================================================================
# D3: the route file's facts (read 17 Nov 2026)
# =====================================================================================================================
def test_d3_the_route_file_facts():
    from mvp import cancel
    data = cancel.load_routes()
    ms = {m["key"]: m for m in data["merchants"]}
    assert ms["amazon_prime"]["route"] == "web"
    assert ms["amazon_prime"]["url"] == "https://www.amazon.com/mm/pipeline/cancellation"
    assert ms["audible"]["route"] == "web" and ms["audible"]["final_names"] == ["Confirm cancellation"]
    assert ms["netflix"]["final_names"] == ["Finish Cancellation"] and ms["netflix"]["domains"] == ["www.netflix.com"]
    assert ms["spotify"]["final_names"] == ["Cancel subscription"]
    assert ms["youtube_premium"]["final_names"] == ["Yes, cancel"]
    for k in ("netflix", "spotify", "youtube_premium", "amazon_prime", "audible"):
        assert "final_names" in ms[k] and ms[k]["domains"], k
    la = ms["la_fitness"]
    assert la["route"] == "notice" and "P.O. Box 54170" in la["notice_post"]
    assert la["notice_days"] == 5 and la["notice_business_days"] is True
    assert ms["planet_fitness"]["notice_days"] == 7
    assert "51355" not in json.dumps(data)   # LA Fitness's payments box: never the notice address
    for m in data["merchants"]:
        facts = [k for k in ("url", "notice_email", "notice_post", "notice_deadline", "phone") if m.get(k)]
        if facts or m.get("steps"):
            assert m.get("source_url", "").startswith("https://") and m.get("checked_on") == "2026-11-17", m["key"]


@pytest.fixture()
def real_routes(b, monkeypatch):
    from mvp import cancel
    monkeypatch.setattr(cancel, "ROUTES_PATH", os.path.join(os.path.dirname(HERE), "cancel_routes.json"))
    return b


def test_d3_la_fitness_notice_shows_the_po_box_from_its_page(real_routes):
    b = real_routes
    msg(b, "cancel my la fitness membership")
    out = "\n".join(replies(b, "Alex Rivera"))
    assert ("LA Fitness takes a written notice by post to P.O. Box 54170, Irvine, CA 92619 (from their help page, "
            "checked 17 Nov).") in out
    assert "They ask for it postmarked at least 5 business days before your next billing date" in out
    assert "51355" not in out


def test_d3_amazon_and_audible_give_steps_now(real_routes):
    b = real_routes
    out = msg(b, "cancel my amazon prime")
    assert "Open https://www.amazon.com/mm/pipeline/cancellation and sign in if it asks." in out
    msg(b, "no")
    out = msg(b, "cancel my audible")
    assert "\"Confirm cancellation\"" in out and "Apple, Google Play" in out
    no_model(b)


# =====================================================================================================================
# The Connections panel (the addendum, section 2)
# =====================================================================================================================
SECRET_VALUES = {"MVP_MAILBOX_APP_PASSWORD": "abcd efgh ijkl mnop", "MVP_TICKTICK_TOKEN": "tt-made-up-0123456789abcdef",
                 "MVP_TODOIST_TOKEN": "td-made-up-0123456789abcdef", "MVP_WEBHOOK_URL":
                 "https://hooks.example.com/made-up-0123456789", "MVP_YT_CLIENT_SECRET": "yt-made-up-secret-0123"}


def _everything_on_disk(root):
    out = b""
    for dp, _, fs in os.walk(root):
        for f in fs:
            with open(os.path.join(dp, f), "rb") as fh:
                out += fh.read()
    return out


def test_panel_a_saved_value_is_sealed_and_never_shown_again(b, capsys):
    from mvp import config, export, panel, settings
    bot = b["bot"]
    panel.save("MVP_MAILBOX_ADDRESS", "Me@Example.com")
    for k, v in SECRET_VALUES.items():
        assert panel.save(k, v) == "sealed"
    assert settings.secret("MVP_MAILBOX_APP_PASSWORD") == "abcdefghijklmnop"   # Gmail's groups of four, joined
    assert settings.secret("MVP_TICKTICK_TOKEN") == SECRET_VALUES["MVP_TICKTICK_TOKEN"]
    st = json.dumps(panel.state())
    for v in SECRET_VALUES.values():
        assert v not in st and v.replace(" ", "") not in st
    assert {r["name"]: r["words"] for r in panel.rows()}["MVP_TICKTICK_TOKEN"] == "set"
    # nowhere in the store, the files under MVP_HOME, an export, or the output
    msg(b, "export my data")
    blob = _everything_on_disk(config.HOME)
    dump = "\n".join(sqlite3.connect(bot.store.path).iterdump())
    out = capsys.readouterr()
    for v in SECRET_VALUES.values():
        for w in (v, v.replace(" ", "")):
            assert w.encode() not in blob and w not in dump and w not in out.out and w not in out.err, w
    assert panel.remove("MVP_TICKTICK_TOKEN") is True and settings.secret("MVP_TICKTICK_TOKEN") is None
    assert export  # imported: "export my data" ran above


def test_panel_turns_sending_on_for_the_operator(b, monkeypatch):
    from mvp import panel
    from mvp.actions import mailbox
    operator(b, monkeypatch, mailbox=False)
    assert panel.sending_state() == "need_both"
    panel.save("MVP_MAILBOX_ADDRESS", "me@gmail.com")
    assert panel.sending_state() == "need_both"
    panel.save("MVP_MAILBOX_APP_PASSWORD", "abcd efgh ijkl mnop")
    assert panel.sending_state() == "on" and mailbox.settings()["host"] == "smtp.gmail.com"
    assert "Sending is on" in panel.state()["sending"]
    panel.save("MVP_MAILBOX_ADDRESS", "me@unknown-provider.example")
    assert panel.sending_state() == "host"


@pytest.mark.parametrize("name,value,code", [
    ("MVP_MAILBOX_ADDRESS", "not-an-address", "address"),
    ("MVP_MAILBOX_ADDRESS", "me@", "address"),
    ("MVP_MAILBOX_ADDRESS", "me@outlook.com", "outlook"),
    ("MVP_WEBHOOK_URL", "http://hooks.example.com/abc", "https"),
    ("MVP_TICKTICK_TOKEN", "   ", "empty"),
    ("MVP_TICKTICK_TOKEN", "two words", "spaces"),
    ("MVP_TICKTICK_TOKEN", "x" * 600, "too_long"),
    ("MVP_OPENAI_API_KEY", "sk-made-up", "name"),
    ("MVP_TOKEN_KEY", "made-up", "name"),
])
def test_panel_refuses_with_a_code_and_never_the_value(b, name, value, code):
    from mvp import panel, settings
    with pytest.raises(panel.PanelError) as e:
        panel.save(name, value)
    assert e.value.code == code and str(e.value) == code
    assert not value.strip() or value.strip() not in repr(e.value)
    if name in settings.SEALABLE:
        assert settings.where(name) is None


def test_panel_will_not_shadow_a_value_set_on_the_computer(b, monkeypatch):
    from mvp import panel
    monkeypatch.setenv("MVP_TODOIST_TOKEN", "td-env-made-up-0000000000")
    with pytest.raises(panel.PanelError) as e:
        panel.save("MVP_TODOIST_TOKEN", "td-other-made-up-000000")
    assert e.value.code == "in_setting"
    row = {r["name"]: r for r in panel.rows()}["MVP_TODOIST_TOKEN"]
    assert row["state"] == "setting" and not row["removable"]


def test_panel_without_a_key_keeps_nothing(b, monkeypatch):
    from mvp import config, panel
    monkeypatch.setenv("MVP_TOKEN_KEY_AUTO", "0")
    with pytest.raises(panel.PanelError) as e:
        panel.save("MVP_TICKTICK_TOKEN", "tt-made-up-0123456789abcdef")
    assert e.value.code == "no_key"
    assert b"tt-made-up" not in _everything_on_disk(config.HOME)
    assert "set MVP_TOKEN_KEY" in panel.key_words()


def test_panel_over_http_on_the_test_page(b):
    """The page's endpoint, on a free local port (never 8765): the token is required; a value goes in; the reply and
    a later GET carry only states."""
    from mvp import settings
    from mvp.channels.web import WebChannel
    ch = WebChannel(port=0)
    try:
        def call(method, path, body=None, token=True):
            c = http.client.HTTPConnection("127.0.0.1", ch.port, timeout=5)
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-Test-Token"] = ch.token
            c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            r = c.getresponse()
            data = r.read().decode()
            c.close()
            return r.status, data
        value = SECRET_VALUES["MVP_TODOIST_TOKEN"]
        assert call("POST", "/api/connections", {"name": "MVP_TODOIST_TOKEN", "value": value}, token=False)[0] == 403
        assert settings.where("MVP_TODOIST_TOKEN") is None
        code, data = call("POST", "/api/connections", {"name": "MVP_TODOIST_TOKEN", "value": value})
        assert code == 200 and value not in data and json.loads(data)["ok"] is True
        assert settings.secret("MVP_TODOIST_TOKEN") == value
        code, data = call("GET", "/api/connections")
        assert code == 200 and value not in data
        assert {r["name"]: r["words"] for r in json.loads(data)["rows"]}["MVP_TODOIST_TOKEN"] == "set"
        code, data = call("POST", "/api/connections", {"name": "MVP_WEBHOOK_URL", "value": "http://x.example/abc"})
        assert code == 400 and json.loads(data)["error"] == "https" and "x.example" not in data
        code, data = call("POST", "/api/connections", {"name": "MVP_TODOIST_TOKEN", "remove": True})
        assert code == 200 and settings.where("MVP_TODOIST_TOKEN") is None
        page = call("GET", "/")[1]
        assert '<h2>Connections</h2>' in page and 'autocomplete="off"' in page
    finally:
        ch.close()


def test_the_chat_still_refuses_secrets_and_on_the_page_points_to_the_panel(b):
    from mvp import texts as T
    t = f"my todoist api key is {SECRET_VALUES['MVP_TODOIST_TOKEN']}"
    assert msg(b, t) == T.SECRET_IN_CHAT   # elsewhere: no panel to point to
    as_web(b)
    assert msg(b, t) == T.SECRET_IN_CHAT + " On the test page, use the Connections panel."
    assert msg(b, "my gmail app password is abcd efgh ijkl mnop").endswith(" On the test page, use the Connections "
                                                                          "panel.")
    assert msg(b, "my netflix password is hunter22") == T.CANCEL_PASSWORD
    no_model(b)


def test_connect_my_ticktick_on_the_page_names_the_panel(b, monkeypatch):
    from mvp import config
    from mvp import texts as T
    monkeypatch.setattr(config, "OPERATOR", H)
    say(b, "connect my ticktick", CHAT)
    assert last(b["ch"]) == T.TOKEN_SETUP["ticktick"]
    as_web(b)
    say(b, "connect my ticktick", CHAT)
    out = last(b["ch"])
    assert "Paste it into \"TickTick API token\" in the Connections panel" in out and "settings file" not in out
    assert out.startswith("I can add tasks to your TickTick") and "3. Text me \"check my ticktick\"." in out


def test_the_founders_path_on_the_test_page_end_to_end(b, monkeypatch):
    """The page's own person is the operator (MVP_OPERATOR unset); sending is off; a draft; "send" says how to switch
    it on; the panel takes the address and the app password; "send" shows the card again; "send" holds; it goes once;
    the receipt says the mail server accepted it."""
    from mvp import config
    from mvp.channels.web import connections_post
    monkeypatch.setattr(config, "OPERATOR", None)
    monkeypatch.setattr(config, "PAGE_OPERATOR", True)
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    as_web(b)
    draft(b)
    assert "Connections panel on this page" in msg(b, "send")
    for name, value in (("MVP_MAILBOX_ADDRESS", ME), ("MVP_MAILBOX_APP_PASSWORD", PASSWORD)):
        code, out = connections_post({"name": name, "value": value})
        assert code == 200 and value not in json.dumps(out)
    assert msg(b, "send").startswith("Your mail connection changed")
    assert msg(b, "send").startswith("Sending to maria@example.com")
    out = tick(b, 3)
    assert out[-1].startswith("Your mail server accepted the email to maria@example.com at ")
    assert len(b["sends"]()) == 1
    no_model(b)


# =====================================================================================================================
# What the new words never take (the verdict's common checks; end to end, test_round9_merge runs these hooks too)
# =====================================================================================================================
def test_no_rule_eval_text_or_rule_phrasing_matches_a_new_read():
    from mvp import cancel, drafts
    from mvp.tests.test_round9_merge import eval_texts, rule_phrasings
    texts = eval_texts() + rule_phrasings()
    assert len(texts) > 200
    reads = (drafts.SEND_FOR_ME, drafts.SEND_ASK, cancel.CONFIRMED_ANY, cancel.SECOND_ASK)
    assert [t for t in texts for rx in reads if rx.match(" ".join(t.split()))] == []
    # the check reminder's answers are read only right after that reminder; even so they take no rule text
    assert [t for t in texts if cancel.CONFIRMED.match(t) or cancel.NOT_CONFIRMED.match(t)] == []
