"""PROTOTYPE ONLY - an email to someone else, written by the bot and sent by the person (round 9, slice A: W2, W3,
W4, A5, A6; DESIGN.md section 16.A; amendments A-012 and A-013, Proposed). Mixed into core.Bot.

"email my landlord that the kitchen sink is broken" is read here by code, before the model. The bot writes the email
(its words: the person's own, a checked post block, and, when draft_v1 is on, a model's text that code checked), shows
it whole as a three-message card, and gives a mailto: link. The person sends it from their own mail app: on this route
the bot sends nothing. For the operator only, with their own mailbox in the environment, the word "send" on the exact
version last shown sends it from their address after a two-minute hold (actions/mailbox.py).

Rules that hold everywhere here:
- The recipient is only ever an address the person typed in this draft's exchange. Never one from a post, a caption,
  an answer or the model.
- Every change makes a new version with a new text hash; a yes given to an older version is void.
- A reply never says "sent" unless the mail server accepted it; a link is "a link you tap", never "sent".
- action_log rows hold the recipient's domain and counts, never the address, the subject or the body.

Public entry points other slices call (C1 published their names; the bot is the first argument here because these
are methods of the bot): Bot.draft_start(person, kind, to=None, to_name=None, subject=None, paragraphs=(), post=None,
placeholders=(), job=None, now=None) -> the first message's ref; Bot.open_draft(handle) -> dict or None;
Bot.draft_from_todo(person, todo, now=None) -> ref or None. Module-level start(bot, ...), open_draft(bot, handle) and
from_todo(bot, person, todo, now) call them.
"""
import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import config
from . import texts as T
from .store import now_iso

OPEN_HOURS = 24               # a draft card stays open this long after it was last shown or asked about
CLEAR_DAYS = 7                # the address, subject and words of a finished draft are cleared after this
MAX_CHANGES = 5               # changes per draft; then "tell me the whole text"
LINK_MAX = 1500               # the body in a mailto: link is cut at a line boundary past this
FRESH_MINUTES = 30            # W4: "send" more than this long after the version was shown shows it again
REQUEST_MAX = 600             # an email request is read by code up to this many characters

ADDR = r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
ADDR_RE = re.compile(ADDR)
# the people a message can name (outputs.OTHER_PERSON keeps the same words; "agent" and "assistant" stay out: F10)
PEOPLE_WORDS = (r"mom|mum|mother|dad|father|parents?|wife|husband|partner|friends?|boss|sister|brother|son|daughter|"
                r"girlfriend|boyfriend|roommate|colleague|coworker|co-worker|teacher|team|family|grandma|grandpa|aunt|"
                r"uncle|cousin|landlord|landlady|neighbou?r|client|doctor|dentist|professor|tutor|coach|manager|"
                r"recruiter|lawyer|accountant|plumber|contractor|therapist")
# places that are the person's own ("send it to my gmail"): never a recipient
SELF_WORDS = re.compile(r"^(?:me|myself|us|my\s+(?:own\s+)?(?:e-?mail|inbox|gmail|icloud|outlook|hotmail|yahoo|"
                        r"proton(?:mail)?|mail(?:\s+app)?|mailbox|drafts?|address|account))\b", re.I)
_LEAD = (r"^\W*(?:(?:hey|hi|ok(?:ay)?|so|please|pls|plz|can you|could you|would you|will you|can u|could u|"
         r"i (?:need|want|have) to|i'?d like (?:you )?to|help me|i need you to|go ahead and)[\s,]+)*")
_NAME = r"[A-Z][a-z][A-Za-z'’-]*"
NOT_NAMES = set("""I Me My It This That The A An And Hi Hey Ok Okay Monday Tuesday Wednesday Thursday Friday Saturday
Sunday January February March April May June July August September October November December Gmail Icloud
Outlook Hotmail Yahoo Proton Email Mail Instagram Youtube YouTube Tomorrow Today Tonight Please Them Him Her""".split())
# (round 9 live fix pass, finding 104) the address the person typed right after the role word or the name, in any of
# the usual ways: "my friend maya@example.com", "my landlord (bob@example.com)", "my friend Maya at maya@...",
# "my sister, ana@example.com,", "Maya <maya@example.com>"; a lowercase name only before "at <address>"
_AT_ADDR = r"(?:\s+at\s+|\s*[(<]\s*|\s*[,:]\s*|\s+)"
_LOW_NAME = (r"(?!(?:that|about|saying|and|to|with|re|regarding|asking|for|at|asap|now|quick|quickly|today|tomorrow|"
             r"tonight|please|pls|again|back|also|too|just|here|there|this|it|or|but|so|if|when)\b)[a-z][a-z'’-]{1,20}")
# (check of the live fix pass, fix9) a title before the name ("Mr Smith", "Dr. Ruiz", "ms lee"), a second name
# ("Maya Lopez") or a lowercase name of two words ("maya lopez") when the typed address comes right after it
_TITLE = r"(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor)\.?"
_TITLE_LOW = r"(?:mr|mrs|ms|miss|mx|dr|prof|professor)\.?"
_NOT_NAME_WORD = "|".join(sorted(NOT_NAMES, key=len, reverse=True))
_ADDR_NEXT = rf"(?:\s+at\s+|\s*[(<]\s*|\s*[,:]\s*|\s+){ADDR}"
_RCPT = (rf"(?P<addr>{ADDR})"
         rf"|(?P<my>(?:my|our)\s+(?P<word>(?:{PEOPLE_WORDS})s?))"
         rf"(?:\s+(?P<wname>(?:{_TITLE}\s+)?{_NAME}(?:\s+(?!(?:{_NOT_NAME_WORD})\b){_NAME}(?={_ADDR_NEXT}))?)"
         rf"|\s+(?P<lname>(?:{_TITLE_LOW}\s+)?{_LOW_NAME}(?:\s+{_LOW_NAME})?)(?={_ADDR_NEXT}))?"
         rf"(?:{_AT_ADDR}(?P<waddr>{ADDR})(?:\s*[)>])?)?"
         rf"|(?P<name>(?:{_TITLE}\s+)?{_NAME}(?:\s+{_NAME})?)(?:{_AT_ADDR}(?P<naddr>{ADDR})(?:\s*[)>])?)?"
         r"|(?P<pron>him|her|them)"
         # ---------- round 10, slice W (W5): "coach dan", "ms rivera (rivera@example.com)", "sam that ..." ----------
         rf"|(?P<bword>(?:{PEOPLE_WORDS}))\s+(?P<bname>{_NAME}|{_LOW_NAME})(?=\s+(?:that|saying|about|an?\s+e-?mail)\b|$)"
         rf"|(?P<tname>{_TITLE_LOW}\s+{_LOW_NAME}){_AT_ADDR}(?P<taddr>{ADDR})(?:\s*[)>])?"
         rf"|(?P<lone>(?!(?:{PEOPLE_WORDS}|me|us|you|everyone|someone|somebody|people|them|him|her)\b){_LOW_NAME})"
         r"(?=\s+(?:that|saying|to say|about|asking)\b|\s+an?\s+(?:quick\s+|short\s+)?e-?mail\b|$)")
         # ---------- end round 10, slice W ----------
# "email ...": what follows the verb
_EMAIL_VERB = (r"(?:e-?mail|draft(?:\s+and\s+send)?\s+(?:an?\s+)?e-?mail\s+(?:to|for)|"
               r"write\s+(?:an?\s+)?e-?mail\s+(?:to|for)|"
               r"send\s+(?:an?\s+)?e-?mail\s+to|compose\s+(?:an?\s+)?e-?mail\s+to|write\s+to|"
               r"(?:draft|write)\s+(?:an?\s+)?(?:reply|note|letter)\s+to)")
VERB_FIRST = re.compile(_LEAD + rf"(?P<verb>{_EMAIL_VERB})\s+(?P<rest>.+)$", re.I | re.S)
# "send the pasta recipe to sam@example.com": an object, then an address (a send with no address is a share)
SEND_TO_ADDR = re.compile(_LEAD + rf"(?:send|forward|share)\s+(?P<obj>.{{1,60}}?)\s+to\s+(?P<rest>{ADDR}.*)$",
                          re.I | re.S)
# (round 9 live fix pass, finding 104) "send maya@example.com an email saying ...", "shoot my landlord an email about
# ...": the recipient between the verb and "an email"; only with words that say what it says (or none)
SEND_RCPT_EMAIL = re.compile(_LEAD + r"(?:send|shoot|drop|write)\s+(?P<r>.{1,80}?)\s+an?\s+(?:quick\s+|short\s+)?"
                             r"e-?mail(?:\s+(?P<tail>(?:saying|that|to say|about|regarding|asking|and\s+(?:ask|tell|say)|"
                             r"telling)\b.*))?\s*[.!]?$", re.I | re.S)
# ---------- round 10, slice W (W5): "let my professor know by email that ...", "drop sam a line saying ..." ----------
LET_KNOW = re.compile(_LEAD + r"(?:let|tell)\s+(?P<r>.{1,60}?)\s+(?:know\s+)?(?:by|via|over|in\s+an?)\s+e-?mail"
                      r"(?:\s+(?P<tail>.+))?\s*[.!]?$", re.I | re.S)
DROP_LINE = re.compile(_LEAD + r"(?:drop|send|shoot)\s+(?P<r>.{1,60}?)\s+a\s+(?:quick\s+)?(?:line|note)"
                       r"(?:\s+(?P<tail>(?:saying|that|to say|about|asking)\b.*))?\s*[.!]?$", re.I | re.S)
# ---------- end round 10, slice W ----------
POINTS = re.compile(r"^(?:it|this|that|these|those|them|both|all of them|this one|that one|the\s+(?:\w+\s+){0,3}?"
                    r"(?:one|ones|recipe|recipes|video|post|reel|tutorial|workout|pick|link|thing|programme|program|"
                    r"opportunity|place|event|answer)|the\s+(?:first|second|third|fourth|fifth|last)\b.*|#\s?\d|"
                    r"number\s+\d)\b", re.I)
PLURAL = re.compile(r"^(?:these|those|them|both|all of them|the\s+(?:\w+\s+)?(?:ones|recipes|picks|posts|videos))\b",
                    re.I)
CC = re.compile(r"\b(?:cc|bcc|cc'?d|copy in|everyone|everybody|all of them at|the whole team)\b", re.I)
REPEATING = re.compile(r"\b(?:every|each)\s+(?:day|morning|evening|night|week|month|weekday|weekend|"
                       r"(?:mon|tues|wednes|thurs|fri|satur|sun)day)s?\b|\b(?:daily|weekly|monthly)\b|"
                       r"\bon\s+(?:mon|tues|wednes|thurs|fri|satur|sun)days\b", re.I)
EMAIL_WORD = re.compile(r"\be-?mail", re.I)
PHONE_RE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b|\+\d[\d\s().-]{8,}\d")
OTHER_RE = re.compile(rf"\b(?:my|our)\s+(?:{PEOPLE_WORDS})s?\b", re.I)

# ---------- the draft reader's words (whole message only) ----------
# (round 9 checks: a question, "send it?", is never the yes, so the end allows only spaces, "." and "!")
SEND_WORDS = re.compile(r"^\W*(?:(?:yes|ok(?:ay)?|go ahead and|please"
                        # round 10, slice W (W5): "looks good, send", "perfect send it now pls"; never normalize (W-2)
                        r"|looks good|sounds good|perfect|great|cool|alright|all good|yep|yeah)[\s,!.]+)?"
                        r"send(?:\s+(?:it|the email|it now|now))?"
                        r"(?:\s+now)?(?:\s+(?:please|pls))?[\s.!]*$"
                        r"|^\W*(?:s[ií][\s,!.]+)?(?:env[ií]alo|m[aá]ndalo)(?:\s+ya)?[\s.!]*$", re.I)
SEND_QUESTION = re.compile(r"^\W*(?:(?:should|shall|can|could|do|will)\s+(?:i|you|we)\s+)?send(?:\s+(?:it|the email))?"
                           r"(?:\s+now)?\s*\?[\s?!]*$", re.I)
CANCEL_WORDS = re.compile(r"^\W*(?:cancel(?:\s+(?:it|that|the (?:email|draft)))?|don'?t send(?:\s+it)?|"
                          r"do not send(?:\s+it)?|never\s?mind|scrap(?:\s+it|\s+that)?|no|nope|drop it|forget it|"
                          r"delete (?:it|the draft))\W*$",
                          re.I)
YES_WORDS = re.compile(r"^\s*(?:yes|y|yep|yeah|yup|sure|ok|okay|go|do it|sounds good|looks good|perfect|great|👍"
                       # round 10, slice W (W5): "go ahead", "ok go ahead": the card's yes line (it never sends)
                       r"|(?:(?:ok|okay|yes|yeah|sure)[\s,]+)?go\s+ahead)"
                       r"[\s.!]*$", re.I)
SHOW_WORDS = re.compile(r"^\W*(?:show|see)\s+(?:me\s+)?(?:it|the (?:draft|email)|my draft)(?:\s+again)?\W*$", re.I)
SENT_WORDS = re.compile(r"^\W*(?:(?:ok|okay|done)[\s,]+)?(?:sent|i sent it|i'?ve sent it|i have sent it|sent it|"
                        r"i sent the email)\W*$", re.I)
BLANK = re.compile(r"^\W*(?:blank|leave it blank|no address|i'?ll (?:pick|add) (?:it|them)(?: myself)?)\W*$", re.I)
NO_NAME = re.compile(r"^\W*(?:no name|none|nothing|don'?t sign(?: it)?|no sign[- ]?off)\W*$", re.I)
SIGN_NAME = re.compile(r"^\W*(?:(?:sign it|it'?s|i'?m|call me|use)\s+)?([^\W\d_][\w'’ .-]{0,30}?)\W*$", re.I)
CH_ADD = re.compile(r"^\W*(?:also\s+)?(?:say|add|mention|also mention|tell (?:him|her|them))\s+(?:that\s+)?"
                    r"(?P<x>.+?)\W*$",
                    re.I | re.S)
CH_INSTEAD = re.compile(r"^\W*(?:instead,?\s+say|say instead|change it to say|make it say)\s+(?:that\s+)?(?P<x>.+?)\W*$"
                        r"|^\W*say\s+(?:that\s+)?(?P<y>.+?)\s+instead\W*$", re.I | re.S)
CH_SUBJECT = re.compile(r"^\W*(?:subject(?:\s+line)?\s*[:\-]\s*|(?:change|make|set)\s+the\s+subject(?:\s+line)?\s+"
                        r"(?:to\s+)?|subject\s+line\s+)[\"“]?(?P<x>.+?)[\"”]?\W*$", re.I)
