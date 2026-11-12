"""Offline tests for slice 2 (DESIGN.md sections 1, 2, 4, 5 and 11): the interpreter's form for every intent, its
code-side completion and cache, the evaluation runner's matcher, and each conversation flow with the fake model.
Synthetic data only; the bot fixtures come from test_mvp.py."""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)

H = "+15550001"
UTC = timezone.utc
EVERY_DAY = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def say(e, text, answer):
    """The person sends `text`; the fake interpreter returns `answer` (a dict, or a function of the prompt)."""
    e["state"]["answers"]["mvp_interpret"] = answer if callable(answer) else (lambda u: answer)
    e["bot"].on_message(H, text)
    return last(e["ch"])


def note_spec(when, text):
    return {"when": when, "content": {"source": "note", "text": text}}


def ask_pasta():
    """An answer with one pick (itm_a, whose ingredient lines are checked) as the last answer."""
    return {"intent": "ask", "spec": pasta_spec({"type": "now"}, avoid=["cream"])}


def lemon_pick():
    return compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "Fits.", "verdict": "clear",
                          "lines": ["200g spaghetti", "2 lemons"]})


# ---------- the form ----------
def test_every_new_intent_validates_and_bad_forms_are_refused():
    from mvp.schema import Interpretation as I
    ok = [
        {"intent": "todo_add", "todo_text": "buy basil", "list": "Shopping list", "due": "2026-11-13T09:00"},
        {"intent": "todo_add", "pick_number": 2},
        {"intent": "todo_done", "todo_number": 2},
        {"intent": "todo_remove", "todo_text": "basil"},
        {"intent": "todo_due", "todo_number": [1], "in_minutes": 30},
        {"intent": "todo_list"},
        {"intent": "act_on_last", "actions": ["email.send", "calendar.add"], "pick_number": 1,
         "params": {"date": "2026-11-13", "time": "19:00"}, "when": {"type": "once", "in_minutes": 60}},
        {"intent": "profile_show"}, {"intent": "profile_update", "profile_note": "beginner at Blender"},
        {"intent": "set_quiet_hours", "end": "10"}, {"intent": "snooze", "until": "2026-11-16"},
        {"intent": "snooze", "clear": True}, {"intent": "set_email", "email": "Me@Example.com"},
        {"intent": "clarify", "spec": {"when": {"type": "schedule", "days": ["SUN"]}}, "question": "When does it end?"},
        {"intent": "undo"}, {"intent": "library_status"},
        {"intent": "library_stats", "stats": {"words": ["recipe"], "kinds": ["save"], "by": "month"}},
        {"intent": "feedback", "feedback": "harder"}, {"intent": "feedback", "feedback": "hide", "pick_number": 1},
        {"intent": "more", "criteria": ["shorter"], "outside": "some"},
        {"intent": "run_rule", "rule_number": 1, "skip_next": True},
    ]
    forms = [I.model_validate(f) for f in ok]
    assert forms[0].todo_list == "shopping" and forms[1].what == "pick" and forms[2].todo_number == [2]
    assert forms[4].in_minutes == 30
    cal = next(a for a in forms[6].actions if a.action == "calendar.add")
    assert cal.params == {"date": "2026-11-13", "time": "19:00"}            # top-level params go to the calendar entry
    assert forms[9].end == "10:00" and forms[12].email == "me@example.com"
    assert forms[13].draft["when"]["days"] == ["SUN"] and forms[13].spec is None
    bad = [
        {"intent": "todo_add"}, {"intent": "todo_done"}, {"intent": "todo_due", "todo_number": [1]},
        {"intent": "act_on_last"}, {"intent": "act_on_last", "actions": ["fax.send"]},
        {"intent": "act_on_last", "actions": ["email.send"], "when": {"type": "schedule", "days": ["MON"]}},
        {"intent": "set_quiet_hours"}, {"intent": "snooze"}, {"intent": "set_email", "email": "not an address"},
        {"intent": "clarify", "spec": {"when": {"type": "once"}}}, {"intent": "feedback", "feedback": "meh"},
    ]
    for f in bad:
        with pytest.raises(Exception):
            I.model_validate(f)


