"""Offline tests for the round 8 merge: where the slices meet (DESIGN.md sections 13 to 15). The recap counts what the
rules slice records (quiet empty days, overdue nudges, reminders counted back from a thing's date); the theme check's
labels keep topics out of the recap's suggestion and go into the export; the agent's what_i_am_into is the chat's
trends answer; "delete my data" removes what all three slices store; and each code-read phrase of one slice is read
in its own context and not swallowed by another's. Synthetic data, the fake model, the fake search pool and the fake
clock only (New York)."""
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round7 import ask  # noqa: E402
from mvp.tests.test_round8_rules import (EMPTY, NOON, no_model, noon, opps, pasta_rule, rules, statuses,  # noqa: E402
                                         tick_at, tue_todo, u)
from mvp.tests.test_round8_understanding import QUESTION, TRENDS, lib8  # noqa: E402,F401  (lib8 is a fixture)

UTC = timezone.utc
CHAT = {"intent": "chat", "reply": "Sure."}
NUDGE = '"call the bank" was due yesterday. Reply "done 1", "tomorrow" or "drop it".'


def model_calls(e):
    return sum(1 for c in e["calls"] if c == "mvp_interpret")


def nudged(env):
    """A to-do due Tuesday 17 Nov 6pm, reminded at its time and nudged on Wednesday 6:01pm; the clock stays there."""
    t = tue_todo(env)
    tick_at(env, u(2026, 11, 17, 23, 1))
    assert tick_at(env, u(2026, 11, 18, 23, 1)) == 1 and last(env["ch"]) == NUDGE
    return t


def recap(e):
    return say(e, "recap", no_model)


def line_of(msg, head):
    got = [x for x in msg.split("\n") if x.startswith(head)]
    return got[0] if got else None


# ---------- the recap counts what the rules slice records ----------
def test_merge_recap_counts_the_quiet_empty_days_the_scheduler_records(env):
    bot = env["bot"]
    pasta_rule(env)                                                            # quiet on empty days by default
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    for d in (13, 14, 15):
        env["clock"][0] = noon(d)
        bot.tick()
    assert statuses(bot) == ["empty_quiet"] * 3
    env["clock"][0] = noon(15) + timedelta(hours=2)
    msg = recap(env)
    assert line_of(msg, "• Rules:") == '• Rules: 1 "a pasta recipe" stayed quiet 3 times with nothing new.'
    # near-variant: a day with picks is a send, beside the quiet ones
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    env["clock"][0] = noon(16)
    assert bot.tick() == 1
    env["clock"][0] = noon(16) + timedelta(hours=2)
    assert line_of(recap(env), "• Rules:") == ('• Rules: 1 "a pasta recipe" sent 1, stayed quiet 3 times with '
                                               'nothing new.')


def test_merge_a_rule_that_says_so_on_empty_days_is_counted_as_sent_not_quiet(env):
    bot = env["bot"]
    pasta_rule(env, text="every day at noon send me a pasta recipe, tell me even if there's nothing")
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    for d in (13, 14):
        env["clock"][0] = noon(d)
        bot.tick()
    assert statuses(bot) == ["none_sent", "none_sent"]
    env["clock"][0] = noon(14) + timedelta(hours=2)
    assert line_of(recap(env), "• Rules:") == '• Rules: 1 "a pasta recipe" sent 2.'


def test_merge_recap_counts_a_todo_the_scheduler_nudged_as_past_due_and_tomorrow_moves_it_to_coming_up(env):
    bot = env["bot"]
    t = nudged(env)
    assert bot.store.todo(t["id"])["overdue_at"]
    # "recap" right after the nudge is not an answer to it: the recap, and the to-do stays as it was
    msg = recap(env)
    assert line_of(msg, "• To-dos:") == "• To-dos: 1 is open, 1 of them past its due date."
    assert bot.store.todo(t["id"])["due_at"] == "2026-11-17T23:00:00+00:00" and not bot.store.get_state(f"overdue:{H}")
    assert say(env, "tomorrow", CHAT) == "Sure."                              # the question ended with the recap
    # nudged again (a new to-do), then "tomorrow": not past due, and it is coming up
    bot.store.update_todo(t["id"], done_at="2026-11-18T23:30:00+00:00")
    t2 = bot.store.add_todo(H, "pay rent", due_at=u(2026, 11, 19, 23, 0), at=u(2026, 11, 18, 23, 30))
    assert tick_at(env, u(2026, 11, 19, 23, 1)) == 1                         # its reminder
    assert tick_at(env, u(2026, 11, 20, 23, 1)) == 1
    assert last(env["ch"]) == '"pay rent" was due yesterday. Reply "done 1", "tomorrow" or "drop it".'
    assert line_of(recap(env), "• To-dos:") == "• To-dos: you ticked off 1; 1 is open, 1 of them past its due date."
    tick_at(env, u(2026, 11, 21, 23, 1))
    assert tick_at(env, u(2026, 11, 22, 23, 1)) == 0                          # never nudged twice
    bot.store.set_state(f"overdue:{H}", {"todo_id": t2, "at": "2026-11-22T23:01:00+00:00"})
    assert say(env, "tomorrow", no_model) == 'OK. "pay rent" is now due tomorrow at 6pm.'
    msg = recap(env)
    assert line_of(msg, "• To-dos:") == "• To-dos: you ticked off 1; 1 is open."
    assert line_of(msg, "• Coming up:") == '• Coming up: "pay rent" due Monday 23 November.'
    assert bot.store.todo(t2)["overdue_at"] is None


