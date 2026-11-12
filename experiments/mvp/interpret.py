"""PROTOTYPE ONLY - one message in, one validated Interpretation out (interpret prompt v3, DESIGN.md sections 1, 2, 4,
5 and 11). The model fills the form; this code validates it, checks that the words of a reminder or a new to-do come
from the person's own message, retries once on an invalid form, and works out dates (relative times, defaults). The
person's message is passed as their request; nothing it says can call an action directly (AGENTS.md rule 6).

The call runs at temperature 0 with a fixed seed (the most deterministic settings the model accepts, measured in the
consistency note). The same text from the same person, with the same rules, to-dos, notes and open question, reuses the
same interpretation for 6 hours (section 4): `store` holds that cache.
"""
import difflib
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from . import config, llm
from .schema import Interpretation, RuleSpec, list_name
from .schedule import complete, describe, resolve_relative, say_time

PROMPT = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_INTERPRET}.md"), encoding="utf-8").read()
CALENDAR_DAYS = 12
WORD = re.compile(r"[^\W_]+", re.UNICODE)
# words a reminder may add to the person's own ("remind me to call my mum" -> "call your mum")
FILLER = set("you your yours yourself the a an to and of for at on in it is".split())


# ---------- the context the model sees ----------
def _day(d):
    return d.strftime("%a %-d %b")


def _context(person, rules, pending, last, now, todos=(), last_write=None, about=()):
    tz = ZoneInfo(person["timezone"])
    local = now.astimezone(tz)
    lines = [f"Now: {local.strftime('%A %Y-%m-%d %H:%M')} local time ({person['timezone']})."]
    days = [local.date() + timedelta(days=i) for i in range(1, CALENDAR_DAYS + 1)]
    lines.append("Calendar: " + ", ".join(f"{d.strftime('%a')} {d.isoformat()}" for d in days) + ".")
    if about:
        lines.append("About them (their own words and what the bot knows; use it to fill criteria and avoid):")
        lines.extend(f"  - {a}" for a in about)
    if rules:
        lines.append("Their rules, as numbered to them:")
        for i, r in enumerate(rules, 1):
            spec = RuleSpec.model_validate(r["spec"])
            extra = []
            if r.get("created_at"):
                extra.append("made " + _day(datetime.fromisoformat(r["created_at"]).astimezone(tz)))
            if r.get("last_run_at"):
                extra.append("last sent " + say_time(datetime.fromisoformat(r["last_run_at"]), now, person["timezone"]))
            lines.append(f"  {i}. {spec.content.goal} - {describe(spec.when)} ({r['status']}"
                         + (", " + ", ".join(extra) if extra else "") + f") spec={json.dumps(spec.stored())}")
    else:
        lines.append("They have no rules.")
    if todos:
        lines.append("Their open to-dos, numbered as shown to them:")
        for i, t in enumerate(todos, 1):
            due = ""
            if t.get("due_at"):
                due = ", due " + say_time(datetime.fromisoformat(t["due_at"]), now, person["timezone"])
            lines.append(f"  {i}. {t['text']} (list: {t.get('list') or 'todo'}{due})")
    else:
        lines.append("They have no open to-dos.")
    if last:
        n = len(last.get("items") or [])
        from_rule = next((i for i, r in enumerate(rules, 1) if r["id"] == last.get("rule_id")), None)
        when = ""
        if last.get("at"):
            when = " " + say_time(datetime.fromisoformat(last["at"]), now, person["timezone"]).replace("today at", "today,")
        how = f"sent by rule {from_rule}" if from_rule else "in reply to their ask" + (
            f" \"{last['request']}\"" if last.get("request") else "")
        lines.append(f"The bot's last answer:{when}, {how}: about \"{last['goal']}\", {n} "
                     f"{'pick' if n == 1 else 'picks'} numbered 1 to {n}.")
    else:
        lines.append("There is no last answer in the thread.")
    if last_write:
        lines.append(f"The bot's last change, {last_write['ago']} (it can be undone): {last_write['say']}.")
    if pending and pending["kind"] == "confirm_rule":
        lines.append("WAITING: the bot showed a preview of a NEW rule and asked them to reply YES to start it. A message "
                     "that changes it returns new_rule with the whole changed spec and edits_pending true. "
                     f"Their request was \"{pending['payload'].get('text', '')}\". Waiting spec="
                     f"{json.dumps(pending['payload']['spec'])}")
    elif pending and pending["kind"] == "clarify":
        p = pending["payload"]
        lines.append(f"WAITING: they asked \"{p.get('text', '')}\" and the bot asked one question: \"{p.get('question')}\". "
                     f"The half-built spec: {json.dumps(p.get('draft') or {})}. If the message answers the question, "
                     f"return intent {p.get('intent') or 'new_rule'} with the whole completed spec.")
    elif pending and pending["kind"] == "confirm_delete":
        lines.append("WAITING: the bot asked them to confirm deleting all their data.")
    return "\n".join(lines)