def test_forms_written_flat_or_with_fields_inside_the_spec_are_read():
    from mvp.schema import Interpretation as I
    it = I.model_validate({"intent": "ask", "content": {"source": "recent", "since_days": 7}})
    assert it.spec.when.type == "now" and it.spec.content.source == "recent"   # an ask is answered now
    it = I.model_validate({"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["MON"]}, "content": {"goal": "a workout", "searches": ["workout"]},
        "also": {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["SAT"]},
                                                "content": {"goal": "a workout", "searches": ["workout"]}},
                 "also": {"intent": "chat"}}}})
    assert it.also.intent == "new_rule" and it.also.also is None               # one more, never a chain
    clar = I.model_validate({"intent": "clarify", "question": "When do exams end?", "spec": {
        "when": {"type": "schedule", "times": ["19:00"]}, "content": {"source": "note", "text": "study"}}})
    assert clar.draft["when"]["days"] == EVERY_DAY                            # the kept timing is in canonical form


def test_a_resolved_relative_time_keeps_what_was_asked_but_stores_the_moment():
    from mvp.interpret import finish
    from mvp.schema import RuleSpec
    spec = RuleSpec.model_validate(note_spec({"type": "once", "in_minutes": 120}, "take the laundry out"))
    finish(spec, datetime(2026, 11, 12, 19, 7, tzinfo=UTC), "America/New_York")
    assert (spec.when.in_minutes, spec.when.date, spec.when.times) == (120, "2026-11-12", ["16:07"])
    stored = spec.stored()
    assert "in_minutes" not in stored["when"] and RuleSpec.model_validate(stored).when.times == ["16:07"]


# ---------- the interpreter: settings, grounding, completion, cache ----------
def _interp(e, answers, text, rules=(), now=None, **kw):
    """Calls interpret() with a fake model that returns `answers` in turn; returns (it, calls)."""
    from mvp import interpret as I
    calls = []

    def fake(system, user, purpose, prompt_version, person=None, max_tokens=0, **extra):
        calls.append({"user": user, **extra})
        return dict(answers[min(len(calls), len(answers)) - 1]), 0.002
    I.llm.chat_json = fake
    person = {"handle": H, "timezone": "America/New_York"}
    it, cost = I.interpret(text, person, list(rules), None, None, now or e["clock"][0], **kw)
    return it, calls


def test_interpreter_runs_at_temperature_0_with_a_seed_and_shows_the_context(env):
    it, calls = _interp(env, [{"intent": "todo_list"}], "whats on my list",
                        todos=[{"id": 1, "text": "buy basil", "list": "todo"}], about=["vegetarian"],
                        last_write={"ago": "2 minutes ago", "say": "added to-do \"buy basil\""})
    assert calls[0]["temperature"] == 0 and calls[0]["seed"] == 7
    u = calls[0]["user"]
    assert "1. buy basil (list: todo)" in u and "vegetarian" in u and "can be undone" in u
    assert "Calendar: Fri 2026-11-13" in u and u.endswith("Their message:\nwhats on my list")


def test_reminder_words_must_come_from_the_message(env):
    bad = {"intent": "new_rule", "spec": note_spec({"type": "once", "in_minutes": 60}, "hydrate and meditate")}
    good = {"intent": "new_rule", "spec": note_spec({"type": "once", "in_minutes": 60}, "call your mum")}
    it, calls = _interp(env, [bad, good], "remind me in an hour to call my mum")
    assert len(calls) == 2 and "must use only words from their message" in calls[1]["user"]
    assert it.spec.content.text == "call your mum"
    it, calls = _interp(env, [bad, bad], "remind me in an hour to call my mum")
    assert it.spec.content.text == "remind me in an hour to call my mum"      # never words they did not write
    typo = {"intent": "todo_add", "todo_text": "buy tomatoes"}
    it, _ = _interp(env, [typo], "add buy tomatos to my list")
    assert it.todo_text == "buy tomatoes"                                    # a spelling fix is their word


