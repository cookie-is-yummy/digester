"""PROTOTYPE ONLY - Apple Reminders and Calendar on the operator's Mac, through AppleScript (round 9, C3; DESIGN.md
section 16.D; amendment A-014, Proposed).

Two actions in the registry use this module: `mac.reminder` (reminders in a Reminders list) and `mac.event` (one event
in the "Digest" calendar). Both are for the operator only, never named by the model, and run only with the yes token of
the exact rows the person was shown (places.py makes the preview and the token; actions.perform checks it).

How a script runs (copied from channels/imessage_mac.py): `osascript -e SCRIPT value1 value2 ...`. Every value (a
title, a note, a list name, a date number, an id) is an argument; no value is ever pasted into a script, so a title
with quotes, backslashes or "& quit" is only ever text. Dates go as separate numbers, and each script sets the day to 1
before it sets the month, so 31 January plus a month never rolls over into March. Times are the person's local wall
time; the Mac uses its own zone (the operator's Mac is in the operator's zone).

Errors keep only a code, never the script's output or its arguments: "blocked" (macOS error -1743, the Automation
permission was refused), "timeout" (no answer in 20 seconds, or AppleEvent timeout -1712), "unreachable" (not on a Mac,
or no osascript), "no_calendar" (no calendar called "Digest"), "failed" (anything else). Every AppleScript detail here
is medium confidence until it is tried on the founder's Mac; the tests use a fake runner.
"""
import json
import re
import shutil
import subprocess
import sys

from ..connectors import ConnectorError
from .base import Outcome

TIMEOUT = 20
CALENDAR = "Digest"          # the calendar events go to (the operator makes it in iCloud, so it reaches the phone)
RUNNER = None                # tests (and a trial) set a runner(script, argv, timeout) -> (returncode, stdout, stderr)

