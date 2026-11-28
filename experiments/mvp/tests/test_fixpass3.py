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


# ======================================= 67. the outside block and its search =======================================
from mvp.tests.test_slice3 import add_items  # noqa: E402
from mvp.tests.test_slice5 import FakeYouTube, KEY  # noqa: E402

COOK = "what should I cook tonight?"
COOK_FORM = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
    "goal": "something to cook tonight", "searches": ["cook tonight", "easy dinner recipe"],
    "criteria": ["ends with a dish you can eat"]}}}
RECIPES = [{"id": f"itm_r{i}", "platform": "instagram", "source_url": f"https://example.com/r{i}",
            "caption": f"{name}\nIngredients:\n- 2 cups rice\n- 1 tbsp oil\nBake for 20 minutes",
            "interaction_kinds": ["save"], "platform_data": {"owner_handle": "chef", "owner_relation": "following"}}
           for i, name in enumerate(["Sheet pan chicken", "Veggie fried rice", "Baked salmon", "Bean chili"])]


def test_67a_a_library_with_plenty_of_recipes_gets_no_uninvited_outside_block(yt):
    add_items(yt, [dict(r) for r in RECIPES])
    yt["bot"].pool.search = lambda lib, q, depth=300: {"ids": [r["id"] for r in RECIPES], "mode": "normal",
                                                       "cost_usd": 0.0}
    # the composer shows one pick and cannot quote "a dish you can eat": a close verdict, so its clear count is 0
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "verdict": "clear", "title": "Sheet pan chicken", "criteria": [{"answer": "unknown"}]}]}
    msg = say(yt, COOK, COOK_FORM)
    assert "Sheet pan chicken" in msg
    assert "Not from your saves" not in msg and "YouTube" not in msg and "You only have" not in msg
    assert not yt["yt"].searches()


def test_67b_the_search_is_topic_words_plus_one_fixed_kind_word_and_time_words_are_dropped():
    from mvp.outside import request_kind, search_text
    from mvp.schema import RuleSpec

    def spec(goal, *searches):
        return RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": goal, "searches": list(searches),
                                                                            "outside": "some"}})
    assert search_text(spec("something to cook tonight", "cook tonight"), [COOK]) is None     # no topic word: none
    assert search_text(spec("a dinner to make this week", "dinner this week"),
                       ["give me something to make for dinner this week"]) == "dinner recipe"
    assert search_text(spec("lemon pasta for tonight", "lemon pasta tonight"),
                       ["lemon pasta for tonight, and some new ones"]) == "lemon pasta"   # no kind said: none added
    assert search_text(spec("a lemon pasta recipe for tonight", "lemon pasta tonight"),
                       ["a lemon pasta recipe for tonight, and some new ones"]) == "lemon pasta recipe"
    assert search_text(spec("a short leg workout", "leg workout today"),
                       ["a short leg workout for today plus new ones"]) == "leg workout"
    assert search_text(spec("a blender donut tutorial", "blender donut"),
                       ["show me new blender donut videos to make"]) == "blender donut tutorial"
    assert search_text(spec("a quick workout", "quick workout"), ["a quick workout for today"]) is None
    # the kind word is code's, from the person's words: never the model's wording
    assert request_kind(["I want to cook something with leeks"]) == "recipe"
    assert request_kind(["leeks"], spec("leek soup recipe", "leek soup")) == "recipe"
    assert request_kind(["leeks"]) is None


def _news_fake():
    def v(vid, title, channel, cat):
        return {"id": vid, "snippet": {"title": title, "channelTitle": channel, "liveBroadcastContent": "none",
                                       "categoryId": cat},
                "status": {"privacyStatus": "public", "embeddable": True, "madeForKids": False},
                "contentDetails": {"duration": "PT5M"}}
    vids = [v("NEWSvid0001", "Chicken curry prices soar, says Cook", "Evening News", "25"),
            v("NEWSvid0002", "Mr Cook speaks tonight", "World News", "25"),
            v("FOODvid0001", "Easy Chicken Curry in 30 Minutes", "Home Kitchen", "26"),
            v("OFFtopic001", "What I eat in a day", "Vlogs", "22"),
            v("FOODvid0002", "Weeknight curry", "CHICKEN masters", "26")]
    return FakeYouTube([x["id"] for x in vids], vids)


