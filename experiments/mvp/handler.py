"""PROTOTYPE ONLY - the conversation side: messages in, dispatch, confirm, activate, feedback, rule management and
follow-ups (BRIEF-10 section 4). The interpreter fills forms (AGENTS.md rule 6); code acts. Mixed into core.Bot.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from . import texts as T
from .interpret import interpret
from .schedule import describe, next_run, resolve_until, say_time, t12
from .schema import RuleSpec
from .store import now_iso
from .texts import (
    AGREE,
    CONSENT,
    CONSENT_VERSION,
    HELP,
    NEGATION,
    NO,
    NOTHING_PENDING,
    QUICK_FEEDBACK,
    REACTION_TEXT,
    UNKNOWN,
    YES,
)

MAX_MESSAGES_PER_MINUTE = 15  # per person; more than this is a loop or a script, and is ignored
MAX_MESSAGES_PER_HOUR = 90
PENDING_TTL = {"confirm_rule": timedelta(hours=24), "confirm_delete": timedelta(minutes=30)}
# what a message must be for an open preview to be dropped; small talk, questions about the last answer, feedback and
# rule management leave it open, so a later "yes" still starts the rule
ENDS_PENDING = ("ask", "change_rule", "delete_data", "decline", "stop")


def norm_handle(h):
    """One spelling per person: a lower-case email, or a phone number in E.164 (+1 added to a bare US number)."""
    h = (h or "").strip()
    if "@" in h:
        return h.lower()
    digits = re.sub(r"[\s().-]", "", h)
    if re.fullmatch(r"\+?\d{10,15}", digits):
        digits = digits.lstrip("+")
        if len(digits) == 10:
            digits = "1" + digits
        return "+" + digits
    return h


class HandlerMixin:
    # ---------- messages in ----------
    def on_message(self, handle, text, tapback=None, tapback_ref=None, received=None):
        """tapback: 'up' or 'down' on an earlier bot message identified by tapback_ref. received: the real time the
        message arrived (it may wait behind a timed send to the same person)."""
        handle = norm_handle(handle)
        self._tl.received = received
        with self.lock_for(handle):
            return self._on_message(handle, text, tapback, tapback_ref)

    def _on_message(self, handle, text, tapback=None, tapback_ref=None):
        now = self.clock()
        seen = [t for t in self._arrivals.get(handle, []) if time.time() - t < 3600]
        self._arrivals[handle] = seen + [time.time()]
        if self.max_per_minute and (len(seen) >= MAX_MESSAGES_PER_HOUR
                                    or sum(1 for t in seen if time.time() - t < 60) >= self.max_per_minute):
            return None  # a loop or a flood: no reply, no paid call
        person = self.store.person(handle)
        if person is None:
            self.note(intent="unknown_person")
            day = now.date().isoformat()
            if getattr(self.channel, "reply_to_unknown", True) and self.store.get_state(f"unknown:{handle}") != day:
                self.store.set_state(f"unknown:{handle}", day)  # one reply a day at most, and no names in it
                return self.channel.send(handle, UNKNOWN)
            return None  # e.g. the Mac channel: people who text the founder's own account are not the bot's users
        if person["paused"]:  # the kill switch for one person: no replies, no paid calls, no timed sends
            self.note(intent="paused_person")
            return None
        self.store.set_state(f"last_in:{handle}", now_iso(now))
        text = (text or "").strip()
        if not person["consent_version"]:
            self.note(intent="consent")
            if text and AGREE.match(text) and not NEGATION.search(text):
                self.store.set_consent(handle, CONSENT_VERSION)
                return self.send(handle, T.WELCOME)
            return self.send(handle, CONSENT)
        pending = self._live_pending(handle, now)
        if tapback:
            self.note(intent="tapback")
            run_id = self.store.run_for_ref(tapback_ref) if tapback_ref else None
            if (pending and pending["kind"] == "confirm_rule" and tapback == "up"
                    and run_id is not None and run_id == pending["payload"].get("run_id")):
                return self._confirm(person, pending)  # 👍 on the preview means yes
            for d in (self.store.items_of_run(run_id) if run_id else []):
                self.store.add_feedback(handle, d["item_id"], d["rule_id"], tapback)
            return None
        if not text:
            return None
        r = REACTION_TEXT.match(text)
        if r:
            down = r.group(1).lower().startswith("disliked") or (r.group(2) == "👎")
            last = self.store.last_answer(handle)
            for iid in (last or {}).get("items", []):
                self.store.add_feedback(handle, iid, last.get("rule_id"), "down" if down else "up")
            return None
        if pending and pending["kind"] == "confirm_rule" and text == "👍":
            return self._confirm(person, pending)
        m = QUICK_FEEDBACK.match(text)
        if m:
            return self._feedback(person, "up" if m.group(1) == "👍" else "down", int(m.group(2)) if m.group(2) else None)
        if pending and pending["kind"] == "confirm_delete":
            if text.strip(" .!").upper() == "YES":  # deleting needs the literal word
                return self._confirm(person, pending)
            self.store.clear_pending(handle)
            if NO.match(text):
                return self.send(handle, T.NOT_DELETED)
            pending = None
        elif pending and pending["kind"] == "confirm_rule" and YES.match(text):
            return self._confirm(person, pending)
        elif pending and NO.match(text):
            self.store.clear_pending(handle)
            return self.send(handle, T.NOT_STARTED if pending["kind"] == "confirm_rule" else T.WAITING_FOR_ANSWER)
        over = self._over_cap(person)
        if over:
            self.note(intent="over_cap")
            return self._limit_notice(person, over)  # before any paid call
        rules = self.store.rules(handle)
        last = self.store.last_answer(handle)
        if last and not last.get("rule_id"):
            last = dict(last, request=(self.store.get_state(f"lastspec:{handle}") or {}).get("text"))
        try:
            it, _ = interpret(text, person, rules, pending, last, now, todos=self.store.todos(handle),
                              last_write=self._last_write_ctx(handle, now), about=self.store.profile_notes(handle),
                              store=self.store)
        except Exception as e:  # noqa: BLE001
            self.store.add_run(handle=handle, kind="interpret", status="error", error=type(e).__name__)
            return self.send(handle, T.INTERPRET_ERROR)
        return self._dispatch(person, it, text, rules, pending, last, now)

    def _live_pending(self, handle, now):
        p = self.store.pending(handle)
        if p and datetime.fromisoformat(p["at"]) < now - PENDING_TTL.get(p["kind"], timedelta(minutes=30)):
            self.store.clear_pending(handle)
            return None
        return p

    def _dispatch(self, person, it, text, rules, pending, last, now):
        """The interpretation, then the one more it may carry ('also'), in order. A lasting fact the person stated
        about themselves is kept for the profile; the language they wrote in is passed on to the runs."""
        h = person["handle"]
        for x in [it] + ([it.also] if it.also else []):
            if x.profile_note:
                self.store.add_profile_note(h, x.profile_note, at=now)
        self._tl.lang = it.lang
        self._tl.made_pending = False
        self._tl.chained = False
        ref = self._dispatch_one(person, it, text, rules, pending, last, now)
        if it.also is not None:
            self._tl.chained = True
            try:
                ref = self._dispatch_one(person, it.also, text, self.store.rules(h), self._live_pending(h, now),
                                         self.store.last_answer(h), now) or ref
            finally:
                self._tl.chained = False
        return ref

    def _dispatch_one(self, person, it, text, rules, pending, last, now):
        h = person["handle"]
        self.note(intent=it.intent)
        chained = getattr(self._tl, "chained", False)
        if pending and not chained and (pending["kind"] == "clarify" or it.intent in ENDS_PENDING
                                        or (it.intent == "new_rule" and not it.edits_pending)):
            self.store.clear_pending(h)  # a different request ends the question that was open; an answer uses it up
            if pending["kind"] == "clarify" and it.intent in ("new_rule", "change_rule"):
                text = pending["payload"].get("text", "") + " / " + text   # the rule keeps the whole request
            pending = None
        if it.intent in ("unsupported", "chat", "help"):
            if it.intent == "unsupported":
                self.store.log_request(h, text, it.intent)
            return self.send(h, HELP if it.intent == "help" and not it.reply else (it.reply or HELP))
        if it.intent == "confirm":
            if pending and pending["kind"] == "confirm_rule":
                return self._confirm(person, pending)
            return self.send(h, NOTHING_PENDING)  # never "OK!": they would think a rule had started
        if it.intent == "decline":
            if pending:
                self.store.clear_pending(h)
            return self.send(h, T.DECLINED)
        if it.intent in ("new_rule", "ask") and it.spec.content.outside == "only":
            return self.send(h, T.NOT_YET["outside_only"])   # outside picks come in a later slice
        if it.intent == "new_rule":
            if it.spec.when.type in ("once", "on_request") or it.spec.content.source in ("note", "todos"):
                # one send at a stated time, a saved request, or a reminder in their own words: nothing from the
                # library repeats, so no preview is needed; the reply states what will happen and how to stop it
                return self._activate(person, text, it.spec)
            if pending and it.edits_pending and T.YES_WITH_EDIT.match(text):
                same = it.spec.stored()["content"] == RuleSpec.model_validate(pending["payload"]["spec"]).stored()["content"]
                ref = self._activate(person, pending["payload"]["text"] + " / " + text, it.spec, edited=True,
                                     preview_run=pending["payload"].get("run_id") if same else None)
                for extra in pending["payload"].get("more") or []:   # a second rule shown in the same preview
                    ref = self._activate(person, extra["text"], RuleSpec.model_validate(extra["spec"])) or ref
                return ref
            more = (pending["payload"].get("more") or []) if pending and pending["kind"] == "confirm_rule" else []
            if pending and it.edits_pending:  # keep the whole request, not only the edit
                text = pending["payload"]["text"] + " / " + text
            never = self._never_sends(person, it.spec, now)
            if never:  # no preview for a rule that would never send (its end has passed, or every moment is quiet)
                return self.send(h, never)
            joined = chained and pending and pending["kind"] == "confirm_rule" and getattr(self._tl, "made_pending", False)
            msg, run_id, n = self.run(person, it.spec, "preview", request_text=text)
            if self._run_failed(run_id):  # no preview, so nothing to say yes to
                if not joined:
                    self.store.clear_pending(h)
                return self.send(h, msg, run_id)
            c = it.spec.content
            what = T.picks_for(c.count, c.goal)
            first = self._first_text(it.spec.when, person, now)
            if joined:   # "weekdays at 8 and weekends at 10": one YES starts both
                payload = dict(pending["payload"])
                payload["more"] = (payload.get("more") or []) + [{"text": text, "spec": it.spec.stored()}]
                self.store.set_pending(h, "confirm_rule", payload, at=datetime.fromisoformat(pending["at"]))
                tail = T.preview_also_tail(describe(it.spec.when), what, first)
            else:
                self.store.set_pending(h, "confirm_rule", {"text": text, "spec": it.spec.stored(), "run_id": run_id,
                                                           "more": more}, at=self.clock())
                self._tl.made_pending = True
                tail = T.preview_tail(describe(it.spec.when), what, first)
                if more:
                    tail += " " + T.preview_more_note(len(more))
            w = it.spec.when
            if w.every_hours and w.window:  # more sends a day than the daily limit allows: the preview says so
                per_day = (int(w.window[1][:2]) * 60 + int(w.window[1][3:]) - int(w.window[0][:2]) * 60
                           - int(w.window[0][3:])) // (w.every_hours * 60) + 1
                if per_day > config.MAX_SCHEDULED_PER_DAY:
                    tail += T.daily_limit_note(config.MAX_SCHEDULED_PER_DAY)
            tail += self._not_yet_notes(it.spec)
            head = T.PREVIEW_HEAD if n else ""
            return self.send(h, head + msg + tail, run_id)
        if it.intent == "ask":
            msg, run_id, _ = self.run(person, it.spec, "ask", request_text=text)
            return self.send(h, msg + self._not_yet_notes(it.spec, sep="\n\n"), run_id)
        if it.intent == "more":
            st = self.store.get_state(f"lastspec:{h}")
            if not st:
                return self.send(h, T.MORE_OF_WHAT)
            spec = RuleSpec.model_validate(st["spec"])
            if it.avoid or it.criteria or it.outside:   # "another but shorter": the change rides on the same request
                c = spec.content
                c.avoid = list(dict.fromkeys([*c.avoid, *it.avoid]))[:8]
                c.criteria = list(dict.fromkeys([*c.criteria, *it.criteria]))[:5]
                if it.outside == "only":
                    return self.send(h, T.NOT_YET["outside_only"])
                if it.outside:
                    c.outside = it.outside
            rule = self.store.rule(st["rule_id"]) if st.get("rule_id") else None
            if rule and rule["status"] in ("active", "paused"):  # one more from a rule counts as sent by that rule
                msg, run_id, _ = self.run(person, spec, "manual", rule_id=rule["id"], request_text=st.get("text") or text,
                                          shown=st.get("shown") or [])
            else:
                msg, run_id, _ = self.run(person, spec, "more", request_text=st.get("text") or text,
                                          shown=st.get("shown") or [])
            return self.send(h, msg + self._not_yet_notes(spec, sep="\n\n"), run_id)
        if it.intent == "follow_up":
            if not last:
                return self.send(h, T.NOTHING_TO_FOLLOW_UP)
            view = self.view(person["library"])
            cands = [c for c in (view.get(i) for i in last["items"]) if c]
            spec = self._spec_for_followup(last, it.question, it.avoid, h)
            known = self.store.get_state(f"lines:{h}", {}) or {}
            msg, run_id, _ = self.run(person, spec, "follow_up", request_text=it.question, cands_override=cands,
                                      known_lines=known)
            return self.send(h, msg, run_id)
        if it.intent == "feedback":
            return self._feedback(person, it.feedback, it.pick_number)
        if it.intent == "list_rules":
            return self.send(h, self._rules_text(person, rules))
        if it.intent in ("pause", "resume", "stop"):
            return self._manage(person, rules, it.intent, it.rule_number, it.all_rules, it.until, it.in_minutes)
        if it.intent == "change_rule":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE)
            status, nxt = self._next_for(it.spec, person, now, r)
            if status == "done":  # a one-off time that has passed would end the rule without saying so
                return self.send(h, T.CHANGE_TIME_PASSED)
            self._wrote(h, "rule_rows", f"changed rule \"{RuleSpec.model_validate(r['spec']).content.goal}\"",
                        {"rows": self._rule_rows([r["id"]])})
            self.store.update_rule(r["id"], spec=it.spec.stored(), text=text)
            self.store.set_slot(r["id"], nxt, status if r["status"] == "active" else r["status"])
            return self.send(h, T.changed(describe(it.spec.when), it.spec.content.goal) + self._not_yet_notes(it.spec))
        if it.intent == "run_rule":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE if rules else T.NO_RULES_ASK)
            msg, run_id, _ = self.run(person, RuleSpec.model_validate(r["spec"]), "manual", rule_id=r["id"],
                                      request_text=text)
            if it.skip_next and r["status"] == "active" and r["next_run_at"] and not self._run_failed(run_id):
                rows = self._rule_rows([r["id"]])
                self.store.skip(r["id"], count=1)  # "send Friday's one now": Friday's is not sent again
                self._wrote(h, "rule_rows", "skipped the next send of a rule", {"rows": rows})
                up = self._upcoming(self.store.rule(r["id"]), person, now)
                msg += "\n\n" + (T.skipped_next(say_time(up, now, person["timezone"])) if up else T.SKIPPED_LAST)
                if up is None:
                    self.store.set_slot(r["id"], None, "done")
            return self.send(h, msg, run_id)
        if it.intent == "skip":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE if rules else T.NO_RULES)
            if r["status"] != "active" or not r["next_run_at"]:
                return self.send(h, T.NO_SEND_COMING)
            self._wrote(h, "rule_rows", "skipped sends of a rule", {"rows": self._rule_rows([r["id"]])})
            return self._skip(person, r, it, now)
        if it.intent == "set_timezone":
            self._wrote(h, "timezone", f"switched to {T.zone_name(it.timezone)} time",
                        {"timezone": person["timezone"], "revert_to": person.get("tz_revert_to"),
                         "revert_at": person.get("tz_revert_at")})
            back = resolve_until(it.until, None, now, it.timezone) if it.until else None
            if back is not None and back <= now:
                back = None
            # "I'm in Chicago until Sunday": code switches back then (to the zone they had before any temporary one)
            home = (person.get("tz_revert_to") or person["timezone"]) if back else None
            self._move_timezone(h, it.timezone, now, revert_to=home, revert_at=back)
            local = now.astimezone(ZoneInfo(it.timezone)).strftime("%-I:%M%p").lower()
            msg = T.timezone_set(it.timezone, local)
            if back:
                msg += T.timezone_back(home, say_time(back, now, it.timezone))
            return self.send(h, msg)
        if it.intent == "delete_data":
            self.store.set_pending(h, "confirm_delete", {}, at=self.clock())
            return self.send(h, T.DELETE_ASK)
        if it.intent == "set_quiet_hours":
            return self._set_quiet(person, it, now)
        if it.intent == "snooze":
            return self._snooze(person, it, now)
        if it.intent == "clarify":
            # the half-built form is kept; the next message completes it (the interpreter sees both)
            self.store.set_pending(h, "clarify", {"text": text, "question": it.question, "draft": it.draft,
                                                  "intent": "change_rule" if it.rule_number else "new_rule",
                                                  "rule_number": it.rule_number}, at=self.clock())
            return self.send(h, T.clarify_ask(it.question))
        if it.intent == "undo":
            return self._undo(person, now)
        if it.intent == "todo_add":
            return self._todo_add(person, it, now)
        if it.intent == "todo_list":
            return self._todo_list(person, it, now)
        if it.intent in ("todo_done", "todo_remove", "todo_due"):
            return self._todo_change(person, it, now)
        if it.intent == "act_on_last":
            if it.when is None and {a.action for a in it.actions} == {"todo.add"}:
                name = it.actions[0].params.get("list") or "todo"
                return self._add_picks(person, [it.pick_number] if it.pick_number else None, name)
            return self.send(h, T.NOT_YET["act_on_last"])   # email and calendar come in a later slice
        if it.intent == "library_stats":
            return self._library_stats(person, it)
        if it.intent == "profile_update":
            if not it.profile_note:   # kept for the profile slice; the interpreter already sees these notes
                self.store.add_profile_note(h, " ".join(text.split())[:300], at=now)
            return self.send(h, T.PROFILE_NOTED)
        if it.intent in ("profile_show", "set_email", "library_status"):
            return self.send(h, T.NOT_YET[it.intent])
        return self.send(h, HELP)

    # ---------- helpers for the slice-2 intents ----------
    def _first_text(self, when, person, now):
        """The first send, in words, for a preview: a clock time; a day and the window for a window rule; nothing for
        random moments, which are never shown in advance."""
        if when.type == "random":
            return None
        nxt = next_run(when, person["timezone"], now, anchor=now, quiet=self.store.quiet(person["handle"]))
        if nxt is None:
            return None
        if when.window and not when.every_hours:
            day = say_time(nxt, now, when.tz or person["timezone"]).split(" at ")[0]
            return f"{day}, between {t12(when.window[0])} and {t12(when.window[1])}"
        return say_time(nxt, now, when.tz or person["timezone"])

    @staticmethod
    def _not_yet_notes(spec, sep=" "):
        """One honest line when a spec asks for something that comes in a later slice."""
        notes = []
        if spec.content.outside == "some":
            notes.append(T.OUTSIDE_SOME)
        if {a.action for a in spec.do} & {"email.send", "calendar.add"}:
            notes.append(T.OUTPUTS_NOT_YET)
        return (sep + " ".join(notes)) if notes else ""

    def _rule_rows(self, ids):
        cols = "id, text, spec, status, next_run_at, slot_at, paused_until, skip_count, skip_dates"
        return [self.store.one(f"SELECT {cols} FROM rules WHERE id=?", (i,)) for i in ids]

    def _set_quiet(self, person, it, now):
        """'No messages before 10am' changes the everyday block; a block with days ('not during class 9 to 3 on
        weekdays') is added beside it (up to 4). Random and window sends move out of the new quiet hours."""
        h = person["handle"]
        old = self.store.quiet(h)
        if it.clear:
            blocks = None
        elif it.days:
            if not (it.start and it.end):
                return self.send(h, T.QUIET_NEEDS_BOTH)
            blocks = [b for b in old if b.get("days") != it.days] + [{"start": it.start, "end": it.end, "days": it.days}]
        else:
            every = next((b for b in old if not b.get("days")), {"start": "22:00", "end": "08:00"})
            new = {"start": it.start or every["start"], "end": it.end or every["end"]}
            blocks = [b for b in old if b.get("days")] + [new]
        try:
            self.store.set_quiet(h, blocks)
        except ValueError:
            return self.send(h, T.QUIET_INVALID)
        self._wrote(h, "quiet", "changed the quiet hours", {"quiet": old})
        for r in self.store.rules(h, statuses=("active",)):   # moments drawn inside the new quiet hours are redrawn
            spec = RuleSpec.model_validate(r["spec"])
            if spec.when.type == "random" or spec.when.window:
                status, nxt = self._next_for(spec, person, now, r)
                self.store.set_slot(r["id"], nxt, status)
        if blocks is None:
            return self.send(h, T.QUIET_RESET)
        return self.send(h, T.quiet_set(T.quiet_words(self.store.quiet(h))))

    def _snooze(self, person, it, now):
        h = person["handle"]
        old = person.get("snooze_until")
        if it.clear:
            if not old or datetime.fromisoformat(old) <= now:
                return self.send(h, T.SNOOZE_NONE)
            self.store.set_snooze(h, None)
            self._wrote(h, "snooze", "turned timed messages back on", {"snooze": old})
            return self.send(h, T.SNOOZE_CLEARED)
        until = resolve_until(it.until, it.in_minutes, now, person["timezone"])
        if until is None or until <= now:
            return self.send(h, T.TIME_PASSED)
        self.store.set_snooze(h, until)
        self._wrote(h, "snooze", f"paused timed messages until {say_time(until, now, person['timezone'])}",
                    {"snooze": old})
        return self.send(h, T.snoozed(say_time(until, now, person["timezone"])))

    def _undo(self, person, now):
        """Reverses the last write within 10 minutes: a to-do added, ticked off, removed or given a time; a rule
        started, changed, paused, resumed, stopped or skipped; quiet hours; a snooze; a time zone."""
        h = person["handle"]
        lw = self._last_write(h, now)
        if not lw:
            return self.send(h, T.NOTHING_TO_UNDO)
        k, u = lw["kind"], lw["undo"]
        self.store.set_state(f"lastwrite:{h}", None)
        if k == "todo_add":
            for i in u["ids"]:
                self.store.update_todo(i, removed_at=now_iso(now))
            return self.send(h, T.undone(f"I took that off your list ({lw['say']})"))
        if k in ("todo_done", "todo_remove"):
            for i in u["ids"]:
                self.store.update_todo(i, **{u["col"]: None})
            return self.send(h, T.undone("it's back on your list"))
        if k == "todo_due":
            for row in u["rows"]:
                self.store.update_todo(row["id"], due_at=row["due_at"], reminded_at=row["reminded_at"])
            return self.send(h, T.undone("the reminder is off"))
        if k == "rule_add":
            r = self.store.rule(u["rule_id"])
            self.store.set_slot(u["rule_id"], None, "stopped")
            goal = RuleSpec.model_validate(r["spec"]).content.goal if r else "that rule"
            return self.send(h, T.undone(f"I stopped the rule I just started, \"{goal}\""))
        if k == "rule_rows":
            for row in u["rows"]:
                self.store.x("UPDATE rules SET text=?, spec=?, status=?, next_run_at=?, slot_at=?, paused_until=?, "
                             "skip_count=?, skip_dates=? WHERE id=?",
                             (row["text"], row["spec"], row["status"], row["next_run_at"], row["slot_at"],
                              row["paused_until"], row["skip_count"], row["skip_dates"], row["id"]))
            goals = ", ".join(RuleSpec.model_validate(json.loads(row["spec"])).content.goal for row in u["rows"])
            return self.send(h, T.undone(f"\"{goals}\" is back as it was"))
        if k == "quiet":
            self.store.set_quiet(h, u["quiet"])
            return self.send(h, T.undone("your quiet hours are back as they were"))
        if k == "snooze":
            back = datetime.fromisoformat(u["snooze"]) if u.get("snooze") else None
            self.store.set_snooze(h, back)
            return self.send(h, T.undone("timed messages are back as they were"))
        if k == "timezone":
            at = datetime.fromisoformat(u["revert_at"]) if u.get("revert_at") else None
            self._move_timezone(h, u["timezone"], now, revert_to=u.get("revert_to"), revert_at=at)
            return self.send(h, T.undone(f"I'm back on {T.zone_name(u['timezone'])} time"))
        return self.send(h, T.NOTHING_TO_UNDO)

    def _spec_for_followup(self, last, question, avoid=(), handle=None):
        """The follow-up's spec. What the person ruled out before ("no cream") and in this question ("any without
        cheese?") is carried into it, so code rechecks it."""
        earlier = (self.store.get_state(f"lastspec:{handle}") or {}).get("spec", {}).get("content", {}).get("avoid") or []
        avoid = list(dict.fromkeys([*avoid, *earlier]))[:8]
        prev = None
        if last.get("rule_id"):
            r = self.store.rule(last["rule_id"])
            prev = RuleSpec.model_validate(r["spec"]) if r else None
        extract = prev.content.extract if prev else (["ingredients"] if T.RECIPE_WORDS.search(question) else [])
        return RuleSpec.model_validate({"when": {"type": "now"}, "content": {
            "goal": question[:200], "searches": [question[:120]], "count": min(3, len(last["items"])) or 1,
            "extract": extract, "avoid": avoid, "exclude_sent": False}})

    def _confirm(self, person, pending):
        h = person["handle"]
        self.note(intent="confirm")
        self.store.clear_pending(h)
        if pending["kind"] == "confirm_rule":
            ref = self._activate(person, pending["payload"]["text"], RuleSpec.model_validate(pending["payload"]["spec"]),
                                 preview_run=pending["payload"].get("run_id"))
            for extra in pending["payload"].get("more") or []:   # a second rule shown in the same preview
                ref = self._activate(person, extra["text"], RuleSpec.model_validate(extra["spec"])) or ref
            return ref
        if pending["kind"] == "confirm_delete":
            self.store.delete_person_data(h)
            os.makedirs(config.HOME, exist_ok=True)
            with open(os.path.join(config.HOME, "deletions.jsonl"), "a") as f:
                f.write(json.dumps({"handle": h, "library": person["library"], "at": now_iso()}) + "\n")
            # sent through the channel directly, so nothing new is recorded about the person
            return self.channel.send(h, T.DELETED)
        return None

    def _activate(self, person, text, spec, edited=False, preview_run=None):
        h = person["handle"]
        if not getattr(self._tl, "chained", False):   # the second request of a message keeps the first one's preview
            self.store.clear_pending(h)
        now = self.clock()
        tz = person["timezone"]
        c = spec.content
        avoid = T.avoid_clause(c.avoid)
        what = T.picks_for(c.count, c.goal) + avoid
        if spec.when.type in ("on_request", "new_items"):
            rule_id = self.store.add_rule(h, text, spec.stored(), "active", None, created_at=now_iso(now))
            self._wrote(h, "rule_add", f"saved a rule, \"{c.goal}\"", {"rule_id": rule_id})
            n = len(self.store.rules(h))
            return self.send(h, T.saved_rule(n, what) + self._not_yet_notes(spec))
        quiet = self.store.quiet(h)
        never = self._never_sends(person, spec, now)
        if never:
            return self.send(h, never)
        # random and window moments are seeded with the rule's id, so the slot is worked out once the rule has one
        rule_id = self.store.add_rule(h, text, spec.stored(), "active", None, created_at=now_iso(now))
        nxt = next_run(spec.when, tz, now, anchor=now, seed=rule_id, quiet=quiet)
        if nxt is None:  # nothing is left of this period's random sends and the rule ends with it
            self.store.set_slot(rule_id, None, "done")
            return self.send(h, T.TIME_PASSED)
        self.store.set_slot(rule_id, now_iso(nxt), "active")
        self._wrote(h, "rule_add", f"started a rule, \"{c.goal}\" ({describe(spec.when)})", {"rule_id": rule_id})
        if preview_run:  # the preview's picks count as sent by this rule, so its first send is something new
            self.store.x("UPDATE deliveries SET rule_id=? WHERE run_id=? AND handle=?", (rule_id, preview_run, h))
            # 👍, 👎 and "more like 2" given on the preview belong to the rule it became
            self.store.x("UPDATE feedback SET rule_id=? WHERE handle=? AND rule_id IS NULL AND item_id IN "
                         "(SELECT item_id FROM deliveries WHERE run_id=?)", (rule_id, h, preview_run))
        n = next((i for i, r in enumerate(self.store.rules(h), 1) if r["id"] == rule_id), len(self.store.rules(h)))
        first = say_time(nxt, now, spec.when.tz or tz)
        notes = self._not_yet_notes(spec)
        if c.source == "note":   # a reminder in their own words
            if spec.when.type == "once":
                return self.send(h, T.reminder_once(first, c.text, n))
            return self.send(h, T.reminder_started(describe(spec.when), c.text, self._first_text(spec.when, person, now)
                                                   if spec.when.type != "random" else None, n))
        if c.source == "todos":
            if spec.when.type == "once":
                return self.send(h, T.todos_once(first, n))
            return self.send(h, T.todos_rule_started(describe(spec.when), self._first_text(spec.when, person, now)
                                                     if spec.when.type != "random" else None, n))
        if spec.when.type == "once":
            return self.send(h, T.once_set(first, what, n) + notes)
        if spec.when.type == "random" or spec.when.window:
            first = None  # random moments are never shown in advance
        return self.send(h, T.rule_started(edited, describe(spec.when), c.goal, avoid, first) + notes)

    def _never_sends(self, person, spec, now):
        """The reply for a timed rule that would never send, else None. Random, window and every_hours moments never
        fall in quiet hours, so hours that are all quiet are said plainly rather than as 'that time has passed'."""
        w, tz = spec.when, person["timezone"]
        if w.type in ("now", "on_request", "new_items"):
            return None
        if next_run(w, tz, now, anchor=now, quiet=self.store.quiet(person["handle"])) is not None:
            return None
        if next_run(w, tz, now, anchor=now, quiet=[]) is not None:
            return T.ALL_QUIET
        return T.TIME_PASSED

    def _answer_seen(self, h):
        """The answer a typed reaction is about: the last one, unless that one was sent after the person's message
        arrived (a timed send that landed while they were typing); then it is the one before."""
        last = self.store.last_answer(h)
        received = getattr(self._tl, "received", None)
        if not last or not received:
            return last
        seen = self.store.one("SELECT run_id FROM sent WHERE handle=? AND run_id IS NOT NULL AND at<=? "
                              "ORDER BY at DESC, rowid DESC LIMIT 1", (h, now_iso(received)))
        if not seen or seen["run_id"] == last["run_id"]:
            return last
        rows = self.store.items_of_run(seen["run_id"])
        if not rows:
            return last
        return {"run_id": seen["run_id"], "rule_id": rows[0]["rule_id"], "items": [r["item_id"] for r in rows]}

    def _feedback(self, person, kind, pick_number):
        h = person["handle"]
        self.note(intent="feedback")
        last = self._answer_seen(h)
        if not last:
            return self.send(h, T.NOTHING_TO_ATTACH)
        items = last["items"]
        if pick_number and not 1 <= pick_number <= len(items):
            return self.send(h, T.which_pick(len(items)))
        chosen = [items[pick_number - 1]] if pick_number else items
        for iid in chosen:
            self.store.add_feedback(h, iid, last.get("rule_id"), kind)
        return self.send(h, T.FEEDBACK_REPLIES.get(kind, T.FEEDBACK_OTHER))

    # ---------- rule management ----------
    def _pick_rule(self, rules, number):
        if number is not None:
            return rules[number - 1] if 1 <= number <= len(rules) else None
        return rules[0] if len(rules) == 1 else None

    def _rules_text(self, person, rules):
        if not rules:
            return T.NO_RULES_LIST
        lines = [T.RULES_HEAD]
        now = self.clock()
        for i, r in enumerate(rules, 1):
            spec = RuleSpec.model_validate(r["spec"])
            state = T.RULE_PAUSED if r["status"] == "paused" else ""
            nxt = ""
            if r["status"] == "active" and r["next_run_at"] and spec.when.type == "schedule" and not spec.when.window:
                up = self._upcoming(r, person, now)
                nxt = T.rule_next(say_time(up, now, person["timezone"])) if up else ""
            lines.append(T.rule_line(i, spec.content.goal, describe(spec.when), state, nxt))
        lines.append(T.RULES_FOOT)
        return "\n".join(lines)

    def _manage(self, person, rules, action, number, all_rules, until=None, in_minutes=None):
        h = person["handle"]
        one = self._pick_rule(rules, number)
        targets = rules if all_rules else ([one] if one else [])
        if not targets:
            return self.send(h, T.WHICH_RULE if rules else T.NO_RULES)
        now = self.clock()
        back = resolve_until(until, in_minutes, now, person["timezone"]) if action == "pause" else None
        if back is not None and back <= now:
            back = None
        for r in targets:
            if action == "pause":
                self.store.pause_rule(r["id"], back)  # with a time, the scheduler resumes it then
            elif action == "stop":
                self.store.set_slot(r["id"], None, "stopped")
                self.store.update_rule(r["id"], paused_until=None)
            else:
                status, nxt = self._next_for(RuleSpec.model_validate(r["spec"]), person, now, r)
                self.store.set_slot(r["id"], nxt, status)
                self.store.update_rule(r["id"], paused_until=None)
        self._wrote(h, "rule_rows", f"{T.MANAGE_WORDS[action].lower()} " + ", ".join(
            f"\"{RuleSpec.model_validate(r['spec']).content.goal}\"" for r in targets),
            {"rows": self._rule_rows([r["id"] for r in targets])})
        word = T.MANAGE_WORDS[action]
        names = ", ".join(RuleSpec.model_validate(r["spec"]).content.goal for r in targets)
        msg = T.managed(word, names)
        if back:
            msg += T.resumes_at(say_time(back, now, person["timezone"]))
        return self.send(h, msg)

    def _skip(self, person, r, it, now):
        """'Skip the next one', 'skip the next two' (count), 'not on the 26th' (date), 'not Thanksgiving week' (date
        to until). The scheduler skips those sends when they come due and records them as 'skipped'."""
        tz = person["timezone"]
        dates = []
        if it.date:
            first = datetime.fromisoformat(it.date).date()
            last = datetime.fromisoformat(it.until[:10]).date() if it.until else first
            span = min(max((last - first).days, 0), 62)
            dates = [(first + timedelta(days=i)).isoformat() for i in range(span + 1)]
        count = 0 if dates else (it.count or 1)
        self.store.skip(r["id"], count=count, dates=dates)
        r = self.store.rule(r["id"])
        up = self._upcoming(r, person, now)
        if up is None:
            self.store.set_slot(r["id"], None, "done")
            return self.send(person["handle"], T.SKIPPED_LAST)
        if RuleSpec.model_validate(r["spec"]).when.type == "random":
            return self.send(person["handle"], T.SKIPPED_RANDOM)
        label = None
        if dates:
            first, last = datetime.fromisoformat(dates[0]), datetime.fromisoformat(dates[-1])
            label = first.strftime("%A %-d %B") if len(dates) == 1 else \
                f"{first.strftime('%-d %B')} to {last.strftime('%-d %B')}"
        return self.send(person["handle"], T.skipped(say_time(up, now, tz), count=count, dates=label))
