"""Offline tests for the final check after the four review fix passes (privacy, reliability, cost-failure, experience):
what was left where two fixes meet. Fakes only: no network, no real data, no model calls."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_review_experience import DAYS, H, note, say, tick_at, w  # noqa: E402,F401  (w is a fixture)


def test_the_test_pages_rules_panel_shows_the_numbers_the_bot_uses(w):
    """Experience X1 gave each rule a number of its own; the test page's Rules panel still numbered by place, so it
    showed "1." for the rule the bot calls rule 2 once a one-time reminder had finished."""
    from datetime import datetime, timezone
    from mvp.channels.web import WebChannel
    say(w, "remind me to buy rice in 30 minutes", note({"type": "once", "in_minutes": 30}, "buy rice"))
    b = say(w, "every day at 9am remind me to stretch", note({"type": "schedule", "days": DAYS, "times": ["09:00"]},
                                                             "stretch"))
    assert '"stop 2"' in b
    tick_at(w, datetime(2026, 11, 12, 18, 31, tzinfo=timezone.utc))   # the one-time reminder goes out and is done
    web = WebChannel(serve=False)
    web.attach(w["bot"])
    try:
        rules = web.state(H)["rules"]
    finally:
        web.close()
    assert [(r["number"], r["goal"]) for r in rules if r["status"] == "active"][0][0] == 2


def test_a_held_new_items_release_that_meets_the_cap_keeps_waiting(env, monkeypatch):
    """Cost-failure X3: the held new_items rules were deleted from the state before the release, and the release
    returns False (runs nothing) when the person is over a cap by then: the rules were then never run, without a
    word. They are kept for the next release."""
    bot = env["bot"]
    key = f"heldnew:{H}"
    bot.store.set_state(key, {"fresh": ["itm_a"], "rules": [1]})
    answers = iter([None, "daily"])   # under the cap at the check, over it when the release looks again
    monkeypatch.setattr(type(bot), "_over_cap", lambda self, person: next(answers, "daily"))
    bot._release_held(bot.clock())
    assert bot.store.get_state(key) == {"fresh": ["itm_a"], "rules": [1]}


def test_a_reminder_in_their_own_words_goes_out_when_they_are_over_the_spending_cap(w, monkeypatch):
    """Cost-failure X1 let "run 1" run a reminder over the cap, since it costs nothing; the timed send of the same
    reminder was still skipped silently for the cap ("over_cap"), unlike a to-do's reminder. A library rule is still
    skipped."""
    from datetime import datetime, timezone
    bot = w["bot"]
    say(w, "every day at 9am remind me to stretch", note({"type": "schedule", "days": DAYS, "times": ["09:00"]},
                                                         "stretch"))
    monkeypatch.setattr(type(bot), "_over_cap", lambda self, person: "daily")
    out = tick_at(w, datetime(2026, 11, 13, 14, 0, 30, tzinfo=timezone.utc))   # 9am in New York
    assert "stretch" in out
    assert bot.store.one("SELECT status FROM runs WHERE kind='scheduled' ORDER BY id DESC LIMIT 1")["status"] == "sent"


def test_not_this_creator_after_a_reminder_still_leaves_the_creator_out(w):
    """Experience X2 answers a 👍 or 👎 that follows a reminder in the person's own words as being about that
    reminder; experience X9 reads "not this creator" (feedback down or less) as about the last answer's pick. With a
    reminder sent after the answer, "not this creator" (down) got the reminder's stop hint and the creator stayed."""
    from datetime import datetime, timezone
    from mvp.tests.test_review_experience import CR, YES_ING, composer
    w["state"]["answers"]["mvp_compose"] = composer(("Instant pot chicken", "clear", YES_ING))
    say(w, "chicken and rice?", CR)
    say(w, "remind me to stretch in 30 minutes", note({"type": "once", "in_minutes": 30}, "stretch"))
    assert "stretch" in tick_at(w, datetime(2026, 11, 12, 18, 31, tzinfo=timezone.utc))
    out = say(w, "not this creator please", {"intent": "feedback", "feedback": "down"})
    assert out == "Got it: I'll leave out posts by @souschef from now on."


def test_held_notices_and_imports_are_read_again_under_the_lock(env):
    """Reliability S1 re-reads the person under their lock for timed sends, to-dos, resumes and zone reverts; the
    held notices and held import messages still used the person read before the lock, so a deletion or a snooze made
    while they waited was ignored (a notice went to a deleted person)."""
    from datetime import datetime, timezone
    from mvp.tests.test_review_reliability import race
    bot, ch = env["bot"], env["ch"]
    bot.store.set_state(f"heldnotice:{H}", ["I was offline and missed your reminder."])
    n0 = len(ch.outbox)
    race(bot, lambda: bot.store.delete_person_data(H))
    assert len(ch.outbox) == n0 and bot.store.get_state(f"heldnotice:{H}") is None
    bot.load_people()
    held = {"fresh": [], "by_source": {"instagram": 2}, "totals": {}, "refused": 0}
    bot.store.set_state(f"heldimport:{H}", held)
    race(bot, lambda: bot.store.set_snooze(H, datetime(2026, 11, 30, tzinfo=timezone.utc)))
    assert len(ch.outbox) == n0 and bot.store.get_state(f"heldimport:{H}") == held


def test_a_notice_for_a_person_who_is_gone_is_not_sent(env):
    """Any notice that time alone caused (a missed send, an ended rule, a cut answer) is sent through _notice; for a
    person no longer in the store it went out anyway."""
    bot, ch = env["bot"], env["ch"]
    bot.store.delete_person_data(H)
    n0 = len(ch.outbox)
    bot._notice(H, "I was offline and missed a send you asked for.", bot.clock())
    assert len(ch.outbox) == n0 and bot.store.get_state(f"heldnotice:{H}") is None


def test_a_code_email_that_smtp_refused_is_not_also_said_to_be_sent(env, monkeypatch):
    """Cost-failure X8 fixed the code email reply on Messages and Sendblue; where the outbox can be opened (the
    console, the test page) the reply still said "and sent a 6-digit code to it" and then "I couldn't send that
    email"."""
    from mvp.tests.test_mvp import last
    bot, ch = env["bot"], env["ch"]
    monkeypatch.setenv("MVP_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("MVP_SMTP_PORT", "1")   # refused at once, on this machine
    monkeypatch.setenv("MVP_SMTP_USER", "u")
    monkeypatch.setenv("MVP_SMTP_PASSWORD", "p")
    monkeypatch.setenv("MVP_SMTP_FROM", "bot@example.com")
    bot._set_email(bot.store.person(H), "tester@example.com", env["clock"][0])
    msg = last(ch)
    assert "sent a 6-digit code" not in msg
    assert msg.startswith("I saved tester@example.com as your email address. I couldn't email the 6-digit code")
    assert "outbox" in msg and "within 15 minutes" in msg
