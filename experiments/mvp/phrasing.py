"""PROTOTYPE ONLY - everyday wording read by code (round 10, slice W4; DESIGN.md section 17.W).

Three helpers, pure code, no model:
- normalize(text): the message with polite openers and closers taken off and texting shorthand spelled out
  ("hey can u cancel my hulu thx" -> "cancel my hulu"). Used ONLY as a second try by the request reads (hooks 5 to 8,
  through variants()). It is never stored, logged, shown, fed to the interpreter, a rule's text or a draft's words, and
  never reaches the reads above hook 5 (secret_reads, browser_reads, _asked_reads, draft_reads, the confirm yes), so
  "yes cancel netflix" stays a yes and "cancel it for me" stays what it says (verdict W-1, W-2).
- clauses(text) / parts(text): a message of two asks split into its parts ("cancel my hulu and also email my
  landlord about the rent"), at most 3; never a message with a time or repeat word (a rule: the interpreter's `also`
  handles its parts) or with quotes.
- TIME_WORDS: the words that make a message a rule; they stop the splitter and the errand form (W-3).
"""
import re

STUB = False

# texting shorthand, whole words only
SHORT = [(r"\bu\b", "you"), (r"\bur\b", "your"), (r"\bpl[sz]\b", "please"), (r"\bim\b", "i'm"), (r"\bive\b", "i've"),
         (r"\bdont\b", "don't"), (r"\bcant\b", "can't"), (r"\bwont\b", "won't"), (r"\bdidnt\b", "didn't"),
         (r"\bwanna\b", "want to"), (r"\bgonna\b", "going to"), (r"\bjs\b", "just"), (r"\btmrw?\b", "tomorrow"),
         (r"\bthx\b", "thanks")]
# verbs that start an errand (after them, a soft opener may be stripped)
VERBS = (r"(?:e-?mail|mail|write|draft|send|shoot|forward|cancel|unsubscribe|stop paying|get rid of|end|quit|add|put|"
         r"save|keep|stick|drop|book|reserve|apply|buy|order|get me|sign me up|sign up|register|connect|link|hook up|"
         r"disconnect|unlink|check|remind|set (?:it |this |that )?up|sync|export|upload|make|change|take out|remove|"
         r"do|handle|go ahead with|show|tell|let)")
# request openers: stripped before any word
HARD = (r"(?:please|can you|could you|would you|will you|can i get you to|i need you to|i want you to|"
        r"i'?d like you to|i might want you to|i was wondering if you could|is it possible to|"
        r"do you think you could|go ahead and|help me(?: to)?)")
# soft openers: stripped only when a comma follows, or an errand verb, or another opener
SOFT = (r"(?:hey|hi|hello|yo|ok(?:ay)?|so|um+|uh+|also|and|but|actually|just|quick(?:ly)?|"
        r"looks good|sounds good|all good|perfect|great|cool|yes|yeah|yep|yup|sure)")
LEAD = re.compile(rf"^\W*(?:{HARD}\b[\s,]*|{SOFT}(?:\s*,\s*|\s+(?={VERBS}\b|{HARD}\b|{SOFT}\b)))", re.I)
# closers; "for me" stays after do/did/done/doing ("what did you do for me") and whenever an errand verb that could
# take it is in the message ("cancel it for me" is not "cancel it": W-1)
TAIL = re.compile(r"(?:[\s,]+(?:please|thanks|thank you|ty|asap|real quick|if you can|if possible|lol|lmao|haha))+\W*$",
                  re.I)
FOR_ME = re.compile(r"[\s,]+for me\W*$", re.I)
KEEPS_FOR_ME = re.compile(r"\b(?:cancel\w*|do|did|done|doing|handle|send|e-?mail|add)\b", re.I)


def _collapse(text):
    return " ".join((text or "").split())


