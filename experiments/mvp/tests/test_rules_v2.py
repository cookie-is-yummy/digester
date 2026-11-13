"""Offline tests for RuleSpec v 2, every timing form, person-level timing and the scheduler's guards (DESIGN.md
sections 1 and 11). Synthetic data only; the bot fixtures come from test_mvp.py."""
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)

NY = "America/New_York"
UTC = timezone.utc
ANCHOR = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)   # Thursday 12 November 2026, 1pm in New York
DAILY = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def W(**kw):
    from mvp.schema import When
    return When(**kw)


def nxt(when, after=ANCHOR, anchor=ANCHOR, tz=NY, seed=1, quiet=None):
    from mvp.schedule import next_run
    return next_run(when, tz, after, anchor=anchor, seed=seed, quiet=quiet)


def run_of(when, n, after=ANCHOR, **kw):
    out, t = [], after
    for _ in range(n):
        t = nxt(when, after=t, **kw)
        if t is None:
            break
        out.append(t)
    return out


def u(*a):
    return datetime(*a, tzinfo=UTC)


def local(t, tz=NY):
    from zoneinfo import ZoneInfo
    return t.astimezone(ZoneInfo(tz))


# ---------- next_run for every form ----------

def test_every_2_days_counts_from_creation_or_start():
    w = W(type="schedule", every_days=2, times=["08:00"])
    # 8am on the 12th has passed when the rule is made at 1pm, so the first is the 13th, then every second day
    assert run_of(w, 3) == [u(2026, 11, 13, 13), u(2026, 11, 15, 13), u(2026, 11, 17, 13)]
    w2 = W(type="schedule", every_days=2, times=["08:00"], start="2026-11-20")
    assert run_of(w2, 2) == [u(2026, 11, 20, 13), u(2026, 11, 22, 13)]


def test_month_days_first_and_fifteenth_and_last_day():
    w = W(type="schedule", month_days=[1, 15])
    assert run_of(w, 3) == [u(2026, 11, 15, 14), u(2026, 12, 1, 14), u(2026, 12, 15, 14)]
    last_day = W(type="schedule", month_days=[31])
    assert last_day.month_days == [-1]                                   # one stored form for one meaning
    days = [local(t).date().isoformat() for t in run_of(last_day, 4)]
    assert days == ["2026-11-30", "2026-12-31", "2027-01-31", "2027-02-28"]   # a 30-day month and February
    thirtieth = W(type="schedule", month_days=[29, 30], times=["09:00"])
    feb = [local(t).date().isoformat() for t in run_of(thirtieth, 8, after=u(2027, 1, 20))]
    assert feb[:3] == ["2027-01-29", "2027-01-30", "2027-02-28"]       # past the end means the last day, once
    assert feb[3] == "2027-03-29"


def test_month_weeks_first_monday_and_last_friday():
    first_monday = W(type="schedule", month_weeks=[1], days=["MON"])
    assert [local(t).date().isoformat() for t in run_of(first_monday, 3)] == ["2026-12-07", "2027-01-04", "2027-02-01"]
    last_friday = W(type="schedule", month_weeks=[-1], days=["FRI"], times=["17:00"])
    assert run_of(last_friday, 2) == [u(2026, 11, 27, 22), u(2026, 12, 25, 22)]
    fifth = W(type="schedule", month_weeks=[5], days=["MON"])          # only months that have a fifth Monday
    assert [local(t).date().isoformat() for t in run_of(fifth, 2)] == ["2026-11-30", "2027-03-29"]


def test_every_6_months_and_each_year():
    from mvp.schedule import complete
    w = complete(W(type="schedule", every_months=6), ANCHOR, NY)
    assert w.month_days == [12]                                          # "every 6 months" with no day: today's day
    # counted from the month it was made; 9am on the 12th had passed, so the first is six months on
    assert run_of(w, 2) == [u(2027, 5, 12, 13), u(2027, 11, 12, 14)]
    yearly = W(type="schedule", every_months=12, month_days=[3], start="2027-03-03")
    assert run_of(yearly, 2) == [u(2027, 3, 3, 14), u(2028, 3, 3, 14)]
    on_31 = complete(W(type="schedule", every_months=1), u(2026, 12, 31, 18), NY)
    assert on_31.month_days == [-1]
    weeks = complete(W(type="schedule", every_weeks=3), ANCHOR, NY)
    assert weeks.days == ["THU"]                                         # "every 3 weeks": today's weekday


def test_every_2_hours_in_a_window_and_quiet_blocks():
    w = W(type="schedule", every_hours=2, window=["09:00", "17:00"])
    assert run_of(w, 3) == [u(2026, 11, 12, 20), u(2026, 11, 12, 22), u(2026, 11, 13, 14)]   # 3pm, 5pm, then 9am
    lunch = [{"start": "22:00", "end": "08:00"}, {"start": "12:00", "end": "14:00"}]
    after = u(2026, 11, 12, 16, 30)                                      # 11:30 in New York
    assert nxt(w, after=after, quiet=lunch) == u(2026, 11, 12, 20)      # 1pm is inside a quiet block: skipped
    early = W(type="schedule", every_hours=1, window=["06:00", "09:00"])
    assert [local(t).hour for t in run_of(early, 2, after=u(2026, 11, 13, 5))] == [8, 9]   # 6 and 7 are quiet


def test_twice_a_day_defaults_and_until():
    from mvp.schedule import TIMES_A_DAY, times_a_day
    assert times_a_day(2) == ["08:00", "20:00"] and times_a_day(3) == ["08:00", "13:00", "19:00"]
    assert times_a_day(4) == ["08:00", "13:00", "16:00", "19:00"] and TIMES_A_DAY[1] == ["09:00"]
    w = W(type="schedule", times=times_a_day(2), until="2026-12-24")
    assert w.days == DAILY
    assert run_of(w, 3) == [u(2026, 11, 13, 1), u(2026, 11, 13, 13), u(2026, 11, 14, 1)]
    assert nxt(w, after=u(2026, 12, 24, 14)) == u(2026, 12, 25, 1)       # 8pm on the 24th is still in
    assert nxt(w, after=u(2026, 12, 25, 2)) is None                      # until has passed: the rule is done


