"""PROTOTYPE ONLY - where a to-do or a calendar entry goes (round 9, C2 and C3; DESIGN.md section 16.D).

C2. A list named after an app ("add this to my Notion", "put the ingredients in todoist"): with no connector for that
app, the to-dos go where they go today (the bot's own list, with the name the form gave) and the reply says so
plainly: 'I can't reach Notion, so I added "..." to your list here, called "notion".' The ask is kept in `requests`
(intent "wanted:<app>") as the backlog of places people want.

C3. The operator's Mac (connectors.py, actions/mac.py): a place named in the message ("to my apple reminders", "in my
mac calendar") or chosen "from now on" (prefs place_todo / place_calendar = "mac") sends the to-dos to Reminders and
the event to the "Digest" calendar, for the operator only and only while connected. The founder's rule for anything
that reaches an outside account (17 Nov, "Always show, then wait for yes"): the bot first shows exactly what it will
add and does it only after the person's yes to that message (the next message only, 30 minutes); the yes token binds
the exact rows shown (actions.perform refuses anything else). When it cannot (a tester, not on a Mac, not connected,
turned off, broken after 3 failures, the Mac blocked it, a timeout, no "Digest" calendar, the daily limit) today's
action runs and the reply says why in one plain line. A rule's timed send never writes outside (nobody is there to say
yes): a rule's list named after Reminders stays on the bot's list, and the line says so.

Code reads, no model call: "connect my mac" (and "connect my reminders / calendar"), "check my mac", "what are you
connected to", "disconnect my mac" (then REMOVE or KEEP), "put my lists in reminders from now on", "use my list here
again", "put events straight in my calendar", "use calendar links again"; the yes / no after a preview.

Adding a place: one entry in PLACES (the words), and for a real connector one entry in connectors.CONNECTORS plus its
registry entries (connectors.py says how).
"""
import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional
from zoneinfo import ZoneInfo

from . import config
from . import connectors as C
from . import texts as T
from .render import Reply
from .store import now_iso

ASK_OPEN = timedelta(minutes=30)       # a preview waits this long for its yes (the next message only)
REMOVE_OPEN = timedelta(minutes=30)    # "Reply REMOVE ... or KEEP" after "disconnect my mac"
SAME_ASK = timedelta(hours=24)         # the same things asked again within this are not added twice
LOOK_BACK = timedelta(days=30)         # what "disconnect" offers to remove


@dataclass(frozen=True)
class Place:
    key: str
    app: str                 # its name in a reply: "Notion", "Apple Reminders"
    kind: str                # what it takes: "todo" or "calendar"
    connector: Optional[str]  # a key of connectors.CONNECTORS, or None: the bot cannot reach it
    words: str               # what names it after "to / in / into / onto / on (my|the)" in a message
    names: tuple = ()        # list names (schema.list_name spelling) that mean it


_PREP = r"\b(?:to|in|into|onto|on)\s+(?:my\s+|the\s+|our\s+)?"
_TAIL = r"(?:\s+(?:app|list|account|board|inbox))?\b"
PLACES = (
    Place("mac_reminders", "Apple Reminders", "todo", "mac",
          r"(?:apple\s+reminders|reminders\s+app|(?:mac|iphone|ios|icloud)\s+reminders|"
          r"reminders\s+on\s+(?:my|the)\s+(?:mac|iphone|phone))",
          ("apple reminders", "reminders app", "mac reminders", "iphone reminders", "ios reminders", "icloud reminders")),
    Place("mac_calendar", "Calendar on your Mac", "calendar", "mac",
          r"(?:(?:apple|mac|icloud|iphone)\s+calendar|calendar\s+app|calendar\s+on\s+(?:my|the)\s+(?:mac|iphone|phone)|"
          r"ical|digest\s+calendar)"),
    Place("notion", "Notion", "todo", None, r"notion", ("notion",)),
    Place("todoist", "Todoist", "todo", "todoist", r"todoist", ("todoist",)),           # round 9, E: by a token
    Place("ticktick", "TickTick", "todo", "ticktick", r"tick\s?tick", ("ticktick", "tick tick")),
    Place("webhook", "your webhook", "todo", "webhook", r"(?:webhook|automation|ifttt|zapier|n8n)",
          ("webhook", "automation")),
    Place("things", "Things", "todo", None, r"things\s+(?:3|app)", ("things 3", "things app")),
    Place("trello", "Trello", "todo", None, r"trello", ("trello",)),
    Place("google_tasks", "Google Tasks", "todo", None, r"google\s+tasks", ("google tasks",)),
    Place("google_keep", "Google Keep", "todo", None, r"google\s+keep", ("google keep",)),
    Place("apple_notes", "Apple Notes", "todo", None, r"(?:apple\s+notes|notes\s+app)", ("apple notes", "notes app")),
    Place("evernote", "Evernote", "todo", None, r"evernote", ("evernote",)),
    Place("onenote", "OneNote", "todo", None, r"one\s?note", ("onenote", "one note")),
    Place("microsoft_todo", "Microsoft To Do", "todo", None, r"(?:microsoft|ms)\s+to[\s-]?do",
          ("microsoft to do", "microsoft todo", "microsoft to-do", "ms to do", "ms todo")),
)
BY_KEY = {p.key: p for p in PLACES}
_RX = {p.key: re.compile(_PREP + p.words + _TAIL, re.I) for p in PLACES}
# "put it in reminders" (no "my": the app); "add milk to my reminders (list)" keeps today's meaning (a list here)
_BARE_REMINDERS = re.compile(r"\b(?:to|in|into)\s+reminders\b(?!\s+list)", re.I)


def named(text, list_name=None, kind=None):
    """The place a message (or the list name a form gave) names, or None."""
    from .schema import list_name as norm
    ln = norm(list_name) if list_name else None
    for p in PLACES:
        if kind and p.kind != kind:
            continue
        if ln and ln in p.names:
            return p
        if text and (_RX[p.key].search(text) or (p.key == "mac_reminders" and _BARE_REMINDERS.search(text))):
            return p
    return None


