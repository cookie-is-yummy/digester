"""PROTOTYPE ONLY - every date and time is worked out here, never by the model (DESIGN.md sections 1 and 11).

`next_run` is the single place where send moments are computed. Clock times are read in the rule's pinned zone
(`when.tz`) or the person's zone, and every comparison is made in UTC (local times compare wrongly in the repeated hour
when clocks go back). Quiet hours belong to the person and are read in the person's zone.

Random moments and window moments come from a generator seeded with the rule's id and the period, so they are the same
after a restart and in tests. Random moments, window moments and every_hours moments never fall inside quiet hours
(windows are clipped to waking hours); a clock time the person named is kept even inside quiet hours.
"""
import hashlib
import random
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .schema import DAYS, RANDOM_WINDOW, When, minutes, quiet_blocks

UTC = ZoneInfo("UTC")
HORIZON_DAYS = 800            # how far ahead a schedule is searched (every 12 months, a fifth Monday)
RANDOM_PERIODS = 120          # how many days, weeks or months ahead a random rule is searched

# Defaults the interpreter uses, shown in the preview through describe()
TIMES_A_DAY = {1: ["09:00"], 2: ["08:00", "20:00"], 3: ["08:00", "13:00", "19:00"], 4: ["08:00", "13:00", "16:00", "19:00"]}
A_COUPLE, A_FEW = 2, 3        # "a couple of times a week" and "a few times a week" (random)


def times_a_day(n):
    """'twice a day' is 08:00 and 20:00; three times 08:00, 13:00, 19:00; four adds 16:00."""
    return list(TIMES_A_DAY[max(1, min(4, int(n)))])


def _at(day, hhmm, tz):
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=tz)


def _utc(dt):
    return dt.astimezone(UTC)