def test_a_window_is_one_seeded_moment_a_day_clipped_to_waking_hours():
    w = W(type="schedule", window=["18:00", "20:00"])
    moments = run_of(w, 6, seed=11)
    assert moments == run_of(w, 6, seed=11)                              # the same after a restart
    assert all(18 <= local(t).hour < 20 for t in moments)
    assert len({local(t).date() for t in moments}) == 6                  # one a day
    assert len({(local(t).hour, local(t).minute) for t in moments}) > 1  # at different minutes
    late = W(type="schedule", window=["21:00", "23:00"])
    assert all(local(t).hour == 21 for t in run_of(late, 10, seed=3))    # 22:00 to 08:00 is quiet: clipped


def test_random_three_a_week_seeded_quiet_and_mid_week():
    from mvp.schedule import in_quiet_hours, random_moments
    w = W(type="random")
    assert (w.per, w.count, w.window) == ("week", 3, ["09:00", "21:00"])    # "randomly" with nothing else
    monday = datetime(2026, 11, 16, 0, 0, tzinfo=local(ANCHOR).tzinfo)
    week = random_moments(w, NY, date(2026, 11, 16), monday, seed=5)
    assert len(week) == 3 and week == random_moments(w, NY, date(2026, 11, 16), monday, seed=5)   # stable
    assert week != random_moments(w, NY, date(2026, 11, 16), monday, seed=6)                       # per rule
    assert all(9 <= local(t).hour < 21 and local(t).date() >= date(2026, 11, 16) for t in week)
    # created on Wednesday at noon: only what is left of the week is used, and the count is scaled to it
    wed = u(2026, 11, 18, 17)
    this_week = random_moments(w, NY, date(2026, 11, 18), wed, seed=5)
    assert len(this_week) == 2 and all(t > wed for t in this_week)      # 57 of 84 waking hours left: 2 of 3
    sends = run_of(w, 8, after=wed, anchor=wed, seed=5)
    by_week = {}
    for t in sends:
        by_week.setdefault(local(t).date().isocalendar()[1], []).append(t)
    assert [len(v) for v in by_week.values()][:3] == [2, 3, 3]
    # never inside quiet hours, whatever they are
    quiet = [{"start": "12:00", "end": "18:00"}, {"start": "22:00", "end": "08:00"}]
    for seed in range(30):
        for t in run_of(w, 3, seed=seed, quiet=quiet):
            assert not in_quiet_hours(t, NY, quiet) and 9 <= local(t).hour < 21


def test_random_per_day_in_a_window_and_on_days():
    w = W(type="random", per="day", window=["07:00", "10:00"], days=["MON", "TUE", "WED", "THU", "FRI"])
    assert w.count == 1
    sends = run_of(w, 5, seed=2)
    assert [local(t).strftime("%a") for t in sends] == ["Fri", "Mon", "Tue", "Wed", "Thu"]
    assert all(8 <= local(t).hour < 10 for t in sends)                   # 7 to 8 is quiet: clipped


def test_except_dates_start_until_and_pinned_zone():
    w = W(type="schedule", days=["MON", "TUE", "WED", "THU", "FRI"], times=["08:00"], except_dates=["2026-11-26"])
    assert nxt(w, after=u(2026, 11, 25, 14)) == u(2026, 11, 27, 13)     # not on Thanksgiving
    starts = W(type="schedule", days=["MON"], times=["07:00"], start="2026-11-23", until="2026-11-30")
    assert run_of(starts, 5) == [u(2026, 11, 23, 12), u(2026, 11, 30, 12)]
    pinned = W(type="schedule", days=["FRI"], times=["19:00"], tz="America/Los_Angeles")
    assert nxt(pinned) == u(2026, 11, 14, 3)                             # 7pm in Los Angeles, wherever they are
    assert nxt(pinned, tz="Europe/London") == u(2026, 11, 14, 3)
    once = W(type="once", date="2026-11-20", time="19:00", tz="America/Chicago")
    assert nxt(once) == u(2026, 11, 21, 1)


def test_both_daylight_saving_changes():
    daily = W(type="schedule", times=["08:00"])
    assert run_of(daily, 2, after=u(2027, 3, 13, 14)) == [u(2027, 3, 14, 12), u(2027, 3, 15, 12)]   # spring forward
    gap = W(type="schedule", times=["02:30"])                            # 2:30 does not exist on 14 March 2027
    assert run_of(gap, 2, after=u(2027, 3, 13, 8)) == [u(2027, 3, 14, 7, 30), u(2027, 3, 15, 6, 30)]
    hourly = W(type="schedule", every_hours=1, window=["00:00", "03:00"])
    night = run_of(hourly, 4, after=u(2026, 11, 1, 3), quiet=[])        # 1 November 2026: clocks go back at 2am
    assert night == [u(2026, 11, 1, 4), u(2026, 11, 1, 5), u(2026, 11, 1, 7), u(2026, 11, 1, 8)]
    weekly = W(type="random")
    mon = u(2027, 3, 8, 5)
    moments = run_of(weekly, 3, after=mon, anchor=mon, seed=9)
    assert len(moments) == 3 and all(9 <= local(t).hour < 21 for t in moments)


# ---------- describe ----------

