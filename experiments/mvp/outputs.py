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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config
from . import texts as T
from .actions import ordered, perform
from .actions import email as email_action
from .actions.base import Ctx, Outcome, outbox_reachable
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
# checker of fix pass 4, finding 78: "it", "that one" mean the pick the answer opened with (every library answer leads with
# one pick, its details shown, and the others one line each); "them", "these", "both" mean them all
ONE_PICK = re.compile(r"\b(?:it|its|that one|this one|the one you (?:recommended|picked)|th(?:at|is) (?:recipe|video|post|reel|"
                      r"workout|tutorial|routine|lesson|pick))\b", re.I)
ALL_PICKS = re.compile(r"\b(?:them|these|those|they|all|both|everything|each|the picks|the others)\b", re.I)


def lead_only(text, acts):
    """True when an act on the last answer with no number points at one pick ("add it to my list", "put that one on my
    calendar", "remind me of it tonight"): that is the lead pick. An email of "it" is the whole answer, as before."""
    return bool(ONE_PICK.search(text or "")) and not ALL_PICKS.search(text or "") and \
        not any(n == "email.send" for n, _ in acts)


SEND_WORDS = re.compile(r"\be-?mail\b|\bforward\b|\b(?:send|share)\s+(?:it|this|that|these|those|the\s+\w+\s+one)\b", re.I)
VERB = {"message.send": "send it to you here", "email.send": "email it to you",
        "calendar.add": "give you a link to put it on your calendar", "todo.add": "add it to your list"}


def _hash(salt, code):
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


