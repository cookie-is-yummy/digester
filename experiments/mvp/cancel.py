"""PROTOTYPE ONLY - the cancel helper (round 9, slice B: W5, W6; DESIGN.md section 16.B; amendment A-012, Proposed).

"Cancel my netflix", "how do I get out of my gym membership": read by code before the model (no model call, no
prompt). The bot never signs in as the person and never asks for a password; it finds the way out from a checked
file (cancel_routes.json: a link only when the merchant's own help page was read on the day it records, and for 60
days after), writes a notice when a written notice is the way, and offers a check reminder that the person times.
It never says the subscription is cancelled or done: only the merchant can say that.

Money is a sensitive category (docs/07): what a person ends is kept in the `cancellations` table only (no amounts,
no account numbers), never sent to a model, never in the recap or the MCP server, and never in action_log detail
(detail is `{route, known}`). A merchant name from a caption or a saved post never picks a route: only the person's
own words do.

Module functions are pure (they read text and the route file); CancelMixin (in core.Bot) talks and stores.
"""
import json
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import texts as T

ROUTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cancel_routes.json")
LINK_DAYS = 60           # a link checked longer ago than this is not given; the steps are
ASK_HOURS = 24           # a question the helper asked is answered by the next message, within this
SAID_DONE_DAYS = 7       # "I cancelled it" refers to a cancel reply this recent

# ---------- the trigger (W5) ----------
CANCEL_VERB = re.compile(r"\b(?:cancel|cancelling|canceling|unsubscribe me from|unsubscribe from|get out of|"
                         r"stop paying for)\b|\b(?:end|quit|close)\s+(?:my|the|our)\b|"
                         r"\bhow (?:do|can|would|should) i (?:cancel|end|stop|quit|get out of)\b"
                         # ---------- round 10, slice W (W5): "get rid of my hulu", "drop my ... subscription" ----------
                         r"|\bget rid of (?:my|the|our)\b"
                         r"|\bdrop (?:my|the|our)\b(?=.*\b(?:subscriptions?|memberships?|plan|trial)\b)", re.I)
# round 10, slice W (W5): a question about the library is never a cancel request ("any videos on how to cancel
# subscriptions", "im thinking of cancelling netflix, did i save anything ..."); "how do i cancel my netflix" still is
LIBRARY_ASK = re.compile(r"\b(?:did i save|have i saved|i saved anything|anything i saved|any (?:videos?|reels?|posts?|"
                         r"tips?)\b|show me\b|^\W*find\b|\bfind (?:me )?(?:the|a|some)\b|what did i save|reels? about|"
                         r"videos? about|posts? about)", re.I)
HOW_TO_CANCEL_ANY = re.compile(r"\bhow to (?:cancel|unsubscribe)\b(?!.*\bmy\b)", re.I)
# W5: a stop or pause the model read from a message about a subscription counts as a cancel verb there
FORCED_VERB = re.compile(r"\b(?:stop|pause|turn off|end|cancel)\b", re.I)
SUB_WORD = re.compile(r"\b(?:subscriptions?|memberships?|free trial|trial|auto-?renew(?:al)?)\b", re.I)
GYM_SAID = re.compile(r"\bmy gym\b|\bgym (?:membership|contract|plan)\b", re.I)
# never a cancel: a rule, a reminder, the bot's own sends, or the picks it sends
NOT_CANCEL = re.compile(r"\b(?:rules?|reminders?|nudges?|list|lists|to-?dos?|digest|recap|texts?|texting|messages?|"
                        r"messaging|emails? from you|notifications?|send|sends|sending|sent|recommendations?|recommend|"
                        r"suggestions?|picks?|ideas?|remind\w*|e-?mails?|newsletters?|mailing lists?)\b", re.I)
BARE = re.compile(r"^\W*(?:cancel|cancel it|cancel that|cancel this|unsubscribe|unsubscribe me)(?:\s+please)?\W*$",
                  re.I)
ONLY_NUMBER = re.compile(r"^\W*(?:cancel|end|stop|pause|close|quit)\s+(?:rule\s+|number\s+|#\s*)?\d{1,2}\W*$", re.I)
CARD = re.compile(r"\b(?:credit card|debit card|bank account|checking account|savings account|my (?:[\w&'-]+ )?card)\b",
                  re.I)
PRODUCT = re.compile(r"\b(?:meal kits?|kits?|box|boxes|apps?|services?|deliver(?:y|ies))\b", re.I)
FROM_SAVED = re.compile(r"\b(?:from|in|on)\s+(?:that|the|this|an?)\s+(?:ad|advert|post|reel|video)\b|\bi saved\b", re.I)
_NAME_BEFORE = re.compile(r"\b(?:my|the|our|this|that)\s+([\w&+.'-]+(?:\s+[\w&+.'-]+){0,3}?)\s+"
                          r"(?:subscriptions?|memberships?|free trial|trial|account|plan)\b", re.I)
_NAME_AFTER = re.compile(r"\b(?:unsubscribe me from|unsubscribe from|cancel|end|quit|get out of|stop paying for|close)"
                         r"\s+(?:my\s+|the\s+|our\s+)?([\w&+.'-]+(?:\s+[\w&+.'-]+){0,2}?)\s*(?:please|pls|for me|now|"
                         r"today|asap)?\W*$", re.I)
GENERIC = set("""a an the my our this that it its one subscription subscriptions membership memberships trial free plan
account monthly yearly annual paid premium service services app apps auto renew renewal recurring current old new
streaming music tv video so just all every""".split())
GYM_WORDS = re.compile(r"^(?:the\s+)?(?:gym|fitness|club)$", re.I)
CHANNEL_NAME = re.compile(r"(?:youtube\s+|yt\s+)?(?:channels?|youtubers?|creators?|accounts?|pages?|guy|girl)", re.I)

# ---------- the other reads ----------
PASSWORD = re.compile(r"\b(?:my|the)\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|pass code|login|log-in)\s*(?:is|=|:)"
                      r"|\bhere'?s my\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|login)\b"
                      r"|\b(?:password|passcode)\s*[:=]"
                      r"|\b(?:give|send|tell|text)\s+you\s+my\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|login)\b"
                      r"|\b(?:use|with)\s+my\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|login)\b"
                      r"|\b(?:can|could|will|would)\s+you\s+(?:just\s+)?(?:log|sign)\s*(?:in|into|on)\b"
                      r"|\b(?:log|sign)\s*(?:in|into|on)\s+(?:as me|for me|to my|into my|on my)\b"
                      # checks of round 10 (secrets): "my password for netflix is ..." reached the model
                      r"|\b(?:password|passcode)\s+(?:for|to|on|of)\s+(?:my\s+|the\s+)?[\w+.'-]+(?:\s+[\w+.'-]+)?"
                      r"\s*(?:is|=|:)\s*\S", re.I)