def test_describe_reads_naturally_for_every_form():
    from mvp.schedule import describe, times_a_day
    cases = [
        (dict(type="schedule", days=["FRI"], time="19:00"), "every Friday at 7pm"),
        (dict(type="schedule", every_days=2, times=["08:00"]), "every 2 days at 8am"),
        (dict(type="schedule", month_days=[1, 15]), "on the 1st and 15th at 9am"),
        (dict(type="schedule", month_days=[12]), "on the 12th of every month at 9am"),
        (dict(type="schedule", month_days=[31]), "on the last day of the month at 9am"),
        (dict(type="schedule", month_days=[1, -1]), "on the 1st and the last day of the month at 9am"),
        (dict(type="schedule", month_weeks=[1], days=["MON"]), "on the first Monday of every month at 9am"),
        (dict(type="schedule", month_weeks=[-1], days=["FRI"], times=["17:30"]),
         "on the last Friday of every month at 5:30pm"),
        (dict(type="schedule", every_months=6, month_days=[12]), "every 6 months on the 12th at 9am"),
        (dict(type="schedule", every_months=12, month_days=[3], start="2027-03-03"), "every year on 3 March at 9am"),
        (dict(type="schedule", every_hours=2, window=["09:00", "17:00"]), "every 2 hours from 9am to 5pm"),
        (dict(type="schedule", every_hours=1, window=["09:00", "12:00"], days=["MON", "TUE", "WED", "THU", "FRI"]),
         "every weekday, every hour from 9am to noon"),
        (dict(type="schedule", times=times_a_day(2), until="2026-12-24"),
         "twice a day, at 8am and 8pm, until 24 December"),
        (dict(type="schedule", times=times_a_day(3)), "three times a day, at 8am, 1pm and 7pm"),
        (dict(type="schedule", window=["18:00", "20:00"]), "every day at a random time between 6pm and 8pm"),
        (dict(type="schedule", days=["FRI"], every_days=14, times=["17:00"]), "every other Friday at 5pm"),
        (dict(type="schedule", days=["MON", "TUE", "THU", "FRI", "SAT", "SUN"], times=["06:00"]),
         "every day except Wednesday at 6am"),
        (dict(type="schedule", days=["SAT"], times=["10:00"], every_weeks=3), "every 3 weeks on Saturday at 10am"),
        (dict(type="schedule", days=["MON", "TUE", "WED", "THU", "FRI"], times=["07:00"], start="2026-11-16"),
         "every weekday at 7am, starting 16 November"),
        (dict(type="schedule", times=["08:00"], max_sends=5), "every day at 8am, 5 times in all"),
        (dict(type="schedule", days=["MON", "TUE", "WED", "THU", "FRI"], times=["08:00"], except_dates=["2026-11-26"]),
         "every weekday at 8am, except on 26 November"),
        (dict(type="schedule", days=["FRI"], times=["19:00"], tz="America/New_York"), "every Friday at 7pm New York time"),
        (dict(type="random"), "about 3 times a week at random times"),
        (dict(type="random", per="week", count=1, max_sends=1), "once a week at a random time, just once"),
        (dict(type="random", per="day", window=["07:00", "10:00"]), "once a day at a random time between 7am and 10am"),
        (dict(type="random", count=2, days=["SAT", "SUN"]), "about 2 times a week at random times on weekends"),
        (dict(type="once", date="2026-11-13", time="08:00"), "once on Fri 13 Nov at 8am"),
        (dict(type="once", in_minutes=20), "in 20 minutes"),
        (dict(type="on_request"), "whenever you ask"),
        (dict(type="new_items"), "whenever you save something new that fits"),
    ]
    for kw, want in cases:
        assert describe(W(**kw)) == want, kw


# ---------- the schema ----------

def test_canonical_forms_and_validation():
    from pydantic import ValidationError
    w = W(type="schedule", days=["fri"], time="19:00")
    assert (w.times, w.time, w.every_weeks) == (["19:00"], None, 1)      # time is an alias for one time
    assert W(type="schedule", days=["FRI"], every_days=14).every_weeks == 2
    assert W(type="schedule", every_days=1, times=["08:00"]).days == DAILY
    assert W(type="schedule", times=["08:00"]).days == DAILY               # times with no cadence: every day
    assert W(type="schedule", days=["MON"]).times == ["09:00"]             # no time given: the default, shown in describe
    assert W(type="once", in_minutes=30, date="2026-11-12", time="10:00").date is None
    bad = [dict(type="schedule", days=["MON"], every_days=3),            # two cadences
           dict(type="schedule", month_days=[1], days=["MON"]),
           dict(type="schedule", every_hours=2, times=["09:00"]),         # every_hours needs a window
           dict(type="schedule", window=["18:00", "20:00"], times=["19:00"]),
           dict(type="schedule", month_weeks=[1]),                        # which day?
           dict(type="schedule", times=["06:00", "08:00", "10:00", "12:00", "14:00"]),
           dict(type="schedule", every_weeks=9, days=["MON"]),
           dict(type="schedule", every_days=91),
           dict(type="schedule", days=["MON"], count=2),                  # count is for random
           dict(type="schedule", month_days=[32]),
           dict(type="schedule", window=["20:00", "18:00"]),
           dict(type="random", per="day", count=5),
           dict(type="random", times=["09:00"]),
           dict(type="schedule", days=["MON"], start="2026-12-01", until="2026-11-01"),
           dict(type="schedule", days=["MON"], tz="Mars/Base"),
           dict(type="once", date="2026-11-12"),
           dict(type="schedule", days=["XYZ"])]
    for kw in bad:
        with pytest.raises(ValidationError):
            W(**kw)
    # fields that do not belong to the type are dropped, so the stored form is one per meaning
    assert W(type="once", date="2026-11-13", time="08:00", days=["MON"], max_sends=3).model_dump(exclude_none=True) == \
        {"type": "once", "date": "2026-11-13", "days": [], "month_days": [], "month_weeks": [], "times": ["08:00"],
         "except_dates": []}


