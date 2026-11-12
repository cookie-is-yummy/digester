"""PROTOTYPE ONLY - the scheduler: tick, the guards before a timed send, retries and recovery (BRIEF-10 section 5,
DESIGN.md sections 1 and 11).

Mixed into core.Bot.

The order of the guards for a due rule: the person's kill switch; the unanswered-sends pause; too late (missed); a skip
the person asked for (by count or date); their snooze; their quiet hours; the daily limit of timed sends; the budget.
Every slot that does not go out is recorded in `runs` with a status that says why: missed, skipped, snoozed,
quiet_hours, daily_limit, over_cap.

Holds. A send that cannot go out yet but should still go out (a retry, or a random, window or every_hours moment that
lands in quiet hours after the person changed them, or a one-time send over the daily limit) is held: next_run_at moves
to the release time and the state key hold:<rule id> remembers it. Lateness is then counted from the release, so a
hold never turns into a silent 'missed'. A held repeating send whose next regular slot comes before the release is
skipped and recorded instead, so the person never gets two at once.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .channels.base import SendUncertain
from .schedule import _at, end_of_quiet, in_quiet_hours, next_run
from .schema import RuleSpec
from .store import now_iso
from .texts import LAST_SEND, PAUSED_QUIET, STILL_USEFUL

UNANSWERED_CHECK = 3   # after this many timed sends in a row with no word from the person, the next one asks
UNANSWERED_PAUSE = 5   # after this many, their timed sends are paused (message services flag unanswered streams)
MISSED_AFTER = timedelta(hours=2)   # a timed send this late is skipped, not sent (the bot was off, or kept failing)
RETRY_AFTER = timedelta(minutes=15)
MAX_RETRIES = 3
SENT_STATUSES = ("sent", "none_sent", "unknown")


class SchedulerMixin:
    def tick(self):
        now = self.clock()
        self._upkeep(now)
        sent = 0
        for rule in self.store.due_rules(now):
            progress = {}
            try:
                sent += self._tick_rule(rule, now, progress)
            except Exception as e:  # noqa: BLE001 - one rule never blocks the others
                self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status="error",
                                   error=type(e).__name__, at=now_iso(now))
                if progress.get("advanced"):
                    # The rule had already moved on to its next slot, and the message may already be out. Trying this
                    # slot again could send it twice, so it is treated like a crash while sending: never sent again.
                    if progress.get("run_id"):
                        self.store.x("UPDATE runs SET status='unknown', error=? WHERE id=? AND status='sending'",
                                     (type(e).__name__, progress["run_id"]))
                    continue
                slot = progress.get("slot") or datetime.fromisoformat(rule.get("slot_at") or rule["next_run_at"])
                self._retry_or_skip(self.store.rule(rule["id"]) or rule, now, slot)
        sent += self._tick_todos(now)   # due to-dos remind once (todos.py)
        return sent

    # ---------- what changes with time alone ----------
    def _upkeep(self, now):
        """A temporary time zone switches back, and a rule paused until a time resumes."""
        for p in self.store.timezone_reverts_due(now):
            with self.lock_for(p["handle"]):
                self._move_timezone(p["handle"], p["tz_revert_to"], now)
        for r in self.store.rules_to_resume(now):
            person = self.store.person(r["handle"])
            if not person:
                continue
            with self.lock_for(person["handle"]):
                status, nxt = self._next_for(RuleSpec.model_validate(r["spec"]), person, now, r)
                self.store.set_slot(r["id"], nxt, status)
                self.store.update_rule(r["id"], paused_until=None)

    def _move_timezone(self, handle, new_tz, now, revert_to=None, revert_at=None):
        """The person's zone changes. Each rule's next send keeps its date and clock time, read in the new zone (so a
        skipped or already-sent day stays skipped); only if that moment has passed is the next one worked out afresh.
        Rules pinned to a zone (when.tz) do not move."""
        person = self.store.person(handle)
        old_tz = ZoneInfo(person["timezone"])
        self.store.set_timezone(handle, new_tz, revert_to=revert_to, revert_at=revert_at)
        person = self.store.person(handle)
        for r in self.store.rules(handle, statuses=("active",)):
            if not r["next_run_at"]:
                continue
            spec = RuleSpec.model_validate(r["spec"])
            if spec.when.tz:
                continue
            kept = datetime.fromisoformat(r["next_run_at"]).astimezone(old_tz).replace(tzinfo=ZoneInfo(new_tz))
            if kept > now and spec.when.type != "random":
                self.store.set_slot(r["id"], now_iso(kept), "active")
                continue
            status, nxt = self._next_for(spec, person, now, r)
            self.store.set_slot(r["id"], nxt, status)

    # ---------- slots ----------
    def _next_for(self, spec, person, now, rule=None, after=None):
        """(status, next_run_at) for a rule: a saved on-request or new-items rule stays active with no time; a timed
        rule whose time has passed is done. `rule` gives the anchor (its creation) and the seed (its id)."""
        if spec.when.type in ("on_request", "new_items"):
            return "active", None
        anchor = datetime.fromisoformat(rule["created_at"]) if rule and rule.get("created_at") else now
        nxt = next_run(spec.when, person["timezone"], after or now, anchor=anchor, seed=rule["id"] if rule else None,
                       quiet=self.store.quiet(person["handle"]))
        return ("active", now_iso(nxt)) if nxt else ("done", None)

    def _upcoming(self, rule, person, now):
        """The next send that will really go out, after the skips the person asked for (None if there is none)."""
        if not rule.get("next_run_at") or rule["status"] != "active":
            return None
        spec = RuleSpec.model_validate(rule["spec"])
        tz = ZoneInfo(spec.when.tz or person["timezone"])
        t = datetime.fromisoformat(rule.get("slot_at") or rule["next_run_at"])
        count, dates = rule.get("skip_count") or 0, set(rule.get("skip_dates") or [])
        for _ in range(200):
            local = t.astimezone(tz)
            after = t
            if local.date().isoformat() in dates:   # every send on a skipped date: go on from the end of that day
                after = _at(local.date() + timedelta(days=1), "00:00", tz) - timedelta(seconds=1)
            elif count > 0:
                count -= 1
            else:
                return t
            _, nxt = self._next_for(spec, person, now, rule, after=after)
            if not nxt:
                return None
            t = datetime.fromisoformat(nxt)
        return None

    def _advance(self, rule, spec, tz, now, sending=False):
        person = self.store.person(rule["handle"]) or {"timezone": tz, "handle": rule["handle"]}
        status, nxt = self._next_for(spec, dict(person, timezone=tz), now, rule)
        if spec.when.max_sends:  # "stop after three times": counted in messages that went out
            marks = ",".join("?" * len(SENT_STATUSES))
            sent = self.store.one(f"SELECT COUNT(*) n FROM runs WHERE rule_id=? AND kind='scheduled' AND status IN "
                                  f"({marks})", (rule["id"], *SENT_STATUSES))["n"] + (1 if sending else 0)
            if sent >= spec.when.max_sends:
                status, nxt = "done", None
        self.store.set_slot(rule["id"], nxt, status)
        self.store.update_rule(rule["id"], last_run_at=now_iso(now))
        self.store.set_state(f"retry:{rule['id']}", 0)
        self.store.set_state(f"hold:{rule['id']}", None)

    def _hold(self, rule, release):
        self.store.set_state(f"hold:{rule['id']}", now_iso(release))
        self.store.update_rule(rule["id"], next_run_at=now_iso(release), status="active")

    def _skip_slot(self, rule, spec, tz, now, status, detail=None):
        self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status=status, error=detail,
                           at=now_iso(now))
        self._advance(rule, spec, tz, now)
        return 0

    @staticmethod
    def _moved(rule):
        """True when next_run_at was moved off the rule's slot by a retry or a hold. Anything that sets a new slot
        (a send, a skip, a change, a resume, a time zone move) sets both to the same time, so retry counts and holds
        left from an earlier slot never apply to a new one."""
        return bool(rule.get("slot_at")) and rule.get("next_run_at") != rule.get("slot_at")

    def _retry_or_skip(self, rule, now, slot=None, advanced=False, tries=None):
        """After an error: try this slot again in 15 minutes, up to 3 times; then move to the next scheduled time.
        `advanced` says the rule was already moved on to its next slot (a send that failed). `tries` is how many
        retries this slot has had (read before the rule moved on). A retry that lands in quiet hours is held to their
        end when it comes due."""
        if tries is None:
            tries = (self.store.get_state(f"retry:{rule['id']}", 0) or 0) if self._moved(rule) else 0
        n = tries
        if n < MAX_RETRIES:
            self.store.set_state(f"retry:{rule['id']}", n + 1)
            fields = {"next_run_at": now_iso(now + RETRY_AFTER), "status": "active"}
            if slot is not None:
                fields["slot_at"] = now_iso(slot)  # still the same slot: the lateness limit counts from it
            self.store.update_rule(rule["id"], **fields)
            return
        if advanced:
            self.store.set_state(f"retry:{rule['id']}", 0)
            return
        person = self.store.person(rule["handle"])
        spec = RuleSpec.model_validate(rule["spec"])
        self._advance(rule, spec, person["timezone"] if person else "UTC", now)

    # ---------- one due rule ----------
    def _tick_rule(self, rule, now, progress=None):
        person = self.store.person(rule["handle"])
        if not person:
            return 0
        with self.lock_for(person["handle"]):  # not while a message from this person is being handled
            rule = self.store.rule(rule["id"])  # it may have been paused, stopped or changed a moment ago
            if not rule or rule["status"] != "active" or not rule["next_run_at"] or rule["next_run_at"] > now_iso(now):
                return 0
            return self._tick_rule_locked(rule, person, now, {} if progress is None else progress)

    def _tick_rule_locked(self, rule, person, now, progress):
        spec = RuleSpec.model_validate(rule["spec"])
        tz = person["timezone"]
        slot = datetime.fromisoformat(rule.get("slot_at") or rule["next_run_at"])
        progress["slot"] = slot
        if person["paused"]:
            self._advance(rule, spec, tz, now)  # skip this slot rather than fire late after unpausing
            return 0
        quiet_streak = self._unanswered(person["handle"])
        if quiet_streak >= UNANSWERED_PAUSE:
            for r in self.store.rules(person["handle"]):
                if r["status"] == "active" and r["next_run_at"]:
                    self.store.update_rule(r["id"], status="paused")
                if r.get("paused_until"):  # "paused until Monday" must not restart while they are still silent
                    self.store.update_rule(r["id"], paused_until=None)
            self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status="paused_quiet",
                               at=now_iso(now))
            self.send(person["handle"], PAUSED_QUIET)
            return 0
        moved = self._moved(rule)   # a retry or a held send of this slot (never one left from an earlier slot)
        retries = (self.store.get_state(f"retry:{rule['id']}", 0) or 0) if moved else 0
        hold = self.store.get_state(f"hold:{rule['id']}") if moved else None
        late_from = max(slot, datetime.fromisoformat(hold)) if hold else slot
        if now - late_from > MISSED_AFTER:  # e.g. the bot was off on Friday evening: Friday's pick is not sent on Monday
            return self._skip_slot(rule, spec, tz, now, "missed")
        again = bool(retries or hold)   # this slot already passed the checks below once: a retry or a held send
        if not again:
            why = self.store.consume_skip(rule["id"], slot.astimezone(ZoneInfo(spec.when.tz or tz)).date().isoformat())
            if why:  # "skip the next two", "not on the 26th"
                return self._skip_slot(rule, spec, tz, now, "skipped", why)
        snooze = person.get("snooze_until")
        if snooze and now < datetime.fromisoformat(snooze):  # "I'm away until the 20th"; asking still works
            return self._skip_slot(rule, spec, tz, now, "snoozed")
        quiet = self.store.quiet(person["handle"])
        if in_quiet_hours(now, tz, quiet) and not (spec.when.named_time and not again):
            # A clock time the person named is kept even in quiet hours. Random, window and every_hours moments, retries
            # and held sends are not: they wait for the end of quiet hours, unless the next regular send comes first.
            release = end_of_quiet(now, tz, quiet)
            regular = next_run(spec.when, tz, slot, anchor=datetime.fromisoformat(rule["created_at"]), seed=rule["id"],
                               quiet=quiet)
            if spec.when.type != "once" and regular and regular <= release:
                return self._skip_slot(rule, spec, tz, now, "quiet_hours")
            self._hold(rule, release)
            return 0
        local = now.astimezone(ZoneInfo(tz))
        midnight = _at(local.date(), "00:00", ZoneInfo(tz))
        if self.store.scheduled_today(person["handle"], midnight) >= config.MAX_SCHEDULED_PER_DAY:
            # A one-time send the person asked for is held to the next morning (lateness counts from then, so it is
            # never turned into a silent 'missed'). A repeating rule's slot is skipped and recorded: its next slot comes
            # anyway, and sending it tomorrow would only push tomorrow over the limit too.
            if spec.when.type == "once":
                tomorrow = _at(local.date() + timedelta(days=1), "00:00", ZoneInfo(tz))
                self._hold(rule, end_of_quiet(tomorrow, tz, quiet))
                return 0
            return self._skip_slot(rule, spec, tz, now, "daily_limit")
        if self._over_cap(person):  # this slot is skipped and recorded; it is not held to fire late
            return self._skip_slot(rule, spec, tz, now, "over_cap")
        h = person["handle"]
        before = (self.store.last_answer(h), self.store.get_state(f"lines:{h}"), self.store.get_state(f"linekinds:{h}"))
        msg, run_id, n = self.run(person, spec, "scheduled", rule_id=rule["id"])
        progress["run_id"] = run_id
        if self._run_failed(run_id):
            self._retry_or_skip(rule, now, slot, tries=retries)  # nothing is sent: an error text would be unprompted
            return 0
        # Recorded before the send: the rule moves to its next slot and the run is marked 'sending'. A crash from here
        # on can lose this one message but can never send the slot twice.
        self._advance(rule, spec, tz, now, sending=True)
        progress["advanced"] = True
        self.store.x("UPDATE runs SET status='sending' WHERE id=?", (run_id,))
        if spec.when.repeating and self.store.rule(rule["id"])["status"] == "done":
            msg += "\n" + LAST_SEND   # max_sends reached, or until has passed
        elif quiet_streak >= UNANSWERED_CHECK and spec.when.repeating:
            msg += "\n" + STILL_USEFUL
        try:
            self.send(person["handle"], msg, run_id)
        except SendUncertain:  # it may have gone out: keep the deliveries, do not retry
            self.store.x("UPDATE runs SET status='unknown', error='SendUncertain' WHERE id=?", (run_id,))
            return 0
        except Exception as e:  # noqa: BLE001 - a clear failure: nothing went out
            self.store.x("DELETE FROM deliveries WHERE run_id=?", (run_id,))
            self.store.x("UPDATE runs SET status='send_failed', error=? WHERE id=?", (type(e).__name__, run_id))
            last, lines, kinds = before  # what they never received is not their "last answer": 👎 must not land on it
            if last:
                self.store.set_last_answer(h, last["run_id"], last["rule_id"], last["items"], last["goal"])
            else:
                self.store.x("DELETE FROM last_answer WHERE handle=?", (h,))
            self.store.set_state(f"lines:{h}", lines or {})
            self.store.set_state(f"linekinds:{h}", kinds or {})
            self._retry_or_skip(rule, now, slot, advanced=True, tries=retries)  # _advance reset the stored count
            return 0
        self.store.x("UPDATE runs SET status=? WHERE id=?", ("sent" if n else "none_sent", run_id))
        return 1

    def _unanswered(self, handle):
        """Timed sends that went out since the person last wrote or reacted."""
        since = self.store.get_state(f"last_in:{handle}") or ""
        return self.store.one("SELECT COUNT(*) n FROM runs WHERE handle=? AND kind IN ('scheduled','todo') AND status IN "
                              "('sent','none_sent','unknown') AND at>?", (handle, since))["n"]

    def _run_failed(self, run_id):
        return self.store.one("SELECT status FROM runs WHERE id=?", (run_id,))["status"] == "error"

    def recover(self):
        """At start: a run left as 'sending' by a crash may or may not have gone out. It is never sent again."""
        self.store.x("UPDATE runs SET status='unknown', error='stopped while sending' WHERE status='sending'")