@dataclass(frozen=True)
class Decision:
    place: Place
    use: bool                # True: show what would go there and wait for a yes
    reason: Optional[str] = None   # why not (texts.PLACE_CLAUSE)


def place_for(kind, connector):
    return next(p for p in PLACES if p.kind == kind and p.connector == connector)


def decide(store, person, kind, list_name, text, scheduled=False):
    """None when nothing names an outside place (today's path, unchanged)."""
    h = person["handle"]
    p = named("" if scheduled else text, list_name, kind)
    if p is None and not scheduled:
        pref = store.person_context(h)["prefs"].get("place_todo" if kind == "todo" else "place_calendar")
        if pref in C.CONNECTORS:
            p = place_for(kind, pref)
    if p is None:
        return None
    if p.connector is None:
        return Decision(p, False, "no_connector")
    if scheduled:
        return Decision(p, False, "scheduled")
    why = C.unavailable(store, h, p.connector)
    if why:
        return Decision(p, False, why)
    if kind == "calendar" and (store.connection(h, p.connector) or {}).get("last_error") == "no_calendar":
        return Decision(p, False, "no_calendar")
    return Decision(p, True)


def _short(place):
    return C.CONNECTORS[place.connector].apps[place.kind] if place.connector else place.app


def clause(place, reason, cap=None):
    con = C.CONNECTORS.get(place.connector) if place.connector else None
    action = con.actions[place.kind] if con else None
    if reason == "cap" and cap is None and action:
        from .actions import REGISTRY
        cap = REGISTRY[action].max_per_day
    nouns = con.nouns[action][1] if con else None
    if con and con.kind != "mac":   # round 9, E: a task app by token, or the webhook
        return T.token_clause(reason, con.apps[place.kind], cap, nouns)
    return T.place_clause(reason, place.app, _short(place), cap, nouns)


def after(place, reason):
    """The hint after a clause ("Text me ... to set it up.")."""
    con = C.CONNECTORS.get(place.connector) if place.connector else None
    if con and con.kind != "mac":
        return T.token_after(reason, con.key)
    return T.PLACE_AFTER.get(reason, "")


def _kind(place):
    con = C.CONNECTORS.get(place.connector) if place.connector else None
    return con.kind if con else None


def _local(dt, tz):
    return dt.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M")


def _idem(handle, action, run_id, keys):
    return hashlib.sha256(json.dumps([handle, action, run_id, list(keys)], ensure_ascii=False).encode()).hexdigest()


def _over_cap(store, handle, tz, action, n, now):
    from .actions import REGISTRY, local_day_bounds
    cap = REGISTRY[action].max_per_day
    start, end = local_day_bounds(now, tz)
    return cap if cap is not None and store.placements_in(handle, action, start, end) + n > cap else None


def _save_ask(bot, handle, plan, now):
    """One preview per message: a second place in the same message joins it (asked_reads cleared any older one)."""
    st = bot.store.get_state(f"placeask:{handle}") or {"plans": []}
    st["plans"] = [*st.get("plans", []), plan]
    st["at"] = now_iso(now)
    bot.store.set_state(f"placeask:{handle}", st)


def write_here(bot, person, rows, name, now, undoable=True):
    """Today's write: rows [(text, item_id, url, due)] on the bot's list `name`, recorded for "undo"."""
    h = person["handle"]
    ids = [bot.store.add_todo(h, t, name, item_id=iid, url=url, due_at=due, at=now) for t, iid, url, due in rows]
    bot._wrote(h, "todo_add", f"added {len(ids)} to-do{'s' if len(ids) > 1 else ''} to the list \"{name}\"",
               {"ids": ids}, timed=not undoable)
    return ids


def _app_list(name, app_list, place):
    """The Reminders list: a recipe's title for its ingredients, a list the person named, else the default list."""
    if app_list:
        return app_list.strip()[:60] or None
    if name in (None, "todo", "reminders", "reminder") or name in place.names or named(f"to {name}", None):
        return None
    return name[:1].upper() + name[1:60]


# ---------- the hooks where a to-do or an event is made ----------
def route_todo(bot, person, rows, name, text, now, scheduled=False, run_id=None, app_list=None, undoable=True):
    """rows: [(text, item_id, url, due UTC or None)] for the bot list `name`. None: no outside place is named (the
    caller does today's write). Else (line, to-do ids written, detail for the action log): a preview waiting for a
    yes (nothing written), or today's write made here with the line that says why it is here."""
    d = decide(bot.store, person, "todo", name, text, scheduled)
    if d is None:
        return None
    h, tz = person["handle"], person["timezone"]
    due = rows[0][3] if rows and all(r[3] == rows[0][3] for r in rows) else None
    due_text = None
    if due:
        from .schedule import say_time
        due_text = say_time(due, now, tz)
    if d.use:
        got = _ask_todo(bot, person, d.place, rows, name, app_list, run_id, due_text, now)
        if got[0] != "cap":
            return got[1], [], {"asked": C.CONNECTORS[d.place.connector].actions["todo"], "wanted": d.place.key}
        d = replace(d, use=False, reason="cap")
    ids = write_here(bot, person, rows, name, now, undoable)
    if d.reason == "no_connector" or (_kind(d.place) in ("token", "webhook") and d.reason in ("operator",
                                                                                            "unreachable")):
        bot.store.log_request(h, text or name or "", f"wanted:{d.place.key}")   # the backlog of places people want
    line = T.place_fell_back(clause(d.place, d.reason), [r[0] for r in rows], name, due_text,
                             after(d.place, d.reason))
    return line, ids, {"ids": ids, "list": name, "wanted": d.place.key, "why": d.reason}