# checker, round 7: a reminder set relative to a thing's own date ("two days before its deadline", "on its deadline")
WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}
BEFORE_DATE = re.compile(r"\b(?:(\d{1,2}|a|an|one|two|three|four|five|six|seven|ten)\s+(days?|weeks?)|(the day|the week))"
                         r"\s+before\s+(?:its\s+|the\s+|it\s+)?(?:deadline|due date|due|closes|close|closing date|ends|"
                         r"end date|starts|start date|date)\b|\b(?:on|the day of)\s+(?:its|the)\s+(deadline|due date)\b",
                         re.I)


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
        snap = self.store.answer(last["run_id"]) or {}
        kept = {p["item_id"]: p for p in snap.get("picks") or []}
        if what == "pick":   # round 7, finding 90: an items answer: a number or a name means one of its things
            got = self._answer_item(snap, numbers)
            if got is not None:
                return got
        if what == "ingredients" and not numbers and len(items) > 1:
            # whose ingredients: one pick at a time. Fix pass 3, finding 68: the wider links are not picks with
            # details, so an answer with one recommended pick and a wider selection means that pick
            main = [n for n, iid in enumerate(items, 1) if kept.get(iid, {}).get("main", True)] if kept else []
            lead = kept.get(items[0]) or {}
            if len(main) > 1 and lead.get("main", True) and (lead.get("facts") or {}).get("ingredients"):
                # fix pass 4, finding 78: "it", "the ingredients" with no number mean the lead pick, the one the answer
                # opened with and showed the ingredients of; the alternatives under it were one line each
                main = [1]
            if len(main) != 1:
                return None, False, None, T.which_pick(len(items))
            numbers = main
        whole = not numbers
        numbers = numbers or list(range(1, len(items) + 1))
        if any(not 1 <= n <= len(items) for n in numbers):
            return None, False, None, T.which_pick(len(items))
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

    ITEM_NAME_SKIP = set("""add put the a an to my me list lists todo to-do calendar remind reminder about one ones next
week tomorrow tonight that this it its on in for of and or please pls can you could would email send text at from
saves saved post posts link""".split())

    def _answer_item(self, snap, numbers):
        """(picks, whole, answer, problem) for the one thing of an items answer the person points at (its number, or
        its name in their message), each as a pick record: the thing's name, its words, its date, and the link of the
        post it came from. None when the answer names no things, or the message points at none of them."""
        from .compose import tokens
        its = [(x, p) for p in snap.get("picks") or [] for x in p.get("items") or []]
        if not its:
            return None
        chosen = None
        if numbers and len(numbers) == 1:
            chosen = next(((x, p) for x, p in its if x.get("n") == numbers[0]), None)
            if chosen is None:
                return None, False, None, T.which_item(len(its))
        elif not numbers:
            said = {w for w in tokens(getattr(self._tl, "msg_text", "") or "") if w not in self.ITEM_NAME_SKIP}
            scored = []
            for x, p in its:
                words = [w for w in tokens(x.get("name") or "") if w not in self.ITEM_NAME_SKIP
                         and (len(w) >= 3 or w.isupper())]
                hits = sum(1 for w in words if w in said)
                if hits:
                    scored.append((hits, x["n"], x, p))
            if scored:
                scored.sort(key=lambda r: (-r[0], r[1]))
                if len(scored) == 1 or scored[0][0] > scored[1][0]:
                    chosen = (scored[0][2], scored[0][3])
        if chosen is None:
            return None
        x, p = chosen
        rec = {"item_id": p["item_id"], "title": x.get("name"), "url": p.get("url"), "platform": p.get("platform"),
               "video_id": p.get("video_id"), "creator": p.get("creator"),
               "facts": {"key_points": [x["about"]]} if x.get("about") else {}, "lines": [], "line_kinds": None,
               "item": dict(x), "source_title": p.get("title"), "main": True, "posted": p.get("posted")}
        return [rec], False, snap, None

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
        rel = BEFORE_DATE.search(text or "")
        if rel:   # checker, round 7: "remind me about the NASA one two days before its deadline": code works out the day
            got = self._before_date(person, it, acts, text, now, rel)
            if got is not None:
                return got
        if it.when is not None:
            return self._act_later(person, it, acts, text, now)
        what = next((p.get("what") for n, p in acts if n == "todo.add"), "pick") or "pick"
        plain = None
        if not it.pick_number and str(it.answer_ref or "last") == "last" and not any(n == "todo.add" for n, _ in acts):
            plain = self._plain_answer(h)
        if plain:   # a reminder or a list: the whole message, as it was sent
            picks, whole, answer, problem = [], True, plain, None
        else:
            one = [1] if not it.pick_number and what == "pick" and lead_only(text, acts) else None
            picks, whole, answer, problem = self._answer_picks(h, [it.pick_number] if it.pick_number else one,
                                                               it.answer_ref, what)
        if problem:
            if problem == T.NO_PICK_TO_ADD and not any(n == "todo.add" for n, _ in acts):
                problem = T.NOTHING_TO_ACT_ON
            return self.send(h, problem)
        item = (picks[0].get("item") if picks and len(picks) == 1 else None) or {}
        day = self._thing_date(picks[0], now, person) if item else None
        if day is not None and day >= now.astimezone(ZoneInfo(person["timezone"])).date():
            # round 7: "put the NASA one in my calendar": on the date its post gives, when none is named (checker: read
            # by code from the thing's own words for any request, not only a time-sensitive one)
            acts = [(n, dict(p, date=day.isoformat()) if n == "calendar.add" and not p.get("date")
                     and not p.get("day_offset") else p) for n, p in acts]
        ctx = Ctx(bot=self, person=person, answer=answer, picks=picks, whole=whole, run_id=answer.get("run_id"),
                  rule_id=answer.get("rule_id"), kind="act_on_last", now=now, tz=person["timezone"], request_text=text)
        before = self.store.get_state(f"lastwrite:{h}")
        done = self._perform(ctx, acts)
        # review fix S5: an email or a calendar link cannot be taken back; "undo" after it never reaches back to an
        # older write. With todo.add as well, "undo" takes those to-dos off and says the rest stays.
        final = [w for n, w in (("email.send", "an email"), ("calendar.add", "a calendar link"))
                 if any(a == n and o.status not in ("failed", "skipped") for a, o in done)]
        if final:
            todo_write = self.store.get_state(f"lastwrite:{h}")
            self._wrote_final(h, " or ".join(final))
            if todo_write and todo_write != before:
                self._join_writes(h, self.store.get_state(f"lastwrite:{h}"), todo_write)
        if any(n == "message.send" for n, _ in acts):   # "send me the second one again"
            base = Reply(answer["parts"]) if whole else Reply([q for p in picks for q in pick_parts(p)])
            ctx.chat = self._with_lines(base, done)
            return self._message(ctx)
        return self.send(h, self._with_lines(None, done))

    def _thing_date(self, rec, now, person):
        """Checker, round 7: the date a thing of an items answer (or a post) gives in its own words, read by code with
        the post's year for a date that has none; None when its words give no date."""
        from .dates import deadline_in, first_kept, posted_on
        x = rec.get("item") or {}
        if x:
            if x.get("date"):
                return datetime.fromisoformat(x["date"]).date()
            hint = rec.get("posted") or rec.get("kept")
            return deadline_in(" ".join(t for t in (x.get("when"), x.get("about")) if t), hint)[0]
        got = self.view(person["library"]).get(rec.get("item_id"))
        if got is None:
            return None
        return deadline_in(got.raw_caption or got.caption, posted_on(got) or first_kept(got))[0]

    def _before_date(self, person, it, acts, text, now, rel):
        """"Remind me about <name> two days before its deadline": the day is the thing's own date less the days asked
        for, at the time named (else 9am). With no date in its words, or one that has passed or is too near, it says
        so in one plain line and sets nothing. None when the message points at no single thing or pick."""
        from .dates import date_note, say_day
        from .schema import When
        h = person["handle"]
        picks, _, _, problem = self._answer_picks(h, [it.pick_number] if it.pick_number else None, it.answer_ref)
        if problem or not picks or len(picks) != 1:
            return None
        rec = picks[0]
        name = rec.get("title") or "it"
        day = self._thing_date(rec, now, person)
        if day is None:
            return self.send(h, T.no_date_for(name))
        n = WORD_NUM.get((rel.group(1) or "").lower(), None)
        n = int(rel.group(1)) if n is None and (rel.group(1) or "").isdigit() else (n if n is not None else 1)
        if (rel.group(2) or "").lower().startswith("week") or (rel.group(3) or "").lower() == "the week":
            n *= 7
        if rel.group(4):   # "on its deadline"
            n = 0
        today = now.astimezone(ZoneInfo(person["timezone"])).date()
        if day < today:
            return self.send(h, T.date_passed_for(name, date_note({"state": "passed", "date": day, "deadline": True},
                                                                  today)))
        target = day - timedelta(days=n)
        if target < today or (target == today and n):
            return self.send(h, T.date_too_near(name, f"{say_day(day, today)}"))
        time = (it.when.time if it.when is not None and it.when.time else None) or "09:00"
        acts = [(a, p) for a, p in acts if a != "calendar.add"] or [("message.send", {})]
        it = it.model_copy(update={"when": When(type="once", date=target.isoformat(), time=time),
                                   "actions": [x for x in it.actions if x.action != "calendar.add"] or it.actions})
        return self._act_later(person, it, acts, text, now)

    def _act_later(self, person, it, acts, text, now):
        """'Remind me of the 2nd one at 6', 'email me this tomorrow morning': a one-off rule whose content is the
        picks themselves (source items), so it sends them as they were, with no new search."""
        h, tz = person["handle"], person["timezone"]
        one = [1] if not it.pick_number and lead_only(text, acts) else None   # "remind me of it tonight"
        picks, whole, answer, problem = self._answer_picks(h, [it.pick_number] if it.pick_number else one,
                                                           it.answer_ref)
        if problem:
            return self.send(h, T.NOTHING_TO_ACT_ON if problem == T.NO_PICK_TO_ADD else problem)
        goal = picks[0]["title"] if len(picks) == 1 else f"the {len(picks)} picks for \"{answer.get('goal') or 'that'}\""
        do = [{"action": n, "params": p} for n, p in acts] or ["message.send"]
        when = it.when.model_dump(exclude_none=True)
        if when.get("date") and when.get("times"):   # "in 2 hours", resolved by code: the moment is what is kept
            when.pop("in_minutes", None)            # (validation would otherwise drop it and the send never comes)
        names = [p["item"]["name"] for p in picks if p.get("item") and p["item"].get("name")]
        spec = RuleSpec.model_validate({"when": when,
                                        "content": {"source": "items", "item_ids": [p["item_id"] for p in picks][:10],
                                                    "goal": goal[:200], "count": min(len(picks), 10),
                                                    # round 7: one thing of an items answer, by its name
                                                    **({"item_names": names[:10]} if names else {})}, "do": do})
        never = self._never_sends(person, spec, now)
        if never:
            return self.send(h, never)
        rule_id = self.store.add_rule(h, text, spec.stored(), "active", None, created_at=now_iso(now))
        nxt = next_run(spec.when, tz, now, anchor=now, seed=rule_id, quiet=self.store.quiet(h))
        self.store.set_slot(rule_id, now_iso(nxt), "active")
        self._wrote_rule(h, f"set up a one-time send of \"{goal}\"", rule_id)
        n = self.store.rule_number(h, rule_id)
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
        # review fix X10: the codes a day are counted in real time (the test page's clock can move; the emails are real)
        real = datetime.now(timezone.utc)
        sent = [t for t in (self.store.get_state(f"emailcodes:{h}") or [])
                if datetime.fromisoformat(t) > real - timedelta(days=1)]
        if len(sent) >= config.CODES_PER_DAY:
            return out(T.CODE_LIMIT)
        if not outbox_reachable(self) and not email_action.smtp_settings():
            # review fix X8: no email is set up, and this person cannot open the outbox: a code could never reach them
            self.store.set_state(f"emailask:{h}", None)
            return out(T.EMAIL_NOT_SET_UP)
        self.store.set_email(h, email)
        self.store.set_state(f"emailask:{h}", None)
        self._wrote_final(h, "an email address change")   # review fix S5
        code = f"{secrets.randbelow(10 ** 6):06d}"
        salt = secrets.token_hex(8)
        self.store.set_state(f"emailcode:{h}", {"email": email, "salt": salt, "hash": _hash(salt, code),
                                                "sent_at": now_iso(now), "tries": 0})
        via, _path, err = email_action.send_code(self, h, email, code, now)
        self.store.log_action(h, None, None, "email.code", {"smtp": "done", "none": "failed"}.get(via, "outbox"),
                              ref=_path, detail={"via": via, "error": err}, at=now)
        if via == "none":
            # review fix X8: the code did not go out and is kept nowhere: it is not counted toward the day's codes,
            # and the reply says so plainly ("new code" tries again)
            self.store.set_state(f"emailcode:{h}", None)
            return out(T.code_not_sent(email, changed=bool(cur and cur != email)))
        self.store.set_state(f"emailcodes:{h}", sent + [now_iso(real)])
        msg = T.code_sent(email, config.CODE_MINUTES, changed=bool(cur and cur != email), again=again)
        if via != "smtp" and err and not again:
            msg = T.code_failed_to_outbox(email, config.CODE_MINUTES, email_action.where_outbox(self),
                                          changed=bool(cur and cur != email))
        elif via != "smtp":
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
