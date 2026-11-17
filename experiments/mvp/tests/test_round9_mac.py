"""Offline tests for round 9, slice D, C2 and C3 (DESIGN.md section 16.D): honest replies when a list is named after an
app the bot cannot reach; Apple Reminders and Calendar on the operator's Mac through AppleScript, with a preview that
waits for a yes, the connections and placements tables, places.route, connect / check / disconnect by text, undo, and
every fallback line. This machine is not a Mac: every script runs against FakeRunner. Synthetic data only; no model
call is added (the fake interpreter answers the forms; the code reads never call it)."""
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

UTC = timezone.utc
TRICKY = 'Say "hi" \\ to C:\\temp & quit'


class FakeRunner:
    """Stands in for osascript: records (script, argv) and answers like Reminders and Calendar would."""

    def __init__(self):
        self.calls = []
        self.fail = None            # "blocked" | "timeout" | "error": every call fails this way
        self.calendar = True        # a calendar called "Digest" exists
        self.delete_fails = False   # delete scripts report "failed" for every id
        self.items = {}             # id -> {"kind", "title", "notes", "due", "list"}
        self.lists = {"L-default": "Reminders"}
        self.n = 0

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}-{self.n}"

    def adds(self):
        return [c for c in self.calls if c[0] in (self.mac.REMINDERS_ADD, self.mac.CALENDAR_ADD)]

    def __call__(self, script, argv, timeout):
        mac = self.mac
        self.calls.append((script, list(argv)))
        assert all(isinstance(v, str) for v in argv)                      # values only ever as argument strings
        if self.fail == "blocked":
            return 1, "", "execution error: Not authorized to send Apple events to Reminders. (-1743)"
        if self.fail == "timeout":
            raise subprocess.TimeoutExpired("osascript", timeout)
        if self.fail == "error":
            return 1, "", "execution error: something else (-2700)"
        if script == mac.REMINDERS_CHECK:
            return 0, str(len(self.lists)), ""
        if script == mac.CALENDAR_CHECK:
            return 0, "1" if self.calendar else "0", ""
        if script == mac.REMINDERS_ADD:
            name, n = argv[0], int(argv[1])
            made = "0"
            lid = next((k for k, v in self.lists.items() if v == name), None) if name else "L-default"
            if lid is None:
                lid, made = self._id("L"), "1"
                self.lists[lid] = name
            ids = []
            for i in range(n):
                b = 2 + i * 8
                rid = self._id("R")
                self.items[rid] = {"kind": "reminder", "title": argv[b], "notes": argv[b + 1], "list": lid,
                                   "due": argv[b + 3:b + 8] if argv[b + 2] == "1" else None}
                ids.append(rid)
            return 0, "\n".join([f"{made}\t{lid}", *ids]) + "\n", ""
        if script == mac.CALENDAR_ADD:
            if not self.calendar:
                return 0, "NO_CALENDAR", ""
            eid = self._id("E")
            self.items[eid] = {"kind": "event", "title": argv[1], "notes": argv[2], "all_day": argv[3],
                               "start": argv[4:9], "end": argv[9:14]}
            return 0, eid, ""
        if script in (mac.REMINDERS_DELETE, mac.CALENDAR_DELETE):
            ids = argv[1::2] if script == mac.REMINDERS_DELETE else argv[1:]
            out = []
            for i in ids:
                if self.delete_fails:
                    out.append(f"failed\t{i}")
                elif i in self.items or i in self.lists:
                    self.items.pop(i, None)
                    self.lists.pop(i, None)
                    out.append(f"ok\t{i}")
                else:
                    out.append(f"missing\t{i}")
            return 0, "\n".join(out), ""
        raise AssertionError("unknown script")


@pytest.fixture()
def mac(env, monkeypatch):
    """The operator (H) on a Mac with a fake osascript."""
    from mvp import config
    from mvp.actions import mac as M
    r = FakeRunner()
    r.mac = M
    monkeypatch.setattr(M, "RUNNER", r)
    monkeypatch.setattr(config, "OPERATOR", H)
    return r


def no_model(env):
    """A message the fake interpreter must never see."""
    def boom(u):
        raise AssertionError("the model was called")
    return boom


def connect(env):
    assert say(env, "check my mac", no_model(env)) == \
        'Reminders and Calendar are connected on this Mac. Events go to your "Digest" calendar.'


