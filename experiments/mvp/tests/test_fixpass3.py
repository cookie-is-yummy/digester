"""Offline tests for fix pass 3 (live findings of 12 Nov evening, round 3): one or more tests per finding 65 to 73, each
failing without its fix. Synthetic data, a fake model, a fake search pool, a fake YouTube and a fake clock only; the
fixtures come from the earlier test files."""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402,F401
from mvp.tests.test_slice4 import ask_with, confirmed, outbox_rows  # noqa: E402,F401
from mvp.tests.test_slice5 import standard_fake, yt  # noqa: E402,F401
from mvp.tests.test_slice6 import AllPool, pick, rich, start  # noqa: E402,F401

UTC = timezone.utc


# ======================================= 65. refs across a restart =======================================
def test_65_the_test_page_still_answers_after_a_restart_on_the_same_store(env):
    from mvp.channels.web import WebChannel
    from mvp.runtime import Runtime
    bot, st = env["bot"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi!"}

    def one_run(text):
        web = WebChannel(serve=False)   # a new process: the page's counter starts again from 1
        web.attach(bot)
        bot.channel = web
        rt = Runtime(bot, web, workers=0, join_seconds=0)
        try:
            web.post_message(H, text)
            rt.step()
            return [m for m in web.threads[H] if m["dir"] == "out"]
        finally:
            web.close()
    assert one_run("hello")
    assert one_run("hello again")                 # the same number as before the restart: still answered
    rows = bot.store.q("SELECT ref, status FROM inbound WHERE handle=? ORDER BY id", (H,))
    assert [r["status"] for r in rows] == ["done", "done"] and rows[0]["ref"] != rows[1]["ref"]


def test_65_console_refs_differ_across_runs_and_a_dropped_duplicate_leaves_a_row(env):
    from mvp.channels.base import Inbound
    from mvp.channels.console import ConsoleChannel
    from mvp.runtime import Runtime
    a, b = ConsoleChannel(printer=None), ConsoleChannel(printer=None)
    assert a.send(H, "x") != b.send(H, "x")       # the sent table is keyed by the reference
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi!"}
    rt = Runtime(bot, ch, workers=0, join_seconds=0)
    ch.inbox.put(Inbound(handle=H, text="hi", ref="sb-1"))
    rt.step()
    ch.inbox.put(Inbound(handle=H, text="hi", ref="sb-1"))   # the provider sends the same webhook again
    rt.step()
    rows = bot.store.q("SELECT status, error, text FROM inbound WHERE handle=? ORDER BY id", (H,))
    assert [r["status"] for r in rows] == ["done", "duplicate"]
    assert rows[1]["text"] is None and "same reference" in rows[1]["error"]
    assert len(ch.outbox) == 1


# ======================================= 66. spacing and randomness =======================================
from mvp.tests.test_interpret_round import S  # noqa: E402

DAY_WINDOW = ["09:00", "21:00"]


def note(when, text="stretch"):
    return {"intent": "new_rule", "spec": {"when": when, "content": {"source": "note", "text": text}}}


# the forms the live interpreter returned for these phrasings (diagnosis run, 13 Nov), and what code must store
CASES_66 = [
    ("remind me every 2 days at a random time to stretch",
     {"type": "random", "window": DAY_WINDOW, "per": "day", "count": 1},
     {"type": "schedule", "every_days": 2, "window": DAY_WINDOW}),
    ("every 3 days at a random time remind me to tidy my desk",      # refused twice live: random with every_days
     {"type": "random", "every_days": 3, "window": DAY_WINDOW},
     {"type": "schedule", "every_days": 3, "window": DAY_WINDOW}),
    ("remind me every 2 days to drink more water",
     {"type": "schedule", "times": ["09:00"]},
     {"type": "schedule", "every_days": 2, "times": ["09:00"]}),
    ("remind me every other day at 7am to water the plants",
     {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "times": ["07:00"]},
     {"type": "schedule", "every_days": 2, "times": ["07:00"]}),
    ("randomly, about twice a week, remind me to call grandma",
     {"type": "random", "per": "week", "count": 3},
     {"type": "random", "per": "week", "count": 2, "window": DAY_WINDOW}),
    ("remind me to stretch at random times on weekends",
     {"type": "random", "days": ["SAT", "SUN"], "window": DAY_WINDOW, "per": "week", "count": 1},
     {"type": "random", "days": ["SAT", "SUN"], "per": "week", "count": 2}),
    ("a few times a month remind me to back up my laptop",
     {"type": "schedule", "month_days": [12], "every_months": 1, "times": ["19:00"]},
     {"type": "random", "per": "month", "count": 3, "window": DAY_WINDOW}),
    ("every 2 days sometime in the afternoon remind me to go for a walk",
     {"type": "schedule", "every_days": 2, "times": ["15:00"]},
     {"type": "schedule", "every_days": 2, "window": ["12:00", "17:00"]}),
    ("every other week at a random time remind me to clean the fridge",
     {"type": "random", "per": "week", "count": 1},
     {"type": "schedule", "every_weeks": 2, "days": ["THU"], "window": DAY_WINDOW}),
]


@pytest.mark.parametrize("text,model,want", CASES_66, ids=[c[0][:40] for c in CASES_66])
def test_66_the_spacing_and_the_randomness_said_are_stored(env, text, model, want):
    it = S(note(model), text)
    assert it.intent == "new_rule"
    w = it.spec.when.model_dump()
    for k, v in want.items():
        assert w[k] == v, (k, w)
    if want["type"] == "schedule" and "window" in want:
        assert not w["times"]


def test_66_once_in_a_while_asks_how_often_and_a_yes_takes_the_default(env):
    from mvp import texts
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: note({"type": "random", "per": "week", "count": 1}, "journal")
    bot.on_message(H, "remind me to journal once in a while")
    assert last(ch) == texts.HOW_OFTEN_ASK and "9am and 9pm" in last(ch)
    assert bot.store.pending(H)["kind"] == "clarify" and not bot.store.rules(H)
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "confirm"}
    bot.on_message(H, "yes")
    rules = bot.store.rules(H)
    assert len(rules) == 1 and rules[0]["status"] == "active"
    w = rules[0]["spec"]["when"]
    assert (w["type"], w["count"], w["per"]) == ("random", 1, "week")
    assert "once a week at a random time" in last(ch)
    # an answer with a frequency is the model's form as usual, with the spacing kept by code
    st["answers"]["mvp_interpret"] = lambda u: note({"type": "random", "per": "week", "count": 1}, "read")
    bot.on_message(H, "remind me to read once in a while")
    st["answers"]["mvp_interpret"] = lambda u: note({"type": "random", "per": "day", "count": 1}, "read")
    bot.on_message(H, "every 3 days")
    w = bot.store.rules(H)[-1]["spec"]["when"]
    assert (w["type"], w["every_days"], w["window"]) == ("schedule", 3, DAY_WINDOW)