def _rng(seed, key):
    """A generator that gives the same numbers for the same rule and period in every process."""
    digest = hashlib.sha256(f"{seed}|{key}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# ---------- quiet hours ----------
def _blocks(quiet):
    return quiet_blocks(quiet)


def quiet_intervals(quiet, tzname, lo, hi):
    """The person's quiet hours as merged UTC intervals that overlap [lo, hi)."""
    tz = ZoneInfo(tzname)
    out = []
    d, last = lo.astimezone(tz).date() - timedelta(days=1), hi.astimezone(tz).date()
    while d <= last:
        for b in _blocks(quiet):
            if b.days and DAYS[d.weekday()] not in b.days:
                continue
            s = _at(d, b.start, tz)
            e = _at(d if minutes(b.end) > minutes(b.start) else d + timedelta(days=1), b.end, tz)
            s, e = _utc(s), _utc(e)
            if e > lo and s < hi:
                out.append((s, e))
        d += timedelta(days=1)
    out.sort()
    merged = []
    for s, e in out:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def in_quiet_hours(at_utc, tzname, quiet=None):
    at_utc = _utc(at_utc)
    return any(s <= at_utc < e for s, e in quiet_intervals(quiet, tzname, at_utc - timedelta(minutes=1),
                                                            at_utc + timedelta(minutes=1)))


def end_of_quiet(at_utc, tzname, quiet=None):
    """The first moment at or after at_utc that is outside every quiet block."""
    t = _utc(at_utc)
    for _ in range(12):
        ivs = [iv for iv in quiet_intervals(quiet, tzname, t - timedelta(minutes=1), t + timedelta(days=2))
               if iv[0] <= t < iv[1]]
        if not ivs:
            return t
        t = max(e for _, e in ivs)
    return t


def _free(lo, hi, quiet, tzname):
    """[lo, hi) minus quiet hours, as UTC intervals."""
    out, cur = [], lo
    for s, e in quiet_intervals(quiet, tzname, lo, hi):
        if s > cur:
            out.append((cur, min(s, hi)))
        cur = max(cur, e)
        if cur >= hi:
            break
    if cur < hi:
        out.append((cur, hi))
    return [(a, b) for a, b in out if b > a]


def _pick_in(intervals, rng, n=1):
    """n moments spread over the intervals (one inside each of n equal shares, so they never bunch up), whole minutes."""
    spans = []
    for a, b in intervals:
        whole = a.replace(second=0, microsecond=0)
        a = whole if whole == a else whole + timedelta(minutes=1)
        length = int((b - a).total_seconds() // 60)
        if length > 0:
            spans.append((a, length))
    total = sum(length for _, length in spans)
    if total <= 0 or n <= 0:
        return []
    out = []
    for i in range(n):
        u = int((i + 0.1 + 0.8 * rng.random()) * total / n)
        for a, length in spans:
            if u < length:
                out.append(a + timedelta(minutes=u))
                break
            u -= length
    return out


# ---------- which days a rule sends on ----------
def _in_span(when, d):
    """d is between start and until (both inclusive)."""
    if when.start and d < date.fromisoformat(when.start):
        return False
    return not (when.until and d > date.fromisoformat(when.until))


def _limits_ok(when, d):
    return _in_span(when, d) and d.isoformat() not in when.except_dates


def _month_set(when, y, m, anchor_day):
    """The days of month (y, m) a monthly rule sends on."""
    last = (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).day
    out = set()
    if when.month_weeks:
        wanted = [DAYS.index(x) for x in when.days]
        for w in when.month_weeks:
            for wd in wanted:
                days = [d for d in range(1, last + 1) if date(y, m, d).weekday() == wd]
                if w == -1:
                    out.add(days[-1])
                elif w <= len(days):
                    out.add(days[w - 1])   # a fifth Monday that does not exist is skipped
    else:
        for md in when.month_days or [anchor_day]:
            out.add(last if md == -1 else min(md, last))   # a day past the month's end means the last day
    return out


def _weekly_days(when, anchor_local):
    return {DAYS.index(x) for x in when.days} if when.days else {anchor_local.weekday()}


def counts_from_a_day(when):
    """True for the cadences counted from a first day: every N days, every N weeks (N > 1)."""
    return when.type == "schedule" and bool(when.every_days or (not (when.month_days or when.month_weeks or
                                                                     when.every_months) and (when.every_weeks or 1) > 1))


def _base_day(when, anchor_local, day_moments):
    """The first day an every-N-days or every-N-weeks rule counts from: `start` for every N days, else the first
    matching day after creation (or `start`) with a send moment after creation."""
    start = date.fromisoformat(when.start) if when.start else None
    if when.every_days and start:
        return start
    base_from = max(anchor_local.date(), start) if start else anchor_local.date()
    wanted = None if when.every_days else _weekly_days(when, anchor_local)
    for i in range(HORIZON_DAYS):
        d = base_from + timedelta(days=i)
        # except_dates remove sends; they never move the cadence ("every other Friday, but not the 13th")
        if (wanted is None or d.weekday() in wanted) and _in_span(when, d) \
                and any(m > anchor_local for m in day_moments(d)):
            return d
    return None


def base_day(when, tzname, anchor, seed=None, quiet=None):
    """The day the cadence counts from, worked out in zone `tzname` (ISO date or None). Kept by the scheduler when the
    person's zone changes, so the count never starts again from a new day (review fix S2)."""
    if not counts_from_a_day(when):
        return None
    tz = ZoneInfo(when.tz or tzname)
    seed = "preview" if seed is None else seed
    d = _base_day(when, anchor.astimezone(tz), lambda x: _day_moments(when, tz, x, seed, quiet, tzname))
    return d.isoformat() if d else None


def _cadence(when, tz, anchor_local, day_moments, base=None):
    """A test day -> bool for a schedule. Rules that repeat every N weeks or N days start on the first matching day
    after creation (or `start`); every N months counts from the month of creation (or of `start`). `anchor_local` is
    the creation moment, and day_moments(d) the send moments of a day. `base` (a date) is that first day when it was
    kept from before a time zone change."""
    start = date.fromisoformat(when.start) if when.start else None
    if when.every_days:
        day0 = base or _base_day(when, anchor_local, day_moments)
        return lambda d: day0 is not None and d >= day0 and (d - day0).days % when.every_days == 0
    if when.month_days or when.month_weeks or when.every_months:
        anchor_day = date.fromisoformat(when.start).day if start else anchor_local.day
        if anchor_day >= 31:
            anchor_day = -1

        def in_month(d):
            return d.day in _month_set(when, d.year, d.month, anchor_day)
        n = when.every_months or 1
        if n == 1:
            return in_month
        base = start or anchor_local.date()   # "every 6 months" counts months from the month it was made (or start)
        return lambda d: in_month(d) and ((d.year - base.year) * 12 + d.month - base.month) % n == 0
    wanted = _weekly_days(when, anchor_local)
    n = when.every_weeks or 1
    if n == 1:
        return lambda d: d.weekday() in wanted
    base = base or _base_day(when, anchor_local, day_moments)
    if base is None:
        return lambda d: False
    base_monday = base - timedelta(days=base.weekday())
    return lambda d: d.weekday() in wanted and ((d - timedelta(days=d.weekday()) - base_monday).days // 7) % n == 0


def _day_moments(when, tz, d, seed, quiet, ptz):
    """The send moments of one schedule day, as aware datetimes in the rule's zone."""
    if when.times:
        return [_at(d, t, tz) for t in when.times]
    lo, hi = _utc(_at(d, when.window[0], tz)), _utc(_at(d, when.window[1], tz))
    if when.every_hours:
        out = []
        m, end = minutes(when.window[0]), minutes(when.window[1])
        while m <= end:
            t = _at(d, f"{m // 60:02d}:{m % 60:02d}", tz)
            if not in_quiet_hours(t, ptz, quiet):
                out.append(t)
            m += when.every_hours * 60
        return out
    picked = _pick_in(_free(lo, hi, quiet, ptz), _rng(seed, f"window:{d.isoformat()}"))
    return [p.astimezone(tz) for p in picked]


# ---------- the next send ----------
def next_run(when: When, tzname: str, after: datetime, anchor: datetime | None = None, seed=None, quiet=None,
             base=None):
    """The first send strictly after `after` (aware), as an aware UTC datetime; None for now, on_request, new_items,
    a past once, or a rule whose until has passed.
    tzname: the person's zone (quiet hours are read in it); the rule's clock is `when.tz` or this zone.
    anchor: when the rule was made; repeats counted from creation start there, and random moments for the period it
    falls in are drawn only from what is left of that period. seed: the rule's id (random and window moments).
    quiet: the person's quiet blocks (None = the default 22:00 to 08:00). base: the day an every-N cadence counts
    from (ISO date), kept from before a time zone change; None works it out from the anchor."""
    tz = ZoneInfo(when.tz or tzname)
    after_utc = _utc(after)
    if when.type in ("now", "on_request", "new_items"):
        return None
    if when.type == "once":
        if not when.date or not when.times:
            return None
        t = _utc(_at(date.fromisoformat(when.date), when.times[0], tz))
        return t if t > after_utc else None
    anchor_local = (anchor or after).astimezone(tz)
    seed = "preview" if seed is None else seed
    if when.type == "random":
        return _next_random(when, tz, tzname, after_utc, anchor_local, seed, quiet)

    def moments(d):
        return _day_moments(when, tz, d, seed, quiet, tzname)
    matches = _cadence(when, tz, anchor_local, moments, date.fromisoformat(base) if base else None)
    first = after_utc.astimezone(tz).date()
    if when.start:
        first = max(first, date.fromisoformat(when.start))
    for i in range(HORIZON_DAYS):
        d = first + timedelta(days=i)
        if when.until and d > date.fromisoformat(when.until):
            return None
        if not _limits_ok(when, d) or not matches(d):
            continue
        for m in sorted(_utc(x) for x in moments(d)):
            if m > after_utc:
                return m
    return None


def _period(per, d):
    """(first day, last day, key) of the day, week or month that holds d."""
    if per == "day":
        return d, d, d.isoformat()
    if per == "week":
        mon = d - timedelta(days=d.weekday())
        return mon, mon + timedelta(days=6), "w" + mon.isoformat()
    first = d.replace(day=1)
    nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1), "m" + first.isoformat()[:7]


def random_moments(when, tzname, d, anchor, seed, quiet=None):
    """All the random moments of the period that holds local day d (UTC, sorted). The number per full period is
    `count`; in the period the rule was made in, it is scaled to the share of the period that was left, and the
    moments are drawn only from that part."""
    tz = ZoneInfo(when.tz or tzname)
    a, b, key = _period(when.per, d)
    window = when.window or RANDOM_WINDOW
    wanted = {DAYS.index(x) for x in when.days} if when.days else set(range(7))
    full, left = [], []
    anchor_utc = _utc(anchor)
    day = a
    while day <= b:
        if day.weekday() in wanted:
            # the full period counts every allowed day, so a period cut short by start, until or except_dates gets
            # its share of `count`, not all of it squeezed into the days that are left
            for s, e in _free(_utc(_at(day, window[0], tz)), _utc(_at(day, window[1], tz)), quiet, tzname):
                full.append((s, e))
                if e > anchor_utc and _limits_ok(when, day):
                    left.append((max(s, anchor_utc), e))
        day += timedelta(days=1)
    full_len = sum((e - s).total_seconds() for s, e in full)
    left_len = sum((e - s).total_seconds() for s, e in left)
    if full_len <= 0 or left_len <= 0:
        return []
    n = when.count if left_len >= full_len else int(when.count * left_len / full_len + 0.5)
    return sorted(_pick_in(left, _rng(seed, key), n))


def _next_random(when, tz, tzname, after_utc, anchor_local, seed, quiet):
    d = max(after_utc.astimezone(tz).date(), anchor_local.date())
    if when.start:
        d = max(d, date.fromisoformat(when.start))
    week0 = anchor_local.date() - timedelta(days=anchor_local.weekday())
    for _ in range(RANDOM_PERIODS * (when.every_weeks or 1)):
        a, b, _key = _period(when.per, d)
        if when.until and a > date.fromisoformat(when.until):
            return None
        if (when.every_weeks or 1) > 1 and ((a - week0).days // 7) % when.every_weeks:
            d = b + timedelta(days=1)   # "every other week": only the weeks counted from the week it was made
            continue
        for m in random_moments(when, tzname, d, anchor_local, seed, quiet):
            if m > after_utc:
                return m
        d = b + timedelta(days=1)
    return None


# ---------- code-side completion ----------
def resolve_relative(when: When, now: datetime, tzname: str) -> When:
    """'in two hours' (in_minutes) becomes a local date and time here, never in the model. in_minutes stays on the
    object as the record of what was asked; RuleSpec.stored() keeps only the moment."""
    if when.type == "once" and when.in_minutes and not when.date:
        t = now.astimezone(ZoneInfo(when.tz or tzname)) + timedelta(minutes=when.in_minutes)
        when.date, when.times = t.strftime("%Y-%m-%d"), [t.strftime("%H:%M")]
    return when


def complete(when: When, now: datetime, tzname: str) -> When:
    """Fills what the person left to 'today': 'every 3 weeks' with no day is today's weekday; 'once a month' or
    'every 6 months' with no day is today's day of the month (or start's). Stored this way, the rule never drifts."""
    resolve_relative(when, now, tzname)
    if when.type != "schedule":
        return when
    ref = date.fromisoformat(when.start) if when.start else now.astimezone(ZoneInfo(when.tz or tzname)).date()
    if when.every_weeks and not when.days and not when.month_weeks:
        when.days = [DAYS[ref.weekday()]]
    if when.every_months and not when.month_days and not when.month_weeks:
        when.month_days = [-1 if ref.day == 31 else ref.day]
    if when.every_months == 12 and not when.start:
        when.start = ref.isoformat()   # "every year on the 3rd" counts from this month; describe can name the month
    return when


def resolve_until(until, in_minutes, now: datetime, tzname: str):
    """'until the 20th' (a local date: the start of that day), 'until 6pm Friday' (a local date and time) or 'for two
    hours' (in_minutes) as an aware UTC datetime; None when neither is given."""
    if in_minutes:
        return _utc(now) + timedelta(minutes=in_minutes)
    if not until:
        return None
    tz = ZoneInfo(tzname)
    if len(until) <= 10:
        return _utc(_at(date.fromisoformat(until), "00:00", tz))
    dt = datetime.fromisoformat(until)
    return _utc(dt.replace(tzinfo=tz))


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


# ---------- describe ----------
NAMES = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday",
         "SAT": "Saturday", "SUN": "Sunday"}
WEEKDAYS = DAYS[:5]
HOW_OFTEN = {1: "once", 2: "twice", 3: "three times", 4: "four times"}
ORDINAL_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", -1: "last"}


def t12(hhmm):
    h, m = map(int, hhmm.split(":"))
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    if (h, m) == (12, 0):
        return "noon"
    return f"{h12}{suffix}" if m == 0 else f"{h12}:{m:02d}{suffix}"


def _join(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _ordinal(n):
    if n == -1:
        return "last day"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _day_month(iso):
    return date.fromisoformat(iso).strftime("%-d %B")


def _days_phrase(days):
    if days == DAYS:
        return "every day"
    if days == WEEKDAYS:
        return "every weekday"
    if len(days) == 6:
        return "every day except " + NAMES[next(d for d in DAYS if d not in days)]
    return "every " + _join(NAMES[d] for d in days)


def _on_days(days):
    """For random rules: 'on weekdays', 'on Mondays and Fridays'."""
    if not days or days == DAYS:
        return ""
    if days == WEEKDAYS:
        return " on weekdays"
    if days == ["SAT", "SUN"]:
        return " on weekends"
    return " on " + _join(NAMES[d] + "s" for d in days)


def _at_times(when):
    if when.window and when.every_hours:
        every = "every hour" if when.every_hours == 1 else f"every {when.every_hours} hours"
        return f"{every} from {t12(when.window[0])} to {t12(when.window[1])}"
    if when.window:
        return f"at a random time between {t12(when.window[0])} and {t12(when.window[1])}"  # finding 66
    return "at " + _join(t12(t) for t in when.times)


def describe(when: When) -> str:
    """How a rule's timing reads in previews and the rules list: 'every Friday at 7pm', 'every 2 days at 8am',
    'on the 1st and 15th at 9am', 'about 3 times a week at random times', 'twice a day, at 8am and 8pm, until
    24 December'."""
    if when.type == "now":
        return "now"
    if when.type == "on_request":
        return "whenever you ask"
    if when.type == "new_items":
        core = "whenever you save something new that fits"
    elif when.type == "once":
        if not when.date:
            return f"in {when.in_minutes} minutes"
        return f"once on {date.fromisoformat(when.date).strftime('%a %-d %b')} at {t12(when.times[0])}" + _zone(when)
    elif when.type == "random":
        per = when.per or "week"
        window = when.window or RANDOM_WINDOW
        between = "" if window == RANDOM_WINDOW else f" between {t12(window[0])} and {t12(window[1])}"
        every = f"a {per}"
        if (when.every_weeks or 1) > 1:
            every = "every other week" if when.every_weeks == 2 else f"every {when.every_weeks} weeks"
        if when.count == 1:
            core = f"once {every} at a random time{between}"
        else:
            core = f"about {when.count} times {every} at random times{between}"
        core += _on_days(when.days) + _zone(when)
    else:
        core = _schedule_phrase(when) + _zone(when)
    return core + _limits(when)


def _zone(when):
    return f" {when.tz.split('/')[-1].replace('_', ' ')} time" if when.tz else ""


def _schedule_phrase(when):
    at = _at_times(when)
    if when.every_days:
        return f"every {when.every_days} days {at}"
    if when.month_days or when.month_weeks or when.every_months:
        n = when.every_months or 1
        if when.month_weeks:
            which = _join(ORDINAL_WORDS[w] for w in when.month_weeks)
            day = _join(NAMES[d] for d in when.days)
            if n == 1:
                return f"on the {which} {day} of every month {at}"
            return f"every {n} months, on the {which} {day} {at}"
        mds = when.month_days or []
        if n == 12 and when.start and len(mds) == 1 and mds[0] > 0:
            month = date.fromisoformat(when.start).strftime("%B")
            return f"every year on {mds[0]} {month} {at}"
        if not mds:
            return f"every {n} months {at}" if n > 1 else f"every month {at}"
        days = _join(_ordinal(d) for d in mds)
        if mds == [-1]:
            days = "last day of the month"
        elif -1 in mds:
            days = _join([_ordinal(d) for d in mds if d != -1] + ["the last day of the month"])
        if n > 1:
            return f"every {n} months on the {days} {at}"
        return f"on the {days} {at}" if len(mds) > 1 or mds == [-1] else f"on the {days} of every month {at}"
    n = when.every_weeks or 1
    days = when.days
    if when.every_hours and n == 1 and days:
        return at if days == DAYS else f"{_days_phrase(days)}, {at}"
    if not days:
        return f"every {n} weeks {at}" if n > 1 else f"every week {at}"
    if n == 1:
        if days == DAYS and when.times and len(when.times) > 1:
            return f"{HOW_OFTEN[len(when.times)]} a day, {at}"
        return f"{_days_phrase(days)} {at}"
    if n == 2:
        if days in (DAYS, WEEKDAYS):
            return f"every other week, {'every day' if days == DAYS else 'on weekdays'} {at}"
        return f"every other {_join(NAMES[d] for d in days)} {at}"
    if days in (DAYS, WEEKDAYS):
        return f"every {n} weeks, {'every day' if days == DAYS else 'on weekdays'} {at}"
    return f"every {n} weeks on {_join(NAMES[d] for d in days)} {at}"


def _limits(when):
    out = ""
    yearly = when.every_months == 12 and len(when.month_days) == 1 and when.month_days[0] > 0
    if when.start and not yearly:   # "every year on 3 March" already names the start
        out += f", starting {_day_month(when.start)}"
    if when.except_dates:
        out += ", except on " + _join(_day_month(d) for d in when.except_dates[:4]) + \
               (f" and {len(when.except_dates) - 4} more days" if len(when.except_dates) > 4 else "")
    if when.until:
        out += f", until {_day_month(when.until)}"
    if when.max_sends:
        out += ", just once" if when.max_sends == 1 else f", {when.max_sends} times in all"
    return out