def test_code_completes_what_the_message_states(env):
    saved = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "travel reels", "kinds": ["save"], "platforms": ["instagram"]}}}   # no searches, one kind
    it, _ = _interp(env, [saved], "travel reels i saved")
    assert it.spec.content.kinds == ["save", "collection", "share_self", "playlist"]
    assert it.spec.content.searches == ["travel reels"]                        # the goal is searched
    it, _ = _interp(env, [{"intent": "todo_add", "todo_text": "oat milk"}], "put oat milk on my shopping list")
    assert it.todo_list == "shopping"
    it, _ = _interp(env, [{"intent": "todo_add", "todo_text": "oat milk"}], "add oat milk to my to-do list")
    assert it.todo_list is None
    it, _ = _interp(env, [{"intent": "todo_add", "pick_number": 2}], "add the ingredients for #2 to my list")
    assert it.what == "ingredients"


def test_a_change_that_only_adds_a_start_or_dates_off_is_a_pause_or_a_skip(env):
    rule = {"id": 7, "status": "active", "spec": {"when": {"type": "schedule", "days": ["FRI"], "times": ["19:00"]},
                                                   "content": {"goal": "a pasta recipe", "searches": ["pasta"]}}}
    later = {"intent": "change_rule", "rule_number": 1, "spec": {
        "when": {"type": "schedule", "days": ["FRI"], "times": ["19:00"], "start": "2026-12-01"},
        "content": {"goal": "a pasta recipe", "searches": ["pasta"]}}}
    it, _ = _interp(env, [later], "hold off on pasta until december", rules=[rule])
    assert (it.intent, it.until, it.rule_number, it.spec) == ("pause", "2026-12-01", 1, None)
    off = json.loads(json.dumps(later))
    off["spec"]["when"].pop("start")
    off["spec"]["when"]["except_dates"] = ["2026-11-20"]
    it, _ = _interp(env, [off], "no pasta on the 20th", rules=[rule])
    assert (it.intent, it.date, it.until) == ("skip", "2026-11-20", None)
    moved = json.loads(json.dumps(later))
    moved["spec"]["when"].update(start=None, times=["20:00"])
    it, _ = _interp(env, [moved], "pasta at 8 from december", rules=[rule])
    assert it.intent == "change_rule"                                        # a real change stays a change


def test_the_same_request_reuses_its_interpretation_for_6_hours(env, monkeypatch):
    from mvp import config, interpret as I
    monkeypatch.setattr(config, "INTERPRET_CACHE_HOURS", 6)
    store = env["bot"].store
    person = {"handle": H, "timezone": "America/New_York"}
    calls = []

    def fake(system, user, purpose, prompt_version, person=None, max_tokens=0, **extra):
        calls.append(1)
        return ({"intent": "ask", "spec": pasta_spec({"type": "now"})}), 0.002
    I.llm.chat_json = fake
    now = env["clock"][0]
    a, c1 = I.interpret("Pasta  ideas?", person, [], None, None, now, store=store)
    b, c2 = I.interpret("pasta ideas?", person, [], None, None, now + timedelta(hours=5), store=store)
    assert len(calls) == 1 and c2 == 0.0 and a.spec.stored() == b.spec.stored()
    rule = {"id": 1, "status": "active", "spec": pasta_spec()}
    I.interpret("pasta ideas?", person, [rule], None, None, now + timedelta(hours=5), store=store)
    assert len(calls) == 2                                                    # other rules: asked again
    I.interpret("pasta ideas?", dict(person, handle="+1999"), [], None, None, now, store=store)
    assert len(calls) == 3                                                    # another person
    I.interpret("pasta ideas?", person, [], None, None, now + timedelta(hours=6, minutes=1), store=store)
    assert len(calls) == 4                                                    # older than 6 hours


