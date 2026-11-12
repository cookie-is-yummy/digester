"""PROTOTYPE ONLY - the bot: message handler, executor and scheduler (docs/06 'Executor', BRIEF-10 sections 4 and 5).

Only this module sends (AGENTS.md rule 5): retrieve and compose read; the interpreter fills forms (rule 6).
"""
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, llm
from .compose import compose
from .interpret import interpret
from .libview import LibraryView
from .render import none_message, picks_message
from .retrieve import candidates
from .schedule import describe, end_of_quiet, in_quiet_hours, next_run, rule_time_in_quiet, say_time
from .schema import RuleSpec
from .channels.base import SendUncertain
from .store import Store, now_iso

CONSENT_VERSION = "mvp-consent-v1"
YES = re.compile(r"^\s*(yes|y|yep|yeah|yup|sure|ok|okay|go|start|do it|sounds good|👍)[\s.!]*$", re.I)
NO = re.compile(r"^\s*(no|n|nope|nah|cancel|don'?t)[\s.!]*$", re.I)
AGREE = re.compile(r"^\s*(i agree|agree|agreed|i'm in|im in|yes)\b", re.I)
NEGATION = re.compile(r"\b(not|don'?t|do not|no|disagree|never)\b", re.I)
QUICK_FEEDBACK = re.compile(r"^\s*(👍|👎)\s*(\d)?\s*$")
# How a reaction reaches a phone that shows it as text (SMS, or a reaction the channel passes on as text).
REACTION_TEXT = re.compile(r"^\s*(Liked|Loved|Laughed at|Emphasized|Disliked|Reacted (👍|👎|❤️)( to)?)\s+[“\"]", re.I)
MAX_MESSAGES_PER_MINUTE = 15  # per person; more than this is a loop or a script, and is ignored
MAX_MESSAGES_PER_HOUR = 90
PENDING_TTL = {"confirm_rule": timedelta(hours=24), "confirm_delete": timedelta(minutes=30)}
# what a message must be for an open preview to be dropped; small talk, questions about the last answer, feedback and
# rule management leave it open, so a later "yes" still starts the rule
ENDS_PENDING = ("ask", "change_rule", "delete_data", "decline", "stop")
MISSED_AFTER = timedelta(hours=2)   # a timed send this late is skipped, not sent (the bot was off, or kept failing)
RETRY_AFTER = timedelta(minutes=15)
MAX_RETRIES = 3

HELP = ("I find things in what you've saved and watched on Instagram and YouTube. Ask whenever you want something, "
        "or tell me when to send it.\n"
        "Now: \"what can I make with chicken and rice?\"\n"
        "Later: \"tonight at 9 send me something to wind down with\" or \"in two hours…\"\n"
        "Repeating: \"a pasta recipe every Friday at 7pm\"\n"
        "Manage: \"my rules\", \"run 1\", \"skip 1\", \"pause 1\", \"stop 1\". Reply 👍 or 👎, or \"👎 2\" for one pick. "
        "\"delete my data\" removes everything I hold about you.")
CONSENT = ("Hi! I'm a prototype that finds things in your own saved and watched posts and sends them when you ask. "
           "Your library stays on the founders' Mac. Your messages to me are stored so I work, and the founders look at "
           "them only to fix problems. Your requests and the text of posts I consider go to OpenAI to understand them "
           "(not used for training). You can say "
           "\"delete my data\" at any time. Reply \"I agree\" to start, and confirm you're 18 or over.")
SCHEDULED_FOOTER = "Reply 👎 if that's not for you, or \"pause\" to pause."
UNKNOWN = "Hi! I'm a private test bot, and you're not set up with me yet."
NOTHING_PENDING = "I don't have anything waiting for a yes. Tell me what you'd like and I'll set it up."
LOADING = "One moment, I'm opening your library…"


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
LIMIT = "I've reached today's limit for you. I'll be able to search again tomorrow."


