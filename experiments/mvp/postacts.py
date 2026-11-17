"""PROTOTYPE ONLY - acting on a saved post (round 9, slice C: W8 and V1; DESIGN.md section 16.C). Mixed into core.Bot.

Read by code in `handler.answer_normally` (hook 7), before the model, only when the message points at something the
last answer showed (a number, a name, "it" by the existing rules); anything else goes on as before. No model call.

W8, what the bot can honestly prepare, and plain words for what it did not do:
- apply ("apply to the second one", "help me apply to NASA L'SPACE", "sign me up for 3", "register me for the
  workshop", "get me ready for the fellowship"): a menu of its deadline on the calendar with a reminder 3 days before,
  and a checklist of the post's own lines after a cue ("requirements", "you need", ...), each a verbatim run of its
  text. No date: the existing "Tell me the date" question. A date that has passed is said.
- book ("book it", "reserve the taco place", "book a table at the second one for saturday at 7"): Google Maps by the
  thing's checked name and one place word of the post's text (the domain is fixed here), and a calendar hold only at a
  day and time the person typed. A phone number in the post is shown, never used.
- buy ("buy the ingredients for the first one", "order these for me", "buy the lamp in the second one", "where can I
  buy it"): a recipe's checked ingredient lines go on the shopping list; a product gets the post's link (a price only
  from the post's own text, always with the month it was posted) and an offer to put it on the list.
The menus are numbered offers (offers.py). The bot never fills in a form, books, pays or orders, and never says it did.

V1, after an items answer (the things the posts name): "add them all", "add all of them to my reading list", "put all 6
on my list", "add 2, 4 and 5", "add the rest", "remind me about all of them on friday" (one later send),
"put them all in my calendar" (links only for things whose own words give a date ahead), and a question about a
numbered thing ("what's number 4?", "how long is the second one?"), answered from that thing's own words.
"""
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import texts as T
from .actions import perform
from .actions.base import Ctx, Outcome
from .followup import SHARE_ORDINAL, all_things, detail_kinds, numbers_in, thing_question
from .render import Reply
from .schema import list_name
from .store import now_iso

MAPS = "https://www.google.com/maps/search/"   # Google Maps URLs (documented); never a link from a post
THINGS_MAX = 12
HOLD_MINUTES = 90
DAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3,
        "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
_DAYW = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues|tue|wed|thurs|thur|thu|fri|sat|sun|" \
        r"today|tonight|tomorrow"
_ORD = r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|[4-9]th|10th"
# round 10, slice W (W5): "can i buy the first one"
_LEAD = (r"^\W*(?:(?:please|pls|can you|could you|would you|will you|ok|okay|so|and|hey|now"
         r"|can i|could i|i want to|i'd like to)[,\s]+)*")
_END = r"(?:\s+(?:for (?:me|us)|please|pls|thanks))*\s*[.!?]*\s*$"

APPLY = re.compile(_LEAD + r"(?:help me(?: to)?\s+|i (?:want|would like|'d like) to\s+)?"
                   r"(?P<verb>apply|sign me up|sign up|register me|enrol me|enroll me|get me ready)\b"
                   r"(?P<target>.*?)" + _END, re.I)
BOOK = re.compile(_LEAD + r"(?:help me\s+|i (?:want|would like|'d like) to\s+)?"
                  r"(?P<verb>book|reserve|make a reservation|make a booking|get (?:us|me) a table|grab (?:us|me) a table"
                  r"|get (?:us|me) (?:some\s+)?tickets?(?:\s+for)?|buy (?:us|me) tickets?(?:\s+for)?)"   # W5
                  r"\b(?P<target>.*?)" + _END, re.I)
BUY = re.compile(_LEAD + r"(?P<verb>buy|order|purchase|shop for|where can i (?:buy|get|order)|where do i (?:buy|get)|"
                 r"get me the (?:ingredients|stuff|groceries))\b(?P<target>.*?)" + _END, re.I)
# a message that asks for more than the act ("... and email me", "every friday") is the interpreter's
OTHER_ASK = re.compile(r"\b(?:remind|e-?mail|calendar|text me|every|daily|weekly|tomorrow at|share|forward)\b", re.I)
INGREDIENT_WORDS = re.compile(r"\b(?:ingredients?|groceries|grocery|the stuff|stuff for|recipe)\b", re.I)
VAGUE = re.compile(r"\b(?:somewhere|anywhere|some ?place|something|anything|a new|a good|a nice|a cheap|one of)\b",
                   re.I)
TABLE_WORDS = re.compile(r"\b(?:table|restaurant|reservation|dinner|lunch|brunch|breakfast)\b", re.I)
GENERIC = set("""it this that these those them one ones the a an restaurant restaurants place spot table programme
program workshop fellowship course class event thing things recipe product scholarship internship camp competition
contest job opportunity post video reel item""".split())
PRONOUNS = set("it its this that these those them one ones the a an".split())
# (round 9 live fix pass) a to-do that already says to apply (the menu's own "Apply to ..." or the person's words)
APPLY_ON_LIST = re.compile(r"^\W*(?:apply|sign\s+up|register|enrol+)\b", re.I)
_FILLER = re.compile(r"^(?:(?:me|us|a table|a spot|a seat|a reservation|a booking|a room|tickets?|a ticket|up)\b\s*|"
                     r"(?:at|for|to|in|into|with|on)\s+)+", re.I)
