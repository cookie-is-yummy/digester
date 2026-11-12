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
from .schema import Interpretation, RuleSpec, When, list_name
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
# read the same whatever rules exist, so its cached reading is reused after a rule is added or changed. Nor does such a
# form depend on whether there is a write to undo (checker: starting a rule made one, so the same ask was read again);
# "chat" is left out, since "never mind" is chat with nothing to undo and an undo with something to undo
RULE_FREE = {"ask", "new_rule", "todo_add", "todo_list", "todo_done", "todo_remove", "todo_due", "profile_show",
             "profile_update", "set_email", "library_status", "library_stats", "help", "set_quiet_hours",
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
        "undoable": bool(last_write) if with_rules else "any",   # "never mind" is an undo only while there is
    }                                                                 # something to undo (never a rule-free form)
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
    """Before validation: a library search with no search text searches for its goal; a schedule given a window and
    a clock time beside it keeps the window ("every evening some time between 6 and 8" came back with both, was refused
    twice and read as unsupported: improvement round)."""
    if not isinstance(raw, dict):
        return raw
    spec_ = raw.get("spec") if isinstance(raw.get("spec"), dict) else raw
    w = spec_.get("when") if isinstance(spec_, dict) else None
    if isinstance(w, dict) and w.get("type") == "schedule" and w.get("window") and (w.get("times") or w.get("time")):
        spec_["when"] = {k: v for k, v in w.items() if k not in ("times", "time")}
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
# fix pass 2, finding 49: words about when or how often ("daily", "every day", "to start doing") are timing, and
# "mini" / "short" / "quick" is the length bound of finding 18 (worked out by code from the request): a must-have
# made only of these and filler is dropped
TIMING_CRITERIA = set("""daily every day days each weekly week weeks monthly month nightly night nights tonight today
    tomorrow morning mornings evening evenings afternoon weekday weekdays weekend weekends regularly often routine
    start starting doing do to begin practise practice practising practicing habit times time once twice""".split())
LENGTH_CRITERIA = set("""mini short shorter quick quicker tiny small bite bitesized bite-sized sized brief little length
    long minutes minute video videos tutorial tutorials clip clips""".split())
def timing_only(cr):
    """A must-have made only of words about when or how often (and filler)."""
    words = WORD.findall(cr.lower())
    return bool(words) and all(w in FILLER_CRITERIA or w in TIMING_CRITERIA for w in words) \
        and any(w in TIMING_CRITERIA for w in words)


def length_only(cr):
    """A must-have made only of a length word ("mini", "shorter", "short videos"): the length bound of finding 18
    covers it (worked out by code and checked against YouTube's length), so the composer is not asked it."""
    words = WORD.findall(cr.lower())
    return bool(words) and all(w in FILLER_CRITERIA or w in LENGTH_CRITERIA or w in TIMING_CRITERIA for w in words) \
        and any(w in LENGTH_CRITERIA - {"video", "videos", "tutorial", "tutorials", "clip", "clips"} for w in words)


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
        if timing_only(cr):
            continue   # finding 49: "daily", "every day", "to start doing" are timing, never must-haves
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


FIND_THEN = re.compile(r"^\W*(?:(?:can|could|would)\s+you\s+|please\s+|pls\s+)?(?:find|pick|choose|get|look\s+up|"
                       r"search\s+for|dig\s+up|grab)\s+(?:me\s+)?(?P<what>.+?)\s*,?\s+(?:and|then|&)\s+"
                       r"(?:(?:please|pls)\s+)?(?:email|e-mail|mail|put|add|send|save|text)\b", re.I)
ARTICLE = re.compile(r"^(?:a|an|one|some|the)\s+|\s+for\s+me$", re.I)


def new_find(it: Interpretation, message, last):
    """'Pick a blender project for me and email it to me' asks for something NEW, then sends it on: an ask with that
    action in do. Read as act_on_last, it would have emailed the answer shown before, about something else. Only when
    the thing asked for shares no topic word with the last answer."""
    if it.intent != "act_on_last" or it.when is not None or not it.actions:
        return it
    m = FIND_THEN.match(message)
    if not m:
        return it
    what = m.group("what").strip()
    said = _topic_stems(what)
    if not said or len(what) > 120:
        return it
    before = _topic_stems((last or {}).get("goal") or "", (last or {}).get("request") or "")
    if said & before:
        return it
    goal = ARTICLE.sub("", ARTICLE.sub("", what)).strip() or what
    count = 1 if re.match(r"^(?:a|an|one)\s", what, re.I) else 3
    q = QUANTITY.match(what)
    if q and q.group(1).lower() not in ("some",):
        w = " ".join(q.group(1).lower().split())
        count = int(w) if w.isdigit() else NUMBER_WORDS.get(w, count)
        goal = what[q.end():].strip() or goal
    do = ["message.send"] + [a.model_dump() for a in it.actions if a.action != "message.send"]
    try:
        out = Interpretation.model_validate({
            "intent": "ask", "spec": {"when": {"type": "now"}, "content": {
                "source": "library", "goal": goal[:200], "searches": [goal[:120]], "count": max(1, min(count, 10))},
                "do": do}, "profile_note": it.profile_note, "lang": it.lang})
    except ValidationError:
        return it
    out.also = it.also
    return out


