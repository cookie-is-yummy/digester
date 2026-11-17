"""PROTOTYPE ONLY - to-dos (DESIGN.md sections 2 and 11) and library counts (section 11 'library_stats').

To-dos: one table, several named lists ("todo" by default), one numbering across all lists so "done 3" always means
the same thing. A to-do with a due time reminds once through the scheduler, with the same guards as a timed rule. A
pick of the last answer is added with a title made from the item's own words; its ingredients only from lines that
code already checked against the item's text. Library counts are worked out by code only; friends' posts are not
counted (LibraryView leaves them out). Mixed into core.Bot.
"""
import re
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import texts as T
from .channels.base import SendUncertain
from .schedule import _at, end_of_quiet, in_quiet_hours, say_time
from .store import by_number, now_iso

UNDO_WINDOW = timedelta(minutes=10)
OVERDUE_AFTER = timedelta(hours=24)   # round 8: a to-do this far past its due time gets one nudge ...
OVERDUE_LOOK_DAYS = 7                 # ... unless it is older than this (a store's old to-dos are never all nudged)
OVERDUE_OPEN = timedelta(hours=12)    # checker, round 8: one nudge at a time waits this long for its answer
WORD = re.compile(r"[^\W_]+", re.UNICODE)
SMALL = set("a an the my to of for on in at and".split())
# fix pass, finding 3: "add oat milk and eggs to my grocery list" is two to-dos on the list "grocery". The list's name
# never stays in an item's text, and a few fixed pairs stay one thing.
LIST_TAIL = re.compile(r"\s+(?:to|on|onto|in|into|for)\s+(?:my|the|our)\s+((?:[^\W\d_][\w-]*\s+){0,2}?)"
                       r"(?:to-?do\s+|todo\s+)?list\b.*$", re.I)
LEAD_ADD = re.compile(r"^\s*(?:please\s+)?(?:add|put|jot down|jot|write down|stick|pop|throw)\s+", re.I)
SPLIT = re.compile(r"\s*,\s*(?:and\s+|&\s+)?|\s+and\s+|\s*&\s*|\s*\+\s*", re.I)
PAIRS = {"mac and cheese", "salt and pepper", "peanut butter and jelly", "fish and chips", "bread and butter",
         "rock and roll", "pros and cons", "oil and vinegar", "black and white", "sweet and sour", "rice and beans",
         "chips and salsa", "milk and cookies", "bacon and eggs", "ham and cheese", "spaghetti and meatballs",
         "strawberries and cream", "cookies and cream", "pb and j", "fruit and nut", "salt and vinegar"}


VERBS = set("""call buy get pick email text book pay clean fix send make finish do go take write read watch check ring
    phone order return cancel renew wash cook bake visit meet tell ask help water feed walk mail post print sign file
    submit prepare plan schedule book review practise practice study learn find look""".split())


# ---------- round 9, W10 (DESIGN.md section 16.F): "do 2 for me" on the to-do list ----------
DOIT_VIEW = timedelta(hours=24)   # a list shown this long ago (with no newer answer) is still "in view"
DOIT_ASK = timedelta(hours=24)    # "tell me when" after a to-do the bot can't do: the next message only
_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
        "sixth": 6, "6th": 6, "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9, "tenth": 10,
        "10th": 10}
_DOIT = re.compile(
    r"^\W*(?:(?:please|ok|okay|so|hey)[\s,]+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:please\s+)?"
    r"(?P<verb>do|handle|take\s+care\s+of|help\s+(?:me\s+)?with|deal\s+with|sort\s+out)\s+"
    r"(?:(?P<it>it|that|this|that\s+one|this\s+one)"
    r"|(?P<todo>(?:my\s+)?(?:to-?do|todo|task)\s+(?:number\s+|#\s*)?)?(?:number\s+|#\s*)?(?P<n>\d{1,2})"
    r"|the\s+(?P<ord>" + "|".join(_ORD) + r")(?:\s+(?:one|to-?do|todo|task))?"
    r"|the\s+(?P<words>[^\W\d_][\w' -]{1,40}?)\s+(?:one|to-?do|todo|task))"
    r"(?P<forme>\s+for\s+me)?(?:[\s,]+(?:please|pls|thanks))?\W*$", re.I)
EMAIL_TODO = re.compile(r"^\W*e-?mail\b", re.I)
BUY_TODO = re.compile(r"^\W*(?:buy|get|pick\s+up|order|grab)\b", re.I)
CALL_TODO = re.compile(r"^\W*(?:call|ring|phone|text)\b", re.I)
APPLY_TODO = re.compile(r"\b(?:apply|application|sign\s+up|register|enrol+)\b", re.I)
BOOK_TODO = re.compile(r"\b(?:book|reserve|reservation|table\s+(?:at|for))\b", re.I)


