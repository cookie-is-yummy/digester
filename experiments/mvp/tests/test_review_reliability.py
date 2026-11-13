"""Offline tests for the reliability review fixes (S1 to S12). Fakes only: no API calls, no real data."""
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

from mvp.tests.test_mvp import env, last  # noqa: F401 - the fixture
from mvp.tests.test_rules_v2 import weekly

H = "+15550001"


def u(*a):
    return datetime(*a, tzinfo=timezone.utc)


def runs(bot, kinds=("scheduled", "todo", "manual")):
    marks = ",".join("?" * len(kinds))
    return [(r["rule_id"], r["kind"], r["status"], r["error"]) for r in
            bot.store.q(f"SELECT rule_id, kind, status, error FROM runs WHERE kind IN ({marks}) ORDER BY id", kinds)]


def race(bot, during):
    """Hold the person's lock the way a message being handled does, tick in a second thread, change state while the
    tick waits, then let it go on."""
    lock = bot.lock_for(H)
    lock.acquire()
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("n", bot.tick()))
    t.start()
    time.sleep(0.4)
    try:
        during()
    finally:
        lock.release()
    t.join(10)
    return out.get("n")


def note_rule(bot, st, when, text="Call mum"):
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "new_rule", "spec": {
        "when": when, "content": {"source": "note", "text": text, "goal": text.lower()}}}
    bot.on_message(H, f"remind me to {text}")
    if bot.store.pending(H):
        bot.on_message(H, "yes")
    return bot.store.rules(H)[-1]


# ---------- S1: the scheduler re-reads the person and the rule under the lock ----------

def test_s1_snooze_set_while_the_tick_waits_is_honoured(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    weekly(bot, st)                                   # Fri 19:00 New York = Sat 00:00 UTC
    clock[0] = u(2026, 11, 14, 0, 0, 30)
    n0 = len(ch.outbox)
    n = race(bot, lambda: bot.store.set_snooze(H, u(2026, 11, 20, 0, 0)))
    assert n == 0 and len(ch.outbox) == n0
    assert runs(bot)[-1][2] == "snoozed"


def test_s1_a_rule_stopped_while_resume_waits_stays_stopped(env):
    bot, st, clock = env["bot"], env["state"], env["clock"]
    r = weekly(bot, st)
    bot.store.pause_rule(r["id"], u(2026, 11, 16, 5, 0))
    clock[0] = u(2026, 11, 16, 5, 0, 20)

    def stop():   # what handler._manage('stop') writes
        bot.store.set_slot(r["id"], None, "stopped")
        bot.store.update_rule(r["id"], paused_until=None)
    race(bot, stop)
    x = bot.store.rule(r["id"])
    assert x["status"] == "stopped" and not x["next_run_at"]


def test_s1_an_import_made_while_the_tick_waits_is_used(env, tmp_path):
    bot, st, clock = env["bot"], env["state"], env["clock"]
    weekly(bot, st)
    lib2 = tmp_path / "lib2"
    shutil.copytree(env["lib"], lib2)
    used = []
    real_view = bot.view
    bot.view = lambda lib: (used.append(lib), real_view(lib))[1]
    clock[0] = u(2026, 11, 14, 0, 0, 30)
    race(bot, lambda: bot.store.switch_library(H, str(lib2)))
    assert used and all(x == str(lib2) for x in used)


def test_s1_a_todo_reminder_honours_a_snooze_set_while_it_waits(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "todo_add", "todo_text": "pay rent", "due": "2026-11-13T10:00"}
    bot.on_message(H, "add pay rent to my list for tomorrow 10am")
    clock[0] = u(2026, 11, 13, 15, 0, 30)
    n0 = len(ch.outbox)
    race(bot, lambda: bot.store.set_snooze(H, u(2026, 11, 20, 0, 0)))
    assert not any("pay rent" in m[2] for m in ch.outbox[n0:])
    assert ("snoozed" in [s for _, k, s, _ in runs(bot) if k == "todo"])


def test_s1_a_time_zone_revert_cancelled_while_upkeep_waits_does_not_run(env):
    bot, clock = env["bot"], env["clock"]
    bot.store.set_timezone(H, "America/Chicago", revert_to="America/New_York", revert_at=u(2026, 11, 13, 5, 0))
    clock[0] = u(2026, 11, 13, 5, 1)
    race(bot, lambda: bot.store.set_timezone(H, "Asia/Tokyo"))   # "I live in Tokyo now": a plain change
    assert bot.store.person(H)["timezone"] == "Asia/Tokyo"


# ---------- S2: every N days / every other week keep their count across a time zone change ----------

def drive(bot, clock, start, end, step=30):
    """Tick every `step` minutes, the person answering each time; the moments a tick sent something."""
    out, t = [], start
    while t < end:
        t += timedelta(minutes=step)
        clock[0] = t
        bot.store.set_state(f"last_in:{H}", "2099-01-01")
        if bot.tick():
            out.append(t)
    return out


def move_to(bot, st, clock, at, tz="Asia/Tokyo"):
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "set_timezone", "timezone": tz}
    clock[0] = at
    bot.on_message(H, "I'm in Tokyo now")