def _plain_todo(x):
    return isinstance(x, dict) and x.get("intent") == "todo_add" and bool(x.get("todo_text")) \
        and not x.get("pick_number") and x.get("what") in (None, "pick")


def _todo_key(x):
    return (x.get("list") or x.get("todo_list"), x.get("due"), x.get("in_minutes"))


def merge_todo_adds(raw):
    """Found live (checker): "add bread, rice and lemons to groceries" came back as one todo_add per item, chained
    through `also` three deep; the form keeps one `also` and drops a chain, so the third item was lost without a word.
    Plain todo_adds in a row for the same list and time are one to-do text here (on the raw form, before the chain is
    cut), and code then splits it (todos.split_todo)."""
    if not isinstance(raw, dict):
        return raw
    while _plain_todo(raw) and _plain_todo(raw.get("also")) and _todo_key(raw) == _todo_key(raw["also"]):
        nxt = raw["also"]
        raw = dict(raw, todo_text=f"{raw['todo_text']}, {nxt['todo_text']}"[:200])
        if nxt.get("also") is not None:
            raw["also"] = nxt["also"]
        else:
            raw.pop("also", None)
    if isinstance(raw.get("also"), dict):
        raw = dict(raw, also=merge_todo_adds(raw["also"]))
    return raw


# ---------- improvement round: completions for kinds of misreading the evaluator reported ----------
# Each one fills or corrects a form from what the message says in so many words, or from the person's own rules and
# to-dos. None of them invents a time, a text or a number the person did not give.
STOP_TOPIC = set("""a an the my me i to for of and or on in at with from by your this that these those one ones it its
    some any next last first second third two three four five few couple times time today tomorrow tonight morning
    mornings evening evenings night nights week weeks weekend weekends day days daily now please pls send sending skip
    pause stop resume no not don dont do want get give again more new monday tuesday wednesday thursday friday saturday
    sunday mondays tuesdays wednesdays thursdays fridays saturdays sundays recipe recipes idea ideas video videos
    reminder reminders rule rules thing things stuff""".split())
ALL_WORDS = re.compile(r"\b(?:everything|all\s+(?:of\s+)?(?:them|my|the|it|rules|reminders|messages|texts|sends)"
                       r"|(?:pause|stop|resume|restart|unpause)\s+all\b|both|every\s+(?:rule|reminder)"
                       r"|any(?:thing|\s+(?:more\s+)?(?:messages|texts|reminders)))\b", re.I)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "couple": 2, "a couple": 2, "couple of": 2, "a couple of": 2, "few": 3, "a few": 3}
NEXT_N = re.compile(r"\bnext\s+(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|couple(?:\s+of)?|few)\s+"
                    r"(?!days?\b|weeks?\b|months?\b|hours?\b|minutes?\b)([a-z]+)", re.I)


def _topic_stems(*texts):
    return {s for s in _stems(" ".join(t or "" for t in texts)) if s not in STOP_TOPIC and len(s) > 2}


def _rule_by_topic(message, rules):
    """The one rule whose topic the message names ("no workouts" is the workout rule), or None."""
    said = _topic_stems(message)
    if not said:
        return None
    hits = []
    for i, r in enumerate(rules, 1):
        c = RuleSpec.model_validate(r["spec"]).content
        own = _topic_stems(c.goal or "", *c.searches)
        n = sum(1 for s in said if s in own or difflib.get_close_matches(s, list(own), n=1, cutoff=0.85))
        hits.append((n, i))
    hits.sort(reverse=True)
    if hits and hits[0][0] > 0 and (len(hits) == 1 or hits[0][0] > hits[1][0]):
        return hits[0][1]
    return None


def _target(x: Interpretation, message, rules):
    """A command about rules always has a target: 'all_rules' when they say everything (or, for a resume, name no
    rule), else the rule whose topic they name. A skip of "the next two" counts two sends."""
    if x.intent not in ("pause", "resume", "stop", "skip", "run_rule", "change_rule"):
        return
    if x.rule_number is not None and not 1 <= x.rule_number <= len(rules):
        x.rule_number = None
    if x.all_rules and x.rule_number is not None:   # both: the words decide
        if ALL_WORDS.search(message):
            x.rule_number = None
        else:
            x.all_rules = False
    if x.rule_number is None and not x.all_rules:
        n = _rule_by_topic(message, rules) if rules else None
        if n is not None:
            x.rule_number = n
        elif x.intent in ("pause", "resume", "stop") and (ALL_WORDS.search(message) or x.intent == "resume"):
            x.all_rules = True   # "text me again" names no rule: every paused rule (the handler asks when none fit)
    if x.intent == "skip" and not x.date:
        m = NEXT_N.search(message)
        if m:
            w = m.group(1).lower()
            n = int(w) if w.isdigit() else NUMBER_WORDS.get(w)
            if n and 1 <= n <= 20:
                x.count = n