def test_66_the_confirmation_says_every_2_days_at_a_random_time_between_9am_and_9pm(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: note({"type": "random", "window": DAY_WINDOW, "per": "day", "count": 1})
    bot.on_message(H, "remind me every 2 days at a random time to stretch")
    assert "every 2 days at a random time between 9am and 9pm" in last(ch)
    assert "once a day" not in last(ch)


def test_66_every_2_days_at_a_random_minute_keeps_the_spacing_across_the_clock_change(env):
    from mvp.schedule import next_run
    from mvp.schema import When
    w = When(type="schedule", every_days=2, window=DAY_WINDOW)
    tz = "America/New_York"
    made = datetime(2026, 10, 27, 14, 0, tzinfo=UTC)        # Tue 27 Oct, 10am in New York; clocks go back 1 Nov
    t, sends = made, []
    for _ in range(6):
        t = next_run(w, tz, t, anchor=made, seed=42)
        sends.append(t)
    local = [s.astimezone(__import__("zoneinfo").ZoneInfo(tz)) for s in sends]
    days = [d.date() for d in local]
    assert all((b - a).days == 2 for a, b in zip(days, days[1:]))           # every 2 days, through 1 Nov
    assert all(9 <= d.hour < 21 for d in local)                              # inside the window, local time
    assert len({(d.hour, d.minute) for d in local}) > 1                      # a different minute each due day
    assert next_run(w, tz, made, anchor=made, seed=42) == sends[0]           # seeded: the same after a restart
    # quiet hours that cover most of the window leave only the free part
    quiet = [{"start": "08:00", "end": "20:00"}]
    q = next_run(w, tz, made, anchor=made, seed=42, quiet=quiet).astimezone(__import__("zoneinfo").ZoneInfo(tz))
    assert q.hour == 20
