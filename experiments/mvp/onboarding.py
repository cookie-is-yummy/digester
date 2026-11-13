"""PROTOTYPE ONLY - onboarding (DESIGN.md section 5, slice 6). Mixed into core.Bot.

At most four bot messages, each step skippable ("skip"), and a real request at any step is answered, after which the
setup goes on:
  1. Consent (as before).
  2. The read of the person (profile.guess on their library, adopted as unconfirmed interests): their main interests,
     the level guessed, each with a count worked out by code; then "did I get that right, and what are you working
     toward?"
  3. Their answer is merged into the profile (profile.merge: the model fills a form, code checks it); the reply says in
     one or two lines what the bot now knows, asks for the email address (the code flow of the outputs slice) and
     checks the time zone.
  4. The export routine of the refresh slice (links, choices, the reminder offer), then up to three first requests
     written for this person, each checked by code to find at least three candidates in their library, and the offer
     of the first one as a morning rule (a preview and a YES, like any library rule).
The step is kept in state `onboard:<handle>`. Only someone who agrees from now on is set up this way: a person already
in the store is not put through it again; "set me up again" restarts it at step 2.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, llm
from . import profile as P
from . import texts as T
from .schedule import describe, next_run, say_time
from .schema import EMAIL, RuleSpec
from .store import now_iso

ADDRESS = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
FILLER = set("my email is it's its it is use here you go and thanks thank please email address the i'm im".split())


class OnboardingMixin:
    # ---------- state ----------
    def _onboard(self, h):
        return self.store.get_state(f"onboard:{h}")

    def _set_onboard(self, h, step, now, **extra):
        self.store.set_state(f"onboard:{h}", {"step": step, "at": now_iso(now), **extra})

    # ---------- step 2: the read ----------
    def onboard_start(self, person, now, lead="Thanks!"):
        """After consent (or "set me up again"): the guess, kept as unconfirmed interests, and message 2."""
        h = person["handle"]
        lines, shown, guessed = [], [], None
        try:
            if self._over_cap(person):
                raise RuntimeError("over the cap")
            result, _ = P.guess(self.view(person["library"]), store=self.store, handle=h, now=now)
            P.adopt_guess(self.store, h, result, now=now)
            prof = P.get(self.store, h)
            lines = P.read_lines(prof)   # finding 41: every guessed topic is shown, most saved first
            shown = [i["topic"] for i in prof["interests"][:len(lines)]]
            guessed = P.direction_guess(prof["interests"]) if not prof["direction"] else None
        except Exception as e:  # noqa: BLE001 - the setup goes on without a read
            self.store.add_run(handle=h, kind="profile_guess", status="error", error=type(e).__name__)
        self._set_onboard(h, "read", now, shown=shown, guessed_direction=guessed)
        self.note(intent="onboarding")
        return self.send(h, T.read_message(lines, lead=lead, direction=guessed))

    # ---------- any message while the setup is open ----------
    def onboard_step(self, person, text, now):
        """Handles a message during the setup; returns the reply's reference, or None when the message is not part of
        the setup (it then goes through the normal path)."""
        h = person["handle"]
        if T.SET_ME_UP_AGAIN.match(text):
            return self.onboard_start(person, now, lead="OK, let's set you up again.")
        st = self._onboard(h)
        if not st or st.get("step") == "done":
            return None
        step = st["step"]
        if step in ("read", "contact"):
            if datetime.fromisoformat(st["at"]) < now - timedelta(hours=config.ONBOARD_STEP_HOURS):
                self._set_onboard(h, "done", now)   # they never answered: the setup ends quietly ("set me up again")
                return None
            pending = self._live_pending(h, now)
            if pending and pending["kind"] == "clarify":
                return None   # a request answered in the middle asked a question: this message answers it
        if step == "read":
            return self._onboard_read(person, text, now)
        if step == "contact":
            return self._onboard_contact(person, text, now)
        if step == "offer":
            if datetime.fromisoformat(st["at"]) < now - timedelta(hours=config.ONBOARD_OFFER_HOURS):
                self._set_onboard(h, "done", now)
                return None
            ref = self._onboard_choice(person, st, text, now)
            if ref is None and st.get("prefs_open"):
                return self._onboard_prefs(person, st, text, now)   # finding 46: the optional last question
            if ref is None:
                # fix pass, finding 34: the offer closes once two other messages have come since, so a bare "2"
                # much later is never read as a pick from it
                others = (st.get("others") or 0) + 1
                if others >= 2:
                    self._set_onboard(h, "done", now)
                else:
                    self.store.set_state(f"onboard:{h}", dict(st, others=others))
            return ref
        return None

    def _onboard_read(self, person, text, now):
        h = person["handle"]
        self.note(intent="onboarding")
        if T.SKIP.match(text):
            return self._onboard_contact_ask(person, now, "No problem.")
        if T.RIGHT.match(text):
            st = self._onboard(h) or {}
            res = P.apply_merge(self.store, h, {"kind": "about_me", "confirm_all": True}, text,
                                shown=st.get("shown") or [])
            if st.get("guessed_direction") and not P.get(self.store, h)["direction"]:
                self.store.set_direction(h, st["guessed_direction"])   # the direction they just said yes to
            return self._onboard_contact_ask(person, now, "Great, thanks." + self._knows_line(h), res)
        if self._over_cap(person):   # no paid call: the answer is kept as a note, and the setup goes on
            self.store.add_profile_note(h, " ".join(text.split())[:300], at=now)
            return self._onboard_contact_ask(person, now, "Thanks.")
        st0 = self._onboard(h) or {}
        try:
            res, _ = P.merge(self.store, h, text, asked="Here's my read of you (their main interests). Did I get that "
                             "right? And in a sentence or two, what are you working toward right now?",
                             shown=st0.get("shown") or [])
        except Exception as e:  # noqa: BLE001 - their words are kept as a note, and the setup goes on
            self.store.add_run(handle=h, kind="profile_merge", status="error", error=type(e).__name__)
            self.store.add_profile_note(h, " ".join(text.split())[:300], at=now)
            return self._onboard_contact_ask(person, now, "Thanks.")
        if res.get("confirmed_all") and st0.get("guessed_direction") and not P.get(self.store, h)["direction"]:
            # checker, round 2 (finding 41): "mostly right" through the form also says yes to the direction it was
            # shown, as a bare "yes" does; a goal of their own (stored by the form) wins
            self.store.set_direction(h, st0["guessed_direction"])
        if res["kind"] in ("request", "both"):
            # merged already: a profile_note in it is not merged a second time, and a reading of it as only about
            # them (profile_update, chat) sends nothing, so the one summary below is the only reply (finding 42)
            self._tl.merged_text = text
            try:
                ref = self.answer_normally(person, text, now)   # the request is answered; then the setup goes on
            finally:
                self._tl.merged_text = None
            if res["kind"] == "request":
                st = self._onboard(h) or {}
                pending = self._live_pending(h, now)
                if st.get("reasked") or (pending and (pending["kind"] == "clarify"
                                                      or datetime.fromisoformat(pending["at"]) >= now)):
                    return ref   # asked once already, or the answer just asked a question of its own (a YES, a date)
                self._set_onboard(h, "read", datetime.fromisoformat(st["at"]) if st.get("at") else now, reasked=True,
                                  shown=st.get("shown") or [])
                return self.send(h, T.READ_AGAIN) or ref
        lead = "Thanks." + self._knows_line(h)
        return self._onboard_contact_ask(person, now, lead, res)

    def _knows_line(self, h):
        s = P.short_summary(P.get(self.store, h))
        return (" Here's what I have now: " + s) if s else ""

    # ---------- step 3: the email address and the time zone ----------
    def _onboard_contact_ask(self, person, now, lead, res=None):
        h = person["handle"]
        person = self.store.person(h) or person   # a request answered in between may have moved the time zone
        if res and res.get("other"):   # a setting their answer changed that the summary does not show
            lead += " " + T.cap_first("; ".join(res["other"])) + "."
        if res and res.get("skipped_sensitive"):
            lead += self._sensitive_once(" ")
        tz = person["timezone"]
        local = now.astimezone(ZoneInfo(tz)).strftime("%-I:%M%p").lower()
        _, ok = self.store.email_of(h)
        from .actions.base import outbox_reachable
        from .actions.email import smtp_settings
        if not outbox_reachable(self) and not smtp_settings():
            ok = True   # review fix X8: no email is set up and the outbox is out of reach: the address is not asked
        self._set_onboard(h, "contact", now)
        return self.send(h, T.contact_message(lead, T.zone_name(tz), local, has_email=ok))

    def _onboard_contact(self, person, text, now):
        self.note(intent="onboarding")
        if T.SKIP.match(text) or T.RIGHT.match(text):
            return self._onboard_final(person, now)
        m = ADDRESS.search(text)
        if m and re.match(EMAIL, m.group(0)) and not self.to_someone_else(text):
            line = self._set_email(person, m.group(0), now, reply=False)
            rest = [w for w in re.findall(r"[a-z']+", (text[:m.start()] + " " + text[m.end():]).lower())
                    if w not in FILLER]
            if rest:   # "a@b.co, and I'm in Chicago now": the rest is a request of its own (without the address,
                #          which is set already)
                self.answer_normally(person, " ".join((text[:m.start()] + " " + text[m.end():]).split()), now)
            return self._onboard_final(person, now, lead=line)
        self.answer_normally(person, text, now)   # a time zone ("I'm in Chicago") or any other request
        return self._onboard_final(person, now)

    # ---------- step 4: the export routine and the first requests ----------
    def _onboard_final(self, person, now, lead=""):
        """The setup's last message: the export reminder offer (one line, finding 43), up to three first requests,
        and one optional question about what would help the bot pick (finding 46)."""
        from .refresh import offer_export_routine
        h = person["handle"]
        person = self.store.person(h)   # the time zone may have just changed
        parts = [lead] if lead else []
        try:
            parts.append(offer_export_routine(self, h, now=now))
        except Exception as e:  # noqa: BLE001
            self.store.add_run(handle=h, kind="export_routine", status="error", error=type(e).__name__)
        reqs = []
        try:
            reqs = self.first_requests(person, now)
        except Exception as e:  # noqa: BLE001 - no offer rather than an unchecked one
            self.store.add_run(handle=h, kind="first_requests", status="error", error=type(e).__name__)
        if reqs:
            parts.append(T.first_requests_block([r["text"] for r in reqs]))
        parts.append(T.PREFS_QUESTION)
        self._set_onboard(h, "offer", now, requests=reqs, prefs_open=True)
        return self.send(h, "\n\n".join(p for p in parts if p))

    def _onboard_prefs(self, person, st, text, now):
        """The answer to the last question ("food you avoid, kit you have, how much time you usually have?"), merged
        into the profile by the form call. A request in it is answered as usual. Either way the question is closed,
        and with it the setup unless the first-requests offer is still open."""
        h = person["handle"]
        self.note(intent="onboarding")
        started = self._export_yes(person, text, now) or self._export_no(person, text, now)
        if started:
            text_rest = T.NO_LEAD.sub("", T.YES_LEAD.sub("", text)).strip(" ,.!;:-")
            text_rest = re.sub(r"^(?:and|also|plus|y)\b[\s,]*", "", text_rest, flags=re.I).strip()
            if not text_rest or T.YES.match(text_rest):   # "ok, sure": only the reminders
                return self.send(h, started)
            started += "\n\n"
        others = (st.get("others") or 0) + 1
        if not st.get("requests") or others >= 2:
            self._set_onboard(h, "done", now)
        else:
            self.store.set_state(f"onboard:{h}", dict(st, prefs_open=False, others=others))
        if T.SKIP.match(text):
            return self.send(h, started + T.PREFS_SKIPPED)
        if self._over_cap(person):
            self.store.add_profile_note(h, " ".join(text.split())[:300], at=now)
            return self.send(h, started + T.PREFS_THANKS)
        try:
            res, _ = P.merge(self.store, h, text, asked=T.PREFS_QUESTION)
        except Exception as e:  # noqa: BLE001 - their words are kept as a note
            self.store.add_run(handle=h, kind="profile_merge", status="error", error=type(e).__name__)
            self.store.add_profile_note(h, " ".join(text.split())[:300], at=now)
            return self.send(h, started + T.PREFS_THANKS)
        said = T.profile_changed(res["changes"], res["skipped_sensitive"] and self._sensitive_once()) \
            if res["changes"] else ""
        if res["kind"] in ("request", "both"):
            if started:
                self.send(h, started.strip())
            self._tl.merged_text = text
            self._tl.carry_said = said or None   # what changed rides on the answer (_dispatch takes it up)
            try:
                return self.answer_normally(person, text, now)
            finally:
                self._tl.merged_text = None
                self._tl.carry_said = None
        if not said and not res["skipped_sensitive"]:
            note = " ".join(text.split())[:300]
            if not P.stated_sensitive(note):
                self.store.add_profile_note(h, note, at=now)
        return self.send(h, started + (said or (T.PREFS_THANKS + (self._sensitive_once(" ") if res["skipped_sensitive"]
                                                                 else ""))))

    def _export_yes(self, person, text, now):
        """Review fix X6 (experience): the setup's last message asks "OK?" about the export reminders and asks about
        their kit. An answer to both ("ok sure, and I have an instant pot") starts the reminders too, and returns the
        line that says so; else ''."""
        from .handler import EXPORT_REMINDER
        h = person["handle"]
        pending = self._live_pending(h, now)
        if not (pending and pending["kind"] == "confirm_rule"
                and EXPORT_REMINDER.match(str(pending["payload"].get("text") or ""))):
            return ""
        if not T.YES_LEAD.match(text) or T.NEGATION.search(text):
            return ""
        self.store.clear_pending(h)
        self._tl.join_write = True
        try:
            return self._start_export_reminders(person, [pending["payload"]] + list(pending["payload"].get("more") or []),
                                                say=False) or ""
        finally:
            self._tl.join_write = False

    def _export_no(self, person, text, now):
        """Fix pass 3, finding 72: "no. I have an instant pot" at the last step: the reminders are not started, the
        offer is closed, and the reply says so before the rest. "no mushrooms" is about food, not the reminders."""
        from .handler import EXPORT_REMINDER
        h = person["handle"]
        pending = self._live_pending(h, now)
        if not (pending and pending["kind"] == "confirm_rule"
                and EXPORT_REMINDER.match(str(pending["payload"].get("text") or ""))):
            return ""
        if not (T.NO_LEAD.match(text) or T.NO_REMINDERS.search(text)):
            return ""
        self.store.clear_pending(h)
        return T.EXPORT_DECLINED

    def first_requests(self, person, now):
        """Up to FIRST_REQUESTS requests written for the person (one model call), each run through retrieval and
        kept only when at least FIRST_REQUEST_MIN candidates mention its topic words. [{text, spec}]."""
        from .retrieve import candidates, contains_word
        h = person["handle"]
        if self._over_cap(person):
            return []
        about = "\n".join(P.about_lines(self.store, h)) or "Nothing is known yet: write requests for common hobbies."
        raw, _ = llm.chat_json(P._prompt(config.PROMPT_FIRST_REQUESTS), "<about>" + about.replace("<", "‹") + "</about>",
                               purpose="mvp_first_requests", prompt_version=config.PROMPT_FIRST_REQUESTS, person=h,
                               max_tokens=900, temperature=config.PROFILE_TEMPERATURE, seed=config.PROFILE_SEED)
        view = self.view(person["library"])
        ex_kinds, ex_platforms = self._exclusions(h)
        prof = P.get(self.store, h)
        out = []
        for r in (raw.get("requests") if isinstance(raw, dict) else None) or []:
            if len(out) >= config.FIRST_REQUESTS or not isinstance(r, dict):
                continue
            text = P._clean(r.get("text"), 110)
            if not text or P.sensitive(text, r.get("goal"), " ".join(map(str, r.get("searches") or []))):
                continue
            try:
                spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
                    "source": "library", "goal": P._clean(r.get("goal"), 120) or text,
                    "searches": [str(s) for s in (r.get("searches") or [])][:3] or [text],
                    "criteria": [str(c) for c in (r.get("criteria") or [])][:3],
                    "extract": r.get("extract") or [], "count": 3}})
            except ValueError:
                continue
            c = spec.content
            # checker of fix pass 4: the setup's model writes these with the profile in view; a must-have the request's
            # own text does not say (their kit, their usual time, their level) is a preference, as for any message
            from .interpret import guard_criteria
            c.criteria = guard_criteria(c.criteria, c.avoid, text, prof)
            words = P.topic_words(c.goal, *c.searches)
            if not words or any(x["spec"]["content"]["goal"] == c.goal for x in out):
                continue
            cands, _ = candidates(self.pool, view, spec, disliked=self.store.disliked(h), now=now, store=self.store,
                                  exclude_kinds=ex_kinds, exclude_platforms=ex_platforms)
            hits = sum(1 for it in cands if any(contains_word(it.caption, w) for w in words))
            if hits >= config.FIRST_REQUEST_MIN:
                out.append({"text": text, "spec": spec.stored(), "hits": hits})
        return out

    def _onboard_choice(self, person, st, text, now):
        """'2' runs the second request now; 'every morning' previews the first as a morning rule (its YES also starts
        the export reminders that were offered). Anything else goes the normal way."""
        h = person["handle"]
        reqs = st.get("requests") or []
        m = T.ONBOARD_PICK.match(text)
        if (m or T.ONBOARD_REPEAT.match(text)) and reqs:
            over = self._over_cap(person)
            if over:   # no paid call over the cap
                self.note(intent="over_cap")
                return self._limit_notice(person, over) or ""
        if m and reqs:
            n = int(m.group(1)) if m.group(1) else {"first": 1, "second": 2, "third": 3}[m.group(2).lower()]
            if not 1 <= n <= len(reqs):
                return self.send(h, T.which_pick(len(reqs)))
            r = reqs[n - 1]
            self.note(intent="ask")
            self._set_onboard(h, "done", now)   # finding 34: the offer is used, so it is closed
            spec = RuleSpec.model_validate(r["spec"])
            # review fix PRIV-7: the request was written by the setup's model, so the outside search gets only what
            # the person typed ("1"), which holds no search words
            msg, run_id, _ = self.run(person, spec, "ask", request_text=r["text"], own_words=text)
            return self.deliver(person, spec, msg, run_id, kind="ask", request_text=r["text"])
        if T.ONBOARD_REPEAT.match(text) and reqs:
            self._set_onboard(h, "done", now)
            return self._onboard_rule(person, reqs[0], now, own=text)
        return None

    def _onboard_rule(self, person, req, now, own=""):
        h = person["handle"]
        self.note(intent="new_rule")
        stored = dict(req["spec"])
        stored["content"] = dict(stored["content"], count=1)
        stored["when"] = {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
                          "times": ["08:00"]}
        spec = RuleSpec.model_validate(stored)
        text = " ".join(str(own or "every morning").split())[:300]   # the person's own words, never the setup's (PRIV-7)
        pending = self.store.pending(h)
        more = []
        if pending and pending["kind"] == "confirm_rule" and str(pending["payload"].get("text", "")).startswith(
                "export reminders"):   # the reminders offered in step 4 start with the same YES
            more = [{"text": pending["payload"]["text"], "spec": pending["payload"]["spec"]}] + \
                (pending["payload"].get("more") or [])
        msg, run_id, n = self.run(person, spec, "preview", request_text=req["text"], own_words=text)
        if self._run_failed(run_id):
            return self.send(h, msg, run_id)
        self.store.set_pending(h, "confirm_rule", {"text": text, "spec": spec.stored(), "run_id": run_id,
                                                   "more": more}, at=self.clock())
        first = next_run(spec.when, person["timezone"], now, anchor=now, quiet=self.store.quiet(h))
        tail = T.preview_tail(describe(spec.when), T.picks_for(1, spec.content.goal),
                              say_time(first, now, person["timezone"]) if first else None)
        if more:
            tail += " " + T.export_more_note(len(more))
        return self.send(h, (T.PREVIEW_HEAD if n else "") + msg + tail, run_id)