TWICE = re.compile(r"\b(?:twice|2\s*x|2\s*times|two\s+times)\s*(?:a|per|each|every)?\s*day\b|\b(?:twice|2\s*x)\s+daily\b",
                   re.I)
THRICE = re.compile(r"\b(?:three\s+times|3\s*x|3\s*times|thrice)\s*(?:a|per|each|every)?\s*day\b|\b3\s*x\s+daily\b", re.I)
FOUR = re.compile(r"\b(?:four\s+times|4\s*x|4\s*times)\s*(?:a|per|each|every)?\s*day\b|\b4\s*x\s+daily\b", re.I)
PART_OF_DAY = re.compile(r"\b(?:noon|lunch|midday|afternoon|breakfast|dinner|supper|bedtime)\b", re.I)
EVENING_PARTS = re.compile(r"\b(?:morning|evening|night|tonight)s?\b", re.I)
CLOCK = re.compile(r"\d")


def _times_a_day(when, message):
    """Section 11 defaults, set by code: 'twice a day' with no clock times is 08:00 and 20:00 (also with "morning and
    night"); three times 08:00, 13:00, 19:00; four adds 16:00. Named times or other parts of the day stay theirs."""
    if when is None or when.type != "schedule" or when.window:
        return
    for rx, n, default in ((TWICE, 2, ["08:00", "20:00"]), (THRICE, 3, ["08:00", "13:00", "19:00"]),
                           (FOUR, 4, ["08:00", "13:00", "16:00", "19:00"])):
        m = rx.search(message)
        if not m:
            continue
        rest = message[:m.start()] + " " + message[m.end():]
        if CLOCK.search(rest) or PART_OF_DAY.search(rest) or (n > 2 and EVENING_PARTS.search(rest)):
            return
        if len(when.times) in (1, n) and when.times != default:
            when.times = list(default)
        return


SURPRISE = re.compile(r"\bsurprise\b|\b(?:some\s?time|at\s+some\s+point|some\s+day|someday|one\s+day)\b", re.I)
REPEAT = re.compile(r"\b(?:every|each|weekly|daily|monthly|per|times\s+a|a\s+(?:day|week|month))\b", re.I)


def _surprise(x: Interpretation, message, now, tzname):
    """One surprise in a coming period ("surprise me sometime next week") is a random moment, never a fixed time the
    model chose: random, count 1 for that period, max_sends 1 unless they ask for it every period."""
    if x.spec is None or not SURPRISE.search(message) or CLOCK.search(message):
        return
    w = x.spec.when
    if w.type not in ("once", "schedule") or w.window or w.every_hours:
        return
    if w.type == "schedule" and (w.month_days or w.month_weeks or w.every_days):
        return
    low = message.lower()
    local = now.astimezone(ZoneInfo(tzname)).date()
    per = "day" if re.search(r"\b(?:today|tonight|tomorrow)\b", low) else \
        "month" if re.search(r"\bmonth\b", low) else "week"
    days, start, until = [], None, None
    if re.search(r"\bweekend\b", low):
        days = ["SAT", "SUN"]
    if re.search(r"\bnext\s+(?:week|weekend)\b", low):
        start = (local + timedelta(days=7 - local.weekday())).isoformat()
    elif re.search(r"\bnext\s+month\b", low):
        start = (local.replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()
    elif re.search(r"\btomorrow\b", low):
        start = until = (local + timedelta(days=1)).isoformat()
    elif re.search(r"\b(?:today|tonight)\b", low):
        start = until = local.isoformat()
    once = not REPEAT.search(message)
    x.spec.when = When(type="random", count=1, per=per, days=days or (w.days if w.type == "schedule"
                                                                        and len(w.days) < 7 else []),
                       start=start, until=until, max_sends=1 if once else None)


WEEK_END = re.compile(r"\b(?:this\s+week|(?:the\s+)?end\s+of\s+(?:the|this)\s+week|rest\s+of\s+(?:the|this)\s+week)\b",
                      re.I)
MONTH_END = re.compile(r"\b(?:this\s+month|(?:the\s+)?end\s+of\s+(?:the|this)\s+month|rest\s+of\s+(?:the|this)\s+month)\b",
                       re.I)


def _calendar_end(when, message, now, tzname):
    """'This week' as an end is this coming Sunday, not seven days on; 'this month' is its last day."""
    if when is None or not when.repeating or not when.until:
        return
    local = now.astimezone(ZoneInfo(tzname)).date()
    gap = (date.fromisoformat(when.until) - local).days
    if WEEK_END.search(message) and 6 <= gap <= 8:
        when.until = (local + timedelta(days=6 - local.weekday())).isoformat()
    elif MONTH_END.search(message) and 27 <= gap <= 31:
        nxt = (local.replace(day=1) + timedelta(days=32)).replace(day=1)
        when.until = (nxt - timedelta(days=1)).isoformat()


DAY_NAMES = {"monday": "MON", "tuesday": "TUE", "tues": "TUE", "wednesday": "WED", "thursday": "THU", "thurs": "THU",
             "friday": "FRI", "saturday": "SAT", "sunday": "SUN"}
ALL_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DAY_WORD = re.compile(r"\b(" + "|".join(DAY_NAMES) + r")s?\b", re.I)
WEEKDAYS = re.compile(r"\b(?:week\s?days|every\s+week\s?day)\b", re.I)
WEEKENDS = re.compile(r"\b(?:week\s?ends|every\s+week\s?end)\b", re.I)
DAILY = re.compile(r"\b(?:every\s+(?:single\s+)?(?:day|morning|evening|night|afternoon)|daily|each\s+(?:day|morning|"
                   r"evening|night)|nightly)\b", re.I)
AT_TIME = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)


