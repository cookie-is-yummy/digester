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
from .schedule import describe, next_run, resolve_until, say_time
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
        elif pending and YES.match(text):
            return self._confirm(person, pending)
        elif pending and NO.match(text):
            self.store.clear_pending(handle)
            return self.send(handle, T.NOT_STARTED)
        over = self._over_cap(person)
        if over:
            self.note(intent="over_cap")
            return self._limit_notice(person, over)  # before any paid call
        rules = self.store.rules(handle)
        last = self.store.last_answer(handle)
        try:
            it, _ = interpret(text, person, rules, pending, last, now)
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
        h = person["handle"]
        self.note(intent=it.intent)
        if pending and (it.intent in ENDS_PENDING or (it.intent == "new_rule" and not it.edits_pending)):
            self.store.clear_pending(h)  # a different request ends the question that was open
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
        if it.intent == "new_rule":
            if it.spec.when.type in ("once", "on_request"):
                # one send at a stated time, or a saved request: nothing recurring starts, so no preview is needed;
                # the reply states exactly what will happen and how to cancel it
                return self._activate(person, text, it.spec)
            if pending and it.edits_pending and T.YES_WITH_EDIT.match(text):
                same = it.spec.stored()["content"] == RuleSpec.model_validate(pending["payload"]["spec"]).stored()["content"]
                return self._activate(person, pending["payload"]["text"] + " / " + text, it.spec, edited=True,
                                      preview_run=pending["payload"].get("run_id") if same else None)
            if pending and it.edits_pending:  # keep the whole request, not only the edit
                text = pending["payload"]["text"] + " / " + text
            never = self._never_sends(person, it.spec, now)
            if never:  # no preview for a rule that would never send (its end has passed, or every moment is quiet)
                return self.send(h, never)
            msg, run_id, n = self.run(person, it.spec, "preview", request_text=text)
            if self._run_failed(run_id):  # no preview, so nothing to say yes to
                self.store.clear_pending(h)
                return self.send(h, msg, run_id)
            self.store.set_pending(h, "confirm_rule", {"text": text, "spec": it.spec.stored(), "run_id": run_id},
                                   at=self.clock())
            when = describe(it.spec.when)
            c = it.spec.content
            what = T.picks_for(c.count, c.goal)
            tail = T.preview_tail(when, what)
            w = it.spec.when
            if w.every_hours and w.window:  # more sends a day than the daily limit allows: the preview says so
                per_day = (int(w.window[1][:2]) * 60 + int(w.window[1][3:]) - int(w.window[0][:2]) * 60
                           - int(w.window[0][3:])) // (w.every_hours * 60) + 1
                if per_day > config.MAX_SCHEDULED_PER_DAY:
                    tail += T.daily_limit_note(config.MAX_SCHEDULED_PER_DAY)
            head = T.PREVIEW_HEAD if n else ""
            return self.send(h, head + msg + tail, run_id)
        if it.intent == "ask":
            msg, run_id, _ = self.run(person, it.spec, "ask", request_text=text)
            return self.send(h, msg, run_id)
        if it.intent == "more":
            st = self.store.get_state(f"lastspec:{h}")
            if not st:
                return self.send(h, T.MORE_OF_WHAT)
            spec = RuleSpec.model_validate(st["spec"])
            rule = self.store.rule(st["rule_id"]) if st.get("rule_id") else None
            if rule and rule["status"] in ("active", "paused"):  # one more from a rule counts as sent by that rule
                msg, run_id, _ = self.run(person, spec, "manual", rule_id=rule["id"], request_text=st.get("text") or text,
                                          shown=st.get("shown") or [])
            else:
                msg, run_id, _ = self.run(person, spec, "more", request_text=st.get("text") or text,
                                          shown=st.get("shown") or [])
            return self.send(h, msg, run_id)
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
            self.store.update_rule(r["id"], spec=it.spec.stored(), text=text)
            self.store.set_slot(r["id"], nxt, status if r["status"] == "active" else r["status"])
            return self.send(h, T.changed(describe(it.spec.when), it.spec.content.goal))
        if it.intent == "run_rule":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE if rules else T.NO_RULES_ASK)
            msg, run_id, _ = self.run(person, RuleSpec.model_validate(r["spec"]), "manual", rule_id=r["id"],
                                      request_text=text)
            if it.skip_next and r["status"] == "active" and r["next_run_at"] and not self._run_failed(run_id):
                self.store.skip(r["id"], count=1)  # "send Friday's one now": Friday's is not sent again
            return self.send(h, msg, run_id)
        if it.intent == "skip":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE if rules else T.NO_RULES)
            if r["status"] != "active" or not r["next_run_at"]:
                return self.send(h, T.NO_SEND_COMING)
            return self._skip(person, r, it, now)
        if it.intent == "set_timezone":
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
        return self.send(h, HELP)

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
            return self._activate(person, pending["payload"]["text"], RuleSpec.model_validate(pending["payload"]["spec"]),
                                  preview_run=pending["payload"].get("run_id"))
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
        self.store.clear_pending(h)
        now = self.clock()
        tz = person["timezone"]
        c = spec.content
        avoid = T.avoid_clause(c.avoid)
        what = T.picks_for(c.count, c.goal) + avoid
        if spec.when.type in ("on_request", "new_items"):
            self.store.add_rule(h, text, spec.stored(), "active", None, created_at=now_iso(now))
            n = len(self.store.rules(h))
            return self.send(h, T.saved_rule(n, what))
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
        if preview_run:  # the preview's picks count as sent by this rule, so its first send is something new
            self.store.x("UPDATE deliveries SET rule_id=? WHERE run_id=? AND handle=?", (rule_id, preview_run, h))
            # 👍, 👎 and "more like 2" given on the preview belong to the rule it became
            self.store.x("UPDATE feedback SET rule_id=? WHERE handle=? AND rule_id IS NULL AND item_id IN "
                         "(SELECT item_id FROM deliveries WHERE run_id=?)", (rule_id, h, preview_run))
        n = len(self.store.rules(h))
        first = say_time(nxt, now, tz)
        if spec.when.type == "once":
            return self.send(h, T.once_set(first, what, n))
        if spec.when.type == "random" or spec.when.window:
            first = None  # random moments are never shown in advance
        return self.send(h, T.rule_started(edited, describe(spec.when), c.goal, avoid, first))

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