def test_67cd_news_and_off_topic_results_are_dropped_unless_news_was_asked_for(env, monkeypatch):
    from mvp.outside import Outside
    from mvp.schema import RuleSpec
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    fake = _news_fake()
    o = Outside(env["bot"].store, http=fake)
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "chicken curry recipes", "searches": ["chicken curry"], "outside": "some"}})
    res = o.find(H, spec, ["chicken curry recipes, and some new ones from outside my saves"])
    assert fake.searches()[-1][1]["q"] == "chicken curry recipe"
    # the news clips (category 25) go; "What I eat in a day" shares no topic word; a channel name may carry it
    assert [p["video_id"] for p in res["picks"]] == ["FOODvid0001", "FOODvid0002"]
    news = o.find(H, RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "chicken curry news", "searches": ["chicken curry news"], "outside": "some"}}),
        ["any news about chicken curry? new videos please"])
    assert "NEWSvid0001" in [p["video_id"] for p in news["picks"]]
    from mvp.outside import shares_topic
    assert not shares_topic({"title": "Cooking tonight", "channel": "x"}, ["cook"])   # whole words only
    assert shares_topic({"title": "PASTAS of Rome", "channel": "x"}, ["pasta"])


# ======================================= 68. several actions, the ingredients =======================================
from mvp.tests.test_slice4 import last_code  # noqa: E402

WIDE = lambda u: {"picks": [  # noqa: E731  a recipe answer: one recommended pick and two wider links
    {"n": 1, "title": "Lemon garlic pasta", "verdict": "clear", "lines": ["200g spaghetti", "2 lemons"]},
    {"n": 2, "title": "Creamy mushroom pasta", "verdict": "clear"},
    {"n": 3, "title": "Pasta night", "verdict": "clear"}], "intro": "Here you go."}


def test_68_email_it_and_add_the_ingredients_adds_one_to_do_per_ingredient_line_and_the_email_still_goes(env):
    bot, st = env["bot"], env["state"]
    st["answers"]["mvp_compose"] = WIDE
    spec = pasta_spec({"type": "now"})
    say(env, "a lemon pasta recipe", {"intent": "ask", "spec": spec})
    assert len(bot.store.last_answer(H)["items"]) > 1          # wider links: still one recommended pick
    msg = say(env, "email it to me and add the ingredients to my grocery list",
              {"intent": "act_on_last", "actions": ["email.send", {"action": "todo.add", "params": {"list": "grocery"}}]})
    todos = bot.store.todos(H)
    assert [t["text"] for t in todos] == ["200g spaghetti", "2 lemons"] and {t["list"] for t in todos} == {"grocery"}
    assert "Lemon garlic pasta" not in [t["text"] for t in todos]
    assert "email" in msg.lower()                              # the address is asked for
    # the address and its code come later: the held email goes then
    def answers():
        return [r for r in outbox_rows(bot, "email") if not r["subject"].startswith("Your code")]
    say(env, "my email is a@b.co", {"intent": "set_email", "email": "a@b.co"})
    assert not answers()
    say(env, last_code(bot), {"intent": "chat"})
    assert [r["subject"] for r in answers()] == ["Lemon garlic pasta"]     # the held email went once confirmed
    # the single action reads the same, also with the wider links in the answer
    for t in list(todos):
        bot.store.x("DELETE FROM todos WHERE id=?", (t["id"],))
    say(env, "add its ingredients to my shopping list", {"intent": "todo_add", "what": "ingredients", "list": "shopping"})
    assert [t["text"] for t in bot.store.todos(H)] == ["200g spaghetti", "2 lemons"]
    # model variants: the ingredient to-do in `also`, or as the to-do's text
    for t in bot.store.todos(H):
        bot.store.x("DELETE FROM todos WHERE id=?", (t["id"],))
    say(env, "email it to me and add the ingredients to my grocery list",
        {"intent": "act_on_last", "actions": ["email.send"],
         "also": {"intent": "todo_add", "todo_text": "the ingredients", "list": "grocery"}})
    assert [t["text"] for t in bot.store.todos(H)] == ["200g spaghetti", "2 lemons"]
    # found by the live check: both at once (the action and an `also` of the same to-do) writes each line once
    for t in bot.store.todos(H):
        bot.store.x("DELETE FROM todos WHERE id=?", (t["id"],))
    say(env, "email it to me and add the ingredients to my grocery list",
        {"intent": "act_on_last", "actions": ["email.send", "todo.add"],
         "also": {"intent": "todo_add", "list": "grocery", "todo_text": "ingredients"}})
    todos = bot.store.todos(H)
    assert [t["text"] for t in todos] == ["200g spaghetti", "2 lemons"] and {t["list"] for t in todos} == {"grocery"}
    # a to-do of its own beside the action stays
    from mvp.tests.test_interpret_round import S as settle
    it = settle({"intent": "act_on_last", "actions": ["email.send", "todo.add"],
                 "also": {"intent": "todo_add", "todo_text": "buy milk"}}, "email it and add it, and add buy milk to my list")
    assert it.also is not None and it.also.todo_text == "buy milk"


