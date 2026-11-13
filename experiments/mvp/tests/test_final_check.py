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