# ---------- code-side completion ----------
def finish(spec: RuleSpec, now, tzname):
    """Code-side completion of a spec. A period ('recently', since_days) stays relative: retrieve turns it into a date
    at each run, so a recurring rule's window moves with time. A relative time ('in two hours') becomes a date and a
    time here, from the moment the message arrived; 'every 3 weeks' or 'every 6 months' with no day gets today's."""
    complete(spec.when, now, tzname)
    return spec


def finish_all(it: Interpretation, now, tzname):
    if it.spec is not None:
        finish(it.spec, now, tzname)
    if it.when is not None:
        resolve_relative(it.when, now, tzname)
    if it.also is not None:
        finish_all(it.also, now, tzname)
    return it


def _drop_model_moment(raw):
    """A relative time is worked out by code: a date or clock time the model added beside in_minutes is dropped."""
    if not isinstance(raw, dict):
        return raw
    for w in [((raw.get("spec") or {}) if isinstance(raw.get("spec"), dict) else {}).get("when"), raw.get("when")]:
        if isinstance(w, dict) and w.get("in_minutes"):
            for k in ("date", "time", "times"):
                w.pop(k, None)
    if isinstance(raw.get("also"), dict):
        _drop_model_moment(raw["also"])
    return raw


def _stems(text):
    from .retrieve import _stem
    return [_stem(w) for w in WORD.findall((text or "").lower())]


def own_words(text, message):
    """True when every word of `text` comes from the person's message (spelling fixes and 'my' to 'your' allowed)."""
    have = set(_stems(message))
    for w in _stems(text):
        if w in have or w in FILLER:
            continue
        if not difflib.get_close_matches(w, list(have), n=1, cutoff=0.75):
            return False
    return True


# a message that puts something from the last answer on a list says so; "what are the ingredients?" does not
ADDING = re.compile(r"\b(add|adding|put|list|lists|to-?dos?|jot|note|stick|throw|pop|save|keep|remember|track|buy|shop"
                    r"|shopping)\b", re.I)


def _adds_from_answer(x):
    return (x.intent == "todo_add" and bool(x.pick_number or x.what)) or \
        (x.intent == "act_on_last" and any(a.action == "todo.add" for a in x.actions))


def _grounding(it: Interpretation, message):
    """Problems with words shown back to the person as theirs, or with a write they did not ask for; or None."""
    for x in [it] + ([it.also] if it.also else []):
        if _adds_from_answer(x) and not ADDING.search(message):
            return "the message does not ask to add anything to a list; a question about the last answer is follow_up"
        if x.spec is not None and x.spec.content.source == "note" and not own_words(x.spec.content.text, message):
            return "content.text of a note must use only words from their message"
        if x.intent == "todo_add" and x.todo_text and not own_words(x.todo_text, message):
            return "todo_text must use only words from their message"
    return None


# ---------- the interpretation cache (section 4) ----------
# forms whose words come from the last answer ("is it spicy?" is asked about that dish): reused only for that answer
ABOUT_LAST = ("follow_up", "act_on_last")