# ---------- the evaluation runner's matcher ----------
def test_runner_matcher_follows_the_readme_rules():
    from mvp.eval_rules import match, score_case
    from mvp.schema import Interpretation as I
    weekly = I.model_validate({"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["FRI", "MON"], "time": "19:00"},
        "content": {"goal": "pasta", "searches": ["pasta"], "criteria": ["ends with a dish you can eat"],
                    "kinds": ["save", "collection"]},
        "do": ["email.send"]}, "profile_note": "Vegetarian now"})
    assert match({"intent": "new_rule", "when": {"type": "schedule", "days": ["MON", "FRI"], "time": "19:00"}}, weekly) == []
    assert match({"intent": "new_rule", "content": {"source": "library", "criteria": ["dish|finish"]}}, weekly) == []
    assert match({"intent": "new_rule", "do": ["message.send", "email.send"]}, weekly) == []   # message.send implied
    assert match({"intent": "new_rule", "do": ["email.send"]}, weekly) == []
    assert match({"intent": "new_rule", "fields": {"profile_note": "vegetar"}}, weekly) == []
    assert match({"intent": "new_rule", "content": {"kinds": ["save"]}}, weekly)               # sets: same members
    assert match({"intent": "new_rule", "content": {"criteria": []}}, weekly)                  # empty means empty
    assert match({"intent": "ask"}, weekly)[0].startswith("intent")
    assert match({"intent": "new_rule", "when": {"until": "2026-12-24"}}, weekly)              # listed keys must be there
    act = I.model_validate({"intent": "act_on_last", "actions": [
        {"action": "calendar.add", "params": {"date": "2026-11-14", "time": "18:00"}}], "pick_number": 1})
    assert match({"intent": "act_on_last", "fields": {"actions": ["calendar.add"], "params": {"time": "18:00"}}},
                 act) == []                                                  # params of the calendar entry
    more = I.model_validate({"intent": "more", "criteria": ["shorter videos"]})
    assert match({"intent": "more", "fields": {"criteria": ["short|quick"]}}, more) == []
    both = I.model_validate({"intent": "todo_add", "todo_text": "oat milk", "list": "shopping list",
                             "also": {"intent": "ask", "spec": pasta_spec({"type": "now"})}})
    assert match({"intent": "todo_add", "fields": {"list": "shop", "todo_number": [],
                                                   "also": {"intent": "ask", "when": {"type": "now"}}}}, both) == []
    assert match({"intent": "todo_add", "fields": {"also": {"intent": "chat"}}}, both)
    clar = I.model_validate({"intent": "clarify", "question": "When?", "spec": {
        "when": {"type": "schedule", "days": ["SUN"], "time": "09:00"}, "content": {"source": "library"}}})
    assert match({"intent": "clarify", "when": {"type": "schedule", "days": ["SUN"]},
                  "content": {"source": "library"}}, clar) == []             # the half-built spec, as kept
    case = {"expect": {"intent": "ask"}, "accept_also": [{"intent": "new_rule", "when": {"type": "schedule"}}]}
    assert score_case(case, weekly) == (True, [])


def test_runner_end_to_end_with_a_fake_model(tmp_path, monkeypatch):
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    from mvp import eval_rules, llm
    seen = []

    def fake(system, user, purpose, prompt_version, person=None, max_tokens=0, **extra):
        seen.append(user)
        if "Waiting spec" in user:
            return {"intent": "new_rule", "edits_pending": True, "spec": {
                "when": {"type": "schedule", "days": ["FRI"], "times": ["20:00"]},
                "content": {"goal": "a pasta recipe", "searches": ["pasta"]}}}, 0.001
        return {"intent": "todo_done", "todo_number": [2]}, 0.001
    monkeypatch.setattr(llm, "chat_json", fake)
    cases = tmp_path / "cases.jsonl"
    cases.write_text("\n".join(json.dumps(c) for c in [
        {"id": "x-1", "text": "make it 8pm instead", "ctx": "preview_open",
         "expect": {"intent": "new_rule", "when": {"days": ["FRI"], "times": ["20:00"]}, "fields": {"edits_pending": True}}},
        {"id": "x-2", "text": "done 2", "ctx": "has_todos", "expect": {"intent": "todo_done", "fields": {"todo_number": [2]}}},
        {"id": "x-3", "text": "done 3", "ctx": "has_todos", "expect": {"intent": "todo_done", "fields": {"todo_number": [3]}}},
    ]) + "\n")
    out = tmp_path / "counts.json"
    s = eval_rules.main([str(cases), "--out", str(out), "--workers", "2"])
    assert (s["cases"], s["passed"], s["failed"]) == (3, 2, ["x-3"])
    assert json.loads(out.read_text())["by_intent"]["todo_done"] == {"passed": 1, "cases": 2}
    assert any("3. book dentist appointment" in u for u in seen)            # the has_todos context was built
    for name in ("none", "late_evening", "one_rule", "two_rules", "after_ask", "after_rule_send", "preview_open",
                 "has_todos", "after_write", "clarify_open"):
        eval_rules.context(name)


