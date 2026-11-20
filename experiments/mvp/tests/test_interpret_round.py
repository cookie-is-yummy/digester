"""Offline tests for the interpreter's improvement round (kinds of misreading an evaluator reported on the held-out
rule set, checked here with cases of our own). Each test feeds a form the model could return (the wrong reading) and
checks what code makes of it; each fails without its fix. A fake model and a fake clock only."""
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)

TZ = "America/New_York"
NOW = datetime(2026, 11, 12, 19, 7, tzinfo=timezone.utc)      # Thursday 12 Nov 2026, 14:07 in New York


def _lib(when, goal, searches):
    return {"when": when, "content": {"source": "library", "goal": goal, "searches": searches, "count": 1},
            "do": [{"action": "message.send"}]}


PASTA = {"id": 1, "status": "active", "spec": _lib({"type": "schedule", "days": ["FRI"], "times": ["19:00"]},
                                                     "a pasta recipe for Friday dinner",
                                                     ["pasta recipe", "easy pasta dinner"])}
WORKOUT = {"id": 2, "status": "active", "spec": _lib({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI"],
                                                      "times": ["08:00"]}, "a short home workout",
                                                     ["short home workout", "quick workout"])}
RULES = [PASTA, WORKOUT]
TODOS = [{"id": 1, "text": "buy basil", "list": "todo"}, {"id": 2, "text": "call the landlord", "list": "todo"},
         {"id": 3, "text": "book dentist appointment", "list": "todo"}]
LAST = {"goal": "quick chicken and rice dinners", "request": "quick chicken and rice dinner ideas",
        "items": ["e1", "e2", "e3"], "run_id": 5}


def S(form, text, rules=(), todos=()):
    from mvp.interpret import settle
    return settle(form, text, list(rules), NOW, TZ, list(todos))


def ask(goal, **content):
    return {"intent": "ask", "spec": {"when": {"type": "now"},
                                      "content": {"goal": goal, "searches": [goal], **content}}}


def rule(when, goal="a recipe", **content):
    return {"intent": "new_rule", "spec": {"when": when, "content": {"goal": goal, "searches": [goal], **content}}}


# ---------- kind 1: a rule command always has a target ----------
def test_pause_resume_and_stop_get_all_rules_or_the_rule_named(env):
    it = S({"intent": "pause", "until": "2026-11-15"}, "pause everything till sunday", RULES)
    assert (it.all_rules, it.rule_number, it.until) == (True, None, "2026-11-15")
    assert S({"intent": "stop"}, "stop all of them", RULES).all_rules
    assert S({"intent": "resume"}, "ok you can start sending stuff again", RULES).all_rules
    assert S({"intent": "resume"}, "text me again", []).all_rules          # nothing named: every rule
    it = S({"intent": "pause"}, "pause the workouts for now", RULES)        # the topic names rule 2
    assert (it.rule_number, it.all_rules) == (2, False)
    it = S({"intent": "stop", "rule_number": 2, "all_rules": True}, "stop the workout one", RULES)
    assert (it.rule_number, it.all_rules) == (2, False)                      # both given: the words decide
    it = S({"intent": "pause", "rule_number": 1, "all_rules": True}, "pause everything", RULES)
    assert (it.rule_number, it.all_rules) == (None, True)
    it = S({"intent": "pause"}, "pause for a bit", RULES)                   # nothing to go on: the bot asks which
    assert (it.rule_number, it.all_rules) == (None, False)


def test_a_skip_of_one_topic_gets_its_rule_and_the_count_said(env):
    it = S({"intent": "skip"}, "no pasta for the next two fridays", RULES)
    assert (it.intent, it.rule_number, it.count) == ("skip", 1, 2)
    it = S({"intent": "skip", "count": 1}, "skip workouts the next three mornings", RULES)
    assert (it.rule_number, it.count) == (2, 3)
    it = S({"intent": "skip", "rule_number": 2, "date": "2026-11-20"}, "no workout on the 20th pls", RULES)
    assert (it.rule_number, it.count, it.date) == (2, None, "2026-11-20")     # a date stays a date
    it = S({"intent": "skip"}, "skip the next 3 days of workouts", RULES)    # days are not sends: no count from them
    assert (it.rule_number, it.count) == (2, None)