def route(bot, ctx, name, params):
    """outputs._perform: todo.add or calendar.add for an outside place. None: today's path. Else the Outcome to log
    under `name` (a preview is "skipped": nothing was done yet)."""
    from .actions import CalendarParams, TodoParams
    from .actions import todo as todo_action
    from .actions.base import Outcome
    from .schema import list_name
    if name not in ("todo.add", "calendar.add"):
        return None
    scheduled = ctx.kind == "scheduled"
    if name == "todo.add":
        p = TodoParams.model_validate(params or {})
        if not ctx.picks:
            return None
        picks = ctx.picks[:1] if p.what == "ingredients" and ctx.kind != "act_on_last" else ctx.picks
        rows, problem = todo_action.rows_for(picks, p.what)
        if problem or not rows:
            return None
        bot_list = list_name(p.list) or "todo"
        got = route_todo(bot, ctx.person, rows, bot_list, ctx.request_text, ctx.now, scheduled=scheduled,
                         run_id=ctx.run_id, app_list=picks[0]["title"] if p.what == "ingredients" else None,
                         undoable=not scheduled)
        if got is None:
            return None
        line, ids, detail = got
        return Outcome("done" if ids else "skipped", line=line, ref=",".join(map(str, ids)) or None, detail=detail)
    d = decide(bot.store, ctx.person, "calendar", None, ctx.request_text, scheduled)
    if d is None:
        return None
    cap = None
    if d.use:
        from .actions import calendar as cal
        ev = cal.event_for(ctx, CalendarParams.model_validate(params or {}))
        if ev is None:
            return None   # the day has passed: calendar.add says so
        got = _ask_event(bot, ctx, d.place, ev, params)
        if got[0] != "cap":
            return Outcome("skipped", line=got[1], detail={"asked": C.CONNECTORS[d.place.connector].actions["calendar"],
                                                           "wanted": d.place.key})
        d, cap = replace(d, use=False, reason="cap"), got[1]
    o = _today("calendar.add", ctx, params)
    if o.status == "done":
        o.line = T.place_link_instead(clause(d.place, d.reason, cap), after(d.place, d.reason)) + " " + o.line
        o.detail = dict(o.detail or {}, wanted=d.place.key, why=d.reason)
    return o


def _today(name, ctx, params):
    """Today's action, as outputs._perform runs it (an error becomes a failed Outcome with the usual line)."""
    from .actions import perform
    from .actions.base import Outcome
    try:
        return perform(name, ctx, params)
    except Exception as e:  # noqa: BLE001 - one failed action never loses the answer
        return Outcome("failed", line=T.ACTION_FAILED.get(name, T.ACTION_FAILED_OTHER), detail={"error": type(e).__name__})


def _already(place):
    con = C.CONNECTORS[place.connector]
    if con.kind != "mac":
        return T.token_already(con.kind, con.apps[place.kind])
    return T.place_already(con.apps[place.kind])


def _ask_todo(bot, person, place, rows, name, app_list, run_id, due_text, now, move_ids=None):
    """("ask", preview) | ("already", line) | ("cap", n)."""
    from .actions import PlaceTodoParams
    h, tz = person["handle"], person["timezone"]
    con = C.CONNECTORS[place.connector]
    action = con.actions["todo"]
    if len(rows) > 40:
        return "cap", 40
    cap = _over_cap(bot.store, h, tz, action, len(rows), now)
    if cap:
        return "cap", cap
    idem = _idem(h, action, run_id, [r[1] or r[0] for r in rows])
    if bot.store.placement_idem(h, idem, now - SAME_ASK):
        return "already", _already(place)
    lst = _app_list(name, app_list, place)
    if con.kind == "token":
        lst = None   # tasks go to the Inbox (or the project in the settings); the preview names no list there
    params = PlaceTodoParams(list=lst, items=[{"title": t[:200], "notes": url or "", "due": _local(due, tz) if due else None}
                                              for t, iid, url, due in rows])
    titles, notes = [i.title for i in params.items], [i.notes for i in params.items]
    plan = {"action": action, "connector": place.connector, "place": place.key, "kind": "todo",
            "params": params.model_dump(mode="json"), "idem": idem, "run_id": run_id, "due_text": due_text,
            "token": C.module(place.connector).yes_token(SimpleNamespace(handle=h), params),
            "fallback": {"kind": "todo", "list": name,
                         "rows": [[t, iid, url, now_iso(due) if due else None] for t, iid, url, due in rows]}}
    if move_ids:
        plan["move_ids"] = list(move_ids)        # "send my list to ticktick": the copies here go once it is there
        plan["fallback"] = {"kind": "keep"}
    _save_ask(bot, h, plan, now)
    if con.kind != "mac":
        return "ask", T.token_ask(con.kind, con.apps["todo"], titles, notes, due_text)
    return "ask", T.place_ask_todo(titles, notes, lst, due_text)


def _ask_event(bot, ctx, place, ev, cal_params):
    from .actions import MacEventParams
    from .actions import calendar as cal
    from .actions import mac
    h, tz = ctx.handle, ev["tz"]
    con = C.CONNECTORS[place.connector]
    action = con.actions["calendar"]
    cap = _over_cap(bot.store, h, ctx.person["timezone"], action, 1, ctx.now)
    if cap:
        return "cap", cap
    if ev["all_day"]:
        start, end = f"{ev['day']:%Y-%m-%d}T00:00", f"{ev['day'] + timedelta(days=1):%Y-%m-%d}T00:00"
    else:
        start, end = _local(ev["start"], tz), _local(ev["end"], tz)
    notes = f"From your saves: {ev['url']}" if ev.get("url") else ""
    params = MacEventParams(calendar=mac.CALENDAR, title=ev["title"][:200], notes=notes, all_day=ev["all_day"],
                            start=start, end=end)
    pick = ctx.picks[0] if ctx.picks else None
    idem = _idem(h, action, ctx.run_id, [(pick or {}).get("item_id") or ev["title"], start])
    if bot.store.placement_idem(h, idem, ctx.now - SAME_ASK):
        return "already", _already(place)
    when = cal.when_words(ev, ctx.now)
    answer = ctx.answer or {}
    plan = {"action": action, "connector": place.connector, "place": place.key, "kind": "calendar",
            "params": params.model_dump(mode="json"), "idem": idem, "run_id": ctx.run_id, "when": when,
            "token": C.module(place.connector).yes_token(SimpleNamespace(handle=h), params),
            "fallback": {"kind": "calendar", "params": dict(cal_params or {}), "picks": [pick] if pick else [],
                         "answer": {"kind": answer.get("kind"), "goal": answer.get("goal")},
                         "rule_id": ctx.rule_id, "request_text": ctx.request_text}}
    _save_ask(bot, h, plan, ctx.now)
    return "ask", T.place_ask_event(params.title, when, notes, params.calendar)