CH_TO = re.compile(r"^\W*(?:to\s*:\s*|send it to\s+|change (?:the )?(?:recipient|address|to)\s+(?:to\s+)?)"
                   rf"(?P<a>{ADDR})"
                   r"(?:\s+instead)?\W*$", re.I)
CH_SIGN = re.compile(r"^\W*sign it\s+(?:as\s+|with\s+)?(?P<x>[^\W\d_][\w'’ .-]{0,30}?)\W*$", re.I)
CH_NOSIGN = re.compile(r"^\W*(?:don'?t|do not) sign it\W*$", re.I)
CH_NOLINK = re.compile(r"^\W*(?:remove|take out|drop|delete|leave out)\s+the\s+link\W*$", re.I)
CH_NOPOST = re.compile(r"^\W*(?:remove|take out|drop|delete|leave out)\s+the\s+post\W*$", re.I)
CH_LINKBACK = re.compile(r"^\W*(?:add|put)\s+the\s+(?:link|post)\s+back(?:\s+in)?\W*$", re.I)
TONE = re.compile(r"\b(?:shorter|longer|more formal|less formal|formal|informal|friendlier|friendly|warmer|nicer|"
                  r"politer|more polite|polite|casual|professional|firmer|kinder|softer|in (?:spanish|french|german|"
                  r"italian|portuguese|english))\b", re.I)
TONE_ASK = re.compile(r"^\W*(?:can you\s+|could you\s+|please\s+)?(?:make it|make this|rewrite it|write it|reword it|"
                      r"translate it|put it)\b", re.I)
REMOVE_IT = re.compile(r"^\W*(?:remove it|remove that line|take it out|leave it out)\W*$", re.I)
# (round 9 live fix pass, finding 107) with a card open, "put this in my email", "put it in my drafts", "save it as a
# draft", "stick it in my inbox" mean the card (a number, "the second one", is about the answer: mailbox_reads)
SAVE_DRAFT = re.compile(r"^\W*(?:(?:please|can you|could you|pls|just|ok|okay)\s+)*"
                        # round 10, slice W (W5): "dont send yet, keep it in drafts", "put it in my gmail drafts pls"
                        r"(?:(?:don'?t|do not)\s+send(?:\s+it)?(?:\s+yet)?[\s,.;]+(?:just\s+)?)?"
                        r"(?:save|put|stick|keep)\s+"
                        r"(?:it|that|this|this one|that one|that email|this email|the email|the draft|my draft)?\s*"
                        r"(?:as\s+an?\s+(?:e-?mail\s+)?draft|in(?:to)?\s+(?:my\s+|the\s+)?drafts?(?:\s+folder)?"
                        r"|in(?:to)?\s+my\s+(?:e-?mail|drafts?(?:\s+folder)?|gmail|"
                        r"icloud|outlook|mailbox|inbox|mail(?:\s+app)?)(?:\s+drafts?(?:\s+folder)?)?)"
                        r"(?:\s+(?:please|pls|for now))?\W*$", re.I)
# round 10, slice W (W5): "save it, i'll send it myself" with the card in view
SAVE_IT = re.compile(r"^\W*(?:just\s+|ok\s+|okay\s+)?(?:save|keep)\s+it(?:\s+for\s+now)?(?:[\s,.;]+(?:i'?ll|i will)\s+send"
                     r"\s+it\s+(?:myself|later|from my (?:phone|mail|email|gmail)))?\W*$", re.I)
# "(no,) say tuesday not monday", "say X instead of Y": X in place of Y where Y is in the draft
CH_REPLACE = re.compile(r"^\W*(?:no[\s,.!]+)?(?:say|make it|put|change it to)\s+(?P<x>[^,]{1,60}?)\s*,?\s+"
                        r"(?:not|instead of|rather than)\s+(?P<y>[^,]{1,60}?)\W*$"
                        r"|^\W*(?:no[\s,.!]+)?(?:change|replace)\s+(?P<y2>[^,]{1,60}?)\s+(?:to|with)\s+(?P<x2>[^,]{1,60}?)\W*$",
                        re.I)
# "take out the part about the doctor": the sentences of the words that hold it
CH_DROP_PART = re.compile(r"^\W*(?:(?:can you|please|pls|just)\s+)?(?:take out|remove|drop|delete|leave out|cut)\s+"
                          r"(?:the\s+)?(?:part|bit|line|sentence|stuff)\s+(?:about|on|with|where i say|that says)\s+"
                          r"(?P<x>.{1,60}?)\W*$", re.I)
# A5: "put this in my email", "save it as a draft", "put the second one in my drafts", "draft it in my gmail"
MAILBOX_SAVE = re.compile(r"^\W*(?:(?:please|can you|could you|pls)\s+)?(?:put|save|draft|stick)\s+"
                          r"(?P<what>it|this|that|them|these|this one|that one|"
                          r"the\s+(?:first|second|third|fourth|fifth|"
                          r"last)\s+one|the\s+\w+\s+one|#\s?\d|number\s+\d)?\s*(?:as\s+an?\s+(?:e-?mail\s+)?draft|"
                          r"in(?:to)?\s+my\s+(?:e-?mail|drafts?(?:\s+folder)?|gmail|icloud|mailbox|inbox)"
                          r"(?:\s+drafts?)?)(?:\s+please)?\W*$", re.I)
# ---------- round 10, slice D: "send it for me" is the send word; "can you send it (for me)" asks ----------
_SEND_OBJ = r"send\s+(?:it|this|that|this one|the (?:email|notice|draft|message))(?:\s+(?:out|off))?"
_FOR_ME = r"(?:for me|yourself|on my behalf|from my (?:e-?mail|address|account|gmail|mailbox))"
SEND_FOR_ME = re.compile(rf"^\W*(?:(?:please|pls|just|ok(?:ay)?|yes|go ahead and)[\s,]+)*{_SEND_OBJ}\s+{_FOR_ME}"
                         r"(?:\s+(?:please|now))*[\s.!?]*$", re.I)
SEND_ASK = re.compile(r"^\W*(?:can|could|would|will|can'?t|couldn'?t|why can'?t)\s+(?:you|u)\s+(?:please\s+|just\s+)?"
                      rf"{_SEND_OBJ}(?:\s+{_FOR_ME})?(?:\s+(?:please|now))*[\s.!?]*$", re.I)


class NotBuilt(Exception):
    """A send route the seam names but this round does not build (send_as: the person's own connected mailbox)."""


# ---------- end round 10, slice D ----------
NOT_A_CHANGE = re.compile(r"\b(?:to|on|onto|in|into)\s+(?:my|the)\s+(?:[\w-]+\s+){0,2}(?:list|calendar|reminders?|"
                          r"to-?dos?)\b", re.I)
# ---------- round 10, slice W (W1): "email it to me", read with a card open (also while it waits for "to") ----------
_SELF_LEAD = r"^\W*(?:(?:ok(?:ay)?|so|just|please|pls|can you|could you|can u|could u|actually)[\s,]+)*"
SELF_COPY = re.compile(
    _SELF_LEAD + r"(?:(?:e-?mail|send|mail|forward)\s+(?:it|this|that|this one|that one|the (?:draft|email)|a copy)\s+"
    r"to\s+(?:me|myself|my (?:own )?(?:e-?mail|inbox|address))(?:\s+instead)?"
    r"|(?:e-?mail|mail|send)\s+me\s+(?:it|that|this|a copy|the draft|a copy of (?:it|the draft))(?:\s+instead)?"
    # checks of round 10 (reading): "send me a copy of that email", "email it to me first so i can check"
    r"|(?:e-?mail|mail|send|forward)\s+me\s+a\s+copy\s+of\s+(?:that|this|the|my)\s+(?:e-?mail|draft|message)"
    r"|(?:can|could)\s+i\s+(?:get|have)\s+a\s+copy(?:\s+of\s+(?:it|that|the\s+(?:e-?mail|draft)))?)"
    r"(?:\s+(?:please|pls|first|too))?"
    r"(?:\s+(?:so\s+(?:that\s+)?i\s+can\s+(?:check|read|look\s+at|see|forward)(?:\s+it)?(?:\s+first)?|to\s+check(?:\s+it)?|"
    r"before\s+(?:i|you)\s+send\s+it))?(?:\s+(?:please|pls))?[\s.!]*$", re.I)
# with nothing open: only the "... to me" shapes are read by code ("email me that" stays the interpreter's
# act_on_last, whose reply with nothing to send is the same NOTHING_TO_EMAIL: outputs._act_on_last)
SELF_COPY_TO_ME = re.compile(
    _SELF_LEAD + r"(?:e-?mail|send|mail|forward)\s+(?:it|this|that|this one|that one|the (?:draft|email)|a copy)\s+"
    r"to\s+(?:me|myself)(?:\s+instead)?(?:\s+(?:please|pls))?[\s.!]*$", re.I)
# ---------- end round 10, slice W ----------


def addresses(text):
    return list(dict.fromkeys(m.group(0).rstrip(".").lower() for m in ADDR_RE.finditer(text or "")))


def domain_of(addr):
    return addr.rsplit("@", 1)[1].lower() if addr and "@" in addr else None


def cap(s):
    s = " ".join(str(s or "").split()).strip(" ,;:-")
    return (s[:1].upper() + s[1:]) if s else s


def sentence(s, end="."):
    s = cap(s)
    if s and s[-1] not in ".!?…":
        s += end
    return s


def _you(rest):
    """'ask if she can come' -> 'if you can come': only (he|she|they) + a modal right after the question word."""
    return re.sub(r"^(he|she|they)\s+(can|could|will|would|should|might)\b", r"you \2", rest, count=1, flags=re.I)


def clause_paragraph(rest):
    """The request paragraph from the person's own words after the recipient, by fixed patterns only (no other
    rewording). Returns (paragraph or None, subject words or None, points-at-post words or None)."""
    r = " ".join((rest or "").split()).strip(" ,")
    subj = None
    m = re.search(r"[,\s]+(?:with\s+)?(?:the\s+)?subject(?:\s+line)?\s*[:\-]?\s*[\"“](?P<s>[^\"”]+)[\"”]\s*$", r, re.I)
    if m:
        subj, r = m.group("s").strip(), r[:m.start()].strip(" ,")
    if not r:
        return None, subj, None
    m = re.match(r"^(?:and\s+)?(?:ask(?:ing)?|to ask)\s+(?:(?:him|her|them)\s+)?"
                 r"(?P<w>if|whether|when|what|where|how|why|"
                 r"who)\s+(?P<c>.+)$", r, re.I)
    if m:
        return f"Can you let me know {m.group('w').lower()} {_you(m.group('c')).rstrip(' .?!')}?", subj, None
    m = re.match(r"^(?:and\s+)?(?:ask(?:ing)?|to ask)\s+(?:(?:him|her|them)\s+)?for\s+(?P<c>.+)$", r, re.I)
    if m:
        return sentence(f"I'd like to ask for {m.group('c').rstrip(' .')}"), subj, None
    m = re.match(r"^(?:and\s+)?(?:tell|let)\s+(?:him|her|them)\s+(?:know\s+)?(?:that\s+)?(?P<c>.+)$", r, re.I)
    if m:
        return sentence(m.group("c")), subj, None
    m = re.match(r"^(?:that|saying|to say|and say|and say that)\s+(?P<c>.+)$", r, re.I)
    if m:
        # (round 9 live fix pass) "that i can't make it on saturday and ask if sunday works": the statement, then the
        # question as a question, both in the person's own words
        q = re.match(r"^(?P<a>.+?),?\s+and\s+(?:ask(?:ing)?|to ask)\s+(?:(?:him|her|them)\s+)?"
                     r"(?P<w>if|whether|when|what|where|how|why|who)\s+(?P<c>.+)$", m.group("c"), re.I)
        if q:
            return (sentence(q.group("a")) + " " +
                    f"Can you let me know {q.group('w').lower()} {_you(q.group('c')).rstrip(' .?!')}?"), subj, None
        return sentence(m.group("c")), subj, None
    m = re.match(r"^(?:about|regarding|re:?)\s+(?P<c>.+)$", r, re.I)
    if m:
        c = m.group("c").strip(" .")
        if POINTS.match(c):
            return None, subj, c
        return sentence(f"I'm writing about {c}"), subj, None
    if POINTS.match(r):
        return None, subj, r
    return None, subj, None


def _recipient(rest, original):
    """(recipient dict, the words after it) from the start of `rest`, or (None, rest)."""
    m = re.match(rf"^(?:{_RCPT})(?=$|[\s,.;:!?])", rest)
    if not m:
        return None, rest
    if m.group("name"):
        first = m.group("name").split()[0]
        if first in NOT_NAMES or first.lower() in ("me", "my"):
            return None, rest
    if m.group("pron"):
        return {"pron": m.group("pron").lower()}, rest[m.end():]
    # ---------- round 10, slice W (W5): a bare role word with a name, a lowercase title, a lone lowercase name ------
    if m.group("bword") or m.group("tname") or m.group("lone"):
        addr = m.group("taddr")
        nm = m.group("bname") or m.group("tname") or m.group("lone")
        who = {"to": addr.lower() if addr else None, "word": m.group("bword").lower() if m.group("bword") else None,
               "name": " ".join(cap(w) for w in nm.split())}
        return who, rest[m.end():]
    # ---------- end round 10, slice W ----------
    addr = m.group("addr") or m.group("waddr") or m.group("naddr")
    who = {"to": addr.lower() if addr else None,
           "word": m.group("word").lower() if m.group("word") else None,
           "name": m.group("wname") or (" ".join(cap(w) for w in m.group("lname").split()) if m.group("lname")
                                        else None) or m.group("name")}
    tail = rest[m.end():]
    m2 = re.match(rf"^\s*(?:and|or|,)\s*({ADDR})", tail)
    if m2 and addr:
        who["two"] = [addr.lower(), m2.group(1).lower()]
    return who, tail


