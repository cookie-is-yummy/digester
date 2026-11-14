"""PROTOTYPE ONLY - round 8 (BN5; DESIGN.md section 14): "how did my rules do?", the recap.

The vision's core loop step 6: report what the rules did and suggest a rule no rule covers yet. Never offered at setup
and never sent unless the person asks for it, now ("recap", "my week", "how did my rules do") or as a rule they make
("every sunday at 6pm send me a recap"). Everything is read back from the store and counted by code (runs, feedback,
to-dos, action_log, imports, answers); no model call. A recap rule is not the person's own words: its sends count as
unanswered and bring "Still useful?" like any timed send. A recap with nothing to report is not sent.

At most 6 lines (the head and up to 5 of these, in this order of importance: the rules, to-dos, what is coming up, one
suggested rule, calendar links, the library):
- per rule since `since`: sent, quiet on empty days (run status "empty_quiet", round 8 slice B, when it exists),
  skipped, snoozed, past the daily limit, and what the person said about its picks (👍, made it, too easy, too hard);
- to-dos ticked off in the period, open, and past their due date (todos.overdue_at too, when the column exists);
- coming up in the next 7 days: a one-time reminder about a thing (content source "items") and to-dos with a due date;
- calendar links given ("I gave you N calendar links", never "you added");
- the newest kept date and the next export due (refresh.export_due's phrases);
- one suggestion at most: 3 asks or more whose goals share a topic word, on 2 days or more in the last 21 days, with
  no active or paused rule on that word and no "not me" or "someday" label on it, offered once per word per 30 days.
  "yes" right after it shows the standard preview of that ask as a rule every Saturday at 10am; nothing starts without
  YES.
"""
import json
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import profile as P
from . import texts as T
from .attention import kept_day
from .retrieve import _stem, norm
from .schema import RuleSpec
from .store import now_iso, number_of

PERIOD_DAYS = 7
COMING_DAYS = 7
SUGGEST_DAYS, SUGGEST_ASKS, SUGGEST_DAYS_MIN = 21, 3, 2
SUGGEST_AGAIN_DAYS = 30
SUGGEST_WHEN = {"type": "schedule", "days": ["SAT"], "times": ["10:00"]}
MAX_LINES = 6
COMING_MAX = 3
RULE_STATUSES = {"sent": "sent", "none_sent": "sent", "unknown": "sent", "empty_quiet": "quiet", "skipped": "skipped",
                 "snoozed": "snoozed", "daily_limit": "daily_limit"}
FEEDBACK = ("up", "done", "harder", "easier")


def _day(dt, tz):
    return dt.astimezone(ZoneInfo(tz)).strftime("%A %-d %B")


def _name(spec, text):
    from .refresh import reminder_name
    name = (reminder_name(spec.content.text) if spec.content.source == "note" else None) or spec.content.goal or ""
    name = " ".join(name.split())
    return name if len(name) <= 40 else name[:40].rsplit(" ", 1)[0] + "…"


def _rules_line(store, handle, since):
    rules = store.rules(handle)
    clauses = []
    for r in rules:
        spec = RuleSpec.model_validate(r["spec"])
        if spec.content.source == "recap":   # the recap does not report on itself
            continue
        counts = Counter()
        for row in store.q("SELECT status, COUNT(*) n FROM runs WHERE rule_id=? AND kind='scheduled' AND at>=? "
                           "GROUP BY status", (r["id"], now_iso(since))):
            if row["status"] in RULE_STATUSES:
                counts[RULE_STATUSES[row["status"]]] += row["n"]
        fb = {row["kind"]: row["n"] for row in store.q(
            "SELECT kind, COUNT(*) n FROM feedback WHERE rule_id=? AND at>=? GROUP BY kind", (r["id"], now_iso(since)))
            if row["kind"] in FEEDBACK}
        if not counts and not fb:
            continue
        clauses.append(T.recap_rule_clause(number_of(rules, r["id"], r["id"]), _name(spec, r.get("text")), counts, fb))
    return T.recap_rules(clauses) if clauses else None


