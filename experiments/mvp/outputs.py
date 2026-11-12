"""PROTOTYPE ONLY - outputs: what a rule or an answer does besides a chat message (DESIGN.md sections 2, 6, 7 and 11,
slice 4). Mixed into core.Bot.

- deliver(): after composing, for an ask and for every rule send, each action in the spec's `do` is performed once
  (actions/, in registry order), recorded in the action log (run, action, status, a reference such as the outbox
  file), and the reply says what was done in one short line per action. The thread's message goes last. A failed
  action never loses the chat answer; it is said in the reply. With no message.send, the thread gets only the lines,
  unless the email could not reach the person (no confirmed address, a failure, an outbox they cannot open): then the
  answer comes in the thread too.
  A timed send that is retried after a failed message does not repeat its other actions (the log is keyed by slot).
- act_on_last: the last answer (or a rule's latest send, answer_ref) or one pick of it, emailed, put on a calendar,
  added to a list or sent again, now or later ("when": a one-off rule whose content is source items for those picks).
- The person's email: their own address only. set_email stores it unconfirmed and sends a 6-digit code to it; they
  text the code back (15 minutes, 5 wrong tries, a new code on request). An email that needs a confirmed address
  waits (at most 3, for 24 hours) and goes out once the code is confirmed.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from . import config
from . import texts as T
from .actions import ordered, perform
from .actions import email as email_action
from .actions.base import Ctx, Outcome
from .render import Reply, pick_parts
from .schedule import next_run, say_time
from .schema import EMAIL, RuleSpec, list_name
from .store import now_iso

CODE = re.compile(r"^\s*(?:(?:my|the|here'?s? the|here is the)\s+)?(?:code(?:\s+is)?\s*[:\-]?\s*)?(\d{3})[\s-]?(\d{3})"
                  r"\s*[.!]?\s*$", re.I)
# "new code", "send me another code", "I didn't get the code": the whole message is about the code
NEW_CODE = re.compile(r"^\W*(?:(?:please|pls|can you|could you|can i (?:get|have))\s+)?(?:(?:send|text|email)\s+(?:me\s+)?)?"
                      r"(?:a\s+)?(?:new|another|fresh)\s+(?:6[- ]digit\s+)?code(?:\s+please)?\W*$"
                      r"|^\W*(?:please\s+)?(?:resend|re-send)\s+(?:me\s+)?(?:the\s+|my\s+|a\s+)?code(?:\s+please)?\W*$"
                      r"|^\W*(?:(?:send|text|email)\s+(?:me\s+)?)(?:the\s+|my\s+)?code\s+again(?:\s+please)?\W*$"
                      r"|^\W*(?:i\s+)?(?:didn'?t|did not|never|haven'?t)\s+(?:get|got|gotten|received?)\s+(?:the|a|my|any|your)"
                      r"\s+code\W*$", re.I)
BARE_EMAIL = re.compile(r"^\s*(?:(?:it'?s|it is|my email is|my email'?s|email:?|use)\s+)?([^@\s]+@[^@\s]+\.[A-Za-z]{2,})"
                        r"\s*[.!]?\s*$", re.I)
# someone other than the person ("email this to my mom"): sending to others stays out (DESIGN.md section 11)
OTHER_PERSON = re.compile(r"\b(?:my|our)\s+(?:mom|mum|mother|dad|father|parents?|wife|husband|partner|friends?|boss|"
                          r"sister|brother|son|daughter|girlfriend|boyfriend|roommate|colleague|coworker|co-worker|"
                          r"teacher|team|family|grandma|grandpa|aunt|uncle|cousin)s?\b|\b(?:to|cc)\s+(?:him|her|them)\b",
                          re.I)
SEND_WORDS = re.compile(r"\be-?mail\b|\bforward\b|\b(?:send|share)\s+(?:it|this|that|these|those|the\s+\w+\s+one)\b", re.I)
VERB = {"message.send": "send it to you here", "email.send": "email it to you",
        "calendar.add": "give you a link to put it on your calendar", "todo.add": "add it to your list"}


def _hash(salt, code):
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


class OutputsMixin:
    # ---------- the answer each run showed (store.answers) ----------
    def _keep_answer(self, run_id, handle, rule_id, goal, kind, parts, picks=()):
        self.store.put_answer(run_id, handle, rule_id, goal, kind, Reply.of(parts).parts, list(picks), at=self.clock())

    # ---------- the executor's do list ----------
    def deliver(self, person, spec, msg, run_id, kind="ask", rule_id=None, slot=None, request_text=None, after=""):
        """Performs the spec's `do` for this run's answer and sends the reply. `after` is a note that ends the reply
        however it is sent ("That was the last one of this rule."). Returns the thread message's reference."""
        h = person["handle"]
        names = [a.action for a in spec.do]
        answer = self.store.answer(run_id) if run_id else None
        if answer is None:   # nothing found, or an error: nothing to act on
            return self.send(h, msg + after if after else msg, run_id)
        ctx = Ctx(bot=self, person=person, answer=answer, picks=[p for p in answer["picks"] if p.get("main", True)],
                  run_id=run_id, rule_id=rule_id, kind=kind, now=self.clock(), tz=spec.when.tz or person["timezone"],
                  request_text=request_text or "", slot_at=datetime.fromisoformat(slot) if slot else None)
        done = self._perform(ctx, [(a.action, a.params) for a in spec.do], slot=slot)
        if "message.send" in names or ("email.send" in names and not self._email_reached(done)):
            # an email that waits for an address, failed, or sits in an outbox the person cannot open: the answer
            # comes here too, so it is never lost (with the line that says what happened to the email)
            ctx.chat = self._with_lines(msg, done) + after
            return self._message(ctx, slot)
        head = f"For \"{answer.get('goal') or 'your request'}\": "
        lines = self._with_lines(None, done, head=head)
        if not lines.parts:   # nothing to say about where it went: the answer itself, rather than silence
            lines = Reply.of(msg)
        else:
            block = getattr(self._tl, "outside_block", None)
            if block and block[0] == run_id:   # finds from YouTube are never emailed (never kept): they come here
                lines = lines + "\n\n" + block[1]
        return self.send(h, lines + after, run_id)

    def _email_reached(self, done):
        """True when the answer's email went where the person can read it: sent, or (on the test page) written to
        the Outbox panel they can open."""
        o = next((o for n, o in done if n == "email.send"), None)
        if o is None:
            return False
        return o.status == "done" or (o.status == "outbox" and bool(getattr(self.channel, "outbox_place", None)))

    def _perform(self, ctx, actions, slot=None):
        """[(name, Outcome)] for every action but message.send, in registry order. Each is logged."""
        class A:   # registry order works on objects with .action
            def __init__(self, name, params):
                self.action, self.params = name, params
        out, seen = [], set()
        for a in ordered([A(n, p) for n, p in actions]):
            if a.action == "message.send" or a.action in seen:   # each action once per answer
                continue
            seen.add(a.action)
            prior = self.store.action_done(ctx.rule_id, slot, a.action) if ctx.kind == "scheduled" else None
            if prior:   # this slot's send is being retried: what was done is not done again
                d = prior.get("detail") or {}
                o = Outcome(prior["status"], line=d.get("line") or "", link=d.get("link_part"), ref=prior.get("ref"))
                ctx.done.append((a.action, o))
                out.append((a.action, o))
                continue
            try:
                o = perform(a.action, ctx, a.params)
            except Exception as e:  # noqa: BLE001 - one failed action never loses the answer or the other actions
                o = Outcome("failed", line=T.ACTION_FAILED.get(a.action, T.ACTION_FAILED_OTHER),
                            detail={"error": type(e).__name__})
            ctx.done.append((a.action, o))
            self.store.log_action(ctx.handle, ctx.run_id, ctx.rule_id, a.action, o.status, ref=o.ref,
                                  detail=dict(o.detail or {}, line=o.line, link_part=o.link), slot=slot, at=ctx.now)
            out.append((a.action, o))
        return out

    def _message(self, ctx, slot=None):
        try:
            o = perform("message.send", ctx)
        except Exception as e:
            self.store.log_action(ctx.handle, ctx.run_id, ctx.rule_id, "message.send", "failed",
                                  detail={"error": type(e).__name__}, slot=slot, at=ctx.now)
            raise
        self.store.log_action(ctx.handle, ctx.run_id, ctx.rule_id, "message.send", "done", ref=o.ref, slot=slot,
                              at=ctx.now)
        return o.ref

    @staticmethod
    def _with_lines(base, done, head=""):
        """The reply with one line per action after it; a calendar link goes right after its line, as its own part."""
        r = Reply.of(base) if base is not None else Reply([])
        first, after_link = True, False
        for _, o in done:
            if o.line:
                line = (head if first else "") + o.line
                if not r.parts:
                    r = Reply([{"type": "text", "text": line}])
                else:
                    r = r + (("\n\n" if first or after_link else "\n") + line)
                first, after_link = False, False
            if o.link:
                r = r + Reply([o.link])
                after_link = True
        return r

    # ---------- acting on an answer ----------
    def _answer_picks(self, h, numbers=None, answer_ref=None, what="pick"):
        """(picks, whole, answer, problem): the picks of the last answer (or a rule's latest send) the person points
        at, each as kept by the executor: its checked title, link and details. For the last answer, the details are
        the ones its follow-ups kept. Nothing is chosen unless every number is in the answer."""
        last = self._answer_for(h, answer_ref)
        if not last or not last.get("items"):
            return None, False, None, T.NO_PICK_TO_ADD
        items = last["items"]
        if what == "ingredients" and not numbers and len(items) > 1:
            return None, False, None, T.which_pick(len(items))   # whose ingredients: one pick at a time
        whole = not numbers
        numbers = numbers or list(range(1, len(items) + 1))
        if any(not 1 <= n <= len(items) for n in numbers):
            return None, False, None, T.which_pick(len(items))
        snap = self.store.answer(last["run_id"]) or {}
        kept = {p["item_id"]: p for p in snap.get("picks") or []}
        if whole and snap.get("picks"):
            numbers = [n for n in numbers if kept.get(items[n - 1], {}).get("main", True)]   # not the wider links
        cur = self.store.last_answer(h)
        is_last = bool(cur) and cur["run_id"] == last["run_id"]
        lines = (self.store.get_state(f"lines:{h}", {}) or {}) if is_last else {}
        kinds = self.store.get_state(f"linekinds:{h}") if is_last else None
        facts = (self.store.get_state(f"facts:{h}", {}) or {}) if is_last else {}
        extract = (self.store.get_state(f"lastspec:{h}") or {}).get("spec", {}).get("content", {}).get("extract") or []
        extract = [extract] if isinstance(extract, str) else extract
        view = self.view(self.store.person(h)["library"])
        from .compose import title_from_item
        picks = []
        for n in numbers:
            iid = items[n - 1]
            rec = dict(kept.get(iid) or {})
            if not rec:   # an answer from before answers were kept: the item's own words
                it = view.get(iid)
                if it is None:
                    continue
                rec = {"item_id": iid, "title": title_from_item(it), "url": it.url, "platform": it.platform,
                       "video_id": it.video_id, "creator": it.creator, "facts": {}, "lines": [], "line_kinds": None}
            if is_last:
                rec["facts"] = (facts.get(iid) if isinstance(facts, dict) else None) or {}
                rec["lines"] = lines.get(iid) or []
                rec["line_kinds"] = kinds.get(iid) if isinstance(kinds, dict) else extract   # older state: the request's
            picks.append(rec)
        if not picks:
            return None, False, None, T.NO_PICK_TO_ADD
        if what == "ingredients":
            self._ingredients_now(h, picks, view, is_last)
        answer = snap or {"run_id": last["run_id"], "rule_id": last.get("rule_id"), "kind": "picks",
                          "goal": (cur or {}).get("goal"), "parts": [], "picks": picks}
        if not answer.get("parts"):
            whole = False   # nothing kept to send whole: the picks one by one
        return picks, whole, answer, None

    def _ingredients_now(self, h, picks, view, is_last):
        """Fix pass, finding 28: "add its ingredients to my list" when no ingredient lines were found yet (the answer
        did not ask for details): the details step runs now on the pick's whole text, checked as always."""
        from .extract import details
        person = self.store.person(h)
        for rec in picks:
            if (rec.get("facts") or {}).get("ingredients") or (rec.get("line_kinds") == ["ingredients"]
                                                                and rec.get("lines")):
                continue
            it = view.get(rec["item_id"])
            if it is None or self._over_cap(person):
                continue
            now = self.clock()
            extra = self._youtube().details([it], now=now) if it.platform == "youtube" else {}
            try:
                got, _ = details(it, ["ingredients"], view.lib, store=self.store, person=h, extra=extra, now=now)
            except Exception:  # noqa: BLE001 - then nothing is added, and the reply says so
                continue
            if got.get("ingredients"):
                rec["facts"] = dict(rec.get("facts") or {}, **{k: v for k, v in got.items() if v})
                if is_last:
                    fs = self.store.get_state(f"facts:{h}", {}) or {}
                    fs[rec["item_id"]] = rec["facts"]
                    self.store.set_state(f"facts:{h}", fs)

    def _plain_answer(self, h):
        """The newest answer when it is a reminder or a to-do list sent after the last picks ("email me that" after
        "Reminder: call mum"), or None."""
        row = self.store.one("SELECT run_id, kind FROM answers WHERE handle=? ORDER BY run_id DESC LIMIT 1", (h,))
        if not row or row["kind"] not in ("note", "todos"):
            return None
        cur = self.store.last_answer(h)
        if cur and cur.get("run_id") and cur["run_id"] > row["run_id"]:
            return None
        return self.store.answer(row["run_id"])

    def _act_on_last(self, person, it, text, now):
        h = person["handle"]
        if any(a.action == "email.send" for a in it.actions) and self.to_someone_else(text):
            return self.send(h, T.EMAIL_ONLY_YOU)
        acts = []
        for a in it.actions:
            params = dict(a.params)
            if a.action == "todo.add":
                params["list"] = it.todo_list or list_name(params.get("list")) or "todo"
            acts.append((a.action, params))
        if it.when is not None:
            return self._act_later(person, it, acts, text, now)
        what = next((p.get("what") for n, p in acts if n == "todo.add"), "pick") or "pick"
        plain = None
        if not it.pick_number and str(it.answer_ref or "last") == "last" and not any(n == "todo.add" for n, _ in acts):
            plain = self._plain_answer(h)
        if plain:   # a reminder or a list: the whole message, as it was sent
            picks, whole, answer, problem = [], True, plain, None
        else:
            picks, whole, answer, problem = self._answer_picks(h, [it.pick_number] if it.pick_number else None,
                                                               it.answer_ref, what)
        if problem:
            if problem == T.NO_PICK_TO_ADD and not any(n == "todo.add" for n, _ in acts):
                problem = T.NOTHING_TO_ACT_ON
            return self.send(h, problem)
        ctx = Ctx(bot=self, person=person, answer=answer, picks=picks, whole=whole, run_id=answer.get("run_id"),
                  rule_id=answer.get("rule_id"), kind="act_on_last", now=now, tz=person["timezone"], request_text=text)
        done = self._perform(ctx, acts)
        if any(n == "message.send" for n, _ in acts):   # "send me the second one again"
            base = Reply(answer["parts"]) if whole else Reply([q for p in picks for q in pick_parts(p)])
            ctx.chat = self._with_lines(base, done)
            return self._message(ctx)
        return self.send(h, self._with_lines(None, done))

    def _act_later(self, person, it, acts, text, now):
        """'Remind me of the 2nd one at 6', 'email me this tomorrow morning': a one-off rule whose content is the
        picks themselves (source items), so it sends them as they were, with no new search."""
        h, tz = person["handle"], person["timezone"]
        picks, whole, answer, problem = self._answer_picks(h, [it.pick_number] if it.pick_number else None,
                                                           it.answer_ref)
        if problem:
            return self.send(h, T.NOTHING_TO_ACT_ON if problem == T.NO_PICK_TO_ADD else problem)
        goal = picks[0]["title"] if len(picks) == 1 else f"the {len(picks)} picks for \"{answer.get('goal') or 'that'}\""
        do = [{"action": n, "params": p} for n, p in acts] or ["message.send"]
        spec = RuleSpec.model_validate({"when": it.when.model_dump(exclude_none=True),
                                        "content": {"source": "items", "item_ids": [p["item_id"] for p in picks][:10],
                                                    "goal": goal[:200], "count": min(len(picks), 10)}, "do": do})
        never = self._never_sends(person, spec, now)
        if never:
            return self.send(h, never)
        rule_id = self.store.add_rule(h, text, spec.stored(), "active", None, created_at=now_iso(now))
        nxt = next_run(spec.when, tz, now, anchor=now, seed=rule_id, quiet=self.store.quiet(h))
        self.store.set_slot(rule_id, now_iso(nxt), "active")
        self._wrote_rule(h, f"set up a one-time send of \"{goal}\"", rule_id)
        n = next((i for i, r in enumerate(self.store.rules(h), 1) if r["id"] == rule_id), len(self.store.rules(h)))
        verbs = [VERB[a.action] for a in spec.do if a.action in VERB]
        what = f"\"{goal}\"" if len(picks) == 1 else goal
        msg = T.later_set(say_time(nxt, now, spec.when.tz or tz), verbs, what, n)
        return self.send(h, msg + self._email_ask(person, spec, now))

    # ---------- what a spec's do means, in the replies that start or show a rule ----------
    @staticmethod
    def _do_note(spec):
        return T.outputs_note([a.action for a in spec.do], spec.when.repeating)

    def _email_ask(self, person, spec, now):
        """When a rule or a later send emails and there is no confirmed address: ask for it once, here."""
        if "email.send" not in {a.action for a in spec.do}:
            return ""
        addr, ok = self.store.email_of(person["handle"])
        if ok:
            return ""
        line = self._unconfirmed_line(person["handle"], addr, now)
        if line:
            return " " + line
        self.store.set_state(f"emailask:{person['handle']}", now_iso(now))
        return " " + T.EMAIL_ASK_RULE

    @staticmethod
    def to_someone_else(text):
        """'email this to my mom', 'forward it to my friend': a send to someone other than the person."""
        return bool(OTHER_PERSON.search(text) and SEND_WORDS.search(text))

    # ---------- the person's email address and its code ----------
    def _open_code(self, h, now):
        return self.store.get_state(f"emailcode:{h}")

    def _unconfirmed_line(self, h, addr, now):
        """For an address that has a code: 'text me the code' while it works, 'reply "new code"' once it has expired
        or was cancelled. None when there is no address with a code (the bot then asks for the address)."""
        code = self._open_code(h, now)
        if not (addr and code and code.get("email") == addr):
            return None
        live = not code.get("cancelled") and \
            now - datetime.fromisoformat(code["sent_at"]) <= timedelta(minutes=config.CODE_MINUTES)
        return T.email_confirm_first(addr) if live else T.email_new_code_first(addr)

    def set_email_from(self, person, email, text, now):
        """set_email from the interpreter: the address must be written in the person's own message (the model never
        supplies one), and it must be theirs: sending to someone else stays out."""
        h = person["handle"]
        if self.to_someone_else(text) or (OTHER_PERSON.search(text) and "@" in text):
            return self.send(h, T.EMAIL_ONLY_YOU)
        if not email or email.lower() not in text.lower():
            self.store.set_state(f"emailask:{h}", now_iso(now))
            return self.send(h, T.EMAIL_TYPE_IT)
        return self._set_email(person, email, now)

    def email_waiting(self, person, content, run_id, now):
        """email.send with no confirmed address: the email waits, and the line asks for the address (or the code)."""
        h = person["handle"]
        keep = now - timedelta(hours=config.EMAIL_WAIT_HOURS)
        held = self.store.get_state(f"emailwait:{h}") or []
        wait = [w for w in held if datetime.fromisoformat(w["at"]) > keep]
        expired = len(held) - len(wait)
        wait = wait + [{"content": content, "run_id": run_id, "at": now_iso(now)}]
        over = max(0, len(wait) - config.EMAIL_WAIT_MAX)
        wait = wait[-config.EMAIL_WAIT_MAX:]
        self.store.set_state(f"emailwait:{h}", wait)
        # fix pass, finding 30: an email dropped from the queue (too old, or over the cap) is said, once, here
        gone = (" " + T.emails_dropped(expired, over)) if (expired or over) else ""
        addr, _ = self.store.email_of(h)
        line = self._unconfirmed_line(h, addr, now)
        if line:
            return Outcome("waiting", line=line + gone)
        self.store.set_state(f"emailask:{h}", now_iso(now))
        return Outcome("waiting", line=T.EMAIL_ASK + gone)

    def _set_email(self, person, email, now, again=False, reply=True):
        """Stores the address unconfirmed and sends a new 6-digit code to it. The reply says what changed. With
        reply=False the reply's text is returned instead of sent (onboarding puts it in its own message)."""
        h = person["handle"]
        out = (lambda m: self.send(h, m)) if reply else (lambda m: m)
        email = email.strip().lower()
        cur, ok = self.store.email_of(h)
        if cur == email and ok and not again:
            return out(T.email_already(email) + self._flush_waiting(person, now))
        sent = [t for t in (self.store.get_state(f"emailcodes:{h}") or [])
                if datetime.fromisoformat(t) > now - timedelta(days=1)]
        if len(sent) >= config.CODES_PER_DAY:
            return out(T.CODE_LIMIT)
        self.store.set_email(h, email)
        self.store.set_state(f"emailask:{h}", None)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        salt = secrets.token_hex(8)
        self.store.set_state(f"emailcode:{h}", {"email": email, "salt": salt, "hash": _hash(salt, code),
                                                "sent_at": now_iso(now), "tries": 0})
        self.store.set_state(f"emailcodes:{h}", sent + [now_iso(now)])
        via, _path, err = email_action.send_code(self, h, email, code, now)
        self.store.log_action(h, None, None, "email.code", "done" if via == "smtp" else "outbox", ref=_path,
                              detail={"via": via, "error": err}, at=now)
        msg = T.code_sent(email, config.CODE_MINUTES, changed=bool(cur and cur != email), again=again)
        if via != "smtp":
            msg += " " + T.code_in_outbox(email_action.where_outbox(self), failed=bool(err))
        return out(msg)

    def _email_text(self, person, text, now):
        """A message about the email address that code answers without the model: a 6-digit code while one is open,
        "new code", or a bare address right after the bot asked for one. Returns the reply's reference, or None."""
        h = person["handle"]
        st = self._open_code(h, now)
        m = CODE.match(text)
        if st and m:
            self.note(intent="email_code")
            if st.get("cancelled"):
                return self.send(h, T.CODE_CANCELLED)
            if now - datetime.fromisoformat(st["sent_at"]) > timedelta(minutes=config.CODE_MINUTES):
                return self.send(h, T.CODE_EXPIRED)
            if hmac.compare_digest(_hash(st["salt"], m.group(1) + m.group(2)), st["hash"]):
                self.store.set_email(h, st["email"], verified=True, at=now)
                self.store.set_state(f"emailcode:{h}", None)
                return self.send(h, T.email_confirmed(st["email"]) + self._flush_waiting(person, now))
            st["tries"] = st.get("tries", 0) + 1
            if st["tries"] >= config.CODE_TRIES:
                st["cancelled"] = True
                self.store.set_state(f"emailcode:{h}", st)
                return self.send(h, T.CODE_TOO_MANY)
            self.store.set_state(f"emailcode:{h}", st)
            return self.send(h, T.code_wrong(config.CODE_TRIES - st["tries"]))
        if NEW_CODE.match(text):
            addr, ok = self.store.email_of(h)
            target = (st or {}).get("email") or (addr if addr and not ok else None)
            if target:
                self.note(intent="email_code")
                return self._set_email(person, target, now, again=True)
        asked = self.store.get_state(f"emailask:{h}")
        m = BARE_EMAIL.match(text)
        if m and not re.match(EMAIL, m.group(1)):   # "x,y@b.co" would reach two people
            m = None
        if m and asked and datetime.fromisoformat(asked) > now - timedelta(hours=config.EMAIL_WAIT_HOURS):
            self.note(intent="set_email")
            return self._set_email(person, m.group(1), now)
        return None

    def _flush_waiting(self, person, now):
        """The emails that waited for a confirmed address go out now; one line each, after a newline."""
        h = person["handle"]
        to, ok = self.store.email_of(h)
        keep = now - timedelta(hours=config.EMAIL_WAIT_HOURS)
        held = self.store.get_state(f"emailwait:{h}") or []
        wait = [w for w in held if datetime.fromisoformat(w["at"]) > keep]
        expired = len(held) - len(wait)
        self.store.set_state(f"emailwait:{h}", None)
        lines = [T.emails_dropped(expired, 0)] if (ok and expired) else []   # finding 30: said once, never silently
        if not ok or not wait:
            return ("\n" + "\n".join(lines)) if lines else ""
        for w in wait:
            c = w["content"]
            try:
                via, path, err = email_action.send(self, h, to, c["subject"], c["text"], c.get("html"),
                                                   [tuple(x) for x in c.get("attach") or []], w.get("run_id"), now)
            except Exception as e:  # noqa: BLE001 - one waiting email never stops the others
                self.store.log_action(h, w.get("run_id"), None, "email.send", "failed", detail={"error": type(e).__name__},
                                      at=now)
                lines.append(T.waiting_failed(c["subject"]))
                continue
            self.store.log_action(h, w.get("run_id"), None, "email.send", "done" if via == "smtp" else "outbox",
                                  ref=path, detail={"via": via, "error": err}, at=now)
            lines.append(T.waiting_sent(c["subject"], to, via, err, email_action.where_outbox(self)))
        return "\n" + "\n".join(lines)