def test_content_v2_fields_and_limits():
    from pydantic import ValidationError
    from mvp.schema import Content, Interpretation, RuleSpec
    c = Content(goal="pasta", searches=["pasta"], extract="ingredients", creators=["@Chef_A", "chef_a"],
                criteria=["ends with a dish you can eat"], order="easiest_first", outside="only", style="brief",
                avoid_collections=["Old stuff"])
    assert c.extract == ["ingredients"] and c.creators == ["chef_a"] and c.outside == "only"
    assert Content(goal="x y", searches=["a"], extract="none").extract == []
    assert Content(goal="x y", searches=["a"], extract=["ingredients", "steps"]).extract == ["ingredients", "steps"]
    note = Content(source="note", text="Call mum")
    assert note.goal == "Call mum" and note.searches == []
    assert Content(source="todos").goal == "your to-do list"
    assert Content(source="recent").since_days == 7
    ask = Content(goal="x y", searches=["a"], count=12)
    assert (ask.count, ask.asked_count) == (10, 12)                       # cut, and the number asked is kept
    rule = RuleSpec.model_validate({"when": {"type": "schedule", "days": ["FRI"], "time": "19:00"},
                                    "content": {"goal": "x y", "searches": ["a"], "count": 8}})
    assert (rule.content.count, rule.content.asked_count) == (5, 8)
    for kw in [dict(source="note"), dict(source="items"), dict(goal="x y", searches=["a"], item_ids=["i1"]),
               dict(goal="x y"), dict(goal="x y", searches=["a"], extract=["poems"]),
               dict(goal="x y", searches=["a"], criteria=["a", "b", "c", "d", "e", "f"]),
               dict(goal="x y", searches=["a"], saved_after="2026-10-01", saved_before="2026-09-01"),
               dict(goal="x y", searches=["a"], order="loudest")]:
        with pytest.raises(ValidationError):
            Content(**kw)
    assert Content(source="items", item_ids=["i1", "i2"]).item_ids == ["i1", "i2"]
    with pytest.raises(ValidationError):                                  # the model never sets item_ids
        Interpretation.model_validate({"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
            "source": "items", "item_ids": ["i1"]}}})


def test_do_is_validated_against_the_action_registry():
    from pydantic import ValidationError
    from mvp.actions import REGISTRY, needs
    from mvp.schema import RuleSpec
    base = {"when": {"type": "schedule", "days": ["MON"], "time": "08:00"}, "content": {"goal": "x y", "searches": ["a"]}}
    s = RuleSpec.model_validate(dict(base, do=["message.send", "email.send", "email.send"]))
    assert [a.action for a in s.do] == ["message.send", "email.send"]
    s = RuleSpec.model_validate(dict(base, do=[{"action": "calendar.add", "params": {"time": "7:00", "day_offset": 2}},
                                               {"action": "todo.add"}]))
    assert s.do[0].params == {"time": "07:00", "day_offset": 2} and s.do[1].params == {}
    assert RuleSpec.model_validate(base).stored()["do"] == [{"action": "message.send"}]
    assert set(REGISTRY) == {"message.send", "email.send", "calendar.add", "todo.add"} and needs("email.send") == "verified_email"
    for do in [["sms.send"], [{"action": "calendar.add", "params": {"time": "25:00"}}],
               [{"action": "calendar.add", "params": {"date": "2026-11-20", "day_offset": 1}}],
               [{"action": "email.send", "params": {"to": "someone@example.com"}}], "sms.send"]:
        with pytest.raises(ValidationError):
            RuleSpec.model_validate(dict(base, do=do))
    # forms a model gives for "just reply" or one action: read as the list they mean (nothing outside the registry)
    for do in ([], None):
        assert RuleSpec.model_validate(dict(base, do=do)).stored()["do"] == [{"action": "message.send"}]
    assert RuleSpec.model_validate(dict(base, do="email.send")).stored()["do"] == [{"action": "email.send"}]
    one = RuleSpec.model_validate(dict(base, do={"action": "todo.add", "params": None}))
    assert one.stored()["do"] == [{"action": "todo.add"}]


def test_v1_specs_still_validate():
    from mvp.schema import RuleSpec
    v1 = [
        {"v": 1, "when": {"type": "schedule", "days": ["FRI"], "every_weeks": 4, "time": "19:00", "date": None,
                          "in_minutes": None, "max_sends": 3},
         "content": {"goal": "a pasta recipe", "searches": ["pasta recipe"], "kinds": ["save"], "platforms": [],
                     "count": 2, "extract": "ingredients", "avoid": ["cream"], "since_days": None, "saved_after": None,
                     "saved_before": None, "exclude_sent": True}, "do": [{"action": "message.send"}]},
        {"v": 1, "when": {"type": "once", "days": [], "every_weeks": 1, "time": "15:00", "date": "2026-11-12",
                          "in_minutes": None, "max_sends": None},
         "content": {"goal": "a pasta recipe", "searches": ["pasta"], "count": 1, "extract": "none"}},
        {"v": 1, "when": {"type": "on_request", "days": [], "every_weeks": 1}, "content": {"goal": "pasta", "searches": ["p"],
                                                                                          "extract": "key_points"}},
        {"v": 1, "when": {"type": "now"}, "content": {"goal": "pasta", "searches": ["p"], "extract": "steps"}},
    ]
    specs = [RuleSpec.model_validate(s) for s in v1]
    assert specs[0].v == 2 and specs[0].when.times == ["19:00"] and specs[0].when.every_weeks == 4
    assert specs[0].when.max_sends == 3 and specs[0].content.extract == ["ingredients"]
    assert specs[1].stored()["when"] == {"type": "once", "date": "2026-11-12", "times": ["15:00"]}
    assert specs[2].content.extract == ["key_points"] and specs[3].content.extract == ["steps"]
    for s in specs:   # the stored form loads back to the same spec
        assert RuleSpec.model_validate(s.stored()).same_as(s)