# ---------- the scripts: values only through argv ----------
# argv: list name ("" = the default list), how many reminders, then 8 values per reminder: title, notes, has a due
# date ("1"/"0"), year, month, day, hour, minute. Returns "<made the list 1/0>\t<list id>" and one reminder id a line.
REMINDERS_ADD = """
on run argv
    set listName to item 1 of argv
    set n to (item 2 of argv) as integer
    tell application "Reminders"
        set made to "0"
        if listName is "" then
            set theList to default list
        else if exists list listName then
            set theList to list listName
        else
            set theList to make new list with properties {name:listName}
            set made to "1"
        end if
        set out to made & tab & (id of theList)
        repeat with i from 0 to (n - 1)
            set b to 3 + i * 8
            set props to {name:(item b of argv)}
            if (item (b + 1) of argv) is not "" then set props to props & {body:(item (b + 1) of argv)}
            set r to make new reminder at end of theList with properties props
            if (item (b + 2) of argv) is "1" then
                set d to current date
                set day of d to 1
                set year of d to (item (b + 3) of argv) as integer
                set month of d to (item (b + 4) of argv) as integer
                set day of d to (item (b + 5) of argv) as integer
                set hours of d to (item (b + 6) of argv) as integer
                set minutes of d to (item (b + 7) of argv) as integer
                set seconds of d to 0
                set due date of r to d
                set remind me date of r to d
            end if
            set out to out & linefeed & (id of r)
        end repeat
    end tell
    return out
end run
"""
# argv: pairs of kind ("reminder" or "list") and id. A list is deleted only when it is empty. Returns one line per
# pair: "ok", "missing" (already gone) or "failed", a tab, the id.
REMINDERS_DELETE = """
on run argv
    set out to ""
    tell application "Reminders"
        repeat with i from 1 to (count of argv) by 2
            set k to item i of argv
            set theId to item (i + 1) of argv
            try
                if k is "list" then
                    set L to list id theId
                    if (count of reminders of L) is 0 then delete L
                else
                    delete reminder id theId
                end if
                set out to out & "ok" & tab & theId & linefeed
            on error errMsg number errNum
                if errNum is -1728 or errNum is -1719 then
                    set out to out & "missing" & tab & theId & linefeed
                else
                    set out to out & "failed" & tab & theId & linefeed
                end if
            end try
        end repeat
    end tell
    return out
end run
"""
REMINDERS_CHECK = """
on run argv
    tell application "Reminders"
        return (count of lists) as text
    end tell
end run
"""
# argv: calendar name, title, notes, all day ("1"/"0"), start year, month, day, hour, minute, end year, month, day,
# hour, minute. Returns the new event's uid, or NO_CALENDAR.
CALENDAR_ADD = """
on mkdate(y, mo, d, h, mi)
    set t to current date
    set day of t to 1
    set year of t to y as integer
    set month of t to mo as integer
    set day of t to d as integer
    set hours of t to h as integer
    set minutes of t to mi as integer
    set seconds of t to 0
    return t
end mkdate

on run argv
    set calName to item 1 of argv
    set s to my mkdate(item 5 of argv, item 6 of argv, item 7 of argv, item 8 of argv, item 9 of argv)
    set e to my mkdate(item 10 of argv, item 11 of argv, item 12 of argv, item 13 of argv, item 14 of argv)
    tell application "Calendar"
        if not (exists calendar calName) then return "NO_CALENDAR"
        set theCal to calendar calName
        set props to {summary:(item 2 of argv), start date:s, end date:e}
        if (item 4 of argv) is "1" then set props to props & {allday event:true}
        if (item 3 of argv) is not "" then set props to props & {description:(item 3 of argv)}
        set ev to make new event at end of events of theCal with properties props
        return uid of ev
    end tell
end run
"""
# argv: calendar name, then uids. Returns one line per uid, as REMINDERS_DELETE.
CALENDAR_DELETE = """
on run argv
    set out to ""
    tell application "Calendar"
        set theCal to calendar (item 1 of argv)
        repeat with i from 2 to (count of argv)
            set u to item i of argv
            try
                delete (first event of theCal whose uid is u)
                set out to out & "ok" & tab & u & linefeed
            on error errMsg number errNum
                if errNum is -1728 or errNum is -1719 then
                    set out to out & "missing" & tab & u & linefeed
                else
                    set out to out & "failed" & tab & u & linefeed
                end if
            end try
        end repeat
    end tell
    return out
end run
"""
CALENDAR_CHECK = """
on run argv
    tell application "Calendar"
        if exists calendar (item 1 of argv) then return "1"
        return "0"
    end tell
end run
"""


class MacError(ConnectorError):
    """A script did not do its work. `code` is one of the codes in the module docstring; nothing else is kept."""


def reachable():
    """True when scripts can run here: a runner was given (tests, a trial), or this is a Mac with osascript."""
    return RUNNER is not None or (sys.platform == "darwin" and shutil.which("osascript") is not None)