def email_request(text):
    """An email to someone other than the person, read by code: {"to", "word", "name", "request", "subject",
    "post" (the words that point at a shown post, or None), "two", "cc", "pron"}; None when the message is not one
    (an email to the person themselves, a share with no email word or address, a change of their own address)."""
    t = " ".join((text or "").split())
    if not t or len(t) > REQUEST_MAX:
        return None
    if re.search(r"\b(?:my|change|update|set)\s+(?:my\s+)?e-?mail(?:\s+address)?\s+(?:is|to)\b", t, re.I):
        return None
    m = VERB_FIRST.match(t)
    obj = None
    if m:
        rest = m.group("rest").strip()
        verb = m.group("verb").lower()
        if verb.startswith(("e-mail", "email")) and verb in ("email", "e-mail"):
            if SELF_WORDS.match(rest):
                return None
            # "email this to my sister", "email the second one to sam@example.com": the object first, then "to"
            mo = re.match(r"^(?P<obj>.{1,60}?)\s+to\s+(?P<r>.+)$", rest, re.I)
            if mo and POINTS.match(mo.group("obj").strip()):
                obj, rest = mo.group("obj").strip(), mo.group("r").strip()
    elif (LET_KNOW.match(t) or DROP_LINE.match(t)) and not SEND_RCPT_EMAIL.match(t):   # round 10, slice W (W5)
        m = LET_KNOW.match(t) or DROP_LINE.match(t)
        r = m.group("r").strip()
        who, left = _recipient(r, t)
        if who is None or who.get("pron") or left.strip(" ,"):
            return None
        tail = (m.group("tail") or "").strip()
        if tail and not re.match(r"^(?:that|saying|to say|about|asking|re:?)\b", tail, re.I):
            tail = "that " + tail
        rest = r + " " + tail
    elif SEND_RCPT_EMAIL.match(t):
        m = SEND_RCPT_EMAIL.match(t)
        r = m.group("r").strip()
        who, left = _recipient(r, t)
        if who is None or who.get("pron") or left.strip(" ,"):
            return None   # the words before "an email" must be the recipient and nothing else
        rest = r + " " + (m.group("tail") or "")
    else:
        m = SEND_TO_ADDR.match(t)
        if not m:
            return None
        obj, rest = m.group("obj").strip(), m.group("rest").strip()
    if SELF_WORDS.match(rest):
        return None
    who, tail = _recipient(rest, t)
    if who is None:
        return None
    if who.get("pron") and not tail.strip() and not obj:
        who["bare_pron"] = True
    para, subj, points = clause_paragraph(tail)
    if obj and not points:
        points = obj
    out = dict(who, request=para, subject=subj, post=points, cc=bool(CC.search(t)))
    if not obj and not para and not points and tail.strip() and not who.get("pron"):
        # "email my mom a recipe": the words after the recipient are kept as they are, as the request
        out["request"] = sentence(tail.strip(" ,"))
    return out


def repeating_email(text):
    """'every friday email my mom a recipe': an email to someone else on a schedule (refused by code)."""
    t = " ".join((text or "").split())
    if not REPEATING.search(t) or not EMAIL_WORD.search(t):
        return None
    if not (OTHER_RE.search(t) or ADDR_RE.search(t)):
        return None
    if re.search(r"\be-?mail\s+(?:it\s+|them\s+|this\s+)?(?:to\s+)?me\b", t, re.I):
        return None
    return REPEATING.search(t).group(0)


def mailto(to, subject, body, cut_note=None):
    """A mailto: link (RFC 6068): the address percent-encoded, subject and body UTF-8 percent-encoded, spaces as %20,
    line breaks as %0D%0A. A body over LINK_MAX characters is cut at a line boundary and ends with `cut_note`."""
    b = body or ""
    if len(b) > LINK_MAX:
        lines, kept, n = b.split("\n"), [], 0
        for line in lines:
            if n + len(line) + 1 > LINK_MAX - 80:
                break
            kept.append(line)
            n += len(line) + 1
        while kept and not kept[-1].strip():
            kept.pop()
        b = "\n".join(kept) + "\n\n" + (cut_note or "(The rest is in my message above.)")
    q = "subject=" + quote(subject or "", safe="") + "&body=" + quote(b.replace("\r\n", "\n").replace("\n", "\r\n"),
                                                                     safe="")
    return "mailto:" + quote(to or "", safe="@") + "?" + q


def cut_at_section(text, limit=LINK_MAX):
    """W3: a long answer for a link to self, cut at a blank line (a section) when one is near, else at a line;
    never mid-line."""
    if len(text) <= limit:
        return text, False
    head = text[:limit]
    i = head.rfind("\n\n")
    if i < limit // 2:
        i = head.rfind("\n")
    return text[:max(i, 0)].rstrip(), True


# ---------- A6: the checks on what draft_v1 wrote (drafts.grounded) ----------
_PROMPT = {}


def PROMPT_TEXT():   # noqa: N802 - read once, when first used
    if "t" not in _PROMPT:
        import os
        with open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_DRAFT}.md"), encoding="utf-8") as f:
            _PROMPT["t"] = f.read()
    return _PROMPT["t"]


# Capitalised words that are never a fact: greetings, sign-offs and the usual words a sentence starts with (English
# and Spanish). Any other capitalised word, at a sentence's start or not, must be in the sources (a name, a day).
_OK_CAPS = set("""I I'm I'll I've I'd Hi Hello Hey Dear Thanks Thank Best Regards Cheers Please Sorry Sincerely Kind
Warm Hope Could Can Would Will Should May Might Must Let Let's Just Also Hola Gracias Saludos Querido Querida Estimado
Estimada Bonjour Merci Hallo Danke Ciao Grazie Olá Obrigado Obrigada OK Ok Okay PS The This That These Those It It's Its
We We're We'll You You're Your My Our Their They He She His Her There There's Here Here's What What's Which Who How Why
Where When While If As Since Because So But And Or Nor Yet Is Are Was Were Do Does Did Have Has Had Any Anything Is
Not No Yes Sure Happy Glad Great Good Quick Wanted Writing Following Regarding About Thought Saw Found That's Feel One
All Some Each Every Both Once After Before Until Unfortunately Apologies Looking Hoping Just Thanks Many Much More
Also Hopefully Otherwise Meanwhile Please Today Tomorrow Tonight Again Still Right Now Well Lovely Nice Sounds Would
Unless Either Neither Even Really Actually Maybe Perhaps Probably Definitely Of In On At For From With To By Into
El La Los Las Un Una Lo Me Te Se Le Les Nos Mi Mis Tu Tus Su Sus Nuestro Nuestra Que Qué Por Para Con Sin Si Sí Es
Está Estoy Estamos Hay Quería Quiero Queremos Puedes Podrías Podemos Puede Espero Muchas Ya También Solo Cuando Como
Pero Muy Al Del Este Esta Ese Esa Te Avísame Dime Gracias Buenas Buenos Disculpa Lamento Siento Saludos""".split())
CLAIMS = re.compile(r"\b(sent|emailed|paid|cancell?ed|canceled|booked|ordered|bought|applied|attached|enclosed|"
                    r"transferred|wired|signed up|registered|submitted|confirmed|returned|reserved|scheduled|fixed|"
                    r"repaired)\b", re.I)
# (round 9 live fix pass) a sign-off line alone: "Thanks," "Thanks so much!" "Best wishes," - never a sentence that
# starts with thanks ("Thanks for watering my plants." is the email itself; it was cut, leaving an empty body)
_CLOSING_LINE = re.compile(r"^(?:thanks|thank you|many thanks|best|best wishes|regards|kind regards|warm regards|"
                           r"cheers|sincerely|gracias|muchas gracias|saludos|un saludo|merci|danke|grazie|obrigad[oa])"
                           r"(?:[ ,]+(?:so much|again|a lot|very much|in advance|mil))?[\s,!.]*$", re.I)
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
# (check of the live fix pass, fix9) a brief that says its own claim is untrue ("say the report is done even though it
# isn't", "and pretend i was sick", "lie to my boss and say ..."): the email is not written. A negation that goes on to
# say something ("even though it wasn't my fault") is a real statement and stays; "make up an excuse" is draft_v2's to
# leave out (evaluation case d-dev-13)
ADMITS_FALSE = re.compile(
    r"\b(?:even\s+though|although|though)\s+(?:it|i|that|they|we|he|she|this)\s+(?:really\s+)?(?:isn'?t|wasn'?t|"
    r"didn'?t|hasn'?t|haven'?t|won'?t|aren'?t|weren'?t|is\s+not|was\s+not|did\s+not|has\s+not|have\s+not|"
    r"will\s+not|are\s+not|were\s+not)(?:\s+(?:true|done|ready|finished|sent|paid|really|yet))?\s*(?:[,.;!?]|$|"
    r"\band\b|\bbut\b|\bso\b)|\b(?:and|to)\s+pretend\s+(?:that\s+)?(?:i|it)\b|\b(?:lie|fib)\s+(?:to|and\s+say)\b", re.I)
# (round 9 checks) facts the capitalised-word check cannot see: a day or a month written in small letters, "tomorrow"
# and "tonight" (they start sentences, so they are in _OK_CAPS), a number written as a word, and a claim that something
# was already done. Each must be in the sources, in any case. ("may" and "one" are left out: they are ordinary words.)
DATE_WORDS = re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|january|february|"
                        r"march|april|june|july|august|september|october|november|december|today|tonight|tomorrow|"
                        r"yesterday|next\s+(?:week|month|year)|this\s+(?:week|month)|noon|midnight|lunes|martes|"
                        r"miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|hoy|mañana|manana|"
                        r"esta\s+noche)\b", re.I)
NUMBER_WORDS = re.compile(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                          r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
                          r"eighty|ninety|hundred|thousand|million|billion|dozen|third|fourth|fifth|sixth|seventh|"
                          r"eighth|ninth|tenth|dollars?|bucks|euros?|cents?|dos|tres|cuatro|cinco|seis|siete|ocho|"
                          r"nueve|diez|veinte|cien|mil)\b", re.I)
# a word counts as said when the person said it or its equivalent (a translation, the digits): "sábado" for "Saturday"
SAME_AS = {"lunes": "monday", "martes": "tuesday", "miércoles": "wednesday", "miercoles": "wednesday",
           "jueves": "thursday", "viernes": "friday", "sábado": "saturday", "sabado": "saturday", "domingo": "sunday",
           "hoy": "today", "mañana": "tomorrow", "manana": "tomorrow", "esta noche": "tonight",
           "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
           "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
           "hundred": "100", "thousand": "1000", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
           "siete": "7", "ocho": "8", "nueve": "9", "diez": "10", "veinte": "20", "cien": "100", "mil": "1000",
           "dollars": "$", "dollar": "$", "bucks": "$", "euros": "€", "euro": "€"}
DONE_WORDS = re.compile(r"\b(already|taken care of|took care of|completed|finished|settled|handled|spoke|agreed|"
                        r"promised|approved|delivered|received|mailed|texted|ya)\b", re.I)


def _words_in(word, low):
    return re.search(rf"(?<!\w){re.escape(word.lower())}(?!\w)", low) is not None


_GREET_WORDS = set("hi hello hey dear good morning afternoon evening hola querido querida estimado estimada "
                   "buenos buenas "
                   "días dias tardes bonjour hallo ciao olá".split())


def grounded(form, sources, name=None):
    """What is wrong with a draft_v1 form, as short reasons (an empty list: it passes). Every number, address,
    link and capitalised name must be in the sources (the person's message, the recipient word or name, the
    sign-off name, the checked post lines; for a rewrite, the version they saw and the change); nothing may be
    said to be done unless their message says it; no placeholder; at most 1,200 characters."""
    if not isinstance(form, dict):
        return ["the answer was not a form"]
    subj, greet, body, close = (" ".join(str(form.get(k) or "").split()) if k != "body" else str(form.get(k) or "")
                                .strip() for k in ("subject", "greeting", "body", "closing"))
    out = []
    if not body:
        out.append("the body is empty")
    if len(body) > 1200:
        out.append("the body is over 1,200 characters")
    if len(subj) > 120 or len(greet) > 60 or len(close) > 40:
        out.append("the subject, greeting or closing is too long")
    src = "\n".join(s for s in sources if s)
    low = src.lower()
    every = "\n".join([subj, greet, body, close])
    for u in URL_RE.findall(every):
        if u.rstrip(".,);:!?") not in src:
            out.append("a link that is not the post's")
    for a in ADDR_RE.findall(every):
        if a.lower().rstrip(".") not in low:
            out.append(f"the address {a} is not in their message")
    src_nums = set(re.findall(r"\d+", src))
    for n in re.findall(r"\d+", URL_RE.sub(" ", every)):
        if n not in src_nums:
            out.append(f"the number {n} is not in their message")
    for w in re.findall(r"[^\W\d_][\w'’-]*", URL_RE.sub(" ", every)):
        w = w.replace("’", "'")
        if w[0].isupper() and w not in _OK_CAPS and len(w) > 1 and not _words_in(w, low.replace("’", "'")):
            out.append(f"the name {w} is not in their message")
    for m in CLAIMS.finditer(body + "\n" + subj):
        if not _words_in(m.group(1), low):
            out.append(f"it says something was {m.group(1).lower()}, which their message does not say")
    plain = URL_RE.sub(" ", every)
    flat = " ".join(low.split())
    for rx, what in ((DATE_WORDS, "the day or time"), (NUMBER_WORDS, "the number")):
        for m in rx.finditer(plain):
            w = " ".join(m.group(0).lower().split())
            alt = SAME_AS.get(w)
            if not _words_in(w, flat) and not (alt and (alt in flat if not alt.isalnum() else _words_in(alt, flat))):
                out.append(f"{what} \"{w}\" is not in their message")
    for m in DONE_WORDS.finditer(body + "\n" + subj):
        if not _words_in(m.group(1), low):
            out.append(f"it says \"{m.group(1).lower()}\", which their message does not say")
    if name is not None:   # "Hi <name>," only with the name the person typed; never "Hi landlord,"
        allowed = _GREET_WORDS | {w.lower() for w in re.findall(r"[^\W\d_]+", name)}
        if any(w.lower() not in allowed for w in re.findall(r"[^\W\d_]+", greet)):
            out.append("the greeting must be \"Hi,\"" + (f" or \"Hi {name},\"" if name else ""))
        elif re.fullmatch(r"\W*(?:dear|querid[oa]|estimad[oa])\W*", greet, re.I):
            # (round 9 live fix pass) "Dear," with no name is not a greeting anyone writes
            out.append("\"Dear\" needs a name: write \"Hello,\"")
    if re.search(r"\[[^\]]*\]|\(your |\bXX+\b|_{3,}|\{[^}]*\}", every, re.I):
        out.append("a placeholder")
    return list(dict.fromkeys(out))


