"""PROTOTYPE ONLY - the errand form (round 10, slice W7; DESIGN.md section 17.W; design A6).

One small model call, only after the interpreter has refused, chatted, answered "help" with no help word, or clashed
with what is on screen, and only when every code read missed. The model fills a form (`prompts/errand_v1.md`): which
of the helpers the message asks for, and words copied from the message. Code checks every field against the message
and what is on screen, then hands a message built by code to the helper's existing code entry, which acts as it does
today (cards, previews, a yes, "send"). The model never acts, never sends, never names a recipient, an address, an
app or a merchant that the message does not hold (AGENTS.md rule 6).

Its input is the state word and the message only: no caption, title, to-do text, rule text or profile line ever goes
in. When the form says "none", fails a check, or the helper does not take the built message, the interpreter's
answer is dispatched as before, so the errand can only rescue a message, never take one from the normal path. It never
runs on a message with a time or repeat word (a rule: W-3), over 400 characters, over 30 calls a person a day
(MVP_ERRAND_PER_DAY), or over the caps. Each call is logged in ai_runs (llm.chat_json) and as an action_log row
"errand.form" with the errand's name only.
"""
import hashlib
import os
import re
import unicodedata
from datetime import datetime, timedelta

from . import config, llm, phrasing
from . import texts as T
from .store import now_iso

PROMPT_VERSION = "errand_v2"   # v1 plus: an errand marked for a state is "none" in any other; a number only when said
MAX_CHARS = 400
CACHE_HOURS = 6
ERRANDS = ("email_other", "email_self", "save_draft", "change_draft", "send_draft", "cancel", "post_act",
           "add_to_app", "app_connection", "what_did_you_do", "do_todo", "exports")
SMALLTALK = re.compile(r"^\W*(?:thanks|thank you|thx|ty|ok|okay|cool|nice|great|lol|haha|hi|hello|hey|bye|"
                       r"good (?:morning|night)|gracias|hola|vale)\W*$", re.I)
HELP_WORD = re.compile(r"\b(?:help|ayuda|what can you do|how does this work|commands?)\b", re.I)
CHANGES = {"shorter": "make it shorter", "longer": "make it longer", "more_formal": "make it more formal",
           "less_formal": "make it less formal", "friendlier": "make it friendlier"}
LANGS = {"english", "spanish", "french", "german", "italian", "portuguese"}
ACTS = {"apply": "apply to", "book": "book", "buy": "buy", "tickets": "get me tickets for", "sign_up": "sign me up for"}
APP_OPS = {"connect": "connect my {app}", "check": "check my {app}", "disconnect": "disconnect my {app}"}
_PROMPT = {}
# the person's role words in Spanish, said back in English ("your boss's email address"); any other word as written
SAME_WORD = {"jefe": "boss", "jefa": "boss", "profe": "teacher", "profesor": "teacher", "profesora": "teacher",
             "maestro": "teacher", "maestra": "teacher", "mama": "mom", "madre": "mother", "papa": "dad",
             "padre": "father", "casero": "landlord", "casera": "landlord", "amigo": "friend", "amiga": "friend",
             "hermano": "brother", "hermana": "sister", "entrenador": "coach", "entrenadora": "coach",
             "doctor": "doctor", "doctora": "doctor"}


def per_day():
    try:
        return max(0, int(os.environ.get("MVP_ERRAND_PER_DAY") or 30))
    except ValueError:
        return 30


def model():
    return os.environ.get("MVP_ERRAND_MODEL") or None   # None: config.MODEL


def prompt():
    if "t" not in _PROMPT:
        with open(os.path.join(config.HERE, "prompts", f"{PROMPT_VERSION}.md"), encoding="utf-8") as f:
            _PROMPT["t"] = f.read()
    return _PROMPT["t"]