def pasta(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta, no cream", ask_pasta())


def sent_since(env, n):
    return "\n".join(t for _, _, t in env["ch"].outbox[n:])


INGREDIENTS = {"intent": "todo_add", "pick_number": 1, "what": "ingredients", "list": "apple reminders"}
PREVIEW = ('I\'ll add these 2 to your Reminders list "Lemon garlic pasta" on your Mac:\n• 200g spaghetti\n• 2 lemons\n'
           'Reply "yes" to add them, or "no" to leave them.')


# ======================================= C2: a list named after an app =======================================
def test_c2_a_list_named_after_an_app_gets_the_honest_line_and_goes_on_the_list_here(env):
    bot = env["bot"]
    calls = len(env["calls"])
    assert say(env, "add milk to my Notion", {"intent": "todo_add", "todo_text": "milk", "list": "notion"}) == \
        'I can\'t reach Notion, so I added "milk" to your list here, called "notion".'
    assert len(env["calls"]) == calls + 1                                 # the one interpreter call; no other
    assert [(t["text"], t["list"]) for t in bot.store.todos(H)] == [("milk", "notion")]
    assert bot.store.one("SELECT intent FROM requests WHERE handle=? ORDER BY id DESC", (H,))["intent"] == "wanted:notion"
    # the app named in the message, the form's list plain: the list here keeps today's name
    assert say(env, "put eggs and bread in todoist", {"intent": "todo_add", "todo_text": "eggs and bread"}) == \
        'I can\'t reach Todoist, so I added 2 things to your list here: eggs; bread.'
    assert say(env, "add it to my evernote", {"intent": "todo_add", "todo_text": "renew passport",
                                              "list": "evernote"}).startswith("I can't reach Evernote, so I added")
    msg = say(env, "add call mum to my ticktick tomorrow at 9am",
              {"intent": "todo_add", "todo_text": "call mum", "list": "ticktick", "due": "2026-11-13T09:00"})
    assert msg == ('I can\'t reach TickTick, so I added "call mum" to your list here, called "ticktick". I\'ll remind '
                   'you tomorrow at 9am.')
    # undo takes it off as usual
    assert say(env, "undo", {"intent": "undo"}).startswith("Undone: I took that off your list")


def test_c2_picks_and_ingredients_named_after_an_app(env):
    bot = env["bot"]
    pasta(env)
    msg = say(env, "put the ingredients in todoist",
              {"intent": "todo_add", "pick_number": 1, "what": "ingredients", "list": "todoist"})
    assert msg == "I can't reach Todoist, so I added 2 things to your list here, called \"todoist\": 200g spaghetti; 2 lemons."
    msg = say(env, "add it to my notion", {"intent": "act_on_last", "pick_number": 1,
                                           "actions": [{"action": "todo.add", "params": {"list": "notion"}}]})
    assert msg == 'I can\'t reach Notion, so I added "Lemon garlic pasta" to your list here, called "notion".'
    row = bot.store.one("SELECT * FROM action_log WHERE action='todo.add' ORDER BY id DESC")
    assert row["status"] == "done" and json.loads(row["detail"])["wanted"] == "notion"


def test_c2_plain_reminders_and_app_words_inside_a_to_do_keep_todays_meaning(env):
    bot = env["bot"]
    assert say(env, "add milk to my reminders list", {"intent": "todo_add", "todo_text": "milk", "list": "reminders"}) \
        == 'Added "milk" to your reminders list.'
    assert say(env, "add cancel notion subscription to my list",
               {"intent": "todo_add", "todo_text": "cancel notion subscription"}) == \
        'Added "cancel notion subscription" to your list.'
    assert say(env, "add things to buy to my list", {"intent": "todo_add", "todo_text": "things to buy"}) == \
        'Added "things to buy" to your list.'
    from mvp.places import named
    for text in ("show my reminders", "stop my reminders", "add milk to my reminders", "remind me at 5 to call mum",
                 "put it on my calendar", "add it to my list", "I have a notion that it works", "my things list"):
        assert named(text, None) is None, text
    assert bot.store.one("SELECT COUNT(*) AS n FROM requests WHERE intent LIKE 'wanted:%'")["n"] == 0


def test_c2_places_read_the_app_words():
    from mvp.places import named
    cases = {"add this to my Notion": "notion", "put the ingredients in todoist": "todoist",
             "add it to my evernote": "evernote", "send it to TickTick": "ticktick", "add it to things 3": "things",
             "put it in google tasks": "google_tasks", "add it to my apple notes": "apple_notes",
             "put it in onenote": "onenote", "add to my trello board": "trello",
             "add it to microsoft to do": "microsoft_todo", "add the ingredients to my apple reminders": "mac_reminders",
             "put this in reminders": "mac_reminders", "add it to the reminders app": "mac_reminders",
             "add it to reminders on my iphone": "mac_reminders", "put it in my mac calendar": "mac_calendar",
             "add it to apple calendar": "mac_calendar", "put it in the calendar app": "mac_calendar"}
    for text, key in cases.items():
        p = named(text, None)
        assert p is not None and p.key == key, text
    assert named("", "Notion list").key == "notion" and named("", "apple reminders").key == "mac_reminders"
    assert named("", "reminders") is None and named("", "grocery") is None


# ======================================= C3: the script runner =======================================
def test_c3_values_only_as_arguments_and_a_tricky_title_passes_untouched(env, mac):
    from mvp.actions import PlaceTodoParams, mac as M
    from mvp.actions.base import Ctx
    connect(env)
    plain = 'Say "hi" \\ to C:\\temp'   # through the whole path ("&" splits a typed list into two to-dos, as today)
    say(env, f"add {plain} to my apple reminders", {"intent": "todo_add", "todo_text": plain, "list": "apple reminders"})
    assert say(env, "yes", no_model(env)).startswith("Added ")
    script, argv = mac.adds()[-1]
    assert script == M.REMINDERS_ADD and plain in argv                      # the title is one argument, as it was
    # the module itself, with "& quit" too
    ctx = Ctx(bot=env["bot"], person=env["bot"].store.person(H), answer={}, picks=[], now=env["clock"][0])
    out = M.run(ctx, PlaceTodoParams(list='My "list" & quit', items=[{"title": TRICKY, "notes": TRICKY}]))
    script, argv = mac.adds()[-1]
    assert argv[0] == 'My "list" & quit' and argv[2:4] == [TRICKY, TRICKY] and out.status == "done"
    assert all(TRICKY not in s and plain not in s and "hi" not in s for s, _ in mac.calls)   # never in a script
    assert list(mac.items.values())[-1]["title"] == TRICKY


def test_c3_run_script_keeps_only_a_code(monkeypatch):
    from mvp.actions import mac as M
    seen = []

    def runner(script, argv, timeout):
        seen.append((script, argv, timeout))
        return 1, "", f"execution error: {argv[0]} is not allowed. (-1743)"
    with pytest.raises(M.MacError) as e:
        M.run_script(M.REMINDERS_CHECK, "secret title", runner=runner, app="Reminders")
    assert e.value.code == "blocked" and e.value.app == "Reminders" and "secret" not in str(e.value)
    assert seen[0][2] == 20                                                 # the 20-second timeout
    for err, code in (("x (-1712)", "timeout"), ("x (-2700)", "failed"), ("", "failed")):
        with pytest.raises(M.MacError) as e:
            M.run_script(M.REMINDERS_CHECK, runner=lambda s, a, t, err=err: (1, "", err))
        assert e.value.code == code
    # NUL characters cannot be arguments; they are dropped
    got = []
    M.run_script(M.REMINDERS_CHECK, "a\x00b", runner=lambda s, a, t: (got.append(a), (0, "ok\n", ""))[1])
    assert got == [["ab"]]


def test_c3_not_on_a_mac_says_so_and_never_runs(env, monkeypatch):
    from mvp import config
    from mvp.actions import mac as M
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setattr(M, "RUNNER", None)
    monkeypatch.setattr(M.sys, "platform", "linux")
    assert not M.reachable()
    with pytest.raises(M.MacError) as e:
        M.run_script(M.REMINDERS_CHECK)
    assert e.value.code == "unreachable"
    assert say(env, "check my mac", no_model(env)) == M_UNREACHABLE()
    assert say(env, "connect my reminders", no_model(env)) == M_UNREACHABLE()
    msg = say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    assert msg == ("I can't reach a Mac from where I'm running, so I added \"milk\" to your list here, called "
                   "\"apple reminders\".")


def M_UNREACHABLE():
    from mvp import texts as T
    return T.MAC_UNREACHABLE


# ---------- dates: separate numbers, the day set to 1 before the month ----------
def _apply_setters(script, start, values):
    """Runs the date lines of a script the way AppleScript does: each field set on its own, an impossible day rolling
    over into the next month."""
    import re
    y, mo, d, h, mi = start.year, start.month, start.day, start.hour, start.minute

    def norm(y, mo, d):
        first = date(y, mo, 1)
        return (first + timedelta(days=d - 1)).timetuple()[:3]
    i = 0
    for line in script.splitlines():
        m = re.match(r"\s*set (day|year|month|hours|minutes) of \w+ to (1|.+)$", line)
        if not m:
            continue
        field, val = m.group(1), m.group(2)
        v = 1 if val.strip() == "1" else values[i]
        if val.strip() != "1":
            i += 1
        if field == "day":
            d = v
        elif field == "year":
            y = v
        elif field == "month":
            mo = v
        elif field == "hours":
            h = v
        else:
            mi = v
        y, mo, d = norm(y, mo, d)
    return datetime(y, mo, d, h, mi)


def test_c3_date_numbers_and_the_day_set_to_1_before_the_month():
    from mvp.actions import mac as M
    assert M.date_args("2028-02-29T23:59") == [2028, 2, 29, 23, 59]
    assert M.date_args("2027-02-28") == [2027, 2, 28, 0, 0]
    for script in (M.REMINDERS_ADD, M.CALENDAR_ADD):
        body = script[script.index("set day of"):]
        assert body.index("to 1\n") < body.index("set month of")              # day 1 first, then the month
    # the script's order on 31 January: one month on is 28 February, not 3 March; 29 February in a leap year; 23:59
    adder = M.REMINDERS_ADD[M.REMINDERS_ADD.index("set d to current date"):M.REMINDERS_ADD.index("set due date")]
    jan31 = datetime(2027, 1, 31, 8, 0)
    assert _apply_setters(adder, jan31, M.date_args("2027-02-28T09:00")) == datetime(2027, 2, 28, 9, 0)
    assert _apply_setters(adder, jan31, M.date_args("2028-02-29T23:59")) == datetime(2028, 2, 29, 23, 59)
    # without the day set to 1 first, the same numbers land in March
    unsafe = adder.replace("set day of d to 1\n", "")
    assert _apply_setters(unsafe, jan31, M.date_args("2027-02-28T09:00")) != datetime(2027, 2, 28, 9, 0)


# ======================================= C3: preview, yes, undo =======================================
def test_c3_ingredients_preview_then_yes_then_undo(env, mac):
    bot = env["bot"]
    connect(env)
    pasta(env)
    calls = len(env["calls"])
    assert say(env, "add the ingredients to my apple reminders", INGREDIENTS) == PREVIEW
    assert mac.adds() == [] and bot.store.todos(H) == []                    # nothing added before the yes
    assert say(env, "yes", no_model(env)) == \
        'Added 2 items to your Reminders list "Lemon garlic pasta". Reply "undo" within 10 minutes to remove them.'
    assert len(env["calls"]) == calls + 1                                   # only the form of the add itself
    assert [x["title"] for x in mac.items.values()] == ["200g spaghetti", "2 lemons"]
    rows = bot.store.placements(H)
    assert [r["action"] for r in rows] == ["mac.reminder", "mac.reminder", "mac.list"]
    assert set(rows[0]) == {"id", "handle", "connector", "action", "remote_id", "run_id", "idem", "created_at",
                            "removed_at"}                                   # no title, no body in the table
    assert bot.store.todos(H) == []                                         # not on the bot's list too
    log = bot.store.one("SELECT * FROM action_log WHERE action='mac.reminder'")
    assert log["status"] == "done" and "spaghetti" not in (log["detail"] or "")
    assert say(env, "undo", {"intent": "undo"}) == "Undone: I took those 2 out of Reminders on your Mac."
    assert mac.items == {} and "Lemon garlic pasta" not in mac.lists.values()   # the list it made, empty, went too
    assert bot.store.placements(H) == []


def test_c3_a_to_do_with_a_due_time_gets_it_there_and_the_bot_never_nudges(env, mac):
    bot = env["bot"]
    connect(env)
    msg = say(env, "add call the dentist to my apple reminders tomorrow at 9am",
              {"intent": "todo_add", "todo_text": "call the dentist", "list": "apple reminders",
               "due": "2026-11-13T09:00"})
    assert msg == ('I\'ll add "call the dentist" to Reminders on your Mac, due tomorrow at 9am.\nReply "yes" to add it, '
                   'or "no" to leave it.')
    assert say(env, "yes please", no_model(env)) == (
        'Added "call the dentist" to Reminders. Reminders will remind you tomorrow at 9am; I won\'t send my own '
        'reminder. Reply "undo" within 10 minutes to remove it.')
    item = list(mac.items.values())[0]
    assert item["due"] == ["2026", "11", "13", "9", "0"] and item["list"] == "L-default"
    assert bot.store.todos(H) == [] and bot.store.due_todos(datetime(2026, 11, 14, tzinfo=UTC)) == []


def test_c3_no_and_any_other_message_leave_it(env, mac):
    connect(env)
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    assert say(env, "no", no_model(env)) == "OK, I didn't add anything."
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    say(env, "what's on my list", {"intent": "todo_list"})                   # another message ends the question
    assert say(env, "yes", {"intent": "confirm"}) == "I don't have anything waiting for a yes. Tell me what you'd like and I'll set it up."
    assert mac.adds() == []
    # a yes after 30 minutes adds nothing
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    env["clock"][0] += timedelta(minutes=31)
    say(env, "yes", {"intent": "confirm"})
    assert mac.adds() == []


def test_c3_a_tapback_never_says_yes(env, mac):
    connect(env)
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    ref = env["ch"].outbox[-1][0]
    env["bot"].on_message(H, "", tapback="up", tapback_ref=ref)
    assert mac.adds() == []


def test_c3_the_yes_token_binds_the_exact_rows_shown(env, mac):
    bot = env["bot"]
    connect(env)
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    st = bot.store.get_state(f"placeask:{H}")
    st["plans"][0]["params"]["items"][0]["title"] = "something else"      # anything changed after the preview
    bot.store.set_state(f"placeask:{H}", st)
    msg = say(env, "yes", no_model(env))
    assert msg.startswith("Reminders on your Mac gave an error, so I added \"milk\" to your list here")
    assert mac.adds() == []                                                 # perform refused it: never ran
    assert [t["text"] for t in bot.store.todos(H)] == ["milk"]


def test_c3_code_only_and_never_in_a_rule_or_a_model_form(env):
    from pydantic import ValidationError
    from mvp.actions import REGISTRY, validate_action
    from mvp.schema import Action, Interpretation
    for name in ("mac.reminder", "mac.event"):
        d = REGISTRY[name]
        assert (d.outside, d.undo, d.confirm, d.who, d.from_model, d.in_rules, d.connector) == \
            (True, "delete", "send_word", "operator", False, False, "mac")
        with pytest.raises(ValidationError):
            Action.model_validate({"action": name})
        with pytest.raises(ValidationError):
            Interpretation.model_validate({"intent": "act_on_last", "pick_number": 1, "actions": [name]})
    assert REGISTRY["mac.reminder"].max_per_day == 40 and REGISTRY["mac.event"].max_per_day == 10
    assert REGISTRY["mac.reminder"].fallback == "todo.add" and REGISTRY["mac.event"].fallback == "calendar.add"
    assert validate_action("mac.reminder", {"items": [{"title": "x"}]}, by="code")[0] == "mac.reminder"


def test_c3_a_tester_never_reaches_the_runner(env, mac, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    msg = say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    assert msg == ('Reminders on my Mac only works for the person who runs me, so I added "milk" to your list here, '
                   'called "apple reminders".')
    assert say(env, "check my mac", no_model(env)) == ("Reminders and Calendar on my Mac are only for the person who "
                                                       "runs me. I keep your lists here, and I give you a calendar link "
                                                       "you tap, with no sign-in.")
    assert say(env, "connect my calendar", no_model(env)).startswith("Reminders and Calendar on my Mac are only")
    assert say(env, "put my lists in reminders from now on", no_model(env)).startswith("Reminders and Calendar on my")
    assert mac.calls == []


def test_c3_operator_unset_means_nobody(env, mac, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", None)
    assert say(env, "check my mac", no_model(env)).startswith("Reminders and Calendar on my Mac are only")
    assert mac.calls == []


# ---------- calendar ----------
CAL_FORM = {"intent": "act_on_last", "pick_number": 1,
            "actions": [{"action": "calendar.add", "params": {"date": "2026-11-14", "time": "10:00"}}]}


def test_c3_an_event_in_the_digest_calendar(env, mac):
    bot = env["bot"]
    connect(env)
    pasta(env)
    msg = say(env, "put the first one in my mac calendar on saturday at 10", CAL_FORM)
    assert msg == ('I\'ll put "Lemon garlic pasta" in your "Digest" calendar on your Mac, on Saturday 14 November at '
                   '10am.\nWith the note: From your saves: https://example.com/itm_a\nReply "yes" to add it, or "no" to '
                   'leave it.')
    assert bot.store.outbox(H) == []                                        # no link, no .ics yet
    assert say(env, "yes", no_model(env)) == ('Added "Lemon garlic pasta" to your "Digest" calendar, on Saturday 14 '
                                              'November at 10am. Reply "undo" within 10 minutes to remove it.')
    script, argv = mac.adds()[-1]
    assert argv[:4] == ["Digest", "Lemon garlic pasta", "From your saves: https://example.com/itm_a", "0"]
    assert argv[4:] == ["2026", "11", "14", "10", "0", "2026", "11", "14", "10", "30"]
    assert say(env, "undo", {"intent": "undo"}) == 'Undone: I took "Lemon garlic pasta" out of Calendar on your Mac.'
    assert mac.items == {}


def test_c3_no_digest_calendar_gives_the_link_and_says_so(env, mac):
    bot = env["bot"]
    connect(env)
    mac.calendar = False
    pasta(env)
    say(env, "put the first one in my mac calendar on saturday at 10", CAL_FORM)
    n = len(env["ch"].outbox)
    say(env, "yes", no_model(env))
    msg = sent_since(env, n)
    assert msg.startswith('I couldn\'t find a calendar called "Digest" on this Mac, so here\'s a link instead. Make '
                          'one in Calendar, then text me "check my mac".')
    assert 'To put "Lemon garlic pasta" on your calendar on Saturday 14 November at 10am, tap this link:' in msg
    assert "https://calendar.google.com/calendar/render?action=TEMPLATE" in msg
    assert [r["kind"] for r in bot.store.outbox(H)] == ["calendar"]
    # the next event goes straight to the link, with no preview, and nothing counts as a failure
    msg = say(env, "put the first one in my mac calendar on saturday at 10", CAL_FORM)
    assert msg.startswith('I couldn\'t find a calendar called "Digest" on this Mac, so here\'s a link instead.')
    assert bot.store.connection(H, "mac")["status"] == "connected" and bot.store.connection(H, "mac")["fails"] == 0


@pytest.mark.parametrize("fail,reminders_line,calendar_line", [
    ("blocked", "Your Mac blocked me from Reminders, so I added \"milk\" to your list here, called \"apple reminders\". "
                "Turn it on in System Settings › Privacy & Security › Automation.",
     "Your Mac blocked me from Calendar, so here's a link instead. Turn it on in System Settings › Privacy & Security "
     "› Automation."),
    # (round 9 checks) a time-out may still have added it on the Mac: the line says so
    ("timeout", "Reminders didn't answer in time, so I added \"milk\" to your list here, called \"apple reminders\". "
                "It may have reached Reminders anyway, so check there before you ask me again.",
     "Calendar didn't answer in time, so here's a link instead."),
])
def test_c3_blocked_and_timeout_fall_back_with_their_lines(env, mac, fail, reminders_line, calendar_line):
    bot = env["bot"]
    connect(env)
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    mac.fail = fail
    assert say(env, "yes", no_model(env)) == reminders_line
    assert [t["text"] for t in bot.store.todos(H)] == ["milk"]              # the fallback ran
    mac.fail = None
    pasta(env)
    say(env, "put the first one in my mac calendar on saturday at 10", CAL_FORM)
    mac.fail = fail
    n = len(env["ch"].outbox)
    say(env, "yes", no_model(env))
    msg = sent_since(env, n)
    assert msg.startswith(calendar_line) and "https://calendar.google.com/" in msg
    log = bot.store.q("SELECT status, detail FROM action_log WHERE action IN ('mac.reminder','mac.event')")
    assert [r["status"] for r in log] == ["failed", "failed"] and all(fail in r["detail"] for r in log)


# ---------- the circuit breaker ----------
def test_c3_three_failures_break_it_no_fourth_call_and_check_recovers(env, mac):
    bot = env["bot"]
    connect(env)
    mac.fail = "error"
    for i in range(3):
        say(env, f"add milk {i} to my apple reminders", {"intent": "todo_add", "todo_text": f"milk {i}",
                                                    "list": "apple reminders"})
        assert say(env, "yes", no_model(env)).startswith("Reminders on your Mac gave an error, so I added")
    row = bot.store.connection(H, "mac")
    assert (row["status"], row["fails"], row["last_error"]) == ("broken", 3, "failed")
    n = len(mac.calls)
    msg = say(env, "add eggs to my apple reminders", {"intent": "todo_add", "todo_text": "eggs", "list": "apple reminders"})
    assert msg == ("I've stopped using Reminders on your Mac after 3 failures in a row, so I added \"eggs\" to your "
                   "list here, called \"apple reminders\". Text me \"check my mac\" when it's ready.")
    assert len(mac.calls) == n                                              # no fourth call
    mac.fail = None
    connect(env)
    assert (bot.store.connection(H, "mac")["status"], bot.store.connection(H, "mac")["fails"]) == ("connected", 0)
    assert say(env, "add eggs to my apple reminders",
               {"intent": "todo_add", "todo_text": "eggs", "list": "apple reminders"}).startswith("I'll add \"eggs\"")


def test_c3_a_success_ends_a_run_of_failures(env, mac):
    bot = env["bot"]
    connect(env)
    for i, fail in enumerate(("error", "error", None, "error")):
        mac.fail = fail
        say(env, f"add milk {i} to my apple reminders", {"intent": "todo_add", "todo_text": f"milk {i}",
                                                    "list": "apple reminders"})
        say(env, "yes", no_model(env))
    assert (bot.store.connection(H, "mac")["status"], bot.store.connection(H, "mac")["fails"]) == ("connected", 1)


# ---------- the same thing twice, the daily limit ----------
def test_c3_the_same_run_asked_again_adds_nothing_twice(env, mac):
    connect(env)
    pasta(env)
    say(env, "add the ingredients to my apple reminders", INGREDIENTS)
    say(env, "yes", no_model(env))
    assert say(env, "add the ingredients to my apple reminders", INGREDIENTS) == \
        "I already added that to Reminders on your Mac today."
    assert len(mac.adds()) == 1
    # a replayed yes (the same plan kept from before) adds nothing either
    from mvp import places
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    plan = env["bot"].store.get_state(f"placeask:{H}")
    say(env, "yes", no_model(env))
    person = env["bot"].store.person(H)
    assert str(places.run_plan(env["bot"], person, plan["plans"][0], env["clock"][0])) == \
        "I already added that to Reminders on your Mac today."
    assert len(mac.adds()) == 2


def test_c3_the_41st_reminder_in_a_day_falls_back_with_the_cap_line(env, mac):
    bot = env["bot"]
    connect(env)
    for i in range(40):   # 40 made today (local day), whatever happened to them since
        bot.store.add_placement(H, "mac", "mac.reminder", f"R-old-{i}", at=env["clock"][0])
    bot.store.add_placement(H, "mac", "mac.reminder", "R-yesterday", at=env["clock"][0] - timedelta(days=1))
    msg = say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    assert msg == ("I've reached my limit of 40 reminders a day on your Mac, so I added \"milk\" to your list here, "
                   "called \"apple reminders\".")
    assert mac.adds() == []
    # the next local day (New York) it asks again
    env["clock"][0] = datetime(2026, 11, 13, 5, 1, tzinfo=UTC)               # 00:01 in New York
    assert say(env, "add milk to my apple reminders",
               {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"}).startswith("I'll add \"milk\"")


def test_c3_events_have_their_own_limit_of_10(env, mac):
    bot = env["bot"]
    connect(env)
    for i in range(10):
        bot.store.add_placement(H, "mac", "mac.event", f"E-old-{i}", at=env["clock"][0])
    pasta(env)
    msg = say(env, "put the first one in my mac calendar on saturday at 10", CAL_FORM)
    assert msg.startswith("I've reached my limit of 10 events a day on your Mac, so here's a link instead.")


# ---------- connect, check, what are you connected to, from now on ----------
def test_c3_connect_check_and_what_are_you_connected_to(env, mac):
    bot = env["bot"]
    calls = len(env["calls"])
    msg = say(env, "connect my reminders", no_model(env))
    assert msg.startswith("I can add to Reminders and Calendar on this Mac, with no password.\n1. In Calendar on the "
                          "Mac, make a calendar called \"Digest\"")
    assert say(env, "Connect my calendar.", no_model(env)) == msg
    msg = say(env, "what are you connected to?", no_model(env))
    assert msg.splitlines() == [
        "Here's where I can put things for you:", "• Your list here: always on.",
        "• Email to you: not connected here, so emails wait in the bot's outbox folder.",   # no SMTP in the tests
        "• Calendar: a link you tap, no sign-in.",
        "• Email to other people: a draft you send from your mail app.",
        "• Reminders and Calendar on this Mac: not connected yet (say \"connect my mac\")."]
    mac.calendar = False
    assert say(env, "check my mac", no_model(env)) == (
        'Reminders is connected on this Mac. I couldn\'t find a calendar called "Digest", so events still come as a '
        'link. Make one in Calendar, then text me "check my mac" again.')
    assert "connected (events still come as a link" in say(env, "what are you connected to", no_model(env))
    mac.calendar = True
    connect(env)
    msg = say(env, "what are you connected to", no_model(env))
    assert msg.endswith("• Reminders and Calendar on this Mac: connected.\nSay \"disconnect my mac\" to stop.")
    assert say(env, "connect my mac", no_model(env)) == \
        'Reminders and Calendar are connected on this Mac. Events go to your "Digest" calendar.'
    assert len(env["calls"]) == calls                                       # no model call for any of these
    # a tester gets the first lines and the Mac line
    from mvp import config
    config.OPERATOR = "+15559999"
    msg = say(env, "what are you connected to", no_model(env))
    assert msg.endswith("• Email to other people: a draft you send from your mail app.\nReminders and Calendar on my "
                        "Mac are only for the person who runs me.")
    assert bot


def test_c3_a_failed_check(env, mac):
    bot = env["bot"]
    mac.fail = "blocked"
    assert say(env, "check my mac", no_model(env)) == (
        'Your Mac blocked me from Reminders. Turn it on in System Settings › Privacy & Security › Automation, then '
        'text me "check my mac" again.')
    assert bot.store.connection(H, "mac") is None                          # never connected: nothing recorded
    mac.fail = None
    connect(env)
    mac.fail = "timeout"
    assert say(env, "check my mac", no_model(env)).startswith("Reminders didn't answer in time. Make sure the Mac is")
    assert bot.store.connection(H, "mac")["status"] == "broken"


def test_c3_from_now_on_lists_and_events_go_to_the_mac_after_a_preview(env, mac):
    bot = env["bot"]
    connect(env)
    assert say(env, "put my lists in reminders from now on", no_model(env)).startswith(
        "OK. From now on I'll offer to put new things for your lists in Reminders on your Mac")
    assert bot.store.person_context(H)["prefs"]["place_todo"] == "mac"
    assert say(env, "add milk to my list", {"intent": "todo_add", "todo_text": "milk"}).startswith(
        'I\'ll add "milk" to Reminders on your Mac.')
    assert say(env, "yes", no_model(env)).startswith('Added "milk" to Reminders.')
    assert say(env, "put events straight in my calendar", no_model(env)).startswith(
        "OK. From now on I'll offer to put events straight in your \"Digest\" calendar")
    pasta(env)
    assert say(env, "put the first one on my calendar saturday at 10", CAL_FORM).startswith(
        'I\'ll put "Lemon garlic pasta" in your "Digest" calendar')
    say(env, "no", no_model(env))
    assert say(env, "use my list here again", no_model(env)) == "OK. New things for your lists stay on your list here."
    assert say(env, "use calendar links again", no_model(env)) == "OK. Calendar entries come as a link you tap again."
    assert say(env, "add eggs to my list", {"intent": "todo_add", "todo_text": "eggs"}) == 'Added "eggs" to your list.'


def test_c3_a_rule_never_writes_to_the_mac_by_itself(env, mac):
    bot = env["bot"]
    connect(env)
    from mvp import places
    person = bot.store.person(H)
    got = places.route_todo(bot, person, [("Lemon garlic pasta", "itm_a", "https://example.com/itm_a", None)],
                            "apple reminders", "", env["clock"][0], scheduled=True, undoable=False)
    assert got[0] == ('I only add to Reminders on your Mac after you say yes, so I added "Lemon garlic pasta" to your '
                      'list here, called "apple reminders".')
    bot.store.set_prefs(H, place_todo="mac")
    assert places.decide(bot.store, person, "todo", "todo", "", scheduled=True) is None   # the choice is not a rule's
    assert mac.adds() == []


# ---------- disconnect, REMOVE / KEEP, delete my data ----------
def _two_added(env, mac):
    connect(env)
    pasta(env)
    say(env, "add the ingredients to my apple reminders", INGREDIENTS)
    say(env, "yes", no_model(env))
    say(env, "put the first one in my mac calendar on saturday at 10", CAL_FORM)
    say(env, "yes", no_model(env))


def test_c3_disconnect_then_remove_deletes_only_what_the_bot_added(env, mac):
    bot = env["bot"]
    _two_added(env, mac)
    mac.items["R-theirs"] = {"kind": "reminder", "title": "their own", "list": "L-default"}
    assert say(env, "disconnect my mac", no_model(env)) == (
        "I've stopped using Reminders and Calendar. I added 2 reminders and 1 event in the last 30 days. Reply REMOVE "
        "to delete those, or KEEP to leave them.")
    assert bot.store.connection(H, "mac")["status"] == "off"
    assert say(env, "REMOVE", no_model(env)) == (
        "I deleted the 2 reminders and 1 event I'd added. To take back my access completely, go to System Settings › "
        "Privacy & Security › Automation.")
    assert list(mac.items) == ["R-theirs"]                                 # only placement ids were deleted
    deleted = [a for s, a in mac.calls if s in (mac.mac.REMINDERS_DELETE, mac.mac.CALENDAR_DELETE)]
    assert all("R-theirs" not in a for a in deleted)
    assert bot.store.placements(H) == []
    # off: the next add falls back and says so
    msg = say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    assert msg.startswith("Reminders on your Mac is turned off, so I added \"milk\"")
    assert say(env, "disconnect my mac", no_model(env)) == \
        "Reminders and Calendar on the Mac aren't connected, so there's nothing to stop."


@pytest.mark.parametrize("answer", ["KEEP", "later", None])
def test_c3_keep_another_message_or_30_minutes_leave_them(env, mac, answer):
    bot = env["bot"]
    _two_added(env, mac)
    say(env, "stop using reminders", no_model(env))
    if answer == "KEEP":
        assert say(env, "keep them", no_model(env)).startswith("OK, they stay where they are.")
    elif answer == "later":
        say(env, "what's on my list", {"intent": "todo_list"})
    else:
        env["clock"][0] += timedelta(minutes=31)
    say(env, "remove", {"intent": "chat", "reply": "ok"})
    assert len(mac.items) == 3 and len(bot.store.placements(H)) == 4      # 2 reminders, the list, 1 event


def test_c3_delete_my_data_clears_both_tables_and_says_the_mac_stays(env, mac):
    bot = env["bot"]
    _two_added(env, mac)
    assert say(env, "delete my data", {"intent": "delete_data"}) == (
        "This deletes your library, rules and history with me. Reply YES to delete everything. This also stops "
        "Reminders and Calendar on the Mac. What I added there stays there.")
    say(env, "YES", no_model(env))
    for t in ("connections", "placements"):
        assert bot.store.one(f"SELECT COUNT(*) AS n FROM {t} WHERE handle=?", (H,))["n"] == 0
    assert len(mac.items) == 3                                              # what it added stays there


def test_c3_delete_my_data_without_the_mac_is_unchanged(env):
    assert say(env, "delete my data", {"intent": "delete_data"}) == \
        "This deletes your library, rules and history with me. Reply YES to delete everything."


def test_c3_a_failed_undo_names_what_to_delete(env, mac):
    connect(env)
    say(env, "add milk to my apple reminders", {"intent": "todo_add", "todo_text": "milk", "list": "apple reminders"})
    say(env, "yes", no_model(env))
    mac.delete_fails = True
    assert say(env, "undo", {"intent": "undo"}) == 'I couldn\'t take it out of Reminders just now. It\'s "milk"; delete it there.'
    mac.delete_fails = False
    # deleted on the phone already: "undo" counts it as gone
    say(env, "add eggs to my apple reminders", {"intent": "todo_add", "todo_text": "eggs", "list": "apple reminders"})
    say(env, "yes", no_model(env))
    mac.items.clear()
    assert say(env, "undo", {"intent": "undo"}) == 'Undone: I took "eggs" out of Reminders on your Mac.'


# ---------- the store ----------
def test_a_store_from_before_gains_the_two_tables(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT NOT NULL,"
               " consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT)")
    db.execute("INSERT INTO people(handle, library, timezone) VALUES('+15550002', '/x', 'UTC')")
    db.commit()
    db.close()
    from mvp.store import Store
    s = Store(str(path))
    assert s.person("+15550002")["timezone"] == "UTC"
    assert s.connection("+15550002", "mac") is None and s.placements("+15550002") == []
    s.set_connection("+15550002", "mac", status="connected", at=datetime(2026, 11, 12, tzinfo=UTC), checked=True)
    s.set_connection("+15550002", "mac", fails=2, last_error="timeout")
    row = s.connection("+15550002", "mac")
    assert (row["status"], row["fails"], row["last_error"]) == ("connected", 2, "timeout")
    s.set_connection("+15550002", "mac", last_error="")
    assert s.connection("+15550002", "mac")["last_error"] is None


# ---------- no new read takes an existing request ----------
def test_no_eval_text_is_taken_by_the_new_reads():
    from mvp import places
    here = os.path.join(os.path.dirname(HERE), "evalset")
    n = 0
    for name in ("rules_dev_timing.jsonl", "rules_dev_content.jsonl", "rules_dev_extra.jsonl"):
        for line in open(os.path.join(here, name), encoding="utf-8"):
            if not line.strip():
                continue
            text = json.loads(line)["text"]
            t = places._norm(text)
            n += 1
            for rx in (places.CONNECTED, places.CONNECT, places.CHECK, places.DISCONNECT, places.PREF_TODO_ON,
                       places.PREF_TODO_OFF, places.PREF_CAL_ON, places.PREF_CAL_OFF, places.REMOVE, places.KEEP):
                assert not rx.match(t), text
            assert places.named(text, None) is None, text
    assert n == 159


# ---------- the round 9 merge: "what are you connected to" is true for what is merged ----------
def _email_lines(env):
    return [x for x in say(env, "what are you connected to", no_model(env)).splitlines() if x.startswith("• Email")]


def test_connected_to_says_how_email_to_you_works_here(env, monkeypatch):
    bot = env["bot"]
    monkeypatch.delenv("MVP_SMTP_HOST", raising=False)
    # no SMTP, on a channel whose person cannot open the outbox (Messages): a link to themselves (slice A, W3)
    monkeypatch.setattr(bot.channel, "outbox_reachable", False, raising=False)
    monkeypatch.setattr(bot.channel, "outbox_place", None, raising=False)
    assert _email_lines(env)[0] == ("• Email to you: not connected here, so I give you a link that opens an email to "
                                    "yourself.")
    # with SMTP: the address and its state, as before
    monkeypatch.setenv("MVP_SMTP_HOST", "smtp.example.invalid")
    assert _email_lines(env)[0] == "• Email to you: not set up yet (tell me your email address)."
    bot.store.set_email(H, "alex@example.com", verified=True)
    assert _email_lines(env)[0] == "• Email to you: on, to alex@example.com."


def test_connected_to_says_the_operator_s_mailbox_sends_only_after_send(env, mac, monkeypatch):
    monkeypatch.setenv("MVP_MAILBOX_ADDRESS", "me@example.com")
    monkeypatch.setenv("MVP_MAILBOX_APP_PASSWORD", "fake-app-pass-1234")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.delenv("MVP_MAILBOX_IMAP_HOST", raising=False)
    line = "• Email to other people: a draft I show you first, and I send it from me@example.com only after you reply \"send\""
    assert _email_lines(env)[1] == line + "."
    monkeypatch.setenv("MVP_MAILBOX_IMAP_HOST", "imap.example.invalid")
    assert _email_lines(env)[1] == line + ". \"save it as a draft\" puts it in your Drafts folder."
    out = say(env, "what are you connected to", no_model(env))
    assert "fake-app-pass" not in out
    # a tester never sees the operator's mailbox
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    assert _email_lines(env)[1] == "• Email to other people: a draft you send from your mail app."


def test_export_my_data_has_the_connections_and_placements_without_titles(env, mac):
    import json as _json
    from mvp import export as X
    bot = env["bot"]
    out = X.export(bot, bot.store.person(H), env["clock"][0])
    assert "connections.json" not in [n for n, _ in out["files"]]           # nothing connected: as before
    _two_added(env, mac)
    say(env, "undo", {"intent": "undo"})
    out = X.export(bot, bot.store.person(H), env["clock"][0])
    path = dict(out["files"])["connections.json"]
    data = _json.load(open(path))
    assert [c["connector"] for c in data["connections"]] == ["mac"] and data["connections"][0]["status"] == "connected"
    assert set(data["connections"][0]) == {"connector", "status", "created_at", "checked_at"}
    acts = [p["action"] for p in data["placements"]]   # 2 reminders, their list, the event ("undo" took it out)
    assert sorted(acts) == ["mac.event", "mac.list", "mac.reminder", "mac.reminder"]
    assert [p["action"] for p in data["placements"] if p["removed_at"]] == ["mac.event"]
    assert set(data["placements"][0]) == {"id", "connector", "action", "remote_id", "run_id", "created_at",
                                          "removed_at"}
    raw = open(path).read().lower()
    for title in (x["title"].lower() for x in mac.items.values() if isinstance(x, dict) and x.get("title")):
        assert title not in raw
    assert "connections.json" in open(dict(out["files"])["README.txt"]).read()