# ======================================= 69. the person's own word for a saved rule ==================================
def test_69_when_i_say_boost_gives_their_word_back_and_the_word_runs_the_rule_before_any_model_call(env):
    from mvp.core import Bot
    from mvp.store import Store
    from mvp import config
    bot, ch, st = env["bot"], env["ch"], env["state"]
    form = {"intent": "new_rule", "spec": {"when": {"type": "on_request"}, "content": {
        "goal": "a motivational video", "searches": ["motivational video"]}}}
    msg = say(env, "when I say boost, send me a motivational video", form)
    n = bot.store.rule_number(H, bot.store.rules(H)[-1]["id"])
    assert msg.startswith(f'Saved. Say "boost" whenever you want one (or "run {n}").')
    assert "Ask for it" not in msg
    st["answers"]["mvp_compose"] = lemon_pick()
    calls = sum(1 for c in env["calls"] if c == "mvp_interpret")
    bot.on_message(H, "Boost!")
    assert sum(1 for c in env["calls"] if c == "mvp_interpret") == calls     # read by code, no model call
    assert "I recommend" in last(ch)                                         # the rule ran
    # after a restart: a new bot on the same store still knows the word
    bot2 = Bot(ch, store=Store(config.DB), pool=bot.pool, clock=bot.clock)
    st["answers"]["mvp_interpret"] = lambda u: (_ for _ in ()).throw(AssertionError("model called"))
    n_out = len(ch.outbox)
    bot2.on_message(H, "BOOST")
    assert len(ch.outbox) > n_out and "I recommend" in "\n".join(t for _, _, t in ch.outbox[n_out:])
    from mvp.followup import trigger_word
    assert trigger_word('whenever I text "pasta time" send me a pasta recipe') == "pasta time"
    assert trigger_word("when I say so, remind me") is None
    assert trigger_word("send me a motivational video") is None


# ======================================= 70. the count is said once =======================================
def test_70_the_goal_shown_does_not_repeat_the_count():
    from mvp import texts
    assert texts.picks_for(3, "3 videos about investing") == '3 picks for "videos about investing"'
    assert texts.picks_for(3, "three videos about investing") == '3 picks for "videos about investing"'
    assert texts.picks_for(1, "5 minute workouts") == '1 pick for "5 minute workouts"'   # not the count: kept
    assert texts.picks_for(2, "2") == '2 picks for "2"'