def clean_form(raw):
    """The checked form, trimmed: no greeting or sign-off inside the body (code adds them)."""
    body = str(raw.get("body") or "").strip().replace("\r\n", "\n")
    lines = body.split("\n")
    if lines and re.match(r"^(?:hi|hello|hey|dear|hola|bonjour|hallo|ciao)\b[^\n.!?]{0,40},\s*$", lines[0], re.I):
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines.pop()
    for i in range(len(lines) - 1, max(len(lines) - 3, -1), -1):
        if _CLOSING_LINE.match(lines[i].strip()):
            lines = lines[:i]
            break
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    greet = " ".join(str(raw.get("greeting") or "").split()) or "Hi,"
    close = " ".join(str(raw.get("closing") or "").split()) or "Thanks,"
    return {"subject": " ".join(str(raw.get("subject") or "").split())[:120], "greeting": greet, "body": body,
            "closing": close}


def draft_user(p, sign, change=None, current=None):
    """(the user text for draft_v1, the sources its words are checked against). The post's own text never goes in:
    only the checked lines code would have used (title, creator, at most two checked points, the link)."""
    post = p.get("post") if p.get("post") and not p.get("no_post") else None
    post_lines = []
    if post:
        post_lines = [post.get("title") or "", post.get("creator") or ""] + list(post.get("points") or [])[:2] + \
            [post.get("url") or ""]
    name, role = p.get("greet_name") or "", p.get("to_word") or ""
    message = p.get("text") or p.get("request") or ""
    user = (f"<request>{message}</request>\n<to_name>{name}</to_name>\n<to_role>{role}</to_role>\n"
            f"<sign_as>{sign or ''}</sign_as>\n"
            + ("<post>\n" + "\n".join(x for x in post_lines if x) + "\n</post>\n" if post else "")
            + (f"<current>{current}</current>\n<change>{change}</change>\n" if change else ""))
    return user, [message, name, sign or "", *post_lines, current or "", change or ""]


def model_write(p, sign, handle, change=None, current=None):
    """One draft_v1 call through llm.py (logged with its cost, purpose "draft") and, when a check fails, one retry
    that names the failure. Returns (the checked form or None, attempts, the first try's problems)."""
    from . import llm
    user, sources = draft_user(p, sign, change, current)
    why, first, attempts = None, [], 0
    for attempt in range(2):
        attempts = attempt + 1
        try:
            raw, _cost = llm.chat_json(PROMPT_TEXT(), user + (f"\nYour last answer failed a check: {why}. Fix only "
                                                              "that." if why else ""),
                                       purpose="draft", prompt_version=config.PROMPT_DRAFT, person=handle,
                                       max_tokens=600)
        except Exception as e:  # noqa: BLE001 - a failed call: the code-built words stand
            print(f"{config.PROMPT_DRAFT}: {type(e).__name__}", file=__import__("sys").stderr)
            return None, attempts, first or ["the call failed"]
        problems = grounded(raw, sources, name=p.get("greet_name") or "")
        if not problems:
            form = clean_form(raw)
            if form["body"]:
                return form, attempts, first
            problems = ["the body is only a greeting or a sign-off"]   # (round 9 live fix pass) never an empty email
        if attempt == 0:
            first = problems
        why = "; ".join(problems[:3])
    return None, attempts, first


def render_body(p, sign):
    """The body from the draft's parts: greeting, the words, the post block, extra paragraphs, the sign-off."""
    greet = p.get("greeting") or (f"Hi {p['greet_name']}," if p.get("greet_name") else "Hi,")
    paras = []
    if p.get("model_body"):
        paras.append(p["model_body"].strip())
    elif p.get("request"):
        paras.append(p["request"])
    paras += [x for x in p.get("paragraphs") or [] if x]
    post = p.get("post")
    if post and not p.get("no_post"):
        lines = []
        if not p.get("model_body") or not (post.get("title") and post["title"] in p["model_body"]):
            head = post.get("title") or "A post"
            lines.append(head + (f" by {post['creator']}" if post.get("creator") else ""))
            if not post.get("sensitive"):
                lines += [x for x in (post.get("points") or [])[:2]]
        if post.get("url") and p.get("link", True) and not (p.get("model_body") and post["url"] in p["model_body"]):
            lines.append(post["url"])
        if lines:
            paras.append("\n".join(lines))
        for x in post.get("more") or []:   # "email them to ...": the other posts, each its title and link
            paras.append("\n".join([x["title"] + (f" by {x['creator']}" if x.get("creator") else "")]
                                   + ([x["url"]] if x.get("url") and p.get("link", True) else [])))
    paras += [x for x in p.get("extra") or [] if x]
    closing = p.get("closing") or "Thanks,"
    end = closing + ("\n" + sign if sign else "")
    body = "\n\n".join([greet] + paras + [end])
    if p.get("model_body") and post and post.get("url") and not p.get("link", True):
        body = body.replace(post["url"], "").replace("\n\n\n", "\n\n")
    return body


def exact_text(to, subject, body):
    """What one version is: the recipient, the subject and the body, exactly (its hash is the version's text_hash)."""
    return f"{to or ''}\n{subject or ''}\n{body or ''}"


def _fill_line(paragraphs, label, value):
    """The paragraphs with the line that starts with `label` and holds the placeholder filled with `value`, or taken
    out when `value` is None. A line inside a paragraph counts (a notice's facts are lines of one paragraph)."""
    out = []
    for para in paragraphs:
        lines = []
        for ln in para.split("\n"):
            if ln.lower().startswith(label.lower()) and T.PLACEHOLDER in ln:
                if value is None:
                    continue
                ln = ln.replace(T.PLACEHOLDER, value, 1)
            lines.append(ln)
        if lines:
            out.append("\n".join(lines))
    return out


# ---------- round 10, slice W (W5): a word swapped or a sentence taken out, only where the draft's words hold it ----------
def _text_fields(p):
    """(key, index or None) of each of the draft's own text fields, the words first."""
    out = [("model_body", None)] if p.get("model_body") else ([("request", None)] if p.get("request") else [])
    out += [("paragraphs", i) for i, x in enumerate(p.get("paragraphs") or []) if x]
    out += [("extra", i) for i, x in enumerate(p.get("extra") or []) if x]
    return out


def _get(p, key, i):
    return p[key] if i is None else p[key][i]


def _set(p, key, i, v):
    if i is None:
        p[key] = v
    else:
        p[key][i] = v


def _replace_words(t):
    """The words "say X not Y" would replace, or "take out the part about X" would take out; None when neither."""
    m = CH_REPLACE.match(t)
    if m:
        return (m.group("y") or m.group("y2") or "").strip(" .\"'") or None
    m = CH_DROP_PART.match(t)
    return m.group("x").strip(" .\"'") if m else None


def _replace_in_parts(p, t):
    """New parts for "say X not Y" (Y must be a whole word or phrase in the words; each place it is becomes X) or
    "take out the part about X" (the sentences holding X go; at least one sentence is left). None when the message is
    neither, or the words do not hold Y / X."""
    import copy
    m = CH_REPLACE.match(t)
    if m:
        x = (m.group("x") or m.group("x2") or "").strip(" .\"'")
        y = (m.group("y") or m.group("y2") or "").strip(" .\"'")
        if not x or not y or x.lower() == y.lower():
            return None
        q, hit = copy.deepcopy(p), False
        rx = re.compile(r"(?<![\w])" + re.escape(y) + r"(?![\w])", re.I)
        for key, i in _text_fields(q):
            old = _get(q, key, i)

            def keep_case(mm):
                w = mm.group(0)
                return x[:1].upper() + x[1:] if w[:1].isupper() else x
            new = rx.sub(keep_case, old)
            if new != old:
                _set(q, key, i, new)
                hit = True
        return q if hit else None
    m = CH_DROP_PART.match(t)
    if m:
        x = m.group("x").strip(" .\"'")
        x = re.sub(r"^(?:the|my|a|an)\s+", "", x, flags=re.I)
        if len(x) < 3:
            return None
        rx = re.compile(r"(?<![\w])" + re.escape(x) + r"(?![\w])", re.I)
        q, hit = copy.deepcopy(p), False
        for key, i in _text_fields(q):
            old = _get(q, key, i)
            sents = re.split(r"(?<=[.!?])\s+", old)
            kept = [z for z in sents if not rx.search(z)]
            if len(kept) != len(sents):
                hit = True
                _set(q, key, i, " ".join(kept))
        left = " ".join(_get(q, k, i) for k, i in _text_fields(q) if _get(q, k, i).strip())
        if not hit or not left.strip():
            return None
        if q.get("model_body") is not None and not q["model_body"].strip():
            q["model_body"] = None
        return q
    return None
# ---------- end round 10, slice W ----------


def placeholders_left(row):
    p = row.get("parts")
    p = p if isinstance(p, dict) else json.loads(p or "{}")
    return [x for x in (p.get("placeholders") or []) if T.PLACEHOLDER in (row.get("body") or "")]