_WHEN = re.compile(rf"\s*(?:\b(?:on|this|next|for)\s+)*\b(?:{_DAYW})\b(?:\s+(?:at\s+)?\d{{1,2}}(?::\d\d)?\s*(?:am|pm)?)?"
                   rf"|\s*\b(?:at\s+)?\d{{1,2}}(?::\d\d)?\s*(?:am|pm)\b(?:\s+(?:on\s+)?(?:{_DAYW}))?"
                   rf"|\s*\bfor\s+(?:\d{{1,2}}|two|three|four|five|six)\s+(?:people|of us|persons)\b"
                   # (round 9 checks) "a table for 2" is how many people, never pick 2
                   rf"|\s*\b(?:a\s+)?table\s+for\s+(?:\d{{1,2}}|two|three|four|five|six)\b(?!\s*(?:st|nd|rd|th)\b)"
                   # round 10, slice W (W5): "at that place for 2 on friday": how many people, never pick 2
                   rf"|\s*\bfor\s+(?:\d{{1,2}}|two|three|four|five|six)\b(?=\s*(?:on\b|at\b|this\b|next\b|tonight\b|"
                   rf"tomorrow\b))", re.I)


# ---------- reading the message (code only) ----------
def request(text):
    """{verb, target, said} for an apply, book or buy request, else None. `target` is the words naming what it is about
    (number, name, generic); `said` the whole message, for the day and time a hold may use."""
    t = " ".join((text or "").split())
    if not t or len(t) > 200 or OTHER_ASK.search(t):
        return None
    for verb, rx in (("apply", APPLY), ("book", BOOK), ("buy", BUY)):
        m = rx.match(t)
        if not m:
            continue
        raw = m.group("target") or ""
        if VAGUE.search(raw):
            return None   # "book me a table somewhere nice": not about something shown
        if verb == "buy" and re.match(r"order", m.group("verb"), re.I) and re.search(r"\b(?:by|from)\b", raw, re.I):
            return None   # "order them by date" is not a purchase
        ingredients = verb == "buy" and bool(INGREDIENT_WORDS.search(m.group("verb") + " " + raw))
        return {"verb": verb, "target": target_of(raw, verb), "ingredients": ingredients, "said": t}
    return None


def target_of(raw, verb=None):
    """{number, name, generic} for the words after the verb ("the second one", "the taco place", "it")."""
    s = _WHEN.sub(" ", raw or "")
    s = " ".join(s.split()).strip(" ,.")
    s = _FILLER.sub("", s).strip(" ,.")
    s = re.sub(r"\s+(?:for|at|on|to)$", "", s, flags=re.I).strip()
    s = re.sub(r"^(?:the\s+)?(?:ingredients|groceries|stuff|things)(?:\s+(?:for|of|in|from)\s+|$)", "", s,
               flags=re.I).strip()
    m = re.match(r"^(?:the\s+)?[\w' -]{2,30}?\s+(?:in|from|of)\s+(?P<rest>(?:the\s+)?(?:" + _ORD +
                 r")(?:\s+one)?|#?\d{1,2}|it|this|that|this one|that one|number \d{1,2})$", s, re.I)
    if m:
        s = m.group("rest")
    low = s.lower()
    num = None
    mm = re.fullmatch(r"(?:the\s+)?(?:(?:number|no\.?|#)\s*)?(\d{1,2})(?:\s+one)?", low) or \
        re.fullmatch(rf"(?:the\s+)?({_ORD})(?:\s+one)?", low)
    if mm:
        w = mm.group(1)
        num = int(w) if w.isdigit() else (SHARE_ORDINAL.get(w) or int(re.sub(r"\D", "", w)))
    words = re.findall(r"[\w']+", low)
    generic = num is None and all(w in GENERIC for w in words)
    # "the workshop" is tried as a name first (a thing called "Design Workshop"), then as "it"
    name = s if num is None and any(w not in PRONOUNS for w in words) else None
    return {"number": num, "name": name, "generic": generic,
            "all": bool(re.fullmatch(r"(?:these|those|them|all of them)", low)), "said": bool(words)}


def day_time(text, today):
    """(date or None, 'HH:MM' or None) the person's own message names, read by code. A day of the week is the next one
    (today counts); an hour without am or pm from 1 to 10 is in the evening."""
    t = " ".join((text or "").split()).lower()
    day = None
    m = re.search(rf"\b(?:(next)\s+)?({_DAYW})\b", t)
    if m:
        w = m.group(2)
        if w in ("today", "tonight"):
            day = today
        elif w == "tomorrow":
            day = today + timedelta(days=1)
        else:
            delta = (DAYS[w] - today.weekday()) % 7
            day = today + timedelta(days=delta or (7 if m.group(1) else 0))
    else:
        from .dates import find_dates
        found = find_dates(text or "", year_hint=today.isoformat())
        if found:
            day = found[0][0]
    hhmm = None
    tm = re.search(r"\b(\d{1,2})(?::(\d\d))?\s*(am|pm|a\.m\.|p\.m\.)", t) or \
        re.search(rf"\b(?:{_DAYW})\s+at\s+(\d{{1,2}})(?::(\d\d))?\b()", t) or \
        re.search(rf"\bat\s+(\d{{1,2}})(?::(\d\d))?()(?=\s+(?:on\s+)?(?:{_DAYW})\b|\s*$)", t)
    if tm:
        h, mins, ap = int(tm.group(1)), int(tm.group(2) or 0), (tm.group(3) or "").replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif not ap and 1 <= h <= 10:
            h += 12
        if 0 <= h < 24 and 0 <= mins < 60:
            hhmm = f"{h:02d}:{mins:02d}"
    elif re.search(r"\b(?:noon|midday)\b", t):
        hhmm = "12:00"
    return day, hhmm


WHEN_ONLY = re.compile(rf"^[\s\"'(]*(?:(?:ok|okay|sure|yes|how about|maybe|make it)[,\s]+)*(?:on\s+|this\s+|next\s+)?"
                       rf"(?:(?:{_DAYW})\s*)?(?:at\s+)?(?:\d{{1,2}}(?::\d\d)?\s*(?:am|pm|a\.m\.|p\.m\.)?|noon)?"
                       rf"(?:\s+(?:on\s+)?(?:{_DAYW}))?\s*(?:please|pls)?\W*$", re.I)