SAID_DONE = re.compile(r"^\W*(?:(?:ok(?:ay)?|so|yes|yep)[\s,!.]+)?"
                       r"(?:i(?:'ve| have)?\s+(?:just\s+|finally\s+|already\s+)?(?:cancell?ed|canceled)\s+(?P<a>.+?)"
                       r"|(?P<b>.+?)\s+is\s+(?:now\s+)?(?:cancell?ed|canceled))"
                       r"(?:\s+(?:now|today|already))?\W*$", re.I)
_IT = re.compile(r"^(?:it|that|this|them|my (?:subscription|membership)|the (?:subscription|membership))$", re.I)
BILLING = {"apple": re.compile(r"\b(?:apple|iphone|ipad|ios|app store|itunes|through apple)\b", re.I),
           "google_play": re.compile(r"\b(?:google play|play store|google|android|through google)\b", re.I),
           "web": re.compile(r"\b(?:website|web site|web|their site|online|on their site|directly|card|credit card|"
                             r"paypal|browser)\b", re.I)}
STOP_ASKING = re.compile(r"^\W*(?:no|nope|nah|no thanks|no thank you|never ?mind|forget it|skip|skip it|cancel|"
                         r"not now)\W*$", re.I)
# (round 9 checks) never a name typed back to "Which one?", "Which gym?" or "What name is the membership under?": a
# command ("stop 2", "pause everything", "cancel rule 2", "undo", "help"), a word about the bot's own rules, lists or
# texts, or a question. Such a message ends the question and is handled as usual.
NOT_AN_ANSWER = re.compile(r"^\W*(?:(?:pls|please|ok(?:ay)?|hey|so|and|but|actually|no|wait)[\s,]+)*"
                           r"(?:stop|pause|resume|restart|unpause|cancel|unsubscribe|undo|help|end|quit|delete|remove|"
                           r"show|list|send|email|remind|snooze|change|move|make|add|turn|done|what|why|how|who|"
                           r"when|where|everything)\b"
                           r"|\b(?:rules?|reminders?|nudges?|lists?|to-?dos?|digest|recap|texts?|texting|messages?|"
                           r"everything|all of them)\b|\?", re.I)
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD = r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
_TIME = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d\d))?\s*(am|pm|a\.m\.|p\.m\.)|\b(?:at\s+)?(noon|midday)\b|"
                   r"\bat\s+(\d{1,2}):(\d\d)\b", re.I)
_WHEN_FILLER = set("""ok okay sure yes yep yeah please pls remind me on this coming next at in the morning by around
then""".split())

# ---------- second merge of round 10 (self-test c06): an answer to "Which gym?" or "Which one?" that says how the
# person pays ("i pay by card", "it's billed to my card") is not a name: the question is asked again, and nothing of
# it reaches the notice. A name that only holds such a word ("Card Club Fitness") is still a name.
PAY_ANSWER = re.compile(r"^\W*(?:(?:i|we|they)\s+(?:pay|paid|am\s+paying|charge|charged|bill|billed)\b|"
                        r"(?:it'?s|it\s+is|its)\s+(?:billed|charged|paid|on\s+my)\b|"
                        r"(?:by|with|through|via|on)\s+(?:my\s+|a\s+)?(?:credit\s+|debit\s+)?(?:card|paypal|"
                        r"bank|direct\s+debit|cash|apple\s+pay|google\s+pay)\b|"
                        r"(?:monthly|yearly|annually|every\s+month)\b)", re.I)
# self-test c31: "do it for me" right after the steps (no browser offered to this person, or none for this merchant)
DOIT_AFTER_STEPS = re.compile(r"^\W*(?:(?:yes|ok|okay|sure|please|so|can\s+you|could\s+you|will\s+you|just)[\s,!.]*)*"
                              r"(?:do\s+it\s+for\s+me|cancel\s+it\s+for\s+me|do\s+that\s+for\s+me|you\s+do\s+it|"
                              r"do\s+it\s+yourself)(?:\s+(?:please|pls|thanks))*\W*$", re.I)
# ---------- end second merge of round 10 ----------
# ---------- round 10, slice D: the notice's follow-up (DESIGN.md section 17.D) ----------
CHECK_DAYS = 7           # the check date offered after a notice went, when the route file gives no notice_days
AFTER_CHECK_HOURS = 72   # an answer to the check reminder ("they confirmed", "no") is read this long after it fired
NOTICE_OPEN_DAYS = 60    # "write a second notice" / "they confirmed" refer to a notice that went this recently
# the answer right after the check reminder (the bot's newest message is that reminder)
CONFIRMED = re.compile(r"^\W*(?:(?:yes|yep|yeah|ok)[\s,!.]+)?(?:they(?:'ve| have)?\s+(?:did|confirmed)(?:\s+it)?|"
                       r"(?:i\s+)?got\s+their\s+(?:email|e-mail|confirmation|reply|letter)|confirmed|"
                       r"it'?s\s+cancell?ed|it\s+is\s+cancell?ed|it'?s\s+canceled|they\s+cancell?ed\s+it)"
                       r"(?:\s+(?:already|now|today|yesterday))?\W*$", re.I)
NOT_CONFIRMED = re.compile(r"^\W*(?:no|nope|nah|not yet|nothing yet|no reply(?: yet)?|no confirmation(?: yet)?|"
                           r"(?:no[\s,]+)?(?:they\s+)?(?:didn'?t|haven'?t|have not|did not|hasn'?t)(?:\s+(?:yet|"
                           r"confirmed|replied|answered))?(?:\s+yet)?)\W*$", re.I)
# any time while a notice is open (the words name the merchant's confirmation, so no reminder is needed first)
CONFIRMED_ANY = re.compile(r"^\W*(?:(?:ok(?:ay)?|so|good news)[\s,!.]+)?(?:they(?:'ve| have)?\s+confirmed\s+(?:it|the "
                           r"cancell?ation|my cancell?ation)|(?:i\s+)?got\s+their\s+confirmation)\W*$", re.I)