class DraftsMixin:
    # ---------- the store's rows ----------
    def _draft(self, draft_id):
        return self.store.draft(draft_id)

    def open_draft(self, handle, now=None):
        """The person's open draft (a dict with its parts), or None: one shown or asked about in the last 24 hours
        that was not cancelled, sent or marked sent by them."""
        st = self.store.get_state(f"draft_open:{handle}")
        if not st:
            return None
        now = now or self.clock()
        if now - datetime.fromisoformat(st["at"]) > timedelta(hours=OPEN_HOURS):
            row = self._draft(st["id"])
            if row and row["status"] in ("open", "link_shown"):
                self.store.update_draft(st["id"], status="expired", done_at=now_iso(now))
            self.store.set_state(f"draft_open:{handle}", None)
            return None
        row = self._draft(st["id"])
        if not row or row["status"] not in ("open", "link_shown", "held", "failed"):
            return None
        row["parts"] = json.loads(row.get("parts") or "{}")
        row["state"] = st
        return row

    def _draft_touch(self, h, draft_id, now, **st):
        cur = self.store.get_state(f"draft_open:{h}") or {}
        if cur.get("id") != draft_id:
            cur = {}
        cur.update(st, id=draft_id, at=now_iso(now))
        self.store.set_state(f"draft_open:{h}", cur)

    def _log_draft(self, h, action, row, status="done", now=None, **more):
        p = row["parts"] if isinstance(row.get("parts"), dict) else json.loads(row.get("parts") or "{}")
        detail = {"kind": row.get("kind"), "route": row.get("route"), "version": row.get("version"),
                  "recipient_domain": None if row.get("kind") == "notice" else
                  (domain_of(row.get("to_addr")) or row.get("to_domain")),
                  "body_from": p.get("body_from") or "words", **more}
        self.store.log_action(h, None, None, action, status, ref=str(row["id"]), detail=detail, at=now or self.clock())

    # ---------- starting a draft ----------
    def draft_start(self, person, kind, to=None, to_name=None, subject=None, paragraphs=(), post=None,
                    placeholders=(), job=None, now=None, to_word=None, request=None, greeting=None, closing=None,
                    sources=None, note=None, text=None, sign=None, head=None, to_hint=None):
        """Opens a draft card and returns the first message's reference. kind: "email" (W2) or "notice" (W6's
        cancellation notice: greeting "Hello,", closing "Thank you,"). to: an address the person typed; None asks for
        one; "" leaves To blank. paragraphs: the body's words, used as they are. post: a checked post block
        ({title, creator, points, url, sensitive, stale}). placeholders: labels of "(fill this in)" lines ("member
        number"); while one is left the link and "send" are held back. job: who started it ("cancel:3"). sign: the
        sign-off name, not asked for (a notice signs with the name on the membership). head: the card's first line in
        place of "Here's the email." to_hint: what the To line says while it is blank."""
        h = person["handle"]
        now = now or self.clock()
        route = self._send_route(h)   # round 10, slice D: the one route chooser (read again at "send")
        p = {"greet_name": to_name, "to_word": to_word, "request": request, "paragraphs": list(paragraphs or []),
             "post": post, "link": True, "extra": [], "changes": 0, "placeholders": list(placeholders or []),
             "greeting": greeting or ("Hello," if kind == "notice" else None),
             "closing": closing or ("Thank you," if kind == "notice" else None),
             "subject_set": bool(subject), "body_from": "pick" if post and not request and not paragraphs else "words",
             "note": note, "text": (getattr(self._tl, "norm_of", None) or text or "")[:REQUEST_MAX]}
        if sign is not None:
            p["sign"] = sign
        if head:
            p["head"] = head
        if to_hint:
            p["to_hint"] = to_hint
        subj = subject or self._draft_subject_of(p)
        draft_id = self.store.add_draft(h, kind, route, to if to else None, to_name, subj, p, job=job,
                                        sources=sources, at=now)
        self._log_draft(h, "draft.made", {"id": draft_id, "kind": kind, "route": route, "version": 0, "to_addr": to,
                                          "parts": p}, now=now)
        if to is None:
            return self._draft_ask_to(person, draft_id, p, now)
        self._draft_touch(h, draft_id, now, waiting=None)
        return self._draft_after_to(person, draft_id, now)

    def _draft_subject_of(self, p):
        if p.get("post") and p["post"].get("title") and not p.get("request"):
            return p["post"]["title"][:150]
        words = p.get("request") or next((x for x in p.get("paragraphs") or [] if x), "") or ""
        words = words.split("\n")[0]
        # (round 9 live fix pass) a statement, then a question: the subject is the statement alone
        words = re.split(r"(?<=[.!?])\s+(?=[A-Z])", words, maxsplit=1)[0].rstrip(".")
        if len(words) > 60:
            words = words[:60].rsplit(" ", 1)[0]
        return words or (p["post"]["title"][:150] if p.get("post") and p["post"].get("title") else "Hello")

    def _draft_ask_to(self, person, draft_id, p, now, lead=""):
        h = person["handle"]
        self._draft_touch(h, draft_id, now, waiting="to", asked_at=now_iso(now))
        whose = (f"{p['greet_name']}'s" if p.get("greet_name") else
                 f"your {p['to_word']}'s" if p.get("to_word") else "their")
        return self.send(h, lead + T.draft_who(whose))

    def _draft_after_to(self, person, draft_id, now):
        """Once the recipient is known: the sign-off name (asked once), the words (asked when there are none), then
        the card."""
        h = person["handle"]
        row = self._draft(draft_id)
        p = json.loads(row["parts"])
        if "sign" not in p and self._draft_sign_name(person) is None:
            self._draft_touch(h, draft_id, now, waiting="sign", asked_at=now_iso(now))
            return self.send(h, T.DRAFT_SIGN_ASK)
        if not (p.get("request") or p.get("paragraphs") or p.get("post") or p.get("model_body")):
            self._draft_touch(h, draft_id, now, waiting="say", asked_at=now_iso(now))
            return self.send(h, T.DRAFT_SAY_ASK)
        if row["version"] == 0 and row["kind"] == "email":
            self._draft_model_body(person, draft_id, now)   # A6: the model writes it (when on); code checks it
        return self._draft_show(person, draft_id, now, new=False)

    def _draft_sign_name(self, person):
        """The sign-off name: prefs.sign_as (empty: no name), else the first word of people.name, else None."""
        prefs = json.loads(person.get("prefs") or "{}") if isinstance(person.get("prefs"), str) else \
            (person.get("prefs") or {})
        if "sign_as" in prefs:
            return prefs["sign_as"] or ""
        name = (person.get("name") or "").strip()
        return name.split()[0] if name else None

    def _draft_render(self, person, row, p=None):
        p = p if p is not None else json.loads(row["parts"])
        sign = p["sign"] if "sign" in p else (self._draft_sign_name(person) or "")
        return render_body(p, sign)

    # ---------- the card ----------
    def _draft_show(self, person, draft_id, now, new=False, lead=""):
        """Renders the version, stores it with its hash, and sends the card: (1) what it is, To, Subject; (2) the
        body alone; (3) the link (or, for the operator's mailbox, "send"), and how to change it. Returns the first
        message's reference."""
        from .actions import Refused, perform, text_hash
        h = person["handle"]
        person = self.store.person(h) or person
        row = self._draft(draft_id)
        # ---------- round 10, slice D: the card shows the route as it is now (a "send" checks it again) ----------
        cur = self._send_route(h)
        if row.get("route") != cur and row["status"] != "held":
            self.store.update_draft(draft_id, route=cur)
            row = self._draft(draft_id)
        # ---------- end round 10, slice D ----------
        p = json.loads(row["parts"])
        body = self._draft_render(person, row, p)
        to = row.get("to_addr") or ""
        th = text_hash(exact_text(to, row["subject"], body))
        same = bool(row.get("version")) and th == row.get("text_hash")   # shown again, unchanged: the same version
        version = row["version"] if same else (row.get("version") or 0) + 1
        if not same and row["status"] == "held" and self._draft_stop_hold(h, row, now):
            # (round 9 checks) the words came out different (their sign-off name changed meanwhile): the yes was for
            # the old words, so the send stops, and the person is told rather than left waiting for it
            lead = T.HOLD_STOPPED_BY_CHANGE + "\n\n" + lead
            row = self._draft(draft_id)
        status = "held" if same and row["status"] == "held" else "link_shown"
        self.store.update_draft(draft_id, body=body, version=version, text_hash=th, shown_at=now_iso(now),
                                status=status)
        row = self._draft(draft_id)
        self._draft_touch(h, draft_id, now, waiting=None, shown_version=version)
        to_line = T.draft_to_line(to) if to or not p.get("to_hint") else f"To: {p['to_hint']}"
        head = (T.DRAFT_NEW_VERSION if new else (p.get("head") or T.DRAFT_HEAD)) + "\n" + to_line + "\n" + \
            f"Subject: {row['subject']}"
        if p.get("post") and p["post"].get("sensitive") and not p.get("no_post"):
            head += "\n" + T.DRAFT_SENSITIVE
        if p.get("note"):
            head += "\n" + p["note"]
        ref = self.send(h, lead + head)
        refs = [ref, self.send(h, body)]
        left = placeholders_left(row)
        if left:
            refs.append(self.send(h, T.fill_first(left[0])))
            self._draft_touch(h, draft_id, now, refs=refs)
            if new:
                self._log_draft(h, "draft.changed", row, now=now)
            return ref
        cut = (T.DRAFT_REST_IN_POST.format(url=p["post"]["url"]) if p.get("post") and p["post"].get("url")
               and p.get("link", True) and not p.get("no_post") else None)
        o = None
        try:
            from .actions.base import Ctx
            ctx = Ctx(bot=self, person=person, answer={}, picks=[], kind="draft", now=now, tz=person["timezone"])
            o = perform("email.draft_link", ctx, {"draft_id": draft_id, "cut_note": cut})
        except Refused:
            o = None
        except Exception as e:  # noqa: BLE001 - the body is in message 2 either way
            print(f"draft link: {type(e).__name__}", file=__import__("sys").stderr)
        link = (o.detail or {}).get("url") if o and o.status == "done" else None
        self._log_draft(h, "email.draft_link", row, status=o.status if o else "failed", now=now,
                        **({"cap": (o.detail or {}).get("cap")} if o and o.status == "skipped" else {}))
        if new:
            self._log_draft(h, "draft.changed", row, now=now)
        if link is None:
            refs.append(self.send(h, (o.line + " " if o and o.line else "") + T.DRAFT_COPY_IT))
        else:
            sender = self._mailbox_sender(h) if row["route"] == "mailbox" else None
            refs.append(self.send(h, T.draft_link_message(link, sender)))
        self._draft_touch(h, draft_id, now, refs=refs)
        return ref

    def _draft_job_done(self, row, how, now):
        """A draft another helper started (job "cancel:<id>", the cancel helper's notice) hears how it ended: "sent"
        (the mail server took it, or the person says they sent it) or "dropped". Returns a line to add to the reply."""
        job = row.get("job") or ""
        if job.startswith("todo:") and job[5:].isdigit():   # round 9, W10: a to-do handed to the draft
            return self._doit_ticked(row["handle"], int(job[5:]), now) if how in ("sent", "bot_sent") else ""
        if not job.startswith("cancel:") or not job[7:].isdigit():
            return ""
        # ---------- round 10, slice D: a notice that went gets the follow-up offer (cancel.py) ----------
        if how in ("sent", "bot_sent"):
            return " " + self._cancel_notice_went(int(job[7:]), row, by_bot=how == "bot_sent", now=now)
        # ---------- end round 10, slice D ----------
        self.store.update_cancellation(int(job[7:]), at=now, status="dropped")
        return ""

    # ---------- the person's next messages while a draft is open ----------
    def draft_reads(self, person, text, pending, now):
        """Round 9, slice A: the messages a draft card owns. Runs in _on_message right after the confirm_delete
        branch (verdict section 4, hook 1). Returns a reply reference, or None for anything it does not own."""
        h = person["handle"]
        d = self.open_draft(h, now)
        t = " ".join((text or "").split())
        if d is None:
            if SEND_WORDS.match(t) and self._draft_just_finished(h, now):
                return self._draft_send_again(person, now)
            # ---------- round 10, slice W (W1): "email it to me" with nothing written and no answer in view ----------
            if SELF_COPY_TO_ME.match(t) and not self.store.last_answer(h) and not self._plain_answer(h) \
                    and not self._export_in_view(h, now):   # (round 8: "email it to me" right after an export)
                self.note(intent="unsupported")
                return self.send(h, T.NOTHING_TO_EMAIL)
            # ---------- end round 10, slice W ----------
            return None
        st = d["state"]
        waiting = st.get("waiting")
        draft_at = datetime.fromisoformat(st["at"])
        pend_at = datetime.fromisoformat(pending["at"]) if pending and pending.get("at") else None
        draft_newer = pend_at is None or draft_at >= pend_at
        # a recipient typed in answer to "Who should it go to?" (F6: only when that question is newer than the
        # bot's own "what's your email address?")
        if waiting == "to":
            got = addresses(t)
            asked_self = self.store.get_state(f"emailask:{h}")
            ours = datetime.fromisoformat(st.get("asked_at") or st["at"])
            newer = not asked_self or ours > datetime.fromisoformat(asked_self)
            bare = re.match(rf"^\W*(?:(?:it'?s|its|it is|use|send it to|to:?|their (?:email|address) is|"
                            rf"(?:his|her) (?:email|address) is)\s+)?({ADDR})\s*[.!]?\s*$", t, re.I)
            if bare and newer:
                return self._draft_set_to(person, d, bare.group(1).lower(), now)
            if len(got) >= 2 and newer and not CANCEL_WORDS.match(t):
                return self.send(h, T.draft_which_address(got[:2]))
            if CC.search(t) and newer:
                return self.send(h, T.DRAFT_ONE_AT_A_TIME)
            if BLANK.match(t):
                return self._draft_set_to(person, d, "", now)
        # ---------- round 10, slice W (W1): the draft to the person themselves; the card stays open ----------
        if SELF_COPY.match(t):
            return self._draft_to_self(person, d, now)
        # ---------- end round 10, slice W ----------
        if SEND_QUESTION.match(t):   # round 9 checks: "send it?" asks; it is never the yes
            self.note(intent="draft_send")
            if waiting in ("to", "sign", "say"):
                return self.send(h, T.DRAFT_NOT_READY)
            hold = self.store.get_state(f"sendhold:{h}") or {}
            if d["status"] == "held" and hold.get("draft_id") == d["id"]:
                return self.send(h, T.mailbox_already_held(self._clock(datetime.fromisoformat(hold["due_at"]),
                                                                       person)))
            return self.send(h, T.DRAFT_SEND_ASKED if d["route"] == "mailbox" and self._mailbox_route(h)
                             # round 10, slice D: the operator hears how to switch sending on
                             else self._switch_on_line(h) if config.is_operator(h) else T.DRAFT_SEND_LINK)
        if waiting == "sign" and not CANCEL_WORDS.match(t) and not SEND_WORDS.match(t) and "?" not in t \
                and not re.search(r"\b(?:what|why|how|who|when|where|help|stop|undo|show|draft|email)\b", t, re.I):
            if NO_NAME.match(t):
                self.store.set_prefs(h, sign_as="")
                return self._draft_after_to(self.store.person(h), d["id"], now)
            m = SIGN_NAME.match(t)
            if m and len(m.group(1).split()) <= 3 and not YES_WORDS.match(t):
                self.store.set_prefs(h, sign_as=cap(m.group(1).strip()))
                return self._draft_after_to(self.store.person(h), d["id"], now)
        if waiting == "say" and not CANCEL_WORDS.match(t) and not SEND_WORDS.match(t) and not YES_WORDS.match(t) \
                and not SAVE_DRAFT.match(t):
            m = CH_INSTEAD.match(t) or CH_ADD.match(t)
            words = (m.group("x") or m.groupdict().get("y") or t) if m else t
            p = d["parts"]
            p["request"] = sentence(words)
            self.store.update_draft(d["id"], parts=p,
                                    subject=d["subject"] if p.get("subject_set") else self._draft_subject_of(p))
            return self._draft_after_to(person, d["id"], now)
        # ---------- round 10, slice D: "send it for me" (the send word) and "can you send it for me" (a question) ----
        fm = SEND_FOR_ME.match(t) or SEND_ASK.match(t)
        if fm:
            self.note(intent="draft_send")
            if waiting in ("to", "sign", "say"):
                return self.send(h, T.DRAFT_NOT_READY)
            if fm.re is SEND_ASK or "?" in t:
                return self._draft_send_asked(person, d, now)
            return self._draft_send_word(person, d, now)
        # ---------- end round 10, slice D ----------
        if SEND_WORDS.match(t):
            self.note(intent="draft_send")
            if waiting in ("to", "sign", "say"):
                return self.send(h, T.DRAFT_NOT_READY)
            return self._draft_send_word(person, d, now)
        if CANCEL_WORDS.match(t):
            if not draft_newer and pending:
                self.store.clear_pending(h)
                return self.send(h, (T.NOT_STARTED if pending["kind"] == "confirm_rule" else T.WAITING_FOR_ANSWER)
                                 + " " + T.DRAFT_STILL_OPEN)
            return self._draft_cancel(person, d, pending, now)
        if YES_WORDS.match(t) and waiting is None:
            if pending and pending["kind"] == "confirm_rule":
                return None   # the rule preview takes its yes, as today
            if self._draft_card_in_view(h, d):
                self.note(intent="draft_yes")
                return self.send(h, T.DRAFT_YES_MAILBOX if d["route"] == "mailbox" else T.DRAFT_YES)
            return None
        if SHOW_WORDS.match(t):
            self.note(intent="draft_show")
            return self._draft_show(person, d["id"], now, new=False)
        if SENT_WORDS.match(t) and d["status"] == "link_shown":
            self.store.update_draft(d["id"], status="person_sent", done_at=now_iso(now))
            self.store.set_state(f"draft_open:{h}", None)
            self._log_draft(h, "draft.person_sent", d, now=now)
            self.note(intent="draft_sent")
            return self.send(h, T.DRAFT_THANKS + self._draft_job_done(d, "sent", now))
        if SAVE_DRAFT.match(t) and (re.search(r"\bdrafts?\b", t, re.I) or self._draft_card_in_view(h, d)):
            # (check of the live fix pass, fix9) "put this in my email" is about the newest thing shown: with a newer
            # answer after the card, it is that answer's (as before finding 107); a word "draft" means the card
            return self._save_to_drafts(person, d, now)
        # round 10, slice W (W5): "save it, i'll send it myself" with the card in view
        if SAVE_IT.match(t) and waiting is None and self._draft_card_in_view(h, d):
            return self._save_to_drafts(person, d, now)
        return self._draft_change(person, d, t, now)

    def _draft_card_in_view(self, h, d):
        """The card is the newest thing the bot sent this person (so a bare "yes" or "ok" is about it)."""
        row = self.store.one("SELECT channel_ref FROM sent WHERE handle=? ORDER BY rowid DESC LIMIT 1", (h,))
        refs = d["state"].get("refs") or []
        return bool(row and row["channel_ref"] in refs) or not refs

    # ---------- round 10, slice W (W1): the draft to the person themselves ----------
    def _draft_to_self(self, person, d, now):
        """'email it to me' with a card open: with a confirmed address and email set up, the draft's words go to the
        person's own address (email.send: only ever to them, no hold, as for every email to self); else a mailto:
        link with their address in To (blank when unknown) and the card's exact subject and body. Nothing goes to the
        other person, and the card stays open."""
        from .actions import perform
        from .actions.base import Ctx
        from .actions.email import smtp_settings
        h = person["handle"]
        person = self.store.person(h) or person
        self.note(intent="draft_self_copy")
        p = d["parts"]
        waiting = d["state"].get("waiting")
        body = d.get("body") if d.get("version") and d.get("body") and not waiting else \
            self._draft_render(person, d, p)
        whom = T.draft_whom(p.get("greet_name"), p.get("to_word"))
        own, confirmed = self.store.email_of(h)
        self._draft_touch(h, d["id"], now)
        if own and confirmed and smtp_settings():
            ctx = Ctx(bot=self, person=person, picks=[], kind="draft", now=now, tz=person["timezone"],
                      answer={"kind": "draft_copy", "subject": d["subject"], "parts": [{"type": "text", "text": body}]})
            o = perform("email.send", ctx, {})
            self._log_draft(h, "draft.self_copy", d, status=o.status, now=now, route_self="email")
            if o.status == "done":
                self._wrote_final(h, "an email")
                return self.send(h, T.draft_self_emailed(_masked_dots(own), whom))
            return self.send(h, ((o.line or "") + " " + T.draft_still_open(whom, waiting == "to")).strip())
        self._log_draft(h, "draft.self_copy", d, status="link", now=now, route_self="link")
        link = mailto(own or "", d["subject"], body)
        return self.send(h, T.draft_self_link(link, whom, waiting == "to" or not d.get("to_addr")))
    # ---------- end round 10, slice W ----------

    def _draft_set_to(self, person, d, addr, now):
        h = person["handle"]
        self.store.update_draft(d["id"], to_addr=addr or None)
        self._draft_touch(h, d["id"], now, waiting=None)
        if d["version"]:
            return self._draft_changed(person, d["id"], now)
        return self._draft_after_to(person, d["id"], now)

    def _draft_cancel(self, person, d, pending, now):
        h = person["handle"]
        self.note(intent="draft_cancel")
        self._draft_stop_hold(h, d, now)
        self.store.update_draft(d["id"], status="cancelled", done_at=now_iso(now))
        self.store.set_state(f"draft_open:{h}", None)
        self._log_draft(h, "draft.cancelled", d, now=now)
        self._draft_job_done(d, "dropped", now)
        line = T.DRAFT_DROPPED if d["version"] else T.DRAFT_DROPPED_UNSHOWN
        if pending and pending["kind"] == "confirm_rule":
            line += " " + T.PREVIEW_STILL_OPEN
        return self.send(h, line)

    def _draft_change(self, person, d, t, now):
        """One change by code: a new version, and the whole card again. None when the message is not a change."""
        h = person["handle"]
        p = d["parts"]
        left = placeholders_left(d)
        if left:
            if REMOVE_IT.match(t):
                lab = left[0]
                p["paragraphs"] = _fill_line(p.get("paragraphs") or [], lab, None)
                p["placeholders"] = [x for x in p["placeholders"] if x != lab]
                return self._draft_apply(person, d, p, now)
            for lab in left:
                m = re.match(rf"^\W*{re.escape(lab)}\s*(?:is\s+)?[:\-]?\s*(?P<v>\S.{{0,80}}?)\W*$", t, re.I)
                if m:
                    p["paragraphs"] = _fill_line(p.get("paragraphs") or [], lab, m.group("v"))
                    p["placeholders"] = [x for x in p["placeholders"] if x != lab]
                    return self._draft_apply(person, d, p, now)
        m_to = CH_TO.match(t)
        if TONE.search(t) and (TONE_ASK.match(t) or len(t.split()) <= 4):
            return self._draft_tone(person, d, t, now)
        kind = None
        if m_to:
            kind = "to"
        elif CH_SUBJECT.match(t):
            kind = "subject"
        elif CH_NOSIGN.match(t):
            kind = "nosign"
        elif CH_SIGN.match(t):
            kind = "sign"
        elif CH_NOLINK.match(t):
            kind = "nolink"
        elif CH_NOPOST.match(t):
            kind = "nopost"
        elif CH_LINKBACK.match(t):
            kind = "linkback"
        elif CH_INSTEAD.match(t):
            kind = "instead"
        elif CH_ADD.match(t) and not NOT_A_CHANGE.search(t):
            kind = "add"
        # ---------- round 10, slice W (W5): "say tuesday not monday", "take out the part about the doctor" -------
        edited = None
        if kind is None or kind == "add":
            edited = _replace_in_parts(p, t)
            if edited is not None:
                kind = "edited"
            elif _replace_words(t) and self._draft_card_in_view(h, d):
                # the words to change are not in the draft: said plainly, nothing changed (never a reminder)
                self.note(intent="draft_change")
                return self.send(h, T.draft_words_not_found(_replace_words(t)))
            elif kind is None:
                return None
        # ---------- end round 10, slice W ----------
        if (p.get("changes") or 0) >= MAX_CHANGES:
            return self.send(h, T.DRAFT_TOO_MANY_CHANGES)
        if kind == "to":
            a = m_to.group("a").lower()
            self.store.update_draft(d["id"], to_addr=a)
        elif kind == "subject":
            p["subject_set"] = True
            self.store.update_draft(d["id"], subject=cap(CH_SUBJECT.match(t).group("x"))[:150])
        elif kind == "nosign":
            p["sign"] = ""
        elif kind == "sign":
            p["sign"] = cap(CH_SIGN.match(t).group("x"))
        elif kind == "nolink":
            p["link"] = False
        elif kind == "nopost":
            p["no_post"] = True
        elif kind == "linkback":
            p["link"], p["no_post"] = True, False
        elif kind == "instead":
            m = CH_INSTEAD.match(t)
            p["request"] = sentence(m.group("x") or m.group("y"))
            p["model_body"] = None
            p["body_from"] = "words"
        elif kind == "add":
            p.setdefault("extra", []).append(sentence(CH_ADD.match(t).group("x")))
        elif kind == "edited":   # round 10, slice W (W5)
            p = edited
        return self._draft_apply(person, d, p, now)

    def _draft_same(self, person, d, p):
        """(round 9 live fix pass, finding 105) True when these parts make exactly the words of the version last
        shown (same recipient, subject and body, spacing aside): no new version, and nothing to call new."""
        if not d.get("version") or not d.get("body"):
            return False
        row = self._draft(d["id"])
        body = self._draft_render(self.store.person(person["handle"]) or person, row, p)
        flat = lambda s: " ".join((s or "").split())  # noqa: E731
        return (flat(body) == flat(d["body"]) and (row.get("to_addr") or "") == (d.get("to_addr") or "")
                and flat(row.get("subject")) == flat(d.get("subject")))

    def _draft_same_line(self, person, d, line):
        """(check of the live fix pass, fix9) the "nothing changed" line; when a send of these same words is waiting in
        its hold, it says so (the person asked for a change, so they may think the send stopped: it did not)."""
        hold = self.store.get_state(f"sendhold:{person['handle']}")
        if hold and hold.get("draft_id") == d["id"] and hold.get("due_at"):
            line += " " + T.mailbox_already_held(self._clock(datetime.fromisoformat(hold["due_at"]), person))
        return self.send(person["handle"], line)

    def _draft_apply(self, person, d, p, now):
        if self._draft_same(person, d, p):
            self.note(intent="draft_change")
            return self._draft_same_line(person, d, T.DRAFT_SAME_TEXT)
        p["changes"] = (p.get("changes") or 0) + 1
        self.store.update_draft(d["id"], parts=p)
        return self._draft_changed(person, d["id"], now)

    def _draft_changed(self, person, draft_id, now):
        """A new version: any send waiting for the old one stops (its yes was for other words)."""
        h = person["handle"]
        row = self._draft(draft_id)
        stopped = self._draft_stop_hold(h, row, now)
        return self._draft_show(person, draft_id, now, new=True,
                                lead=(T.HOLD_STOPPED_BY_CHANGE + "\n\n") if stopped else "")

    def _draft_tone(self, person, d, t, now):
        """'make it shorter', 'more formal', 'in Spanish': with draft_v1 on, the model rewrites the last shown version
        under the same checks (A6); otherwise, or when that fails, the fixed line."""
        h = person["handle"]
        p = d["parts"]
        if (p.get("changes") or 0) >= MAX_CHANGES:
            return self.send(h, T.DRAFT_TOO_MANY_CHANGES)
        tried = self._draft_model_ok(person, now) and d["kind"] == "email"
        got = self._draft_model_rewrite(person, d, t, now)
        if not got or self._draft_same(person, d, got):
            # (round 9 live fix pass, finding 105) the model was asked but its rewrite failed the checks or came back
            # with the same words: said plainly, with what the person can do; never "the new version", never a change
            if not tried:
                return self.send(h, T.DRAFT_NO_TONE)
            self.note(intent="draft_change")
            if not got and getattr(self._tl, "draft_call_failed", False):
                return self._draft_same_line(person, d, T.DRAFT_TONE_FAILED)
            m = TONE.search(t)
            return self._draft_same_line(person, d, T.draft_tone_same(m.group(0).lower() if m else None))
        return self._draft_apply(person, d, got, now)

    # ---------- the email request, read before the model (hook 5 in answer_normally) ----------
    def email_reads(self, person, text, now):
        """'email my landlord that the sink is broken' and the other forms of email_request: a draft card, with no
        model call. 'every friday email my mom a recipe': refused. None for anything else."""
        h = person["handle"]
        ref = self.mailbox_reads(person, text, now)   # A5: the operator's own Drafts folder
        if ref is not None:
            return ref
        when = repeating_email(text)
        if when:
            self.note(intent="unsupported")
            self.store.log_request(h, "email someone on a schedule", "unsupported")
            return self.send(h, T.draft_no_schedule(when))
        req = email_request(text)
        if req is None:
            return None
        if self._another_ask(person, text, "email"):   # checks of round 10 (reading): "email maria ... and cancel my
            return None                                # netflix" is two asks (the split, hook 8z), never one card
        return self.draft_from_request(person, text, now, req)

    def draft_from_request(self, person, text, now, req=None):
        """Starts a draft from an email request (read by code, or as the backstop for a model form that would have
        emailed the person themselves or refused). Returns the reply's reference, or None when the message names
        nobody else after all."""
        h = person["handle"]
        req = req or email_request(text) or self._draft_loose_request(text)
        if req is None:
            return None
        self.note(intent="draft")
        if ADMITS_FALSE.search(" ".join(text.split())):
            # (check of the live fix pass, fix9) the person says the claim is not true: no card (draft_v2 wrote "the
            # report is done. I sent it yesterday." for "... even though it isn't, say i sent it yesterday")
            return self.send(h, T.DRAFT_NOT_TRUE)
        if req.get("cc"):
            return self.send(h, T.DRAFT_ONE_AT_A_TIME)
        own, _ = self.store.email_of(h)
        if req.get("to") and own and req["to"] == own.lower() and not req.get("word") and not req.get("name"):
            return None   # their own address: the email to them, as before
        post = None
        if req.get("post"):
            post = self._draft_post_for(person, req["post"], text)
            if isinstance(post, str):   # nothing shown to point at, or a number past the answer
                return self.send(h, post)
        elif req.get("pron") and req.get("bare_pron"):
            post = self._draft_post_for(person, "it", text)
            if isinstance(post, str) or not post or not post.get("has_address"):
                return None   # "email them" with no post giving an address: not about someone else
        if req.get("two"):   # two addresses typed: which one (one person at a time)
            p_post = {k: v for k, v in post.items() if k != "has_address"} if post else None
            draft_id = self._new_draft_row(person, dict(req, to=None), p_post, now, text)
            self._draft_touch(h, draft_id, now, waiting="to", asked_at=now_iso(now))
            return self.send(h, T.draft_which_address(req["two"]))
        lead = ""
        to = req.get("to")
        if to is None and post and post.get("has_address"):
            lead = T.DRAFT_POST_ADDRESS + " "
        return self._draft_start_from(person, req, post, to, lead, now, text)

    def _draft_start_from(self, person, req, post, to, lead, now, text, job=None):
        p_post = dict(post) if post else None
        if p_post:
            p_post.pop("has_address", None)
        if to is None:
            draft_id = self._new_draft_row(person, req, p_post, now, text, job=job)
            p = json.loads(self._draft(draft_id)["parts"])
            return self._draft_ask_to(person, draft_id, p, now, lead=lead)
        return self.draft_start(person, "email", to=to, to_name=req.get("name"), to_word=req.get("word"),
                                request=req.get("request"), subject=req.get("subject"), post=p_post,
                                sources=self._draft_sources(p_post), now=now, text=text, job=job)

    def _new_draft_row(self, person, req, post, now, text, job=None):
        h = person["handle"]
        route = self._send_route(h)   # round 10, slice D
        p = {"greet_name": req.get("name"), "to_word": req.get("word"), "request": req.get("request"),
             "paragraphs": [], "post": post, "link": True, "extra": [], "changes": 0, "placeholders": [],
             "subject_set": bool(req.get("subject")),
             "body_from": "pick" if post and not req.get("request") else "words", "text": (getattr(self._tl, "norm_of", None) or text or "")[:REQUEST_MAX]}
        subj = req.get("subject") or self._draft_subject_of(p)
        draft_id = self.store.add_draft(h, "email", route, None, req.get("name"), subj, p,
                                        sources=self._draft_sources(post), at=now, job=job)
        self._log_draft(h, "draft.made", {"id": draft_id, "kind": "email", "route": route, "version": 0,
                                          "to_addr": None, "parts": p}, now=now)
        return draft_id

    @staticmethod
    def _draft_sources(post):
        return {"run_id": post.get("run_id"), "items": [post.get("item_id")]} if post else None

    def _draft_loose_request(self, text):
        """The backstop for a model form: an email verb and someone named anywhere in the message."""
        t = " ".join((text or "").split())
        if not EMAIL_WORD.search(t) and not ADDR_RE.search(t):
            return None
        word = OTHER_RE.search(t)
        name = re.search(rf"\bto\s+({_NAME})\b", t)
        if name and name.group(1) in NOT_NAMES:
            name = None
        addr = [a for a in addresses(t)]
        if not (word or name or addr):
            return None
        rest = t[word.end():] if word else ""
        para, subj, points = clause_paragraph(rest.strip())
        if points is None and re.search(r"\b(?:it|this|that|them|these)\b", t, re.I):
            points = "it"
        return {"to": addr[0] if len(addr) == 1 else None, "two": addr[:2] if len(addr) >= 2 else None,
                "word": re.sub(r"^(?:my|our)\s+", "", word.group(0), flags=re.I).lower() if word else None,
                "name": name.group(1) if name else None, "request": para, "subject": subj, "post": points,
                "cc": bool(CC.search(t))}

    def _draft_post_for(self, person, words, text):
        """The checked post block for the pick the words point at, by the existing rules (a number, "it", "them",
        a thing's name). A string is a reply line (nothing shown, a number past the answer)."""
        from . import profile as P
        from .followup import pick_number
        from .outputs import lead_only
        h = person["handle"]
        last = self._answer_seen(h) if hasattr(self, "_answer_seen") else self.store.last_answer(h)
        if not last or not last.get("items"):
            return T.DRAFT_NOTHING_SHOWN
        n = pick_number(words, len(last["items"])) if not re.match(r"^(?:it|this|that|them|these|those)$", words,
                                                                    re.I) else None
        self._tl.msg_text = words
        numbers = [n] if n else ([1] if not PLURAL.match(words) and lead_only(words, []) else None)
        picks, _whole, answer, problem = self._answer_picks(h, numbers, None, "pick")
        if problem:
            return problem
        picks = picks[:1] if not PLURAL.match(words) else picks[:3]
        rec = picks[0]
        view = self.view(person["library"])
        item = view.get(rec.get("item_id"))
        own = (item.raw_caption if item else "") or ""
        points = []
        if rec.get("item"):
            about = (rec["item"].get("about") or "").strip()
            if about:
                points.append(about + (f" (as of {rec['item']['stale_from']})" if rec["item"].get("stale_from")
                                       else ""))
        else:
            points = [x for x in ((rec.get("facts") or {}).get("key_points") or []) if isinstance(x, str)][:2]
        title = rec.get("title") if not rec.get("item") else f"{rec['title']} (from \"{rec.get('source_title')}\")" \
            if rec.get("source_title") else rec.get("title")
        sens = P.sensitive(title, own, *points)
        # (round 9 checks) a phone number in a checked line came from the post's own text: never in an email the
        # person sends (the composer already keeps addresses and links out of titles)
        if PHONE_RE.search(title or ""):
            title = f"A post from {rec['creator']}" if rec.get("creator") else "A post"
        points = [x for x in points if not PHONE_RE.search(x)]
        block = {"title": " ".join(str(title or "").split())[:150], "creator": rec.get("creator"),
                 "points": [] if sens else points[:2], "url": rec.get("url"), "sensitive": bool(sens),
                 "item_id": rec.get("item_id"), "run_id": (answer or {}).get("run_id"),
                 "has_address": bool(ADDR_RE.search(own))}
        if len(picks) > 1:   # "email them to sam@example.com": up to three posts, each its title and link
            block["more"] = [{"title": " ".join(str(x.get("title") or "").split())[:150], "url": x.get("url"),
                              "creator": x.get("creator")} for x in picks[1:]]
        return block

    # ---------- W1: a model form that would email the person, or refuse, when the message names someone else ----------
    def email_to_other(self, text, handle=None):
        """True when an email message names someone other than the person (a recipient word, a name after "to",
        or an address that is not theirs)."""
        t = " ".join((text or "").split())
        if not EMAIL_WORD.search(t) and not ADDR_RE.search(t):
            return False
        own = (self.store.email_of(handle)[0] or "").lower() if handle else ""
        mine = re.search(r"\b(?:to\s+me|me\s+at|myself|my\s+(?:own\s+)?(?:e-?mail|address))\b", t, re.I)
        if not mine and any(a != own for a in addresses(t)):
            return True
        if email_request(t) and not (own and addresses(t) == [own]):
            return True
        return bool(OTHER_RE.search(t) or re.search(rf"\bto\s+(?!(?:{'|'.join(NOT_NAMES)})\b){_NAME}\b", t))

    # ---------- W4: the operator's own mailbox (actions/mailbox.py) ----------
    def _mailbox_route(self, h):
        from .actions import mailbox
        return config.is_operator(h) and mailbox.settings() is not None and mailbox.refused_domain() is None

    def _mailbox_sender(self, h):
        from .actions import mailbox
        s = mailbox.settings()
        return s["address"] if s else None

    def _clock(self, dt, person):
        """'6:04 pm' on the person's own clock."""
        loc = dt.astimezone(ZoneInfo(person.get("timezone") or "America/New_York"))
        return f"{loc.hour % 12 or 12}:{loc.minute:02d} {'am' if loc.hour < 12 else 'pm'}"

    def _draft_last_sent(self, h, now):
        """The person's draft the mailbox sent (or may have) in the last 24 hours, or None."""
        row = self.store.one("SELECT * FROM drafts WHERE handle=? AND status IN ('sent','unknown') AND sent_at IS NOT "
                             "NULL ORDER BY id DESC LIMIT 1", (h,))
        if row and now - datetime.fromisoformat(row["sent_at"]) <= timedelta(hours=OPEN_HOURS):
            return row
        return None

    def _draft_just_finished(self, h, now):
        return self._draft_last_sent(h, now) is not None

    def _draft_send_again(self, person, now):
        """'send' after the mailbox sent the draft: one send per yes."""
        row = self._draft_last_sent(person["handle"], now)
        if row is None:
            return None
        self.note(intent="draft_send")
        if row["status"] == "unknown":   # (round 9 checks) the bot can't see whether it went: never "I sent"
            return self.send(person["handle"], T.MAILBOX_ERRORS["unknown"])
        return self.send(person["handle"], T.mailbox_already_sent(self._clock(datetime.fromisoformat(row["sent_at"]),
                                                                              person)))

    def draft_undo(self, person, now):
        """'undo' (handler._undo checks this first): a send in its hold stops; one the server accepted in the last
        10 minutes cannot be taken back, and the reply says where it went. None when neither."""
        from .todos import UNDO_WINDOW
        h = person["handle"]
        hold = self.store.get_state(f"sendhold:{h}")
        if hold:
            row = self._draft(hold["draft_id"])
            self.store.set_state(f"sendhold:{h}", None)
            if row and row["status"] == "held":
                self.store.update_draft(row["id"], status="link_shown")
                self._draft_touch(h, row["id"], now)
                self.note(intent="undo")
                return self.send(h, T.MAILBOX_STOPPED)
        row = self._draft_last_sent(h, now)
        if row and now - datetime.fromisoformat(row["sent_at"]) <= UNDO_WINDOW:
            lw = self.store.get_state(f"lastwrite:{h}")
            if not lw or datetime.fromisoformat(lw["at"]) <= datetime.fromisoformat(row["sent_at"]):
                self.note(intent="undo")
                if row["status"] == "unknown":   # (round 9 checks) never "it went" when the bot can't see that
                    return self.send(h, T.mailbox_cant_stop_unknown(_masked(row.get("to_addr"), row.get("to_domain"))))
                return self.send(h, T.mailbox_cant_unsend(row["to_addr"] or row["to_domain"],
                                                          self._clock(datetime.fromisoformat(row["sent_at"]), person)))
        return None

    def _draft_stop_hold(self, h, row, now):
        """Stops a send waiting in its hold for this draft. True when one was stopped."""
        hold = self.store.get_state(f"sendhold:{h}")
        if not hold or (row and hold.get("draft_id") != row["id"]):
            return False
        self.store.set_state(f"sendhold:{h}", None)
        if row:
            self.store.update_draft(row["id"], status="link_shown")
        return True

    def _draft_send_word(self, person, d, now):
        """'send' on route L: the bot cannot send from the person's address. On the mailbox route (W4): the yes for
        the exact version last shown, then the hold."""
        from .actions import mailbox
        h = person["handle"]
        if config.is_operator(h) and mailbox.refused_domain():
            return self.send(h, T.MAILBOX_OUTLOOK)
        left = placeholders_left(d)
        if left:   # no link was given and nothing can be sent while one is left, on either route
            return self.send(h, T.fill_first(left[0]))
        # ---------- round 10, slice D: the route is read again at "send"; a change shows the card again ----------
        cur = self._send_route(h)
        if cur != d["route"]:
            return self._draft_route_changed(person, d, cur, now)
        if cur != "mailbox":
            return self.send(h, self._switch_on_line(h) if config.is_operator(h) else T.DRAFT_SEND_LINK)
        # ---------- end round 10, slice D ----------
        return self._mailbox_send_word(person, d, now)

    # ---------- round 10, slice D: the send route (D1), the switch-on line (D4) ----------
    SEND_ROUTES = ("send_as", "mailbox", "link")   # send_as (the person's own connected mailbox) is round 11

    def _send_route(self, h):
        """How a draft for this person goes: "mailbox" (the operator, with A-013's settings: the bot sends after
        "send") or "link" (the person taps the mailto: link). Read when the card is made and again at "send"."""
        return "mailbox" if self._mailbox_route(h) else "link"

    def _send_as(self, person, d, now):
        raise NotBuilt("send_as")

    def _switch_on_line(self, h):
        """D4: what the operator needs to do so "send" sends (on the test page: the Connections panel)."""
        from . import panel
        state = panel.sending_state()
        if state in ("outlook", "host", "nobody"):
            return T.panel_sending(state)
        return T.SEND_SWITCH_ON_PAGE if getattr(self.channel, "name", "") == "web" else T.SEND_SWITCH_ON

    def _draft_send_asked(self, person, d, now):
        """'can you send it for me': a question, never the yes. What "send" would do now, in one line."""
        h = person["handle"]
        left = placeholders_left(d)
        if left:
            return self.send(h, T.fill_first(left[0]))
        if self._send_route(h) == "mailbox":
            if d["route"] != "mailbox":
                return self._draft_route_changed(person, d, "mailbox", now)
            return self.send(h, T.DRAFT_SEND_ASKED)
        return self.send(h, self._switch_on_line(h) if config.is_operator(h) else T.SEND_FOR_ME_TESTER)

    def _draft_route_changed(self, person, d, cur, now):
        """The route at "send" is not the one the card showed (sending was switched on or off meanwhile): the card
        again with the route as it is now, and no yes taken."""
        h = person["handle"]
        if d["status"] == "held":
            self._draft_stop_hold(h, self._draft(d["id"]), now)
        self._draft_show(person, d["id"], now)
        return self.send(h, T.SEND_ROUTE_CHANGED if cur == "mailbox" else T.SEND_ROUTE_GONE)
    # ---------- end round 10, slice D ----------

    def _mailbox_send_word(self, person, d, now):
        """W4: "send" is the yes for the version last shown, and only that version: its token is made here from the
        draft's id, version and the hash of the text the card showed. The send waits SEND_HOLD_MIN minutes."""
        from .actions import make_yes_token, over_cap
        from .actions.base import Ctx
        h = person["handle"]
        if d["status"] == "held":
            hold = self.store.get_state(f"sendhold:{h}") or {}
            if hold.get("draft_id") == d["id"]:
                return self.send(h, T.mailbox_already_held(self._clock(datetime.fromisoformat(hold["due_at"]),
                                                                       person)))
        left = placeholders_left(d)
        if left:
            return self.send(h, T.fill_first(left[0]))
        if not d.get("to_addr"):
            return self.send(h, T.MAILBOX_NEEDS_TO)
        other = self.store.get_state(f"sendhold:{h}") or {}
        if other.get("draft_id") not in (None, d["id"]):
            # (round 9 checks) one send waits at a time: a second "send" would replace the first one's hold, and the
            # first email, already promised for a time, would silently never go
            first = self._draft(other["draft_id"])
            if first and first["status"] == "held":
                return self.send(h, T.mailbox_other_waiting(first["to_addr"] or first.get("to_domain") or "them",
                                                            self._clock(datetime.fromisoformat(other["due_at"]),
                                                                        person)))
        shown = datetime.fromisoformat(d["shown_at"]) if d.get("shown_at") else None
        if shown is None or now - shown > timedelta(minutes=FRESH_MINUTES):
            when = self._clock(shown or now, person)
            self._draft_show(person, d["id"], now)
            return self.send(h, T.mailbox_stale(when))
        ctx = Ctx(bot=self, person=person, answer={}, picks=[], kind="draft", now=now, tz=person["timezone"])
        cap = over_cap("mailbox.send", ctx)
        if cap is not None:
            from .drafts import mailto as _mailto
            return self.send(h, T.mailbox_cap(cap, _mailto(d["to_addr"], d["subject"], d["body"])))
        token = make_yes_token(d["id"], d["version"], d["text_hash"])
        due = now + timedelta(minutes=config.SEND_HOLD_MIN)
        self.store.update_draft(d["id"], status="held")
        self.store.set_state(f"sendhold:{h}", {"draft_id": d["id"], "version": d["version"], "token": token,
                                               "due_at": now_iso(due), "at": now_iso(now)})
        self._draft_touch(h, d["id"], now)
        return self.send(h, T.mailbox_held(d["to_addr"], self._clock(due, person)))

    def _draft_tick_holds(self, now):
        """Every tick: each hold that is due is sent (or, more than 15 minutes late, not sent and the person asked
        again); a send cut off by a restart is never tried again. Returns the number sent."""
        n = 0
        for r in self.store.q("SELECT key, value FROM state WHERE key LIKE 'sendhold:%'"):
            hold = json.loads(r["value"]) if r["value"] else None
            if not hold:
                continue
            h = r["key"].split(":", 1)[1]
            if now < datetime.fromisoformat(hold["due_at"]):
                continue
            with self.lock_for(h):
                n += self._draft_send_due(h, hold, now)
        for row in self.store.q("SELECT * FROM drafts WHERE status='sending'"):
            started = datetime.fromisoformat(row["sent_at"]) if row.get("sent_at") else None
            if started is None or now - started > timedelta(minutes=2):
                with self.lock_for(row["handle"]):
                    self.store.update_draft(row["id"], status="unknown", done_at=now_iso(now))
                    self.store.x("UPDATE action_log SET action='mailbox.send', status='unknown' WHERE "
                                 "action='mailbox.attempt' AND status='sending' AND ref=?", (str(row["id"]),))
                    person = self.store.person(row["handle"])
                    if person:
                        self.send(row["handle"], T.mailbox_restarted(_masked(row.get("to_addr"),
                                                                             row.get("to_domain"))))
        return n

    def _draft_send_due(self, h, hold, now):
        from .actions import perform
        from .actions.base import Ctx
        from .actions.mailbox import SendError
        if self.store.get_state(f"sendhold:{h}") != hold:
            return 0   # stopped or replaced meanwhile
        self.store.set_state(f"sendhold:{h}", None)
        row = self._draft(hold["draft_id"])
        person = self.store.person(h)
        if not row or not person or row["status"] != "held" or row["version"] != hold["version"]:
            return 0   # changed, cancelled or sent: that yes was for another version
        # ---------- round 10, slice D: sending was switched off during the hold: nothing goes, and the person hears it
        if self._send_route(h) != "mailbox":
            self.store.update_draft(row["id"], status="link_shown")
            self._draft_touch(h, row["id"], now)
            self._draft_show(person, row["id"], now, lead=T.SEND_ROUTE_GONE_HELD + "\n\n")
            return 0
        # ---------- end round 10, slice D ----------
        due = datetime.fromisoformat(hold["due_at"])
        if now - due > timedelta(minutes=config.SEND_LATE_MIN):
            self.store.update_draft(row["id"], status="link_shown")
            self._draft_touch(h, row["id"], now)
            self.send(h, T.mailbox_offline(row["to_name"] or row["to_addr"], self._clock(due, person)))
            return 0
        if any(json.loads(x["detail"] or "{}").get("token") == hold["token"] for x in
               self.store.q("SELECT detail FROM action_log WHERE handle=? AND action IN ('mailbox.send',"
                            "'mailbox.attempt') AND status IN ('sending','done','unknown')", (h,))):
            return 0   # one send per yes
        p = json.loads(row["parts"] or "{}")
        detail = {"kind": row["kind"], "route": "mailbox", "version": row["version"],
                  "recipient_domain": None if row["kind"] == "notice" else row["to_domain"],
                  "body_from": p.get("body_from") or "words", "token": hold["token"]}
        self.store.update_draft(row["id"], status="sending", sent_at=now_iso(now))   # before SMTP: never twice
        # logged before SMTP as an attempt (not counted against the day's cap until it has a result)
        log_id = self.store.log_action(h, None, None, "mailbox.attempt", "sending", ref=str(row["id"]),
                                       detail=detail, at=now)
        ctx = Ctx(bot=self, person=person, answer={}, picks=[], kind="draft", now=now, tz=person["timezone"])
        try:
            o = perform("mailbox.send", ctx, {"draft_id": row["id"]}, yes_token=hold["token"])
        except SendError as e:
            kind = e.kind
            st = "unknown" if kind == "unknown" else "failed"
            self.store.update_draft(row["id"], status=st,   # a failed one stays open: "send" can try again
                                    **({"done_at": now_iso(now)} if st == "unknown" else {"sent_at": None}))
            self.store.update_action(log_id, st, dict(detail, error=kind), action="mailbox.send")
            if st != "unknown":
                self._draft_touch(h, row["id"], now)
            print(f"mailbox: send {st} ({kind})", file=__import__("sys").stderr)
            self.send(h, T.MAILBOX_ERRORS[kind])
            return 0
        except Exception as e:  # noqa: BLE001 - refused by the registry, or anything else: nothing was sent
            self.store.update_draft(row["id"], status="link_shown", sent_at=None)
            self.store.update_action(log_id, "failed", dict(detail, error=type(e).__name__), action="mailbox.send")
            print(f"mailbox: not sent ({type(e).__name__})", file=__import__("sys").stderr)
            self.send(h, T.MAILBOX_ERRORS["reach"])
            return 0
        if o.status != "done":   # over a cap at the last moment: not sent, and said
            self.store.update_draft(row["id"], status="link_shown", sent_at=None)
            self.store.update_action(log_id, "skipped", detail, action="mailbox.send")
            self.send(h, o.line or T.MAILBOX_ERRORS["reach"])
            return 0
        self.store.update_draft(row["id"], status="sent", done_at=now_iso(now))
        self.store.update_action(log_id, "done", detail, action="mailbox.send")
        if (self.store.get_state(f"draft_open:{h}") or {}).get("id") == row["id"]:
            # (round 9 checks) only this card closes: a newer card the person opened meanwhile stays open, so its
            # "send" is never answered with "I already sent that one"
            self.store.set_state(f"draft_open:{h}", None)
        # ---------- round 10, slice D: a notice's receipt names the merchant; the follow-up offer comes with it ------
        if row["kind"] == "notice":
            head = T.notice_accepted(p.get("merchant"), row["to_addr"], self._clock(now, person))
        else:
            head = T.mailbox_accepted(row["to_addr"], self._clock(now, person))
        self.send(h, head + self._draft_job_done(row, "bot_sent", now))
        # ---------- end round 10, slice D ----------
        return 1

    # ---------- A5: a real draft in the operator's Drafts folder (actions/mailbox_imap.py) ----------
    def _mailbox_drafts_on(self, h):
        from .actions import mailbox_imap
        return config.is_operator(h) and mailbox_imap.settings() is not None

    def _save_to_drafts(self, person, d, now):
        """'save it as a draft' with a card open: the card's version as last shown goes to their Drafts folder
        (recipient, subject and body kept). The card stays open, so "send" still works by W4's rules."""
        h = person["handle"]
        if not self._mailbox_drafts_on(h):
            # (round 9 live fix pass, finding 107) the truth in one line, and the version last shown's link again
            self.note(intent="draft_save_link")
            if not d.get("version") or d["state"].get("waiting"):
                return self.send(h, T.DRAFT_NOT_READY)
            left = placeholders_left(d)
            if left:   # no link while a placeholder is left
                return self.send(h, T.fill_first(left[0]))
            p = d["parts"]
            cut = (T.DRAFT_REST_IN_POST.format(url=p["post"]["url"]) if p.get("post") and p["post"].get("url")
                   and p.get("link", True) and not p.get("no_post") else None)
            self._draft_touch(h, d["id"], now)
            return self.send(h, T.draft_save_link(mailto(d.get("to_addr") or "", d["subject"], d["body"], cut)))
        self.note(intent="mailbox_draft")
        if not d.get("version"):
            return self.send(h, T.DRAFT_NOT_READY)
        from .actions.base import Ctx
        ctx = Ctx(bot=self, person=person, answer={}, picks=[], kind="draft", now=now, tz=person["timezone"])
        return self._mailbox_draft_run(person, ctx, {"draft_id": d["id"]}, d.get("to_addr"), now, card=True)

    def mailbox_reads(self, person, text, now):
        """'put this in my email', 'save it as a draft', 'put the second one in my drafts', 'draft it in my gmail',
        with no card open: for the operator with a mailbox, the answer (or the pick) as a draft in their Drafts
        folder, addressed to them. For everyone else None (the old way: the email to them, or W3's link)."""
        h = person["handle"]
        m = MAILBOX_SAVE.match(" ".join((text or "").split()))
        if not m or not self._mailbox_drafts_on(h):
            return None
        from .actions import mailbox_imap
        from .actions.base import Ctx
        from .followup import pick_number
        last = self._answer_seen(h) or self.store.last_answer(h)
        if not last or not last.get("items"):
            return self.send(h, T.NOTHING_TO_ACT_ON)
        n = pick_number(m.group("what") or "", len(last["items"])) if m.group("what") and \
            not re.match(r"^(?:it|this|that|them|these)$", m.group("what"), re.I) else None
        self._tl.msg_text = text
        picks, whole, answer, problem = self._answer_picks(h, [n] if n else None, None, "pick")
        if problem:
            return self.send(h, problem)
        self.note(intent="mailbox_draft")
        ctx = Ctx(bot=self, person=person, answer=answer, picks=picks, whole=whole, run_id=answer.get("run_id"),
                  rule_id=answer.get("rule_id"), kind="act_on_last", now=now, tz=person["timezone"], request_text=text)
        return self._mailbox_draft_run(person, ctx, {}, mailbox_imap.settings()["address"], now, card=False)

    def _mailbox_draft_run(self, person, ctx, params, to, now, card):
        from .actions import perform
        from .actions.mailbox_imap import DraftError
        h = person["handle"]
        detail = {"recipient_domain": domain_of(to), "card": card}
        try:
            o = perform("mailbox.draft", ctx, params)
        except DraftError as e:
            self.store.log_action(h, None, None, "mailbox.draft", "failed", detail=dict(detail, error=e.kind), at=now)
            print(f"mailbox draft: not saved ({e.kind})", file=__import__("sys").stderr)
            return self._mailbox_draft_fallback(person, ctx, T.MAILBOX_DRAFT_FAILED[e.kind], card, now)
        except Exception as e:  # noqa: BLE001 - nothing was saved
            self.store.log_action(h, None, None, "mailbox.draft", "failed",
                                  detail=dict(detail, error=type(e).__name__), at=now)
            print(f"mailbox draft: not saved ({type(e).__name__})", file=__import__("sys").stderr)
            return self._mailbox_draft_fallback(person, ctx, T.MAILBOX_DRAFT_FAILED["reach"], card, now)
        if o.status != "done":   # over the day's cap
            return self._mailbox_draft_fallback(person, ctx, o.line, card, now)
        uid, folder = (o.detail or {}).get("uid"), (o.detail or {}).get("folder")
        self.store.log_action(h, None, None, "mailbox.draft", "done", detail=dict(detail, undo=bool(uid)), at=now)
        if uid:
            self._wrote(h, "mailbox_draft", "the draft in your Drafts folder", {"folder": folder, "uid": uid})
        else:
            self._wrote_final(h, "a draft in your Drafts folder")
        return self.send(h, T.mailbox_drafted(to, bool(uid)))

    def _mailbox_draft_fallback(self, person, ctx, why, card, now):
        h = person["handle"]
        if card:
            return self.send(h, why + " " + T.MAILBOX_DRAFT_USE_LINK)
        from .actions import email as email_action
        to, _ = self.store.email_of(h)
        o = email_action.self_link(ctx, email_action.content(ctx), to)
        return self.send(h, why + "\n" + o.line)

    def mailbox_undraft(self, h, u):
        """'undo' after a draft was saved: deletes that one UID from that folder. Returns what was undone, in words."""
        from .actions import mailbox_imap
        s = mailbox_imap.settings()
        try:
            if s is None:
                raise mailbox_imap.DraftError("reach")
            mailbox_imap.delete_draft(s, u["folder"], u["uid"])
        except Exception as e:  # noqa: BLE001 - said plainly; nothing else is touched
            print(f"mailbox draft: not deleted ({type(e).__name__})", file=__import__("sys").stderr)
            return T.MAILBOX_UNDRAFT_FAILED
        self.store.log_action(h, None, None, "mailbox.undraft", "done", detail={}, at=self.clock())
        return T.MAILBOX_UNDRAFTED

    # ---------- A6: the model writes the words (config.DRAFT_MODEL); code checks every word before it is shown ----
    def _draft_model_ok(self, person, now):
        """The model may write for this person now: on, under the spend caps, and under 6 drafts or rewrites today."""
        if not config.DRAFT_MODEL:
            return False
        from .actions import local_day_bounds
        start, end = local_day_bounds(now, person.get("timezone") or "America/New_York")
        if self.store.actions_in(person["handle"], ["draft.model"], start, end) >= config.DRAFT_MODEL_PER_DAY:
            return False
        return not self._over_cap(person)

    def _draft_model_call(self, person, p, row, sign, now, change=None, current=None):
        """One draft_v1 call and, if a check fails, one retry naming the failure. Returns the checked form or None
        (then the code-built words stand and nobody is told about the model)."""
        h = person["handle"]
        form, attempts, first = model_write(p, sign, h, change=change, current=current)
        self._tl.draft_call_failed = not form and first == ["the call failed"]
        self.store.log_action(h, None, None, "draft.model", "done" if form else "fallback", ref=str(row["id"]),
                              detail={"attempts": attempts, "used": bool(form), "rewrite": bool(change),
                                      "first_try": not first}, at=now)
        return form

    def _draft_model_body(self, person, draft_id, now):
        """A new draft: the model writes the words, under the checks; else the code-built words stand."""
        if not self._draft_model_ok(person, now):
            return None
        row = self._draft(draft_id)
        p = json.loads(row["parts"])
        if p.get("paragraphs"):   # words given as they are (a notice): never rewritten
            return None
        form = self._draft_model_call(person, p, row, self._draft_sign_name(person), now)
        if not form:
            return None
        p.update(model_body=form["body"], greeting=form["greeting"], closing=form["closing"], body_from="model")
        fields = {"parts": p}
        if not p.get("subject_set") and form["subject"] and not (p.get("post") and not p.get("request")):
            # (an email that only passes on a post keeps the post's checked title as its subject)
            fields["subject"] = form["subject"]
        self.store.update_draft(draft_id, **fields)
        return True

    def _draft_model_rewrite(self, person, d, t, now):
        """'make it shorter', 'in Spanish': the model rewrites the last shown version under the same checks. Returns
        the new parts, or None (then the fixed line)."""
        if not self._draft_model_ok(person, now) or d["kind"] != "email":
            return None
        p = dict(d["parts"])
        current = render_body(p, "")
        form = self._draft_model_call(person, p, d, self._draft_sign_name(person), now, change=t, current=current)
        if not form:
            return None
        p.update(model_body=form["body"], greeting=form["greeting"], closing=form["closing"], body_from="model",
                 request=None, extra=[])
        return p

    # ---------- W10 and slice B ----------
    def draft_from_todo(self, person, todo, now=None, job=None):
        """A to-do that is an email ("Email landlord about sink"): the draft starts, asking for the address. None
        when the to-do is not an email. job "todo:<id>" (W10): the to-do is ticked off once the email is sent."""
        now = now or self.clock()
        text = (todo or {}).get("text") or ""
        m = re.match(rf"^\W*e-?mail\s+(?:(?:my|the)\s+)?(?P<who>(?:{PEOPLE_WORDS})s?|{_NAME})\b\s*(?P<rest>.*)$",
                     text, re.I)
        if not m:
            return None
        who = m.group("who")
        is_word = bool(re.fullmatch(rf"(?:{PEOPLE_WORDS})s?", who, re.I))
        para, subj, _ = clause_paragraph(m.group("rest"))
        req = {"to": None, "word": who.lower() if is_word else None, "name": None if is_word else cap(who),
               "request": para, "subject": subj}
        if (todo or {}).get("item_id"):
            # (round 9 checks) a to-do that came from a saved post holds the post's words (its title, a caption line):
            # they never name who it goes to. The person is asked, with no name from the post
            req.update(word=None, name=None)
        return self._draft_start_from(person, req, None, None, "", now, text, job=job)

    # ---------- upkeep (Bot.tick) ----------
    def drafts_tick(self, now):
        """Every tick: a send whose hold is over goes out (W4), and the address and words of a draft finished more
        than 7 days ago are cleared (the row keeps the domain and status). Returns the number sent."""
        self.store.clear_old_drafts(now - timedelta(days=CLEAR_DAYS))
        return self._draft_tick_holds(now)


def _masked(addr, domain=None):
    """'m***@example.com': an address said back when the bot is not sure what happened."""
    if addr and "@" in addr:
        local, dom = addr.split("@", 1)
        return f"{local[:1]}***@{dom}"
    return f"someone at {domain}" if domain else "them"


def _masked_dots(addr):
    """'m•••@example.com' (round 10, slice W): the person's own address said back after an email to them."""
    local, _, dom = (addr or "").partition("@")
    return f"{local[:1]}•••@{dom}" if dom else "your address"


# ---------- module-level entry points for the other slices (the bot is the first argument) ----------
def start(bot, person, kind, to=None, to_name=None, subject=None, paragraphs=(), post=None, placeholders=(), job=None,
          now=None, **more):
    return bot.draft_start(person, kind, to=to, to_name=to_name, subject=subject, paragraphs=paragraphs, post=post,
                           placeholders=placeholders, job=job, now=now, **more)


def open_draft(bot, handle):
    return bot.open_draft(handle)


def from_todo(bot, person, todo, now=None, job=None):
    return bot.draft_from_todo(person, todo, now, job=job)