def test_merge_recap_lists_a_reminder_counted_back_from_a_things_date_under_coming_up(env, tmp_path):
    opps(env, tmp_path)
    say(env, "remind me 3 days before the NASA one closes", no_model)
    COMING = ("• Coming up: a reminder about NASA L'SPACE Academy on Friday 27 November (its deadline is "
              "30 November).")
    env["clock"][0] = u(2026, 11, 14, 16, 0)                                    # 13 days ahead: not in the next 7
    assert line_of(recap(env), "• Coming up:") is None
    env["clock"][0] = u(2026, 11, 21, 15, 0)
    assert line_of(recap(env), "• Coming up:") == COMING
    say(env, "stop 1", no_model)                                               # near-variant: a stopped one is gone
    assert line_of(recap(env), "• Coming up:") is None


def test_merge_recap_lists_a_reminder_whose_date_the_person_gave(env, tmp_path):
    opps(env, tmp_path)
    say(env, "remind me before the city lab one closes", no_model)
    say(env, "dec 5", no_model)
    env["clock"][0] = u(2026, 11, 28, 15, 0)
    assert line_of(recap(env), "• Coming up:") == ("• Coming up: a reminder about City Lab fellowship on Wednesday "
                                                   "2 December (its deadline is 5 December).")


# ---------- the theme check's labels and the recap's suggestion, through the chat ----------
def climbing_asks(e):
    e["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Climb", "why": "x", "verdict": "clear"})
    base = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
    for d, h in ((0, 0), (0, 2), (1, 1)):
        e["clock"][0] = base + timedelta(days=d, hours=h)
        say(e, "climbing routes please", ask("climbing routes", ["climbing"]))
    e["clock"][0] = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)


SUGGEST_HEAD = "• You asked about climbing 3 times since Thursday 12 November."


def test_merge_labels_given_in_the_chat_keep_a_topic_out_of_the_recaps_suggestion(lib8):
    bot = lib8["bot"]
    climbing_asks(lib8)
    assert say(lib8, "what have I been into lately", no_model).endswith(QUESTION)
    assert say(lib8, "4 someday", no_model).startswith("Thanks, noted. Climbing: parked for someday")
    assert SUGGEST_HEAD not in recap(lib8)
    say(lib8, "climbing is not me now", no_model)
    assert SUGGEST_HEAD not in recap(lib8)
    say(lib8, "climbing is pursue now", no_model)                              # near-variant: a goal may be suggested
    assert SUGGEST_HEAD in recap(lib8)
    assert bot.store.rules(H) == []


# ---------- the agent's what_i_am_into is the chat's trends answer ----------
def agent_into(e):
    from mvp import config
    from mvp.mcp_server import Agent
    agent = Agent(H, db=config.DB, pool=e["bot"].pool, clock=lambda: e["clock"][0])
    out = agent.call("what_i_am_into")
    first, _, rest = out.partition("\n")
    return first, json.loads(rest)


def test_merge_what_i_am_into_returns_the_trends_answer_the_chat_gives(lib8):
    from mvp import profile as P
    first, out = agent_into(lib8)
    assert "data" in first.lower()
    assert out["into"] == TRENDS.split("\n")
    chat = say(lib8, "what have I been into lately", no_model).split("\n\n")[0]
    assert out["into"] == chat.split("\n")
    # near-variant: a topic labelled "not me" is gone from both
    P.set_relations(lib8["bot"].store, H, [("Climbing", "not_me")])
    _, out = agent_into(lib8)
    assert not any("Climbing" in x for x in out["into"])
    assert out["into"] == say(lib8, "what's rising", no_model).split("\n\n")[0].split("\n")
    assert lib8["calls"] == []