SECOND_ASK = re.compile(r"^\W*(?:(?:please|pls|can you|could you)\s+)?(?:write|draft|make|do)\s+(?:me\s+)?(?:a|the)\s+"
                        r"second\s+notice(?:\s+please)?\W*$", re.I)
_MEMBER_LINE = re.compile(r"^Member number: (.+)$", re.M)


def check_date(now, tz, entry=None):
    """The check date offered after a notice went: the route file's notice_days (business days when it says so),
    else 7 days, at 9am in the person's zone."""
    days = (entry or {}).get("notice_days") or CHECK_DAYS
    d = now.astimezone(ZoneInfo(tz)).date()
    if (entry or {}).get("notice_business_days"):
        left = int(days)
        while left:
            d += timedelta(days=1)
            if d.weekday() < 5:
                left -= 1
    else:
        d += timedelta(days=int(days))
    return datetime(d.year, d.month, d.day, 9, 0, tzinfo=ZoneInfo(tz))


def day_words(at, tz):
    """'Wednesday 25 November'."""
    return at.astimezone(ZoneInfo(tz)).strftime("%A %-d %B")
# ---------- end round 10, slice D ----------


def load_routes(path=None):
    """The route file as a dict ({"stores": {...}, "merchants": [...]})."""
    with open(path or ROUTES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _alias_re(entry):
    return re.compile(r"(?<![\w])(?:" + "|".join(entry["names"]) + r")(?![\w])", re.I)


def merchant_in(text, routes=None):
    """The route entry whose distinctive name the text says (the longest match wins), or None."""
    routes = routes or load_routes()
    best = None
    for e in routes["merchants"]:
        m = _alias_re(e).search(text or "")
        if m and (best is None or len(m.group(0)) > best[1]):
            best = (e, len(m.group(0)))
    return best[0] if best else None


def merchant_named(text, routes=None):
    """A merchant named as the whole of a short answer ("spotify", "Planet Fitness", "it's hulu"), or None."""
    t = re.sub(r"^\W*(?:it'?s|its|it is|the one (?:from|by|with)|that'?s|from|with)\s+", "", " ".join(text.split()),
               flags=re.I)
    t = re.sub(r"\W+$", "", t)
    e = merchant_in(t, routes)
    if e and _alias_re(e).fullmatch(t):
        return e
    return None


def _clean_name(s):
    words = [w for w in re.findall(r"[\w&+.'-]+", s or "") if w.lower() not in GENERIC]
    if not words or len(" ".join(words)) > 40:
        return None
    return " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)


def unknown_name(text):
    """The name a person gave a merchant the file does not know ("my brightbox subscription" -> "Brightbox")."""
    for rx in (_NAME_BEFORE, _NAME_AFTER):
        m = rx.search(text or "")
        if m:
            name = _clean_name(m.group(1))
            if name:
                return name
    return None


def answer_name(text):
    """A bare company name typed as the answer to "Which one?" (one to four words, nothing else), or None."""
    t = re.sub(r"^\W*(?:it'?s|its|it is|that'?s|from|with)\s+", "", " ".join((text or "").split()), flags=re.I)
    t = re.sub(r"\W+$", "", t)
    if not t or len(t) > 40 or len(t.split()) > 4 or re.search(r"\d{3,}|@|https?:|\?", t):
        return None
    return _clean_name(t)


def request(text, rules=(), forced=False, routes=None):
    """W5: what a cancel message asks for, or None when it is not one. Code only.

    {"kind": "merchant", "entry"} | {"kind": "unknown", "name"} | {"kind": "which"} | {"kind": "from_ad"} |
    {"kind": "gym"} | {"kind": "card"}. forced=True (the guard before _manage): the model read the message as a stop or
    pause; "stop" and "pause" count as cancel verbs there."""
    t = " ".join((text or "").split())
    if not t or len(t) > 300 or BARE.match(t) or ONLY_NUMBER.match(t):
        return None
    if not (CANCEL_VERB.search(t) or (forced and FORCED_VERB.search(t))):
        return None
    if NOT_CANCEL.search(t):
        return None
    if not forced and (LIBRARY_ASK.search(t) or HOW_TO_CANCEL_ANY.search(t)):   # round 10, slice W (W5)
        return None
    if rules:
        from .interpret import names_rule
        from .store import numbered
        if any(names_rule(t, rules, k) for k, _ in numbered(rules)):
            return None
    routes = routes or load_routes()
    entry = merchant_in(t, routes)
    if entry:
        return {"kind": "merchant", "entry": entry}
    if CARD.search(t) and not SUB_WORD.search(t):
        return {"kind": "card"}
    sub = SUB_WORD.search(t) or re.search(r"\bunsubscribe\b", t, re.I)
    gym = GYM_SAID.search(t)
    if FROM_SAVED.search(t) and (sub or PRODUCT.search(t)):
        return {"kind": "from_ad"}   # never a merchant read from the post: the person names it
    if not (sub or gym):
        return None
    name = unknown_name(t)
    if name and CHANNEL_NAME.fullmatch(name):   # checks of round 10 (reading): "unsubscribe from that channel"
        return None                             # is the person's YouTube (ytreads), never a merchant called Channel
    if gym or (name and GYM_WORDS.match(name)):
        return {"kind": "gym"}
    if name:
        return {"kind": "unknown", "name": name}
    return {"kind": "which"}


def password_said(text):
    """True for a message that hands over a password or asks the bot to sign in as the person."""
    return bool(PASSWORD.search(" ".join((text or "").split())))


def said_done(text, routes=None):
    """'I cancelled netflix' -> the entry; 'I cancelled it' -> "it"; else None."""
    m = SAID_DONE.match(" ".join((text or "").split()))
    if not m:
        return None
    target = (m.group("a") or m.group("b") or "").strip(" .!")
    if _IT.match(target):
        return "it"
    e = merchant_in(target, routes)
    if e:
        return e
    return None


def billing_answer(text):
    """'apple', 'google_play' or 'web' for a short answer to "How do you pay for X?", else None."""
    t = " ".join((text or "").split())
    if len(t) > 80:
        return None
    hits = [k for k, rx in BILLING.items() if rx.search(t)]
    return hits[0] if len(hits) == 1 else None


def link_fresh(checked_on, today):
    """True when a link checked on `checked_on` (YYYY-MM-DD) may still be given on `today`."""
    if not checked_on:
        return False
    try:
        d = date.fromisoformat(checked_on)
    except ValueError:
        return False
    return 0 <= (today - d).days <= LINK_DAYS


def checked_words(checked_on):
    return date.fromisoformat(checked_on).strftime("%-d %b")


def when_answer(text, now, tz):
    """The moment a short answer names ("friday", "tomorrow at 6pm", "in 3 days", "dec 5", "next week"), as an aware
    datetime in the person's zone, or None when the answer says anything more or names a moment that has passed.
    9am when no time is given."""
    from .dates import find_dates
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    today = local.date()
    t = " ".join((text or "").lower().split()).strip(" .!?")
    if not t or len(t) > 60:
        return None
    hh, mm = 9, 0
    m = _TIME.search(t)
    if m:
        if m.group(4):
            hh, mm = 12, 0
        elif m.group(5):
            hh, mm = int(m.group(5)), int(m.group(6))
        else:
            hh, mm = int(m.group(1)), int(m.group(2) or 0)
            ap = m.group(3).lower().replace(".", "")
            if not 1 <= hh <= 12:
                return None
            hh = hh % 12 + (12 if ap == "pm" else 0)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        t = (t[:m.start()] + " " + t[m.end():]).strip()
    day, rest = None, t
    if re.search(r"\btonight\b", t):
        day, rest = today, re.sub(r"\btonight\b", " ", t)
        if not m:
            hh, mm = 20, 0
    elif re.search(r"\btoday\b", t):
        day, rest = today, re.sub(r"\btoday\b", " ", t)
    elif re.search(r"\btomorrow\b", t):
        day, rest = today + timedelta(days=1), re.sub(r"\btomorrow\b", " ", t)
    elif re.search(r"\bnext week\b", t):
        day, rest = today + timedelta(days=7), re.sub(r"\bnext week\b", " ", t)
    elif re.search(r"\bin (?:a|one) week\b", t):
        day, rest = today + timedelta(days=7), re.sub(r"\bin (?:a|one) week\b", " ", t)
    else:
        n = re.search(r"\bin (\d{1,2}|two|three|four|five|six|seven|ten) days?\b", t)
        w = re.search(rf"\b{_WD}\b", t)
        if n:
            words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}
            k = int(n.group(1)) if n.group(1).isdigit() else words[n.group(1)]
            if not 1 <= k <= 60:
                return None
            day, rest = today + timedelta(days=k), t[:n.start()] + " " + t[n.end():]
        elif w:
            name = next(x for x in _WEEKDAYS if x.startswith(w.group(0)[:3]))
            ahead = (_WEEKDAYS.index(name) - today.weekday()) % 7 or 7
            day, rest = today + timedelta(days=ahead), t[:w.start()] + " " + t[w.end():]
        else:
            found = find_dates(t, year_hint=today.isoformat())
            if len(found) != 1:
                return None
            d, s, e = found[0]
            if d < today - timedelta(days=7):
                d = d.replace(year=d.year + 1)
            day, rest = d, t[:s] + " " + t[e:]
    if any(x not in _WHEN_FILLER for x in re.findall(r"[^\W\d_]+", rest)):
        return None
    if re.search(r"\d", rest):
        return None
    at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)
    return at if at > now else None