# forms that never refer to the person's rules (fix pass, finding 20): an ask, a to-do, a reminder or a new rule is
# read the same whatever rules exist, so its cached reading is reused after a rule is added or changed
RULE_FREE = {"ask", "new_rule", "todo_add", "todo_list", "todo_done", "todo_remove", "todo_due", "profile_show",
             "profile_update", "set_email", "library_status", "library_stats", "help", "chat", "set_quiet_hours",
             "snooze", "set_timezone", "follow_up", "more", "feedback"}


def rule_free(it):
    return all(x.intent in RULE_FREE and not x.edits_pending and x.rule_number is None
               for x in [it] + ([it.also] if it.also else []))


def cache_key(text, person, rules, pending, now, todos=(), about=(), last_write=None, with_rules=True):
    local = now.astimezone(ZoneInfo(person["timezone"])).date().isoformat()
    parts = {
        "v": config.PROMPT_INTERPRET, "who": person["handle"], "text": " ".join(text.lower().split()), "day": local,
        "tz": person["timezone"],
        "rules": [[r["id"], r["status"], r["spec"]] for r in rules] if with_rules else "any",
        "pending": [pending["kind"], pending["payload"].get("spec"), pending["payload"].get("draft")] if pending else None,
        "todos": [[t.get("id"), t["text"], t.get("list"), t.get("due_at")] for t in todos],
        "about": list(about),
        "undoable": bool(last_write),   # "never mind" is an undo only while there is something to undo
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _still_good(it, cached_last, last, now, tzname):
    """A cached form is reused only if its moment has not passed ("at 6" asked again at 7pm is tomorrow's 6) and, for
    a form about the last answer, the last answer is still the same one."""
    from .schedule import next_run
    for x in [it] + ([it.also] if it.also else []):
        if x.intent in ABOUT_LAST and cached_last != (last or {}).get("run_id"):
            return False
        for w in ((x.spec.when if x.spec is not None else None), x.when):
            if w is not None and w.type == "once" and next_run(w, tzname, now) is None:
                return False
    return True


def _ttl():
    return timedelta(hours=config.INTERPRET_CACHE_HOURS)


def _cached(store, key, now):
    if store is None or not config.INTERPRET_CACHE_HOURS:
        return None
    row = store.one("SELECT raw, at FROM interp_cache WHERE key=?", (key,))
    if row and datetime.fromisoformat(row["at"]) > now - _ttl():
        return json.loads(row["raw"])
    return None


def _remember(store, key, handle, raw, now, last=None):
    if store is None or not config.INTERPRET_CACHE_HOURS:
        return
    from .store import now_iso
    store.x("INSERT OR REPLACE INTO interp_cache(key,handle,raw,at) VALUES(?,?,?,?)",
            (key, handle, json.dumps({"form": raw, "last": (last or {}).get("run_id")}), now_iso(now)))
    store.x("DELETE FROM interp_cache WHERE at<?", (now_iso(now - _ttl()),))


# ---------- code-side completion of a form ----------
SAVED_KINDS = ["save", "collection", "share_self", "playlist"]
WATCHED_KINDS = ["watch", "like", "playlist"]
NAMED_LIST = re.compile(r"\b(?:on|to|onto|in|into|from|off)\s+(?:my|the)\s+([^\W\d_][\w-]*(?:\s[^\W\d_][\w-]*)?)\s+list\b",
                        re.I)
INGREDIENTS = re.compile(r"\bingredients?\b", re.I)


def _fill_raw(raw):
    """Before validation: a library search with no search text searches for its goal."""
    if not isinstance(raw, dict):
        return raw
    spec = raw.get("spec") if isinstance(raw.get("spec"), dict) else raw
    c = spec.get("content") if isinstance(spec, dict) else None
    if isinstance(c, dict) and c.get("source", "library") == "library" and not c.get("searches") and c.get("goal"):
        c["searches"] = [str(c["goal"])[:120]]
    if isinstance(raw.get("also"), dict):
        _fill_raw(raw["also"])
    return raw


# words that only say "give me one" (fix pass, finding 2): a must-have made of these alone is not a must-have
FILLER_CRITERIA = set("""another more one ones next else different new newer something anything other others please pls
    again give me show send a an the some pick picks option options thing things try i want like this that these those
    just same kind sort""".split())
FINISHED_BY_TOPIC = {"food": "ends with a dish you can eat", "fitness": "a full routine from start to finish",
                     "making": "walks through one whole project from start to finish"}
_CRIT_TOPIC = [("food", re.compile(r"\b(dish|eat|meal|food|recipe)\b", re.I)),
               ("fitness", re.compile(r"\b(routine|workout|exercise)\b", re.I))]


def clean_criteria(criteria, *texts):
    """Must-haves as code keeps them: never only filler words ("another" is not a must-have), and a finished-result
    must-have worded for the request's own topic (finding 11: a workout's "full routine from start to finish" was
    used for Blender tutorials)."""
    from .compose import FINISHED
    from .extract import topic_kind
    kind = topic_kind(*texts)
    out = []
    for cr in criteria:
        words = WORD.findall(cr.lower())
        if not words or all(w in FILLER_CRITERIA for w in words):
            continue
        if FINISHED.search(cr) and kind in FINISHED_BY_TOPIC:
            own = next((k for k, rx in _CRIT_TOPIC if rx.search(cr)), "making")
            if own != kind:
                cr = FINISHED_BY_TOPIC[kind]
        if cr not in out:
            out.append(cr)
    return out


def _from_message(x: Interpretation, message):
    """Facts the message states in so many words, filled when the form left them out: the saved or watched kinds in
    full, a named list ("on my packing list"), and ingredients asked for by name. Must-haves are cleaned (above)."""
    if x.spec is not None:
        c = x.spec.content
        if c.kinds == ["save"]:
            c.kinds = list(SAVED_KINDS)
        elif c.kinds == ["watch"]:
            c.kinds = list(WATCHED_KINDS)
        if c.criteria:
            c.criteria = clean_criteria(c.criteria, c.goal or "", *c.searches, message)
    if x.criteria:
        x.criteria = clean_criteria(x.criteria)
    adds = x.intent in ("todo_add", "todo_list") or (x.intent == "act_on_last"
                                                     and any(a.action == "todo.add" for a in x.actions))
    if adds and not x.todo_list:
        m = NAMED_LIST.search(message)
        name = list_name(m.group(1)) if m else None
        if name and name != "todo":
            x.todo_list = name
    if x.intent == "act_on_last" and {a.action for a in x.actions} == {"todo.add"} and x.when is None \
            and INGREDIENTS.search(message):
        # "add its ingredients to my list" read as "add the pick": the ingredient lines are what they asked for
        given = x.actions[0].params.get("list")
        x.intent, x.what, x.actions = "todo_add", "ingredients", []
        x.todo_list = x.todo_list or (list_name(given) if given and list_name(given) != "todo" else None)
    if x.intent == "todo_add" and x.pick_number and x.what == "pick" and INGREDIENTS.search(message):
        x.what = "ingredients"


def _canonical_change(x: Interpretation, rules):
    """A change_rule that only adds a later start is a pause until then; one that only adds dates to leave out is a
    skip of those dates. One form for one meaning, so the rule keeps its own timing and the reply says the right thing."""
    if x.intent != "change_rule" or x.spec is None:
        return
    n = x.rule_number or (1 if len(rules) == 1 else None)
    if not n or not 1 <= n <= len(rules):
        return
    old, new = RuleSpec.model_validate(rules[n - 1]["spec"]).stored(), x.spec.stored()
    ow, nw = dict(old["when"]), dict(new["when"])
    added_start = nw.pop("start", None) if nw.get("start") != ow.get("start") else None
    ow.pop("start", None) if added_start else None
    added = sorted(set(nw.pop("except_dates", [])) - set(ow.pop("except_dates", [])))
    if ow != nw or old["content"] != new["content"] or old.get("do") != new.get("do"):
        return
    if added_start and not added:
        x.intent, x.spec, x.until, x.rule_number = "pause", None, added_start, n
    elif added and not added_start:
        first, last = date.fromisoformat(added[0]), date.fromisoformat(added[-1])
        if (last - first).days + 1 == len(added):   # one day, or a run of days
            x.intent, x.spec, x.date, x.rule_number = "skip", None, added[0], n
            x.until = added[-1] if len(added) > 1 else None


# a message that asks for a pick of the last answer ("remind me of the second one", "send me #2") or for the answer
# itself ("send me that tonight") to be sent again. The verb must come right before the pointer, so "remind me to
# watch the last video of the series" or "send me the first recipe I ever saved" stay what they are, and the pointer
# must end the phrase, so "send me this weekend's pasta" stays a search.
AGAIN = r"(?:remind me (?:of|about)|send(?: me)?|email(?: me)?|text me|resend|re-send|share)"
ORD = r"(first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)"
THEN = r"(?=\s*$|\s*[.,!?]|\s+(?:again|at|on|in|by|around|tonight|tomorrow|later|this\s+(?:morning|afternoon|evening)" \
       r"|next|before|after|to me|please)\b)"
PICK_REF = re.compile(r"\b" + AGAIN + r"\s+(?:the\s+)?" + ORD + r"\s+(?:one|pick|recipe|video|post|reel)" + THEN
                      + r"|\b" + AGAIN + r"\s+(?:#\s?|number\s+)([1-9])\b" + THEN, re.I)
THAT_REF = re.compile(r"^\W*(?:(?:please|pls|can you|could you)\s+)?" + AGAIN + r"\s+(?:it|that|this|these|those)"
                      r"(?:\s+(?:one|ones))?" + THEN, re.I)
ORDINAL = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5}