def doit_request(text):
    """{"number", "words", "said_todo"} for a W10 message, else None. A bare "do it" is never one (it is a yes), nor is
    "do 2" (a numbered offer's choice): "do" needs "for me", a to-do word or an ordinal."""
    t = " ".join((text or "").split())
    if not t or len(t) > 80:
        return None
    m = _DOIT.match(t)
    if not m:
        return None
    verb = m.group("verb").lower()
    if verb == "do" and not (m.group("forme") or m.group("todo") or m.group("ord") or m.group("words")
                             or re.search(r"\b(?:number|#)", t, re.I)):
        return None
    if m.group("it") and not m.group("forme"):
        # "do it" is a yes; (round 9 checks) "handle it" and "take care of it" are ordinary words about whatever was
        # just shown (an answer, a draft): only "<verb> it for me" asks W10 to do a to-do
        return None
    if m.group("words") and m.group("words").lower().split()[0] in ("first", "last", "next", "other", "same", "whole"):
        return None
    number = int(m.group("n")) if m.group("n") else _ORD.get((m.group("ord") or "").lower())
    return {"number": number, "words": None if number else m.group("words"), "said_todo": bool(m.group("todo"))}


# lists people name without "my ... list" ("add eggs to groceries"); the person's own list names count too
COMMON_LISTS = ("groceries", "grocery", "shopping", "packing")


def split_todo(text, lists=()):
    """(items, list name or None): the things one to-do text names, without the list phrase. `lists`: names of the
    person's lists (and the list the form named), so "eggs and bread to groceries" loses "to groceries" too."""
    from .schema import list_name
    t = " ".join((text or "").split())
    name = None
    m = LIST_TAIL.search(t)
    if m:
        name = list_name(m.group(1).strip() or "todo")
        t = t[:m.start()]
    else:
        names = sorted({x.lower() for x in (*lists, *COMMON_LISTS) if x and x != "todo"}, key=len, reverse=True)
        if names:
            bare = re.search(r"\s+(?:to|on|onto|in|into|for)\s+(?:(?:my|the|our)\s+)?(" + "|".join(map(re.escape, names))
                             + r")(?:\s+list)?\s*[.!]*$", t, re.I)
            if bare:
                name = list_name(bare.group(1))
                t = t[:bare.start()]
    t = LEAD_ADD.sub("", t).strip(" .,;")
    if not t:
        return [], name
    low = t.lower()
    if low in PAIRS or not SPLIT.search(t) or low.split()[0] in VERBS:   # "call mum and dad" is one thing to do
        return [t], name
    protected = low
    for i, pair in enumerate(PAIRS):   # a fixed pair inside a longer list stays whole
        protected = protected.replace(pair, pair.replace(" and ", f" \x00{i}\x00 "))
    parts, out, pos = SPLIT.split(protected), [], 0
    for part in parts:
        part = re.sub(r" \x00\d+\x00 ", " and ", part).strip(" .,;")
        if part:
            k = low.find(part, pos)
            out.append(t[k:k + len(part)] if k >= 0 else part)
            pos = max(pos, k + len(part)) if k >= 0 else pos
    return (out or [t]), name