def _todos_line(store, handle, since, now):
    rows = store.q("SELECT * FROM todos WHERE handle=?", (handle,))
    done = sum(1 for t in rows if t.get("done_at") and t["done_at"] >= now_iso(since))
    open_ = [t for t in rows if not t.get("done_at") and not t.get("removed_at")]
    # round 8 slice B's nudge column is read only when it exists (a store made before it has none)
    overdue = sum(1 for t in open_ if (t.get("due_at") and t["due_at"] < now_iso(now)) or t.get("overdue_at"))
    if not done and not open_:
        return None, False
    return T.recap_todos(done, len(open_), overdue), bool(done or overdue)


def _coming_line(store, handle, now, tz):
    end = now + timedelta(days=COMING_DAYS)
    entries = []
    for r in store.rules(handle, statuses=("active",)):
        spec = RuleSpec.model_validate(r["spec"])
        if spec.when.type != "once" or spec.content.source != "items" or not r.get("next_run_at"):
            continue
        at = datetime.fromisoformat(r["next_run_at"])
        if not now <= at <= end:
            continue
        name = (spec.content.item_names or [spec.content.goal])[0]
        entry = f"a reminder about {name} on {_day(at, tz)}"
        dl = store.get_state(f"deadline:{r['id']}")   # round 8 slice B: the thing's own date, when it was read
        if isinstance(dl, dict) and dl.get("date"):
            d = date.fromisoformat(dl["date"])
            entry += f" ({'its deadline' if dl.get('deadline', True) else 'its date'} is {d.day} {d.strftime('%B')})"
        entries.append((at, entry))
    for t in store.todos(handle):
        if t.get("due_at"):
            at = datetime.fromisoformat(t["due_at"])
            if now <= at <= end:
                entries.append((at, f"\"{t['text']}\" due {_day(at, tz)}"))
    if not entries:
        return None
    entries.sort(key=lambda e: e[0])
    return T.recap_coming([e for _, e in entries[:COMING_MAX]], len(entries) - COMING_MAX if len(entries) > COMING_MAX
                          else 0)


def _calendar_line(store, handle, since):
    n = store.one("SELECT COUNT(*) n FROM action_log WHERE handle=? AND action='calendar.add' AND status='done' "
                  "AND at>=?", (handle, now_iso(since)))["n"]
    return T.recap_calendar(n) if n else None


def _library_line(store, view, handle, tz, now):
    from .refresh import _export_due
    today = now.astimezone(ZoneInfo(tz)).date()
    days = [d for d in (kept_day(it) for it in view.items.values()) if d]
    newest = max(days) if days else None
    imp = store.one("SELECT at FROM imports WHERE handle=? AND status='done' ORDER BY id DESC LIMIT 1", (handle,))
    counts = Counter(it.platform for it in view.items.values())
    counts = {p: counts[p] for p in ("instagram", "youtube") if counts.get(p)}
    dates = [max(it.dates.values())[:10] for it in view.items.values() if it.dates]
    due = _export_due(store, handle, tz, today, counts, datetime.fromisoformat(imp["at"]) if imp else None, dates)
    return T.recap_library(T.long_day(newest) if newest else None, "; ".join(due))


def _label_words(store, handle, prof):
    """The topic words of the topics the person said are not them or are for someday: never suggested."""
    out = set()
    for i in P.not_me_markers(store, handle) + P.parked(prof):
        out |= set(P.topic_words(i["topic"])) | {_stem(w) for w in i.get("words") or []}
    return out


# checker, round 8: a word that names a kind of thing, not a topic ("tools", "advice", "apps"): "productivity tools",
# "design tools" and "AI tools" are three topics, never one rule
KIND_WORDS = {"advice", "help", "inspiration", "inspo", "hack", "example", "option", "suggestion", "recommendation",
              "rec", "review", "piece", "type", "kind"}


def _kind_word(w):
    from .extract import GENERIC
    return w in KIND_WORDS or w in GENERIC or w + "s" in GENERIC