# ---------- kind 2: month_weeks as a nested list ----------
def test_month_weeks_written_nested_or_as_words_validate(env):
    from mvp.schema import When
    w = When.model_validate({"type": "schedule", "month_weeks": [[1, 3]], "days": ["MON"]})
    assert (w.month_weeks, w.days) == ([1, 3], ["MON"])
    w = When.model_validate({"type": "schedule", "month_weeks": [[1, "MON"], [3, "MON"]]})
    assert (w.month_weeks, w.days) == ([1, 3], ["MON"])
    w = When.model_validate({"type": "schedule", "month_weeks": ["last"], "days": "FRI"})
    assert (w.month_weeks, w.days) == ([-1], ["FRI"])
    w = When.model_validate({"type": "schedule", "month_weeks": [{"week": 2, "day": "SAT"}, {"week": 4, "day": "SAT"}]})
    assert (w.month_weeks, w.days) == ([2, 4], ["SAT"])
    assert When.model_validate({"type": "schedule", "month_days": [[1, 15]]}).month_days == [1, 15]


def test_a_nested_month_weeks_form_is_a_rule_not_unsupported(env):
    from mvp import interpret as I
    form = rule({"type": "schedule", "month_weeks": [[1], [3]], "days": [["MON"]]}, "a sketching exercise")
    I.llm.chat_json = lambda *a, **k: (form, 0.001)
    it, _ = I.interpret("on the first and third monday of every month send me a sketching exercise",
                        {"handle": "t", "timezone": TZ}, [], None, None, NOW)
    assert it.intent == "new_rule" and (it.spec.when.month_weeks, it.spec.when.days) == ([1, 3], ["MON"])


# ---------- kind 3: two requests in one message (prompt rule; code keeps the second) ----------
def test_the_prompt_in_use_keeps_every_request_and_never_hides_one_in_a_profile_note(env):
    from mvp import config, interpret as I
    assert config.PROMPT_INTERPRET == "interpret_v5"
    assert "Keep every request in the message" in I.PROMPT and "never only a profile_note" in I.PROMPT
    it = S({"intent": "set_timezone", "timezone": "America/Chicago",
            "also": {"intent": "change_rule", "rule_number": 1,
                     "spec": _lib({"type": "schedule", "days": ["FRI"], "times": ["20:00"]}, "a pasta recipe for "
                                  "Friday dinner", ["pasta recipe"])}},
           "im in chicago this week, and move the pasta one to 8pm", [PASTA])
    assert it.intent == "set_timezone" and it.also.intent == "change_rule" and it.also.spec.when.times == ["20:00"]


# ---------- kind 4: section 11 timing defaults ----------
def test_twice_a_day_with_no_clock_time_is_8am_and_8pm(env):
    daily = list("MON TUE WED THU FRI SAT SUN".split())
    it = S(rule({"type": "schedule", "days": daily, "times": ["08:00", "19:00"]}, "a vocab word video"),
           "twice a day, morning and night, send me a vocab word video")
    assert it.spec.when.times == ["08:00", "20:00"]
    it = S(rule({"type": "schedule", "days": daily, "times": ["09:00", "21:00"]}, "a drawing warmup"),
           "2x daily drawing warmups pls")
    assert it.spec.when.times == ["08:00", "20:00"]
    it = S(rule({"type": "schedule", "days": daily, "times": ["08:00", "12:00", "18:00"]}, "a desk stretch"),
           "three times a day send me a quick desk stretch")
    assert it.spec.when.times == ["08:00", "13:00", "19:00"]
    # what they named stays theirs
    for text, times in [("send me a recipe twice a day, at 8am and 8pm", ["08:00", "20:00"]),
                        ("twice a day, at 7 and 5, a stretch", ["07:00", "17:00"]),
                        ("twice a day, breakfast and lunch, a recipe", ["08:00", "12:00"]),
                        ("3x a day pls, morning noon and evening, quick ab workouts", ["08:00", "12:00", "19:00"])]:
        assert S(rule({"type": "schedule", "days": daily, "times": times}), text).spec.when.times == times