def when_only(text):
    """True when the whole message is a day and/or a time ("7pm", "saturday at 7"), nothing more."""
    t = " ".join((text or "").split())
    return bool(t) and bool(WHEN_ONLY.match(t)) and bool(re.search(r"am\b|pm\b|a\.m\.|p\.m\.|noon|\bat\b|\b(?:"
                                                                  + _DAYW + r")\b", t, re.I))


CUE = re.compile(r"\b(?:requirements?|you(?:'ll)? need|you must|eligibility|eligible|to apply|submit|must)\b", re.I)
BULLET = re.compile(r"^\s*(?:[-•*·▪●◦–—✅✔☑️➡️👉🔹🔸]+|\d{1,2}[.)])\s*")
NOT_A_LINE = re.compile(r"@|https?://|www\.|\w\.[a-z]{2,}\b|\bdm\b|\bcomment\b|link in bio|\bfollow\b", re.I)
# (round 9 checks) a caption's line that asks the reader to pay, or to like, share, tag or text for the creator, is an
# instruction from the post, never a step of the person's own checklist
NOT_A_STEP = re.compile(r"[$€£]\s?\d|\d\s?(?:usd|eur|gbp|dollars?|euros?|bucks)\b|\b(?:pay|venmo|cash\s?app|paypal|"
                        r"zelle|wire|crypto|bitcoin|gift\s?cards?|tag|tagging|share|repost|retweet|like\s+(?:and|&|\+)|"
                        r"subscribe|giveaway|text\s+\S+\s+to|reply\s+\S+|message\s+me|inbox\s+me|click)\b", re.I)


def checklist_lines(text):
    """The post's own lines after a cue ("Requirements:", "you need"), each a verbatim run of its text, 3 to 120
    characters, at most 8; a line with "@", a link, "DM", "comment", "link in bio" or "follow" is left out."""
    lines = (text or "").split("\n")
    out = []
    for i, line in enumerate(lines):
        m = CUE.search(line)
        if not m:
            continue
        rest = line[m.end():]
        inline = rest.split(":", 1)[1].strip() if ":" in rest else ""
        if inline:   # "Requirements: transcript, one-page essay, a teacher's recommendation"
            out = [re.sub(r"^\s*(?:and|&)\s+", "", piece) for piece in re.split(r"[,;]", inline)]
        else:   # the lines under it, until a blank line (or a plain line after list lines)
            bullets = False
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    if out:
                        break
                    continue
                if bullets and not BULLET.match(nxt):
                    break
                bullets = bullets or bool(BULLET.match(nxt))
                out.append(BULLET.sub("", nxt))
        if out:
            break
    clean = []
    for x in out:
        x = x.strip().rstrip(".,;:!").strip()
        if 3 <= len(x) <= 120 and not NOT_A_LINE.search(x) and not NOT_A_STEP.search(x) and x in (text or "") \
                and x not in clean:
            clean.append(x)
    return clean[:8]


_NOT_PLACE = set("""January February March April May June July July August September October November December Monday
Tuesday Wednesday Thursday Friday Saturday Sunday The This That My Your Our Bio Stories Reels""".split())


# (round 9 checks) what follows 📍 is used only when it looks like a place name: at most 4 capitalised words (small
# joining words allowed), no digits; "📍 Click my bio for the address and call ..." is an instruction, not a place
PLACE_SHAPE = re.compile(r"^(?:[A-ZÀ-Þ][\w'’.-]*|de|del|da|do|la|le|les|los|las|el|di|du|of|on|upon|the|y|e|am|an|"
                         r"im|sur|in)(?:\s+(?:[A-ZÀ-Þ][\w'’.-]*|de|del|da|do|la|le|les|los|las|el|di|du|of|on|upon|the|"
                         r"y|e|am|an|im|sur|in)){0,3}$")


def place_word(text):
    """One place word of the post's own text: what follows 📍 (to the first comma), or "in <Capitalised>"."""
    m = re.search(r"📍\s*([^\n,|•]{2,40})", text or "")
    if m and m.group(1).strip() and not NOT_A_LINE.search(m.group(1)) and PLACE_SHAPE.match(m.group(1).strip()) \
            and not re.search(r"\d", m.group(1)):
        return m.group(1).strip()
    for m in re.finditer(r"\bin ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)", text or ""):
        if m.group(1).split()[0] not in _NOT_PLACE:
            return m.group(1)
    return None


def maps_link(name, place=None):
    """https://www.google.com/maps/search/?api=1&query=<name> <place>: the domain is fixed here, the words encoded."""
    q = " ".join(x for x in (name, place) if x)
    return MAPS + "?" + urlencode({"api": "1", "query": q})


PHONE = re.compile(r"(?<![\w/])\+?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\w)|(?<![\w/])\+\d{1,3}[\s.-]?\d{2,4}[\s.-]\d{3,4}"
                   r"[\s.-]?\d{3,4}(?!\w)")
PRICE = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d\d)?|\d[\d,]*(?:\.\d\d)?\s?(?:USD|EUR|GBP|dollars))")


def phone_in(text):
    m = PHONE.search(text or "")
    return m.group(0).strip() if m else None


def price_in(text):
    """The one price the text gives, or None (none, or more than one: then it is not said whose it is)."""
    found = list(dict.fromkeys(m.group(0).strip() for m in PRICE.finditer(text or "")))
    return found[0] if len(found) == 1 else None