def suggestion(store, prof, handle, now, tz):
    """The one rule to suggest, or None: {"word", "say", "n", "since", "spec"}. Only asks kept with their spec count
    (answers rows from before round 8 have none and are never offered)."""
    start = now - timedelta(days=SUGGEST_DAYS)
    rows = store.q("SELECT a.run_id, a.goal, a.spec, a.at FROM answers a JOIN runs r ON r.id = a.run_id "
                   "WHERE a.handle=? AND r.kind='ask' AND a.spec IS NOT NULL AND a.at>=? ORDER BY a.run_id",
                   (handle, now_iso(start)))
    by_word = {}
    for row in rows:
        try:
            spec = json.loads(row["spec"])
        except (TypeError, ValueError):
            continue
        content = spec.get("content") or {}
        if content.get("source", "library") != "library" or not row.get("goal") or P.sensitive(row["goal"]):
            continue   # checker, round 8: an ask on a personal topic is never counted toward a suggestion
        day = datetime.fromisoformat(row["at"]).astimezone(ZoneInfo(tz)).date()
        for w in P.topic_words(row["goal"]):
            by_word.setdefault(w, []).append((row, day, spec))
    taken = set()
    for r in store.rules(handle):
        c = r["spec"].get("content") or {}
        taken |= set(P.topic_words(c.get("goal") or "", *(c.get("searches") or []), c.get("text") or ""))
    taken |= _label_words(store, handle, prof)
    offered = store.get_state(f"suggested:{handle}") or {}
    best = None
    for w, asks in by_word.items():
        if len(asks) < SUGGEST_ASKS or len({d for _, d, _ in asks}) < SUGGEST_DAYS_MIN or w in taken or P.sensitive(w) \
                or _kind_word(w):
            continue
        when = offered.get(w)
        if when and now - datetime.fromisoformat(when) < timedelta(days=SUGGEST_AGAIN_DAYS):
            continue
        key = (len(asks), asks[-1][0]["run_id"])
        if best is None or key > best[0]:
            best = (key, w, asks)
    if best is None:
        return None
    _, w, asks = best
    latest = asks[-1]
    say = next((t for t in norm(latest[0]["goal"]).split() if _stem(t) == w), w)
    return {"word": w, "say": say, "n": len(asks), "since": asks[0][1].strftime("%A %-d %B"), "spec": latest[2]}


def build(store, view, prof, handle, since, now, suggest=True, found=None):
    """The recap's lines (at most MAX_LINES, the head first), or [] when there is nothing to report. `found` (a dict)
    gets the suggestion shown, if any."""
    person = store.person(handle) or {}
    tz = person.get("timezone") or "America/New_York"
    lines = {}
    lines["rules"] = _rules_line(store, handle, since)
    todo, todo_news = _todos_line(store, handle, since, now)
    lines["todos"] = todo
    lines["coming"] = _coming_line(store, handle, now, tz)
    lines["calendar"] = _calendar_line(store, handle, since)
    sug = suggestion(store, prof, handle, now, tz) if suggest else None
    lines["suggest"] = T.recap_suggest(sug["say"], sug["n"], sug["since"]) if sug else None
    news = lines["rules"] or todo_news or lines["coming"] or lines["calendar"] or lines["suggest"]
    if not news:
        return []
    lines["library"] = _library_line(store, view, handle, tz, now)
    keep = [k for k in ("rules", "todos", "coming", "suggest", "calendar", "library") if lines.get(k)][:MAX_LINES - 1]
    if found is not None and "suggest" in keep:
        found["suggestion"] = sug
    order = ("rules", "todos", "coming", "calendar", "library", "suggest")
    return [T.recap_head(_day(since, tz))] + [lines[k] for k in order if k in keep]