def test_quiet_blocks_validate_and_read():
    from pydantic import ValidationError
    from mvp.schedule import end_of_quiet, in_quiet_hours
    from mvp.schema import quiet_blocks
    assert [b.model_dump() for b in quiet_blocks(None)] == [{"start": "22:00", "end": "08:00", "days": []}]
    with pytest.raises(ValidationError):
        quiet_blocks([{"start": "9:00", "end": "9:00"}])
    with pytest.raises(ValueError):
        quiet_blocks([{"start": "01:00", "end": "02:00"}] * 5)
    school = [{"start": "22:00", "end": "08:00"}, {"start": "09:00", "end": "15:00", "days": ["MON", "TUE", "WED", "THU", "FRI"]}]
    assert in_quiet_hours(u(2026, 11, 16, 15), NY, school)                 # Monday 10am: class
    assert not in_quiet_hours(u(2026, 11, 21, 15), NY, school)             # Saturday 10am
    assert end_of_quiet(u(2026, 11, 16, 15), NY, school) == u(2026, 11, 16, 20)
    friday_night = [{"start": "23:00", "end": "09:00", "days": ["FRI"]}]
    assert in_quiet_hours(u(2026, 11, 14, 4), NY, friday_night)            # Friday 11pm
    assert in_quiet_hours(u(2026, 11, 14, 12), NY, friday_night)           # Saturday 7am: the block started Friday
    assert not in_quiet_hours(u(2026, 11, 15, 4), NY, friday_night)        # Saturday 11pm
    chained = [{"start": "22:00", "end": "08:00"}, {"start": "08:00", "end": "10:00"}]
    assert end_of_quiet(u(2026, 11, 13, 4), NY, chained) == u(2026, 11, 13, 15)   # 10am: blocks that touch chain


# ---------- the store and the scheduler ----------

def weekly(bot, st, h="+15550001", when=None):
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "new_rule", "spec": pasta_spec(when)}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    bot.on_message(h, "pasta rule")
    bot.on_message(h, "yes")
    return bot.store.rules(h)[-1]


def more_pasta(bot, n=12):
    from mvp.libview import Item
    view = bot.view(next(iter(bot.views)) if bot.views else bot.store.person("+15550001")["library"])
    ids = []
    for i in range(n):
        iid = f"itm_p{i}"
        view.items[iid] = Item({"id": iid, "platform": "instagram", "source_url": f"https://example.com/{iid}",
                                "caption": f"Pasta number {i}", "interaction_kinds": ["save"], "platform_data": {}})
        ids.append(iid)
    bot.pool.search = lambda lib, q, depth=300: {"ids": ids, "mode": "normal", "cost_usd": 0.0}


def statuses(bot):
    return [r["status"] for r in bot.store.q("SELECT status FROM runs WHERE kind='scheduled' ORDER BY id")]


def test_a_store_made_by_the_old_code_still_loads_and_runs(env, tmp_path):
    from mvp.core import Bot
    from mvp.store import Store
    old = tmp_path / "old.sqlite"
    db = sqlite3.connect(old)
    db.executescript("""
CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT NOT NULL,
  consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE rules (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, text TEXT, spec TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT, next_run_at TEXT, last_run_at TEXT);""")
    v1 = {"v": 1, "when": {"type": "schedule", "days": ["FRI"], "every_weeks": 1, "time": "19:00", "date": None,
                           "in_minutes": None, "max_sends": None},
          "content": {"goal": "a pasta recipe", "searches": ["pasta recipe"], "kinds": [], "platforms": [], "count": 1,
                      "extract": "ingredients", "avoid": [], "since_days": None, "saved_after": None,
                      "saved_before": None, "exclude_sent": True}, "do": [{"action": "message.send"}]}
    db.execute("INSERT INTO people VALUES ('+15550001', 'T', ?, 'America/New_York', 'v', '2026-11-01', 0, '2026-11-01')",
               (str(env["lib"]),))
    db.execute("INSERT INTO rules(handle,text,spec,status,created_at,next_run_at) VALUES "
               "('+15550001','pasta',?,'active','2026-11-10T12:00:00+00:00','2026-11-14T00:00:00+00:00')", (json.dumps(v1),))
    db.commit()
    db.close()
    store = Store(str(old))
    cols = {r["name"] for r in store.q("PRAGMA table_info(rules)")} | {r["name"] for r in store.q("PRAGMA table_info(people)")}
    assert {"slot_at", "paused_until", "skip_count", "skip_dates", "quiet", "snooze_until", "tz_revert_to",
            "tz_revert_at"} <= cols
    r = store.rules("+15550001")[0]
    assert r["skip_count"] == 0 and r["skip_dates"] == [] and store.quiet("+15550001") == [{"start": "22:00", "end": "08:00"}]
    Store(str(old))                                                     # opening it twice is fine
    clock = [u(2026, 11, 14, 0, 1)]
    bot = Bot(env["ch"], store=store, pool=env["bot"].pool, clock=lambda: clock[0])
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    assert bot.tick() == 1 and store.rules("+15550001")[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"


def test_an_error_after_the_rule_moved_on_never_sends_twice(env):
    """Defect (a): an exception after the rule was advanced (here, after the message went out) used to retry the slot
    in 15 minutes, which sent it a second time."""
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    weekly(bot, st)
    real_x = bot.store.x

    def failing_x(sql, args=()):
        if sql.startswith("UPDATE runs SET status=? WHERE id=?"):
            raise sqlite3.OperationalError("disk I/O error")
        return real_x(sql, args)
    bot.store.x = failing_x
    clock[0] = u(2026, 11, 14, 0, 1)
    n = len(ch.outbox)
    assert bot.tick() == 0 and len(ch.outbox) == n + 1                   # it went out, then the error
    bot.store.x = real_x
    for minutes in (16, 31, 46):
        clock[0] = u(2026, 11, 14, 0, 1) + timedelta(minutes=minutes)
        bot.tick()
    assert len(ch.outbox) == n + 1                                       # never a second time
    assert bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"
    assert statuses(bot) == ["unknown", "error"]
    # an error before the rule moved on is still retried, for the same slot
    real_run = bot.run
    bot.run = lambda *a, **k: (_ for _ in ()).throw(KeyError("boom"))
    clock[0] = u(2026, 11, 21, 0, 1)
    assert bot.tick() == 0 and bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-21T00:16:00+00:00"
    bot.run = real_run
    clock[0] = u(2026, 11, 21, 0, 17)
    assert bot.tick() == 1 and bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-28T00:00:00+00:00"


def test_a_retry_held_for_quiet_hours_is_sent_not_missed(env):
    """Defect (b): a retry that falls in quiet hours waits for their end, and lateness counts from then."""
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    rule = weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "21:50"})
    assert rule["next_run_at"] == "2026-11-13T02:50:00+00:00"            # 9:50pm in New York
    st["answers"]["mvp_compose"] = lambda u_: (_ for _ in ()).throw(RuntimeError("model down"))
    clock[0] = u(2026, 11, 13, 2, 51)
    assert bot.tick() == 0
    clock[0] = u(2026, 11, 13, 3, 6)                                     # the retry, at 10:06pm: quiet hours
    assert bot.tick() == 0
    assert bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-13T13:00:00+00:00"   # held to 8am
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    clock[0] = u(2026, 11, 13, 13, 1)
    n = len(ch.outbox)
    assert bot.tick() == 1 and len(ch.outbox) == n + 1
    assert "missed" not in statuses(bot) and statuses(bot)[-1] == "sent"
    assert bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-14T02:50:00+00:00"   # the next day as usual


