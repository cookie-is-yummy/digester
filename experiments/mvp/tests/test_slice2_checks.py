"""Offline tests for the checker's fixes to slice 2 (DESIGN.md sections 1, 2, 4 and 11): every rule that starts,
changes or ends is said in the reply, undo reverses the whole write, the cache never reuses a form that no longer
fits, to-dos from an answer use only what was checked, and to-do reminders survive a failing channel.
Synthetic data only; the fixtures come from test_mvp.py and test_slice2.py."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import EVERY_DAY, H, ask_pasta, lemon_pick, note_spec, say  # noqa: E402

UTC = timezone.utc


def _status(bot, n=1):
    return bot.store.one("SELECT status FROM rules ORDER BY id LIMIT 1 OFFSET ?", (n - 1,))["status"]


def _start_pasta(env, spec=None):
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "P", "why": "Good.", "verdict": "clear"})
    say(env, "pasta", {"intent": "new_rule", "spec": spec or pasta_spec()})
    say(env, "yes", {"intent": "confirm"})


# ---------- no rule ends without the reply saying so ----------
def test_quiet_hours_that_leave_a_window_rule_no_time_say_it_ended_and_undo_brings_it_back(env):
    bot = env["bot"]
    _start_pasta(env, pasta_spec({"type": "schedule", "days": EVERY_DAY, "window": ["09:00", "10:00"]}))
    msg = say(env, "no messages before 11am", {"intent": "set_quiet_hours", "end": "11:00"})
    assert _status(bot) == "done"
    assert msg.endswith('That leaves no time to send "a pasta recipe", so I stopped that rule. '
                        'Reply "undo" to keep your old quiet hours.')
    assert say(env, "undo", {"intent": "undo"}) == "Undone: your quiet hours are back as they were."
    assert _status(bot) == "active" and bot.store.quiet(H) == [{"start": "22:00", "end": "08:00"}]


def test_resume_after_the_only_time_passed_says_the_rule_is_finished(env):
    bot, clock = env["bot"], env["clock"]
    say(env, "remind me tomorrow at 7pm to call mum",
        {"intent": "new_rule", "spec": note_spec({"type": "once", "date": "2026-11-13", "time": "19:00"}, "call mum")})
    say(env, "pause 1", {"intent": "pause", "rule_number": 1})
    clock[0] = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)
    msg = say(env, "resume 1", {"intent": "resume", "rule_number": 1})
    assert _status(bot) == "done" and "Resumed" not in msg
    assert msg.startswith('"call mum" had no send left') and "finished" in msg


def test_a_time_zone_move_that_ends_a_one_off_send_says_so_and_undo_restores_it(env):
    bot = env["bot"]   # 13:00 in New York; 7pm today in Tokyo has passed
    say(env, "remind me at 7pm to call mum",
        {"intent": "new_rule", "spec": note_spec({"type": "once", "date": "2026-11-12", "time": "19:00"}, "call mum")})
    msg = say(env, "I'm in Tokyo now", {"intent": "set_timezone", "timezone": "Asia/Tokyo"})
    assert _status(bot) == "done" and '"call mum" has no send left, so I ended that rule.' in msg
    say(env, "undo", {"intent": "undo"})
    assert _status(bot) == "active" and bot.store.person(H)["timezone"] == "America/New_York"


def test_pause_then_undo_really_resumes(env):
    """The undo record was taken after the pause, so 'undo' said "back as it was" and left the rule paused."""
    bot = env["bot"]
    _start_pasta(env)
    say(env, "pause 1", {"intent": "pause", "rule_number": 1})
    assert _status(bot) == "paused"
    assert say(env, "undo", {"intent": "undo"}) == 'Undone: "a pasta recipe" is back as it was.'
    assert _status(bot) == "active" and bot.store.rules(H)[0]["next_run_at"]


# ---------- undo reverses the whole write of one message ----------
def test_undo_after_one_yes_started_two_rules_stops_both(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "W", "why": "Good.", "verdict": "clear"})
    a = pasta_spec({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI"], "time": "08:00"})
    b = pasta_spec({"type": "schedule", "days": ["SAT", "SUN"], "time": "10:00"})
    say(env, "weekdays at 8 and weekends at 10", {"intent": "new_rule", "spec": a, "also": {"intent": "new_rule", "spec": b}})
    say(env, "yes", {"intent": "confirm"})
    assert say(env, "undo", {"intent": "undo"}).startswith("Undone: I stopped the rules I just started")
    assert [r["status"] for r in bot.store.rules(H, statuses=("active", "stopped"))] == ["stopped", "stopped"]


def test_undo_after_two_adds_in_one_message_removes_both(env):
    bot = env["bot"]
    say(env, "add milk and eggs to my list",
        {"intent": "todo_add", "todo_text": "milk", "also": {"intent": "todo_add", "todo_text": "eggs"}})
    assert [t["text"] for t in bot.store.todos(H)] == ["milk", "eggs"]
    assert say(env, "undo", {"intent": "undo"}).startswith("Undone: I took those off your list")
    assert bot.store.todos(H) == []


# ---------- to-dos from an answer ----------
def test_act_on_last_keeps_a_named_list_and_does_the_part_that_works(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta, no cream", ask_pasta())
    msg = say(env, "add 1 to my grocery list", {"intent": "act_on_last", "actions": ["todo.add"], "pick_number": 1,
                                               "list": "grocery"})
    assert msg == 'Added "Lemon garlic pasta" to your grocery list.' and bot.store.todos(H)[0]["list"] == "grocery"
    msg = say(env, "add it to my list and email it to me",
              {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {"list": "My Groceries List"}},
                                                    "email.send"], "pick_number": 1})
    assert msg.startswith('Added "Lemon garlic pasta" to your groceries list. I can\'t email answers')
    assert len(bot.store.todos(H)) == 2


def test_act_on_last_with_a_rule_number_uses_that_rules_last_send(env):
    bot, clock = env["bot"], env["clock"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta every friday at 7pm", {"intent": "new_rule", "spec": pasta_spec(avoid=["cream"])})
    say(env, "yes", {"intent": "confirm"})
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=UTC)
    assert bot.tick() == 1
    sent = bot.store.items_of_run(bot.store.one("SELECT id FROM runs WHERE kind='scheduled'")["id"])
    assert [d["item_id"] for d in sent] == ["itm_c"]                        # Friday's send: "Pasta night!"
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 3, "title": "Best carbonara ever", "why": "x", "verdict": "clear"})
    say(env, "anything else", {"intent": "ask", "spec": pasta_spec({"type": "now"}, avoid=["cream"])})
    assert bot.store.last_answer(H)["items"] == ["itm_e"]
    msg = say(env, "add friday's pasta to my list", {"intent": "act_on_last", "actions": ["todo.add"], "answer_ref": "1"})
    assert msg == 'Added "Pasta night!" to your list.'


def test_a_due_time_that_has_passed_is_said(env):
    msg = say(env, "add call the dentist at 9am", {"intent": "todo_add", "todo_text": "call the dentist",
                                                   "due": "2026-11-12T09:00"})
    assert msg == 'Added "call the dentist" to your list. That time has already passed, so I didn\'t set a reminder for it.'
    assert env["bot"].store.todos(H)[0]["due_at"] is None


def test_ingredients_come_only_from_lines_that_are_ingredients_alone(env):
    from mvp.schema import Interpretation
    assert Interpretation.model_validate({"intent": "todo_add", "what": "ingredients"}).what == "ingredients"
    bot = env["bot"]
    two = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "Fits.", "verdict": "clear",
                         "lines": ["200g spaghetti", "2 lemons"]},
                        {"n": 2, "title": "Pasta night", "why": "Fits.", "verdict": "clear"})
    env["state"]["answers"]["mvp_compose"] = two
    spec = pasta_spec({"type": "now"}, avoid=["cream"])
    spec["content"]["count"] = 2
    say(env, "two pasta ideas", {"intent": "ask", "spec": spec})
    assert say(env, "add the ingredients to my list", {"intent": "todo_add", "what": "ingredients"}) == \
        "My last message had 2 picks. Which one?"                           # whose ingredients
    assert say(env, "add the ingredients of 2", {"intent": "todo_add", "pick_number": 2, "what": "ingredients"}) \
        .startswith("I don't have the ingredients") and bot.store.todos(H) == []
    # a recipe ask: the details step (extract.py) returns ingredients and steps apart, so "add its ingredients" adds
    # the ingredient lines only, never a step (slice 3; before it, mixed lines were never guessed apart)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["200g spaghetti", "2 lemons"],
                                                        "steps": ["4 cloves garlic"]}
    recipe = pasta_spec({"type": "now"}, avoid=["cream"])
    recipe["content"]["extract"] = ["ingredients", "steps"]
    bot.store.x("DELETE FROM facts")   # the first ask cached itm_a's details (no steps after two tries): start afresh
    say(env, "a pasta recipe", {"intent": "ask", "spec": recipe})
    add = {"intent": "todo_add", "pick_number": 1, "what": "ingredients"}
    assert say(env, "add its ingredients to my list", add) == "Added 2 things to your list: 200g spaghetti; 2 lemons."
    # a follow-up that found nothing new keeps what the lines were
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "x", "verdict": "clear"})
    say(env, "how long does it take?", {"intent": "follow_up", "question": "how long does it take?"})
    assert bot.store.get_state(f"linekinds:{H}") == {"itm_a": ["ingredients", "steps"]}
    assert bot.store.get_state(f"facts:{H}")["itm_a"]["ingredients"] == ["200g spaghetti", "2 lemons"]


# ---------- small things ----------
def test_profile_notes_are_kept_once(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    for _ in range(2):
        say(env, "im vegetarian now, dinner?", dict(ask_pasta(), profile_note="Vegetarian"))
    say(env, "I'm a beginner at Blender", {"intent": "profile_update"})
    say(env, "I'm a beginner at Blender", {"intent": "profile_update"})
    assert env["bot"].store.profile_notes(H) == ["Vegetarian", "I'm a beginner at Blender"]


def test_a_snooze_that_has_passed_says_nothing_changed(env):
    msg = say(env, "don't text me until yesterday", {"intent": "snooze", "until": "2026-11-11"})
    assert msg.startswith("That time has already passed, so nothing changes.") and "send it" not in msg
    assert env["bot"].store.person(H)["snooze_until"] is None


def test_a_clarify_answered_hours_later_still_completes_the_form(env):
    bot, clock = env["bot"], env["clock"]
    draft = {"when": {"type": "schedule", "days": ["SUN"], "time": "09:00"},
             "content": {"goal": "a study tip", "searches": ["study tip"]}}
    say(env, "every sunday a study tip until the end of the semester",
        {"intent": "clarify", "spec": draft, "question": "When does your semester end?"})
    clock[0] += timedelta(hours=3)
    seen = []
    say(env, "dec 18", lambda u: (seen.append(u), {"intent": "chat", "reply": "OK"})[1])
    assert "When does your semester end?" in seen[0] and bot.store.pending(H) is None   # shown, then used up


def test_top_level_calendar_params_are_read_in_their_checked_form():
    from mvp.schema import Interpretation
    it = Interpretation.model_validate({"intent": "act_on_last", "actions": ["calendar.add"],
                                        "params": {"time": "6", "duration_min": 30, "date": "2026-11-14"}})
    assert it.params == {"time": "06:00", "duration_min": 30, "date": "2026-11-14"}


# ---------- the interpretation cache ----------
def _cached_bot(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "INTERPRET_CACHE_HOURS", 6)
    seen = []
    return seen


def test_cache_never_reuses_a_question_about_another_answer(env, monkeypatch):
    seen = _cached_bot(env, monkeypatch)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta, no cream", ask_pasta())
    ask = lambda q: lambda u: (seen.append(u), {"intent": "follow_up", "question": q})[1]   # noqa: E731
    say(env, "is it spicy?", ask("is the lemon pasta spicy?"))
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Best carbonara", "why": "x", "verdict": "clear"})
    say(env, "carbonara please", {"intent": "ask", "spec": pasta_spec({"type": "now"})})
    say(env, "is it spicy?", ask("is the carbonara spicy?"))
    assert len(seen) == 2                                                   # a new answer: asked again


def test_cache_reuses_a_repeated_ask_but_not_a_moment_that_has_passed(env, monkeypatch):
    seen = _cached_bot(env, monkeypatch)
    clock = env["clock"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    for _ in range(2):
        say(env, "pasta, no cream", lambda u: (seen.append(u), ask_pasta())[1])
    assert len(seen) == 1                                                   # the same request: the same form
    at6 = lambda d: lambda u: (seen.append(u), {"intent": "new_rule", "spec": note_spec(   # noqa: E731
        {"type": "once", "date": d, "time": "18:00"}, "call mum")})[1]
    say(env, "remind me at 6 to call mum", at6("2026-11-12"))
    say(env, "stop 1", {"intent": "stop", "rule_number": 1})
    clock[0] = datetime(2026, 11, 12, 23, 30, tzinfo=UTC)                   # 6:30pm the same day
    msg = say(env, "remind me at 6 to call mum", at6("2026-11-13"))
    assert len(seen) == 3 and msg.startswith("OK. Tomorrow at 6pm")


def test_cache_rows_from_before_still_load_and_undo_changes_the_key(env, monkeypatch):
    from mvp import interpret as I
    _cached_bot(env, monkeypatch)
    store = env["bot"].store
    person = {"handle": H, "timezone": "America/New_York"}
    now = env["clock"][0]
    key = I.cache_key("never mind", person, [], None, now)
    store.x("INSERT INTO interp_cache(key,handle,raw,at) VALUES(?,?,?,?)",
            (key, H, json.dumps({"intent": "chat", "reply": "OK"}), now.isoformat()))   # a bare form, as before
    calls = []
    I.llm.chat_json = lambda *a, **k: (calls.append(1), ({"intent": "undo"}, 0.001))[1]
    it, cost = I.interpret("never mind", person, [], None, None, now, store=store)
    assert (it.intent, cost, calls) == ("chat", 0.0, [])
    it, _ = I.interpret("never mind", person, [], None, None, now, store=store,
                        last_write={"ago": "1 minute ago", "say": "added to-do \"milk\""})
    assert it.intent == "undo" and calls == [1]                             # something to undo: asked again


# ---------- to-do reminders and a failing channel ----------
def test_a_failing_send_never_blocks_other_reminders_and_an_uncertain_one_is_not_repeated(env):
    from mvp.channels.base import SendUncertain
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    for text in ("call the bank", "feed the cat", "water plants"):
        say(env, f"add {text} at 2pm", {"intent": "todo_add", "todo_text": text, "due": "2026-11-12T14:00"})
    real = ch.send
    fail = {"call the bank": RuntimeError, "feed the cat": SendUncertain}

    def flaky(handle, text):
        for k, e in fail.items():
            if k in text:
                raise e("down")
        return real(handle, text)
    ch.send = flaky
    clock[0] = datetime(2026, 11, 12, 19, 1, tzinfo=UTC)
    assert bot.tick() == 1 and last(ch) == "Reminder from your list: water plants"
    runs = [r["status"] for r in bot.store.q("SELECT status FROM runs WHERE kind='todo' ORDER BY id")]
    assert sorted(runs) == ["send_failed", "sent", "unknown"]
    ch.send = real
    clock[0] += timedelta(minutes=1)
    assert bot.tick() == 1 and last(ch) == "Reminder from your list: call the bank"   # tried again; the cat is not
    assert bot.tick() == 0


def test_adding_ingredients_read_as_adding_the_pick_is_read_as_ingredients(env):
    """Found live: "add its ingredients to my grocery list" came back as act_on_last todo.add, so the recipe's title
    went on the grocery list instead of its ingredient lines."""
    from mvp.tests.test_slice2 import _interp
    form = {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {"list": "grocery"}}], "pick_number": 1}
    it, _ = _interp(env, [form], "add its ingredients to my grocery list")
    assert (it.intent, it.what, it.pick_number, it.todo_list) == ("todo_add", "ingredients", 1, "grocery")
    it, _ = _interp(env, [form], "add the first one to my grocery list")
    assert it.intent == "act_on_last"                                        # no ingredients named: the pick itself


def test_a_question_about_the_answer_never_writes_to_the_list(env):
    """Found live: "what are the ingredients of the first one?" came back once as act_on_last todo.add."""
    from mvp.tests.test_slice2 import _interp
    wrong = {"intent": "act_on_last", "actions": ["todo.add"], "pick_number": 1}
    right = {"intent": "follow_up", "question": "what are the ingredients of the first recipe?"}
    it, calls = _interp(env, [wrong, right], "what are the ingredients of the first one?")
    assert len(calls) == 2 and "does not ask to add anything" in calls[1]["user"] and it.intent == "follow_up"
    it, _ = _interp(env, [wrong, wrong], "what are the ingredients of the first one?")
    assert (it.intent, it.question, it.actions) == ("follow_up", "what are the ingredients of the first one?", [])
    it, calls = _interp(env, [wrong], "put the first one on my list")
    assert len(calls) == 1 and it.intent == "act_on_last"
