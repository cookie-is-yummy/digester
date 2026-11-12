"""PROTOTYPE ONLY - every date and time is worked out here, in the person's timezone, never by the model."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .schema import DAYS, When


def _at(day, hhmm, tz):
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=tz)


def next_run(when: When, tzname: str, after: datetime, anchor: datetime | None = None):
    """The first run strictly after `after` (aware datetime), as an aware UTC datetime; None for 'now' or a past 'once'.
    `anchor` (the rule's creation time) fixes the week parity for every_weeks > 1."""
    tz = ZoneInfo(tzname)
    local = after.astimezone(tz)
    if when.type == "now":
        return None
    if when.type == "once":
        y, mo, d = map(int, when.date.split("-"))
        t = _at(datetime(y, mo, d), when.time, tz)
        return t.astimezone(ZoneInfo("UTC")) if t > local else None
    wanted = {DAYS.index(d) for d in when.days}
    base = (anchor or after).astimezone(tz).date()
    base_monday = base - timedelta(days=base.weekday())
    for i in range(0, 7 * when.every_weeks + 8):
        day = local.date() + timedelta(days=i)
        if day.weekday() not in wanted:
            continue
        weeks = ((day - timedelta(days=day.weekday())) - base_monday).days // 7
        if weeks % when.every_weeks:
            continue
        t = _at(day, when.time, tz)
        if t > local:
            return t.astimezone(ZoneInfo("UTC"))
    return None


def in_quiet_hours(at_utc: datetime, tzname: str) -> bool:
    h = at_utc.astimezone(ZoneInfo(tzname)).hour
    return h >= config.QUIET_START or h < config.QUIET_END


def rule_time_in_quiet(when: When) -> bool:
    """A rule the person set for a late hour is honoured (BRIEF-10 rule 8)."""
    if not when.time:
        return False
    h = int(when.time[:2])
    return h >= config.QUIET_START or h < config.QUIET_END


def end_of_quiet(at_utc: datetime, tzname: str) -> datetime:
    tz = ZoneInfo(tzname)
    local = at_utc.astimezone(tz)
    day = local.date() if local.hour < config.QUIET_END else local.date() + timedelta(days=1)
    return _at(day, f"{config.QUIET_END:02d}:00", tz).astimezone(ZoneInfo("UTC"))


def describe(when: When) -> str:
    """'every Friday at 7pm' for previews and the rules list."""
    names = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday",
             "SAT": "Saturday", "SUN": "Sunday"}

    def t12(hhmm):
        h, m = map(int, hhmm.split(":"))
        suffix = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}{suffix}" if m == 0 else f"{h12}:{m:02d}{suffix}"
    if when.type == "now":
        return "now"
    if when.type == "once":
        return f"on {when.date} at {t12(when.time)}"
    days = when.days
    if days == ["MON", "TUE", "WED", "THU", "FRI"]:
        d = "every weekday"
    elif len(days) == 7:
        d = "every day"
    else:
        joined = " and ".join(names[x] for x in days)
        d = {1: f"every {joined}", 2: f"every other {joined}"}.get(when.every_weeks, f"every {when.every_weeks} weeks on {joined}")
    return f"{d} at {t12(when.time)}"