def test_merge_what_i_am_into_with_no_topics_says_what_the_chat_says(env):
    from mvp import texts as T
    _, out = agent_into(env)
    assert out["into"] == [T.TRENDS_NO_TOPICS]


# ---------- export my data includes the labels ----------
def exported_profile(e):
    from mvp.actions.base import outbox_dir
    d = sorted(glob.glob(os.path.join(outbox_dir(H), "export-*")))[-1]
    with open(os.path.join(d, "profile.json"), encoding="utf-8") as f:
        return json.load(f), open(os.path.join(d, "README.txt"), encoding="utf-8").read()


def test_merge_export_my_data_includes_the_theme_labels_with_the_profile(lib8):
    say(lib8, "export my data", no_model)
    prof, _ = exported_profile(lib8)
    assert prof["not_me"] == [] and all(not i.get("relation") for i in prof["interests"])
    say(lib8, "what have I been into lately", no_model)
    say(lib8, "1 practise, 2 for fun, 3 someday, 4 not me", no_model)
    say(lib8, "export my data", no_model)
    prof, readme = exported_profile(lib8)
    rel = {i["topic"]: i.get("relation") for i in prof["interests"]}
    assert rel == {"Blender 3D": "practise", "Guitar": "enjoy", "Sourdough": "someday", "Mental health": None}
    assert [x["topic"] for x in prof["not_me"]] == ["Climbing"] and prof["not_me"][0]["relation_at"]
    assert all(i.get("relation_at") for i in prof["interests"] if i.get("relation"))
    assert '"not_me"' in readme and "someday" in readme
    assert lib8["calls"] == []


# ---------- delete my data removes what all three slices store ----------
def test_merge_delete_my_data_removes_labels_overdue_state_deadlines_exports_and_the_agents_log(env, tmp_path):
    from mvp import config
    from mvp import profile as P
    from mvp.actions.base import outbox_dir
    from mvp.mcp_server import Agent
    bot = env["bot"]
    opps(env, tmp_path)
    say(env, "remind me 3 days before the NASA one closes", no_model)
    rid = rules(bot)[-1]["id"]
    P.set_interests(bot.store, H, [{"topic": "Climbing", "words": ["climbing"], "source": "guess"},
                                   {"topic": "Guitar", "words": ["guitar"], "source": "guess"}])
    P.set_relations(bot.store, H, [("Climbing", "someday"), ("Guitar", "not_me")])
    bot.store.set_state(f"themecheck:{H}", {"shown": ["Climbing"], "at": "2026-11-14T15:00:00+00:00"})
    bot.store.set_state(f"suggested:{H}", {"climb": "2026-11-14T15:00:00+00:00"})
    t = nudged(env)
    assert bot.store.get_state(f"overdue:{H}") and bot.store.todo(t["id"])["overdue_at"]
    say(env, "thanks", CHAT)
    say(env, "export my data", no_model)
    say(env, "export my lists", no_model)
    Agent(H, db=config.DB, pool=bot.pool, clock=lambda: env["clock"][0]).call("my_rules")
    assert bot.store.q("SELECT id FROM action_log WHERE handle=? AND action LIKE 'mcp.%'", (H,))
    bot.store.set_state(f"overdue:{H}", {"todo_id": t["id"], "at": "2026-11-18T23:01:00+00:00"})
    exports = glob.glob(os.path.join(outbox_dir(H), "export-*")) + glob.glob(os.path.join(outbox_dir(H), "lists-*"))
    assert len(exports) == 2 and bot.store.get_state(f"deadline:{rid}")
    say(env, "delete my data", {"intent": "delete_data"})
    say(env, "YES", CHAT)
    assert bot.store.person(H) is None
    assert not any(os.path.isdir(d) for d in exports)
    for table in ("todos", "action_log", "rules", "runs", "answers", "feedback"):
        assert bot.store.q(f"SELECT * FROM {table} WHERE handle=?", (H,)) == [], table
    keys = [r["key"] for r in bot.store.q("SELECT key FROM state")]
    assert not [k for k in keys if k.endswith(":" + H) or k == f"deadline:{rid}"], keys
    assert bot.store.profile_data(H) == {}