def test_70_the_rule_preview_says_3_picks_for_videos_about_investing(env):
    bot, st = env["bot"], env["state"]
    st["answers"]["mvp_compose"] = lemon_pick()
    form = {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON"], "times": ["09:00"]},
                                           "content": {"goal": "3 videos about investing", "count": 3,
                                                       "searches": ["investing videos"]}}}
    msg = say(env, "every monday send me 3 videos about investing", form)
    assert '3 picks for "videos about investing"' in msg and '"3 videos' not in msg


# ======================================= 71. no Steps label under a talk =======================================
TALK_ITEM = {"id": "itm_talk", "platform": "instagram", "source_url": "https://example.com/talk",
             "caption": "My TEDx talk on investing\n1. Start early\n2. Spend less than you earn\n3. Buy index funds",
             "interaction_kinds": ["save"], "platform_data": {"owner_handle": "speaker", "owner_relation": "following"}}
LIST_LINES = ["1. Start early", "2. Spend less than you earn", "3. Buy index funds"]


def _one(env, item):
    add_items(env, [dict(item)])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": [item["id"]], "mode": "normal", "cost_usd": 0.0}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "title": "Investing talk", "verdict": "clear", "lines": LIST_LINES}], "intro": "Here you go."}


def test_71_a_talk_or_a_how_to_about_something_nobody_makes_gets_no_steps_label(env):
    from mvp.extract import default_extract
    from mvp.schema import RuleSpec
    _one(env, TALK_ITEM)
    for text, goal in (("send me an investing tutorial", "an investing tutorial"),
                       ("how to start investing", "how to start investing")):
        n = sum(1 for c in env["calls"] if c == "mvp_extract")
        msg = say(env, text, {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
            "goal": goal, "searches": [goal]}}})
        # round 7 (finding 90) changes this on purpose: a request that is not a recipe, a workout or a make-or-build
        # tutorial now gets the named things its picks list, then their key points (the gist); never Steps
        assert "Steps" not in msg, text
    # what still gets steps: recipes, workouts and make-or-build tutorials; every other request: items, key points
    def spec(goal):
        return RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": goal, "searches": [goal]}})
    assert default_extract(spec("a blender donut tutorial")) == ["steps"]
    assert default_extract(spec("a quick pasta recipe")) == ["ingredients", "steps"]
    assert default_extract(spec("a leg workout")) == ["steps"]
    assert default_extract(spec("how to start investing")) == ["items", "key_points"]   # round 7
    asked = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "the investing talk",
                                                                         "searches": ["investing"],
                                                                         "extract": ["key_points"]}})
    assert default_extract(asked) == ["key_points"]


# ======================================= 72 and 73. the last setup message =======================================
from mvp.tests.test_fixpass2 import CHAT, _to_the_last_message  # noqa: E402

KIT = {"kind": "about_me", "tools": ["instant pot"], "time": "about 20 minutes a day"}


@pytest.mark.parametrize("text", ["yes. I have an instant pot and about 20 minutes a day",
                                  "Yes, I have an instant pot and about 20 minutes a day",
                                  "yeah! i have an instant pot, about 20 minutes a day",
                                  "sounds good. I have an instant pot and about 20 minutes a day"])
def test_72_a_yes_with_extra_words_starts_the_export_reminders_and_keeps_the_kit_and_time(rich, text):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: dict(KIT)
    out = say(rich, text, {"intent": "profile_update"})
    assert out.startswith("Done. Next Instagram reminder"), out
    assert "an instant pot" in out and "about 20 minutes a day" in out
    assert bot.store.rules(H) and bot.store.pending(H) is None


@pytest.mark.parametrize("text", ["no. I have an instant pot and about 20 minutes a day",
                                  "no thanks, I have an instant pot and about 20 minutes a day"])
def test_72_a_no_with_extra_words_starts_nothing_and_says_so(rich, text):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: dict(KIT)
    out = say(rich, text, {"intent": "profile_update"})
    assert "Done. Next" not in out and not bot.store.rules(H) and bot.store.pending(H) is None
    assert out.startswith("OK, no export reminders.") and "an instant pot" in out