def stated_days(message):
    """The weekdays a message names in so many words, or None."""
    if WEEKDAYS.search(message):
        return ALL_DAYS[:5]
    if WEEKENDS.search(message):
        return ["SAT", "SUN"]
    named = [DAY_NAMES[m.lower()] for m in DAY_WORD.findall(message)]
    if named:
        return sorted(set(named), key=ALL_DAYS.index)
    if DAILY.search(message):
        return list(ALL_DAYS)
    return None


def _clarify_keeps(x: Interpretation, message):
    """The half-built form of clarify keeps the weekly days (and a clock time) the person stated; the model sometimes
    dropped them for on_request."""
    if x.intent != "clarify" or not isinstance(x.draft, dict):
        return
    w = x.draft.get("when") if isinstance(x.draft.get("when"), dict) else {}
    if w.get("days") or w.get("type") in ("random", "once", "new_items") or w.get("every_days") \
            or w.get("month_days") or w.get("month_weeks"):
        return
    days = stated_days(message)
    if not days:
        return
    new = {k: v for k, v in w.items() if k not in ("type",)}
    new.update({"type": "schedule", "days": days})
    m = AT_TIME.search(message)
    if m and not (new.get("times") or new.get("time")):
        h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
        new["times"] = [f"{h:02d}:{int(m.group(2) or 0):02d}"]
    try:
        new = When.model_validate(new).model_dump(exclude_none=True)
    except ValueError:
        return
    x.draft = {**x.draft, "when": {k: v for k, v in new.items() if v not in ([], None)}}


def _norm(text):
    return " ".join(WORD.findall((text or "").lower()))


RULE_NOW = re.compile(r"\b(?:now|right\s+now|early|earlier)\b", re.I)
NEXT_SEND = re.compile(r"\b(?:this\s+week'?s|tomorrow'?s|next|(?:mon|tues|wednes|thurs|fri|satur|sun)day'?s)\b", re.I)
WHOSE = re.compile(r"\b(?:today'?s|tonight'?s|this\s+week'?s|tomorrow'?s|next|"
                   r"(?:mon|tues|wednes|thurs|fri|satur|sun)day'?s|the\s+[a-z]+(?:\s+[a-z]+)?\s+one)\b", re.I)


def _rule_now(x: Interpretation, rules, message=""):
    """An ask for an existing rule's send now ("can I have this week's pasta now?", "the workout one now") is that rule
    run now, not a fresh search with a copy of its spec. "Next", "tomorrow's" or a weekday's is the next send, so it
    is not sent again then (skip_next). A plain ask on the same topic ("pasta ideas?") stays an ask."""
    if x.intent != "ask" or x.spec is None or not rules:
        return
    if RULE_NOW.search(message) and WHOSE.search(message):
        n = _rule_by_topic(message, rules)
        if n is not None:
            x.intent, x.spec, x.rule_number = "run_rule", None, n
            x.skip_next = bool(NEXT_SEND.search(message))
            return


def _todo_match(text, todos):
    """The number of the one open to-do whose words are all in `text` (or nearly the same text), or None."""
    want = _topic_stems(text) - {"remind", "due", "need", "doing", "done", "finish", "finished"}
    hits = []
    for i, t in enumerate(todos, 1):
        own = _topic_stems(t["text"])
        if not own:
            continue
        if own <= want or (want and want <= own) or \
                difflib.SequenceMatcher(None, _norm(text), _norm(t["text"])).ratio() >= 0.85:
            hits.append(i)
    return hits[0] if len(hits) == 1 else None


def _due_for_todo(x: Interpretation, todos):
    """A one-time reminder (or a new to-do with a time) whose words are an open to-do's is that to-do's due time."""
    if not todos:
        return x
    w, text = None, None
    if x.intent == "new_rule" and x.spec is not None and x.spec.content.source == "note" and x.spec.when.type == "once":
        w, text = x.spec.when, x.spec.content.text
    elif x.intent == "todo_add" and x.todo_text and (x.due or x.in_minutes) and not x.pick_number:
        text = x.todo_text
    else:
        return x
    n = _todo_match(text, todos)
    if n is None:
        return x
    form = {"intent": "todo_due", "todo_number": [n], "profile_note": x.profile_note, "lang": x.lang}
    if w is not None:
        if w.in_minutes:
            form["in_minutes"] = w.in_minutes
        elif w.date and w.times:
            form["due"] = f"{w.date}T{w.times[0]}"
    else:
        form["due"], form["in_minutes"] = x.due, x.in_minutes
    try:
        out = Interpretation.model_validate({k: v for k, v in form.items() if v is not None})
    except ValidationError:
        return x
    out.also = x.also
    return out