# ---------- the yes (or no) to a preview; REMOVE or KEEP after "disconnect my mac" ----------
_YES_ADD = re.compile(r"^\W*(?:(?:yes|yep|yeah|ok|okay|sure)[\s,!.]*)?(?:please\s+)?(?:add|put)\s+(?:it|them|those|these|"
                      r"that)(?:\s+(?:there|in))?(?:[\s,]+please)?[\s.!]*$|^\W*(?:yes|yep|yeah|ok|okay|sure)[\s,]+please"
                      r"[\s.!]*$", re.I)
_NO_ADD = re.compile(r"^\W*(?:no\s+thanks?|no\s+thank\s+you|leave\s+(?:it|them)|don'?t\s+add\s+(?:it|them))[\s.!]*$", re.I)
REMOVE = re.compile(r"^\W*remove(?:\s+(?:them|those|it|all|everything|them all))?[\s.!]*$", re.I)
KEEP = re.compile(r"^\W*keep(?:\s+(?:them|those|it|them all))?[\s.!]*$", re.I)


def asked_reads(bot, person, text, now):
    """handler._asked_reads: the next message after a preview or after "disconnect my mac". None: not an answer (the
    question is dropped and the message is handled as usual)."""
    ref = _place_answer(bot, person, text, now)
    if ref is not None:
        return ref
    return _remove_answer(bot, person, text, now)


def _open(bot, key, now, life):
    st = bot.store.get_state(key)
    if not st:
        return None
    bot.store.set_state(key, None)   # the next message only
    return st if now - datetime.fromisoformat(st["at"]) <= life else None


def _place_answer(bot, person, text, now):
    h = person["handle"]
    st = _open(bot, f"placeask:{h}", now, ASK_OPEN)
    if not st:
        return None
    if T.YES.match(text) or _YES_ADD.match(text):
        bot.note(intent="place_yes")
        out = None
        for plan in st.get("plans") or []:
            r = run_plan(bot, person, plan, now)
            out = r if out is None else (out + "\n\n") + r
        return bot.send(h, out if out is not None else T.PLACE_LEFT)
    if T.NO.match(text) or _NO_ADD.match(text):
        bot.note(intent="place_no")
        return bot.send(h, T.PLACE_LEFT)
    return None


def _remove_answer(bot, person, text, now):
    h = person["handle"]
    st = _open(bot, f"macremove:{h}", now, REMOVE_OPEN)
    if not st:
        st = _open(bot, f"placeremove:{h}", now, REMOVE_OPEN)   # round 9, E: after "disconnect my ticktick"
        if st:
            return _token_remove_answer(bot, person, st, text, now)
        return None
    if KEEP.match(text):
        bot.note(intent="mac_keep")
        return bot.send(h, T.MAC_KEPT)
    if not REMOVE.match(text):
        return None
    bot.note(intent="mac_remove")
    rows = bot.store.placements(h, ids=st.get("ids") or [])
    if not rows:
        return bot.send(h, T.mac_removed(0, 0, 0))
    mod = C.module("mac")
    if not mod.reachable():
        return bot.send(h, T.MAC_REMOVE_UNREACHABLE)
    res = mod.remove(rows)
    bot.store.remove_placements(res["removed"], now)
    gone = [r for r in rows if r["id"] in res["removed"]]
    failed = [r for r in rows if r["id"] in res["failed"] and r["action"] != "mac.list"]
    return bot.send(h, T.mac_removed(sum(r["action"] == "mac.reminder" for r in gone),
                                     sum(r["action"] == "mac.event" for r in gone), len(failed)))


def _token_remove_answer(bot, person, st, text, now):
    h, key = person["handle"], st["connector"]
    app = C.CONNECTORS[key].apps["todo"]
    if KEEP.match(text):
        bot.note(intent="place_keep")
        return bot.send(h, T.token_kept(app))
    if not REMOVE.match(text):
        return None
    bot.note(intent="place_remove")
    rows = bot.store.placements(h, ids=st.get("ids") or [])
    mod = C.module(key)
    res = mod.remove(rows) if rows and mod.reachable() else {"removed": [], "failed": [r["id"] for r in rows]}
    bot.store.remove_placements(res["removed"], now)
    return bot.send(h, T.token_removed(app, len(res["removed"]), len(res["failed"])))