class Bot:
    def __init__(self, channel, store=None, pool=None, clock=None):
        self.channel = channel
        self.store = store or Store(config.DB)
        if pool is None:
            from .engines import EnginePool
            pool = EnginePool()
        self.pool = pool
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.views = {}
        self._views_lock = threading.Lock()
        self._locks = {}      # handle -> lock: one person's messages and timed sends never run at the same time
        self._tl = threading.local()   # what happened to the message this thread is handling (for the journal)
        self._arrivals = {}   # handle -> real times of recent messages
        self.max_per_minute = MAX_MESSAGES_PER_MINUTE   # None switches the flood guard off (batch test runs)

    # ---------- people ----------
    def load_people(self, path=None):
        path = self.people_path = path or getattr(self, "people_path", None) or config.PEOPLE
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8") as f:
            people = json.load(f)
        deleted = set()
        gone = os.path.join(config.HOME, "deletions.jsonl")
        if os.path.exists(gone):  # a person who asked for deletion is not added back from people.json
            with open(gone, encoding="utf-8") as f:
                deleted = {json.loads(line)["handle"] for line in f if line.strip()}
        n = 0
        for i, (handle, p) in enumerate(people.items(), 1):
            handle = norm_handle(handle)
            if handle in deleted:
                print(f"people.json, person {i}: skipped, they asked for their data to be deleted", file=sys.stderr)
                continue
            n += 1
            lib = p["library"]
            if not os.path.isabs(lib):  # "data/all" means the repo's data folder, wherever the bot is started from
                lib = next((os.path.join(b, lib) for b in (config.REPO, os.getcwd(), os.path.dirname(os.path.abspath(path)))
                            if os.path.isdir(os.path.join(b, lib))), lib)
            lib = os.path.abspath(lib)
            if not os.path.isfile(os.path.join(lib, "corpus", "items.jsonl")):
                raise SystemExit(f"people.json, person {i}: there is no library at {lib}")
            try:
                ZoneInfo(p.get("timezone", "America/New_York"))
            except Exception:  # noqa: BLE001
                raise SystemExit(f"people.json, person {i}: unknown timezone {p.get('timezone')!r}") from None
            self.store.upsert_person(handle, p.get("name"), lib, p.get("timezone", "America/New_York"))
        return n

    def view(self, library):
        with self._views_lock:
            if library not in self.views:
                self.views[library] = LibraryView(library)
            return self.views[library]

    def lock_for(self, handle):
        with self._views_lock:
            return self._locks.setdefault(handle, threading.RLock())

    def note(self, **kw):
        """Facts about the message being handled (intent, run, reply), for the inbound journal. No text."""
        trace = getattr(self._tl, "trace", None)
        if trace is not None:
            trace.update(kw)

    def send(self, handle, text, run_id=None):
        ref = self.channel.send(handle, text)
        self.store.record_sent(ref, handle, run_id)
        self.note(reply_ref=ref)
        return ref

    # ---------- caps ----------
    def _over_cap(self, person):
        libs = [p["library"] for p in self.store.q("SELECT library FROM people")]
        if llm.spent_total(libs) >= config.TOTAL_CAP_USD:
            return "total"
        if llm.spent_today(person["handle"], person["library"]) >= config.DAILY_CAP_USD:
            return "daily"
        return None

    def _limit_notice(self, person):
        """The limit message, at most once a day per person; otherwise silence (no paid calls either way)."""
        day = self.clock().astimezone(ZoneInfo(person["timezone"])).date().isoformat()
        key = f"cap_notice:{person['handle']}"
        if self.store.get_state(key) == day:
            return None
        self.store.set_state(key, day)
        return self.send(person["handle"], LIMIT)

    # ---------- the executor ----------
    def run(self, person, spec: RuleSpec, kind, rule_id=None, request_text=None, cands_override=None, known_lines=None):
        """kind: preview | scheduled | manual | ask | follow_up. Returns (message, run_id, n_picks). 'manual' is a
        rule run because the person asked for it now. Deliveries are written here; a caller whose send fails removes
        them (unsend)."""
        t0 = time.time()
        cost = 0.0
        status, err, result, cands, view = "ok", None, None, [], None
        disliked = self.store.disliked(person["handle"])
        try:
            view = self.view(person["library"])
            ready = getattr(self.pool, "is_ready", None)
            if cands_override is None and kind != "scheduled" and ready and not ready(person["library"]):
                self.send(person["handle"], LOADING)  # the first search after a start can take a minute
            if cands_override is not None:
                cands = [c for c in cands_override if c.id not in disliked]  # rule 9 holds for follow-ups too
            else:
                exclude = self.store.delivered(rule_id) if (rule_id and spec.content.exclude_sent) else set()
                weights = self._feedback_weights(rule_id, view)
                cands, meta = candidates(self.pool, view, spec, exclude=exclude, disliked=disliked,
                                         creator_weights=weights, now=self.clock())
                cost += meta.get("cost_usd", 0.0)
            result, c = compose(cands, spec, person["handle"], request_text=request_text,
                                feedback_note=self._feedback_note(rule_id, view), known_lines=known_lines)
            cost += c
        except Exception as e:  # noqa: BLE001 - one failed run never stops the bot
            status, err = "error", type(e).__name__ + (": " + str(e)[:120] if isinstance(e, RuntimeError) else "")
        picks = (result or {}).get("picks") or []
        run_id = self.store.add_run(handle=person["handle"], rule_id=rule_id, kind=kind, at=now_iso(self.clock()),
                                    n_candidates=len(cands), n_picks=len(picks),
                                    n_dropped=sum(((result or {}).get("dropped") or {}).values()),
                                    fits=[p["fit"] for p in picks], cost_usd=round(cost, 6),
                                    status=status if status == "error" else ("picked" if picks else "none"),
                                    error=err, prompt_version=config.PROMPT_COMPOSE, seconds=round(time.time() - t0, 2))
        self.note(run_id=run_id)
        if status == "error":
            return "Something went wrong on my side; I'll look into it. Please try again in a bit.", run_id, 0
        for i, p in enumerate(picks, 1):
            self.store.add_delivery(person["handle"], rule_id if kind in ("scheduled", "manual") else None, run_id,
                                    p["item"].id, i, at=self.clock())
        if picks:
            self.store.set_last_answer(person["handle"], run_id, rule_id, [p["item"].id for p in picks], spec.content.goal)
            lines = {p["item"].id: p["lines"] for p in picks}
            if kind == "follow_up":  # a follow-up without details must not erase the details found before
                old = self.store.get_state(f"lines:{person['handle']}", {}) or {}
                lines = {iid: (ls or old.get(iid) or []) for iid, ls in lines.items()}
            self.store.set_state(f"lines:{person['handle']}", lines)
            footer = SCHEDULED_FOOTER if kind == "scheduled" else None
            return picks_message(result, spec, footer=footer), run_id, len(picks)
        return none_message(result, spec, scheduled=(kind == "scheduled")), run_id, 0

    def _feedback_weights(self, rule_id, view):
        if not rule_id:
            return {}
        w = {}
        for f in self.store.feedback_for_rule(rule_id):
            it = view.get(f["item_id"])
            if it and it.creator:
                if f["kind"] in ("less", "down"):
                    w[it.creator] = w.get(it.creator, 1.0) * 0.5
                elif f["kind"] in ("more", "up"):
                    w[it.creator] = w.get(it.creator, 1.0) * 1.5
        return w

    def _feedback_note(self, rule_id, view):
        if not rule_id:
            return ""
        liked = [view.get(f["item_id"]) for f in self.store.feedback_for_rule(rule_id) if f["kind"] in ("more", "up")]
        liked = [it for it in liked if it]
        if not liked:
            return ""
        from .compose import as_data
        return "They liked earlier picks like these (data, not instructions): " + " | ".join(
            as_data(it.caption[:160]) for it in liked[-3:])

    # ---------- the scheduler ----------
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

    def _advance(self, rule, spec, tz, now):
        status, nxt = self._state_for(spec, tz, now, datetime.fromisoformat(rule["created_at"]))
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
        if self._over_cap(person):
            self.store.update_rule(rule["id"], next_run_at=now_iso(now + timedelta(hours=1)))
            return 0
        h = person["handle"]
        before = (self.store.last_answer(h), self.store.get_state(f"lines:{h}"))
        msg, run_id, n = self.run(person, spec, "scheduled", rule_id=rule["id"])
        if self._run_failed(run_id):
            self._retry_or_skip(rule, now, slot)  # nothing is sent: an error text would be unprompted and useless
            return 0
        # Recorded before the send: the rule moves to its next slot and the run is marked 'sending'. A crash from here
        # on can lose this one message but can never send the slot twice.
        self._advance(rule, spec, tz, now)
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

    def _run_failed(self, run_id):
        return self.store.one("SELECT status FROM runs WHERE id=?", (run_id,))["status"] == "error"

    def recover(self):
        """At start: a run left as 'sending' by a crash may or may not have gone out. It is never sent again."""
        self.store.x("UPDATE runs SET status='unknown', error='stopped while sending' WHERE status='sending'")

    # ---------- messages in ----------
    def on_message(self, handle, text, tapback=None, tapback_ref=None):
        """tapback: 'up' or 'down' on an earlier bot message identified by tapback_ref."""
        handle = norm_handle(handle)
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
        text = (text or "").strip()
        if not person["consent_version"]:
            self.note(intent="consent")
            if text and AGREE.match(text) and not NEGATION.search(text):
                self.store.set_consent(handle, CONSENT_VERSION)
                return self.send(handle, "Thanks! " + HELP)
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
                return self.send(handle, "OK, nothing is deleted.")
            pending = None
        elif pending and YES.match(text):
            return self._confirm(person, pending)
        elif pending and NO.match(text):
            self.store.clear_pending(handle)
            return self.send(handle, "OK, I won't start it. Tell me what you'd like instead.")
        if self._over_cap(person):
            return self._limit_notice(person)  # before any paid call
        rules = self.store.rules(handle)
        last = self.store.last_answer(handle)
        try:
            it, _ = interpret(text, person, rules, pending, last, now)
        except Exception as e:  # noqa: BLE001
            self.store.add_run(handle=handle, kind="interpret", status="error", error=type(e).__name__)
            return self.send(handle, "Something went wrong on my side. Please try again in a bit.")
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
            return self.send(h, "OK, I won't do that.")
        if it.intent == "new_rule":
            if it.spec.when.type in ("once", "on_request"):
                # one send at a stated time, or a saved request: nothing recurring starts, so no preview is needed;
                # the reply states exactly what will happen and how to cancel it
                return self._activate(person, text, it.spec)
            if pending and it.edits_pending and re.match(r"^\s*(yes|yep|yeah|ok|okay|sure)\b", text, re.I):
                same = it.spec.content.model_dump() == pending["payload"]["spec"]["content"]
                return self._activate(person, pending["payload"]["text"] + " / " + text, it.spec, edited=True,
                                      preview_run=pending["payload"].get("run_id") if same else None)
            if pending and it.edits_pending:  # keep the whole request, not only the edit
                text = pending["payload"]["text"] + " / " + text
            msg, run_id, n = self.run(person, it.spec, "preview", request_text=text)
            if self._run_failed(run_id):  # no preview, so nothing to say yes to
                self.store.clear_pending(h)
                return self.send(h, msg, run_id)
            self.store.set_pending(h, "confirm_rule", {"text": text, "spec": it.spec.model_dump(), "run_id": run_id},
                                   at=self.clock())
            when = describe(it.spec.when)
            c = it.spec.content
            what = f"{c.count} {'pick' if c.count == 1 else 'picks'} for \"{c.goal}\""
            tail = (f"\n\n{when[0].upper() + when[1:]} I'll send {what} that I haven't sent you before. "
                    "Reply YES to start, or tell me what to change.")
            head = "Here's what that would look like now:\n\n" if n else ""
            return self.send(h, head + msg + tail, run_id)
        if it.intent == "ask":
            msg, run_id, _ = self.run(person, it.spec, "ask", request_text=text)
            return self.send(h, msg, run_id)
        if it.intent == "follow_up":
            if not last:
                return self.send(h, "I haven't sent you anything to follow up on yet. What are you looking for?")
            view = self.view(person["library"])
            cands = [c for c in (view.get(i) for i in last["items"]) if c]
            spec = self._spec_for_followup(last, it.question)
            known = self.store.get_state(f"lines:{h}", {}) or {}
            msg, run_id, _ = self.run(person, spec, "follow_up", request_text=it.question, cands_override=cands,
                                      known_lines=known)
            return self.send(h, msg, run_id)
        if it.intent == "feedback":
            return self._feedback(person, it.feedback, it.pick_number)
        if it.intent == "list_rules":
            return self.send(h, self._rules_text(person, rules))
        if it.intent in ("pause", "resume", "stop"):
            return self._manage(person, rules, it.intent, it.rule_number, it.all_rules)
        if it.intent == "change_rule":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, "Which rule? Reply \"my rules\" to see their numbers.")
            status, nxt = self._state_for(it.spec, person["timezone"], now, datetime.fromisoformat(r["created_at"]))
            if status == "done":  # a one-off time that has passed would end the rule without saying so
                return self.send(h, "That time has already passed, so I left the rule as it was. When should I send it?")
            self.store.update_rule(r["id"], spec=it.spec.model_dump(), text=text)
            self.store.set_slot(r["id"], nxt, status if r["status"] == "active" else r["status"])
            return self.send(h, f"Changed: {describe(it.spec.when)}, {it.spec.content.goal}.")
        if it.intent == "run_rule":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, "Which rule? Reply \"my rules\" to see their numbers." if rules else
                                 "You have no rules yet. Just ask me for what you want.")
            msg, run_id, _ = self.run(person, RuleSpec.model_validate(r["spec"]), "manual", rule_id=r["id"],
                                      request_text=text)
            return self.send(h, msg, run_id)
        if it.intent == "skip":
            r = self._pick_rule(rules, it.rule_number)
            if not r:
                return self.send(h, "Which rule? Reply \"my rules\" to see their numbers." if rules else "You have no rules yet.")
            if r["status"] != "active" or not r["next_run_at"]:
                return self.send(h, "That one has no send coming up.")
            spec = RuleSpec.model_validate(r["spec"])
            nxt = next_run(spec.when, person["timezone"], datetime.fromisoformat(r["next_run_at"]),
                           anchor=datetime.fromisoformat(r["created_at"]))
            self.store.set_slot(r["id"], now_iso(nxt) if nxt else None, "active" if nxt else "done")
            return self.send(h, f"Skipped. Next one {say_time(nxt, now, person['timezone'])}." if nxt else
                             "Skipped. That was its only send, so the rule is finished.")
        if it.intent == "set_timezone":
            old_tz, new_tz = ZoneInfo(person["timezone"]), ZoneInfo(it.timezone)
            self.store.set_timezone(h, it.timezone)
            for r in self.store.rules(h, statuses=("active",)):
                if not r["next_run_at"]:
                    continue
                # the next send keeps its date and clock time, read in the new zone (so a skipped or already-sent
                # day stays skipped); only if that moment has passed is the next one worked out afresh
                kept = datetime.fromisoformat(r["next_run_at"]).astimezone(old_tz).replace(tzinfo=new_tz)
                if kept > now:
                    self.store.set_slot(r["id"], now_iso(kept), "active")
                    continue
                status, nxt = self._state_for(RuleSpec.model_validate(r["spec"]), it.timezone, now,
                                              datetime.fromisoformat(r["created_at"]))
                self.store.set_slot(r["id"], nxt, status)
            local = now.astimezone(ZoneInfo(it.timezone)).strftime("%-I:%M%p").lower()
            return self.send(h, f"OK, I'll use {it.timezone.split('/')[-1].replace('_', ' ')} time from now on "
                                f"(it's {local} there). Your send times keep their clock time.")
        if it.intent == "delete_data":
            self.store.set_pending(h, "confirm_delete", {}, at=self.clock())
            return self.send(h, "This deletes your library, rules and history with me. Reply YES to delete everything.")
        return self.send(h, HELP)

    def _spec_for_followup(self, last, question):
        prev = None
        if last.get("rule_id"):
            r = self.store.rule(last["rule_id"])
            prev = RuleSpec.model_validate(r["spec"]) if r else None
        extract = prev.content.extract if prev else ("ingredients" if re.search(r"ingredient|recipe|make|cook", question, re.I) else "none")
        return RuleSpec.model_validate({"when": {"type": "now"}, "content": {
            "goal": question[:200], "searches": [question[:120]], "count": min(3, len(last["items"])) or 1,
            "extract": extract, "exclude_sent": False}})

    def _confirm(self, person, pending):
        h = person["handle"]
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
            return self.channel.send(h, "Done: your rules and history are deleted. A founder will remove your library "
                                        "and our message thread within 24 hours and confirm here.")
        return None

    def _activate(self, person, text, spec, edited=False, preview_run=None):
        h = person["handle"]
        self.store.clear_pending(h)
        now = self.clock()
        tz = person["timezone"]
        c = spec.content
        avoid = f", nothing with {', '.join(c.avoid)}" if c.avoid else ""
        what = f"{c.count} {'pick' if c.count == 1 else 'picks'} for \"{c.goal}\"{avoid}"
        if spec.when.type == "on_request":
            self.store.add_rule(h, text, spec.model_dump(), "active", None, created_at=now_iso(now))
            n = len(self.store.rules(h))
            return self.send(h, f"Saved as rule {n}: {what}. Ask for it, or text \"run {n}\", whenever you want it. "
                                "I won't repeat picks.")
        nxt = next_run(spec.when, tz, now, anchor=now)
        if nxt is None:
            return self.send(h, "That time has already passed. When should I send it?")
        rule_id = self.store.add_rule(h, text, spec.model_dump(), "active", now_iso(nxt), created_at=now_iso(now))
        if preview_run:  # the preview's picks count as sent by this rule, so its first send is something new
            self.store.x("UPDATE deliveries SET rule_id=? WHERE run_id=? AND handle=?", (rule_id, preview_run, h))
            # 👍, 👎 and "more like 2" given on the preview belong to the rule it became
            self.store.x("UPDATE feedback SET rule_id=? WHERE handle=? AND rule_id IS NULL AND item_id IN "
                         "(SELECT item_id FROM deliveries WHERE run_id=?)", (rule_id, h, preview_run))
        n = len(self.store.rules(h))
        first = say_time(nxt, now, tz)
        if spec.when.type == "once":
            return self.send(h, f"OK. {first[0].upper() + first[1:]} I'll send {what}. Reply \"stop {n}\" to cancel.")
        lead = "Got it" + (" with your change" if edited else "")
        return self.send(h, f"{lead}: {describe(spec.when)}, {c.goal}{avoid}. First one {first}. "
                            "Reply \"my rules\" any time to see or change it.")

    def _feedback(self, person, kind, pick_number):
        h = person["handle"]
        last = self.store.last_answer(h)
        if not last:
            return self.send(h, "Thanks! Nothing to attach that to yet.")
        items = last["items"]
        if pick_number and not 1 <= pick_number <= len(items):
            return self.send(h, f"My last message had {len(items)} {'pick' if len(items) == 1 else 'picks'}. Which one?")
        chosen = [items[pick_number - 1]] if pick_number else items
        for iid in chosen:
            self.store.add_feedback(h, iid, last.get("rule_id"), kind)
        replies = {"up": "Noted 👍", "down": "Noted. I won't send that again.", "more": "Noted: more like that.",
                   "less": "Noted: less like that."}
        return self.send(h, replies.get(kind, "Noted."))

    def _pick_rule(self, rules, number):
        if number is not None:
            return rules[number - 1] if 1 <= number <= len(rules) else None
        return rules[0] if len(rules) == 1 else None

    def _rules_text(self, person, rules):
        if not rules:
            return ("You have no rules yet. Ask me anything now, or tell me when to send something: "
                    "\"tonight at 9…\", \"every Friday at 7pm…\".")
        lines = ["Your rules:"]
        now = self.clock()
        for i, r in enumerate(rules, 1):
            spec = RuleSpec.model_validate(r["spec"])
            state = " (paused)" if r["status"] == "paused" else ""
            nxt = ""
            if r["status"] == "active" and r["next_run_at"] and spec.when.type == "schedule":
                nxt = f" (next: {say_time(datetime.fromisoformat(r['next_run_at']), now, person['timezone'])})"
            lines.append(f"{i}. {spec.content.goal}: {describe(spec.when)}{state}{nxt}")
        lines.append("Reply \"run 1\" to get one now, or \"skip 1\", \"pause 1\", \"stop 1\", \"change 1 to …\".")
        return "\n".join(lines)

    def _manage(self, person, rules, action, number, all_rules):
        h = person["handle"]
        one = self._pick_rule(rules, number)
        targets = rules if all_rules else ([one] if one else [])
        if not targets:
            return self.send(h, "Which rule? Reply \"my rules\" to see their numbers." if rules else "You have no rules yet.")
        now = self.clock()
        for r in targets:
            if action == "pause":
                self.store.update_rule(r["id"], status="paused")
            elif action == "stop":
                self.store.set_slot(r["id"], None, "stopped")
            else:
                status, nxt = self._state_for(RuleSpec.model_validate(r["spec"]), person["timezone"], now,
                                              datetime.fromisoformat(r["created_at"]))
                self.store.set_slot(r["id"], nxt, status)
        word = {"pause": "Paused", "stop": "Stopped", "resume": "Resumed"}[action]
        names = ", ".join(RuleSpec.model_validate(r["spec"]).content.goal for r in targets)
        return self.send(h, f"{word}: {names}.")