FINDABLE = re.compile(r"\b(?:recipes|videos|vids|tutorials|reels|posts|workouts|routines|ideas|projects|lessons|"
                      r"exercises|stretches|tips|meals|dishes|songs|crafts)\b", re.I)
QUANTITY = re.compile(r"^\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|a\s+couple(?:\s+of)?|couple(?:\s+of)?"
                      r"|a\s+few|few|some|several)\s+", re.I)
FROM_SAVES = re.compile(r"\b(?:from|in)\s+my\s+(?:saves|saved|library|youtube|instagram|feed|likes)\b|\bi\s+(?:saved|kept|"
                        r"liked|watched)\b", re.I)


def _todo_by_text(x: Interpretation, todos):
    """'Mark call the landlord done' gives the to-do's words: its number is filled when exactly one open to-do fits, so
    one meaning has one form."""
    if x.intent in ("todo_done", "todo_remove", "todo_due") and x.todo_text and not x.todo_number and todos:
        n = _todo_match(x.todo_text, todos)
        if n is not None:
            x.todo_number = [n]


def _find_for_list(x: Interpretation, message):
    """'Put a couple of lunch recipes on my list' asks the bot to FIND them first: an ask with todo.add, never a to-do
    whose text is the request."""
    if x.intent != "todo_add" or not x.todo_text or x.pick_number or x.what == "ingredients" or x.due or x.in_minutes:
        return x
    text = x.todo_text
    if not FINDABLE.search(text):
        return x
    q = QUANTITY.match(text)
    if not (q or FROM_SAVES.search(text) or FROM_SAVES.search(message)):
        return x
    count = 3
    goal = text
    if q:
        w = " ".join(q.group(1).lower().split())
        count = int(w) if w.isdigit() else NUMBER_WORDS.get(w, 3)
        goal = text[q.end():]
    goal = FROM_SAVES.sub("", goal).strip(" ,.") or text
    todo = {"action": "todo.add", "params": {"list": x.todo_list}} if x.todo_list and x.todo_list != "todo" \
        else {"action": "todo.add"}
    content = {"source": "library", "goal": goal[:200], "searches": [goal[:120]], "count": max(1, min(count, 10))}
    if FROM_SAVES.search(message) and re.search(r"\bsaves?\b|\bsaved\b", message, re.I):
        content["kinds"] = list(SAVED_KINDS)
    try:
        out = Interpretation.model_validate({"intent": "ask", "spec": {"when": {"type": "now"}, "content": content,
                                                                         "do": ["message.send", todo]},
                                             "profile_note": x.profile_note, "lang": x.lang})
    except ValidationError:
        return x
    out.also = x.also
    return out


def _act_into_do(it: Interpretation):
    """'Find a yoga flow and put it on my calendar at 7': the calendar (email, list) is the new answer's own output, in
    its do list, not a second act_on_last that would act on the answer shown before."""
    a = it.also
    if it.intent not in ("ask", "new_rule") or it.spec is None or a is None or a.intent != "act_on_last":
        return
    if a.when is not None or (a.pick_number not in (None, 1)) or (a.answer_ref not in (None, "last")):
        return
    do = list(it.spec.do)
    for act in a.actions:
        if all(d.action != act.action for d in do):
            do.append(act)
    if len(do) > 4:
        return
    it.spec.do = do
    it.also = None


NEGATED = re.compile(r"^\s*(?:no|without|nothing\s+with|not|avoid|skip|minus|leave\s+out|hold\s+the)\s+(?:any\s+)?"
                     r"([a-z][a-z' -]{1,30}?)\s*$", re.I)
# a thing they lack is a must-have ("needs no oven"), not a word to leave out: avoid would drop every item whose text
# says "no oven needed"
NEEDS = set("""equipment gear weights weight dumbbells dumbbell kettlebell kettlebells oven stove stovetop microwave
    blender mixer machine machines tools tool gym mat bench bands band cooking baking prep jumping jump noise""".split())
NOT_THINGS = set("more less longer than too over under fewer".split())


def _negations_to_avoid(criteria, avoid):
    """'no mushrooms' as a must-have is a thing to leave out: it moves to avoid (as the plain noun)."""
    from .retrieve import _stem
    keep = []
    for cr in criteria:
        m = NEGATED.match(cr)
        words = m.group(1).lower().split() if m else []
        if not words or words[0] in NOT_THINGS or any(_stem(w) in NEEDS or w in NEEDS for w in words) \
                or len(words) > 3:
            keep.append(cr)
            continue
        noun = " ".join(_stem(w) for w in words)
        if noun not in avoid and len(avoid) < 8:
            avoid.append(noun)
    return keep


