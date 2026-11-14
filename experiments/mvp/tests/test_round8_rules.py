"""Offline tests for round 8, slice B (DESIGN.md section 13): rules beyond timing. BN1: a reminder counted back from a
thing's own date ("remind me 3 days before the NASA one closes"). BN2: a repeating rule that stays quiet on an empty day,
a reminder that runs until the person says done, and one nudge for a to-do a day past due. Synthetic data, the fake
model, the fake search pool and the fake clock only (New York; today is 14 Nov 2026 unless a test moves it)."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round7 import ask, ig, pick, use_lib  # noqa: E402

UTC = timezone.utc
DAILY = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def u(*a):
    return datetime(*a, tzinfo=UTC)


def no_model(user):
    raise AssertionError("the model was called for a message code reads")


def rules(bot):
    return bot.store.q("SELECT * FROM rules WHERE handle=? ORDER BY id", (H,))


def spec_of(row):
    return json.loads(row["spec"])


# ---------- BN1: a reminder counted back from a thing's own date ----------
OPPS = ("Opportunities for students:\nCity Lab fellowship: rolling applications, open to all\n"
        "NASA L'SPACE Academy: free program, applications close 30 November 2026\n"
        "Design Jam: a weekend event for beginners")
OPP_ITEMS = [{"name": "City Lab fellowship", "about": "rolling applications, open to all", "when": ""},
             {"name": "NASA L'SPACE Academy", "about": "free program, applications close 30 November 2026",
              "when": "30 November 2026"},
             {"name": "Design Jam", "about": "a weekend event for beginners", "when": ""}]


def opps(env, tmp_path, cap=OPPS, items=OPP_ITEMS, posted="2026-11-01", clock=u(2026, 11, 14, 15, 0)):
    """An items answer from one post (posted `posted`); the clock at `clock` (default Sat 14 Nov, 10am New York)."""
    env["clock"][0] = clock
    use_lib(env, tmp_path, [("o1", "opps", cap, posted, "2026-11-02", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda x: {"picks": [pick(x, cap.split("\n")[0][:20])]}
    env["state"]["answers"]["mvp_extract"] = lambda x: {"items": [dict(i) for i in items]} if items else {}
    return say(env, "opportunities to apply for", ask("opportunities to apply for"))


def one_post(env, tmp_path, cap, posted="2026-11-01", clock=u(2026, 11, 14, 15, 0)):
    """An answer with one pick and no things listed: "it" is that post, its date read from its own text."""
    env["clock"][0] = clock
    use_lib(env, tmp_path, [("p1", "progs", cap, posted, "2026-11-02", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda x: {"picks": [pick(x, cap[:15], title="The programme")]}
    env["state"]["answers"]["mvp_extract"] = lambda x: {}
    return say(env, "programmes to apply to", ask("programmes to apply to"))


def test_bn1_remind_me_3_days_before_the_nasa_one_closes_is_read_by_code_and_set_for_9am(env, tmp_path):
    msg = opps(env, tmp_path)
    assert "NASA L'SPACE Academy" in msg
    bot, n_calls = env["bot"], len(env["calls"])
    msg = say(env, "remind me 3 days before the NASA one closes", no_model)
    assert len(env["calls"]) == n_calls                                       # no model call
    rs = rules(bot)
    assert len(rs) == 1
    sp = spec_of(rs[0])
    assert sp["when"] == {"type": "once", "date": "2026-11-27", "times": ["09:00"]}
    assert sp["content"]["source"] == "items" and sp["content"]["item_names"] == ["NASA L'SPACE Academy"]
    assert rs[0]["next_run_at"] == "2026-11-27T14:00:00+00:00"                # 9am in New York
    assert "27 November" in msg and "30 November (in 16 days)" in msg
    assert msg == ("OK. I'll remind you about NASA L'SPACE Academy on Friday 27 November at 9am, 3 days before its "
                   "deadline, 30 November (in 16 days). Reply \"stop 1\" to cancel.")


def test_bn1_near_variants_of_the_phrasing_and_the_default_of_3_days(env, tmp_path):
    from mvp.followup import deadline_request
    assert deadline_request("remind me before it closes")["days"] == 3
    assert deadline_request("remind me the day before its deadline")["days"] == 1
    assert deadline_request("Remind me two weeks before nasa closes.")["days"] == 14
    assert deadline_request("remind me before the second one closes")["number"] == 2
    assert deadline_request("remind me before the NASA one's deadline and put it on my calendar") == {
        "days": 3, "calendar": True, "number": None, "name": "NASA"}
    for other in ("remind me to call mum before work", "remind me about the nasa one two days before its deadline",
                  "remind me tomorrow at 9", "what closes soon?"):
        assert deadline_request(other) is None
    opps(env, tmp_path)
    msg = say(env, "remind me before nasa closes", no_model)                   # no number: 3 days, by its name
    assert "on Friday 27 November at 9am, 3 days before" in msg


def test_bn1_a_week_before_it_closes_after_a_one_post_answer(env, tmp_path):
    one_post(env, tmp_path, "Space programme for students: applications close 30 November 2026, apply now")
    msg = say(env, "remind me a week before it closes", no_model)
    sp = spec_of(rules(env["bot"])[-1])
    assert sp["when"] == {"type": "once", "date": "2026-11-23", "times": ["09:00"]}
    assert "a week before its deadline, 30 November (in 16 days)" in msg


def test_bn1_it_with_several_things_asks_which_and_a_name_not_shown_is_left_to_the_model(env, tmp_path):
    opps(env, tmp_path)
    msg = say(env, "remind me before it closes", no_model)
    assert msg == "My last message listed 3 things. Which number?" and not rules(env["bot"])
    n_calls = len(env["calls"])
    say(env, "remind me before the bakery closes", {"intent": "chat", "reply": "ok"})
    assert len(env["calls"]) == n_calls + 1 and not rules(env["bot"])          # not about that answer: the model reads it
    msg = say(env, "remind me before number 2 closes", no_model)
    assert "NASA L'SPACE Academy on Friday 27 November" in msg


def test_bn1_a_passed_deadline_says_so_and_sets_nothing(env, tmp_path):
    one_post(env, tmp_path, "Space programme for students: applications close 10 November 2026")
    msg = say(env, "remind me before it closes", no_model)
    assert "10 November 2026" in msg and "has passed" in msg and not rules(env["bot"])


def test_bn1_no_date_in_its_words_asks_once_and_the_next_message_gives_it(env, tmp_path):
    opps(env, tmp_path)
    bot = env["bot"]
    msg = say(env, "remind me before the city lab one closes", no_model)
    assert msg == ("The post doesn't say when City Lab fellowship closes. Tell me the date, like \"dec 5\", and I'll "
                   "set the reminder.")
    assert not rules(bot)
    msg = say(env, "dec 5", no_model)
    sp = spec_of(rules(bot)[-1])
    assert sp["when"] == {"type": "once", "date": "2026-12-02", "times": ["09:00"]}
    assert sp["content"]["item_names"] == ["City Lab fellowship"]
    assert "Wednesday 2 December at 9am, 3 days before its deadline, 5 December (in 21 days)" in msg
    # asked once: a later date is an ordinary message
    n_calls = len(env["calls"])
    say(env, "dec 9", {"intent": "chat", "reply": "ok"})
    assert len(env["calls"]) == n_calls + 1 and len(rules(bot)) == 1


def test_bn1_any_other_message_ends_the_question_and_is_answered_normally(env, tmp_path):
    opps(env, tmp_path)
    bot = env["bot"]
    bot.store.add_todo(H, "buy stamps", "todo", at=env["clock"][0])
    say(env, "remind me before the design jam one closes", no_model)
    msg = say(env, "what's on my list", {"intent": "todo_list"})
    assert "buy stamps" in msg and not bot.store.get_state(f"deadline_ask:{H}")
    say(env, "dec 5", {"intent": "chat", "reply": "ok"})
    assert not rules(bot)
    # "dec 5 party ideas" is more than a date: never read as the answer
    say(env, "remind me before the design jam one closes", no_model)
    say(env, "dec 5 party ideas", {"intent": "chat", "reply": "ok"})
    assert not rules(bot)


def test_bn1_less_time_left_than_asked_is_set_for_the_next_9am(env, tmp_path):
    one_post(env, tmp_path, "Space programme: applications close 16 November 2026")
    msg = say(env, "remind me 3 days before it closes", no_model)
    sp = spec_of(rules(env["bot"])[-1])
    assert sp["when"] == {"type": "once", "date": "2026-11-15", "times": ["09:00"]}
    assert msg == ("OK. The programme's deadline is 16 November (in 2 days), less than 3 days away, so I'll remind you "
                   "tomorrow at 9am. Reply \"stop 1\" to cancel.")
    env["clock"][0] = u(2026, 11, 15, 14, 1)
    assert env["bot"].tick() == 1
    assert last(env["ch"]).startswith("Reminder: The programme's deadline is 16 November (tomorrow).")


def test_bn1_before_9am_the_next_9am_is_today_and_a_deadline_today_after_9am_sets_nothing(env, tmp_path):
    one_post(env, tmp_path, "Space programme: applications close 16 November 2026", clock=u(2026, 11, 14, 12, 0))
    msg = say(env, "remind me 3 days before it closes", no_model)              # 7am in New York
    assert "so I'll remind you today at 9am" in msg
    assert spec_of(rules(env["bot"])[-1])["when"]["date"] == "2026-11-14"
    env["clock"][0] = u(2026, 11, 16, 16, 0)                                    # 11am on the day itself
    msg = say(env, "remind me the day before it closes", no_model)
    assert "is today, 16 November" in msg and len(rules(env["bot"])) == 1


def test_bn1_a_date_with_no_year_takes_the_posts_year_and_rolls_into_next_year(env, tmp_path):
    items = [{"name": "Winter Lab", "about": "deadline Jan 9", "when": "Jan 9"},
             {"name": "Spring Camp", "about": "for first years", "when": ""}]
    cap = "Programs to apply to:\nWinter Lab: deadline Jan 9\nSpring Camp: for first years"
    opps(env, tmp_path, cap=cap, items=items, posted="2026-11-03")
    msg = say(env, "remind me 3 days before winter lab closes", no_model)
    assert spec_of(rules(env["bot"])[-1])["when"]["date"] == "2027-01-06"
    assert "9 January 2027 (in 56 days)" in msg


def test_bn1_the_reminder_fires_once_names_the_thing_and_its_days_left_and_is_not_unanswered(env, tmp_path):
    opps(env, tmp_path)
    bot, ch = env["bot"], env["ch"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    n0 = len(ch.outbox)
    env["clock"][0] = u(2026, 11, 27, 13, 59)
    assert bot.tick() == 0
    env["clock"][0] = u(2026, 11, 27, 14, 1)
    assert bot.tick() == 1
    out = " ".join(m[2] for m in ch.outbox[n0:])
    assert out.startswith("Reminder: NASA L'SPACE Academy's deadline is 30 November (in 3 days).")
    assert "in 3 days" in out and ig("2026-11-01", 1) in out
    assert bot._unanswered(H) == 0
    env["clock"][0] = u(2026, 11, 28, 14, 1)
    assert bot.tick() == 0 and len(ch.outbox) == n0 + len(ch.outbox[n0:])   # once
    assert rules(bot)[-1]["status"] == "done"


def test_bn1_undo_within_10_minutes_removes_the_reminder(env, tmp_path):
    opps(env, tmp_path)
    bot = env["bot"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    env["clock"][0] += timedelta(minutes=5)
    msg = say(env, "undo", no_model)
    assert "I stopped the rule I just started" in msg and rules(bot)[-1]["status"] == "stopped"


def test_bn1_and_put_it_on_my_calendar_adds_an_all_day_entry_on_the_deadline(env, tmp_path):
    opps(env, tmp_path)
    bot = env["bot"]
    msg = say(env, "remind me 3 days before the NASA one closes and put it on my calendar", no_model)
    assert "30 November (in 16 days)" in msg and "calendar.google.com/calendar/render" in msg
    assert "dates=20261130%2F20261201" in msg
    path = bot.store.q("SELECT path FROM outbox WHERE handle=? AND kind='calendar'", (H,))[-1]["path"]
    ics = open(path).read()
    assert "DTSTART;VALUE=DATE:20261130" in ics and "SUMMARY:NASA L'SPACE Academy" in ics
    assert spec_of(rules(bot)[-1])["do"] == [{"action": "message.send"}]     # the reminder itself is a message
    env["clock"][0] += timedelta(minutes=2)
    msg = say(env, "undo", no_model)
    assert "I stopped the rule I just started" in msg


def test_bn1_the_round7_form_sets_the_thing_it_names_even_when_its_words_say_its(env, tmp_path):
    """Round 7's interpreter path ("remind me about <name> two days before its deadline") read "its" as the first
    thing when the reminder was written; it now sets the thing found by its name, with the deadline head when it
    comes."""
    items = [{"name": "City Lab fellowship", "about": "apply by 20 December 2026", "when": "20 December 2026"},
             {"name": "NASA L'SPACE Academy", "about": "applications close 30 November 2026",
              "when": "30 November 2026"}]
    cap = ("Programs:\nCity Lab fellowship: apply by 20 December 2026\n"
           "NASA L'SPACE Academy: applications close 30 November 2026")
    opps(env, tmp_path, cap=cap, items=items)
    bot, ch = env["bot"], env["ch"]
    msg = say(env, "remind me about nasa two days before its deadline",
              {"intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}]})
    assert "Saturday 28 November at 9am" in msg and "NASA L'SPACE Academy" in msg
    assert spec_of(rules(bot)[-1])["content"]["item_names"] == ["NASA L'SPACE Academy"]
    env["clock"][0] = u(2026, 11, 28, 14, 1)
    n0 = len(ch.outbox)
    bot.tick()
    assert ch.outbox[n0][2].startswith("Reminder: NASA L'SPACE Academy's deadline is 30 November (in 2 days).")


def test_bn1_delete_my_data_removes_the_deadline_record(env, tmp_path):
    opps(env, tmp_path)
    bot = env["bot"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    rid = rules(bot)[-1]["id"]
    assert bot.store.get_state(f"deadline:{rid}")
    bot.store.delete_person_data(H)
    assert bot.store.get_state(f"deadline:{rid}") is None


# ---------- BN2 (a): a repeating library rule that stays quiet on a day with nothing new ----------
NOON = {"type": "schedule", "days": DAILY, "time": "12:00"}
QUIET_LINE = 'Nothing new for "a pasta recipe" since 1 March. I\'ll stay quiet until there is. "run 1" asks now.'
EMPTY = {"picks": [], "intro": ""}


def pasta_rule(env, text="every day at noon send me a pasta recipe", when=None):
    """A new daily library rule made the normal way: the preview (one pick) and YES."""
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    preview = say(env, text, {"intent": "new_rule", "spec": pasta_spec(when or NOON)})
    start = say(env, "yes", no_model)
    return preview, start, rules(env["bot"])[-1]


def statuses(bot):
    return [r["status"] for r in bot.store.q("SELECT status FROM runs WHERE kind='scheduled' ORDER BY id")]


def noon(day):
    return u(2026, 11, day, 17, 1)   # 12:01 in New York


def test_bn2_a_new_daily_rule_with_nothing_new_says_one_line_then_stays_quiet(env):
    from mvp.texts import PAUSED_QUIET
    bot, ch = env["bot"], env["ch"]
    preview, start, rule = pasta_rule(env)
    assert "On a day with nothing new I'll stay quiet." in preview and "On a day with nothing new I'll stay quiet." in start
    assert spec_of(rule)["when"]["if_empty"] == "quiet"
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    bot.store.set_state(f"last_in:{H}", "2026-11-12T18:30:00+00:00")
    n0 = len(ch.outbox)
    for d in range(13, 18):
        env["clock"][0] = noon(d)
        bot.tick()
    sent = [m[2] for m in ch.outbox[n0:]]
    assert sent == [QUIET_LINE]
    assert statuses(bot) == ["empty_quiet"] * 5
    assert bot._unanswered(H) == 0 and PAUSED_QUIET not in sent
    assert bot.store.rule(rule["id"])["status"] == "active"


def test_bn2_after_quiet_days_a_send_with_picks_goes_out_and_the_next_empty_day_says_the_line_again(env):
    bot, ch = env["bot"], env["ch"]
    pasta_rule(env)
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    for d in (13, 14):
        env["clock"][0] = noon(d)
        bot.tick()
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta two", "why": "x", "verdict": "clear"})
    env["clock"][0] = noon(15)
    assert bot.tick() == 1 and "Pasta two" in last(ch)
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    n0 = len(ch.outbox)
    for d in (16, 17):
        env["clock"][0] = noon(d)
        bot.tick()
    assert [m[2] for m in ch.outbox[n0:]] == [QUIET_LINE]
    assert statuses(bot) == ["empty_quiet", "empty_quiet", "sent", "empty_quiet", "empty_quiet"]


def test_bn2_quiet_days_never_count_toward_max_sends_or_the_daily_limit(env):
    bot = env["bot"]
    pasta_rule(env, when=dict(NOON, max_sends=2))
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    for d in (13, 14, 15):
        env["clock"][0] = noon(d)
        bot.tick()
    assert bot.store.rules(H)[-1]["status"] == "active"
    assert bot.store.scheduled_today(H, u(2026, 11, 15, 5, 0)) == 0


def test_bn2_a_quiet_rules_last_slot_never_ends_it_without_a_word(env):
    bot, ch = env["bot"], env["ch"]
    pasta_rule(env, when=dict(NOON, until="2026-11-15"))
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    n0 = len(ch.outbox)
    for d in (13, 14, 15):
        env["clock"][0] = noon(d)
        bot.tick()
    assert [m[2] for m in ch.outbox[n0:]] == [
        QUIET_LINE, 'Nothing new for "a pasta recipe" this time. That was the last one of this rule.']
    assert rules(bot)[-1]["status"] == "done"


def test_bn2_a_rule_stored_before_round_8_still_says_nothing_new_byte_for_byte(env):
    from mvp.schema import RuleSpec
    bot, ch = env["bot"], env["ch"]
    old = RuleSpec.model_validate(pasta_spec(NOON)).stored()
    assert "if_empty" not in old["when"]                                      # the stored bytes are unchanged
    rid = bot.store.add_rule(H, "pasta", old, "active", None, created_at="2026-11-12T18:00:00+00:00")
    bot.store.set_slot(rid, "2026-11-13T17:00:00+00:00", "active")
    env["state"]["answers"]["mvp_compose"] = lambda x: EMPTY
    env["clock"][0] = noon(13)
    assert bot.tick() == 1
    assert last(ch).startswith('Nothing new for "a pasta recipe" this time: ')
    assert last(ch).endswith("I'd rather skip than send something weak.")
    assert statuses(bot) == ["none_sent"]
    assert bot.store.rule(rid)["spec"] == old


def test_bn2_tell_me_even_if_theres_nothing_on_the_preview_or_in_the_request(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    preview = say(env, "every day at noon send me a pasta recipe", {"intent": "new_rule", "spec": pasta_spec(NOON)})
    assert "On a day with nothing new I'll stay quiet." in preview
    msg = say(env, "tell me even if there's nothing", no_model)
    assert msg == "OK. On a day with nothing new I'll tell you so. Reply YES to start it."
    assert bot.store.pending(H)["payload"]["spec"]["when"]["if_empty"] == "say"
    start = say(env, "yes", no_model)
    assert "stay quiet" not in start and spec_of(rules(bot)[-1])["when"]["if_empty"] == "say"
    # the phrase inside the request itself: the preview has no quiet line
    preview = say(env, "every day at 6pm send me a pasta recipe, tell me even if there's nothing new",
                  {"intent": "new_rule", "spec": pasta_spec(dict(NOON, time="18:00"))})
    assert "stay quiet" not in preview and bot.store.pending(H)["payload"]["spec"]["when"]["if_empty"] == "say"
    # "don't text me if there's nothing" right after a rule started: that rule stays quiet
    say(env, "yes", no_model)
    msg = say(env, "don't text me if there's nothing", no_model)
    assert msg == "OK. On a day with nothing new I'll stay quiet. (rule 2)"
    assert spec_of(rules(bot)[-1])["when"]["if_empty"] == "quiet"


def test_bn2_a_changed_rule_keeps_its_own_setting_and_only_timed_library_rules_take_one(env):
    from mvp.schema import RuleSpec
    bot = env["bot"]
    _, _, rule = pasta_rule(env)
    msg = say(env, "make it 1pm", {"intent": "change_rule", "rule_number": 1,
                                   "spec": pasta_spec(dict(NOON, time="13:00"))})
    assert "1pm" in msg and bot.store.rule(rule["id"])["spec"]["when"]["if_empty"] == "quiet"
    for when in ({"type": "once", "date": "2026-11-20", "time": "09:00"}, {"type": "on_request"},
                 {"type": "new_items"}):
        sp = RuleSpec.model_validate(dict(pasta_spec(when), when=dict(when, if_empty="quiet", stop_when="done")))
        assert "if_empty" not in sp.stored()["when"] and "stop_when" not in sp.stored()["when"]
    sp = RuleSpec.model_validate({"when": dict(NOON, if_empty="quiet", stop_when="done"),
                                  "content": {"source": "note", "text": "stretch"}})
    assert sp.when.if_empty is None and sp.when.stop_when == "done"
    sp = RuleSpec.model_validate(dict(pasta_spec(dict(NOON, stop_when="done"))))
    assert sp.when.stop_when is None


# ---------- BN2 (b): a reminder that repeats until the person says done ----------
NASA_FORM = {"intent": "new_rule", "spec": {
    "when": {"type": "schedule", "days": DAILY, "time": "08:00", "until": "2026-11-30"},
    "content": {"source": "note", "text": "apply to the NASA internship until I've done it"}}}
NASA_TEXT = "remind me every morning at 8 to apply to the NASA internship until I've done it"


def eight(day, minute=1):
    return u(2026, 11, day, 13, minute)   # 8:01 in New York


def test_bn2_until_ive_done_it_stores_stop_when_done_and_done_finishes_it(env):
    bot, ch = env["bot"], env["ch"]
    msg = say(env, NASA_TEXT, NASA_FORM)
    sp = spec_of(rules(bot)[-1])
    assert sp["when"] == {"type": "schedule", "days": DAILY, "every_weeks": 1, "times": ["08:00"], "stop_when": "done"}
    assert sp["content"]["text"] == "apply to the NASA internship"
    assert "until you say done" in msg and "30 November" not in msg
    env["clock"][0] = eight(13)
    assert bot.tick() == 1 and last(ch).startswith("Reminder: apply to the NASA internship")
    env["clock"][0] = eight(13, 40)
    n_calls = len(env["calls"])
    assert say(env, "done", no_model) == "Rule 1 is finished."
    assert len(env["calls"]) == n_calls and rules(bot)[-1]["status"] == "done"
    n0 = len(ch.outbox)
    env["clock"][0] = eight(14)
    assert bot.tick() == 0 and len(ch.outbox) == n0


def test_bn2_until_done_near_variants(env):
    bot = env["bot"]
    for text, until in [("remind me every morning to apply until I've applied", None),
                        ("every evening remind me to call the bank till I tick it off", None),
                        ("remind me daily to send the form until Friday, or until I've done it", "2026-11-20")]:
        form = {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": DAILY, "time": "08:00",
                                                        "until": "2026-11-20"},
                                               "content": {"source": "note", "text": "do the thing"}}}
        say(env, text, form)
        w = spec_of(rules(bot)[-1])["when"]
        assert w.get("stop_when") == "done" and w.get("until") == until, text
    say(env, "remind me every morning to stretch", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": DAILY, "time": "08:00"}, "content": {"source": "note", "text": "stretch"}}})
    assert "stop_when" not in spec_of(rules(bot)[-1])["when"]
    assert "until you say done" in say(env, "my rules", no_model)


def test_bn2_done_with_no_such_reminder_in_view_is_read_as_before(env):
    from mvp.tests.test_slice2 import ask_pasta, lemon_pick
    bot = env["bot"]
    # no reminder that runs until done: the model reads "done", as before
    n_calls = len(env["calls"])
    say(env, "done", {"intent": "chat", "reply": "Nice."})
    assert len(env["calls"]) == n_calls + 1
    say(env, NASA_TEXT, NASA_FORM)
    rid = rules(bot)[-1]["id"]
    env["clock"][0] = eight(13)
    bot.tick()
    # more than 12 hours after the send: not about it
    env["clock"][0] = u(2026, 11, 14, 2, 0)
    n_calls = len(env["calls"])
    say(env, "done", {"intent": "chat", "reply": "Nice."})
    assert len(env["calls"]) == n_calls + 1 and bot.store.rule(rid)["status"] == "active"
    # the next morning's send, then a library answer after it: "done" / "made it" is feedback on that answer
    env["clock"][0] = eight(14)
    bot.tick()
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "a pasta recipe", ask_pasta())
    n_calls = len(env["calls"])
    say(env, "done", {"intent": "feedback", "feedback": "done"})
    assert len(env["calls"]) == n_calls + 1 and bot.store.rule(rid)["status"] == "active"
    say(env, "made it", {"intent": "feedback", "feedback": "done"})
    assert "itm_a" in bot.store.disliked(H)
    # "done 2" stays the to-do command
    bot.store.add_todo(H, "milk", at=env["clock"][0])
    bot.store.add_todo(H, "eggs", at=env["clock"][0])
    env["clock"][0] = eight(15)
    bot.tick()
    msg = say(env, "done 2", no_model)
    assert "eggs" in msg and bot.store.rule(rid)["status"] == "active"


# ---------- BN2 (c): one nudge for a to-do a day past due ----------
def tue_todo(env, due="2026-11-17T18:00", text="call the bank"):
    env["clock"][0] = u(2026, 11, 16, 15, 0)                                  # Monday 10am in New York
    say(env, f"add {text} to my list for tuesday", {"intent": "todo_add", "todo_text": text, "due": due})
    return env["bot"].store.todos(H)[-1]


def tick_at(env, t):
    env["clock"][0] = t
    return env["bot"].tick()


def test_bn2_a_todo_due_tuesday_is_nudged_once_on_wednesday_then_tomorrow_moves_it_and_drop_it_removes_it(env):
    bot, ch = env["bot"], env["ch"]
    t = tue_todo(env)
    assert tick_at(env, u(2026, 11, 17, 23, 1)) == 1 and last(ch) == "Reminder from your list: call the bank"
    assert tick_at(env, u(2026, 11, 18, 22, 59)) == 0                         # Wednesday 5:59pm: not yet a day
    assert tick_at(env, u(2026, 11, 18, 23, 1)) == 1
    assert last(ch) == '"call the bank" was due yesterday. Reply "done 1", "tomorrow" or "drop it".'
    for m in (10, 30, 50):
        assert tick_at(env, u(2026, 11, 18, 23, m)) == 0                      # never twice
    assert bot.store.scheduled_today(H, u(2026, 11, 18, 5, 0)) == 1          # it counts toward the daily limit
    msg = say(env, "tomorrow", no_model)
    assert msg == 'OK. "call the bank" is now due tomorrow at 6pm.'
    assert bot.store.todo(t["id"])["due_at"] == "2026-11-19T23:00:00+00:00"
    assert tick_at(env, u(2026, 11, 19, 23, 1)) == 1 and last(ch) == "Reminder from your list: call the bank"
    assert tick_at(env, u(2026, 11, 20, 23, 1)) == 1 and "was due yesterday" in last(ch)
    assert say(env, "drop it", no_model) == 'OK. I took "call the bank" off your list.'
    assert bot.store.todo(t["id"])["removed_at"] and not bot.store.todos(H)
    assert tick_at(env, u(2026, 11, 22, 23, 1)) == 0


def test_bn2_tomorrow_and_drop_it_are_read_only_right_after_a_nudge(env):
    bot = env["bot"]
    t = tue_todo(env)
    tick_at(env, u(2026, 11, 17, 23, 1))
    tick_at(env, u(2026, 11, 18, 23, 1))
    n_calls = len(env["calls"])
    say(env, "thanks", {"intent": "chat", "reply": "ok"})                       # any other message ends the question
    say(env, "tomorrow", {"intent": "chat", "reply": "ok"})
    assert len(env["calls"]) == n_calls + 2 and bot.store.todo(t["id"])["due_at"] == "2026-11-17T23:00:00+00:00"


def test_bn2_undo_after_tomorrow_brings_the_due_time_back_and_never_nudges_twice(env):
    bot, ch = env["bot"], env["ch"]
    t = tue_todo(env)
    tick_at(env, u(2026, 11, 17, 23, 1))
    tick_at(env, u(2026, 11, 18, 23, 1))
    say(env, "tomorrow", no_model)
    env["clock"][0] = u(2026, 11, 18, 23, 5)
    assert "the reminder is off" in say(env, "undo", no_model)
    assert bot.store.todo(t["id"])["due_at"] == "2026-11-17T23:00:00+00:00"
    n0 = len(ch.outbox)
    assert tick_at(env, u(2026, 11, 19, 1, 0)) == 0 and len(ch.outbox) == n0


def test_bn2_the_nudge_waits_for_quiet_hours_to_end(env):
    ch = env["ch"]
    tue_todo(env, due="2026-11-17T22:30")
    assert tick_at(env, u(2026, 11, 18, 3, 31)) == 1                          # Tue 10:30pm: a time they named
    assert tick_at(env, u(2026, 11, 19, 3, 31)) == 0                          # Wed 10:31pm: quiet hours
    assert tick_at(env, u(2026, 11, 19, 12, 59)) == 0                         # Thu 7:59am
    assert tick_at(env, u(2026, 11, 19, 13, 1)) == 1
    assert last(ch) == '"call the bank" was due on Tuesday 17 November. Reply "done 1", "tomorrow" or "drop it".'


def test_bn2_a_snoozed_or_paused_person_gets_the_nudge_once_it_ends_exactly_once(env):
    bot, ch = env["bot"], env["ch"]
    tue_todo(env)
    tick_at(env, u(2026, 11, 17, 23, 1))
    bot.store.set_snooze(H, u(2026, 11, 20, 5, 0))                            # away until Friday
    for t in (u(2026, 11, 18, 23, 1), u(2026, 11, 19, 15, 0), u(2026, 11, 19, 23, 1)):
        assert tick_at(env, t) == 0
    assert tick_at(env, u(2026, 11, 20, 14, 0)) == 1
    assert last(ch) == '"call the bank" was due on Tuesday 17 November. Reply "done 1", "tomorrow" or "drop it".'
    assert tick_at(env, u(2026, 11, 20, 15, 0)) == 0
    # the kill switch for one person: nothing, then one nudge once it is lifted
    bot.store.set_snooze(H, None)
    tue_todo(env, text="post the letter")
    tick_at(env, u(2026, 11, 17, 23, 1))
    bot.store.x("UPDATE people SET paused=1 WHERE handle=?", (H,))
    assert tick_at(env, u(2026, 11, 18, 23, 1)) == 0
    bot.store.x("UPDATE people SET paused=0 WHERE handle=?", (H,))
    assert tick_at(env, u(2026, 11, 18, 23, 2)) == 1 and "post the letter" in last(ch)
    assert tick_at(env, u(2026, 11, 18, 23, 30)) == 0


def test_bn2_no_overdue_nudges_stops_them_and_overdue_nudges_on_brings_them_back(env):
    bot = env["bot"]
    tue_todo(env)
    tick_at(env, u(2026, 11, 17, 23, 1))
    assert say(env, "no overdue nudges", no_model).startswith("OK. I won't nudge you about to-dos that are past due.")
    assert bot.store.person_context(H)["prefs"]["overdue_nudges"] is False
    assert tick_at(env, u(2026, 11, 18, 23, 1)) == 0 and tick_at(env, u(2026, 11, 19, 23, 1)) == 0
    say(env, "overdue nudges on", no_model)
    assert tick_at(env, u(2026, 11, 19, 23, 2)) == 1


def test_bn2_old_todos_and_reminders_missed_while_the_bot_was_off_are_never_nudged(env):
    bot = env["bot"]
    env["clock"][0] = u(2026, 11, 16, 15, 0)
    bot.store.add_todo(H, "an old one", due_at=u(2026, 11, 1, 14, 0), at=u(2026, 10, 30, 14, 0))
    bot.store.x("UPDATE todos SET reminded_at=? WHERE handle=?", ("2026-11-01T14:00:00+00:00", H))
    assert tick_at(env, u(2026, 11, 16, 16, 0)) == 0                          # due more than 7 days ago
    tue_todo(env)
    tick_at(env, u(2026, 11, 19, 16, 0))                                      # the bot was off: "I was offline" only
    assert "offline" in last(env["ch"])
    assert tick_at(env, u(2026, 11, 19, 23, 30)) == 0


# ---------- the new phrasings, whatever form the model returns (the live check is the checker's) ----------
QUIET_FORMS = [pasta_spec(NOON), pasta_spec(dict(NOON, if_empty="say")), pasta_spec(dict(NOON, until="2026-11-30")),
               pasta_spec({"type": "random", "count": 3, "per": "week"})]


@pytest.mark.parametrize("form", QUIET_FORMS)
@pytest.mark.parametrize("text,way", [
    ("every day at noon send me a pasta recipe, don't text me if there's nothing", "quiet"),
    ("every day at noon send me a pasta recipe and tell me even if there's nothing", "say"),
    ("send me a pasta recipe at noon every day", "quiet"),                    # no words for it: the default
])
def test_bn2_what_code_does_with_any_form_for_the_empty_day_phrasings(env, form, text, way):
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    preview = say(env, text, {"intent": "new_rule", "spec": form})
    assert env["bot"].store.pending(H)["payload"]["spec"]["when"]["if_empty"] == way
    assert ("On a day with nothing new I'll stay quiet." in preview) == (way == "quiet")


@pytest.mark.parametrize("until", [None, "2026-11-13", "2026-11-30", "2027-11-12"])
@pytest.mark.parametrize("text", [
    "remind me every morning at 8 to apply to the NASA internship until I've done it",
    "every morning at 8 remind me to apply to the NASA internship until I've applied",
    "remind me to apply to the NASA internship every morning at 8 till I tick it off",
])
@pytest.mark.parametrize("keep_phrase", [False, True])
def test_bn2_what_code_does_with_any_form_for_the_until_done_phrasings(env, until, text, keep_phrase):
    from mvp.followup import UNTIL_DONE
    words = "apply to the NASA internship" + (UNTIL_DONE.search(text).group(0) if keep_phrase else "")
    when = {"type": "schedule", "days": DAILY, "time": "08:00", **({"until": until} if until else {})}
    msg = say(env, text, {"intent": "new_rule", "spec": {"when": when, "content": {"source": "note", "text": words}}})
    sp = spec_of(rules(env["bot"])[-1])
    assert sp["when"].get("stop_when") == "done" and "until" not in sp["when"]   # code overrides any guessed end
    assert sp["content"]["text"] == "apply to the NASA internship" and "until you say done" in msg


@pytest.mark.parametrize("form", [{"intent": "chat", "reply": "ok"}, {"intent": "profile_update"},
                                  {"intent": "stop", "all_rules": True}])
def test_bn2_no_overdue_nudges_is_read_by_code_whatever_the_model_would_say(env, form):
    n_calls = len(env["calls"])
    assert say(env, "No overdue nudges please", form).startswith("OK. I won't nudge you")
    assert len(env["calls"]) == n_calls
