"""PROTOTYPE ONLY - the conversation side: messages in, dispatch, confirm, activate, feedback, rule management and
follow-ups (BRIEF-10 section 4). The interpreter fills forms (AGENTS.md rule 6); code acts. Mixed into core.Bot.
"""
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from . import profile as P
from . import texts as T
from .interpret import interpret
from .llm import budget_stop
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
# a clarify question waits as long as a preview: any next message uses it up, so a late answer still completes it
PENDING_TTL = {"confirm_rule": timedelta(hours=24), "confirm_delete": timedelta(minutes=30), "clarify": timedelta(hours=24)}
# what a message must be for an open preview to be dropped; small talk, questions about the last answer, feedback and
# rule management leave it open, so a later "yes" still starts the rule
ENDS_PENDING = ("ask", "change_rule", "delete_data", "decline", "stop")


# the export reminders offered in the setup (refresh.offer_export_routine names them so)
EXPORT_REMINDER = re.compile(r"^export reminders \((instagram|youtube)\)$")
HOW_EXPORT = re.compile(r"\bhow (?:do|can|should|would) i\b|\bsteps?\b|\binstructions?\b|\bhow to\b", re.I)


def change_words(old, new):
    """What a change to a rule changed, in plain words (fix pass 2, finding 50), or None when nothing but the time
    or the topic changed (those are said by the reply already)."""
    a, b = old.content, new.content
    out = []
    if a.outside != b.outside:
        out.append({"only": "now from YouTube, outside your saves",
                    "some": "now with new videos from YouTube as well as your saves",
                    "none": "now from your saves only"}[b.outside])
    if b.count != a.count:
        out.append(f"{b.count} {'pick' if b.count == 1 else 'picks'} each time")
    added = [x for x in b.avoid if x not in a.avoid]
    if added:
        out.append("nothing with " + ", ".join(added))
    back = [x for x in a.avoid if x not in b.avoid]   # checker, round 2: what a change takes away is said too
    if back:
        out.append(T.and_words(back) + " allowed again")
    crit = [x for x in b.criteria if x not in a.criteria]
    if crit:
        out.append("only ones that fit " + T.and_words([f"\"{x}\"" for x in crit]))
    gone = [x for x in a.criteria if x not in b.criteria]
    if gone:
        out.append("no longer only ones that fit " + T.and_words([f"\"{x}\"" for x in gone]))
    if b.platforms != a.platforms and b.platforms:
        out.append("only from " + T.and_words([T.PLATFORM_NAMES.get(p, p) for p in b.platforms]))
    elif b.platforms != a.platforms:
        out.append("from " + T.and_words([T.PLATFORM_NAMES.get(p, p) for p in ("instagram", "youtube")]))
    if b.order != a.order and b.order in ("newest", "oldest", "random", "easiest_first"):
        out.append({"newest": "newest first", "oldest": "oldest first", "random": "in a random order",
                    "easiest_first": "easiest first"}[b.order])
    names = {"email.send": "emailed to you", "calendar.add": "with a calendar link", "todo.add": "put on your list"}
    for act in [x.action for x in new.do if x.action not in {y.action for y in old.do}]:
        if act in names:
            out.append(names[act])
    stopped = {"email.send": "no longer emailed", "calendar.add": "without the calendar link",
               "todo.add": "no longer put on your list"}
    for act in [x.action for x in old.do if x.action not in {y.action for y in new.do}]:
        if act in stopped:
            out.append(stopped[act])
    return ", ".join(out) or None


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
        self._tl.sens_said = False   # the "left out one personal detail" line, at most once per message (finding 38)
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
                ref = self.onboard_start(person, now)   # slice 6: the setup starts with the read of the person
                self._contact_card(handle)
                return ref
            return self.send(handle, CONSENT)
        pending = self._live_pending(handle, now)
        if tapback:
            self.note(intent="tapback")
            run_id = self.store.run_for_ref(tapback_ref) if tapback_ref else None
            if (pending and pending["kind"] == "confirm_rule" and tapback == "up"
                    and run_id is not None and run_id == pending["payload"].get("run_id")):
                return self._confirm(person, pending)  # 👍 on the preview means yes
            rows = self.store.items_of_run(run_id) if run_id else []
            for d in rows:
                self.store.add_feedback(handle, d["item_id"], d["rule_id"], tapback)
            if rows:
                self._wrote_final(handle, "a reaction")
            return None
        if not text:
            return None
        r = REACTION_TEXT.match(text)
        if r:
            down = r.group(1).lower().startswith("disliked") or (r.group(2) == "👎")
            last = self.store.last_answer(handle)
            for iid in (last or {}).get("items", []):
                self.store.add_feedback(handle, iid, last.get("rule_id"), "down" if down else "up")
            if (last or {}).get("items"):
                self._wrote_final(handle, "a reaction")
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
        ref = self._email_text(person, text, now)   # a code, "new code", or the address the bot just asked for
        if ref is not None:
            return ref
        ref = self.onboard_step(person, text, now)   # slice 6: a step of the setup ("skip", their answer, "2")
        if ref is not None:
            return ref
        return self.answer_normally(person, text, now)

    def answer_normally(self, person, text, now):
        """The normal path for a message: what code reads by itself (plain commands, "another", a question about a
        shown pick: followup.py), the caps, the interpreter, then the dispatch."""
        handle = person["handle"]
        pending = self._live_pending(handle, now)
        rules = self.store.rules(handle)
        last = self.store.last_answer(handle)
        it, paid = self.code_reads(person, text, self._answer_seen(handle))
        if it is not None and not paid:   # "stop 2", "my rules", "undo": no model call, never misread
            return self._dispatch(person, it, text, rules, pending, last, now)
        over = self._over_cap(person)
        if over:
            self.note(intent="over_cap")
            return self._limit_notice(person, over)  # before any paid call
        if it is not None:
            return self._dispatch(person, it, text, rules, pending, last, now)
        if last and not last.get("rule_id"):
            last = dict(last, request=(self.store.get_state(f"lastspec:{handle}") or {}).get("text"))
        try:
            it, _ = interpret(text, person, rules, pending, last, now, todos=self.store.todos(handle),
                              last_write=self._last_write_ctx(handle, now), about=P.about_lines(self.store, handle, text),
                              store=self.store)
        except Exception as e:  # noqa: BLE001
            self.store.add_run(handle=handle, kind="interpret", status="error", error=type(e).__name__)
            if budget_stop(e):   # review fix X6: ai.py's budget guard refused the call: never a false "try again"
                self.note(intent="over_cap")
                return self._limit_notice(person, "total")
            return self.send(handle, T.INTERPRET_ERROR)
        return self._dispatch(person, it, text, rules, pending, last, now)

    def _contact_card(self, handle):
        """Once, after the person's first replies: our contact card, so their phone shows previews of our links
        (DESIGN.md section 11). Only on a channel that can send one; a failure never stops the welcome."""
        if self.store.get_state(f"card:{handle}"):
            return
        try:
            ref = self.channel.send_contact_card(handle)
        except Exception:  # noqa: BLE001 - the type is enough; the card is a nicety
            return
        if ref is not None:
            self.store.set_state(f"card:{handle}", True)
            self.send(handle, T.CONTACT_CARD)

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
        # what the setup's last question just changed rides on this answer (checker, round 2: it was reset here and
        # never said)
        self._tl.profile_said = getattr(self._tl, "carry_said", None)
        self._tl.carry_said = None
        for x in [it] + ([it.also] if it.also else []):
            known = {n.lower() for n in self.store.profile_notes(h)}
            if x.profile_note and x.profile_note.lower() not in known and x.intent != "profile_update" \
                    and getattr(self._tl, "merged_text", None) != text:   # onboarding merged this message already
                self._merge_note(person, x.profile_note, text, now)   # slice 6: merged into the profile
        self._tl.lang = it.lang
        self._tl.made_pending = False
        self._tl.chained = False
        self._tl.hint = text          # the message itself, for what code reads from it (a length bound: "mini")
        self._tl.ran_more = False
        before = self.store.get_state(f"lastwrite:{h}")
        try:
            ref = self._dispatch_one(person, it, text, rules, pending, last, now)
        except BaseException:
            self._tl.hint = None
            raise
        if it.also is not None and it.also.intent == "more" and self._tl.ran_more:
            pass   # "too hard, something shorter": the feedback already sent the shorter one
        elif it.also is not None:
            first = self.store.get_state(f"lastwrite:{h}")
            first = None if first == before else first   # only a write this message made
            self._tl.chained = True
            try:
                ref = self._dispatch_one(person, it.also, text, self.store.rules(h), self._live_pending(h, now),
                                         self.store.last_answer(h), now) or ref
            finally:
                self._tl.chained = False
            self._join_writes(h, first, self.store.get_state(f"lastwrite:{h}"))
        self._tl.hint = None
        said = getattr(self._tl, "profile_said", None)
        if said:   # what changed in the profile is always said; here when no reply carried it
            self._tl.profile_said = None
            ref = self.send(h, said) or ref
        return ref

    def _sensitive_once(self, prefix=""):
        """The line that says a personal detail was left out: the first time in this message only (finding 38)."""
        if getattr(self._tl, "sens_said", False):
            return ""
        self._tl.sens_said = True
        return prefix + T.PROFILE_SENSITIVE

    def _merge_note(self, person, note, text, now):
        """A lasting fact said inside a request ("I'm vegetarian now, any dinner ideas?"): merged into the profile by
        the form call, and the line saying what changed rides on the reply. When the call fails or changes nothing,
        the note is kept as it is (as before)."""
        h = person["handle"]
        res = None
        if not self._over_cap(person):
            try:
                res, _ = P.merge(self.store, h, text)
            except Exception as e:  # noqa: BLE001
                self.store.add_run(handle=h, kind="profile_merge", status="error", error=type(e).__name__)
        if res and res["changes"]:
            self._tl.profile_said = T.profile_changed(res["changes"],
                                                      res["skipped_sensitive"] and self._sensitive_once())
            return
        if not P.stated_sensitive(note):
            self.store.add_profile_note(h, note, at=now)

    def _profile_tail(self):
        """The profile line for a reply that carries it (once)."""
        said = getattr(self._tl, "profile_said", None)
        if not said:
            return ""
        self._tl.profile_said = None
        return "\n\n" + said

    def _join_writes(self, h, first, second):
        """Two writes of one message ("add milk and eggs", two reminders) are one write for 'undo'. Two writes of
        different kinds ("add milk to my list and pause the yoga one") are kept as both, and 'undo' reverses both
        (fix pass, finding 25)."""
        if not first or not second or first == second:
            return
        if first["kind"] != second["kind"] or first["kind"] not in ("todo_add", "rule_add"):
            parts = (first["undo"]["writes"] if first["kind"] == "multi" else [first]) + [second]
            self.store.set_state(f"lastwrite:{h}", {"kind": "multi", "say": first["say"] + " and " + second["say"],
                                                    "undo": {"writes": parts}, "at": second["at"]})
            return
        if first["kind"] == "todo_add":
            undo = {"ids": first["undo"]["ids"] + second["undo"]["ids"]}
        else:
            ids = (first["undo"].get("rule_ids") or [first["undo"]["rule_id"]]) + \
                (second["undo"].get("rule_ids") or [second["undo"]["rule_id"]])
            undo = {"rule_id": ids[0], "rule_ids": list(dict.fromkeys(ids))}
        self.store.set_state(f"lastwrite:{h}", dict(second, say=first["say"] + " and " + second["say"], undo=undo))

    def _dispatch_one(self, person, it, text, rules, pending, last, now):
        h = person["handle"]
        self.note(intent=it.intent)
        if it.intent in ("profile_update", "chat") and getattr(self._tl, "merged_text", None) == text:
            # a setup answer the form call merged already: no second "Noted" and no small talk beside the setup's
            # own reply (fix pass 2, finding 42)
            return None
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
                if self.to_someone_else(text):   # sending to others stays out; offer to send it to them (section 11)
                    return self.send(h, T.EMAIL_ONLY_YOU)
                # fix pass 2, finding 62: never the model's own words for a request it would not do: code picks the
                # sentence (the model's "reply" is not shown)
                return self.send(h, T.unsupported_reply(text, it.reply, lang=it.lang))
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
            if it.spec.when.type in ("once", "on_request") or it.spec.content.source in ("note", "todos"):
                # one send at a stated time, a saved request, or a reminder in their own words: nothing from the
                # library repeats, so no preview is needed; the reply states what will happen and how to stop it
                return self._activate(person, text, it.spec)
            if pending and it.edits_pending and T.YES_WITH_EDIT.match(text):
                same = it.spec.stored()["content"] == RuleSpec.model_validate(pending["payload"]["spec"]).stored()["content"]
                ref = self._activate(person, pending["payload"]["text"] + " / " + text, it.spec, edited=True,
                                     preview_run=pending["payload"].get("run_id") if same else None)
                return self._activate_more(person, pending, ref)
            more = (pending["payload"].get("more") or []) if pending and pending["kind"] == "confirm_rule" else []
            if pending and it.edits_pending:  # keep the whole request, not only the edit
                text = pending["payload"]["text"] + " / " + text
            never = self._never_sends(person, it.spec, now)
            if never:  # no preview for a rule that would never send (its end has passed, or every moment is quiet)
                return self.send(h, never)
            joined = chained and pending and pending["kind"] == "confirm_rule" and getattr(self._tl, "made_pending", False)
            self._tl.auto_outside = False
            msg, run_id, n = self.run(person, it.spec, "preview", request_text=text)
            offer = self._preview_supply(person, it.spec, text, run_id, now)
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
                                                           "more": more, "outside_offer": bool(offer[1])},
                                       at=self.clock())
                self._tl.made_pending = True
                tail = T.preview_tail(describe(it.spec.when), what, first, heads=offer[0], offer=offer[1])
                if more:
                    tail += " " + T.preview_more_note(len(more))
            w = it.spec.when
            if w.every_hours and w.window:  # more sends a day than the daily limit allows: the preview says so
                per_day = (int(w.window[1][:2]) * 60 + int(w.window[1][3:]) - int(w.window[0][:2]) * 60
                           - int(w.window[0][3:])) // (w.every_hours * 60) + 1
                if per_day > config.MAX_SCHEDULED_PER_DAY:
                    tail += T.daily_limit_note(config.MAX_SCHEDULED_PER_DAY)
            tail += self._do_note(it.spec) + self._not_yet_notes(it.spec)
            head = T.PREVIEW_HEAD if n else ""
            return self.send(h, head + msg + tail, run_id)
        if it.intent == "ask":
            msg, run_id, _ = self.run(person, it.spec, "ask", request_text=text)
            return self.deliver(person, it.spec, msg + self._not_yet_notes(it.spec, sep="\n\n"), run_id, kind="ask",
                                request_text=text, after=self._profile_tail())
        if it.intent == "more":
            return self._more(person, it, text)
        if it.intent == "follow_up":
            if not last:
                return self.send(h, T.NOTHING_TO_FOLLOW_UP)
            from .followup import detail_kinds, pick_number
            kinds = detail_kinds(it.question or "", text)
            if kinds:   # the details of a pick already shown: answered directly, never "I recommend" (findings 4, 5)
                seen = self._answer_seen(h) or last
                n = it.pick_number or pick_number(text, len(seen["items"])) or 1
                return self._detail_answer(person, seen, kinds, n)
            view = self.view(person["library"])
            cands = [c for c in (view.get(i) for i in last["items"]) if c]
            spec = self._spec_for_followup(last, it.question, it.avoid, h)
            known = self.store.get_state(f"lines:{h}", {}) or {}
            msg, run_id, _ = self.run(person, spec, "follow_up", request_text=it.question, cands_override=cands,
                                      known_lines=known)
            return self.send(h, msg, run_id)
        if it.intent == "feedback":
            return self._feedback(person, it.feedback, it.pick_number, it=it, text=text)
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
            old = RuleSpec.model_validate(r["spec"])
            self._wrote(h, "rule_rows", f"changed rule \"{old.content.goal}\"", {"rows": self._rule_rows([r["id"]])})
            # fix pass 2, finding 51: the rule keeps the words it was made with (its outside search and its length
            # bound are read from them); the change is added after them, never in their place
            kept = (r.get("text") or "").strip()
            self.store.update_rule(r["id"], spec=it.spec.stored(),
                                   text=text if not kept else (kept if text in kept else f"{kept} / {text}"))
            self.store.set_slot(r["id"], nxt, status if r["status"] == "active" else r["status"])
            return self.send(h, T.changed(describe(it.spec.when), it.spec.content.goal, change_words(old, it.spec))
                             + self._do_note(it.spec) + self._not_yet_notes(it.spec)
                             + self._email_ask(person, it.spec, now))
        if it.intent == "run_rule":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE if rules else T.NO_RULES_ASK)
            spec = RuleSpec.model_validate(r["spec"])
            # review fix X1: "run 1" is read by code (no interpreter call), but its run searches and composes, so the
            # caps are checked here, before any paid call; a reminder or a kept answer costs nothing and still runs
            over = self._over_cap(person) if spec.content.source in ("library", "recent") else None
            if over:
                self.note(intent="over_cap")
                return self._limit_notice(person, over)
            msg, run_id, _ = self.run(person, spec, "manual", rule_id=r["id"], request_text=text)
            if it.skip_next and r["status"] == "active" and r["next_run_at"] and not self._run_failed(run_id):
                rows = self._rule_rows([r["id"]])
                self.store.skip(r["id"], count=1)  # "send Friday's one now": Friday's is not sent again
                # and this send counts as Friday's toward "3 times in all" (review fix S10)
                self.store.set_state(f"replaced:{r['id']}", (self.store.get_state(f"replaced:{r['id']}", 0) or 0) + 1)
                self._wrote(h, "rule_rows", "skipped the next send of a rule", {"rows": rows})
                up = self._upcoming(self.store.rule(r["id"]), person, now)
                msg += "\n\n" + (T.skipped_next(say_time(up, now, person["timezone"])) if up else T.SKIPPED_LAST)
                if up is None:
                    self.store.set_slot(r["id"], None, "done")
            return self.deliver(person, spec, msg, run_id, kind="manual", rule_id=r["id"], request_text=r.get("text"))
        if it.intent == "skip":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, T.WHICH_RULE if rules else T.NO_RULES)
            if r["status"] != "active" or not r["next_run_at"]:
                return self.send(h, T.NO_SEND_COMING)
            self._wrote(h, "rule_rows", "skipped sends of a rule", {"rows": self._rule_rows([r["id"]])})
            return self._skip(person, r, it, now)
        if it.intent == "set_timezone":
            live = [r["id"] for r in self.store.rules(h, statuses=("active",))]
            self._wrote(h, "timezone", f"switched to {T.zone_name(it.timezone)} time",
                        {"timezone": person["timezone"], "revert_to": person.get("tz_revert_to"),
                         "revert_at": person.get("tz_revert_at"), "rows": self._rule_rows(live),
                         "todos": [{"id": t["id"], "due_at": t["due_at"]} for t in self.store.todos(h)
                                   if t.get("due_at") and not t.get("reminded_at")]})
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
            # a one-off time that, read in the new zone, has already passed ends its rule: the reply says so
            ended = [RuleSpec.model_validate(r["spec"]).content.goal for r in map(self.store.rule, live)
                     if r and r["status"] == "done"]
            if ended:
                msg += T.ended_by_move(ended)
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
            return self._act_on_last(person, it, text, now)
        if it.intent == "set_email":
            return self.set_email_from(person, it.email, text, now)
        if it.intent == "library_stats":
            return self._library_stats(person, it)
        if it.intent == "profile_update":
            return self._profile_update(person, text, now)
        if it.intent == "library_status":
            from .refresh import library_status
            # "how do I export?", "how do I get my new saves in?": the steps too (findings 43 and 60)
            return self.send(h, library_status(self, person, now, steps=bool(HOW_EXPORT.search(text))))
        if it.intent == "profile_show":
            return self.send(h, P.show_text(P.get(self.store, h), now))
        return self.send(h, HELP)

    def _profile_update(self, person, text, now):
        """'I'm past beginner at Blender now', 'I have an air fryer', 'stop guessing my level': the form call fills
        the profile form, code applies it, and the reply says what changed. If nothing could be applied, their words
        are kept as a note (as before)."""
        h = person["handle"]
        res = None
        try:
            res, _ = P.merge(self.store, h, text)
        except Exception as e:  # noqa: BLE001
            self.store.add_run(handle=h, kind="profile_merge", status="error", error=type(e).__name__)
        if res and res["changes"]:
            return self.send(h, T.profile_changed(res["changes"], res["skipped_sensitive"] and self._sensitive_once()))
        note = " ".join(text.split())[:300]
        if P.stated_sensitive(note):
            return self.send(h, self._sensitive_once() or T.PROFILE_NOTED)
        if note.lower() not in {n.lower() for n in self.store.profile_notes(h)}:
            self.store.add_profile_note(h, note, at=now)
        return self.send(h, T.PROFILE_NOTED)

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
        """One honest line when a spec asks for something that comes in a later slice. None is left: outside picks
        (slice 5) say in the answer itself when they cannot be served."""
        notes = []
        return (sep + " ".join(notes)) if notes else ""

    def _rule_rows(self, ids):
        cols = "id, text, spec, status, next_run_at, slot_at, paused_until, skip_count, skip_dates"
        return [self.store.one(f"SELECT {cols} FROM rules WHERE id=?", (i,)) for i in ids]

    def _restore_rows(self, rows):
        for row in rows:
            self.store.x("UPDATE rules SET text=?, spec=?, status=?, next_run_at=?, slot_at=?, paused_until=?, "
                         "skip_count=?, skip_dates=? WHERE id=?",
                         (row["text"], row["spec"], row["status"], row["next_run_at"], row["slot_at"],
                          row["paused_until"], row["skip_count"], row["skip_dates"], row["id"]))

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
        moved = [r for r in self.store.rules(h, statuses=("active",))
                 if RuleSpec.model_validate(r["spec"]).when.type == "random" or RuleSpec.model_validate(r["spec"]).when.window]
        self._wrote(h, "quiet", "changed the quiet hours", {"quiet": old, "rows": self._rule_rows([r["id"] for r in moved])})
        ended = []
        for r in moved:   # moments drawn inside the new quiet hours are redrawn
            spec = RuleSpec.model_validate(r["spec"])
            status, nxt = self._next_for(spec, person, now, r)
            self.store.set_slot(r["id"], nxt, status)
            if status == "done":   # its hours are now all quiet: the rule ends, and the reply says so
                ended.append(spec.content.goal)
        tail = T.quiet_ended(ended) if ended else ""
        if blocks is None:
            return self.send(h, T.QUIET_RESET + tail)
        return self.send(h, T.quiet_set(T.quiet_words(self.store.quiet(h))) + tail)

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
            return self.send(h, T.SNOOZE_PASSED)
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
        self.store.set_state(lw.get("key") or f"lastwrite:{h}", None)
        writes = lw["undo"]["writes"] if lw["kind"] == "multi" else [lw]
        said = [x for x in (self._undo_one(h, w, now) for w in reversed(writes)) if x]   # the last write first
        if not said:
            final = [w["say"] for w in writes if w["kind"] == "final"]
            return self.send(h, T.cant_undo(" or ".join(dict.fromkeys(final))) if final else T.NOTHING_TO_UNDO)
        return self.send(h, T.undone("; ".join(reversed(said))))

    def _undo_one(self, h, lw, now):
        """Reverses one write; returns what was undone, in words (or None)."""
        k, u = lw["kind"], lw["undo"]
        if k == "todo_add":
            for i in u["ids"]:
                self.store.update_todo(i, removed_at=now_iso(now))
            return f"I took {'that' if len(u['ids']) == 1 else 'those'} off your list ({lw['say']})"
        if k in ("todo_done", "todo_remove"):
            for i in u["ids"]:
                self.store.update_todo(i, **{u["col"]: None})
            return "it's back on your list"
        if k == "todo_due":
            for row in u["rows"]:
                self.store.update_todo(row["id"], due_at=row["due_at"], reminded_at=row["reminded_at"])
            return "the reminder is off"
        if k == "rule_add":
            ids = u.get("rule_ids") or [u["rule_id"]]
            goals = []
            for i in ids:
                r = self.store.rule(i)
                self.store.set_slot(i, None, "stopped")
                goals.append(RuleSpec.model_validate(r["spec"]).content.goal if r else "that rule")
            if len(goals) == 1:
                return f"I stopped the rule I just started, \"{goals[0]}\""
            return "I stopped the rules I just started, " + ", ".join(f"\"{g}\"" for g in goals)
        if k == "rule_rows":
            self._restore_rows(u["rows"])
            goals = ", ".join(RuleSpec.model_validate(json.loads(row["spec"])).content.goal for row in u["rows"])
            return f"\"{goals}\" is back as it was"
        if k == "quiet":
            self.store.set_quiet(h, u["quiet"])
            self._restore_rows(u.get("rows") or [])   # random and window moments as they were drawn before
            return "your quiet hours are back as they were"
        if k == "snooze":
            back = datetime.fromisoformat(u["snooze"]) if u.get("snooze") else None
            self.store.set_snooze(h, back)
            return "timed messages are back as they were"
        if k == "timezone":
            at = datetime.fromisoformat(u["revert_at"]) if u.get("revert_at") else None
            self._move_timezone(h, u["timezone"], now, revert_to=u.get("revert_to"), revert_at=at)
            self._restore_rows(u.get("rows") or [])   # the sends as they were before the switch
            for t in u.get("todos") or []:   # and the to-do reminders (review fix S6)
                row = self.store.todo(t["id"])
                if row and not row.get("reminded_at"):
                    self.store.update_todo(t["id"], due_at=t["due_at"])
            return f"I'm back on {T.zone_name(u['timezone'])} time"
        return None

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

    def _preview_supply(self, person, spec, text, run_id, now):
        """(heads-up, offer) for a repeating library rule's preview (findings 19 and 26): how many fitting items code
        saw (clear and close, from the composer's verdicts), said when under 3; and, when YouTube can serve it, the
        offer to include new videos from there (YES then stores outside "some")."""
        info = getattr(self._tl, "run_info", None) or {}
        c = spec.content
        if c.source != "library" or not spec.when.repeating or info.get("run_id") != run_id:
            return "", ""
        supply = info.get("n_clear", 0) + info.get("n_close", 0)
        # fewer than 3 that fit BEYOND the pick this preview shows: the rule would run dry within a few sends
        low = supply - min(supply, info.get("n_picks", 0)) < 3
        shown = bool(getattr(self._tl, "auto_outside", False))
        heads = T.supply_note(supply) if low else ""
        offer = ""
        if (low or shown) and c.outside == "none":
            try:
                ok = shown or self._outside().available(person["handle"], spec, [text], now=now)
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                offer = T.outside_offer(describe(spec.when), shown=shown)
        return heads, offer

    def _confirm(self, person, pending):
        h = person["handle"]
        self.note(intent="confirm")
        self.store.clear_pending(h)
        if pending["kind"] == "confirm_rule" and EXPORT_REMINDER.match(str(pending["payload"].get("text") or "")):
            self._tl.join_write = True
            try:   # only export reminders: one line for all of them (finding 44)
                return self._start_export_reminders(person, [pending["payload"]] +
                                                    list(pending["payload"].get("more") or []))
            finally:
                self._tl.join_write = False
        if pending["kind"] == "confirm_rule":
            spec = RuleSpec.model_validate(pending["payload"]["spec"])
            if pending["payload"].get("outside_offer") and spec.content.outside == "none":
                spec.content.outside = "some"   # the YES answers the offer too: new videos from YouTube as well
            ref = self._activate(person, pending["payload"]["text"], spec,
                                 preview_run=pending["payload"].get("run_id"))
            return self._activate_more(person, pending, ref)
        if pending["kind"] == "confirm_delete":
            # review fix PRIV-5: the inbox folder (raw exports, the failed ones too) goes with the rows; every library
            # that was theirs is named in the deletion line for a founder to remove, and so are ledger rows written
            # with their handle before the ledger used a hashed ref. One deletion list per store (PRIV-3).
            from . import llm
            from .refresh import forget_inbox
            inbox_left = forget_inbox(self.store, h)
            gone = self.store.delete_person_data(h)
            line = {"handle": h, "library": person["library"], "libraries": gone["libraries"], "at": now_iso()}
            if inbox_left:
                line["inbox_left"] = inbox_left
            old_rows = llm.rows_naming(h)
            if old_rows:
                line["ledger_rows_with_handle"] = old_rows
            self.store.add_deletion(line)
            # sent through the channel directly, so nothing new is recorded about the person
            return self.channel.send(h, T.DELETED)
        return None

    def _activate_more(self, person, pending, ref):
        """A second rule shown in the same preview starts with the same YES; 'undo' then stops both. Export
        reminders started this way are said in one line together (finding 44)."""
        self._tl.join_write = True
        exports = []
        try:
            for extra in pending["payload"].get("more") or []:
                if EXPORT_REMINDER.match(str(extra.get("text") or "")):
                    exports.append(extra)
                    continue
                ref = self._activate(person, extra["text"], RuleSpec.model_validate(extra["spec"])) or ref
            if exports:
                ref = self._start_export_reminders(person, exports) or ref
        finally:
            self._tl.join_write = False
        return ref

    def _start_export_reminders(self, person, entries):
        """The export reminders a YES started, said in one line: 'Done. Next Instagram reminder 10 December, next
        YouTube one 12 January.' (finding 44: never their whole text)."""
        h, tz = person["handle"], person["timezone"]
        now = self.clock()
        nexts = []
        for e in entries:
            spec = RuleSpec.model_validate(e["spec"])
            rule_id = self.store.add_rule(h, e["text"], spec.stored(), "active", None, created_at=now_iso(now))
            nxt = next_run(spec.when, tz, now, anchor=now, seed=rule_id, quiet=self.store.quiet(h))
            if nxt is None:
                self.store.set_slot(rule_id, None, "done")
                continue
            self.store.set_slot(rule_id, now_iso(nxt), "active")
            self._wrote_rule(h, f"started the {EXPORT_REMINDER.match(e['text']).group(1)} export reminder", rule_id)
            nexts.append((EXPORT_REMINDER.match(e["text"]).group(1), nxt.astimezone(ZoneInfo(tz))))
        return self.send(h, T.export_started(nexts)) if nexts else None

    def _wrote_rule(self, h, say, rule_id):
        """The last write for 'undo': a rule started (with the rules the same YES started before it)."""
        ids, says = [rule_id], [say]
        if getattr(self._tl, "join_write", False):
            prev = self.store.get_state(f"lastwrite:{h}") or {}
            if prev.get("kind") == "rule_add":
                ids = (prev["undo"].get("rule_ids") or [prev["undo"]["rule_id"]]) + ids
                says = [prev["say"]] + says
        self._wrote(h, "rule_add", " and ".join(says), {"rule_id": ids[0], "rule_ids": ids})

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
            self._wrote_rule(h, f"saved a rule, \"{c.goal}\"", rule_id)
            n = len(self.store.rules(h))
            return self.send(h, T.saved_rule(n, what) + self._do_note(spec) + self._not_yet_notes(spec)
                             + self._email_ask(person, spec, now))
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
        self._wrote_rule(h, f"started a rule, \"{c.goal}\" ({describe(spec.when)})", rule_id)
        if preview_run:  # the preview's picks count as sent by this rule, so its first send is something new
            self.store.x("UPDATE deliveries SET rule_id=? WHERE run_id=? AND handle=?", (rule_id, preview_run, h))
            shown = self.store.get_state(f"outside_shown:{h}", {}) or {}
            if shown.get(f"preview:{preview_run}"):   # finding 33: so are the preview's videos from YouTube
                box = shown.setdefault(f"rule:{rule_id}", {})
                box.update(shown.pop(f"preview:{preview_run}"))
                self.store.set_state(f"outside_shown:{h}", shown)
            # 👍, 👎 and "more like 2" given on the preview belong to the rule it became
            self.store.x("UPDATE feedback SET rule_id=? WHERE handle=? AND rule_id IS NULL AND item_id IN "
                         "(SELECT item_id FROM deliveries WHERE run_id=?)", (rule_id, h, preview_run))
        n = next((i for i, r in enumerate(self.store.rules(h), 1) if r["id"] == rule_id), len(self.store.rules(h)))
        first = say_time(nxt, now, spec.when.tz or tz)
        notes = self._do_note(spec) + self._not_yet_notes(spec) + self._email_ask(person, spec, now)
        if c.source == "note":   # a reminder in their own words
            if spec.when.type == "once":
                return self.send(h, T.reminder_once(first, c.text, n) + notes)
            return self.send(h, T.reminder_started(describe(spec.when), c.text, self._first_text(spec.when, person, now)
                                                   if spec.when.type != "random" else None, n) + notes)
        if c.source == "todos":
            if spec.when.type == "once":
                return self.send(h, T.todos_once(first, n) + notes)
            return self.send(h, T.todos_rule_started(describe(spec.when), self._first_text(spec.when, person, now)
                                                     if spec.when.type != "random" else None, n) + notes)
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

    def _feedback(self, person, kind, pick_number, it=None, text=""):
        h = person["handle"]
        self.note(intent="feedback")
        last = self._answer_seen(h)
        if not last:
            return self.send(h, T.NOTHING_TO_ATTACH)
        items = last["items"]
        if pick_number and not 1 <= pick_number <= len(items):
            return self.send(h, T.which_pick(len(items)))
        chosen = [items[pick_number - 1]] if pick_number else items
        if kind == "done" and not pick_number and len(items) > 1:
            chosen = items[:1]   # "made it" is about the recommended pick, not every alternative
        for iid in chosen:
            self.store.add_feedback(h, iid, last.get("rule_id"), kind)
        self._wrote_final(h, "feedback on a pick")
        if kind in ("harder", "easier"):   # slice 6: the level of the answer's topic moves one step, and is said
            spec = (self.store.get_state(f"lastspec:{h}") or {})
            words = " ".join(x for x in [last.get("goal") or "", spec.get("text") or ""] if x)
            interest, level = P.move_level(self.store, h, words, kind)
            if spec and not self._over_cap(person):
                # fix pass, finding 6: "too hard, something shorter" records the feedback AND sends one now, in one
                # reply: the same request without what was shown, easiest first for "easier", with the change it
                # carries ("shorter" is a length bound worked out by code from the message)
                from .schema import Interpretation
                more = it.also if it is not None and it.also is not None and it.also.intent == "more" else None
                ask = Interpretation(intent="more", criteria=[*(it.criteria if it else []),
                                                              *(more.criteria if more else [])][:5],
                                     avoid=[*(it.avoid if it else []), *(more.avoid if more else [])][:8])
                lead = T.level_moved_now(interest["topic"] if interest else None,
                                         P.LEVEL_PLAIN[level] if interest else None, kind, T.SHORTER.search(text or ""))
                none = (T.level_moved_only(interest["topic"], P.LEVEL_PLAIN[level], kind) if interest else "Noted.") \
                    + "\n\n"
                self._tl.ran_more = True
                return self._more(person, ask, text, lead=lead, easier=(kind == "easier"), lead_none=none)
            if interest:
                return self.send(h, T.level_moved(interest["topic"], P.LEVEL_PLAIN[level], kind))
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
        rows = self._rule_rows([r["id"] for r in targets])   # as they were, for "undo"
        ended = []
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
                if status == "done":   # its only time passed while it was paused: it ends, and the reply says so
                    ended.append(RuleSpec.model_validate(r["spec"]).content.goal)
        self._wrote(h, "rule_rows", f"{T.MANAGE_WORDS[action].lower()} " + ", ".join(
            f"\"{RuleSpec.model_validate(r['spec']).content.goal}\"" for r in targets), {"rows": rows})
        word = T.MANAGE_WORDS[action]
        names = ", ".join(RuleSpec.model_validate(r["spec"]).content.goal for r in targets
                          if RuleSpec.model_validate(r["spec"]).content.goal not in ended)
        msg = T.managed(word, names) if names else ""
        if ended:
            msg = (msg + " " if msg else "") + T.ended_on_resume(ended)
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