AP = "['\u2019]?"
FACT = re.compile(
    r"\b(?:i" + AP + r"m|i\s+am)\s+(?:now\s+)?(?:a\s+)?(?:vegetarian|vegan|pescatarian|gluten[- ]free|dairy[- ]free|keto|"
    r"halal|kosher|lactose[- ]intolerant)\b(?:\s+now)?"
    r"|\bi\s+(?:don" + AP + r"t|do\s+not|can" + AP + r"t|cannot|never)\s+eat\s+[a-z][a-z -]{1,30}?"
    r"(?=[,.;!?]|\s+(?:and|so|but|any|anymore)\b|$)"
    r"|\bi\s+(?:(?:only|just)\s+(?:have|got|bought)|bought|own|(?:have|got)(?=\s+(?:a|an)\s+new\b))\s+"
    r"(?:a|an|my|one|some)\s+(?:new\s+)?[a-z][a-z -]{1,30}?(?=[,.;!?]|\s+(?:and|so|but|at|in|for|now|any|what|anymore)\b|$)",
    re.I)
NOT_A_FACT = re.compile(r"\b(?:time|minutes?|hours?|question|party|day|night|week|idea|moment|sec|second)\b", re.I)


def _fact_note(it: Interpretation, message):
    """A lasting fact said inside a request ("I'm vegetarian now, dinner ideas?") is kept as a profile note too."""
    if it.intent not in ("ask", "new_rule", "more") or any(x.profile_note for x in [it] + ([it.also] if it.also else [])):
        return
    m = FACT.search(message)
    if m and not NOT_A_FACT.search(m.group(0)):
        it.profile_note = " ".join(m.group(0).split())[:120]


TIPS_ONLY = re.compile(r"\b(?:tips?|tricks?|hacks?|advice|theory|inspo|inspiration|recap)\b", re.I)


def _tips_must_haves(c, message):
    """A tips request keeps only the must-haves its own words state: the person's direction or level from their
    profile is not a must-have for tips (DESIGN.md section 3: tips and theory get no finished-result criterion)."""
    if TIPS_ONLY.search(message):
        said = set(_stems(message))
        c.criteria = [cr for cr in c.criteria
                      if any(s in said for s in _topic_stems(cr) - {"end", "finish", "finished", "whole", "full"})]


THIS_WEEK = re.compile(r"\b(?:this|the\s+past|the\s+last)\s+week\b|\blast\s+7\s+days\b", re.I)


def _recent_week(c, message, now, tzname):
    """'What did I save this week' written as dates (a week back to tomorrow) is since_days 7: one form, and a rule
    keeps a window that moves with time."""
    if c.source != "recent" or not c.saved_after or c.since_days or not THIS_WEEK.search(message):
        return
    local = now.astimezone(ZoneInfo(tzname)).date()
    back = (local - date.fromisoformat(c.saved_after)).days
    if 6 <= back <= 8 and (not c.saved_before or date.fromisoformat(c.saved_before) > local):
        c.since_days, c.saved_after, c.saved_before = 7, None, None


# ---------- fix pass 2 (findings 58 and 60): code-side completions for kinds the interpreter still misses ----------
LEVEL_WORD = [(re.compile(r"\b(?:absolute |complete |total )?beginners?\b|\bnewbies?\b|\bnovices?\b|\bfor starters\b",
                          re.I), "suits a beginner"),
              (re.compile(r"\bintermediate\b", re.I), "suits an intermediate level"),
              (re.compile(r"\badvanced\b|\bexpert[- ]level\b", re.I), "suits an advanced level"),
              (re.compile(r"\bfor (?:kids|children|my kids|toddlers)\b|\bkid[- ]friendly\b", re.I), "suits kids")]
LEVEL_IN_CRITERION = re.compile(r"\b(?:beginner|novice|newbie|intermediate|advanced|expert|kids?|children|toddlers?)",
                                re.I)


def _level_criterion(c, message):
    """Finding 58: a level word in the person's own message (beginner, intermediate, advanced, for kids) is a
    must-have, worded in plain words, when the form left it out. ("easy" is given to the composer as the level asked
    for instead: profile.composer_context.)"""
    if any(LEVEL_IN_CRITERION.search(cr) for cr in c.criteria) or len(c.criteria) >= 5:
        return
    for rx, crit in LEVEL_WORD:
        if rx.search(message):
            c.criteria.append(crit)
            return


RANDOM_PICK = re.compile(r"\b(?:a|any|some|one)\s+random\b|\brandom\s+(?:one|pick|picks|recipe|recipes|video|videos|post|"
                         r"posts|reel|reels|tutorial|tutorials|workout|workouts|thing|things|idea|ideas|meal|meals|dish)\b"
                         r"|\bsurprise me with (?:any|anything|something|one|a)\b|\b(?:pick|choose|grab) (?:any|one) at random\b",
                         re.I)


def _random_pick(c, message):
    """Finding 60: an explicit "random one" or "surprise me with any" is the order, not the timing."""
    if c.source == "library" and c.order == "best" and RANDOM_PICK.search(message):
        c.order = "random"


TOO_HARD = re.compile(r"\btoo (?:hard|difficult|advanced|complicated|complex)\b|\b(?:something|one) easier\b|"
                      r"\beasier (?:one|please|pls)\b|\bover my head\b", re.I)
TOO_EASY = re.compile(r"\btoo (?:easy|basic|simple)\b|\b(?:something|one) harder\b|\bharder (?:one|please|pls)\b|"
                      r"\bmore (?:advanced|challenging)\b", re.I)