def notice_text(merchant, member_name, email=None, sign_name=None, second_on=None, member_number=None,
                member_line=True):
    """The written notice (W6), built by code from the person's own words. The merge seam: slice A's
    drafts.start(person, "notice", to=..., subject=..., paragraphs=..., placeholders=...) takes these fields as they
    are. {"to": None (the person types it), "subject", "paragraphs", "placeholders", "body"}.
    Round 10, slice D: second_on ("17 November") makes the second notice (its subject and first paragraph);
    member_number fills the line (from the first notice); member_line=False leaves it out (they removed it)."""
    paras = ["Please cancel my membership effective immediately and stop all future charges. Please confirm the "
             "cancellation in writing."]
    if second_on:
        paras = [T.second_notice_paragraph(second_on)]
    facts = [f"Name on the membership: {member_name}"]
    if email:
        facts.append(f"Email on the account: {email}")
    if member_line:
        facts.append(f"Member number: {member_number or T.CANCEL_FILL}")
    paras.append("\n".join(facts))
    sign = sign_name or member_name
    body = "\n\n".join(["Hello,", *paras, f"Thank you,\n{sign}"])
    return {"to": None, "merchant": merchant, "subject": T.SECOND_NOTICE_SUBJECT if second_on else
            "Cancel my membership", "paragraphs": paras,
            "placeholders": ["member number"] if member_line and not member_number else [], "body": body, "sign": sign}


def from_todo(person, todo, now=None):
    """For W10 ("do it for me" on a to-do): the cancel request a to-do's text makes ("Cancel the gym", "cancel
    netflix"), or None when it is not one. The bot answers it with Bot.cancel_todo(person, todo, now)."""
    text = (todo or {}).get("text") or ""
    req = request(text) or request(text, forced=True)
    if req is None and re.match(r"^\W*(?:cancel|end|quit)\s+(?:the\s+|my\s+)?gym\b", text, re.I):
        req = {"kind": "gym"}
    if req is not None and req["kind"] in ("merchant", "unknown", "gym") and (todo or {}).get("item_id"):
        # (round 9 checks) a to-do that came from a saved post holds the post's words: a merchant read from them
        # never picks the way out. The person names the company
        req = {"kind": "from_ad"}
    return req