# ---------- conversation flows ----------
def test_a_preview_says_the_schedule_and_the_first_send(env):
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta A", "why": "Good.", "verdict": "clear"})
    msg = say(env, "pasta every friday at 7pm", {"intent": "new_rule", "spec": pasta_spec()})
    assert "Every Friday at 7pm I'll send" in msg and "The first one would come tomorrow at 7pm." in msg
    window = pasta_spec({"type": "schedule", "days": EVERY_DAY, "window": ["18:00", "20:00"]})
    msg = say(env, "pasta every evening between 6 and 8", {"intent": "new_rule", "spec": window})
    assert "The first one would come today, between 6pm and 8pm." in msg   # the day, never the drawn minute
    rand = pasta_spec({"type": "random", "count": 3, "per": "week"})
    msg = say(env, "pasta at random", {"intent": "new_rule", "spec": rand})
    assert "first one would come" not in msg                                # random moments are never shown


def test_plain_reminders_need_no_preview_once_or_repeating(env):
    bot, clock = env["bot"], env["clock"]
    msg = say(env, "remind me in 2 hrs to take the laundry out",
              {"intent": "new_rule", "spec": note_spec({"type": "once", "in_minutes": 120}, "take the laundry out")})
    assert msg == 'OK. Today at 3pm I\'ll remind you: "take the laundry out". Reply "stop 1" to cancel.'
    assert bot.store.pending(H) is None and "mvp_compose" not in env["calls"]
    msg = say(env, "every 10 days remind me to water the cactus",
              {"intent": "new_rule", "spec": note_spec({"type": "schedule", "every_days": 10}, "water the cactus")})
    assert msg.startswith("Got it: every 10 days at 9am, I'll remind you: \"water the cactus\". First one tomorrow")
    assert 'Reply "stop 2" to end it.' in msg and len(bot.store.rules(H)) == 2
    clock[0] = datetime(2026, 11, 12, 20, 8, tzinfo=UTC)
    assert bot.tick() == 1 and last(env["ch"]) == "Reminder: take the laundry out"
    clock[0] = datetime(2026, 11, 13, 14, 1, tzinfo=UTC)
    assert bot.tick() == 1 and last(env["ch"]).startswith("Reminder: water the cactus\nReply \"stop 1\"")
    assert "mvp_compose" not in env["calls"]                                # no search, no model call


def test_todos_add_list_done_remove_and_named_lists(env):
    bot = env["bot"]
    assert say(env, "add buy basil to my list", {"intent": "todo_add", "todo_text": "buy basil"}) == \
        'Added "buy basil" to your list.'
    assert say(env, "put oat milk on my shopping list", {"intent": "todo_add", "todo_text": "oat milk"}) == \
        'Added "oat milk" to your shopping list.'
    say(env, "add call the landlord to my list", {"intent": "todo_add", "todo_text": "call the landlord"})
    msg = say(env, "whats on my list", {"intent": "todo_list"})
    assert msg.splitlines()[:4] == ["Your list:", "1. buy basil", "2. call the landlord", "3. oat milk [shopping]"]
    assert say(env, "what's on my shopping list", {"intent": "todo_list", "list": "shopping"}).splitlines()[:2] == \
        ["Your shopping list:", "3. oat milk"]                             # the same numbers as the full list
    assert say(env, "done 1", {"intent": "todo_done", "todo_number": [1]}) == "Done: buy basil. 2 left on your list."
    assert say(env, "take the oat milk off", {"intent": "todo_remove", "todo_text": "oat milk"}) == "Removed: oat milk."
    assert say(env, "done 7", {"intent": "todo_done", "todo_number": [7]}).startswith("Your list has 1 thing")
    assert say(env, "remove the cat", {"intent": "todo_remove", "todo_text": "cat"}).startswith("I can't find that")
    assert [t["text"] for t in bot.store.todos(H)] == ["call the landlord"]