def gaps(days):
    return [(b - a).days for a, b in zip(days, days[1:])]


def test_s2_every_2_days_keeps_its_count_after_a_time_zone_change(env):
    from zoneinfo import ZoneInfo
    from mvp.tests.test_rules_v2 import more_pasta
    bot, st, clock = env["bot"], env["state"], env["clock"]
    clock[0] = u(2026, 11, 13, 4, 30)            # Thu 12 Nov 23:30 New York
    weekly(bot, st, when={"type": "schedule", "every_days": 2, "time": "08:00"})
    more_pasta(bot, 30)
    ny = drive(bot, clock, clock[0], u(2026, 11, 14, 1, 0))
    assert [s.astimezone(ZoneInfo("America/New_York")).date().day for s in ny] == [13]
    move_to(bot, st, clock, u(2026, 11, 14, 1, 0))
    sends = drive(bot, clock, clock[0], u(2026, 11, 22, 0, 0))
    days = [s.astimezone(ZoneInfo("Asia/Tokyo")).date() for s in sends]
    assert [d.day for d in days] == [15, 17, 19, 21] and set(gaps(days)) == {2}


def test_s2_every_other_monday_keeps_its_weeks_after_a_time_zone_change(env):
    from zoneinfo import ZoneInfo
    from mvp.tests.test_rules_v2 import more_pasta
    bot, st, clock = env["bot"], env["state"], env["clock"]
    clock[0] = u(2026, 11, 16, 12, 0)            # Mon 16 Nov 7am New York
    weekly(bot, st, when={"type": "schedule", "days": ["MON"], "every_weeks": 2, "time": "08:00"})
    more_pasta(bot, 30)
    s1 = drive(bot, clock, clock[0], u(2026, 11, 16, 14, 0), step=10)
    move_to(bot, st, clock, u(2026, 11, 17, 1, 0))
    s2 = drive(bot, clock, clock[0], u(2026, 12, 30), step=60)
    days = [s.astimezone(ZoneInfo("America/New_York")).date() for s in s1] + \
        [s.astimezone(ZoneInfo("Asia/Tokyo")).date() for s in s2]
    assert days[0].day == 16 and set(gaps(days)) == {14}


def test_s2_the_kept_day_is_used_in_the_new_zone():
    from mvp.schedule import base_day, next_run
    from mvp.schema import When
    w = When(type="schedule", every_days=2, time="08:00")
    made = u(2026, 11, 13, 4, 30)                 # Thu 23:30 New York, Fri 13:30 Tokyo
    assert base_day(w, "America/New_York", made) == "2026-11-13"
    assert base_day(w, "Asia/Tokyo", made) == "2026-11-14"
    after = u(2026, 11, 14, 1, 0)                 # Sat 10:00 Tokyo
    # counted from the 13th, the next send in Tokyo is Sun 15 at 8am (Sat 14 23:00 UTC), not Mon 16
    assert next_run(w, "Asia/Tokyo", after, anchor=made, base="2026-11-13") == u(2026, 11, 14, 23, 0)
    assert next_run(w, "Asia/Tokyo", after, anchor=made) == u(2026, 11, 15, 23, 0)


# ---------- S3: after the bot was off, nothing the person asked for is dropped without a word ----------

DAILY = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def test_s3_an_outage_tells_about_missed_reminders_and_records_every_slot(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    weekly(bot, st)                                                         # Fri 19:00 New York
    d = weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "08:00"})
    n = note_rule(bot, st, {"type": "once", "date": "2026-11-13", "time": "16:00"})
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "todo_add", "todo_text": "pay rent", "due": "2026-11-13T10:00"}
    bot.on_message(H, "add pay rent to my list for tomorrow 10am")
    n0 = len(ch.outbox)
    clock[0] = u(2026, 11, 15, 23, 0)          # off from Thu 18:00 UTC to Sun 23:00 UTC (Sun 6pm New York)
    bot.tick()
    out = " ".join(m[2] for m in ch.outbox[n0:])
    assert "Call mum" in out and "pay rent" in out and "offline" in out
    assert "still on your list" in out
    assert bot.store.rule(n["id"])["status"] == "done"
    rr = runs(bot)
    assert len([x for x in rr if x[0] == d["id"] and x[2] == "missed"]) == 3    # Fri, Sat and Sun at 8am
    assert [x[2] for x in rr if x[1] == "todo"] == ["missed"]