def run_plan(bot, person, plan, now):
    """Does one previewed thing after the yes, through the registry with the yes token of what was shown. Returns the
    Reply: what was added (and how to undo it), or why not and what was done instead."""
    from .actions import perform, validate_action
    from .actions.base import Ctx
    h = person["handle"]
    key, action, place = plan["connector"], plan["action"], BY_KEY[plan["place"]]
    why = C.unavailable(bot.store, h, key)
    if why:
        return _fallback(bot, person, plan, why, now)
    if bot.store.placement_idem(h, plan["idem"], now - SAME_ASK):
        return Reply.of(_already(place))
    n = len(plan["params"].get("items") or [1])
    cap = _over_cap(bot.store, h, person["timezone"], action, n, now)
    if cap:
        return _fallback(bot, person, plan, "cap", now, cap=cap)
    ctx = Ctx(bot=bot, person=person, answer={}, picks=[], run_id=plan.get("run_id"), kind="act_on_last", now=now,
              tz=person["timezone"])
    try:
        validate_action(action, plan["params"], by="code")
        o = perform(action, ctx, plan["params"], yes_token=plan["token"])
    except C.ConnectorError as e:
        C.failed(bot.store, h, key, e.code, now)
        bot.store.log_action(h, plan.get("run_id"), None, action, "failed", detail={"error": e.code}, at=now)
        return _fallback(bot, person, plan, e.code, now)
    except Exception as e:  # noqa: BLE001 - Refused (a token that is not the rows shown), a bad form: today's action
        bot.store.log_action(h, plan.get("run_id"), None, action, "failed", detail={"error": type(e).__name__}, at=now)
        return _fallback(bot, person, plan, "failed", now)
    if o.status != "done":   # perform's own daily cap (all outside writes together)
        bot.store.log_action(h, plan.get("run_id"), None, action, o.status, detail=o.detail, at=now)
        return _fallback(bot, person, plan, "cap", now, cap=(o.detail or {}).get("cap"))
    placed = (o.detail or {}).get("placed") or []
    ids = [bot.store.add_placement(h, key, x["action"], x["remote_id"], plan.get("run_id"), plan["idem"], now)
           for x in placed]
    C.worked(bot.store, h, key, now)
    bot.store.log_action(h, plan.get("run_id"), None, action, "done", ref=",".join(map(str, ids)),
                         detail={"count": o.detail.get("count"), "placements": ids}, at=now)
    p = plan["params"]
    titles = [i["title"] for i in p["items"]] if plan["kind"] == "todo" else [p["title"]]
    named_ids = [i for i, x in zip(ids, placed) if x["action"] != "mac.list"]
    con = C.CONNECTORS[key]
    one, many = con.nouns[action]
    for i in plan.get("move_ids") or []:   # the list moved there: the copies here are taken off (no double nudges)
        bot.store.update_todo(i, removed_at=now_iso(now))
    if con.kind == "webhook":   # nothing to take back: "undo" says so
        bot._wrote_final(h, "something sent to your webhook")
    else:
        bot._wrote(h, "placed", f"added {len(named_ids)} {one if len(named_ids) == 1 else many} {con.where}",
                   {"ids": ids, "connector": key, "app": _short(place), "moved": plan.get("move_ids") or [],
                    "titles": {str(i): t for i, t in zip(named_ids, titles)}})
    if con.kind != "mac":
        return Reply.of(T.token_done(con.kind, con.apps[place.kind], titles, plan.get("due_text"))
                        + (T.token_moved(len(plan["move_ids"])) if plan.get("move_ids") else ""))
    if plan["kind"] == "todo":
        return Reply.of(T.place_done_todo(titles, p.get("list"), plan.get("due_text")))
    return Reply.of(T.place_done_event(p["title"], p["calendar"], plan.get("when")))


def _fallback(bot, person, plan, reason, now, cap=None):
    """What runs instead of the outside place: the to-dos on the bot's list, or the calendar link."""
    place = BY_KEY[plan["place"]]
    fb = plan["fallback"]
    if fb["kind"] == "keep":   # the to-dos are on the list here already: nothing to write
        return Reply.of(clause(place, reason, cap) + "." + T.LIST_STAYS + after(place, reason))
    if fb["kind"] == "todo":
        rows = [(t, iid, url, datetime.fromisoformat(d) if d else None) for t, iid, url, d in fb["rows"]]
        write_here(bot, person, rows, fb["list"], now)
        return Reply.of(T.place_fell_back(clause(place, reason, cap), [r[0] for r in rows], fb["list"],
                                          plan.get("due_text"), after(place, reason)))
    from .actions.base import Ctx
    from .outputs import OutputsMixin
    ctx = Ctx(bot=bot, person=person, answer=dict(fb.get("answer") or {}, parts=[], picks=fb.get("picks") or []),
              picks=fb.get("picks") or [], run_id=plan.get("run_id"), rule_id=fb.get("rule_id"), kind="act_on_last",
              now=now, tz=person["timezone"], request_text=fb.get("request_text") or "")
    o = _today("calendar.add", ctx, fb.get("params") or {})
    bot.store.log_action(person["handle"], plan.get("run_id"), fb.get("rule_id"), "calendar.add", o.status, ref=o.ref,
                         detail=dict(o.detail or {}, line=o.line, link_part=o.link, wanted=place.key, why=reason),
                         at=now)
    head = T.place_link_instead(clause(place, reason, cap), after(place, reason))
    return head + ("\n\n" if o.line else "") + OutputsMixin._with_lines(None, [("calendar.add", o)])


# ---------- "undo" (handler._undo) and "delete my data" ----------
def undo_text(bot, handle, u, now):
    """Takes out what the last yes added (within 10 minutes), by the ids kept; says what it could not take out."""
    con = C.CONNECTORS.get(u.get("connector") or "mac") or C.CONNECTORS["mac"]
    token = con.kind != "mac"
    gone_line = T.token_undo_gone(con.apps["todo"]) if token else T.PLACE_UNDO_GONE
    rows = bot.store.placements(handle, ids=u.get("ids") or [])
    if not rows:
        return gone_line
    mod = C.module(con.key)
    res = mod.remove(rows) if mod.reachable() else {"removed": [], "failed": [r["id"] for r in rows]}
    bot.store.remove_placements(res["removed"], now)
    if res["removed"] and u.get("moved"):   # "send my list to ticktick" taken back: the list is here again
        for i in u["moved"]:
            bot.store.update_todo(i, removed_at=None)
    titles = u.get("titles") or {}
    gone = [r for r in rows if r["id"] in res["removed"] and r["action"] != "mac.list"]
    left = [titles.get(str(r["id"]), "") for r in rows if r["id"] in res["failed"] and r["action"] != "mac.list"]
    parts = []
    app = u.get("app") or "Reminders"
    if gone:
        say = T.token_undone if token else T.place_undone
        parts.append(T.undone(say(len(gone), app, titles.get(str(gone[0]["id"])))))
    if left:
        parts.append((T.token_undo_failed if token else T.place_undo_failed)(app, left))
    return " ".join(parts) or gone_line


def delete_data_line(store, handle):
    """The line "delete my data" adds when the Mac (or a connector by token) is in use: it stops, and what it added
    stays there."""
    out = T.MAC_DELETE_DATA if C.status(store, handle, "mac") in ("connected", "broken") else ""
    names = [c.name for k, c in C.CONNECTORS.items() if k != "mac" and c.kind == "token"
             and (store.placements(handle, k) or C.status(store, handle, k) in ("connected", "broken"))]
    return out + (T.token_delete_data(names) if names else "")