def _fold(s):
    s = unicodedata.normalize("NFKD", " ".join(str(s or "").split()).casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def in_message(words, text):
    """True when the words (casefolded, accents aside) occur in the message or its normalised form."""
    w = _fold(words).strip(" .,!?¿¡\"'")
    if not w:
        return False
    return any(w in _fold(t) for t in (text, phrasing.normalize(text)))


# ---------- when it runs ----------
def wanted(it, text):
    """True when the interpreter's answer is one the errand may rescue (design A6, step 3), and the message may go."""
    t = " ".join((text or "").split())
    if not t or len(t) > MAX_CHARS or phrasing.TIME_WORDS.search(phrasing.normalize(t)) or phrasing.TIME_WORDS.search(t):
        return False
    if it is None or it.intent == "unsupported":
        return True
    if it.intent == "help":
        return not HELP_WORD.search(t)
    if it.intent == "chat":
        return not SMALLTALK.match(t)
    return False


def state_word(bot, person, now):
    """fresh | answer N | draft | todos N | setup: what is on the person's screen, in a word and a count."""
    h = person["handle"]
    d = bot.open_draft(h, now)
    if d is not None and bot._draft_card_in_view(h, d):
        return "draft"
    st = bot.store.get_state(f"onboard:{h}")
    if st and st.get("step") not in (None, "done"):
        return "setup"
    if bot.store.get_state(f"todoview:{h}") and bot._todos_in_view(h, now):
        return f"todos {len(bot.store.todos(h))}"
    last = bot._answer_seen(h)
    if last and last.get("items"):
        return f"answer {len(last['items'])}"
    if d is not None:
        return "draft"
    return "fresh"


def _used_today(bot, person, now):
    from .actions import local_day_bounds
    start, end = local_day_bounds(now, person.get("timezone") or "America/New_York")
    return bot.store.actions_in(person["handle"], ["errand.form"], start, end)


# ---------- the call ----------
def ask(bot, person, text, state, now):
    """The form for this message (cached 6 hours by version, state and text), or None when the call failed."""
    h = person["handle"]
    t = " ".join(text.split())
    key = hashlib.sha256(f"{PROMPT_VERSION}|{state}|{t}".encode("utf-8")).hexdigest()[:16]
    ck = f"errandc:{key}:{h}"   # ends in the handle: "delete my data" removes it
    hit = bot.store.get_state(ck)
    if hit and now - datetime.fromisoformat(hit["at"]) <= timedelta(hours=CACHE_HOURS):
        return hit["form"]
    user = f"<state>{state}</state>\n<message>{t.replace('<', '‹').replace('>', '›')}</message>"
    try:
        raw, _ = llm.chat_json(prompt(), user, purpose="mvp_errand", prompt_version=PROMPT_VERSION, person=h,
                               max_tokens=120, temperature=config.INTERPRET_TEMPERATURE, seed=config.INTERPRET_SEED,
                               model=model())
    except Exception as e:  # noqa: BLE001 - the interpreter's answer stands
        bot.store.add_run(handle=h, kind="errand", status="error", error=type(e).__name__)
        return None
    form = raw if isinstance(raw, dict) else {}
    bot.store.set_state(ck, {"at": now_iso(now), "form": form})
    return form


# ---------- the checks, per errand ----------
def _num(v, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


# a number the message itself says: a digit, or an ordinal in English or Spanish (the model never picks one)
_SAID = {1: r"first|1st|one|primer[oa]?|un[oa]?", 2: r"second|2nd|two|segund[oa]|dos", 3: r"third|3rd|three|tercer[oa]?|tres",
         4: r"fourth|4th|four|cuart[oa]|cuatro", 5: r"fifth|5th|five|quint[oa]|cinco"}
POINTER = re.compile(r"\b(?:it|this|that|this one|that one|esto|eso|este|ese|esta|esa|lo|la)\b", re.I)


def said_number(n, text):
    t = _fold(text)
    return bool(re.search(rf"(?<!\d){n}(?!\d)", t) or (n in _SAID and re.search(rf"\b(?:{_SAID[n]})\b", t)))


def _ordinal(n):
    return {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(n)


def built(bot, person, form, text, state, now):
    """(errand, the message code builds for its helper or a callable) after every check; None when a check fails."""
    from .drafts import ADDR_RE, OTHER_RE, PEOPLE_WORDS
    name = form.get("errand")
    if name not in ERRANDS:
        return None
    h = person["handle"]
    draft = state == "draft"
    n_ans = int(state.split()[1]) if state.startswith("answer ") else 0
    n_todo = int(state.split()[1]) if state.startswith("todos ") else 0

    def words(k):
        v = form.get(k)
        return " ".join(str(v).split()) if isinstance(v, str) and v.strip() and in_message(v, text) else None
    if name == "email_other":
        to = words("to_words")
        if not to:
            return None
        addr = form.get("address")
        addr = addr if isinstance(addr, str) and addr in ADDR_RE.findall(text) else None
        say = words("say_words")
        if not say:
            return None
        from .drafts import is_group
        if is_group(to):   # first full live self-test (c04): a group is never a name
            return name, {"to": addr, "word": None, "name": "everyone", "group": True, "say": say}
        m = re.match(rf"^(?:my|mi|mis|our)\s+(?P<w>{PEOPLE_WORDS}|[^\W\d_]{{2,20}})$", to, re.I)
        word = SAME_WORD.get(_fold(m.group("w")), m.group("w").lower()) if m else None
        return name, {"to": addr, "word": word,
                      "name": None if m else " ".join(w[:1].upper() + w[1:] for w in to.split())[:40], "say": say}
    if name == "email_self":
        what = form.get("what")
        if what == "draft":
            return (name, {"what": "draft"}) if bot.open_draft(h, now) is not None else None
        if what in ("answer", "pick") and n_ans:
            pick = _num(form.get("pick"), 1, n_ans) if form.get("pick") is not None else None
            if form.get("pick") is not None and (pick is None or not said_number(pick, text)):
                return None
            return name, {"what": what, "pick": pick}
        return None
    if name in ("save_draft", "send_draft"):
        return (name, {}) if draft else None
    if name == "change_draft":
        if not draft:
            return None
        ch = form.get("change")
        if ch in CHANGES:
            return name, CHANGES[ch]
        if ch == "language":
            lang = str(form.get("language") or "").lower()
            return (name, f"make it in {lang}") if lang in LANGS else None
        new, old = words("new_words"), form.get("old_words")
        d = bot.open_draft(h, now)
        body = (d or {}).get("body") or ""
        old_ok = isinstance(old, str) and old.strip() and _fold(old) in _fold(body)
        if ch == "replace" and new and old_ok:
            return name, f"say {new} instead of {old.strip()}"
        if ch == "remove" and old_ok:
            return name, f"take out the part about {old.strip()}"
        if ch == "add" and new:
            return name, f"add that {new}"
        if ch == "subject" and new:
            return name, f"change the subject to {new}"
        if ch == "sign" and new:
            return name, f"sign it {new}"
        return None
    if name == "cancel":
        mw = words("merchant_words")
        return (name, mw) if mw else None
    if name == "post_act":
        act = ACTS.get(form.get("act"))
        if not act or not n_ans:
            return None
        pick = _num(form.get("pick"), 1, n_ans)
        if pick and said_number(pick, text):
            return name, f"{act} the {_ordinal(pick)} one" if _ordinal(pick) else f"{act} number {pick}"
        tw = words("target_words")
        # "that one", "ese restaurante": the helper's own rule for a pointer picks what is meant (never the model)
        pointer = f"{act} that one" if POINTER.search(text) else None
        if tw:
            return name, [f"{act} {tw}"] + ([pointer] if pointer else [])
        return (name, [pointer]) if pointer else None
    if name == "add_to_app":
        from .places import named
        app = words("app_words")
        if not app or not n_ans or named(f"to my {app}") is None:
            return None
        what = form.get("what")
        if what in ("ingredients", "list"):
            thing = "the ingredients"
        elif str(form.get("pick")).lower() == "all":
            thing = "them"
        else:
            pick = _num(form.get("pick"), 1, n_ans)
            if pick is None or not (said_number(pick, text) or (pick == 1 and POINTER.search(text))):
                return None   # a number the message does not say is never used; "this" is the first, as by code
            thing = f"the {_ordinal(pick)} one" if _ordinal(pick) else f"number {pick}"
        return name, f"add {thing} to my {app}"
    if name == "app_connection":
        op = form.get("op")
        if op == "list":
            return name, "what are you connected to"
        app = words("app_words")
        return (name, APP_OPS[op].format(app=app)) if op in APP_OPS and app else None
    if name == "what_did_you_do":
        return name, "what did you do for me"
    if name == "do_todo":
        if not n_todo:
            return None
        todo = form.get("todo")
        if str(todo).lower() == "all":
            return name, "do all of them"
        n = _num(todo, 1, n_todo)
        if n and said_number(n, text):
            return name, f"do {n} for me"
        tw = words("todo_words")
        return (name, {"words": tw}) if tw else None
    if name == "exports":
        plats = form.get("platforms") or []
        plats = [p for p in plats if p in ("instagram", "youtube")] if isinstance(plats, list) else []
        want = form.get("want")
        if want not in ("steps", "reminders", "automatic"):
            return None
        return name, {"platforms": plats, "want": want}
    return None


# ---------- the helper's own code entry ----------
def act(bot, person, name, what, text, now):
    """Hands the checked form to the helper's existing code entry. The reply's reference, or None when the helper
    did not take it (then the interpreter's answer is dispatched as before)."""
    from . import drafts as D
    h = person["handle"]
    if name == "email_other":
        req = {"to": what["to"], "word": what["word"], "name": what["name"], "group": what.get("group"),
               "request": D.sentence(what["say"]), "subject": None, "post": None, "cc": False}
        if what["to"] is None:
            draft_id = bot._new_draft_row(person, req, None, now, text)
            import json as _json
            p = _json.loads(bot._draft(draft_id)["parts"])
            return bot._draft_ask_to(person, draft_id, p, now)
        return bot.draft_start(person, "email", to=what["to"], to_name=what["name"], to_word=what["word"],
                               request=req["request"], now=now, text=text)
    if name == "email_self":
        if what["what"] == "draft":
            d = bot.open_draft(h, now)
            return bot._draft_to_self(person, d, now) if d is not None else None
        from .schema import Interpretation
        it = Interpretation.model_validate({"intent": "act_on_last", "actions": ["email.send"],
                                            **({"pick_number": what["pick"]} if what.get("pick") else {})})
        return bot._act_on_last(person, it, text, now)
    if name == "save_draft":
        d = bot.open_draft(h, now)
        return bot._save_to_drafts(person, d, now) if d is not None else None
    if name == "send_draft":   # never sends: what "send" would do now (merge of round 10: slice D's own read, with
        d = bot.open_draft(h, now)   # the route read again and the switch-on line for the operator)
        if d is None:
            return None
        return bot._draft_send_asked(person, d, now)
    if name == "change_draft":
        d = bot.open_draft(h, now)
        if d is None:
            return None
        if what.startswith("make it "):
            return bot._draft_tone(person, d, what, now)
        return bot._draft_change(person, d, what, now)
    if name == "cancel":
        from . import cancel as C
        entry = C.merchant_in(what)
        req = {"kind": "merchant", "entry": entry} if entry else \
            {"kind": "unknown", "name": C._clean_name(what) if hasattr(C, "_clean_name") else what}
        if not req.get("entry") and not req.get("name"):
            return None
        if not entry and C.CHANNEL_NAME.fullmatch(req["name"]):   # checks of round 10 (reading): "desuscríbeme de
            return None                                            # ese canal" is a channel, never a merchant
        return bot._cancel_start(person, req, text, now)
    if name == "post_act":   # the words named, then "that one" when the message points at what is shown
        for t in what:
            ref = bot.postact_reads(person, t, now)
            if ref is not None:
                return ref
        return None
    if name in ("add_to_app", "app_connection"):
        from .places import place_reads
        if name == "app_connection":   # second merge of round 10: YouTube's connection is slice Y's own read (5b)
            from .ytreads import youtube_reads
            ref = youtube_reads(bot, person, what, now)
            if ref is not None:
                return ref
        return place_reads(bot, person, what, now)
    if name == "what_did_you_do":
        return bot.receipts_reads(person, what, now)
    if name == "do_todo":
        if isinstance(what, dict):
            from .retrieve import _stem
            from .todos import SMALL, WORD
            want = {_stem(w) for w in WORD.findall(what["words"].lower()) if w not in SMALL}
            todos = bot.store.todos(h)
            hits = [(i, t) for i, t in enumerate(todos, 1)
                    if want and want <= {_stem(x) for x in WORD.findall(t["text"].lower())}]
            if not hits:
                return None
            if len(hits) > 1:
                return bot.send(h, T.which_todo(hits))
            return bot._do_todo(person, hits[0][0], hits[0][1], now, said=text)
        return bot.do_it(person, what, now)
    if name == "exports":
        from .refresh import export_text, library_status
        if what["want"] == "steps":
            return bot.send(h, library_status(bot, person, now, steps=True))
        words = "export my " + " and ".join(what["platforms"] or ["saves"]) + " regularly"
        msg = export_text(bot, person, words, now, kind="regular")
        return bot.send(h, msg) if msg else None
    return None


def try_errand(bot, person, it, text, now):
    """The errand form for a message the interpreter could not place: the helper's reply's reference, or None (the
    interpreter's answer then goes on as before)."""
    h = person["handle"]
    if not wanted(it, text) or getattr(bot._tl, "code_only", False) or getattr(bot._tl, "in_errand", False):
        return None
    if bot._over_cap(person) or _used_today(bot, person, now) >= per_day():
        return None
    state = state_word(bot, person, now)
    form = ask(bot, person, text, state, now)
    got = built(bot, person, form, text, state, now) if form else None
    name = (form or {}).get("errand") if (form or {}).get("errand") in ERRANDS else "none"
    if got is None:
        bot.store.log_action(h, None, None, "errand.form", "done", detail={"errand": name, "used": False,
                                                                          "state": state.split()[0]}, at=now)
        return None
    bot._tl.in_errand = True
    try:
        ref = act(bot, person, got[0], got[1], text, now)
    finally:
        bot._tl.in_errand = False
    bot.store.log_action(h, None, None, "errand.form", "done", detail={"errand": name, "used": ref is not None,
                                                                      "state": state.split()[0]}, at=now)
    if ref is not None:
        bot.note(intent=f"errand:{got[0]}")
    return ref