def _osascript(script, argv, timeout):
    if not (sys.platform == "darwin" and shutil.which("osascript")):
        raise MacError("unreachable")
    try:
        r = subprocess.run(["osascript", "-e", script, *argv], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MacError("timeout") from None
    except OSError:
        raise MacError("unreachable") from None
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


ERROR_CODE = re.compile(r"\((-?\d+)\)\s*$")


def run_script(script, *argv, runner=None, app=None):
    """Runs one script with these values as its arguments; returns its output (stripped). Raises MacError with a code
    (and `app`, the app it was for). Never raises with the arguments or the script's own words (they can hold titles)."""
    values = [str(v).replace("\x00", "") for v in argv]   # an argument cannot hold a NUL
    run = runner or RUNNER or _osascript
    try:
        code, out, err = run(script, values, TIMEOUT)
    except subprocess.TimeoutExpired:
        raise MacError("timeout", app) from None
    except MacError as e:
        raise MacError(e.code, app) from None
    if code != 0:
        m = ERROR_CODE.search((err or "").strip())
        n = int(m.group(1)) if m else None
        raise MacError("blocked" if n == -1743 else "timeout" if n == -1712 else "failed", app)
    return (out or "").strip()


def date_args(local):
    """The five numbers a script builds a date from: year, month, day, hour, minute of a local 'YYYY-MM-DDTHH:MM' (or
    'YYYY-MM-DD', which is midnight)."""
    day, _, hm = str(local).partition("T")
    y, mo, d = (int(x) for x in day.split("-"))
    h, mi = (int(x) for x in (hm or "00:00").split(":")[:2])
    return [y, mo, d, h, mi]


# ---------- the actions (actions.perform calls run; the yes token binds the exact rows shown) ----------
def _canon(params):
    return json.dumps(params.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def yes_token(ctx, params):
    """The token of exactly these rows (list, titles, notes, due times; or the event's fields) for this person."""
    from . import make_yes_token, text_hash
    return make_yes_token(ctx.handle, type(params).__name__, text_hash(_canon(params)))


def _lines(out):
    return [x for x in (out or "").splitlines() if x.strip()]


def run(ctx, params):
    if type(params).__name__ == "MacEventParams":
        return _event(params)
    return _reminders(params)


def _reminders(p):
    argv = [p.list or "", len(p.items)]
    for it in p.items:
        argv += [it.title, it.notes or "", "1" if it.due else "0", *(date_args(it.due) if it.due else [0] * 5)]
    lines = _lines(run_script(REMINDERS_ADD, *argv, app="Reminders"))
    head = (lines[0] if lines else "").split("\t")
    ids = lines[1:]
    if len(ids) != len(p.items) or len(head) != 2:
        raise MacError("failed", "Reminders")
    placed = [{"action": "mac.reminder", "remote_id": i} for i in ids]
    if head[0] == "1":   # a list the bot made goes on the record, so undo and REMOVE can take it away when empty
        placed.append({"action": "mac.list", "remote_id": head[1]})
    return Outcome("done", detail={"placed": placed, "count": len(ids)})


def _event(p):
    start, end = date_args(p.start), date_args(p.end)
    uid = run_script(CALENDAR_ADD, p.calendar, p.title, p.notes or "", "1" if p.all_day else "0", *start, *end,
                     app="Calendar")
    if uid == "NO_CALENDAR":
        raise MacError("no_calendar", "Calendar")
    if not uid or "\n" in uid:
        raise MacError("failed", "Calendar")
    return Outcome("done", detail={"placed": [{"action": "mac.event", "remote_id": uid}], "count": 1})


def remove(rows):
    """Deletes what the bot placed (placement rows: action, remote_id). Returns {"removed": [row ids], "failed": [row
    ids]}; a thing already gone counts as removed. Reminders before the list they are in."""
    out = {"removed": [], "failed": []}
    rem = [r for r in rows if r["action"] == "mac.reminder"] + [r for r in rows if r["action"] == "mac.list"]
    ev = [r for r in rows if r["action"] == "mac.event"]
    for script, group, args in ((REMINDERS_DELETE, rem, lambda g: [x for r in g for x in
                                                                   ("list" if r["action"] == "mac.list" else "reminder",
                                                                    r["remote_id"])]),
                                (CALENDAR_DELETE, ev, lambda g: [CALENDAR, *[r["remote_id"] for r in g]])):
        if not group:
            continue
        try:
            got = {}
            for line in _lines(run_script(script, *args(group))):   # one call per app
                status, _, rid = line.partition("\t")
                got[rid] = status
        except ConnectorError:
            out["failed"] += [r["id"] for r in group]
            continue
        for r in group:
            ok = got.get(r["remote_id"]) in ("ok", "missing")
            out["removed" if ok else "failed"].append(r["id"])
    return out


def check():
    """The harmless checks "check my mac" runs: count Reminders lists, look for the "Digest" calendar. Returns
    {"reminders": True, "calendar": True | False}; raises MacError when Reminders cannot be reached."""
    run_script(REMINDERS_CHECK, app="Reminders")
    return {"reminders": True, "calendar": run_script(CALENDAR_CHECK, CALENDAR, app="Calendar") == "1"}
