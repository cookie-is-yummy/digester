"""PROTOTYPE ONLY - one numbered-offer reader (round 9, slice C, W7; DESIGN.md section 16.C). Mixed into core.Bot.

A reply that offers numbered things to do ("1. Its deadline on your calendar ... 2. A checklist ...") keeps them in
state `offers:<handle>` = {at, source, run_id, text, offers: [{n, kind, params, text, done}], ask}. The next messages
are read here, in `handler._on_message` right after the draft card's reads and before a rule preview's YES, whole
message only:

- "1", "2 and 3", "1, 3", "all", "all of them", "both", "do 2", "yes to 1", "the first one": each offer chosen runs
  through the code path its `kind` names (postacts.py), one line each, then one undo line. The offer's text said the
  exact effect; the number runs exactly that. Nothing here reaches another person or an outside account.
- "none", "not now", "no thanks", "neither": the offers end ("OK. They're still in your saves ...").
- A number past the list: "I offered 3 things. Reply 1, 2 or 3."
- `ask`: the offer list may wait for one more answer (W8's "What time?"); a day and a time read by code answers it.

They live 24 hours, a newer list replaces them, and a new answer clears them (outputs._keep_answer), so "2" never
means an offer from an older answer. With a rule preview or another question waiting, "yes" and "no" go to it, never
here. A setup step newer than the offers keeps its own "2". No model call.
"""
import re
from datetime import datetime, timedelta

from . import texts as T
from .followup import SHARE_ORDINAL
from .store import now_iso

OFFERS_HOURS = 24
_ORD = r"first|second|third|fourth|fifth|sixth|seventh|eighth|1st|2nd|3rd|[4-8]th"
_ONE = rf"(?:#\s*)?(?:\d{{1,2}}|(?:the\s+)?(?:{_ORD})(?:\s+one)?)"
CHOICE = re.compile(rf"^[\s\"'(]*(?:(?:yes|ok|okay|sure|please)[,\s]+)?(?:(?:yes\s+)?to\s+|do\s+|number\s+|option\s+)?"
                    rf"(?P<nums>{_ONE}(?:\s*(?:,|&|\+|and|,\s*and)\s*{_ONE})*)"
                    rf"(?:\s+(?:please|pls|thanks|thank you))?\W*$", re.I)
ALL = re.compile(r"^[\s\"'(]*(?:(?:yes|ok|okay|sure)[,\s]+)?(?:(?:yes\s+)?to\s+|do\s+)?(?:all|all of them|all of it|"
                 r"both|both of them|everything|all three|all 3|all two)(?:\s+(?:please|pls|thanks))?\W*$", re.I)
NONE = re.compile(r"^[\s\"'(]*(?:none|none of them|none of those|not now|no thanks|no thank you|nah thanks|neither|"
                  r"neither one|no|nope|nah|maybe later)\W*$", re.I)


def parse_choice(text, n):
    """("pick", [numbers]) / ("all", None) / ("none", None) for a whole-message answer to n offers, else None."""
    t = " ".join((text or "").split())
    if NONE.match(t):
        return "none", None
    if ALL.match(t):
        return "all", None
    m = CHOICE.match(t)
    if not m:
        return None
    out = []
    for g in re.finditer(rf"\d{{1,2}}|{_ORD}", m.group("nums"), re.I):
        w = g.group(0).lower()
        k = int(w) if w.isdigit() else (SHARE_ORDINAL.get(w) or int(re.sub(r"\D", "", w)))
        if k not in out:
            out.append(k)
    return ("pick", out) if out else None


class OffersMixin:
    def offers_open(self, h, source, offers, text, now, run_id=None, ask=None):
        """Keeps a new numbered list (replacing any older one). `offers`: [{kind, params, text}], numbered here."""
        rows = [dict(o, n=i, done=False) for i, o in enumerate(offers, 1)]
        self.store.set_state(f"offers:{h}", {"at": now_iso(now), "source": source, "run_id": run_id,
                                             "text": " ".join((text or "").split())[:300], "offers": rows,
                                             "ask": ask})

    def offers_live(self, h, now):
        st = self.store.get_state(f"offers:{h}")
        if not st:
            return None
        if datetime.fromisoformat(st["at"]) < now - timedelta(hours=OFFERS_HOURS):
            self.store.set_state(f"offers:{h}", None)
            return None
        return st

    def offer_reads(self, person, text, pending, now):
        """The reply's reference when the message answers the open offers, else None (handled as usual)."""
        h = person["handle"]
        st = self.offers_live(h, now)
        if not st:
            return None
        ob = self.store.get_state(f"onboard:{h}")
        if ob and ob.get("step") not in (None, "done") and ob.get("at") and \
                datetime.fromisoformat(ob["at"]) > datetime.fromisoformat(st["at"]):
            return None   # a setup step asked after the offers: its own "2"
        if pending and (T.YES.match(text) or T.NO.match(text)):
            return None   # a rule preview or a question waits: "yes" and "no" are its own
        if st.get("ask"):
            ref = self.offer_answer(person, st, text, now)   # postacts.py: "What time?" and its answer
            if ref is not None:
                return ref
        offers = st["offers"]
        n = len(offers)
        if n == 1 and T.YES.match(text) and not re.match(r"^\W*(?:go|start)\W*$", text, re.I):
            got = ("pick", [1])
        else:
            got = parse_choice(text, n)
        if got is None:
            return None
        self.note(intent="offer")
        kind, nums = got
        if kind == "none":
            self.store.set_state(f"offers:{h}", None)
            self._offers_date_again(h, st, now)
            return self.send(h, T.OFFERS_NONE)
        if kind == "all":
            if re.search(r"\bboth\b", text, re.I) and n != 2:
                self._offers_date_again(h, st, now)
                return self.send(h, T.offers_which(n))
            nums = [o["n"] for o in offers if not o.get("done")] or [o["n"] for o in offers]
        if any(not 1 <= k <= n for k in nums):
            self._offers_date_again(h, st, now)
            return self.send(h, T.offers_which(n))
        chosen = [offers[k - 1] for k in nums]
        if all(o.get("done") for o in chosen):
            self._offers_date_again(h, st, now)
            return self.send(h, T.OFFER_DONE_ALREADY)
        chosen = [o for o in chosen if not o.get("done")]
        ref = self.offers_run(person, st, chosen, now)   # postacts.py: each kind through its own code path
        for o in offers:
            if o["n"] in {c["n"] for c in chosen}:
                o["done"] = True
        left = [o for o in offers if not o.get("done")]
        self.store.set_state(f"offers:{h}", dict(st, offers=offers, ask=None) if left else None)
        # (round 9 live fix pass, finding 108) the apply menu's last line asked for the date; the choice was this
        # message, so the date question waits for the next one again (check of the fix: kept while the menu is open,
        # so a number already done or past the list keeps it too)
        self._offers_date_again(h, st, now)
        return ref

    def _offers_date_again(self, h, st, now):
        """(check of the live fix pass, fix9) the apply menu's last line asked for the date: "none", a number past the
        list or one already done answered the menu, not the date, so the date question waits for the next message
        again (as after a choice)."""
        if st.get("date_ask") and not self.store.get_state(f"deadline_ask:{h}"):
            self.store.set_state(f"deadline_ask:{h}", dict(st["date_ask"], at=now_iso(now)))