def test_72_a_bare_answer_to_the_kit_question_keeps_the_offer_open(rich):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: dict(KIT)
    out = say(rich, "I have an instant pot and about 20 minutes a day", {"intent": "profile_update"})
    assert "an instant pot" in out and "Done. Next" not in out
    assert bot.store.pending(H)["kind"] == "confirm_rule"             # the reminders still wait for a yes
    assert say(rich, "yes", {"intent": "confirm"}).startswith("Done. Next Instagram reminder")


def test_73_kit_and_time_notes_read_as_plain_sentences(rich):
    from mvp import texts
    from mvp.profile import kit_words
    assert kit_words(["Instant Pot"]) == "an Instant Pot"
    assert kit_words(["air fryer", "rice cooker"]) == "an air fryer and a rice cooker"
    assert kit_words(["knives", "my wok", "a blender"]) == "knives, my wok and a blender"
    msg = texts.profile_changed(["you usually have about 20 minutes a day", "you have an Instant Pot"])
    assert msg.startswith("Noted: you usually have about 20 minutes a day, and you have an Instant Pot.")
    st = rich["state"]
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "tools": ["Instant Pot"]}
    out = say(rich, "I have an Instant Pot", {"intent": "profile_update"})
    assert out.startswith("Noted: you have an Instant Pot.")
    st["answers"]["mvp_profile_show"] = None
    shown = say(rich, "what do you know about me", {"intent": "profile_show"})
    assert "you have an instant pot" in shown.lower()


# ======================================= checker of fix pass 3 =======================================
@pytest.mark.parametrize("form", [
    {"intent": "act_on_last", "actions": ["email.send", {"action": "todo.add", "params": {"list": "shopping"}}]},
    {"intent": "act_on_last", "actions": ["email.send", "todo.add"], "todo_list": "shopping"},
    {"intent": "act_on_last", "actions": ["email.send"],
     "also": {"intent": "todo_add", "todo_text": "what I need to buy", "list": "shopping"}},
])
def test_check68_put_what_i_need_to_buy_on_my_shopping_list_adds_the_ingredients(env, form):
    bot, st = env["bot"], env["state"]
    st["answers"]["mvp_compose"] = WIDE
    say(env, "a lemon pasta recipe", {"intent": "ask", "spec": pasta_spec({"type": "now"})})
    say(env, "send it to my email and put what I need to buy on my shopping list", form)
    todos = bot.store.todos(H)
    assert [t["text"] for t in todos] == ["200g spaghetti", "2 lemons"] and {t["list"] for t in todos} == {"shopping"}


def test_check68_add_it_to_my_shopping_list_is_still_the_pick(env):
    bot, st = env["bot"], env["state"]
    st["answers"]["mvp_compose"] = WIDE
    say(env, "a lemon pasta recipe", {"intent": "ask", "spec": pasta_spec({"type": "now"})})
    say(env, "email it to me and add it to my shopping list",
        {"intent": "act_on_last", "actions": ["email.send", {"action": "todo.add", "params": {"list": "shopping"}}]})
    assert [t["text"] for t in bot.store.todos(H)] == ["Lemon garlic pasta"]


@pytest.mark.parametrize("text", ["when I send you a link, save it and send me similar ones",
                                  "when I write a note send me a pasta recipe",
                                  "when I text you, send me a workout"])
def test_check69_an_event_is_not_a_word_to_say(text):
    from mvp.followup import trigger_word
    assert trigger_word(text) is None
    assert trigger_word('when I say "the usual", send me a pasta recipe') == "the usual"   # quoted: their word


def test_check69_the_word_inside_a_longer_message_goes_to_the_model(env):
    st = env["state"]
    form = {"intent": "new_rule", "spec": {"when": {"type": "on_request"}, "content": {
        "goal": "a pasta recipe", "searches": ["pasta recipe"]}}}
    assert say(env, "when I say pasta, send me a pasta recipe", form).startswith('Saved. Say "pasta"')
    st["answers"]["mvp_compose"] = lemon_pick()
    calls = sum(1 for c in env["calls"] if c == "mvp_interpret")
    say(env, "any pasta with mushrooms?", {"intent": "chat", "reply": "ok"})
    assert sum(1 for c in env["calls"] if c == "mvp_interpret") == calls + 1