# ---------- the routing: each phrase in its own context, and not swallowed by another slice's ----------
def test_merge_done_after_a_nudge_ticks_that_todo_off_and_undo_brings_it_back(env):
    bot = env["bot"]
    t = nudged(env)
    n = model_calls(env)
    assert say(env, "done", no_model) == "Done: call the bank. Your list is clear."
    assert model_calls(env) == n and bot.store.todo(t["id"])["done_at"]
    env["clock"][0] += timedelta(minutes=2)
    say(env, "undo", no_model)
    assert bot.store.todo(t["id"])["done_at"] is None
    # near-variants: "did it" after a nudge; "done" with no nudge in view goes to the model as before
    t2 = tue_todo(env, text="post the letter")
    tick_at(env, u(2026, 11, 17, 23, 1))
    tick_at(env, u(2026, 11, 18, 23, 5))
    assert '"post the letter" was due yesterday' in last(env["ch"])
    say(env, "did it", no_model)
    assert bot.store.todo(t2["id"])["done_at"]
    n = model_calls(env)
    say(env, "done", CHAT)
    assert model_calls(env) == n + 1


def test_merge_done_after_a_nudge_and_a_later_until_done_reminder_finishes_the_reminder(env):
    bot = env["bot"]
    t = nudged(env)
    rid = bot.store.add_rule(H, "remind me to stretch every day at 7pm until I've done it", {
        "when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "time": "19:00",
                 "stop_when": "done"}, "content": {"source": "note", "text": "stretch"}}, "active",
        "2026-11-19T00:00:00+00:00", created_at="2026-11-18T20:00:00+00:00")
    assert tick_at(env, u(2026, 11, 19, 0, 1)) == 1 and "stretch" in last(env["ch"])
    msg = say(env, "done", no_model)
    assert msg == f"Rule {bot.store.rule_number(H, rid)} is finished."
    assert bot.store.rule(rid)["status"] == "done" and bot.store.todo(t["id"])["done_at"] is None


def test_merge_tomorrow_and_drop_it_only_after_a_nudge(env):
    bot = env["bot"]
    t = nudged(env)
    assert say(env, "drop it", no_model) == 'OK. I took "call the bank" off your list.'
    assert bot.store.todo(t["id"])["removed_at"]
    # out of their context: after an answer and with the theme check open, the model reads them; nothing changes
    t2 = bot.store.add_todo(H, "buy stamps", due_at=u(2026, 11, 20, 14, 0))
    bot.store.set_state(f"themecheck:{H}", {"shown": ["Climbing"], "at": "2026-11-18T23:00:00+00:00"})
    n = model_calls(env)
    assert say(env, "drop it", CHAT) == "Sure."
    assert say(env, "tomorrow", CHAT) == "Sure."
    assert model_calls(env) == n + 2 and not bot.store.get_state(f"themecheck:{H}")
    assert bot.store.todo(t2)["removed_at"] is None and bot.store.todo(t2)["due_at"] == "2026-11-20T14:00:00+00:00"


def test_merge_recap_ends_the_theme_check_and_the_every_export_offer(lib8):
    bot = lib8["bot"]
    say(lib8, "what have I been into lately", no_model)
    assert bot.store.get_state(f"themecheck:{H}") and bot.store.get_state(f"trendsoffer:{H}")
    assert say(lib8, "recap", no_model).startswith("Nothing to report")
    assert not bot.store.get_state(f"themecheck:{H}") and not bot.store.get_state(f"trendsoffer:{H}")
    n = model_calls(lib8)
    say(lib8, "1 someday", CHAT)                                               # no longer read as labels
    say(lib8, "every export", CHAT)                                            # no longer the offer
    assert model_calls(lib8) == n + 2 and bot.store.rules(H) == []
    assert all(not i.get("relation") for i in bot.store.profile_data(H)["interests"])


def test_merge_every_export_only_right_after_the_trends_answer(lib8):
    bot = lib8["bot"]
    n = model_calls(lib8)
    say(lib8, "every export", CHAT)
    assert model_calls(lib8) == n + 1 and bot.store.rules(H) == []
    say(lib8, "what have I been into lately", no_model)
    msg = say(lib8, "every export", no_model)
    assert '"stop 1"' in msg and bot.store.rules(H)[0]["spec"]["content"]["source"] == "trends"
    assert not bot.store.get_state(f"themecheck:{H}")