def test_a_due_todo_reminds_once_through_the_scheduler(env):
    bot, clock = env["bot"], env["clock"]
    msg = say(env, "add call the dentist to my list for tomorrow at 9",
              {"intent": "todo_add", "todo_text": "call the dentist", "due": "2026-11-13T09:00"})
    assert msg == 'Added "call the dentist" to your list. I\'ll remind you tomorrow at 9am.'
    clock[0] = datetime(2026, 11, 13, 13, 59, tzinfo=UTC)
    assert bot.tick() == 0
    clock[0] = datetime(2026, 11, 13, 14, 1, tzinfo=UTC)
    assert bot.tick() == 1 and last(env["ch"]) == "Reminder from your list: call the dentist"
    clock[0] = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
    assert bot.tick() == 0                                                   # once only
    say(env, "remind me about the dentist in 30 min", {"intent": "todo_due", "todo_text": "dentist", "in_minutes": 30})
    bot.store.set_snooze(H, datetime(2026, 11, 14, tzinfo=UTC))
    clock[0] = datetime(2026, 11, 13, 15, 31, tzinfo=UTC)
    assert bot.tick() == 0 and bot.store.one("SELECT status FROM runs WHERE kind='todo' ORDER BY id DESC")["status"] == \
        "snoozed"                                                            # the same guards as a timed rule


def test_a_rule_with_source_todos_sends_the_open_list(env):
    bot, clock = env["bot"], env["clock"]
    say(env, "add buy basil to my list", {"intent": "todo_add", "todo_text": "buy basil"})
    spec = {"when": {"type": "schedule", "days": EVERY_DAY, "times": ["08:00"]}, "content": {"source": "todos"}}
    msg = say(env, "every morning send me my list", {"intent": "new_rule", "spec": spec})
    assert msg.startswith("Got it: every day at 8am, I'll send you your open to-dos. First one tomorrow at 8am.")
    clock[0] = datetime(2026, 11, 13, 13, 1, tzinfo=UTC)
    assert bot.tick() == 1 and last(env["ch"]).startswith("Your list:\n1. buy basil")


def test_picks_and_their_checked_ingredients_go_on_a_list(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta, no cream", ask_pasta())
    msg = say(env, "add the ingredients for 1 to my grocery list",
              {"intent": "todo_add", "pick_number": 1, "what": "ingredients", "list": "grocery"})
    assert msg.startswith("Added 2 things to your grocery list: 200g spaghetti; 2 lemons")
    msg = say(env, "add the first one to my list", {"intent": "act_on_last", "actions": ["todo.add"], "pick_number": 1})
    assert msg == 'Added "Lemon garlic pasta" to your list.'                 # a title made of the item's own words
    assert bot.store.todos(H)[0]["url"] == "https://example.com/itm_a"
    assert say(env, "add the 4th one", {"intent": "todo_add", "pick_number": 4}).startswith("My last message had 1 pick")
    assert say(env, "email me that", {"intent": "act_on_last", "actions": ["email.send"]}) == \
        "I can't email answers or add them to your calendar yet. You can copy the link from my last message for now."


def test_undo_reverses_the_last_write_within_10_minutes(env):
    bot, clock = env["bot"], env["clock"]
    say(env, "add pick up dry cleaning to my list", {"intent": "todo_add", "todo_text": "pick up dry cleaning"})
    assert say(env, "wait no, undo that", {"intent": "undo"}).startswith("Undone: I took that off your list")
    assert bot.store.todos(H) == []
    assert say(env, "undo", {"intent": "undo"}) == "There's nothing from the last 10 minutes to undo."
    say(env, "every 10 days remind me to water the cactus",
        {"intent": "new_rule", "spec": note_spec({"type": "schedule", "every_days": 10}, "water the cactus")})
    assert say(env, "undo", {"intent": "undo"}) == \
        'Undone: I stopped the rule I just started, "water the cactus".'   # the reply says a rule ended
    assert bot.store.rules(H) == []
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "P", "why": "Good.", "verdict": "clear"})
    say(env, "pasta every friday at 7pm", {"intent": "new_rule", "spec": pasta_spec()})
    say(env, "yes", {"intent": "confirm"})
    clock[0] += timedelta(minutes=11)
    say(env, "make it 8pm", {"intent": "change_rule", "rule_number": 1,
                             "spec": pasta_spec({"type": "schedule", "days": ["FRI"], "time": "20:00"})})
    assert say(env, "undo", {"intent": "undo"}) == 'Undone: "a pasta recipe" is back as it was.'
    assert bot.store.rules(H)[0]["spec"]["when"]["times"] == ["19:00"]
    clock[0] += timedelta(minutes=11)
    assert say(env, "undo", {"intent": "undo"}) == "There's nothing from the last 10 minutes to undo."