# ---------- kind 5: a one-time surprise in a coming period ----------
def test_a_surprise_in_a_coming_period_is_one_random_moment(env):
    it = S(rule({"type": "once", "date": "2026-11-18", "time": "19:00"}, "a dessert recipe"),
           "surprise me with a dessert recipe sometime next week")
    w = it.spec.when
    assert (it.intent, w.type, w.count, w.per, w.max_sends, w.start) == ("new_rule", "random", 1, "week", 1,
                                                                        "2026-11-16")
    it = S(rule({"type": "schedule", "days": ["SAT"], "times": ["10:00"]}, "a blender project"),
           "at some point this weekend surprise me with a fun blender project")
    w = it.spec.when
    assert (w.type, w.count, w.max_sends, w.days) == ("random", 1, 1, ["SAT", "SUN"])
    it = S(rule({"type": "schedule", "days": ["MON"], "times": ["09:00"]}), "surprise me with a recipe every week")
    assert (it.spec.when.type, it.spec.when.max_sends) == ("random", None)   # every week: no one-send limit
    # a window or a named time is theirs
    daily = list("MON TUE WED THU FRI SAT SUN".split())
    it = S(rule({"type": "schedule", "days": daily, "window": ["18:00", "20:00"]}),
           "every evening some time between 6 and 8 send a dinner idea")
    assert it.spec.when.type == "schedule"
    it = S(rule({"type": "once", "date": "2026-11-13", "time": "19:00"}), "surprise me tomorrow at 7pm with a recipe")
    assert it.spec.when.type == "once"


# ---------- kind 6: "this week" as an end ----------
def test_this_week_as_an_end_is_this_sunday(env):
    daily = list("MON TUE WED THU FRI SAT SUN".split())
    it = S(rule({"type": "schedule", "days": daily, "times": ["08:00"], "until": "2026-11-19"}, "a workout"),
           "send me a workout every morning this week")
    assert it.spec.when.until == "2026-11-15"
    it = S(rule({"type": "schedule", "days": daily, "times": ["19:00"], "until": "2026-11-18"}, "a dinner idea"),
           "every evening until the end of the week send me a dinner idea")
    assert it.spec.when.until == "2026-11-15"
    it = S(rule({"type": "schedule", "days": daily, "times": ["08:00"], "until": "2026-12-12"}, "a stretch"),
           "a stretch every morning for the rest of the month")
    assert it.spec.when.until == "2026-11-30"
    it = S(rule({"type": "schedule", "days": daily, "times": ["08:00"], "until": "2026-11-19"}, "a workout"),
           "a workout every morning for the next 7 days")
    assert it.spec.when.until == "2026-11-19"                                # a rolling week they asked for stays


# ---------- kind 7: clarify keeps the days they stated ----------
def test_clarify_keeps_the_weekly_days_said(env):
    form = {"intent": "clarify", "question": "When is your recital?",
            "spec": {"when": {"type": "on_request"}, "content": {"source": "note", "text": "practice scales"}}}
    it = S(form, "remind me to practice scales every tuesday and thursday until my recital")
    assert it.intent == "clarify" and it.draft["when"]["type"] == "schedule"
    assert it.draft["when"]["days"] == ["TUE", "THU"] and it.draft["content"]["source"] == "note"
    form["spec"]["when"] = {}
    it = S(form, "send me a spanish lesson on weekdays at 7pm till my trip")
    assert (it.draft["when"]["days"], it.draft["when"]["times"]) == (["MON", "TUE", "WED", "THU", "FRI"], ["19:00"])
    form["spec"]["when"] = {"type": "schedule", "days": ["SUN"], "times": ["09:00"]}
    assert S(form, "every sunday a study tip till the semester ends").draft["when"]["days"] == ["SUN"]