# ---------- by text: connect, check, what are you connected to, disconnect, from now on ----------
_MAC_WORDS = (r"(?:my\s+|the\s+)?(?:mac|apple\s+reminders|reminders(?:\s+app)?|(?:mac\s+|apple\s+|icloud\s+)?calendar"
              r"(?:\s+app)?|reminders\s+and\s+(?:the\s+)?calendar)(?:\s+on\s+(?:my|the)\s+mac)?")
CONNECT = re.compile(r"^(?:please\s+)?(?:connect|link|set\s*up|hook\s+up)\s+" + _MAC_WORDS + r"$")
CHECK = re.compile(r"^(?:please\s+)?(?:check|test)\s+(?:my\s+|the\s+)?mac(?:\s+again)?$")
DISCONNECT = re.compile(r"^(?:please\s+)?(?:disconnect|unlink)\s+" + _MAC_WORDS + r"$"
                        r"|^(?:please\s+)?stop\s+using\s+" + _MAC_WORDS + r"$")
CONNECTED = re.compile(r"^(?:what|which\s+apps?)\s+(?:are\s+you|you're|are)\s+connected\s+(?:to|with)$"
                       r"|^what\s+(?:can|do)\s+you\s+connect\s+(?:to|with)$|^(?:show\s+)?my\s+connections$"
                       r"|^where\s+can\s+you\s+put\s+things(?:\s+for\s+me)?$")
_LISTS = r"(?:my\s+)?(?:lists?|to-?dos?|todos|tasks|reminders)"
PREF_TODO_ON = re.compile(r"^(?:please\s+)?(?:put|add|send|save)\s+" + _LISTS + r"\s+(?:in|into|to|on)\s+(?:my\s+|the\s+)?"
                          r"(?:apple\s+)?reminders(?:\s+app)?(?:\s+on\s+(?:my|the)\s+mac)?\s+from\s+now\s+on$"
                          r"|^(?:please\s+)?use\s+(?:apple\s+)?reminders(?:\s+app)?\s+for\s+" + _LISTS +
                          r"(?:\s+from\s+now\s+on)?$")
PREF_TODO_OFF = re.compile(r"^(?:please\s+)?(?:use|keep)\s+(?:my|the)\s+lists?\s+here(?:\s+again)?$"
                           r"|^(?:please\s+)?stop\s+putting\s+" + _LISTS + r"\s+in\s+(?:apple\s+)?reminders$")
PREF_CAL_ON = re.compile(r"^(?:please\s+)?put\s+(?:my\s+|new\s+)?events\s+straight\s+(?:in|into|on)\s+(?:my\s+|the\s+)?"
                         r"(?:mac\s+|apple\s+|icloud\s+)?calendar(?:\s+from\s+now\s+on)?$"
                         r"|^(?:please\s+)?put\s+(?:my\s+|new\s+)?events\s+(?:in|into|on)\s+my\s+(?:mac|apple|icloud)\s+"
                         r"calendar\s+from\s+now\s+on$"
                         r"|^(?:please\s+)?use\s+my\s+(?:mac|apple|icloud)\s+calendar\s+for\s+events(?:\s+from\s+now\s+on)?$")
PREF_CAL_OFF = re.compile(r"^(?:please\s+)?(?:use|send\s+me|give\s+me)\s+calendar\s+links\s+again$"
                          r"|^(?:please\s+)?stop\s+putting\s+events\s+(?:straight\s+)?in\s+my\s+(?:mac\s+)?calendar$")


# round 9, E (DESIGN.md section 16.E): the same for TickTick, Todoist and the webhook
_TOK = r"(?P<app>tick\s?tick|todoist|webhook|automation|ifttt|zapier|n8n)"
_TOK_KEY = {"ticktick": "ticktick", "tick tick": "ticktick", "todoist": "todoist"}
T_CONNECT = re.compile(r"^(?:please\s+)?(?:connect|link|set\s*up|hook\s+up)\s+(?:my\s+|the\s+|a\s+)?" + _TOK +
                       r"(?:\s+account)?$")
T_CHECK = re.compile(r"^(?:please\s+)?(?:check|test)\s+(?:my\s+|the\s+)?" + _TOK + r"(?:\s+again)?$")
T_DISCONNECT = re.compile(r"^(?:please\s+)?(?:disconnect|unlink|stop\s+using)\s+(?:my\s+|the\s+)?" + _TOK + r"$")
T_PREF_ON = re.compile(r"^(?:please\s+)?(?:put|add|send|save)\s+" + _LISTS + r"\s+(?:in|into|to|on)\s+(?:my\s+|the\s+)?"
                       + _TOK + r"\s+from\s+now\s+on$")
T_PREF_USE = re.compile(r"^(?:please\s+)?use\s+(?:my\s+)?" + _TOK + r"\s+for\s+" + _LISTS + r"(?:\s+from\s+now\s+on)?$")
T_SEND = re.compile(r"^(?:please\s+)?(?:can\s+you\s+)?(?:add|put|send|push|move|save)\s+(?P<what>.+?)\s+"
                    r"(?:to|in|into|on|onto)\s+(?:my\s+|the\s+)?" + _TOK + r"(?:\s+(?:app|list|inbox|account))?"
                    r"(?:\s+please)?$")
_IT = re.compile(r"^(?:it|this|that|this one|that one)$")
_THEM = re.compile(r"^(?:them|them all|all of them|both|all)$")
_NTH = re.compile(r"^(?:the\s+)?(?:(?P<ord>first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)(?:\s+one)?|"
                  r"(?:number\s+|#\s*)(?P<n>\d{1,2})|(?P<bare>\d{1,2}))$")
_INGR = re.compile(r"^(?:the\s+|its\s+|their\s+)?(?:ingredients|shopping list|groceries)(?:\s+for\s+(?:it|the\s+(?P<ord>first|"
                   r"second|third|fourth|fifth)\s+one))?$")
_MYLIST = re.compile(r"^(?:my|the|our)\s+(?:(?P<name>[a-z][\w-]*)\s+)?(?:list|lists|to-?dos|todos|tasks|to-?do list)$")
_ORDN = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5,
         "5th": 5}


def _tok_key(word):
    w = " ".join(word.lower().split())
    return _TOK_KEY.get(w, "webhook")