def normalize(text):
    """The text the request reads try second (the original is tried first). Never shown, stored or sent to a model.
    Returns the message itself when nothing is left after the openers."""
    t = _collapse(text)
    for a, b in SHORT:
        t = re.sub(a, b, t, flags=re.I)
    prev = None
    while prev != t:
        prev = t
        t = LEAD.sub("", t, count=1).strip()
        t = TAIL.sub("", t).strip()
        if FOR_ME.search(t) and not KEEPS_FOR_ME.search(FOR_ME.sub("", t)):
            t = FOR_ME.sub("", t).strip()
    t = re.sub(r"\s+([,.!?])", r"\1", t).strip(" ,")
    return t if t else _collapse(text)


def variants(text):
    """[text, normalize(text)] (one entry when they are the same), for hooks 5 to 8 only."""
    t = text or ""
    n = normalize(t)
    return [t] if n == _collapse(t) or not n else [t, n]


# a time or repeat word: the message is a rule (never split; never sent to the errand form)
TIME_WORDS = re.compile(
    r"\b(?:every|each|daily|weekly|monthly|nightly|whenever|once a|twice a|"
    r"on (?:mon|tues|wednes|thurs|fri|satur|sun)days?|tomorrow|tonight|next (?:mon|tues|wednes|thurs|fri|satur|sun)day|"
    r"next (?:week|month)|at \d|in \d+ (?:min\w*|hours?|days?|weeks?)|from now on|until)\b", re.I)

ADDR = r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
REQ_START = re.compile(rf"^\W*(?:{HARD}\b|{VERBS}\b|i want\b|i'?d like\b|remind me\b)", re.I)
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[a-z])|\s*;\s*|\s*\n+\s*|,?\s+(?:and also|and then|also|plus|but)\s+"
                   r"|,\s+(?=(?:can you|could you|and)\b)"
                   r"|\s+and\s+(?=(?:can you|could you|please|e-?mail|write|send|cancel|unsubscribe|add|put|book|"
                   r"reserve|buy|remind|set (?:it )?up|help me|connect|disconnect)\b)", re.I)
CONNECTOR = re.compile(r"^(?:and|also|but|plus|then)\b[\s,]*", re.I)


def is_request(part):
    """True when the part asks for something: after normalize it starts with a request opener, an errand verb,
    "i want", "i'd like" or "remind me"."""
    return bool(REQ_START.search(part or "") or REQ_START.search(normalize(part or "")))


def clauses(text):
    """The message's parts, at most 3, as strings (one part when it is not split)."""
    return [p for p, _ in parts(text)]


def parts(text):
    """[(part, is_request)]. A message with a time or repeat word (read on the normalised text, so "tmrw" counts), or
    with two or more quote marks, is never split. "can you also X" is first read as "also can you X". A part of one or
    two words that asks for nothing ("too", "thanks") joins the part before it. A leading "and", "also", "but" is
    taken off each later part."""
    t = _collapse(text)
    if not t:
        return [(t, False)]
    t2 = re.sub(r"\b(can you|could you|would you|please|pls)\s+also\b", r"also \1", t, flags=re.I)
    if t2.count('"') + t2.count("“") + t2.count("”") >= 2 or TIME_WORDS.search(normalize(t2)) or TIME_WORDS.search(t2):
        return [(t, is_request(t))]
    raw = [p.strip(" ,") for p in SPLIT.split(t2) if p and p.strip(" ,")]
    out = []
    for i, p in enumerate(raw):
        if i:
            p = CONNECTOR.sub("", p).strip(" ,") or p
        if out and len(p.split()) <= 2 and not is_request(p):
            out[-1] = (out[-1][0] + " " + p, out[-1][1])
            continue
        out.append((p, is_request(p)))
    if len(out) <= 1:
        return [(t, is_request(t))]
    if len(out) > 3:   # at most 3 parts: the rest stays with the third
        third = " ".join(p for p, _ in out[2:])
        out = out[:2] + [(third, is_request(third))]
    return out


def leftover(parts_list):
    """The parts that ask for nothing, joined, for the profile form ("" when none)."""
    return ". ".join(p for p, req in parts_list if not req).strip()


BARE_NO = re.compile(r"^\W*(?:not really|no|nope|nah|nothing|not that i know(?: of)?|not much|none)\W*$", re.I)
