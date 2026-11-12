"""PROTOTYPE ONLY - every date and time is worked out here, in the person's timezone, never by the model."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .schema import DAYS, When


UTC = ZoneInfo("UTC")


def _at(day, hhmm, tz):
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=tz)


def next_run(when: When, tzname: str, after: datetime, anchor: datetime | None = None):
    """The first run strictly after `after` (aware datetime), as an aware UTC datetime; None for 'now' or a past 'once'.
    `anchor` (the rule's creation time) fixes the week parity for every_weeks > 1."""
    tz = ZoneInfo(tzname)
    local = after.astimezone(tz)
    after_utc = after.astimezone(UTC)
    if when.type in ("now", "on_request"):
        return None
    if when.type == "once":
        y, mo, d = map(int, when.date.split("-"))
        t = _at(datetime(y, mo, d), when.time, tz).astimezone(UTC)
        return t if t > after_utc else None
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
        t = _at(day, when.time, tz).astimezone(UTC)
        if t > after_utc:  # compared in UTC: in the repeated hour when clocks go back, local times compare wrongly
            return t
    return None


def resolve_relative(when: When, now: datetime, tzname: str) -> When:
    """'in two hours' (in_minutes) becomes a local date and time here, never in the model."""
    if when.type == "once" and when.in_minutes:
        t = now.astimezone(ZoneInfo(tzname)) + timedelta(minutes=when.in_minutes)
        when.date, when.time, when.in_minutes = t.strftime("%Y-%m-%d"), t.strftime("%H:%M"), None
    return when


def say_time(at: datetime, now: datetime, tzname: str) -> str:
    """'today at 9pm', 'tomorrow at 8am', 'on Friday 13 November at 7pm', in the person's time zone."""
    tz = ZoneInfo(tzname)
    a, n = at.astimezone(tz), now.astimezone(tz)
    clock = a.strftime("%-I:%M%p").lower().replace(":00", "")
    days = (a.date() - n.date()).days
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    return f"on {a.strftime('%A %-d %B')} at {clock}"


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
    if when.type == "on_request":
        return "whenever you ask"
    if when.type == "once":
        if not when.date:
            return f"in {when.in_minutes} minutes"
        y, mo, d = map(int, when.date.split("-"))
        return f"once on {datetime(y, mo, d).strftime('%a %-d %b')} at {t12(when.time)}"
    days, n = when.days, when.every_weeks
    weeks = {1: "", 2: "every other week, "}.get(n, f"every {n} weeks, ")
    if days == ["MON", "TUE", "WED", "THU", "FRI"]:
        d = "every weekday" if n == 1 else weeks + "on weekdays"
    elif len(days) == 7:
        d = "every day" if n == 1 else weeks + "every day"
    else:
        joined = " and ".join(names[x] for x in days)
        d = {1: f"every {joined}", 2: f"every other {joined}"}.get(n, f"every {n} weeks on {joined}")
    return f"{d} at {t12(when.time)}"