class TodoMixin:
    # ---------- the last write, for "undo" (section 11) ----------
    def _wrote(self, handle, kind, say, undo, timed=False):
        """The last write, for "undo". A write a timed send made (timed=True) is kept apart: "undo" reverses the
        person's own last write first, and the timed one only when they made none in the last 10 minutes (review fix
        S4)."""
        key = f"lastwrite_timed:{handle}" if timed else f"lastwrite:{handle}"
        # (round 9 checks) "answer": the answer in view when it was written, so W10's "do it for me" can tell whether
        # a newer answer came after the to-do (then "it" is that answer's, not the to-do's)
        self.store.set_state(key, {"kind": kind, "say": say, "undo": undo, "at": now_iso(self.clock()),
                                   "answer": (self.store.last_answer(handle) or {}).get("run_id")})

    def _wrote_final(self, handle, what):
        """Review fix S5: something "undo" cannot reverse (an email, a calendar link, feedback, an address) is the last
        thing the person did, so "undo" says so instead of reaching back to an older write."""
        self._wrote(handle, "final", what, {})

    def _last_write(self, handle, now):
        for key in (f"lastwrite:{handle}", f"lastwrite_timed:{handle}"):
            lw = self.store.get_state(key)
            if lw and datetime.fromisoformat(lw["at"]) >= now - UNDO_WINDOW:
                return dict(lw, key=key)
        return None

    def _last_write_ctx(self, handle, now):
        lw = self._last_write(handle, now)
        if not lw:
            return None
        mins = int((now - datetime.fromisoformat(lw["at"])).total_seconds() // 60)
        ago = "just now" if mins < 1 else f"{mins} minute{'s' if mins != 1 else ''} ago"
        return {"ago": ago, "say": lw["say"]}

    # ---------- reading the person's words ----------
    def _due_from(self, it, person, now):
        """A to-do's due moment (aware UTC) from in_minutes or a local 'YYYY-MM-DD[THH:MM]'; a date alone is 9am. A
        moment that has passed gives None (no reminder)."""
        if it.in_minutes:
            return now + timedelta(minutes=it.in_minutes)
        if not it.due:
            return None
        tz = ZoneInfo(person["timezone"])
        if len(it.due) <= 10:   # no time named: 9am, or the end of their quiet hours if later (review fix S11)
            due = _at(datetime.fromisoformat(it.due).date(), "09:00", tz)
            quiet = self.store.quiet(person["handle"])
            if in_quiet_hours(due, person["timezone"], quiet):
                due = end_of_quiet(due, person["timezone"], quiet)
        else:
            due = datetime.fromisoformat(it.due).replace(tzinfo=tz)
        return due if due > now else None

    def _find_todos(self, handle, it):
        """([(number, row)], None) or ([], reply)."""
        todos = self.store.todos(handle)
        if not todos:
            return [], T.NO_TODOS
        if it.todo_number:
            if any(not 1 <= n <= len(todos) for n in it.todo_number):
                return [], T.todo_numbers_unknown(len(todos))
            return [(n, todos[n - 1]) for n in dict.fromkeys(it.todo_number)], None
        from .retrieve import _stem
        want = [_stem(w) for w in WORD.findall((it.todo_text or "").lower()) if w not in SMALL]
        exact = [(i, t) for i, t in enumerate(todos, 1) if t["text"].strip().lower() == (it.todo_text or "").strip().lower()]
        if exact:
            return exact[:1], None
        hits = [(i, t) for i, t in enumerate(todos, 1)
                if want and all(w in {_stem(x) for x in WORD.findall(t["text"].lower())} for w in want)]
        if not hits:
            return [], T.TODO_NOT_FOUND
        if len(hits) > 1:
            return [], T.which_todo(hits)
        return hits, None

    # ---------- the intents ----------
    def _todo_add(self, person, it, now):
        h = person["handle"]
        name = it.todo_list or "todo"
        due = self._due_from(it, person, now)
        # a time that has passed sets no reminder, and the reply says so
        tail = " " + T.TODO_DUE_PASSED if (it.due or it.in_minutes) and due is None else ""
        if it.pick_number or it.what == "ingredients":
            return self._add_picks(person, [it.pick_number] if it.pick_number else None, name, it.what or "pick", due,
                                   tail=tail)
        known = {t.get("list") for t in self.store.todos(h)} | ({name} if it.todo_list else set())
        texts, named = split_todo(it.todo_text, lists=[x for x in known if x])
        if named and named != "todo" and name == "todo":
            name = named
        texts = texts or [it.todo_text]
        # round 9, slice D (C2, C3; DESIGN.md section 16.D): a list named after an app ("add milk to my notion",
        # "add call mum to my apple reminders"): a preview for the Mac that waits for a yes, or the list here with a
        # line that says why. None: today's write below.
        from .places import route_todo
        got = route_todo(self, person, [(x, None, None, due) for x in texts], name, getattr(self._tl, "msg_text", ""),
                         now)
        if got is not None:
            return self.send(h, got[0] + tail)
        ids = [self.store.add_todo(h, x, name, due_at=due, at=now) for x in texts]
        self._wrote(h, "todo_add", f"added to-do{'s' if len(ids) > 1 else ''} " + "; ".join(f"\"{x}\"" for x in texts)
                    + f" to the list \"{name}\"", {"ids": ids})
        return self.send(h, T.todos_added(texts, name, say_time(due, now, person["timezone"]) if due else None)
                         + tail)

    def _answer_for(self, h, answer_ref=None):
        """The answer a person points at: the last one, or with answer_ref a rule number, that rule's latest send."""
        if answer_ref and str(answer_ref).strip().isdigit():
            r = by_number(self.store.rules(h), int(str(answer_ref).strip()))
            if r is None:
                return None
            row = self.store.one("SELECT run_id FROM deliveries WHERE handle=? AND rule_id=? ORDER BY run_id DESC "
                                 "LIMIT 1", (h, r["id"]))
            if not row:
                return None
            rows = self.store.items_of_run(row["run_id"])
            return {"run_id": row["run_id"], "rule_id": r["id"], "items": [x["item_id"] for x in rows]}
        return self._answer_seen(h)

    def _add_picks(self, person, numbers, name="todo", what="pick", due=None, answer_ref=None, tail=""):
        """Picks of the last answer (each one's checked title and link), or the checked ingredient lines of one pick,
        go on a list. Nothing is written unless everything asked for can be added. The writing is actions/todo.py,
        the same code a rule's or an ask's `do: todo.add` runs."""
        from .actions import todo as todo_action
        h = person["handle"]
        picks, _, answer, problem = self._answer_picks(h, numbers, answer_ref, what)
        if problem:
            return self.send(h, problem + tail)
        # round 9, slice D (C2, C3; DESIGN.md section 16.D): the same for picks and their ingredients
        rows, missing = todo_action.rows_for(picks, what, due)
        if not missing and rows:
            from .places import route_todo
            got = route_todo(self, person, rows, name, getattr(self._tl, "msg_text", ""), self.clock(),
                             run_id=(answer or {}).get("run_id"),
                             app_list=picks[0]["title"] if what == "ingredients" else None)
            if got is not None:
                return self.send(h, got[0] + tail)
        out = todo_action.add(self, person, picks, what, name, due)
        return self.send(h, out.line + tail)

    def _todo_list(self, person, it, now):
        h = person["handle"]
        todos = self.store.todos(h)
        name = it.todo_list if it.todo_list and it.todo_list != "todo" else None
        shown = [(i, t) for i, t in enumerate(todos, 1) if not name or (t.get("list") or "todo") == name]
        if not shown:
            return self.send(h, T.NO_TODOS)
        lists = {t.get("list") or "todo" for _, t in shown}
        lines = [T.todo_list_head(name)]
        for i, t in shown:
            due = say_time(datetime.fromisoformat(t["due_at"]), now, person["timezone"]) if t.get("due_at") else None
            lines.append(T.todo_line(i, t, due, show_list=len(lists) > 1))
        lines.append(T.TODO_FOOT)
        self._todo_view_mark(h, now)   # round 9, W10: "do 2 for me" now means to-do 2
        return self.send(h, "\n".join(lines))

    def _todo_change(self, person, it, now):
        """todo_done, todo_remove, todo_due."""
        h = person["handle"]
        found, problem = self._find_todos(h, it)
        if problem:
            return self.send(h, problem)
        at = now_iso(now)
        texts = [t["text"] for _, t in found]
        if it.intent == "todo_due":
            due = self._due_from(it, person, now)
            if due is None:
                return self.send(h, T.TIME_PASSED)
            old = [{"id": t["id"], "due_at": t["due_at"], "reminded_at": t["reminded_at"]} for _, t in found]
            for _, t in found:
                self.store.update_todo(t["id"], due_at=now_iso(due), reminded_at=None)
            self._wrote(h, "todo_due", f"set a reminder for \"{texts[0]}\"", {"rows": old})
            return self.send(h, T.todo_due_set("; ".join(texts), say_time(due, now, person["timezone"])))
        col = "done_at" if it.intent == "todo_done" else "removed_at"
        for _, t in found:
            self.store.update_todo(t["id"], **{col: at})
        verb = "ticked off" if col == "done_at" else "removed"
        self._wrote(h, it.intent, f"{verb} " + "; ".join(f"\"{x}\"" for x in texts),
                    {"ids": [t["id"] for _, t in found], "col": col})
        if col == "done_at":
            return self.send(h, T.todos_done(texts, len(self.store.todos(h))))
        return self.send(h, T.todos_removed(texts))

    def _todos_text(self, handle):
        """The open list, as a rule with source 'todos' sends it."""
        todos = self.store.todos(handle)
        if not todos:
            return T.TODO_LIST_EMPTY_SEND, 0
        lists = {t.get("list") or "todo" for t in todos}
        now = self.clock()
        person = self.store.person(handle)
        lines = [T.todo_list_head()]
        for i, t in enumerate(todos, 1):
            due = say_time(datetime.fromisoformat(t["due_at"]), now, person["timezone"]) if t.get("due_at") else None
            lines.append(T.todo_line(i, t, due, show_list=len(lists) > 1))
        return "\n".join(lines), len(todos)

    # ---------- due to-dos: one reminder each, through the scheduler's guards ----------
    def _tick_todos(self, now):
        from .scheduler import MISSED_AFTER
        sent = 0
        for t in self.store.due_todos(now):
            person = self.store.person(t["handle"])
            if not person:
                continue
            with self.lock_for(person["handle"]):
                t = self.store.todo(t["id"])
                person = self.store.person(person["handle"])   # review fix S1: a snooze or a stop made meanwhile
                if not person or not t or t["reminded_at"] or t["done_at"] or t["removed_at"] or t["due_at"] > now_iso(now):
                    continue
                h, tz = person["handle"], person["timezone"]

                def record(status, h=h, todo_id=t["id"]):
                    self.store.add_run(handle=h, kind="todo", status=status, at=now_iso(now))
                    self.store.update_todo(todo_id, reminded_at=now_iso(now))
                if person["paused"]:
                    record("paused")
                    continue
                if now - datetime.fromisoformat(t["due_at"]) > MISSED_AFTER:
                    record("missed")   # review fix S3: and the person is told, once (held through quiet hours)
                    self._notice(h, T.missed_todo(t["text"], say_time(datetime.fromisoformat(t["due_at"]), now, tz)),
                                 now)
                    continue
                snooze = person.get("snooze_until")
                if snooze and now < datetime.fromisoformat(snooze):
                    record("snoozed")
                    continue
                # review fix S12: the person set this time themselves, so the daily limit of timed sends does not
                # move it to the next morning without a word (it still counts toward that limit)
                # recorded before the send, as for a rule: a crash from here on can lose this reminder but never
                # send it twice; a clear failure is tried again next tick, until it is too late (missed)
                self.store.update_todo(t["id"], reminded_at=now_iso(now))
                run_id = self.store.add_run(handle=h, kind="todo", status="sending", at=now_iso(now))
                try:
                    self.send(h, T.todo_reminder(t["text"]), run_id)   # a time the person named: honoured in quiet hours
                except SendUncertain:   # it may have gone out: never again
                    self.store.x("UPDATE runs SET status='unknown', error='SendUncertain' WHERE id=?", (run_id,))
                    continue
                except Exception as e:  # noqa: BLE001 - one to-do never blocks the others
                    self.store.x("UPDATE runs SET status='send_failed', error=? WHERE id=?", (type(e).__name__, run_id))
                    self.store.update_todo(t["id"], reminded_at=None)
                    continue
                self.store.x("UPDATE runs SET status='sent' WHERE id=?", (run_id,))
                sent += 1
        return sent + self._tick_overdue(now)

    # ---------- round 8, BN2 (c): one nudge for a to-do a day past due ----------
    def _tick_overdue(self, now):
        """A to-do due more than 24 hours ago (and at most OVERDUE_LOOK_DAYS ago), not done or removed, gets one nudge.
        Quiet hours, a snooze, the person's kill switch and the daily limit make it wait (it goes out once they end,
        never lost and never twice); "no overdue nudges" stops them. The reply to it is read by code
        (_overdue_reply)."""
        from . import config
        from .scheduler import MISSED_AFTER
        sent = 0
        for t in self.store.overdue_todos(now - OVERDUE_AFTER, now - timedelta(days=OVERDUE_LOOK_DAYS)):
            person = self.store.person(t["handle"])
            if not person:
                continue
            with self.lock_for(person["handle"]):
                t = self.store.todo(t["id"])
                person = self.store.person(person["handle"])
                if not person or not t or t["done_at"] or t["removed_at"] or t.get("overdue_at"):
                    continue
                if t.get("reminded_at") and datetime.fromisoformat(t["reminded_at"]) - \
                        datetime.fromisoformat(t["due_at"]) > MISSED_AFTER:
                    continue   # its reminder was missed while the bot was off, and that notice said it is still listed
                h, tz = person["handle"], person["timezone"]
                if person["paused"] or self.store.person_context(h)["prefs"].get("overdue_nudges") is False:
                    continue
                if self._held_now(person, now):   # quiet hours or a snooze: it waits
                    continue
                open_q = self.store.get_state(f"overdue:{h}")
                if open_q and open_q.get("todo_id") != t["id"] and \
                        datetime.fromisoformat(open_q["at"]) > now - OVERDUE_OPEN:
                    continue   # checker, round 8: one nudge waits for its answer, so "drop it" is never about the other
                    # one (the next goes out once they reply, or OVERDUE_OPEN later)
                midnight = _at(now.astimezone(ZoneInfo(tz)).date(), "00:00", ZoneInfo(tz))
                if self.store.scheduled_today(h, midnight) >= config.MAX_SCHEDULED_PER_DAY:
                    continue   # it counts toward the daily limit: tomorrow, then
                numbers = [x["id"] for x in self.store.todos(h)]
                if t["id"] not in numbers:
                    continue
                due = datetime.fromisoformat(t["due_at"]).astimezone(ZoneInfo(tz))
                days = (now.astimezone(ZoneInfo(tz)).date() - due.date()).days
                when = "yesterday" if days == 1 else f"on {due.strftime('%A %-d %B')}"
                self.store.update_todo(t["id"], overdue_at=now_iso(now))   # before the send: never twice
                run_id = self.store.add_run(handle=h, kind="todo", status="sending", at=now_iso(now))
                try:
                    self.send(h, T.overdue_nudge(t["text"], when, numbers.index(t["id"]) + 1), run_id)
                except SendUncertain:
                    self.store.x("UPDATE runs SET status='unknown', error='SendUncertain' WHERE id=?", (run_id,))
                    continue
                except Exception as e:  # noqa: BLE001 - tried again at the next tick
                    self.store.x("UPDATE runs SET status='send_failed', error=? WHERE id=?", (type(e).__name__, run_id))
                    self.store.update_todo(t["id"], overdue_at=None)
                    continue
                self.store.x("UPDATE runs SET status='sent' WHERE id=?", (run_id,))
                self.store.set_state(f"overdue:{h}", {"todo_id": t["id"], "at": now_iso(now)})
                self._todo_view_mark(h, now)   # round 9, W10: the nudge says the to-do's number
                sent += 1
        return sent

    def _overdue_reply(self, person, text, now):
        """The message right after an overdue nudge: "tomorrow" moves the to-do to tomorrow at its own clock time (its
        reminder comes again), "drop it" takes it off the list, and a bare "done" ("did it", "finished") ticks it off
        (merge of round 8: "done" right after the nudge is about that to-do, not feedback on an older answer). Any
        other message ends the question (None)."""
        from .followup import DONE_BARE, OVERDUE_DROP, OVERDUE_TOMORROW
        h = person["handle"]
        st = self.store.get_state(f"overdue:{h}")
        if not st:
            return None
        self.store.set_state(f"overdue:{h}", None)
        t = self.store.todo(st["todo_id"])
        if not t or t["handle"] != h or t["done_at"] or t["removed_at"]:
            return None
        tz = ZoneInfo(person["timezone"])
        if OVERDUE_TOMORROW.match(text):
            self.note(intent="todo_due")
            due = datetime.fromisoformat(t["due_at"]).astimezone(tz)
            new = _at(now.astimezone(tz).date() + timedelta(days=1), due.strftime("%H:%M"), tz)
            self._wrote(h, "todo_due", f"moved \"{t['text']}\" to tomorrow",
                        {"rows": [{"id": t["id"], "due_at": t["due_at"], "reminded_at": t["reminded_at"],
                                   "overdue_at": t.get("overdue_at")}]})
            self.store.update_todo(t["id"], due_at=now_iso(new), reminded_at=None, overdue_at=None)
            return self.send(h, T.overdue_moved(t["text"], say_time(new, now, person["timezone"])))
        if DONE_BARE.match(text) and not self.store.one(
                "SELECT id FROM runs WHERE handle=? AND kind='scheduled' AND status IN ('sent','unknown') AND at>? "
                "LIMIT 1", (h, st["at"])):   # a timed send after the nudge: "done" may be about that one
            self.note(intent="todo_done")
            self.store.update_todo(t["id"], done_at=now_iso(now))
            self._wrote(h, "todo_done", f"ticked off \"{t['text']}\"", {"ids": [t["id"]], "col": "done_at"})
            return self.send(h, T.todos_done([t["text"]], len(self.store.todos(h))))
        if OVERDUE_DROP.match(text):
            self.note(intent="todo_remove")
            self.store.update_todo(t["id"], removed_at=now_iso(now))
            self._wrote(h, "todo_remove", f"removed \"{t['text']}\"", {"ids": [t["id"]], "col": "removed_at"})
            return self.send(h, T.overdue_dropped(t["text"]))
        return None

    # ---------- round 9, W10 (DESIGN.md section 16.F): "do 2 for me" hands a to-do to the helper that fits ----------
    def _todo_view_mark(self, h, now):
        """The to-do list was just shown: a number in "do 2 for me" means a to-do while no newer answer came."""
        last = self.store.last_answer(h) or {}
        self.store.set_state(f"todoview:{h}", {"at": now_iso(now), "run_id": last.get("run_id")})
        # (round 9 checks, acts) a newer numbered list replaces an open offer menu, as a new answer does
        # (outputs._keep_answer): "2" or "do 2" now means the list's number, never an older menu's offer
        self.store.set_state(f"offers:{h}", None)

    def _todos_in_view(self, h, now):
        st = self.store.get_state(f"todoview:{h}")
        last = self.store.last_answer(h)
        if st and now - datetime.fromisoformat(st["at"]) <= DOIT_VIEW and (last or {}).get("run_id") == st.get("run_id"):
            return True
        return last is None   # no answer was ever shown: a number can only mean a to-do

    def do_it(self, person, text, now):
        """W10: "do it for me", "do 3 for me", "can you do number 2", "do the first one", "help me with 2", "handle the
        landlord one", "take care of the first one". Code only, no model call. None when the message is not one of
        these (or a rule preview waits: its "do it" is a yes, as today)."""
        h = person["handle"]
        req = doit_request(text)
        if req is None:
            return None
        pending = self._live_pending(h, now)
        if pending and pending["kind"] == "confirm_rule":
            return None
        todos = self.store.todos(h)
        n, row = None, None
        if req["number"] is not None:
            if not req["said_todo"] and not self._todos_in_view(h, now):
                return None   # "do 2 for me" right after an answer: the number may be a pick; the usual path reads it
            self.note(intent="do_it")
            if not todos:
                return self.send(h, T.NO_TODOS)
            if not 1 <= req["number"] <= len(todos):
                return self.send(h, T.todo_numbers_unknown(len(todos)))
            n, row = req["number"], todos[req["number"] - 1]
        elif req["words"]:
            from .retrieve import _stem
            want = {_stem(w) for w in WORD.findall(req["words"].lower()) if w not in SMALL}
            hits = [(i, t) for i, t in enumerate(todos, 1)
                    if want and want <= {_stem(x) for x in WORD.findall(t["text"].lower())}]
            if not hits:
                return None   # "handle the landlord one" with no such to-do: not about the list
            self.note(intent="do_it")
            if len(hits) > 1:
                return self.send(h, T.which_todo(hits))
            n, row = hits[0]
        else:   # "it": the one to-do just added, or the only one on a list just shown
            self.note(intent="do_it")
            lw = self._last_write(h, now)
            ids = (lw or {}).get("undo", {}).get("ids") if (lw or {}).get("kind") == "todo_add" else None
            if ids and lw.get("answer") != (self.store.last_answer(h) or {}).get("run_id"):
                return None   # (round 9 checks) an answer came after the to-do: "it" is about that answer
            if ids and len(ids) == 1:
                n, row = next(((i, t) for i, t in enumerate(todos, 1) if t["id"] == ids[0]), (None, None))
            elif len(todos) == 1 and self._todos_in_view(h, now) and self.store.get_state(f"todoview:{h}"):
                n, row = 1, todos[0]
            if row is None:
                return self.send(h, T.DOIT_WHICH)
        return self._do_todo(person, n, row, now, said=text)

    def _do_todo(self, person, n, row, now, said=""):
        """The to-do's helper by what its words say: an email (drafts), a cancel (cancel), a programme or a place from a
        pick (the apply or book menu); else a plain line that says what the bot can't do and offers a reminder."""
        from . import cancel as cancel_mod
        h = person["handle"]
        text = row["text"]
        tail = T.doit_tick(n)
        ref = self.draft_from_todo(person, row, now, job=f"todo:{row['id']}") if EMAIL_TODO.match(text) else None
        if ref is not None:
            self.send(h, tail)
            return ref
        if cancel_mod.from_todo(person, row, now) is not None:
            last = self.store.one("SELECT MAX(id) AS n FROM cancellations WHERE handle=?", (h,))
            self.store.set_state(f"doit:{h}", {"todo_id": row["id"], "kind": "cancel", "after": (last or {}).get("n") or 0,
                                               "at": now_iso(now)})
            ref = self.cancel_todo(person, row, now)
            if ref is not None:
                self.send(h, tail)
                return ref
        if row.get("item_id"):
            rec = self._todo_rec(person, row)
            if rec is not None:
                snap = {"run_id": None, "picks": []}
                if BOOK_TODO.search(text):
                    # (round 9 checks) the to-do's words came from a post: never its day or time for the hold
                    ref = self._book_menu(person, rec, snap, text, now, when_text=said)
                    self.send(h, tail)
                    return ref
                if APPLY_TODO.search(text) or (not BUY_TODO.match(text) and self._thing_date(rec, now, person)
                                               and self._is_deadline(rec, person)):
                    ref = self._apply_menu(person, rec, snap, text, now)
                    self.send(h, tail)
                    return ref
        self.store.set_state(f"doitask:{h}", {"todo_id": row["id"], "at": now_iso(now)})
        if BUY_TODO.match(text):
            return self.send(h, T.doit_buy(n))
        if CALL_TODO.match(text):
            return self.send(h, T.DOIT_CALL)
        return self.send(h, T.doit_none(text))

    def _todo_rec(self, person, row):
        """A to-do that came from a pick, as the menus read a pick: its title, link and creator from the item."""
        it = self.view(person["library"]).get(row["item_id"])
        if it is None:
            return None
        # (round 9 checks) the name without the to-do's verb: "Tacos El Gordo" in the Maps search, not "Book Tacos ..."
        name = re.sub(r"^\W*(?:book|reserve|apply\s+(?:to|for)|sign\s+up\s+for|register\s+for|enrol+\s+in)\s+", "",
                      row["text"], flags=re.I).strip() or row["text"]
        return {"item_id": row["item_id"], "title": name, "url": row.get("url") or it.url,
                "platform": it.platform, "video_id": it.video_id, "creator": it.creator, "facts": {}, "lines": [],
                "line_kinds": None}

    def _doit_answer(self, person, text, now):
        """The next message after "I can't do X for you. I can remind you if you tell me when.": a time sets the
        to-do's reminder (it reminds through the scheduler, as any due to-do). Any other message ends the offer."""
        from .cancel import when_answer
        h = person["handle"]
        st = self.store.get_state(f"doitask:{h}")
        if not st:
            return None
        self.store.set_state(f"doitask:{h}", None)
        if now - datetime.fromisoformat(st["at"]) > DOIT_ASK:
            return None
        t = self.store.todo(st["todo_id"])
        if not t or t["handle"] != h or t["done_at"] or t["removed_at"]:
            return None
        at = when_answer(text, now, person["timezone"])
        if at is None:
            return None
        self.note(intent="todo_due")
        self._wrote(h, "todo_due", f"set a reminder for \"{t['text']}\"",
                    {"rows": [{"id": t["id"], "due_at": t["due_at"], "reminded_at": t["reminded_at"]}]})
        self.store.update_todo(t["id"], due_at=now_iso(at), reminded_at=None)
        return self.send(h, T.todo_due_set(t["text"], say_time(at, now, person["timezone"])))

    def _doit_ticked(self, h, todo_id, now):
        """A to-do handed to a helper is ticked off only when the outcome is real (an email the server took, or the
        person's "sent" / "I cancelled it"). Returns the line to add, or ""."""
        t = self.store.todo(todo_id)
        if not t or t["handle"] != h or t["done_at"] or t["removed_at"]:
            return ""
        self.store.update_todo(todo_id, done_at=now_iso(now))
        return " " + T.doit_ticked(t["text"])

    def _doit_cancel_done(self, h, cancel_id, now):
        st = self.store.get_state(f"doit:{h}")
        if not st or st.get("kind") != "cancel" or cancel_id <= (st.get("after") or 0):
            return ""
        if now - datetime.fromisoformat(st["at"]) > timedelta(days=7):
            return ""
        self.store.set_state(f"doit:{h}", None)
        return self._doit_ticked(h, st["todo_id"], now)

    # ---------- library counts (section 11) ----------
    def _library_stats(self, person, it):
        from .libview import KIND_LABEL
        from .retrieve import contains_word
        q = it.stats
        view = self.view(person["library"])
        items = [x for x in view.items.values()
                 if (not q or not q.platforms or x.platform in q.platforms)
                 and (not q or not q.kinds or x.kinds & set(q.kinds))]
        names = {"instagram": "Instagram", "youtube": "YouTube"}
        by_platform = sorted(Counter(names.get(x.platform, x.platform) for x in items).items(), key=lambda kv: -kv[1])
        kinds = Counter(k for x in items for k in x.kinds if k in KIND_LABEL)
        by_kind = [(KIND_LABEL[k], n) for k, n in kinds.most_common()]
        words = [w for w in (q.words if q else []) if w.lower().strip() not in T.GENERIC_WORDS]
        matched = sum(1 for x in items if any(contains_word(x.caption, w) for w in words)) if words else None
        extra = None
        if q and q.by == "month":
            months = Counter((x.kept_on() or "")[:7] for x in items if x.kept_on())
            last6 = sorted(months)[-6:]
            extra = "By month: " + ", ".join(f"{datetime.strptime(m, '%Y-%m').strftime('%b %Y')} {months[m]}"
                                             for m in last6) + "." if last6 else None
        elif q and q.by == "creator":
            top = Counter(x.creator for x in items if x.creator).most_common(5)
            extra = "Most kept: " + ", ".join(f"{c} ({n})" for c, n in top) + "." if top else None
        return self.send(person["handle"], T.stats_message(len(items), by_platform, by_kind, words, matched, extra=extra))