def _norm(text):
    t = " ".join((text or "").lower().replace("’", "'").split())
    return re.sub(r"^[\s\"'“”]+|[\s\"'“”.!?]+$", "", t)


def place_reads(bot, person, text, now):
    """handler.answer_normally: the messages above, read by code. None when the message is none of them."""
    t = _norm(text)
    if not t or len(t) > 80:
        return None
    for rx, fn in ((CONNECTED, _connected), (CONNECT, _connect), (CHECK, _check), (DISCONNECT, _disconnect)):
        if rx.match(t):
            bot.note(intent="places")
            return fn(bot, person, now)
    for rx, kind, on in ((PREF_TODO_ON, "todo", True), (PREF_TODO_OFF, "todo", False), (PREF_CAL_ON, "calendar", True),
                         (PREF_CAL_OFF, "calendar", False)):
        if rx.match(t):
            bot.note(intent="places")
            return _pref(bot, person, kind, on)
    return token_reads(bot, person, text, t, now)


def token_reads(bot, person, text, t, now):
    """Round 9, E: connect / check / disconnect a task app or the webhook, "put my to-dos in ticktick from now on",
    and "add it / the ingredients / my list to ticktick". None when the message is none of these."""
    for rx, fn in ((T_CONNECT, _t_connect), (T_CHECK, _t_check), (T_DISCONNECT, _t_disconnect),
                   (T_PREF_ON, _t_pref), (T_PREF_USE, _t_pref)):
        m = rx.match(t)
        if m:
            bot.note(intent="places")
            return fn(bot, person, _tok_key(m.group("app")), now)
    m = T_SEND.match(t)
    if m:
        return _t_send(bot, person, text, m.group("what"), _tok_key(m.group("app")), now)
    return None


def _t_send(bot, person, text, what, key, now):
    """'add it to my ticktick', 'push the second one to my automation', 'put the ingredients in todoist', 'send my
    list to ticktick'. Each goes through the same preview and yes as the Mac (route_todo); a tester gets the list here
    with the honest line."""
    h = person["handle"]
    place = next(p for p in PLACES if p.connector == key)
    bot._tl.msg_text = text
    m = _MYLIST.match(what)
    if m:
        bot.note(intent="places")
        return _t_send_list(bot, person, place, m.group("name"), text, now)
    numbers, kind = None, "pick"
    if _IT.match(what):
        numbers = [1]
    elif _THEM.match(what):
        numbers = None
    elif _NTH.match(what):
        n = _NTH.match(what)
        numbers = [_ORDN[n.group("ord").lower()] if n.group("ord") else int(n.group("n") or n.group("bare"))]
    elif _INGR.match(what):
        kind = "ingredients"
        o = _INGR.match(what).group("ord")
        numbers = [_ORDN[o]] if o else None
    else:
        return None   # "add milk to my ticktick": a to-do typed by the person goes the usual way (todo_add)
    if not bot.store.last_answer(h):
        return None
    bot.note(intent="todo_add")
    return bot._add_picks(person, numbers, place.names[0], kind)


def _t_send_list(bot, person, place, name, text, now):
    from .schema import list_name
    h = person["handle"]
    todos = bot.store.todos(h)
    if name and name not in ("todo", "to-do"):
        todos = [t for t in todos if (t.get("list") or "todo") == list_name(name)]
    if not todos:
        return bot.send(h, T.NO_TODOS)
    d = decide(bot.store, person, "todo", None, text)
    if d is None:
        return None
    if not d.use:
        return bot.send(h, clause(d.place, d.reason) + "." + T.LIST_STAYS + after(d.place, d.reason))
    rows = [(t["text"], t.get("item_id"), t.get("url"), datetime.fromisoformat(t["due_at"]) if t.get("due_at") else None)
            for t in todos]
    due = rows[0][3] if rows and all(r[3] == rows[0][3] for r in rows) else None
    due_text = None
    if due:
        from .schedule import say_time
        due_text = say_time(due, now, person["timezone"])
    got = _ask_todo(bot, person, d.place, rows, None, None, None, due_text, now, move_ids=[t["id"] for t in todos])
    if got[0] == "cap":
        return bot.send(h, clause(d.place, "cap", got[1]) + "." + T.LIST_STAYS)
    return bot.send(h, got[1])


def _only_operator(app):
    line = T.TOKEN_ONLY_OPERATOR.format(app=app)
    return line[:1].upper() + line[1:]


def _t_app(key):
    return C.CONNECTORS[key].apps["todo"]


def _t_word(key):
    return key


def _t_connect(bot, person, key, now):
    h = person["handle"]
    if not config.is_operator(h):
        return bot.send(h, _only_operator(_t_app(key)))
    out = T.TOKEN_SETUP[key]
    if C.module(key).reachable():
        out += "\n" + T.token_set_already(_t_word(key))
    return bot.send(h, out)


def _t_check(bot, person, key, now):
    import os
    h = person["handle"]
    app = _t_app(key)
    if not config.is_operator(h):
        return bot.send(h, _only_operator(app))
    mod = C.module(key)
    if key == "webhook" and (os.environ.get("MVP_WEBHOOK_URL") or "").strip() and not mod.reachable():
        return bot.send(h, T.WEBHOOK_NOT_HTTPS)
    if not mod.reachable():
        return bot.send(h, T.token_check_failed("unreachable", app, _t_word(key)))
    try:
        mod.check()
    except C.ConnectorError as e:
        row = bot.store.connection(h, key)
        bot.store.set_connection(h, key, status="broken" if row and row["status"] == "connected" else
                                 (None if row else "broken"), last_error=e.code, at=now, checked=True)
        return bot.send(h, T.token_check_failed(e.code, app, _t_word(key)))
    bot.store.set_connection(h, key, status="connected", fails=0, last_error="", at=now, checked=True)
    return bot.send(h, T.token_checked(key, app))