class DigestMixin:
    def understanding_reads(self, person, text, now):
        """Round 8 (DESIGN.md section 14): (True, ref) for a message code reads here (the recap, "yes" to its
        suggestion, then attention.py's: trends, the theme check, labels, "what did I park?", "every export");
        else (False, None)."""
        from .followup import RECAP_ASK
        h = person["handle"]
        sug = self.store.get_state(f"suggest:{h}")
        if sug:   # "yes" right after the suggestion; any other message ends it
            self.store.set_state(f"suggest:{h}", None)
            if T.YES.match(text) and now - datetime.fromisoformat(sug["at"]) < timedelta(hours=24):
                for key in ("themecheck", "trendsoffer"):
                    self.store.set_state(f"{key}:{h}", None)
                return True, self._suggest_preview(person, sug, now)
        if RECAP_ASK.match(text):
            # merge of round 8: the recap is "anything else", so it ends the theme check and the "every export" offer
            for key in ("themecheck", "trendsoffer"):
                self.store.set_state(f"{key}:{h}", None)
            return True, self._recap_answer(person, now)
        return self._attention_reads(person, text, now)

    def _recap_lines(self, person, now, suggest):
        h = person["handle"]
        lib = (self.store.person(h) or person)["library"]
        found = {}
        pending = self._live_pending(h, now)
        if pending and pending["kind"] == "confirm_rule":
            # checker, round 8: a rule preview is waiting for YES, and the handler reads "yes" as that YES first: the
            # suggestion is not offered now, so "yes" can only mean the preview the person saw (it comes next time)
            suggest = False
        lines = build(self.store, self.view(lib), P.get(self.store, h), h, now - timedelta(days=PERIOD_DAYS), now,
                      suggest=suggest, found=found)
        if found.get("suggestion"):   # offered once per word per 30 days; "yes" to it is read with the next message
            sug = found["suggestion"]
            offered = self.store.get_state(f"suggested:{h}") or {}
            offered[sug["word"]] = now_iso(now)
            self.store.set_state(f"suggested:{h}", offered)
            self.store.set_state(f"suggest:{h}", dict(sug, at=now_iso(now)))
        return lines

    def _recap_answer(self, person, now):
        self.note(intent="recap")
        lines = self._recap_lines(person, now, suggest=True)
        return self.send(person["handle"], "\n".join(lines) if lines else T.RECAP_NOTHING)

    def understanding_text(self, person, spec, kind, rule_id):
        """(message, n) for a rule whose content is counted by code (executor._run_plain): "trends" or "recap". A
        recap with nothing to report has n = 0 (a timed one is then not sent)."""
        if spec.content.source == "trends":
            msg, n = self.trends_text(person)
            return msg or "", n
        lines = self._recap_lines(person, self.clock(), suggest=kind in ("scheduled", "manual"))
        if lines:
            return "\n".join(lines), len(lines)
        return (T.RECAP_PREVIEW_EMPTY if kind == "preview" else T.RECAP_NOTHING if kind == "manual" else ""), 0

    def _recap_preview(self, person, spec, text, now):
        """'every sunday at 6pm send me a recap': this week's recap now, then YES starts the rule."""
        from .schedule import describe
        h = person["handle"]
        self.note(intent="new_rule")
        self.store.clear_pending(h)
        msg, run_id, n = self.run(person, spec, "preview", request_text=text)
        self.store.set_pending(h, "confirm_rule", {"text": " ".join(text.split())[:300], "spec": spec.stored(),
                                                   "run_id": run_id, "more": []}, at=self.clock())
        tail = T.recap_preview_tail(describe(spec.when), self._first_text(spec.when, person, now))
        return self.send(h, (T.PREVIEW_HEAD if n else "") + msg + tail + self._do_note(spec), run_id)

    def _suggest_preview(self, person, sug, now):
        """'yes' to the recap's suggestion: the ask it counted, as a rule every Saturday at 10am, through the standard
        preview; nothing starts without YES. No new interpretation."""
        from .schedule import describe
        h = person["handle"]
        self.note(intent="new_rule")
        stored = dict(sug["spec"])
        stored["content"] = dict(stored.get("content") or {}, count=1, outside="none")
        stored["when"] = dict(SUGGEST_WHEN)
        stored["do"] = [{"action": "message.send"}]
        spec = RuleSpec.model_validate(stored)
        text = f"every saturday at 10am: {sug['say']}"
        msg, run_id, n = self.run(person, spec, "preview", request_text=spec.content.goal, own_words="yes")
        if self._run_failed(run_id):
            return self.send(h, msg, run_id)
        self.store.set_pending(h, "confirm_rule", {"text": text, "spec": spec.stored(), "run_id": run_id, "more": []},
                               at=self.clock())
        tail = T.preview_tail(describe(spec.when), T.picks_for(1, spec.content.goal),
                              self._first_text(spec.when, person, now))
        return self.send(h, (T.PREVIEW_HEAD if n else "") + msg + tail, run_id)