class CancelMixin:
    """W6: the helper's replies, its next-message questions (state `cancelask:<handle>`, 24 hours, the next message
    only), the `cancellations` rows and the check reminder (a one-time note rule)."""

    # ---------- reads: answer_normally hook 6 ----------
    def cancel_reads(self, person, text, now):
        """The password line, "I cancelled it", and a cancel request. None for anything else. No model call."""
        t = " ".join((text or "").split())
        if not t or len(t) > 400:
            return None
        h = person["handle"]
        if password_said(t):
            self.note(intent="cancel_password")
            self.store.forget_last_inbound(h)
            return self.send(h, self.browser_password(person, t) or T.CANCEL_PASSWORD)   # round 10, slice V
        ref = self._cancel_said_done(person, t, now)
        if ref is not None:
            return ref
        # ---------- round 10, slice D: "they confirmed it" and "write a second notice" while a notice is open -------
        if CONFIRMED_ANY.match(t) or SECOND_ASK.match(t):
            row = self._cancel_open_notice(h, now)
            if row is not None:
                if SECOND_ASK.match(t):
                    return self._cancel_second(person, row, now)
                return self._cancel_mark_done(h, row, now)
        # ---------- end round 10, slice D ----------
        # the helper's own check reminders name the merchant; "cancel my netflix" again is still a cancel (a stop or
        # pause of "the netflix one" goes through cancel_stop_guard, which keeps them)
        mine = {r["check_rule_id"] for r in self.store.cancellations(h) if r.get("check_rule_id")}
        # round 10, slice V: with MVP_BROWSER_DEMO=1 (and the browser on) the practice merchant is known too
        from .browser import practice_routes
        req = request(t, [r for r in self.store.rules(h) if r["id"] not in mine], routes=practice_routes())
        if req is not None and self._another_ask(person, t, "cancel"):   # checks of round 10 (reading): two asks
            return None                                                 # go to the split (hook 8z), each on its own
        if req is None:
            return None
        return self._cancel_start(person, req, t, now)

    def secret_reads(self, person, text, now):
        """Round 9 (W6 and E): a password handed over or a request to sign in as the person (W6's line), and a key,
        token or webhook address typed into the chat (E's line). The message is not kept (its text is cleared from
        the inbound journal at once), no model call, no requests or interpretation-cache row. Read in _on_message
        before every next-message read and before the setup's questions, so it is reached while onboarding asks
        something too. None for anything else."""
        from .connectors import secret_said
        t = " ".join((text or "").split())
        if not t or len(t) > 1000:
            return None
        h = person["handle"]
        # round 10, slice D: on the test page, the line says where such a value goes (the Connections panel)
        page = T.PANEL_TAIL if getattr(getattr(self, "channel", None), "name", "") == "web" else ""
        if password_said(t):
            self.note(intent="cancel_password")
            self.store.forget_last_inbound(h)
            # round 10, slice V: where the browser is on for this person and the merchant they name, its own line
            return self.send(h, self.browser_password(person, t)
                             or T.CANCEL_PASSWORD + (page if re.search(r"\bapp\s+password\b", t, re.I) else ""))
        if secret_said(t):
            self.note(intent="secret_refused")
            self.store.forget_last_inbound(h)
            self.store.log_action(h, None, None, "secret.refused", "done", at=now)
            return self.send(h, T.SECRET_IN_CHAT + page)
        return None

    def cancel_stop_guard(self, person, text, rules, now):
        """W5: a model stop or pause on a message about a subscription (and naming no rule) is never a stop: the
        helper answers. None when the message is not about one (the stop goes on as before)."""
        req = request(text, rules, forced=True)
        if req is None:
            return None
        return self._cancel_start(person, req, " ".join(text.split()), now)

    def cancel_todo(self, person, todo, now):
        """W10's entry: the helper's first reply for a "cancel ..." to-do, or None."""
        req = from_todo(person, todo, now)
        return None if req is None else self._cancel_start(person, req, todo.get("text") or "", now)

    # ---------- the first reply ----------
    def _cancel_start(self, person, req, text, now):
        h = person["handle"]
        self.note(intent="cancel")
        self.store.set_state(f"cancelask:{h}", None)
        kind = req["kind"]
        if kind == "card":
            return self.send(h, T.CANCEL_CARD)
        if kind in ("which", "from_ad"):
            self._cancel_ask(h, "which", now)
            return self.send(h, T.CANCEL_WHICH if kind == "which" else T.CANCEL_WHICH_COMPANY)
        if kind == "gym":
            self._cancel_ask(h, "gym", now)
            return self.send(h, T.CANCEL_WHICH_GYM)
        if kind == "unknown":
            return self._cancel_unknown(person, req["name"], now)
        return self._cancel_entry(person, req["entry"], now)

    def _cancel_entry(self, person, e, now):
        """The reply for a merchant in the route file, by its route."""
        h = person["handle"]
        today = now.astimezone(ZoneInfo(person["timezone"])).date()
        checked = bool(e.get("source_url")) and bool(e.get("checked_on"))
        route = e.get("route") or "ask"
        if route == "phone" and checked and e.get("phone") and link_fresh(e["checked_on"], today):
            cid = self._cancel_row(h, e["key"], "phone", "prepared", now)
            self._cancel_ask(h, "when", now, key=e["key"], name=e["name"], cid=cid, call=True)
            return self.send(h, T.cancel_phone(e["name"], e["phone"], checked_words(e["checked_on"])) + "\n\n"
                             + T.CANCEL_OFFER_CALL)
        # ---------- round 10, slice V: the browser offer (only where browser.available says so; else today's steps) ---
        pre = ""
        if route == "web" and checked and e.get("steps") and not getattr(self._tl, "browser_steps", False):
            from . import browser
            if browser.available(self, person, e["key"]):
                return self.browser_offer(person, e, now)
            pre = self.browser_note(person, e)
        # ---------- end round 10, slice V ----------
        if route == "web" and checked and e.get("steps"):
            steps = list(e["steps"])
            if e.get("url") and link_fresh(e["checked_on"], today):
                steps[0] = f"Open {e['url']} and sign in if it asks."
            lines = T.cancel_web(e["name"], steps, checked_words(e["checked_on"]))
            if getattr(self._tl, "browser_steps", False):   # round 10, slice V: "steps" after the browser offer
                lines[0] = T.browser_steps_head(e["name"])
            if any(b != "web" for b in e.get("billed_via") or []):
                lines.append(T.CANCEL_OTHER_BILLING)
            cid = self._cancel_row(h, e["key"], "web", "prepared", now)
            self._cancel_ask(h, "when", now, key=e["key"], name=e["name"], cid=cid)
            return self.send(h, pre + "\n".join(lines) + "\n\n" + T.CANCEL_OFFER_CHECK)
        if route == "store" and checked:
            via = (e.get("billed_via") or ["apple"])[0]
            return self._cancel_store(person, e["key"], e["name"], via, now, own=True)
        if route == "notice":
            cid = self._cancel_row(h, e["key"], "notice", "prepared", now)
            self._cancel_ask(h, "member_name", now, key=e["key"], name=e["name"], cid=cid)
            return self.send(h, T.CANCEL_MEMBER_NAME)
        # "ask", or an entry whose page was not read: how they pay decides the way out
        cid = self._cancel_row(h, e["key"], "ask", "asked_billing", now)
        self._cancel_ask(h, "billing", now, key=e["key"], name=e["name"], cid=cid)
        return self.send(h, T.cancel_ask_billing(e["name"]))

    def _cancel_store(self, person, key, name, via, now, own=False, cid=None):
        """Apple or Google Play: the path, the store's own page when its check is fresh, the offer."""
        h = person["handle"]
        today = now.astimezone(ZoneInfo(person["timezone"])).date()
        s = load_routes()["stores"][via]
        url = s["url"] if s.get("source_url") and link_fresh(s.get("checked_on"), today) else None
        path = s["path"].format(name="the subscription" if own else name)
        if cid is None:
            cid = self._cancel_row(h, key, "store", "prepared", now)
        else:
            self._cancel_update(cid, route="store", status="prepared", now=now)
        self._cancel_ask(h, "when", now, key=key, name=name if not own else s["name"], cid=cid)
        return self.send(h, T.cancel_store(s["name"], path, url, s.get("note")) + "\n\n" + T.CANCEL_OFFER_CHECK)

    def _cancel_unknown(self, person, name, now):
        h = person["handle"]
        today = now.astimezone(ZoneInfo(person["timezone"])).date()
        st = load_routes()["stores"]
        urls = [s["url"] if s.get("source_url") and link_fresh(s.get("checked_on"), today) else None
                for s in (st["apple"], st["google_play"])]
        self.store.log_request(h, "cancel: unknown merchant", "cancel")   # never the name
        self._cancel_row(h, None, "unknown", "prepared", now)
        return self.send(h, T.cancel_unknown(name, *urls))

    # ---------- the next message: handler._asked_reads hook 3 ----------
    def _cancel_answer(self, person, text, now):
        """The answer to the helper's last question (how they pay, which one, which gym, the name on the membership,
        when to remind them). Next message only: any other message ends the question and is handled as usual."""
        h = person["handle"]
        st = self.store.get_state(f"cancelask:{h}")
        if not st:
            return self._cancel_after_check(person, text, now)   # round 10, slice D: the check reminder's answer
        self.store.set_state(f"cancelask:{h}", None)
        if datetime.fromisoformat(st["at"]) < now - timedelta(hours=ASK_HOURS):
            return None
        t = " ".join((text or "").split())
        step = st.get("step")
        # ---------- round 10, slice D: "Want me to write a second notice?" ----------
        if step == "second":
            row = next((r for r in self.store.cancellations(h) if r["id"] == st.get("cid")), None)
            if row is None:
                return None
            if STOP_ASKING.match(t):
                self.note(intent="cancel")
                return self.send(h, T.SECOND_NOTICE_NO)
            if T.YES.match(t) or SECOND_ASK.match(t) or re.match(r"^\W*(?:yes|ok|sure)?[\s,]*please\W*$", t, re.I):
                return self._cancel_second(person, row, now)
            return None
        # ---------- end round 10, slice D ----------
        if step == "when":
            # second merge of round 10 (self-test c31): after the steps, "do it for me" gets why not, plainly; the
            # reminder question stays open (the browser's own offer, where it is on, is read before this)
            if st.get("name") and not st.get("notice") and DOIT_AFTER_STEPS.match(t):
                self._cancel_ask(h, "when", now, **{k: v for k, v in st.items() if k not in ("step", "at")})
                self.note(intent="cancel")
                return self.send(h, T.cancel_doit_cant(st["name"]))
            if STOP_ASKING.match(t):
                self.note(intent="cancel")
                return self.send(h, T.CANCEL_NO_REMINDER)
            if T.YES.match(t):
                # round 10, slice D: after a notice went, the offer named a date: "yes" takes it
                offer = datetime.fromisoformat(st["offer_at"]) if st.get("offer_at") else None
                if offer is not None and offer > now:
                    return self._cancel_reminder(person, st, offer, t, now)
                self._cancel_ask(h, "when", now, **{k: st.get(k) for k in ("key", "name", "cid", "call", "notice")})
                self.note(intent="cancel")
                return self.send(h, T.CANCEL_WHEN_AGAIN)
            at = when_answer(t, now, person["timezone"])
            if at is None:
                return None
            return self._cancel_reminder(person, st, at, t, now)
        if STOP_ASKING.match(t) and step in ("which", "gym", "member_name", "billing"):
            if st.get("cid"):
                self._cancel_update(st["cid"], status="dropped", now=now)
            self.note(intent="cancel")
            return self.send(h, T.CANCEL_LEFT)
        if step == "billing":
            via = billing_answer(t)
            if via is None:
                return None
            self.note(intent="cancel")
            if via == "web":
                self._cancel_update(st["cid"], route="web", status="prepared", now=now)
                self._cancel_ask(h, "when", now, key=st.get("key"), name=st["name"], cid=st["cid"])
                return self.send(h, T.cancel_web_unchecked(st["name"]) + "\n\n" + T.CANCEL_OFFER_CHECK)
            return self._cancel_store(person, st.get("key"), st["name"], via, now, cid=st["cid"])
        if step in ("which", "gym", "member_name") and NOT_AN_ANSWER.search(t) and merchant_named(t) is None:
            return None   # a command or a question, not a name: handled as usual (the question has ended)
        if step in ("which", "gym"):
            if request(t) is not None:
                return None   # a whole new cancel request: cancel_reads answers it
            if PAY_ANSWER.search(t) and merchant_named(t) is None:   # second merge of round 10 (self-test c06)
                self._cancel_ask(h, step, now, **{k: v for k, v in st.items() if k not in ("step", "at")})
                self.note(intent="cancel")
                return self.send(h, T.cancel_which_again(step == "gym"))
            e = merchant_named(t)
            if e is not None:
                return self._cancel_entry(person, e, now)
            name = answer_name(t)
            if name is None:
                return None
            self.note(intent="cancel")
            if step == "gym":   # a gym the file does not know: a written notice is the way that always works
                cid = self._cancel_row(h, None, "notice", "prepared", now)
                self._cancel_ask(h, "member_name", now, key=None, name=name, cid=cid)
                return self.send(h, T.CANCEL_MEMBER_NAME)
            return self._cancel_unknown(person, name, now)
        if step == "member_name":
            name = " ".join(re.findall(r"[^\W\d_][\w.'-]*", t))
            if not name or len(name) > 60 or len(name.split()) > 5 or len(t) > 80:
                return None
            self.note(intent="cancel")
            return self._cancel_notice(person, st, name, now, second=st.get("second"))
        return None

    def _cancel_notice(self, person, st, member_name, now, second=None):
        """The written notice as slice A's draft card (drafts.start, kind "notice"): the whole text shown, the link
        (or, for the operator's mailbox, "send") held back while the member number is "(fill this in)". The To line
        is the merchant's address only from an entry whose own help page was read; else it stays blank with a hint.
        The draft's id is kept on the cancellation row.
        Round 10, slice D: a merchant that takes notice by post (and its deadline) gets that line on the card, from
        its read page; `second` ({asked_on, member_number, member_line, to}) makes the second notice; the merchant's
        name is kept in the draft's parts (cleared with its words) for the receipt and the follow-up."""
        from . import drafts
        h = person["handle"]
        addr, ok = self.store.email_of(h)
        second = second or {}
        n = notice_text(st["name"], member_name, addr if ok else None,   # signed with the name on the membership
                        second_on=second.get("asked_on"), member_number=second.get("member_number"),
                        member_line=second.get("member_line", True))
        e = next((x for x in load_routes()["merchants"] if st.get("key") and x["key"] == st["key"]), None) or {}
        # the merchant's address only from an entry whose own page was read (never from a post or a guess)
        # (round 9 checks) and, like a link, only while that check is at most 60 days old
        today = now.astimezone(ZoneInfo(person["timezone"])).date()
        fresh = bool(e.get("source_url")) and link_fresh(e.get("checked_on"), today)
        to = second.get("to") or (e.get("notice_email") if fresh and e.get("notice_email") else None)
        note = []
        if fresh and e.get("notice_post"):
            note.append(T.notice_post_line(e["name"], e["notice_post"], checked_words(e["checked_on"])))
        if fresh and e.get("notice_deadline"):
            note.append(T.notice_deadline_line(e["notice_deadline"]))
        cid = st.get("cid")
        self._cancel_update(cid, route="notice", status="notice_drafted", now=now)
        job = f"cancel:{cid}" if cid else None
        ref = drafts.start(self, person, "notice", to=to or "", subject=n["subject"], paragraphs=n["paragraphs"],
                           placeholders=n["placeholders"], job=job, now=now, sign=n["sign"],
                           head=T.second_notice_head(st["name"]) if second.get("asked_on") else
                           T.cancel_notice_head(st["name"]), to_hint=T.CANCEL_TO_HINT,
                           note="\n".join(note) or None)
        if cid:
            row = next((r for r in reversed(self.store.drafts_of(h)) if r["job"] == job), None)
            if row is not None:
                self._cancel_update(cid, draft_id=row["id"], now=now)
                p = json.loads(row["parts"] or "{}")
                p["merchant"] = st["name"]
                self.store.update_draft(row["id"], parts=p)
        return ref

    # ---------- round 10, slice D: after the notice went (DESIGN.md section 17.D) ----------
    def _cancel_entry_of(self, key):
        return next((x for x in load_routes()["merchants"] if key and x["key"] == key), None)

    def _cancel_notice_went(self, cid, draft_row, by_bot, now):
        """drafts._draft_job_done for a notice that went: the bot sent it after "send" (`notice_sent`) or the person
        says they sent it after the link (`person_sent`). Returns the follow-up: not over until they confirm, and a
        check date offered (the route file's notice_days, else 7 days, 9am). The bot never sets it by itself."""
        h = draft_row["handle"]
        self._cancel_update(cid, status="notice_sent" if by_bot else "person_sent", now=now)
        person = self.store.person(h) or {"timezone": "America/New_York"}
        row = next((r for r in self.store.cancellations(h) if r["id"] == cid), None) or {}
        e = self._cancel_entry_of(row.get("merchant_key"))
        p = draft_row.get("parts")
        p = p if isinstance(p, dict) else json.loads(p or "{}")
        name = p.get("merchant") or (e or {}).get("name") or "them"
        at = check_date(now, person["timezone"], e)
        from .store import now_iso
        self._cancel_ask(h, "when", now, key=row.get("merchant_key"), name=name, cid=cid, notice=True,
                         offer_at=now_iso(at))
        return T.notice_offer(day_words(at, person["timezone"]))

    def _cancel_open_notice(self, h, now, cid=None):
        """The person's newest notice that went (notice_sent or person_sent) in the last 60 days, or None."""
        from .store import now_iso
        rows = self.store.cancellations(h, since=now_iso(now - timedelta(days=NOTICE_OPEN_DAYS)))
        rows = [r for r in rows if r["status"] in ("notice_sent", "person_sent") and r.get("route") == "notice"
                and (cid is None or r["id"] == cid)]
        return rows[0] if rows else None

    def _cancel_mark_done(self, h, row, now):
        """The person says it ended (or that the merchant confirmed): person_says_done, and the check reminder
        stopped if it is still waiting."""
        self.note(intent="cancel")
        self._cancel_update(row["id"], status="person_says_done", now=now)
        ticked = self._doit_cancel_done(h, row["id"], now)   # round 9, W10: the to-do it came from, if any
        r = self.store.rule(row["check_rule_id"]) if row.get("check_rule_id") else None
        if r and r["status"] in ("active", "paused"):
            self.store.set_slot(r["id"], None, "stopped")
            return self.send(h, T.CANCEL_SAID_DONE + ticked)
        return self.send(h, T.CANCEL_SAID_DONE_NO_RULE + ticked)

    def _cancel_after_check(self, person, text, now):
        """The answer to a notice's check reminder: the bot's newest message to the person is that reminder (fired
        in the last 72 hours). "they confirmed" ends it; "no" / "they didn't" offers a second notice. None for
        anything else (handled as usual)."""
        t = " ".join((text or "").split())
        yes, no = CONFIRMED.match(t), NOT_CONFIRMED.match(t)
        if not (yes or no) or len(t) > 80:
            return None
        h = person["handle"]
        last = self.store.one("SELECT run_id FROM sent WHERE handle=? ORDER BY rowid DESC LIMIT 1", (h,))
        run = self.store.one("SELECT rule_id, at FROM runs WHERE id=?", (last["run_id"],)) \
            if last and last.get("run_id") else None
        if not run or not run.get("rule_id") or not run.get("at"):
            return None
        if now - datetime.fromisoformat(run["at"]) > timedelta(hours=AFTER_CHECK_HOURS):
            return None
        row = next((r for r in self.store.cancellations(h) if r.get("check_rule_id") == run["rule_id"]
                    and r.get("route") == "notice" and r["status"] in ("notice_sent", "person_sent")), None)
        if row is None:
            return None
        if yes:
            return self._cancel_mark_done(h, row, now)
        self.note(intent="cancel")
        asked = self._cancel_asked_on(row, person)
        self._cancel_ask(h, "second", now, cid=row["id"])
        return self.send(h, T.second_notice_offer(asked))

    def _cancel_asked_on(self, row, person):
        """The day the first notice went ('17 November'), from its draft row (sent_at, else done_at)."""
        d = self.store.draft(row["draft_id"]) if row.get("draft_id") else None
        at = (d or {}).get("sent_at") or (d or {}).get("done_at") or row.get("updated_at")
        return datetime.fromisoformat(at).astimezone(ZoneInfo(person["timezone"])).strftime("%-d %B")

    def _cancel_second(self, person, row, now):
        """The second notice: code-written, the same card and rules as the first (nothing goes without "send").
        Its name, member number and address come from the first notice while its words are still kept (7 days);
        else the name is asked again and the member number is "(fill this in)"."""
        h = person["handle"]
        self.note(intent="cancel")
        first = self.store.draft(row["draft_id"]) if row.get("draft_id") else None
        p = json.loads((first or {}).get("parts") or "{}")
        e = self._cancel_entry_of(row.get("merchant_key"))
        name = p.get("merchant") or (e or {}).get("name") or self._cancel_name_from_rule(row)
        second = {"asked_on": self._cancel_asked_on(row, person), "to": (first or {}).get("to_addr")}
        body = (first or {}).get("body")
        if body:
            m = _MEMBER_LINE.search(body)
            second["member_line"] = m is not None
            if m and T.CANCEL_FILL not in m.group(1):
                second["member_number"] = m.group(1).strip()
        cid = self.store.add_cancellation(h, row.get("merchant_key"), "notice", "prepared", at=now)
        self.store.log_action(h, None, None, "cancel.help", "done", detail={"route": "notice", "known":
                                                                           row.get("merchant_key") is not None,
                                                                           "second": True}, at=now)
        st = {"key": row.get("merchant_key"), "name": name or "them", "cid": cid}
        member = p.get("sign")
        if not member or not name:
            self._cancel_ask(h, "member_name", now, second=second, **st)
            return self.send(h, T.CANCEL_MEMBER_NAME)
        return self._cancel_notice(person, st, member, now, second=second)

    def _cancel_name_from_rule(self, row):
        """The merchant's name as the check reminder says it (an unknown gym's name is kept nowhere else)."""
        r = self.store.rule(row["check_rule_id"]) if row.get("check_rule_id") else None
        try:
            text = json.loads(r["spec"])["content"]["text"] if r and isinstance(r["spec"], str) else \
                (r["spec"]["content"]["text"] if r else "")
        except (KeyError, TypeError, ValueError):
            return None
        m = re.match(r"^Check that (.{1,60}?) confirmed your cancellation", text or "")
        return m.group(1) if m else None
    # ---------- end round 10, slice D ----------

    def _cancel_reminder(self, person, st, at, text, now):
        """The check reminder the person timed: a one-time note rule ("stop N" or "undo" drops it)."""
        from .schedule import next_run, say_time
        from .schema import RuleSpec
        from .store import now_iso
        h, tz = person["handle"], person["timezone"]
        local = at.astimezone(ZoneInfo(tz))
        words = T.cancel_call_text(st["name"]) if st.get("call") else \
            T.notice_check_text(st["name"]) if st.get("notice") else T.cancel_check_text(st["name"])   # round 10, D
        spec = RuleSpec.model_validate({"when": {"type": "once", "date": local.date().isoformat(),
                                                 "time": local.strftime("%H:%M")},
                                        "content": {"source": "note", "text": words, "goal": "a check you asked for"},
                                        "do": ["message.send"]})
        self.note(intent="cancel")
        rule_id = self.store.add_rule(h, f"check reminder: {text}"[:300], spec.stored(), "active", None,
                                      created_at=now_iso(now))
        nxt = next_run(spec.when, tz, now, anchor=now, seed=rule_id, quiet=self.store.quiet(h))
        if nxt is None:
            self.store.set_slot(rule_id, None, "done")
            return self.send(h, T.TIME_PASSED)
        self.store.set_slot(rule_id, now_iso(nxt), "active")
        self._wrote_rule(h, "set up a check reminder", rule_id)
        if st.get("cid"):
            self._cancel_update(st["cid"], check_rule_id=rule_id, now=now)
        n = self.store.rule_number(h, rule_id)
        say = T.cancel_call_reminder_set if st.get("call") else T.cancel_reminder_set
        return self.send(h, say(say_time(nxt, now, tz), n))

    def _cancel_said_done(self, person, text, now):
        """'I cancelled netflix', 'netflix is cancelled', 'I cancelled it' within 7 days of a cancel reply: the row
        says the person did it, and its check reminder stops. None when nothing recent matches."""
        got = said_done(text)
        if got is None:
            return None
        h = person["handle"]
        from .store import now_iso
        since = now_iso(now - timedelta(days=SAID_DONE_DAYS))
        rows = self.store.cancellations(h, since=since)
        rows = [r for r in rows if r["status"] not in ("person_says_done", "dropped")]
        if got != "it":
            rows = [r for r in rows if r["merchant_key"] == got["key"]]
        if not rows:
            return None
        row = rows[0]
        self.note(intent="cancel")
        self._cancel_update(row["id"], status="person_says_done", now=now)
        ticked = self._doit_cancel_done(h, row["id"], now)   # round 9, W10: the to-do it came from, if any
        r = self.store.rule(row["check_rule_id"]) if row.get("check_rule_id") else None
        if r and r["status"] in ("active", "paused"):
            self.store.set_slot(r["id"], None, "stopped")
            return self.send(h, T.CANCEL_SAID_DONE + ticked)
        return self.send(h, T.CANCEL_SAID_DONE_NO_RULE + ticked)

    # ---------- rows, questions, the log ----------
    def _cancel_ask(self, h, step, now, **kw):
        from .store import now_iso
        self.store.set_state(f"cancelask:{h}", dict(kw, step=step, at=now_iso(now)))

    def _cancel_row(self, h, key, route, status, now):
        cid = self.store.add_cancellation(h, key, route, status, at=now)
        self.store.log_action(h, None, None, "cancel.help", "done", detail={"route": route, "known": key is not None},
                              at=now)
        return cid

    def _cancel_update(self, cid, now=None, **fields):
        if cid:
            self.store.update_cancellation(cid, at=now, **fields)