def test_s3_a_missed_reminder_notice_waits_for_quiet_hours_to_end(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    note_rule(bot, st, {"type": "once", "date": "2026-11-13", "time": "16:00"})
    n0 = len(ch.outbox)
    clock[0] = u(2026, 11, 14, 4, 0)           # Fri 11pm New York: quiet hours
    bot.tick()
    assert len(ch.outbox) == n0
    clock[0] = u(2026, 11, 14, 13, 5)          # Sat 8:05am
    bot.tick()
    assert "Call mum" in " ".join(m[2] for m in ch.outbox[n0:])


def test_s3_a_time_zone_switch_back_after_an_outage_records_the_missed_moment(env):
    from mvp.tests.test_rules_v2 import more_pasta
    bot, st, clock = env["bot"], env["state"], env["clock"]
    r = weekly(bot, st, when={"type": "random", "per": "day", "count": 1})
    more_pasta(bot, 30)
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "set_timezone", "timezone": "America/Chicago",
                                                "until": "2026-11-14"}
    bot.on_message(H, "I'm in Chicago until tomorrow")
    p, rule = bot.store.person(H), bot.store.rule(r["id"])
    due = datetime.fromisoformat(rule["next_run_at"])
    clock[0] = max(due, datetime.fromisoformat(p["tz_revert_at"])) + timedelta(hours=3)
    before = len(runs(bot))
    bot.tick()
    assert "missed" in [x[2] for x in runs(bot)[before:] if x[0] == r["id"]]


# ---------- S4 and S5: "undo" means what the person just did ----------

def test_s4_undo_after_a_timed_todo_add_reverses_the_persons_own_write(env):
    from mvp.tests.test_mvp import compose_picks, pasta_spec
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "new_rule", "spec": dict(pasta_spec(), do=[
        {"action": "message.send"}, {"action": "todo.add"}])}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    bot.on_message(H, "pasta every friday at 7pm and add it to my list")
    bot.on_message(H, "yes")
    other = weekly(bot, st, when={"type": "schedule", "days": ["MON"], "time": "08:00"})
    clock[0] = u(2026, 11, 13, 23, 58)
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "stop", "rule_number": 2}
    bot.on_message(H, "stop 2")
    assert bot.store.rule(other["id"])["status"] == "stopped"
    clock[0] = u(2026, 11, 14, 0, 0, 30)
    assert bot.tick() == 1
    n_todos = len(bot.store.todos(H))
    assert n_todos == 1
    clock[0] = u(2026, 11, 14, 0, 2)
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "undo"}
    bot.on_message(H, "undo")
    assert bot.store.rule(other["id"])["status"] == "active"     # the stop is undone
    assert len(bot.store.todos(H)) == n_todos                    # the timed send's to-do stays


def _ask_then(bot, st, act, words="do it"):
    from mvp.tests.test_mvp import pasta_spec
    r = weekly(bot, st)
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    bot.on_message(H, "pasta ideas?")
    st["answers"]["mvp_interpret"] = lambda x: act
    bot.on_message(H, words)
    st["answers"]["mvp_interpret"] = lambda x: {"intent": "undo"}
    bot.on_message(H, "undo")
    return r


def test_s5_undo_after_a_calendar_link_leaves_the_rule_alone(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    r = _ask_then(bot, st, {"intent": "act_on_last", "actions": [
        {"action": "calendar.add", "params": {"time": "19:00"}}], "pick_number": 1})
    assert bot.store.rule(r["id"])["status"] == "active"
    assert "can't take back a calendar link" in last(ch)


def test_s5_undo_after_feedback_leaves_the_rule_alone(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    r = _ask_then(bot, st, {"intent": "feedback", "feedback": "hide", "pick_number": 1})
    assert bot.store.rule(r["id"])["status"] == "active"
    assert "can't take back feedback" in last(ch)


def test_s5_undo_after_calendar_and_list_takes_the_todos_off_only(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    r = _ask_then(bot, st, {"intent": "act_on_last", "actions": [
        {"action": "calendar.add", "params": {"time": "19:00"}}, {"action": "todo.add"}], "pick_number": 1},
        "put the first one on my calendar for 7 and add it to my list")
    assert bot.store.rule(r["id"])["status"] == "active"
    assert not bot.store.todos(H) and "off your list" in last(ch)