_THINGS_LEAD = _LEAD
ADD_THINGS = re.compile(_THINGS_LEAD + r"(?P<verb>add|put|save|stick|throw|pop|jot down)\s+(?P<target>.+?)"
                        r"(?:\s+(?:to|on|in|into|onto)\s+(?:(?P<cal>my\s+calendar|the\s+calendar)|"
                        r"(?:my|the)\s+(?P<list>[\w' -]{0,30}?)\s*(?:list|to-?do list|to-?dos|todos|todo)))?" + _END,
                        re.I)
REMIND_THINGS = re.compile(_THINGS_LEAD + r"remind me (?:about|of)\s+(?P<target>.+?)\s+(?P<when>(?:(?:on|this|next)\s+)?"
                           rf"(?:{_DAYW})(?:\s+(?:at\s+)?\d{{1,2}}(?::\d\d)?\s*(?:am|pm)?)?|(?:at\s+)?\d{{1,2}}(?::\d\d)?"
                           rf"\s*(?:am|pm)(?:\s+(?:on\s+)?(?:{_DAYW}))?)" + _END, re.I)


def things_request(text):
    """{verb: add | calendar | remind, all, n_said, numbers, rest, list, when} for an act on several things of an
    items answer, else None (one thing, or no list of them, stays as before)."""
    t = " ".join((text or "").split())
    if not t or len(t) > 160:
        return None
    m = REMIND_THINGS.match(t)
    verb = "remind" if m else None
    if not m:
        m = ADD_THINGS.match(t)
        if not m:
            return None
        verb = "calendar" if m.group("cal") else "add"
    target = m.group("target").strip(" ,.")
    rest = bool(re.fullmatch(r"(?:the\s+)?(?:rest|others|other ones)(?:\s+of\s+them)?", target, re.I))
    al = all_things(target)
    nums = None if al or rest else numbers_in(target)
    if not (al or rest or nums):
        return None
    if rest and verb != "add":
        return None
    name = list_name(m.group("list")) if verb == "add" and m.groupdict().get("list") is not None else "todo"
    return {"verb": verb, "all": bool(al) or rest, "n_said": al[1] if al else None, "numbers": nums, "rest": rest,
            "list": name or "todo", "when": m.group("when") if verb == "remind" else None}