# ---------- kind 8: running a rule now ----------
def test_a_rules_send_asked_for_now_is_run_rule(env):
    it = S(ask("a pasta recipe for Friday dinner"), "can i have this weeks pasta recipe now?", [PASTA])
    assert (it.intent, it.rule_number, it.skip_next) == ("run_rule", 1, True)
    it = S(ask("a short home workout"), "send me tomorrow's workout now", RULES)
    assert (it.intent, it.rule_number, it.skip_next) == ("run_rule", 2, True)
    it = S(ask("a short home workout"), "the workout one now please", RULES)
    assert (it.intent, it.rule_number, it.skip_next) == ("run_rule", 2, False)
    assert S(ask("pasta ideas"), "pasta ideas now?", [PASTA]).intent == "ask"          # no rule named: a search
    assert S(ask("a cocktail"), "this weeks cocktail now", RULES).intent == "ask"      # no rule on that topic


# ---------- kind 9: a due time for an open to-do ----------
def test_a_time_for_an_open_todo_is_its_due_time(env):
    form = rule({"type": "once", "date": "2026-11-13", "time": "10:00"})
    form["spec"]["content"] = {"source": "note", "text": "call the landlord"}
    it = S(form, "remind me to call the landlord tomorrow at 10am", todos=TODOS)
    assert (it.intent, it.todo_number, it.due) == ("todo_due", [2], "2026-11-13T10:00")
    it = S({"intent": "todo_add", "todo_text": "dentist", "due": "2026-11-13"}, "the dentist one needs doing by friday",
           todos=TODOS)
    assert (it.intent, it.todo_number, it.due) == ("todo_due", [3], "2026-11-13")
    it = S({"intent": "todo_due", "todo_text": "call the landlord", "due": "2026-11-13T10:00"},
           "remind me to call the landlord tomorrow at 10am", todos=TODOS)
    assert it.todo_number == [2]                                             # its number, from its words
    form["spec"]["content"] = {"source": "note", "text": "call mum"}
    assert S(form, "remind me to call mum tomorrow at 10am", todos=TODOS).intent == "new_rule"   # not on the list


# ---------- kind 10: find things, then list them ----------
def test_finding_things_for_the_list_is_an_ask_with_todo_add(env):
    it = S({"intent": "todo_add", "todo_text": "a couple of easy lunch recipes"},
           "put a couple of easy lunch recipes on my to-do list")
    assert (it.intent, it.spec.content.count, [a.action for a in it.spec.do]) == ("ask", 2, ["message.send", "todo.add"])
    assert it.spec.content.goal == "easy lunch recipes"
    it = S({"intent": "todo_add", "todo_text": "beginner watercolor tutorials from my saves", "list": "art"},
           "add beginner watercolor tutorials from my saves to my art list")
    assert it.intent == "ask" and it.spec.do[-1].params.get("list") == "art"
    assert it.spec.content.kinds == ["save", "collection", "share_self", "playlist"]
    # found live in this round: "do" written inside content was dropped without a word
    raw = {"intent": "ask", "content": {"goal": "easy lunch recipes", "searches": ["easy lunch"], "count": 2,
                                        "do": ["message.send", "todo.add"]}}
    assert [a.action for a in S(raw, "put a couple of easy lunch recipes on my list").spec.do] == \
        ["message.send", "todo.add"]
    for text in ("add buy basil to my list", "add watch the blender videos to my list"):
        assert S({"intent": "todo_add", "todo_text": text[4:-11]}, text).intent == "todo_add"


# ---------- kind 11: an output of a new ask is in its own do list ----------
def test_an_output_for_a_new_ask_goes_in_its_do_list(env):
    form = ask("a 20 minute yoga flow")
    form["also"] = {"intent": "act_on_last", "actions": ["calendar.add"],
                    "params": {"date": "2026-11-13", "time": "07:00"}}
    it = S(form, "find me a 20 minute yoga flow and put it on my calendar tomorrow at 7am")
    assert it.also is None and [a.action for a in it.spec.do] == ["message.send", "calendar.add"]
    assert it.spec.do[1].params["time"] == "07:00" and it.spec.do[1].params["date"] == "2026-11-13"
    form["also"]["pick_number"] = 2                                          # a pick of the answer shown before
    assert S(form, "find me a yoga flow, and put the second one from before on my calendar").also is not None


