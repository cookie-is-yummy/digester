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

from . import config
from . import texts as T
from .schedule import _at, end_of_quiet, say_time
from .store import now_iso

UNDO_WINDOW = timedelta(minutes=10)
WORD = re.compile(r"[^\W_]+", re.UNICODE)
SMALL = set("a an the my to of for on in at and".split())


class TodoMixin:
    # ---------- the last write, for "undo" (section 11) ----------
    def _wrote(self, handle, kind, say, undo):
        self.store.set_state(f"lastwrite:{handle}", {"kind": kind, "say": say, "undo": undo, "at": now_iso(self.clock())})

    def _last_write(self, handle, now):
        lw = self.store.get_state(f"lastwrite:{handle}")
        if not lw or datetime.fromisoformat(lw["at"]) < now - UNDO_WINDOW:
            return None
        return lw

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
        if len(it.due) <= 10:
            due = _at(datetime.fromisoformat(it.due).date(), "09:00", tz)
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
        if it.pick_number or it.what == "ingredients":
            return self._add_picks(person, [it.pick_number] if it.pick_number else None, name, it.what or "pick", due)
        tid = self.store.add_todo(h, it.todo_text, name, due_at=due, at=now)
        self._wrote(h, "todo_add", f"added to-do \"{it.todo_text}\" to the list \"{name}\"", {"ids": [tid]})
        return self.send(h, T.todos_added([it.todo_text], name, say_time(due, now, person["timezone"]) if due else None))

    def _add_picks(self, person, numbers, name="todo", what="pick", due=None):
        """Picks of the last answer (title from the item's own words, and its link), or the checked ingredient lines
        of one pick, go on a list."""
        h = person["handle"]
        last = self._answer_seen(h)
        if not last or not last.get("items"):
            return self.send(h, T.NO_PICK_TO_ADD)
        items = last["items"]
        numbers = numbers or list(range(1, len(items) + 1))
        if any(not 1 <= n <= len(items) for n in numbers):
            return self.send(h, T.which_pick(len(items)))
        view = self.view(person["library"])
        from .compose import title_from_item
        added, ids = [], []
        if what == "ingredients":
            spec = (self.store.get_state(f"lastspec:{h}") or {}).get("spec", {})
            extract = spec.get("content", {}).get("extract") or []
            if isinstance(extract, str):
                extract = [extract]
            lines = (self.store.get_state(f"lines:{h}", {}) or {})
            for n in numbers:
                got = lines.get(items[n - 1]) or []
                if extract != ["ingredients"] or not got:   # lines that are not only ingredients are never guessed apart
                    return self.send(h, T.NO_INGREDIENTS)
                for line in got:
                    ids.append(self.store.add_todo(h, line, name, item_id=items[n - 1], at=self.clock()))
                    added.append(line)
        else:
            for n in numbers:
                it = view.get(items[n - 1])
                if it is None:
                    continue
                title = title_from_item(it)
                ids.append(self.store.add_todo(h, title, name, item_id=it.id, url=it.url,
                                               due_at=due, at=self.clock()))
                added.append(title)
        if not ids:
            return self.send(h, T.NO_PICK_TO_ADD)
        self._wrote(h, "todo_add", f"added {len(ids)} to-do{'s' if len(ids) > 1 else ''} to the list \"{name}\"",
                    {"ids": ids})
        due_text = say_time(due, self.clock(), person["timezone"]) if due else None
        return self.send(h, T.todos_added(added, name, due_text))

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
                if not t or t["reminded_at"] or t["done_at"] or t["removed_at"] or t["due_at"] > now_iso(now):
                    continue
                h, tz = person["handle"], person["timezone"]

                def record(status, h=h, todo_id=t["id"]):
                    self.store.add_run(handle=h, kind="todo", status=status, at=now_iso(now))
                    self.store.update_todo(todo_id, reminded_at=now_iso(now))
                if person["paused"]:
                    record("paused")
                    continue
                if now - datetime.fromisoformat(t["due_at"]) > MISSED_AFTER:
                    record("missed")
                    continue
                snooze = person.get("snooze_until")
                if snooze and now < datetime.fromisoformat(snooze):
                    record("snoozed")
                    continue
                local = now.astimezone(ZoneInfo(tz))
                midnight = _at(local.date(), "00:00", ZoneInfo(tz))
                if self.store.scheduled_today(h, midnight) >= config.MAX_SCHEDULED_PER_DAY:
                    tomorrow = _at(local.date() + timedelta(days=1), "00:00", ZoneInfo(tz))
                    self.store.update_todo(t["id"], due_at=now_iso(end_of_quiet(tomorrow, tz, self.store.quiet(h))))
                    continue
                self.send(h, T.todo_reminder(t["text"]))   # a time the person named: honoured in quiet hours
                record("sent")
                sent += 1
        return sent

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
        words = list(q.words) if q else []
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