def test_check71_a_recipe_that_says_lets_talk_still_gets_its_ingredients(env):
    from mvp.extract import default_fits
    item = {"id": "itm_tk", "platform": "instagram", "source_url": "https://example.com/tk",
            "caption": "Let's talk about this lemon pasta, one of the reasons I love lemons\nIngredients:\n"
                       "- 200g spaghetti\n- 2 lemons\nBoil the pasta",
            "interaction_kinds": ["save"], "platform_data": {"owner_handle": "chef", "owner_relation": "following"}}
    add_items(env, [item])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_tk"], "mode": "normal", "cost_usd": 0.0}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "title": "Lemon pasta", "verdict": "clear", "lines": ["200g spaghetti", "2 lemons"]}], "intro": "x"}
    msg = say(env, "a lemon pasta recipe", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a lemon pasta recipe", "searches": ["lemon pasta recipe"]}}})
    assert "Ingredients" in msg
    assert not default_fits(TALK_ITEM["caption"])                         # the talk still gets none
    assert default_fits("My leg day habits\n3 sets of 12 squats")


@pytest.mark.parametrize("model", [
    {"type": "random", "per": "week", "count": 1, "days": ["MON", "TUE", "WED", "THU", "FRI"]},
    {"type": "random", "per": "week", "count": 1, "every_weeks": 2, "days": ["MON", "TUE", "WED", "THU", "FRI"]},
    {"type": "schedule", "every_weeks": 2, "days": ["THU"], "times": ["09:00"]},
])
def test_check66_every_other_week_on_a_random_weekday_is_one_send_in_every_second_week(env, model):
    from zoneinfo import ZoneInfo
    from mvp.schedule import describe, next_run
    it = S(note(model, "clean the fridge"), "every other week on a random weekday remind me to clean the fridge")
    w = it.spec.when
    assert (w.type, w.per, w.count, w.every_weeks, w.days) == ("random", "week", 1, 2, ["MON", "TUE", "WED", "THU", "FRI"])
    assert describe(w) == "once every other week at a random time on weekdays"
    tz = "America/New_York"
    made = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)
    monday0 = made.astimezone(ZoneInfo(tz)).date() - timedelta(days=3)
    t, sends = made, []
    for _ in range(12):
        t = next_run(w, tz, t, anchor=made, seed=9)
        sends.append(t.astimezone(ZoneInfo(tz)))
    weeks = [(s.date() - monday0).days // 7 for s in sends]
    assert all(k % 2 == 0 for k in weeks) and len(set(weeks)) == len(weeks)     # one send, in every 2nd week only
    assert all(s.weekday() < 5 and 9 <= s.hour < 21 for s in sends)
    assert len({s.weekday() for s in sends}) > 1                               # the day is drawn, not fixed
    # a time stays a fixed day; random cadence words other than weeks stay refused
    it = S(note({"type": "random", "per": "week", "count": 1}, "x"), "every other week at a random time remind me")
    assert it.spec.when.type == "schedule" and it.spec.when.every_weeks == 2
    from mvp.schema import When
    with pytest.raises(ValueError):
        When(type="random", per="day", count=1, every_weeks=2)
    assert describe(When(type="random", per="week", count=2, every_weeks=3)) == \
        "about 2 times every 3 weeks at random times"


def test_check66_a_window_that_is_all_quiet_hours_is_said_plainly(env):
    from mvp import texts
    bot = env["bot"]
    bot.store.set_quiet(H, [{"start": "17:00", "end": "23:00"}])
    msg = say(env, "remind me every 2 days sometime in the evening to stretch",
              note({"type": "random", "per": "day", "count": 1, "window": ["17:00", "21:00"]}))
    assert texts.ALL_QUIET in msg and not bot.store.rules(H, statuses=("active",))