def _level_feedback(it: Interpretation, message):
    """Finding 60: "too hard" is feedback "easier" (and "too easy" is "harder"), never generic negative feedback; a
    "more" that says it ("too hard, something shorter") keeps its change as the one sent now."""
    way = "easier" if TOO_HARD.search(message) else "harder" if TOO_EASY.search(message) else None
    if not way:
        return it
    if it.intent == "feedback" and it.feedback in (None, "down", "less", "up", "more"):
        it.feedback = way
    elif it.intent == "more" and it.also is None:
        more = it.model_copy(deep=True)
        return Interpretation(intent="feedback", feedback=way, pick_number=it.pick_number, lang=it.lang,
                              also=more)
    return it


# a few words that mark a language (each a whole word), for a message the form left without "lang"
LANG_WORDS = {
    "es": set("qué que quiero receta recetas para con por favor dame busca búscame envíame mándame cómo como hacer "
              "una unos unas algo nuevo nueva cena comida rápida fácil mañana hoy noche semana".split()),
    "fr": set("je veux une des recette recettes pour avec s'il te plaît plait donne moi cherche envoie comment faire "
              "quelque chose nouveau dîner rapide facile demain ce soir semaine".split()),
    "de": set("ich möchte ein eine rezept rezepte für mit bitte gib mir such schick wie machen etwas neues "
              "abendessen schnell einfach morgen heute woche".split()),
    "pt": set("eu quero uma receita receitas para com por favor dá manda procura como fazer algo novo jantar rápido "
              "fácil amanhã hoje semana".split()),
    "it": set("voglio una ricetta ricette con favore dammi cerca mandami qualcosa nuovo cena veloce facile domani oggi "
              "settimana".split()),
}
EN_WORDS = set("i me my the a an to for with and of some please send find give show want need what how recipe "
               "recipes video videos new quick easy dinner tonight tomorrow week".split())


def detect_lang(message):
    """The language a message is written in, by its script or its common words; None for English or when unsure."""
    t = message or ""
    if re.search(r"[\u3040-\u30ff]", t):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", t):
        return "zh"
    if re.search(r"[\uac00-\ud7af]", t):
        return "ko"
    if re.search(r"[\u0400-\u04ff]", t):
        return "ru"
    if re.search(r"[\u0600-\u06ff]", t):
        return "ar"
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", t.lower())
    if len(words) < 2:
        return None
    en = sum(w in EN_WORDS for w in words)
    best, score = None, 0
    for code, vocab in LANG_WORDS.items():
        n = sum(w in vocab for w in words)
        if n > score:
            best, score = code, n
    return best if score >= 2 and score > en else None


NEW_SAVES_IN = re.compile(r"\b(?:get|bring|add|load|import|put|upload|send)\s+(?:in\s+)?(?:my\s+|the\s+)?(?:new|newest|"
                          r"latest|recent|fresh|more)?\s*(?:saves|saved posts|saved stuff|exports?|likes|data|library|"
                          r"watch history|history)\s+(?:in|into|over|across|to you|up to date)\b"
                          r"|\bhow (?:do|can|should) i (?:export|update|refresh|sync)\b"
                          r"|\b(?:update|refresh|sync)\s+my\s+(?:library|saves|data)\b"
                          r"|\bhow do i (?:get|send|give) you my\b", re.I)


def _library_question(it: Interpretation, message):
    """Finding 60: "how do I get my new saves in?" is the library status with the export steps."""
    if it.intent in ("unsupported", "help", "chat") and NEW_SAVES_IN.search(message):
        return Interpretation(intent="library_status", lang=it.lang)
    return it


def _every_day(when, message):
    """Finding 60: "every day" stays every day even when the message also names a routine ("before work", "after
    my run"); the weekdays come only from the message saying weekdays."""
    if when.type == "schedule" and when.days == ALL_DAYS[:5] and DAILY.search(message) \
            and not WEEKDAYS.search(message) and stated_days(message) in (None, ALL_DAYS):
        when.days = list(ALL_DAYS)


FIND_CLAUSE = re.compile(r"(?:,|;|\band\b|\bthen\b|\balso\b)\s+(?:also\s+|then\s+)?(?:can you\s+|could you\s+|please\s+)?"
                         r"(?:find|send|show|get|give|recommend|suggest|look up|pull up|pick)\s+(?:me\s+)?"
                         r"(?P<what>[^,;.!?]{3,120})", re.I)
TODO_CLAUSE = re.compile(r"\b(?:add|put|jot down|stick)\s+(?P<what>[^,;.!?]{2,80}?)\s+(?:to|on|onto)\s+(?:my|the)\s+"
                         r"(?:(?P<list>[a-z]+)\s+)?(?:to-?do\s+)?list\b", re.I)