def test_daily_limit_holds_a_one_time_send_and_skips_a_repeating_one(env):
    """Defect (b), the daily limit: a one-time send the person asked for goes out the next morning; a repeating
    rule's slot is skipped and recorded as daily_limit (never a silent 'missed')."""
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "new_rule", "spec": pasta_spec({"type": "once", "in_minutes": 120})}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    bot.on_message(h, "in two hours send me pasta")
    for i in range(5):                                                   # five timed sends already went out today
        bot.store.add_run(handle=h, rule_id=None, kind="scheduled", status="sent", at=f"2026-11-12T1{i}:00:00+00:00")
    clock[0] = u(2026, 11, 12, 20, 1)
    n = len(ch.outbox)
    assert bot.tick() == 0 and len(ch.outbox) == n
    once = bot.store.rules(h)[0]
    assert once["next_run_at"] == "2026-11-13T13:00:00+00:00" and once["status"] == "active"   # 8am tomorrow
    clock[0] = u(2026, 11, 13, 13, 1)
    assert bot.tick() == 1 and statuses(bot)[-1] == "sent"
    assert bot.store.rule(once["id"])["status"] == "done"
    rule = weekly(bot, st)
    for i in range(5):
        bot.store.add_run(handle=h, rule_id=None, kind="scheduled", status="sent", at=f"2026-11-13T2{i}:00:00+00:00")
    bot.store.set_state(f"last_in:{h}", "2026-11-13T23:59:00+00:00")   # they wrote back: not an unanswered stream
    clock[0] = u(2026, 11, 14, 0, 1)
    assert bot.tick() == 0 and statuses(bot)[-1] == "daily_limit"
    assert bot.store.rule(rule["id"])["next_run_at"] == "2026-11-21T00:00:00+00:00"


def test_named_times_are_honoured_in_quiet_hours_but_random_moments_wait(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "23:00"})
    clock[0] = u(2026, 11, 13, 4, 0, 30)                                 # 11pm, inside 22:00 to 08:00
    assert bot.tick() == 1                                               # the time they named is kept
    bot.store.x("UPDATE rules SET status='stopped'")
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "new_rule", "spec": pasta_spec({"type": "random", "per": "day"})}
    bot.on_message(h, "pasta at random once a day")
    bot.on_message(h, "yes")
    assert "First one" not in last(ch)                                   # random moments are never shown in advance
    r = bot.store.rules(h, statuses=("active",))[0]
    slot = datetime.fromisoformat(r["next_run_at"])
    from mvp.schedule import next_run
    from mvp.schema import When
    assert slot == next_run(When(type="random", per="day"), NY, ANCHOR, anchor=datetime.fromisoformat(r["created_at"]),
                            seed=r["id"])                                # seeded with the rule's id: stable
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "list_rules"}
    bot.on_message(h, "my rules")
    assert "once a day at a random time" in last(ch) and "next:" not in last(ch)
    # the person makes the hour around that moment quiet; when it comes due it waits for the end of the block
    loc = local(slot)
    start, end = (loc - timedelta(minutes=30)).strftime("%H:%M"), (loc + timedelta(minutes=30)).strftime("%H:%M")
    bot.store.set_quiet(h, [{"start": "22:00", "end": "08:00"}, {"start": start, "end": end}])
    clock[0] = slot + timedelta(seconds=30)
    assert bot.tick() == 0
    release = datetime.fromisoformat(bot.store.rules(h, statuses=("active",))[0]["next_run_at"])
    assert local(release).strftime("%H:%M") == end
    clock[0] = release + timedelta(seconds=30)
    assert bot.tick() == 1 and statuses(bot)[-1] == "sent"


def test_snooze_skips_timed_sends_and_asking_still_works(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    rule = weekly(bot, st)
    bot.store.set_snooze(h, u(2026, 11, 16, 5))                           # "I'm away until Monday"
    clock[0] = u(2026, 11, 14, 0, 1)
    n = len(ch.outbox)
    assert bot.tick() == 0 and len(ch.outbox) == n and statuses(bot) == ["snoozed"]
    assert bot.store.rule(rule["id"])["next_run_at"] == "2026-11-21T00:00:00+00:00"
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    bot.on_message(h, "pasta now?")
    assert "example.com" in last(ch)
    clock[0] = u(2026, 11, 21, 0, 1)
    assert bot.tick() == 1
    bot.store.set_snooze(h, None)
    assert bot.store.person(h)["snooze_until"] is None


def test_pause_until_resumes_by_itself(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    rule = weekly(bot, st)
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "pause", "rule_number": 1, "until": "2026-11-20"}
    bot.on_message(h, "no pasta until the 20th")
    assert "Paused" in last(ch) and "starts again on Friday 20 November" in last(ch)
    r = bot.store.rule(rule["id"])
    assert r["status"] == "paused" and r["paused_until"] == "2026-11-20T05:00:00+00:00"
    clock[0] = u(2026, 11, 14, 0, 1)
    assert bot.tick() == 0 and statuses(bot) == []
    clock[0] = u(2026, 11, 20, 5, 1)
    bot.tick()
    r = bot.store.rule(rule["id"])
    assert r["status"] == "active" and r["paused_until"] is None and r["next_run_at"] == "2026-11-21T00:00:00+00:00"
    clock[0] = u(2026, 11, 21, 0, 1)
    assert bot.tick() == 1
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "pause", "rule_number": 1, "in_minutes": 90}
    bot.on_message(h, "pause it for an hour and a half")
    assert bot.store.rule(rule["id"])["paused_until"] == "2026-11-21T01:31:00+00:00"
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "pause", "rule_number": 1}
    bot.on_message(h, "pause it")                                         # a plain pause has no end
    assert bot.store.rule(rule["id"])["paused_until"] is None