REMIND = re.compile(r"\bremind me (?:of|about)\b", re.I)
CALENDAR_WORD = re.compile(r"\bcalendar\b|\bcal\b", re.I)


def later_on_last(it: Interpretation, message, last, now=None, tzname=None):
    """Found live: "remind me of the second one tonight at 8" came back in a different form from run to run: a new
    library search at that time, a reminder whose text was "the second one", a to-do with a due time, or act_on_last
    with the time in its calendar params. A message that points at a pick of the last answer (or at the answer: "send
    me that tonight") plus a time always ends as act_on_last with that pick and that time, so the pick itself is sent
    and nothing is searched again (fix pass, finding 29)."""
    items = (last or {}).get("items") or []
    if not items:
        return it
    m = PICK_REF.search(message)
    n = None
    if m:
        word = (m.group(1) or "").lower()
        n = len(items) if word == "last" else ORDINAL.get(word) or int(m.group(2))
        if not 1 <= n <= len(items):
            return it
    elif not THAT_REF.search(message):
        return it
    remind = bool(REMIND.search(message))
    when, actions = None, None
    if it.intent == "new_rule" and it.spec is not None and it.spec.when.type == "once" \
            and it.spec.content.source in ("library", "note"):
        when, actions = it.spec.stored()["when"], [a.model_dump() for a in it.spec.do]
    elif it.intent == "todo_add" and (it.due or it.in_minutes) and remind and not it.todo_list:
        if it.in_minutes:
            when = {"type": "once", "in_minutes": it.in_minutes}
        elif len(it.due) > 10:
            when = {"type": "once", "date": it.due[:10], "time": it.due[11:16]}
        actions = [{"action": "message.send"}]
    elif it.intent == "act_on_last":
        when = it.when.model_dump(exclude_none=True) if it.when is not None else None
        actions = [a.model_dump() for a in it.actions]
        cal = next((a for a in it.actions if a.action == "calendar.add"), None)
        if when is None and remind and cal is not None and cal.params.get("time") and now is not None and tzname:
            day = cal.params.get("date") or now.astimezone(ZoneInfo(tzname)).date().isoformat()
            when = {"type": "once", "date": day, "time": cal.params["time"]}
        if when is None:
            if n and it.pick_number != n:   # "email me the second one": the pick the message names
                it.pick_number = n
            return it
    if when is None or actions is None:
        return it
    if remind:   # "remind me of" sends the pick here; a calendar entry only when they name the calendar
        actions = [a for a in actions if a.get("action") != "calendar.add" or CALENDAR_WORD.search(message)]
        if not any(a.get("action") in ("message.send", "email.send") for a in actions):
            actions.insert(0, {"action": "message.send"})
    out = Interpretation(intent="act_on_last", actions=actions, pick_number=n, when=when, answer_ref="last",
                         profile_note=it.profile_note, lang=it.lang)
    if out.when is not None and out.when.in_minutes and now is not None and tzname:
        resolve_relative(out.when, now, tzname)
    return out


