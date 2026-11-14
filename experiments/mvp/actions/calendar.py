"""PROTOTYPE ONLY - calendar.add (DESIGN.md sections 6 and 11; the checked research note on outputs, section 2).

One event per answer, never a recurrence rule: a repeating rule with calendar.add adds that send's event at each send.
- A Google Calendar "add event" link (`calendar/render?action=TEMPLATE`), with local wall time and `ctz` (the person's
  zone): no sign-in. It goes out as a part of its own, after one line that says what it adds and when.
- An .ics file (RFC 5545: CRLF, folded at 75 octets, UTC times with Z so no VTIMEZONE is needed, a UID per send),
  written to the outbox and attached when the answer is emailed.
The title is the pick's checked title, or the reminder's own words; a title in `params` is used only when every word of
it is in the person's own request. The description is the link to the post. Default length 30 minutes; with no time it
is an all-day event. The day is `date`, or the day of the send plus `day_offset`; a time already passed today moves to
tomorrow (for a timed send: a time before the moment the send was due), a named day that has passed adds nothing
(and the line says so).
"""
from datetime import date, timedelta, timezone
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from .. import config
from ..schedule import _at, say_time
from .base import Outcome, write_outbox

GOOGLE = "https://calendar.google.com/calendar/render"
UID_DOMAIN = "digest-bot.invalid"


def _title(ctx, params, pick):
    if params.title:
        from ..interpret import own_words
        if ctx.request_text and own_words(params.title, ctx.request_text):
            return params.title
    if pick:
        return pick["title"]
    a = ctx.answer or {}
    if a.get("kind") == "todos":
        return "Your to-do list"
    return (a.get("goal") or "A reminder")[:100]


def event_for(ctx, params):
    """The event as a dict, or None when the day named has already passed."""
    tz = ZoneInfo(ctx.tz)
    now = ctx.now
    today = now.astimezone(tz).date()
    pick = ctx.picks[0] if ctx.picks else None
    named = bool(params.date)
    day = date.fromisoformat(params.date) if named else today + timedelta(days=params.day_offset or 0)
    ev = {"title": _title(ctx, params, pick), "tz": ctx.tz, "url": (pick or {}).get("url"), "all_day": not params.time,
          "uid": f"r{ctx.rule_id or 0}-run{ctx.run_id or 0}-{(pick or {}).get('item_id') or 'note'}@{UID_DOMAIN}"}
    if params.time:
        start = _at(day, params.time, tz)
        # a timed send compares with the moment it was due, so "remind me at 2pm and put it on my calendar" makes
        # today's 2pm event even though the send goes out a few seconds after 2pm (or later, on a retry)
        if start < (ctx.slot_at or now):
            if named:
                return None
            start = _at(day + timedelta(days=1), params.time, tz)
        length = timedelta(minutes=params.duration_min or config.CALENDAR_MINUTES)
        ev["start"], ev["end"] = start, start.astimezone(timezone.utc) + length   # real minutes, across a DST change
        ev["day"] = start.astimezone(tz).date()
    else:
        if day < today:
            return None
        ev["day"] = day
    if ev["url"]:
        ev["details"] = f"From your saves: {ev['url']}" + details_text(pick)
    else:
        ev["details"] = f"A reminder you set with {config.BOT_NAME}."
    return ev


def details_text(pick):
    """The pick's checked details, as the answer shows them (fix pass 2, finding 47: the email body and the calendar
    description carry the same lines)."""
    from ..render import LABEL
    facts = (pick or {}).get("facts") or {}
    out = []
    for kind in ("ingredients", "steps", "key_points"):
        lines = facts.get(kind) or []
        if lines:
            out.append(f"{LABEL[kind]} ({len(lines)}):")
            out += [f"{i}. {x}" if kind == "steps" else f"• {x}" for i, x in enumerate(lines[:20], 1)]
    return ("\n\n" + "\n".join(out)) if out else ""


def google_link(ev):
    """Local wall time plus ctz (never mixed with Z), or a date pair for an all-day event."""
    if ev["all_day"]:
        dates = f"{ev['day']:%Y%m%d}/{ev['day'] + timedelta(days=1):%Y%m%d}"
        q = {"action": "TEMPLATE", "text": ev["title"], "dates": dates}
    else:
        tz = ZoneInfo(ev["tz"])
        a, b = ev["start"].astimezone(tz), ev["end"].astimezone(tz)
        q = {"action": "TEMPLATE", "text": ev["title"], "dates": f"{a:%Y%m%dT%H%M%S}/{b:%Y%m%dT%H%M%S}", "ctz": ev["tz"]}
    q["details"] = ev["details"]
    return GOOGLE + "?" + urlencode(q, quote_via=quote)


def _esc(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line):
    """RFC 5545 3.1: lines longer than 75 octets are folded with CRLF and one space, never inside a UTF-8 character."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics_text(ev, now):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//digest-bot//prototype//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{_utc(now)}"]
    if ev["all_day"]:
        lines += [f"DTSTART;VALUE=DATE:{ev['day']:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{ev['day'] + timedelta(days=1):%Y%m%d}"]
    else:
        lines += [f"DTSTART:{_utc(ev['start'])}", f"DTEND:{_utc(ev['end'])}"]
    lines += [f"SUMMARY:{_esc(ev['title'])}", f"DESCRIPTION:{_esc(ev['details'])}"]
    if ev.get("url"):
        lines.append(f"URL:{ev['url']}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def when_words(ev, now):
    if ev["all_day"]:
        today = now.astimezone(ZoneInfo(ev["tz"])).date()
        days = (ev["day"] - today).days
        day = "today" if days == 0 else "tomorrow" if days == 1 else f"on {ev['day']:%A %-d %B}"
        return f"{day} (all day)"
    return say_time(ev["start"], now, ev["tz"])


def run(ctx, params):
    ev = event_for(ctx, params)
    if ev is None:
        return Outcome("skipped", line="That day has already passed, so I didn't make a calendar entry.")
    when = when_words(ev, ctx.now)
    link = google_link(ev)
    data = ics_text(ev, ctx.now).encode("utf-8")
    path = write_outbox(ctx.handle, "event-" + ev["title"], "ics", data, ctx.now)
    oid = ctx.store.add_outbox(ctx.handle, "calendar", f"{ev['title']}, {when}", path, "file", run_id=ctx.run_id,
                               at=ctx.now)
    # fix pass 2, finding 56: one short line, then the link alone; the test page draws it as a card with the title,
    # the day and time, and the .ics file beside it
    return Outcome("done", line=f"To put \"{ev['title']}\" on your calendar {when}, tap this link:",
                   link={"type": "link", "url": link, "title": f"Add to Google Calendar: {ev['title']}",
                         "platform": "calendar", "event_title": ev["title"], "when": when,
                         "outbox_id": oid},
                   ref=path, attach=[("event.ics", path, "text", "calendar")],
                   email_links=[(f"Add \"{ev['title']}\" to Google Calendar", link)],
                   detail={"title": ev["title"], "when": when, "link": link, "path": path})