def test_clarify_keeps_the_half_built_form_and_the_next_message_completes_it(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Tip", "why": "Good.", "verdict": "clear"})
    draft = {"when": {"type": "schedule", "days": ["SUN"], "time": "09:00"},
             "content": {"goal": "a study tip", "searches": ["study tip"]}}
    msg = say(env, "every sunday a study tip until the end of the semester",
              {"intent": "clarify", "spec": draft, "question": "When does your semester end?"})
    assert msg == "When does your semester end?" and bot.store.pending(H)["kind"] == "clarify"
    assert bot.store.rules(H) == []

    def complete(user):
        assert "WAITING" in user and "When does your semester end?" in user and '"days": ["SUN"]' in user
        return {"intent": "new_rule", "spec": dict(draft, when=dict(draft["when"], until="2026-12-18"))}
    msg = say(env, "dec 18", complete)
    assert "Reply YES to start" in msg and "until 18 December" in msg
    say(env, "yes", {"intent": "confirm"})
    r = bot.store.rules(H)[0]
    assert r["spec"]["when"]["until"] == "2026-12-18" and r["text"].endswith(" / dec 18")
    say(env, "every sunday a study tip until the end of the semester",
        {"intent": "clarify", "spec": draft, "question": "When does your semester end?"})
    assert say(env, "no", {"intent": "decline"}) == "OK, I won't set that up. Tell me what you'd like instead."
    assert bot.store.pending(H) is None


def test_also_runs_a_second_request_in_order(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    n0 = len(env["ch"].outbox)
    say(env, "put oat milk on my shopping list and find me a pasta recipe",
        {"intent": "todo_add", "todo_text": "oat milk", "also": ask_pasta()})
    replies = [t for _, _, t in env["ch"].outbox[n0:]]
    assert replies[0] == 'Added "oat milk" to your shopping list.' and "Lemon garlic pasta" in replies[1]


def test_two_rules_in_one_message_start_with_one_yes(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Workout", "why": "Good.", "verdict": "clear"})
    weekdays = pasta_spec({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI"], "time": "08:00"})
    weekends = pasta_spec({"type": "schedule", "days": ["SAT", "SUN"], "time": "10:00"})
    n0 = len(env["ch"].outbox)
    say(env, "every weekday at 8 a workout, and weekends at 10",
        {"intent": "new_rule", "spec": weekdays, "also": {"intent": "new_rule", "spec": weekends}})
    replies = [t for _, _, t in env["ch"].outbox[n0:]]
    assert len(replies) == 2 and "Reply YES to start, or" in replies[0] and "Reply YES to start both" in replies[1]
    assert len(bot.store.pending(H)["payload"]["more"]) == 1
    say(env, "yes", {"intent": "confirm"})
    assert [r["spec"]["when"]["days"] for r in bot.store.rules(H)] == [["MON", "TUE", "WED", "THU", "FRI"], ["SAT", "SUN"]]


def test_run_now_and_skip_the_next_says_so(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "P", "why": "Good.", "verdict": "clear"})
    say(env, "pasta every friday at 7pm", {"intent": "new_rule", "spec": pasta_spec()})
    say(env, "yes", {"intent": "confirm"})
    msg = say(env, "send me fridays pasta now", {"intent": "run_rule", "rule_number": 1, "skip_next": True})
    assert "The next scheduled one is skipped, so the one after comes on Friday 20 November at 7pm." in msg
    assert bot.store.rules(H)[0]["skip_count"] == 1


def test_quiet_hours_and_snooze_by_text(env):
    bot = env["bot"]
    msg = say(env, "pls no messages before 10am", {"intent": "set_quiet_hours", "end": "10:00"})
    assert msg == "OK, no timed messages from 10pm to 10am. Times you named yourself still go out."
    assert bot.store.quiet(H) == [{"start": "22:00", "end": "10:00"}]
    msg = say(env, "not during class 9 to 3 on weekdays",
              {"intent": "set_quiet_hours", "start": "09:00", "end": "15:00", "days": ["MON", "TUE", "WED", "THU", "FRI"]})
    assert msg == ("OK, no timed messages from 10pm to 10am, and from 9am to 3pm on weekdays. "
                   "Times you named yourself still go out.")
    say(env, "undo", {"intent": "undo"})
    assert bot.store.quiet(H) == [{"start": "22:00", "end": "10:00"}]
    assert say(env, "back to normal", {"intent": "set_quiet_hours", "clear": True}).startswith("OK, quiet hours are back")
    msg = say(env, "dont text me this weekend", {"intent": "snooze", "until": "2026-11-16"})
    assert msg.startswith("OK, no timed messages until Monday 16 November at 12am.")
    assert bot.store.person(H)["snooze_until"] == "2026-11-16T05:00:00+00:00"
    assert say(env, "ok you can text me again", {"intent": "snooze", "clear": True}) == "OK, timed messages are back on."


def test_library_stats_are_counted_by_code_without_friends(env):
    msg = say(env, "how many pasta things have i kept", {"intent": "library_stats", "stats": {"words": ["pasta"]}})
    lines = msg.splitlines()
    assert lines[0] == "You've kept 4 things: 3 on Instagram, 1 on YouTube."   # the friend's post is not counted
    assert '3 of them mention "pasta".' in lines and lines[-1] == "Posts from friends are not counted."


def test_profile_notes_are_kept_and_later_features_say_so_honestly(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "im vegetarian now, any dinner ideas?", dict(ask_pasta(), profile_note="vegetarian"))
    assert bot.store.profile_notes(H) == ["vegetarian"]
    seen = []
    say(env, "what can i cook", lambda u: (seen.append(u), {"intent": "chat", "reply": "What kind of dish?"})[1])
    assert "About them" in seen[0] and "- vegetarian" in seen[0]
    assert say(env, "I'm a total beginner at Blender", {"intent": "profile_update"}).startswith("Noted.")
    assert bot.store.profile_notes(H)[-1] == "I'm a total beginner at Blender"
    assert say(env, "what do you know about me", {"intent": "profile_show"}) == \
        "Showing what I know about you isn't ready yet."
    assert say(env, "my email is a@b.co", {"intent": "set_email", "email": "a@b.co"}).startswith("Email isn't switched on")
    assert say(env, "did my export come", {"intent": "library_status"}).startswith("I can't check your library")
    only = ask_pasta()
    only["spec"]["content"]["outside"] = "only"
    assert say(env, "only new pasta stuff", only).startswith("I can only look in your own saves")
    some = ask_pasta()
    some["spec"]["content"]["outside"] = "some"
    assert say(env, "new pasta stuff", some).endswith("so these are all from your library.")


def test_feedback_kinds_more_with_a_change_and_the_language(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta, no cream", dict(ask_pasta(), lang="es"))
    assert bot.store.one("SELECT lang FROM runs WHERE kind='ask'")["lang"] == "es"
    assert say(env, "too easy", {"intent": "feedback", "feedback": "harder"}).startswith("Noted. Ask for \"a harder one\"")
    assert say(env, "made it!", {"intent": "feedback", "feedback": "done", "pick_number": 1}).startswith("Nice!")
    say(env, "never show me that", {"intent": "feedback", "feedback": "hide", "pick_number": 1})
    assert "itm_a" in bot.store.disliked(H)
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    say(env, "another but without garlic", {"intent": "more", "avoid": ["garlic"], "criteria": ["shorter"]})
    assert seen and "Lemon garlic" not in seen[0]                            # the added avoid word is enforced


def test_a_store_made_before_slice_2_gains_its_tables_and_columns(tmp_path):
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.store import Store
    old = tmp_path / "old.sqlite"
    db = sqlite3.connect(old)
    db.executescript("CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT, rule_id INTEGER, kind TEXT, "
                     "at TEXT, n_candidates INTEGER, n_picks INTEGER, n_dropped INTEGER, fits TEXT, cost_usd REAL, "
                     "status TEXT, error TEXT, prompt_version TEXT, seconds REAL);")
    db.commit()
    db.close()
    store = Store(str(old))
    assert "lang" in {r["name"] for r in store.q("PRAGMA table_info(runs)")}
    tables = {r["name"] for r in store.q("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"todos", "profile_notes", "interp_cache"} <= tables
    store.add_todo("+1", "buy basil")
    store.delete_person_data("+1")
    assert store.todos("+1") == []