def test_a_new_find_read_as_act_on_last_is_an_ask(env):
    from mvp.interpret import new_find
    raw = {"intent": "act_on_last", "actions": ["email.send"], "pick_number": 1}
    text = "pick a blender project for me and email it to me"
    it = new_find(S(raw, text), text, LAST)
    assert (it.intent, it.spec.content.goal, it.spec.content.count) == ("ask", "blender project", 1)
    assert [a.action for a in it.spec.do] == ["message.send", "email.send"]
    for text in ("email me that", "find me another chicken one and email it to me"):   # about the last answer
        assert new_find(S(raw, text), text, LAST).intent == "act_on_last"


# ---------- kind 12: things to leave out ----------
def test_a_thing_to_leave_out_is_avoid_not_a_criterion(env):
    it = S(ask("pasta", criteria=["no mushrooms"]), "pasta recipe but no mushrooms")
    assert (it.spec.content.criteria, it.spec.content.avoid) == ([], ["mushroom"])
    it = S(ask("leg workout", criteria=["without lunges", "a full routine from start to finish"]),
           "leg workout without lunges")
    assert it.spec.content.avoid == ["lunge"] and it.spec.content.criteria == ["a full routine from start to finish"]
    for crit in ("no equipment", "no oven", "no more than 5 ingredients", "not too spicy"):   # a must-have stays
        it = S(ask("dinner", criteria=[crit]), "dinner " + crit)
        assert it.spec.content.criteria == [crit] and it.spec.content.avoid == []
    it = S({"intent": "more", "criteria": ["no nuts"]}, "another but no nuts")
    assert (it.criteria, it.avoid) == ([], ["nut"])


# ---------- kind 13: a fact said inside a request ----------
def test_a_fact_said_inside_an_ask_is_kept_as_a_profile_note(env):
    it = S(ask("microwave lunch", criteria=["microwave only"]), "i only have a microwave at work, lunch ideas?")
    assert it.profile_note == "i only have a microwave"
    assert S(ask("easy dinner"), "I don't eat pork, any easy dinner recipes?").profile_note == "I don't eat pork"
    assert S(ask("dinner"), "I’m vegan now so dinner ideas pls").profile_note == "I’m vegan now"
    it = S(dict(ask("dinner"), profile_note="vegetarian"), "im vegetarian now, any dinner ideas?")
    assert it.profile_note == "vegetarian"                                   # the model's own note stays
    for text in ("i only have 20 minutes, quick lunch?", "i have a question about pasta", "I'm in Boston, dinner?",
                 "I just got home, dinner ideas?"):
        assert S(ask("lunch"), text).profile_note is None


# ---------- found on the development files in this round ----------
def test_a_window_with_a_time_beside_it_keeps_the_window(env):
    daily = list("MON TUE WED THU FRI SAT SUN".split())
    it = S(rule({"type": "schedule", "days": daily, "times": ["19:00"], "window": ["18:00", "20:00"]}, "a dinner idea"),
           "every evening some time between 6 and 8 send a dinner idea")
    assert (it.intent, it.spec.when.window, it.spec.when.times) == ("new_rule", ["18:00", "20:00"], [])


def test_a_tips_request_gets_no_must_have_it_did_not_state(env):
    it = S(ask("Blender modeling tips", criteria=["beginner-friendly", "helps finish a small scene each week"]),
           "Blender modeling tips?")
    assert it.spec.content.criteria == []
    it = S(ask("beginner Blender tips", criteria=["suits a beginner"]), "beginner blender tips")
    assert it.spec.content.criteria == ["suits a beginner"]                  # their own word stays
    it = S(ask("photo editing tutorial", criteria=["beginner"]), "a beginner photo editing tutorial")
    assert it.spec.content.criteria == ["beginner"]                          # not a tips request: untouched


def test_this_week_as_dates_for_a_recap_is_seven_days(env):
    it = S({"intent": "ask", "content": {"source": "recent", "saved_after": "2026-11-05", "saved_before": "2026-11-13"}},
           "what did i save this week")
    c = it.spec.content
    assert (c.since_days, c.saved_after, c.saved_before) == (7, None, None)
    it = S({"intent": "ask", "content": {"source": "recent", "saved_after": "2026-10-01", "saved_before": "2026-11-01"}},
           "Can you recap what I kept in October?")
    assert (it.spec.content.since_days, it.spec.content.saved_after) == (None, "2026-10-01")
