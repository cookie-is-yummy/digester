"""PROTOTYPE ONLY - the executor: one run (retrieve, enrich, compose, extract, render, record) and the send (docs/06
'Executor', DESIGN.md sections 3, 4 and 11).

Only the bot sends (AGENTS.md rule 5): retrieve, compose and extract read. A reply is a list of parts (render.Reply):
a channel that shows link previews gets each part as its own message, others get the parts joined; every message a
reply went out as is recorded, so a reaction on any of them maps to the run. Mixed into core.Bot.
"""
import hashlib
import json
import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from . import config, llm
from .channels.base import SendUncertain
from .compose import compose
from .extract import details_many, kinds_for
from .render import Reply, joined, none_message, pick_parts, pick_record, picks_message
from .retrieve import candidates
from .schema import KINDS, PLATFORMS
from .schema import RuleSpec
from .store import now_iso
from . import texts as T
from .texts import LIMIT, LIMIT_TOTAL, LOADING, RUN_ERROR, SCHEDULED_FOOTER


class ExecutorMixin:
    def send(self, handle, text, run_id=None):
        """Sends a reply. A Reply goes out part by part on a channel that shows link previews (each link alone in its
        message, so the app can show it as a card); elsewhere it is one text. Returns the first message's reference."""
        if isinstance(text, Reply) and getattr(self.channel, "link_previews", False):
            first = None
            for i, part in enumerate(text.split()):
                try:
                    if part["type"] == "link":
                        ref = self.channel.send_link(handle, part)
                    else:
                        ref = self.channel.send(handle, part["text"])
                except Exception as e:  # noqa: BLE001
                    if i == 0:
                        raise
                    raise SendUncertain("partly sent") from e   # the first parts went out: never sent again
                self.store.record_sent(ref, handle, run_id, part=i)
                first = first or ref
            self.note(reply_ref=first)
            return first
        ref = self.channel.send(handle, joined(text))
        self.store.record_sent(ref, handle, run_id)
        self.note(reply_ref=ref)
        return ref

    # ---------- the person's context ----------
    def _profile_text(self, handle, *texts):
        """What the composer may use about the person (slice 6, profile.composer_context): their direction, their level
        at this request's topic when it may be used, their preferences and what they said about themselves. Returns
        (text, level_ok, guessed interest)."""
        from .profile import composer_context
        return composer_context(self.store, handle, *texts)

    def _level_note(self, h, result, guessed):
        """'I'm guessing you're new to Blender; tell me if that's wrong.': said once per topic, when an answer's reason
        leans on a level that is only a guess."""
        if not guessed or not result.get("level_used"):
            return
        seen = self.store.get_state(f"levelnote:{h}") or []
        if guessed["topic"].lower() in seen:
            return
        self.store.set_state(f"levelnote:{h}", seen + [guessed["topic"].lower()])
        result["level_note"] = T.level_guess_note(guessed["topic"], guessed["level"])

    def _exclusions(self, handle):
        prefs = self.store.person_context(handle).get("prefs") or {}
        kinds = [k for k in prefs.get("exclude_kinds") or [] if k in KINDS]
        platforms = [p for p in prefs.get("exclude_platforms") or [] if p in PLATFORMS]
        return kinds, platforms

    def _youtube(self):
        yt = getattr(self, "yt", None)
        if yt is None:
            from .ytinfo import YouTubeInfo
            yt = self.yt = YouTubeInfo(self.store)
        return yt

    # ---------- caps ----------
    def _over_cap(self, person):
        libs = [p["library"] for p in self.store.q("SELECT library FROM people")]
        if llm.spent_total(libs) >= config.TOTAL_CAP_USD:
            return "total"
        if llm.spent_today(person["handle"], person["library"]) >= config.DAILY_CAP_USD:
            return "daily"
        return None

    def _limit_notice(self, person, which="daily"):
        """The limit message, at most once a day per person; otherwise silence (no paid calls either way)."""
        day = self.clock().astimezone(ZoneInfo(person["timezone"])).date().isoformat()
        key = f"cap_notice:{person['handle']}"
        if self.store.get_state(key) == day:
            return None
        self.store.set_state(key, day)
        return self.send(person["handle"], LIMIT_TOTAL if which == "total" else LIMIT)

    # ---------- one run ----------
    def run(self, person, spec: RuleSpec, kind, rule_id=None, request_text=None, cands_override=None, known_lines=None,
            shown=(), only_ids=None):
        """kind: preview | scheduled | manual | ask | more | follow_up. Returns (message, run_id, n_picks). 'manual'
        is a rule run because the person asked for it now; 'more' repeats the last question without the picks already
        shown (`shown`). Deliveries are written here; a caller whose send fails removes them (unsend). `only_ids`
        limits the library's candidates to those items (a new_items rule after an import).
        A library request with outside "some" gets the outside block after its picks; "only" shows just that block
        (outside.py). The block is never kept with the answer, never a delivery and never counted in n_picks."""
        c = spec.content
        outside = c.source == "library" and cands_override is None and kind != "follow_up"
        if outside and c.outside == "only":
            return self._run_outside_only(person, spec, kind, rule_id, request_text)
        msg, run_id, n = self._run_once(person, spec, kind, rule_id=rule_id, request_text=request_text,
                                        cands_override=cands_override, known_lines=known_lines, shown=shown,
                                        only_ids=only_ids)
        if outside and c.outside == "some" and not self._run_failed(run_id):
            msg = self._add_outside(person, spec, kind, rule_id, request_text, msg, run_id)
        return msg, run_id, n

    def _run_once(self, person, spec: RuleSpec, kind, rule_id=None, request_text=None, cands_override=None,
                  known_lines=None, shown=(), only_ids=None):
        if spec.content.source in ("note", "todos"):
            return self._run_plain(person, spec, kind, rule_id)
        if spec.content.source == "items" and kind in ("scheduled", "manual"):
            return self._run_items(person, spec, kind, rule_id)
        t0 = time.time()
        cost = 0.0
        status, err, result, cands, view = "ok", None, None, [], None
        steps = {}
        disliked = self.store.disliked(person["handle"])
        try:
            view = self.view(person["library"])
            ready = getattr(self.pool, "is_ready", None)
            if cands_override is None and kind != "scheduled" and ready and not ready(person["library"]):
                self.send(person["handle"], LOADING)  # the first search after a start can take a minute
            h = person["handle"]
            now = self.clock()
            sent_before = self.store.delivered(rule_id) if rule_id else set()
            if cands_override is not None:
                cands = [c for c in cands_override if c.id not in disliked]  # rule 9 holds for follow-ups too
            else:
                exclude = sent_before if spec.content.exclude_sent else set()
                exclude |= set(shown)
                weights = self._feedback_weights(rule_id, view)
                ex_kinds, ex_platforms = self._exclusions(h)
                seed = f"{rule_id or h}:{now.date().isoformat()}"   # order "random": one draw per run, repeatable
                cands, meta = candidates(self.pool, view, spec, exclude=exclude, disliked=disliked,
                                         creator_weights=weights, now=now, store=self.store, exclude_kinds=ex_kinds,
                                         exclude_platforms=ex_platforms, seed=seed, only=only_ids)
                cost += meta.get("cost_usd", 0.0)
            steps["search"] = round(time.time() - t0, 2)
            t1 = time.time()
            extra = self._youtube().details(cands, now=now) if any(c.platform == "youtube" for c in cands) else {}
            steps["youtube"] = round(time.time() - t1, 2)
            t1 = time.time()
            about, level_ok, guessed = self._profile_text(h, spec.content.goal, request_text or "",
                                                          *spec.content.searches)
            result, c = compose(cands, spec, h, request_text=request_text,
                                feedback_note=self._feedback_note(rule_id, view), known_lines=known_lines,
                                extra=extra, profile=about, lang=getattr(self._tl, "lang", None),
                                store=self.store, use_cache=(kind != "more"), sent_count=len(sent_before),
                                wider=(kind == "ask"), now=now, level_ok=level_ok)
            cost += c
            if result.get("picks") and kind != "follow_up":
                self._level_note(h, result, guessed)
            steps["compose"], steps["answer_cached"] = round(time.time() - t1, 2), result.get("cached", False)
            t1 = time.time()
            main = result.get("picks") or []
            if main and kinds_for(spec.content.extract):
                facts, info = details_many([p["item"] for p in main], spec.content.extract, view.lib, store=self.store,
                                           person=h, extra=extra, now=now)
                cost += info["cost"]
                result["dropped"]["lines_not_in_text"] = info["dropped"]
                for p in main:
                    p["facts"] = facts.get(p["item"].id) or {}
                    found = [line for k in ("ingredients", "steps", "key_points") for line in p["facts"].get(k) or []]
                    if found or not p.get("lines_reused"):
                        p["lines"], p["lines_reused"] = found, False
                steps["extract"], steps["extract_calls"] = round(time.time() - t1, 2), info["calls"]
                if info.get("errors"):   # a failed details call: the answer goes out without those details
                    steps["extract_errors"] = info["errors"]
        except Exception as e:  # noqa: BLE001 - one failed run never stops the bot
            status, err = "error", type(e).__name__ + (": " + str(e)[:120] if isinstance(e, RuntimeError) else "")
        picks = ((result or {}).get("picks") or []) + ((result or {}).get("wider") or [])
        run_id = self.store.add_run(handle=person["handle"], rule_id=rule_id, kind=kind, at=now_iso(self.clock()),
                                    n_candidates=len(cands), n_picks=len(picks),
                                    # what the checks removed (picks, lines, titles); a replaced "because" is not
                                    n_dropped=sum(v for k, v in ((result or {}).get("dropped") or {}).items()
                                                  if not k.startswith("because_")),
                                    fits=[p["verdict"] for p in picks], cost_usd=round(cost, 6),
                                    status=status if status == "error" else ("picked" if picks else "none"),
                                    error=err, prompt_version=config.PROMPT_COMPOSE, seconds=round(time.time() - t0, 2),
                                    lang=getattr(self._tl, "lang", None),
                                    dropped={k: v for k, v in ((result or {}).get("dropped") or {}).items() if v},
                                    steps=steps)
        self.note(run_id=run_id)
        if status == "error":
            return RUN_ERROR, run_id, 0
        for i, p in enumerate(picks, 1):
            self.store.add_delivery(person["handle"], rule_id if kind in ("scheduled", "manual") else None, run_id,
                                    p["item"].id, i, at=self.clock())
        if picks:
            self.store.set_last_answer(person["handle"], run_id, rule_id, [p["item"].id for p in picks], spec.content.goal)
            lines = {p["item"].id: p["lines"] for p in picks}
            # what each item's lines are (the kinds that were found), so a to-do of its ingredients is made only
            # from lines that are ingredients alone
            kinds = {p["item"].id: ([k for k in ("ingredients", "steps", "key_points") if (p.get("facts") or {}).get(k)]
                                    if p["lines"] and not p.get("lines_reused") else None) for p in picks}
            facts = {p["item"].id: p.get("facts") or {} for p in picks}
            if kind == "follow_up":  # a follow-up without details must not erase the details found before
                old = self.store.get_state(f"lines:{person['handle']}", {}) or {}
                old_kinds = self.store.get_state(f"linekinds:{person['handle']}", {}) or {}
                old_facts = self.store.get_state(f"facts:{person['handle']}", {}) or {}
                for p in picks:
                    if not p["lines"] or p.get("lines_reused"):   # the lines found before: they keep what they were
                        kinds[p["item"].id] = old_kinds.get(p["item"].id)
                        facts[p["item"].id] = old_facts.get(p["item"].id) or {}
                lines = {iid: (ls or old.get(iid) or []) for iid, ls in lines.items()}
            self.store.set_state(f"lines:{person['handle']}", lines)
            self.store.set_state(f"linekinds:{person['handle']}", kinds)
            self.store.set_state(f"facts:{person['handle']}", facts)
            if kind != "follow_up":  # what "another" repeats: this request, without what has been shown
                self.store.set_state(f"lastspec:{person['handle']}", {
                    "spec": spec.stored(), "rule_id": rule_id if kind in ("scheduled", "manual") else None,
                    "text": (request_text or "")[:300], "shown": list(shown) + [p["item"].id for p in picks]})
            footer = None
            if kind == "scheduled":
                number = next((i for i, r in enumerate(self.store.rules(person["handle"]), 1) if r["id"] == rule_id), 1)
                footer = SCHEDULED_FOOTER.format(n=number)
            msg = picks_message(result, spec, footer=footer, now=self.clock())
            # what this run showed, kept for its outputs (email, calendar, to-dos) and for sending it again later:
            # the same parts without the chat footer, and each pick's checked title, link and details
            main = {id(p) for p in result["picks"]}
            self._keep_answer(run_id, person["handle"], rule_id if kind in ("scheduled", "manual") else None,
                              spec.content.goal, "picks", picks_message(result, spec, now=self.clock()) if footer else msg,
                              [dict(pick_record(p), main=id(p) in main) for p in picks])
            return msg, run_id, len(picks)
        return none_message(result, spec, scheduled=(kind == "scheduled")), run_id, 0

    # ---------- outside picks (outside.py, DESIGN.md section 11) ----------
    def _outside(self):
        o = getattr(self, "outside", None)
        if o is None:
            from .outside import Outside
            o = self.outside = Outside(self.store)
        return o

    def _outside_find(self, person, spec, kind, rule_id, request_text):
        """The outside block for this run: the person's own words are the request (and, for a rule, its stored
        request text); videos already in their library are removed; a rule or "another" does not show a video it
        showed in the last 30 days. Returns the result of Outside.find."""
        from . import outside as O
        h = person["handle"]
        texts = [request_text or ""]
        if rule_id:
            r = self.store.rule(rule_id)
            if r and r.get("text") and r["text"] != request_text:
                texts.append(r["text"])
        view = self.view(person["library"])
        have = {it.video_id for it in view.items.values() if it.platform == "youtube" and it.video_id}
        q = O.search_text(spec, texts)
        scope = f"rule:{rule_id}" if rule_id else ("q:" + hashlib.sha1(q.lower().encode()).hexdigest()[:12] if q else None)
        now = self.clock()
        shown = self.store.get_state(f"outside_shown:{h}", {}) or {}
        cutoff = now_iso(now - timedelta(days=config.OUTSIDE_SHOWN_DAYS))
        shown = {k: {v: at for v, at in vids.items() if at >= cutoff} for k, vids in shown.items()}
        skip = set(shown.get(scope, {})) if scope and kind in ("scheduled", "manual", "more") else set()
        res = self._outside().find(h, spec, texts, have_ids=have, now=now, skip_ids=skip)
        if scope and res["picks"]:
            box = shown.setdefault(scope, {})
            for p in res["picks"]:
                box[p["video_id"]] = now_iso(now)
        self.store.set_state(f"outside_shown:{h}", {k: v for k, v in shown.items() if v})
        return res

    @staticmethod
    def _outside_parts(picks, before=None):
        """The block: its label, then per video one line (YouTube's title and channel, its length) and its link alone,
        marked as an outside pick so the test page labels the card. After `before` (the library answer), with a blank
        line between them when they are joined into one text."""
        from .outside import watch_url
        head = Reply.of(before) + ("\n\n" + T.OUTSIDE_HEAD) if before is not None else \
            Reply([{"type": "text", "text": T.OUTSIDE_HEAD}])
        parts = list(head.parts)
        for p in picks:
            parts.append({"type": "text", "text": T.outside_line(p)})
            parts.append({"type": "link", "url": watch_url(p["video_id"]), "title": p["title"], "platform": "youtube",
                          "video_id": p["video_id"], "outside": True})
        return Reply(parts)

    def _note_outside(self, run_id, res):
        row = self.store.one("SELECT steps FROM runs WHERE id=?", (run_id,))
        steps = json.loads(row["steps"]) if row and row.get("steps") else {}
        steps["outside"] = {"status": res["status"], "shown": len(res["picks"]), "searched": res["searched"],
                            "cached": res["cached"]}
        self.store.x("UPDATE runs SET steps=? WHERE id=?", (json.dumps(steps), run_id))

    def _add_outside(self, person, spec, kind, rule_id, request_text, msg, run_id):
        """The library answer, then the outside block or one line saying why there is none."""
        try:
            res = self._outside_find(person, spec, kind, rule_id, request_text)
        except Exception as e:  # noqa: BLE001 - the library answer is never lost to this block
            res = {"picks": [], "status": "error:" + type(e).__name__, "line": T.OUTSIDE_ERROR, "searched": False,
                   "cached": False}
        self._note_outside(run_id, res)
        if res["picks"]:
            # kept aside too: when the answer itself goes only by email, deliver() still puts this block in the thread
            self._tl.outside_block = (run_id, self._outside_parts(res["picks"]))
            return self._outside_parts(res["picks"], before=msg)
        if res["line"]:
            return msg + "\n\n" + res["line"]
        return msg

    def _run_outside_only(self, person, spec, kind, rule_id, request_text):
        """outside "only": just the outside block (or the one line saying why there is none). No library search and
        no model call; nothing is recorded as a delivery or as the last answer, so feedback never lands on it."""
        h = person["handle"]
        t0 = time.time()
        try:
            res = self._outside_find(person, spec, kind, rule_id, request_text)
        except Exception as e:  # noqa: BLE001
            res = {"picks": [], "status": "error:" + type(e).__name__, "line": T.OUTSIDE_ERROR, "searched": False,
                   "cached": False}
        n = len(res["picks"])
        run_id = self.store.add_run(handle=h, rule_id=rule_id, kind=kind, at=now_iso(self.clock()), n_candidates=0,
                                    n_picks=0, n_dropped=0, cost_usd=0.0, status="picked" if n else "none",
                                    prompt_version=None, seconds=round(time.time() - t0, 2),
                                    lang=getattr(self._tl, "lang", None))
        self._note_outside(run_id, res)
        self.note(run_id=run_id)
        if kind != "follow_up":   # "another" repeats this request, without the videos it showed
            self.store.set_state(f"lastspec:{h}", {"spec": spec.stored(),
                                                   "rule_id": rule_id if kind in ("scheduled", "manual") else None,
                                                   "text": (request_text or "")[:300], "shown": []})
        if n:
            msg = self._outside_parts(res["picks"])
            undone = [a.action for a in spec.do if a.action != "message.send"]
            if undone:   # finds from YouTube are never kept, so no email, calendar or list entry is made: say so
                msg = msg + ("\n\n" + T.outside_only_no_actions(undone))
            if kind == "scheduled":
                number = next((i for i, r in enumerate(self.store.rules(h), 1) if r["id"] == rule_id), 1)
                msg = msg + ("\n\n" + T.REMINDER_FOOTER.format(n=number))
            return msg, run_id, n
        line = res["line"] or T.OUTSIDE_NONE
        if res["status"] in ("sensitive", "off", "instagram_only", "limit_all", "limit_person", "error"):
            line += T.OUTSIDE_ONLY_TAIL
        return line, run_id, 0

    def _run_plain(self, person, spec, kind, rule_id):
        """A reminder in the person's own words, or their open to-dos: no search and no model call."""
        h = person["handle"]
        if spec.content.source == "note":
            msg, n = T.reminder(spec.content.text), 1
        else:
            msg, n = self._todos_text(h)
        run_id = self.store.add_run(handle=h, rule_id=rule_id, kind=kind, at=now_iso(self.clock()), n_candidates=0,
                                    n_picks=n, n_dropped=0, cost_usd=0.0, status="picked" if n else "none",
                                    prompt_version=None, seconds=0.0)
        self.note(run_id=run_id)
        if n:   # kept for the rule's outputs ("email me my list every morning")
            self._keep_answer(run_id, h, rule_id, spec.content.goal, spec.content.source, msg)
        if kind == "scheduled" and spec.when.repeating:
            number = next((i for i, r in enumerate(self.store.rules(h), 1) if r["id"] == rule_id), 1)
            msg += "\n" + T.REMINDER_FOOTER.format(n=number)
        return msg, run_id, n

    def _run_items(self, person, spec, kind, rule_id):
        """An earlier answer sent again ("remind me of the 2nd one at 6"): the picks as they were kept, with their
        checked titles and details, and no new search or model call. An item no longer in the library is left out."""
        h = person["handle"]
        view = self.view(person["library"])
        kept = {}
        for row in self.store.q("SELECT picks FROM answers WHERE handle=? ORDER BY run_id DESC LIMIT 200", (h,)):
            for p in json.loads(row["picks"] or "[]"):
                kept.setdefault(p["item_id"], p)
        from .compose import title_from_item
        recs = []
        disliked = self.store.disliked(h)
        for iid in spec.content.item_ids:
            it = view.get(iid)
            if it is None or iid in disliked:
                continue
            rec = dict(kept.get(iid) or {"item_id": iid, "title": title_from_item(it), "url": it.url,
                                         "platform": it.platform, "video_id": it.video_id, "creator": it.creator,
                                         "facts": {}, "lines": [], "line_kinds": None})
            rec["main"] = True
            recs.append(rec)
        parts = [{"type": "text", "text": T.SENT_AGAIN_HEAD}] if recs else []
        for i, rec in enumerate(recs):
            parts += pick_parts(rec, lead="\n" if i else "")
        run_id = self.store.add_run(handle=h, rule_id=rule_id, kind=kind, at=now_iso(self.clock()),
                                    n_candidates=len(spec.content.item_ids), n_picks=len(recs), n_dropped=0,
                                    cost_usd=0.0, status="picked" if recs else "none", prompt_version=None, seconds=0.0)
        self.note(run_id=run_id)
        if not recs:
            return T.ITEMS_GONE, run_id, 0
        for i, rec in enumerate(recs, 1):
            self.store.add_delivery(h, rule_id, run_id, rec["item_id"], i, at=self.clock())
        self.store.set_last_answer(h, run_id, rule_id, [r["item_id"] for r in recs], spec.content.goal)
        self.store.set_state(f"lines:{h}", {r["item_id"]: r.get("lines") or [] for r in recs})
        self.store.set_state(f"linekinds:{h}", {r["item_id"]: r.get("line_kinds") for r in recs})
        self.store.set_state(f"facts:{h}", {r["item_id"]: r.get("facts") or {} for r in recs})
        msg = Reply(parts)
        self._keep_answer(run_id, h, rule_id, spec.content.goal, "picks", msg, recs)
        return msg, run_id, len(recs)

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