# ---------- the mixin ----------
class PostactsMixin:
    def postact_reads(self, person, text, now):
        """Hook 7 (verdict section 4): V1's acts on the things of an items answer and its numbered-thing question,
        then W8's apply, book and buy. The reply's reference, or None when the message is not one of these about
        something the last answer showed."""
        h = person["handle"]
        last = self._answer_for(h)
        if not last or not last.get("items"):
            return None
        self._tl.msg_text = text
        snap = self.store.answer(last["run_id"]) or {}
        things = sorted(((x, p) for p in snap.get("picks") or [] for x in p.get("items") or []),
                        key=lambda r: r[0].get("n") or 0)
        if things:
            req = things_request(text)
            if req:
                return self._things_act(person, snap, things, req, text, now)
            n = thing_question(text)
            if n is not None and not detail_kinds(text):
                self.note(intent="follow_up")
                return self.thing_reply(person, snap, n)
        req = request(text)
        if not req:
            return None
        if not req["target"].get("said", True) and not (req["verb"] == "buy" and req["ingredients"]):
            # (round 9 checks) "book me a table", "book a table for 2": nothing shown is pointed at ("it", a number, a
            # name), so it is not about the answer (a pasta recipe is never a place to book); the usual path reads it
            return None
        got = self._postact_target(h, last, snap, things, req)
        if got is None:
            return None
        self.note(intent="postact")
        self.store.set_state(f"offers:{h}", None)   # a new request: an older menu's numbers mean nothing now
        rec, n_post, problem = got
        if problem:
            return self.send(h, problem)
        if req["verb"] == "apply":
            return self._apply_menu(person, rec, snap, text, now)
        if req["verb"] == "book":
            return self._book_menu(person, rec, snap, text, now)
        return self._buy(person, rec, n_post, snap, req, text, now)

    # ---------- what the message points at ----------
    def _postact_target(self, h, last, snap, things, req):
        """(rec, post number or None, problem) by the existing rules, or None when it points at nothing shown."""
        from .compose import tokens
        from .retrieve import _stem
        tgt = req["target"]
        main = [n for n, iid in enumerate(last["items"], 1)
                if next((p for p in snap.get("picks") or [] if p.get("item_id") == iid), {}).get("main", True)] \
            or list(range(1, len(last["items"]) + 1))
        if tgt["number"] is not None:
            if things:
                got = self._answer_item(snap, [tgt["number"]])
                picks, _, _, problem = got
                return (None, None, problem) if problem else (picks[0], None, None)
            picks, _, _, problem = self._answer_picks(h, [tgt["number"]])
            return (None, None, problem) if problem else (picks[0], tgt["number"], None)
        if tgt["name"]:
            if things:
                self._tl.msg_text = tgt["name"]
                got = self._answer_item(snap, None)
                self._tl.msg_text = req["said"]
                if got is not None and not got[3]:
                    return got[0][0], None, None
            said = {_stem(w) for w in tokens(tgt["name"]) if w not in PRONOUNS and w not in self.ITEM_NAME_SKIP}
            scored = []
            for n in main:
                iid = last["items"][n - 1]
                p = next((q for q in snap.get("picks") or [] if q.get("item_id") == iid), {})
                hits = len(said & {_stem(w) for w in tokens(p.get("title") or "") if len(w) >= 3 or w.isupper()})
                if hits:
                    scored.append((hits, n))
            scored.sort(key=lambda r: (-r[0], r[1]))
            if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                n = scored[0][1]
                picks, _, _, problem = self._answer_picks(h, [n])
                return (None, None, problem) if problem else (picks[0], n, None)
            if not tgt["generic"]:
                return None   # a name nothing shown matches: the interpreter reads it
        if things:   # "it", "the restaurant": the only thing, else which one
            if len(things) == 1:
                return self._thing_rec(*things[0]), None, None
            return None, None, T.which_item(len(things))
        if len(main) > 1 and tgt.get("all") and req["verb"] != "buy":
            return None, None, T.which_pick(len(main))
        n = main[0]   # "it" is the pick the answer opened with (outputs.lead_only)
        picks, _, _, problem = self._answer_picks(h, [n])
        return (None, None, problem) if problem else (picks[0], n, None)

    def _post_text(self, person, rec):
        it = self.view(person["library"]).get(rec.get("item_id"))
        return (getattr(it, "raw_caption", None) or getattr(it, "caption", None) or "") if it else ""

    def _post_link(self, rec):
        if not rec.get("url"):
            return None
        return {"type": "link", "url": rec["url"], "title": rec.get("source_title") or rec.get("title"),
                "platform": rec.get("platform"), "video_id": rec.get("video_id")}

    def _menu(self, h, verb, head, offers, notes, rec, snap, text, now, tail=(), ask=None, last=()):
        """Sends a numbered menu and keeps its offers (offers.py). `last`: lines after the reply line."""
        lines = [head] + [f"{i}. {o['text']}" for i, o in enumerate(offers, 1)] + list(notes)
        parts = [{"type": "text", "text": "\n".join(lines)}]
        link = self._post_link(rec)
        if link:
            parts += [{"type": "text", "text": T.POST_LINK_HEAD}, link]
        end = list(tail) + ([T.offers_reply_line(len(offers))] if offers else []) + list(last)
        if end:
            parts.append({"type": "text", "text": "\n".join(end)})
        self.offers_open(h, verb, [dict(o, verb=verb) for o in offers], text, now, run_id=snap.get("run_id"), ask=ask)
        self.store.log_action(h, snap.get("run_id"), None, "postact.menu", "done",
                              detail={"verb": verb, "offers": len(offers)}, at=now)
        return self.send(h, Reply(parts))

    # ---------- W8: apply ----------
    def _remind_at(self, day, days, now, tz):
        """The 9am `days` before `day`, or the next 9am while it is still before the day; None when none is left."""
        from .schedule import _at
        zone = ZoneInfo(tz)
        today = now.astimezone(zone).date()
        at = _at(day - timedelta(days=days), "09:00", zone)
        if at <= now:
            at = _at(today, "09:00", zone)
            if at <= now:
                at = _at(today + timedelta(days=1), "09:00", zone)
        return at if at.astimezone(zone).date() <= day else None

    def _apply_menu(self, person, rec, snap, text, now):
        from .dates import say_day
        from .schedule import say_time
        h, tz = person["handle"], person["timezone"]
        today = now.astimezone(ZoneInfo(tz)).date()
        name = rec.get("title") or "it"
        day = self._thing_date(rec, now, person)
        deadline = self._is_deadline(rec, person) if day else True
        offers, notes = [], []
        if day is not None and day >= today:
            at = self._remind_at(day, 3, now, tz)
            offers.append({"kind": "deadline", "text": T.apply_deadline_offer(
                deadline, say_day(day, today), say_time(at, now, tz) if at else None, 3),
                "params": {"rec": rec, "day": day.isoformat(), "deadline": deadline, "days": 3}})
        elif day is not None:
            notes.append(T.apply_passed(deadline, say_day(day, today)))
        last = []
        if day is None and not self._apply_on_list(h, rec):
            # (round 9 live fix pass, finding 108) no date: still what the bot can do now, as a numbered menu like the
            # dated case: the to-do "Apply to <name>" with the post's link first (not when it is on the list already:
            # W10 hands such a to-do to this menu)
            offers.append({"kind": "todo", "text": T.apply_todo_offer(name),
                           "params": {"rec": dict(rec, title=T.apply_todo_text(name))}})
        lines = self._checklist_for(person, rec, snap)
        if lines:
            offers.append({"kind": "checklist", "text": T.apply_checklist_offer(lines),
                           "params": {"rec": dict(rec, checklist=lines), "list": name}})
        date_ask = None
        if day is None:   # the existing question; the next message's date sets the reminder (handler._asked_reads)
            date_ask = {"rec": rec, "run_id": snap.get("run_id"), "days": 3, "calendar": True,
                        "text": " ".join(text.split())[:300], "at": now_iso(now)}
            self.store.set_state(f"deadline_ask:{h}", date_ask)
            if offers:   # the date question is the menu's last line
                last.append(T.APPLY_ASK_DATE)
            else:
                notes.append(T.deadline_ask(name))
        if not offers:
            msg = Reply([{"type": "text", "text": T.APPLY_CANT + " " + " ".join(notes)}])
            link = self._post_link(rec)
            if link and day is not None:
                msg = msg + Reply([link])
            self.store.log_action(h, snap.get("run_id"), None, "postact.menu", "done",
                                  detail={"verb": "apply", "offers": 0}, at=now)
            return self.send(h, msg)
        src = f"from \"{rec['source_title']}\"" + (f" by {rec['creator']}" if rec.get("creator") else "") \
            if rec.get("source_title") else "from your saves"
        ref = self._menu(h, "apply", T.apply_head(name, src), offers, notes, rec, snap, text, now, last=last)
        if date_ask:
            # the date question stays open after a choice from the menu ("1", then "dec 5"): offers.offer_reads asks
            # it again once the choice has run (handler._asked_reads reads only the next message)
            st = self.store.get_state(f"offers:{h}")
            if st:
                self.store.set_state(f"offers:{h}", dict(st, date_ask=date_ask))
        return ref

    def _apply_on_list(self, h, rec):
        """An open to-do from the same post that says apply ("Apply to <name>"), already on the person's list."""
        return any(t.get("item_id") == rec.get("item_id") and APPLY_ON_LIST.match(t.get("text") or "")
                   for t in self.store.todos(h)) if rec.get("item_id") else False

    def _checklist_for(self, person, rec, snap):
        """Checklist lines from the post's own text, only when the post is about this one thing (a post naming several
        things may list another one's requirements)."""
        if rec.get("item"):
            p = next((q for q in snap.get("picks") or [] if q.get("item_id") == rec["item_id"]), {})
            if len(p.get("items") or []) > 1:
                return []
        return checklist_lines(self._post_text(person, rec))

    # ---------- W8: book ----------
    def _book_menu(self, person, rec, snap, text, now, when_text=None):
        """`when_text`: the person's own message when `text` is not theirs (W10 passes a to-do's words, which came
        from a post's title): a hold's day and time are only ever read from what the person typed."""
        from .schedule import _at
        h, tz = person["handle"], person["timezone"]
        zone = ZoneInfo(tz)
        today = now.astimezone(zone).date()
        name = rec.get("title") or "it"
        post = self._post_text(person, rec)
        place = place_word(post)
        url = maps_link(name, place)
        offers = [{"kind": "maps", "text": T.maps_offer(url), "params": {"name": name, "url": url}}]
        notes = [] if place else [T.MAPS_NAME_ONLY]
        day, hhmm = day_time(text if when_text is None else when_text, today)   # the person's words only
        ask = None
        if day and hhmm:
            start = _at(day, hhmm, zone)
            if start <= now and day != today:
                start += timedelta(days=7)
            if start > now:
                offers.append({"kind": "hold", "text": T.hold_offer(hold_words(start, tz)),
                               "params": {"rec": rec, "date": start.astimezone(zone).date().isoformat(), "time": hhmm,
                                          "name": name}})
        elif day:
            notes.append(T.book_ask_time(f"{day:%A}"))
            ask = {"kind": "hold", "day": day.isoformat(), "rec": rec, "name": name}
        else:
            notes.append(T.BOOK_ASK_WHEN)
            ask = {"kind": "hold", "day": None, "rec": rec, "name": name}
        phone = phone_in(post)
        if phone:
            notes.append(T.post_number(phone))
        return self._menu(h, "book", T.book_head(name, bool(TABLE_WORDS.search(text))), offers, notes, rec, snap,
                          text, now, tail=[T.BOOK_EMAIL_HINT], ask=ask)

    def offer_answer(self, person, st, text, now):
        """The answer to the book menu's "What time?" / "tell me when": a day and a time make the hold at once (the
        person asked for it), else None."""
        from .schedule import _at
        ask = st.get("ask") or {}
        if ask.get("kind") != "hold" or not when_only(text):
            return None
        h, tz = person["handle"], person["timezone"]
        zone = ZoneInfo(tz)
        today = now.astimezone(zone).date()
        day, hhmm = day_time(text, today)
        day = day or (date.fromisoformat(ask["day"]) if ask.get("day") else None)
        if not day or not hhmm:
            return self.send(h, T.book_ask_time(f"{day:%A}") if day else T.BOOK_ASK_WHEN)
        start = _at(day, hhmm, zone)
        if start <= now and day != today:
            start += timedelta(days=7)
        if start <= now:
            return self.send(h, T.HOLD_PASSED)
        o = {"n": 0, "kind": "hold", "verb": "book", "params": {"rec": ask["rec"], "name": ask["name"], "time": hhmm,
                                                               "date": start.astimezone(zone).date().isoformat()}}
        self.note(intent="offer")
        ref = self.offers_run(person, st, [o], now)
        self.store.set_state(f"offers:{h}", dict(st, ask=None))
        return ref

    # ---------- W8: buy ----------
    def _buy(self, person, rec, n_post, snap, req, text, now):
        from .actions import todo as todo_action
        from .dates import month_year, posted_on
        h = person["handle"]
        facts = rec.get("facts") or {}
        recipe = n_post is not None and (req["ingredients"] or facts.get("ingredients")
                                          or rec.get("line_kinds") == ["ingredients"])
        if recipe:
            picks, _, answer, problem = self._answer_picks(h, [n_post], what="ingredients")
            if problem:
                return self.send(h, problem)
            rows, why = todo_action.rows_for(picks, "ingredients")
            if why or not rows:
                return self.send(h, T.BUY_CANT + " " + T.NO_INGREDIENTS)
            ctx = self._postact_ctx(person, answer or snap, picks, text, now)
            o = self._postact_do(ctx, "todo.add", {"what": "ingredients", "list": "shopping"},
                                 {"what": "ingredients", "count": len(rows)})
            if o.status != "done":
                return self.send(h, T.BUY_CANT + " " + (o.line or T.ACTION_FAILED_OTHER))
            return self.send(h, T.buy_ingredients([r[0] for r in rows]) + " " + T.undo_line("them"))
        name = rec.get("title") or "it"
        x = rec.get("item") or {}
        words = " ".join(t for t in (x.get("about"), x.get("when")) if t) if x else self._post_text(person, rec)
        price = price_in(words)
        posted = rec.get("posted")
        if not posted:
            it = self.view(person["library"]).get(rec.get("item_id"))
            posted = posted_on(it) if it else None
        month = month_year(posted) if posted else None
        head = T.buy_product(name, price, month) if price and month else T.buy_product(name)
        offer = {"kind": "todo", "text": "", "params": {"rec": rec}, "verb": "buy"}
        self.offers_open(h, "buy", [offer], text, now, run_id=snap.get("run_id"))
        self.store.log_action(h, snap.get("run_id"), None, "postact.menu", "done",
                              detail={"verb": "buy", "offers": 1}, at=now)
        parts = [{"type": "text", "text": head}]
        link = self._post_link(rec)
        if link:
            parts.append(link)
        parts.append({"type": "text", "text": T.BUY_LIST_OFFER})
        return self.send(h, Reply(parts))

    # ---------- running the offers chosen (offers.py calls this) ----------
    def _postact_ctx(self, person, answer, picks, text, now):
        return Ctx(bot=self, person=person, answer=answer or {}, picks=picks, whole=False,
                   run_id=(answer or {}).get("run_id"), rule_id=None, kind="act_on_last", now=now,
                   tz=person["timezone"], request_text=text or "")

    def _postact_do(self, ctx, name, params, detail):
        """One registry action, logged with counts only (never a name or a line of the post)."""
        try:
            o = perform(name, ctx, params)
        except Exception as e:  # noqa: BLE001 - one failed action never loses the others
            o = Outcome("failed", line=T.ACTION_FAILED.get(name, T.ACTION_FAILED_OTHER),
                        detail={"error": type(e).__name__})
        d = dict(detail or {})
        if (o.detail or {}).get("error"):
            d["error"] = o.detail["error"]
        self.store.log_action(ctx.handle, ctx.run_id, None, name, o.status, ref=o.ref, detail=d, at=ctx.now)
        return o

    def offers_run(self, person, st, chosen, now):
        """Each chosen offer through its own code path; one line each, then what the bot did not do and the undo."""
        from .dates import say_day
        from .schedule import say_time
        from .schema import When
        h, tz = person["handle"], person["timezone"]
        today = now.astimezone(ZoneInfo(tz)).date()
        answer = (self.store.answer(st["run_id"]) if st.get("run_id") else None) or {}
        text = st.get("text") or ""
        parts, writes, undoable, verb = [], [], [], None

        def line(s, link=None):
            parts.append({"type": "text", "text": s})
            if link:
                parts.append(link)

        def wrote():
            lw = self.store.get_state(f"lastwrite:{h}")
            if lw and lw not in writes:
                writes.append(lw)

        before = self.store.get_state(f"lastwrite:{h}")
        for o in chosen:
            verb = o.get("verb") or verb
            k, p = o["kind"], o.get("params") or {}
            if k == "deadline":
                rec, day = p["rec"], date.fromisoformat(p["day"])
                if day < today:
                    line(T.apply_passed(p.get("deadline", True), say_day(day, today)))
                    continue
                ctx = self._postact_ctx(person, answer, [rec], text, now)
                c = self._postact_do(ctx, "calendar.add", {"date": day.isoformat()}, {"kind": "deadline"})
                if c.status == "done":
                    line(T.done_deadline(p.get("deadline", True), say_day(day, today)), c.link)
                    self._wrote_final(h, "a calendar link")
                    wrote()
                elif c.line:
                    line("• " + c.line)
                at = self._remind_at(day, p.get("days") or 3, now, tz)
                if at is not None:
                    got = self._later_rule(person, [rec], answer, [("message.send", {})],
                                           When(type="once", date=at.astimezone(ZoneInfo(tz)).date().isoformat(),
                                                time="09:00"), text, now)
                    if isinstance(got, str):
                        line("• " + got)
                    else:
                        rule_id, nxt, _, _ = got
                        self.store.set_state(f"deadline:{rule_id}", {"date": day.isoformat(),
                                                                     "deadline": p.get("deadline", True)})
                        line(T.done_reminder(say_time(nxt, now, tz), self.store.rule_number(h, rule_id)))
                        wrote()
                        undoable.append("the reminder")
            elif k == "checklist":
                rec = p["rec"]
                ctx = self._postact_ctx(person, answer, [rec], text, now)
                c = self._postact_do(ctx, "todo.add", {"what": "checklist", "list": list_name(p["list"]) or "todo"},
                                     {"what": "checklist", "count": len(rec.get("checklist") or [])})
                if c.status == "done":
                    line(T.done_checklist(rec.get("checklist") or [], p["list"]))
                    wrote()
                    undoable.append("the list")
                else:
                    line("• " + (c.line or T.ACTION_FAILED_OTHER))
            elif k == "maps":
                line(T.done_maps(p["name"], p["url"]))
            elif k == "hold":
                rec = dict(p["rec"], title=f"{p['name']} (hold)"[:100])
                ctx = self._postact_ctx(person, answer, [rec], text, now)
                c = self._postact_do(ctx, "calendar.add", {"date": p["date"], "time": p["time"],
                                                           "duration_min": HOLD_MINUTES}, {"kind": "hold"})
                if c.status == "done":
                    from .schedule import _at
                    line(T.done_hold(hold_words(_at(date.fromisoformat(p["date"]), p["time"], ZoneInfo(tz)), tz)),
                         c.link)
                    self._wrote_final(h, "a calendar link")
                    wrote()
                else:
                    line("• " + (c.line or T.ACTION_FAILED_OTHER))
            elif k == "todo":
                ctx = self._postact_ctx(person, answer, [p["rec"]], text, now)
                c = self._postact_do(ctx, "todo.add", {"what": "pick", "list": "todo"}, {"what": "pick", "count": 1})
                said = c.line or T.ACTION_FAILED_OTHER
                line(said if len(chosen) == 1 and verb == "buy" else T.done_todo(said))
                if c.status == "done":
                    wrote()
                    undoable.append("it")
        writes = [w for w in writes if w != before]
        if len(writes) > 1:   # one message, one "undo": the reminder and the list come off, the links stay (said)
            self.store.set_state(f"lastwrite:{h}", {"kind": "multi", "say": " and ".join(w["say"] for w in writes),
                                                    "undo": {"writes": writes}, "at": now_iso(now)})
        end = {"apply": T.APPLY_DONE_END, "book": T.BOOK_DONE_END}.get(verb)
        tail = [end] if end else []
        if undoable:
            tail.append(T.undo_line(T.and_words(list(dict.fromkeys(undoable)))))
        headed = len(chosen) > 1 or verb != "buy"   # "Here's what I set up:" and a bullet each; one plain line else
        out, cur = [], T.DONE_HEAD if headed else ""
        for q in parts:   # one bullet a line, a link alone right after its line
            if q["type"] == "link":
                out += [{"type": "text", "text": cur}, q]
                cur = ""
            else:
                cur = (cur + "\n" + q["text"]) if cur else q["text"]
        cur = (cur + ("\n" if headed else " ") + " ".join(tail)) if cur and tail else (cur or " ".join(tail))
        out.append({"type": "text", "text": cur})
        return self.send(h, Reply(out))

    # ---------- V1: the things of an items answer ----------
    def thing_reply(self, person, snap, n):
        """A question about thing n: its own words, the post it is in and its link. No model call."""
        h = person["handle"]
        its = sorted(((x, p) for p in snap.get("picks") or [] for x in p.get("items") or []),
                     key=lambda r: r[0].get("n") or 0)
        if self._numbered_twice(its):
            return self.send(h, T.THINGS_BY_POST)   # (round 9 checks) "number 2" could be either post's
        hit = next(((x, p) for x, p in its if x.get("n") == n), None)
        if hit is None:
            return self.send(h, T.which_item(len(its)))
        x, p = hit
        msg = T.thing_words(x.get("name") or "It", x.get("about"), x.get("when"), p.get("title"), p.get("creator"))
        parts = [{"type": "text", "text": msg}]
        if p.get("url") and p.get("title"):
            parts.append({"type": "link", "url": p["url"], "title": p.get("title"), "platform": p.get("platform"),
                          "video_id": p.get("video_id")})
        return self.send(h, Reply(parts))

    def _things_act(self, person, snap, things, req, text, now):
        from .actions import todo as todo_action
        h, tz = person["handle"], person["timezone"]
        self.note(intent="act_on_last")
        total = len(things)
        if req["n_said"] and req["n_said"] != total:
            return self.send(h, T.things_count_off(total))
        picks, _, _, problem = self._answer_items(snap, req["numbers"], all_things=req["all"])
        if problem:
            return self.send(h, problem)
        if req["verb"] == "remind":
            from .schedule import say_time
            from .schema import When
            today = now.astimezone(ZoneInfo(tz)).date()
            day, hhmm = day_time(req["when"], today)
            if day is None:
                day = today
            picks = picks[:10]
            when = When(type="once", date=day.isoformat(), time=hhmm or "09:00")
            got = self._later_rule(person, picks, snap, [("message.send", {})], when, text, now)
            if isinstance(got, str):
                return self.send(h, got)
            rule_id, nxt, _, _ = got
            return self.send(h, T.things_later(say_time(nxt, now, tz), len(picks), self.store.rule_number(h, rule_id)))
        if req["verb"] == "calendar":
            return self._things_calendar(person, snap, picks, text, now)
        name = req["list"]
        where = "your list" if name in (None, "todo") else f"your {name} list"
        open_on = {(t.get("text") or "").strip().casefold() for t in self.store.todos(h)
                   if (t.get("list") or "todo") == name}
        new = [p for p in picks if (p.get("title") or "").strip().casefold() not in open_on]
        already = [p["title"] for p in picks if (p.get("title") or "").strip().casefold() in open_on]
        new = list({(p["title"] or "").casefold(): p for p in new}.values())   # the same name twice: once
        if not new:
            return self.send(h, T.things_all_on(where))
        rest = max(0, len(new) - THINGS_MAX)
        new = new[:THINGS_MAX]
        o = todo_action.add(self, person, new, "pick", name)
        self.store.log_action(h, snap.get("run_id"), None, "todo.add", o.status, ref=o.ref,
                              detail={"count": len(new), "from": "things", "already": len(already)}, at=now)
        if o.status != "done":
            return self.send(h, o.line or T.ACTION_FAILED_OTHER)
        return self.send(h, T.things_added([p["title"] for p in new], where, already if not req["rest"] else (),
                                           rest, listed=req["all"]))

    def _things_calendar(self, person, snap, picks, text, now):
        """"put them all in my calendar": a link for each thing whose own words give a date ahead; the rest said."""
        from .dates import say_day
        h, tz = person["handle"], person["timezone"]
        today = now.astimezone(ZoneInfo(tz)).date()
        ahead, passed, missing = [], 0, 0
        for rec in picks:
            day = self._thing_date(rec, now, person)
            if day is None:
                missing += 1
            elif day < today:
                passed += 1
            else:
                ahead.append((rec, day))
        links, found = [], []
        for rec, day in ahead[:THINGS_MAX]:
            ctx = self._postact_ctx(person, snap, [rec], text, now)
            c = self._postact_do(ctx, "calendar.add", {"date": day.isoformat()}, {"kind": "thing"})
            if c.status == "done" and c.link:
                links.append(c.link)
                found.append((rec["title"], say_day(day, today)))
        head, tail = T.things_dates(found, missing, passed)
        if links:
            self._wrote_final(h, "a calendar link")
        parts = [{"type": "text", "text": head}] + links + ([{"type": "text", "text": tail}] if tail else [])
        return self.send(h, Reply(parts))


def hold_words(start, tz):
    """'Saturday 14 November at 7pm' (the person's zone)."""
    a = start.astimezone(ZoneInfo(tz))
    clock = a.strftime("%-I:%M%p").lower().replace(":00", "")
    return f"{a:%A %-d %B} at {clock}"