def test_merge_share_it_with_the_theme_check_open_shares_and_ends_the_question(lib8):
    bot = lib8["bot"]
    lib8["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Climb", "why": "x", "verdict": "clear"})
    say(lib8, "climbing routes please", ask("climbing routes", ["climbing"]))
    say(lib8, "what have I been into lately", no_model)
    n0 = len(lib8["ch"].outbox)
    say(lib8, "share it", no_model)
    out = [m[2] for m in lib8["ch"].outbox[n0:]]
    assert len(out) == 2 and out[1].startswith("Press and hold that message to forward it.")
    assert not bot.store.get_state(f"themecheck:{H}")
    # out of context: no answer in view says so plainly, with no model call
    bot.store.x("DELETE FROM last_answer WHERE handle=?", (H,))
    msg = say(lib8, "share it", no_model)
    assert "forward" not in msg.lower() or "nothing" in msg.lower()


def test_merge_export_my_lists_and_what_did_my_agent_ask_end_an_open_nudge_and_leave_the_todo(env):
    bot = env["bot"]
    t = nudged(env)
    msg = say(env, "export my lists", no_model)
    assert msg.startswith("I saved your lists (1 to-do)")
    assert not bot.store.get_state(f"overdue:{H}") and bot.store.todo(t["id"])["due_at"] == "2026-11-17T23:00:00+00:00"
    assert say(env, "tomorrow", CHAT) == "Sure."                              # the nudge's question ended
    tick_at(env, u(2026, 11, 20, 23, 1))                                      # a new to-do, nudged
    t2 = tue_todo(env, text="post the letter")
    tick_at(env, u(2026, 11, 17, 23, 1))
    tick_at(env, u(2026, 11, 18, 23, 2))
    assert say(env, "what did my agent ask", no_model) == ("Your agent hasn't asked me for anything in the last 7 "
                                                           "days.")
    assert say(env, "drop it", CHAT) == "Sure." and bot.store.todo(t2["id"])["removed_at"] is None
    # out of context: empty lists say so
    for x in bot.store.todos(H):
        bot.store.update_todo(x["id"], removed_at="2026-11-18T23:00:00+00:00")
    bot.store.x("DELETE FROM todos WHERE handle=?", (H,))
    assert say(env, "export my lists", no_model).startswith("Your lists are empty")


def test_merge_what_did_i_park_with_a_date_question_open_ends_it_and_lists_the_parked(env, tmp_path):
    from mvp import profile as P
    bot = env["bot"]
    opps(env, tmp_path)
    P.set_interests(bot.store, H, [{"topic": "Climbing", "words": ["climbing"], "source": "guess"}])
    P.set_relations(bot.store, H, [("Climbing", "someday")])
    say(env, "remind me before the city lab one closes", no_model)
    assert bot.store.get_state(f"deadline_ask:{H}")
    msg = say(env, "what did I park?", no_model)
    assert "Climbing" in msg and not bot.store.get_state(f"deadline_ask:{H}")
    n = model_calls(env)
    say(env, "dec 5", CHAT)                                                    # no longer the date's answer
    assert model_calls(env) == n + 1 and rules(bot) == []
    # near-variant: "what did my agent ask" in the same place
    say(env, "remind me before the city lab one closes", no_model)
    assert say(env, "what did my agent ask?", no_model).startswith("Your agent hasn't asked me")
    assert not bot.store.get_state(f"deadline_ask:{H}")


@pytest.mark.parametrize("phrase", ["recap", "share it", "export my lists", "every export", "what did I park",
                                    "what did my agent ask", "tomorrow", "drop it", "done"])
def test_merge_no_code_read_phrase_is_read_as_a_date_or_as_labels(phrase):
    from datetime import date
    from mvp import profile as P
    from mvp.followup import date_answer
    assert date_answer(phrase, date(2026, 11, 14)) is None
    assert P.parse_labels(phrase, ["Blender 3D", "Guitar", "Sourdough", "Climbing"]) is None


def test_merge_theme_question_ends_on_a_request_read_as_chat(lib8):
    """The theme check (understanding) and interpret.chat_guard (slice A2): a request the model reads as small talk,
    sent while the question is open, ends the question and is searched."""
    bot = lib8["bot"]
    say(lib8, "what have I been into lately", no_model)
    lib8["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    msg = say(lib8, "find me a pasta recipe", {"intent": "chat", "reply": "Hello."})
    assert msg != "Hello." and "mvp_compose" in lib8["calls"] and "went wrong" not in msg
    assert bot.store.q("SELECT status FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")[0]["status"] != "error"
    assert bot.store.get_state(f"themecheck:{H}") is None
    n = model_calls(lib8)
    say(lib8, "1 someday", CHAT)                                               # no longer read as labels
    assert model_calls(lib8) == n + 1
    assert all(not i.get("relation") for i in bot.store.profile_data(H)["interests"])
