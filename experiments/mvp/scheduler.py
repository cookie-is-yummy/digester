"""PROTOTYPE ONLY - the scheduler: tick, the guards before a timed send, retries and recovery (BRIEF-10 section 5).

Mixed into core.Bot.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .channels.base import SendUncertain
from .schedule import end_of_quiet, in_quiet_hours, next_run, rule_time_in_quiet
from .schema import RuleSpec
from .store import now_iso
from .texts import LAST_SEND, PAUSED_QUIET, STILL_USEFUL

UNANSWERED_CHECK = 3   # after this many timed sends in a row with no word from the person, the next one asks
UNANSWERED_PAUSE = 5   # after this many, their timed sends are paused (message services flag unanswered streams)
MISSED_AFTER = timedelta(hours=2)   # a timed send this late is skipped, not sent (the bot was off, or kept failing)
RETRY_AFTER = timedelta(minutes=15)
MAX_RETRIES = 3


class SchedulerMixin:
    def tick(self):
        now = self.clock()
        sent = 0
        for rule in self.store.due_rules(now):
            try:
                sent += self._tick_rule(rule, now)
            except Exception as e:  # noqa: BLE001 - one rule never blocks the others
                self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status="error",
                                   error=type(e).__name__, at=now_iso(now))
                self._retry_or_skip(rule, now)
        return sent

    def _advance(self, rule, spec, tz, now, sending=False):
        status, nxt = self._state_for(spec, tz, now, datetime.fromisoformat(rule["created_at"]))
        if spec.when.max_sends:  # "stop after three times": counted in messages that went out
            sent = self.store.one("SELECT COUNT(*) n FROM runs WHERE rule_id=? AND kind='scheduled' AND status IN "
                                  "('sent','none_sent','unknown')", (rule["id"],))["n"] + (1 if sending else 0)
            if sent >= spec.when.max_sends:
                status, nxt = "done", None
        self.store.set_slot(rule["id"], nxt, status)
        self.store.update_rule(rule["id"], last_run_at=now_iso(now))
        self.store.set_state(f"retry:{rule['id']}", 0)

    def _state_for(self, spec, tz, now, anchor):
        """(status, next_run_at) for a rule: a saved on-request rule stays active with no time; a timed rule whose
        time has passed is done."""
        if spec.when.type == "on_request":
            return "active", None
        nxt = next_run(spec.when, tz, now, anchor=anchor)
        return ("active", now_iso(nxt)) if nxt else ("done", None)

    def _retry_or_skip(self, rule, now, slot=None, advanced=False):
        """After an error: try this slot again in 15 minutes, up to 3 times; then move to the next scheduled time.
        `advanced` says the rule was already moved on to its next slot (a send that failed)."""
        n = self.store.get_state(f"retry:{rule['id']}", 0) or 0
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

    def _tick_rule(self, rule, now):
        person = self.store.person(rule["handle"])
        if not person:
            return 0
        with self.lock_for(person["handle"]):  # not while a message from this person is being handled
            rule = self.store.rule(rule["id"])  # it may have been paused, stopped or changed a moment ago
            if not rule or rule["status"] != "active" or not rule["next_run_at"] or rule["next_run_at"] > now_iso(now):
                return 0
            return self._tick_rule_locked(rule, person, now)

    def _tick_rule_locked(self, rule, person, now):
        spec = RuleSpec.model_validate(rule["spec"])
        tz = person["timezone"]
        slot = datetime.fromisoformat(rule.get("slot_at") or rule["next_run_at"])
        if person["paused"]:
            self._advance(rule, spec, tz, now)  # skip this slot rather than fire late after unpausing
            return 0
        quiet_streak = self._unanswered(person["handle"])
        if quiet_streak >= UNANSWERED_PAUSE:
            for r in self.store.rules(person["handle"], statuses=("active",)):
                if r["next_run_at"]:
                    self.store.update_rule(r["id"], status="paused")
            self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status="paused_quiet",
                               at=now_iso(now))
            self.send(person["handle"], PAUSED_QUIET)
            return 0
        if now - slot > MISSED_AFTER:  # e.g. the bot was off on Friday evening: Friday's pick is not sent on Monday
            self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status="missed",
                               at=now_iso(now))
            self._advance(rule, spec, tz, now)
            return 0
        if in_quiet_hours(now, tz) and not rule_time_in_quiet(spec.when):
            self.store.update_rule(rule["id"], next_run_at=now_iso(end_of_quiet(now, tz)))
            return 0
        local_midnight = now.astimezone(ZoneInfo(tz)).replace(hour=0, minute=0, second=0, microsecond=0)
        if self.store.scheduled_today(person["handle"], local_midnight) >= config.MAX_SCHEDULED_PER_DAY:
            self.store.update_rule(rule["id"], next_run_at=now_iso(local_midnight + timedelta(days=1, hours=config.QUIET_END)))
            return 0
        if self._over_cap(person):  # this slot is skipped and recorded; it is not held to fire late
            self.store.add_run(handle=rule["handle"], rule_id=rule["id"], kind="scheduled", status="over_cap",
                               at=now_iso(now))
            self._advance(rule, spec, tz, now)
            return 0
        h = person["handle"]
        before = (self.store.last_answer(h), self.store.get_state(f"lines:{h}"))
        msg, run_id, n = self.run(person, spec, "scheduled", rule_id=rule["id"])
        if self._run_failed(run_id):
            self._retry_or_skip(rule, now, slot)  # nothing is sent: an error text would be unprompted and useless
            return 0
        # Recorded before the send: the rule moves to its next slot and the run is marked 'sending'. A crash from here
        # on can lose this one message but can never send the slot twice.
        self._advance(rule, spec, tz, now, sending=True)
        if spec.when.max_sends and self.store.rule(rule["id"])["status"] == "done":
            msg += "\n" + LAST_SEND
        elif quiet_streak >= UNANSWERED_CHECK and spec.when.type == "schedule":
            msg += "\n" + STILL_USEFUL
        self.store.x("UPDATE runs SET status='sending' WHERE id=?", (run_id,))
        try:
            self.send(person["handle"], msg, run_id)
        except SendUncertain:  # it may have gone out: keep the deliveries, do not retry
            self.store.x("UPDATE runs SET status='unknown', error='SendUncertain' WHERE id=?", (run_id,))
            return 0
        except Exception as e:  # noqa: BLE001 - a clear failure: nothing went out
            self.store.x("DELETE FROM deliveries WHERE run_id=?", (run_id,))
            self.store.x("UPDATE runs SET status='send_failed', error=? WHERE id=?", (type(e).__name__, run_id))
            last, lines = before  # what they never received is not their "last answer": 👎 must not land on it
            if last:
                self.store.set_last_answer(h, last["run_id"], last["rule_id"], last["items"], last["goal"])
            else:
                self.store.x("DELETE FROM last_answer WHERE handle=?", (h,))
            self.store.set_state(f"lines:{h}", lines or {})
            self._retry_or_skip(rule, now, slot, advanced=True)
            return 0
        self.store.x("UPDATE runs SET status=? WHERE id=?", ("sent" if n else "none_sent", run_id))
        return 1

    def _unanswered(self, handle):
        """Timed sends that went out since the person last wrote or reacted."""
        since = self.store.get_state(f"last_in:{handle}") or ""
        return self.store.one("SELECT COUNT(*) n FROM runs WHERE handle=? AND kind='scheduled' AND status IN "
                              "('sent','none_sent','unknown') AND at>?", (handle, since))["n"]

    def _run_failed(self, run_id):
        return self.store.one("SELECT status FROM runs WHERE id=?", (run_id,))["status"] == "error"

    def recover(self):
        """At start: a run left as 'sending' by a crash may or may not have gone out. It is never sent again."""
        self.store.x("UPDATE runs SET status='unknown', error='stopped while sending' WHERE status='sending'")