def test_skip_by_count_and_by_date(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    more_pasta(bot)
    rule = weekly(bot, st)
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "skip", "rule_number": 1, "count": 2}
    bot.on_message(h, "skip the next two")
    assert "Skipped the next 2. Next one on Friday 27 November at 7pm" in last(ch)
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "list_rules"}
    bot.on_message(h, "my rules")
    assert "next: on Friday 27 November at 7pm" in last(ch)
    for day in (14, 21, 28):
        clock[0] = u(2026, 11, day, 0, 1)
        bot.tick()
    assert statuses(bot) == ["skipped", "skipped", "sent"]
    bot.store.x("UPDATE rules SET status='stopped' WHERE id=?", (rule["id"],))
    daily = weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "12:00"})
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "skip", "date": "2026-11-30", "until": "2026-12-01"}
    bot.on_message(h, "no pasta on the 30th and the 1st")
    assert "Skipped 30 November to 1 December." in last(ch)
    for day in ((11, 28), (11, 29), (11, 30), (12, 1), (12, 2)):
        clock[0] = u(2026, day[0], day[1], 17, 1)
        bot.tick()
    assert statuses(bot)[-4:] == ["sent", "skipped", "skipped", "sent"]
    assert bot.store.rule(daily["id"])["skip_dates"] == []
    # "send Friday's one now": sent now, and Friday's is skipped
    bot.store.x("UPDATE rules SET status='stopped' WHERE id=?", (daily["id"],))
    fri = weekly(bot, st)
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "run_rule", "rule_number": 1, "skip_next": True}
    bot.on_message(h, "send friday's one now")
    assert "example.com" in last(ch) and bot.store.rule(fri["id"])["skip_count"] == 1


def test_a_temporary_time_zone_switches_back_and_pinned_rules_stay(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    rule = weekly(bot, st)
    pinned = weekly(bot, st, when={"type": "schedule", "days": ["SAT"], "time": "10:00", "tz": "America/New_York"})
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "set_timezone", "timezone": "America/Los_Angeles",
                                                 "until": "2026-11-16"}
    bot.on_message(h, "I'm in LA until Monday")
    assert "switch back to New York time on Monday 16 November" in last(ch)
    p = bot.store.person(h)
    assert p["timezone"] == "America/Los_Angeles" and p["tz_revert_to"] == NY
    assert bot.store.rule(rule["id"])["next_run_at"] == "2026-11-14T03:00:00+00:00"     # 7pm in LA
    assert bot.store.rule(pinned["id"])["next_run_at"] == "2026-11-14T15:00:00+00:00"   # pinned: 10am New York
    clock[0] = u(2026, 11, 14, 3, 1)
    assert bot.tick() == 1
    clock[0] = u(2026, 11, 16, 8, 1)                                     # Monday 00:00 in LA
    bot.tick()
    p = bot.store.person(h)
    assert p["timezone"] == NY and p["tz_revert_at"] is None
    assert bot.store.rule(rule["id"])["next_run_at"] == "2026-11-21T00:00:00+00:00"     # 7pm New York again


def test_until_ends_the_rule_and_says_the_last_one(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    more_pasta(bot)
    rule = weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "12:00", "until": "2026-11-14"})
    clock[0] = u(2026, 11, 13, 17, 1)
    assert bot.tick() == 1 and "last one" not in last(ch)
    clock[0] = u(2026, 11, 14, 17, 1)
    assert bot.tick() == 1 and "That was the last one of this rule." in last(ch)
    assert bot.store.rule(rule["id"])["status"] == "done"


def test_every_hours_preview_says_the_daily_limit_applies(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "new_rule", "spec": pasta_spec(
        {"type": "schedule", "every_hours": 2, "window": ["09:00", "21:00"]})}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    bot.on_message("+15550001", "pasta every 2 hours")
    assert "every 2 hours from 9am to 9pm" in last(ch).lower() and "at most 5 timed messages a day" in last(ch)
    assert bot.store.pending("+15550001")["payload"]["spec"]["when"] == {
        "type": "schedule", "days": DAILY, "every_weeks": 1, "every_hours": 2, "window": ["09:00", "21:00"]}


# ---------- found by the checker ----------

def test_except_dates_never_move_the_cadence():
    """'Every 2 days' and 'every other Friday' keep their rhythm when the first day is excluded."""
    w = W(type="schedule", every_days=2, times=["08:00"], except_dates=["2026-11-13"])
    assert [local(t).date().isoformat() for t in run_of(w, 3)] == ["2026-11-15", "2026-11-17", "2026-11-19"]
    f = W(type="schedule", days=["FRI"], every_weeks=2, times=["19:00"], except_dates=["2026-11-13"])
    assert [local(t).date().isoformat() for t in run_of(f, 2)] == ["2026-11-27", "2026-12-11"]