def _two_parts(it: Interpretation, message):
    """Finding 60: a to-do and a request in one message keep their two-part shape ("add milk to my list and find me
    a pancake recipe"). Code adds the half the form dropped, in the person's own words. Both clauses must be in the
    message, apart from each other ("put a few recipes on my list" is one request: _find_for_list)."""
    if it.also is not None or it.intent not in ("todo_add", "ask", "new_rule"):
        return it
    f, t = FIND_CLAUSE.search(message), TODO_CLAUSE.search(message)
    if not f or not t or (t.start() < f.end() and f.start() < t.end()):
        return it
    what = " ".join(f.group("what").split()).strip(" .")
    if it.intent == "todo_add":
        if it.todo_text and what.lower() in it.todo_text.lower():   # the request was lumped into the to-do's text
            cut = it.todo_text[:it.todo_text.lower().index(what.lower())]
            cut = re.sub(r"[\s,;]*(?:and|then|also)?\s*(?:find|send|show|get|give|recommend|suggest|pick)?\s*(?:me)?\s*$",
                         "", cut, flags=re.I).strip(" ,;.")
            it.todo_text = cut or it.todo_text
        it.also = Interpretation.model_validate({"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
            "goal": what[:120], "searches": [what[:120]]}}})
        return it
    if it.spec is not None and any(a.action == "todo.add" for a in it.spec.do):
        return it
    name = list_name(t.group("list")) if t.group("list") else None
    todo = Interpretation.model_validate({"intent": "todo_add", "todo_text": " ".join(t.group("what").split()),
                                          **({"list": name} if name and name != "todo" else {})})
    if t.start() < f.start():   # in the order they said them
        todo.also, todo.lang = it, it.lang
        return todo
    it.also = todo
    return it


# fix pass 2, finding 63: a profile note needs the person to say something about themselves; words about timing or the
# request itself ("start doing daily") are never one
ABOUT_ME = re.compile(r"\b(?:i|i['’]m|im|i['’]ve|ive|i['’]d|i['’]ll|myself|my (?:goal|diet|kitchen|level|knee|back))\b|"
                      r"\b(?:vegetarian|vegan|pescatarian|gluten[- ]free|dairy[- ]free|keto|halal|kosher|lactose)\b", re.I)


def _request_note(x: Interpretation, message):
    if x.profile_note and (timing_only(x.profile_note) or not ABOUT_ME.search(message)):
        x.profile_note = None


def _message_wins(x: Interpretation, message):
    """Finding 62: what the message asks for wins over the profile: an avoid entry the message names ("chicken" for
    "what can I make with chicken and rice?", or "meat", which covers it) is dropped; "no chicken" stays."""
    from .profile import avoid_for
    if x.spec is not None and x.spec.content.avoid:
        x.spec.content.avoid = avoid_for(x.spec.content.avoid, message)
    if x.avoid:
        x.avoid = avoid_for(x.avoid, message)


def _took_back(it: Interpretation, message):
    """Finding 62: "I eat meat again, I'm not vegetarian" is about them: profile_update (or a note on a request), so
    the avoid entry is removed."""
    from .profile import ALLOW_AGAIN
    m = ALLOW_AGAIN.search(message)
    if not m:
        return it
    if it.intent in ("chat", "unsupported", "feedback", "help"):
        return Interpretation(intent="profile_update", lang=it.lang)
    if it.intent in ("ask", "new_rule", "more") and not it.profile_note:
        it.profile_note = " ".join(m.group(0).split())[:120]
    return it


def settle(raw, message, rules, now, tzname, todos=()):
    """A raw form from the model (or the cache) to a validated, completed Interpretation. Raises ValidationError."""
    it = Interpretation.model_validate(_fill_raw(_drop_model_moment(merge_todo_adds(raw))))
    it = _library_question(_level_feedback(it, message), message)
    if not it.lang:
        it.lang = detect_lang(message)
    it = _two_parts(_find_for_list(_due_for_todo(it, todos), message), message)
    if it.also is not None:
        it.also = _find_for_list(_due_for_todo(it.also, todos), message)
    _act_into_do(it)
    _fact_note(it, message)
    it = _took_back(it, message)
    for x in [it] + ([it.also] if it.also else []):
        _request_note(x, message)
        _message_wins(x, message)
        _from_message(x, message)
        _todo_by_text(x, todos)
        _rule_now(x, rules, message)
        _target(x, message, rules)
        _canonical_change(x, rules)
        _clarify_keeps(x, message)
        if x.spec is not None:
            _surprise(x, message, now, tzname)
            _times_a_day(x.spec.when, message)
            _calendar_end(x.spec.when, message, now, tzname)
            _every_day(x.spec.when, message)
            c = x.spec.content
            c.criteria = _negations_to_avoid(c.criteria, c.avoid)
            if c.source == "library" and x.intent in ("ask", "new_rule"):
                _tips_must_haves(c, message)
                _level_criterion(c, message)
                _random_pick(c, message)
            _recent_week(c, message, now, tzname)
        if x.criteria:
            x.criteria = _negations_to_avoid(x.criteria, x.avoid)
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
            it = new_find(later_on_last(settle(raw, text, rules, now, person["timezone"], todos), text, last, now,
                                            person["timezone"]), text, last)
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
            it = new_find(later_on_last(settle(raw, text, rules, now, person["timezone"], todos), text, last, now,
                                            person["timezone"]), text, last)
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
    from .texts import NOT_CAUGHT
    return Interpretation(intent="unsupported", reply=NOT_CAUGHT), cost


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