def settle(raw, message, rules, now, tzname):
    """A raw form from the model (or the cache) to a validated, completed Interpretation. Raises ValidationError."""
    it = Interpretation.model_validate(_fill_raw(_drop_model_moment(raw)))
    for x in [it] + ([it.also] if it.also else []):
        _from_message(x, message)
        _canonical_change(x, rules)
    return finish_all(it, now, tzname)


# ---------- one message ----------
def interpret(text, person, rules, pending, last, now, todos=(), last_write=None, about=(), store=None):
    """Returns (Interpretation, cost_usd). With `store`, the same request reuses the same interpretation (6 hours)."""
    key = cache_key(text, person, rules, pending, now, todos, about, last_write)
    free_key = cache_key(text, person, rules, pending, now, todos, about, last_write, with_rules=False)
    for k, need_free in ((free_key, True), (key, False)):
        hit = _cached(store, k, now)
        if not isinstance(hit, dict):
            continue
        # rows written before the last answer was recorded beside the form hold the bare form
        raw, cached_last = (hit["form"], hit.get("last")) if "form" in hit and "intent" not in hit else (hit, None)
        try:
            it = later_on_last(settle(raw, text, rules, now, person["timezone"]), text, last, now, person["timezone"])
            if (rule_free(it) or not need_free) and _still_good(it, cached_last, last, now, person["timezone"]):
                return it, 0.0
        except ValidationError:
            pass   # a form that no longer validates (the rules changed under it) is asked for again
    user = _context(person, rules, pending, last, now, todos, last_write, about) + \
        "\n\nTheir message:\n" + text.strip()[:1000]
    cost = 0.0
    err = None
    for attempt in range(2):
        prompt = user if err is None else user + f"\n\nYour last form was invalid ({err}). Return a valid form."
        raw, c = llm.chat_json(PROMPT, prompt, purpose="mvp_interpret", prompt_version=config.PROMPT_INTERPRET,
                               person=person["handle"], max_tokens=900, temperature=config.INTERPRET_TEMPERATURE,
                               seed=config.INTERPRET_SEED)
        cost += c
        try:
            it = later_on_last(settle(raw, text, rules, now, person["timezone"]), text, last, now, person["timezone"])
            err = _grounding(it, text)
            if err and attempt == 0:
                continue
            if err:   # still not their words: their whole message is used instead, never words they did not write
                it = _use_message(it, text)
            else:
                _remember(store, free_key if rule_free(it) else key, person["handle"], raw, now, last)
            return it, cost
        except ValidationError as e:
            err = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:4])
    return Interpretation(intent="unsupported", reply="Sorry, I didn't catch that. Could you say it another way?"), cost


def _use_message(it, message):
    msg = " ".join(message.split())[:200]
    for x in [it] + ([it.also] if it.also else []):
        if x.intent == "act_on_last" and not ADDING.search(message) and \
                any(a.action != "todo.add" for a in x.actions):   # "email it": the email stays, the to-do goes
            x.actions = [a for a in x.actions if a.action != "todo.add"]
            continue
        if _adds_from_answer(x) and not ADDING.search(message):   # still a write they did not ask for: their question
            x.intent, x.question, x.what, x.actions, x.todo_text, x.todo_list = "follow_up", msg, None, [], None, None
            continue
        if x.spec is not None and x.spec.content.source == "note":
            x.spec.content.text = msg
        if x.intent == "todo_add" and x.todo_text:
            x.todo_text = msg
    return it