def _t_disconnect(bot, person, key, now):
    h = person["handle"]
    app = _t_app(key)
    if not config.is_operator(h):
        return bot.send(h, _only_operator(app))
    row = bot.store.connection(h, key)
    if (row is None and not C.module(key).reachable()) or (row and row["status"] == "off"):
        return bot.send(h, T.token_not_on(app))
    bot.store.set_connection(h, key, status="off", at=now)
    if bot.store.person_context(h)["prefs"].get("place_todo") == key:
        bot.store.set_prefs(h, place_todo=None)
    rows = bot.store.placements(h, key, since=now - LOOK_BACK)
    if rows and C.CONNECTORS[key].kind == "token":
        bot.store.set_state(f"placeremove:{h}", {"at": now_iso(now), "connector": key, "ids": [r["id"] for r in rows]})
    return bot.send(h, T.token_off(key, app, len(rows), _t_word(key)))


def _t_pref(bot, person, key, now):
    h = person["handle"]
    app = _t_app(key)
    if not config.is_operator(h):
        return bot.send(h, _only_operator(app))
    bot.store.set_prefs(h, place_todo=key)
    return bot.send(h, T.token_pref_set(app, C.unavailable(bot.store, h, key) is None, _t_word(key)))


def _email_lines(bot, h):
    """The two email lines of "what are you connected to", true for what runs: with no SMTP here a person on
    Messages gets a link to themselves (slice A, W3) and the test page's outbox holds the rest; the operator's own
    mailbox (W4, A5) sends a draft only after "send"."""
    from .actions import email as E, mailbox, mailbox_imap
    from .actions.base import outbox_reachable, where_outbox
    addr, ok = bot.store.email_of(h)
    if E.smtp_settings():
        email = T.email_status(addr, ok)
    elif outbox_reachable(bot):
        email = T.email_waits(where_outbox(bot))
    else:
        email = T.EMAIL_SELF_LINK
    others = None
    if bot._mailbox_route(h):
        others = T.others_mailbox(mailbox.settings()["address"], mailbox_imap.settings() is not None)
    return email, others


def _connected(bot, person, now):
    h = person["handle"]
    email, others = _email_lines(bot, h)
    if not config.is_operator(h):
        return bot.send(h, T.connected_lines(email, None, others) + "\n" + T.MAC_ONLY_OPERATOR)
    why = C.unavailable(bot.store, h, "mac")
    line = T.MAC_STATUS[why or "connected"]
    if not why and (bot.store.connection(h, "mac") or {}).get("last_error") == "no_calendar":
        line += " (events still come as a link: there's no \"Digest\" calendar)"
    out = T.connected_lines(email, line, others)
    for key, con in C.CONNECTORS.items():   # round 9, E: a task app or the webhook set up here, with its state
        if con.kind != "mac" and (C.module(key).reachable() or bot.store.connection(h, key)):
            out += f"\n• {con.name[:1].upper() + con.name[1:]}: {T.token_status(key, C.unavailable(bot.store, h, key))}."
    if why in (None, "broken"):
        out += "\n" + T.MAC_DISCONNECT_HINT
    return bot.send(h, out)


def _connect(bot, person, now):
    h = person["handle"]
    if not config.is_operator(h):
        return bot.send(h, T.MAC_ONLY_OPERATOR + T.MAC_TESTER_INSTEAD)
    if not C.module("mac").reachable():
        return bot.send(h, T.MAC_UNREACHABLE)
    row = bot.store.connection(h, "mac")
    if row and row["status"] == "connected" and not row.get("last_error"):
        return bot.send(h, T.MAC_CONNECTED)
    return bot.send(h, T.MAC_CONNECT)


def _check(bot, person, now):
    h = person["handle"]
    if not config.is_operator(h):
        return bot.send(h, T.MAC_ONLY_OPERATOR + T.MAC_TESTER_INSTEAD)
    mod = C.module("mac")
    if not mod.reachable():
        return bot.send(h, T.MAC_UNREACHABLE)
    try:
        got = mod.check()
    except C.ConnectorError as e:
        row = bot.store.connection(h, "mac")
        if row:   # a connection that stops working is broken until a check passes; one never made stays unmade
            bot.store.set_connection(h, "mac", status="broken" if row["status"] == "connected" else None,
                                     last_error=e.code, at=now, checked=True)
        return bot.send(h, T.mac_check_failed(e.code, e.app))
    bot.store.set_connection(h, "mac", status="connected", fails=0, last_error="" if got["calendar"] else "no_calendar",
                             at=now, checked=True)
    return bot.send(h, T.MAC_CONNECTED if got["calendar"] else T.MAC_CONNECTED_NO_CALENDAR)


def _disconnect(bot, person, now):
    h = person["handle"]
    if not config.is_operator(h):
        return bot.send(h, T.MAC_ONLY_OPERATOR)
    row = bot.store.connection(h, "mac")
    if row is None or row["status"] == "off":
        return bot.send(h, T.MAC_NOT_ON)
    bot.store.set_connection(h, "mac", status="off", at=now)
    prefs = bot.store.person_context(h)["prefs"]
    for k in ("place_todo", "place_calendar"):
        if prefs.get(k) == "mac":
            bot.store.set_prefs(h, **{k: None})
    rows = bot.store.placements(h, "mac", since=now - LOOK_BACK)
    n_rem = sum(r["action"] == "mac.reminder" for r in rows)
    n_ev = sum(r["action"] == "mac.event" for r in rows)
    if n_rem or n_ev:
        bot.store.set_state(f"macremove:{h}", {"at": now_iso(now), "ids": [r["id"] for r in rows]})
    return bot.send(h, T.mac_off(n_rem, n_ev))


def _pref(bot, person, kind, on):
    h = person["handle"]
    key = "place_todo" if kind == "todo" else "place_calendar"
    if not on:
        bot.store.set_prefs(h, **{key: None})
        return bot.send(h, T.PLACE_PREF_TODO_OFF if kind == "todo" else T.PLACE_PREF_CAL_OFF)
    if not config.is_operator(h):
        return bot.send(h, T.MAC_ONLY_OPERATOR + T.MAC_TESTER_INSTEAD)
    bot.store.set_prefs(h, **{key: "mac"})
    return bot.send(h, T.place_pref_set(kind, C.unavailable(bot.store, h, "mac") is None))
