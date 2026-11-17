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
                         r"\bhow (?:do|can|would|should) i (?:cancel|end|stop|quit|get out of)\b", re.I)
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

# ---------- the other reads ----------
PASSWORD = re.compile(r"\b(?:my|the)\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|pass code|login|log-in)\s*(?:is|=|:)"
                      r"|\bhere'?s my\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|login)\b"
                      r"|\b(?:password|passcode)\s*[:=]"
                      r"|\b(?:give|send|tell|text)\s+you\s+my\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|login)\b"
                      r"|\b(?:use|with)\s+my\s+(?:[\w+.'-]+\s+){0,2}(?:password|passcode|login)\b"
                      r"|\b(?:can|could|will|would)\s+you\s+(?:just\s+)?(?:log|sign)\s*(?:in|into|on)\b"
                      r"|\b(?:log|sign)\s*(?:in|into|on)\s+(?:as me|for me|to my|into my|on my)\b", re.I)
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
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD = r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
_TIME = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d\d))?\s*(am|pm|a\.m\.|p\.m\.)|\b(?:at\s+)?(noon|midday)\b|"
                   r"\bat\s+(\d{1,2}):(\d\d)\b", re.I)
_WHEN_FILLER = set("""ok okay sure yes yep yeah please pls remind me on this coming next at in the morning by around
then""".split())


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


def notice_text(merchant, member_name, email=None, sign_name=None):
    """The written notice (W6), built by code from the person's own words. The merge seam: slice A's
    drafts.start(person, "notice", to=..., subject=..., paragraphs=..., placeholders=...) takes these fields as they
    are. {"to": None (the person types it), "subject", "paragraphs", "placeholders", "body"}."""
    paras = ["Please cancel my membership effective immediately and stop all future charges. Please confirm the "
             "cancellation in writing."]
    facts = [f"Name on the membership: {member_name}"]
    if email:
        facts.append(f"Email on the account: {email}")
    facts.append(f"Member number: {T.CANCEL_FILL}")
    paras.append("\n".join(facts))
    sign = sign_name or member_name
    body = "\n\n".join(["Hello,", *paras, f"Thank you,\n{sign}"])
    return {"to": None, "merchant": merchant, "subject": "Cancel my membership", "paragraphs": paras,
            "placeholders": ["member number"], "body": body, "sign": sign}


def from_todo(person, todo, now=None):
    """For W10 ("do it for me" on a to-do): the cancel request a to-do's text makes ("Cancel the gym", "cancel
    netflix"), or None when it is not one. The bot answers it with Bot.cancel_todo(person, todo, now)."""
    text = (todo or {}).get("text") or ""
    req = request(text) or request(text, forced=True)
    if req is None and re.match(r"^\W*(?:cancel|end|quit)\s+(?:the\s+|my\s+)?gym\b", text, re.I):
        req = {"kind": "gym"}
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
            return self.send(h, T.CANCEL_PASSWORD)
        ref = self._cancel_said_done(person, t, now)
        if ref is not None:
            return ref
        # the helper's own check reminders name the merchant; "cancel my netflix" again is still a cancel (a stop or
        # pause of "the netflix one" goes through cancel_stop_guard, which keeps them)
        mine = {r["check_rule_id"] for r in self.store.cancellations(h) if r.get("check_rule_id")}
        req = request(t, [r for r in self.store.rules(h) if r["id"] not in mine])
        if req is None:
            return None
        return self._cancel_start(person, req, t, now)

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
        if route == "web" and checked and e.get("steps"):
            steps = list(e["steps"])
            if e.get("url") and link_fresh(e["checked_on"], today):
                steps[0] = f"Open {e['url']} and sign in if it asks."
            lines = T.cancel_web(e["name"], steps, checked_words(e["checked_on"]))
            if any(b != "web" for b in e.get("billed_via") or []):
                lines.append(T.CANCEL_OTHER_BILLING)
            cid = self._cancel_row(h, e["key"], "web", "prepared", now)
            self._cancel_ask(h, "when", now, key=e["key"], name=e["name"], cid=cid)
            return self.send(h, "\n".join(lines) + "\n\n" + T.CANCEL_OFFER_CHECK)
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
            return None
        self.store.set_state(f"cancelask:{h}", None)
        if datetime.fromisoformat(st["at"]) < now - timedelta(hours=ASK_HOURS):
            return None
        t = " ".join((text or "").split())
        step = st.get("step")
        if step == "when":
            if STOP_ASKING.match(t):
                self.note(intent="cancel")
                return self.send(h, T.CANCEL_NO_REMINDER)
            if T.YES.match(t):
                self._cancel_ask(h, "when", now, **{k: st.get(k) for k in ("key", "name", "cid", "call")})
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
        if step in ("which", "gym"):
            if request(t) is not None:
                return None   # a whole new cancel request: cancel_reads answers it
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
            return self._cancel_notice(person, st, name, now)
        return None

    def _cancel_notice(self, person, st, member_name, now):
        """The written notice. Until slice A's draft card is merged, the notice as text to copy (no link). On the
        merge this one function becomes a call to drafts.start(person, "notice", ...) with notice_text's fields."""
        h = person["handle"]
        addr, ok = self.store.email_of(h)
        n = notice_text(st["name"], member_name, addr if ok else None)
        e = next((x for x in load_routes()["merchants"] if st.get("key") and x["key"] == st["key"]), None) or {}
        # the merchant's address only from an entry whose own page was read (never from a post or a guess)
        to = e.get("notice_email") if e.get("source_url") and e.get("notice_email") else None
        self._cancel_update(st["cid"], route="notice", status="notice_drafted", now=now)
        return self.send(h, T.cancel_notice_card(st["name"], to or T.CANCEL_TO_HINT, n["subject"], n["body"]))

    def _cancel_reminder(self, person, st, at, text, now):
        """The check reminder the person timed: a one-time note rule ("stop N" or "undo" drops it)."""
        from .schedule import next_run, say_time
        from .schema import RuleSpec
        from .store import now_iso
        h, tz = person["handle"], person["timezone"]
        local = at.astimezone(ZoneInfo(tz))
        words = T.cancel_call_text(st["name"]) if st.get("call") else T.cancel_check_text(st["name"])
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
        r = self.store.rule(row["check_rule_id"]) if row.get("check_rule_id") else None
        if r and r["status"] in ("active", "paused"):
            self.store.set_slot(r["id"], None, "stopped")
            return self.send(h, T.CANCEL_SAID_DONE)
        return self.send(h, T.CANCEL_SAID_DONE_NO_RULE)

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