def test_a_random_period_cut_by_start_or_until_gets_its_share():
    """3 a week that ends on a Wednesday sends about 3 x 3/7 = 1 that week, not 3 squeezed into three days."""
    w = W(type="random", until="2026-11-18")
    moments = run_of(w, 5, after=u(2026, 11, 16, 5), anchor=u(2026, 11, 1))
    assert len(moments) == 1 and local(moments[0]).date().isoformat() <= "2026-11-18"
    s = W(type="random", start="2026-11-21")                              # starts on a Saturday
    sat_sun = [t for t in run_of(s, 6) if local(t).date().isoformat() <= "2026-11-22"]
    assert len(sat_sun) == 1


def test_each_year_without_a_start_names_its_month():
    from mvp.schedule import complete, describe
    w = complete(W(type="schedule", every_months=12, month_days=[3]), ANCHOR, NY)
    assert w.start == "2026-11-12" and describe(w) == "every year on 3 November at 9am"
    assert local(nxt(w)).date().isoformat() == "2027-11-03"


def test_a_skipped_date_covers_every_send_that_day(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    weekly(bot, st, when={"type": "schedule", "times": ["08:00", "20:00"]})
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "skip", "rule_number": 1, "date": "2026-11-14"}
    bot.on_message(h, "not on saturday")
    assert "Skipped Saturday 14 November. Next one today at 8pm" in last(ch)
    for t in [u(2026, 11, 13, 1, 1), u(2026, 11, 13, 13, 1), u(2026, 11, 14, 1, 1), u(2026, 11, 14, 13, 1),
              u(2026, 11, 15, 1, 1), u(2026, 11, 15, 13, 1)]:
        clock[0] = t
        bot.tick()
    got = statuses(bot)                                                  # both Saturday sends are skipped
    assert got[:5] == ["sent", "sent", "sent", "skipped", "skipped"] and got[5] in ("sent", "none_sent")
    # a long run of skipped days does not end the rule, and the reply names the first real send after it
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "skip", "rule_number": 1, "date": "2026-11-15",
                                                  "until": "2027-01-10"}
    bot.on_message(h, "no pasta until 11 January")
    assert "Next one on Monday 11 January at 8am" in last(ch) and bot.store.rules(h)[0]["status"] == "active"


def test_a_hold_or_retry_from_an_earlier_slot_never_applies_to_a_new_one(env):
    """A retry count or a hold belongs to its slot. After the person changes or skips, a stale one must not stop a
    skip from being used or hold a time they named."""
    bot, st, clock = env["bot"], env["state"], env["clock"]
    h = "+15550001"
    weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "21:50"})
    st["answers"]["mvp_compose"] = lambda u_: (_ for _ in ()).throw(RuntimeError("model down"))
    clock[0] = u(2026, 11, 13, 2, 51)
    bot.tick()
    clock[0] = u(2026, 11, 13, 3, 6)
    bot.tick()                                                           # held to 8am
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-13T13:00:00+00:00"
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "change_rule", "rule_number": 1,
                                                  "spec": pasta_spec({"type": "schedule", "days": DAILY, "time": "07:00"})}
    bot.on_message(h, "make it 7am")
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "skip", "rule_number": 1}
    bot.on_message(h, "skip the next one")
    clock[0] = u(2026, 11, 13, 12, 1)                                    # 7:01am, in quiet hours, a time they named
    assert bot.tick() == 0 and statuses(bot)[-1] == "skipped"            # the skip is used, not held to 8am
    clock[0] = u(2026, 11, 14, 12, 1)
    assert bot.tick() == 1                                               # the next 7am goes out at 7am


def test_a_failed_send_is_retried_three_times_then_moves_on(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    weekly(bot, st)
    real, tries = ch.send, []

    def down(*a, **k):
        tries.append(1)
        raise ConnectionError("down")
    ch.send = down
    for i in range(10):
        clock[0] = u(2026, 11, 14, 0, 1) + timedelta(minutes=16 * i)
        bot.tick()
    ch.send = real
    assert len(tries) == 4                                               # the first try and 3 retries, not until 'missed'
    assert bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"


def test_a_rule_paused_until_a_date_stays_paused_while_the_person_is_silent(env):
    from mvp.texts import PAUSED_QUIET
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "12:00"})
    second = weekly(bot, st, when={"type": "schedule", "days": DAILY, "time": "13:00"})
    bot.store.pause_rule(second["id"], u(2026, 11, 22, 0))
    bot.store.set_state(f"last_in:{h}", "2026-11-12T18:30:00+00:00")
    for d in range(14):
        clock[0] = u(2026, 11, 13, 17, 1) + timedelta(days=d)
        bot.tick()
    assert sum(1 for m in ch.outbox if m[2] == PAUSED_QUIET) == 1      # one note, not one more when the date comes
    assert [r["status"] for r in bot.store.rules(h)] == ["paused", "paused"]


def test_hours_that_are_all_quiet_are_said_plainly_before_any_preview(env):
    from mvp import texts as T
    bot, ch, st = env["bot"], env["ch"], env["state"]
    h = "+15550001"
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "verdict": "clear"})
    for when, says in [({"type": "schedule", "window": ["22:30", "23:30"]}, T.ALL_QUIET),
                       ({"type": "random", "window": ["23:00", "23:59"]}, T.ALL_QUIET),
                       ({"type": "schedule", "days": ["MON"], "time": "09:00", "until": "2026-11-01"}, T.TIME_PASSED)]:
        st["answers"]["mvp_interpret"] = lambda u_, w=when: {"intent": "new_rule", "spec": pasta_spec(w)}
        bot.on_message(h, "pasta rule")
        assert last(ch) == says and bot.store.pending(h) is None
    assert env["calls"].count("mvp_compose") == 0 and bot.store.rules(h) == []
    bot.store.set_quiet(h, [])                                            # no quiet hours: a late window is fine
    st["answers"]["mvp_interpret"] = lambda u_: {"intent": "new_rule",
                                                  "spec": pasta_spec({"type": "schedule", "window": ["22:30", "23:30"]})}
    bot.on_message(h, "pasta rule")
    assert "YES" in last(ch)
